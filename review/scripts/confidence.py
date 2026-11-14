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
            experiment on the real code 60, code metric before vs after 40, no check 15
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

The gate is separate from the score. It reads old vs new (isolation.json: the old and the new code run
on the same inputs that existed before the change, with line coverage) and works line by line:
  ran, same output       no gate: evidence that nothing broke on those inputs
  ran, output differs    NEEDS OWNER when the difference changes a promise users rely on. The kind of
                         difference picks the promise: a project warning (MsgPackNNN) appears or goes away
                         -> diagnostics; a generated file that existed before now differs -> generated; a new
                         compiler error -> generated. A crash that goes away is a fix, not a promise change.
                         The gate goes to the claim the matching rule names; a difference no rule explains
                         goes to every claim whose lines that input ran.
  never ran              NEEDS OWNER when the line is in a hunk that tripwires.json ties to a promise:
                         "no input that existed before the change runs this line".
A planned difference still gates: a rule that explains a difference names a claim, it does not clear it.
An experiment that records `contract_changes` gates too (its claim's lines must lie inside the change and
tripwires must agree); a claim whose lines only partly overlap gets `shares_lines_with`. A claim that
depends on a claim that needs an owner needs one too. A high score never clears the gate.

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
    "count": (40, "code metric, before vs after"),
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


# What kind of difference changes a promise. Keyed by the match type of the expected rule that explains it.


def promise_of(match):
    """The contract a difference changes, or None when it is a fix (a crash that goes away)."""
    t, mid = match.get("type", ""), match.get("id", "")
    if t in ("diagnostic_removed", "diagnostic_added") and mid.startswith("MsgPack"):
        return "diagnostics"
    if t in ("generated_rewrite", "generated_file_changed", "generated_file_removed"):
        return "generated"
    if t == "generated_file_added" and not match.get("requires_base"):
        return "generated"
    if t == "diagnostic_added" and mid.startswith("CS"):
        return "generated"
    return None


def old_vs_new_gates(branch, claims, trips, errors):
    """Per claim, the reasons old vs new sends it to an owner: [(contract, why, hunks)]."""
    ip = os.path.join(REVIEW, f"evidence/{branch}/isolation.json")
    if not os.path.exists(ip):
        return {}, None
    iso = json.load(open(ip))["details"]
    rules = json.load(open(os.path.join(HERE, "isolation", "expected", f"{branch}.json")))["rules"]
    match_of = {(r["claim"], r["what"]): r["match"] for r in rules}
    own = {c["id"]: [p for p in c.get("diff_parts", []) if not p.startswith("tests/")] for c in claims}
    trip_hunks = [(k, t["hunk"]) for k, v in trips.items() for t in v]
    reasons = {}

    def hunks_for(cid, contract):
        return [h for k, h in trip_hunks if k == contract and own[cid] and overlaps(own[cid], [h])]

    # ran, output differs: explained differences on the real projects and on the old tests' inputs
    for group, entries in (("real projects", iso.get("explained", [])),
                           ("old tests", iso.get("control", {}).get("explained", []))):
        best = {}
        for e in entries:
            # the claim comes from the rule that explains this difference (an input can match several rules)
            r = next((r for r in rules if r["what"] == e["what"]), None)
            if r is None:
                errors.append(f"isolation: no expected rule for '{e['what'][:60]}'"); continue
            n = e.get("units") or (e["inputs"] if isinstance(e.get("inputs"), int) else len(e.get("inputs", [])))
            key = (r["claim"], r["what"])
            best[key] = max(best.get(key, 0), n)
        for (cid, what), n in best.items():
            contract = promise_of(match_of[(cid, what)])
            if not contract:
                continue
            if cid not in own:
                errors.append(f"isolation: rule names {cid}, which is not a claim"); continue
            reasons.setdefault(cid, []).append((contract,
                f"old vs new: {n} {'output' if n == 1 else 'outputs'} from the {group} came out different ({what})",
                hunks_for(cid, contract)))
    # ran, output differs, and no rule explains it: every claim whose lines that input ran
    for u in iso.get("unexplained", []) + iso.get("control", {}).get("unexplained", []):
        hit = next((pi for pi in iso["coverage"].get("per_input", []) if pi["input"] == u.get("input")), None)
        lines = (hit or {}).get("hit_branch_lines", [])
        for cid, parts in own.items():
            if parts and (not lines or overlaps(lines, parts)):
                for contract in sorted({k for k, h in trip_hunks if overlaps(parts, [h])}) or ["unknown"]:
                    reasons.setdefault(cid, []).append((contract,
                        f"old vs new: an output changed that no planned change explains ({u.get('input', 'an input')})",
                        hunks_for(cid, contract)))
    # never ran: a changed line no old input runs, in a hunk tied to a promise
    unrun = {}
    for u in iso["coverage"].get("unreached", []):
        if u.get("reached_by_control_group"):
            continue
        line = f"{u['file']}:{u['line']}"
        for k, h in trip_hunks:
            hit = overlaps([line], [h]) if u["side"] == "branch" else h.split(":")[0] == u["file"]
            if not hit:
                continue
            for cid, parts in own.items():
                inside = overlaps([line], parts) if u["side"] == "branch" else any(p.split(":")[0] == u["file"] for p in parts)
                if inside:
                    g = unrun.setdefault((cid, k), {"lines": [], "hunks": []})
                    g["lines"].append(f"{os.path.basename(u['file'])}:{u['line']}")
                    g["hunks"].append(h)
    for (cid, k), g in unrun.items():
        reasons.setdefault(cid, []).append((k,
            f"old vs new: no input that existed before the change runs {' or '.join(dict.fromkeys(g['lines']))}",
            list(dict.fromkeys(g["hunks"]))))
    return reasons, iso


def score_branch(branch, project, history, errors):
    dossier = load(f"dossier/{branch}.json")
    trips = load(f"evidence/{branch}/tripwires.json")["details"]["trips"]
    rp = os.path.join(REVIEW, f"evidence/{branch}/replay.json")
    replay = json.load(open(rp))["details"]["files"] if os.path.exists(rp) else {}
    maint = {c["id"]: c["maintainers"] for c in project["contracts"]}
    rules = [r for r in (history or {}).get("rules", []) if not r.get("off")]  # a person can turn a rule off
    ev_cache = {}

    def ev(path):
        if path not in ev_cache:
            full = os.path.join(REVIEW, path)
            ev_cache[path] = json.load(open(full)) if os.path.exists(full) else None
        return ev_cache[path]

    ovn, _ = old_vs_new_gates(branch, dossier["claims"], trips, errors)

    def make_gate(contract, change, shown_by, hunks, source):
        m = maint.get(contract, {})
        return {
            "contract": contract, "change": change, "shown_by": shown_by, "source": source,
            "hunks": hunks,
            "owner": (m.get("top") or [{}])[0].get("name"),
            "owner_basis": f"most commits on the {contract} paths at base ({m.get('commits')} commits)",
            "rules": [{"id": r["id"], "rule": r["rule"], "sources": r["sources"][:2]}
                      for r in rules if r.get("concern") == contract
                      or (contract == "generated" and r.get("concern") in ("public-api", "compat-breaking"))][:3],
        }

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

        # gate, first input: an experiment recorded that a promise changed on these lines
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
                out[cid]["gate"] = make_gate(ch["contract"], ch["what"], s["file"], hunks, "experiment")
                break
            if out[cid]["gate"]:
                break
        # gate, second input: old vs new and its coverage
        reasons = ovn.get(cid, [])
        if reasons:
            if not out[cid]["gate"]:
                contract, why, hunks = reasons[0]
                out[cid]["gate"] = make_gate(contract, why, f"evidence/{branch}/isolation.json", hunks, "old-vs-new")
            seen = set()
            out[cid]["gate"]["also"] = [r[1] for r in reasons if r[1] != out[cid]["gate"]["change"]
                                        and not (r[1] in seen or seen.add(r[1]))]

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
