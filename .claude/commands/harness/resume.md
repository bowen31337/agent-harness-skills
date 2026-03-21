# Harness Resume

Load the most recent plan state from `.claude/plan-progress.md` (and, when available,
`.plan_progress.jsonl`) and present a structured context handoff so an incoming agent
can continue seamlessly from where the previous session left off.

Use this skill at the **start** of any agent session that picks up prior work, or
whenever you need to answer: *"Where exactly did the last session stop, and what do I
do next?"*

---

## Usage

```bash
# Read plan-progress.md from the default location
/harness:resume

# Read from a custom path
/harness:resume --file path/to/plan-progress.md

# Also surface the last N JSONL entries (full audit trail)
/harness:resume --history 5

# Emit only the structured JSON block (no human-readable header)
/harness:resume --format json
```

---

## Instructions

### Step 1 — Locate the handoff file

Check for the Markdown handoff in order of preference:

```bash
# 1. Argument-supplied path (if --file was passed)
# 2. Default location
ls .claude/plan-progress.md 2>/dev/null || echo "__MISSING__"
```

**If the file is missing:**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Harness Resume — ⚠ NO HANDOFF FOUND
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  .claude/plan-progress.md does not exist.

  This means either:
    • No previous agent wrote a handoff for this session, or
    • The handoff was written to a non-standard location.

  Next steps:
    1. Run /harness:context <domain> to orient on the codebase.
    2. Check .plan_progress.jsonl for a JSONL audit trail.
    3. Ask the user to describe the task to start fresh.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Stop here if the file is missing (unless `--history` was also passed — in that case
proceed to Step 2B for JSONL only).

---

### Step 2A — Read the Markdown handoff

Use the `Read` tool to load `.claude/plan-progress.md` (or the `--file` path).

Parse the YAML frontmatter and body sections:

| Section | Extracted fields |
|---|---|
| Frontmatter | `session_id`, `timestamp`, `task`, `status` |
| `## Accomplished` | List of completed items |
| `## In Progress` | List of in-progress items with % complete |
| `## Next Steps` | Ordered action list |
| `## Search Hints` | Key Files, Key Directories, Grep Patterns, Key Symbols |
| `## Open Questions` | Unresolved decisions or blockers |
| `## Artifacts` | Files created or significantly modified |
| `## Notes` | Free-form context |

---

### Step 2B — Read JSONL history (optional, `--history N`)

If `--history N` is passed (or if the Markdown file was missing), check for the JSONL
audit trail:

```bash
ls .plan_progress.jsonl 2>/dev/null || echo "__MISSING__"
```

If present, extract the last N lines:

```bash
tail -n <N> .plan_progress.jsonl
```

Each line is a standalone JSON object. Parse and display them in reverse-chronological
order (most recent first) in a collapsible **Audit Trail** section after the main
handoff block.

---

### Step 3 — Verify search hints against live code

> **Do not trust the handoff descriptions as ground truth.** Always verify with the
> actual tools so you see the *current* state of the code, not a potentially stale
> description.

For each item in **Search Hints**, run the corresponding tool:

| Hint type | Tool | Action |
|---|---|---|
| Key Files | `Read` | Read each listed file |
| Key Directories | `Glob` | `Glob("<dir>/**/*")` to list structure |
| Grep Patterns | `Grep` | Run each pattern across the repo |
| Key Symbols | `Grep` | Search for each symbol name |

Collect the verification results. Note any **discrepancies** (e.g. a file listed in
the handoff that no longer exists, a symbol that has been renamed).

Report discrepancies clearly in the output under a **⚠ Drift Detected** callout.

---

### Step 4 — Emit the human-readable resume report

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Harness Resume — <status icon> <STATUS>
  Task: <task>
  Session: <session_id>  ·  Saved: <timestamp>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Accomplished
────────────────────────────────────────────────────
  • <item>
  • <item>

In Progress
────────────────────────────────────────────────────
  • <item (~X% complete)>

Next Steps  ← start here
────────────────────────────────────────────────────
  1. <action>
  2. <action>
  3. <action>

Open Questions
────────────────────────────────────────────────────
  • <question>

Artifacts (created / significantly modified)
────────────────────────────────────────────────────
  • <file>

Search Hints — Verified ✅ / Drifted ⚠
────────────────────────────────────────────────────
  Key Files
    ✅  src/api/gateway.py            — wire RateLimiter into handle_request()
    ⚠   src/db/cache.py              — FILE NOT FOUND (may have been renamed)

  Key Directories
    ✅  src/api/
    ✅  tests/

  Grep Patterns
    ✅  class RateLimiter             — found in src/api/rate_limit.py:12
    ✅  def handle_request            — found in src/api/gateway.py:47

  Key Symbols
    ✅  RateLimiter
    ⚠   redis_client                 — SYMBOL NOT FOUND (check for rename)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Notes
  <free-form notes from handoff>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Status icon mapping:

| `status` field | Icon |
|---|---|
| `in_progress` | 🔄 IN PROGRESS |
| `blocked` | 🔴 BLOCKED |
| `done` | ✅ DONE |

---

### Step 5 — Emit the machine-readable resume block

Always append a fenced JSON block after the human-readable section so downstream
agents can act on it without re-parsing the Markdown:

```json
{
  "command": "harness resume",
  "handoff_file": ".claude/plan-progress.md",
  "session_id": "<session_id>",
  "timestamp": "<ISO-8601>",
  "task": "<task>",
  "status": "<status>",
  "next_steps": [
    "<step 1>",
    "<step 2>"
  ],
  "search_hints": {
    "key_files": [
      { "path": "src/api/gateway.py", "note": "wire RateLimiter here", "verified": true }
    ],
    "key_directories": [
      { "path": "src/api/", "verified": true }
    ],
    "grep_patterns": [
      { "pattern": "class RateLimiter", "verified": true, "found_in": "src/api/rate_limit.py:12" }
    ],
    "key_symbols": [
      { "symbol": "RateLimiter", "verified": true },
      { "symbol": "redis_client", "verified": false, "drift_note": "symbol not found" }
    ]
  },
  "open_questions": ["<question>"],
  "artifacts": ["<file>"],
  "drift_detected": false,
  "notes": "<free-form notes>"
}
```

Set `drift_detected: true` if any search hint verification failed.

---

### Step 6 — Recommend next action

After the JSON block, emit a single concise recommendation:

**No drift detected:**
```
▶ Ready to continue. Begin at Next Step 1:
  "<step 1 text>"
```

**Drift detected:**
```
⚠ Drift detected in search hints — review the flagged items above before
  proceeding. The codebase may have changed since the last session.
  Suggested first action: re-read the drifted files / search for renamed symbols,
  then continue from Next Step 1.
```

**Status is `blocked`:**
```
🔴 The previous session ended in a BLOCKED state.
  Open Questions that may be the cause:
    • <question>
  Resolve the blocker before starting Next Steps, or run /coordinate to check
  for conflicting agents.
```

**Status is `done`:**
```
✅ The previous session marked this task DONE.
  If work remains, the handoff status may be stale — update it and continue.
  Otherwise, this task is complete — no further action needed.
```

---

## Options

| Flag | Default | Effect |
|---|---|---|
| `--file PATH` | `.claude/plan-progress.md` | Path to the Markdown handoff file |
| `--history N` | `0` (disabled) | Show the last N entries from `.plan_progress.jsonl` |
| `--no-verify` | off | Skip Step 3 (search hint verification) — faster, but no drift detection |
| `--format json` | off | Emit only the raw JSON block, no human-readable header |

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Start a session that continues prior work | **`/harness:resume`** ← you are here |
| End a session and write a handoff | `/context-handoff` (write mode) |
| Find relevant files for a plan by ID or domain | `/harness:context` |
| Detect whether a plan has stalled | `/harness:detect-stale` |
| Check for conflicts with other running agents | `/coordinate` |

---

## Notes

- **Read-only** — this skill never modifies any file.
- **Verify, don't trust** — search hint verification (Step 3) is enabled by default
  because handoffs can go stale. Use `--no-verify` only when speed is critical and
  you are confident the codebase has not changed.
- **JSONL trail is append-only** — `.plan_progress.jsonl` preserves the full session
  history across all agents. Use `--history N` to surface earlier sessions if the
  Markdown handoff is insufficient.
- **Drift is normal** — a few drifted symbols or renamed files does not mean the
  handoff is useless. Read the drifted items, adapt, and continue.
