#!/usr/bin/env python3
"""Sign a dossier: the owner picks accept / reject / send back for every claim that
needs an owner (evidence/<branch>/confidence.json `gate`), and a receipt is written to
review/receipts/<branch>.json. Same claims and fields as the web page's receipt.

    python3 review/scripts/sign_receipt.py ju26-issue-2283                     # interactive
    python3 review/scripts/sign_receipt.py ju26-issue-2283 --name "Ada L" \\
        --picks C-2283-03=reject,C-2283-04=accept
    python3 review/scripts/sign_receipt.py review/dossier/_sample.json --name X --picks ...

Nothing is pre-picked. Every needs-owner claim needs a pick or nothing is written.
A sample dossier signs to review/receipts/_sample.json. Standard library only.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REVIEW = Path(__file__).resolve().parent.parent
DOSSIER_DIR = REVIEW / "dossier"
RECEIPT_DIR = REVIEW / "receipts"


def confidence(d):
    p = REVIEW / "evidence" / str(d.get("branch")) / "confidence.json"
    return json.loads(p.read_text(encoding="utf-8"))["details"]["claims"] if p.is_file() else {}


def split(d):
    """(needs owner, other claims); a claim with no score yet counts as needing an owner."""
    conf = confidence(d)
    owner, other = [], []
    for c in d.get("claims") or []:
        k = conf.get(c["id"])
        (owner if not k or k.get("gate") else other).append(c)
    return owner, other, conf


def scored(conf, c, o):
    k = conf.get(c["id"]) or {}
    if "score" in k:
        o["score"], o["band"] = k["score"], k["band"]
    if k.get("gate"):
        o["owner"] = k["gate"].get("owner") or ""
    return o
PICKS = {"accept": "accept", "a": "accept",
         "reject": "reject", "r": "reject",
         "send back": "send back", "send-back": "send back", "sendback": "send back", "s": "send back"}


def resolve(arg):
    p = Path(arg)
    if p.suffix == ".json" and p.is_file():
        return p
    p = DOSSIER_DIR / f"{arg}.json"
    if p.is_file():
        return p
    sys.exit(f"no dossier: {arg}")


def parse_picks(s):
    out = {}
    for part in filter(None, (x.strip() for x in s.split(","))):
        if "=" not in part:
            sys.exit(f"bad pick (want ID=accept|reject|send back): {part}")
        cid, val = (x.strip() for x in part.split("=", 1))
        if val.lower() not in PICKS:
            sys.exit(f"bad pick for {cid}: {val}")
        out[cid] = PICKS[val.lower()]
    return out


def ask(prompt):
    try:
        return input(prompt)
    except EOFError:
        sys.exit("\naborted: no input")


def build_receipt(d, name, picks, signed_at=None):
    human, other, conf = split(d)
    missing = [c["id"] for c in human if c["id"] not in picks]
    if missing:
        raise ValueError("no pick for: " + ", ".join(missing))
    unknown = set(picks) - {c["id"] for c in human}
    if unknown:
        raise ValueError("not a needs-owner claim: " + ", ".join(sorted(unknown)))
    if not name.strip():
        raise ValueError("signed_by is empty")
    r = {
        "branch": d.get("branch"),
        "head": d.get("head"),
        "signed_by": name.strip(),
        "signed_at": signed_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "picks": [scored(conf, c, {"id": c["id"], "pick": picks[c["id"]], "claim": c.get("claim", "")}) for c in human],
        "auto_settled": [scored(conf, c, {"id": c["id"]}) for c in other],
        "not_checked": list(d.get("not_checked") or []),
        "uncovered_diff_parts": list(d.get("uncovered_diff_parts") or []),
    }
    if d.get("sample"):
        r["sample"] = True
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("branch", help="branch name or dossier path")
    ap.add_argument("--name", help="who signs (typed by the owner)")
    ap.add_argument("--picks", help="ID=accept|reject|send back, comma separated")
    ap.add_argument("--out", help="override output path")
    ap.add_argument("--stdout", action="store_true", help="print the receipt, do not write it")
    a = ap.parse_args()

    path = resolve(a.branch)
    d = json.loads(path.read_text(encoding="utf-8"))
    if path.name.startswith("_"):
        d["sample"] = True
    human, other, conf = split(d)
    picks = parse_picks(a.picks) if a.picks else {}

    print(f"{d.get('branch')} @ {d.get('head')}" + ("   [SAMPLE]" if d.get("sample") else ""))
    for c in sorted(other, key=lambda c: -conf[c["id"]]["score"]):
        print(f"  {conf[c['id']]['score']:3} {conf[c['id']]['band']:<6} {c['id']}")
    batch = a.picks is not None and a.name is not None  # fully scripted: never prompt
    for c in human:
        if c["id"] in picks or batch:
            continue
        print()
        g = (conf.get(c["id"]) or {}).get("gate") or {}
        print(f"  NEEDS OWNER  {c['id']}" + (f"  · {g.get('owner')} ({g.get('contract')})" if g else ""))
        print(f"  {c.get('claim', '')}")
        if c.get("why_this_tier"):
            print(f"  > {c['why_this_tier']}")
        while True:
            v = ask("  [a]ccept  [r]eject  [s]end back: ").strip().lower()
            if v in PICKS:
                picks[c["id"]] = PICKS[v]
                break
    name = a.name if a.name is not None else ask("\nsigned by: ")

    try:
        r = build_receipt(d, name, picks)
    except ValueError as e:
        sys.exit(f"not signed: {e}")

    text = json.dumps(r, ensure_ascii=False, indent=2) + "\n"
    if a.stdout:
        print(text)
        return
    out = Path(a.out) if a.out else RECEIPT_DIR / (("_sample" if d.get("sample") else d.get("branch")) + ".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"\nsigned → {out}")


if __name__ == "__main__":
    main()
