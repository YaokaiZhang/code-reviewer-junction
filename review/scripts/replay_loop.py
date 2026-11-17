#!/usr/bin/env python3
"""Prequential replay of the learning loop over the cached PR stream, against the frozen baseline.

    python3 review/scripts/replay_loop.py [--write] [--from-git REV]

Stream: the 97 PRs of evidence/pr-stream.json (37 history incl. 16 positives, 60 controls), in order
(date, pr). For each PR, in order:
  1. predict with the current contract state: which contracts trip; routed = a promise contract trips
     (backtest.PROMISES; user-docs is not a promise); a positive is caught when a tripped contract is
     one of its expected contracts; a control is noise when it is routed.
  2. its decision (context/decisions.jsonl, history/control lines) becomes available at
     max(decision when, PR date) and is fed to the loop only before PRs dated strictly later
     (loop.py: event model). When decisions become available on day D the loop runs once with
     cutoff D: propose (widen + narrow) from every available decision, gate each on the PRs available
     on or before D, and accept every eligible proposal in order, re-gating each on the state left by
     the ones accepted before it ("approval": simulated: accept every eligible proposal).
Start state (k=0, the owner's choice): the 2025 baseline generalised contracts, which were written
after these PRs (a limit already listed in evidence/backtest.json). The frozen baseline arm runs the
same stream with no learning. Rule proposals (rule-off/-reword/new-rule) do not change contracts and
are not part of the replay; --llm is never used here. Deterministic: no clock, no randomness.

Writes review/evidence/feedback-loop.json.
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import loop  # noqa: E402
from backtest import PROMISES  # noqa: E402

OUT = os.path.join(loop.REVIEW, "evidence", "feedback-loop.json")
APPROVAL = "simulated: accept every eligible proposal"
GUARDS = ("min-positives", "declared-paths")
VARIANTS = [
    # name, kinds, choose, guards, post_hoc. The first is the headline. The first four were fixed before the
    # first run; the guarded ones were added after seeing it (details.tried).
    ("loop", loop.CONTRACT_KINDS, "specific", (), False),
    ("widen-only", ("widen-contract",), "specific", (), False),
    ("narrow-only", ("narrow-contract",), "specific", (), False),
    ("general-choice", loop.CONTRACT_KINDS, "general", (), False),
    ("guarded", loop.CONTRACT_KINDS, "specific", GUARDS, True),
    ("general-choice-guarded", loop.CONTRACT_KINDS, "general", GUARDS, True),
]


def outcome(r, trips):
    routed = bool(trips & set(PROMISES))
    o = {"routed": routed, "contracts": sorted(trips)}
    if r["kind"] == "history" and r["positive"]:
        o["caught"] = bool(trips & set(r["expected_contracts"]))
    elif r["kind"] == "control":
        o["noise"] = routed
    return o


def run_arm(rows, matcher, base, kinds=None, choose="specific", guards=()):
    """Returns (per-PR outcomes, overrides accepted, overrides-active count per PR)."""
    state = base
    accepted, preds, active = [], [], []
    feed = sorted(range(len(rows)), key=lambda i: (rows[i]["available"], i))
    ptr = 0
    for j, r in enumerate(rows):
        dates = []
        while ptr < len(feed) and rows[feed[ptr]]["available"] < r["date"]:
            d = rows[feed[ptr]]["available"]
            if not dates or dates[-1] != d:
                dates.append(d)
            ptr += 1
        if kinds:
            for T in dates:
                for p in loop.propose_contracts(matcher, state, rows, T, kinds, choose, guards):
                    if not p["gate"]["eligible"]:
                        continue
                    avail = [x for x in rows if x["available"] <= T and "error" not in x]
                    g = loop.gate(p, state, [x["decision"] for x in avail], avail, matcher, T, guards=guards)
                    if not g["eligible"]:
                        continue
                    o = loop.as_override(p, who=APPROVAL, when=T)
                    state = state.plus(o)
                    accepted.append({"proposal_id": p["id"], "kind": p["kind"], "contract": p["target"]["contract"],
                                     "change": {k: v for k, v in o.items() if k in ("add", "exclude")},
                                     "when": T, "accepted_before_pr_index": j,
                                     "triggered_by": p["triggered_by"], "gate": g, "why": p["why"]})
        trips = matcher.trips(state, r) if "error" not in r else frozenset()
        preds.append(outcome(r, trips))
        active.append(len(state.overrides))
    return preds, accepted, active, state


def totals(rows, preds, lo=0):
    pos = [i for i in range(lo, len(rows)) if rows[i]["kind"] == "history" and rows[i]["positive"]]
    ctl = [i for i in range(lo, len(rows)) if rows[i]["kind"] == "control"]
    oth = [i for i in range(lo, len(rows)) if rows[i]["kind"] == "history" and not rows[i]["positive"]]
    c = sum(preds[i]["caught"] for i in pos)
    n = sum(preds[i]["noise"] for i in ctl)
    o = sum(preds[i]["routed"] for i in oth)
    pct = lambda a, b: f"{a} of {b} ({round(100 * a / b)}%)" if b else f"{a} of {b}"
    return {"catches": c, "positives": len(pos), "noise": n, "controls": len(ctl),
            "routed_non_positives": o, "non_positives": len(oth),
            "caught_prs": [rows[i]["pr"] for i in pos if preds[i]["caught"]],
            "noisy_prs": [rows[i]["pr"] for i in ctl if preds[i]["noise"]],
            "routed_non_positive_prs": [rows[i]["pr"] for i in oth if preds[i]["routed"]],
            "text": {"catches": pct(c, len(pos)), "noise": pct(n, len(ctl)), "routed_non_positives": pct(o, len(oth))}}


def verdict(L, B):
    lc, ln, bc, bn = L["catches"], L["noise"], B["catches"], B["noise"]
    if (lc >= bc and ln < bn) or (lc > bc and ln <= bn):
        return f"beats baseline: {lc} vs {bc} catches, {ln} vs {bn} noise"
    if lc == bc and ln == bn:
        return f"same as baseline: {lc} catches, {ln} noise"
    part = lambda d, w: f"{abs(d)} {'fewer' if d < 0 else 'more'} {w}"
    bits = []
    if ln != bn:
        bits.append(part(ln - bn, "noise"))
    if lc != bc:
        bits.append(part(lc - bc, "catch" if abs(lc - bc) == 1 else "catches"))
    return (" but ".join(bits) if len(bits) == 2 else bits[0]) + f" than baseline ({lc} vs {bc} catches, {ln} vs {bn} noise)"


def attribute(rows, matcher, base_state, final_state, accepted, active):
    """For each accepted override: which later PRs' outcome it changed (leave-one-out at that PR's state)."""
    overrides = final_state.overrides
    out = []
    for k, a in enumerate(accepted):
        helped, hurt, unscored = [], [], []
        for j, r in enumerate(rows):
            if "error" in r or active[j] <= k:
                continue
            st = loop.State(base_state.contracts, base_state.base_rules, overrides[:active[j]])
            without = st.minus(a["proposal_id"])
            w, wo = outcome(r, matcher.trips(st, r)), outcome(r, matcher.trips(without, r))
            if w == wo:
                continue
            if "caught" in w and w["caught"] != wo["caught"]:
                (helped if w["caught"] else hurt).append(r["pr"])
            elif "noise" in w and w["noise"] != wo["noise"]:
                (hurt if w["noise"] else helped).append(r["pr"])
            elif w["routed"] != wo["routed"]:
                unscored.append({"pr": r["pr"], "routed": w["routed"]})
        out.append({**{x: a[x] for x in ("proposal_id", "kind", "contract", "change", "when", "accepted_before_pr_index", "triggered_by", "why")},
                    "gate": {x: a["gate"][x] for x in ("replayed_on", "before", "after", "helped", "regressions")},
                    "later_helped": helped, "later_hurt": hurt, "later_routing_changed_unscored": unscored})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--from-git", dest="rev")
    a = ap.parse_args()
    ctx = loop.load_context(a.rev, overrides=False)
    stream = loop.load_stream()
    rows = loop.build_events(stream, ctx["decisions"])
    base = loop.baseline_state(stream, ctx["project"])
    matcher = loop.Matcher([r for r in rows if "error" not in r])
    n = len(rows)
    half = n // 2

    b_preds, _, _, _ = run_arm(rows, matcher, base, None)
    arms = {}
    for name, kinds, choose, guards, _ in VARIANTS:
        arms[name] = run_arm(rows, matcher, base, kinds, choose, guards)

    L_preds, L_acc, L_active, L_final = arms["loop"][:4]
    TB, TL = totals(rows, b_preds), totals(rows, L_preds)
    HB, HL = totals(rows, b_preds, half), totals(rows, L_preds, half)
    v_full, v_half = verdict(TL, TB), verdict(HL, HB)

    per_pr, cum = [], {"x": [], "loop_catches": [], "loop_noise": [], "baseline_catches": [], "baseline_noise": []}
    cl = nl = cb = nb = 0
    for i, r in enumerate(rows):
        bp, lp = b_preds[i], L_preds[i]
        per_pr.append({"index": i, "pr": r["pr"], "date": r["date"], "kind": r["kind"], "positive": r["positive"],
                       "concern": r.get("concern"), "decision": r["decision"]["decision"],
                       "decision_available": r["available"],
                       "expected_contracts": r["expected_contracts"], "baseline": bp, "loop": lp,
                       "overrides_active": L_active[i]})
        cl += bool(lp.get("caught")); nl += bool(lp.get("noise"))
        cb += bool(bp.get("caught")); nb += bool(bp.get("noise"))
        cum["x"].append(i); cum["loop_catches"].append(cl); cum["loop_noise"].append(nl)
        cum["baseline_catches"].append(cb); cum["baseline_noise"].append(nb)

    variants = []
    for name, kinds, choose, guards, post_hoc in VARIANTS:
        preds, acc, active, final = arms[name]
        T, H = totals(rows, preds), totals(rows, preds, half)
        variants.append({"name": name, "kinds": list(kinds), "choose": choose, "guards": list(guards),
                         "added_after_seeing_results": post_hoc,
                         "overrides_accepted": len(acc), "full": {k: T[k] for k in ("catches", "positives", "noise", "controls", "routed_non_positives", "non_positives")},
                         "later_half": {k: H[k] for k in ("catches", "positives", "noise", "controls", "routed_non_positives", "non_positives")},
                         "verdict_full": verdict(T, TB), "verdict_later_half": verdict(H, HB),
                         "accepted": [{"proposal_id": x["proposal_id"], "kind": x["kind"], "contract": x["contract"],
                                       "change": x["change"], "when": x["when"]} for x in acc]})

    acc_detail = attribute(rows, matcher, base, L_final, L_acc, L_active)
    reverts_early = [{"pr": r["pr"], "decision_when": r["decision"]["when"], "pr_date": r["date"], "available": r["available"]}
                     for r in rows if r["decision"]["when"] < r["date"]]
    summary = (f"Replay over {n} PRs with simulated approvals: loop caught {TL['catches']} of {TL['positives']} positives "
               f"(baseline {TB['catches']}), noise {TL['noise']} of {TL['controls']} controls (baseline {TB['noise']}), "
               f"routed {TL['routed_non_positives']} of {TL['non_positives']} non-positives (baseline {TB['routed_non_positives']}); "
               f"later half (PR index {half}-{n - 1}): loop {HL['catches']} of {HL['positives']} catches, {HL['noise']} of "
               f"{HL['controls']} noise vs baseline {HB['catches']} and {HB['noise']}; {len(L_acc)} overrides accepted. "
               f"Verdict: {v_full}.")
    ev = {
        "check": "feedback-loop",
        "branch": None,
        "base": stream.get("base"),
        "command": "python3 review/scripts/replay_loop.py" + (f" --from-git {a.rev}" if a.rev else "") + " --write",
        "result": "pass",
        "summary": summary,
        "details": {
            "approval": APPROVAL,
            "verdict": v_full,
            "verdict_later_half": v_half,
            "totals": {"loop": TL, "baseline": TB},
            "later_half": {"from_index": half, "to_index": n - 1, "loop": HL, "baseline": HB},
            "accepted_overrides": acc_detail,
            "variants": variants,
            "tried": [
                {"change": "first run (pre-declared): learner parameters (candidate features, TOKENS_PER_PR=5, token rule, narrow "
                           "candidate shapes, 'most specific' choice, gate exactly as specified) and the variants loop, widen-only, "
                           "narrow-only, general-choice were fixed before any replay run. The headline stays this pre-declared loop.",
                 "result": v_full},
                {"change": "after seeing the first run: added optional gate guards (loop.GUARDS) as two extra variants, not as the "
                           "default. Why: in the first run, on 2019-06-10, before any positive had been decided, the gate accepted "
                           "excluding path prefix src/MessagePack/ from wire-format ('caught must not drop' is vacuous with no "
                           "positives), which later lost #2139; and general-choice reached its low noise by excluding the contracts' "
                           "own declared paths (e.g. src/MessagePack.SourceGenerator/Transforms/ from generated). Guards: "
                           + "; ".join(f"{k}: {v}" for k, v in loop.GUARDS.items()) + ".",
                 "result": "first version of the guards (prefixes and segments only): guarded 12 vs 10 catches, 31 vs 33 noise; "
                           "general-choice-guarded 12 vs 10 catches, 26 vs 33 noise"},
                {"change": "after reviewing the live proposals list (propose.py, guards on by default there): declared-paths widened "
                           "to also block excluding the file name of a declared file (it offered excluding MessagePackReader.cs and "
                           "MessagePackWriter.cs from wire-format) and the files a contract's `sources` cite (it offered excluding "
                           "src/MessagePack/MessagePack.csproj, the file that declares the targets, from targets).",
                 "result": "; ".join(f"{v['name']}: {v['verdict_full']}" for v in variants if v["added_after_seeing_results"])},
            ],
            "cumulative": cum,
            "per_pr": per_pr,
            "method": {
                "stream": "evidence/pr-stream.json prs sorted by (date, pr); date = history.json date (merge/close date, not the open date) or control merge date.",
                "start_state": "k=0: the 2025 baseline generalised contracts (pr-stream.json details.generalised_rules + project.json paths).",
                "decision_availability": "max(decision when, PR date); fed to the loop only before PRs dated strictly later than that day, so a PR never sees its own decision and same-day PRs never see each other's.",
                "decisions_with_when_before_pr_date": reverts_early,
                "learning_step": "for each day D on which decisions become available: loop.propose_contracts(cutoff=D) over all available decisions, each proposal gated (loop.gate) on the PRs available on or before D; every eligible proposal accepted in order (widen first, then narrow, stream order of trigger), re-gated on the state after the earlier acceptances.",
                "routed": "a promise contract (" + ", ".join(PROMISES) + ") trips; user-docs is not a promise.",
                "caught": "positive (concern in backtest.POSITIVE_CONCERNS) with a tripped contract in its expected_contracts.",
                "noise": "control routed.",
                "non_positives": "history PRs whose concern is not a promise (maintainability, performance, scope, ...): not scored as catches or noise; how many are routed is reported separately.",
                "not_used": "rule_ids_cited (rules mined from these same PRs: leakage); rule proposals; --llm.",
                "attribution": "accepted_overrides[].later_*: for each later PR, the outcome with the state active at that PR vs the same state without that override.",
            },
            "limits": [
                "Small stream: 16 positives (6 missed by the baseline) and 60 controls; one PR is about 6 points of catch rate and under 2 points of noise rate.",
                "The 2025 contracts were written after these PRs (k=0 start state); the baseline already benefits from hindsight (limit listed in evidence/backtest.json).",
                "Approval is simulated: every eligible proposal is accepted. A real owner may reject some; the replay shows what the gate alone allows.",
                "The gate only sees PRs decided before the cutoff; a feature that passes on a few past PRs can still add noise on later ones (see accepted_overrides[].later_hurt).",
                "Positive labels and expected contracts come from history.json concern labels (hand, from maintainer comments); a wrong label moves a PR between caught and missed.",
                "Line-pattern candidates see only cached lines: on the PRs marked truncated in pr-stream.json, lines beyond the cap are kept only if they match a baseline pattern.",
                "Controls carry no recorded pushback but history.json came from targeted searches; some controls may have had review pushback we could not see, so noise is an upper bound.",
                "date is the merge/close date, so a PR can be predicted after discussions that, in reality, happened earlier; the open date is not in the cache.",
            ],
        },
        "tool_versions": {"python": sys.version.split()[0]},
        "produced_by": "script",
    }
    print(summary)
    print(f"later half verdict: {v_half}")
    for v in variants:
        print(f"  {v['name']:15} accepted {v['overrides_accepted']:2}  full {v['full']['catches']}/{v['full']['positives']} "
              f"noise {v['full']['noise']}/{v['full']['controls']} other {v['full']['routed_non_positives']}/{v['full']['non_positives']}  "
              f"half {v['later_half']['catches']}/{v['later_half']['positives']} noise {v['later_half']['noise']}/{v['later_half']['controls']}  | {v['verdict_full']}")
    for x in acc_detail:
        print(f"  {x['when']} {x['proposal_id']} {x['kind']} {x['contract']} {json.dumps(x['change'])} "
              f"trig={[t['pr_or_branch'] for t in x['triggered_by']]} helped={x['later_helped']} hurt={x['later_hurt']}")
    if a.write:
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(ev, f, indent=1, ensure_ascii=False)
            f.write("\n")
        print(f"wrote {os.path.relpath(OUT)}")


if __name__ == "__main__":
    main()
