#!/usr/bin/env python3
"""Clone and complexity numbers for one C# file, base versus branch.

Measures, on the base commit and on the branch:
  * duplicated-line blocks: simple line-window clone detection. Lines are
    normalised (whitespace collapsed, comments dropped, lines that are only
    braces or blank dropped). Every window of --window consecutive normalised
    lines is hashed; windows seen 2+ times are clones. Overlapping clone windows
    are merged into blocks. Reports blocks, duplicated lines, and how many of the
    branch's added lines sit inside a duplicated block.
  * a cyclomatic complexity estimate for the method(s) the diff touches and for
    each top-level foreach loop the diff touches: 1 + number of decision tokens
    (if, while, for, foreach, case, catch, &&, ||, ternary ?, ??). Strings and
    comments are stripped first. `?.` is not counted (listed separately).
    This is an estimate from tokens, not from a compiler's control-flow graph.

Usage:
  python3 review/scripts/clone_complexity.py --repo <clone> --branch ju26-issue-2234 \
      --file src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs \
      --out review/evidence/ju26-issue-2234/clone-complexity.json
Python 3, standard library only; reads blobs with `git show`, never checks out.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

DECISION = [
    ("if", re.compile(r"\bif\s*\(")),
    ("while", re.compile(r"\bwhile\s*\(")),
    ("for", re.compile(r"\bfor\s*\(")),
    ("foreach", re.compile(r"\bforeach\s*\(")),
    ("case", re.compile(r"\bcase\b")),
    ("catch", re.compile(r"\bcatch\b")),
    ("&&", re.compile(r"&&")),
    ("||", re.compile(r"\|\|")),
    ("??", re.compile(r"\?\?(?!=)")),
    ("ternary", re.compile(r"\s\?\s")),
]
NULL_COND = re.compile(r"\?\.")
METHOD_SIG = re.compile(r"^    (?:public|private|internal|protected)[^;=]*?\b([A-Za-z_]\w*)\s*\([^;]*$")


def git(repo, *a):
    p = subprocess.run(["git", "-C", repo, *a], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode:
        raise SystemExit(p.stderr)
    return p.stdout


def resolve(repo, rev):
    for c in (rev, "origin/" + rev):
        p = subprocess.run(["git", "-C", repo, "rev-parse", "--verify", "--quiet", c + "^{commit}"], stdout=subprocess.PIPE, text=True)
        if p.returncode == 0:
            return p.stdout.strip()
    raise SystemExit("cannot resolve " + rev)


def strip_code(line):
    """Remove string/char literals and // comments (single line; verbatim strings approximated)."""
    line = re.sub(r'@"(?:[^"]|"")*"', '""', line)
    line = re.sub(r'"(?:\\.|[^"\\])*"', '""', line)
    line = re.sub(r"'(?:\\.|[^'\\])'", "''", line)
    i = line.find("//")
    return line[:i] if i >= 0 else line


def normalise(lines):
    out = []  # (orig_line_no, text)
    in_block = False
    for n, raw in enumerate(lines, 1):
        s = raw
        if in_block:
            if "*/" in s:
                s = s.split("*/", 1)[1]
                in_block = False
            else:
                continue
        if "/*" in s:
            s, _, rest = s.partition("/*")
            if "*/" not in rest:
                in_block = True
        s = strip_code(s)
        s = " ".join(s.split())
        if not s or re.fullmatch(r"[{}();,]*", s):
            continue
        out.append((n, s))
    return out


def clones(lines, window):
    norm = normalise(lines)
    seen = {}
    for i in range(len(norm) - window + 1):
        h = hashlib.sha1("\n".join(t for _, t in norm[i:i + window]).encode()).hexdigest()
        seen.setdefault(h, []).append(i)
    dup_idx = set()
    groups = 0
    for h, starts in seen.items():
        if len(starts) > 1:
            groups += 1
            for s in starts:
                dup_idx.update(range(s, s + window))
    # merge consecutive normalised indices into blocks
    blocks = []
    for i in sorted(dup_idx):
        if blocks and i == blocks[-1][1] + 1:
            blocks[-1][1] = i
        else:
            blocks.append([i, i])
    block_ranges = [(norm[a][0], norm[b][0]) for a, b in blocks]
    dup_lines = {norm[i][0] for i in dup_idx}
    return {
        "normalised_lines": len(norm),
        "duplicated_normalised_lines": len(dup_idx),
        "duplicated_share_percent": round(100.0 * len(dup_idx) / max(1, len(norm)), 1),
        "repeated_window_hashes": groups,
        "duplicated_blocks": len(blocks),
        "duplicated_block_line_ranges": [f"{a}-{b}" for a, b in block_ranges],
    }, dup_lines


def find_block_end(lines, start_idx):
    depth, opened = 0, False
    for j in range(start_idx, len(lines)):
        t = strip_code(lines[j])
        depth += t.count("{") - t.count("}")
        if "{" in t:
            opened = True
        if opened and depth <= 0:
            return j
    return len(lines) - 1


def methods(lines):
    res = []
    for i, l in enumerate(lines):
        m = METHOD_SIG.match(l)
        if m and not l.rstrip().endswith(";") and "=>" not in l:
            end = find_block_end(lines, i)
            res.append((m.group(1), i + 1, end + 1))
    return res


def top_loops(lines, mstart, mend):
    """foreach loops at 12-space indent inside the method (the member loops)."""
    res = []
    for i in range(mstart - 1, mend):
        m = re.match(r"^ {12}foreach \((\w+) item in", lines[i])
        if m:
            res.append((f"foreach {m.group(1)}", i + 1, find_block_end(lines, i) + 1))
    return res


def complexity(lines, a, b):
    counts = {k: 0 for k, _ in DECISION}
    nullcond = 0
    for l in lines[a - 1:b]:
        t = strip_code(l)
        if t.strip().startswith("//"):
            continue
        for k, rx in DECISION:
            counts[k] += len(rx.findall(t))
        nullcond += len(NULL_COND.findall(t))
    return {"estimate": 1 + sum(counts.values()), "decision_tokens": counts, "null_conditional_not_counted": nullcond,
            "lines": f"{a}-{b}", "line_count": b - a + 1}


def added_lines(repo, base, head, path):
    diff = git(repo, "diff", "-U0", base, head, "--", path)
    added = []
    cur = None
    for l in diff.splitlines():
        m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", l)
        if m:
            cur = int(m.group(1))
            continue
        if cur is None or l.startswith("+++") or l.startswith("---"):
            continue
        if l.startswith("+"):
            added.append(cur)
            cur += 1
        elif not l.startswith("-"):
            cur += 1
    return added


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=os.environ.get("MP_REPO"), required=os.environ.get("MP_REPO") is None)
    ap.add_argument("--branch", required=True)
    ap.add_argument("--base", default="32258fdb")
    ap.add_argument("--file", default="src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs")
    ap.add_argument("--window", type=int, default=6)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    repo = os.path.abspath(a.repo)
    base, head = resolve(repo, a.base), resolve(repo, a.branch)

    sides = {}
    added = added_lines(repo, base, head, a.file)
    for side, rev in (("base", base), ("branch", head)):
        lines = git(repo, "show", f"{rev}:{a.file}").splitlines()
        cl, dup_lines = clones(lines, a.window)
        sides[side] = {"rev": rev[:8], "file_lines": len(lines), "clones": cl, "_dup": dup_lines, "_lines": lines}

    # Touched methods / loops: methods on the branch that contain an added line.
    bl = sides["branch"]["_lines"]
    touched = [m for m in methods(bl) if any(m[1] <= x <= m[2] for x in added)]
    base_methods = {m[0]: m for m in methods(sides["base"]["_lines"])}
    cc = []
    for name, s, e in touched:
        entry = {"unit": f"method {name}", "branch": complexity(bl, s, e)}
        if name in base_methods:
            _, bs, be = base_methods[name]
            entry["base"] = complexity(sides["base"]["_lines"], bs, be)
            entry["delta"] = entry["branch"]["estimate"] - entry["base"]["estimate"]
        cc.append(entry)
        base_loops = top_loops(sides["base"]["_lines"], *base_methods[name][1:]) if name in base_methods else []
        for k, (lname, ls, le) in enumerate(top_loops(bl, s, e)):
            if not any(ls <= x <= le for x in added):
                continue
            le_entry = {"unit": f"{lname} loop in {name}", "branch": complexity(bl, ls, le)}
            match = [x for x in base_loops if x[0] == lname]
            if match:
                le_entry["base"] = complexity(sides["base"]["_lines"], match[0][1], match[0][2])
                le_entry["delta"] = le_entry["branch"]["estimate"] - le_entry["base"]["estimate"]
            cc.append(le_entry)

    added_in_dup = sorted(x for x in added if x in sides["branch"]["_dup"])
    # added lines that are code (not blank/comment/brace-only)
    code_added = {n for n, _ in normalise(bl) if n in set(added)}
    added_code_in_dup = sorted(x for x in code_added if x in sides["branch"]["_dup"])
    for s in sides.values():
        s.pop("_dup")
        s.pop("_lines")

    b, h = sides["base"]["clones"], sides["branch"]["clones"]
    m0 = cc[0] if cc else None
    summary = (f"{a.file.split('/')[-1]}: duplicated blocks {b['duplicated_blocks']} -> {h['duplicated_blocks']}, "
               f"duplicated normalised lines {b['duplicated_normalised_lines']} -> {h['duplicated_normalised_lines']} "
               f"(window {a.window}); {len(added_code_in_dup)} of {len(code_added)} added code lines sit in duplicated blocks")
    if m0 and "base" in m0:
        summary += f"; {m0['unit']} complexity estimate {m0['base']['estimate']} -> {m0['branch']['estimate']}"
    ev = {
        "check": "clone-complexity",
        "branch": a.branch,
        "base": a.base,
        "head": head[:8],
        "command": f"python3 review/scripts/clone_complexity.py --repo <clone> --branch {a.branch} --file {a.file} --window {a.window} --out {os.path.relpath(os.path.abspath(a.out), os.getcwd())}",
        "result": "pass",
        "summary": summary,
        "details": {
            "file": a.file,
            "window": a.window,
            "method": "line-window clone detection on normalised lines; cyclomatic estimate = 1 + decision tokens",
            "base": sides["base"],
            "branch": sides["branch"],
            "delta_duplicated_normalised_lines": h["duplicated_normalised_lines"] - b["duplicated_normalised_lines"],
            "delta_duplicated_blocks": h["duplicated_blocks"] - b["duplicated_blocks"],
            "added_lines_on_branch": added,
            "added_code_lines": len(code_added),
            "added_code_lines_in_duplicated_blocks": added_code_in_dup,
            "complexity": cc,
        },
        "tool_versions": {"python": sys.version.split()[0], "git": git(repo, "--version").strip()},
        "produced_by": "script",
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(ev, f, indent=2)
        f.write("\n")
    print(summary)


if __name__ == "__main__":
    main()
