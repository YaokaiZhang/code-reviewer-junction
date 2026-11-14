#!/usr/bin/env python3
"""Check the pseudo-code cards for new tests against the real code, and attach the real results.

The reviewing agent writes review/explain/<branch>.json: one card per new test, each step a plain
sentence with `backticked` tokens and the line range it summarises. The agent can be wrong, so this
script checks every step and never takes a result from the card:

  step check    the cited lines exist at the branch head, lie inside the test or a listed helper, and
                every `backticked` token appears in them (whitespace ignored). A step that fails is
                shown as unverified on the page.
  results       read from the evidence files the card names (old-vs-new test runs, regen runs), never
                from the card: before the change, after the change, and any extra run (e.g. one part
                undone).
  code          the test's and helpers' real lines, so the page can show them next to the pseudo-code.

    python3 review/scripts/explain_check.py --repo <clone> --branch ju26-issue-2283 [--write]

Writes evidence/<branch>/explain-check.json. Standard library only.
"""
import argparse, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REVIEW = os.path.dirname(HERE)
TOKEN = re.compile(r"`([^`]+)`")


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True).stdout


def squash(s):
    return re.sub(r"\s+", "", s)


def norm_outcome(v):
    v = (v or "").lower()
    return "pass" if v in ("passed", "pass") else "fail" if v in ("failed", "fail") else v or "unknown"


def results_for(card, branch):
    """Rows {run, outcome, message, source} from the evidence files the card names."""
    rows, name = [], card["test"]
    for rel in card.get("results_from", []):
        p = os.path.join(REVIEW, rel)
        if not os.path.exists(p):
            rows.append({"run": "?", "outcome": "missing", "message": f"{rel} not found", "source": rel})
            continue
        ev = json.load(open(p))
        det = ev.get("details", {})
        for m in det.get("methods", []):              # old_vs_new_tests.py and dropped_warning_test
            if m.get("method") != name:
                continue
            for side in ("base", "branch", "nofilter"):
                if side not in m:
                    continue
                v = m[side]
                outcome = norm_outcome(v.get("outcome") if isinstance(v, dict) else v)
                msg = v.get("message") if isinstance(v, dict) else m.get(f"{side}_message")
                diags = v.get("unexpected_diagnostics") if isinstance(v, dict) else None
                if diags:
                    msg = "; ".join(d[:140] for d in diags[:2])
                rows.append({"run": {"base": "before the change", "branch": "after the change",
                                     "nofilter": "after, with the filter line undone"}[side],
                             "outcome": outcome, "message": (msg or "")[:300], "source": rel,
                             "produced_by": ev.get("produced_by")})
        for r in det.get("runs", []):                  # regen_check.py
            takes = [x.get("path") for x in r.get("modifiers", []) if x.get("modifier") == "take-from-branch"]
            has_test = r.get("rev") == f"origin/{branch}" or card["file"] in takes
            if not has_test or not r.get("total"):
                continue
            fail = next((f for f in r.get("failures", []) if f.get("test", "").split(".")[-1] == name), None)
            label = {"base-newtests": "before the change (new test copied onto base)",
                     "branch": "after the change"}.get(r["label"], r["label"])
            rows.append({"run": label, "outcome": "fail" if fail else "pass",
                         "message": (fail or {}).get("message", "")[:300], "source": rel,
                         "produced_by": ev.get("produced_by")})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.environ.get("MP_REPO"), required=os.environ.get("MP_REPO") is None)
    ap.add_argument("--branch", required=True)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    spec = json.load(open(os.path.join(REVIEW, "explain", f"{a.branch}.json")))
    rev = f"origin/{a.branch}"
    head = git(a.repo, "rev-parse", "--short=8", rev).strip()
    src = {}

    def lines_of(path):
        if path not in src:
            src[path] = git(a.repo, "show", f"{rev}:{path}").split("\n")
        return src[path]

    cards, bad_steps, n_steps = [], 0, 0
    for c in spec["cards"]:
        spans = [(c["file"], c["span"])] + [(h["file"], h["span"]) for h in c.get("helpers", [])]
        code = {}
        for f, (lo, hi) in spans:
            L = lines_of(f)
            code.setdefault(f, {}).update({str(i): L[i - 1] for i in range(lo, min(hi, len(L)) + 1)})
        method_found = any(c["test"] in code[c["file"]].get(str(i), "")
                           for i in range(c["span"][0], c["span"][1] + 1))
        steps = []
        for s in c["steps"]:
            n_steps += 1
            f = s.get("file", c["file"])
            lo, hi = s["lines"][0], s["lines"][-1]
            problems = []
            inside = any(f == sf and sp[0] <= lo and hi <= sp[1] for sf, sp in spans)
            if not inside:
                problems.append("lines outside the test and its helpers")
            text = squash("".join(lines_of(f)[lo - 1:hi]))
            missing = [t for t in TOKEN.findall(s["text"]) if squash(t) not in text]
            if missing:
                problems.append("not in the cited lines: " + ", ".join(missing))
            if not TOKEN.findall(s["text"]):
                problems.append("no token to check")
            bad_steps += bool(problems and problems != ["no token to check"])
            steps.append(dict(s, file=f, verified=not problems, problems=problems,
                              tokens=TOKEN.findall(s["text"])))
        res = results_for(c, a.branch)
        before = [r for r in res if r["run"].startswith("before")]
        after = [r for r in res if r["run"] == "after the change"]
        flips = bool(before) and all(r["outcome"] == "fail" for r in before) and bool(after) and all(r["outcome"] == "pass" for r in after)
        verdict = ("fails before, passes after: it tests the change" if flips else
                   "passes before the change too: it does not test the change" if before and all(r["outcome"] == "pass" for r in before) else
                   "did not run here" if all(r["outcome"] not in ("pass", "fail") for r in res) else
                   "see results")
        cards.append(dict(c, method_found=method_found, steps=steps, results=res, flips=flips,
                          verdict=verdict, code=code))

    unverified = [f"{c['id']} {s['op']}" for c in cards for s in c["steps"] if not s["verified"]]
    flips = sum(c["flips"] for c in cards)
    ev = {
        "check": "explain-check",
        "branch": a.branch,
        "base": "32258fdb",
        "head": head,
        "command": f"python3 review/scripts/explain_check.py --repo $MP_REPO --branch {a.branch} --write",
        "result": "pass" if not unverified and all(c["method_found"] for c in cards) else "fail",
        "provides": ["count"],
        "summary": f"{len(cards)} new tests explained in {n_steps} steps; {n_steps - len(unverified)} of {n_steps} steps "
                   f"match the cited code; {flips} of {len(cards)} tests fail before the change and pass after",
        "details": {"cards": cards, "unverified_steps": unverified, "pseudo_code_by": spec.get("produced_by", "agent"),
                    "spec": f"explain/{a.branch}.json"},
        "tool_versions": {"git": git(a.repo, "--version").strip(), "python": sys.version.split()[0]},
        "produced_by": "script",
    }
    print(ev["summary"])
    for u in unverified:
        c = next(x for x in cards if u.startswith(x["id"]))
        print("  unverified:", u, [s["problems"] for s in c["steps"] if not s["verified"]])
    if a.write:
        with open(os.path.join(REVIEW, "evidence", a.branch, "explain-check.json"), "w") as f:
            json.dump(ev, f, indent=2, ensure_ascii=False)
            f.write("\n")


if __name__ == "__main__":
    main()
