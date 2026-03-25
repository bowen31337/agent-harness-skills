# Coordinate — Cross-Agent Task Conflict Dashboard

Analyse all running agents, detect file-level conflicts, and suggest a task
ordering that minimises merge collisions.

## What it shows

- **Agent roster**: every active session with its current task and status
- **File conflict matrix**: which pairs of agents are touching the same paths
- **Conflict severity**: low (different functions) / medium (same file) / high (same region)
- **Reorder suggestions**: a prioritised execution plan that serialises conflicting tasks
- **Blocked tasks**: tasks that cannot proceed until a dependency finishes

## Usage

```bash
# Live data from the state service
python coordinate.py

# Point at a non-default state service
python coordinate.py --state-url http://localhost:8420

# Show demo data without a running state service
python coordinate.py --demo

# Output JSON instead of a formatted table (for piping / CI)
python coordinate.py --json
```

## Instructions

### Step 1 — Run the coordination script

```bash
python coordinate.py
```

If the state service is offline the script falls back to git-branch analysis.
Pass `--demo` to explore the output format without any live agents.

### Step 2 — Read the Agent Status table

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Cross-Agent Coordination — claw-forge
  Snapshot: 2026-03-13 14:02:11  |  Agents: 4  |  Conflicts: 3
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Agent               Task                          Status      Files
  ──────────────────────────────────────────────────────────────────
  agent-a (feat/auth) Add JWT middleware            🟡 running   7
  agent-b (feat/api)  Refactor user endpoints       🟡 running   5
  agent-c (feat/db)   Migrate schema v3             🟢 pending   3
  agent-d (feat/ui)   Update login form             🟡 running   4
```

- 🟢 pending — queued, not started
- 🟡 running — actively editing files
- 🔵 paused  — waiting for a dependency
- ✅ done    — finished, branch ready to merge
- 🔴 blocked — dependency failed or conflict lock held

### Step 3 — Read the Conflict Matrix

```
  Conflict Analysis
  ─────────────────────────────────────────────────────────────────
  🔴 HIGH   agent-a × agent-b  →  src/middleware/auth.py (+3 shared regions)
  🟡 MED    agent-a × agent-d  →  src/models/user.py
  🟡 MED    agent-b × agent-c  →  src/db/schema.py
```

Severity rules:
- **HIGH** — agents overlap on the *same function or class block* (line ranges intersect)
- **MEDIUM** — agents touch the *same file* but different sections
- **LOW** — agents touch files that import each other (indirect coupling)

### Step 4 — Read the Suggested Execution Order

Claude analyses the conflict graph and outputs a safe serialisation:

```
  Suggested Execution Order  (minimises merge conflicts)
  ─────────────────────────────────────────────────────────────────
  Slot 1 — run in parallel:  agent-c  agent-d
  Slot 2 — run in parallel:  agent-b
  Slot 3 — run in parallel:  agent-a

  Rationale:
  • agent-c and agent-d have no shared files — safe to parallelise.
  • agent-b must finish before agent-a: both edit auth.py at overlapping
    line ranges. Serialising removes the HIGH conflict.
  • agent-d touches user.py (read-only import) — safe alongside agent-c.

  Expected merge savings: 2 of 3 conflicts eliminated.
```

### Step 5 — Act on the recommendations

| Recommendation type | Action |
|---|---|
| Serialise HIGH conflict | Pause the later agent, let the earlier one merge first |
| Serialise MEDIUM conflict | Add a dependency in `claw-forge.yaml` or the task state |
| LOW coupling only | Safe to run in parallel; review imports after merge |
| Blocked task | Check the dependency's status; intervene if stuck |

### Step 6 — Re-run after changes

After pausing or re-sequencing agents, run `coordinate` again to confirm the
conflict count dropped to zero.

## Requirements

- **State service** (`claw-forge state`) for live agent/task data — or `--demo` mode
- **Git** for branch-level file enumeration when state is unavailable
- **Python ≥ 3.11** and `claude-agent-sdk` installed (`uv add claude-agent-sdk`)
- `ANTHROPIC_API_KEY` or `ANTHROPIC_OAUTH_TOKEN` in environment / `.env`
