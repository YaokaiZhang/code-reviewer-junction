#!/usr/bin/env python3
"""PR stream cache: every upstream PR the backtest looks at, with its diff hunks, in date order,
so a chronological replay can run offline from committed data (no clone, no network).

    python3 review/scripts/pr_stream.py --repo <clone> [--fetch] [--write]   # build (needs the clone)
    python3 review/scripts/pr_stream.py --verify                             # check the cache (no clone)

Build:
  history   all 37 PRs in context/history.json (positives and non-positives). Diff exactly as
            backtest.py diffs positives: refs/pr/N (fetched from github.com with --fetch) against
            choose_base(...).
  control   the same 60 ordinary merged PRs backtest.py picks (pick_controls, same exclusions and
            years). Diff = <merge>^1..<merge>.
  Every hunk keeps file and start. Lines: the first MAX_LINES +/- lines of each of the first
  MAX_HUNKS hunks, each cut to MAX_LINE chars; beyond that only lines matching a baseline
  generalised line pattern are kept (uncut), so the baseline matcher is exact on the cache
  (`truncated: true` on the PR when anything was cut). `generalised_tripped` per PR is computed on
  the FULL hunks from the clone.
  details.generalised_rules caches backtest.Generalised(...).rules (derived from the base tree)
  so the matcher can be rebuilt without the clone (cached_generalised()).

Verify (--verify): rebuilds the Generalised matcher from the cache, re-runs it over the cached
(truncated) hunks only, and checks (a) every PR's tripped set equals the full-hunk
`generalised_tripped`, (b) for positives and controls it equals the generalised trips recorded in
evidence/backtest.json, (c) the headline counts (caught X of N positives, Y of M controls tripping
a promise) equal backtest.json's. Exit 1 on any difference.

Writes review/evidence/pr-stream.json. Standard library only.
"""
import argparse, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import backtest as bt  # noqa: E402
from backtest import (BASE, UPSTREAM, POSITIVE_CONCERNS, PROMISES, CONCERN_TO_CONTRACTS,  # noqa: E402
                      Generalised, choose_base, exists, git, hunks, pick_controls)

REVIEW = os.path.dirname(HERE)
OUT = os.path.join(REVIEW, "evidence", "pr-stream.json")
MAX_LINE, MAX_LINES, MAX_HUNKS = 200, 40, 400
CMD = "python3 review/scripts/pr_stream.py --repo $MP_REPO --fetch --write"


# ---------------------------------------------------------------- helpers the replay can import

def load_stream(path=OUT):
    return json.load(open(path, encoding="utf-8"))


def cached_generalised(stream, contracts=None):
    """backtest.Generalised rebuilt from the cached rules, without reading a clone."""
    if contracts is None:
        contracts = json.load(open(os.path.join(REVIEW, "context", "project.json")))["contracts"]
    g = Generalised.__new__(Generalised)
    g.contracts = contracts
    g.rules = stream["details"]["generalised_rules"]
    return g


def tripped(matcher, hunk_list):
    """Contract ids a matcher trips on any hunk of a PR (what backtest.run's keys are)."""
    out = set()
    for h in hunk_list:
        out |= set(matcher.trip(h))
    return sorted(out)


def headline(prs, trips_of):
    """(caught, positives evaluated, controls tripping a promise, controls) as backtest.score does."""
    pos = [p for p in prs if p["kind"] == "history" and p["positive"] and "error" not in p]
    ctl = [p for p in prs if p["kind"] == "control" and "error" not in p]
    caught = [p["pr"] for p in pos if set(trips_of(p)) & set(p["expected_contracts"])]
    noisy = [p["pr"] for p in ctl if set(trips_of(p)) & set(PROMISES)]
    return {"caught": len(caught), "positives_evaluated": len(pos),
            "controls_tripping_a_promise": len(noisy), "controls": len(ctl),
            "caught_prs": caught, "noisy_control_prs": noisy}


# ---------------------------------------------------------------- build

def cap(hs, patterns):
    """Cut a PR's hunks to size. Every hunk keeps file and start (path rules see the whole diff).
    Lines: the first MAX_LINES of each of the first MAX_HUNKS hunks, each cut to MAX_LINE chars;
    beyond that only lines that match a baseline generalised line pattern are kept, uncut, so the
    baseline matcher sees exactly what it saw on the full diff. Returns (hunks, truncated)."""
    pats = [re.compile(x) for x in patterns]
    hit = lambda l: any(x.search(l[1:]) for x in pats)
    out, trunc = [], False
    for i, h in enumerate(hs):
        keep = []
        for j, l in enumerate(h["lines"]):
            if i < MAX_HUNKS and j < MAX_LINES:
                if len(l) > MAX_LINE and not hit(l):
                    keep.append(l[:MAX_LINE])
                    trunc = True
                else:
                    keep.append(l)
            elif hit(l):
                keep.append(l)
                trunc = True
            else:
                trunc = True
        out.append({"file": h["file"], "start": h["start"], "lines": keep})
    return out, trunc


def build(R, fetch):
    ctx = json.load(open(os.path.join(REVIEW, "context", "project.json")))
    hist = json.load(open(os.path.join(REVIEW, "context", "history.json")))
    contracts = ctx["contracts"]
    gen = Generalised(contracts, R)
    excluded = {p["pr"] for p in hist["prs"]} | {int(x) for x in re.findall(r"#(\d{3,4})\b", json.dumps(hist))}

    prs = []
    for p in hist["prs"]:
        positive = p["concern"] in POSITIVE_CONCERNS
        ref = f"refs/pr/{p['pr']}"
        if not exists(R, ref) and fetch:
            git(R, "fetch", "-q", UPSTREAM, f"pull/{p['pr']}/head:{ref}", ok=True)
        row = {"pr": p["pr"], "date": p["date"], "title": p["title"], "kind": "history",
               "concern": p["concern"], "outcome": p["outcome"], "positive": positive,
               "expected_contracts": CONCERN_TO_CONTRACTS[p["concern"]] if positive else [],
               "url": p.get("url") or f"{UPSTREAM}/pull/{p['pr']}"}
        rc = (p.get("revert_commit") or "").split(" ")[0]
        if rc and exists(R, rc):
            d, who, subj = git(R, "log", "-1", "--date=short", "--format=%ad%x1f%an%x1f%s", rc).strip().split("\x1f")
            row["revert"] = {"commit": rc, "date": d, "author": who, "subject": subj}
        if not exists(R, ref):
            row["error"] = f"{ref} could not be fetched from {UPSTREAM}"
            prs.append(row)
            continue
        head = git(R, "rev-parse", ref).strip()
        mb, how = choose_base(R, head, p.get("merge_commit"))
        row.update({"head": head[:8], "merge_base": mb[:8], "diff": f"{mb[:8]}..{head[:8]}", "base_rule": how})
        prs.append(_diff(R, row, mb, head, gen))

    # controls: identical to backtest.main (years = years of all positive rows, errored or not)
    years = {p["date"][:4] for p in hist["prs"] if p["concern"] in POSITIVE_CONCERNS}
    picked, pool_sizes, quota, dropped = pick_controls(R, excluded, years)
    for c in picked:
        row = {"pr": c["pr"], "date": c["date"], "title": c["title"], "kind": "control",
               "concern": None, "outcome": "merged_clean", "positive": False, "expected_contracts": [],
               "url": f"{UPSTREAM}/pull/{c['pr']}", "merge": c["merge"], "branch": c["branch"],
               "diff": f"{c['merge']}^1..{c['merge']}", "base_rule": "first-parent diff of the merge commit"}
        prs.append(_diff(R, row, c["merge"] + "^1", c["merge"], gen))

    prs.sort(key=lambda r: (r["date"], r["pr"]))
    errors = [r["pr"] for r in prs if "error" in r]
    trunc = [r["pr"] for r in prs if r.get("truncated")]
    h = headline(prs, lambda r: r["generalised_tripped"])
    nh = sum(1 for r in prs if r["kind"] == "history")
    summary = (f"{len(prs)} PRs cached ({nh} history, {len(prs) - nh} controls; {len(errors)} without a fetchable ref, "
               f"{len(trunc)} truncated); generalised on full hunks: caught {h['caught']} of {h['positives_evaluated']} "
               f"positives, {h['controls_tripping_a_promise']} of {h['controls']} controls tripped a promise contract")
    return {
        "check": "pr-stream", "branch": None, "base": BASE, "command": CMD, "result": "pass",
        "summary": summary,
        "details": {
            "notes": [
                "history: all PRs in context/history.json; diff = refs/pr/N (final PR head, fetched from "
                f"{UPSTREAM} pull/N/head) against backtest.choose_base: " + " ".join(choose_base.__doc__.split()),
                "control: the exact PRs backtest.pick_controls picks (same exclusions, years and quotas); diff = <merge>^1..<merge>.",
                "date: history.json `date` (the merge or close date, not the PR open date); controls: merge date. Sorted by (date, pr).",
                "hunks: git diff -U0 --no-renames as backtest.hunks. Every hunk keeps file and start. Lines: the first "
                f"{MAX_LINES} +/- lines of each of the first {MAX_HUNKS} hunks, each cut to {MAX_LINE} chars; any other line is kept "
                "(uncut) only if it matches a baseline generalised line pattern, so the baseline matcher is exact on the cache. "
                "A NEW line pattern proposed later sees only the kept lines on a `truncated` PR. `n_hunks`/`n_files` count the full diff.",
                "generalised_tripped: backtest.Generalised trips over the FULL hunks; generalised_rules caches Generalised(...).rules so "
                "cached_generalised() rebuilds the matcher offline. --verify re-runs it over the cached hunks.",
                "positive: concern in backtest.POSITIVE_CONCERNS; expected_contracts = backtest.CONCERN_TO_CONTRACTS (empty for non-positives).",
                "revert: for history PRs with a revert_commit in history.json, that commit's author date, author and subject from the clone.",
                "outcome: history.json outcome for history PRs; 'merged_clean' for controls (merged, no recorded pushback).",
            ],
            "errors": errors,
            "truncated_prs": trunc,
            "headline_full_hunks": h,
            "controls_pool_per_year": pool_sizes, "controls_quota_per_year": quota, "controls_dropped": dropped,
            "limits": {"max_line_chars": MAX_LINE, "max_lines_per_hunk": MAX_LINES, "max_hunks_per_pr": MAX_HUNKS},
            "generalised_rules": gen.rules,
            "prs": prs,
        },
        "tool_versions": {"git": git(R, "--version").strip(), "python": sys.version.split()[0]},
        "produced_by": "script",
    }


def _diff(R, row, a, b, gen):
    full = list(hunks(R, a, b))
    kept, trunc = cap(full, sorted({x for r in gen.rules.values() for x in r["line_patterns"]}))
    row.update({"n_hunks": len(full), "n_files": len({h["file"] for h in full}),
                "generalised_tripped": tripped(gen, full), "truncated": trunc, "hunks": kept})
    return row


# ---------------------------------------------------------------- verify

def verify(path=OUT):
    s = load_stream(path)
    g = cached_generalised(s)
    prs = s["details"]["prs"]
    bj = json.load(open(os.path.join(REVIEW, "evidence", "backtest.json")))["details"]
    recorded = {("history", r["pr"]): sorted(r["trips"]["generalised"]) for r in bj["positives"] if "trips" in r}
    recorded |= {("control", r["pr"]): sorted(r["trips"]["generalised"]) for r in bj["controls"]}
    problems, cached = [], {}
    for p in prs:
        if "error" in p:
            continue
        t = tripped(g, p["hunks"])
        cached[(p["kind"], p["pr"])] = t
        if t != p["generalised_tripped"]:
            problems.append(f"{p['kind']} #{p['pr']}: cached hunks trip {t}, full hunks tripped {p['generalised_tripped']}")
        rec = recorded.get((p["kind"], p["pr"]))
        if rec is not None and t != rec:
            problems.append(f"{p['kind']} #{p['pr']}: cached hunks trip {t}, backtest.json recorded {rec}")
    missing = set(recorded) - set(cached)
    problems += [f"{k} #{n}: in backtest.json but not evaluable in the cache" for k, n in sorted(missing)]
    h = headline(prs, lambda p: cached[(p["kind"], p["pr"])])
    G = bj["generalised"]
    for k in ("caught", "positives_evaluated", "controls_tripping_a_promise", "controls"):
        if h[k] != G[k]:
            problems.append(f"{k}: cache {h[k]} vs backtest.json {G[k]}")
    line = (f"cache: caught {h['caught']} of {h['positives_evaluated']}, {h['controls_tripping_a_promise']} of "
            f"{h['controls']} controls tripped; backtest.json: caught {G['caught']} of {G['positives_evaluated']}, "
            f"{G['controls_tripping_a_promise']} of {G['controls']}")
    return not problems, line, problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.environ.get("MP_REPO"))
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--verify", action="store_true", help="check the committed cache offline (no clone)")
    a = ap.parse_args()
    if a.verify and not a.write:
        ok, line, problems = verify()
        print(("verify OK: " if ok else "verify FAILED: ") + line)
        for x in problems:
            print("  " + x)
        sys.exit(0 if ok else 1)
    if not a.repo:
        ap.error("--repo (or MP_REPO) is required to build")
    ev = build(a.repo, a.fetch)
    print(ev["summary"])
    for p in ev["details"]["prs"]:
        if "error" in p:
            print(f"  #{p['pr']}: {p['error']}")
    if a.write:
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(ev, f, ensure_ascii=False, separators=(",", ":"))
            f.write("\n")
        print(f"wrote {os.path.relpath(OUT)} ({os.path.getsize(OUT)} bytes)")
        if a.verify:
            ok, line, problems = verify()
            print(("verify OK: " if ok else "verify FAILED: ") + line)
            for x in problems:
                print("  " + x)
            sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
