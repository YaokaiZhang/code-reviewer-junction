#!/usr/bin/env python3
"""Isolation check: a differential run of the source generator and analyzers, base versus branch.

Legacy code often has weak tests, and new tests cannot show that a change left old behaviour alone.
This check needs no assertions. It builds the MessagePack source generator (which also holds the
analyzers) at the base commit and at the branch, feeds both the same corpus of inputs that existed
before the branch, captures everything they emit (generated source files, generator diagnostics,
analyzer diagnostics, compiler diagnostics of the final compilation), and diffs. Identical output on
an input means the change did not touch that input. Every difference must match a rule in
scripts/isolation/expected/<branch>.json, and each rule names the dossier claim that states that
intent. A difference no rule matches is "unexplained": a possible break.

Corpus (all taken from the BASE commit, so it is independent of the branch):
  1. every compilation the base tests in tests/MessagePack.SourceGenerator.Tests hand to Roslyn,
     recorded by running those tests once with a small recorder patched into the verifier plumbing
     (scripts/isolation/corpus_dump/). Sources are recorded after markup processing, with the test's
     own language version, compilation options and references.
  2. the real projects in the base repo that consume the generator, compiled as one compilation each
     with the sources, references and options MSBuild would pass to csc
     (scripts/isolation/DumpCompileInputs.targets).
  A separate group, kept out of the totals, runs the branch's NEW test inputs (the same recorder on the
  branch's test project) to show that the intended changes do show up.

Usage:
  python3 review/scripts/isolation_check.py --repo <clone> --branch ju26-issue-2297 [--write] [--fresh]

  --fresh   delete this run's worktrees, build output and recorded corpus first (determinism rerun)
  --write   write review/evidence/<branch>/isolation.json (otherwise print the summary only)

Worktrees: .work/worktrees/isolation/{base,b<NNNN>,corpus-base,corpus-b<NNNN>}, created with
`git worktree add --detach`; the clone's checked-out branch is never touched. Each gets a global.json
pinning --sdk (default 9.0.321); NBGV_GitEngine=Disabled is set because the clone is shallow.
Python 3, standard library only; needs ~/.dotnet with that SDK.
"""
import argparse, difflib, glob, hashlib, json, os, re, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
REVIEW = os.path.dirname(HERE)
ROOT = os.path.dirname(REVIEW)
ISO = os.path.join(HERE, "isolation")
HARNESS_DIR = os.path.join(ISO, "harness")
HARNESS_DLL = os.path.join(ROOT, ".work", "isolation", "harness-bin", "Release", "net8.0", "IsolationHarness.dll")
DUMP_TARGETS = os.path.join(ISO, "DumpCompileInputs.targets")
TEST_PROJ = "tests/MessagePack.SourceGenerator.Tests"
GEN_PROJ = "src/MessagePack.SourceGenerator/MessagePack.SourceGenerator.csproj"
GEN_DLL = "bin/MessagePack.SourceGenerator/Release/netstandard2.0/MessagePack.SourceGenerator.dll"
MP_NET8 = "bin/MessagePack/Release/net8.0"

# Real projects in the base repo that use the generator (they import tests/SourceGeneratorConsumer.props).
REAL_PROJECTS = [
    ("tests/MessagePack.GeneratedCode.Tests/MessagePack.GeneratedCode.Tests.csproj", "net8.0"),
    ("tests/MessagePack.SourceGenerator.ExecutionTests/MessagePack.SourceGenerator.ExecutionTests.csproj", "net8.0"),
    ("tests/MessagePack.SourceGenerator.MapModeExecutionTests/MessagePack.SourceGenerator.MapModeExecutionTests.csproj", "net8.0"),
    ("sandbox/Sandbox/Sandbox.csproj", "net8.0"),
    ("sandbox/SharedData/SharedData.csproj", "netstandard2.0"),
]
# Other projects under sandbox/ and tests/ that were looked at and left out, with the reason.
NOT_CONSUMERS = {
    "sandbox/DynamicCodeDumper": "does not reference the source generator",
    "sandbox/MessagePack.Internal": "does not reference the source generator",
    "sandbox/PerfBenchmarkDotNet": "does not reference the source generator",
    "sandbox/PerfNetFramework": "does not reference the source generator",
    "sandbox/TestData2": "does not reference the source generator",
    "sandbox/TestData.InvalidProject": "does not reference the source generator",
    "sandbox/TestData.InvalidSyntax": "does not reference the source generator",
    "tests/MessagePack.Tests": "does not reference the source generator as an analyzer (no SourceGeneratorConsumer.props)",
    "tests/MessagePack.Internal.Tests": "does not reference the source generator",
    "tests/MessagePack.Experimental.Tests": "does not reference the source generator",
    "tests/MessagePack.AspNetCoreMvcFormatter.Tests": "does not reference the source generator",
}
DIFF_CAP = 15
UNEXPLAINED_CAP = 20


def log(msg):
    sys.stderr.write(f"[isolation] {msg}\n")
    sys.stderr.flush()


def dotnet_env():
    home = os.path.expanduser("~/.dotnet")
    return dict(os.environ, DOTNET_ROOT=home, PATH=home + os.pathsep + os.environ.get("PATH", ""),
                NBGV_GitEngine="Disabled", DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1",
                MSBUILDDISABLENODEREUSE="1")


def sh(cmd, cwd=None, check=True, env=None):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env)
    if check and p.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed ({p.returncode}):\n{p.stdout[-4000:]}\n{p.stderr[-2000:]}")
    return p


def resolve(repo, rev):
    for cand in (rev, f"origin/{rev}"):
        p = sh(["git", "-C", repo, "rev-parse", "--verify", "--quiet", cand + "^{commit}"], check=False)
        if p.returncode == 0:
            return p.stdout.strip()
    raise SystemExit(f"cannot resolve {rev}")


def ensure_worktree(repo, path, sha, sdk, fresh):
    if fresh and os.path.exists(path):
        sh(["git", "-C", repo, "worktree", "remove", "--force", path], check=False)
        shutil.rmtree(path, ignore_errors=True)
        sh(["git", "-C", repo, "worktree", "prune"], check=False)
    if os.path.exists(os.path.join(path, ".git")):
        sh(["git", "-C", path, "checkout", "--quiet", "--detach", "--force", sha])
        sh(["git", "-C", path, "reset", "--quiet", "--hard", sha])
        sh(["git", "-C", path, "clean", "-fdq"])  # keeps ignored bin/obj for speed
    else:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        sh(["git", "-C", repo, "worktree", "add", "--quiet", "--detach", path, sha])
    with open(os.path.join(path, "global.json"), "w") as f:
        json.dump({"sdk": {"version": sdk, "rollForward": "latestFeature"}}, f)


def build_errors(text):
    return sorted(set(re.findall(r"error [A-Z]+\d+: [^\[\r\n]*", text)))[:20]


def build_side(wt, dump_dir):
    """Build the generator, and the real consumer projects with the compile-input recorder attached."""
    env = dotnet_env()
    out = {"generator": None, "projects": {}}
    p = sh(["dotnet", "build", GEN_PROJ, "-c", "Release", "-nologo"], cwd=wt, check=False, env=env)
    out["generator"] = {"exit_code": p.returncode, "errors": build_errors(p.stdout)}
    if p.returncode != 0:
        return out
    shutil.rmtree(dump_dir, ignore_errors=True)
    for proj, _tf in REAL_PROJECTS:
        p = sh(["dotnet", "build", proj, "-c", "Release", "-nologo",
                f"-p:CustomAfterMicrosoftCommonTargets={DUMP_TARGETS}", f"-p:IsolationDumpDir={dump_dir}"],
               cwd=wt, check=False, env=env)
        out["projects"][proj] = {"exit_code": p.returncode, "errors": build_errors(p.stdout)}
    return out


def record_test_corpus(wt, dump_dir, trx_dir):
    """Run the side's generator test project once with CorpusDump patched in; returns test outcome counts."""
    sh([sys.executable, os.path.join(ISO, "corpus_dump", "patch_verifiers.py"), wt])
    shutil.rmtree(dump_dir, ignore_errors=True)
    shutil.rmtree(trx_dir, ignore_errors=True)
    env = dict(dotnet_env(), CORPUS_DUMP_DIR=dump_dir)
    p = sh(["dotnet", "test", TEST_PROJ, "-p:TreatWarningsAsErrors=false", "-p:AllowUnsafeBlocks=true", "-nologo",
            "--logger", "trx;LogFileName=corpus.trx", "--results-directory", trx_dir], cwd=wt, check=False, env=env)
    tests = parse_trx(os.path.join(trx_dir, "corpus.trx"))
    return {"exit_code": p.returncode, "errors": build_errors(p.stdout), "tests": tests}


def parse_trx(path):
    import xml.etree.ElementTree as ET
    if not os.path.exists(path):
        return []
    ns = {"t": "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"}
    root = ET.parse(path).getroot()
    rows = []
    for r in root.iterfind(".//t:UnitTestResult", ns):
        rows.append({"name": r.get("testName"), "outcome": r.get("outcome")})
    defs = {}
    for d in root.iterfind(".//t:UnitTest", ns):
        tm = d.find("t:TestMethod", ns)
        if tm is not None:
            defs[d.get("name")] = tm.get("className")
    for r in rows:
        r["class"] = defs.get(r["name"])
    return rows


def load_test_corpus(dump_dir):
    inputs = {}
    for f in sorted(glob.glob(os.path.join(dump_dir, "*.json"))):
        d = json.load(open(f))
        extra = os.path.join(dump_dir, d["id"] + ".tests")
        if os.path.exists(extra):
            d["tests"] = d["tests"] + [l for l in open(extra).read().splitlines() if l]
        d["tests"] = sorted(set(d["tests"]))
        inputs[d["id"]] = d
    return inputs


def content_key(d):
    """Identity of a test input that ignores where its reference assemblies live on disk."""
    def proj(p):
        return {k: p.get(k) for k in ("language", "documents", "additional_files", "parse_options", "compilation_options",
                                       "has_analyzer_references", "assembly_name")} | {
            "refs": sorted(os.path.basename(r) for r in p.get("metadata_references", []))}
    body = proj(d) | {"project_references": [proj(p) for p in d.get("project_references", [])]}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]


def retarget_refs(d, side_wt):
    """Point MessagePack.dll / MessagePack.Annotations.dll at the side's own net8.0 build."""
    def fix(p):
        refs = []
        for r in p["metadata_references"]:
            name = os.path.basename(r)
            if r and r.startswith("mdblob:"):
                pass  # in-memory test assembly, saved by CorpusDump; same bytes on both sides
            elif name in ("MessagePack.dll", "MessagePack.Annotations.dll"):
                r = os.path.join(side_wt, MP_NET8, name)
            refs.append(r)
        p["metadata_references"] = refs
    d = json.loads(json.dumps(d))
    fix(d)
    for pr in d.get("project_references", []):
        fix(pr)
    return d


def read_tsv(path):
    props, items = {}, {"compile": [], "ref": [], "analyzer": [], "additional": []}
    last = None
    for line in open(path, encoding="utf-8").read().splitlines():
        parts = line.split("\t")
        if parts[0] == "prop" and len(parts) >= 3:
            last = parts[1]
            props[last] = [parts[2]] if parts[2] else []
        elif parts[0] in items and len(parts) == 2:
            items[parts[0]].append(parts[1])
            last = None
        elif last is not None:  # a ';'-separated property value was split into several lines
            props[last].append(line)
    return props, items


def lang_version(v):
    v = (v or "").strip().lower()
    if not v or v == "default":
        return "Default"
    if v in ("latest", "latestmajor", "preview"):
        return {"latest": "Latest", "latestmajor": "LatestMajor", "preview": "Preview"}[v]
    major, _, minor = v.partition(".")
    return f"CSharp{major}" + (f"_{minor}" if minor and minor != "0" else "")


def project_input(base_tsv, side_tsv, base_wt):
    """Sources and options from the BASE project; references from the side's own build of the same project."""
    props, items = read_tsv(base_tsv)
    _sprops, sitems = read_tsv(side_tsv)
    single = lambda k: (props.get(k) or [""])[0]
    nowarn = {w.strip() for w in props.get("NoWarn", []) if w.strip()}
    specific = {}
    for w in nowarn:
        specific[w if not w.isdigit() else f"CS{int(w):04d}"] = "Suppress"
    nullable = {"enable": "Enable", "disable": "Disable", "warnings": "Warnings", "annotations": "Annotations"}.get(single("Nullable").lower(), "Disable")
    return {
        "language": "C#",
        "assembly_name": single("AssemblyName"),
        "root": base_wt.rstrip("/") + "/",
        "documents": [{"name": c, "path": c} for c in items["compile"] if c.endswith(".cs")],
        "additional_files": [],
        "parse_options": {"language_version": lang_version(single("LangVersion")),
                          "preprocessor_symbols": [s for s in props.get("DefineConstants", []) if s], "documentation_mode": "Parse"},
        "compilation_options": {
            "output_kind": "ConsoleApplication" if single("OutputType").lower() == "exe" else "DynamicallyLinkedLibrary",
            "nullable": nullable,
            "allow_unsafe": single("AllowUnsafeBlocks").lower() == "true",
            "warning_level": int(single("WarningLevel") or 4),
            "general_diagnostic_option": "Default",
            "specific_diagnostic_options": specific,
            "check_overflow": single("CheckForOverflowUnderflow").lower() == "true",
            "optimization": "Release" if single("Optimize").lower() == "true" else "Debug",
        },
        "metadata_references": sitems["ref"],
        "project_references": [],
        "has_analyzer_references": True,
    }


COVERLET_VERSION = "10.1.0"
TOOLS = os.path.join(ROOT, ".work", "isolation", "tools")


def ensure_coverlet():
    exe = os.path.join(TOOLS, "coverlet")
    if not os.path.exists(exe):
        os.makedirs(TOOLS, exist_ok=True)
        with open(os.path.join(TOOLS, "global.json"), "w") as f:
            json.dump({"sdk": {"version": "9.0.321", "rollForward": "latestFeature"}}, f)
        sh(["dotnet", "tool", "install", "coverlet.console", "--version", COVERLET_VERSION, "--tool-path", TOOLS], cwd=TOOLS, env=dotnet_env())
    return exe


def changed_src_lines(repo, base_sha, br_sha):
    """Lines of src/ that the branch removes (base numbering) or adds (branch numbering), from git diff -U0."""
    out = {"base": [], "branch": []}
    diff = sh(["git", "-C", repo, "diff", "-U0", "--no-color", f"{base_sha}...{br_sha}", "--", "src/"]).stdout
    old_file = new_file = None
    old_ln = new_ln = 0
    for line in diff.splitlines():
        if line.startswith("--- "):
            old_file = line[6:] if line.startswith("--- a/") else None
        elif line.startswith("+++ "):
            new_file = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("@@"):
            m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            old_ln, new_ln = int(m.group(1)), int(m.group(2))
        elif line.startswith("-") and old_file:
            out["base"].append((old_file, old_ln, line[1:].strip()))
            old_ln += 1
        elif line.startswith("+") and new_file:
            out["branch"].append((new_file, new_ln, line[1:].strip()))
            new_ln += 1
    return out


def coverlet_run(gen_dll, inputs_dir, out_dir, cov_dir, cov_json):
    """Run the harness under coverlet on a private copy of the generator; returns {relpath: {line: hits}}
    (only lines coverlet has a sequence point for) and the command used."""
    exe = ensure_coverlet()
    shutil.rmtree(cov_dir, ignore_errors=True)
    os.makedirs(cov_dir)
    for f in glob.glob(os.path.join(os.path.dirname(gen_dll), "MessagePack.SourceGenerator.*")):
        shutil.copy(f, cov_dir)
    for f in glob.glob(os.path.join(os.path.dirname(HARNESS_DLL), "Microsoft.CodeAnalysis*.dll")):
        shutil.copy(f, cov_dir)  # coverlet's instrumenter must resolve the generator's Roslyn references
    gen_copy = os.path.join(cov_dir, "MessagePack.SourceGenerator.dll")
    shutil.rmtree(out_dir, ignore_errors=True)
    cmd = [exe, gen_copy, "--include-test-assembly", "--include", "[MessagePack.SourceGenerator]*", "--format", "json",
           "--output", cov_json, "--target", "dotnet",
           "--targetargs", f"{HARNESS_DLL} --generator {gen_copy} --inputs {inputs_dir} --out {out_dir}"]
    p = sh(cmd, cwd=TOOLS, check=False, env=dotnet_env())
    if p.returncode != 0 or not os.path.exists(cov_json):
        raise RuntimeError("coverlet failed:\n" + p.stdout[-2000:])
    data = json.load(open(cov_json))
    lines = {}
    for _mod, files in data.items():
        for path, classes in files.items():
            m = re.search(r"/(src/.*)$", path)
            rel = m.group(1) if m else path
            for _cls, methods in classes.items():
                for _meth, info in methods.items():
                    for ln, hits in info.get("Lines", {}).items():
                        lines.setdefault(rel, {})
                        lines[rel][int(ln)] = lines[rel].get(int(ln), 0) + hits
    return lines, cmd


def extra_side_steps(side, wt, work, ctx):
    """Per-side coverage of the changed src/ lines, over each main-corpus input (one coverlet run per input)
    and over the control group as a whole (one run). Returns {"per_input": {iid: {...}}, "control": {...}}."""
    changed = ctx["changed"][side]
    if not changed:
        return {"per_input": {}, "control": None, "trackable": [], "not_trackable": []}
    gen_dll = os.path.join(wt, GEN_DLL)
    per_input, trackable_seen, cmd = {}, {}, None
    for iid in ctx["main_ids"]:
        one = os.path.join(work, f"cov-{side}", iid, "in")
        os.makedirs(one, exist_ok=True)
        shutil.copy(os.path.join(ctx["side_dirs"][side], iid + ".json"), one)
        lines, cmd = coverlet_run(gen_dll, one, os.path.join(work, f"cov-{side}", iid, "out"),
                                  os.path.join(work, f"cov-{side}", iid, "gen"), os.path.join(work, f"cov-{side}", iid, "coverage.json"))
        hit = []
        for f, ln, text in changed:
            if ln in lines.get(f, {}):
                trackable_seen[(f, ln)] = text
                if lines[f][ln] > 0:
                    hit.append(f"{f}:{ln}")
        # Instrumented run must give the same output as the plain run, or coverage would describe a different run.
        a = json.load(open(os.path.join(work, f"cov-{side}", iid, "out", iid + ".json")))
        b = json.load(open(os.path.join(work, f"out-{side}", iid + ".json")))
        same = all(a.get(k) == b.get(k) for k in ("generated", "generator_diagnostics", "analyzer_diagnostics", "compiler_diagnostics"))
        per_input[iid] = {"hit": hit, "instrumented_output_matches": same}
    control = None
    if ctx["control_dir"].get(side):
        lines, _ = coverlet_run(gen_dll, ctx["control_dir"][side], os.path.join(work, f"cov-{side}", "control", "out"),
                                os.path.join(work, f"cov-{side}", "control", "gen"), os.path.join(work, f"cov-{side}", "control", "coverage.json"))
        control = sorted(f"{f}:{ln}" for f, ln, _t in changed if lines.get(f, {}).get(ln, 0) > 0)
        for f, ln, text in changed:
            if ln in lines.get(f, {}):
                trackable_seen[(f, ln)] = text
    return {"per_input": per_input, "control": control,
            "trackable": sorted(f"{f}:{ln}" for f, ln in trackable_seen),
            "not_trackable": [{"side": side, "file": f, "line": ln, "text": t} for f, ln, t in changed if (f, ln) not in trackable_seen],
            "command": " ".join(cmd) if cmd else None}


def run_harness(gen_dll, inputs_dir, out_dir):
    shutil.rmtree(out_dir, ignore_errors=True)
    p = sh(["dotnet", HARNESS_DLL, "--generator", gen_dll, "--inputs", inputs_dir, "--out", out_dir], env=dotnet_env(), check=False)
    return {"exit_code": p.returncode, "log": (p.stderr or "").strip().splitlines()[-3:]}


# ---------------------------------------------------------------- comparison


def diag_key(d):
    return (d["id"], d["severity"], d["location"], d["message"])


def gen_file_of(loc):
    m = re.match(r"generated:(.*):(\d+)$", loc)
    return (m.group(1), int(m.group(2))) if m else (None, None)


def line_map(a, b):
    """Map 1-based line numbers of text a to text b through unchanged regions."""
    sm = difflib.SequenceMatcher(None, a.split("\n"), b.split("\n"), autojunk=False)
    mp = {}
    for tag, i1, i2, j1, _j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                mp[i1 + k + 1] = j1 + k + 1
    return mp


def short_diff(a, b, name):
    lines = list(difflib.unified_diff((a or "").split("\n"), (b or "").split("\n"), f"base/{name}", f"branch/{name}", n=1, lineterm=""))
    if len(lines) > DIFF_CAP:
        lines = lines[:DIFF_CAP] + [f"... ({len(lines) - DIFF_CAP} more diff lines)"]
    return "\n".join(lines)


def match_diag(rule_m, d):
    return (re.fullmatch(rule_m.get("id", ".*"), d["id"]) and re.search(rule_m.get("message", ""), d["message"])
            and re.search(rule_m.get("location", ""), d["location"]))


def compare(base, branch, rules):
    """Return a list of difference items for one input, each with 'explained_by' (claims) or None."""
    items = []
    if base.get("status") != "ok" or branch.get("status") != "ok":
        if base.get("status") != branch.get("status") or base.get("error") != branch.get("error"):
            items.append({"kind": "harness", "file": None, "diff": f"base: {base.get('status')} {base.get('error') or ''}\nbranch: {branch.get('status')} {branch.get('error') or ''}", "explained_by": None})
        return items

    def base_has(pattern):
        cats = ("generator_diagnostics", "analyzer_diagnostics", "compiler_diagnostics")
        return any(match_diag(pattern, d) for c in cats for d in base.get(c, [])) or any(
            re.search(pattern.get("message", ""), e) for e in base.get("generator_exceptions", []) if pattern.get("exceptions"))

    # Generated files.
    file_explained = {}
    bg, rg = base["generated"], branch["generated"]
    for name in sorted(set(bg) | set(rg)):
        a, b = bg.get(name), rg.get(name)
        if a == b:
            continue
        claims, explained = [], False
        if a is not None and b is not None:
            text = b
            for r in rules:
                m = r["match"]
                if m.get("type") != "generated_rewrite" or not re.search(m.get("file", ""), name):
                    continue
                new, n = re.subn(m["regex"], m["replace"], text, flags=re.M)
                if n:
                    text = new
                    claims.append(r["claim"])
                if text == a:
                    explained = True
                    break
        else:
            change = "added" if a is None else "removed"
            for r in rules:
                m = r["match"]
                if m.get("type") == f"generated_file_{change}" and re.search(m.get("file", ""), name) and \
                        (not m.get("requires_base") or base_has(m["requires_base"])):
                    claims, explained = [r["claim"]], True
                    break
        file_explained[name] = (sorted(set(claims)) if explained else None)
        items.append({"kind": "generated", "file": name, "change": "changed" if a and b else ("added" if a is None else "removed"),
                      "diff": short_diff(a, b, name.split("/")[-1]), "explained_by": file_explained[name],
                      "rules": [r["what"] for r in rules if r["claim"] in (claims if explained else [])]})

    # Diagnostics and generator exceptions.
    for cat in ("generator_diagnostics", "analyzer_diagnostics", "compiler_diagnostics"):
        ba = [diag_key(d) for d in base.get(cat, [])]
        bb = [diag_key(d) for d in branch.get(cat, [])]
        removed, added = list(ba), []
        for k in bb:
            if k in removed:
                removed.remove(k)
            else:
                added.append(k)
        # A diagnostic inside a generated file that only moved because lines were inserted above it.
        for r_ in list(removed):
            f, line = gen_file_of(r_[2])
            if f is None:
                continue
            full = next((n for n in bg if n.endswith("/" + f)), None)
            if not full or full not in rg:
                continue
            target = line_map(bg[full], rg[full]).get(line)
            moved = (r_[0], r_[1], f"generated:{f}:{target}", r_[3])
            if target and moved in added:
                removed.remove(r_)
                added.remove(moved)
                items.append({"kind": "diagnostic", "category": cat, "change": "moved", "file": f,
                              "diff": f"- {r_[0]} {r_[2]}\n+ {moved[0]} {moved[2]}  (same diagnostic, line moved by the generated-file change)",
                              "explained_by": file_explained.get(full), "rules": ["moved with its generated file"]})
        for change, keys in (("removed", removed), ("added", added)):
            for k in keys:
                d = {"id": k[0], "severity": k[1], "location": k[2], "message": k[3]}
                claim, what = None, None
                for r in rules:
                    m = r["match"]
                    if m.get("type") == f"diagnostic_{change}" and cat in m.get("categories", [cat]) and match_diag(m, d) and \
                            (not m.get("requires_base") or base_has(m["requires_base"])):
                        claim, what = r["claim"], r["what"]
                        break
                items.append({"kind": "diagnostic", "category": cat, "change": change, "file": k[2],
                              "diff": f"{'-' if change == 'removed' else '+'} {k[1]} {k[0]} at {k[2]}: {k[3]}",
                              "explained_by": [claim] if claim else None, "rules": [what] if what else []})
    eb, er = base.get("generator_exceptions", []), branch.get("generator_exceptions", [])
    for change, keys in (("removed", [e for e in eb if e not in er]), ("added", [e for e in er if e not in eb])):
        for e in keys:
            claim, what = None, None
            for r in rules:
                m = r["match"]
                if m.get("type") == f"generator_exception_{change}" and re.search(m.get("message", ""), e):
                    claim, what = r["claim"], r["what"]
                    break
            items.append({"kind": "generator_exception", "change": change, "file": None,
                          "diff": f"{'-' if change == 'removed' else '+'} {e}", "explained_by": [claim] if claim else None,
                          "rules": [what] if what else []})
    return items


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=os.environ.get("MP_REPO"), required=os.environ.get("MP_REPO") is None)
    ap.add_argument("--branch", required=True)
    ap.add_argument("--base", default="32258fdb")
    ap.add_argument("--sdk", default="9.0.321")
    ap.add_argument("--workdir", default=os.path.join(ROOT, ".work", "worktrees", "isolation"))
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    timings = {}

    repo = os.path.abspath(args.repo)
    num = re.search(r"(\d+)$", args.branch).group(1)
    base_sha, br_sha = resolve(repo, args.base), resolve(repo, args.branch)
    rules_path = os.path.join(ISO, "expected", f"{args.branch}.json")
    rules_doc = json.load(open(rules_path))
    rules = rules_doc["rules"]
    work = os.path.join(ROOT, ".work", "isolation", num)
    if args.fresh:
        shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)

    wts = {k: os.path.join(args.workdir, k) for k in ("base", f"b{num}", "corpus-base", f"corpus-b{num}")}
    for k, path in wts.items():
        ensure_worktree(repo, path, base_sha if "base" in k else br_sha, args.sdk, args.fresh)
    base_wt, br_wt = wts["base"], wts[f"b{num}"]

    # Harness (built once; Roslyn 4.12.0 as the generator expects).
    t = time.time()
    stale = not os.path.exists(HARNESS_DLL) or any(os.path.getmtime(f) > os.path.getmtime(HARNESS_DLL)
                                                   for f in glob.glob(os.path.join(HARNESS_DIR, "*")))
    if args.fresh or stale:
        p = sh(["dotnet", "build", HARNESS_DIR, "-c", "Release", "-nologo"], cwd=HARNESS_DIR, check=False, env=dotnet_env())
        if p.returncode != 0:
            raise SystemExit("harness build failed:\n" + p.stdout[-3000:])
    timings["harness_build_s"] = round(time.time() - t, 1)

    t = time.time()
    log("building base and branch")
    builds = {"base": build_side(base_wt, os.path.join(work, "projects-base")),
              "branch": build_side(br_wt, os.path.join(work, "projects-branch"))}
    timings["build_s"] = round(time.time() - t, 1)
    for side, b in builds.items():
        if b["generator"]["exit_code"] != 0:
            raise SystemExit(f"{side} generator build failed: {b['generator']['errors']}")

    t = time.time()
    log("recording test inputs (base, then branch)")
    rec_base = record_test_corpus(wts["corpus-base"], os.path.join(work, "corpus-base"), os.path.join(work, "trx-base"))
    rec_br = record_test_corpus(wts[f"corpus-b{num}"], os.path.join(work, "corpus-branch"), os.path.join(work, "trx-branch"))
    timings["record_corpus_s"] = round(time.time() - t, 1)
    tests_base = load_test_corpus(os.path.join(work, "corpus-base"))
    tests_br = load_test_corpus(os.path.join(work, "corpus-branch"))
    base_keys = {content_key(d) for d in tests_base.values()}
    new_inputs = {i: d for i, d in tests_br.items() if content_key(d) not in base_keys}

    # Inputs per side.
    groups = {}
    skipped = {"tests": [], "projects": []}
    side_dirs = {}
    for side, wt in (("base", base_wt), ("branch", br_wt)):
        d = os.path.join(work, f"inputs-{side}")
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
        side_dirs[side] = d
        for i, inp in tests_base.items():
            if inp["language"] != "C#":
                continue
            x = retarget_refs(inp, wt)
            x["id"] = f"t-{i}"
            json.dump(x, open(os.path.join(d, x["id"] + ".json"), "w"))
            groups[x["id"]] = "tests"
        for i, inp in new_inputs.items():
            x = retarget_refs(inp, wt)
            x["id"] = f"n-{i}"
            json.dump(x, open(os.path.join(d, x["id"] + ".json"), "w"))
            groups[x["id"]] = "new"
        for proj, tf in REAL_PROJECTS:
            name = os.path.splitext(os.path.basename(proj))[0]
            btsv = os.path.join(work, "projects-base", f"{name}.{tf}.tsv")
            stsv = os.path.join(work, f"projects-{side}", f"{name}.{tf}.tsv")
            if not (os.path.exists(btsv) and os.path.exists(stsv)):
                if side == "base":
                    skipped["projects"].append(f"{proj}: build did not reach the compiler on {'base' if not os.path.exists(btsv) else 'branch'} "
                                               f"({(builds['base']['projects'].get(proj) or {}).get('errors')})")
                continue
            x = project_input(btsv, stsv, base_wt)
            x["id"] = f"p-{name}"
            json.dump(x, open(os.path.join(d, x["id"] + ".json"), "w"))
            groups[x["id"]] = "projects"

    t = time.time()
    log("running harness on both sides")
    hr = {"base": run_harness(os.path.join(base_wt, GEN_DLL), side_dirs["base"], os.path.join(work, "out-base")),
          "branch": run_harness(os.path.join(br_wt, GEN_DLL), side_dirs["branch"], os.path.join(work, "out-branch"))}
    timings["harness_s"] = round(time.time() - t, 1)
    t = time.time()
    log("coverage of changed src/ lines (coverlet), per real project and for the control group")
    ctrl_dirs = {}
    for side in ("base", "branch"):
        cd = os.path.join(work, f"control-inputs-{side}")
        shutil.rmtree(cd, ignore_errors=True)
        os.makedirs(cd)
        for f in glob.glob(os.path.join(side_dirs[side], "t-*.json")):
            shutil.copy(f, cd)
        ctrl_dirs[side] = cd
    ctx = {"changed": changed_src_lines(repo, base_sha, br_sha), "side_dirs": side_dirs, "control_dir": ctrl_dirs,
           "main_ids": [i for i in sorted(groups) if groups[i] == "projects"]}
    cov = {side: extra_side_steps(side, wt, work, ctx) for side, wt in (("base", base_wt), ("branch", br_wt))}
    timings["coverage_s"] = round(time.time() - t, 1)

    # Compare.
    results = {}
    for iid in sorted(groups):
        bp, rp = os.path.join(work, "out-base", iid + ".json"), os.path.join(work, "out-branch", iid + ".json")
        if not (os.path.exists(bp) and os.path.exists(rp)):
            results[iid] = {"status": "missing-output"}
            continue
        b, r = json.load(open(bp)), json.load(open(rp))
        res = {"status": "compared"}
        if b.get("status") != "ok":
            res["status"] = "base-harness-crash"
        elif b.get("compiler_errors", 0) > 0:
            res["status"] = "base-compile-errors"
            res["base_errors"] = sorted({d["id"] for d in b["compiler_diagnostics"] if d["severity"] == "Error"})
        res["items"] = compare(b, r, rules)
        results[iid] = res

    def label(iid):
        if iid.startswith("p-"):
            return "project " + iid[2:]
        d = tests_base.get(iid[2:]) or new_inputs.get(iid[2:])
        names = d["tests"] if d else ["?"]
        return names[0] + (f" (+{len(names) - 1} more tests)" if len(names) > 1 else "")

    # Tallies. MAIN group = real projects, counted per unit (one generated file, or one diagnostic), so the
    # totals say how much real output was compared. CONTROL group = test snippets, counted per input.
    def collect_explained(store, iid, it):
        for c in it["explained_by"] or []:
            for w in it.get("rules") or ["?"]:
                e = store.setdefault((c, w), {"claim": c, "what": w, "units": 0, "inputs": set(), "example": None})
                e["units"] += 1
                e["inputs"].add(iid)
                if e["example"] is None:
                    e["example"] = {"input": label(iid), "diff": it["diff"]}

    def explained_rows(store, unit_word):
        return sorted(({"claim": v["claim"], "what": v["what"], unit_word: v["units"] if unit_word == "units" else len(v["inputs"]),
                        "inputs": sorted(label(i) for i in v["inputs"]) if unit_word == "units" else len(v["inputs"]),
                        "example": v["example"]} for v in store.values()), key=lambda x: (x["claim"], x["what"]))

    def not_compared_row(iid, res):
        return {"input": label(iid), "id": iid, "reason": res["status"] + (f" {res.get('base_errors')}" if res.get("base_errors") else ""),
                "differs_anyway": bool(res.get("items")),
                "unexplained_items": [it["diff"][:300] for it in res.get("items", []) if not it["explained_by"]][:3]}

    def unexplained_row(iid, it):
        return {"input": label(iid), "id": iid, "kind": "generated" if it["kind"] == "generated" else it["kind"],
                "category": it.get("category"), "file": it.get("file"), "change": it.get("change"), "diff": it["diff"],
                "note": ""}

    main_ids = [i for i in groups if groups[i] == "projects"]
    totals = {"inputs": 0, "compared": 0, "same": 0, "differ": 0, "explained": 0, "unexplained": 0, "not_compared": 0}
    per_project, main_expl, unexplained, not_compared = [], {}, [], []
    for iid in main_ids:
        res = results[iid]
        b = json.load(open(os.path.join(work, "out-base", iid + ".json")))
        r = json.load(open(os.path.join(work, "out-branch", iid + ".json")))
        items = res.get("items", [])
        gen_union = set(b.get("generated", {})) | set(r.get("generated", {}))
        same_diags = 0
        for cat in ("generator_diagnostics", "analyzer_diagnostics", "compiler_diagnostics"):
            rest = [diag_key(d) for d in r.get(cat, [])]
            for k in (diag_key(d) for d in b.get(cat, [])):
                if k in rest:
                    rest.remove(k)
                    same_diags += 1
        gen_items = [it for it in items if it["kind"] == "generated"]
        other_items = [it for it in items if it["kind"] != "generated"]
        units = len(gen_union) + same_diags + len(other_items)
        row = {"project": iid[2:], "status": res["status"], "documents": len(json.load(open(os.path.join(side_dirs["base"], iid + ".json")))["documents"]),
               "generated_files_base": len(b.get("generated", {})), "generated_files_branch": len(r.get("generated", {})),
               "formatter_files_base": sum(1 for n in b.get("generated", {}) if "Formatter" in n.split("/")[-1]),
               "generated_files_differ": len(gen_items),
               "generated_files_unexplained": sum(1 for it in gen_items if not it["explained_by"]),
               "diagnostics_base": sum(len(b.get(c, [])) for c in ("generator_diagnostics", "analyzer_diagnostics", "compiler_diagnostics")),
               "diagnostics_branch": sum(len(r.get(c, [])) for c in ("generator_diagnostics", "analyzer_diagnostics", "compiler_diagnostics")),
               "diagnostic_changes": len(other_items),
               "diagnostic_changes_unexplained": sum(1 for it in other_items if not it["explained_by"]),
               "differing_types": sorted(it["file"].split("/")[-1] for it in gen_items)[:40]}
        per_project.append(row)
        totals["inputs"] += units
        if res["status"] != "compared":
            totals["not_compared"] += units
            not_compared.append(not_compared_row(iid, res))
            continue
        totals["compared"] += units
        totals["same"] += units - len(items)
        totals["differ"] += len(items)
        for it in items:
            if it["explained_by"]:
                totals["explained"] += 1
                collect_explained(main_expl, iid, it)
            else:
                totals["unexplained"] += 1
                unexplained.append(unexplained_row(iid, it))
    explained_list = explained_rows(main_expl, "units")

    ctrl_ids = [i for i in groups if groups[i] == "tests"]
    ctrl = {"inputs": len(ctrl_ids), "compared": 0, "same": 0, "differ": 0, "explained": 0, "unexplained": 0, "not_compared": 0}
    ctrl_expl, ctrl_unexpl, ctrl_nc = {}, [], []
    for iid in ctrl_ids:
        res = results[iid]
        if res["status"] != "compared":
            ctrl["not_compared"] += 1
            ctrl_nc.append(not_compared_row(iid, res))
            continue
        ctrl["compared"] += 1
        items = res["items"]
        if not items:
            ctrl["same"] += 1
            continue
        ctrl["differ"] += 1
        bad = [it for it in items if not it["explained_by"]]
        ctrl["unexplained" if bad else "explained"] += 1
        ctrl_unexpl += [unexplained_row(iid, it) for it in bad]
        for it in items:
            collect_explained(ctrl_expl, iid, it)

    new_ids = [i for i in groups if groups[i] == "new"]
    new_differ = [i for i in new_ids if results[i].get("items")]
    br_rows = rec_br["tests"]
    base_methods = {f"{r['class']}.{r['name'].split('(')[0].split('.')[-1]}" for r in rec_base["tests"] if r["class"]}
    br_recorded = {t for d in tests_br.values() for t in d["tests"]}
    br_new_methods = sorted({f"{r['class']}.{r['name'].split('(')[0].split('.')[-1]}" for r in br_rows if r["class"]} - base_methods)
    br_unrecorded = [m for m in br_new_methods if not any(n.split(".")[-1] == m.split(".")[-1] and n.split(".")[-2] == m.split(".")[-2] for n in br_recorded)]
    new_summary = {"inputs": len(new_ids), "differ": len(new_differ),
                   "new_test_methods_on_branch": len(br_new_methods),
                   "new_test_methods_not_recorded": br_unrecorded,
                   "not_recorded_reason": "these tests build their compilation themselves (CSharpCompilation / CSharpGeneratorDriver) instead of through the verifiers the recorder patches" if br_unrecorded else None,
                   "unexplained_inputs": sum(1 for i in new_differ if any(not it["explained_by"] for it in results[i]["items"])),
                   "note": "the branch's own new or changed test inputs, recorded the same way on the branch's test project; shown separately and not part of the totals",
                   "examples": [{"input": label(i), "diff": next(it["diff"] for it in results[i]["items"])} for i in new_differ[:5]]}

    # Corpus description.
    base_test_rows = rec_base["tests"]
    recorded_names = {t for d in tests_base.values() for t in d["tests"]}
    method_of = lambda row: f"{row['class']}.{row['name'].split('(')[0].split('.')[-1]}"
    methods = sorted({method_of(r) for r in base_test_rows if r["class"]})
    unrecorded = [m for m in methods if not any(n.endswith(m.split(".")[-1]) and n.split(".")[-2] == m.split(".")[-2] for n in recorded_names)]
    vb = [m for m in unrecorded if "VB" in m or "VisualBasic" in m]
    reasons = []
    by_class = {}
    for m in unrecorded:
        by_class.setdefault(m.rsplit(".", 1)[0].split(".")[-1], []).append(m.rsplit(".", 1)[1])
    for cls, ms in sorted(by_class.items()):
        reasons.append(f"{cls}: {len(ms)} test method(s) build no C# compilation through the patched verifiers ({', '.join(sorted(ms)[:6])}{'...' if len(ms) > 6 else ''})")
    corpus = [
        {"group": "real projects that consume the generator (base)", "role": "main",
         "how": "each project compiled as a whole with the sources, references and options MSBuild passes to csc at base; references from each side's own build",
         "inputs": len(main_ids), "projects": [i[2:] for i in main_ids],
         "unit": "one generated file or one diagnostic; totals count units",
         "skipped": len(skipped["projects"]) + len(NOT_CONSUMERS),
         "skip_reasons": skipped["projects"] + [f"{k}: {v}" for k, v in NOT_CONSUMERS.items()]},
        {"group": "generator and analyzer test inputs (base)", "role": "control",
         "how": f"every distinct compilation the {len(base_test_rows)} base test cases of {TEST_PROJ} hand to Roslyn, recorded by running them once; already snapshot-tested by CI, so kept out of the headline totals",
         "base_test_run": f"{sum(1 for r in base_test_rows if r['outcome'] == 'Passed')} of {len(base_test_rows)} passed",
         "inputs": len(ctrl_ids),
         "test_methods": len(methods), "test_methods_recorded": len(methods) - len(unrecorded),
         "skipped": len(unrecorded), "skip_reasons": reasons},
    ]

    # Cross coverage with the output diff (main corpus).
    changed = ctx["changed"]
    text_of = {(side, f, ln): t for side in ("base", "branch") for f, ln, t in changed[side]}
    trackable = [(side, *x.rsplit(":", 1)) for side in ("base", "branch") for x in cov[side]["trackable"]]
    trackable = [(sd, f, int(ln)) for sd, f, ln in trackable]
    reached = {(side, *h.rsplit(":", 1)) for side in ("base", "branch") for v in cov[side]["per_input"].values() for h in v["hit"]}
    reached = {(sd, f, int(ln)) for sd, f, ln in reached}
    ctrl_reached = {(side, *h.rsplit(":", 1)) for side in ("base", "branch") for h in (cov[side]["control"] or [])}
    ctrl_reached = {(sd, f, int(ln)) for sd, f, ln in ctrl_reached}
    cov_inputs = []
    for iid in ctx["main_ids"]:
        hb = cov["base"]["per_input"].get(iid, {}).get("hit", [])
        hr_ = cov["branch"]["per_input"].get(iid, {}).get("hit", [])
        cov_inputs.append({"input": iid[2:], "reaches_change": bool(hb or hr_), "hit_base_lines": hb, "hit_branch_lines": hr_,
                           "output_differs": bool(results[iid].get("items")),
                           "instrumented_output_matches": all(cov[s_]["per_input"].get(iid, {}).get("instrumented_output_matches", True) for s_ in ("base", "branch"))})
    coverage = {
        "tool": f"coverlet.console {COVERLET_VERSION}, line coverage of the Release MessagePack.SourceGenerator.dll while the harness runs; one run per real project per side, plus one run over the whole control group per side",
        "changed_lines_source": f"git diff -U0 {args.base}...{args.branch} -- src/ (base: removed lines in base numbering; branch: added lines in branch numbering)",
        "changed_lines": {"base": len(changed["base"]), "branch": len(changed["branch"])},
        "trackable": len(trackable),
        "reached": sum(1 for x in trackable if x in reached),
        "unreached": [{"side": sd, "file": f, "line": ln, "text": text_of.get((sd, f, ln), ""), "reached_by_control_group": (sd, f, ln) in ctrl_reached}
                      for sd, f, ln in sorted(trackable) if (sd, f, ln) not in reached],
        "not_trackable": cov["base"]["not_trackable"] + cov["branch"]["not_trackable"],
        "not_trackable_rule": "a changed line coverlet has no sequence point for (declaration, brace, comment, attribute, constant, or a file that is not compiled such as a .tt template) is listed here and never counted as safe",
        "inputs_touching": sum(1 for c in cov_inputs if c["reaches_change"]),
        "inputs_untouched": sum(1 for c in cov_inputs if not c["reaches_change"]),
        "untouched_but_differ": [c["input"] for c in cov_inputs if not c["reaches_change"] and c["output_differs"]],
        "per_input": cov_inputs,
        "control_group_reached": sum(1 for x in trackable if x in ctrl_reached),
        "granularity_note": "coverage is per real project (one compilation), not per type, so a project counts as touching if any of its types runs a changed line",
        "command": cov["base"].get("command") or cov["branch"].get("command"),
    }

    result = "fail" if totals["unexplained"] or ctrl["unexplained"] or coverage["untouched_but_differ"] else "pass"
    n_proj = len(main_ids)
    summary = (f"{n_proj} real projects, {totals['inputs']} output units (generated files and diagnostics): {totals['same']} same, "
               f"{totals['differ']} differ, {totals['explained']} explained"
               + (f" by {', '.join(sorted({e['claim'] for e in explained_list}))}" if explained_list else "")
               + f", {totals['unexplained']} unexplained"
               + (f", {totals['not_compared']} not compared" if totals["not_compared"] else "")
               + f"; coverage: {coverage['reached']} of {coverage['trackable']} trackable changed lines reached, {len(coverage['not_trackable'])} not trackable"
               + f"; control group of {ctrl['inputs']} test inputs: {ctrl['differ']} differ, {ctrl['unexplained']} unexplained")
    harness_rel = os.path.relpath(HARNESS_DIR, ROOT)
    evidence = {
        "check": "isolation",
        "branch": args.branch,
        "base": args.base,
        "command": f"python3 review/scripts/isolation_check.py --repo $MP_REPO --branch {args.branch} --write  (coverage inside it: coverlet <copy of MessagePack.SourceGenerator.dll> --include-test-assembly --include '[MessagePack.SourceGenerator]*' --format json --target dotnet --targetargs '<IsolationHarness.dll> --generator <copy> --inputs <one project input> --out <dir>')",
        "result": result,
        "provides": ["old-vs-new-run", "count"],
        "summary": summary,
        "details": {
            "what": "Differential run: the base and branch builds of the source generator and analyzers get the same inputs; every difference in generated files or diagnostics must match a rule naming a claim.",
            "expected_rules": os.path.relpath(rules_path, ROOT),
            "rules": [{"claim": r["claim"], "what": r["what"]} for r in rules],
            "corpus": corpus,
            "totals": totals,
            "explained": explained_list,
            "unexplained_total_items": len(unexplained),
            "unexplained": unexplained[:UNEXPLAINED_CAP],
            "not_compared": not_compared,
            "per_project": per_project,
            "coverage": coverage,
            "control": {"totals": ctrl, "explained": explained_rows(ctrl_expl, "inputs"),
                        "unexplained_total_items": len(ctrl_unexpl), "unexplained": ctrl_unexpl[:UNEXPLAINED_CAP],
                        "not_compared": ctrl_nc},
            "new_inputs": new_summary,
            "builds": {s: {"generator_exit": b["generator"]["exit_code"],
                           "projects": {k: v["exit_code"] for k, v in b["projects"].items()}} for s, b in builds.items()},
            "test_recording": {"base": {"exit_code": rec_base["exit_code"], "cases": len(rec_base["tests"])},
                               "branch": {"exit_code": rec_br["exit_code"], "cases": len(rec_br["tests"])}},
            "harness_runs": hr,
            "compared_outputs": "generated files (hint name -> text, CRLF normalised to LF); generator, analyzer and compiler diagnostics of the final compilation (id, severity, file:line, message); generator exceptions",
            "generators_and_analyzers": "all [Generator] types and all C# DiagnosticAnalyzers in MessagePack.SourceGenerator.dll (Release build), as a user's build gets them; analyzers see the compilation with the generated files",
            "base_sha": base_sha[:8], "branch_sha": br_sha[:8],
            "sdk": args.sdk, "roslyn": "4.12.0",
            "harness": harness_rel,
            "timings": timings | {"total_s": round(time.time() - t0, 1)},
        },
        "tool_versions": {"dotnet_sdk": args.sdk, "Microsoft.CodeAnalysis.CSharp": "4.12.0"},
        "produced_by": "script",
    }
    out_json = os.path.join(work, "isolation.json")
    json.dump(evidence, open(out_json, "w"), indent=2)
    json.dump({i: results[i] for i in results}, open(os.path.join(work, "all-results.json"), "w"), indent=1)
    print(summary)
    if args.write:
        dst = os.path.join(REVIEW, "evidence", args.branch, "isolation.json")
        prev = json.load(open(dst)) if os.path.exists(dst) else None
        def fingerprint(ev):
            dd = ev["details"]
            c = dd.get("coverage", {})
            return {"totals": dd.get("totals"), "control": (dd.get("control") or {}).get("totals"),
                    "new_inputs": [(dd.get("new_inputs") or {}).get(k) for k in ("inputs", "differ", "unexplained_inputs")],
                    "coverage": [c.get(k) for k in ("trackable", "reached", "inputs_touching")], "result": ev.get("result")}
        if prev and args.fresh:
            evidence["details"]["rerun_matches"] = fingerprint(prev) == fingerprint(evidence)
            evidence["details"]["rerun"] = {"how": "second run with --fresh: worktrees (with their bin and obj), recorded corpus and outputs deleted and recreated; the harness is rebuilt incrementally",
                                            "compared": "totals, control totals, new-input counts, coverage counts and result",
                                            "first_run": fingerprint(prev), "rerun": fingerprint(evidence)}
        elif prev and "rerun_matches" in prev.get("details", {}) and fingerprint(prev) == fingerprint(evidence):
            evidence["details"]["rerun_matches"] = prev["details"]["rerun_matches"]
            evidence["details"]["rerun"] = prev["details"].get("rerun")
        json.dump(evidence, open(dst, "w"), indent=2)
        open(dst, "a").write("\n")
        log(f"wrote {os.path.relpath(dst, ROOT)}")


if __name__ == "__main__":
    main()
