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
#   • bash ≥ 4  (macOS: brew install bash)
#   • git       (for git-log strategy)
#   • grep / awk / sed / wc / find  (standard POSIX utilities)
#   • curl      (optional — for state-service lookup)
#   • jq        (optional — for JSON output formatting)
# =============================================================================
set -euo pipefail

# ── colour helpers ────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
  BOLD='\033[1m'; CYAN='\033[0;36m'; GREEN='\033[0;32m'
  YELLOW='\033[1;33m'; DIM='\033[2m'; RESET='\033[0m'
else
  BOLD=''; CYAN=''; GREEN=''; YELLOW=''; DIM=''; RESET=''
fi

stderr() { echo -e "$*" >&2; }
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
INPUT=""
MAX_FILES=20
BUDGET=0
FORMAT="human"
STATE_URL="${CLAW_FORGE_STATE_URL:-http://localhost:8888}"
NO_GIT=false
INCLUDE_GLOB=""
EXCLUDE_GLOB=""
CWD="$(pwd)"

# ── argument parsing ──────────────────────────────────────────────────────────
[[ $# -eq 0 ]] && usage

INPUT="$1"; shift

while [[ $# -gt 0 ]]; do
  case $1 in
    --max-files)  MAX_FILES="${2:?--max-files requires a number}"; shift 2 ;;
    --budget)     BUDGET="${2:?--budget requires a number}";      shift 2 ;;
    --format)     FORMAT="${2:?--format requires json|human}";    shift 2 ;;
    --state-url)  STATE_URL="${2:?--state-url requires a URL}";   shift 2 ;;
    --no-git)     NO_GIT=true;                                    shift   ;;
    --include)    INCLUDE_GLOB="${2:?--include requires a glob}"; shift 2 ;;
    --exclude)    EXCLUDE_GLOB="${2:?--exclude requires a glob}"; shift 2 ;;
    --cwd)        CWD="${2:?--cwd requires a directory}";         shift 2 ;;
    -h|--help)    usage ;;
    *) die "Unknown flag: $1" ;;
  esac
done

cd "$CWD" || die "Cannot cd to $CWD"

# ── temporary work directory (cleaned up on exit) ─────────────────────────────
TMPDIR_WORK="${TMPDIR:-/tmp}/harness-context-$$"
mkdir -p "$TMPDIR_WORK"
trap 'rm -rf "$TMPDIR_WORK"' EXIT

# Files used to accumulate candidate paths + scores
SCORES_FILE="$TMPDIR_WORK/scores.tsv"   # <score>\t<path>
SKIP_FILE="$TMPDIR_WORK/skip.txt"
STATE_META="$TMPDIR_WORK/state.json"

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
  HTTP_STATUS=0
  if command -v curl &>/dev/null; then
    HTTP_STATUS=$(curl -sf -w "%{http_code}" -o "$STATE_META" \
      "${STATE_URL}/features/${INPUT}" 2>/dev/null || echo "0")
  fi

  if [[ "$HTTP_STATUS" == "200" ]] && [[ -s "$STATE_META" ]]; then
    STATE_SERVICE_USED=true
    info "State service responded (200)"

    # Extract domain for keyword fallback
    if command -v jq &>/dev/null; then
      DOMAIN=$(jq -r '.domain // .description // empty' "$STATE_META" 2>/dev/null | head -1)
      [[ -z "$DOMAIN" ]] && DOMAIN="$INPUT"

      # Seed files from state service (score 100 each)
      while IFS= read -r f; do
        [[ -z "$f" ]] && continue
        echo -e "100\t${f}" >> "$SCORES_FILE"
        FILES_FROM_STATE+=("$f")
      done < <(jq -r '
        .tasks[]?.files_touched[]?
        // .files_touched[]?
        // empty' "$STATE_META" 2>/dev/null)

      # Extra keywords from task descriptions
      while IFS= read -r desc; do
        [[ -z "$desc" ]] && continue
        EXTRA_KEYWORDS+=("$desc")
      done < <(jq -r '.tasks[]?.description // empty' "$STATE_META" 2>/dev/null)

    else
      warn "jq not found — state service JSON parsed with grep (less accurate)"
      DOMAIN=$(grep -o '"domain":"[^"]*"' "$STATE_META" 2>/dev/null \
               | head -1 | sed 's/"domain":"//;s/"//' || echo "$INPUT")
      [[ -z "$DOMAIN" ]] && DOMAIN="$INPUT"
    fi
    info "Domain resolved to: ${BOLD}${DOMAIN}${RESET}"
  else
    warn "State service unreachable or returned non-200 (status: ${HTTP_STATUS}) — falling back to keyword search for: $INPUT"
    DOMAIN="$INPUT"
  fi
fi

# ── Step 2B — Derive keywords ─────────────────────────────────────────────────
# Tokenise: split on spaces/hyphens/underscores/camelCase, drop tokens < 3 chars
tokenise() {
  local input="$1"
  echo "$input" \
    | sed 's/[[:space:]_-]/ /g' \
    | sed 's/\([a-z]\)\([A-Z]\)/\1 \2/g' \
    | tr '[:upper:]' '[:lower:]' \
    | tr ' ' '\n' \
    | awk 'length($0) >= 3' \
    | sort -u
}

KEYWORDS=()
while IFS= read -r _kw; do
  [[ -n "$_kw" ]] && KEYWORDS+=("$_kw")
done < <(
  {
    tokenise "$DOMAIN"
    for extra in "${EXTRA_KEYWORDS[@]:-}"; do
      tokenise "$extra"
    done
  } | sort -u
)

if [[ ${#KEYWORDS[@]} -eq 0 ]]; then
  die "Could not extract any keywords from input: '$INPUT'"
fi

info "Keywords: ${KEYWORDS[*]}"

# ── Built-in exclusion patterns ───────────────────────────────────────────────
BUILTIN_EXCLUDES=(
  '.git/'
  'node_modules/'
  '__pycache__/'
  '.pyc'
  '/dist/'
  '/build/'
  '.lock'
  '.min.js'
  '.min.css'
)

_excluded() {
  local path="$1"
  for pat in "${BUILTIN_EXCLUDES[@]}"; do
    [[ "$path" == *"$pat"* ]] && return 0
  done
  [[ -n "$EXCLUDE_GLOB" && "$path" == $EXCLUDE_GLOB ]] && return 0
  return 1
}

_matches_include() {
  local path="$1"
  [[ -z "$INCLUDE_GLOB" ]] && return 0
  [[ "$path" == $INCLUDE_GLOB ]] && return 0
  return 1
}

add_score() {
  local score="$1" path="$2"
  _excluded "$path"  && return
  _matches_include "$path" || return
  [[ -f "$path" ]] || return
  echo -e "${score}\t${path}" >> "$SCORES_FILE"
}

# ── Step 3 — Discover candidate files ────────────────────────────────────────

# Strategy A — Git log
if ! $NO_GIT && command -v git &>/dev/null && git rev-parse --git-dir &>/dev/null; then
  info "Strategy A: git log …"
  for KW in "${KEYWORDS[@]}"; do
    while IFS= read -r filepath; do
      [[ -z "$filepath" ]] && continue
      add_score 10 "$filepath"
    done < <(
      git log --all --oneline --name-only --grep="$KW" -20 2>/dev/null \
        | grep -E '\.(py|ts|tsx|js|jsx|go|rs|rb|java|kt|swift|yaml|yml|json|toml|md)$' \
        || true
    )
  done
else
  [[ "$NO_GIT" == "true" ]] && info "Strategy A: skipped (--no-git)"
fi

# Strategy B — Symbol grep
info "Strategy B: symbol grep …"
for KW in "${KEYWORDS[@]}"; do
  while IFS= read -r filepath; do
    [[ -z "$filepath" ]] && continue
    add_score 5 "$filepath"
  done < <(
    grep -rli "$KW" \
      --include='*.py' --include='*.ts' --include='*.tsx' \
      --include='*.js' --include='*.jsx' --include='*.go' \
      --include='*.rs' --include='*.rb' --include='*.java' \
      --include='*.kt' --include='*.swift' --include='*.yaml' \
      --include='*.yml' --include='*.json' --include='*.toml' \
      . 2>/dev/null \
      | grep -v '/.git/' \
      | head -40 \
      || true
  )
done

# Strategy C — Path name match
info "Strategy C: path name match …"
for KW in "${KEYWORDS[@]}"; do
  while IFS= read -r filepath; do
    [[ -z "$filepath" ]] && continue
    # Strip leading ./
    filepath="${filepath#./}"
    add_score 2 "$filepath"
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

# Sum scores per unique path, then sort descending
RANKED_FILE="$TMPDIR_WORK/ranked.tsv"  # <total_score>\t<path>

awk -F'\t' '
  { score[$2] += $1 }
  END {
    for (path in score) {
      print score[path] "\t" path
    }
  }
' "$SCORES_FILE" \
  | sort -t$'\t' -k1 -rn \
  | head -"$MAX_FILES" \
  > "$RANKED_FILE"

# ── Annotate with line counts ──────────────────────────────────────────────────
ANNOTATED_FILE="$TMPDIR_WORK/annotated.tsv"  # <score>\t<lines>\t<sources>\t<path>
touch "$ANNOTATED_FILE"

while IFS=$'\t' read -r score path; do
  lines=0
  if [[ -f "$path" ]]; then
    lines=$(wc -l < "$path" 2>/dev/null | tr -d ' ' || echo 0)
  fi

  # Determine sources
  sources=""
  for sf in "${FILES_FROM_STATE[@]:-}"; do
    if [[ "$sf" == "$path" ]]; then sources="state_service,"; break; fi
  done
  if ! $NO_GIT && command -v git &>/dev/null; then
    for KW in "${KEYWORDS[@]}"; do
      if git log --all --oneline --name-only --grep="$KW" -20 2>/dev/null \
          | grep -qF "$path" 2>/dev/null; then
        sources+="git_log,"
        break
      fi
    done
  fi
  for KW in "${KEYWORDS[@]}"; do
    if grep -qli "$KW" "$path" 2>/dev/null; then
      sources+="symbol_grep,"
      break
    fi
  done
  for KW in "${KEYWORDS[@]}"; do
    if [[ "$path" == *"$KW"* ]]; then
      sources+="path_name,"
      break
    fi
  done
  sources="${sources%,}"  # strip trailing comma

  echo -e "${score}\t${lines}\t${sources}\t${path}" >> "$ANNOTATED_FILE"
done < "$RANKED_FILE"

# ── Skip list (generated / lockfiles) ─────────────────────────────────────────
SKIP_PATTERNS=(
  'migrations/[0-9]'
  '\.min\.(js|css)$'
  '(package-lock|yarn\.lock|poetry\.lock|Gemfile\.lock|Cargo\.lock|uv\.lock)$'
  '(\.pyc|\.pyo)$'
  '__pycache__'
  'node_modules'
)

for pat in "${SKIP_PATTERNS[@]}"; do
  grep -rEl "$pat" . 2>/dev/null \
    | grep -v '/.git/' \
    | while IFS= read -r f; do
        reason="generated/lockfile"
        [[ "$f" =~ migrations/ ]] && reason="generated migration file"
        [[ "$f" =~ \.lock$ ]]     && reason="lockfile"
        [[ "$f" =~ \.min\. ]]     && reason="minified asset"
        echo -e "${f}\t${reason}"
      done
done | sort -u > "$SKIP_FILE" || true

# ── Step 5 — Generate search patterns ────────────────────────────────────────
generate_patterns() {
  local -a patterns=()
  local count=0
  for kw in "${KEYWORDS[@]}"; do
    [[ $count -ge 15 ]] && break
    patterns+=("{\"label\":\"define:${kw}\",\"pattern\":\"(?:class|def|function|fn|type|interface|struct)\\\\s+\\\\w*${kw}\\\\w*\",\"flags\":\"-i\",\"rationale\":\"Symbol definitions matching '${kw}'\"}")
    (( count++ )) || true
    [[ $count -ge 15 ]] && break
    patterns+=("{\"label\":\"import:${kw}\",\"pattern\":\"(?:import|from|require|use)\\\\s+.*${kw}\",\"flags\":\"-i\",\"rationale\":\"Import statements pulling in '${kw}' components\"}")
    (( count++ )) || true
    [[ $count -ge 15 ]] && break
    patterns+=("{\"label\":\"route:${kw}\",\"pattern\":\"(?:@\\\\w+\\\\.(?:get|post|put|patch|delete)|router\\\\.\\\\w+)\\\\s*\\\\(['\\\"].*${kw}\",\"flags\":\"-i\",\"rationale\":\"HTTP endpoints related to '${kw}'\"}")
    (( count++ )) || true
  done
  local IFS=','
  echo "[${patterns[*]}]"
}

PATTERNS_JSON=$(generate_patterns)

# ── Step 6 — Emit ContextManifest ─────────────────────────────────────────────

# ── Count stats ───────────────────────────────────────────────────────────────
TOTAL_CANDIDATES=$(wc -l < "$SCORES_FILE" | tr -d ' ')
RETURNED_FILES=$(wc -l < "$ANNOTATED_FILE" | tr -d ' ')
TOTAL_LINES=$(awk -F'\t' '{s+=$2} END{print s+0}' "$ANNOTATED_FILE")
SKIP_COUNT=$(wc -l < "$SKIP_FILE" | tr -d ' ')

# ── Human-readable output ─────────────────────────────────────────────────────
print_human() {
  local bar="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  local thin="────────────────────────────────────────────────────────────"

  echo -e "\n${BOLD}${bar}${RESET}"
  printf "${BOLD}  Harness Context — %s${RESET}\n" "$INPUT"
  printf "  %s files · %s patterns · ~%s estimated lines\n" \
    "$RETURNED_FILES" \
    "$(echo "$PATTERNS_JSON" | grep -o '"label"' | wc -l | tr -d ' ')" \
    "$TOTAL_LINES"
  echo -e "${BOLD}${bar}${RESET}\n"

  echo -e "${BOLD}Ranked Files${RESET}"
  echo -e "$thin"
  printf "  ${BOLD}%3s  %6s  %5s  %-50s  %s${RESET}\n" "#" "Score" "Lines" "Path" "Sources"
  printf "  %s\n" "$thin"

  local rank=1
  while IFS=$'\t' read -r score lines sources path; do
    src_label=""
    [[ "$sources" == *"state_service"* ]] && src_label+="● state "
    [[ "$sources" == *"git_log"* ]]       && src_label+="⎇ git "
    [[ "$sources" == *"symbol_grep"* ]]   && src_label+="⌕ grep "
    [[ "$sources" == *"path_name"* ]]     && src_label+="⌂ path "
    printf "  ${CYAN}%3d${RESET}  %6s  %5s  %-50s  ${DIM}%s${RESET}\n" \
      "$rank" "$score" "$lines" "$path" "$src_label"
    (( rank++ )) || true
  done < "$ANNOTATED_FILE"

  echo ""
  echo -e "${BOLD}Search Patterns (apply to ranked files first)${RESET}"
  echo -e "$thin"
  echo "$PATTERNS_JSON" | grep -o '"label":"[^"]*","pattern":"[^"]*"' \
    | sed 's/"label":"//;s/","pattern":"/ → /;s/"//' \
    | while IFS= read -r line; do
        printf "  %s\n" "$line"
      done

  if [[ "$SKIP_COUNT" -gt 0 ]]; then
    echo ""
    echo -e "${BOLD}Skip List (do not load)${RESET}"
    echo -e "$thin"
    while IFS=$'\t' read -r path reason; do
      printf "  %-55s  ${DIM}(%s)${RESET}\n" "$path" "$reason"
    done < "$SKIP_FILE"
  fi

  echo -e "\n${BOLD}${bar}${RESET}"
  echo -e "  ${DIM}Tip: read only the top-N files; use patterns to extract"
  echo -e "  specific sections rather than loading full contents.${RESET}"
  echo -e "${BOLD}${bar}${RESET}\n"
}

# ── JSON output ───────────────────────────────────────────────────────────────
print_json() {
  # Build files array
  local files_json="["
  local first=true
  local rank=1
  while IFS=$'\t' read -r score lines sources path; do
    $first || files_json+=","
    first=false
    # Build sources array
    local src_arr="["
    local sf=true
    IFS=',' read -ra src_parts <<< "$sources"
    for s in "${src_parts[@]}"; do
      [[ -z "$s" ]] && continue
      $sf || src_arr+=","
      sf=false
      src_arr+="\"${s}\""
    done
    src_arr+="]"
    files_json+="{\"path\":\"${path}\",\"score\":${score},\"estimated_lines\":${lines},\"sources\":${src_arr},\"rationale\":\"score=${score}; sources=${sources}\"}"
    (( rank++ )) || true
  done < "$ANNOTATED_FILE"
  files_json+="]"

  # Build skip_list array
  local skip_json="["
  local sfirst=true
  while IFS=$'\t' read -r path reason; do
    [[ -z "$path" ]] && continue
    $sfirst || skip_json+=","
    sfirst=false
    skip_json+="{\"path\":\"${path}\",\"reason\":\"${reason}\"}"
  done < "$SKIP_FILE"
  skip_json+="]"

  # Build keywords array
  local kw_json="["
  local kfirst=true
  for kw in "${KEYWORDS[@]}"; do
    $kfirst || kw_json+=","
    kfirst=false
    kw_json+="\"${kw}\""
  done
  kw_json+="]"

  local manifest
  manifest=$(cat <<JSON
{
  "command": "harness context",
  "input": "${INPUT}",
  "keywords": ${kw_json},
  "files": ${files_json},
  "patterns": ${PATTERNS_JSON},
  "skip_list": ${skip_json},
  "stats": {
    "total_candidate_files": ${TOTAL_CANDIDATES},
    "returned_files": ${RETURNED_FILES},
    "total_estimated_lines": ${TOTAL_LINES},
    "state_service_used": ${STATE_SERVICE_USED}
  }
}
JSON
)

  if command -v jq &>/dev/null; then
    echo "$manifest" | jq .
  else
    echo "$manifest"
  fi
}

# ── Step 7 — Token budget advisory ────────────────────────────────────────────
print_budget_advisory() {
  local budget_tokens="$1"
  local chars_budget=$(( budget_tokens * 4 ))

  echo ""
  echo -e "  ${BOLD}Token Budget Advisory${RESET}  (target: $(printf '%d' "$budget_tokens") tokens)"
  echo "  ────────────────────────────────────────────────────────────"
  printf "  Assume ~4 chars/token → %d chars budget\n\n" "$chars_budget"
  printf "  %-45s %6s %12s %12s\n" "File" "Lines" "Est. chars" "Cumulative"
  echo "  ─────────────────────────────────────────────────────────────────"

  local cumulative=0
  local within=true
  while IFS=$'\t' read -r score lines sources path; do
    local chars=$(( lines * 38 ))  # ~38 chars/line heuristic
    (( cumulative += chars )) || true
    local status="✅"
    if [[ "$cumulative" -gt "$chars_budget" ]]; then
      within=false
      status="⚠️ "
    fi
    printf "  %-45s %6s %12s %12s  %s\n" \
      "$path" "$lines" "$chars" "$cumulative" "$status"
  done < "$ANNOTATED_FILE"

  echo "  ─────────────────────────────────────────────────────────────────"
  if $within; then
    echo -e "  → Load all ${RETURNED_FILES} ranked files comfortably within budget."
    echo -e "    Use patterns on remaining candidates to extract snippets."
  else
    echo -e "  → Budget exceeded. Load only files marked ✅;"
    echo -e "    use patterns (grep -E) to extract snippets from ⚠️  files."
  fi
  echo ""
}

# ── Dispatch output ───────────────────────────────────────────────────────────
case "$FORMAT" in
  json)
    print_json
    ;;
  human|*)
    print_human
    if [[ "$BUDGET" -gt 0 ]]; then
      print_budget_advisory "$BUDGET"
    fi
    # Always emit the JSON manifest after the human summary
    echo -e "${DIM}── JSON Manifest ─────────────────────────────────────────────────${RESET}"
    print_json
    ;;
esac
