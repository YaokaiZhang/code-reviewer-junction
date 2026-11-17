#!/usr/bin/env python3
"""Decision log: review/context/decisions.jsonl, one JSON object per line, append-only for receipts.

    python3 review/scripts/build_decisions.py            # dry run: print what would be written
    python3 review/scripts/build_decisions.py --write

Line schema (shared with the receipt writer):
  {"source": "receipt"|"history"|"control", "pr_or_branch": "2013"|"ju26-issue-2283",
   "claim_id": null|"C-2283-03", "rule_ids_cited": [...], "contracts_tripped": [...],
   "decision": "accept"|"reject"|"send_back"|"reverted"|"pushed_back"|"merged_clean",
   "reason": "...", "who": "...", "when": "YYYY-MM-DD", "url": null|"https://..."}

Reads only committed data: context/history.json, evidence/pr-stream.json (pr_stream.py),
receipts/*.json, evidence/<branch>/confidence.json. No clone, no network.

Rebuild rule: history and control lines are regenerated deterministically (sorted by when, then
source, then PR number) and written first. Existing `source: "receipt"` lines are kept verbatim
and in order at the end; a receipt pick not yet in the log is appended after them.

History PRs (one line each). history.json `date` is the merge/close date, not the open date.
A statement whose URL is the PR's own description (`/pull/<n>#issue-...`) is the author speaking,
not a maintainer reacting, and is never used as the objection.
  outcome reverted
      decision "reverted". when = revert commit date (pr-stream.json `revert`, from the clone's
      revert_commit) if recorded, else the latest statement date (else PR date). who/reason/url =
      the statement dated on the revert date if there is one, else the revert commit's author and
      subject with the upstream commit URL.
  outcome closed-unmerged, merged-after-changes
      decision "pushed_back".
  outcome merged (with a concern)
      "pushed_back" only if some statement is not the PR description (a maintainer reacted);
      otherwise "merged_clean". In the data the one such PR, #2139, has only statements from its
      own description (the author, neuecc, flags the break and the chosen mitigation), so it is
      "merged_clean".
  pushed_back: when = earliest non-description statement dated on/after the PR date, falling back
      to the PR date; who/reason/url = that statement, or, on fallback, the earliest
      non-description statement (the first objection on record).
  rule_ids_cited = history.json rules (turned-off ones included: this is provenance) with a
      `sources` URL containing /pull/<n> (not followed by a digit) or equal to one of the PR's
      statement URLs (e.g. issues/2040 for #2013, pull/1679 for #1678).
  contracts_tripped = pr-stream.json `generalised_tripped` (baseline generalised matcher, all
      contracts incl. user-docs).
Controls (one line each): decision "merged_clean", who null, reason "nobody objected ...",
  when = merge date, url = upstream PR, contracts_tripped as above, rule_ids_cited [].
Receipts (review/receipts/*.json, `sample: true` receipts skipped): one line per pick;
  accept/reject/"send back"->send_back; who = signed_by; when = signed_at date; claim_id = pick id;
  contracts_tripped / rule_ids_cited from that claim's gate in evidence/<branch>/confidence.json.
"""
import argparse, glob, json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
REVIEW = os.path.dirname(HERE)
OUT = os.path.join(REVIEW, "context", "decisions.jsonl")
UPSTREAM = "https://github.com/MessagePack-CSharp/MessagePack-CSharp"
KEYS = ["source", "pr_or_branch", "claim_id", "rule_ids_cited", "contracts_tripped",
        "decision", "reason", "who", "when", "url"]
PICK = {"accept": "accept", "reject": "reject", "send back": "send_back", "send_back": "send_back"}


def line(**kw):
    return {k: kw[k] for k in KEYS}


def short(q, n=200):
    q = " ".join(q.split())
    return q if len(q) <= n else q[:n - 1].rstrip() + "…"


def is_description(st, pr):
    return re.search(rf"/pull/{pr}#issue-", st["url"]) is not None


def history_line(p, row, rules):
    n, date = p["pr"], p["date"]
    sts = sorted(p["statements"], key=lambda s: s["date"])  # stable: keeps file order within a day
    reacts = [s for s in sts if not is_description(s, n)]
    oc = p["outcome"]
    if oc == "reverted":
        decision = "reverted"
        rv = row.get("revert")
        when = rv["date"] if rv else (sts[-1]["date"] if sts else date)
        st = next((s for s in sts if s["date"] == when), None)
        if st:
            who, reason, url = st["who"], short(st["quote"]), st["url"]
        elif rv:
            who, reason, url = rv["author"], short(rv["subject"]), f"{UPSTREAM}/commit/{rv['commit']}"
        else:
            st = sts[-1]
            who, reason, url = st["who"], short(st["quote"]), st["url"]
    else:
        if oc in ("closed-unmerged", "merged-after-changes"):
            decision = "pushed_back"
        elif oc == "merged":
            decision = "pushed_back" if reacts else "merged_clean"
        else:
            raise SystemExit(f"#{n}: unmapped outcome {oc!r}")
        if decision == "pushed_back":
            after = [s for s in reacts if s["date"] >= date]
            st = after[0] if after else reacts[0]
            when = after[0]["date"] if after else date
        else:
            st, when = (sts[0] if sts else None), date
        who = st["who"] if st else None
        reason = short(st["quote"]) if st else ""
        url = st["url"] if st else p.get("url")
        if decision == "merged_clean":
            reason = "merged; no maintainer objection on record (only the PR description): " + reason
    urls = {s["url"] for s in p["statements"]}
    pat = re.compile(rf"/pull/{n}(?!\d)")
    cited = sorted(r["id"] for r in rules if any(pat.search(u) or u in urls for u in r.get("sources", [])))
    return line(source="history", pr_or_branch=str(n), claim_id=None, rule_ids_cited=cited,
                contracts_tripped=row.get("generalised_tripped", []), decision=decision,
                reason=reason, who=who, when=when, url=url)


def receipt_lines():
    out = []
    for f in sorted(glob.glob(os.path.join(REVIEW, "receipts", "*.json"))):
        r = json.load(open(f, encoding="utf-8"))
        if r.get("sample") or os.path.basename(f).startswith("_"):
            continue
        br = r.get("branch")
        cp = os.path.join(REVIEW, "evidence", str(br), "confidence.json")
        conf = json.load(open(cp))["details"]["claims"] if os.path.isfile(cp) else {}
        for pk in r.get("picks", []):
            g = (conf.get(pk["id"]) or {}).get("gate") or {}
            rules = sorted({x if isinstance(x, str) else x.get("id") for x in g.get("rules", [])} - {None})
            out.append(line(source="receipt", pr_or_branch=br, claim_id=pk["id"], rule_ids_cited=rules,
                            contracts_tripped=[g["contract"]] if g.get("contract") else [],
                            decision=PICK[pk["pick"].lower()], reason=short(pk.get("claim", "")),
                            who=r.get("signed_by"), when=(r.get("signed_at") or "")[:10], url=None))
    return out


def build():
    hist = json.load(open(os.path.join(REVIEW, "context", "history.json"), encoding="utf-8"))
    stream = json.load(open(os.path.join(REVIEW, "evidence", "pr-stream.json"), encoding="utf-8"))
    rows = {(r["kind"], r["pr"]): r for r in stream["details"]["prs"]}
    lines = []
    for p in hist["prs"]:
        lines.append(history_line(p, rows.get(("history", p["pr"]), {}), hist["rules"]))
    for (kind, n), r in rows.items():
        if kind != "control":
            continue
        lines.append(line(source="control", pr_or_branch=str(n), claim_id=None, rule_ids_cited=[],
                          contracts_tripped=r.get("generalised_tripped", []), decision="merged_clean",
                          reason="nobody objected: merged with no pushback recorded in history.json",
                          who=None, when=r["date"], url=r["url"]))
    lines.sort(key=lambda d: (d["when"], d["source"], int(d["pr_or_branch"])))
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    backfill = build()

    kept_raw, kept = [], []
    if os.path.isfile(OUT):
        for raw in open(OUT, encoding="utf-8"):
            raw = raw.rstrip("\n")
            if raw.strip() and json.loads(raw).get("source") == "receipt":
                kept_raw.append(raw)
                kept.append(json.loads(raw))
    key = lambda d: (d.get("pr_or_branch"), d.get("claim_id"), d.get("decision"), d.get("who"), d.get("when"))
    have = {key(d) for d in kept}
    new = [d for d in receipt_lines() if key(d) not in have]

    text = "".join(json.dumps(d, ensure_ascii=False) + "\n" for d in backfill)
    text += "".join(r + "\n" for r in kept_raw)
    text += "".join(json.dumps(d, ensure_ascii=False) + "\n" for d in new)
    from collections import Counter
    c = Counter((d["source"], d["decision"]) for d in backfill + kept + new)
    print(f"{len(backfill)} backfill lines, {len(kept)} receipt lines kept, {len(new)} receipt lines added")
    for k, v in sorted(c.items()):
        print(f"  {k[0]:8} {k[1]:13} {v}")
    if a.write:
        with open(OUT, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {os.path.relpath(OUT)}")


if __name__ == "__main__":
    main()
