#!/usr/bin/env bash
# One entry point. Usually called through npm:  npm run dev | setup | evidence | tests | sign
set -euo pipefail
cd "$(dirname "$0")"

ROOT=$PWD
WORK=$ROOT/.work
PORT=${PORT:-5173}
export MP_REPO=${MP_REPO:-$WORK/mp}
export DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1
[ -x "$WORK/dotnet/dotnet" ] && export DOTNET_ROOT=$WORK/dotnet PATH=$WORK/dotnet:$PATH

say() { printf '\033[1;33m▸ %s\033[0m\n' "$*"; }
need_repo() {
  [ -d "$MP_REPO/.git" ] || { echo "No target clone at $MP_REPO. Run: npm run setup"; exit 1; }
}
need_dotnet() {
  command -v dotnet >/dev/null && dotnet --list-sdks | grep -q '^8\.0\.4' ||
    { echo "Needs .NET SDK 8.0.4xx. Run: npm run setup"; exit 1; }
}

render() {
  python3 review/scripts/render_markdown.py --all >/dev/null
  python3 review/scripts/render_web.py
}

cmd_dev() {
  while [ $# -gt 0 ]; do
    case "$1" in
      -p|--port) PORT=${2:?--port needs a number}; shift 2 ;;
      --port=*) PORT=${1#--port=}; shift ;;
      [0-9]*) PORT=$1; shift ;;
      *) echo "dev: unknown option $1 (use --port N)"; exit 1 ;;
    esac
  done
  case "$PORT" in ''|*[!0-9]*) echo "dev: port must be a number, got '$PORT'"; exit 1 ;; esac
  render
  local url="http://localhost:$PORT/web/"
  say "Owner view → $url   (Ctrl+C to stop)"
  ( sleep 1; command -v open >/dev/null && open "$url" || { command -v xdg-open >/dev/null && xdg-open "$url"; } ) >/dev/null 2>&1 &
  python3 -m http.server "$PORT" --bind 127.0.0.1 --directory review
}

cmd_setup() {
  mkdir -p "$WORK"
  if [ -d "$MP_REPO/.git" ]; then
    say "Target clone present: $MP_REPO"; git -C "$MP_REPO" fetch -q origin
  else
    say "Cloning target (all branches) → $MP_REPO"
    git clone -q --no-single-branch https://github.com/te-industry-tech-office/junction26-messagepack-csharp "$MP_REPO"
  fi
  if command -v dotnet >/dev/null && dotnet --list-sdks | grep -q '^8\.0\.4'; then
    say ".NET SDK 8.0.4xx present"
  else
    say "Installing .NET SDK 8.0.402 → $WORK/dotnet"
    curl -sSL https://dot.net/v1/dotnet-install.sh -o "$WORK/dotnet-install.sh"
    bash "$WORK/dotnet-install.sh" --version 8.0.402 --install-dir "$WORK/dotnet" >/dev/null
  fi
  say "Ready. Next: npm run evidence  (fast)  ·  npm run tests  (builds, ~10 min)"
}

# Collectors that only read git: seconds.
cmd_evidence() {
  need_repo
  say "2297 diff classifier";   python3 review/scripts/diff_classifier.py --branch ju26-issue-2297 --write
  say "2234 clones/complexity"; python3 review/scripts/clone_complexity.py --branch ju26-issue-2234 --out review/evidence/ju26-issue-2234/clone-complexity.json
  say "2283 report sites";      python3 review/scripts/report_sites.py --branch ju26-issue-2283 --out review/evidence/ju26-issue-2283/report-sites.json
  for b in 2297 2234 2283; do
    say "$b claim coverage";    python3 review/scripts/claim_coverage.py --branch ju26-issue-$b --write
  done
  render
}

# Collectors that build and run the C# tests.
cmd_tests() {
  need_repo; need_dotnet
  local wd=$WORK/worktrees; mkdir -p "$wd"
  say "2297 regeneration (base vs branch)"
  python3 review/scripts/regen_check.py --branch ju26-issue-2297 --workdir "$wd/2297" --out regeneration --write \
    --run 'base=32258fdb' --run 'branch=origin/ju26-issue-2297'
  say "2297 TransformUtilities removal"
  python3 review/scripts/regen_check.py --branch ju26-issue-2297 --workdir "$wd/2297" --out transformutilities-removal --write \
    --run 'no-tu=origin/ju26-issue-2297+revert:src/MessagePack.SourceGenerator/Transforms/TransformUtilities.cs'
  say "2234 new tests on base vs branch"
  python3 review/scripts/old_vs_new_tests.py --branch ju26-issue-2234 --workdir "$wd/2234" \
    --out review/evidence/ju26-issue-2234/old-vs-new-tests.json
  say "2283 new tests on base vs branch"
  python3 review/scripts/old_vs_new_tests.py --branch ju26-issue-2283 --workdir "$wd/2283" \
    --out review/evidence/ju26-issue-2283/old-vs-new-tests.script.json
  say "2283 dropped-warning probe"
  python3 review/scripts/dropped_warning_test/run.py --workdir "$wd/2283-probe" --out-dir review/evidence/ju26-issue-2283
  render
}

cmd_sign() { python3 review/scripts/sign_receipt.py "${1:-ju26-issue-2283}" "${@:2}"; render >/dev/null; }

case "${1:-dev}" in
  dev) shift || true; cmd_dev "$@" ;;
  -*|[0-9]*) cmd_dev "$@" ;;
  render) render ;;
  setup) cmd_setup ;;
  evidence) cmd_evidence ;;
  tests) cmd_tests ;;
  all) cmd_setup; cmd_evidence; cmd_tests ;;
  sign) shift; cmd_sign "$@" ;;
  *) echo "usage: $0 dev [--port N]|render|setup|evidence|tests|all|sign [branch]"; exit 1 ;;
esac
