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

BANDS = ["high", "medium", "low"]
GLYPH = {"high": "●", "medium": "◐", "low": "○"}
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
    g = c.get("_conf", {}).get("gate")
    if g:
        meta.append(f"owner: **{md_escape(g.get('owner') or '?')}** ({md_escape(g['contract'])})")
    if meta:
        out.append(" · ".join(meta))
        out.append("")
    for link in c.get("chain") or []:
        out.append(f"- {md_escape(link.get('link', ''))}")
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
    conf = (load_evidence(f"evidence/{d.get('branch')}/confidence.json") or {}).get("details", {}).get("claims", {})
    for c in claims:
        c["_conf"] = conf.get(c.get("id"), {"score": 0, "band": "low"})
    counts = {b: sum(1 for c in claims if c["_conf"]["band"] == b) for b in BANDS}
    owner = sorted((c for c in claims if c["_conf"].get("gate")), key=lambda c: c.get("id", ""))
    rest = sorted((c for c in claims if not c["_conf"].get("gate")),
                  key=lambda c: (-c["_conf"]["score"], c.get("id", "")))

    def label(c):
        k = c["_conf"]
        return f"{GLYPH[k['band']]} {k['score']} · {c.get('id', '?')}"

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
    if d.get("summary"):
        L += [f"**What the AI changed:** {md_escape(d['summary'])}", ""]

    L.append("| " + " | ".join(f"{GLYPH[b]} {b}" for b in BANDS) + " | needs owner |")
    L.append("|" + ":-:|" * (len(BANDS) + 1))
    L.append("| " + " | ".join(str(counts[b]) if counts[b] else "·" for b in BANDS) + f" | {len(owner) or '·'} |")
    L.append("")
    L.append("<sub>Confidence 0–100 from the evidence, by a fixed formula. Needs owner: a check shows a promise to users changed.</sub>")
    L.append("")

    if owner:
        L.append(f"#### Needs owner · {len(owner)}")
        L.append("")
        for c in owner:
            L.append(f"**{label(c)}** — {md_escape(c.get('claim', ''))}")
            L.append("")
            L += claim_body(c, md_dir)
            L += ["- [ ] accept", "- [ ] reject", "- [ ] send back", ""]

    if rest:
        L.append(f"#### By confidence · {len(rest)}")
        L.append("")
        for c in rest:
            L.append(f"<details><summary>{label(c)} — {md_escape(c.get('claim', ''))}</summary>")
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
    section("Needs owner: why", d.get("refused"),
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
