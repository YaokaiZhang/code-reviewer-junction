#!/usr/bin/env python3
"""Replay: re-run the recorded evidence commands on a clean machine and say, per evidence file,
whether the fresh result matches the committed one. confidence.py reads the result
(evidence/<branch>/replay.json -> details.files) for its +5 / -30 replay signal.

Two steps, run against a COPY of this repo (so --write outputs never touch the committed files):

    python3 review/scripts/replay.py prepare --copy <copy>
        deletes every script-made evidence file in the copy (keeps hand-made ones, which some
        collectors read or rewrite) and writes the marker <copy>/.work/replay-start.
    # in the copy: bash review.sh evidence; bash review.sh tests; other recorded commands ...
    python3 review/scripts/replay.py compare --copy <copy> --all [--write]
        compares the copy's evidence with this repo's and writes evidence/<branch>/replay.json here.

Per file:
  match       the copy re-made it, and `result` and the normalised `summary` are equal
  mismatch    the copy re-made it, and `result` or the normalised `summary` differs (both kept)
  not re-run  produced_by hand; or derived from the replay itself (confidence.json); or the copy
              did not re-make it (file absent, or older than the replay-start marker)

Normalised before comparing summaries (NORMALISE below): durations ("12.3s", "4 ms", "2 min"),
temp/scratch paths (/tmp/..., /var/folders/..., anything under a .work/ dir), tool version
strings ("8.0.402", "git version 2.43.0"), runs of whitespace.
"""
import argparse, datetime, json, os, platform, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REVIEW = os.path.dirname(HERE)
BRANCHES = ["ju26-issue-2234", "ju26-issue-2283", "ju26-issue-2297"]
DERIVED = {"confidence.json", "replay.json"}
MARKER = os.path.join(".work", "replay-start")

NORMALISE = [
    ("duration", r"\b\d+(?:\.\d+)?\s*(?:ms|s|sec|secs|seconds?|min|mins|minutes?)\b", "<dur>"),
    ("temp path", r"(?:/tmp|/var/folders|/private/var)/\S*|\S*/\.work/\S*", "<path>"),
    ("tool version", r"\b(?:git version |dotnet |SDK |version )?\d+\.\d+\.\d+(?:[.+-][\w.+-]*)?\b", "<ver>"),
    ("whitespace", r"\s+", " "),
]


def norm(s):
    s = s or ""
    for _, pat, rep in NORMALISE:
        s = re.sub(pat, rep, s)
    return s.strip()


def load(p):
    try:
        return json.load(open(p))
    except (OSError, ValueError):
        return None


def out(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True).stdout.strip() or None
    except OSError:
        return None


def prepare(copy):
    ev = os.path.join(copy, "review", "evidence")
    gone = []
    for b in BRANCHES:
        d = os.path.join(ev, b)
        for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
            e = load(os.path.join(d, f))
            if f.endswith(".json") and f not in DERIVED and e and e.get("produced_by") == "script":
                os.remove(os.path.join(d, f)); gone.append(f"{b}/{f}")
    os.makedirs(os.path.join(copy, ".work"), exist_ok=True)
    with open(os.path.join(copy, MARKER), "w") as f:
        f.write(datetime.datetime.now(datetime.timezone.utc).isoformat() + "\n")
    print(f"deleted {len(gone)} script-made evidence files in the copy; marker written")


def machine(copy):
    dn = os.path.join(copy, ".work", "dotnet", "dotnet")
    dn = dn if os.path.exists(dn) else shutil.which("dotnet")
    return {
        "os": f"{platform.system()} {platform.release()} {platform.machine()}",
        "dotnet --version": out([dn, "--version"]) if dn else None,
        "git --version": out(["git", "--version"]),
        "python": platform.python_version(),
        "date": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    }


def compare(copy, branch, since, mach, extra):
    files, diffs = {}, {}
    real_dir = os.path.join(REVIEW, "evidence", branch)
    copy_dir = os.path.join(copy, "review", "evidence", branch)
    for f in sorted(os.listdir(real_dir)):
        if not f.endswith(".json") or f == "replay.json":
            continue
        old = load(os.path.join(real_dir, f)) or {}
        cp = os.path.join(copy_dir, f)
        new = load(cp)
        fresh = new is not None and os.path.getmtime(cp) > since
        if old.get("produced_by") == "hand":
            files[f] = "not re-run"
            reason = "produced_by hand"
        elif f in DERIVED:
            files[f] = "not re-run"
            reason = "derived from the replay itself"
        elif not fresh:
            files[f] = "not re-run"
            reason = "the copy did not re-make it"
        else:
            same = old.get("result") == new.get("result") and norm(old.get("summary")) == norm(new.get("summary"))
            files[f] = "match" if same else "mismatch"
            reason = None
        d = {"status": files[f]}
        if reason:
            d["why"] = reason
        if fresh:
            d |= {"committed": {"result": old.get("result"), "summary": old.get("summary")},
                  "replayed": {"result": new.get("result"), "summary": new.get("summary")}}
            if files[f] == "not re-run":
                d["note"] = "the copy re-made it, shown for information only"
        diffs[f] = d
    n = {k: sum(1 for v in files.values() if v == k) for k in ("match", "mismatch", "not re-run")}
    return {
        "check": "replay",
        "branch": branch,
        "base": "32258fdb",
        "command": f"python3 review/scripts/replay.py compare --copy <copy> --branch {branch} --write"
                   "   (after: replay.py prepare --copy <copy>; in the copy: bash review.sh evidence; "
                   "bash review.sh tests; tripwires.py and the other recorded script commands)",
        "result": "fail" if n["mismatch"] else "pass",
        "summary": f"{n['match']} match, {n['mismatch']} mismatch, {n['not re-run']} not re-run "
                   f"of {len(files)} evidence files re-checked on a clean machine",
        "details": {"files": files, "counts": n, "compared": diffs, "machine": mach,
                    "normalised": [{"what": w, "pattern": p, "replacement": r} for w, p, r in NORMALISE],
                    "compared_fields": ["result", "summary (normalised)"]} | extra,
        "tool_versions": {"python": platform.python_version(), "git": mach.get("git --version"),
                          "dotnet_sdk": mach.get("dotnet --version")},
        "produced_by": "script",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["prepare", "compare"])
    ap.add_argument("--copy", required=True, help="the copy of this repo the commands were re-run in")
    ap.add_argument("--branch", action="append")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--notes", help="JSON file of extra details to store (e.g. run times, blocked steps)")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    copy = os.path.abspath(a.copy)
    if a.step == "prepare":
        return prepare(copy)
    marker = os.path.join(copy, MARKER)
    if not os.path.exists(marker):
        sys.exit(f"no {marker}: run `replay.py prepare --copy {a.copy}` before re-running the commands")
    since = os.path.getmtime(marker)
    mach = machine(copy)
    extra = json.load(open(a.notes)) if a.notes else {}
    for b in BRANCHES if a.all else (a.branch or ap.error("--branch or --all")):
        ev = compare(copy, b, since, mach, extra)
        print(f"{b}: {ev['summary']}")
        for f, d in ev["details"]["compared"].items():
            if d["status"] == "mismatch":
                print(f"  MISMATCH {f}\n    committed: {d['committed']}\n    replayed:  {d['replayed']}")
        if a.write:
            p = os.path.join(REVIEW, "evidence", b, "replay.json")
            with open(p, "w") as f:
                json.dump(ev, f, indent=2); f.write("\n")
            print(f"  wrote {os.path.relpath(p, os.path.dirname(REVIEW))}")


if __name__ == "__main__":
    main()
