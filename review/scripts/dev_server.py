#!/usr/bin/env python3
"""Local server for the owner view: serves review/ and saves edits to the learned rules.

    python3 review/scripts/dev_server.py [--port 8000]

GET  anything under review/ (the page is /web/).
POST /api/rules   {"who": "<name>", "rules": [<rule>, ...]}
     Writes review/context/history.json. A rule is {id, concern, rule, sources, off?}. Rules are never
     deleted: a person turns one off instead, so old evidence that cites it still resolves. Every change
     is recorded on the rule (`edits`: who, when, and the fields as they were), and a new rule records
     `added_by`. Then confidence.py and render_web.py re-run, so scores, gates and the page use the edit.
     readability.json is not re-run here (it needs the target clone); its flags read rule text from the
     rules file at page time, and `npm run evidence` re-runs it.
POST /api/receipt {"key": "<dossier file name without .json>", "signed_by": "<name>", "picks": {"C-2283-03": "reject", ...}}
     Signs a dossier like `npm run sign`: sign_receipt.build_receipt checks the picks, the receipt is written to
     review/receipts/<branch>.json, each pick is appended to review/context/decisions.jsonl (not for the
     sample dossier), and render_web.py re-runs so the page shows the receipt.
POST /api/proposals {"who": "<name>", "id": "P-001", "action": "accept" | "reject"}
     Decides an open proposal in review/context/proposals.json. Only a proposal whose evidence gate is
     `eligible` can be accepted. A rule change (rule-off, rule-reword, new-rule) goes through the same
     apply() as a rules save, and its edit (or `added_by`) records the proposal id. A contract change
     (widen-contract, narrow-contract) is written to review/context/contract_overrides.json, which the
     dossiers' tripwires do not read. The proposal records who decided and when. Accepting re-runs
     confidence.py and render_web.py; rejecting re-runs render_web.py.

Only binds 127.0.0.1. Standard library only.
"""
import argparse, functools, http.server, json, os, re, subprocess, sys, threading
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sign_receipt  # noqa: E402

REVIEW = os.path.dirname(HERE)
HISTORY = os.path.join(REVIEW, "context", "history.json")
PROPOSALS = os.path.join(REVIEW, "context", "proposals.json")
OVERRIDES = os.path.join(REVIEW, "context", "contract_overrides.json")
PROJECT = os.path.join(REVIEW, "context", "project.json")
OVERRIDES_NOTE = ("Accepted learned contract changes. Opt-in: tripwires.py and the three dossiers do NOT read "
                  "this file; backtest/replay do.")
CONTRACT_KEYS = {"widen-contract": ("add", ("dir_segments", "file_names", "line_patterns")),
                 "narrow-contract": ("exclude", ("dir_segments", "file_names", "path_prefixes"))}
WRITE_LOCK = threading.Lock()
CONCERNS = ["compat-breaking", "public-api", "wire-format", "generated", "diagnostics", "targets", "security",
            "user-docs", "maintainability", "readability", "performance", "tests", "scope", "other"]
FIELDS = ("concern", "rule", "sources", "off")
MAX_BODY = 512 * 1024


def validate(rules):
    """Return a list of problems with the submitted rules (empty when they are fine)."""
    probs, ids = [], set()
    if not isinstance(rules, list) or not rules:
        return ["rules must be a non-empty list"]
    for i, r in enumerate(rules):
        rid = r.get("id") if isinstance(r, dict) else None
        if not isinstance(rid, str) or not re.fullmatch(r"H-\d{2,3}", rid):
            probs.append(f"rule {i + 1}: id must look like H-21"); continue
        if rid in ids:
            probs.append(f"{rid}: duplicate id")
        ids.add(rid)
        if r.get("concern") not in CONCERNS:
            probs.append(f"{rid}: concern must be one of {', '.join(CONCERNS)}")
        text = r.get("rule")
        if not isinstance(text, str) or not text.strip() or len(text) > 600:
            probs.append(f"{rid}: rule text must be 1-600 characters")
        src = r.get("sources", [])
        if not isinstance(src, list) or any(not isinstance(u, str) or not u.startswith("https://") for u in src):
            probs.append(f"{rid}: sources must be https links")
        if "off" in r and not isinstance(r["off"], bool):
            probs.append(f"{rid}: off must be true or false")
    return probs


def apply(doc, submitted, who):
    """Merge the submitted rules into the history document. Returns the ids that changed."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    old = {r["id"]: r for r in doc.get("rules", [])}
    new_ids = {r["id"] for r in submitted}
    gone = sorted(set(old) - new_ids)
    if gone:
        raise ValueError(f"rules cannot be deleted, turn them off instead: {', '.join(gone)}")
    changed, out = [], []
    for s in submitted:
        clean = {"concern": s["concern"], "rule": s["rule"].strip(),
                 "sources": [u.strip() for u in s.get("sources", []) if u.strip()], "off": bool(s.get("off"))}
        r = old.get(s["id"])
        if r is None:
            out.append({"id": s["id"], **{k: v for k, v in clean.items() if k != "off" or v},
                        "times_cited": 0, "added_by": {"who": who, "when": now}})
            changed.append(s["id"]); continue
        before = {k: r.get(k, False if k == "off" else None) for k in FIELDS if r.get(k, False if k == "off" else None) != clean[k]}
        r = dict(r)
        if before:
            for k in FIELDS:
                if k == "off" and not clean[k]:
                    r.pop("off", None)
                else:
                    r[k] = clean[k]
            r["edits"] = r.get("edits", []) + [{"who": who, "when": now, "before": before}]
            changed.append(s["id"])
        out.append(r)
    doc["rules"] = out
    return changed


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, doc):
    """Write through a temp file, so a crash never leaves half a file."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def rerun(*scripts):
    runs = []
    for cmd in scripts:
        p = subprocess.run([sys.executable, os.path.join(HERE, cmd[0]), *cmd[1:]], capture_output=True, text=True)
        runs.append({"cmd": " ".join(cmd), "ok": p.returncode == 0, "out": (p.stdout + p.stderr)[-2000:]})
    return runs


RESCORE = (["confidence.py", "--all", "--write"], ["render_web.py"])


def next_rule_id(rules):
    n = max([int(r["id"][2:]) for r in rules if re.fullmatch(r"H-\d+", str(r.get("id")))] or [0]) + 1
    return f"H-{n:02d}"


def rule_change(history, p, who):
    """Apply an accepted rule proposal to the history document through apply(). Returns the rule id."""
    kind, change, target = p["kind"], p.get("change") or {}, p.get("target") or {}
    rules = [{"id": r["id"], "concern": r.get("concern"), "rule": r.get("rule", ""), "sources": r.get("sources", []),
              "off": bool(r.get("off"))} for r in history.get("rules", [])]
    if kind == "new-rule":
        new = change.get("rule")
        if not isinstance(new, dict):
            raise ValueError(f"{p['id']}: change.rule must be {{concern, rule, sources}}")
        rid = next_rule_id(rules)
        rules.append({"id": rid, "concern": new.get("concern"), "rule": new.get("rule"),
                      "sources": new.get("sources") or [], "off": False})
    else:
        rid = target.get("rule")
        r = next((x for x in rules if x["id"] == rid), None)
        if r is None:
            raise ValueError(f"{p['id']}: no rule {rid} in history.json")
        if kind == "rule-off":
            if change.get("off") is not True:
                raise ValueError(f"{p['id']}: change must be {{\"off\": true}}")
            r["off"] = True
        else:
            if not isinstance(change.get("rule"), str):
                raise ValueError(f"{p['id']}: change.rule must be the new text")
            r["rule"] = change["rule"]
    probs = validate(rules)
    if probs:
        raise ValueError("; ".join(probs))
    changed = apply(history, rules, who)
    if changed != [rid]:
        raise ValueError(f"{p['id']}: nothing to change, {rid} already says that")
    r = next(x for x in history["rules"] if x["id"] == rid)
    (r["added_by"] if kind == "new-rule" else r["edits"][-1])["proposal_id"] = p["id"]
    return rid


def contract_change(overrides, contracts, p, who, when):
    """Record an accepted contract proposal in contract_overrides.json. Returns the contract id."""
    key, allowed = CONTRACT_KEYS[p["kind"]]
    contract = (p.get("target") or {}).get("contract")
    if contract not in contracts:
        raise ValueError(f"{p['id']}: no contract {contract!r} in project.json")
    spec = (p.get("change") or {}).get(key)
    if not isinstance(spec, dict) or not spec:
        raise ValueError(f"{p['id']}: change.{key} is missing")
    clean = {}
    for k, v in spec.items():
        if k not in allowed:
            raise ValueError(f"{p['id']}: change.{key}.{k} is not one of {', '.join(allowed)}")
        if not isinstance(v, list) or any(not isinstance(x, str) or not x for x in v):
            raise ValueError(f"{p['id']}: change.{key}.{k} must be a list of text")
        if k == "line_patterns":
            for x in v:
                try:
                    re.compile(x)
                except re.error as e:
                    raise ValueError(f"{p['id']}: bad line pattern {x!r}: {e}")
        if v:
            clean[k] = v
    if not clean:
        raise ValueError(f"{p['id']}: change.{key} is empty")
    overrides.setdefault("overrides", []).append(
        {"proposal_id": p["id"], "contract": contract, key: clean, "who": who, "when": when})
    return contract


def decide(body):
    """Handle POST /api/proposals. Returns (http code, response)."""
    who = str(body.get("who") or "").strip()[:80]
    pid, action = body.get("id"), body.get("action")
    if not who:
        return 400, {"ok": False, "error": "say who is deciding (your name)"}
    if action not in ("accept", "reject"):
        return 400, {"ok": False, "error": "action must be accept or reject"}
    doc = load_json(PROPOSALS)
    if not isinstance(doc, dict):
        return 404, {"ok": False, "error": "no proposals.json; run python3 review/scripts/propose.py --write"}
    p = next((x for x in doc.get("proposals") or [] if x.get("id") == pid), None)
    if p is None:
        return 404, {"ok": False, "error": f"no proposal {pid}"}
    if p.get("status", "open") != "open":
        return 409, {"ok": False, "error": f"{pid} is already {p.get('status')}"}
    if action == "accept" and not (p.get("gate") or {}).get("eligible"):
        return 409, {"ok": False, "error": f"{pid} did not pass the evidence gate, so it cannot be accepted"}
    when = now_utc()
    what = ""
    if action == "accept":
        if p.get("kind") in ("rule-off", "rule-reword", "new-rule"):
            history = load_json(HISTORY)
            try:
                rid = rule_change(history, p, who)
            except ValueError as e:
                return 400, {"ok": False, "error": str(e)}
            save_json(HISTORY, history)
            what = f"{p['kind']} {rid} in history.json"
        elif p.get("kind") in CONTRACT_KEYS:
            overrides = load_json(OVERRIDES) or {"note": OVERRIDES_NOTE, "overrides": []}
            contracts = {c.get("id") for c in (load_json(PROJECT) or {}).get("contracts") or []}
            try:
                cid = contract_change(overrides, contracts, p, who, when)
            except ValueError as e:
                return 400, {"ok": False, "error": str(e)}
            save_json(OVERRIDES, overrides)
            what = f"{p['kind']} {cid} in contract_overrides.json"
        else:
            return 400, {"ok": False, "error": f"{pid}: unknown kind {p.get('kind')!r}"}
    p["status"] = "accepted" if action == "accept" else "rejected"
    p["decided"] = {"who": who, "when": when, "proposal_id": pid}
    save_json(PROPOSALS, doc)
    runs = rerun(*RESCORE) if action == "accept" else rerun(["render_web.py"])
    return 200, {"ok": all(r["ok"] for r in runs), "runs": runs,
                 "summary": f"{pid} {p['status']}" + (f": {what}" if what else "")}


def sign(body):
    """Handle POST /api/receipt. Returns (http code, response)."""
    key = str(body.get("key") or body.get("branch") or "")
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", key) or ".." in key:
        return 400, {"ok": False, "error": "key must be a dossier name"}
    path = os.path.join(REVIEW, "dossier", key + ".json")
    if not os.path.isfile(path):
        return 404, {"ok": False, "error": f"no dossier {key}"}
    d = load_json(path)
    if key.startswith("_"):
        d["sample"] = True
    raw = body.get("picks")
    if not isinstance(raw, dict):
        return 400, {"ok": False, "error": "picks must map claim id to accept, reject or send back"}
    picks = {}
    for cid, v in raw.items():
        v = sign_receipt.PICKS.get(str(v).lower())
        if not v:
            return 400, {"ok": False, "error": f"bad pick for {cid}"}
        picks[cid] = v
    try:
        r = sign_receipt.build_receipt(d, str(body.get("signed_by") or "")[:80], picks)
        out, n = sign_receipt.write_receipt(d, r)
    except ValueError as e:
        return 400, {"ok": False, "error": f"not signed: {e}"}
    runs = rerun(["render_web.py"])
    return 200, {"ok": all(x["ok"] for x in runs), "receipt": r, "runs": runs, "logged": n,
                 "file": os.path.relpath(out, REVIEW)}


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # the page reloads after a save; without this the browser can show the old data.js from its cache
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def _json(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        routes = {"/api/receipt": sign, "/api/proposals": decide}
        if self.path not in routes and self.path != "/api/rules":
            return self._json(404, {"ok": False, "error": "not found"})
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > MAX_BODY:
            return self._json(400, {"ok": False, "error": "empty or too large"})
        try:
            body = json.loads(self.rfile.read(n))
        except ValueError:
            return self._json(400, {"ok": False, "error": "not JSON"})
        if not isinstance(body, dict):
            return self._json(400, {"ok": False, "error": "send a JSON object"})
        with WRITE_LOCK:  # one write at a time: the handlers read, change and rewrite files
            if self.path == "/api/rules":
                return self.save_rules(body)
            return self._json(*routes[self.path](body))

    def save_rules(self, body):
        who = str(body.get("who") or "").strip()[:80]
        if not who:
            return self._json(400, {"ok": False, "error": "say who is editing (your name)"})
        probs = validate(body.get("rules"))
        if probs:
            return self._json(400, {"ok": False, "error": "; ".join(probs)})
        doc = json.load(open(HISTORY, encoding="utf-8"))
        try:
            changed = apply(doc, body["rules"], who)
        except ValueError as e:
            return self._json(400, {"ok": False, "error": str(e)})
        if not changed:
            return self._json(200, {"ok": True, "changed": [], "summary": "nothing changed"})
        save_json(HISTORY, doc)
        runs = rerun(*RESCORE)
        return self._json(200, {"ok": all(r["ok"] for r in runs), "changed": changed, "runs": runs,
                                "summary": f"saved {len(changed)} rule(s): {', '.join(changed)}"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    handler = functools.partial(Handler, directory=REVIEW)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), handler)
    print(f"serving {REVIEW} on http://127.0.0.1:{a.port}/web/  (POST /api/rules, /api/receipt, /api/proposals)")
    srv.serve_forever()


if __name__ == "__main__":
    main()
