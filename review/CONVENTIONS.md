# Conventions

Shared rules for everything under `review/`. Target repo: `te-industry-tech-office/junction26-messagepack-csharp`, base commit `32258fdb`.

Scripts take the path of a local clone of the target repo as `--repo` (or env `MP_REPO`). Python 3, standard library only. Scripts never modify the target clone's checked-out branch in place; they use `git worktree add` under a temp dir.

## Evidence file — `evidence/<branch>/<check>.json`

```json
{
  "check": "snapshot-classifier",
  "branch": "ju26-issue-2297",
  "base": "32258fdb",
  "command": "the exact command that produced this",
  "result": "pass | fail | error",
  "provides": ["rebuild-compare | proof-model | flip-test | revert-test | old-vs-new-run | probe | count"],
  "contract_changes": [{"contract": "diagnostics", "what": "...", "diff_parts": ["..."]}],
  "summary": "one line, every number in it comes from details",
  "details": {},
  "tool_versions": {},
  "produced_by": "script | hand"
}
```

## Dossier — `dossier/<branch>.json`

```json
{
  "branch": "ju26-issue-2283",
  "issue": 2283,
  "title": "short title of the issue",
  "summary": "what the AI changed, in two or three plain sentences",
  "base": "32258fdb",
  "head": "9df83c38",
  "diff": {"files": 4, "insertions": 225, "deletions": 3},
  "claims": [ {
    "id": "C-2283-01",
    "claim": "one plain sentence",
    "tier": "Proved | Tested | Measured | Argued | Refused",
    "why_this_tier": "one sentence, no confidence number",
    "requirement": "R-2283-1",
    "requirement_inferred": false,
    "evidence": ["evidence/ju26-issue-2283/old-vs-new-tests.json"],
    "support": [{"file": "evidence/ju26-issue-2283/old-vs-new-tests.json", "kind": "flip-test"}],
    "combine": "any | all (all = a chain: the weakest link counts)",
    "contradicted_by": ["evidence files that contradict the claim"],
    "depends_on": ["claim ids this claim stands or falls with"],
    "diff_parts": ["src/.../TypeCollector.cs:236-240"],
    "owner_role": "only for Argued and Refused",
    "chain": [{"link": "...", "tier": "Tested"}]
  } ],
  "found": ["what the AI reviewer found"],
  "refused": [{"what": "...", "why": "..."}],
  "scope_drift": ["..."],
  "not_checked": ["..."],
  "uncovered_diff_parts": ["diff parts no claim covers"]
}
```

## Confidence score and owner gate — `scripts/confidence.py`

The agent does not pick a tier or a number. The script computes both from the evidence and writes
`evidence/<branch>/confidence.json`.

**Score (0–100)** — the kind of check the claim uses, then fixed adjustments:

| Kind (`support[].kind`) | Points | Plain words |
|---|---|---|
| rebuild-compare | 90 | rebuilt and compared: identical |
| proof-model | 80 | model proved, and matched to the real code on every tested input |
| flip-test | 75 | a test fails before the change and passes after |
| revert-test | 75 | undo only this change: a test fails |
| old-vs-new-run | 30–75 | old and new code on the same inputs: no unexplained difference (points below) |
| probe | 60 | an experiment on the real code |
| count | 40 | code metric, before vs after (e.g. copy-pasted blocks, complexity) |
| (none) | 15 | no check backs it |

**old-vs-new-run** (`isolation.json`) has no fixed points. Same output only speaks for the changed
lines that ran, so: 30 + 45 × (changed lines reached ÷ trackable changed lines), rounded; 30 when no
changed line is trackable; 15 when any difference matches no rule. At most 75, below rebuild-compare,
because it tries a corpus of inputs rather than every file. confidence.json also records this score
per branch under `details.old_vs_new`, so pages can show it without a claim using it.

Adjustments: run by hand −10 · an undo test also backs it +5 · re-run on a clean machine matched +5,
did not match −30 · contradicting evidence caps the score at 25. `combine: any` takes the best
supporting check, `all` the weakest. Bands: high ≥ 80, medium 50–79, low < 50.

The script refuses a claim that uses a file as a kind the file does not `provides`.

**Owner gate (was "Refused")** — separate from the score. It has two inputs.
1. Old vs new (`isolation.json`): the old and the new code run on the same inputs from before the change,
   with line coverage. A changed line that ran with the same output clears. A difference that changes a
   promise gates the claim its expected rule names (a project warning appears or goes away → diagnostics;
   a generated file that existed before differs, or a new compiler error → generated; a crash that goes
   away is a fix). A difference no rule explains gates every claim whose lines that input ran. A changed
   line no input runs, in a hunk `tripwires.json` ties to a contract, gates every claim that covers it.
2. Experiments: an evidence file's `contract_changes` shows a promise changed, the claim's non-test diff
   parts lie inside that change's diff parts, and `tripwires.json` shows those hunks touch the contract.
A claim that `depends_on` a gated claim is gated too. A high score never clears the gate. The owner is the top
committer on the contract's paths at base (`context/project.json`); the gate cites matching maintainer
rules from `context/history.json`.

The old tier names stay as words for the kinds: Proved = rebuild-compare / proof, Tested = flip or
undo test, Measured = count, Argued = none, Refused = needs owner.

## Traces for readability flags — `explain/<branch>.decisions.json`

Each flag in `evidence/<branch>/readability.json` gets a decision card like a claim: `kind: "flag"`, the
flag's id, steps that cite the real lines, a verdict and reasons. Its reasons must name the
readability.json file. `decision_check.py` checks the steps against the code and fails when a flag has
no card or a card names a flag that does not exist.

## Learned rules — `context/history.json`

People edit the rules on the owner view's Rules page (`#/rules`), served by `scripts/dev_server.py`
(`npm run dev`). A rule is `{id, concern, rule, sources, off?}`. Rules are never deleted, only turned off
(`off: true`), so evidence that already cites one still resolves. Each saved change appends
`edits: [{who, when, before}]` to the rule; a new rule carries `added_by`. Saving re-runs confidence.py
and render_web.py. Turned-off rules are left out of owner-gate citations and readability flags. The page
reads rule text from this file, so a reworded rule shows on every flag at once.

## Honesty rules

- Every number in a summary, dossier or UI must appear in an evidence file with its command.
- `"produced_by": "hand"` when a person/agent ran it by hand; only say "the tool flagged" for `script`.
- Never write: "zero hallucination", "237 files cut to 15" (say "222 derived from 15 edits").
