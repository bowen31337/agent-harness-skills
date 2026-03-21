---
name: context-handoff
description: "Context handoff protocol for multi-session agent work. When an agent session ends, write a structured summary to the plan progress log so the next agent can continue seamlessly. The handoff contains search hints — specific file paths, grep patterns, glob patterns, and symbol names — that let the next agent rebuild its own context using Read/Grep/Glob tools, rather than relying on pre-assembled content dumps. Use when: (1) ending an agent session where work continues, (2) starting work previously begun by another agent, (3) writing or reading session handoffs, (4) resuming from a previous agent session, (5) implementing multi-agent context continuity, (6) approaching context window limits mid-task. Triggers on: write handoff, session ending, context handoff, hand off context, resume from previous session, pick up where we left off, context window full."
---

# Context Handoff Protocol

## Workflow

**Are you ending a session?** → [Write a Handoff](#ending-session-write-handoff)

**Are you starting from a handoff?** → [Resume from Handoff](#resuming-session-use-the-handoff)

---

## Ending Session: Write Handoff

Before stopping, write the handoff to `.claude/plan-progress.md`.

Use your `Write` tool to create or overwrite that file with the exact format below.
See [references/handoff-format.md](references/handoff-format.md) for a worked example and field-by-field guidance.

```markdown
---
session_id: "<session id if known, else 'unknown'>"
timestamp: "<UTC ISO-8601, e.g. 2026-03-14T10:30:00Z>"
task: "<one-line description of the overall task>"
status: "<in_progress | blocked | done>"
---

## Accomplished
- <bullet: concrete item completed>

## In Progress
- <bullet: partially-done work — what's left and ~% complete>

## Next Steps
- <ordered action for the next agent>

## Search Hints
### Key Files
- <relative/path/to/file.py> — <why it matters>

### Key Directories
- <src/module/> — <what lives here>

### Grep Patterns
```
class MyClass
def authenticate
TODO.*payment
```

### Key Symbols
- MyClass
- authenticate_user
- PAYMENT_TIMEOUT

## Open Questions
- <unresolved decision or blocker>

## Artifacts
- <file created or significantly modified this session>

## Notes
<free-form context that doesn't fit above>
```

**Search hints philosophy — hints, not dumps.**
Give the next agent a *map*, not the *territory*. List file paths and grep patterns so it can read the actual current code itself. Never paste file contents into the handoff — those go stale and bloat the context.

---

## Resuming Session: Use the Handoff

1. **Read the handoff file** with the `Read` tool:
   ```
   Read: .claude/plan-progress.md
   ```

2. **Run the search hints** to verify current code (do NOT trust handoff descriptions as ground truth — always verify):
   - `Read` each file in **Key Files**
   - `Grep` each pattern in **Grep Patterns**
   - `Glob` each pattern in **Key Directories** to discover structure
   - Search for each **Key Symbol** with `Grep`

3. **Continue from Next Steps** — unless your search reveals a reason to change course.

4. **Overwrite the handoff** when your own session ends, with a fresh summary reflecting the updated state.

---

## CLI: Write a Handoff from Bash

Use `skills/write_handoff.py` when you want to record the handoff by running a
script instead of composing Markdown by hand with the `Write` tool.

```bash
# Minimal — just task, status, and search hints:
python skills/write_handoff.py \
    --task "Add JWT authentication" \
    --status in_progress \
    --key-files "src/auth/service.py" "src/config.py" \
    --grep "class AuthService" "def validate_token" \
    --symbols "AuthService" "JWT_SECRET"

# Full handoff with all fields + progress log row:
python skills/write_handoff.py \
    --task "Add JWT authentication" \
    --status in_progress \
    --accomplished "Scaffolded AuthService" "Added JWT config" \
    --in-progress "Wiring middleware (~30% done)" \
    --next-steps "Import AuthService in gateway.py" "Wire into handle_request()" \
    --key-files "src/auth/service.py — AuthService class" \
               "src/api/gateway.py — wire here" \
    --key-dirs "src/auth/" "src/api/" \
    --grep "class AuthService" "def handle_request" "JWT_SECRET" \
    --symbols "AuthService" "handle_request" "JWT_SECRET" \
    --open-questions "Should tokens expire after 1h or 24h?" \
    --artifacts "src/auth/service.py (new)" "src/config.py (modified)" \
    --notes "Using PyJWT 2.x — import is jwt not JWT" \
    --also-progress-log \
    --plan-id "feature/jwt-auth" \
    --agent-id "agent/coder-v1"
```

The script writes three things:
1. **`.claude/plan-progress.md`** — overwrites with the latest Markdown handoff.
2. **`.plan_progress.jsonl`** — appends one JSON line (append-only audit trail).
3. **`docs/exec-plans/progress.md`** — appends a summary row (when `--also-progress-log`).

---

## Programmatic Integration (Agent SDK)

The `HandoffTracker` (hook-based, JSONL + progress log) and `HandoffProtocol`
(system-prompt injection, Markdown) Python classes live in `harness_skills`:

```python
# Hook-based — auto-syncs handoff to JSONL + progress log on Stop event
from harness_skills.handoff import HandoffTracker
from claude_agent_sdk import ClaudeAgentOptions

tracker = HandoffTracker(
    task="Add rate-limiting to API gateway",
    plan_id="feature/rate-limiting",
    agent_id="agent/coder-v1",
)

# Ending session — inject writing instructions + register Stop hook
options = ClaudeAgentOptions(
    system_prompt=tracker.system_prompt_addendum(),
    hooks=tracker.hooks(),
)

# After the session ends, read from the JSONL audit log:
resume_prompt = HandoffTracker.get_resume_prompt()   # pre-rendered preamble
search_hints  = HandoffTracker.get_search_hints()    # SearchHints object
```

```python
# Protocol-based — injects instructions into system prompt only
from harness_skills.handoff import HandoffProtocol

protocol = HandoffProtocol()
options       = protocol.ending_agent_options(base_options, task="...")   # ending
options, doc  = protocol.resuming_agent_options(base_options)             # resuming
```

### How `HandoffTracker` works

```
Ending session:
  1. tracker.system_prompt_addendum() → injected into agent system prompt
  2. Agent writes .claude/plan-progress.md using its Write tool
  3. Session ends → Stop hook fires automatically:
       a. Reads .claude/plan-progress.md
       b. Appends JSON line to .plan_progress.jsonl  (audit trail)
       c. Appends summary row to docs/exec-plans/progress.md

Resuming session:
  HandoffTracker.get_resume_prompt()  ← reads from .plan_progress.jsonl
  HandoffTracker.get_search_hints()   ← parses hints from latest JSONL entry
```

### Key files

| Path | Purpose |
|------|---------|
| `harness_skills/handoff.py` | `HandoffDocument`, `SearchHints`, `HandoffProtocol`, `HandoffTracker`, `_append_jsonl`, `_append_progress_log_entry` |
| `skills/write_handoff.py` | CLI — write a handoff from Bash arguments |
| `skills/context-handoff/scripts/read_handoff.py` | CLI — display a saved handoff |
| `.claude/plan-progress.md` | Latest Markdown handoff (overwritten each session) |
| `.plan_progress.jsonl` | Append-only JSONL audit trail across all sessions |

See [references/handoff-format.md](references/handoff-format.md) for the full format reference and a worked example.
