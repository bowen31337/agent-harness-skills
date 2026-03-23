#!/usr/bin/env bash
# =============================================================================
# harness-lint.sh — run all architectural checks in one pass
#
# Runs three gates in sequence:
#   architecture  — import-layer isolation (static AST analysis)
#   principles    — custom golden-rule enforcement (.claude/principles.yaml)
#   lint          — language-level ruff rules (style, naming, imports)
#
# Exit codes:
#   0  All gates passed
#   1  One or more error-severity violations found
#   2  Internal gate-runner error
#
# Usage:
#   bash scripts/harness-lint.sh [OPTIONS]
#
# Options:
#   --gate architecture|principles|lint   Run only this gate (repeatable)
#   --no-principles                       Skip the principles gate
#   --format json|table                   Output format (default: table)
#   --project-root PATH                   Override repo root (default: .)
#   --fix                                 Auto-fix ruff issues after the check
#                                         (does NOT re-run gates after fixing)
#   -h, --help                            Show this help and exit
#
# Examples:
#   bash scripts/harness-lint.sh
#   bash scripts/harness-lint.sh --format json | jq '.passed'
#   bash scripts/harness-lint.sh --gate architecture --gate principles
#   bash scripts/harness-lint.sh --fix
# =============================================================================
set -euo pipefail

# ── colour helpers ─────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
_info()    { echo -e "${CYAN}[harness-lint]${RESET}  $*" >&2; }
_success() { echo -e "${GREEN}[harness-lint]${RESET}  $*" >&2; }
_warn()    { echo -e "${YELLOW}[harness-lint]${RESET}  $*" >&2; }
_error()   { echo -e "${RED}[harness-lint]${RESET}  $*" >&2; }

# ── defaults ───────────────────────────────────────────────────────────────────
GATES=()
NO_PRINCIPLES=false
FORMAT="table"
PROJECT_ROOT="."
AUTO_FIX=false

# ── argument parsing ───────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case $1 in
    --gate)
      GATES+=("--gate" "${2:?'--gate requires a value'}"); shift 2 ;;
    --no-principles)
      NO_PRINCIPLES=true; shift ;;
    --format)
      FORMAT="${2:?'--format requires a value (json|table)'}"; shift 2 ;;
    --project-root)
      PROJECT_ROOT="${2:?'--project-root requires a path'}"; shift 2 ;;
    --fix)
      AUTO_FIX=true; shift ;;
    -h|--help)
      sed -n '/^# Usage:/,/^# ===/p' "$0" | sed 's/^# \?//'
      exit 0 ;;
    *)
      _error "Unknown option: $1  (run with --help for usage)"
      exit 2 ;;
  esac
done

# ── locate the harness runner ──────────────────────────────────────────────────
_find_runner() {
  # 1. Prefer an installed 'harness' binary on PATH
  if command -v harness &>/dev/null; then
    echo "harness"
    return 0
  fi

  # 2. Fall back to uv run (works from any venv state)
  if command -v uv &>/dev/null; then
    echo "uv run python -m harness_skills.cli.main"
    return 0
  fi

  # 3. Last resort: plain python -m (assumes the package is importable)
  for py in python3 python; do
    if command -v "$py" &>/dev/null; then
      if "$py" -c "import harness_skills" 2>/dev/null; then
        echo "$py -m harness_skills.cli.main"
        return 0
      fi
    fi
  done

  _error "Cannot find 'harness' on PATH and 'uv' is not available."
  _error "Install with:  pip install -e .   or   uv sync"
  return 2
}

RUNNER="$(_find_runner)"

# ── build the command ──────────────────────────────────────────────────────────
CMD_ARGS=(lint "--format" "$FORMAT" "--project-root" "$PROJECT_ROOT")
CMD_ARGS+=("${GATES[@]}")
[[ "$NO_PRINCIPLES" == "true" ]] && CMD_ARGS+=("--no-principles")

# ── banner (suppressed for json output) ───────────────────────────────────────
if [[ "$FORMAT" != "json" ]]; then
  echo ""
  echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
  echo -e "${BOLD}  Harness Lint${RESET}  ·  architecture · principles · lint"
  echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
  echo ""
fi

# ── run the gates ──────────────────────────────────────────────────────────────
# shellcheck disable=SC2086
LINT_EXIT=0
$RUNNER "${CMD_ARGS[@]}" || LINT_EXIT=$?

# ── optional ruff auto-fix ─────────────────────────────────────────────────────
if [[ "$AUTO_FIX" == "true" ]]; then
  if [[ "$FORMAT" != "json" ]]; then
    echo ""
    _info "Running ruff auto-fix …"
  fi

  FIX_RUNNER=""
  if command -v uv &>/dev/null; then
    FIX_RUNNER="uv run"
  fi

  $FIX_RUNNER ruff check "$PROJECT_ROOT" --fix --quiet 2>/dev/null && \
    $FIX_RUNNER ruff format "$PROJECT_ROOT" --quiet 2>/dev/null && \
    _success "ruff auto-fix applied — re-run harness-lint.sh to confirm" || \
    _warn "ruff auto-fix encountered issues; check output above"
fi

# ── exit with the gate runner's code ──────────────────────────────────────────
exit "$LINT_EXIT"
