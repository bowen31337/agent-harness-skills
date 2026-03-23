#!/usr/bin/env bash
# =============================================================================
# harness-init.sh — Standalone Claw-Forge Agent Harness Initialiser
# =============================================================================
# For teams NOT using Claude Code.  Bootstraps a project with the same
# skill library and harness config that Claude Code agents receive, then
# exposes every skill as a runnable CLI command so any LLM client, CI
# pipeline, or shell script can invoke them.
#
# Usage:
#   chmod +x harness-init.sh
#   ./harness-init.sh [OPTIONS]
#
# Options:
#   -p, --profile  <starter|standard|advanced>   Skill profile to install  [default: standard]
#   -r, --registry <URL>                          Remote skill registry URL [default: bundled]
#   -o, --output   <dir>                          Target project directory  [default: .]
#   -s, --state    <URL>                          Claw-forge state service   [default: http://localhost:8888]
#   --no-color                                    Disable ANSI colours
#   --dry-run                                     Print actions without executing them
#   -h, --help                                    Show this help and exit
#
# After init you can run any skill via:
#   ./harness skill <skill-name> [ARGS...]
# =============================================================================

set -euo pipefail

# ── Colour helpers ────────────────────────────────────────────────────────────
NO_COLOR="${NO_COLOR:-}"
if [ -t 1 ] && [ -z "$NO_COLOR" ]; then
  BOLD=$'\033[1m'; RESET=$'\033[0m'
  GREEN=$'\033[0;32m'; YELLOW=$'\033[0;33m'; CYAN=$'\033[0;36m'; RED=$'\033[0;31m'
else
  BOLD=""; RESET=""; GREEN=""; YELLOW=""; CYAN=""; RED=""
fi

info()    { printf "%s%s%s\n"  "$CYAN"   "  $*" "$RESET"; }
success() { printf "%s%s%s\n"  "$GREEN"  "✔ $*" "$RESET"; }
warn()    { printf "%s%s%s\n"  "$YELLOW" "⚠ $*" "$RESET" >&2; }
error()   { printf "%s%s%s\n"  "$RED"    "✖ $*" "$RESET" >&2; exit 1; }
header()  { printf "\n%s%s%s\n\n" "$BOLD" "$*" "$RESET"; }
sep()     { printf '%s\n' "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; }

# ── Defaults ──────────────────────────────────────────────────────────────────
PROFILE="standard"
REGISTRY_URL=""            # empty = use bundled skill definitions below
OUTPUT_DIR="."
STATE_URL="http://localhost:8888"
DRY_RUN=false

# ── Skill profile definitions ─────────────────────────────────────────────────
# Each profile lists the skill files to install.  Override via --registry to
# fetch from a remote server instead.
SKILLS_STARTER=(
  "check-code"
  "checkpoint"
  "review-pr"
)

SKILLS_STANDARD=(
  "${SKILLS_STARTER[@]}"
  "browser-automation"
  "ci-pipeline"
  "claw-forge-status"
  "coordinate"
  "create-bug-report"
  "create-spec"
  "define-principles"
  "dom-snapshot"
  "expand-project"
  "harness-changelog"
  "pool-status"
)

SKILLS_ADVANCED=(
  "${SKILLS_STANDARD[@]}"
  # Future skills land here automatically when the registry is updated.
)

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--profile)   PROFILE="$2";      shift 2 ;;
    -r|--registry)  REGISTRY_URL="$2"; shift 2 ;;
    -o|--output)    OUTPUT_DIR="$2";   shift 2 ;;
    -s|--state)     STATE_URL="$2";    shift 2 ;;
    --no-color)     NO_COLOR=1;        shift   ;;
    --dry-run)      DRY_RUN=true;      shift   ;;
    -h|--help)
      sed -n '3,30p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    *) error "Unknown option: $1 (try --help)" ;;
  esac
done

# ── Helpers ───────────────────────────────────────────────────────────────────
run() {
  if $DRY_RUN; then
    printf "  %s[dry-run]%s %s\n" "$YELLOW" "$RESET" "$*"
  else
    eval "$@"
  fi
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || error "Required command '$1' not found. Install it and retry."
}

# ── Pre-flight checks ─────────────────────────────────────────────────────────
require_cmd git
require_cmd mkdir
require_cmd curl

sep
header "  Claw-Forge Harness Init  —  Standalone Edition"
sep
info "Profile  : $PROFILE"
info "Output   : $OUTPUT_DIR"
info "State    : $STATE_URL"
info "Dry-run  : $DRY_RUN"
[ -n "$REGISTRY_URL" ] && info "Registry : $REGISTRY_URL"
echo ""

# ── Resolve skill list ────────────────────────────────────────────────────────
case "$PROFILE" in
  starter)  SKILLS=("${SKILLS_STARTER[@]}") ;;
  standard) SKILLS=("${SKILLS_STANDARD[@]}") ;;
  advanced) SKILLS=("${SKILLS_ADVANCED[@]}") ;;
  *) error "Unknown profile '$PROFILE'. Choose: starter | standard | advanced" ;;
esac

# ── Directory scaffold ────────────────────────────────────────────────────────
COMMANDS_DIR="$OUTPUT_DIR/.claude/commands"
DOCS_DIR="$OUTPUT_DIR/docs"

header "1 / 5  Directory scaffold"
run "mkdir -p '$COMMANDS_DIR'"
run "mkdir -p '$DOCS_DIR'"
success "Directories ready"

# ── Write CLAUDE.md ───────────────────────────────────────────────────────────
header "2 / 5  CLAUDE.md"

CLAUDE_MD="$OUTPUT_DIR/CLAUDE.md"
if [ ! -f "$CLAUDE_MD" ] || $DRY_RUN; then
  run "cat > '$CLAUDE_MD' <<'CLAUDE_MD_EOF'
# CLAUDE.md
> Auto-generated by harness-init.sh — edit freely.

## Project Overview
<!-- TODO: describe what this project does -->

## Stack
- Language: unknown
- Framework: unknown

## Build & Test
- Add your build/test/lint commands here

## claw-forge Agent Notes
- State service: $STATE_URL
- Report task complete: PATCH /features/{id} with status=done
- Request human input: POST /features/{id}/human-input
- Skills available: see .claude/commands/ directory
CLAUDE_MD_EOF"
  success "CLAUDE.md written"
else
  warn "CLAUDE.md already exists — skipping (delete to regenerate)"
fi

# ── Fetch / embed skill files ─────────────────────────────────────────────────
header "3 / 5  Install skills  (profile: $PROFILE, ${#SKILLS[@]} skills)"

install_skill_from_registry() {
  local name="$1"
  local dest="$COMMANDS_DIR/${name}.md"
  local url="${REGISTRY_URL%/}/${name}.md"
  info "Fetching $name from $url ..."
  run "curl -fsSL '$url' -o '$dest'"
}

install_skill_stub() {
  local name="$1"
  local dest="$COMMANDS_DIR/${name}.md"
  info "Writing stub for $name ..."
  run "cat > '$dest' <<STUB_EOF
# ${name}

> Skill stub generated by harness-init.sh.
> Replace this file with the real skill definition from your registry
> or from the claw-forge agent-harness-skills repository.

## Instructions

1. Fetch the latest version of this skill from the claw-forge skill registry.
2. Replace this file with the downloaded content.
3. Commit the result alongside your claw-forge.yaml.
STUB_EOF"
}

for skill in "${SKILLS[@]}"; do
  dest="$COMMANDS_DIR/${skill}.md"
  if [ -f "$dest" ] && ! $DRY_RUN; then
    warn "Skill '$skill' already exists — skipping"
    continue
  fi
  if [ -n "$REGISTRY_URL" ]; then
    install_skill_from_registry "$skill" || {
      warn "Registry fetch failed for '$skill' — installing stub instead"
      install_skill_stub "$skill"
    }
  else
    install_skill_stub "$skill"
  fi
  success "Installed: $skill"
done

# ── Write claw-forge.yaml ─────────────────────────────────────────────────────
header "4 / 5  claw-forge.yaml"

YAML_PATH="$OUTPUT_DIR/claw-forge.yaml"
if [ ! -f "$YAML_PATH" ] || $DRY_RUN; then
  run "cat > '$YAML_PATH' <<YAML_EOF
# claw-forge.yaml — generated by harness-init.sh
version: '1'
state_service: '$STATE_URL'
harness:
  profile: '$PROFILE'
  skills_dir: .claude/commands
  changelog: docs/harness-changelog.md
YAML_EOF"
  success "claw-forge.yaml written"
else
  warn "claw-forge.yaml already exists — skipping"
fi

# ── Write the standalone harness CLI runner ───────────────────────────────────
header "5 / 5  Standalone CLI runner  (./harness)"

RUNNER="$OUTPUT_DIR/harness"
run "cat > '$RUNNER' <<'RUNNER_EOF'
#!/usr/bin/env bash
# harness — Standalone skill runner (no Claude Code required)
# Generated by harness-init.sh
#
# Usage:
#   ./harness skill <name> [ARGS...]   Run a skill
#   ./harness list                     List installed skills
#   ./harness doctor                   Verify environment
#   ./harness update                   Re-run harness-init.sh
set -euo pipefail

COMMANDS_DIR="\$(cd "\$(dirname "\$0")/.claude/commands" 2>/dev/null && pwd)"
STATE_URL="$STATE_URL"
LLM_BIN="\${HARNESS_LLM:-claude}"   # override with HARNESS_LLM env var

cmd_list() {
  echo "Installed skills:"
  for f in "\$COMMANDS_DIR"/*.md; do
    basename "\$f" .md
  done
}

cmd_doctor() {
  echo "Harness doctor"
  echo "  Skills dir : \$COMMANDS_DIR"
  echo "  State URL  : \$STATE_URL"
  echo "  LLM binary : \$LLM_BIN"
  command -v "\$LLM_BIN" >/dev/null 2>&1 \
    && echo "  LLM        : OK (\$(which "\$LLM_BIN"))" \
    || echo "  LLM        : NOT FOUND — set HARNESS_LLM or install claude CLI"
  curl -sf "\$STATE_URL/health" >/dev/null 2>&1 \
    && echo "  State svc  : OK" \
    || echo "  State svc  : UNREACHABLE (\$STATE_URL) — start with: claw-forge serve"
}

cmd_skill() {
  local name="\${1:-}"
  [ -z "\$name" ] && { echo "Usage: harness skill <name> [ARGS]"; exit 1; }
  local skill_file="\$COMMANDS_DIR/\${name}.md"
  [ -f "\$skill_file" ] || { echo "Skill not found: \$name"; exit 1; }

  # Pass the skill markdown as the system prompt to the CLI LLM.
  # The LLM client must support reading a system prompt via stdin or flag.
  # Adjust for your client (claude, llm, openai-cli, etc.).
  shift
  SYSTEM_PROMPT="\$(cat "\$skill_file")"
  TASK_ARGS="\${*:-}"

  if command -v "\$LLM_BIN" >/dev/null 2>&1; then
    echo "\$SYSTEM_PROMPT" | "\$LLM_BIN" chat --system - --message "\$TASK_ARGS"
  else
    echo "No LLM binary found. Set HARNESS_LLM=<your-cli> or install the claude CLI."
    echo ""
    echo "Skill content (\$name):"
    echo "----------------------------------------------------------------------"
    cat "\$skill_file"
    echo "----------------------------------------------------------------------"
  fi
}

cmd_update() {
  local init="\$(cd "\$(dirname "\$0")" && pwd)/harness-init.sh"
  [ -f "\$init" ] || { echo "harness-init.sh not found next to this script."; exit 1; }
  bash "\$init" "\$@"
}

case "\${1:-help}" in
  list)   cmd_list ;;
  doctor) cmd_doctor ;;
  skill)  shift; cmd_skill "\$@" ;;
  update) shift; cmd_update "\$@" ;;
  help|-h|--help)
    sed -n '3,12p' "\$0" | sed 's/^# \?//'
    ;;
  *) echo "Unknown command: \$1 — try: ./harness help"; exit 1 ;;
esac
RUNNER_EOF"

run "chmod +x '$RUNNER'"
success "Standalone runner written: $OUTPUT_DIR/harness"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
sep
printf "%s  Harness init complete!%s\n" "$BOLD" "$RESET"
sep
echo ""
printf "  Skills installed : %s${#SKILLS[@]}%s  (%s profile)\n" "$GREEN" "$RESET" "$PROFILE"
printf "  Commands dir     : %s\n"   "$COMMANDS_DIR"
printf "  State service    : %s\n"   "$STATE_URL"
printf "  Runner           : %s./harness%s\n" "$CYAN" "$RESET"
echo ""
printf "  Next steps:\n"
printf "    %s./harness doctor%s         — verify your environment\n"       "$CYAN" "$RESET"
printf "    %s./harness list%s           — list installed skills\n"          "$CYAN" "$RESET"
printf "    %s./harness skill <name>%s   — run a skill\n"                    "$CYAN" "$RESET"
echo ""
if [ -z "$REGISTRY_URL" ]; then
  warn "Skills were installed as STUBS.  Populate .claude/commands/*.md with"
  warn "real skill definitions from the agent-harness-skills repository, then"
  warn "re-run:  ./harness-init.sh --profile $PROFILE --registry <URL>"
fi
sep
echo ""
