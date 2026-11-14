#!/usr/bin/env python3
"""Confidence: one score per claim, computed by a fixed formula from the evidence. No AI picks a number.

Inputs, all in this repo:
  dossier/<branch>.json         each claim's `support` (evidence file + the kind of check it is used as),
                                `combine` (any | all), `contradicted_by`, `depends_on`
  evidence/<branch>/*.json      `provides` (the kinds of check this file can back), `produced_by`,
                                `contract_changes` (a user-visible promise the check showed changed)
  evidence/<branch>/tripwires.json   which hunks touch which project contract
  evidence/<branch>/replay.json      (optional) recorded commands re-run on a clean machine
  context/project.json          contract maintainers
  context/history.json          (optional) maintainers' past statements, as rules with links

The formula (also printed into the output, so the page can show it):
  base      the kind of check: rebuilt-and-compared 90, model proof 80, flip test 75, undo test 75,
            experiment on the real code 60, number from a tool 40, no check 15
  old vs new  run the old and new code on the same inputs (isolation.json). Same output only speaks for
            changed lines that ran, so the points follow coverage: 30 + 45 x (changed lines reached /
            trackable changed lines), at most 75; no trackable line: 30; any unexplained difference: 15.
            It stays below rebuilt-and-compared because it tries a sample of inputs, not every file.
  hand      evidence a person or agent ran by hand: -10
  undo      a separate undo test backs the same claim: +5
  replay    the file was re-run on a clean machine and matched: +5; did not match: -30
  combine   any: the best supporting file counts; all (a chain): the weakest one counts
  contra    evidence contradicts the claim: score is at most 25
  bands     high >= 80, medium 50-79, low < 50

The gate is separate from the score. A claim NEEDS OWNER when a check shows a user-visible promise
changed (evidence `contract_changes`), the change's diff parts overlap the claim's, and tripwires.json
shows those hunks touch that contract; or when the claim depends on a claim that needs an owner.
A claim whose lines only partly overlap such a change gets `shares_lines_with`, not the gate.
A high score never clears the gate: being sure a promise changed does not make the change acceptable.

Checks it enforces (exit 1 on failure): every `support` file is listed in `evidence`, exists, and
`provides` the kind the claim uses it as.

    python3 review/scripts/confidence.py --branch ju26-issue-2283 [--write]
    python3 review/scripts/confidence.py --all --write
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REVIEW = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from claim_coverage import parse_part, covered  # noqa: E402

BRANCHES = ["ju26-issue-2234", "ju26-issue-2283", "ju26-issue-2297"]
KIND = {
    "rebuild-compare": (90, "rebuilt and compared: identical"),
    "proof-model": (80, "model proved, and model matched the real code on every tested input"),
    "flip-test": (75, "test fails before the change, passes after"),
    "revert-test": (75, "undo only this change: a test fails"),
    "probe": (60, "experiment on the real code"),
    "count": (40, "number from a tool"),
    "old-vs-new-run": (None, "old and new code, same inputs: no unexplained difference"),  # points: old_vs_new_points()
}
OVN_FLOOR, OVN_SPAN, OVN_UNEXPLAINED = 30, 45, 15
NONE = (15, "no check backs it")
HAND, UNDO, REPLAY_OK, REPLAY_BAD, CONTRA_CAP = -10, 5, 5, -30, 25
FORMULA = {
    "kinds": {k: v[0] for k, v in KIND.items() if v[0] is not None} | {"none": NONE[0]},
    "old_vs_new": {"floor": OVN_FLOOR, "span": OVN_SPAN, "max": OVN_FLOOR + OVN_SPAN,
                   "unexplained": OVN_UNEXPLAINED,
                   "rule": "floor + span x changed lines reached / trackable changed lines; "
                           "any unexplained difference: unexplained"},
    "hand": HAND, "undo_bonus": UNDO, "replay_match": REPLAY_OK, "replay_mismatch": REPLAY_BAD,
    "contradicted_cap": CONTRA_CAP, "bands": {"high": 80, "medium": 50},
    "combine": "any = best supporting file; all = weakest",
}


def old_vs_new_points(e):
    """Points for an old-vs-new run, from its own coverage numbers: (points, label)."""
    d = e.get("details") or {}
    c = d.get("coverage") or {}
    reached, trackable = int(c.get("reached") or 0), int(c.get("trackable") or 0)
    if int(d.get("unexplained_total_items") or 0) or d.get("unexplained"):
        return OVN_UNEXPLAINED, "old and new code differ where no rule expects it"
    if not trackable:
        return OVN_FLOOR, "old and new code, same output; no changed line could be tracked"
    pts = OVN_FLOOR + round(OVN_SPAN * reached / trackable)
    same = "every difference matches a rule" if d.get("explained") else "same output"
    return pts, f"old and new code, {same}; {reached} of {trackable} changed lines ran"


def kind_points(kind, e):
    return old_vs_new_points(e) if kind == "old-vs-new-run" else KIND[kind]


def band(s):
    return "high" if s >= 80 else "medium" if s >= 50 else "low"


def load(p):
    return json.load(open(os.path.join(REVIEW, p)))


def overlaps(parts_a, parts_b):
    pb = [parse_part(p) for p in parts_b]
    for p in parts_a:
        f, lo, hi = parse_part(p)
        if covered(f, lo or 1, hi or 10**9, pb):
            return True
    return False


def score_branch(branch, project, history, errors):
    dossier = load(f"dossier/{branch}.json")
    trips = load(f"evidence/{branch}/tripwires.json")["details"]["trips"]
    rp = os.path.join(REVIEW, f"evidence/{branch}/replay.json")
    replay = json.load(open(rp))["details"]["files"] if os.path.exists(rp) else {}
    maint = {c["id"]: c["maintainers"] for c in project["contracts"]}
    rules = (history or {}).get("rules", [])
    ev_cache = {}

    def ev(path):
        if path not in ev_cache:
            full = os.path.join(REVIEW, path)
            ev_cache[path] = json.load(open(full)) if os.path.exists(full) else None
        return ev_cache[path]

    out = {}
    for c in dossier["claims"]:
        cid, support = c["id"], c.get("support", [])
        signals, scored = [], []
        has_undo = any(s["kind"] == "revert-test" for s in support)
        for s in support:
            f, kind = s["file"], s["kind"]
            e = ev(f)
            if f not in c.get("evidence", []):
                errors.append(f"{cid}: support {f} is not in its evidence list")
            if e is None:
                errors.append(f"{cid}: {f} does not exist"); continue
            if kind not in e.get("provides", []):
                errors.append(f"{cid}: uses {f} as {kind}, but the file provides only {e.get('provides')}")
                continue
            pts, label = kind_points(kind, e)
            parts = [{"text": label, "delta": pts}]
            if e.get("produced_by") == "hand":
                parts.append({"text": "run by hand, not by a script", "delta": HAND})
            if has_undo and kind != "revert-test":
                parts.append({"text": "an undo test confirms it", "delta": UNDO})
            r = replay.get(os.path.basename(f))
            if r == "match":
                parts.append({"text": "re-run on a clean machine: same result", "delta": REPLAY_OK})
            elif r == "mismatch":
                parts.append({"text": "re-run on a clean machine: different result", "delta": REPLAY_BAD})
            total = max(0, min(100, sum(p["delta"] for p in parts)))
            scored.append(total)
            signals.append({"file": f, "kind": kind, "summary": e.get("summary", ""),
                            "produced_by": e.get("produced_by"), "replay": r or "not re-run",
                            "parts": parts, "score": total})
        if scored:
            score = min(scored) if c.get("combine") == "all" else max(scored)
            how = "weakest link of a chain" if c.get("combine") == "all" else "best supporting check"
        else:
            score, how = NONE[0], NONE[1]
        contra = [{"file": f, "summary": (ev(f) or {}).get("summary", "")} for f in c.get("contradicted_by", [])]
        if contra and score > CONTRA_CAP:
            score = CONTRA_CAP
        out[cid] = {"score": score, "band": band(score), "how": how, "signals": signals,
                    "contradicted_by": contra, "gate": None, "depends_on": c.get("depends_on", [])}

        # gate: a check shows a promise changed, on these diff parts, and tripwires agree the hunks touch it
        for s in support + [{"file": f} for f in c.get("contradicted_by", [])]:
            for ch in (ev(s["file"]) or {}).get("contract_changes", []):
                own = [p for p in c.get("diff_parts", []) if not p.startswith("tests/")]
                if not overlaps(own, ch["diff_parts"]):
                    continue
                if not all(overlaps([p], ch["diff_parts"]) for p in own):
                    # the claim's lines include the changed promise, but the claim is about more than that
                    out[cid].setdefault("shares_lines_with", []).append(ch["what"])
                    continue
                hunks = [t["hunk"] for t in trips.get(ch["contract"], []) if overlaps([t["hunk"]], ch["diff_parts"])]
                if not hunks:
                    errors.append(f"{cid}: {s['file']} reports a {ch['contract']} change, but no tripwire hunk matches")
                    continue
                m = maint.get(ch["contract"], {})
                out[cid]["gate"] = {
                    "contract": ch["contract"], "change": ch["what"], "shown_by": s["file"],
                    "hunks": hunks,
                    "owner": (m.get("top") or [{}])[0].get("name"),
                    "owner_basis": f"most commits on the {ch['contract']} paths at base ({m.get('commits')} commits)",
                    "rules": [{"id": r["id"], "rule": r["rule"], "sources": r["sources"][:2]}
                              for r in rules if r.get("concern") == ch["contract"]
                              or (ch["contract"] == "generated" and r.get("concern") in ("public-api", "compat-breaking"))][:3],
                }
                break
            if out[cid]["gate"]:
                break

    for cid, o in out.items():  # inherited gates
        for d in o["depends_on"]:
            if not o["gate"] and out.get(d, {}).get("gate"):
                o["gate"] = dict(out[d]["gate"], inherited_from=d)

    # the old-vs-new run of this branch, scored on its own, so the page can show its score
    iso, ovn = f"evidence/{branch}/isolation.json", None
    if ev(iso):
        pts, label = old_vs_new_points(ev(iso))
        cov = (ev(iso).get("details") or {}).get("coverage") or {}
        ovn = {"file": iso, "score": pts, "band": band(pts), "label": label,
               "reached": cov.get("reached"), "trackable": cov.get("trackable")}

    counts = {b: sum(1 for o in out.values() if o["band"] == b) for b in ("high", "medium", "low")}
    gated = sorted(k for k, o in out.items() if o["gate"])
    return {
        "check": "confidence",
        "branch": branch,
        "base": dossier["base"],
        "command": f"python3 review/scripts/confidence.py --branch {branch} --write",
        "result": "pass",
        "summary": f"{len(out)} claims: {counts['high']} high, {counts['medium']} medium, {counts['low']} low; "
                   f"{len(gated)} need an owner ({', '.join(gated) or 'none'})",
        "details": {"formula": FORMULA, "claims": out, "old_vs_new": ovn, "replayed": bool(replay),
                    "history_rules_available": len(rules)},
        "tool_versions": {"python": sys.version.split()[0]},
        "produced_by": "script",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--branch")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    project = load("context/project.json")
    hp = os.path.join(REVIEW, "context/history.json")
    history = json.load(open(hp)) if os.path.exists(hp) else None
    errors = []
    for b in (BRANCHES if a.all else [a.branch]):
        res = score_branch(b, project, history, errors)
        print(res["summary"])
        for cid, o in res["details"]["claims"].items():
            g = f"  NEEDS OWNER ({o['gate']['contract']})" if o["gate"] else ""
            print(f"  {cid} {o['score']:3} {o['band']:6}{g}")
        if errors:
            res["result"] = "fail"
        if a.write:
            with open(os.path.join(REVIEW, f"evidence/{b}/confidence.json"), "w") as f:
                json.dump(res, f, indent=2, ensure_ascii=False)
                f.write("\n")
    for e in errors:
        print("ERROR", e, file=sys.stderr)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
