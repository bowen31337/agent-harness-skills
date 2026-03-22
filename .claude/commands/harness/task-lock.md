<<<<<<< HEAD
# Harness Task Lock

Acquire, inspect, extend, or release an **exclusive task lock** before an
agent begins work on a plan task.  The lock prevents two agents from
concurrently modifying the same task and auto-expires after a configurable
timeout so a crashed agent never permanently blocks progress.

---

## How task locks work

```
Agent A calls /harness:task-lock acquire TASK-001
   │
   ▼  creates .claude/task-locks/TASK-001.lock  (atomic O_CREAT|O_EXCL)
   │  POSTs lock to state service  PATCH /features/TASK-001
   │
   │  Agent B calls /harness:task-lock acquire TASK-001
   │      └─ sees non-expired lock → prints conflict, exits non-zero
   │
   ▼  Agent A finishes work
Agent A calls /harness:task-lock release TASK-001 --outcome done
   │
   ▼  removes .claude/task-locks/TASK-001.lock
      PATCHes state service  { "lock_action": "release", "outcome": "done" }

Agent B retries → acquires successfully
```

**Lock payload** (JSON stored in `.claude/task-locks/<task_id>.lock`):

```json
{
    "task_id":          "TASK-001",
    "agent_id":         "agent-42",
    "acquired_at":      "2026-03-22T09:00:00+00:00",
    "expires_at":       "2026-03-22T09:05:00+00:00",
    "timeout_seconds":  300.0
}
```

---

## Usage

```bash
# Acquire a lock before starting work (default timeout: 300 s)
/harness:task-lock acquire TASK-001

# Acquire with a custom timeout (seconds)
/harness:task-lock acquire TASK-001 --timeout 600

# Inspect the current lock on a task
/harness:task-lock status TASK-001

# List all active locks across the entire plan
/harness:task-lock list

# Extend an existing lock mid-task (add 120 s)
/harness:task-lock extend TASK-001 --add 120

# Release the lock when work is done
/harness:task-lock release TASK-001 --outcome done

# Release with a different outcome
/harness:task-lock release TASK-001 --outcome failed
/harness:task-lock release TASK-001 --outcome skipped
/harness:task-lock release TASK-001 --outcome handed-off

# Force-release a lock held by another agent (admin / clean-up only)
/harness:task-lock release TASK-001 --force

# Sweep all expired locks from the lock directory
/harness:task-lock sweep

# Output JSON instead of a formatted table (for CI / piping)
/harness:task-lock list --json
/harness:task-lock status TASK-001 --json
```

---

## Instructions

### Step 0 — Resolve agent identity

Every lock operation requires an `AGENT_ID`.  Resolve it in this order:

```python
import os

agent_id = (
    os.environ.get("AGENT_ID")
    or os.environ.get("CLAW_FORGE_AGENT_ID")
    or _git_branch_name()   # subprocess: git rev-parse --abbrev-ref HEAD
    or "unknown-agent"
)
```

```bash
# Shell equivalent
AGENT_ID="${AGENT_ID:-${CLAW_FORGE_AGENT_ID:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown-agent)}}"
echo "Agent ID: $AGENT_ID"
```

---

### Step 1 — Acquire the lock  (`acquire`)

Before touching **any** file related to a plan task, acquire its lock.

```python
from harness_skills.task_lock import AsyncTaskLockProtocol, StateServiceLockClient
import asyncio

STATE_URL = os.environ.get("STATE_SERVICE_URL", "http://localhost:8888")
TIMEOUT   = float(os.environ.get("TASK_LOCK_TIMEOUT", "300"))

proto = AsyncTaskLockProtocol(
    state_client=StateServiceLockClient(STATE_URL),
    default_timeout_seconds=TIMEOUT,
)

lock = asyncio.run(proto.async_acquire(TASK_ID, agent_id=AGENT_ID))

if lock is None:
    existing = proto.get_lock(TASK_ID)
    print(f"⛔  Task '{TASK_ID}' is locked by '{existing.agent_id}' "
          f"(expires in {existing.seconds_remaining():.0f}s).")
    print("    Back off and retry, or wait for the lock to expire.")
    sys.exit(1)

print(f"🔒  Lock acquired on '{TASK_ID}' "
      f"(expires in {lock.seconds_remaining():.0f}s, agent={AGENT_ID})")
```

**Conflict resolution rules:**

| Situation | Action |
|---|---|
| Lock held by a **different agent**, not expired | Print holder info, exit 1 — do NOT proceed |
| Lock held by the **same agent** (re-entrant) | TTL is refreshed, lock returned — safe to continue |
| Lock is **expired** (any agent) | Swept automatically, new lock acquired |
| Lock file **corrupt** or missing | Treated as no lock — acquire succeeds |

---

### Step 2 — Do the work

While holding the lock, complete the task.  If the task is long-running:

- **Extend** the lock periodically (before it expires) rather than letting it
  lapse and risking a sweep by another agent.
- A 50 % threshold is a good heuristic: extend when less than half the TTL
  remains.

```python
# Mid-task heartbeat — extend if less than 150 s remain on a 300 s lock
remaining = proto.get_lock(TASK_ID).seconds_remaining()
if remaining < (TIMEOUT * 0.5):
    extended = asyncio.run(proto.async_extend(TASK_ID, agent_id=AGENT_ID,
                                               additional_seconds=TIMEOUT))
    if extended:
        print(f"⏱  Lock on '{TASK_ID}' extended "
              f"(now expires in {extended.seconds_remaining():.0f}s)")
```

---

### Step 3 — Release the lock  (`release`)

**Always release the lock** — even on failure.  Use a try/finally block.

```python
try:
    # ... do work ...
    outcome = "done"
except Exception as exc:
    print(f"❌  Task failed: {exc}")
    outcome = "failed"
finally:
    released = asyncio.run(
        proto.async_release(TASK_ID, agent_id=AGENT_ID, outcome=outcome)
    )
    if released:
        print(f"🔓  Lock released on '{TASK_ID}' (outcome={outcome})")
```

When `outcome="done"` the release call also sends `status=done` to the state
service so the task is marked complete without a separate PATCH.

---

### Step 4 — Inspect lock state  (`status` / `list`)

```python
# Single task
lock = proto.get_lock(TASK_ID)
if lock:
    print(f"🔒  {lock.task_id}  held by {lock.agent_id}  "
          f"(expires in {lock.seconds_remaining():.0f}s)")
else:
    print(f"🔓  {TASK_ID} — no active lock")

# All tasks
for lock in proto.list_locks():
    icon = "⚠️" if lock.seconds_remaining() < 60 else "🔒"
    print(f"  {icon}  {lock.task_id:<20}  {lock.agent_id:<20}  "
          f"{lock.seconds_remaining():.0f}s remaining")
```

---

### Step 5 — Sweep expired locks  (`sweep`)

Run this during housekeeping or at plan startup to clean stale lock files left
by crashed agents:

```python
swept = proto.sweep_expired()
if swept:
    print(f"🧹  Swept {len(swept)} expired lock(s): {', '.join(swept)}")
else:
    print("✅  No expired locks to sweep.")
```

---

### Step 6 — Formatted output

**Table format (default):**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Task Lock State  ·  Snapshot: 2026-03-22 09:00:00  ·  Locks: 2
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Task ID          Agent              Acquired             Expires In
  ──────────────────────────────────────────────────────────────────
  🔒 TASK-001      agent-42           09:00:00             4m 52s
  🔒 TASK-003      agent-17           08:58:12             2m 34s
  🔓 TASK-002      —                  —                    —

  Active: 2  ·  Unlocked: 1  ·  Timeout default: 300 s
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**JSON format (`--json`):**

```json
{
  "snapshot_time": "2026-03-22T09:00:00+00:00",
  "total_active": 2,
  "locks": [
    {
      "task_id": "TASK-001",
      "agent_id": "agent-42",
      "acquired_at": "2026-03-22T09:00:00+00:00",
      "expires_at":  "2026-03-22T09:05:00+00:00",
      "timeout_seconds": 300.0
    }
  ]
}
```

---

### Step 7 — Agent SDK hook integration

For fully automatic lock lifecycle management, attach the lock hooks to a
``ClaudeAgentOptions`` instance.  The lock is **acquired on SessionStart** and
**released on Stop** without any manual try/finally blocks:

```python
from claude_agent_sdk import ClaudeAgentOptions
from harness_skills.task_lock import AsyncTaskLockProtocol, StateServiceLockClient

proto = AsyncTaskLockProtocol(
    state_client=StateServiceLockClient("http://localhost:8888"),
    default_timeout_seconds=300,
)

options = ClaudeAgentOptions(
    allowed_tools=["Read", "Edit", "Bash"],
    hooks={
        "SessionStart": [
            HookMatcher(
                matcher=".*",
                hooks=[proto.as_async_acquire_hook(TASK_ID, AGENT_ID)],
            )
        ],
        "Stop": [
            HookMatcher(
                matcher=".*",
                hooks=[proto.as_async_release_hook(TASK_ID, AGENT_ID, outcome="done")],
            )
        ],
    },
)
```

If the task is already locked when ``SessionStart`` fires, a
``LockConflictError`` is raised — the SDK aborts the session cleanly before
the agent reads a single file.

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `STATE_SERVICE_URL` | `http://localhost:8888` | claw-forge state service base URL |
| `TASK_LOCK_TIMEOUT` | `300` | Default lock TTL in seconds |
| `TASK_LOCK_DIR` | `.claude/task-locks` | Directory for `.lock` files |
| `AGENT_ID` | *(git branch)* | Overrides auto-detected agent identity |
| `CLAW_FORGE_AGENT_ID` | *(git branch)* | Alternative agent identity env var |

Timeouts are configurable per-acquire call via `--timeout <seconds>` or the
`timeout_seconds` parameter in Python.  Maximum recommended TTL: **3600 s
(1 hour)**.  Beyond that, set a dependency in `claw-forge.yaml` instead of
holding a long lock.

---

## Options

| Flag | Default | Effect |
|---|---|---|
| `--timeout SECONDS` | `300` | Lock TTL for `acquire` |
| `--add SECONDS` | *(required)* | Additional seconds for `extend` |
| `--outcome VALUE` | `done` | Outcome tag for `release` (`done\|failed\|skipped\|handed-off`) |
| `--force` | off | Force-release even if lock is held by a different agent |
| `--json` | off | Emit JSON instead of formatted table |
| `--locks-dir PATH` | `.claude/task-locks` | Custom lock directory |
| `--state-url URL` | `http://localhost:8888` | Custom state service URL |
| `--no-state-sync` | off | Skip state service notification (file lock only) |

---

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Operation succeeded |
| `1` | Lock conflict — task held by another agent |
| `2` | Lock not owned — release/extend attempted by wrong agent |
| `3` | State service unreachable (file lock still operated; best-effort) |
| `4` | Invalid arguments |

---

## Python API quick-reference

```python
from harness_skills.task_lock import (
    TaskLock,               # Pydantic lock record
    TaskLockProtocol,       # synchronous file-based locking
    AsyncTaskLockProtocol,  # file lock + async state service sync
    StateServiceLockClient, # async HTTP client for the state service
    LockConflictError,      # raised on conflict (raise_on_conflict=True)
    LockNotOwnedError,      # raised on release/extend by wrong agent
)
from harness_skills.models.lock import (
    LockAcquireRequest,     # wire models for the state service REST API
    LockExtendRequest,
    LockReleaseRequest,
    LockRecord,
    LockStateResponse,
    LockOperationResponse,
    LockListResponse,
)
```

---

## When to use this skill

| Scenario | Action |
|---|---|
| Starting work on any plan task | **`/harness:task-lock acquire`** ← start here |
| Task is taking longer than expected | `/harness:task-lock extend` |
| Work is complete | `/harness:task-lock release --outcome done` |
| Plan startup / agent bootstrap | `/harness:task-lock sweep` (clean stale locks) |
| Debugging / coordination review | `/harness:task-lock list` |
| Reviewing a specific task's lock | `/harness:task-lock status TASK-ID` |
| Conflict detected by `/coordinate` | Pause lower-priority agent; let higher-priority agent merge first |

---

## Notes

- **File-based locking uses `O_CREAT | O_EXCL`** — the kernel guarantees
  atomicity on POSIX filesystems.  On network file systems (NFS, CIFS) the
  same guarantee does not hold; use the state service as the authoritative
  source in those environments.
- **State service sync is best-effort** — if the service is down, file-based
  locks still work correctly.  Pass `--no-state-sync` to suppress the warning
  when operating offline intentionally.
- **Auto-expiry prevents deadlocks** — if an agent crashes while holding a
  lock, the lock file will be swept on the next `acquire` or `sweep` call
  once `expires_at` passes.  No manual intervention is needed.
- **Re-entrant acquire is safe** — calling `acquire` for a task you already
  own simply refreshes the TTL.  This is useful when an agent spawns a
  sub-agent for the same task.
- **Coordinate integration** — `coordinate.py` reads `.claude/task-locks/`
  and the state service `/features/locks` endpoint automatically; no extra
  configuration is needed for lock state to appear in the conflict dashboard.
||||||| 0e893bd
=======
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
>>>>>>> feat/execution-plans-skill-generates-a-task-lock-protocol-wh
