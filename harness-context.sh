||||||| 8e612d9
=======
#!/usr/bin/env bash
# =============================================================================
# harness-context.sh — Standalone CLI equivalent of the /harness:context skill
#
# For teams NOT using the Claude Code IDE extension.
# Implements Steps 1-7 of the harness:context skill entirely via native shell
# tools: curl, git, grep, find, awk, sed — no Claude SDK or Python required.
#
# Usage:
#   bash harness-context.sh <plan-id|domain>  [options]
#
# Examples:
#   bash harness-context.sh auth
#   bash harness-context.sh "user onboarding"
#   bash harness-context.sh PLAN-42
#   bash harness-context.sh PLAN-42   --max-files 10
#   bash harness-context.sh auth      --format json
#   bash harness-context.sh auth      --budget 40000
#   bash harness-context.sh PLAN-42   --state-url http://localhost:9000
#   bash harness-context.sh auth      --no-git
#   bash harness-context.sh auth      --include "src/**/*.py"
#   bash harness-context.sh auth      --exclude "tests/**"
#
# Requirements:
#   • bash ≥ 3.2  (macOS default shell is sufficient)
#   • git          (for git-log strategy; gracefully skipped if absent)
#   • grep / awk / sed / wc / find  (standard POSIX utilities)
#   • curl         (optional — for state-service lookup)
#   • jq           (optional — for pretty-printed JSON output)
# =============================================================================
set -euo pipefail

# ── colour helpers ────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
  BOLD='\033[1m'; CYAN='\033[0;36m'
  YELLOW='\033[1;33m'; DIM='\033[2m'; RESET='\033[0m'
else
  BOLD=''; CYAN=''; YELLOW=''; DIM=''; RESET=''
fi

stderr() { printf '%b\n' "$*" >&2; }
die()    { stderr "${BOLD}[error]${RESET} $*"; exit 1; }
warn()   { stderr "${YELLOW}[warn]${RESET}  $*"; }
info()   { stderr "${CYAN}[info]${RESET}  $*"; }

# ── usage ─────────────────────────────────────────────────────────────────────
usage() {
  cat <<USAGE
Usage: $(basename "$0") <plan-id|domain> [options]

Arguments:
  plan-id|domain    A plan ID (e.g. PLAN-42, FEAT-7) or domain keyword
                    (e.g. "auth", "user onboarding", "payment")

Options:
  --max-files N         Cap returned file list at N entries (default: 20)
  --budget N            Emit token budget advisory for N-token context window
  --format json         Emit only the raw JSON ContextManifest
  --state-url URL       Override state service URL (default: http://localhost:8888)
  --no-git              Skip git-log strategy
  --include GLOB        Restrict candidates to paths matching this glob
  --exclude GLOB        Add extra exclusion glob on top of built-in skip list
  --cwd DIR             Repository root to search (default: current directory)
  -h, --help            Show this help message

USAGE
  exit 0
}

# ── defaults ──────────────────────────────────────────────────────────────────
MAX_FILES=20
BUDGET=0
FORMAT="human"
STATE_URL="${CLAW_FORGE_STATE_URL:-http://localhost:8888}"
NO_GIT=false
INCLUDE_GLOB=""
EXCLUDE_GLOB=""
CWD="$(pwd)"

# ── argument parsing ──────────────────────────────────────────────────────────
# Handle no-arg and early help flags before consuming INPUT
[[ $# -eq 0 ]] && usage
case "${1:-}" in -h|--help) usage ;; esac

INPUT="$1"; shift

while [[ $# -gt 0 ]]; do
  case $1 in
    --max-files)  MAX_FILES="${2:?--max-files requires a number}"; shift 2 ;;
    --budget)     BUDGET="${2:?--budget requires a number}";       shift 2 ;;
    --format)     FORMAT="${2:?--format requires json|human}";     shift 2 ;;
    --state-url)  STATE_URL="${2:?--state-url requires a URL}";    shift 2 ;;
    --no-git)     NO_GIT=true;                                     shift   ;;
    --include)    INCLUDE_GLOB="${2:?--include requires a glob}";  shift 2 ;;
    --exclude)    EXCLUDE_GLOB="${2:?--exclude requires a glob}";  shift 2 ;;
    --cwd)        CWD="${2:?--cwd requires a directory}";          shift 2 ;;
    -h|--help)    usage ;;
    *) die "Unknown flag: $1" ;;
  esac
done

cd "$CWD" || die "Cannot cd to $CWD"

# ── temporary work directory (cleaned up on exit) ─────────────────────────────
WORK_DIR="${TMPDIR:-/tmp}/harness-context-$$"
mkdir -p "$WORK_DIR"
trap 'rm -rf "$WORK_DIR"' EXIT

SCORES_FILE="$WORK_DIR/scores.tsv"    # <score>\t<path>
RANKED_FILE="$WORK_DIR/ranked.tsv"    # <total_score>\t<path>
ANNOTATED_FILE="$WORK_DIR/annotated.tsv"  # <score>\t<lines>\t<sources>\t<path>
SKIP_FILE="$WORK_DIR/skip.tsv"        # <path>\t<reason>
STATE_META="$WORK_DIR/state.json"

touch "$SCORES_FILE" "$SKIP_FILE"

# ── Step 1 — Identify input type ──────────────────────────────────────────────
PLAN_ID_RE='^[A-Za-z]+-[0-9]+$'
IS_PLAN_ID=false
if [[ "$INPUT" =~ $PLAN_ID_RE ]]; then
  IS_PLAN_ID=true
fi

# ── Step 2A — Fetch plan metadata ─────────────────────────────────────────────
DOMAIN="$INPUT"
STATE_SERVICE_USED=false
FILES_FROM_STATE=()
EXTRA_KEYWORDS=()

if $IS_PLAN_ID; then
  info "Input looks like a plan ID — querying state service …"
  HTTP_STATUS="0"
  if command -v curl &>/dev/null; then
    HTTP_STATUS=$(curl -sf -w "%{http_code}" -o "$STATE_META" \
      "${STATE_URL}/features/${INPUT}" 2>/dev/null || echo "0")
  fi

  if [[ "$HTTP_STATUS" == "200" ]] && [[ -s "$STATE_META" ]]; then
    STATE_SERVICE_USED=true
    info "State service responded (200)"

    if command -v jq &>/dev/null; then
      _domain=$(jq -r '.domain // .description // empty' "$STATE_META" 2>/dev/null | head -1)
      [[ -n "$_domain" ]] && DOMAIN="$_domain"

      # Seed files from state service — score 100 each
      while IFS= read -r f; do
        [[ -z "$f" ]] && continue
        printf '100\t%s\n' "$f" >> "$SCORES_FILE"
        FILES_FROM_STATE+=("$f")
      done < <(jq -r '
        .tasks[]?.files_touched[]?
        // .files_touched[]?
        // empty' "$STATE_META" 2>/dev/null)

      # Collect task descriptions as extra keyword seeds
      while IFS= read -r desc; do
        [[ -z "$desc" ]] && continue
        EXTRA_KEYWORDS+=("$desc")
      done < <(jq -r '.tasks[]?.description // empty' "$STATE_META" 2>/dev/null)

    else
      warn "jq not found — state service JSON parsed with grep (less accurate)"
      _domain=$(grep -o '"domain":"[^"]*"' "$STATE_META" 2>/dev/null \
                | head -1 | sed 's/"domain":"//;s/"//' || true)
      [[ -n "$_domain" ]] && DOMAIN="$_domain"
    fi
    info "Domain resolved to: ${BOLD}${DOMAIN}${RESET}"
  else
    warn "State service unreachable or non-200 (status: ${HTTP_STATUS}) — falling back to keyword search for: $INPUT"
  fi
fi

# ── Step 2B — Derive keywords from domain ────────────────────────────────────
# Tokenise: split on spaces/hyphens/underscores/camelCase; drop tokens < 3 chars
tokenise() {
  printf '%s' "$1" \
    | sed 's/[[:space:]_-]/ /g' \
    | sed 's/\([a-z]\)\([A-Z]\)/\1 \2/g' \
    | tr '[:upper:]' '[:lower:]' \
    | tr ' ' '\n' \
    | awk 'length($0) >= 3'
}

KEYWORDS=()
while IFS= read -r _kw; do
  [[ -n "$_kw" ]] && KEYWORDS+=("$_kw")
done < <(
  {
    tokenise "$DOMAIN"
    for _ex in "${EXTRA_KEYWORDS[@]:-}"; do
      tokenise "$_ex"
    done
  } | sort -u
)

[[ ${#KEYWORDS[@]} -eq 0 ]] && die "Could not extract any keywords from: '$INPUT'"
info "Keywords: ${KEYWORDS[*]}"

# ── Helpers: exclusion & inclusion filters ────────────────────────────────────
BUILTIN_EXCLUDE_PARTS=('.git/' 'node_modules/' '__pycache__/' '.pyc' '/dist/' '/build/' '.lock' '.min.js' '.min.css')

_is_excluded() {
  local p="$1"
  for pat in "${BUILTIN_EXCLUDE_PARTS[@]}"; do
    [[ "$p" == *"$pat"* ]] && return 0
  done
  [[ -n "$EXCLUDE_GLOB" && "$p" == $EXCLUDE_GLOB ]] && return 0
  return 1
}

_matches_include() {
  local p="$1"
  [[ -z "$INCLUDE_GLOB" ]] && return 0
  [[ "$p" == $INCLUDE_GLOB ]] && return 0
  return 1
}

add_score() {
  local score="$1" path="$2"
  path="${path#./}"
  _is_excluded "$path"    && return 0
  _matches_include "$path" || return 0
  [[ -f "$path" ]]        || return 0
  printf '%s\t%s\n' "$score" "$path" >> "$SCORES_FILE"
}

# ── Step 3 — Discover candidate files ────────────────────────────────────────

# Strategy A — git log (highest signal)
if ! $NO_GIT && command -v git &>/dev/null && git rev-parse --git-dir &>/dev/null 2>&1; then
  info "Strategy A: git log …"
  for KW in "${KEYWORDS[@]}"; do
    while IFS= read -r fp; do
      [[ -z "$fp" ]] && continue
      add_score 10 "$fp"
    done < <(
      git log --all --oneline --name-only --grep="$KW" -20 2>/dev/null \
        | grep -E '\.(py|ts|tsx|js|jsx|go|rs|rb|java|kt|swift|yaml|yml|json|toml|md)$' \
        || true
    )
  done
else
  $NO_GIT && info "Strategy A: skipped (--no-git)" || true
fi

# Strategy B — symbol grep (medium signal)
info "Strategy B: symbol grep …"
for KW in "${KEYWORDS[@]}"; do
  while IFS= read -r fp; do
    [[ -z "$fp" ]] && continue
    add_score 5 "$fp"
  done < <(
    grep -rli "$KW" \
      --include='*.py'   --include='*.ts'   --include='*.tsx' \
      --include='*.js'   --include='*.jsx'  --include='*.go' \
      --include='*.rs'   --include='*.rb'   --include='*.java' \
      --include='*.kt'   --include='*.swift' \
      --include='*.yaml' --include='*.yml'  --include='*.json' \
      --include='*.toml' \
      . 2>/dev/null \
      | grep -v '/.git/' \
      | head -40 \
      || true
  )
done

# Strategy C — path name match (low signal)
info "Strategy C: path name match …"
for KW in "${KEYWORDS[@]}"; do
  while IFS= read -r fp; do
    [[ -z "$fp" ]] && continue
    add_score 2 "$fp"
  done < <(
    find . -type f \
      \( -name "*${KW}*" -o -path "*/${KW}/*" \) \
      -not -path '*/.git/*' \
      -not -path '*/node_modules/*' \
      -not -path '*/__pycache__/*' \
      -not -path '*/dist/*' \
      -not -path '*/build/*' \
      2>/dev/null \
      | head -40 \
      || true
  )
done

# ── Step 4 — Aggregate, de-duplicate, and rank ────────────────────────────────
info "Ranking candidates …"

awk -F'\t' '
  NF==2 { score[$2] += $1 }
  END   { for (p in score) printf "%s\t%s\n", score[p], p }
' "$SCORES_FILE" \
  | sort -t$'\t' -k1 -rn \
  | head -"$MAX_FILES" \
  > "$RANKED_FILE"

# Annotate with line counts and source labels
touch "$ANNOTATED_FILE"
while IFS=$'\t' read -r score path; do
  lines=0
  [[ -f "$path" ]] && lines=$(wc -l < "$path" 2>/dev/null | tr -d '[:space:]' || echo 0)
  lines="${lines:-0}"

  sources=""

  # Source: state service
  for _sf in "${FILES_FROM_STATE[@]:-}"; do
    [[ "$_sf" == "$path" ]] && { sources="state_service,"; break; }
  done

  # Source: git log
  if ! $NO_GIT && command -v git &>/dev/null; then
    for KW in "${KEYWORDS[@]}"; do
      if git log --all --oneline --name-only --grep="$KW" -20 2>/dev/null \
          | grep -qF "$path" 2>/dev/null; then
        sources+="git_log,"; break
      fi
    done
  fi

  # Source: symbol grep
  for KW in "${KEYWORDS[@]}"; do
    if grep -qli "$KW" "$path" 2>/dev/null; then
      sources+="symbol_grep,"; break
    fi
  done

  # Source: path name
  for KW in "${KEYWORDS[@]}"; do
    if [[ "$path" == *"$KW"* ]]; then
      sources+="path_name,"; break
    fi
  done

  sources="${sources%,}"
  printf '%s\t%s\t%s\t%s\n' "$score" "$lines" "$sources" "$path" >> "$ANNOTATED_FILE"
done < "$RANKED_FILE"

# ── Build skip list — match by FILE PATH, not file contents ──────────────────
# Use find to collect generated/lock files; classify each by name pattern.
while IFS= read -r fp; do
  fp="${fp#./}"
  reason="generated/lockfile"
  [[ "$fp" =~ /migrations/[0-9]  ]] && reason="generated migration file"
  [[ "$fp" =~ \.(lock)$          ]] && reason="lockfile"
  [[ "$fp" =~ \.min\.(js|css)$   ]] && reason="minified asset"
  [[ "$fp" =~ \.(pyc|pyo)$       ]] && reason="compiled Python"
  printf '%s\t%s\n' "$fp" "$reason"
done < <(
  find . -type f \( \
    -name "*.lock"     -o \
    -name "*.pyc"      -o \
    -name "*.pyo"      -o \
    -name "*.min.js"   -o \
    -name "*.min.css"  -o \
    -path "*/migrations/[0-9]*" \
  \) \
  -not -path '*/.git/*' \
  2>/dev/null || true
) | sort -u > "$SKIP_FILE"

# ── Step 5 — Generate search patterns ────────────────────────────────────────
# Build as an explicit string (avoids IFS/word-splitting bugs with JSON values)
generate_patterns_json() {
  local result="[" first=true count=0

  for kw in "${KEYWORDS[@]}"; do
    for type in define import route; do
      [[ $count -ge 15 ]] && break 2

      case $type in
        define) pat="(?:class|def|function|fn|type|interface|struct)\\s+\\w*${kw}\\w*"
                rationale="Symbol definitions matching '${kw}'" ;;
        import) pat="(?:import|from|require|use)\\s+.*${kw}"
                rationale="Import statements pulling in '${kw}' components" ;;
        route)  pat="(?:@\\w+\\.(?:get|post|put|patch|delete)|router\\.\\w+)\\s*\\(.*${kw}"
                rationale="HTTP endpoints related to '${kw}'" ;;
      esac

      # JSON-escape backslashes (\ → \\) and double-quotes (" → \") in pattern
      local json_pat
      json_pat=$(printf '%s' "$pat" | sed 's/\\/\\\\/g; s/"/\\"/g')
      local json_rat
      json_rat=$(printf '%s' "$rationale" | sed 's/"/\\"/g')

      $first || result+=","
      first=false
      result+="{\"label\":\"${type}:${kw}\",\"pattern\":\"${json_pat}\",\"flags\":\"-i\",\"rationale\":\"${json_rat}\"}"
      (( count++ )) || true
    done
  done

  result+="]"
  printf '%s' "$result"
}

PATTERNS_JSON=$(generate_patterns_json)

# ── Stats ─────────────────────────────────────────────────────────────────────
TOTAL_CANDIDATES=$(wc -l < "$SCORES_FILE" | tr -d '[:space:]')
RETURNED_FILES=$(wc -l < "$ANNOTATED_FILE" | tr -d '[:space:]')
TOTAL_LINES=$(awk -F'\t' 'NF>=2{s+=$2} END{print s+0}' "$ANNOTATED_FILE")
SKIP_COUNT=$(wc -l < "$SKIP_FILE" | tr -d '[:space:]')
PAT_COUNT=$(printf '%s' "$PATTERNS_JSON" | grep -o '"label"' | wc -l | tr -d '[:space:]')

# ── Step 6 — Emit ContextManifest ────────────────────────────────────────────

print_human() {
  local bar="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  local thin="────────────────────────────────────────────────────────────"

  printf '\n%b\n' "${BOLD}${bar}${RESET}"
  printf '%b\n'   "  ${BOLD}Harness Context — ${INPUT}${RESET}"
  printf '  %s files · %s patterns · ~%s estimated lines\n' \
    "$RETURNED_FILES" "$PAT_COUNT" "$TOTAL_LINES"
  printf '%b\n\n' "${BOLD}${bar}${RESET}"

  printf '%b\n' "${BOLD}Ranked Files${RESET}"
  printf '%s\n' "$thin"
  printf '  %b\n' "${BOLD}$(printf '%3s  %6s  %5s  %-50s  %s' '#' 'Score' 'Lines' 'Path' 'Sources')${RESET}"
  printf '  %s\n' "$thin"

  local rank=1
  while IFS=$'\t' read -r score lines sources path; do
    local src_label=""
    [[ "$sources" == *"state_service"* ]] && src_label+="● state "
    [[ "$sources" == *"git_log"*       ]] && src_label+="⎇ git "
    [[ "$sources" == *"symbol_grep"*   ]] && src_label+="⌕ grep "
    [[ "$sources" == *"path_name"*     ]] && src_label+="⌂ path "
    printf '  %b%3d%b  %6s  %5s  %-50s  %b%s%b\n' \
      "$CYAN" "$rank" "$RESET" "$score" "$lines" "$path" "$DIM" "$src_label" "$RESET"
    (( rank++ )) || true
  done < "$ANNOTATED_FILE"

  printf '\n%b\n' "${BOLD}Search Patterns (apply to ranked files first)${RESET}"
  printf '%s\n' "$thin"
  printf '%s\n' "$PATTERNS_JSON" \
    | grep -o '"label":"[^"]*","pattern":"[^"]*"' \
    | sed 's/"label":"//; s/","pattern":"/ → /; s/"$//' \
    | while IFS= read -r line; do printf '  %s\n' "$line"; done

  if [[ "$SKIP_COUNT" -gt 0 ]]; then
    printf '\n%b\n' "${BOLD}Skip List (do not load)${RESET}"
    printf '%s\n' "$thin"
    while IFS=$'\t' read -r path reason; do
      [[ -z "$path" ]] && continue
      printf '  %-55s  %b(%s)%b\n' "$path" "$DIM" "$reason" "$RESET"
    done < "$SKIP_FILE"
  fi

  printf '\n%b\n' "${BOLD}${bar}${RESET}"
  printf '%b\n'   "  ${DIM}Tip: read only the top-N files; use patterns to extract"
  printf '%b\n'   "  specific sections rather than loading full contents.${RESET}"
  printf '%b\n\n' "${BOLD}${bar}${RESET}"
}

# JSON-escape a plain string value (no surrounding quotes added)
_json_str() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/	/\\t/g'
}

print_json() {
  # files array
  local files_json="[" first=true
  while IFS=$'\t' read -r score lines sources path; do
    $first || files_json+=","
    first=false

    # sources → JSON array of strings
    local src_arr="[" sf=true
    local _old_ifs="$IFS"; IFS=','
    local _src_parts
    read -ra _src_parts <<< "$sources"
    IFS="$_old_ifs"
    for s in "${_src_parts[@]:-}"; do
      [[ -z "$s" ]] && continue
      $sf || src_arr+=","
      sf=false
      src_arr+="\"$(_json_str "$s")\""
    done
    src_arr+="]"

    local jpath; jpath=$(_json_str "$path")
    local jrat;  jrat=$(_json_str "score=${score}; sources=${sources}")
    files_json+="{\"path\":\"${jpath}\",\"score\":${score:-0},\"estimated_lines\":${lines:-0},\"sources\":${src_arr},\"rationale\":\"${jrat}\"}"
  done < "$ANNOTATED_FILE"
  files_json+="]"

  # skip_list array
  local skip_json="[" sfirst=true
  while IFS=$'\t' read -r path reason; do
    [[ -z "$path" ]] && continue
    $sfirst || skip_json+=","
    sfirst=false
    skip_json+="{\"path\":\"$(_json_str "$path")\",\"reason\":\"$(_json_str "$reason")\"}"
  done < "$SKIP_FILE"
  skip_json+="]"

  # keywords array
  local kw_json="[" kfirst=true
  for kw in "${KEYWORDS[@]}"; do
    $kfirst || kw_json+=","
    kfirst=false
    kw_json+="\"$(_json_str "$kw")\""
  done
  kw_json+="]"

  local manifest
  manifest=$(printf '{
  "command": "harness context",
  "input": "%s",
  "keywords": %s,
  "files": %s,
  "patterns": %s,
  "skip_list": %s,
  "stats": {
    "total_candidate_files": %s,
    "returned_files": %s,
    "total_estimated_lines": %s,
    "state_service_used": %s
  }
}' \
    "$(_json_str "$INPUT")" \
    "$kw_json" \
    "$files_json" \
    "$PATTERNS_JSON" \
    "$skip_json" \
    "${TOTAL_CANDIDATES:-0}" \
    "${RETURNED_FILES:-0}" \
    "${TOTAL_LINES:-0}" \
    "$STATE_SERVICE_USED"
  )

  if command -v jq &>/dev/null; then
    printf '%s\n' "$manifest" | jq .
  else
    printf '%s\n' "$manifest"
  fi
}

# ── Step 7 — Token budget advisory ───────────────────────────────────────────
print_budget_advisory() {
  local budget_tokens="$1"
  local chars_budget=$(( budget_tokens * 4 ))

  printf '\n  %b\n' "${BOLD}Token Budget Advisory${RESET}  (target: ${budget_tokens} tokens)"
  printf '  %s\n' "────────────────────────────────────────────────────────────"
  printf '  Assume ~4 chars/token → %d chars budget\n\n' "$chars_budget"
  printf '  %-45s %6s %12s %12s\n' "File" "Lines" "Est. chars" "Cumulative"
  printf '  %s\n' "─────────────────────────────────────────────────────────────────"

  local cumulative=0 within=true
  while IFS=$'\t' read -r score lines sources path; do
    local chars=$(( ${lines:-0} * 38 ))
    (( cumulative += chars )) || true
    local status="OK"
    [[ "$cumulative" -gt "$chars_budget" ]] && { within=false; status="OVER"; }
    printf '  %-45s %6s %12s %12s  %s\n' "$path" "${lines:-0}" "$chars" "$cumulative" "$status"
  done < "$ANNOTATED_FILE"

  printf '  %s\n' "─────────────────────────────────────────────────────────────────"
  if $within; then
    printf '  -> Load all %s ranked files comfortably within budget.\n' "$RETURNED_FILES"
    printf '     Use patterns on remaining candidates to extract snippets.\n'
  else
    printf '  -> Budget exceeded. Load only OK files;\n'
    printf '     use patterns (grep -E) to extract snippets from OVER files.\n'
  fi
  printf '\n'
}

# ── Dispatch ──────────────────────────────────────────────────────────────────
case "$FORMAT" in
  json)
    print_json
    ;;
  human|*)
    print_human
    [[ "$BUDGET" -gt 0 ]] && print_budget_advisory "$BUDGET"
    printf '%b\n' "${DIM}── JSON Manifest ─────────────────────────────────────────────────${RESET}"
    print_json
    ;;
esac
>>>>>>> feat/codebase-analys-skill-detects-primary-language-s-and-fr
