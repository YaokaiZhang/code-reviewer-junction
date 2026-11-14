# Earned Trust in AI Code

*Read the evidence, not the diff.*

An AI agent writes a change. The reviewer turns it into checkable claims. Each claim gets a **confidence score** (0–100) from the evidence behind it, by a fixed formula. When the old and the new code give a different result on something users rely on, or no input runs a changed line, the claim **needs an owner**: a named maintainer decides and signs a receipt.

Target: [`junction26-messagepack-csharp`](https://github.com/te-industry-tech-office/junction26-messagepack-csharp), base `32258fdb`.

## Owner view

Open `review/web/index.html` (works from disk). Markdown versions for PR comments: `review/dossier/<branch>.md`.

| Branch | Claims | High (80+) | Medium (50–79) | Low (<50) | Needs owner | New tests that prove the fix |
|---|---|---|---|---|---|---|
| [2297](review/dossier/ju26-issue-2297.md) | 10 | 4 | 3 | 3 | 1 | 2 of 2 |
| [2234](review/dossier/ju26-issue-2234.md) | 9 | 3 | 2 | 4 | 1 | 4 of 10 |
| [2283](review/dossier/ju26-issue-2283.md) | 4 | 1 | 2 | 1 | 2 | 3 of 3 |

## Layout

```
review/
  CONVENTIONS.md       schemas, score formula, owner gate, honesty rules
  REQUIREMENTS.md      R-<issue>-n, inferred lines marked
  LESSONS.md DECISIONS.md
  evidence/<branch>/   one JSON per check, each with the command that produced it
  dossier/<branch>.*   claims (.json) and the PR comment (.md)
  source/<branch>.json diff hunks behind each claim, with GitHub links
  receipts/            signed receipts
  proof/               Dafny model + proof for 2234
  scripts/             collectors and renderers (Python 3, stdlib)
  web/                 static owner view
```

## Run

Needs Python 3, git and Node (for `npm run`; or call `./review.sh <command>` directly).

```bash
npm run dev
```

Opens the owner view at http://localhost:5173/web/. No other setup needed. Another port: `npm run dev -- --port 3001` (or `PORT=3001 npm run dev`).

To reproduce the evidence:

```bash
npm run setup
```

```bash
npm run evidence
```

```bash
npm run tests
```

| Command | Does | Time |
|---|---|---|
| `npm run dev` | render dossiers, serve the owner view | 1 s |
| `npm run setup` | clone the target into `.work/mp`, install .NET SDK 8.0.402 into `.work/dotnet` if missing | 1–2 min |
| `npm run evidence` | git-only collectors: diff classifier, clones and complexity, report sites, claim coverage, source excerpts for the owner view | seconds |
| `npm run tests` | build and run the C# tests: regeneration, TransformUtilities removal, old-vs-new tests, dropped-warning probe | ~4 min |
| `npm run sign -- ju26-issue-2283` | sign a dossier from the terminal, writes `review/receipts/` | — |

Use your own clone with `MP_REPO=/path/to/clone npm run evidence`. The Dafny proof (`review/proof/`) and the template check need Dafny and dotnet-t4 and are not part of `npm run tests`. Each evidence file's `command` field gives the exact invocation.
