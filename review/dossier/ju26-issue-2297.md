### ju26-issue-2297 · #2297 — Add ExcludeFromCodeCoverage attribute to generated code

`32258fdb..a0aa5ab2` · 237 files +1383 −9

**What the AI changed:** The source generator now marks every formatter and resolver it emits with `[ExcludeFromCodeCoverage]`, so coverage tools skip them. The attribute sits inside `#if !NETSTANDARD2_0 && !NETFRAMEWORK`. The AI edited the 6 code templates and one helper, TransformUtilities.cs. It re-recorded 222 test snapshots (saved copies of the expected generator output) and added a test file and a README note.

| ● high | ◐ medium | ○ low | needs owner |
|:-:|:-:|:-:|:-:|
| 4 | 3 | 3 | 1 |

<sub>Confidence 0–100 from the evidence, by a fixed formula. Needs owner: a check shows a promise to users changed.</sub>

#### Needs owner · 1

**◐ 50 · C-2297-07** — The change breaks the build for users who already put [ExcludeFromCodeCoverage] on their resolver by hand: they get compile error CS0579. The generator now adds the attribute to the user's own partial resolver classes (ResolverTemplate, CompositeResolverTemplate). The user picks their visibility, and they can be public.

> It changes public API, so it needs the owner to decide. The attribute ends up in the user's public type and breaks the build for a plausible existing pattern. An experiment on the real generator confirms this: it builds before the change and fails after.

R-2297-1 *(inferred)* · owner: **Andrew Arnott** (generated)

- [`duplicate-attribute-probe`](../evidence/ju26-issue-2297/duplicate-attribute-probe.json) **FAIL** · hand — A user's own [ExcludeFromCodeCoverage] on their partial resolver compiles on base (1 of 1 probe passed) and breaks on the branch (1 of 1 failed, error CS0579 duplicate attribute)
- [`regeneration`](../evidence/ju26-issue-2297/regeneration.json) **pass** — base: 167 passed, 0 failed of 167; branch: 169 passed, 0 failed of 169
- `src/MessagePack.SourceGenerator/Transforms/ResolverTemplate.tt:14-16`
- `src/MessagePack.SourceGenerator/Transforms/ResolverTemplate.cs:38`
- `src/MessagePack.SourceGenerator/Transforms/CompositeResolverTemplate.tt:7-9`
- `src/MessagePack.SourceGenerator/Transforms/CompositeResolverTemplate.cs:27`

- [ ] accept
- [ ] reject
- [ ] send back

#### By confidence · 9

<details><summary>● 95 · C-2297-02 — All 222 changed snapshots are exactly what the new generator emits, and that code compiles. The snapshot tests pass 169 of 169 after the change (167 of 167 before).</summary>

> The snapshot tests run the real generator, compare its output with the committed files, then compile it. They pass.

R-2297-3 *(inferred)*

- [`regeneration`](../evidence/ju26-issue-2297/regeneration.json) **pass** — base: 167 passed, 0 failed of 167; branch: 169 passed, 0 failed of 169
- `tests/MessagePack.SourceGenerator.Tests/Resources/*`

</details>

<details><summary>● 95 · C-2297-03 — The 6 committed template .cs files emit the same text as their edited .tt sources. Regenerating with dotnet-t4 matches 6 of 6 after the change. The same method matches 6 of 6 unchanged templates before the change. As a control, the new output differs from the old .cs files in 6 of 6, so the comparison does catch changes.</summary>

> We regenerated the real templates and compared the text they emit, ignoring layout, after checking the method on the old code. It is not a byte-for-byte match with Visual Studio's tool.

R-2297-1 *(inferred)*

- [`template-regeneration`](../evidence/ju26-issue-2297/template-regeneration.json) **pass** — dotnet-t4 regeneration of 6 templates, TransformText() compared after normalising layout: base 6 of 6 match, branch 6 of 6 match, 0 t4 errors; negative control: branch regeneration differs from base .cs for 6 of 6
- `src/MessagePack.SourceGenerator/Transforms/*Template.tt`
- `src/MessagePack.SourceGenerator/Transforms/*Template.cs`

</details>

<details><summary>● 80 · C-2297-04 — Every generated file has the attribute, and every copy sits inside the #if guard. This holds for a sample with an integer-keyed object, a string-keyed object, an enum, a union and a resolver.</summary>

> The 2 new CodeCoverageExclusionTests fail before the change (2 of 2) and pass after.

R-2297-1 *(inferred)*

- The new tests fail before the change.
- The new tests pass after the change.

- [`new-tests-on-base`](../evidence/ju26-issue-2297/new-tests-on-base.json) **FAIL** — base-newtests: 167 passed, 2 failed of 169
- [`regeneration`](../evidence/ju26-issue-2297/regeneration.json) **pass** — base: 167 passed, 0 failed of 167; branch: 169 passed, 0 failed of 169
- `tests/MessagePack.SourceGenerator.Tests/CodeCoverageExclusionTests.cs`
- `src/MessagePack.SourceGenerator/Transforms/*Template.tt`
- `src/MessagePack.SourceGenerator/Transforms/*Template.cs`

</details>

<details><summary>● 80 · C-2297-05 — The TransformUtilities.cs edit is needed. Without it, a formatter inside a generic type with constraints comes out as `{#if ...` on one line, and the generated code fails to compile (CS1040).</summary>

> Undoing only that line makes GenerationTests.GenericDataTypeWithPrivateMember fail (168 of 169 pass); restoring it makes it pass. A manual run shows the failure is compile error CS1040.

R-2297-2 *(inferred)*

- With the edit undone, the snapshot test fails (scripted run).
- The failure is error CS1040 in the generated code (manual run).

- [`transformutilities-removal`](../evidence/ju26-issue-2297/transformutilities-removal.json) **FAIL** — no-tu: 168 passed, 1 failed of 169
- [`transformutilities-removal-output`](../evidence/ju26-issue-2297/transformutilities-removal-output.json) **FAIL** · hand — Without the TransformUtilities.cs edit the generator emits `{#if !NETSTANDARD2_0 && !NETFRAMEWORK` on one line for the formatter nested in a constrained generic type, which fails to compile with 1 error CS1040; the Ordinal formatter loses the 1 extra blank line, so that blank line is a side effect of the edit
- [`regeneration`](../evidence/ju26-issue-2297/regeneration.json) **pass** — base: 167 passed, 0 failed of 167; branch: 169 passed, 0 failed of 169
- `src/MessagePack.SourceGenerator/Transforms/TransformUtilities.cs:58`

</details>

<details><summary>◐ 65 · C-2297-10 — The snapshot check is sensitive to line endings. It passes here because .gitattributes checks out the 225 snapshot .cs files with Windows line endings (CRLF). With Unix line endings (LF), 89 of 169 tests fail.</summary>

> A count from running the tests on a copy with the snapshots converted to LF. It adds a condition to C-2297-02; it does not back a change.

R-2297-3 *(inferred)*

- [`snapshot-line-endings`](../evidence/ju26-issue-2297/snapshot-line-endings.json) **FAIL** — branch-lf: 80 passed, 89 failed of 169
- [`regeneration`](../evidence/ju26-issue-2297/regeneration.json) **pass** — base: 167 passed, 0 failed of 167; branch: 169 passed, 0 failed of 169
- `tests/MessagePack.SourceGenerator.Tests/Resources/*`

</details>

<details><summary>◐ 50 · C-2297-06 — The TransformUtilities.cs edit has one visible side effect in the snapshots: an extra blank line in the Ordinal formatter of GenericDataTypeWithPrivateMember.</summary>

> The diff-sorting script counted it, and the run with the edit removed confirmed it. Two things are not machine-checked: that the blank line is harmless, and that EnumTemplate gets the same blank line, which we found by reading the code.

R-2297-3 *(inferred)*

- [`diff-classifier`](../evidence/ju26-issue-2297/diff-classifier.json) **pass** — 237 files changed: 222 snapshot, 6 template, 6 generated-output, 1 test, 1 doc, 1 logic; 220 of 222 snapshots change only by attribute and #if/#endif guard lines, 2 do not; 3 snapshot files left unchanged, 1 Resources dir(s) with no test method
- [`transformutilities-removal-output`](../evidence/ju26-issue-2297/transformutilities-removal-output.json) **FAIL** · hand — Without the TransformUtilities.cs edit the generator emits `{#if !NETSTANDARD2_0 && !NETFRAMEWORK` on one line for the formatter nested in a constrained generic type, which fails to compile with 1 error CS1040; the Ordinal formatter loses the 1 extra blank line, so that blank line is a side effect of the edit
- `tests/MessagePack.SourceGenerator.Tests/Resources/GenericDataTypeWithPrivateMember/*`
- `src/MessagePack.SourceGenerator/Transforms/TransformUtilities.cs:58`

</details>

<details><summary>○ 45 · C-2297-01 — 220 of the 222 changed snapshot files only gain the attribute and its #if/#endif lines. The other 2 are both in Resources/GenericDataTypeWithPrivateMember/: in Named a brace moves to its own line, and in Ordinal there is one extra blank line.</summary>

> This is a count from a script that sorts the diff. It describes the change; it does not by itself show the snapshots are correct.

R-2297-3 *(inferred)*

- [`diff-classifier`](../evidence/ju26-issue-2297/diff-classifier.json) **pass** — 237 files changed: 222 snapshot, 6 template, 6 generated-output, 1 test, 1 doc, 1 logic; 220 of 222 snapshots change only by attribute and #if/#endif guard lines, 2 do not; 3 snapshot files left unchanged, 1 Resources dir(s) with no test method
- `tests/MessagePack.SourceGenerator.Tests/Resources/*`

</details>

<details><summary>○ 15 · C-2297-08 — The AI says the guard `#if !NETSTANDARD2_0 && !NETFRAMEWORK` is needed because the attribute is not available on netstandard2.0 or .NET Framework.</summary>

> Only the AI's word backs this, and our check contradicts it. The attribute is in the netstandard2.0 and net472 reference assemblies, and code without the guard compiles on both. So the guard turns the feature off on 2 targets. Whether to turn it on there needs the owner to decide.

R-2297-2 *(inferred)*

- [`attribute-availability`](../evidence/ju26-issue-2297/attribute-availability.json) **pass** · hand — ExcludeFromCodeCoverageAttribute is present in the netstandard2.0 and net472 reference assemblies, and an unguarded probe compiles for netstandard2.0, net472 and net8.0 with 0 errors and 0 warnings, so the agent's `#if !NETSTANDARD2_0 && !NETFRAMEWORK` guard is too strict: it drops the attribute on 2 targets where it exists
- `src/MessagePack.SourceGenerator/Transforms/*Template.tt`
- `src/MessagePack.SourceGenerator/Transforms/*Template.cs`
- `tests/MessagePack.SourceGenerator.Tests/CodeCoverageExclusionTests.cs:18-19`

</details>

<details><summary>○ 15 · C-2297-09 — The README says all generated formatters and resolvers carry [ExcludeFromCodeCoverage], but only where it is available: not on netstandard2.0 or .NET Framework.</summary>

> Documentation is not machine-checked. Its first sentence matches C-2297-04. Its second repeats the claim that the attribute is unavailable, which our check contradicts (C-2297-08).

R-2297-4 *(inferred)*

- [`attribute-availability`](../evidence/ju26-issue-2297/attribute-availability.json) **pass** · hand — ExcludeFromCodeCoverageAttribute is present in the netstandard2.0 and net472 reference assemblies, and an unguarded probe compiles for netstandard2.0, net472 and net8.0 with 0 errors and 0 warnings, so the agent's `#if !NETSTANDARD2_0 && !NETFRAMEWORK` guard is too strict: it drops the attribute on 2 targets where it exists
- [`new-tests-on-base`](../evidence/ju26-issue-2297/new-tests-on-base.json) **FAIL** — base-newtests: 167 passed, 2 failed of 169
- `README.md:1639-1641`

</details>

#### Found · 9

- 2 of the 222 snapshots change by more than the attribute and guard lines; the diff-sorting script flagged both. They are in Resources/GenericDataTypeWithPrivateMember/: in Named, the line `{\tinternal sealed class ...` is split so `{` stands alone; in Ordinal, one blank line is added.
- The TransformUtilities.cs edit is needed, though the commit gives no reason for it. With it undone, the generated code fails to compile (CS1040). Its one visible side effect is the extra blank line in the Ordinal snapshot.
- The guard is too strict. ExcludeFromCodeCoverageAttribute exists in the netstandard2.0 and net472 reference assemblies, so netstandard2.0 and .NET Framework users silently get no exclusion. The README and the test comment say the opposite.
- The change breaks existing users. A hand-written [ExcludeFromCodeCoverage] on the user's partial resolver compiles before the change and fails after with CS0579 (duplicate attribute). No test on the branch covers this.
- CodeCoverageExclusionTests hard-codes the guard text, so widening the guard also means changing the test.
- The tests never compile the guarded-out path for netstandard2.0 or .NET Framework. Reading the test verifier shows no preprocessor symbols are set in the snapshot compilations.
- Resources/InterfaceUnion/ (3 files) is now stale. It already existed, no test uses it, and the change leaves it without the attribute. The diff-sorting script flagged it as a Resources folder with no test method.
- Correction to our task notes: the verifier writes actual output to Resources/ only when WRITE_EXPECTED is defined (the method is [Conditional("WRITE_EXPECTED")]). A plain test run only compares.
- When generated content differs, the test framework reports 'Expected source file list to match' instead of the content difference. That hides the real cause, here CS1040.

#### Needs owner: why · 1

- **[ExcludeFromCodeCoverage] added to the user's own partial resolver classes (C-2297-07).** — It changes the user's public type and breaks the build (CS0579) for users who already excluded their resolver by hand. That is a public API and compatibility question, so it needs the owner to decide.

#### Scope drift · 1

- None found. The TransformUtilities.cs edit looked like drift because it has no stated reason, but the generated code does not compile without it.

#### Not checked · 8

- The text of issue #2297: we could not read it here, so requirements R-2297-1..4 are worked out from the branch title and commit.
- macOS: all runs were on Linux (6.18.44, x86_64). .gitattributes should check the snapshots out with CRLF on every OS, but we did not try a Mac.
- Compiling real generated output for netstandard2.0, netstandard2.1 or net472 projects. Only a small probe was compiled for those targets.
- Whether coverage tools such as coverlet and dotnet-coverage actually leave the generated types out of their reports.
- Unity, Mono and other builds with their own preprocessor symbols; netstandard1.x; and .NET Framework before 4.0.
- Union and enum formatters inside a generic type with constraints. No snapshot covers them; that Union needs the edit and Enum gets the blank line comes from reading the code only.
- Byte-for-byte equality with Visual Studio's TextTemplatingFilePreprocessor. We compared dotnet-t4 output on emitted text only.
- Test projects other than tests/MessagePack.SourceGenerator.Tests.

---
<sub>Sign: `python3 review/scripts/sign_receipt.py ju26-issue-2297` · read the evidence, not the diff</sub>
