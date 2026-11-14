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
- 2283: The crash fix is Tested on 2 tests only (fail on base with AD0001 + CS8785, pass on branch, still pass with the filter reverted). The third new test is filed under the filter claim, because it fails when only the filter is removed.
- 2283: The filter is Refused (rule 1: dropped warnings), owner role analyser owner. The detection link (probe test) is Tested; the site count is Measured; the decision stays Refused. The README and MsgPack004.md text follow the filter and are Refused with it.
- 2283: The "can the location fall outside the compilation" column in report-sites.json is a text heuristic, stated as such; only MsgPack003, MsgPack004 and MsgPack005 were exercised.
- 2283: Evidence from the per-branch harness is marked `produced_by: hand`: the probe cases were designed by the reviewing agent after reading the diff, so "the tool flagged" would be untrue.
- 2283: The remaining duplicate-key crash in a referenced generic is listed under found, not as a claim: same on base and branch, outside this issue.
- Tiers are no longer written by the agent. confidence.py computes a score from the kind of check behind each claim (fixed points, listed in CONVENTIONS) and a separate owner gate. Organizer feedback: "are the labels written by AI? prove them".
- The gate needs a check that a promise changed (evidence `contract_changes`) on the claim's own lines, plus a tripwire on those hunks. It reproduces the 4 claims the agent had marked Refused (C-2234-04, C-2283-02, C-2283-03, C-2297-07). Which lines cause each change is still the reviewer's reading of the probe; an undo-and-rerun per change would make it a machine fact.
- A claim whose lines only partly overlap a changed promise (C-2234-01 shares the `continue` with C-2234-04) gets `shares_lines_with`, not the gate.
- C-2283-04 scores 30 (low): its only evidence was run by hand. This settles the open relabel question.
- Project rules come from upstream history (context/history.json): 37 PRs, 20 rules, each with a linked maintainer quote dated before base. No rule there is about analyzer diagnostics, so the diagnostics gates cite the owner and the probe, not a rule.
- The old-vs-new run (isolation.json) no longer counts as rebuild-compare (90). Same output only speaks for changed lines that ran, so it is its own kind, `old-vs-new-run`, scored 30 + 45 × share of changed lines reached (max 75; 15 on any unexplained difference). Now: 2234 69, 2283 39 (2 of 10 lines ran), 2297 75. No claim used it as support, so no claim score changed.
- Readability flags now carry a trace, like claims: 11 flag cards (4 on 2234, 7 on 2297) in explain/<branch>.decisions.json, checked by decision_check.py (70 of 70 and 74 of 74 steps match the code). The 2234 flags are a maintenance cost, not a bug: the fix is typed into two loops that were already copies. The 2297 flags point at one guard pasted into 9 places, whose reason C-2297-08 already disputes.
- The learned rules are a document people edit (#/rules). Edits record who and what the rule said before; rules are turned off, never deleted.
