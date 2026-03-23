# Concurrency Patterns

Detect the async and concurrency conventions already in use, then generate idiomatic
boilerplate that fits those conventions — async hooks for the Claude Agent SDK, task
groups, thread-safe locks, pool patterns, and more.

Produces ready-to-paste code snippets **and** writes enforceable concurrency principles
into `.claude/principles.yaml` so that `check-code` and `review-pr` catch violations
automatically.

---

## Instructions

### Step 0: Detect language and runtime

```bash
# Is this a Python project?
find . -name "*.py" -not -path "./.venv/*" -not -path "*/node_modules/*" | head -5

# Is this a JS/TS project?
find . \( -name "*.ts" -o -name "*.js" \) \
  -not -path "*/node_modules/*" -not -path "*/dist/*" | head -5
```

Set `LANG` to `python`, `js`, or `both`.

---

### Step 1: Detect the async framework

#### Python

```bash
# asyncio usage
grep -rn "import asyncio\|from asyncio\|asyncio\.run\|asyncio\.gather\|asyncio\.create_task\|asyncio\.sleep" \
  --include="*.py" -l . 2>/dev/null | grep -v ".venv" | grep -v ".git"

# anyio usage
grep -rn "import anyio\|from anyio\|anyio\.run\|anyio\.sleep\|create_task_group\|anyio\.to_thread" \
  --include="*.py" -l . 2>/dev/null | grep -v ".venv" | grep -v ".git"

# trio usage
grep -rn "import trio\|from trio\|trio\.run\|trio\.sleep\|trio\.open_nursery" \
  --include="*.py" -l . 2>/dev/null | grep -v ".venv" | grep -v ".git"

# async def functions (any framework)
grep -rn "^async def\|    async def" --include="*.py" \
  -l . 2>/dev/null | grep -v ".venv" | grep -v ".git" | head -20

# await expressions
grep -rn "\bawait\b" --include="*.py" \
  -l . 2>/dev/null | grep -v ".venv" | grep -v ".git" | head -20
```

Record:
- **async_framework**: `asyncio` / `anyio` / `trio` / `none`
- Number of files with `async def`
- Number of files with `await`

#### JavaScript / TypeScript

```bash
# async/await
grep -rn "async function\|async (\|async (" \
  --include="*.ts" --include="*.js" \
  -l . 2>/dev/null | grep -v node_modules | head -10

# Promise chains
grep -rn "\.then(\|\.catch(\|Promise\.all\|Promise\.allSettled\|Promise\.race" \
  --include="*.ts" --include="*.js" \
  -l . 2>/dev/null | grep -v node_modules | head -10

# Worker threads
grep -rn "Worker\b\|worker_threads\|new Worker" \
  --include="*.ts" --include="*.js" \
  -l . 2>/dev/null | grep -v node_modules | head -10
```

Record:
- **js_async_style**: `async-await` / `promises` / `callbacks` / `mixed`

---

### Step 2: Detect the Claude Agent SDK hook pattern

```bash
# Hook functions attached to SDK sessions
grep -rn "SessionStart\|SessionStop\|PreToolUse\|PostToolUse\|PostToolUseFailure" \
  --include="*.py" -l . 2>/dev/null | grep -v ".venv" | grep -v ".git"

# Hook registration pattern
grep -rn "hooks()\|ClaudeAgentOptions\|agent_options_with" \
  --include="*.py" . 2>/dev/null | grep -v ".venv" | grep -v ".git" | head -10

# async for query pattern (streaming)
grep -rn "async for.*query\|async for.*stream" \
  --include="*.py" . 2>/dev/null | grep -v ".venv" | grep -v ".git" | head -10
```

Record:
- **sdk_hooks_present**: true / false
- **sdk_streaming**: true / false (async-generator `async for` pattern)
- Key files that define hooks

---

### Step 3: Detect thread-safety and lock patterns

```bash
# threading module
grep -rn "import threading\|from threading\|threading\.Lock\|threading\.RLock\|threading\.Event\|threading\.Semaphore" \
  --include="*.py" -l . 2>/dev/null | grep -v ".venv" | grep -v ".git"

# asyncio synchronisation primitives
grep -rn "asyncio\.Lock\|asyncio\.Event\|asyncio\.Semaphore\|asyncio\.Condition\|asyncio\.BoundedSemaphore" \
  --include="*.py" -l . 2>/dev/null | grep -v ".venv" | grep -v ".git"

# anyio synchronisation primitives
grep -rn "anyio\.Lock\|anyio\.Event\|anyio\.Semaphore\|anyio\.CapacityLimiter" \
  --include="*.py" -l . 2>/dev/null | grep -v ".venv" | grep -v ".git"

# File-based / POSIX atomic locking
grep -rn "O_CREAT.*O_EXCL\|os\.open.*O_EXCL\|fcntl\.flock\|fcntl\.lockf\|\.lock\b" \
  --include="*.py" -l . 2>/dev/null | grep -v ".venv" | grep -v ".git"

# contextlib lock usage
grep -rn "async with.*lock\|async with.*Lock\|with.*lock\|with.*Lock" \
  --include="*.py" -l . 2>/dev/null | grep -v ".venv" | grep -v ".git" | head -10
```

Record:
- **lock_type**: `threading` / `asyncio` / `anyio` / `posix-file` / `none`

---

### Step 4: Detect thread and process pool patterns

```bash
# concurrent.futures
grep -rn "ThreadPoolExecutor\|ProcessPoolExecutor\|concurrent\.futures\|loop\.run_in_executor\|anyio\.to_thread\|asyncio\.to_thread" \
  --include="*.py" -l . 2>/dev/null | grep -v ".venv" | grep -v ".git"

# multiprocessing
grep -rn "import multiprocessing\|from multiprocessing\|Pool(\|Process(" \
  --include="*.py" -l . 2>/dev/null | grep -v ".venv" | grep -v ".git"

# JS worker threads / worker pools
grep -rn "new Worker\|workerData\|parentPort\|piscina\|node:worker_threads" \
  --include="*.ts" --include="*.js" -l . 2>/dev/null | grep -v node_modules
```

Record:
- **pool_type**: `thread-pool` / `process-pool` / `run-in-executor` / `none`

---

### Step 5: Score the concurrency profile

Compute a profile label from the signals above:

| Profile | Criteria |
|---|---|
| **sdk-async-hooks** | `sdk_hooks_present = true` AND async framework detected |
| **anyio-first** | `anyio` imports present (regardless of SDK hooks) |
| **asyncio-native** | `asyncio` imports present, no `anyio` |
| **thread-safe-sync** | `threading.Lock` / POSIX file locks present, no async |
| **mixed** | Both thread and async primitives detected |
| **promise-based** (JS) | `async-await` or Promise chains |
| **unknown** | No concurrency signals found |

A project can match **multiple** profiles (e.g. `sdk-async-hooks` + `posix-file`).

Print a confidence table:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Concurrency Profile Detection
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Profile              Detected   Evidence
  ──────────────────────────────────────────────────────
  sdk-async-hooks      🟢 Yes     performance_hooks.py, task_lock.py, handoff.py
  anyio-first          🟢 Yes     anyio in pyproject.toml, create_task_group usage
  asyncio-native       🟠 Mixed   asyncio.Lock in tests; anyio preferred in prod
  posix-file-lock      🟢 Yes     task_lock.py (O_CREAT | O_EXCL)
  thread-safe-sync     ⬜ No      No threading.Lock found in production code
  process-pool         ⬜ No      No multiprocessing / ProcessPoolExecutor found

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### Step 6: Generate pattern snippets

For **each active profile**, emit ready-to-paste code snippets matching the detected
conventions.  Only generate snippets for profiles that were detected; skip the rest.

---

#### Pattern A — Claude Agent SDK async hooks  *(if sdk-async-hooks)*

Emit a minimal, copy-paste–ready hook class that follows the same structure as the
existing hooks in the project:

```python
# hooks/<your_feature>_hooks.py
"""
<YourFeature> hooks — async callbacks for a claude_agent_sdk session.

Attach via:
    options = ClaudeAgentOptions(hooks=YourFeatureHooks().hooks())
"""
from __future__ import annotations

from typing import Any

from claude_agent_sdk import ClaudeAgentOptions


class YourFeatureHooks:
    """Async hook callbacks for <your feature>."""

    # ------------------------------------------------------------------ #
    #  Hook factory                                                        #
    # ------------------------------------------------------------------ #

    def hooks(self) -> dict[str, Any]:
        """Return a hooks dict compatible with ClaudeAgentOptions."""
        return {
            "on_session_start": self._on_session_start,
            "on_pre_tool_use":  self._on_pre_tool_use,
            "on_post_tool_use": self._on_post_tool_use,
            "on_post_tool_use_failure": self._on_post_tool_use_failure,
            "on_session_end":   self._on_session_end,
        }

    def agent_options(
        self,
        base_options: ClaudeAgentOptions | None = None,
    ) -> ClaudeAgentOptions:
        """Merge hooks into existing options (non-destructive)."""
        base = base_options or ClaudeAgentOptions()
        existing = base.hooks or {}
        return ClaudeAgentOptions(
            **{k: v for k, v in vars(base).items() if k != "hooks"},
            hooks={**existing, **self.hooks()},
        )

    # ------------------------------------------------------------------ #
    #  Hook implementations                                                #
    # ------------------------------------------------------------------ #

    async def _on_session_start(self, event: Any) -> None:
        """Called once when the agent session initialises."""
        # TODO: initialise your state here

    async def _on_pre_tool_use(self, event: Any) -> None:
        """Called before every tool invocation."""
        # TODO: record tool name / timestamp if needed

    async def _on_post_tool_use(self, event: Any) -> None:
        """Called after a tool invocation succeeds."""
        # TODO: record success metrics

    async def _on_post_tool_use_failure(self, event: Any) -> None:
        """Called after a tool invocation fails."""
        # TODO: log or re-raise the error

    async def _on_session_end(self, event: Any) -> None:
        """Called once when the session is about to exit."""
        # TODO: flush buffers, release resources
```

**Usage with streaming query:**

```python
from claude_agent_sdk import query

tracker = YourFeatureHooks()

async for msg in query(
    prompt="...",
    options=tracker.agent_options(),
):
    ...  # process streaming messages
```

---

#### Pattern B — anyio task group  *(if anyio-first)*

```python
import anyio


async def run_concurrent_tasks() -> None:
    """Fan-out multiple coroutines and wait for all to finish."""
    async with anyio.create_task_group() as tg:
        tg.start_soon(task_one, arg1)
        tg.start_soon(task_two, arg2)
        tg.start_soon(task_three)
    # All tasks have completed (or the first exception cancelled the group)


async def task_one(arg: str) -> None:
    await anyio.sleep(0)   # yield control; replace with real async work
    ...
```

**Move blocking I/O off the event loop:**

```python
import anyio

async def process_file(path: str) -> str:
    """Run blocking file I/O in a worker thread without blocking the loop."""
    return await anyio.to_thread.run_sync(_read_file_sync, path)

def _read_file_sync(path: str) -> str:
    with open(path) as f:
        return f.read()
```

---

#### Pattern C — asyncio task group / gather  *(if asyncio-native and not anyio-first)*

```python
import asyncio


async def run_concurrent() -> list[str]:
    """Run tasks concurrently and collect results in order."""
    results = await asyncio.gather(
        fetch_data("https://api.example.com/a"),
        fetch_data("https://api.example.com/b"),
        return_exceptions=True,   # prevents one failure from cancelling others
    )
    return [r for r in results if not isinstance(r, BaseException)]


async def run_with_task_group() -> None:
    """Python 3.11+ task-group style (structured concurrency)."""
    async with asyncio.TaskGroup() as tg:
        task_a = tg.create_task(fetch_data("https://api.example.com/a"))
        task_b = tg.create_task(fetch_data("https://api.example.com/b"))
    # Both tasks done; task_a.result() / task_b.result() now available
```

---

#### Pattern D — async lock  *(if asyncio-native or anyio-first)*

Pick the lock primitive that matches the detected framework:

```python
# ── anyio (preferred in anyio-first projects) ─────────────────────────
import anyio

_lock = anyio.Lock()   # Create once, reuse across coroutines

async def safe_update(shared_dict: dict, key: str, value: str) -> None:
    async with _lock:
        shared_dict[key] = value   # only one coroutine at a time


# ── asyncio ───────────────────────────────────────────────────────────
import asyncio

_lock = asyncio.Lock()

async def safe_update_asyncio(shared_dict: dict, key: str, value: str) -> None:
    async with _lock:
        shared_dict[key] = value
```

---

#### Pattern E — POSIX atomic file lock  *(if posix-file-lock)*

```python
"""
Atomic file-lock helper — zero external dependencies.
Uses O_CREAT | O_EXCL for process-safe mutual exclusion.
"""
from __future__ import annotations

import errno
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path


class FileLock:
    """Single-file advisory lock backed by the filesystem."""

    def __init__(self, lock_dir: Path, name: str, ttl_seconds: float = 300) -> None:
        lock_dir.mkdir(parents=True, exist_ok=True)
        self._path = lock_dir / f"{name}.lock"
        self._ttl = ttl_seconds

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def acquire(self, owner: str) -> bool:
        """Return True if lock acquired; False if held by another owner."""
        self._sweep_expired()
        payload = json.dumps({
            "owner":      owner,
            "acquired_at": datetime.now(timezone.utc).isoformat(),
            "expires_at":  (
                datetime.now(timezone.utc) + timedelta(seconds=self._ttl)
            ).isoformat(),
        }).encode()
        try:
            fd = os.open(str(self._path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(fd, payload)
            os.close(fd)
            return True
        except OSError as exc:
            if exc.errno == errno.EEXIST:
                return False
            raise

    def release(self, owner: str) -> bool:
        """Remove the lock file if it is owned by *owner*."""
        try:
            data = json.loads(self._path.read_text())
        except FileNotFoundError:
            return False
        if data.get("owner") != owner:
            return False
        self._path.unlink(missing_ok=True)
        return True

    def is_locked(self) -> bool:
        self._sweep_expired()
        return self._path.exists()

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _sweep_expired(self) -> None:
        """Auto-remove the lock file if its TTL has elapsed."""
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text())
            expires = datetime.fromisoformat(data["expires_at"])
            if datetime.now(timezone.utc) >= expires:
                self._path.unlink(missing_ok=True)
        except (json.JSONDecodeError, KeyError, FileNotFoundError):
            self._path.unlink(missing_ok=True)
```

---

#### Pattern F — thread-pool off-ramp  *(if pool_type includes run-in-executor or anyio)*

```python
# ── anyio (preferred) ─────────────────────────────────────────────────
import anyio
from concurrent.futures import ThreadPoolExecutor

_pool = ThreadPoolExecutor(max_workers=4)

async def run_blocking(fn, *args):
    """Dispatch a sync-blocking call to the shared thread pool."""
    return await anyio.to_thread.run_sync(fn, *args, limiter=anyio.CapacityLimiter(4))


# ── asyncio ───────────────────────────────────────────────────────────
import asyncio
from concurrent.futures import ThreadPoolExecutor

_pool = ThreadPoolExecutor(max_workers=4)

async def run_blocking_asyncio(fn, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_pool, fn, *args)
```

---

#### Pattern G — async streaming generator  *(if sdk_streaming)*

```python
from __future__ import annotations
from collections.abc import AsyncGenerator
from typing import Any


async def streamed_process(
    items: list[str],
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Yield results as they complete rather than buffering everything.
    Callers use:  async for result in streamed_process(items): ...
    """
    for item in items:
        result = await _process_one(item)   # replace with real async I/O
        yield {"item": item, "result": result}


async def _process_one(item: str) -> str:
    # placeholder — do real async work here
    return item.upper()
```

---

### Step 7: Write concurrency principles

Load `.claude/principles.yaml` (create if missing).  Upsert the principles below using
IDs in the range `CP001`–`CP099` so they never collide with hand-written principles.

Only write a principle for a pattern that was **detected** in Step 1–4.

```yaml
# Generated by /concurrency-patterns — do not edit IDs manually

# ── Always write these two ──────────────────────────────────────────
- id: "CP001"
  category: "concurrency"
  severity: "blocking"
  applies_to: ["review-pr", "check-code"]
  rule: >
    Never mix asyncio and threading locks on the same shared state.
    Use asyncio.Lock / anyio.Lock for coroutine-shared state and
    threading.Lock only for purely synchronous, multi-threaded paths.

- id: "CP002"
  category: "concurrency"
  severity: "blocking"
  applies_to: ["review-pr", "check-code"]
  rule: >
    Never call blocking I/O (file reads, network requests, subprocess)
    directly inside an async function.  Offload with anyio.to_thread.run_sync
    or asyncio.to_thread.run_in_executor instead.

# ── SDK-hooks project ───────────────────────────────────────────────
- id: "CP003"       # only if sdk_hooks_present = true
  category: "concurrency"
  severity: "blocking"
  applies_to: ["review-pr", "check-code"]
  rule: >
    Claude Agent SDK hook callbacks (on_session_start, on_pre_tool_use, etc.)
    MUST be declared as `async def`.  A synchronous hook silently swallows
    coroutines and will never be awaited.

# ── anyio-first project ─────────────────────────────────────────────
- id: "CP004"       # only if anyio detected
  category: "concurrency"
  severity: "suggestion"
  applies_to: ["review-pr", "check-code"]
  rule: >
    Prefer anyio primitives (anyio.create_task_group, anyio.Lock,
    anyio.to_thread.run_sync) over bare asyncio equivalents so that
    the codebase remains backend-agnostic (works with asyncio and trio).

# ── POSIX file-lock project ─────────────────────────────────────────
- id: "CP005"       # only if posix-file-lock detected
  category: "concurrency"
  severity: "blocking"
  applies_to: ["review-pr", "check-code"]
  rule: >
    File-based locks MUST be created with O_CREAT | O_EXCL for atomicity.
    Never check-then-create in two steps — that introduces a TOCTOU race.
    Always include an expiry timestamp in the lock payload and sweep expired
    locks before attempting acquisition.

# ── Thread-pool project ─────────────────────────────────────────────
- id: "CP006"       # only if pool_type detected
  category: "concurrency"
  severity: "suggestion"
  applies_to: ["review-pr", "check-code"]
  rule: >
    Thread-pool executors must be created once at module level (or as a
    shared instance) and reused — never create a new ThreadPoolExecutor
    inside a loop or per-request function.
```

After writing, re-run the same `docs/PRINCIPLES.md` regeneration logic as `/define-principles`
Step 4.5 so the table stays up to date.

---

### Step 8: Summary report

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅ Concurrency Patterns — Done
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Detected profiles:
    🟢 sdk-async-hooks    (anyio + claude_agent_sdk hooks)
    🟢 anyio-first        (create_task_group, to_thread.run_sync)
    🟢 posix-file-lock    (O_CREAT | O_EXCL atomic lock files)
    ⬜ thread-pool        (not detected)

  Snippets generated:
    A — Claude Agent SDK async hook class
    B — anyio task group + blocking I/O off-ramp
    D — anyio.Lock for shared state
    E — POSIX atomic file lock helper
    G — async streaming generator

  Principles written → .claude/principles.yaml:
    CP001  Never mix asyncio and threading locks on shared state
    CP002  Never call blocking I/O directly inside async functions
    CP003  SDK hook callbacks must be async def
    CP004  Prefer anyio primitives over bare asyncio (anyio-first)
    CP005  File locks must use O_CREAT | O_EXCL (POSIX atomicity)

  Enforcement active in:
    • /check-code  — scans staged files against CP* principles
    • /review-pr   — flags concurrency violations in PR diffs

  Re-run any time:   /concurrency-patterns
  Detect only:       /concurrency-patterns --detect-only
  Skip principles:   /concurrency-patterns --no-principles
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Flags

| Flag | Behaviour |
|---|---|
| `--detect-only` | Run Steps 0–5 only; print the profile table, generate no snippets or principles |
| `--no-principles` | Skip Step 7; do not write to `.claude/principles.yaml` |
| `--pattern <A\|B\|C\|D\|E\|F\|G>` | Generate only the named pattern(s), comma-separated |
| `--framework <asyncio\|anyio\|trio\|threading>` | Override auto-detected framework |
| `--dry-run` | Print everything; write nothing |
| `--json` | Emit the detection results as JSON instead of a human-readable table |

---

## Notes

- This skill is **safe to re-run**: detection is read-only and principle IDs `CP*` are
  upserted, never duplicated.
- It does **not** commit any generated snippets.  Paste what you need, then stage and
  commit with `/checkpoint` or manually.
- For **monorepos** with mixed sync/async services, run from the specific service
  subdirectory to get accurate per-service results.
- The generated snippets are starting points, not final code.  Always review before
  merging — especially the hook implementations and shared-state access patterns.
- Related skills:
  - `/detect-api-style` — API style detection (REST/GraphQL/gRPC)
  - `/module-boundaries` — enforce package-level encapsulation
  - `/check-code` — run linters, type-checkers, and principle checks
  - `/review-pr` — include CP* principles in PR review checklist
