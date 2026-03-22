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
