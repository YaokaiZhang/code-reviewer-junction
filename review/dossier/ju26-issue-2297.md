### ju26-issue-2297 · #2297 — Add ExcludeFromCodeCoverage attribute to generated code

`32258fdb..a0aa5ab2` · 237 files +1383 −9

**What the AI changed:** The AI made the source generator put `[ExcludeFromCodeCoverage]` on every formatter and resolver it emits, inside `#if !NETSTANDARD2_0 && !NETFRAMEWORK`. It edited the 6 code templates and one helper (TransformUtilities.cs), re-recorded 222 test snapshots, and added a test file and a README note.

| ■ Proved | ▲ Tested | ● Measured | ◆ Argued | ✕ Refused |
|:-:|:-:|:-:|:-:|:-:|
| 2 | 2 | 3 | 2 | 1 |

#### Owner decides · 3

**✕ Refused · C-2297-07** — The generator now puts [ExcludeFromCodeCoverage] on the user-declared partial resolver classes (ResolverTemplate, CompositeResolverTemplate), whose accessibility the user picks and which can be public; a user who already excluded their partial resolver by hand gets compile error CS0579 on the branch.

> It touches public API, so no machine may settle it: the attribute lands in the consumer's public type metadata and breaks the build for an existing, plausible user pattern (shown on the real generator: probe passes on base, fails on branch), which is a public API and compatibility call, not a machine call.

R-2297-1 *(inferred)* · owner: **MessagePack-CSharp maintainer who owns public API and breaking changes**

- [`duplicate-attribute-probe`](../evidence/ju26-issue-2297/duplicate-attribute-probe.json) **FAIL** · hand — A user's own [ExcludeFromCodeCoverage] on their partial resolver compiles on base (1 of 1 probe passed) and breaks on the branch (1 of 1 failed, error CS0579 duplicate attribute)
- [`regeneration`](../evidence/ju26-issue-2297/regeneration.json) **pass** — base: 167 passed, 0 failed of 167; branch: 169 passed, 0 failed of 169
- `src/MessagePack.SourceGenerator/Transforms/ResolverTemplate.tt:14-16`
- `src/MessagePack.SourceGenerator/Transforms/ResolverTemplate.cs:38`
- `src/MessagePack.SourceGenerator/Transforms/CompositeResolverTemplate.tt:7-9`
- `src/MessagePack.SourceGenerator/Transforms/CompositeResolverTemplate.cs:27`

- [ ] accept
- [ ] reject
- [ ] send back

**◆ Argued · C-2297-08** — Agent's claim: the guard `#if !NETSTANDARD2_0 && !NETFRAMEWORK` is needed because the attribute is not available on netstandard2.0 or .NET Framework.

> Only the agent's word backs it, and our check contradicts it: the attribute is in the netstandard2.0 and net472 reference assemblies and an unguarded probe compiles on both, so the guard drops the feature on 2 targets; widening it is a product call.

R-2297-2 *(inferred)* · owner: **MessagePack source generator owner**

- [`attribute-availability`](../evidence/ju26-issue-2297/attribute-availability.json) **pass** · hand — ExcludeFromCodeCoverageAttribute is present in the netstandard2.0 and net472 reference assemblies, and an unguarded probe compiles for netstandard2.0, net472 and net8.0 with 0 errors and 0 warnings, so the agent's `#if !NETSTANDARD2_0 && !NETFRAMEWORK` guard is too strict: it drops the attribute on 2 targets where it exists
- `src/MessagePack.SourceGenerator/Transforms/*Template.tt`
- `src/MessagePack.SourceGenerator/Transforms/*Template.cs`
- `tests/MessagePack.SourceGenerator.Tests/CodeCoverageExclusionTests.cs:18-19`

- [ ] accept
- [ ] reject
- [ ] send back

**◆ Argued · C-2297-09** — README: all generated formatters and resolvers carry [ExcludeFromCodeCoverage], emitted only where available (not netstandard2.0 or .NET Framework).

> Documentation is not machine-checked; its first sentence matches C-2297-04, its second repeats the availability statement that attribute-availability.json contradicts.

R-2297-4 *(inferred)* · owner: **MessagePack documentation owner**

- [`attribute-availability`](../evidence/ju26-issue-2297/attribute-availability.json) **pass** · hand — ExcludeFromCodeCoverageAttribute is present in the netstandard2.0 and net472 reference assemblies, and an unguarded probe compiles for netstandard2.0, net472 and net8.0 with 0 errors and 0 warnings, so the agent's `#if !NETSTANDARD2_0 && !NETFRAMEWORK` guard is too strict: it drops the attribute on 2 targets where it exists
- [`new-tests-on-base`](../evidence/ju26-issue-2297/new-tests-on-base.json) **FAIL** — base-newtests: 167 passed, 2 failed of 169
- `README.md:1639-1641`

- [ ] accept
- [ ] reject
- [ ] send back

#### Machine settled · 7

<details><summary>■ Proved · C-2297-02 — All 222 changed snapshots are exactly what the branch's generator emits, and the emitted code compiles: the snapshot test project passes 169 of 169 on the branch (base: 167 of 167).</summary>

> Regeneration on the real artefact: the snapshot tests run the generator and compare its output text with the committed files, then compile it, and they pass.

R-2297-3 *(inferred)*

- [`regeneration`](../evidence/ju26-issue-2297/regeneration.json) **pass** — base: 167 passed, 0 failed of 167; branch: 169 passed, 0 failed of 169
- `tests/MessagePack.SourceGenerator.Tests/Resources/*`

</details>

<details><summary>■ Proved · C-2297-03 — The 6 committed template .cs files emit the same text as their edited .tt files: dotnet-t4 regeneration matches 6 of 6 on the branch, the same method matches 6 of 6 untouched templates on base, and the negative control differs 6 of 6.</summary>

> A deterministic regeneration of the real templates, compared on the emitted text after layout normalisation and calibrated on base; it is not a byte-for-byte match with Visual Studio's tool.

R-2297-1 *(inferred)*

- [`template-regeneration`](../evidence/ju26-issue-2297/template-regeneration.json) **pass** — dotnet-t4 regeneration of 6 templates, TransformText() compared after normalising layout: base 6 of 6 match, branch 6 of 6 match, 0 t4 errors; negative control: branch regeneration differs from base .cs for 6 of 6
- `src/MessagePack.SourceGenerator/Transforms/*Template.tt`
- `src/MessagePack.SourceGenerator/Transforms/*Template.cs`

</details>

<details><summary>▲ Tested · C-2297-04 — For a sample with an int-keyed object, a string-keyed object, an enum, a union and a resolver, every generated file contains the attribute and every occurrence sits inside the guard.</summary>

> The 2 new CodeCoverageExclusionTests fail on base (2 of 2) and pass on the branch.

R-2297-1 *(inferred)*

- ▲ Tested — new tests fail on base
- ▲ Tested — new tests pass on branch

- [`new-tests-on-base`](../evidence/ju26-issue-2297/new-tests-on-base.json) **FAIL** — base-newtests: 167 passed, 2 failed of 169
- [`regeneration`](../evidence/ju26-issue-2297/regeneration.json) **pass** — base: 167 passed, 0 failed of 167; branch: 169 passed, 0 failed of 169
- `tests/MessagePack.SourceGenerator.Tests/CodeCoverageExclusionTests.cs`
- `src/MessagePack.SourceGenerator/Transforms/*Template.tt`
- `src/MessagePack.SourceGenerator/Transforms/*Template.cs`

</details>

<details><summary>▲ Tested · C-2297-05 — The TransformUtilities.cs edit is required: without it, a formatter nested in a generic type with constraints is emitted as `{#if ...` on one line and the generated code fails to compile (CS1040).</summary>

> Reverting only that line makes GenerationTests.GenericDataTypeWithPrivateMember fail (168 of 169 pass) and restoring it makes it pass; a hand run shows the failure is a CS1040 compile error.

R-2297-2 *(inferred)*

- ▲ Tested — edit reverted: the snapshot test fails (script)
- ▲ Tested — the failure is CS1040 in generated code (hand run)

- [`transformutilities-removal`](../evidence/ju26-issue-2297/transformutilities-removal.json) **FAIL** — no-tu: 168 passed, 1 failed of 169
- [`transformutilities-removal-output`](../evidence/ju26-issue-2297/transformutilities-removal-output.json) **FAIL** · hand — Without the TransformUtilities.cs edit the generator emits `{#if !NETSTANDARD2_0 && !NETFRAMEWORK` on one line for the formatter nested in a constrained generic type, which fails to compile with 1 error CS1040; the Ordinal formatter loses the 1 extra blank line, so that blank line is a side effect of the edit
- [`regeneration`](../evidence/ju26-issue-2297/regeneration.json) **pass** — base: 167 passed, 0 failed of 167; branch: 169 passed, 0 failed of 169
- `src/MessagePack.SourceGenerator/Transforms/TransformUtilities.cs:58`

</details>

<details><summary>● Measured · C-2297-01 — Of the 222 changed snapshot files, 220 change only by added attribute and #if/#endif guard lines; the other 2 are both in Resources/GenericDataTypeWithPrivateMember/ (Named: the brace moves to its own line; Ordinal: one extra blank line).</summary>

> The evidence is a count from the diff classifier script; it describes the diff and does not by itself show the snapshots are right.

R-2297-3 *(inferred)*

- [`diff-classifier`](../evidence/ju26-issue-2297/diff-classifier.json) **pass** — 237 files changed: 222 snapshot, 6 template, 6 generated-output, 1 test, 1 doc, 1 logic; 220 of 222 snapshots change only by attribute and #if/#endif guard lines, 2 do not; 3 snapshot files left unchanged, 1 Resources dir(s) with no test method
- `tests/MessagePack.SourceGenerator.Tests/Resources/*`

</details>

<details><summary>● Measured · C-2297-06 — The TransformUtilities.cs edit has one visible side effect in the snapshots: one extra blank line in the Ordinal formatter of GenericDataTypeWithPrivateMember.</summary>

> Counted by the classifier and confirmed by the removal run; that the blank line is harmless (and that EnumTemplate gets the same blank line, by reading) is not machine-checked.

R-2297-3 *(inferred)*

- [`diff-classifier`](../evidence/ju26-issue-2297/diff-classifier.json) **pass** — 237 files changed: 222 snapshot, 6 template, 6 generated-output, 1 test, 1 doc, 1 logic; 220 of 222 snapshots change only by attribute and #if/#endif guard lines, 2 do not; 3 snapshot files left unchanged, 1 Resources dir(s) with no test method
- [`transformutilities-removal-output`](../evidence/ju26-issue-2297/transformutilities-removal-output.json) **FAIL** · hand — Without the TransformUtilities.cs edit the generator emits `{#if !NETSTANDARD2_0 && !NETFRAMEWORK` on one line for the formatter nested in a constrained generic type, which fails to compile with 1 error CS1040; the Ordinal formatter loses the 1 extra blank line, so that blank line is a side effect of the edit
- `tests/MessagePack.SourceGenerator.Tests/Resources/GenericDataTypeWithPrivateMember/*`
- `src/MessagePack.SourceGenerator/Transforms/TransformUtilities.cs:58`

</details>

<details><summary>● Measured · C-2297-10 — The snapshot check is line-ending sensitive and passes here because .gitattributes checks the 225 snapshot .cs files out with CRLF; with LF snapshots 89 of 169 tests fail.</summary>

> A count from running the tests on a scratch copy with snapshots converted to LF; it qualifies C-2297-02 rather than backing a change.

R-2297-3 *(inferred)*

- [`snapshot-line-endings`](../evidence/ju26-issue-2297/snapshot-line-endings.json) **FAIL** — branch-lf: 80 passed, 89 failed of 169
- [`regeneration`](../evidence/ju26-issue-2297/regeneration.json) **pass** — base: 167 passed, 0 failed of 167; branch: 169 passed, 0 failed of 169
- `tests/MessagePack.SourceGenerator.Tests/Resources/*`

</details>

#### Found · 9

- The diff classifier (script) flagged 2 of 222 snapshots that change beyond attribute and guard lines, both in Resources/GenericDataTypeWithPrivateMember/: Named (the line `{\tinternal sealed class ...` is split so `{` stands alone) and Ordinal (one added blank line).
- The TransformUtilities.cs edit has no stated reason (the commit message has no body). We found it is required: with it reverted, the generated code fails with CS1040; its one visible side effect is the extra blank line in the Ordinal snapshot.
- We found the guard too strict: ExcludeFromCodeCoverageAttribute exists in the netstandard2.0 and net472 reference assemblies, so netstandard2.0 and .NET Framework consumers silently get no exclusion. The README and the test comment state the opposite.
- We found a break for existing users: a hand-written [ExcludeFromCodeCoverage] on the user's partial resolver compiles on base and fails with CS0579 (duplicate attribute) on the branch. No branch test covers it.
- CodeCoverageExclusionTests hard-codes the guard text, so widening the guard also means changing the test.
- By reading the test verifier: no preprocessor symbols are set in the snapshot compilations, so the guarded-out path (netstandard2.0, .NET Framework) is never compiled by the tests.
- The diff classifier (script) flagged 1 Resources directory with no test method (Resources/InterfaceUnion/, 3 files). It already exists on base, is not run by any test, and the branch leaves it without the attribute, so it is now stale.
- Correction to the handoff: the verifier writes actual output to Resources/ only when WRITE_EXPECTED is defined (the method is [Conditional("WRITE_EXPECTED")]); a plain test run only compares.
- When generated content differs, the test framework reports 'Expected source file list to match' rather than the content diff, which hides the real cause (here CS1040).

#### Refused · 1

- **[ExcludeFromCodeCoverage] added to the user-declared partial resolver classes (C-2297-07)** — It changes the consumer's public type metadata and breaks the build (CS0579) for users who already excluded their resolver by hand. That is a public API and compatibility call, so the owner decides.

#### Scope drift · 1

- None found. The TransformUtilities.cs edit looked like drift (it has no stated reason) but the removal test shows the feature does not compile without it.

#### Not checked · 8

- The text of issue #2297: we could not read it here, so R-2297-1..4 are inferred from the branch title and commit.
- macOS: all runs were on Linux (6.18.44, x86_64). Per .gitattributes the snapshots check out as CRLF on every OS, but that was not run on a Mac.
- Compiling real generated output for netstandard2.0, netstandard2.1 or net472 consumers: only a small probe was compiled for those targets.
- Whether coverage tools (coverlet, dotnet-coverage) actually drop the generated types from their reports.
- Unity, Mono and other builds with their own preprocessor symbols; netstandard1.x and .NET Framework before 4.0.
- Union and enum formatters nested in a generic type with constraints: no snapshot covers them; the need for the edit (Union) and the blank line (Enum) are by reading only.
- Byte-for-byte equality with Visual Studio's TextTemplatingFilePreprocessor: dotnet-t4 was compared on emitted text only.
- Test projects other than tests/MessagePack.SourceGenerator.Tests.

---
<sub>Sign: `python3 review/scripts/sign_receipt.py ju26-issue-2297` · read the evidence, not the diff</sub>
