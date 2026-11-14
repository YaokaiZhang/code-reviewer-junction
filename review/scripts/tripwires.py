#!/usr/bin/env python3
"""Tripwires: which project contracts does this diff touch, and which claim answers for each touch?

Reads the contracts from review/context/project.json (paths and line patterns, from
project_context.py) and every changed hunk of the branch. A hunk trips a contract when
its file sits under one of the contract's paths, or when a changed line outside tests/
matches one of its line patterns. Each tripped hunk is matched to the dossier claims
whose diff_parts cover it (same matching as claim_coverage.py).

A trip is not a verdict. It says "a person who knows this contract should see this".
tier_check.py uses it: a tripped hunk must be covered by at least one claim, and
contracts that a check shows were broken make that claim Refused.

    python3 review/scripts/tripwires.py --repo <clone> --branch ju26-issue-2283 [--write]
"""
import argparse, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REVIEW = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from claim_coverage import BASE, parse_part, covered  # noqa: E402


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True).stdout


def hunks_with_lines(repo, branch):
    out = git(repo, "diff", "-U0", "--no-color", f"{BASE}...origin/{branch}")
    cur, h = None, None
    for line in out.splitlines():
        if line.startswith("+++ "):
            p = line[4:]
            cur = None if p == "/dev/null" else p[2:]
        elif line.startswith("--- "):
            if line[4:] != "/dev/null" and cur is None:
                pass
        elif line.startswith("@@") and cur:
            if h:
                yield h
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
            s, n = int(m.group(1)), int(m.group(2) or "1")
            h = {"file": cur, "start": s, "end": s + max(n, 1) - 1, "lines": []}
        elif h is not None and line[:1] in "+-" and not line.startswith(("+++", "---")):
            h["lines"].append(line)
    if h:
        yield h


def under(path, prefixes):
    return any(path == p or (p.endswith("/") and path.startswith(p)) for p in prefixes)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.environ.get("MP_REPO"), required=os.environ.get("MP_REPO") is None)
    ap.add_argument("--branch", required=True)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    ctx = json.load(open(os.path.join(REVIEW, "context", "project.json")))
    dossier = json.load(open(os.path.join(REVIEW, "dossier", f"{a.branch}.json")))
    claim_parts = {c["id"]: [parse_part(p) for p in c.get("diff_parts", [])] for c in dossier["claims"]}

    trips = {c["id"]: [] for c in ctx["contracts"]}
    n_hunks = 0
    for h in hunks_with_lines(a.repo, a.branch):
        n_hunks += 1
        for c in ctx["contracts"]:
            why = None
            if under(h["file"], c["paths"]):
                why = "path"
            elif not h["file"].startswith("tests/"):
                for pat in c.get("line_patterns", []):
                    hit = next((l for l in h["lines"] if re.search(pat, l[1:])), None)
                    if hit:
                        why = "line: " + hit[:120].rstrip()
                        break
            if why:
                claims = [cid for cid, parts in claim_parts.items() if covered(h["file"], h["start"], h["end"], parts)]
                trips[c["id"]].append({"hunk": f"{h['file']}:{h['start']}-{h['end']}", "why": why, "claims": claims})

    tripped = {k: v for k, v in trips.items() if v}
    unanswered = [t["hunk"] for v in tripped.values() for t in v if not t["claims"]]
    per = "; ".join(f"{k} {len(v)}" for k, v in tripped.items()) or "none"
    ev = {
        "check": "tripwires",
        "branch": a.branch,
        "base": BASE,
        "command": f"python3 review/scripts/tripwires.py --repo $MP_REPO --branch {a.branch} --write",
        "result": "pass" if not unanswered else "fail",
        "summary": f"{sum(len(v) for v in tripped.values())} contract trips over {n_hunks} hunks ({per}); "
                   f"{len(unanswered)} trips no claim answers",
        "details": {
            "hunks_total": n_hunks,
            "contracts_tripped": sorted(tripped),
            "contracts_clear": sorted(k for k in trips if not trips[k]),
            "trips": tripped,
            "unanswered": unanswered,
            "context": "review/context/project.json",
        },
        "tool_versions": {"git": git(a.repo, "--version").strip(), "python": sys.version.split()[0]},
        "produced_by": "script",
    }
    print(ev["summary"])
    if a.write:
        out = os.path.join(REVIEW, "evidence", a.branch, "tripwires.json")
        with open(out, "w") as f:
            json.dump(ev, f, indent=2, ensure_ascii=False)
            f.write("\n")


if __name__ == "__main__":
    main()
