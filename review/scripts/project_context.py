#!/usr/bin/env python3
"""Project context: what this repo promises its users, read from the repo itself at base.

The diff alone cannot say whether a change breaks a promise. This collects the
promises (contracts), where each one is written down, and who maintains it:

  diagnostics   documented analyzer rules (doc/analyzers/*.md + release tracking file),
                and the first released tag that documents each rule
  public-api    PublicAPI.Shipped/Unshipped.txt per target framework
  generated     code the generator emits into the consumer's own assembly
                (README + the resolver template: a user-declared partial class)
  targets       target frameworks the library builds for
  wire-format   serializer reader/writer/formatter sources
  security      SECURITY.md and MessagePackSecurity
  release       version.json (pre-release or not, semver)
  user-docs     README.md and doc/

Each contract has `paths` (and optional `line_patterns`) that tripwires.py matches
against a diff, and `maintainers`: commit counts per author on those paths at base.

    python3 review/scripts/project_context.py --repo <clone> [--write]

Writes review/context/project.json. Standard library only.
"""
import argparse, json, os, re, subprocess, sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REVIEW = os.path.dirname(HERE)
BASE = "32258fdb"


def git(repo, *args, ok=False):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if r.returncode and not ok:
        sys.exit(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout if not r.returncode else ""


def show(repo, path):
    return git(repo, "show", f"{BASE}:{path}", ok=True)


def files(repo):
    return git(repo, "ls-tree", "-r", "--name-only", BASE).splitlines()


def line_of(text, needle):
    for i, l in enumerate(text.splitlines(), 1):
        if needle in l:
            return i
    return None


def maintainers(repo, paths, top=3):
    out = git(repo, "log", "--format=%an", BASE, "--", *paths, ok=True).splitlines()
    c = Counter(out)
    return {"commits": len(out), "top": [{"name": n, "commits": k} for n, k in c.most_common(top)]}


def released_tags(repo):
    tags = git(repo, "tag", "--list", "v*", ok=True).split()
    rel = [t for t in tags if re.fullmatch(r"v\d+\.\d+\.\d+", t)]
    key = lambda t: tuple(int(x) for x in t[1:].split("."))
    return sorted(rel, key=key)


def first_tag_with(repo, tags, path):
    """Earliest released tag whose tree has `path` (binary search over sorted tags, assumes it stays)."""
    lo, hi, hit = 0, len(tags) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        if subprocess.run(["git", "-C", repo, "cat-file", "-e", f"{tags[mid]}:{path}"], capture_output=True).returncode == 0:
            hit, hi = tags[mid], mid - 1
        else:
            lo = mid + 1
    return hit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.environ.get("MP_REPO"), required=os.environ.get("MP_REPO") is None)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    R = a.repo
    tree = files(R)
    tags = released_tags(R)

    # diagnostics: rule table from the release tracking files, one doc page per rule
    rules = []
    for f in ("src/MessagePack.SourceGenerator/AnalyzerReleases.Shipped.md",
              "src/MessagePack.SourceGenerator/AnalyzerReleases.Unshipped.md"):
        txt = show(R, f)
        for i, l in enumerate(txt.splitlines(), 1):
            m = re.match(r"^(MsgPack\d{3})\s*\|\s*(\w+)\s*\|\s*(\w+)\s*\|", l)
            if m:
                doc = f"doc/analyzers/{m.group(1)}.md"
                rules.append({"id": m.group(1), "category": m.group(2), "severity": m.group(3),
                              "tracked_in": f"{f}:{i}",
                              "doc": doc if doc in tree else None,
                              "first_released_tag_with_doc": first_tag_with(R, tags, doc) if doc in tree else None})

    pub = [f for f in tree if re.match(r"src/MessagePack/[^/]+/PublicAPI\.(Shipped|Unshipped)\.txt$", f)]
    pub_counts = {f: sum(1 for l in show(R, f).splitlines() if l.strip() and not l.startswith("#")) for f in pub}

    readme = show(R, "README.md")
    resolver_tt = "src/MessagePack.SourceGenerator/Transforms/ResolverTemplate.tt"
    csproj = show(R, "src/MessagePack/MessagePack.csproj")
    tfms = re.search(r"<TargetFrameworks>([^<]+)</TargetFrameworks>", csproj).group(1).split(";")
    version = json.loads(show(R, "version.json"))
    sec = show(R, "SECURITY.md")

    gen_paths = ["src/MessagePack.SourceGenerator/Transforms/"]
    diag_paths = ["src/MessagePack.SourceGenerator/Analyzers/", "src/MessagePack.SourceGenerator/CodeAnalysis/",
                  "src/MessagePack.SourceGenerator/AnalyzerReleases.Shipped.md",
                  "src/MessagePack.SourceGenerator/AnalyzerReleases.Unshipped.md", "doc/analyzers/"]
    wire_paths = ["src/MessagePack/MessagePackReader.cs", "src/MessagePack/MessagePackWriter.cs",
                  "src/MessagePack/MessagePackCode.cs", "src/MessagePack/Formatters/"]
    sec_paths = ["SECURITY.md", "src/MessagePack/MessagePackSecurity.cs"]

    contracts = [
        {"id": "diagnostics",
         "promise": f"{len(rules)} documented analyzer rules; a user's build reports them",
         "rules": rules,
         "paths": diag_paths,
         "line_patterns": [r"reportDiagnostic", r"Diagnostic\.Create", r"ReportDiagnostic"],
         "maintainers": maintainers(R, diag_paths)},
        {"id": "public-api",
         "promise": f"public surface tracked per target in {len(pub)} PublicAPI files",
         "entries": pub_counts,
         "paths": pub,
         "line_patterns": [],
         "maintainers": maintainers(R, pub)},
        {"id": "generated",
         "promise": "generated code compiles into the consumer's own assembly; the resolver may be a partial class the user declares",
         "sources": [f"README.md:{line_of(readme, 'source generated into your project')}",
                     f"README.md:{line_of(readme, 'to a `partial class` that you define')}",
                     f"{resolver_tt}:{line_of(show(R, resolver_tt), 'partial class')}"],
         "paths": gen_paths,
         "line_patterns": [],
         "maintainers": maintainers(R, gen_paths)},
        {"id": "targets",
         "promise": "the library builds for " + ", ".join(tfms),
         "targets": tfms,
         "sources": ["src/MessagePack/MessagePack.csproj:" + str(line_of(csproj, "<TargetFrameworks>"))],
         "paths": [],
         "line_patterns": [r"^\s*#if\b.*\bNET(STANDARD|FRAMEWORK|COREAPP)"],
         "maintainers": maintainers(R, ["src/MessagePack/MessagePack.csproj"])},
        {"id": "wire-format",
         "promise": "bytes written by one version read back in another",
         "paths": wire_paths,
         "line_patterns": [],
         "maintainers": maintainers(R, wire_paths)},
        {"id": "security",
         "promise": "supported majors get security fixes; reports go to the named maintainers",
         "sources": [f"SECURITY.md:{line_of(sec, '## Supported Versions')}"],
         "paths": sec_paths,
         "line_patterns": [],
         "maintainers": maintainers(R, sec_paths)},
        {"id": "user-docs",
         "promise": "README and doc/ describe behaviour users rely on",
         "paths": ["README.md", "doc/"],
         "line_patterns": [],
         "maintainers": maintainers(R, ["README.md", "doc/"])},
    ]

    ev = {
        "check": "project-context",
        "repo": "te-industry-tech-office/junction26-messagepack-csharp",
        "base": BASE,
        "base_describe": git(R, "describe", "--tags", BASE, ok=True).strip(),
        "command": "python3 review/scripts/project_context.py --repo $MP_REPO --write",
        "release": {"version": version.get("version"), "prerelease": "-" in str(version.get("version")),
                    "semver": (version.get("nugetPackageVersion") or {}).get("semVer"),
                    "released_tags": len(tags), "latest_released_tag": tags[-1] if tags else None,
                    "source": "version.json"},
        "contracts": contracts,
        "summary": f"{len(contracts)} contracts; {len(rules)} documented rules "
                   f"({sum(1 for r in rules if r['first_released_tag_with_doc'])} documented in a released tag); "
                   f"{len(pub)} PublicAPI files; targets {', '.join(tfms)}",
        "tool_versions": {"git": git(R, "--version").strip(), "python": sys.version.split()[0]},
        "produced_by": "script",
    }
    print(ev["summary"])
    for c in contracts:
        m = c["maintainers"]
        top = ", ".join(f"{t['name']} {t['commits']}" for t in m["top"])
        print(f"  {c['id']:12} {m['commits']:4} commits  ({top})")
    if a.write:
        out = os.path.join(REVIEW, "context", "project.json")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as f:
            json.dump(ev, f, indent=2, ensure_ascii=False)
            f.write("\n")


if __name__ == "__main__":
    main()
