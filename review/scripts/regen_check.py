#!/usr/bin/env python3
"""Regeneration check: run the source generator snapshot tests and record the result.

The snapshot tests in tests/MessagePack.SourceGenerator.Tests run the generator and compare
its output with the committed files under Resources/<test name>/ (embedded resources), and
compile the generated code. Running this test project is the regeneration check.

Each --run is LABEL=REV, optionally followed by modifiers separated by '+':
    revert:<path>   restore <path> from the base commit in the scratch worktree (removal test)
    take:<path>     copy <path> from origin/<branch> into the scratch worktree (run new tests on base)
    lf-snapshots    convert every Resources/**/*.cs to LF before building (line-ending probe)

Examples:
    python3 review/scripts/regen_check.py --repo <clone> --branch ju26-issue-2297 \
        --run base=32258fdb --run branch=origin/ju26-issue-2297 --out regeneration --write
    python3 review/scripts/regen_check.py --repo <clone> --branch ju26-issue-2297 \
        --run 'no-tu=origin/ju26-issue-2297+revert:src/MessagePack.SourceGenerator/Transforms/TransformUtilities.cs' \
        --out transformutilities-removal --write

Scratch worktrees are created with `git worktree add --detach` under --workdir
(default: a temp dir) as wt-<branch-number>-<label>; the clone's checked-out branch is never touched.
Needs the .NET SDK pinned in global.json on PATH.
"""
import argparse, glob, json, os, platform, re, shutil, subprocess, sys, tempfile, time
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
REVIEW = os.path.dirname(HERE)
BASE = "32258fdb"
TEST_PROJ = "tests/MessagePack.SourceGenerator.Tests"
NS = {"t": "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"}


def sh(cmd, cwd=None, check=True):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed ({p.returncode}):\n{p.stdout[-3000:]}\n{p.stderr[-3000:]}")
    return p


def parse_trx(path):
    root = ET.parse(path).getroot()
    res = root.findall(".//t:Results/t:UnitTestResult", NS)
    out = {"total": len(res), "passed": 0, "failed": 0, "skipped": 0, "failures": [], "passed_names": []}
    for r in res:
        o = r.get("outcome")
        name = r.get("testName")
        if o == "Passed":
            out["passed"] += 1
            out["passed_names"].append(name)
        elif o == "Failed":
            out["failed"] += 1
            msg = r.find(".//t:ErrorInfo/t:Message", NS)
            out["failures"].append({"test": name, "message": (msg.text or "")[:2500] if msg is not None else ""})
        else:
            out["skipped"] += 1
    out["failures"].sort(key=lambda f: f["test"])
    out["passed_names"].sort()
    return out


def build_errors(text):
    errs = sorted(set(re.findall(r"error [A-Z]+\d+: [^\[\r\n]*", text)))
    return errs[:50]


def run_one(repo, workdir, branch, spec):
    label, rest = spec.split("=", 1)
    parts = rest.split("+")
    rev, mods = parts[0], parts[1:]
    m = re.search(r"(\d+)$", branch)
    num = m.group(1) if m else "x"
    wt = os.path.join(workdir, f"wt-{num}-{label}")
    if os.path.exists(wt):
        sh(["git", "-C", repo, "worktree", "remove", "--force", wt], check=False)
        shutil.rmtree(wt, ignore_errors=True)
    sh(["git", "-C", repo, "worktree", "add", "--detach", wt, rev])
    applied = []
    for m in mods:
        if m.startswith("revert:"):
            p = m[len("revert:"):]
            sh(["git", "-C", wt, "checkout", BASE, "--", p])
            applied.append({"modifier": "revert", "path": p,
                            "diff_after_revert_vs_rev": sh(["git", "-C", wt, "diff", "--stat", "HEAD"]).stdout.strip()})
        elif m.startswith("take:"):
            p = m[len("take:"):]
            sh(["git", "-C", wt, "checkout", f"origin/{branch}", "--", p])
            applied.append({"modifier": "take-from-branch", "path": p})
        elif m == "lf-snapshots":
            n = 0
            for f in glob.glob(os.path.join(wt, TEST_PROJ, "Resources", "**", "*.cs"), recursive=True):
                b = open(f, "rb").read()
                if b"\r\n" in b:
                    open(f, "wb").write(b.replace(b"\r\n", b"\n"))
                    n += 1
            applied.append({"modifier": "lf-snapshots", "files_converted_crlf_to_lf": n})
        else:
            raise SystemExit(f"unknown modifier {m}")
    head = sh(["git", "-C", wt, "rev-parse", "--short=8", "HEAD"]).stdout.strip()
    eol = sh(["git", "-C", wt, "ls-files", "--eol", f"{TEST_PROJ}/Resources"]).stdout
    eol_counts = {}
    for l in eol.splitlines():
        k = " ".join(l.split()[:2])
        eol_counts[k] = eol_counts.get(k, 0) + 1

    t0 = time.time()
    b = sh(["dotnet", "build", TEST_PROJ, "-nodeReuse:false", "-v:q", "-nologo"], cwd=wt, check=False)
    build_s = round(time.time() - t0, 1)
    result = {"label": label, "rev": rev, "head": head, "worktree": wt, "modifiers": applied,
              "snapshot_eol_in_worktree": eol_counts, "build_exit_code": b.returncode, "build_seconds": build_s}
    if b.returncode != 0:
        result["build_errors"] = build_errors(b.stdout + b.stderr)
        return result
    resdir = os.path.join(wt, "TestResults-regen")
    t0 = time.time()
    t = sh(["dotnet", "test", TEST_PROJ, "--no-build", "--logger", "trx;LogFileName=regen.trx",
            "--results-directory", resdir, "-nologo"], cwd=wt, check=False)
    result["test_exit_code"] = t.returncode
    result["test_seconds"] = round(time.time() - t0, 1)
    trx = os.path.join(resdir, "regen.trx")
    if os.path.exists(trx):
        result.update(parse_trx(trx))
    else:
        result["test_output_tail"] = (t.stdout + t.stderr)[-3000:]
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.environ.get("MP_REPO"), required=os.environ.get("MP_REPO") is None)
    ap.add_argument("--branch", required=True)
    ap.add_argument("--run", action="append", required=True, help="LABEL=REV[+modifier...]")
    ap.add_argument("--out", default="regeneration")
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    workdir = a.workdir or tempfile.mkdtemp(prefix="regen-")

    runs = [run_one(a.repo, workdir, a.branch, s) for s in a.run]
    by = {r["label"]: r for r in runs}
    ok = all(r.get("build_exit_code") == 0 and r.get("failed", 1) == 0 and r.get("total", 0) > 0 for r in runs)
    bits = []
    for r in runs:
        if r["build_exit_code"] != 0:
            bits.append(f"{r['label']}: build failed with {len(r.get('build_errors', []))} distinct errors")
        else:
            bits.append(f"{r['label']}: {r.get('passed')} passed, {r.get('failed')} failed of {r.get('total')}")
    # tests that differ between runs
    names = {}
    for r in runs:
        if "passed_names" in r:
            names[r["label"]] = (set(r["passed_names"]), {f["test"] for f in r["failures"]})
    comparisons = {}
    labels = list(names)
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            x, y = labels[i], labels[j]
            px, fx = names[x]
            py, fy = names[y]
            comparisons[f"{x}_vs_{y}"] = {
                f"only_in_{x}": sorted((px | fx) - (py | fy)),
                f"only_in_{y}": sorted((py | fy) - (px | fx)),
                f"passed_in_{x}_failed_in_{y}": sorted(px & fy),
                f"failed_in_{x}_passed_in_{y}": sorted(fx & py),
            }
    cmd = (f"python3 review/scripts/regen_check.py --repo $MP_REPO --branch {a.branch} "
           + " ".join(f"--run '{s}'" for s in a.run) + f" --out {a.out} --write")
    ev = {
        "check": a.out,
        "branch": a.branch,
        "base": BASE,
        "command": cmd,
        "result": "pass" if ok else "fail",
        "summary": "; ".join(bits),
        "details": {"test_project": TEST_PROJ, "runs": runs, "comparisons": comparisons},
        "tool_versions": {
            "dotnet_sdk": sh(["dotnet", "--version"]).stdout.strip(),
            "os": f"{platform.system()} {platform.release()} {platform.machine()} (Linux, not macOS)" if platform.system() == "Linux" else platform.platform(),
            "python": sys.version.split()[0],
            "git": sh(["git", "--version"]).stdout.strip(),
        },
        "produced_by": "script",
    }
    if a.write:
        out = os.path.join(REVIEW, "evidence", a.branch, f"{a.out}.json")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(ev, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"wrote {out}")
    print(ev["result"], ev["summary"])


if __name__ == "__main__":
    main()
