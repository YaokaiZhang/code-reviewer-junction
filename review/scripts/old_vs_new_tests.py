#!/usr/bin/env python3
"""Old-versus-new test runner.

Runs the tests that a branch adds or changes on the base commit and on the
branch, and records per-test pass/fail on each side. A test that passes on the
base commit is marked "not evidence": it cannot show that the branch fixed
anything. Only a test that fails (or cannot build) on base and passes on the
branch counts as evidence for tier Tested.

How the base side is built: the branch's changed files under tests/ (test
files plus any helpers or resources they need) are copied onto a worktree of
the base commit. Production code stays at base.

Usage (CLI kept stable, used for several branches):
  python3 review/scripts/old_vs_new_tests.py --repo <clone> --branch ju26-issue-XXXX \
      --out review/evidence/ju26-issue-XXXX/old-vs-new-tests.json [--workdir DIR]

Python 3, standard library only. Never touches the clone's checked-out branch:
uses `git worktree add` under --workdir (default: a new temp dir).
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

TEST_ATTR = re.compile(r"\[\s*(Fact|Theory|SkippableFact|SkippableTheory)\b")
CLASS_RE = re.compile(r"\b(?:public|internal)?\s*(?:sealed\s+|static\s+|partial\s+|abstract\s+)*class\s+([A-Za-z_][A-Za-z0-9_]*)")
METHOD_RE = re.compile(r"\b(?:public|internal|private|protected)\s+(?:static\s+)?(?:async\s+)?[\w<>\[\],\s?]+?\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")
NS_RE = re.compile(r"^\s*namespace\s+([\w.]+)", re.M)


def run(cmd, cwd=None, check=True, env=None):
    p = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    if check and p.returncode != 0:
        sys.stderr.write(p.stdout)
        raise SystemExit(f"command failed: {' '.join(cmd)}")
    return p


def git(repo, *args, check=True):
    return run(["git", "-C", repo, *args], check=check).stdout


def resolve(repo, rev):
    for cand in (rev, f"origin/{rev}"):
        p = run(["git", "-C", repo, "rev-parse", "--verify", "--quiet", cand + "^{commit}"], check=False)
        if p.returncode == 0:
            return cand, p.stdout.strip()
    raise SystemExit(f"cannot resolve {rev}")


def show(repo, rev, path):
    p = run(["git", "-C", repo, "show", f"{rev}:{path}"], check=False)
    return p.stdout if p.returncode == 0 else None


def mask_strings(src):
    """Blank out raw (\"\"\"...\"\"\") and verbatim (@"...") string contents, keeping newlines,
    so `namespace`/`class` text inside test-input literals is not taken for real declarations."""
    def blank(m):
        return re.sub(r"[^\n]", " ", m.group(0))
    src = re.sub(r'(\$*)("{3,})[\s\S]*?\2', blank, src)
    src = re.sub(r'\$?@"(?:[^"]|"")*"', blank, src)
    return src


def test_methods(src):
    """Return {(class, method): body_text} for xunit test methods (simple scan, not a parser)."""
    if src is None:
        return {}
    out = {}
    lines = src.splitlines()
    masked = mask_strings(src).splitlines()
    ns = NS_RE.search(mask_strings(src))
    ns = ns.group(1) + "." if ns else ""
    cls = None
    pending_attr = False
    i = 0
    while i < len(lines):
        line = lines[i]
        m = CLASS_RE.search(masked[i])
        if m and not masked[i].strip().startswith("//"):
            cls = m.group(1)
        if TEST_ATTR.search(line):
            pending_attr = True
        elif pending_attr:
            mm = METHOD_RE.search(line)
            if mm and cls:
                # body: from this line until braces balance
                depth, body, j, started = 0, [], i, False
                while j < len(lines):
                    body.append(lines[j])
                    depth += lines[j].count("{") - lines[j].count("}")
                    if "{" in lines[j] or "=>" in lines[j]:
                        started = True
                    if started and depth <= 0 and ("}" in lines[j] or lines[j].rstrip().endswith(";")):
                        break
                    j += 1
                out[(ns + cls, mm.group(1))] = "\n".join(body)
                pending_attr = False
                i = j
        i += 1
    return out


def find_csproj(worktree, relpath):
    d = os.path.dirname(relpath)
    while d and d != ".":
        full = os.path.join(worktree, d)
        projs = [f for f in os.listdir(full) if f.endswith(".csproj")] if os.path.isdir(full) else []
        if projs:
            return os.path.join(d, projs[0])
        d = os.path.dirname(d)
    return None


def ensure_worktree(repo, path, sha):
    if os.path.isdir(os.path.join(path, ".git")) or os.path.isfile(os.path.join(path, ".git")):
        run(["git", "-C", path, "checkout", "--quiet", "--detach", "--force", sha])
        run(["git", "-C", path, "reset", "--quiet", "--hard", sha])
        run(["git", "-C", path, "clean", "-fdq"])  # keeps ignored bin/obj for speed
    else:
        run(["git", "-C", repo, "worktree", "add", "--quiet", "--detach", path, sha])


def parse_trx(trx_path):
    ns = {"t": "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"}
    root = ET.parse(trx_path).getroot()
    res = {}
    for r in root.iterfind(".//t:UnitTestResult", ns):
        name = r.get("testName")
        msg = r.find("t:Output/t:ErrorInfo/t:Message", ns)
        res[name] = {"outcome": r.get("outcome"), "message": (msg.text or "").strip()[:600] if msg is not None else None}
    return res


def dotnet_test(worktree, csproj, filt, trx_dir, label):
    os.makedirs(trx_dir, exist_ok=True)
    trx_name = f"{label}.trx"
    trx_path = os.path.join(trx_dir, trx_name)
    if os.path.exists(trx_path):
        os.remove(trx_path)
    cmd = ["dotnet", "test", csproj, "--filter", filt, "--logger", f"trx;LogFileName={trx_name}",
           "--results-directory", trx_dir, "-nologo"]
    env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT="1")
    p = run(cmd, cwd=worktree, check=False, env=env)
    build_errors = sorted(set(l.strip() for l in p.stdout.splitlines() if re.search(r"error (CS|MSB|NU)\d+", l)))
    # Warnings that explain a build failure without being errors themselves (e.g. a source generator that did not load).
    notable = sorted(set(l.strip() for l in p.stdout.splitlines() if re.search(r"warning (CS9057|CS8032|CS8784|CS8785|AD0001)", l)))
    results = parse_trx(trx_path) if os.path.exists(trx_path) else {}
    return {"command": " ".join(cmd), "exit_code": p.returncode, "build_errors": build_errors[:30],
            "notable_warnings": notable[:10],
            "results": results, "tail": p.stdout.splitlines()[-15:]}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=os.environ.get("MP_REPO"), required=os.environ.get("MP_REPO") is None)
    ap.add_argument("--branch", required=True)
    ap.add_argument("--base", default="32258fdb")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workdir", help="where worktrees go (reused if present); default: new temp dir")
    ap.add_argument("--sdk", help="run with this .NET SDK instead of the one global.json pins (written into both worktrees only)")
    args = ap.parse_args()

    repo = os.path.abspath(args.repo)
    base_ref, base_sha = resolve(repo, args.base)
    br_ref, br_sha = resolve(repo, args.branch)
    workdir = os.path.abspath(args.workdir) if args.workdir else tempfile.mkdtemp(prefix="oldnew-")
    os.makedirs(workdir, exist_ok=True)

    changed = []
    for line in git(repo, "diff", "--name-status", "--no-renames", base_sha, br_sha).splitlines():
        status, path = line.split("\t", 1)
        if path.startswith("tests/"):
            changed.append((status, path))
    test_files = [(s, p) for s, p in changed if p.endswith(".cs") and TEST_ATTR.search(show(repo, br_sha, p) or "")]

    # Classify test methods per file: added / modified / unchanged.
    methods = []
    for status, path in test_files:
        new = test_methods(show(repo, br_sha, path))
        old = test_methods(show(repo, base_sha, path)) if status != "A" else {}
        for (cls, name), body in new.items():
            change = "added" if (cls, name) not in old else ("modified" if old[(cls, name)] != body else "unchanged")
            methods.append({"file": path, "class": cls, "method": name, "change": change})

    base_wt = os.path.join(workdir, "base-with-branch-tests")
    br_wt = os.path.join(workdir, "branch")
    ensure_worktree(repo, base_wt, base_sha)
    ensure_worktree(repo, br_wt, br_sha)
    if args.sdk:  # same override on both sides, so base and branch still differ only by the change
        for wt in (base_wt, br_wt):
            with open(os.path.join(wt, "global.json"), "w") as f:
                json.dump({"sdk": {"version": args.sdk, "rollForward": "latestFeature"}}, f)

    # Copy every changed file under tests/ (tests + helpers/resources) from the branch onto base.
    copied, removed = [], []
    for status, path in changed:
        dst = os.path.join(base_wt, path)
        if status == "D":
            if os.path.exists(dst):
                os.remove(dst)
                removed.append(path)
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(os.path.join(br_wt, path), dst)
        copied.append(path)

    # Group by project and run.
    projects = {}
    for m in methods:
        proj = find_csproj(br_wt, m["file"])
        m["project"] = proj
        projects.setdefault(proj, set()).add(m["class"])

    runs = []
    trx_dir = os.path.join(workdir, "trx")
    for proj, classes in sorted(projects.items()):
        filt = "|".join(f"FullyQualifiedName~{c}." for c in sorted(classes))
        label = os.path.splitext(os.path.basename(proj))[0]
        sides = {}
        for side, wt in (("base", base_wt), ("branch", br_wt)):
            sys.stderr.write(f"[old-vs-new] {side}: dotnet test {proj}\n")
            sides[side] = dotnet_test(wt, proj, filt, trx_dir, f"{label}-{side}")
        runs.append({"project": proj, "filter": filt, **sides})

    def outcome(proj, side, cls, name):
        r = next(x for x in runs if x["project"] == proj)[side]
        key = f"{cls}.{name}"
        hits = {k: v for k, v in r["results"].items() if k == key or k.startswith(key + "(")}
        if not hits:
            return ("build_failed" if r["build_errors"] else "not_run"), None
        outs = {v["outcome"] for v in hits.values()}
        o = "passed" if outs == {"Passed"} else ("failed" if "Failed" in outs else "/".join(sorted(outs)).lower())
        msg = next((v["message"] for v in hits.values() if v["message"]), None)
        return o, msg

    for m in methods:
        m["base"], m["base_message"] = outcome(m["project"], "base", m["class"], m["method"])
        m["branch"], _ = outcome(m["project"], "branch", m["class"], m["method"])
        if m["branch"] == "build_failed":
            m["verdict"] = "not runnable here (project does not build on branch)"
        elif m["branch"] != "passed":
            m["verdict"] = "branch does not pass"
        elif m["base"] == "passed":
            m["verdict"] = "not evidence (passes on base)"
        elif m["base"] in ("failed", "build_failed"):
            m["verdict"] = "evidence (fails on base, passes on branch)" if m["base"] == "failed" else "evidence (does not build on base, passes on branch)"
        else:
            m["verdict"] = "unknown"

    new_or_changed = [m for m in methods if m["change"] != "unchanged"]
    ev = [m for m in new_or_changed if m["verdict"].startswith("evidence")]
    not_ev = [m for m in new_or_changed if m["verdict"].startswith("not evidence")]
    bad = [m for m in new_or_changed if m["verdict"] in ("branch does not pass", "unknown")]
    unrunnable = [m for m in new_or_changed if m["verdict"].startswith("not runnable")]
    counts = {
        "test_files_changed": len(test_files),
        "test_methods_added": sum(m["change"] == "added" for m in methods),
        "test_methods_modified": sum(m["change"] == "modified" for m in methods),
        "test_methods_unchanged_in_changed_files": sum(m["change"] == "unchanged" for m in methods),
        "new_or_changed_methods": len(new_or_changed),
        "evidence": len(ev),
        "not_evidence_passes_on_base": len(not_ev),
        "branch_not_passing_or_unknown": len(bad),
        "not_runnable_here": len(unrunnable),
    }
    for r in runs:
        for side in ("base", "branch"):
            r[side]["results_count"] = len(r[side]["results"])
            r[side].pop("results")

    dotnet_ver = run(["dotnet", "--version"], cwd=br_wt, check=False).stdout.strip()
    rel_out = os.path.relpath(os.path.abspath(args.out), os.getcwd())
    evidence = {
        "check": "old-vs-new-tests",
        "branch": args.branch,
        "base": args.base,
        "head": br_sha[:8],
        "command": f"python3 review/scripts/old_vs_new_tests.py --repo <clone> --branch {args.branch} --out {rel_out}"
                   + (f" --sdk {args.sdk}" if args.sdk else ""),
        # Nothing actually ran: the filter matched no test. That is a tool error, not a test failure.
        "result": "error" if new_or_changed and all(m["verdict"] in ("unknown",) or m["verdict"].startswith("not runnable") for m in new_or_changed)
                  else ("fail" if bad else ("error" if unrunnable else "pass")),
        "provides": (["flip-test"] if counts["evidence"] else []) + ["count"],
        "summary": (f"{counts['new_or_changed_methods']} new or changed test methods "
                    f"({counts['test_methods_added']} added, {counts['test_methods_modified']} modified): "
                    f"{counts['evidence']} fail on base and pass on branch, "
                    f"{counts['not_evidence_passes_on_base']} pass on base (not evidence), "
                    f"{counts['branch_not_passing_or_unknown']} fail on branch, "
                    f"{counts['not_runnable_here']} not runnable here (project does not build on branch)"),
        "details": {
            "counts": counts,
            "method_count_rule": "xunit methods marked [Fact]/[Theory]/[SkippableFact]/[SkippableTheory] found by a line scan of each changed test file",
            "base_side": "production code at base; branch versions of every changed file under tests/ copied on top",
            "copied_onto_base": copied,
            "removed_on_base": removed,
            "methods": methods,
            "runs": runs,
        },
        "tool_versions": {"dotnet_sdk": dotnet_ver, "python": sys.version.split()[0]},
        "sdk_override": args.sdk and f"global.json pins another SDK; both sides ran on {args.sdk} instead",
        "produced_by": "script",
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(evidence, f, indent=2)
        f.write("\n")
    print(evidence["summary"])


if __name__ == "__main__":
    main()
