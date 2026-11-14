#!/usr/bin/env python3
"""Diff classifier.

Sorts every file a branch changes (vs base) into one of:
  snapshot          tests/**/Resources/**  (expected generator output used by snapshot tests)
  template          *.tt
  generated-output  a .cs file that has a sibling .tt with the same stem (template-generated code)
  test              anything else under tests/
  doc               *.md
  logic             everything else

For every snapshot (and template) file it checks whether each changed hunk is
"pure": no removed lines, and every added line is either a C# attribute line
(`[...]`) or a preprocessor guard line (`#if` / `#elif` / `#else` / `#endif`).
Line endings are ignored (CR stripped) when classifying lines.

    python3 review/scripts/diff_classifier.py --repo <clone> --branch ju26-issue-2297 [--write]

--write stores the result in evidence/<branch>/diff-classifier.json.
Read-only on the clone: only `git diff` against origin/<branch>.
"""
import argparse, collections, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REVIEW = os.path.dirname(HERE)
BASE = "32258fdb"

ATTR_RE = re.compile(r"^\s*\[[^\]]+\]\s*$")
GUARD_RE = re.compile(r"^\s*#\s*(if|elif|else|endif)\b.*$")


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True).stdout


def classify(path, all_files):
    if "/Resources/" in path and path.startswith("tests/"):
        return "snapshot"
    if path.endswith(".tt"):
        return "template"
    if path.endswith(".cs") and (path[:-3] + ".tt") in all_files:
        return "generated-output"
    if path.startswith("tests/"):
        return "test"
    if path.endswith(".md"):
        return "doc"
    return "logic"


def parse_hunks(diff_text):
    """Return {path: [ {old_start, new_start, removed:[...], added:[...]} ]} from a -U0 diff."""
    files, cur, h = {}, None, None
    for raw in diff_text.split("\n"):
        line = raw.rstrip("\r")
        if line.startswith("diff --git "):
            cur, h = None, None
        elif line.startswith("+++ "):
            p = line[4:]
            cur = None if p == "/dev/null" else p[2:]
            if cur is not None:
                files.setdefault(cur, [])
        elif line.startswith("--- "):
            continue
        elif line.startswith("@@") and cur is not None:
            m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            h = {"old_start": int(m.group(1)), "new_start": int(m.group(2)), "removed": [], "added": []}
            files[cur].append(h)
        elif h is not None and line.startswith("+"):
            h["added"].append(line[1:])
        elif h is not None and line.startswith("-"):
            h["removed"].append(line[1:])
    return files


def line_kind(s):
    if ATTR_RE.match(s):
        return "attribute"
    if GUARD_RE.match(s):
        return "guard"
    if s.strip() == "":
        return "blank"
    return "other"


def purity(hunks):
    offending = []
    for h in hunks:
        for s in h["removed"]:
            offending.append({"hunk_new_start": h["new_start"], "side": "removed", "kind": line_kind(s), "line": s})
        for s in h["added"]:
            k = line_kind(s)
            if k not in ("attribute", "guard"):
                offending.append({"hunk_new_start": h["new_start"], "side": "added", "kind": k, "line": s})
    return offending


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.environ.get("MP_REPO"), required=os.environ.get("MP_REPO") is None)
    ap.add_argument("--branch", required=True)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    rng = f"{BASE}..origin/{a.branch}"
    head = git(a.repo, "rev-parse", "--short=8", f"origin/{a.branch}").strip()
    status = [l.split("\t") for l in git(a.repo, "diff", "--name-status", "--no-renames", rng).splitlines() if l]
    branch_files = set(git(a.repo, "ls-tree", "-r", "--name-only", f"origin/{a.branch}").splitlines())
    numstat = {}
    for l in git(a.repo, "diff", "--numstat", "--no-renames", rng).splitlines():
        ins, dele, p = l.split("\t")
        numstat[p] = (int(ins), int(dele))
    hunks = parse_hunks(git(a.repo, "diff", "-U0", "--no-color", "--no-renames", rng))

    files, counts = [], collections.Counter()
    snap_pure, snap_other, attr_lines = [], [], collections.Counter()
    tmpl = []
    for st, path in status:
        cat = classify(path, branch_files)
        counts[cat] += 1
        ins, dele = numstat.get(path, (0, 0))
        entry = {"path": path, "status": st, "category": cat, "insertions": ins, "deletions": dele,
                 "hunks": len(hunks.get(path, []))}
        if cat in ("snapshot", "template"):
            off = purity(hunks.get(path, []))
            entry["pure_attribute_and_guard"] = not off
            if off:
                entry["non_attribute_lines"] = off
            for h in hunks.get(path, []):
                for s in h["added"]:
                    if line_kind(s) == "attribute":
                        attr_lines[s.strip()] += 1
            if cat == "snapshot":
                (snap_pure if not off else snap_other).append(path)
            else:
                tmpl.append((path, not off))
        files.append(entry)

    # snapshot files on the branch that the diff does not touch, and Resources/<dir> with no test method of that name
    res_root = "tests/MessagePack.SourceGenerator.Tests/Resources/"
    changed = {p for _, p in status}
    snaps_on_branch = sorted(f for f in branch_files if f.startswith(res_root) and f.endswith(".cs"))
    unchanged_snaps = [f for f in snaps_on_branch if f not in changed]
    test_src = git(a.repo, "grep", "-h", r"Task [A-Za-z0-9_]*(", f"origin/{a.branch}", "--", "tests/MessagePack.SourceGenerator.Tests/")
    methods = set(re.findall(r"Task ([A-Za-z0-9_]+)\(", test_src))
    res_dirs = sorted({f[len(res_root):].split("/")[0] for f in snaps_on_branch if "/" in f[len(res_root):]})
    orphan_dirs = [d for d in res_dirs if d.split("(")[0] not in methods]

    others = [{"path": f["path"], "non_attribute_lines": f["non_attribute_lines"]}
              for f in files if f["category"] == "snapshot" and not f["pure_attribute_and_guard"]]
    n_snap = counts["snapshot"]
    other_dirs = sorted({os.path.dirname(p) for p in snap_other})
    summary = (f"{len(status)} files changed: {n_snap} snapshot, {counts['template']} template, "
               f"{counts['generated-output']} generated-output, {counts['test']} test, {counts['doc']} doc, "
               f"{counts['logic']} logic; {len(snap_pure)} of {n_snap} snapshots change only by attribute and "
               f"#if/#endif guard lines, {len(snap_other)} do not; {len(unchanged_snaps)} snapshot files left unchanged, "
               f"{len(orphan_dirs)} Resources dir(s) with no test method")
    ev = {
        "check": "diff-classifier",
        "branch": a.branch,
        "base": BASE,
        "head": head,
        "command": f"python3 review/scripts/diff_classifier.py --repo $MP_REPO --branch {a.branch} --write",
        "result": "pass",
        "summary": summary,
        "details": {
            "files_changed": len(status),
            "insertions": sum(i for i, _ in numstat.values()),
            "deletions": sum(d for _, d in numstat.values()),
            "insertions_by_category": {c: sum(f["insertions"] for f in files if f["category"] == c) for c in sorted(counts)},
            "deletions_by_category": {c: sum(f["deletions"] for f in files if f["category"] == c) for c in sorted(counts)},
            "counts_by_category": dict(sorted(counts.items())),
            "snapshots_total": n_snap,
            "snapshots_pure_attribute_and_guard": len(snap_pure),
            "snapshots_other": len(snap_other),
            "snapshots_other_directories": other_dirs,
            "snapshots_other_detail": others,
            "snapshot_files_on_branch": len(snaps_on_branch),
            "snapshot_files_unchanged": unchanged_snaps,
            "resource_dirs_on_branch": len(res_dirs),
            "resource_dirs_without_test_method": orphan_dirs,
            "templates_pure_attribute_and_guard": sum(1 for _, p in tmpl if p),
            "templates_total": len(tmpl),
            "distinct_added_attribute_lines": dict(attr_lines),
            "rules": {
                "pure": "no removed lines; every added line matches attribute /^\\s*\\[[^\\]]+\\]\\s*$/ or guard /^\\s*#\\s*(if|elif|else|endif)\\b/; CR ignored",
                "categories": "snapshot=tests/**/Resources/**; template=*.tt; generated-output=.cs with sibling .tt; test=other tests/**; doc=*.md; logic=rest",
            },
            "files": files,
        },
        "tool_versions": {"python": sys.version.split()[0],
                          "git": git(a.repo, "--version").strip()},
        "produced_by": "script",
    }
    if a.write:
        out = os.path.join(REVIEW, "evidence", a.branch, "diff-classifier.json")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(ev, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"wrote {out}")
    print(summary)
    for o in others:
        print(" other:", o["path"])
        for l in o["non_attribute_lines"]:
            print("    ", l["side"], l["kind"], repr(l["line"][:100]))


if __name__ == "__main__":
    main()
