# Context Handoff

Write a structured handoff block to the progress log when an agent session ends.
The block encodes *search hints* — file paths, grep patterns, and symbol names — so the
next agent can rebuild full context using its own tools rather than relying on a
pre-assembled memory dump.

## When to use

- **Before any planned agent-session boundary** (context-window limit, task handoff,
  parallel-agent split, or explicit `/checkpoint`)
- **On unexpected termination** — always write a best-effort handoff, even partial
- **After a long research phase** — capture what you discovered so the next agent
  doesn't repeat the same searches
- Pair with `/progress-log` entries so the handoff appears inline in the audit trail

## Design principles

1. **Search hints, not dumps** — record *how to find* information, not the information
   itself. File paths + grep patterns are far more durable than pasted code snippets.
2. **Append-only, atomic** — each `echo >> file` is a single OS write; safe for
   parallel agents sharing the same log.
3. **Self-describing** — a cold-start agent reading only the log file should be able
   to reconstruct working context within 2–3 tool calls.
4. **Minimal, not exhaustive** — 5–10 search hints beat 50 stale ones. Prefer
   precision over completeness.

---

## Instructions

### Step 1: Resolve the log file path

```bash
LOG_FILE="${1:-.claw-forge/progress.log}"
mkdir -p "$(dirname "$LOG_FILE")"
TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
```

### Step 2: Capture session metadata

Collect the values you'll embed in the handoff block. Fill these in from your current
working knowledge — do NOT run extra discovery commands just for the handoff.

```
SESSION_ID   = <agent session identifier, or "agent-$(date +%s)" if unknown>
TASK_TITLE   = <one-line description of the task this session worked on>
COMPLETED    = <comma-separated list of sub-tasks finished this session>
REMAINING    = <comma-separated list of sub-tasks NOT yet done>
BLOCKER      = <blocking issue, or "none">
NEXT_ACTION  = <the single most important thing the next agent should do first>
```

### Step 3: Collect search hints

Enumerate the **minimum set** of hints the next agent needs. Three categories:

#### 3a. File paths

List only files that are *directly relevant* to the incomplete work. Prefer specific
paths over directory globs.

```
files:
  src/auth/oauth.py            # main implementation file — partially complete
  src/models/user.py           # User model, needed by oauth.py
  tests/test_oauth.py          # failing tests that define the target behaviour
  .claw-forge/progress.log     # this file — full audit trail
```

#### 3b. Grep patterns

Write patterns a fresh agent would use with the `Grep` tool to land on the right
symbols immediately. Prefer anchored, specific patterns over broad ones.

```
grep:
  "class OAuthProvider"        # primary class being implemented
  "def token_exchange"         # the method left incomplete (line ~87)
  "TODO: refresh"              # outstanding TODO blocks
  "pytest.mark.integration"    # marks the tests that are failing
  "HANDOFF"                    # find all handoff blocks in this log
```

#### 3c. Relevant symbols

List symbols (classes, functions, constants, DB tables, API endpoints) the next agent
must understand to pick up the work.

```
symbols:
  OAuthProvider                # class — src/auth/oauth.py
  TokenExchange                # dataclass — src/auth/oauth.py:TokenExchange
  UserSession                  # SQLAlchemy model — src/models/user.py
  /auth/token  [POST]          # API endpoint wired in src/api/routes.py
  OAUTH_SCOPES                 # config constant — src/config.py
```

### Step 4: Write the handoff block to the log

Append a delimited `[🤝 HANDOFF]` block. The block is human-readable plain text;
the indented `→` lines carry structured data a downstream agent can parse with simple
grep or string matching.

```bash
cat >> "$LOG_FILE" <<HANDOFF_EOF
[$TIMESTAMP] [🤝 HANDOFF] Session ending — context handoff for next agent
  → session:    $SESSION_ID
  → task:       $TASK_TITLE
  → completed:  $COMPLETED
  → remaining:  $REMAINING
  → blocker:    $BLOCKER
  → next:       $NEXT_ACTION
  →
  → ## SEARCH HINTS — use these with Grep / Read / Glob tools
  →
  → files:
  →   <absolute-or-repo-relative path>   # <why this file matters>
  →   <absolute-or-repo-relative path>   # <why this file matters>
  →
  → grep:
  →   "<pattern>"    # <what it finds>
  →   "<pattern>"    # <what it finds>
  →
  → symbols:
  →   <SymbolName>   # <type> — <file>:<approx-line>
  →   <SymbolName>   # <type> — <file>:<approx-line>
  →
  → ## END HANDOFF
HANDOFF_EOF
```

**Concrete example:**

```bash
cat >> ".claw-forge/progress.log" <<'EOF'
[2026-03-22T09:14:03Z] [🤝 HANDOFF] Session ending — context handoff for next agent
  → session:    agent-1742637243
  → task:       Implement OAuth2 token refresh flow
  → completed:  token exchange endpoint, OAuthProvider scaffold, route wiring
  → remaining:  token_refresh method, expiry handling, integration tests (3 failing)
  → blocker:    none
  → next:       Open src/auth/oauth.py ~line 87 and implement token_refresh()
  →
  → ## SEARCH HINTS — use these with Grep / Read / Glob tools
  →
  → files:
  →   src/auth/oauth.py           # primary file — token_refresh stub at ~line 87
  →   src/models/user.py          # UserSession model with expires_at field
  →   tests/test_oauth.py         # 3 failing integration tests define target behaviour
  →   src/api/routes.py           # POST /auth/token route wired here
  →
  → grep:
  →   "def token_refresh"         # the incomplete stub
  →   "TODO: refresh"             # two TODO blocks inside oauth.py
  →   "expires_at"                # expiry field referenced in failing tests
  →   "pytest.mark.integration"   # marks the 3 failing tests
  →   "HANDOFF"                   # find all handoff blocks in this log
  →
  → symbols:
  →   OAuthProvider               # class       — src/auth/oauth.py:12
  →   token_refresh               # method      — src/auth/oauth.py:87 (stub)
  →   UserSession                 # ORM model   — src/models/user.py:34
  →   /auth/token  [POST]         # API route   — src/api/routes.py:61
  →   OAUTH_TOKEN_TTL             # constant    — src/config.py:18
  →
  → ## END HANDOFF
EOF
```

### Step 5: Verify the block was written

```bash
# Print just the last handoff block
grep -A 30 "🤝 HANDOFF" "$LOG_FILE" | tail -35
```

Expected: the block appears correctly in the log with all `→` lines intact.

### Step 6: (Next agent) Consume the handoff

When a fresh agent session starts, it should:

1. **Read the log tail** to find the most recent `[🤝 HANDOFF]` block:
   ```bash
   grep -A 40 "🤝 HANDOFF" .claw-forge/progress.log | tail -45
   ```

2. **Extract `next:`** — perform that single action first to confirm orientation.

3. **Run each `grep:` hint** using the `Grep` tool to land on exact locations:
   ```
   Grep pattern="def token_refresh" → confirms file + line
   Grep pattern="TODO: refresh"     → surfaces outstanding TODOs
   ```

4. **Read each `files:` entry** using the `Read` tool — only the ones relevant to the
   immediate next action; defer others until needed.

5. **Do NOT** copy-paste symbol descriptions from the handoff block as fact —
   verify them via search. Line numbers drift; patterns stay accurate.

### Step 7: Report the handoff to the state service (optional)

```bash
curl -s -X POST http://localhost:8888/features/$FEATURE_ID/events \
  -H "Content-Type: application/json" \
  -d "{
    \"type\": \"agent.handoff\",
    \"payload\": {
      \"session\": \"$SESSION_ID\",
      \"log_file\": \"$LOG_FILE\",
      \"remaining\": \"$REMAINING\",
      \"next_action\": \"$NEXT_ACTION\"
    }
  }" || true
```

---

## Full handoff log format reference

```
[<ISO-8601 UTC>] [🤝 HANDOFF] Session ending — context handoff for next agent
  → session:    <id>
  → task:       <one-line task title>
  → completed:  <what this session finished>
  → remaining:  <what is left>
  → blocker:    <blocking issue or "none">
  → next:       <first action for the next agent>
  →
  → ## SEARCH HINTS — use these with Grep / Read / Glob tools
  →
  → files:
  →   <path>   # <annotation>
  →
  → grep:
  →   "<pattern>"   # <annotation>
  →
  → symbols:
  →   <Name>   # <type> — <file>:<line>
  →
  → ## END HANDOFF
```

---

## Notes

- **Append-only** — never edit or delete a previous handoff block; append a new one
- **One handoff per session** — write it once, just before the session terminates
- **Line numbers are hints, not contracts** — always verify via grep, never hard-code
- **Grep patterns over file excerpts** — a pattern survives refactoring; a pasted
  snippet goes stale immediately
- **`## END HANDOFF` delimiter** — allows downstream tooling (or agents) to extract
  the block with a simple `awk '/HANDOFF/,/END HANDOFF/'` slice
- Pair with `/checkpoint` for git-level durability; pair with `/progress-log` for
  the step-level audit trail
