#!/usr/bin/env python3
"""Render a dossier as one Markdown comment for a GitHub PR.

    python3 review/scripts/render_markdown.py ju26-issue-2283
    python3 review/scripts/render_markdown.py --all [--include-sample]
    python3 review/scripts/render_markdown.py review/dossier/_sample.json

Reads review/dossier/<branch>.json (+ the evidence files it links) and writes
review/dossier/<name>.md next to it. Standard library only.
"""
import argparse
import json
import sys
from pathlib import Path

REVIEW = Path(__file__).resolve().parent.parent
DOSSIER_DIR = REVIEW / "dossier"

TIERS = ["Proved", "Tested", "Measured", "Argued", "Refused"]
MACHINE = {"Proved", "Tested", "Measured"}
GLYPH = {"Proved": "■", "Tested": "▲", "Measured": "●", "Argued": "◆", "Refused": "✕"}
RESULT = {"pass": "pass", "fail": "FAIL", "error": "ERROR"}


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_evidence(ref):
    p = REVIEW / ref
    if not p.is_file():
        return None
    try:
        return load_json(p)
    except (OSError, ValueError):
        return None


def md_escape(text):
    return str(text).replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")


def evidence_line(ref, md_dir):
    # links are relative to the .md file
    rel = Path("..") / ref if md_dir == DOSSIER_DIR else Path(ref)
    rel = rel.as_posix()
    ev = load_evidence(ref)
    name = Path(ref).stem
    if ev is None:
        return f"[`{name}`]({rel}) — missing"
    res = RESULT.get(str(ev.get("result", "")).lower(), ev.get("result", "?"))
    who = " · hand" if ev.get("produced_by") == "hand" else ""
    summary = md_escape(ev.get("summary", ""))
    return f"[`{name}`]({rel}) **{res}**{who} — {summary}"


def claim_body(c, md_dir):
    out = []
    why = c.get("why_this_tier")
    if why:
        out.append(f"> {md_escape(why)}")
        out.append("")
    meta = []
    if c.get("requirement"):
        r = c["requirement"] + (" *(inferred)*" if c.get("requirement_inferred") else "")
        meta.append(r)
    if c.get("owner_role") and c.get("tier") not in MACHINE:
        meta.append(f"owner: **{md_escape(c['owner_role'])}**")
    if meta:
        out.append(" · ".join(meta))
        out.append("")
    for link in c.get("chain") or []:
        t = link.get("tier", "?")
        out.append(f"- {GLYPH.get(t, '·')} {t} — {md_escape(link.get('link', ''))}")
    if c.get("chain"):
        out.append("")
    for ref in c.get("evidence") or []:
        out.append("- " + evidence_line(ref, md_dir))
    for part in c.get("diff_parts") or []:
        out.append(f"- `{part}`")
    if c.get("evidence") or c.get("diff_parts"):
        out.append("")
    return out


def render(d, md_dir=DOSSIER_DIR):
    claims = d.get("claims") or []
    counts = {t: sum(1 for c in claims if c.get("tier") == t) for t in TIERS}
    human = [c for c in claims if c.get("tier") not in MACHINE]
    machine = [c for c in claims if c.get("tier") in MACHINE]
    # Refused first, then Argued; machine rows in tier order
    human.sort(key=lambda c: (0 if c.get("tier") == "Refused" else 1, c.get("id", "")))
    machine.sort(key=lambda c: (TIERS.index(c["tier"]), c.get("id", "")))

    L = []
    issue = d.get("issue")
    title = md_escape(d.get("title", ""))
    head = f"### {d.get('branch', '?')}"
    if issue:
        head += f" · #{issue}"
    if title:
        head += f" — {title}"
    L.append(head)
    if d.get("sample"):
        L.append("")
        L.append("> **SAMPLE DOSSIER** — not a real review.")
    diff = d.get("diff") or {}
    line = f"`{d.get('base', '?')}..{d.get('head', '?')}`"
    if diff:
        line += f" · {diff.get('files', '?')} files +{diff.get('insertions', '?')} −{diff.get('deletions', '?')}"
    L += ["", line, ""]

    L.append("| " + " | ".join(f"{GLYPH[t]} {t}" for t in TIERS) + " |")
    L.append("|" + ":-:|" * len(TIERS))
    L.append("| " + " | ".join(str(counts[t]) if counts[t] else "·" for t in TIERS) + " |")
    L.append("")

    if human:
        L.append(f"#### Owner decides · {len(human)}")
        L.append("")
        for c in human:
            t = c.get("tier", "Argued")
            L.append(f"**{GLYPH.get(t, '◆')} {t} · {c.get('id', '?')}** — {md_escape(c.get('claim', ''))}")
            L.append("")
            L += claim_body(c, md_dir)
            L += ["- [ ] accept", "- [ ] reject", "- [ ] send back", ""]

    if machine:
        L.append(f"#### Machine settled · {len(machine)}")
        L.append("")
        for c in machine:
            t = c["tier"]
            L.append(f"<details><summary>{GLYPH[t]} {t} · {c.get('id', '?')} — {md_escape(c.get('claim', ''))}</summary>")
            L.append("")
            L += claim_body(c, md_dir)
            L.append("</details>")
            L.append("")

    def section(name, items, fmt=lambda x: md_escape(x)):
        if not items:
            return
        L.append(f"#### {name} · {len(items)}")
        L.append("")
        for it in items:
            L.append(f"- {fmt(it)}")
        L.append("")

    section("Found", d.get("found"))
    section("Refused", d.get("refused"),
            lambda r: f"**{md_escape(r.get('what', ''))}** — {md_escape(r.get('why', ''))}" if isinstance(r, dict) else md_escape(r))
    section("Scope drift", d.get("scope_drift"))
    section("Not checked", d.get("not_checked"))
    section("Diff parts with no claim", d.get("uncovered_diff_parts"), lambda p: f"`{p}`")

    L.append("---")
    L.append(f"<sub>Sign: `python3 review/scripts/sign_receipt.py {d.get('branch', '<branch>')}` · read the evidence, not the diff</sub>")
    L.append("")
    return "\n".join(L)


def resolve(arg):
    p = Path(arg)
    if p.suffix == ".json" and p.is_file():
        return p
    p = DOSSIER_DIR / f"{arg}.json"
    if p.is_file():
        return p
    sys.exit(f"no dossier: {arg}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("branch", nargs="*", help="branch name or dossier path")
    ap.add_argument("--all", action="store_true", help="render every dossier in review/dossier/")
    ap.add_argument("--include-sample", action="store_true", help="with --all, also render files starting with _")
    a = ap.parse_args()

    paths = [resolve(b) for b in a.branch]
    if a.all:
        for p in sorted(DOSSIER_DIR.glob("*.json")):
            if p.name.startswith("_") and not a.include_sample:
                continue
            paths.append(p)
    if not paths:
        ap.error("give a branch or --all")

    for p in paths:
        d = load_json(p)
        out = p.with_suffix(".md")
        out.write_text(render(d, out.parent.resolve()), encoding="utf-8")
        print(out.relative_to(REVIEW.parent) if out.resolve().is_relative_to(REVIEW.parent) else out)


if __name__ == "__main__":
    main()
