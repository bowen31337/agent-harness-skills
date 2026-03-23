# Harness Task Lock

Acquire, inspect, extend, and release **exclusive task locks** that prevent
concurrent modification of a plan task by multiple agents.

Before any agent begins work on a task it calls `/harness:task-lock acquire`.
While the lock is held, every other agent that attempts to acquire the same
task receives a conflict signal and must back off.  Locks auto-expire after a
configurable timeout so a crashed agent never leaves a task permanently
blocked.

---

## Lock file format

Each lock is a JSON file stored at `.claude/task-locks/<task_id>.lock`:

```json
{
  "task_id":         "feature/auth-refactor",
  "agent_id":        "agent-42",
  "acquired_at":     "2026-03-13T10:00:00+00:00",
  "expires_at":      "2026-03-13T10:05:00+00:00",
  "timeout_seconds": 300.0
}
```

| Field | Type | Description |
|---|---|---|
| `task_id` | string | Unique identifier of the plan task being locked |
| `agent_id` | string | Identifier of the agent that holds the lock |
| `acquired_at` | ISO-8601 UTC | Timestamp when the lock was acquired |
| `expires_at` | ISO-8601 UTC | Timestamp when the lock auto-expires |
| `timeout_seconds` | float | Configured TTL for this lock (default: 300 s) |

The lock file is created atomically with `O_CREAT | O_EXCL` so only one agent
can win a concurrent race.

---

## Usage

```bash
# Acquire a lock on task "TASK-003" as "agent-42" (default 5-minute TTL)
/harness:task-lock acquire --task-id TASK-003 --agent-id agent-42

# Acquire with a custom 10-minute TTL
/harness:task-lock acquire --task-id TASK-003 --agent-id agent-42 --timeout 600

# Check whether a task is locked and who holds it
/harness:task-lock status --task-id TASK-003

# List all active (non-expired) locks
/harness:task-lock list

# Release the lock when work is done
/harness:task-lock release --task-id TASK-003 --agent-id agent-42

# Force-release a lock held by any agent (admin / crash recovery)
/harness:task-lock release --task-id TASK-003 --agent-id agent-42 --force

# Remove all expired lock files
/harness:task-lock sweep

# Use a custom lock directory (e.g. per-project isolation)
/harness:task-lock --locks-dir /tmp/my-locks list
```

---

## Instructions

### Step 1 — Decide which sub-command to run

| Goal | Sub-command |
|---|---|
| Start work on a task | `acquire` |
| Finish or abort work | `release` |
| Keep working past the TTL | `extend` (Python API) |
| Check who owns a task | `status` |
| See all held locks | `list` |
| Remove stale lock files | `sweep` |

---

### Step 2A — Acquire a lock (before starting work)

```bash
python task_lock.py acquire \
  --task-id  <TASK_ID>  \
  --agent-id <AGENT_ID> \
  --timeout  <SECONDS>
```

**Success output:**

```
  ✅  Lock acquired
       task_id    : TASK-003
       agent_id   : agent-42
       acquired_at: 2026-03-13T10:00:00
       expires_at : 2026-03-13T10:05:00
       remaining  : 5m 00s
```

**Conflict output (another agent holds the lock):**

```
  ❌  Could not acquire lock: Task 'TASK-003' is locked by agent 'agent-99'
      (expires in 287s)
```

**Conflict protocol** — when acquire fails the calling agent must:
1. Log the conflict and the lock holder's `agent_id`.
2. Check `/harness:task-lock status --task-id <TASK_ID>` to see if the lock is
   close to expiry.
3. Either wait and retry, or pick a different ready task with
   `python skills/exec_plan.py ready --plan <PLAN_ID>`.
4. Never overwrite a lock without `--force`.

---

### Step 2B — Check lock status

```bash
python task_lock.py status --task-id <TASK_ID>
```

**Unlocked:**

```
  🟢  'TASK-003' is NOT locked (free to acquire)
```

**Locked:**

```
  🔴  'TASK-003' is LOCKED
       agent_id   : agent-42
       acquired_at: 2026-03-13T10:00:00
       expires_at : 2026-03-13T10:05:00
       remaining  : 4m 47s
```

---

### Step 2C — Release a lock (after finishing or aborting work)

```bash
python task_lock.py release \
  --task-id  <TASK_ID>  \
  --agent-id <AGENT_ID>
```

The release call must use the **same `agent_id`** that acquired the lock.
Attempting to release with a different `agent_id` raises `LockNotOwnedError`
unless `--force` is passed.

After releasing, also mark the task done in the execution plan:

```bash
python skills/exec_plan.py done \
  --plan  <PLAN_ID>  \
  --task  <TASK_ID>  \
  --agent <AGENT_ID>
```

---

### Step 2D — Sweep expired locks (maintenance)

```bash
python task_lock.py sweep
```

Run this at agent startup or periodically in CI to clean up lock files left by
crashed agents.  Output lists every task ID whose lock was removed.

---

### Step 3 — Python API (programmatic use)

```python
from harness_skills.task_lock import (
    TaskLockProtocol,
    TaskLock,
    LockConflictError,
    LockNotOwnedError,
)

proto = TaskLockProtocol(
    locks_dir=Path(".claude/task-locks"),   # default
    default_timeout_seconds=300,            # 5 minutes; override per-call
)

# Acquire
lock = proto.acquire("TASK-003", agent_id="agent-42")
if lock is None:
    print("Locked by another agent — back off")
else:
    print(f"Lock held, expires in {lock.seconds_remaining():.0f}s")

# Strict mode (raises instead of returning None)
try:
    lock = proto.acquire("TASK-003", agent_id="agent-42", raise_on_conflict=True)
except LockConflictError as err:
    print(f"Conflict: {err.holder.agent_id} holds the lock")

# Extend mid-task (refresh TTL without releasing)
updated = proto.extend("TASK-003", agent_id="agent-42", additional_seconds=120)

# Inspect
lock = proto.get_lock("TASK-003")   # returns None if unlocked or expired
locked: bool = proto.is_locked("TASK-003")
all_locks: list[TaskLock] = proto.list_locks()

# Release
proto.release("TASK-003", agent_id="agent-42")

# Sweep
swept_ids: list[str] = proto.sweep_expired()
```

---

### Step 4 — Agent SDK integration (hook-based)

Use `agent_options_with_lock()` to attach acquire/release hooks to a Claude
Agent SDK session.  The lock is acquired automatically when the session starts
and released when it stops (including on errors or interruption).

```python
from claude_agent_sdk import ClaudeAgentOptions, claude_agent
from harness_skills.task_lock import TaskLockProtocol

proto = TaskLockProtocol(default_timeout_seconds=300)

options = proto.agent_options_with_lock(
    base_options=ClaudeAgentOptions(allowed_tools=["Read", "Edit", "Bash"]),
    task_id="TASK-003",
    agent_id="agent-42",
    timeout_seconds=300,  # optional; overrides default
)

# The session acquires the lock on SessionStart and releases on Stop.
async with claude_agent(options=options) as agent:
    await agent.run("Implement the auth middleware for TASK-003")
```

If another agent holds the lock when the session starts, `LockConflictError`
is raised before any tools are invoked, aborting the session safely.

You can also compose hooks manually:

```python
from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

acquire_hook = proto.as_acquire_hook("TASK-003", "agent-42", timeout_seconds=300)
release_hook = proto.as_release_hook("TASK-003", "agent-42")

options = ClaudeAgentOptions(
    allowed_tools=["Read", "Edit"],
    hooks={
        "SessionStart": [HookMatcher(matcher=".*", hooks=[acquire_hook])],
        "Stop":         [HookMatcher(matcher=".*", hooks=[release_hook])],
    },
)
```

---

### Step 5 — Coordinating with the execution plan

The task lock protocol and the execution plan (`skills/exec_plan.py`) are
complementary but independent:

| Layer | Manages |
|---|---|
| **Execution plan YAML** | Task graph, dependencies, `lock_status` field, completion state |
| **Task lock files** | Atomic file-based exclusion, TTL, crash recovery |

Best practice: use **both** together.

```python
from skills.exec_plan import ExecPlan
from harness_skills.task_lock import TaskLockProtocol

proto = TaskLockProtocol()
plan  = ExecPlan.load("PLAN-001")

for task in plan.ready_tasks():
    lock = proto.acquire(task["id"], agent_id=MY_AGENT_ID)
    if lock is None:
        continue          # another agent got there first
    plan.claim(task["id"], agent=MY_AGENT_ID)   # update YAML
    try:
        do_work(task)
        plan.mark_done(task["id"], agent=MY_AGENT_ID)
    finally:
        proto.release(task["id"], agent_id=MY_AGENT_ID)
```

---

## TTL and auto-expiry

| Scenario | Behaviour |
|---|---|
| Agent completes work | Call `release()` immediately |
| Agent crashes mid-task | Lock auto-expires after `timeout_seconds` |
| Long-running task | Call `extend()` before expiry to refresh the TTL |
| Another agent finds an expired lock | Expired lock is swept and replaced atomically |

Choose your TTL generously (e.g. 2× the expected task duration) so that a
slow-but-alive agent is not evicted.  Sweep expired locks at agent startup
with `proto.sweep_expired()` to clean up any previous crash debris.

---

## Options

### Global options

| Flag | Default | Effect |
|---|---|---|
| `--locks-dir PATH` | `.claude/task-locks` | Directory where `.lock` files are stored |
| `--timeout SECONDS` | `300` | Default TTL applied by `acquire` |

### `acquire`

| Flag | Required | Effect |
|---|---|---|
| `--task-id TASK_ID` | ✅ | Task identifier to lock |
| `--agent-id AGENT_ID` | ✅ | Agent identifier recorded in the lock |
| `--timeout SECONDS` | — | Per-call TTL override |

### `release`

| Flag | Required | Effect |
|---|---|---|
| `--task-id TASK_ID` | ✅ | Task whose lock to release |
| `--agent-id AGENT_ID` | ✅ | Must match lock holder unless `--force` |
| `--force` | — | Remove lock regardless of owner |

### `status`

| Flag | Required | Effect |
|---|---|---|
| `--task-id TASK_ID` | ✅ | Task to inspect |

---

## Error reference

| Exception | Meaning | Resolution |
|---|---|---|
| `LockConflictError` | Another agent holds an active lock | Back off; wait or pick a different task |
| `LockNotOwnedError` | `release`/`extend` caller ≠ lock holder | Use the correct `agent_id` or pass `--force` |

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Acquire lock before starting a task | **`/harness:task-lock`** ← you are here |
| See all plan statuses | `/harness:status` |
| Detect which agents conflict on files | `/coordinate` |
| Resume multi-agent work from handoff | `/harness:resume` |
| Check plan health and gate results | `/harness:evaluate` |

---

## Notes

- **File-based, no database** — lock files live in `.claude/task-locks/` and
  are visible to all agents sharing the filesystem.
- **Atomic creation** — uses `O_CREAT | O_EXCL` so two concurrent `acquire`
  calls on the same task can never both succeed.
- **Re-entrant** — the same `agent_id` can call `acquire` again to refresh the
  TTL without releasing first.
- **Crash-safe** — all expired lock files are cleaned up lazily on every
  `acquire`, `get_lock`, and `list_locks` call, and eagerly via `sweep`.
- **SDK-optional** — the protocol has no hard dependency on `claude-agent-sdk`;
  import it only when using `agent_options_with_lock()`.
