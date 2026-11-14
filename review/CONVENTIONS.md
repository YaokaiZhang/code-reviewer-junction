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
  "provides": ["rebuild-compare | proof-model | flip-test | revert-test | probe | count"],
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
| probe | 60 | an experiment on the real code |
| count | 40 | a number from a tool |
| (none) | 15 | no check backs it |

Adjustments: run by hand −10 · an undo test also backs it +5 · re-run on a clean machine matched +5,
did not match −30 · contradicting evidence caps the score at 25. `combine: any` takes the best
supporting check, `all` the weakest. Bands: high ≥ 80, medium 50–79, low < 50.

The script refuses a claim that uses a file as a kind the file does not `provides`.

**Owner gate (was "Refused")** — separate from the score. A claim NEEDS OWNER when an evidence file's
`contract_changes` shows a user-visible promise changed, the claim's non-test diff parts lie inside
that change's diff parts, and `tripwires.json` shows those hunks touch the same contract; or when it
`depends_on` a claim that needs an owner. A high score never clears the gate. The owner is the top
committer on the contract's paths at base (`context/project.json`); the gate cites matching maintainer
rules from `context/history.json`.

The old tier names stay as words for the kinds: Proved = rebuild-compare / proof, Tested = flip or
undo test, Measured = count, Argued = none, Refused = needs owner.

## Honesty rules

- Every number in a summary, dossier or UI must appear in an evidence file with its command.
- `"produced_by": "hand"` when a person/agent ran it by hand; only say "the tool flagged" for `script`.
- Never write: "zero hallucination", "237 files cut to 15" (say "222 derived from 15 edits").
