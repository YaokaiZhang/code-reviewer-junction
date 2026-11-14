#!/usr/bin/env python3
"""Template check: regenerate the T4 template classes with dotnet-t4 and compare with the committed .cs.

Visual Studio's TextTemplatingFilePreprocessor (which produced the committed .cs files) and
dotnet-t4 lay out the generated C# differently (header, CodeDOM formatting, base class region,
line wrapping of long string literals). A byte diff is therefore meaningless. This script compares
the *behaviour* of TransformText() instead:

  * take the TransformText() body from both files,
  * drop whitespace outside string literals,
  * decode and merge string literals ("a" + "b" -> one literal; adjacent this.Write("..") calls merged),
  * drop `this.GenerationEnvironment = null;` (dotnet-t4 adds it, VS does not),
  * read verbatim literals (@"...", which dotnet-t4 emits for long multi-line text) with their raw CRLFs.

Equal normalised bodies mean both write the same text for the same inputs.
The .tt and the committed .cs are both taken with CRLF line endings, as an eol=crlf checkout has them.
Runs on base too, to show the method reproduces the untouched base templates (calibration).

    python3 review/scripts/template_check.py --repo <clone> --branch ju26-issue-2297 --t4 <path to t4> [--write]
"""
import argparse, json, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REVIEW = os.path.dirname(HERE)
BASE = "32258fdb"


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True).stdout


def git_bytes(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True).stdout


def body(cs):
    i = cs.index("TransformText()")
    i = cs.index("{", i) + 1
    j = cs.index("return this.GenerationEnvironment.ToString();", i)
    return cs[i:j]


def decode(lit):
    return bytes(lit, "utf-8").decode("unicode_escape") if "\\" in lit else lit


def normalise(src):
    """Return a list of tokens: ('s', decoded string) or ('c', code char run without whitespace)."""
    out, i, code = [], 0, []
    while i < len(src):
        ch = src[i]
        if ch == "@" and src[i + 1:i + 2] == '"':
            j, buf = i + 2, []
            while True:
                if src[j] == '"' and src[j + 1:j + 2] == '"':
                    buf.append('"'); j += 2
                elif src[j] == '"':
                    break
                else:
                    buf.append(src[j]); j += 1
            if code:
                out.append(("c", "".join(code))); code = []
            out.append(("s", "".join(buf)))
            i = j + 1
        elif ch == '"':
            j, buf = i + 1, []
            while src[j] != '"':
                if src[j] == "\\":
                    buf.append(src[j:j + 2]); j += 2
                else:
                    buf.append(src[j]); j += 1
            if code:
                out.append(("c", "".join(code))); code = []
            out.append(("s", decode("".join(buf))))
            i = j + 1
        elif ch.isspace():
            i += 1
        else:
            code.append(ch); i += 1
    if code:
        out.append(("c", "".join(code)))
    # merge "a" + "b"
    merged = []
    for t in out:
        if merged and len(merged) >= 2 and t[0] == "s" and merged[-1] == ("c", "+") and merged[-2][0] == "s":
            merged.pop(); s = merged.pop()
            merged.append(("s", s[1] + t[1]))
        else:
            merged.append(t)
    # serialise; then merge adjacent Write calls and drop dotnet-t4's reset line
    text = "".join(("\x00" + json.dumps(v) + "\x00") if k == "s" else v for k, v in merged)
    text = text.replace("this.GenerationEnvironment=null;", "")
    pat = re.compile(r'this\.Write\(\x00("(?:[^"\\]|\\.)*")\x00\);this\.Write\(\x00("(?:[^"\\]|\\.)*")\x00\);')
    while True:
        m = pat.search(text)
        if not m:
            break
        text = text[:m.start()] + 'this.Write(\x00' + json.dumps(json.loads(m.group(1)) + json.loads(m.group(2))) + '\x00);' + text[m.end():]
    return text


def check(repo, rev, tt_path, t4, tmp, control_cs=None):
    control_differs = None
    cs_path = tt_path[:-3] + ".cs"
    tt = git_bytes(repo, "show", f"{rev}:{tt_path}").replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    # the index stores LF; eol=crlf checkouts (every OS, per .gitattributes) have CRLF, which matters inside @"" literals
    committed = git_bytes(repo, "show", f"{rev}:{cs_path}").decode("utf-8-sig").replace("\r\n", "\n").replace("\n", "\r\n")
    ns = re.search(r"^namespace\s+([\w.]+)", committed, re.M).group(1)
    cls = re.search(r"public partial class (\w+)", committed).group(1)
    d = os.path.join(tmp, rev.replace("/", "_"))
    os.makedirs(d, exist_ok=True)
    tin = os.path.join(d, os.path.basename(tt_path))
    tout = tin[:-3] + ".t4.cs"
    open(tin, "wb").write(tt)
    p = subprocess.run([t4, "-c", f"{ns}.{cls}", "-o", tout, tin], capture_output=True, text=True)
    if p.returncode != 0:
        return {"template": tt_path, "rev": rev, "status": "error", "t4_output": (p.stdout + p.stderr)[-1500:]}
    regenerated = open(tout, encoding="utf-8-sig", newline="").read()
    a, b = normalise(body(committed)), normalise(body(regenerated))
    if control_cs is not None:
        # negative control: the other revision's committed .cs must NOT match this regeneration
        c = control_cs.decode("utf-8-sig").replace("\r\n", "\n").replace("\n", "\r\n")
        control_differs = normalise(body(c)) != b
    res = {"template": tt_path, "rev": rev, "class": f"{ns}.{cls}", "status": "match" if a == b else "differ",
           "normalised_length": len(a)}
    if control_cs is not None:
        res["negative_control_base_cs_differs"] = control_differs
    if a != b:
        k = next((i for i in range(min(len(a), len(b))) if a[i] != b[i]), min(len(a), len(b)))
        res["first_difference"] = {"committed": a[max(0, k - 80):k + 120].replace("\x00", ""),
                                   "regenerated": b[max(0, k - 80):k + 120].replace("\x00", "")}
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.environ.get("MP_REPO"), required=os.environ.get("MP_REPO") is None)
    ap.add_argument("--branch", required=True)
    ap.add_argument("--t4", required=True)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    head = f"origin/{a.branch}"
    tts = sorted(p for p in git(a.repo, "diff", "--name-only", f"{BASE}..{head}").splitlines() if p.endswith(".tt"))
    tmp = tempfile.mkdtemp(prefix="t4check-")
    results = [check(a.repo, BASE, tt, a.t4, tmp) for tt in tts]
    results += [check(a.repo, head, tt, a.t4, tmp, git_bytes(a.repo, "show", f"{BASE}:{tt[:-3]}.cs")) for tt in tts]
    controls = sum(1 for r in results if r.get("negative_control_base_cs_differs"))
    by = lambda rev, st: sum(1 for r in results if r["rev"] == rev and r["status"] == st)
    nb, nh = by(BASE, "match"), by(head, "match")
    errs = sum(1 for r in results if r["status"] == "error")
    ok = errs == 0 and nb == len(tts) and nh == len(tts) and controls == len(tts)
    summary = (f"dotnet-t4 regeneration of {len(tts)} templates, TransformText() compared after normalising layout: "
               f"base {nb} of {len(tts)} match, branch {nh} of {len(tts)} match, {errs} t4 errors; "
               f"negative control: branch regeneration differs from base .cs for {controls} of {len(tts)}")
    t4v = subprocess.run([a.t4, "-h"], capture_output=True, text=True).stdout.splitlines()
    ev = {
        "check": "template-regeneration",
        "branch": a.branch,
        "base": BASE,
        "command": f"python3 review/scripts/template_check.py --repo $MP_REPO --branch {a.branch} --t4 <dotnet-t4 3.0.0 t4> --write",
        "result": "pass" if ok else ("error" if errs else "fail"),
        "summary": summary,
        "details": {
            "templates": tts,
            "base_matching": nb, "branch_matching": nh, "t4_errors": errs, "negative_controls_differing": controls,
            "method": "TransformText() body compared after dropping whitespace outside string literals, merging string literals and adjacent Write calls, and dropping `this.GenerationEnvironment = null;`; .tt fed with CRLF line endings. Header comment, CodeDOM layout and the base-class region are ignored.",
            "limits": "Not a byte-for-byte reproduction of Visual Studio's TextTemplatingFilePreprocessor output; equality is of emitted text, not of file bytes.",
            "results": results,
        },
        "tool_versions": {"dotnet-t4": next((l for l in t4v if "version" in l.lower()), "unknown"),
                          "python": sys.version.split()[0]},
        "produced_by": "script",
    }
    if a.write:
        out = os.path.join(REVIEW, "evidence", a.branch, "template-regeneration.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(ev, f, indent=2, ensure_ascii=False); f.write("\n")
        print("wrote", out)
    print(ev["result"], summary)
    for r in results:
        if r["status"] != "match":
            print(json.dumps(r, indent=1)[:1500])


if __name__ == "__main__":
    main()
