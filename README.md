# Earned Trust in AI Code

*Read the evidence, not the diff.*

An AI agent writes a change. The reviewer turns it into checkable claims, each with a tier that says what backs it — **Proved, Tested, Measured, Argued, Refused**. Machines settle the first three; a named owner decides the rest and signs a receipt.

Target: [`junction26-messagepack-csharp`](https://github.com/te-industry-tech-office/junction26-messagepack-csharp), base `32258fdb`.

## Owner view

Open `review/web/index.html` (works from disk). Markdown versions for PR comments: `review/dossier/<branch>.md`.

| Branch | Claims | Proved | Tested | Measured | Argued | Refused |
|---|---|---|---|---|---|---|
| [2297](review/dossier/ju26-issue-2297.md) | 10 | 2 | 2 | 3 | 2 | 1 |
| [2234](review/dossier/ju26-issue-2234.md) | 9 | 0 | 3 | 2 | 3 | 1 |
| [2283](review/dossier/ju26-issue-2283.md) | 4 | 0 | 1 | 1 | 0 | 2 |

## Layout

```
review/
  CONVENTIONS.md       schemas, tier rules, honesty rules
  REQUIREMENTS.md      R-<issue>-n, inferred lines marked
  LESSONS.md DECISIONS.md
  evidence/<branch>/   one JSON per check, each with the command that produced it
  dossier/<branch>.*   claims with tiers (.json) and the owner view (.md)
  receipts/            signed receipts
  proof/               Dafny model + proof for 2234
  scripts/             collectors and renderers (Python 3, stdlib)
  web/                 static owner view
```

## Reproduce

Needs a clone of the target with all branches, .NET SDK 8.0.402, Python 3.

```bash
export MP_REPO=/path/to/junction26-messagepack-csharp
```

```bash
python3 review/scripts/diff_classifier.py --repo $MP_REPO --branch ju26-issue-2297
```

```bash
python3 review/scripts/old_vs_new_tests.py --repo $MP_REPO --branch ju26-issue-2234 --out review/evidence/ju26-issue-2234/old-vs-new-tests.json
```

```bash
python3 review/scripts/claim_coverage.py --repo $MP_REPO --branch ju26-issue-2283 --write
```

```bash
python3 review/scripts/render_markdown.py --all && python3 review/scripts/render_web.py
```

```bash
python3 review/scripts/sign_receipt.py ju26-issue-2283
```

Each evidence file's `command` field gives the exact invocation for that check.
