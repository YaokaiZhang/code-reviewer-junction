#!/usr/bin/env python3
"""Proposals for the Rules page: learned contract and rule changes, each behind an evidence gate.

    python3 review/scripts/propose.py [--cutoff YYYY-MM-DD] [--llm] [--write] [--from-git REV]

Reads context/decisions.jsonl (decisions available on or before --cutoff; default: the latest
decision), the accepted overrides in context/contract_overrides.json, the active rules in
context/history.json, and the cached PR stream (evidence/pr-stream.json). Writes
context/proposals.json. Generators, gate and choice rules: see loop.py's docstring.

--from-git REV  read the context files (decisions, history, overrides, existing proposals) as committed
                at REV instead of the working tree, e.g. while uncommitted test data sits there.
--no-guards     gate without loop.GUARDS. By default the guards are on here (the live list a person decides on);
                the replay's headline arm runs without them, and its guarded variants with them.
--llm           phrase new-rule / rule-reword text with the Messages API (needs LLM_KEY or ANTHROPIC_API_KEY;
                otherwise prints a note and keeps the script draft). The verbatim quote and URL stay in `why`.

Ids are "P-" + 6 hex of sha1(kind, target, change), so a re-run gives the same id to the same change.
Proposals already accepted or rejected in the existing file are kept verbatim (status, decided);
open ones are regenerated. At most CAP open proposals per kind are written (eligible first, then
stream order); the number dropped is recorded in `dropped_by_cap`.
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import loop  # noqa: E402

OUT = os.path.join(loop.REVIEW, "context", "proposals.json")
CAP = 10
KINDS = ("widen-contract", "narrow-contract", "rule-off", "rule-reword", "new-rule")


def build(cutoff=None, use_llm=False, rev=None, command=None, guards=tuple(loop.GUARDS)):
    ctx = loop.load_context(rev)
    stream = loop.load_stream()
    rows = loop.build_events(stream, ctx["decisions"])
    cutoff = cutoff or max([r["available"] for r in rows] +
                           [d["when"] for d in ctx["decisions"] if d.get("source") == "receipt"])
    state = loop.State(ctx["project"]["contracts"], stream["details"]["generalised_rules"], ctx["overrides"])
    avail = [r for r in rows if r["available"] <= cutoff and "error" not in r]
    m = loop.Matcher(avail)
    props = loop.propose_contracts(m, state, rows, cutoff, guards=guards)
    props += loop.propose_rules(ctx["history"], ctx["decisions"], cutoff, use_llm=use_llm)

    old = (ctx["proposals"] or {}).get("proposals") or []
    decided = {p["id"]: p for p in old if p.get("status", "open") != "open"}
    fresh, dropped = [], {}
    per = {k: 0 for k in KINDS}
    for k in KINDS:
        ks = [p for p in props if p["kind"] == k and p["id"] not in decided]
        ks.sort(key=lambda p: not p["gate"]["eligible"])  # stable: keeps stream order within each group
        for p in ks:
            if per[k] < CAP:
                fresh.append(p)
                per[k] += 1
            else:
                dropped[k] = dropped.get(k, 0) + 1
    out_props = []
    for p in fresh:
        q = {x: p[x] for x in ("id", "kind", "target", "change", "why", "triggered_by", "gate", "drafted_by", "status")}
        out_props.append(q)
    out_props += [decided[i] for i in sorted(decided)]
    gen = {k: sum(1 for p in props if p["kind"] == k) for k in KINDS}
    elig = {k: sum(1 for p in props if p["kind"] == k and p["gate"]["eligible"]) for k in KINDS}
    receipts = sum(1 for d in ctx["decisions"] if d.get("source") == "receipt" and d["when"] <= cutoff)
    doc = {
        "check": "proposals",
        "command": command or "python3 review/scripts/propose.py --write",
        "produced_by": "script",
        "cutoff": cutoff,
        "proposals": out_props,
        "generated_per_kind": gen,
        "eligible_per_kind": elig,
        "dropped_by_cap": {"cap_per_kind": CAP, "dropped": dropped},
        "notes": [
            f"Decisions available on or before {cutoff}: {len(avail)} PR decisions (history + control) and {receipts} owner receipt decisions"
            + (f"; context read from git {rev}" if rev else "") + ".",
            f"Contract state: baseline generalised contracts + {len(ctx['overrides'])} accepted override(s) from context/contract_overrides.json.",
            "Contract proposals (widen/narrow) are replayed on the decided PRs (gate_kind replay); rule proposals have no replay "
            "ground truth and are checked for citations only (gate_kind citation-only).",
            "rule-off / rule-reword need >= 2 owner receipt decisions citing one rule"
            + ("; there are none yet, so none are proposed." if not receipts else "."),
            "Line-pattern candidates see only the cached lines: on PRs marked truncated in evidence/pr-stream.json, lines beyond "
            "the cap are kept only if they match a baseline pattern, so a new pattern can be under-counted there.",
            ("Guards on (default): " + "; ".join(f"{k}: {loop.GUARDS[k]}" for k in guards) + ". They stop a proposal that would blind a contract's own declared files."
             if guards else "Guards off (--no-guards)."),
            "rule_ids_cited is never used to propose or gate a contract change (those rules were mined from the same PRs).",
        ],
    }
    return doc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cutoff")
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--from-git", dest="rev")
    ap.add_argument("--no-guards", action="store_true", help="gate without loop.GUARDS (the replay's pre-declared headline gate)")
    a = ap.parse_args()
    if a.llm and not (os.environ.get("LLM_KEY") or os.environ.get("ANTHROPIC_API_KEY")):
        print("note: --llm needs LLM_KEY or ANTHROPIC_API_KEY; using the script drafts (drafted_by script)", file=sys.stderr)
    cmd = "python3 review/scripts/propose.py" + (f" --cutoff {a.cutoff}" if a.cutoff else "") + \
          (" --llm" if a.llm else "") + (f" --from-git {a.rev}" if a.rev else "") + (" --no-guards" if a.no_guards else "") + " --write"
    doc = build(a.cutoff, a.llm, a.rev, cmd, guards=() if a.no_guards else tuple(loop.GUARDS))
    for p in doc["proposals"]:
        g = p["gate"]
        tag = "ELIGIBLE" if g.get("eligible") else "no"
        print(f"{p['id']} {p['kind']:15} {json.dumps(p['target'])} {tag:8} {g.get('gate_kind')} "
              f"{json.dumps(g.get('before'))} -> {json.dumps(g.get('after'))} {g.get('reason', '')[:90]}")
    print(f"generated {doc['generated_per_kind']}; eligible {doc['eligible_per_kind']}; dropped {doc['dropped_by_cap']['dropped']}")
    if a.write:
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"wrote {os.path.relpath(OUT)}")


if __name__ == "__main__":
    main()
