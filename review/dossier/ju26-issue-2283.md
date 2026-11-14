### ju26-issue-2283 · #2283 — Generator and analyzer crash on a closed generic struct from a referenced assembly

`32258fdb..9df83c38` · 4 files +225 −3

**What the AI changed:** The generator and analyzer crashed when a project used a generic struct, such as Box&lt;int&gt;, defined in another assembly. They looked up source locations that such a type does not have. The AI made those lookups safe. It also added a filter in TypeCollector.cs that drops every analyzer diagnostic located outside the project's own source. It added 3 tests, and notes in the README and the MsgPack004 page saying the defining assembly reports such diagnostics.

| ■ Proved | ▲ Tested | ● Measured | ◆ Argued | ✕ Refused |
|:-:|:-:|:-:|:-:|:-:|
| · | 1 | 1 | · | 2 |

#### Owner decides · 2

**✕ Refused · C-2283-02** — A new filter drops every analyzer diagnostic located outside this project's source. We showed it hides MsgPack003, an error about the app's own type that lacks [MessagePackObject].

> Silencing diagnostics is a product decision for the analyzer owner; a test cannot settle it.

R-2283-3 *(inferred)* · owner: **analyser owner**

- ▲ Tested — A probe test uses the app's own class Plain as Lib.Box&lt;Plain&gt;. Before the change this reports MsgPack003 'Type must be marked with MessagePackObjectAttribute: Box.Content' (an error, no crash). After the change it is gone, and nothing else reports it.
- ● Measured — 28 of the 29 active places in TypeCollector.cs that report a diagnostic go through the filter. This is a script count; whether each one can point outside the project is a text-based guess.
- ▲ Tested — The new test ClosedGenericStruct_FromMetadataReference_UnkeyedMember needs the filter: without it, the test fails on 2 MsgPack004 diagnostics. So the test locks in the dropped diagnostics.
- ✕ Refused — Open question for the owner: should diagnostics about types from other assemblies be dropped, reported on the app's member instead, or kept?

- [`dropped-warning`](../evidence/ju26-issue-2283/dropped-warning.json) **FAIL** · hand — MsgPack003 (unattributed_consumer_type_inside_metadata_generic) is reported on base without any analyzer crash and is absent on branch; 3 of 6 probe cases lose a diagnostic on branch
- [`report-sites`](../evidence/ju26-issue-2283/report-sites.json) **pass** — 29 live report sites in TypeCollector.cs: 28 go through the filter (19 distinct descriptors), 1 bypass it; 28 of the 28 filtered sites can have a location outside the compilation's source; simple grep for 'reportDiagnostic?.Invoke' counts 29 lines (2 of them commented out)
- [`old-vs-new-tests`](../evidence/ju26-issue-2283/old-vs-new-tests.json) **pass** · hand — 3 of 3 new tests fail on base and pass on branch; 1 of them (ClosedGenericStruct_FromMetadataReference_UnkeyedMember) also fails when only the filter is removed; whole test project: 167 of 167 pre-existing tests pass on base and 167 on branch
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:239`
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1436-1451`
- `tests/MessagePack.SourceGenerator.Tests/GenericsFormatterTests.cs:582-627`

- [ ] accept
- [ ] reject
- [ ] send back

**✕ Refused · C-2283-03** — The README and the MsgPack004 page now say the defining assembly reports diagnostics about types from referenced assemblies. For the MsgPack003 case above that is not true: no assembly reports it.

> The text presents the dropped diagnostics as intended behaviour, so it stands or falls with C-2283-02.

R-2283-3 *(inferred)* · owner: **analyser owner**

- [`dropped-warning`](../evidence/ju26-issue-2283/dropped-warning.json) **FAIL** · hand — MsgPack003 (unattributed_consumer_type_inside_metadata_generic) is reported on base without any analyzer crash and is absent on branch; 3 of 6 probe cases lose a diagnostic on branch
- `README.md:1639-1643`
- `doc/analyzers/MsgPack004.md:48-52`

- [ ] accept
- [ ] reject
- [ ] send back

#### Machine settled · 2

<details><summary>▲ Tested · C-2283-01 — The crash is fixed: a closed generic struct or record struct from a referenced assembly no longer crashes the generator or analyzer, and the resolver is generated again.</summary>

> 2 new tests fail before the change with the issue's crash (AD0001 and CS8785, an IndexOutOfRangeException) and pass after. They still pass with the new filter removed, so the crash fix alone makes them pass.

R-2283-1

- ▲ Tested — ClosedGenericStruct_FromMetadataReference and ClosedGenericRecordStruct_FromMetadataReference crash before the change with AD0001 and CS8785 (an IndexOutOfRangeException).
- ▲ Tested — After the change both pass, and both check that the resolver file is generated (requirement R-2283-2).
- ▲ Tested — Both still pass with the filter line undone, so the crash fix alone makes them pass.

- [`old-vs-new-tests`](../evidence/ju26-issue-2283/old-vs-new-tests.json) **pass** · hand — 3 of 3 new tests fail on base and pass on branch; 1 of them (ClosedGenericStruct_FromMetadataReference_UnkeyedMember) also fails when only the filter is removed; whole test project: 167 of 167 pre-existing tests pass on base and 167 on branch
- [`old-vs-new-tests.script`](../evidence/ju26-issue-2283/old-vs-new-tests.script.json) **pass** — 3 new or changed test methods (3 added, 0 modified): 3 fail on base and pass on branch, 0 pass on base (not evidence), 0 fail on branch, 0 not runnable here (project does not build on branch)
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:985`
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1077`
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1429-1435`
- `tests/MessagePack.SourceGenerator.Tests/GenericsFormatterTests.cs:4-6`
- `tests/MessagePack.SourceGenerator.Tests/GenericsFormatterTests.cs:499-581`
- `tests/MessagePack.SourceGenerator.Tests/GenericsFormatterTests.cs:628-685`

</details>

<details><summary>● Measured · C-2283-04 — No existing test in the source generator test project changes result: 167 of 167 pass before and after the change.</summary>

> This is a count from a test run. Passing both times shows nothing that is tested got worse; it does not prove the change is correct.

R-2283-1

- [`old-vs-new-tests`](../evidence/ju26-issue-2283/old-vs-new-tests.json) **pass** · hand — 3 of 3 new tests fail on base and pass on branch; 1 of them (ClosedGenericStruct_FromMetadataReference_UnkeyedMember) also fails when only the filter is removed; whole test project: 167 of 167 pre-existing tests pass on base and 167 on branch
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:239`
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:985`
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1077`

</details>

#### Found · 6

- We found (with a hand-written probe test, not a rule) that the filter hides MsgPack003 for the consumer's own unattributed type when it is wrapped in a generic from a referenced assembly. A rule cannot notice that a filter hides warnings; the rule only set the tier once the test showed it.
- The change does two things, not one: a crash fix (2 lines plus a helper) and a filter on 28 of 29 live report sites. The issue asked only for the first.
- One of the 3 new tests (ClosedGenericStruct_FromMetadataReference_UnkeyedMember) is a test of the filter, not of the crash fix: it fails when only the filter is removed.
- The filter also prevents a second base crash: with a project (compilation) reference, base throws 'Reported diagnostic MsgPack003 has a source location in file Lib.cs, which is not part of the compilation' (AD0001). On the branch that diagnostic is dropped instead.
- A duplicate [Key(0)] in a generic type from a referenced assembly still crashes the analyzer on the branch (ArgumentException: same key added), as on base; its MsgPack005 is now dropped. Outside this issue's scope.
- Report-site count: 29 live sites by our method (28 through the filter, 1 bypass); the handoff's 29 was a simple grep that includes 2 commented-out lines and misses 2 live calls. Same number, different sites.

#### Refused · 2

- **Accept ReportIfLocatedInCompilation, which drops analyzer diagnostics located in metadata, in another project, or with no location.** — Dropping warnings is a product call. The analyser owner decides whether these are dropped, reported at the consumer's member instead, or kept; the MsgPack003 case shows at least one is a real problem in the consumer's own code.
- **Accept the README and MsgPack004.md text saying the defining assembly reports these diagnostics.** — It describes the filter as intended behaviour, and for MsgPack003 on a consumer type it is not true; it follows the decision on the filter.

#### Scope drift · 2

- Issue 2283 asks for no crash and a generated resolver. The filter, and the docs on where diagnostics are reported, were not asked for; the issue has no maintainer statement on diagnostics for referenced types.
- The filter wraps all 28 filtered report sites, not only the 2 sites that crashed.

#### Not checked · 6

- The issue's exact setup (ProjectReference in a real MSBuild or IDE build). The new tests reference the library as a compiled image; our probe covers a compilation reference only for two other shapes.
- The content of the generated resolver: the new tests use SkipGeneratedSourcesCheck and only check that the resolver file exists.
- Runtime behaviour after a dropped MsgPack003 (does serialising Box&lt;Plain&gt; fail at run time).
- Only MsgPack003, MsgPack004 and MsgPack005 were exercised through the filter; 'can be outside the compilation' for the other filtered sites is a text heuristic in report_sites.py.
- The issue's trigger matrix (class vs struct, generic vs not) beyond the 3 new tests and 6 probe cases.
- The generator path: the generator passes no report callback, so the filter does not apply there (read, not run).

---
<sub>Sign: `python3 review/scripts/sign_receipt.py ju26-issue-2283` · read the evidence, not the diff</sub>
