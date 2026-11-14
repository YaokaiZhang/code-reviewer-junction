### ju26-issue-2234 · #2234 — The analyzer does not work if SuppressSourceGeneration = true

`32258fdb..9007cee1` · 4 files +262 −4

**What the AI changed:** The analyzer crashed when a type had repeated keys, or mixed integer and string keys. The AI changed TypeCollector.cs so the analyzer reports MsgPack005 instead. It keeps the first member for each key, and skips a member with the wrong key kind once it is reported. It also added analyzer tests, execution tests and a README section on opting out of source generation.

| ■ Proved | ▲ Tested | ● Measured | ◆ Argued | ✕ Refused |
|:-:|:-:|:-:|:-:|:-:|
| · | 3 | 2 | 3 | 1 |

#### Owner decides · 4

**✕ Refused · C-2234-04** — The change hides a diagnostic. The new `continue` also skips collecting the member's type. So a member with a mixed key and an unserializable type no longer gets MsgPack003. Before the change, it got MsgPack003 when the first key was a string.

> It drops a diagnostic the old code reported. Whether that is fine, given the same member already gets the MsgPack005 error, is a product decision.

R-2234-4 *(inferred)* · owner: **analyzer owner**

- [`findings-probes`](../evidence/ju26-issue-2234/findings-probes.json) **pass** — (a) continue skips member type: confirmed; (b) second member of a duplicate key gets MsgPack005: yes, finding dropped; null-key first field crashes analyzer on branch: confirmed (11 scenarios, real analyzer, base and branch)
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1008`
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1148`

- [ ] accept
- [ ] reject
- [ ] send back

**◆ Argued · C-2234-03** — The fix is incomplete. If a type's first keyed member is a field with [Key(null)], the analyzer still crashes (AD0001, ArgumentNullException). This also happens with SuppressSourceGeneration = true.

> An experiment on the real analyzer shows the crash before and after the change. That is a gap, not a passing check, so it cannot count as Tested and the owner decides.

R-2234-2 *(inferred)* · owner: **analyzer owner**

- [`findings-probes`](../evidence/ju26-issue-2234/findings-probes.json) **pass** — (a) continue skips member type: confirmed; (b) second member of a duplicate key gets MsgPack005: yes, finding dropped; null-key first field crashes analyzer on branch: confirmed (11 scenarios, real analyzer, base and branch)
- [`proof`](../evidence/ju26-issue-2234/proof.json) **pass** — Dafny: Dafny program verifier finished with 23 verified, 0 errors; locked theorem 'never fails' is false for the branch (counterexample: first keyed member is a field with [Key(null)]), the stated mutation fails to verify; model vs real C# on 3710 inputs of 1..4 members: branch 0 mismatches, base 0 mismatches; C# threw on 156 branch inputs and 3346 base inputs; with int/string keys only (1592 inputs) C# threw on 1500 on base and 0 on branch
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1148`
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1179-1182`

- [ ] accept
- [ ] reject
- [ ] send back

**◆ Argued · C-2234-08** — A type with SuppressSourceGeneration gets no generated formatter, and still round-trips through the run-time (dynamic) resolver. The 2 new execution tests are meant to show this.

> The tests never ran. Their project does not build here, before or after the change, because the source generator does not load (CS9057).

R-2234-1 · owner: **test owner**

- [`old-vs-new-tests`](../evidence/ju26-issue-2234/old-vs-new-tests.json) **ERROR** — 10 new or changed test methods (10 added, 0 modified): 4 fail on base and pass on branch, 4 pass on base (not evidence), 0 fail on branch, 2 not runnable here (project does not build on branch)
- [`execution-tests-build`](../evidence/ju26-issue-2234/execution-tests-build.json) **FAIL** · hand — ExecutionTests does not build here: the source generator is not loaded (CS9057, generator references compiler 4.12, SDK 8.0.402 runs 4.11), so 5 CS errors; the new test file also raises SA1649
- `tests/MessagePack.SourceGenerator.ExecutionTests/SuppressedSourceGenerationTests.cs:1-37`

- [ ] accept
- [ ] reject
- [ ] send back

**◆ Argued · C-2234-09** — The new README section says the analyzer still checks suppressed types for MsgPack003, 004, 005, 012 and 015, and skips MsgPack011, 016 and 017 for them.

> It is documentation. Tests cover 003, 004, 005, 015 and the skipped ones, but not 012. And C-2234-03 shows a case where the MsgPack005 check still crashes.

R-2234-1 · owner: **docs owner**

- [`old-vs-new-tests`](../evidence/ju26-issue-2234/old-vs-new-tests.json) **ERROR** — 10 new or changed test methods (10 added, 0 modified): 4 fail on base and pass on branch, 4 pass on base (not evidence), 0 fail on branch, 2 not runnable here (project does not build on branch)
- [`findings-probes`](../evidence/ju26-issue-2234/findings-probes.json) **pass** — (a) continue skips member type: confirmed; (b) second member of a duplicate key gets MsgPack005: yes, finding dropped; null-key first field crashes analyzer on branch: confirmed (11 scenarios, real analyzer, base and branch)
- `README.md:1620-1633`

- [ ] accept
- [ ] reject
- [ ] send back

#### Machine settled · 5

<details><summary>▲ Tested · C-2234-01 — The analyzer no longer crashes on duplicate integer keys, duplicate string keys or mixed key kinds. It reports MsgPack005 instead, with or without SuppressSourceGeneration.</summary>

> 4 new tests fail before the change, because the analyzer crashes (AD0001) next to the MsgPack005. They pass after.

R-2234-1

- [`old-vs-new-tests`](../evidence/ju26-issue-2234/old-vs-new-tests.json) **ERROR** — 10 new or changed test methods (10 added, 0 modified): 4 fail on base and pass on branch, 4 pass on base (not evidence), 0 fail on branch, 2 not runnable here (project does not build on branch)
- [`findings-probes`](../evidence/ju26-issue-2234/findings-probes.json) **pass** — (a) continue skips member type: confirmed; (b) second member of a duplicate key gets MsgPack005: yes, finding dropped; null-key first field crashes analyzer on branch: confirmed (11 scenarios, real analyzer, base and branch)
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1008`
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1023-1026`
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1039-1042`
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1148`
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1163-1166`
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1179-1182`
- `tests/MessagePack.SourceGenerator.Tests/SuppressSourceGenerationAnalyzerTests.cs:80-167`

</details>

<details><summary>▲ Tested · C-2234-02 — After the change, the real TypeCollector never throws on any list of 1 to 4 keyed members with integer or string keys. Before the change, it threw on most of them.</summary>

> A formal model, written in Dafny, proves this for lists of any length. The model matches the real C# code on every input up to 4 members. The real code throws before the change and not after. The weakest step is a test, so the claim counts as Tested.

R-2234-2 *(inferred)*

- ■ Proved — The Dafny model proves BranchNeverFailsForIntAndStringKeys with no unproven assumptions.
- ▲ Tested — The model matches the real TypeCollector on 3710 inputs, before and after the change, with 0 mismatches.

- [`proof`](../evidence/ju26-issue-2234/proof.json) **pass** — Dafny: Dafny program verifier finished with 23 verified, 0 errors; locked theorem 'never fails' is false for the branch (counterexample: first keyed member is a field with [Key(null)]), the stated mutation fails to verify; model vs real C# on 3710 inputs of 1..4 members: branch 0 mismatches, base 0 mismatches; C# threw on 156 branch inputs and 3346 base inputs; with int/string keys only (1592 inputs) C# threw on 1500 on base and 0 on branch
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1008`
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1023-1026`
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1039-1042`
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1148`
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1163-1166`
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1179-1182`

</details>

<details><summary>▲ Tested · C-2234-05 — Every repeated key is reported. When two members share a key, the first one is kept and the second gets MsgPack005 ('must be unique').</summary>

> The duplicate-key tests fail before the change and pass after. The model's proof DupReported matches the real C# code on every input up to 4 members.

R-2234-3 *(inferred)*

- ■ Proved — The Dafny model proves DupReported: the first member wins and every repeat is reported.
- ▲ Tested — The model matches the real TypeCollector on 3710 inputs.
- ▲ Tested — The duplicate-key tests fail before the change and pass after.

- [`old-vs-new-tests`](../evidence/ju26-issue-2234/old-vs-new-tests.json) **ERROR** — 10 new or changed test methods (10 added, 0 modified): 4 fail on base and pass on branch, 4 pass on base (not evidence), 0 fail on branch, 2 not runnable here (project does not build on branch)
- [`findings-probes`](../evidence/ju26-issue-2234/findings-probes.json) **pass** — (a) continue skips member type: confirmed; (b) second member of a duplicate key gets MsgPack005: yes, finding dropped; null-key first field crashes analyzer on branch: confirmed (11 scenarios, real analyzer, base and branch)
- [`proof`](../evidence/ju26-issue-2234/proof.json) **pass** — Dafny: Dafny program verifier finished with 23 verified, 0 errors; locked theorem 'never fails' is false for the branch (counterexample: first keyed member is a field with [Key(null)]), the stated mutation fails to verify; model vs real C# on 3710 inputs of 1..4 members: branch 0 mismatches, base 0 mismatches; C# threw on 156 branch inputs and 3346 base inputs; with int/string keys only (1592 inputs) C# threw on 1500 on base and 0 on branch
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1023-1026`
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1039-1042`
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1163-1166`
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1179-1182`

</details>

<details><summary>● Measured · C-2234-06 — The fix is copied into both the properties loop and the fields loop, which adds duplicate code to TypeCollector.cs.</summary>

> The numbers come from a script that measures duplicate code and complexity, run before and after the change.

R-2234-1

- [`clone-complexity`](../evidence/ju26-issue-2234/clone-complexity.json) **pass** — TypeCollector.cs: duplicated blocks 10 -&gt; 12, duplicated normalised lines 244 -&gt; 258 (window 6); 6 of 10 added code lines sit in duplicated blocks; method GetObjectInfo complexity estimate 162 -&gt; 166
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1008`
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1023-1026`
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1039-1042`
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1148`
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1163-1166`
- `src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs:1179-1182`

</details>

<details><summary>● Measured · C-2234-07 — 4 of the 8 new analyzer tests already pass before the change, so they guard old behaviour and do not show the fix works. They cover a missing key, AllowPrivate, the member type and generation-only diagnostics.</summary>

> The count comes from running the tests before and after the change.

R-2234-1

- [`old-vs-new-tests`](../evidence/ju26-issue-2234/old-vs-new-tests.json) **ERROR** — 10 new or changed test methods (10 added, 0 modified): 4 fail on base and pass on branch, 4 pass on base (not evidence), 0 fail on branch, 2 not runnable here (project does not build on branch)
- `tests/MessagePack.SourceGenerator.Tests/SuppressSourceGenerationAnalyzerTests.cs:1-79`
- `tests/MessagePack.SourceGenerator.Tests/SuppressSourceGenerationAnalyzerTests.cs:168-193`

</details>

#### Found · 7

- We found (probe, real analyzer): the new `continue` skips CollectCore for the member's type, so MsgPack003 is lost for a mixed-key member (C-2234-04).
- We found (probe, real analyzer, Dafny model): a first field with [Key(null)] still crashes the analyzer with ArgumentNullException, on base and branch, with SuppressSourceGeneration too. The properties loop guards with `else if (stringKey is not null)`; the fields loop uses a bare `else` (C-2234-03).
- The theorem in the brief ('collecting keys never fails, whatever keys repeat or mix kinds') is false for the real code. Dafny proves the exact condition instead: it fails if and only if the first keyed member is a field with [Key(null)].
- Finding (b) dropped: the second member of a repeated key gets MsgPack005 on the branch, and the first one is kept (C-2234-05).
- The base crash on repeated keys also happens without SuppressSourceGeneration (test DuplicateKeysAreReportedWithoutAnalyzerFailureForGeneratedTypes fails on base). The bug is not specific to suppressed types, and 4 of the 8 analyzer tests show the analyzer already validated suppressed types on base.
- SuppressedSourceGenerationTests.cs raises StyleCop SA1649 (file name does not match first type name).
- Pre-existing, outside the diff: the fields-loop BothStringAndIntKeyAreNull diagnostic passes no message arguments, so the message reads 'Both int and string keys are null: {0}.{1}'.

#### Refused · 1

- **C-2234-04: the `continue` drops MsgPack003 for mixed-key members** — Dropping a diagnostic that base reported is a product call for the analyzer owner.

#### Scope drift · 1

- README.md gains a 14-line 'Opting out of source generation' section. The issue title asks for an analyzer fix, not documentation.

#### Not checked · 7

- The 2 execution tests (SuppressedSourceGenerationTests.cs): the project does not build here because the generator needs compiler 4.12 and SDK 8.0.402 has 4.11 (CS9057).
- Source generator output (reportDiagnostic is null in the generator path) for repeated or mixed keys: what code is emitted when the first member wins.
- MsgPack012 (inaccessible types) for suppressed types, which the README claims.
- The full test suite on the branch; only the new tests and our probes were run.
- Members without any [Key] attribute, inherited members, records with positional parameters: not in the model's input domain.
- The model's input domain is keys 0, 1, "a", "b" and null, with up to 4 members, so the model-vs-C# check covers 3710 inputs, not all inputs.
- The issue body: only the issue title was available to us.

---
<sub>Sign: `python3 review/scripts/sign_receipt.py ju26-issue-2234` · read the evidence, not the diff</sub>
