#!/usr/bin/env python3
"""Patch a scratch worktree's tests/MessagePack.SourceGenerator.Tests so every compilation the tests
build is recorded by CorpusDump (see CorpusDump.cs). Only verifier plumbing is touched; test bodies,
expected outputs and production code stay as they are. Usage: patch_verifiers.py <worktree>"""
import os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TP = "tests/MessagePack.SourceGenerator.Tests"


def sub_once(text, old, new, path):
    if text.count(old) != 1:
        raise SystemExit(f"patch anchor not found exactly once in {path}: {old[:60]!r}")
    return text.replace(old, new)


def patch(wt):
    vdir = os.path.join(wt, TP, "Verifiers")
    shutil.copyfile(os.path.join(HERE, "CorpusDump.cs"), os.path.join(vdir, "CorpusDump.cs"))

    p = os.path.join(vdir, "CSharpSourceGeneratorVerifier`1+Test.cs")
    t = open(p, encoding="utf-8-sig").read()
    if "CorpusDump" not in t:
        t = sub_once(t, "private readonly string testMethod;",
                     "private readonly string testMethod;\n        private readonly string corpusName = CorpusDump.FindTestName();", p)
        t = sub_once(t, "var (compilation, diagnostics) = await base.GetProjectCompilationAsync(project, verifier, cancellationToken);",
                     "var (compilation, diagnostics) = await base.GetProjectCompilationAsync(project, verifier, cancellationToken);\n"
                     "            CorpusDump.Dump(project, this.corpusName, \"generator-verifier\");", p)
        open(p, "w", encoding="utf-8").write(t)

    p = os.path.join(vdir, "CSharpCodeFixVerifier`2+Test.cs")
    t = open(p, encoding="utf-8-sig").read()
    if "CorpusDump" not in t:
        t = sub_once(t, "internal class Test : CSharpCodeFixTest<TAnalyzer, TCodeFix, DefaultVerifier>\n    {",
                     "internal class Test : CSharpCodeFixTest<TAnalyzer, TCodeFix, DefaultVerifier>\n    {\n"
                     "        private readonly string corpusName = CorpusDump.FindTestName();\n\n"
                     "        protected override async Task<(Compilation compilation, ImmutableArray<Diagnostic> generatorDiagnostics)> GetProjectCompilationAsync(Project project, IVerifier verifier, CancellationToken cancellationToken)\n"
                     "        {\n"
                     "            var result = await base.GetProjectCompilationAsync(project, verifier, cancellationToken);\n"
                     "            CorpusDump.Dump(project, this.corpusName, \"analyzer-codefix-verifier\");\n"
                     "            return result;\n"
                     "        }\n", p)
        open(p, "w", encoding="utf-8").write(t)


if __name__ == "__main__":
    patch(sys.argv[1])
