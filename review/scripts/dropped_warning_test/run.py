#!/usr/bin/env python3
"""Evidence harness for ju26-issue-2283 (written by the reviewing agent for this branch).

Builds three worktrees of the target clone and runs the same tests on each:

  base      base commit 32258fdb, with the branch's GenericsFormatterTests.cs copied in
  branch    origin/ju26-issue-2283 as committed
  nofilter  the branch with ONE line reverted: the ReportIfLocatedInCompilation wrapper
            (ablation: crash fix kept, filter removed)

On each side it runs GenericsFormatterTests (the branch's 3 new tests plus the existing
ones) and DroppedWarningProbe.cs (this folder), which runs MsgPack00xMessagePackAnalyzer
on small consumer projects that use a closed generic type from another assembly.

Writes:
  <out-dir>/old-vs-new-tests.json   the branch's new tests on base / branch / nofilter
  <out-dir>/dropped-warning.json    analyzer diagnostics per probe case on each side

Usage:
  python3 review/scripts/dropped_warning_test/run.py --repo <clone> \
      --out-dir review/evidence/ju26-issue-2283 [--workdir DIR]

Python 3, standard library only. Never touches the clone's checked-out branch.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

BASE = "32258fdb"
BRANCH = "ju26-issue-2283"
TC = "src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs"
TEST_FILE = "tests/MessagePack.SourceGenerator.Tests/GenericsFormatterTests.cs"
TEST_PROJ = "tests/MessagePack.SourceGenerator.Tests"
FILTER_LINE = "        this.reportDiagnostic = reportAnalyzerDiagnostic is null ? null : diagnostic => ReportIfLocatedInCompilation(reportAnalyzerDiagnostic, diagnostic);"
BASE_LINE = "        this.reportDiagnostic = reportAnalyzerDiagnostic;"
NEW_TESTS = [
    "ClosedGenericStruct_FromMetadataReference",
    "ClosedGenericRecordStruct_FromMetadataReference",
    "ClosedGenericStruct_FromMetadataReference_UnkeyedMember",
]
HERE = os.path.dirname(os.path.abspath(__file__))
TRX_NS = {"t": "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"}
CMD = "python3 review/scripts/dropped_warning_test/run.py --repo <clone> --out-dir review/evidence/ju26-issue-2283"


def run(cmd, cwd=None, env=None, check=True):
    p = subprocess.run(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if check and p.returncode != 0:
        sys.stderr.write(p.stdout[-4000:])
        raise SystemExit("command failed: " + " ".join(cmd))
    return p


def resolve(repo, rev):
    for cand in (rev, "origin/" + rev):
        p = run(["git", "-C", repo, "rev-parse", "--verify", "--quiet", cand + "^{commit}"], check=False)
        if p.returncode == 0:
            return p.stdout.strip()
    raise SystemExit("cannot resolve " + rev)


def worktree(repo, path, commit):
    if os.path.exists(path):
        run(["git", "-C", repo, "worktree", "remove", "--force", path], check=False)
        shutil.rmtree(path, ignore_errors=True)
    run(["git", "-C", repo, "worktree", "add", "--detach", "-f", path, commit])


def full_suite(wt, workdir, name):
    trx = os.path.join(workdir, "full-%s.trx" % name)
    if os.path.exists(trx):
        os.remove(trx)
    cmd = ["dotnet", "test", TEST_PROJ, "--logger", "trx;LogFileName=" + trx]
    run(cmd, cwd=wt, env=dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT="1"), check=False)
    res = {r.get("testName"): r.get("outcome") for r in ET.parse(trx).getroot().iterfind(".//t:UnitTestResult", TRX_NS)}
    return res


def run_side(wt, workdir, name):
    shutil.copy(os.path.join(HERE, "DroppedWarningProbe.cs"), os.path.join(wt, TEST_PROJ))
    probe_out = os.path.join(workdir, "probe-%s.json" % name)
    trx = os.path.join(workdir, "trx-%s.trx" % name)
    for f in (probe_out, trx):
        if os.path.exists(f):
            os.remove(f)
    env = dict(os.environ, DROPPED_WARNING_OUT=probe_out, DOTNET_CLI_TELEMETRY_OPTOUT="1")
    cmd = ["dotnet", "test", TEST_PROJ, "--filter",
           "FullyQualifiedName~DroppedWarningProbe|FullyQualifiedName~GenericsFormatterTests",
           "--logger", "trx;LogFileName=" + trx]
    p = run(cmd, cwd=wt, env=env, check=False)
    if not os.path.exists(trx):
        sys.stderr.write(p.stdout[-4000:])
        raise SystemExit("no test results for side " + name)
    results = {}
    for r in ET.parse(trx).getroot().iterfind(".//t:UnitTestResult", TRX_NS):
        msg = r.find(".//t:Message", TRX_NS)
        first, reported = None, []
        if msg is not None and msg.text:
            lines = [ln.strip() for ln in msg.text.splitlines() if ln.strip()]
            first = lines[0][:300]
            # The verifier prints each unexpected diagnostic as a "// error|warning ID: message" line.
            reported = sorted({ln[3:200] for ln in lines if ln.startswith("// ") and (" AD0001" in ln or " CS8785" in ln or " MsgPack0" in ln)})
        results[r.get("testName").split(".")[-1]] = {"outcome": r.get("outcome"), "message": first, "unexpected_diagnostics": reported}
    probe = json.load(open(probe_out, encoding="utf-8-sig")) if os.path.exists(probe_out) else None
    return {"command": " ".join(cmd), "results": results, "probe": probe}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.environ.get("MP_REPO"))
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--workdir")
    a = ap.parse_args()
    repo = os.path.abspath(a.repo)
    workdir = os.path.abspath(a.workdir or tempfile.mkdtemp(prefix="wt-2283-"))
    os.makedirs(workdir, exist_ok=True)
    base = resolve(repo, BASE)
    head = resolve(repo, BRANCH)

    sides = {}
    wt = os.path.join(workdir, "base")
    worktree(repo, wt, base)
    test_src = run(["git", "-C", repo, "show", head + ":" + TEST_FILE]).stdout
    open(os.path.join(wt, TEST_FILE), "w", encoding="utf-8").write(test_src)
    sides["base"] = run_side(wt, workdir, "base")

    wt = os.path.join(workdir, "branch")
    worktree(repo, wt, head)
    sides["branch"] = run_side(wt, workdir, "branch")

    wt = os.path.join(workdir, "nofilter")
    worktree(repo, wt, head)
    path = os.path.join(wt, TC)
    src = open(path, encoding="utf-8-sig").read()
    if src.count(FILTER_LINE) != 1:
        raise SystemExit("filter line not found exactly once")
    open(path, "w", encoding="utf-8").write(src.replace(FILTER_LINE, BASE_LINE))
    sides["nofilter"] = run_side(wt, workdir, "nofilter")

    full = {s: full_suite(os.path.join(workdir, s), workdir, s) for s in ("base", "branch")}
    pre = sorted(n for n in full["branch"] if not any(n.endswith("." + t) for t in NEW_TESTS) and not n.startswith("DroppedWarningProbe."))
    full_summary = {
        "command": "dotnet test " + TEST_PROJ + "  (whole project, on base and branch worktrees)",
        "pre_existing_tests": len(pre),
        "pre_existing_passing": {s: sum(1 for n in pre if full[s].get(n) == "Passed") for s in full},
        "pre_existing_changed_outcome": [n for n in pre if full["base"].get(n) != full["branch"].get(n)],
        "excluded": NEW_TESTS + ["DroppedWarningProbe.Probe"],
    }
    dotnet = run(["dotnet", "--version"]).stdout.strip()
    versions = {"dotnet_sdk": dotnet, "Microsoft.CodeAnalysis": "4.12.0 (Directory.Packages.props)",
                "Microsoft.CodeAnalysis.Testing": "1.1.2 (Directory.Packages.props)", "python": sys.version.split()[0]}

    # old-vs-new
    methods = []
    for t in NEW_TESTS:
        row = {"method": t, "file": TEST_FILE}
        for s in sides:
            row[s] = sides[s]["results"].get(t, {"outcome": "not_run", "message": None, "unexpected_diagnostics": []})
        b, br = row["base"]["outcome"], row["branch"]["outcome"]
        row["verdict"] = ("evidence: fails on base, passes on branch" if b == "Failed" and br == "Passed"
                          else "not evidence: passes on base" if b == "Passed" else "branch does not pass")
        row["needs_filter"] = row["nofilter"]["outcome"] != "Passed"
        methods.append(row)
    existing = sorted(n for n in sides["branch"]["results"] if n not in NEW_TESTS and n != "Probe")
    existing_ok = {s: sum(1 for n in existing if sides[s]["results"].get(n, {}).get("outcome") == "Passed") for s in sides}
    evidence = sum(1 for m in methods if m["verdict"].startswith("evidence"))
    need = [m["method"] for m in methods if m["needs_filter"]]
    ovn_extra = "; whole test project: %d of %d pre-existing tests pass on base and %d on branch" % (
        full_summary["pre_existing_passing"]["base"], full_summary["pre_existing_tests"], full_summary["pre_existing_passing"]["branch"])
    ovn = {
        "check": "old-vs-new-tests",
        "branch": BRANCH,
        "base": BASE,
        "command": CMD,
        "result": "pass" if evidence == len(methods) else "fail",
        "summary": "%d of %d new tests fail on base and pass on branch; %d of them (%s) also fails when only the filter is removed"
                   % (evidence, len(methods), len(need), ", ".join(need) or "none") + ovn_extra,
        "details": {
            "head": head,
            "base_side": "base commit with the branch's GenericsFormatterTests.cs copied in; production code at base",
            "nofilter_side": "branch with one line reverted to base: " + BASE_LINE.strip(),
            "methods": methods,
            "full_suite": full_summary,
            "existing_tests_in_class": len(existing),
            "existing_tests_passing": existing_ok,
            "dotnet_test_command": sides["branch"]["command"],
            "note": "shared review/scripts/old_vs_new_tests.py was tried first and ran 0 of the 3 tests (it reads 'namespace TempProject' from a raw string literal in the test file as the class namespace, so its test filter matched nothing); this harness was used instead",
        },
        "tool_versions": versions,
        "produced_by": "hand",
    }

    # dropped-warning
    cases = []
    for i, c in enumerate(sides["branch"]["probe"] or []):
        row = {"case": c["name"], "lib_reference": c["lib_reference"]}
        for s in sides:
            pc = (sides[s]["probe"] or [])[i]
            row[s] = {"diagnostics": pc["diagnostics"], "analyzer_exceptions": pc["analyzer_exceptions"]}
        b_ids = sorted(d["id"] for d in row["base"]["diagnostics"])
        br_ids = sorted(d["id"] for d in row["branch"]["diagnostics"])
        row["dropped_on_branch"] = sorted(set(b_ids) - set(br_ids))
        row["base_crashed"] = bool(row["base"]["analyzer_exceptions"])
        row["branch_crashed"] = bool(row["branch"]["analyzer_exceptions"])
        cases.append(row)
    clean = [c for c in cases if c["dropped_on_branch"] and not c["base_crashed"]]
    headline = clean[0] if clean else None
    dw = {
        "check": "dropped-warning",
        "branch": BRANCH,
        "base": BASE,
        "command": CMD,
        "result": "fail" if headline else "pass",
        "summary": ("%s (%s) is reported on base without any analyzer crash and is absent on branch; %d of %d probe cases lose a diagnostic on branch"
                    % (headline["dropped_on_branch"][0], headline["case"], sum(1 for c in cases if c["dropped_on_branch"]), len(cases)))
                   if headline else "no probe case loses a diagnostic on branch without a crash on base",
        "details": {
            "head": head,
            "headline_case": headline,
            "cases": cases,
            "probe_source": "review/scripts/dropped_warning_test/DroppedWarningProbe.cs",
            "how": "the probe runs MsgPack00xMessagePackAnalyzer via CompilationWithAnalyzers on a consumer compilation that references a small library either as a metadata image or as a compilation reference; it records every diagnostic and every analyzer exception",
            "result_meaning": "fail = a diagnostic the base reported is silently gone on the branch",
        },
        "tool_versions": versions,
        "produced_by": "hand",
    }
    os.makedirs(a.out_dir, exist_ok=True)
    for name, obj in (("old-vs-new-tests.json", ovn), ("dropped-warning.json", dw)):
        with open(os.path.join(a.out_dir, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2)
            f.write("\n")
    print(ovn["summary"])
    print(dw["summary"])


if __name__ == "__main__":
    main()
