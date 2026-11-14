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

Only binds 127.0.0.1. Standard library only.
"""
import argparse, functools, http.server, json, os, re, subprocess, sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REVIEW = os.path.dirname(HERE)
HISTORY = os.path.join(REVIEW, "context", "history.json")
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


class Handler(http.server.SimpleHTTPRequestHandler):
    def _json(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path != "/api/rules":
            return self._json(404, {"ok": False, "error": "not found"})
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > MAX_BODY:
            return self._json(400, {"ok": False, "error": "empty or too large"})
        try:
            body = json.loads(self.rfile.read(n))
        except ValueError:
            return self._json(400, {"ok": False, "error": "not JSON"})
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
        with open(HISTORY, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
            f.write("\n")
        runs = []
        for cmd in (["confidence.py", "--all", "--write"], ["render_web.py"]):
            p = subprocess.run([sys.executable, os.path.join(HERE, cmd[0]), *cmd[1:]], capture_output=True, text=True)
            runs.append({"cmd": " ".join(cmd), "ok": p.returncode == 0, "out": (p.stdout + p.stderr)[-2000:]})
        return self._json(200, {"ok": all(r["ok"] for r in runs), "changed": changed, "runs": runs,
                                "summary": f"saved {len(changed)} rule(s): {', '.join(changed)}"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    handler = functools.partial(Handler, directory=REVIEW)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), handler)
    print(f"serving {REVIEW} on http://127.0.0.1:{a.port}/web/  (rule edits: POST /api/rules)")
    srv.serve_forever()


if __name__ == "__main__":
    main()
