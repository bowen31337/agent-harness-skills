# Harness Context

Given a **plan ID** or **domain name**, return a minimal `ContextManifest` — an ordered
list of file paths and search patterns that cover the plan's scope — without loading any
file contents into the context window.

Agents use this skill to assemble *only* the files they actually need instead of doing a
broad codebase dump.  The manifest is machine-readable so downstream agents can act on it
immediately.

---

## Usage

```bash
# Resolve by plan ID (queries the state service)
/harness:context PLAN-42

# Resolve by domain name (heuristic file discovery)
/harness:context auth
/harness:context "user onboarding"

# Limit the result to N highest-ranked files
/harness:context PLAN-42 --max-files 10

# Emit only the JSON manifest (no human-readable header)
/harness:context auth --format json
```

---

## Instructions

### Step 1 — Identify the input type

Determine whether the argument looks like a **plan ID** or a **domain name**:

```
PLAN_ID_PATTERN  = /^[A-Za-z]+-\d+$/          # e.g. PLAN-42, FEAT-7, TASK-001
DOMAIN_PATTERN   = anything else               # e.g. "auth", "user onboarding"
```

If the argument matches `PLAN_ID_PATTERN`, proceed to **Step 2A**.
Otherwise proceed to **Step 2B**.

---

### Step 2A — Fetch plan metadata (plan ID path)

Query the state service for the plan's tasks and touched files:

```bash
PLAN_ID="<argument>"
STATE_URL="${CLAW_FORGE_STATE_URL:-http://localhost:8888}"

# Fetch plan details
curl -sf "$STATE_URL/features/$PLAN_ID" 2>/dev/null
```

Parse the JSON response and extract:

| Field | Used for |
|---|---|
| `description` | Keyword extraction (Step 3) |
| `tasks[].description` | Additional keywords |
| `tasks[].files_touched[]` | Seed file list (high-confidence) |
| `domain` | Fallback domain name for Step 2B |

If the state service is unreachable or returns a non-200 status, fall through to **Step 2B**
using the plan ID string itself as the domain name:

```bash
if [ $? -ne 0 ]; then
  echo "State service unavailable — falling back to keyword search for: $PLAN_ID"
  DOMAIN="$PLAN_ID"
fi
```

---

### Step 2B — Derive keywords from domain name

Tokenise the domain string into search terms:

```python
import re

domain = "<argument>"

# Split on spaces, hyphens, underscores, camelCase boundaries
raw_tokens = re.split(r'[\s\-_]+', domain)
camel_split = re.compile(r'(?<=[a-z])(?=[A-Z])')
tokens = []
for tok in raw_tokens:
    tokens.extend(camel_split.split(tok))

# Lower-case, drop tokens shorter than 3 chars
keywords = [t.lower() for t in tokens if len(t) >= 3]
print("Keywords:", keywords)
```

Example: `"userOnboarding"` → `["user", "onboarding"]`

---

### Step 3 — Discover candidate files

Run a fast multi-strategy file search using the extracted keywords.  Do **not** read file
contents — only collect paths.

#### Strategy A — Git log (highest signal)

```bash
# Files most recently touched in commits whose message mentions a keyword
for KW in <keywords>; do
  git log --all --oneline --name-only --grep="$KW" -20 2>/dev/null \
    | grep -E '\.(py|ts|tsx|js|jsx|go|rs|rb|java|kt|swift|yaml|json|toml|md)$'
done | sort | uniq -c | sort -rn | head -40
```

#### Strategy B — Symbol grep (medium signal)

```bash
# Class / function / type definitions that match any keyword
for KW in <keywords>; do
  grep -rn \
    --include='*.py' --include='*.ts' --include='*.tsx' \
    --include='*.js' --include='*.go' --include='*.rs' \
    -l -i "$KW" . 2>/dev/null
done | sort | uniq -c | sort -rn | head -40
```

#### Strategy C — Path name match (low signal)

```bash
# File and directory names that contain a keyword
for KW in <keywords>; do
  find . -type f \
    \( -name "*${KW}*" -o -path "*/${KW}/*" \) \
    -not -path '*/.git/*' \
    -not -path '*/node_modules/*' \
    -not -path '*/__pycache__/*' \
    -not -path '*/dist/*' \
    -not -path '*/build/*' \
    2>/dev/null
done | sort -u
```

Assign a **relevance score** to each candidate path:

| Source | Base score |
|---|---|
| `tasks[].files_touched[]` from state service | 100 |
| Git log hit | 10 × (commit count) |
| Symbol grep hit | 5 × (keyword match count) |
| Path name match | 2 |

If a path appears in multiple strategies, sum the scores.

---

### Step 4 — Filter and rank

Apply exclusion rules before ranking:

```python
EXCLUDE_PATTERNS = [
    r'\.git/',
    r'node_modules/',
    r'__pycache__/',
    r'\.pyc$',
    r'/dist/',
    r'/build/',
    r'\.lock$',           # lockfiles
    r'migrations/\d+_',  # generated migration files (keep migration base files)
    r'\.min\.(js|css)$',  # minified assets
]
```

Then sort descending by score and apply `--max-files` (default: **20**).

For each surviving file, compute a line-count estimate (used downstream for token budgeting):

```bash
wc -l <file_path> 2>/dev/null | awk '{print $1}'
```

---

### Step 5 — Generate search patterns

For every keyword, produce targeted patterns that agents can use with `Grep` or `ripgrep`
to pull *only the relevant sections* from the ranked files — without reading entire files.

```python
patterns = []

for kw in keywords:
    # Definition sites
    patterns.append({
        "label": f"define:{kw}",
        "pattern": rf"(?:class|def|function|fn|type|interface|struct)\s+\w*{kw}\w*",
        "flags": "-i",
        "rationale": f"Symbol definitions matching '{kw}'"
    })
    # Import sites
    patterns.append({
        "label": f"import:{kw}",
        "pattern": rf"(?:import|from|require|use)\s+.*{kw}",
        "flags": "-i",
        "rationale": f"Import statements pulling in '{kw}' components"
    })
    # Route / endpoint sites (web frameworks)
    patterns.append({
        "label": f"route:{kw}",
        "pattern": rf"(?:@\w+\.(?:get|post|put|patch|delete)|router\.\w+)\s*\(['\"].*{kw}",
        "flags": "-i",
        "rationale": f"HTTP endpoints related to '{kw}'"
    })
```

Deduplicate patterns and cap at **15** total.

---

### Step 6 — Emit the ContextManifest

#### Human-readable summary

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Harness Context — <PLAN_ID | domain>
  <N> files · <M> patterns · ~<T> estimated lines
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Ranked Files
────────────────────────────────────────────────────
  #  Score  Lines  Path
  ─────────────────────────────────────────────────
   1   120     84  src/auth/jwt_middleware.py       ← state service + git
   2    55    210  src/models/user.py               ← git + grep
   3    22     47  src/api/auth_routes.py           ← grep + path
   4    10    130  tests/test_auth.py               ← git
   5     4     18  src/auth/__init__.py             ← path
  ...

Search Patterns (apply to ranked files first)
────────────────────────────────────────────────────
  define:auth   (?:class|def|…)\s+\w*auth\w*   -i
  import:auth   (?:import|from|…).*auth         -i
  route:auth    (?:@\w+\.(?:get|…))\(.*auth     -i
  define:jwt    (?:class|def|…)\s+\w*jwt\w*     -i
  ...

Skip List (do not load)
────────────────────────────────────────────────────
  migrations/0042_add_auth_table.py   (generated)
  package-lock.json                   (lockfile)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Tip: read only the top-N files; use patterns to extract
  specific sections rather than loading full contents.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

#### Machine-readable manifest (always emitted after the summary)

```json
{
  "command": "harness context",
  "input": "<plan_id_or_domain>",
  "keywords": ["auth", "jwt"],
  "files": [
    {
      "path": "src/auth/jwt_middleware.py",
      "score": 120,
      "estimated_lines": 84,
      "sources": ["state_service", "git_log"],
      "rationale": "Listed in plan tasks; 12 matching commits"
    },
    {
      "path": "src/models/user.py",
      "score": 55,
      "estimated_lines": 210,
      "sources": ["git_log", "symbol_grep"],
      "rationale": "8 matching commits; defines UserModel"
    }
  ],
  "patterns": [
    {
      "label": "define:auth",
      "pattern": "(?:class|def|function|fn|type|interface|struct)\\s+\\w*auth\\w*",
      "flags": "-i",
      "rationale": "Symbol definitions matching 'auth'"
    }
  ],
  "skip_list": [
    {
      "path": "migrations/0042_add_auth_table.py",
      "reason": "generated migration file"
    }
  ],
  "stats": {
    "total_candidate_files": 34,
    "returned_files": 5,
    "total_estimated_lines": 489,
    "state_service_used": true
  }
}
```

The schema matches `harness_skills.models.context.ContextManifest`.
Consumers should iterate `files` in order, loading only as many as their token budget allows,
and apply `patterns` with `Grep` to extract targeted sections rather than full file reads.

---

### Step 7 — Token budget advisory (optional)

If `--budget <N>` is passed (where N is a token limit, e.g. `--budget 40000`), append a
budget breakdown showing how many files can be loaded within the limit:

```
  Token Budget Advisory  (target: 40 000 tokens)
  ────────────────────────────────────────────────────
  Assume ~4 chars/token → 160 000 chars budget

  File                              Lines  Est. chars  Cumulative
  ─────────────────────────────────────────────────────────────
  src/auth/jwt_middleware.py           84       3 100       3 100  ✅
  src/models/user.py                  210       7 900      11 000  ✅
  src/api/auth_routes.py               47       1 700      12 700  ✅
  tests/test_auth.py                  130       4 900      17 600  ✅
  src/auth/__init__.py                 18         650      18 250  ✅
  ─────────────────────────────────────────────────────────────
  → Load all 5 ranked files comfortably within budget.
    Use patterns on remaining 29 candidates to extract snippets.
```

---

## Options

| Flag | Effect |
|---|---|
| `--max-files N` | Cap returned file list at N entries (default: 20) |
| `--budget N` | Emit a token budget advisory for a context window of N tokens |
| `--format json` | Emit only the raw JSON `ContextManifest`, no human-readable header |
| `--state-url URL` | Override the state service URL (default: `http://localhost:8888`) |
| `--no-git` | Skip git-log strategy (useful in shallow clones or CI detached HEADs) |
| `--include GLOB` | Restrict candidate files to paths matching GLOB (e.g. `"src/**/*.py"`) |
| `--exclude GLOB` | Add an extra exclusion pattern on top of the built-in skip list |

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Start working on a plan — find relevant files fast | **`/harness:context`** ← you are here |
| Verify architecture & principles after editing | `/harness:lint` |
| Full quality gate before merge | `/harness evaluate` or `/check-code` |
| Detect conflicts with other running agents | `/coordinate` |
| Review a PR end-to-end | `/review-pr` |

---

## Notes

- **Read-only** — this skill never modifies files or the state service.
- **No file contents are loaded** — only paths, line counts, and metadata.
  Agents decide which files to actually read based on the manifest.
- **State service is optional** — if unreachable, the skill falls back gracefully to
  git-log + grep + path-name strategies with no loss of correctness (only lower precision
  on the first ranked file).
- **Incremental use** — run with `--max-files 5` for a quick orientation pass, then re-run
  with `--max-files 20` if deeper context is needed.
- **CI-safe** — all strategies use read-only git and grep commands; no network calls are
  made unless the state service URL is reachable.
