#!/usr/bin/env python3
"""Backtest: would the tripwire step have shown the owner the PRs maintainers pushed back on?

Replays the contracts in review/context/project.json (taken at base 32258fdb) against
real upstream MessagePack-CSharp history:

  positives  history.json PRs whose maintainer concern is a user promise
             (public-api, wire-format, compat-breaking, targets, generated, diagnostics, security).
             Diff = PR head (refs/pr/N, fetched from github.com) against its merge-base with
             the upstream branch it came from (see choose_base).
  controls   ordinary merged PRs: `git log --merges --first-parent 32258fdb`, PRs only, not in
             history.json, not build/CI/dependency/branch-sync by title, sampled evenly over the
             years the positives span. Diff = first-parent diff of the merge commit.

Each diff is run through two matchers:
  strict       the contract paths/patterns exactly as tripwires.py applies them (2025 layout).
  generalised  the same contracts with path drift handled by a rule derived from the base tree,
               not by hand-listed per-era paths (RULE below). This is the headline number.

    python3 review/scripts/backtest.py --repo <clone> [--fetch] [--write]

--fetch fetches missing refs/pr/N from github.com into the clone (refs only; no checkout).
Standard library only. Writes review/evidence/backtest.json.
"""
import argparse, json, os, posixpath, re, subprocess, sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REVIEW = os.path.dirname(HERE)
BASE = "32258fdb"
UPSTREAM = "https://github.com/MessagePack-CSharp/MessagePack-CSharp"

PROMISES = ["public-api", "wire-format", "generated", "targets", "diagnostics", "security"]
POSITIVE_CONCERNS = PROMISES + ["compat-breaking"]
CONCERN_TO_CONTRACTS = {
    "public-api": ["public-api"],
    "wire-format": ["wire-format"],
    "generated": ["generated"],
    "targets": ["targets"],
    "diagnostics": ["diagnostics"],
    "security": ["security"],
    "compat-breaking": ["public-api", "wire-format", "generated", "diagnostics"],
}
# Upstream branches a PR may have been cut from. 32258fdb is the develop line.
BASE_CANDIDATES = [BASE, "origin/master", "origin/v2.x", "origin/v1.x"]
CONTROLS_TARGET = 60
EXCLUDE_TITLE = re.compile(
    r"^\s*(bump|dependency updates)\b|^\s*merge\b(.*\b(to|into)\s+(master|develop|v\d\S*)\s*$|\s+latest\b)|^\s*update\b.*\b(sdk|packages?|dependenc(y|ies)|references)\b|"
    r"dependabot|renovate|library\.template|\bsdk\b|\bci\b|github actions|azure pipelines?|codecov|"
    r"\b(master|develop)\s+(to|into)\s+(master|develop)\b|^\s*build\b|\bbuild (script|tasks?|artifact)|"
    r"\bunity build\b|\bpackage dependenc",
    re.I)
EXCLUDE_BRANCH = re.compile(r"dependabot/|libtemplate|Library\.Template|renovate/", re.I)
NON_PRODUCT_SEG = re.compile(r"^(sandbox|benchmarks?|perf|samples?)$|(^|\.)(unit)?tests?(\.|$)", re.I)


def git(repo, *args, ok=False):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if r.returncode and not ok:
        sys.exit(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout if not r.returncode else None


def exists(repo, rev):
    return git(repo, "rev-parse", "-q", "--verify", rev + "^{commit}", ok=True) is not None


# ---------------------------------------------------------------- diff parsing

def hunks(repo, a, b):
    """Changed hunks of `git diff a b` (no renames, so a move shows as delete + add).
    Unlike tripwires.py, a deleted file keeps its old path (tripwires.py drops it)."""
    out = git(repo, "diff", "-U0", "--no-color", "--no-renames", "--no-ext-diff", a, b)
    old = cur = None
    h = None
    for line in out.splitlines():
        if line.startswith("diff --git "):
            if h:
                yield h
            h, old, cur = None, None, None
        elif line.startswith("--- "):
            old = None if line[4:] == "/dev/null" else line[6:]
        elif line.startswith("+++ "):
            cur = old if line[4:] == "/dev/null" else line[6:]
        elif line.startswith("@@") and cur:
            if h:
                yield h
            m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
            h = {"file": cur, "start": int(m.group(2)), "lines": []}
        elif h is not None and line[:1] in "+-":
            h["lines"].append(line)
        elif line.startswith("Binary files") and cur is None:
            m = re.match(r"Binary files (?:a/)?(\S+) and (?:b/)?(\S+) differ", line)
            if m:
                f = m.group(2) if m.group(2) != "/dev/null" else m.group(1)
                yield {"file": f, "start": 0, "lines": []}
    if h:
        yield h


# ---------------------------------------------------------------- matchers

def under(path, prefixes):
    return any(path == p or (p.endswith("/") and path.startswith(p)) for p in prefixes)


def product(path):
    return not any(NON_PRODUCT_SEG.search(s) for s in path.split("/")[:-1])


class Strict:
    """tripwires.py semantics: file under a contract path, or a changed line outside tests/ matches a pattern."""
    name = "strict"

    def __init__(self, contracts):
        self.contracts = contracts

    def trip(self, h):
        out = {}
        for c in self.contracts:
            if under(h["file"], c["paths"]):
                out[c["id"]] = "path"
            elif not h["file"].startswith("tests/"):
                for pat in c.get("line_patterns", []):
                    hit = next((l for l in h["lines"] if re.search(pat, l[1:])), None)
                    if hit:
                        out[c["id"]] = "line: " + hit[:100].rstrip()
                        break
        return out


class Generalised:
    """Path drift rule, derived from the contracts and the base tree (see RULE)."""
    name = "generalised"

    def __init__(self, contracts, repo):
        self.contracts = contracts
        tree = git(repo, "ls-tree", "-r", "--name-only", BASE).splitlines()
        bn = Counter(posixpath.basename(f) for f in tree)
        unique = lambda n: bn[n] == 1 and not n.startswith(".")
        self.rules = {}
        for c in contracts:
            segs, names = set(), set()
            for p in c["paths"]:
                if p.endswith("/"):
                    segs.add(p.rstrip("/").split("/")[-1])
                    names |= {posixpath.basename(f) for f in tree if f.startswith(p) and unique(posixpath.basename(f))}
                else:
                    names.add(posixpath.basename(p))  # e.g. PublicAPI.Shipped.txt lives in one dir per TFM
            pats = list(c.get("line_patterns", []))
            for src in c.get("sources", []):
                f, _, ln = src.rpartition(":")
                if f.endswith((".csproj", ".props")) and ln.isdigit():
                    text = git(repo, "show", f"{BASE}:{f}").splitlines()[int(ln) - 1]
                    m = re.search(r"<(\w+?)s?>", text)
                    if m:
                        pats.append(rf"<{m.group(1)}s?>")  # <TargetFrameworks> -> also <TargetFramework>
            self.rules[c["id"]] = {"dir_segments": sorted(segs), "file_names": sorted(names), "line_patterns": pats}

    def trip(self, h):
        out = {}
        f = h["file"]
        dirs, base = f.split("/")[:-1], posixpath.basename(f)
        for c in self.contracts:
            r = self.rules[c["id"]]
            if under(f, c["paths"]):
                out[c["id"]] = "path"
                continue
            if not product(f):
                continue
            if any(d in r["dir_segments"] for d in dirs):
                out[c["id"]] = "path-segment"
            elif base in r["file_names"]:
                out[c["id"]] = "file-name"
            else:
                for pat in r["line_patterns"]:
                    hit = next((l for l in h["lines"] if re.search(pat, l[1:])), None)
                    if hit:
                        out[c["id"]] = "line: " + hit[:100].rstrip()
                        break
        return out


def run(repo, a, b, matchers):
    res = {m.name: defaultdict(list) for m in matchers}
    n = 0
    files = set()
    for h in hunks(repo, a, b):
        n += 1
        files.add(h["file"])
        for m in matchers:
            for cid, why in m.trip(h).items():
                if len(res[m.name][cid]) < 3:
                    res[m.name][cid].append(f"{h['file']}:{h['start']} ({why})")
                else:
                    res[m.name][cid].append(None)
    return n, len(files), {k: {c: {"hunks": len(v), "examples": [x for x in v if x]} for c, v in r.items()}
                           for k, r in res.items()}


# ---------------------------------------------------------------- selection

def choose_base(repo, head, merge_commit):
    """Merged PR with a merge commit on record: merge-base with that merge's first parent (the
    branch it landed on). Otherwise: merge-base with whichever upstream line in BASE_CANDIDATES
    is closest to the head (fewest head-only commits). A line that already contains the head
    (PR merged there but no merge commit recorded) is resolved to the first merge on that line's
    first-parent history that brought the head in, and that merge's first parent is used."""
    if merge_commit and exists(repo, merge_commit) and exists(repo, merge_commit + "^2"):
        mb = git(repo, "merge-base", head, merge_commit + "^1").strip()
        return mb, f"merge-base with {merge_commit}^1 (branch it merged into)"
    best = None
    for cand in BASE_CANDIDATES:
        if not exists(repo, cand):
            continue
        if git(repo, "merge-base", "--is-ancestor", head, cand, ok=True) is not None:
            mc = (git(repo, "log", "--ancestry-path", "--merges", "--first-parent", "--reverse",
                      "--format=%H", f"{head}..{cand}") or "").split()
            if mc:
                mb = git(repo, "merge-base", head, mc[0] + "^1").strip()
                return mb, f"merge-base with {mc[0][:8]}^1 (head already merged into {cand} by {mc[0][:8]})"
            continue
        mb = git(repo, "merge-base", head, cand, ok=True)
        if not mb:
            continue
        mb = mb.strip()
        d = int(git(repo, "rev-list", "--count", f"{mb}..{head}").strip())
        if best is None or d < best[2]:
            best = (mb, cand, d)
    return best[0], f"merge-base with {best[1]} (closest of {', '.join(BASE_CANDIDATES)}; {best[2]} PR-only commits)"


def pick_controls(repo, excluded_prs, years):
    log = git(repo, "log", "--merges", "--first-parent", "--date=short",
              "--format=%H%x1f%ad%x1f%s%x1f%b%x1e", BASE)
    seen, by_year, dropped = set(), defaultdict(list), Counter()
    for rec in log.split("\x1e"):
        rec = rec.strip("\n")
        if not rec:
            continue
        sha, date, subj, body = rec.split("\x1f")
        m = re.match(r"Merge pull request #(\d+) from (\S+)", subj)
        if not m:
            dropped["not a PR merge"] += 1
            continue
        pr, branch = int(m.group(1)), m.group(2)
        title = (body.strip().splitlines() or [""])[0].strip()
        if pr in excluded_prs:
            dropped["PR in history.json"] += 1
        elif pr in seen:
            dropped["duplicate PR number"] += 1
        elif EXCLUDE_BRANCH.search(branch) or EXCLUDE_TITLE.search(title):
            dropped["build/CI/dependency/branch-sync by title or branch"] += 1
        elif date[:4] in years:
            seen.add(pr)
            by_year[date[:4]].append({"pr": pr, "merge": sha[:8], "date": date, "title": title, "branch": branch})
        else:
            dropped["outside positive years"] += 1
    # equal share per year, leftover share passed to years with more PRs; evenly spaced within a year
    quota, left, ys = {}, CONTROLS_TARGET, sorted(years)
    pending = sorted(ys, key=lambda y: len(by_year[y]))
    while pending:
        y = pending.pop(0)
        quota[y] = min(len(by_year[y]), left // (len(pending) + 1))
        left -= quota[y]
    picked = []
    for y in ys:
        pool, k = sorted(by_year[y], key=lambda r: r["date"]), quota[y]
        picked += [pool[int(i * len(pool) / k)] for i in range(k)] if k else []
    return picked, {y: len(by_year[y]) for y in ys}, quota, dict(dropped)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.environ.get("MP_REPO"), required=os.environ.get("MP_REPO") is None)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    R = a.repo

    ctx = json.load(open(os.path.join(REVIEW, "context", "project.json")))
    hist = json.load(open(os.path.join(REVIEW, "context", "history.json")))
    contracts = ctx["contracts"]
    strict, gen = Strict(contracts), Generalised(contracts, R)
    matchers = [strict, gen]

    # PR numbers anywhere in history.json (the 37 PRs plus PRs their notes/reverts cite) stay out of the controls
    excluded = {p["pr"] for p in hist["prs"]} | {int(x) for x in re.findall(r"#(\d{3,4})\b", json.dumps(hist))}

    positives = []
    for p in hist["prs"]:
        if p["concern"] not in POSITIVE_CONCERNS:
            continue
        ref = f"refs/pr/{p['pr']}"
        if not exists(R, ref) and a.fetch:
            git(R, "fetch", "-q", UPSTREAM, f"pull/{p['pr']}/head:{ref}", ok=True)
        row = {"pr": p["pr"], "title": p["title"], "date": p["date"], "outcome": p["outcome"],
               "concern": p["concern"], "expected_contracts": CONCERN_TO_CONTRACTS[p["concern"]]}
        if not exists(R, ref):
            row["error"] = f"{ref} not in clone (run with --fetch)"
            positives.append(row)
            continue
        head = git(R, "rev-parse", ref).strip()
        mb, how = choose_base(R, head, p.get("merge_commit"))
        n, nf, trips = run(R, mb, head, matchers)
        row.update({"head": head[:8], "merge_base": mb[:8], "base_rule": how, "hunks": n, "files": nf, "trips": trips})
        oc = p.get("original_commit")
        if p["outcome"] == "reverted" and oc and exists(R, oc):
            par = oc + "^1"
            _, _, t2 = run(R, par, oc, [gen])
            row["cross_check_original_commit"] = {"commit": oc, "diff": f"{oc}^1..{oc}",
                                                  "generalised_tripped": sorted(t2["generalised"])}
        positives.append(row)

    years = {r["date"][:4] for r in positives}
    picked, pool_sizes, quota, dropped = pick_controls(R, excluded, years)
    controls = []
    for c in picked:
        n, nf, trips = run(R, c["merge"] + "^1", c["merge"], matchers)
        controls.append({**c, "hunks": n, "files": nf, "trips": trips})

    def score(mname):
        ok = [r for r in positives if "error" not in r]
        caught, missed, any_trip, any_promise = [], [], [], []
        for r in ok:
            t = set(r["trips"][mname])
            hit = sorted(t & set(r["expected_contracts"]))
            (caught if hit else missed).append(r["pr"])
            if t:
                any_trip.append(r["pr"])
            if t & set(PROMISES):
                any_promise.append(r["pr"])
        noisy = [c["pr"] for c in controls if set(c["trips"][mname]) & set(PROMISES)]
        docs = [c["pr"] for c in controls if "user-docs" in c["trips"][mname]]
        per = Counter(k for c in controls for k in c["trips"][mname])
        by_year = defaultdict(lambda: [0, 0])
        for c in controls:
            by_year[c["date"][:4]][1] += 1
            by_year[c["date"][:4]][0] += c["pr"] in noisy
        return {"positives_evaluated": len(ok), "caught": len(caught), "missed": len(missed),
                "caught_prs": caught, "missed_prs": missed,
                "positives_any_contract_tripped": len(any_trip),
                "positives_any_promise_contract_tripped": len(any_promise),
                "positives_no_promise_contract_tripped": sorted(set(r["pr"] for r in ok) - set(any_promise)),
                "controls": len(controls), "controls_tripping_a_promise": len(noisy),
                "noise_rate": round(len(noisy) / len(controls), 3) if controls else None,
                "noisy_control_prs": noisy,
                "controls_tripping_user_docs": len(docs),
                "controls_trips_per_contract": dict(sorted(per.items())),
                "noise_by_year": {y: f"{a} of {b}" for y, (a, b) in sorted(by_year.items())}}

    S, G = score("strict"), score("generalised")

    # why each generalised miss was missed: what it did touch, and the reason class
    # Hand-written after reading each miss's diff (git diff --stat <merge_base> <head>); they explain, they do not score.
    MISS_REASON = {
        2013: "Behavioural default flip: one line in src/MessagePack/MessagePackSerializerOptions.cs makes UntrustedData the default security policy. No contract path or pattern covers option defaults; the security contract names only SECURITY.md and MessagePackSecurity.cs. Only README/doc (user-docs) tripped.",
        1137: "Behavioural compat change (throw instead of quietly returning null for init-only setters on generic types) inside Resolvers/DynamicObjectResolver.cs, which no contract names. Only README (user-docs) tripped.",
        1697: "Wire compatibility break through member-ordering logic in Resolvers/DynamicObjectResolver.cs (DataContract Order across a hierarchy). The wire-format contract names reader/writer/code/formatter files, not the dynamic resolver that decides key order. Nothing tripped.",
        889: "Field-to-property change on MessagePackSerializerOptions is binary breaking, but the PR edits only MessagePackSerializerOptions.cs and does not touch PublicAPI.*.txt; a one-line .cs change is invisible to paths and patterns. Nothing tripped.",
        1828: "Moves a member from TypelessFormatter to MessagePackSerializerOptions without updating PublicAPI.*.txt, so public-api cannot see it; it did trip wire-format (Formatters/TypelessFormatter.cs), so the owner would still have been shown it, under the wrong contract.",
        1895: "Labelled 'generated' because the maintainer said to edit the .tt and regenerate, but the files are the library's own T4 output (MessagePackReader.Integers.cs etc.), not code generated into the consumer's assembly. It tripped wire-format (MessagePackReader.cs by file name), so it would have been shown; the miss is a label/contract mismatch.",
    }
    missed_list = []
    for r in positives:
        if "error" in r or r["pr"] not in G["missed_prs"]:
            continue
        missed_list.append({"pr": r["pr"], "title": r["title"], "concern": r["concern"],
                            "expected_contracts": r["expected_contracts"],
                            "tripped_instead": sorted(r["trips"]["generalised"]),
                            "files": r["files"],
                            "why": MISS_REASON.get(r["pr"], "")})

    cmd = f"python3 review/scripts/backtest.py --repo $MP_REPO --fetch --write"
    summary = (f"Generalised tripwires caught {G['caught']} of {G['positives_evaluated']} promise-concern PRs "
               f"(missed {G['missed']}; any contract tripped on {G['positives_any_contract_tripped']}); "
               f"{G['controls_tripping_a_promise']} of {G['controls']} ordinary merged PRs tripped a promise contract "
               f"(noise {G['noise_rate']:.0%}); strict 2025 paths: caught {S['caught']}, noise "
               f"{S['controls_tripping_a_promise']} of {S['controls']}")
    ev = {
        "check": "tripwire-backtest",
        "branch": None,
        "base": BASE,
        "command": cmd,
        "result": "pass",
        "summary": summary,
        "details": {
            "headline_matcher": "generalised",
            "generalised": G,
            "strict": S,
            "missed": missed_list,
            "method": {
                "positives": "history.json PRs with concern in " + ", ".join(POSITIVE_CONCERNS)
                             + f"; head = refs/pr/N fetched from {UPSTREAM} pull/N/head (final PR head, i.e. after any review changes).",
                "positive_base": choose_base.__doc__.strip().replace("\n   ", ""),
                "reverted_cross_check": "for reverted PRs the original commit recorded in history.json is also diffed against its first parent (generalised matcher) and reported beside the PR-head result; the PR-head result is the one scored.",
                "controls": f"`git log --merges --first-parent {BASE}`, subjects 'Merge pull request #N from <branch>' only; drop PRs whose number appears anywhere in history.json; drop by branch regex /{EXCLUDE_BRANCH.pattern}/ or title (first body line) regex /{EXCLUDE_TITLE.pattern}/ (case-insensitive); keep only the years the positives span; {CONTROLS_TARGET} picked with an equal share per year (a year with too few PRs passes its unused share on), evenly spaced by date within a year. Diff = <merge>^1..<merge>.",
                "controls_pool_per_year": pool_sizes,
                "controls_quota_per_year": quota,
                "controls_dropped": dropped,
                "diff": "git diff -U0 --no-renames (a moved file counts as delete + add). Deleted files are matched on their old path; tripwires.py currently drops deleted files (it keys hunks on the +++ path), so a pure deletion of a contract file would not trip there.",
                "strict_rule": "exactly tripwires.py: hunk file under a contract path (prefix for dirs, equality for files), or a changed (+/-) line in a file not under tests/ matching a contract line pattern.",
                "generalised_rule": [
                    "A hunk trips contract C when any of these holds:",
                    "(1) strict path match;",
                    "otherwise only for product files, i.e. no directory segment named sandbox/benchmark(s)/perf/sample(s) or containing a 'test'/'tests'/'unittests' dotted component (e.g. tests/, MessagePack.Tests/):",
                    "(2) a directory segment equals the last segment of one of C's directory paths (Formatters, Transforms, Analyzers, CodeAnalysis, analyzers);",
                    "(3) the file name equals the file name of one of C's file paths (PublicAPI.Shipped.txt, PublicAPI.Unshipped.txt, MessagePackReader.cs, SECURITY.md, ...) or of a file inside one of C's directory paths at base, counting only file names that are unique in the base tree and not dotfiles (so FormatterTemplate.tt or StandardClassLibraryFormatter.cs match in any layout, .editorconfig does not);",
                    "(4) a changed line matches one of C's line patterns, plus, for each csproj/props line C cites in `sources`, the XML element on that line in singular or plural form (targets: <TargetFrameworks?>), in any file.",
                    "No per-era path is listed by hand; everything comes from project.json and the base tree."],
                "generalised_rules_derived": gen.rules,
                "concern_to_contracts": CONCERN_TO_CONTRACTS,
                "caught_definition": "caught = the generalised tripped set includes at least one contract mapped from the PR's concern; missed otherwise.",
                "noise_definition": "noise = share of control PRs whose tripped set includes any of " + ", ".join(PROMISES) + "; user-docs is reported separately and not counted as noise.",
            },
            "limits": [
                "Tripping is not a verdict. The real gate also needs a check that the promise actually changed (PublicAPI diff, byte round-trip, regenerated output, TFM list). A trip only says 'show the owner'; a high trip rate on controls means owner time, not wrong answers.",
                f"Small sample: {G['positives_evaluated']} positives and {G['controls']} controls. One PR moves the catch rate by about {100 / max(G['positives_evaluated'], 1):.0f} points.",
                "Concern labels came from an agent reading maintainer comments via WebFetch (history.json, produced_by hand); some quotes are fragments and some PR pages were only partly read. A wrong label moves a PR between caught and missed.",
                "Positives are diffed at the final PR head. For merged-after-changes PRs that is after the maintainer's requested fixes, which can remove (or add) the very change that drew the concern.",
                "Controls are merged PRs with no recorded pushback in history.json, but history.json was built from targeted searches, so some controls may also have had review pushback we could not see (api.github.com is blocked). Noise is therefore an upper bound on 'trips nobody needed'.",
                "Controls come from the develop first-parent line only; PRs that landed on master/v1.x/v2.x are not sampled.",
                "Older layouts (Unity client shared sources, mpc GeneratorCore, MessagePackAnalyzer) only match where a base-tree file name or directory name survived; renamed files and directories are invisible to the rule by design.",
                "The contracts are the 2025 ones; promises the project made in 2019-2021 (e.g. v1 binary compatibility, mpc tool targets) are only covered as far as the 2025 contracts happen to describe them.",
            ],
            "positives": positives,
            "controls": controls,
        },
        "tool_versions": {"git": git(R, "--version").strip(), "python": sys.version.split()[0]},
        "produced_by": "script",
    }
    print(summary)
    for r in positives:
        t = r.get("trips", {})
        print(f"  +{r['pr']:5} {r['concern']:15} strict={sorted(t.get('strict', {}))} gen={sorted(t.get('generalised', {}))} {r.get('error', '')} [{r.get('base_rule', '')[:60]}]")
    if a.write:
        out = os.path.join(REVIEW, "evidence", "backtest.json")
        with open(out, "w") as f:
            json.dump(ev, f, indent=2, ensure_ascii=False)
            f.write("\n")


if __name__ == "__main__":
    main()
