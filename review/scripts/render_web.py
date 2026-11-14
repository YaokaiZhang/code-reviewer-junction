#!/usr/bin/env python3
"""Bundle dossiers, the evidence files they link, and any receipts into
review/web/data.js so review/web/index.html works from file:// and on Pages.

    python3 review/scripts/render_web.py                 # real dossiers; sample only if none exist
    python3 review/scripts/render_web.py --include-sample
    python3 review/scripts/render_web.py --no-sample

Standard library only.
"""
import argparse
import re
import json
from datetime import datetime, timezone
from pathlib import Path

REVIEW = Path(__file__).resolve().parent.parent
DOSSIER_DIR = REVIEW / "dossier"
RECEIPT_DIR = REVIEW / "receipts"
OUT = REVIEW / "web" / "data.js"


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        print(f"skip {path}: {e}")
        return None


def requirements():
    """R-<issue>-n -> text, from REQUIREMENTS.md."""
    out = {}
    path = REVIEW / "REQUIREMENTS.md"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^- (R-\d+-\d+)(?: \*\(inferred\)\*)?: (.*)$", line)
            if m:
                out[m.group(1)] = m.group(2)
    return out



def slim_isolation(e):
    """Only what the page shows from isolation.json (the full file stays in evidence/)."""
    if not isinstance(e, dict):
        return None
    t = e.get("details") or {}
    c = t.get("coverage") or {}
    proj = next((g for g in t.get("corpus") or [] if g.get("role") == "main"), {})
    return {
        "file": f"evidence/{e.get('branch')}/isolation.json",
        "result": e.get("result"), "summary": e.get("summary"),
        "projects": proj.get("projects") or [], "totals": t.get("totals") or {},
        "explained": [{"claim": x.get("claim"), "what": x.get("what"), "inputs": x.get("inputs")} for x in t.get("explained") or []],
        "unexplained": t.get("unexplained") or [],
        "coverage": {
            "tool": c.get("tool"), "trackable": c.get("trackable"), "reached": c.get("reached"),
            "not_trackable": len(c.get("not_trackable") or []),
            "unreached": [{"side": u.get("side"), "file": u.get("file"), "line": u.get("line"), "text": (u.get("text") or "")[:160]} for u in c.get("unreached") or []],
        },
    }

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--include-sample", action="store_true", help="always include _*.json dossiers")
    g.add_argument("--no-sample", action="store_true", help="never include _*.json dossiers")
    a = ap.parse_args()

    files = sorted(DOSSIER_DIR.glob("*.json"))
    real = [p for p in files if not p.name.startswith("_")]
    samples = [p for p in files if p.name.startswith("_")]
    use_samples = a.include_sample or (not a.no_sample and not real)
    chosen = real + (samples if use_samples else [])

    reqs = requirements()
    bundle = {}
    real_branches = set()
    for p in chosen:
        d = load(p)
        if not isinstance(d, dict):
            continue
        branch = d.get("branch") or p.stem
        is_sample = bool(d.get("sample")) or p.name.startswith("_")
        if is_sample and branch in real_branches:
            continue
        if not is_sample:
            real_branches.add(branch)
        evidence = {}
        for c in d.get("claims") or []:
            for ref in c.get("evidence") or []:
                if ref not in evidence:
                    evidence[ref] = load(REVIEW / ref) if (REVIEW / ref).is_file() else None
        receipt_path = RECEIPT_DIR / (("_sample" if is_sample else branch) + ".json")
        receipt = load(receipt_path) if receipt_path.is_file() else None
        key = p.stem
        d["_key"] = key
        d["_file"] = f"dossier/{p.name}"
        d["_evidence"] = evidence
        d["_receipt"] = receipt
        src = load(REVIEW / "source" / f"{branch}.json") if (REVIEW / "source" / f"{branch}.json").is_file() else None
        d["_source"] = src
        cov = REVIEW / "evidence" / branch / "claim-coverage.json"
        d["_coverage"] = load(cov) if cov.is_file() else None
        for name, fn in (("_confidence", "confidence.json"), ("_tests", "explain-check.json"),
                         ("_readability", "readability.json"), ("_replay", "replay.json"), ("_decisions", "decision-check.json")):
            f = REVIEW / "evidence" / branch / fn
            d[name] = load(f) if f.is_file() else None
        iso = REVIEW / "evidence" / branch / "isolation.json"
        d["_isolation"] = slim_isolation(load(iso)) if iso.is_file() else None
        d["_requirements"] = {c["requirement"]: reqs[c["requirement"]] for c in d.get("claims") or [] if c.get("requirement") in reqs}
        d["sample"] = is_sample
        bundle[key] = d
        print(f"{p.relative_to(REVIEW)}  claims={len(d.get('claims') or [])}  evidence={sum(v is not None for v in evidence.values())}/{len(evidence)}  receipt={'yes' if receipt else 'no'}")

    project = {}
    for name, rel in (("history", "context/history.json"), ("backtest", "evidence/backtest.json"),
                      ("context", "context/project.json")):
        f = REVIEW / rel
        project[name] = load(f) if f.is_file() else None
    body = (f"window.DOSSIERS = {json.dumps(bundle, ensure_ascii=False, indent=1)};\n"
            f"window.PROJECT = {json.dumps(project, ensure_ascii=False, indent=1)};\n")
    # Rewrite only when the data changed, so re-rendering leaves the tree clean.
    old = OUT.read_text(encoding="utf-8") if OUT.is_file() else ""
    if old.endswith(body):
        print(f"{OUT.relative_to(REVIEW.parent)} unchanged ({len(bundle)} dossiers)")
        return
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    js = (
        "// generated by review/scripts/render_web.py — do not edit\n"
        f"window.DOSSIERS_BUILT = {json.dumps(stamp)};\n"
        + body
    )
    OUT.write_text(js, encoding="utf-8")
    print(f"wrote {OUT.relative_to(REVIEW.parent)} ({len(bundle)} dossiers)")


if __name__ == "__main__":
    main()
