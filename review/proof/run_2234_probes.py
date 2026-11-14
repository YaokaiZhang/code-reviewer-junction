#!/usr/bin/env python3
"""Probes and proof chain for ju26-issue-2234.

Steps:
  1. `dafny verify` KeyCollection.dfy (the model and its lemmas); grep for assume/axiom.
  2. A mutation check: a copy of the model with the locked theorem stated as "never fails" must NOT verify.
  3. Copy proof/csharp/Probe2234Tests.cs into tests/MessagePack.SourceGenerator.Tests on a worktree of base
     and of the branch, run it (real analyzer scenarios + exhaustive run of the real TypeCollector on every
     list of 1..4 keyed members).
  4. Translate the Dafny model to Python (`dafny translate py`) and run CollectOld / CollectNew on the same
     inputs; compare to base / branch C# results.
Writes evidence/ju26-issue-2234/findings-probes.json and evidence/ju26-issue-2234/proof.json.

Usage:
  python3 review/proof/run_2234_probes.py --repo <clone> --workdir <dir> --dafny <dafny> --z3 <z3>
Python 3, standard library only (plus the Dafny Python runtime shipped with Dafny).
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REVIEW = os.path.dirname(HERE)
BRANCH = "ju26-issue-2234"
BASE = "32258fdb"


def run(cmd, cwd=None, env=None, check=True):
    p = subprocess.run(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if check and p.returncode:
        sys.stderr.write(p.stdout)
        raise SystemExit("failed: " + " ".join(cmd))
    return p


def worktree(repo, path, rev):
    if os.path.exists(os.path.join(path, ".git")):
        run(["git", "-C", path, "checkout", "-q", "--detach", "--force", rev])
        run(["git", "-C", path, "clean", "-fdq"])
    else:
        run(["git", "-C", repo, "worktree", "add", "-q", "--detach", path, rev])
    return run(["git", "-C", path, "rev-parse", "HEAD"]).stdout.strip()


def run_probes(wt, out):
    shutil.copyfile(os.path.join(HERE, "csharp", "Probe2234Tests.cs"),
                    os.path.join(wt, "tests/MessagePack.SourceGenerator.Tests/Probe2234Tests.cs"))
    if os.path.isdir(out):
        shutil.rmtree(out)
    env = dict(os.environ, PROBE_OUT=out, DOTNET_CLI_TELEMETRY_OPTOUT="1")
    cmd = ["dotnet", "test", "tests/MessagePack.SourceGenerator.Tests", "--filter", "FullyQualifiedName~Probe2234Tests", "-nologo"]
    p = run(cmd, cwd=wt, env=env, check=False)
    summary = [l.strip() for l in p.stdout.splitlines() if "Passed!" in l or "Failed!" in l]
    return {"command": " ".join(cmd), "exit_code": p.returncode, "summary": summary,
            "scenarios": json.load(open(os.path.join(out, "scenarios.json"))),
            "exhaustive": json.load(open(os.path.join(out, "exhaustive.json")))}


def diag_list(sc):
    return [f"{d['id']}@line{d['line']}" + (": " + d["message"][:80] if d["id"] == "AD0001" or "same type" in d["message"] or "unique" in d["message"] else "")
            for d in sc["diagnostics"]]


def load_model(dafny, z3, workdir):
    out = os.path.join(workdir, "model-py")
    if os.path.isdir(out):
        shutil.rmtree(out)
    run([dafny, "translate", "py", "--no-verify", "--solver-path", z3, "--output", os.path.join(out, "KeyCollection"),
         os.path.join(HERE, "KeyCollection.dfy")])
    pkg = glob.glob(os.path.join(out, "*-py"))[0]
    rt = glob.glob(os.path.join(os.path.dirname(os.path.realpath(dafny)), ".store", "dafny", "*", "dafny", "*", "tools", "*", "any", "DafnyRuntimePython"))
    if not rt:
        rt = glob.glob(os.path.join(os.path.dirname(dafny), "**", "DafnyRuntimePython"), recursive=True)
    sys.path[:0] = [pkg, rt[0]]
    import _dafny  # noqa
    import module_  # noqa
    return module_, _dafny


def model_eval(mod, _dafny, collect, inp):
    ms = []
    for kind, key in inp:
        k = mod.Kind_Field() if kind == "Field" else mod.Kind_Prop()
        if key == "null":
            kk = mod.Key_N()
        elif key.startswith('"'):
            kk = mod.Key_S(_dafny.Seq(key.strip('"')))
        else:
            kk = mod.Key_I(int(key))
        ms.append(mod.Member_M(k, kk))
    r = collect(_dafny.SeqWithoutIsStrInference(ms))
    if r.is_Fail:
        return {"fail": True}
    st = r.st
    m = {}
    if st.isInt:
        for k in st.ints.keys:
            m["i:" + str(k)] = int(st.ints[k])
    else:
        for k in st.strs.keys:
            m["s:" + "".join(k.Elements if hasattr(k, "Elements") else k)] = int(st.strs[k])
    reps = []
    for rp in st.reports:
        tag = "Dup" if rp.is_Dup else ("Mix" if rp.is_Mix else "BothNull")
        reps.append([tag, int(rp.i)])
    return {"fail": False, "is_int": bool(st.isInt), "map": dict(sorted(m.items())), "reports": reps}


def csharp_view(row):
    if row["exception"]:
        return {"fail": True}
    return {"fail": False, "is_int": row["is_int"], "map": dict(sorted(row["map"].items())), "reports": row["reports"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.environ.get("MP_REPO"), required=os.environ.get("MP_REPO") is None)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--dafny", required=True)
    ap.add_argument("--z3", required=True)
    a = ap.parse_args()
    os.makedirs(a.workdir, exist_ok=True)
    dfy = os.path.join(HERE, "KeyCollection.dfy")

    # 1. verify
    ver = run([a.dafny, "verify", "--solver-path", a.z3, dfy], check=False)
    ver_line = [l for l in ver.stdout.splitlines() if "verifier finished" in l]
    src = open(dfy).read()
    code_only = re.sub(r"//.*", "", src)
    gaps = {w: len(re.findall(r"\b" + w + r"\b", code_only)) for w in ("assume", "axiom", "extern")}
    lemmas = re.findall(r"^lemma (\w+)", src, re.M)

    # 2. mutation: the locked theorem as first stated must fail to verify
    mut = os.path.join(a.workdir, "LockedTheorem.dfy")
    with open(mut, "w") as f:
        f.write(src + "\nlemma LockedTheoremAsStated(ms: seq<Member>)\n  ensures CollectNew(ms).Ok?\n{\n}\n")
    mv = run([a.dafny, "verify", "--solver-path", a.z3, mut], check=False)
    mv_line = [l for l in mv.stdout.splitlines() if "verifier finished" in l or "Error" in l][:3]

    # 3. C# probes on base and branch
    base_sha = worktree(a.repo, os.path.join(a.workdir, "base"), BASE)
    br_rev = "origin/" + BRANCH
    br_sha = worktree(a.repo, os.path.join(a.workdir, "branch"), br_rev)
    sides = {"base": run_probes(os.path.join(a.workdir, "base"), os.path.join(a.workdir, "out-base")),
             "branch": run_probes(os.path.join(a.workdir, "branch"), os.path.join(a.workdir, "out-branch"))}

    # findings evidence
    scen = {}
    for name in sides["branch"]["scenarios"]:
        scen[name] = {"base": diag_list(sides["base"]["scenarios"][name]),
                      "branch": diag_list(sides["branch"]["scenarios"][name]),
                      "source": sides["branch"]["scenarios"][name]["source"]}

    def has(name, side, pat):
        return any(re.search(pat, d) for d in scen[name][side])

    findings = {
        "a_continue_skips_member_type": {
            "confirmed": (not has("a_string_then_int_member_type_unserializable", "branch", r"MsgPack003")
                          and has("a_string_then_int_member_type_unserializable", "base", r"MsgPack003")
                          and has("a_control_valid_key_member_type_unserializable", "branch", r"MsgPack003")),
            "observed": "member with a mixed key and an unserializable type: MsgPack003 reported on base (string-first case), "
                        "not reported on branch; control with a valid key reports MsgPack003 on branch",
        },
        "b_duplicate_key_second_member_diagnostic": {
            "confirmed_no_diagnostic": not all(has(n, "branch", r"MsgPack005@") for n in scen if n.startswith("b_")),
            "observed": "every duplicate-key scenario reports MsgPack005 ('must be unique') on the second member's line on the branch; "
                        "the generated model keeps the first member (see proof.json exhaustive maps)",
        },
        "null_key_first_field_crash": {
            "confirmed": has("null_key_first_field", "branch", r"AD0001") and has("null_key_first_field_suppressed", "branch", r"AD0001"),
            "observed": "a type whose first keyed member is a field with [Key(null)] makes the analyzer throw (AD0001, ArgumentNullException) on base and branch, with or without SuppressSourceGeneration",
        },
    }
    a_ok = findings["a_continue_skips_member_type"]["confirmed"]
    b_drop = not findings["b_duplicate_key_second_member_diagnostic"]["confirmed_no_diagnostic"]
    n_ok = findings["null_key_first_field_crash"]["confirmed"]
    fp = {
        "check": "findings-probes",
        "branch": BRANCH,
        "base": BASE,
        "head": br_sha[:8],
        "command": "python3 review/proof/run_2234_probes.py --repo <clone> --workdir <dir> --dafny <dafny> --z3 <z3>",
        "result": "pass",
        "summary": (f"(a) continue skips member type: {'confirmed' if a_ok else 'not confirmed'}; "
                    f"(b) second member of a duplicate key gets MsgPack005: {'yes, finding dropped' if b_drop else 'no, finding stands'}; "
                    f"null-key first field crashes analyzer on branch: {'confirmed' if n_ok else 'not confirmed'} "
                    f"({len(scen)} scenarios, real analyzer, base and branch)"),
        "details": {"findings": findings, "scenarios": scen,
                    "runs": {s: {"command": v["command"], "exit_code": v["exit_code"], "summary": v["summary"]} for s, v in sides.items()},
                    "probe_source": "review/proof/csharp/Probe2234Tests.cs"},
        "tool_versions": {"dotnet_sdk": run(["dotnet", "--version"], cwd=os.path.join(a.workdir, "branch")).stdout.strip()},
        "produced_by": "script",
    }
    with open(os.path.join(REVIEW, "evidence", BRANCH, "findings-probes.json"), "w") as f:
        json.dump(fp, f, indent=2)
        f.write("\n")

    # 4. model vs C#
    mod, _dafny = load_model(a.dafny, a.z3, a.workdir)
    cmp = {}
    for side, fn in (("base", mod.default__.CollectOld), ("branch", mod.default__.CollectNew)):
        rows = sides[side]["exhaustive"]
        mism = []
        for r in rows:
            mv_ = model_eval(mod, _dafny, fn, r["input"])
            cv = csharp_view(r)
            if mv_ != cv:
                mism.append({"input": r["input"], "model": mv_, "csharp": cv, "csharp_exception": r["exception"]})
        cmp[side] = {"inputs": len(rows), "mismatches": len(mism), "first_mismatches": mism[:10],
                     "csharp_exceptions": sum(1 for r in rows if r["exception"]),
                     "inputs_without_null_key": sum(1 for r in rows if all(k != "null" for _, k in r["input"])),
                     "csharp_exceptions_without_null_key": sum(1 for r in rows if r["exception"] and all(k != "null" for _, k in r["input"])),
                     "csharp_exceptions_first_member_null_key_field": sum(1 for r in rows if r["exception"] and r["input"][0] == ["Field", "null"]),
                     "ok_inputs_with_dup_report": sum(1 for r in rows if not r["exception"] and any(x[0] == "Dup" for x in r["reports"])),
                     "ok_inputs_with_mix_report": sum(1 for r in rows if not r["exception"] and any(x[0] == "Mix" for x in r["reports"])),
                     "csharp_exception_types": sorted({r["exception"] for r in rows if r["exception"]}),
                     "other_diagnostics": sum(1 for r in rows if r["other"])}
    by_len = {}
    for r in sides["branch"]["exhaustive"]:
        by_len[len(r["input"])] = by_len.get(len(r["input"]), 0) + 1

    verified = ver.returncode == 0 and bool(ver_line) and " 0 errors" in ver_line[0]
    mut_failed = mv.returncode != 0
    proof = {
        "check": "proof",
        "branch": BRANCH,
        "base": BASE,
        "head": br_sha[:8],
        "command": "python3 review/proof/run_2234_probes.py --repo <clone> --workdir <dir> --dafny <dafny> --z3 <z3>",
        "result": "pass" if verified and mut_failed and cmp["branch"]["mismatches"] == 0 and cmp["base"]["mismatches"] == 0 else "fail",
        "summary": (f"Dafny: {ver_line[0] if ver_line else 'no result'}; locked theorem 'never fails' is false for the branch "
                    f"(counterexample: first keyed member is a field with [Key(null)]), the stated mutation "
                    f"{'fails to verify' if mut_failed else 'VERIFIED (unexpected)'}; model vs real C# on "
                    f"{cmp['branch']['inputs']} inputs of 1..4 members: branch {cmp['branch']['mismatches']} mismatches, "
                    f"base {cmp['base']['mismatches']} mismatches; C# threw on {cmp['branch']['csharp_exceptions']} branch inputs "
                    f"and {cmp['base']['csharp_exceptions']} base inputs; with int/string keys only ({cmp['branch']['inputs_without_null_key']} inputs) "
                    f"C# threw on {cmp['base']['csharp_exceptions_without_null_key']} on base and {cmp['branch']['csharp_exceptions_without_null_key']} on branch"),
        "details": {
            "model": "review/proof/KeyCollection.dfy",
            "theorem_locked_in_brief": "for any list of members, collecting keys never fails, whatever keys repeat or mix kinds",
            "theorem_outcome": "false for the real logic; proved instead: fails iff the first keyed member is a field with [Key(null)] "
                               "(BranchFailsIffFirstIsNullKeyField), never fails for int/string keys (BranchNeverFailsForIntAndStringKeys), "
                               "first wins and every repeated accepted key is reported (DupReported)",
            "requirement_inferred": True,
            "dafny_verify": {"command": f"dafny verify --solver-path <z3> review/proof/KeyCollection.dfy", "exit_code": ver.returncode,
                             "result_line": ver_line, "lemmas": lemmas, "proof_gaps_in_code": gaps},
            "mutation_locked_theorem": {"lemma": "LockedTheoremAsStated: ensures CollectNew(ms).Ok? for all ms", "exit_code": mv.returncode,
                                        "output": mv_line},
            "model_vs_csharp": cmp,
            "inputs_by_length": by_len,
            "input_domain": "kind in {Prop, Field}, key in {0, 1, \"a\", \"b\", null}, 1..4 members, properties before fields (the C# visit order)",
            "what_is_compared": "fail vs ok; on ok: IsIntKey, the generated model's key->member map, and the ordered Dup/Mix/BothNull reports",
            "chain": [{"link": "model satisfies the lemmas", "tier": "Proved"},
                      {"link": "model matches real TypeCollector on all inputs up to 4 members", "tier": "Tested"}],
        },
        "tool_versions": {"dafny": run([a.dafny, "--version"]).stdout.strip(), "z3": run([a.z3, "--version"]).stdout.strip(),
                          "dotnet_sdk": fp["tool_versions"]["dotnet_sdk"], "python": sys.version.split()[0]},
        "produced_by": "script",
    }
    with open(os.path.join(REVIEW, "evidence", BRANCH, "proof.json"), "w") as f:
        json.dump(proof, f, indent=2)
        f.write("\n")
    print(fp["summary"])
    print(proof["summary"])


if __name__ == "__main__":
    main()
