#!/usr/bin/env python3
"""Learning loop: owner-gate contracts that learn from maintainer and owner decisions, behind a replay gate.

Shared by propose.py (proposals for the Rules page) and replay_loop.py (prequential replay).

    python3 review/scripts/loop.py --self-test     # matcher with no overrides == backtest headline (10/16, 33/60)

Contract state
  baseline = backtest.Generalised rules cached in evidence/pr-stream.json (details.generalised_rules)
             plus the contracts' exact `paths` from context/project.json.
  overrides = accepted proposals, each {"proposal_id", "contract", "add" | "exclude", "who", "when"}:
     add      {dir_segments, file_names, line_patterns}  unioned into the contract's generalised rule
     exclude  {dir_segments, file_names, path_prefixes}  a hunk whose file has an excluded directory
              segment, file name, or path prefix cannot trip that contract by path-segment, file-name
              or line; an exact contract `path` match is blocked only by path_prefixes.
  With no overrides State.trip() is backtest.Generalised.trip() exactly (--self-test asserts it on every
  cached PR and on the headline counts).
  Overrides are read from context/contract_overrides.json only when a caller asks (load_overrides);
  tripwires.py and the dossiers never read them.

What is learned
  Only owner-gate CONTRACTS are scored (the owner decided: contracts first). history.json
  `rule_ids_cited` comes from rules mined from these same PRs, so it is never used to predict.
  Proposal kinds:
    widen-contract   a positive PR (promise concern) that maintainers pushed back on or reverted, whose
                     expected contract did not trip. Candidates: one feature from its PRODUCT hunks
                     (backtest.product): a directory segment, a file name, or a line pattern \\bToken\\b for
                     one of up to TOKENS_PER_PR identifier tokens (PascalCase, >= 2 humps, >= 8 chars,
                     the most frequent in its changed lines). Each candidate adds that one feature to one
                     of the PR's expected contracts.
    narrow-contract  a control (merged clean, nobody objected) that trips a promise contract C.
                     Candidates (each must cover every hunk that trips C on that control): the file
                     name(s) of those hunks (up to 5), their longest common directory prefix, the single
                     file path as a prefix, or the contract directory segment that caused every trip.
    rule-off         a rule cited on >= 2 owner receipt decisions that ACCEPTED the claim anyway.
    rule-reword      a rule cited on >= 2 owner receipt decisions that rejected / sent back the claim.
    new-rule         a maintainer statement in a pushed-back/reverted PR whose concern no active rule of
                     that concern covers (no active rule of the concern cites the statement URL or the PR).
  Rule kinds have no replay ground truth: their gate is a citation check only (gate_kind citation-only).

Gate (contract kinds, gate_kind replay): replay the state with and without the change on the PRs whose
decision is available on or before the cutoff. Eligible iff it helps at least one triggering decision
(widen: the trigger becomes caught; narrow: the trigger control stops tripping any promise contract) and
nothing regresses: no positive newly missed, no control newly noisy for widen (noise must not rise at
all), and for narrow noise must go down and caught must not drop.

Choice among eligible candidates for one trigger (fixed before any replay was run): the most specific,
i.e. the fewest available PRs the feature matches, then kind (file name, line pattern, directory
segment for widen; path prefix, file name, directory segment for narrow), then the longer value, then
lexicographic. choose="general" (a replay_loop variant) takes the most general instead.

Event model (replay and cutoffs): a PR is predicted at its history.json/merge `date` (the merge or close
date; the open date is not recorded). Its decision becomes available at max(decision when, PR date) and
only to predictions on a strictly later date: a decision available on day D is fed to the loop after
every PR dated <= D has been predicted. Same-day PRs therefore never see each other's decisions.
"""
import argparse, hashlib, json, os, posixpath, re, subprocess, sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from backtest import PROMISES, product, under  # noqa: E402

REVIEW = os.path.dirname(HERE)
ROOT = os.path.dirname(REVIEW)
STREAM = os.path.join(REVIEW, "evidence", "pr-stream.json")
CTX = {"project": "context/project.json", "history": "context/history.json",
       "decisions": "context/decisions.jsonl", "overrides": "context/contract_overrides.json",
       "proposals": "context/proposals.json"}
ADD_KEYS = ("dir_segments", "file_names", "line_patterns")
EXCL_KEYS = ("dir_segments", "file_names", "path_prefixes")
TOKENS_PER_PR = 5
TOKEN = re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+\b")
MIN_QUOTE_WORDS = 6
CONTRACT_KINDS = ("widen-contract", "narrow-contract")
RULE_KINDS = ("rule-off", "rule-reword", "new-rule")
MISS_DECISIONS = ("pushed_back", "reverted")
LLM_MODEL = "claude-sonnet-5-5"


# ---------------------------------------------------------------- context

def read_ctx(name, rev=None):
    """Text of a review/context file, from the working tree or from git `rev` (None if absent)."""
    rel = CTX[name]
    if rev:
        r = subprocess.run(["git", "-C", ROOT, "show", f"{rev}:review/{rel}"], capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else None
    p = os.path.join(REVIEW, rel)
    return open(p, encoding="utf-8").read() if os.path.exists(p) else None


def load_context(rev=None, overrides=True):
    j = lambda n: (json.loads(t) if (t := read_ctx(n, rev)) else None)
    dec_text = read_ctx("decisions", rev) or ""
    return {"project": j("project"), "history": j("history"),
            "decisions": [json.loads(x) for x in dec_text.splitlines() if x.strip()],
            "overrides": load_overrides(rev) if overrides else [],
            "proposals": j("proposals"), "rev": rev}


def load_overrides(rev=None):
    """Accepted contract overrides from context/contract_overrides.json (empty when absent)."""
    t = read_ctx("overrides", rev)
    return list((json.loads(t) or {}).get("overrides") or []) if t else []


def load_stream():
    return json.load(open(STREAM, encoding="utf-8"))


# ---------------------------------------------------------------- matcher

_RX = {}


def rx(p):
    if p not in _RX:
        _RX[p] = re.compile(p)
    return _RX[p]


def prep_hunks(hunks):
    """Hunks as tuples the matcher reads fast: (file, dirs, basename, is_product, lines)."""
    return [(h["file"], tuple(h["file"].split("/")[:-1]), posixpath.basename(h["file"]), product(h["file"]), h["lines"])
            for h in hunks]


class State:
    """Contracts = baseline generalised rules + overrides, applied in order."""

    def __init__(self, contracts, base_rules, overrides=()):
        self.contracts = contracts
        self.base_rules = base_rules
        self.overrides = list(overrides)
        self.ids = [c["id"] for c in contracts]
        self.rule = {}
        for c in contracts:
            b = base_rules[c["id"]]
            r = {"paths": tuple(c["paths"]), "segs": set(b["dir_segments"]), "names": set(b["file_names"]),
                 "pats": list(b["line_patterns"]), "xsegs": set(), "xnames": set(), "xpre": set()}
            self.rule[c["id"]] = r
        for o in self.overrides:
            r = self.rule.get(o["contract"])
            if r is None:
                raise ValueError(f"override {o.get('proposal_id')}: no contract {o['contract']!r}")
            a, x = o.get("add") or {}, o.get("exclude") or {}
            r["segs"] |= set(a.get("dir_segments", []))
            r["names"] |= set(a.get("file_names", []))
            r["pats"] += [p for p in a.get("line_patterns", []) if p not in r["pats"]]
            r["xsegs"] |= set(x.get("dir_segments", []))
            r["xnames"] |= set(x.get("file_names", []))
            r["xpre"] |= set(x.get("path_prefixes", []))
        self.sigs = {cid: json.dumps([sorted(r["segs"]), sorted(r["names"]), r["pats"], sorted(r["xsegs"]),
                                      sorted(r["xnames"]), sorted(r["xpre"])]) for cid, r in self.rule.items()}

    def plus(self, override):
        return State(self.contracts, self.base_rules, self.overrides + [override])

    def minus(self, proposal_id):
        return State(self.contracts, self.base_rules, [o for o in self.overrides if o.get("proposal_id") != proposal_id])

    def excluded(self, cid, h):
        r = self.rule[cid]
        f, dirs, base = h[0], h[1], h[2]
        return (any(f.startswith(p) for p in r["xpre"]), any(d in r["xsegs"] for d in dirs) or base in r["xnames"])

    def trip_one(self, cid, h):
        """Why hunk h trips contract cid (backtest.Generalised.trip semantics + excludes), or None."""
        r = self.rule[cid]
        f, dirs, base, prod, lines = h
        xpre = bool(r["xpre"]) and any(f.startswith(p) for p in r["xpre"])
        if under(f, r["paths"]):
            return None if xpre else "path"
        if not prod or xpre or (r["xsegs"] and any(d in r["xsegs"] for d in dirs)) or base in r["xnames"]:
            return None
        if any(d in r["segs"] for d in dirs):
            return "path-segment"
        if base in r["names"]:
            return "file-name"
        for pat in r["pats"]:
            p = rx(pat)
            hit = next((l for l in lines if p.search(l[1:])), None)
            if hit:
                return "line: " + hit[:100].rstrip()
        return None

    def trip(self, h):
        """dict contract -> reason for one prepped hunk, as backtest.Generalised.trip returns."""
        out = {}
        for cid in self.ids:
            w = self.trip_one(cid, h)
            if w:
                out[cid] = w
        return out


class Matcher:
    """Per-PR tripped sets with a cache keyed by (PR, contract, contract rule signature)."""

    def __init__(self, prs):
        self.prs = prs
        self.hunks = {key(p): prep_hunks(p.get("hunks", [])) for p in prs}
        self.cache = {}
        self.fcache = {}

    def spread(self, prs, spec, product_only):
        """How many of prs have a hunk matching any feature of spec (the specificity measure)."""
        sj = json.dumps(spec, sort_keys=True)
        n = 0
        for p in prs:
            k = (key(p), sj, product_only)
            v = self.fcache.get(k)
            if v is None:
                v = any((h[3] or not product_only) and any(feature_matches(h, kk, x) for kk, vs in spec.items() for x in vs)
                        for h in self.hunks[key(p)])
                self.fcache[k] = v
            n += v
        return n

    def trips_c(self, state, p, cid):
        k = (key(p), cid, state.sigs[cid])
        v = self.cache.get(k)
        if v is None:
            v = any(state.trip_one(cid, h) for h in self.hunks[key(p)])
            self.cache[k] = v
        return v

    def trips(self, state, p):
        return frozenset(c for c in state.ids if self.trips_c(state, p, c))

    def causes(self, state, p, cid):
        """Hunks of p that trip cid, with the reason."""
        return [(h, w) for h in self.hunks[key(p)] if (w := state.trip_one(cid, h))]


def key(p):
    return f"{p['kind']}:{p['pr']}"


def score(matcher, state, prs):
    """Counts the backtest way: caught/missed over positives, noise over controls, routed non-positives."""
    pos_c, pos_m, noisy, ctl, other_routed, other = [], [], [], 0, [], 0
    for p in prs:
        if "error" in p:
            continue
        t = matcher.trips(state, p)
        if p["kind"] == "history" and p["positive"]:
            (pos_c if t & set(p["expected_contracts"]) else pos_m).append(p["pr"])
        elif p["kind"] == "control":
            ctl += 1
            if t & set(PROMISES):
                noisy.append(p["pr"])
        else:
            other += 1
            if t & set(PROMISES):
                other_routed.append(p["pr"])
    return {"caught": len(pos_c), "missed": len(pos_m), "noise": len(noisy), "controls": ctl,
            "caught_prs": pos_c, "missed_prs": pos_m, "noisy_prs": noisy,
            "other_routed": len(other_routed), "other": other, "other_routed_prs": other_routed}


def counts(s):
    return {k: s[k] for k in ("caught", "missed", "noise", "controls")}


# ---------------------------------------------------------------- events

def build_events(stream, decisions):
    """Stream rows in prediction order (date, pr) with their own decision and its availability date."""
    dec = {}
    for d in decisions:
        if d.get("source") in ("history", "control"):
            dec[(d["source"], str(d["pr_or_branch"]))] = d
    rows = []
    for p in sorted(stream["details"]["prs"], key=lambda r: (r["date"], r["pr"])):
        d = dec.get((p["kind"], str(p["pr"])))
        if d is None:
            raise SystemExit(f"no decision for {p['kind']} #{p['pr']} in decisions.jsonl")
        rows.append({**p, "decision": d, "available": max(d["when"], p["date"])})
    return rows


def available(rows, cutoff):
    """PR rows whose decision is available on or before cutoff (YYYY-MM-DD), in stream order."""
    return [r for r in rows if r["available"] <= cutoff]


# ---------------------------------------------------------------- proposals: ids and shapes

def pid(kind, target, change):
    h = hashlib.sha1(json.dumps([kind, target, change], sort_keys=True).encode()).hexdigest()
    return "P-" + h[:6]


def trigger(r):
    d = r["decision"]
    return {"pr_or_branch": str(r["pr"]), "decision": d["decision"], "url": d.get("url") or r.get("url")}


def full_spec(keys, part):
    return {k: list(part.get(k, [])) for k in keys}


def contract_proposal(kind, contract, spec, why, triggers):
    ck = "add" if kind == "widen-contract" else "exclude"
    change = {ck: full_spec(ADD_KEYS if ck == "add" else EXCL_KEYS, spec)}
    target = {"contract": contract}
    return {"id": pid(kind, target, change), "kind": kind, "target": target, "change": change, "why": why,
            "triggered_by": triggers, "gate": None, "drafted_by": "script", "status": "open"}


def as_override(p, who="simulated", when=None):
    ck = "add" if p["kind"] == "widen-contract" else "exclude"
    return {"proposal_id": p["id"], "contract": p["target"]["contract"],
            ck: {k: v for k, v in p["change"][ck].items() if v}, "who": who, "when": when}


# ---------------------------------------------------------------- gate

GUARDS = {
    # Not part of the default gate. Added after the first replay run (listed in feedback-loop.json details.tried).
    "min-positives": "narrow needs at least one positive among the replayed PRs (otherwise 'caught must not drop' is vacuous)",
    "declared-paths": "narrow may not exclude a whole declared contract path (a path prefix equal to or above a project.json "
                      "path of that contract, a directory segment derived from one, or the file name of a declared file; declared files include "
                      "the files the contract's `sources` cite)",
}


def gate(proposal, state, decisions_before_cutoff, prs_before_cutoff, matcher=None, cutoff=None, history=None, guards=()):
    """Evidence gate for one proposal. Contract kinds: replay on prs_before_cutoff (rows whose decision is
    available on or before the cutoff). Rule kinds: citation check only. Returns the gate dict.
    guards: optional extra conditions from GUARDS (off by default)."""
    if proposal["kind"] in RULE_KINDS:
        return citation_gate(proposal, history, decisions_before_cutoff)
    m = matcher or Matcher(prs_before_cutoff)
    after_state = state.plus(as_override(proposal))
    b, a = score(m, state, prs_before_cutoff), score(m, after_state, prs_before_cutoff)
    trig = {t["pr_or_branch"] for t in proposal["triggered_by"]}
    known = {str(d["pr_or_branch"]) for d in decisions_before_cutoff}
    trig &= known  # a trigger whose decision is not available yet cannot count
    if proposal["kind"] == "widen-contract":
        helped = sorted((set(map(str, a["caught_prs"])) - set(map(str, b["caught_prs"]))) & trig, key=int)
    else:
        helped = sorted((set(map(str, b["noisy_prs"])) - set(map(str, a["noisy_prs"]))) & trig, key=int)
    newly_missed = sorted(set(b["caught_prs"]) - set(a["caught_prs"]))
    newly_noisy = sorted(set(a["noisy_prs"]) - set(b["noisy_prs"]))
    regressions = [str(x) for x in sorted(set(newly_missed) | set(newly_noisy))]
    reasons = []
    if not helped:
        reasons.append("does not change the outcome of the decision that triggered it")
    if newly_missed:
        reasons.append("would miss " + ", ".join(f"#{x}" for x in newly_missed) + " it caught before")
    if proposal["kind"] == "widen-contract":
        if a["noise"] > b["noise"]:
            reasons.append(f"would add noise: {a['noise'] - b['noise']} more merged-clean PR(s) flagged ("
                           + ", ".join(f"#{x}" for x in newly_noisy) + ")")
    else:
        if a["noise"] >= b["noise"]:
            reasons.append("noise does not go down")
        if a["caught"] < b["caught"]:
            reasons.append("catches fewer")
    if proposal["kind"] == "narrow-contract" and "min-positives" in guards and \
            not any(p["kind"] == "history" and p["positive"] for p in prs_before_cutoff):
        reasons.append("guard min-positives: no positive among the replayed PRs")
    if proposal["kind"] == "narrow-contract" and "declared-paths" in guards:
        c = proposal["target"]["contract"]
        x = proposal["change"]["exclude"]
        decl = next(k for k in state.contracts if k["id"] == c)
        # declared files: the contract's paths plus the files its `sources` cite (e.g. MessagePack.csproj:4 for targets)
        paths = tuple(state.rule[c]["paths"]) + tuple(s_.rpartition(":")[0] or s_ for s_ in decl.get("sources", []))
        segs = {q.rstrip("/").split("/")[-1] for q in paths if q.endswith("/")}
        if any(q.startswith(pre) for pre in x.get("path_prefixes", []) for q in paths if pre.endswith("/") or pre == q) \
                or set(x.get("dir_segments", [])) & segs \
                or set(x.get("file_names", [])) & {q.rsplit("/", 1)[-1] for q in paths if not q.endswith("/")}:
            reasons.append("guard declared-paths: would exclude a whole declared contract path")
    eligible = not reasons
    n = len(prs_before_cutoff)
    g = {"eligible": eligible, "gate_kind": "replay",
         "replayed_on": f"{n} PRs decided on or before {cutoff}" if cutoff else f"{n} PRs",
         "before": counts(b), "after": counts(a), "helped": helped, "regressions": regressions}
    if not eligible:
        g["reason"] = "; ".join(reasons)
    return g


def citation_gate(p, history, decisions):
    """Rule proposals: no replay ground truth. Checks citations only, and says so."""
    rules = [r for r in (history or {}).get("rules", [])]
    active = [r for r in rules if not r.get("off")]
    problems = []
    if p["kind"] == "new-rule":
        new = p["change"]["rule"]
        quote, url = p.get("quote"), (new.get("sources") or [None])[0]
        stmts = {(s.get("quote"), s.get("url")) for pr in (history or {}).get("prs", []) for s in pr.get("statements", [])}
        if not quote or not url or not str(url).startswith("https://"):
            problems.append("no verbatim statement with a URL")
        elif (quote, url) not in stmts:
            problems.append("statement not found verbatim in history.json")
        if any(r.get("rule", "").strip() == new.get("rule", "").strip() for r in active):
            problems.append("same text as an active rule")
        if any(url in r.get("sources", []) for r in active):
            problems.append("an active rule already cites this statement")
    else:
        rid = p["target"]["rule"]
        r = next((x for x in rules if x.get("id") == rid), None)
        if r is None:
            problems.append(f"no rule {rid}")
        elif r.get("off"):
            problems.append(f"{rid} is already off")
        cited = [d for d in decisions if d.get("source") == "receipt" and rid in (d.get("rule_ids_cited") or [])]
        if len(cited) < 2:
            problems.append("fewer than 2 owner decisions cite the rule")
        if p["kind"] == "rule-reword" and r is not None and p["change"]["rule"].strip() == r.get("rule", "").strip():
            problems.append("new text equals the current text")
    g = {"eligible": not problems, "gate_kind": "citation-only",
         "replayed_on": "not replayed: rules have no replay ground truth (citation check only)",
         "before": {}, "after": {}, "helped": [], "regressions": []}
    if problems:
        g["reason"] = "; ".join(problems)
    return g


# ---------------------------------------------------------------- candidate generators

def widen_candidates(matcher, state, r):
    """(contract, key, value) candidates from a missed positive's product hunks."""
    hs = [h for h in matcher.hunks[key(r)] if h[3]]
    segs = sorted({d for h in hs for d in h[1]})
    names = sorted({h[2] for h in hs})
    tok = Counter()
    for h in hs:
        for l in h[4]:
            for t in set(TOKEN.findall(l[1:])):
                if len(t) >= 8:
                    tok[t] += 1
    toks = [t for t, _ in sorted(tok.items(), key=lambda kv: (-kv[1], kv[0]))[:TOKENS_PER_PR]]
    out = []
    for c in r["expected_contracts"]:
        rule = state.rule[c]
        out += [(c, "dir_segments", s) for s in segs if s not in rule["segs"]]
        out += [(c, "file_names", n) for n in names if n not in rule["names"]]
        out += [(c, "line_patterns", rf"\b{t}\b") for t in toks if rf"\b{t}\b" not in rule["pats"]]
    return out


def feature_matches(h, k, v):
    if k == "dir_segments":
        return v in h[1]
    if k == "file_names":
        return h[2] == v
    if k == "line_patterns":
        p = rx(v)
        return any(p.search(l[1:]) for l in h[4])
    if k == "path_prefixes":
        return h[0].startswith(v)
    raise ValueError(k)


WIDEN_RANK = {"file_names": 0, "line_patterns": 1, "dir_segments": 2}
NARROW_RANK = {"path_prefixes": 0, "file_names": 1, "dir_segments": 2}


def narrow_candidates(matcher, state, r, cid):
    """Exclude specs that cover every hunk tripping cid on control r."""
    cs = matcher.causes(state, r, cid)
    files = sorted({h[0] for h, _ in cs})
    names = sorted({posixpath.basename(f) for f in files})
    out = []
    if len(files) == 1:
        out.append({"path_prefixes": [files[0]]})
    if len(names) <= 5:
        out.append({"file_names": names})
    common = posixpath.commonpath(files) if files else ""
    if len(files) > 1 and common:
        out.append({"path_prefixes": [common + "/"]})
    elif len(files) == 1 and "/" in files[0]:
        out.append({"path_prefixes": [posixpath.dirname(files[0]) + "/"]})
    segs = {w for _, w in cs}
    if segs == {"path-segment"}:
        matched = {d for h, _ in cs for d in h[1] if d in state.rule[cid]["segs"]}
        if len(matched) == 1:
            out.append({"dir_segments": sorted(matched)})
    # an exact contract `path` can only be blocked by a path prefix
    if any(w == "path" for _, w in cs):
        out = [s for s in out if "path_prefixes" in s]
    # de-duplicate, keep order
    seen, uniq = set(), []
    for s in out:
        k = json.dumps(s, sort_keys=True)
        if k not in seen:
            seen.add(k)
            uniq.append(s)
    return uniq


def _rank(kind, spec, n, choose):
    (k, vs), = spec.items()
    kr = (WIDEN_RANK if kind == "widen-contract" else NARROW_RANK)[k]
    v = json.dumps(vs)
    if choose == "general":
        return (-n, -kr, len(v), v)
    return (n, kr, -len(v), v)


def propose_contracts(matcher, state, rows, cutoff, kinds=CONTRACT_KINDS, choose="specific", guards=()):
    """Widen/narrow proposals from the decisions available at cutoff, each gated on the PRs available
    at cutoff. One proposal per trigger: the chosen eligible candidate, else the top-ranked candidate
    (ineligible, with its gate reason). Proposals with the same id are merged (triggers joined, re-gated)."""
    avail = [r for r in rows if r["available"] <= cutoff and "error" not in r]
    decs = [r["decision"] for r in avail]
    out = {}

    def consider(kind, cands, trig_row, why_fn):
        best = None
        scored = []
        for contract, spec in cands:
            p = contract_proposal(kind, contract, spec, "", [trigger(trig_row)])
            n = matcher.spread(avail, spec, product_only=(kind == "widen-contract"))
            g = gate(p, state, decs, avail, matcher, cutoff, guards=guards)
            scored.append((not g["eligible"], _rank(kind, spec, n, choose), contract, p, g, n))
        if not scored:
            return
        scored.sort(key=lambda x: x[:3])
        _, _, contract, p, g, n = scored[0]
        p["why"] = why_fn(contract, p, n, sum(1 for s in scored if not s[0]), len(scored))
        p["gate"] = g
        if p["id"] in out:
            q = out[p["id"]]
            q["triggered_by"] += [t for t in p["triggered_by"] if t not in q["triggered_by"]]
            q["gate"] = gate(q, state, decs, avail, matcher, cutoff, guards=guards)
        else:
            out[p["id"]] = p

    if "widen-contract" in kinds:
        for r in avail:
            if not (r["positive"] and r["decision"]["decision"] in MISS_DECISIONS):
                continue
            if matcher.trips(state, r) & set(r["expected_contracts"]):
                continue
            cands = [(c, {k: [v]}) for c, k, v in widen_candidates(matcher, state, r)]

            def why(contract, p, n, n_ok, n_all, r=r):
                (k, vs), = {k: v for k, v in p["change"]["add"].items() if v}.items()
                return (f"Maintainers {r['decision']['decision'].replace('_', ' ')} #{r['pr']} ({r['concern']}), but none of its "
                        f"expected contracts ({', '.join(r['expected_contracts'])}) tripped. Adding the {k.replace('_', ' ')[:-1]} "
                        f"{vs[0]} (from its non-test changes) to {contract} makes it trip; {n} of {len(avail)} decided PRs "
                        f"have a matching product hunk. {n_ok} of {n_all} candidate features passed the gate; "
                        f"{'the most general' if choose == 'general' else 'the most specific'} passing one is shown.")
            consider("widen-contract", cands, r, why)

    if "narrow-contract" in kinds:
        for r in avail:
            if r["kind"] != "control":
                continue
            t = matcher.trips(state, r) & set(PROMISES)
            for cid in sorted(t):
                cands = [(cid, s) for s in narrow_candidates(matcher, state, r, cid)]

                def why(contract, p, n, n_ok, n_all, r=r, t=t):
                    spec = {k: v for k, v in p["change"]["exclude"].items() if v}
                    words = "; ".join(f"{k.replace('_', ' ')} {', '.join(v)}" for k, v in spec.items())
                    also = sorted(t - {contract})
                    return (f"#{r['pr']} was merged with no objection but tripped {contract}. Excluding {words} from "
                            f"{contract} removes that trip; {n} of {len(avail)} decided PRs touch it."
                            + (f" It also trips {', '.join(also)}, so this alone cannot clear it." if also else "")
                            + f" {n_ok} of {n_all} candidate excludes passed the gate.")
                consider("narrow-contract", cands, r, why)
    order = {k: i for i, k in enumerate(CONTRACT_KINDS)}
    return sorted(out.values(), key=lambda p: (order[p["kind"]], not p["gate"]["eligible"],
                                               min(rows_index(rows, t["pr_or_branch"]) for t in p["triggered_by"])))


def rows_index(rows, pr):
    for i, r in enumerate(rows):
        if str(r["pr"]) == str(pr):
            return i
    return len(rows)


# ---------------------------------------------------------------- rule proposals

def propose_rules(history, decisions, cutoff, use_llm=False):
    """rule-off / rule-reword from receipts, new-rule from maintainer statements. Citation-gated."""
    history = history or {"rules": [], "prs": []}
    rules = history.get("rules", [])
    active = [r for r in rules if not r.get("off")]
    decs = [d for d in decisions if (d.get("when") or "") <= cutoff]
    out = []
    receipts = [d for d in decs if d.get("source") == "receipt"]
    by_rule = {}
    for d in receipts:
        for rid in d.get("rule_ids_cited") or []:
            by_rule.setdefault(rid, []).append(d)
    for rid in sorted(by_rule):
        r = next((x for x in active if x["id"] == rid), None)
        if r is None:
            continue
        ds = by_rule[rid]
        acc = [d for d in ds if d["decision"] == "accept"]
        rej = [d for d in ds if d["decision"] in ("reject", "send_back")]
        trig = lambda xs: [{"pr_or_branch": d["pr_or_branch"], "decision": d["decision"], "url": d.get("url")} for d in xs]
        if len(acc) >= 2:
            target, change = {"rule": rid}, {"off": True}
            out.append({"id": pid("rule-off", target, change), "kind": "rule-off", "target": target, "change": change,
                        "why": f"Owners accepted {len(acc)} claims that {rid} was cited against "
                               f"({', '.join(sorted({str(d.get('claim_id')) for d in acc}))}); the rule did not change their decision.",
                        "triggered_by": trig(acc), "drafted_by": "script", "status": "open"})
        if len(rej) >= 2:
            reasons = [d["reason"] for d in rej if d.get("reason")]
            shortest = min(reasons, key=lambda s: (len(s), s)) if reasons else ""
            first = re.split(r"(?<=[.!?])\s", shortest.strip())[0]
            text, drafted = r["rule"].rstrip() + f" Owner example: \"{first}\"", "script"
            if use_llm:
                t = llm_rule(f"Current rule: {r['rule']}\nOwner reasons when they sent back or rejected claims citing it:\n- "
                             + "\n- ".join(reasons), reword=True)
                if t:
                    text, drafted = t, "llm"
            target, change = {"rule": rid}, {"rule": text}
            out.append({"id": pid("rule-reword", target, change), "kind": "rule-reword", "target": target, "change": change,
                        "why": f"Owners rejected or sent back {len(rej)} claims citing {rid}; their own reasons are the evidence for "
                               f"a sharper wording. Reasons on record: " + " | ".join(reasons[:3]),
                        "triggered_by": trig(rej), "drafted_by": drafted, "status": "open"})
    # new-rule: one per pushed-back/reverted PR, its first qualifying maintainer statement
    dec_by_pr = {str(d["pr_or_branch"]): d for d in decs if d.get("source") == "history"}
    for pr in sorted(history.get("prs", []), key=lambda p: (p["date"], p["pr"])):
        d = dec_by_pr.get(str(pr["pr"]))
        if d is None or d["decision"] not in MISS_DECISIONS or max(d["when"], pr["date"]) > cutoff:
            continue
        pat = re.compile(rf"/(pull|issues)/{pr['pr']}(?!\d)")
        same = [r for r in active if r.get("concern") == pr["concern"]]
        if any(pat.search(u) for r in same for u in r.get("sources", [])):
            continue
        stmts = [s for s in pr.get("statements", [])
                 if s.get("url") and not re.search(rf"/pull/{pr['pr']}#issue-", s["url"])
                 and (s.get("date") or "") <= cutoff and len(s.get("quote", "").split()) >= MIN_QUOTE_WORDS]
        if any(s["url"] in r.get("sources", []) for r in same for s in stmts):
            continue
        stmts.sort(key=lambda s: (s.get("date") or "", s["url"]))
        if not stmts:
            continue
        s = stmts[0]
        text, drafted = s["quote"], "script"
        if use_llm:
            t = llm_rule(s["quote"])
            if t:
                text, drafted = t, "llm"
        target, change = {"rule": None}, {"rule": {"concern": pr["concern"], "rule": text, "sources": [s["url"]]}}
        out.append({"id": pid("new-rule", target, change), "kind": "new-rule", "target": target, "change": change,
                    "why": f"{s['who']} on #{pr['pr']} ({pr['outcome']}, concern {pr['concern']}): \"{s['quote']}\" ({s['url']}). "
                           f"No active {pr['concern']} rule cites this PR.",
                    "quote": s["quote"],
                    "triggered_by": [{"pr_or_branch": str(pr["pr"]), "decision": d["decision"], "url": s["url"]}],
                    "drafted_by": drafted, "status": "open"})
    for p in out:
        p["gate"] = citation_gate(p, history, decs)
    return out


def llm_rule(text, reword=False):
    """Optional: ask the Messages API to phrase a rule. Returns None without a key (LLM_KEY or ANTHROPIC_API_KEY) or on error."""
    import urllib.request
    keyv = os.environ.get("LLM_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not keyv:
        return None
    ask = ("Rewrite this rule so it also covers the owner reasons below, as one imperative code review rule, at most 40 "
           "words, no new facts. Reply with the rule only.\n\n" if reword else
           "Rewrite this maintainer quote as one imperative code review rule, at most 40 words, no new facts. "
           "Reply with the rule only.\n\nQuote: ")
    body = json.dumps({"model": LLM_MODEL, "max_tokens": 120,
                       "messages": [{"role": "user", "content": ask + text}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, method="POST",
                                 headers={"x-api-key": keyv, "anthropic-version": "2023-06-01",
                                          "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            j = json.load(res)
        t = "".join(b.get("text", "") for b in j.get("content", []) if b.get("type") == "text").strip()
        return t if t and len(t.split()) <= 60 else None
    except Exception as e:  # network/HTTP error: fall back to the script draft
        print(f"llm: {e.__class__.__name__}: {e}; falling back to the script draft", file=sys.stderr)
        return None


# ---------------------------------------------------------------- self-test

def baseline_state(stream, project):
    return State(project["contracts"], stream["details"]["generalised_rules"])


def self_test():
    import backtest as bt
    from pr_stream import cached_generalised
    stream = load_stream()
    project = json.loads(read_ctx("project"))
    prs = [p for p in stream["details"]["prs"] if "error" not in p]
    st = baseline_state(stream, project)
    g = cached_generalised(stream, project["contracts"])
    m = Matcher(prs)
    for p in prs:
        mine = sorted(m.trips(st, p))
        assert mine == p["generalised_tripped"], (p["pr"], mine, p["generalised_tripped"])
        for h, hp in zip(p["hunks"], m.hunks[key(p)]):
            assert st.trip(hp) == g.trip(h), (p["pr"], h["file"])
    s = score(m, st, prs)
    bj = json.load(open(os.path.join(REVIEW, "evidence", "backtest.json")))["details"]["generalised"]
    assert (s["caught"], s["caught"] + s["missed"], s["noise"], s["controls"]) == \
        (bj["caught"], bj["positives_evaluated"], bj["controls_tripping_a_promise"], bj["controls"]) == (10, 16, 33, 60), s
    # an exclude blocks a path-segment trip; a path prefix blocks an exact path trip
    h = prep_hunks([{"file": "src/MessagePack/Formatters/X.cs", "start": 1, "lines": ["+a"]}])[0]
    ov = {"proposal_id": "t", "contract": "wire-format", "exclude": {"dir_segments": ["Formatters"]}}
    assert st.trip_one("wire-format", h) == "path" and st.plus(ov).trip_one("wire-format", h) == "path"
    ov2 = {"proposal_id": "t2", "contract": "wire-format", "exclude": {"path_prefixes": ["src/MessagePack/Formatters/"]}}
    assert st.plus(ov2).trip_one("wire-format", h) is None
    h2 = prep_hunks([{"file": "src/Other/Formatters/Y.cs", "start": 1, "lines": ["+a"]}])[0]
    assert st.trip_one("wire-format", h2) == "path-segment" and st.plus(ov).trip_one("wire-format", h2) is None
    ov3 = {"proposal_id": "t3", "contract": "public-api", "add": {"line_patterns": [r"\bFoo\b"]}}
    h3 = prep_hunks([{"file": "src/A/B.cs", "start": 1, "lines": ["+ Foo x"]}])[0]
    assert st.trip_one("public-api", h3) is None and st.plus(ov3).trip_one("public-api", h3).startswith("line")
    print(f"self-test OK: no overrides -> caught {s['caught']} of {s['caught'] + s['missed']}, "
          f"{s['noise']} of {s['controls']} controls trip a promise contract; per-PR and per-hunk trips equal "
          f"backtest.Generalised on all {len(prs)} cached PRs")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        self_test()
    else:
        ap.print_help()
