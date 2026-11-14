#!/usr/bin/env python3
"""Coverage of the diff by claims.

Lists every changed hunk of a branch (vs base) that no claim in the dossier covers.
A claim covers a hunk when one of its `diff_parts` names the file (or a glob of it)
and, if a line range is given, the range overlaps the hunk's new-side lines.

    python3 review/scripts/claim_coverage.py --repo <clone> --branch ju26-issue-2283 [--write]

--write stores the result in evidence/<branch>/claim-coverage.json and
updates `uncovered_diff_parts` in dossier/<branch>.json.
"""
import argparse, fnmatch, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REVIEW = os.path.dirname(HERE)
BASE = "32258fdb"


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True).stdout


def hunks(repo, branch):
    """Yield (file, start, end) for each hunk on the new side; deletions-only hunks use the anchor line."""
    out = git(repo, "diff", "-U0", "--no-color", f"{BASE}...origin/{branch}")
    cur = None
    for line in out.splitlines():
        if line.startswith("+++ "):
            p = line[4:]
            cur = None if p == "/dev/null" else p[2:]
        elif line.startswith("--- ") and cur is None:
            pass
        elif line.startswith("@@") and cur:
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
            start, count = int(m.group(1)), int(m.group(2) or "1")
            yield cur, start, start + max(count, 1) - 1


def parse_part(part):
    """'path/glob:10-20' -> (glob, 10, 20); 'path' -> (path, None, None)."""
    m = re.match(r"^(.*?)(?::(\d+)(?:-(\d+))?)?$", part.strip())
    path, a, b = m.group(1), m.group(2), m.group(3)
    a = int(a) if a else None
    b = int(b) if b else a
    return path, a, b


def covered(file, s, e, parts):
    for glob, a, b in parts:
        if file == glob or fnmatch.fnmatch(file, glob) or file.endswith("/" + glob) or fnmatch.fnmatch(file, "*/" + glob):
            if a is None or not (e < a or s > b):
                return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.environ.get("MP_REPO"), required=os.environ.get("MP_REPO") is None)
    ap.add_argument("--branch", required=True)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    dpath = os.path.join(REVIEW, "dossier", f"{a.branch}.json")
    dossier = json.load(open(dpath))
    parts = [parse_part(p) for c in dossier["claims"] for p in c.get("diff_parts", [])]

    all_h = list(hunks(a.repo, a.branch))
    unc = [(f, s, e) for f, s, e in all_h if not covered(f, s, e, parts)]
    files = sorted({f for f, _, _ in all_h})
    unc_files = sorted({f for f, _, _ in unc})
    # Collapse per file so the dossier list stays readable.
    by_file = {}
    for f, s, e in unc:
        by_file.setdefault(f, []).append(f"{s}-{e}" if s != e else str(s))
    unc_list = [f"{f}:{','.join(r)}" for f, r in sorted(by_file.items())]

    ev = {
        "check": "claim-coverage",
        "branch": a.branch,
        "base": BASE,
        "command": f"python3 review/scripts/claim_coverage.py --repo $MP_REPO --branch {a.branch} --write",
        "result": "pass" if not unc else "fail",
        "summary": f"{len(all_h) - len(unc)} of {len(all_h)} changed hunks covered by a claim; {len(unc_files)} of {len(files)} files have uncovered hunks",
        "details": {"hunks_total": len(all_h), "hunks_uncovered": len(unc), "files_total": len(files),
                    "files_with_uncovered": len(unc_files), "uncovered": unc_list},
        "tool_versions": {"git": git(a.repo, "--version").strip(), "python": sys.version.split()[0]},
        "produced_by": "script",
    }
    print(ev["summary"])
    for u in unc_list:
        print("  uncovered:", u)
    if a.write:
        epath = os.path.join(REVIEW, "evidence", a.branch, "claim-coverage.json")
        os.makedirs(os.path.dirname(epath), exist_ok=True)
        json.dump(ev, open(epath, "w"), indent=2)
        open(epath, "a").write("\n")
        dossier["uncovered_diff_parts"] = unc_list
        json.dump(dossier, open(dpath, "w"), indent=2, ensure_ascii=False)
        open(dpath, "a").write("\n")


if __name__ == "__main__":
    main()
