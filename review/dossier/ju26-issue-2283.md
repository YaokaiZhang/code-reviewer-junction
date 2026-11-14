### ju26-issue-2283 · #2283 — Generator and analyzer crash on a closed generic struct from a referenced assembly

`32258fdb..9df83c38` · 4 files +225 −3

**What the AI changed:** The generator and analyzer crashed when a project used a generic struct, such as Box&lt;int&gt;, defined in another assembly. They looked up source locations that such a type does not have. The AI made those lookups safe. It also added a filter in TypeCollector.cs that drops every analyzer diagnostic located outside the project's own source. It added 3 tests, and notes in the README and the MsgPack004 page saying the defining assembly reports such diagnostics.

| ● high | ◐ medium | ○ low | needs owner |
|:-:|:-:|:-:|:-:|
| 1 | 2 | 1 | 2 |

<sub>Confidence 0–100 from the evidence, by a fixed formula. Needs owner: a check shows a promise to users changed.</sub>

#### Needs owner · 2

**◐ 50 · C-2283-02** — A new filter drops every analyzer diagnostic located outside this project's source. We showed it hides MsgPack003, an error about the app's own type that lacks [MessagePackObject].

> Silencing diagnostics is a product decision, so it needs the analyzer owner to decide; a test cannot settle it.

R-2283-3 *(inferred)* · owner: **Andrew Arnott** (diagnostics)

- A probe test uses the app's own class Plain as Lib.Box&lt;Plain&gt;. Before the change this reports MsgPack003 'Type must be marked with MessagePackObjectAttribute: Box.Content' (an error, no crash). After the change it is gone, and nothing else reports it.
- 28 of the 29 active places in TypeCollector.cs that report a diagnostic go through the filter. This is a script count; whether each one can point outside the project is a text-based guess.
- The new test ClosedGenericStruct_FromMetadataReference_UnkeyedMember needs the filter: without it, the test fails on 2 MsgPack004 diagnostics. So the test locks in the dropped diagnostics.
- Open question for the owner: should diagnostics about types from other assemblies be dropped, reported on the app's member instead, or kept?

- [`dropped-warning`](../evidence/ju26-issue-2283/dropped-warning.json) **FAIL** · hand — MsgPack003 (unattributed_consumer_type_inside_metadata_generic) is reported on base without any analyzer crash and is absent on branch; 3 of 6 probe cases lose a diagnostic on branch
- [`report-sites`](../evidence/ju26-issue-2283/report-sites.json) **pass** — 29 live report sites in TypeCollector.cs: 28 go through the filter (19 distinct descriptors), 1 bypass it; 28 of the 28 filtered sites can have a location outside the compilation's source; simple grep for 'reportDiagnostic?.Invoke' counts 29 lines (2 of them commented out)
- [`old-vs-new-tests`](../evidence/ju26-issue-2283/old-vs-new-tests.json) **pass** · hand — 3 of 3 new tests fail on base and pass on branch; 1 of them (ClosedGenericStruct_FromMetadataReference_UnkeyedMember) also fails when only the filter is removed; whole test project: 167 of 167 pre-existing tests pass on base and 167 on branch
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:239`
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1436-1451`
- `tests/MessagePack.SourceGenerator.Tests/GenericsFormatterTests.cs:582-627`

- [ ] accept
- [ ] reject
- [ ] send back

**◐ 50 · C-2283-03** — The README and the MsgPack004 page now say the defining assembly reports diagnostics about types from referenced assemblies. For the MsgPack003 case above that is not true: no assembly reports it.

> The text presents the dropped diagnostics as intended behaviour, so it stands or falls with C-2283-02 and needs the owner to decide.

R-2283-3 *(inferred)* · owner: **Andrew Arnott** (diagnostics)

- [`dropped-warning`](../evidence/ju26-issue-2283/dropped-warning.json) **FAIL** · hand — MsgPack003 (unattributed_consumer_type_inside_metadata_generic) is reported on base without any analyzer crash and is absent on branch; 3 of 6 probe cases lose a diagnostic on branch
- `README.md:1639-1643`
- `doc/analyzers/MsgPack004.md:48-52`

- [ ] accept
- [ ] reject
- [ ] send back

#### By confidence · 2

<details><summary>● 85 · C-2283-01 — The crash is fixed: a closed generic struct or record struct from a referenced assembly no longer crashes the generator or analyzer, and the resolver is generated again.</summary>

> 2 new tests fail before the change with the issue's crash (AD0001 and CS8785, an IndexOutOfRangeException) and pass after. They still pass with the new filter removed, so the crash fix alone makes them pass.

R-2283-1

- ClosedGenericStruct_FromMetadataReference and ClosedGenericRecordStruct_FromMetadataReference crash before the change with AD0001 and CS8785 (an IndexOutOfRangeException).
- After the change both pass, and both check that the resolver file is generated (requirement R-2283-2).
- Both still pass with the filter line undone, so the crash fix alone makes them pass.

- [`old-vs-new-tests`](../evidence/ju26-issue-2283/old-vs-new-tests.json) **pass** · hand — 3 of 3 new tests fail on base and pass on branch; 1 of them (ClosedGenericStruct_FromMetadataReference_UnkeyedMember) also fails when only the filter is removed; whole test project: 167 of 167 pre-existing tests pass on base and 167 on branch
- [`old-vs-new-tests.script`](../evidence/ju26-issue-2283/old-vs-new-tests.script.json) **pass** — 3 new or changed test methods (3 added, 0 modified): 3 fail on base and pass on branch, 0 pass on base (not evidence), 0 fail on branch, 0 not runnable here (project does not build on branch)
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:985`
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1077`
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1429-1435`
- `tests/MessagePack.SourceGenerator.Tests/GenericsFormatterTests.cs:4-6`
- `tests/MessagePack.SourceGenerator.Tests/GenericsFormatterTests.cs:499-581`
- `tests/MessagePack.SourceGenerator.Tests/GenericsFormatterTests.cs:628-685`

</details>

<details><summary>○ 30 · C-2283-04 — No existing test in the source generator test project changes result: 167 of 167 pass before and after the change.</summary>

> This is a count from a test run. Passing both times shows nothing that is tested got worse; it does not prove the change is correct.

R-2283-1

- [`old-vs-new-tests`](../evidence/ju26-issue-2283/old-vs-new-tests.json) **pass** · hand — 3 of 3 new tests fail on base and pass on branch; 1 of them (ClosedGenericStruct_FromMetadataReference_UnkeyedMember) also fails when only the filter is removed; whole test project: 167 of 167 pre-existing tests pass on base and 167 on branch
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:239`
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:985`
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1077`

</details>

#### Found · 6

- The filter hides MsgPack003 when the app's own type lacks [MessagePackObject] and is wrapped in a generic from a referenced assembly. We found this with a hand-written probe test. No automatic rule can notice that a filter hides warnings; the rules only scored it once the test showed it.
- The change does two things, but the issue asked only for the first: a crash fix (2 lines plus a helper), and a filter on 28 of the 29 active places that report a diagnostic.
- One of the 3 new tests, ClosedGenericStruct_FromMetadataReference_UnkeyedMember, tests the filter, not the crash fix: it fails when only the filter is removed.
- The filter also prevents a second crash. With a project reference instead of a compiled one, the old code crashes with AD0001: 'Reported diagnostic MsgPack003 has a source location in file Lib.cs, which is not part of the compilation'. After the change, that diagnostic is dropped instead.
- A duplicate [Key(0)] in a generic type from a referenced assembly still crashes the analyzer (ArgumentException: same key added), before and after the change. Its MsgPack005 is now dropped. This is outside the issue's scope.
- We count 29 active places that report a diagnostic: 28 go through the filter and 1 bypasses it. Our task notes also said 29, but from a simple grep that includes 2 commented-out lines and misses 2 real calls. Same number, different places.

#### Needs owner: why · 2

- **Accept ReportIfLocatedInCompilation, the filter that drops analyzer diagnostics located in a referenced assembly, in another project, or nowhere.** — Dropping warnings is a product decision, so it needs the analyzer owner to decide: drop them, report them on the app's member instead, or keep them. The MsgPack003 case shows at least one is a real problem in the app's own code.
- **Accept the README and MsgPack004.md text saying the defining assembly reports these diagnostics.** — It presents the filter as intended behaviour, and for MsgPack003 on the app's own type it is not true. It follows the owner's decision on the filter.

#### Scope drift · 2

- The issue asks for no crash and a generated resolver. Nobody asked for the filter or for docs on where diagnostics are reported, and no maintainer says anything in the issue about diagnostics for referenced types.
- The filter wraps 28 places that report diagnostics, not only the 2 that crashed.

#### Not checked · 6

- The issue's exact setup: a ProjectReference in a real MSBuild or IDE build. The new tests reference the library as a compiled file. Our probe covers a project reference only for two other cases.
- What the generated resolver contains. The new tests skip that check (SkipGeneratedSourcesCheck) and only check that the resolver file exists.
- What happens at run time after MsgPack003 is dropped, for example whether serializing Box&lt;Plain&gt; fails.
- Only MsgPack003, MsgPack004 and MsgPack005 were tried through the filter. For the other filtered places, whether they can point outside the project is a text-based guess by a script.
- Other combinations from the issue (class or struct, generic or not) beyond the 3 new tests and 6 probe cases.
- Running the generator path. The generator passes no report callback, so the filter does not apply there; we read this in the code but did not run it.

---
<sub>Sign: `python3 review/scripts/sign_receipt.py ju26-issue-2283` · read the evidence, not the diff</sub>
