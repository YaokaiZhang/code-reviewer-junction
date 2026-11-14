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
