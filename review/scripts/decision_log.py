#!/usr/bin/env python3
"""The maintainer decision log: review/context/decisions.jsonl, one JSON object per line.

    from decision_log import append, read
    append([{"source": "receipt", "pr_or_branch": "ju26-issue-2283", "claim_id": "C-2283-03", ...}])
    rows = read()

    python3 review/scripts/decision_log.py            # print the log, one line per decision

Append-only: lines are only ever added at the end, never rewritten or removed. A later line about the
same claim supersedes an earlier one for readers that want the latest decision.
A line is {source, pr_or_branch, claim_id, rule_ids_cited, contracts_tripped, decision, reason, who,
when (YYYY-MM-DD), url}. Standard library only.
"""
import json
import os
import re
import sys
import threading
from pathlib import Path

LOG = Path(__file__).resolve().parent.parent / "context" / "decisions.jsonl"
SOURCES = {"receipt", "history", "control"}
DECISIONS = {"accept", "reject", "send_back", "reverted", "pushed_back", "merged_clean"}
KEYS = ("source", "pr_or_branch", "claim_id", "rule_ids_cited", "contracts_tripped", "decision",
        "reason", "who", "when", "url")
_lock = threading.Lock()


def problems(line):
    """What is wrong with one decision line (empty when it is fine)."""
    if not isinstance(line, dict):
        return ["not an object"]
    p = []
    if line.get("source") not in SOURCES:
        p.append(f"source must be one of {sorted(SOURCES)}")
    if not isinstance(line.get("pr_or_branch"), str) or not line["pr_or_branch"]:
        p.append("pr_or_branch is empty")
    if line.get("claim_id") is not None and not isinstance(line["claim_id"], str):
        p.append("claim_id must be a string or null")
    for k in ("rule_ids_cited", "contracts_tripped"):
        if not isinstance(line.get(k), list) or any(not isinstance(x, str) for x in line[k]):
            p.append(f"{k} must be a list of strings")
    if line.get("decision") not in DECISIONS:
        p.append(f"decision must be one of {sorted(DECISIONS)}")
    if line.get("who") is not None and not isinstance(line["who"], str):
        p.append("who must be a string or null")
    if not isinstance(line.get("when"), str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", line["when"]):
        p.append("when must be YYYY-MM-DD")
    return p


def append(lines, path=LOG):
    """Validate every line, then add them at the end of the log. Returns how many were written."""
    lines = list(lines)
    for i, ln in enumerate(lines):
        bad = problems(ln)
        if bad:
            raise ValueError(f"decision {i + 1}: " + "; ".join(bad))
    if not lines:
        return 0
    text = "".join(json.dumps({k: ln.get(k) for k in KEYS}, ensure_ascii=False) + "\n" for ln in lines)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        # a log whose last line lost its newline gets one first, so the new line never merges into it
        if path.is_file() and path.stat().st_size:
            with open(path, "rb") as f:
                f.seek(-1, os.SEEK_END)
                if f.read(1) != b"\n":
                    text = "\n" + text
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)
    return len(lines)


def read(path=LOG):
    """All decisions in the log, oldest first. Lines that are not JSON are skipped with a warning."""
    path = Path(path)
    if not path.is_file():
        return []
    out = []
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            out.append(json.loads(raw))
        except ValueError:
            print(f"{path.name}:{n}: not JSON, skipped", file=sys.stderr)
    return out


if __name__ == "__main__":
    for d in read():
        print(f"{d.get('when')}  {d.get('source'):<8} {d.get('decision'):<12} {d.get('pr_or_branch')}"
              f"{' ' + d['claim_id'] if d.get('claim_id') else ''}  {d.get('who')}")
