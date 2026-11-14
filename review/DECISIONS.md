# Decisions

Running log, newest last.

## 2026-11-14

- Tool repo (this repo) is separate from the target fork; scripts take `--repo <clone>`.
- Collectors are Python 3, stdlib only, so they run on any laptop without extra installs.
- Owner view ships twice: Markdown (PR comment) and a static HTML page in the retro desk-computer style.
- 2234: A defect that a probe reproduces on both base and branch gets tier Argued (C-2234-03). The tier rules only give Tested to a test that fails on base and passes on the branch. The reproduction is still attached as evidence. We may need a tier for a reproduced gap.
- 2234: The `continue` that drops MsgPack003 for mixed-key members is Refused (rule 1: dropped warning), and the owner role is the analyzer owner.
- 2234: The locked theorem was not weakened to make it pass. proof.json records it as false, with the counterexample and a mutation run showing that "never fails" does not verify. The weaker lemmas that do hold are listed separately.
- 2234: Model-vs-C# inputs are keys {0, 1, "a", "b", null} × {property, field}, 1 to 4 members, properties before fields (the order the C# visits them): 3710 inputs.
- 2297: The attribute on user-declared partial resolver classes is Refused (rule 1: public type metadata plus a CS0579 break for users who already excluded the resolver by hand). The owner role is the public API owner. Internal formatters are not public surface, so they do not trigger rule 1. They are covered by the Proved and Tested rows.
- 2297: The guard is an Argued row stated as the agent's claim, with the contradicting evidence attached. We did not invent a "refuted" tier.
- 2297: The template check counts as Proved: dotnet-t4 regeneration compared on emitted text, calibrated 6/6 on base, with a 6/6 negative control. Its limit (not byte-for-byte with VS) is written in the evidence.
- 2297: The TransformUtilities edit is Tested (reverting it fails a test, restoring it passes). We call it required, with one side effect, and do not call it scope drift.
