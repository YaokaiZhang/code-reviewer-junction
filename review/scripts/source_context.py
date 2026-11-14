#!/usr/bin/env python3
"""Source excerpts for the owner view.

For every `diff_parts` entry in a dossier, stores the diff hunks it points at
(3 lines of context, line numbers on both sides) and a GitHub link at the
branch head, so the owner can read the code without a clone.

    python3 review/scripts/source_context.py --repo <clone> --branch ju26-issue-2234

Writes review/source/<branch>.json. Not evidence: nothing here is a check.
"""
import argparse, fnmatch, json, os, re, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REVIEW = os.path.dirname(HERE)
BASE = "32258fdb"
GH = "https://github.com/te-industry-tech-office/junction26-messagepack-csharp"
MAX_HUNKS = 4       # per diff part
MAX_LINES = 60      # per hunk


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True).stdout


def parse_patch(text):
    """{file: [hunk]}; hunk = {old, new, n0, n1 (new-side range), lines: [[op, old_no, new_no, text]]}."""
    files, cur, h, o, n, hdr, old = {}, None, None, 0, 0, False, ""
    for line in text.splitlines():
        if line.startswith("diff --git "):
            cur, h, hdr = None, None, True
        elif hdr and line.startswith("--- "):
            old = line[4:]
        elif hdr and line.startswith("+++ "):
            p = line[4:]
            cur = (old[2:] if p == "/dev/null" else p[2:])
            files.setdefault(cur, [])
        elif line.startswith("@@") and cur:
            hdr = False
            m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)", line)
            o, n = int(m.group(1)), int(m.group(3))
            cnt = int(m.group(4) or "1")
            h = {"head": line, "n0": n, "n1": n + max(cnt, 1) - 1, "lines": []}
            files[cur].append(h)
        elif h is not None and line[:1] in (" ", "+", "-"):
            op = line[0]
            if op == " ":
                h["lines"].append([" ", o, n, line[1:]]); o += 1; n += 1
            elif op == "-":
                h["lines"].append(["-", o, None, line[1:]]); o += 1
            else:
                h["lines"].append(["+", None, n, line[1:]]); n += 1
    return files


def parse_part(part):
    m = re.match(r"^(.*?)(?::(\d+)(?:-(\d+))?)?$", part.strip())
    a = int(m.group(2)) if m.group(2) else None
    b = int(m.group(3)) if m.group(3) else a
    return m.group(1), a, b


def matches(file, glob):
    return file == glob or fnmatch.fnmatch(file, glob)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.environ.get("MP_REPO"), required=os.environ.get("MP_REPO") is None)
    ap.add_argument("--branch", required=True)
    a = ap.parse_args()

    dossier = json.load(open(os.path.join(REVIEW, "dossier", f"{a.branch}.json")))
    head = git(a.repo, "rev-parse", f"origin/{a.branch}").strip()
    base = git(a.repo, "rev-parse", BASE).strip()
    files = parse_patch(git(a.repo, "diff", "-U3", "--no-color", f"{BASE}...origin/{a.branch}"))

    parts = {}
    for c in dossier["claims"]:
        for p in c.get("diff_parts", []):
            if p in parts:
                continue
            glob, lo, hi = parse_part(p)
            hit_files = sorted(f for f in files if matches(f, glob))
            hunks = []
            for f in hit_files:
                for h in files[f]:
                    if lo is None or not (h["n1"] < lo or h["n0"] > hi):
                        hunks.append((f, h))
            single = len(hit_files) == 1 and not any(ch in glob for ch in "*?[")
            if single:
                url = f"{GH}/blob/{head}/{glob}" + (f"#L{lo}" + (f"-L{hi}" if hi != lo else "") if lo else "")
            else:
                url = f"{GH}/tree/{head}/{os.path.dirname(glob.split('*')[0].rstrip('/')) or ''}".rstrip("/")
            shown = []
            for f, h in hunks[:MAX_HUNKS]:
                lines = h["lines"]
                shown.append({"file": f, "head": h["head"], "lines": lines[:MAX_LINES],
                              "cut": max(0, len(lines) - MAX_LINES)})
            parts[p] = {"url": url, "files": len(hit_files), "hunks": len(hunks), "shown": shown}

    out = {
        "branch": a.branch,
        "base": base,
        "head": head,
        "compare": f"{GH}/compare/{base}...{head}",
        "command": f"python3 review/scripts/source_context.py --repo $MP_REPO --branch {a.branch}",
        "parts": parts,
    }
    path = os.path.join(REVIEW, "source", f"{a.branch}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    print(f"{path}: {len(parts)} parts, {sum(v['hunks'] for v in parts.values())} hunks")


if __name__ == "__main__":
    main()
