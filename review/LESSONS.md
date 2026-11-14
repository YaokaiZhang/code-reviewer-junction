# Lessons

Running log, newest last.

## 2026-11-14

- 2234: write the theorem down before modelling the code, and expect it to be false. "Collecting keys never fails" broke on `[Key(null)]` on a first field. The properties and fields loops had already drifted apart (`else if (stringKey is not null)` against `else`), and duplicated code hides that kind of drift.
- 2234: Dafny 4.11 installs as a .NET tool, but it needs `DOTNET_ROOT` set and its own Z3. `pip install z3-solver==4.12.1.0` provides a `z3` binary that works with `--solver-path`. The model and 9 lemmas verified in seconds.
- 2234: Translating the Dafny model to Python (`dafny translate py`) let us run the model as written against the real C# without porting it by hand. That removes one hand-written link from the chain.
- 2234: 4 of the 8 new analyzer tests pass on base. Without the old-versus-new run they would have looked like evidence.
- 2234: The ExecutionTests project does not build with SDK 8.0.402. The generator references compiler 4.12, the SDK runs 4.11, and CS9057 shows up only as a warning, so look for it when a test project reports that generated members are missing.
- 2297: Do not trust the agent's reason for a guard. The `#if !NETSTANDARD2_0 && !NETFRAMEWORK` guard rests on "not available there". A grep of the reference assemblies plus a 3-target probe took minutes and showed the attribute exists on both targets. Build a negative control into the probe (`NotNullWhen` fails on both) so a pass means something.
- 2297: Ask "what if the user already did this by hand?" Adding an attribute to a partial class the user declares breaks their build with CS0579 if they already added it. No snapshot test would catch this, but a small probe through the real generator did (passes on base, fails on branch).
- 2297: When the snapshot verifier fails on content it reports "Expected source file list to match", which hides the cause. To see the real error, skip the content check in a scratch copy (`TestBehaviors.SkipGeneratedSourcesCheck`). That showed CS1040 for the TransformUtilities removal.
- 2297: A byte diff of T4 output across tools is meaningless (VS and dotnet-t4 lay out the code differently). Comparing the emitted text of `TransformText()` works if both sides use CRLF: the `@""` literals carry the checkout's line endings, and `git show` gives the LF index copy.
- 2297: Snapshot tests are line-ending sensitive (LF copies: 89 of 169 fail). They pass on Linux only because `.gitattributes` sets `eol=crlf` for these files, so the Mac risk is in the checkout, not in the tests.
- 2283: A filter that hides warnings is invisible to a rule and to the branch's own tests. It took a hand-written probe with a control case (same shape, generic in the same project) to show a warning that disappears. Probe the cases the filter targets, not the ones the agent tested.
- 2283: Ablate the diff. Reverting one line (the filter wiring) showed that 1 of the 3 new tests only passes because of the filter, so that test locks the dropping in. Without the ablation all 3 looked like evidence for the crash fix.
- 2283: The dropped warning that matters is MsgPack003 about the consumer's own unattributed type used as `T` in a library generic. The agent's docs say "the defining assembly reports it", but the library never sees `Plain`, so nobody does.
- 2283: Same count, different sites. The handoff's 29 (`grep reportDiagnostic?.Invoke`) includes 2 commented-out lines and misses `this.reportDiagnostic(deferred)` and the raw `reportAnalyzerDiagnostic?.Invoke`. Our method also gives 29. State the method with the number.
- 2283: `old_vs_new_tests.py` ran 0 of the 3 tests on this branch: it takes the namespace from `namespace TempProject` inside a raw string literal in the test file, so its `--filter` matched nothing and the result read "3 do not pass on branch". A result with every test "not_run" should be an error, not a fail. We used a per-branch harness instead (`scripts/dropped_warning_test/run.py`).
- 2283: TRX keys collapse Theory rows if you key by method name; key by the full testName (165 vs 167).
- `old_vs_new_tests.py` took `namespace TempProject` from a raw string literal in a test file and ran 0 of 3 tests for 2283 while reporting "3 do not pass". Fixed by masking string literals; an all-unrun result is now an error. Rerun matches the hand harness (3 of 3 fail on base, pass on branch).
