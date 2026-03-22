# Harness Handoff

Write a structured context handoff when an agent session ends.  The handoff is
saved to `.claude/plan-progress.md` (latest-wins) and appended as one JSON line
to `.plan_progress.jsonl` (append-only audit trail).  A one-line summary is also
appended to the progress log so the plan's timeline stays current.

The next agent reads the handoff with `/harness:resume` and uses the search hints
— file paths, grep patterns, symbol names — to **rebuild its own context** with
`Read`, `Grep`, and `Glob`.  No file contents are ever embedded; only pointers.

---

## Usage

```bash
# Write handoff for the current session (interactive — you fill in the fields)
/harness:handoff

# Mark the task as blocked (default: in_progress)
/harness:handoff --status blocked

# Mark the task as fully complete
/harness:handoff --status done

# Also append a row to the progress log for a specific plan
/harness:handoff --plan-id FEAT-42

# Skip the progress log append
/harness:handoff --no-progress-log

# Write to a non-default handoff path
/harness:handoff --file path/to/plan-progress.md
```

---

## Instructions

### Step 1 — Gather session context

Determine the overall **task** (one-line description of what this session was
working on).  Sources in priority order:

1. `--task` argument if provided
2. The most recent user message that describes the goal
3. The last human turn in the conversation

Also determine the **status** from the `--status` argument (default: `in_progress`).

---

### Step 2 — Discover search hints (active scan)

> **Goal:** produce a compact set of hints the *next* agent can use with its own
> tools — not a content dump.  Run these discovery commands to find signal; do
> **not** read file contents.

#### 2A — Recently-modified files (git)

```bash
# Files changed in the last 20 commits across any branch
git log --all --oneline --name-only -20 2>/dev/null \
  | grep -E '\.(py|ts|tsx|js|jsx|go|rs|rb|java|kt|yaml|json|toml|md)$' \
  | sort | uniq -c | sort -rn | head -20
```

Pick the **top 8** by commit frequency — these are the files most central to
recent work.

#### 2B — Staged / unstaged changes (current session)

```bash
git diff --name-only 2>/dev/null
git diff --cached --name-only 2>/dev/null
```

Any file appearing here is definitely relevant — add it to Key Files at score 100.

#### 2C — Symbol extraction (definition sites)

For each Key File found above, generate grep patterns that will find their most
important definitions:

```python
# For a Python file src/auth/service.py — infer patterns like:
patterns = [
    "class AuthService",
    "def authenticate",
    "def validate_token",
]
# Strategy: look for `class ` and `def ` anchors; use the class/function name
# as a Key Symbol.  Cap at 3 patterns per file; cap total at 15.
```

You do **not** read the file — you generate patterns from the file's path and any
names mentioned in the conversation.  If explicit symbol names were mentioned
(e.g., `RateLimiter`, `UserModel`), add them directly.

#### 2D — Key directories (structural)

Infer from the Key Files which parent directories are most relevant:

```python
dirs = set()
for path in key_files:
    # Add the immediate parent
    dirs.add(str(Path(path).parent) + "/")
# Deduplicate and keep at most 5
```

---

### Step 3 — Compose the handoff sections

From the current conversation, extract:

| Section | What to include |
|---|---|
| `## Accomplished` | Concrete items **completed** in this session. Be specific — name files, functions, tests. |
| `## In Progress` | Partially-done work. **Must** include % complete and exactly what remains. |
| `## Next Steps` | **Ordered** list — the next agent starts at item 1.  Each step must be actionable (name the file and function, not "continue the work"). |
| `## Open Questions` | Genuine blockers or decisions the next agent must make. Omit if none. |
| `## Artifacts` | Every file created or significantly modified in this session (relative paths). |
| `## Notes` | Architecture decisions, gotchas, library quirks that don't fit above. |

**Quality rules (enforce before writing):**

- Next Steps must be ordered and actionable — never "continue the work"
- Key Files must be ≤ 8 entries
- Grep patterns must be paste-ready (no glob wildcards as patterns)
- Key Symbols must match actual identifiers (no guesses)
- No file contents are ever included — only paths and patterns
- In Progress entries include % complete and what specifically remains

---

### Step 4 — Write the handoff to `.claude/plan-progress.md`

Use the `Write` tool to **overwrite** `.claude/plan-progress.md` with the exact
format below.  The file is always the latest snapshot — previous versions survive
only in `.plan_progress.jsonl`.

```markdown
---
session_id: "<session ID from SystemMessage.session_id, or 'unknown'>"
timestamp: "<UTC ISO-8601, e.g. 2026-03-22T10:30:00Z>"
task: "<one-line description of the overall task>"
status: "<in_progress | blocked | done>"
---

## Accomplished
- <bullet: concrete completed item>

## In Progress
- <bullet: partially-done work — what remains + ~% complete>

## Next Steps
- <ordered action for the next agent — name file + function>

## Search Hints
### Key Files
- <relative/path/to/file.py> — <one-line: why it matters>

### Key Directories
- <src/module/> — <one-line: what lives here>

### Grep Patterns
```
class MyClass
def authenticate
TODO.*payment
RATE_LIMIT_WINDOW
```

### Key Symbols
- MyClass
- authenticate_user
- PAYMENT_TIMEOUT

## Open Questions
- <unresolved decision or blocker — omit section if none>

## Artifacts
- <relative/path/created_or_modified.py>

## Notes
<free-form context — architecture decisions, gotchas, library quirks>
```

**Parent directory** `.claude/` must exist.  If it does not, create it first.

---

### Step 5 — Append to `.plan_progress.jsonl`

After writing the Markdown file, append one JSON line to `.plan_progress.jsonl`.
This file is **append-only** — never overwrite it.

If `skills/write_handoff.py` is available, use it:

```bash
python skills/write_handoff.py \
    --task   "<task>" \
    --status "<status>" \
    --session-id "<session_id>" \
    --accomplished <accomplished items…> \
    --in-progress  <in_progress items…> \
    --next-steps   <next_steps items…> \
    --key-files    <key_files…> \
    --key-dirs     <key_dirs…> \
    --grep         <grep_patterns…> \
    --symbols      <symbols…> \
    --open-questions <open_questions…> \
    --artifacts    <artifacts…> \
    --notes        "<notes>"
```

If the script is not available, write the JSONL entry directly with the `Write`
tool by appending a single JSON line:

```json
{"session_id":"<id>","timestamp":"<ts>","task":"<task>","status":"<status>","accomplished":[…],"in_progress":[…],"next_steps":[…],"search_hints":{"file_paths":[…],"directories":[…],"grep_patterns":[…],"symbols":[…]},"open_questions":[…],"artifacts":[…],"notes":"…"}
```

---

### Step 6 — Append to the progress log

Append a one-line summary to `.claw-forge/progress.log` (create if absent).

Status mapping:

| Handoff `status` | Progress log symbol |
|---|---|
| `in_progress` | `🔄 RETRY` |
| `blocked` | `⏳ WAIT` |
| `done` | `✅ DONE` |

```bash
TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
LOG_FILE=".claw-forge/progress.log"
mkdir -p .claw-forge

# Build a compact one-line message
#   e.g. "context-handoff — 3 accomplished; next: Wire RateLimiter into gateway.py"
N_DONE=<count of accomplished items>
NEXT_STEP=<first item from Next Steps, truncated to 60 chars>
MESSAGE="context-handoff — ${N_DONE} accomplished; next: ${NEXT_STEP}"

echo "[$TIMESTAMP] [<STATUS_SYMBOL>] context-handoff — ${MESSAGE}" >> "$LOG_FILE"
echo "  → handoff: .claude/plan-progress.md | hints: <N> files, <M> patterns, <K> symbols" >> "$LOG_FILE"
```

Skip this step if `--no-progress-log` was passed.

If `--plan-id` was provided, also call the Python API to write a typed row:

```bash
python skills/write_handoff.py \
    … same args as Step 5 … \
    --also-progress-log \
    --plan-id "<plan_id>" \
    --agent-id "$(hostname 2>/dev/null || echo unknown)"
```

---

### Step 7 — Optionally report to state service

If a `--plan-id` was provided **and** the state service is reachable:

```bash
PLAN_ID="<plan_id>"
STATE_URL="${CLAW_FORGE_STATE_URL:-http://localhost:8888}"
STATUS="<handoff_status>"

curl -sf -X POST "$STATE_URL/features/$PLAN_ID/events" \
  -H "Content-Type: application/json" \
  -d "{
    \"type\": \"context.handoff\",
    \"payload\": {
      \"status\": \"$STATUS\",
      \"handoff_file\": \".claude/plan-progress.md\",
      \"hints\": {
        \"files\": <N>,
        \"patterns\": <M>,
        \"symbols\": <K>
      }
    }
  }" 2>/dev/null || true
```

Silently skip if the state service is unreachable (the `|| true` absorbs the error).

---

### Step 8 — Emit the confirmation

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Harness Handoff — <STATUS_ICON> <STATUS>
  Task: <task>
  Session: <session_id>  ·  Written: <timestamp>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Handoff written to  : .claude/plan-progress.md
JSONL audit trail   : .plan_progress.jsonl
Progress log        : .claw-forge/progress.log  [<STATUS_SYMBOL>]

Search Hints Summary
────────────────────────────────────────────────────
  Key Files  (<N>):
    - <file 1>
    - <file 2>
    …

  Key Directories  (<N>):
    - <dir 1>
    …

  Grep Patterns  (<M>):
    <pattern 1>
    <pattern 2>
    …

  Key Symbols  (<K>):
    - <symbol 1>
    …

Next Steps (for the resuming agent)
────────────────────────────────────────────────────
  1. <next step 1>
  2. <next step 2>
  …

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Next agent: run /harness:resume to load this handoff.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Status icon mapping:

| `status` | Icon |
|---|---|
| `in_progress` | 🔄 IN PROGRESS |
| `blocked` | 🔴 BLOCKED |
| `done` | ✅ DONE |

Always append a machine-readable JSON block:

```json
{
  "command": "harness handoff",
  "handoff_file": ".claude/plan-progress.md",
  "jsonl_file": ".plan_progress.jsonl",
  "session_id": "<session_id>",
  "timestamp": "<ISO-8601>",
  "task": "<task>",
  "status": "<status>",
  "search_hints": {
    "key_files": ["<path>", "…"],
    "key_directories": ["<dir>/", "…"],
    "grep_patterns": ["<pattern>", "…"],
    "key_symbols": ["<symbol>", "…"]
  },
  "next_steps": ["<step 1>", "…"],
  "stats": {
    "accomplished_count": 0,
    "in_progress_count": 0,
    "artifact_count": 0,
    "hint_files": 0,
    "hint_patterns": 0,
    "hint_symbols": 0
  }
}
```

---

## Options

| Flag | Default | Effect |
|---|---|---|
| `--status STATUS` | `in_progress` | Session outcome: `in_progress \| blocked \| done` |
| `--task TEXT` | *(from conversation)* | Override the task description |
| `--plan-id ID` | *(none)* | Report to state service and tag progress log row |
| `--file PATH` | `.claude/plan-progress.md` | Write handoff to a non-default path |
| `--no-progress-log` | off | Skip Step 6 (progress log append) |
| `--no-jsonl` | off | Skip Step 5 (JSONL audit trail append) |
| `--no-state-service` | off | Skip Step 7 even if `--plan-id` is set |

---

## Search Hints Philosophy

> **Give the next agent a map, not the territory.**

The next agent uses `Read`, `Grep`, and `Glob` with its *own* tools to verify
the current state of the code.  Embedding file contents in the handoff creates
stale, bloated context.  Instead:

- **Key Files** → the next agent calls `Read` on each path and sees today's code.
- **Grep Patterns** → the next agent runs `Grep` and finds the exact current line.
- **Key Symbols** → the next agent searches for `class Foo` and adapts if renamed.

A drifted hint (file moved, symbol renamed) is caught by `/harness:resume`'s
drift-detection step before any work starts.

---

## Anti-patterns (never do these)

| Anti-pattern | Why it fails | Fix |
|---|---|---|
| Pasting file contents into the handoff | Goes stale; bloats next session's context | Use file path + grep pattern instead |
| Vague next steps ("continue the work") | Next agent has no starting point | Name the exact file and function to modify |
| More than 8 key files | Agent reads everything, loses focus | Keep to the 5–8 most critical |
| Generic grep patterns (`*.py`) | Too much noise, no signal | Use class/function names or specific strings |
| Missing % complete in In Progress | Next agent re-does finished work | Always state what's done and what specifically remains |
| `status=done` when work remains | Misleads orchestrators | Use `in_progress` until fully complete |

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| End a session where work continues | **`/harness:handoff`** ← you are here |
| Start a session that picks up prior work | `/harness:resume` |
| Find relevant files for a plan by ID or domain | `/harness:context` |
| Check for conflicts with other running agents | `/coordinate` |
| Detect whether a plan has stalled | `/harness:detect-stale` |
| Full quality gate before merge | `/harness:evaluate` |

---

## Notes

- **Overwrites** `.claude/plan-progress.md` — the Markdown file always reflects
  the *latest* session.  The full history lives in `.plan_progress.jsonl`.
- **Progress log is append-only** — `.claw-forge/progress.log` is never truncated.
  Multiple concurrent agents can safely append; each `echo … >>` is an atomic OS write.
- **State service is optional** — if unreachable, the skill continues silently.
  The Markdown and JSONL writes are the authoritative record.
- **Run at session end** — not mid-session.  If context limits are approaching,
  run `/harness:handoff` before the window fills and restart from `/harness:resume`.
- **Idempotent writes** — running the skill twice in the same session overwrites
  the Markdown and appends a second JSONL entry.  Downstream consumers use the
  *latest* Markdown; the JSONL trail preserves both writes for debugging.
