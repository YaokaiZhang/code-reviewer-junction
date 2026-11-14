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

## Tier rules (first match wins)

1. **Refused** — touches public API, wire format, silenced or dropped warnings, or security.
2. **Proved** — a deterministic checker passed on the real artefact (regeneration, byte diff, proof with no gap).
3. **Tested** — a test fails on base and passes on the branch. A chain takes its weakest link.
4. **Measured** — the evidence is a number from a tool.
5. **Argued** — everything else.

Machines settle Proved/Tested/Measured. A named owner decides Argued and Refused.

## Honesty rules

- Every number in a summary, dossier or UI must appear in an evidence file with its command.
- `"produced_by": "hand"` when a person/agent ran it by hand; only say "the tool flagged" for `script`.
- Never write: "zero hallucination", "237 files cut to 15" (say "222 derived from 15 edits").
