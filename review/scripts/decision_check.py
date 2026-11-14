#!/usr/bin/env python3
"""Check the AI's decisions against the real code, and attach the real evidence.

Every decision the reviewing agent makes (each claim, each finding, each scope-drift note) gets a card
in review/explain/<branch>.decisions.json, written by the agent:

  title      a plain name, a few words
  steps      pseudo-code: plain sentences with `backticked` tokens, each citing lines
             (side "new" = the branch head, side "old" = the base commit)
  verdict    one sentence: what the agent decided
  because    reasons; a reason may name an evidence file
  unsure     what the agent could not settle (optional)
  ask        the question for the owner (optional)

Kinds: claim (id = a dossier claim), found, drift, and flag (id = a readability flag in
evidence/<branch>/readability.json; its reasons must name that file). Every claim and every
readability flag needs a card.

The agent can be wrong, so this script never takes its word:

  step check   the cited lines exist, and every `backticked` token appears in them (whitespace ignored).
               A step that fails is shown as unverified. A claim step outside the claim's changed lines
               is marked as context.
  evidence     each named evidence file is loaded; its real result and summary are attached.
               A file that is missing, or not linked from the claim, is a problem.
  code         the real lines: the diff hunks the steps point at (old and new line numbers), plus
               plain context for cited lines outside the diff.

    python3 review/scripts/decision_check.py --repo <clone> --branch ju26-issue-2283 [--write]

Writes evidence/<branch>/decision-check.json. Standard library only.
"""
import argparse, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REVIEW = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from claim_coverage import BASE, parse_part, covered  # noqa: E402

TOKEN = re.compile(r"`([^`]+)`")
OPS = {"WHEN", "IF", "THEN", "ELSE", "BEFORE", "NOW", "ALSO", "SO", "BUT", "GIVEN", "AND"}
MAX_ROWS = 90


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True).stdout


def squash(s):
    return re.sub(r"\s+", "", s)


def diff_hunks(repo, branch, path):
    """Hunks of one file with 3 lines of context: [{old:(a,b), new:(a,b), rows:[[op, old_no, new_no, text]]}]."""
    out = git(repo, "diff", "-U3", "--no-color", f"{BASE}...origin/{branch}", "--", path)
    hs, cur, o, n = [], None, 0, 0
    for line in out.split("\n"):
        m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
        if m:
            o, n = int(m.group(1)), int(m.group(3))
            cur = {"rows": []}
            hs.append(cur)
            continue
        if cur is None or line.startswith("\\"):
            continue
        if line.startswith("+") and not line.startswith("+++"):
            cur["rows"].append(["+", None, n, line[1:]]); n += 1
        elif line.startswith("-") and not line.startswith("---"):
            cur["rows"].append(["-", o, None, line[1:]]); o += 1
        elif line.startswith(" "):
            cur["rows"].append([" ", o, n, line[1:]]); o += 1; n += 1
    for h in hs:
        olds = [r[1] for r in h["rows"] if r[1]]
        news = [r[2] for r in h["rows"] if r[2]]
        h["old"] = (min(olds), max(olds)) if olds else (0, -1)
        h["new"] = (min(news), max(news)) if news else (0, -1)
    return hs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.environ.get("MP_REPO"), required=os.environ.get("MP_REPO") is None)
    ap.add_argument("--branch", required=True)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    spec_rel = f"explain/{a.branch}.decisions.json"
    spec = json.load(open(os.path.join(REVIEW, spec_rel)))
    dossier = json.load(open(os.path.join(REVIEW, "dossier", f"{a.branch}.json")))
    claims = {c["id"]: c for c in dossier["claims"]}
    rd_rel = f"evidence/{a.branch}/readability.json"
    rd_path = os.path.join(REVIEW, rd_rel)
    flags = {f["id"]: f for f in json.load(open(rd_path))["details"].get("flags", [])} if os.path.exists(rd_path) else {}
    revs = {"new": f"origin/{a.branch}", "old": BASE}
    head = git(a.repo, "rev-parse", "--short=8", revs["new"]).strip()
    src, hunk_cache = {}, {}

    def lines_of(side, path):
        k = (side, path)
        if k not in src:
            try:
                src[k] = git(a.repo, "show", f"{revs[side]}:{path}").split("\n")
            except subprocess.CalledProcessError:
                src[k] = None
        return src[k]

    def hunks_of(path):
        if path not in hunk_cache:
            hunk_cache[path] = diff_hunks(a.repo, a.branch, path)
        return hunk_cache[path]

    cards, problems_all, n_steps, n_bad = [], [], 0, 0
    seen = set()
    for c in spec["decisions"]:
        cid, kind = c["id"], c.get("kind", "claim")
        probs = []
        if cid in seen:
            probs.append("duplicate id")
        seen.add(cid)
        claim = claims.get(c.get("ref", cid)) if kind == "claim" else None
        if kind == "claim" and not claim:
            probs.append("no such claim in the dossier")
        if kind == "flag":
            if cid not in flags:
                probs.append(f"no such flag in {rd_rel}")
            if not any(b.get("evidence") == rd_rel for b in c.get("because", [])):
                probs.append(f"a flag's reasons must name {rd_rel}")
        parts = [parse_part(p) for p in (claim or {}).get("diff_parts", [])]

        # steps
        steps, cited = [], {}
        for s in c.get("steps", []):
            n_steps += 1
            side, f = s.get("side", "new"), s["file"]
            lo, hi = s["lines"][0], s["lines"][-1]
            sp = []
            if s.get("op") not in OPS:
                sp.append(f"unknown word {s.get('op')!r}")
            L = lines_of(side, f)
            toks = TOKEN.findall(s["text"])
            if L is None:
                sp.append(f"{f} does not exist {'after' if side == 'new' else 'before'} the change")
            elif hi > len(L) or lo < 1 or lo > hi:
                sp.append(f"lines {lo}-{hi} are outside the file")
            else:
                text = squash("".join(L[lo - 1:hi]))
                miss = [t for t in toks if squash(t) not in text]
                if miss:
                    sp.append("not in the cited lines: " + ", ".join(miss))
            if not toks:
                sp.append("no `token` to check")
            in_change = None
            if kind == "claim":
                if side == "new":
                    in_change = covered(f, lo, hi, parts)
                else:  # an old line belongs to the claim when its hunk's new side overlaps the claim
                    in_change = any(h["old"][0] <= hi and lo <= h["old"][1] and covered(f, *(h["new"] if h["new"][1] >= h["new"][0] else (h["new"][0], h["new"][0])), parts)
                                    for h in hunks_of(f))
            n_bad += bool(sp)
            cited.setdefault(f, {"new": set(), "old": set()})[side].update(range(lo, hi + 1))
            steps.append(dict(s, side=side, verified=not sp, problems=sp, in_change=in_change))

        # code: diff hunks that the steps touch, then plain context for cited lines outside the diff
        groups = []
        for f, sides in cited.items():
            rows, used_new, used_old = [], set(), set()
            for h in hunks_of(f):
                hit = any(h["new"][0] <= x <= h["new"][1] for x in sides["new"]) or any(h["old"][0] <= x <= h["old"][1] for x in sides["old"])
                if hit:
                    if rows:
                        rows.append(["gap", None, None, ""])
                    rows += h["rows"]
                    used_new.update(r[2] for r in h["rows"] if r[2])
                    used_old.update(r[1] for r in h["rows"] if r[1])
            for side, used, col in (("new", used_new, 2), ("old", used_old, 1)):
                rest = sorted(x for x in sides[side] if x not in used)
                if not rest:
                    continue
                L = lines_of(side, f) or []
                want = sorted({y for x in rest for y in range(x - 2, x + 3) if 1 <= y <= len(L)} - used)
                prev = None
                for y in want:
                    if prev is None or y != prev + 1:
                        rows.append(["gap", None, None, ""])
                    row = [" ", None, None, L[y - 1]]
                    row[col] = y
                    rows.append(row)
                    prev = y
            if rows and rows[0][0] == "gap":
                rows = rows[1:]
            cut = max(0, len(rows) - MAX_ROWS)
            groups.append({"file": f, "rows": rows[:MAX_ROWS], "cut": cut})

        # evidence named by the reasons: attach the real result, never the agent's
        because = []
        for b in c.get("because", []):
            b = dict(b)
            ref = b.get("evidence")
            if ref:
                p = os.path.join(REVIEW, ref)
                if not os.path.exists(p):
                    probs.append(f"{ref} not found")
                    b["result"] = "missing"
                else:
                    ev = json.load(open(p))
                    b.update(result=ev.get("result"), summary=ev.get("summary", ""), produced_by=ev.get("produced_by"),
                             check=ev.get("check"))
                    if claim and ref not in claim.get("evidence", []):
                        probs.append(f"{ref} is not linked from {cid}")
            because.append(b)

        for k in ("title", "verdict"):
            if not c.get(k):
                probs.append(f"missing {k}")
        problems_all += [f"{cid}: {p}" for p in probs]
        cards.append(dict(c, kind=kind, steps=steps, because=because, code=groups, problems=probs,
                          verified=not probs and all(s["verified"] for s in steps)))

    missing = [i for i in claims if i not in seen]
    problems_all += [f"{i}: no card" for i in missing]
    missing_flags = [i for i in flags if i not in seen]
    problems_all += [f"{i}: readability flag has no card" for i in missing_flags]
    ok = sum(c["verified"] for c in cards)
    ev = {
        "check": "decision-check",
        "branch": a.branch,
        "base": BASE,
        "head": head,
        "command": f"python3 review/scripts/decision_check.py --repo $MP_REPO --branch {a.branch} --write",
        "result": "pass" if not problems_all and n_bad == 0 else "fail",
        "provides": ["count"],
        "summary": f"{len(cards)} decisions explained in {n_steps} steps; {n_steps - n_bad} of {n_steps} steps match the cited code; "
                   f"{len(claims) - len(missing)} of {len(claims)} claims have a card"
                   + (f"; {len(flags) - len(missing_flags)} of {len(flags)} readability flags have a card" if flags else ""),
        "details": {"cards": cards, "problems": problems_all, "spec": spec_rel,
                    "pseudo_code_by": spec.get("produced_by", "agent")},
        "tool_versions": {"git": git(a.repo, "--version").strip(), "python": sys.version.split()[0]},
        "produced_by": "script",
    }
    print(ev["summary"])
    for c in cards:
        for s in c["steps"]:
            if not s["verified"]:
                print("  unverified:", c["id"], s["op"], s["problems"])
    for p in problems_all:
        print("  problem:", p)
    if a.write:
        with open(os.path.join(REVIEW, "evidence", a.branch, "decision-check.json"), "w") as f:
            json.dump(ev, f, indent=2, ensure_ascii=False)
            f.write("\n")


if __name__ == "__main__":
    main()
