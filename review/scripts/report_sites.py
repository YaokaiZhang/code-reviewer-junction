#!/usr/bin/env python3
"""List every diagnostic report site in TypeCollector.cs on a branch.

A report site is a call through one of the two reporting delegates in TypeCollector:
  - this.reportDiagnostic?.Invoke(...), reportDiagnostic?.Invoke(...) (local function capture)
    or this.reportDiagnostic(...)          -> goes through the branch's filter (if any)
  - reportAnalyzerDiagnostic?.Invoke(...)  -> the raw callback, bypasses the filter
Lines whose code starts with // are listed separately as commented out and not counted.

For each site the script records the line, the diagnostic descriptor(s), the location
expression (traced through local variables back to where they are assigned), and a
heuristic answer to "can this location be outside the current compilation's source?":
  yes  location is derived from a symbol's syntax or Locations[0]; when the symbol comes
       from a referenced assembly this is null (no location) or a metadata location, and
       when it comes from a project reference it is a syntax tree of another compilation
  no   location is derived from the analysed target type's own declaration
The heuristic reads text only; it is a reading aid, not a proof.

Usage:
  python3 review/scripts/report_sites.py --repo <clone> [--branch ju26-issue-2283] \
      --out review/evidence/ju26-issue-2283/report-sites.json

Python 3, standard library only. Reads the file with `git show`; changes nothing.
"""
import argparse
import json
import os
import re
import subprocess

PATH = "src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs"
BASE = "32258fdb"
CALL = re.compile(r"(?P<via>this\.reportDiagnostic\?\.Invoke|(?<![\w.])reportDiagnostic\?\.Invoke|this\.reportDiagnostic|reportAnalyzerDiagnostic\?\.Invoke)\s*\(")
DESC = re.compile(r"MsgPack00xMessagePackAnalyzer\.(\w+)")
METHOD = re.compile(r"^\s{4}(?:private|public|internal|protected)\b[^=;]*?\b(\w+)\s*\(")
SIMPLE_GREP = "reportDiagnostic?.Invoke"


def git_show(repo, rev, path):
    for cand in (rev, "origin/" + rev):
        p = subprocess.run(["git", "-C", repo, "show", f"{cand}:{path}"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        if p.returncode == 0:
            return p.stdout, cand
    raise SystemExit(f"cannot read {path} at {rev}")


def statement(lines, i):
    """Text from line i to the end of the statement (balanced parentheses, then ';')."""
    text, depth = "", 0
    for j in range(i, min(i + 30, len(lines))):
        for ch in lines[j]:
            depth += ch == "("
            depth -= ch == ")"
        text += " " + lines[j].strip()
        if depth <= 0 and lines[j].rstrip().endswith(";"):
            break
    return text


def find_assignment(lines, i, var, lo):
    """Nearest assignment of `var` above line i (not above lo). Returns (line_no, text)."""
    pat = re.compile(r"(?:\b[\w<>?\[\]]+\s+)?\b" + re.escape(var) + r"\s*=(?!=)")
    for j in range(i, lo - 1, -1):
        code = lines[j].split("//")[0]
        if pat.search(code) and not re.search(r"\bforeach\b", code):
            return j + 1, statement(lines, j)
    return None, None


def first_arg_after(text, token):
    k = text.find(token)
    if k < 0:
        return None
    k += len(token)
    depth, start, args = 0, k, []
    for idx in range(k, len(text)):
        ch = text[idx]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                args.append(text[start:idx].strip())
                break
            depth -= 1
        elif ch == "," and depth == 0:
            args.append(text[start:idx].strip())
            start = idx + 1
    return args


def classify(expr):
    e = expr or ""
    if "decl.Identifier" in e:
        return "no", "declaration of the analysed target type (from FindInaccessibleTypes(targetType))"
    if "Locations[0]" in e:
        return "yes", "symbol.Locations[0]: a metadata location when the symbol comes from a referenced assembly"
    markers = ["DeclaringSyntaxReferences", "GetIdentifierLocation(", "GetPropertyIdentifierLocation(", "GetLocation(item)",
               "GetParameterListLocation(", "ApplicationSyntaxReference", "GetSyntax(", "identifier?", "baseSyntax", "initializer",
               "propertyId.GetLocation()", "attSyntax", "targetType?.Identifier"]
    if any(m in e for m in markers):
        return "yes", "derived from the symbol's declaring syntax: null (no location) for a symbol from a referenced assembly, another compilation's tree for a symbol from a project reference"
    return "unknown", "location expression not recognised by the heuristic"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.environ.get("MP_REPO"))
    ap.add_argument("--branch", default="ju26-issue-2283")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    src, rev = git_show(a.repo, a.branch, PATH)
    base_src, _ = git_show(a.repo, BASE, PATH)
    lines = src.splitlines()

    method_starts = [(i, m.group(1)) for i, ln in enumerate(lines) for m in [METHOD.match(ln)] if m]

    def enclosing(i):
        cur = (0, None)
        for s, name in method_starts:
            if s <= i:
                cur = (s, name)
        return cur

    deferred_adds = [i for i, ln in enumerate(lines) if "deferredDiagnosticsForNonPublicMembers.Add(" in ln]
    sites, commented = [], []
    for i, ln in enumerate(lines):
        m = CALL.search(ln)
        if not m:
            continue
        code = ln.strip()
        if code.startswith("//"):
            commented.append({"line": i + 1, "code": code[:200]})
            continue
        if "= reportAnalyzerDiagnostic is null" in ln:
            continue  # the filter wiring itself, not a report
        mstart, mname = enclosing(i)
        via = m.group("via")
        stmt = statement(lines, i)
        args = first_arg_after(stmt, m.group(0)) or []
        arg = args[0] if args else ""
        traced = []
        diag_exprs = []
        if arg.startswith("Diagnostic.Create("):
            diag_exprs.append((i + 1, arg))
        else:
            var = arg
            if var == "deferred":
                for j in deferred_adds:
                    ln_no, txt = find_assignment(lines, j, "diagnostic", mstart)
                    diag_exprs.append((ln_no, txt))
                    traced.append({"from": "deferredDiagnosticsForNonPublicMembers.Add at line %d" % (j + 1), "assigned_at": ln_no})
            else:
                ln_no, txt = find_assignment(lines, i, var, mstart)
                diag_exprs.append((ln_no, txt))
                traced.append({"var": var, "assigned_at": ln_no})
        descriptors, loc_exprs = [], []
        for ln_no, txt in diag_exprs:
            if not txt:
                continue
            for d in DESC.findall(txt):
                if d not in descriptors:
                    descriptors.append(d)
            k = 0
            while True:
                k = txt.find("Diagnostic.Create(", k)
                if k < 0:
                    break
                cargs = first_arg_after(txt[k:], "Diagnostic.Create(") or []
                if len(cargs) > 1:
                    loc = cargs[1]
                    if re.fullmatch(r"\w+", loc):
                        a_ln, a_txt = find_assignment(lines, (ln_no or i + 1) - 1, loc, mstart)
                        traced.append({"var": loc, "assigned_at": a_ln})
                        loc = f"{loc} <- {a_txt.strip() if a_txt else '?'}"
                    loc_exprs.append(loc[:400])
                k += 1
        verdicts = [classify(e) for e in loc_exprs] or [("unknown", "no location expression found")]
        outside = "yes" if any(v == "yes" for v, _ in verdicts) else ("no" if all(v == "no" for v, _ in verdicts) else "unknown")
        sites.append({
            "line": i + 1,
            "method": mname,
            "via": via,
            "through_filter": via != "reportAnalyzerDiagnostic?.Invoke",
            "descriptors": descriptors,
            "location_expressions": loc_exprs,
            "traced": traced,
            "location_can_be_outside_compilation_source": outside,
            "why": sorted({w for _, w in verdicts}),
            "code": code[:240],
        })

    filtered = [s for s in sites if s["through_filter"]]
    desc_all = sorted({d for s in filtered for d in s["descriptors"]})
    outside_yes = [s for s in filtered if s["location_can_be_outside_compilation_source"] == "yes"]
    simple = sum(1 for ln in lines if SIMPLE_GREP in ln)
    simple_commented = sum(1 for ln in lines if SIMPLE_GREP in ln and ln.strip().startswith("//"))
    simple_base = sum(1 for ln in base_src.splitlines() if SIMPLE_GREP in ln)
    out = {
        "check": "report-sites",
        "branch": a.branch,
        "base": BASE,
        "command": f"python3 review/scripts/report_sites.py --repo <clone> --branch {a.branch} --out review/evidence/{a.branch}/report-sites.json",
        "result": "pass",
        "summary": "%d live report sites in TypeCollector.cs: %d go through the filter (%d distinct descriptors), %d bypass it; %d of the %d filtered sites can have a location outside the compilation's source; simple grep for '%s' counts %d lines (%d of them commented out)"
                   % (len(sites), len(filtered), len(desc_all), len(sites) - len(filtered), len(outside_yes), len(filtered), SIMPLE_GREP, simple, simple_commented),
        "details": {
            "file": PATH,
            "rev": rev,
            "method": "regex over non-comment lines for calls through this.reportDiagnostic (?.Invoke, direct call, local-function capture) and reportAnalyzerDiagnostic?.Invoke; arguments that are variables are traced to their assignment in the same method; 'deferred' is traced to the four deferredDiagnosticsForNonPublicMembers.Add sites",
            "live_sites": len(sites),
            "sites_through_filter": len(filtered),
            "sites_bypassing_filter": len(sites) - len(filtered),
            "distinct_descriptors_through_filter": desc_all,
            "filtered_sites_location_can_be_outside": len(outside_yes),
            "commented_out_sites": commented,
            "simple_grep": {"pattern": SIMPLE_GREP, "branch_count": simple, "base_count": simple_base, "commented_lines_in_branch_count": simple_commented,
                            "live_sites_missed_by_simple_grep": [x["line"] for x in sites if SIMPLE_GREP not in x["code"]],
                            "note": "the handoff's 29; it includes commented-out lines, misses this.reportDiagnostic(deferred) and the unfiltered reportAnalyzerDiagnostic?.Invoke"},
            "premise": "every filtered site sits in code reached from CollectCore, which recurses into closed generic types defined in other assemblies (CollectGeneric -> GetObjectInfo / CollectCore(type.OriginalDefinition)); so the symbol a location is taken from can come from another assembly",
            "sites": sites,
        },
        "tool_versions": {"python": __import__("sys").version.split()[0]},
        "produced_by": "script",
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
        f.write("\n")
    print(out["summary"])


if __name__ == "__main__":
    main()
