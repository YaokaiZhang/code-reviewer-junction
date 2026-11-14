### ju26-issue-2283 · #2283 — Source generator crashes when a member is declared in metadata

> **SAMPLE DOSSIER** — not a real review.

`32258fdb..9df83c38` · 4 files +225 −3

| ■ Proved | ▲ Tested | ● Measured | ◆ Argued | ✕ Refused |
|:-:|:-:|:-:|:-:|:-:|
| 1 | 1 | 1 | 1 | 1 |

#### Owner decides · 2

**✕ Refused · C-2283-03** — A new filter, ReportIfLocatedInCompilation, drops every diagnostic whose location is not in the compilation's own source.

> It silences diagnostics, including ones that point at metadata members a user can still fix by changing their own attributes.

R-2283-1 *(inferred)* · owner: **analyser owner**

- ● Measured — Report sites that go through the filter (report-sites)
- ▲ Tested — A probe diagnostic is lost on branch (dropped-warning)
- ◆ Argued — No lost diagnostic is one a user needs

- [`dropped-warning`](../evidence/ju26-issue-2283/dropped-warning.json) **FAIL** · hand — MsgPack003 (unattributed_consumer_type_inside_metadata_generic) is reported on base without any analyzer crash and is absent on branch; 3 of 6 probe cases lose a diagnostic on branch
- [`report-sites`](../evidence/ju26-issue-2283/report-sites.json) **pass** — 29 live report sites in TypeCollector.cs: 28 go through the filter (19 distinct descriptors), 1 bypass it; 28 of the 28 filtered sites can have a location outside the compilation's source; simple grep for 'reportDiagnostic?.Invoke' counts 29 lines (2 of them commented out)
- `src/MessagePack.SourceGenerator/Analyzers/AnalyzerUtilities.cs:88-131`
- `src/MessagePack.SourceGenerator/Analyzers/MsgPack00xAnalyzer.cs:57-61`

- [ ] accept
- [ ] reject
- [ ] send back

**◆ Argued · C-2283-04** — Skipping metadata members in the collector is safe because their formatters come from the referenced assembly.

> No test covers a referenced assembly that ships without its own formatter.

R-2283-1 · owner: **generator maintainer**

- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:241-252`

- [ ] accept
- [ ] reject
- [ ] send back

#### Machine settled · 3

<details><summary>■ Proved · C-2283-02 — Generated formatters for every existing snapshot type are byte-identical before and after the change.</summary>

> Regenerated all snapshot outputs on base and head; the byte diff is empty.

R-2283-2 *(inferred)*

- [`snapshot-byte-diff`](../evidence/ju26-issue-2283/snapshot-byte-diff.json) — missing
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:236-240`

</details>

<details><summary>▲ Tested · C-2283-01 — The generator no longer throws when a [MessagePackObject] type inherits a member declared in a referenced assembly.</summary>

> The new regression test fails on base with InvalidOperationException and passes on the branch.

R-2283-1

- ▲ Tested — Test reproduces the crash on base
- ▲ Tested — Same test passes on branch head

- [`old-vs-new-tests`](../evidence/ju26-issue-2283/old-vs-new-tests.json) **pass** · hand — 3 of 3 new tests fail on base and pass on branch; 1 of them (ClosedGenericStruct_FromMetadataReference_UnkeyedMember) also fails when only the filter is removed; whole test project: 167 of 167 pre-existing tests pass on base and 167 on branch
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:236-240`
- `tests/MessagePack.SourceGenerator.Tests/MetadataMemberTests.cs:1-64`

</details>

<details><summary>● Measured · C-2283-05 — Generator run time on the benchmark solution is within noise of base.</summary>

> The number comes from a timing harness, not a pass/fail check.

R-2283-2 *(inferred)*

- [`generator-timing`](../evidence/ju26-issue-2283/generator-timing.json) — missing

</details>

#### Found · 2

- ReportIfLocatedInCompilation also suppresses MsgPack003 for user types whose base class lives in a package.
- The regression test pins one shape (inherited property); fields and explicit interface members are not exercised.

#### Refused · 1

- **ReportIfLocatedInCompilation filter** — Drops warnings; tier rule 1.

#### Scope drift · 1

- Analyser diagnostic filtering was not asked for by issue 2283.

#### Not checked · 2

- Behaviour with Unity / IL2CPP builds.
- Diagnostics in IDE live analysis (only command-line build was run).

#### Diff parts with no claim · 1

- `src/MessagePack.SourceGenerator/Analyzers/AnalyzerUtilities.cs:132-140`

---
<sub>Sign: `python3 review/scripts/sign_receipt.py ju26-issue-2283` · read the evidence, not the diff</sub>
