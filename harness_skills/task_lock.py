"""
Task Lock Protocol for Claude Agent SDK sessions.

Before an agent starts work on a plan task it acquires an exclusive lock.
While the lock is held, any other agent that attempts to acquire the same
task receives ``None`` (or a ``LockConflictError``) and must back off.
Locks auto-expire after a configurable timeout so a crashed agent never
leaves a task permanently blocked.

Architecture
------------

  Orchestrator / Agent A
         │
         ▼  TaskLockProtocol.acquire("task-id", agent_id="agent-A")
  ┌──────────────────────────────────────────────────┐
  │  writes .claude/task-locks/<task_id>.lock        │
  │  (atomic O_CREAT | O_EXCL, JSON payload)         │
  └──────────┬───────────────────────────────────────┘
             │  lock is held by agent-A
             ▼
  Agent B tries TaskLockProtocol.acquire("task-id", agent_id="agent-B")
  ┌──────────────────────────────────────────────────┐
  │  sees non-expired lock file → returns None       │
  │  (or raises LockConflictError)                   │
  └──────────────────────────────────────────────────┘
             │  agent-A finishes
             ▼  TaskLockProtocol.release("task-id", agent_id="agent-A")
  ┌──────────────────────────────────────────────────┐
  │  removes lock file                               │
  └──────────────────────────────────────────────────┘
             │
             ▼  Agent B retries → acquires successfully

Each lock file is a JSON document stored at:
    .claude/task-locks/<sanitised_task_id>.lock

Lock payload
------------
    {
        "task_id":          "feature/auth-refactor",
        "agent_id":         "agent-42",
        "acquired_at":      "2026-03-13T10:00:00+00:00",
        "expires_at":       "2026-03-13T10:05:00+00:00",
        "timeout_seconds":  300.0
    }

Usage
-----
Acquire before work:
    proto = TaskLockProtocol(default_timeout_seconds=300)
    lock = proto.acquire("feature/auth-refactor", agent_id="agent-42")
    if lock is None:
        print("Task locked by another agent — backing off")

Release when done:
    proto.release("feature/auth-refactor", agent_id="agent-42")

Extend mid-task:
    proto.extend("feature/auth-refactor", agent_id="agent-42",
                  additional_seconds=120)

Agent SDK integration (hooks):
    options = proto.agent_options_with_lock(
        base_options=ClaudeAgentOptions(allowed_tools=["Read", "Edit"]),
        task_id="feature/auth-refactor",
        agent_id="agent-42",
    )
    # Acquires on SessionStart, releases on Stop.
"""

from __future__ import annotations

import errno
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Optional async state-service integration
# ---------------------------------------------------------------------------
# Import httpx lazily so the file-based lock protocol works even when httpx
# is not installed.  Call sites that need the state service will get an
# ImportError at runtime if the dependency is absent.
try:
    import httpx as _httpx
    _HTTPX_AVAILABLE = True
except ImportError:  # pragma: no cover
    _HTTPX_AVAILABLE = False

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

_DEFAULT_LOCKS_DIR = Path(".claude/task-locks")


class TaskLock(BaseModel):
    """Represents a single held task lock."""

    task_id: str = Field(description="Unique identifier for the plan task being locked.")
    agent_id: str = Field(description="Identifier of the agent that holds the lock.")
    acquired_at: str = Field(description="ISO-8601 UTC timestamp when the lock was acquired.")
    expires_at: str = Field(description="ISO-8601 UTC timestamp when the lock auto-expires.")
    timeout_seconds: float = Field(description="Lock TTL in seconds.", gt=0)

    # ------------------------------------------------------------------
    # Computed helpers
    # ------------------------------------------------------------------

    @property
    def acquired_at_dt(self) -> datetime:
        return datetime.fromisoformat(self.acquired_at)

    @property
    def expires_at_dt(self) -> datetime:
        return datetime.fromisoformat(self.expires_at)

    def is_expired(self) -> bool:
        """Return True if this lock's TTL has elapsed."""
        return datetime.now(timezone.utc) >= self.expires_at_dt

    def seconds_remaining(self) -> float:
        """Seconds until expiry. Negative when the lock has already expired."""
        return (self.expires_at_dt - datetime.now(timezone.utc)).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, text: str) -> "TaskLock":
        return cls(**json.loads(text))

    def __repr__(self) -> str:
        remaining = self.seconds_remaining()
        state = f"expires in {remaining:.0f}s" if remaining > 0 else "EXPIRED"
        return (
            f"TaskLock(task_id={self.task_id!r}, agent_id={self.agent_id!r}, {state})"
        )


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class LockConflictError(Exception):
    """Raised by ``acquire(..., raise_on_conflict=True)`` when a task is locked."""

    def __init__(self, task_id: str, holder: TaskLock) -> None:
        self.task_id = task_id
        self.holder = holder
        super().__init__(
            f"Task '{task_id}' is locked by agent '{holder.agent_id}' "
            f"(expires in {holder.seconds_remaining():.0f}s)"
        )


class LockNotOwnedError(Exception):
    """Raised when release/extend is attempted by an agent that does not hold the lock."""

    def __init__(self, task_id: str, requesting_agent: str, actual_agent: str) -> None:
        self.task_id = task_id
        self.requesting_agent = requesting_agent
        self.actual_agent = actual_agent
        super().__init__(
            f"Agent '{requesting_agent}' cannot modify lock on '{task_id}' "
            f"— it is held by '{actual_agent}'"
        )


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class TaskLockProtocol:
    """
    File-based task lock protocol for multi-agent plan execution.

    Parameters
    ----------
    locks_dir:
        Directory where ``.lock`` files are stored.
        Default: ``.claude/task-locks/``
    default_timeout_seconds:
        Default TTL applied when ``timeout_seconds`` is not given to
        ``acquire()``.  Default: 300 s (5 minutes).
    """

    def __init__(
        self,
        locks_dir: Path = _DEFAULT_LOCKS_DIR,
        default_timeout_seconds: float = 300.0,
    ) -> None:
        self.locks_dir = Path(locks_dir)
        self.default_timeout_seconds = default_timeout_seconds

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _lock_path(self, task_id: str) -> Path:
        """Return the filesystem path for *task_id*'s lock file."""
        # Sanitise so the task_id is safe as a filename component
        safe = (
            task_id
            .replace("/", "_")
            .replace("\\", "_")
            .replace("..", "__")
            .replace(" ", "-")
        )
        return self.locks_dir / f"{safe}.lock"

    def _ensure_dir(self) -> None:
        self.locks_dir.mkdir(parents=True, exist_ok=True)

    def _read_lock(self, path: Path) -> TaskLock | None:
        """Read and deserialise a lock file. Returns None if missing or corrupt."""
        try:
            return TaskLock.from_json(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError, ValueError, KeyError):
            return None

    def _create_lock_atomic(self, path: Path, lock: TaskLock) -> bool:
        """
        Create a new lock file atomically using ``O_CREAT | O_EXCL``.

        Returns True if the file was created, False if it already existed
        (i.e. another process beat us to it).
        """
        self._ensure_dir()
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except OSError as exc:
            if exc.errno == errno.EEXIST:
                return False
            raise
        with os.fdopen(fd, "w") as f:
            f.write(lock.to_json())
        return True

    def _overwrite_lock(self, path: Path, lock: TaskLock) -> None:
        """Atomically replace an existing lock file (POSIX rename)."""
        self._ensure_dir()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(lock.to_json())
        tmp.replace(path)

    def _make_lock(
        self, task_id: str, agent_id: str, timeout_seconds: float
    ) -> TaskLock:
        now = datetime.now(timezone.utc)
        return TaskLock(
            task_id=task_id,
            agent_id=agent_id,
            acquired_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=timeout_seconds)).isoformat(),
            timeout_seconds=timeout_seconds,
        )

    # ------------------------------------------------------------------
    # Public API — core
    # ------------------------------------------------------------------

    def acquire(
        self,
        task_id: str,
        agent_id: str,
        timeout_seconds: float | None = None,
        raise_on_conflict: bool = False,
    ) -> TaskLock | None:
        """
        Attempt to acquire an exclusive lock on *task_id* for *agent_id*.

        If the task is already locked by a **different** agent and the lock
        has **not expired**, returns ``None`` (or raises ``LockConflictError``
        when *raise_on_conflict* is True).

        If the task is locked by the **same** agent (re-entrant call), the
        lock TTL is refreshed and the updated ``TaskLock`` is returned.

        Expired locks from any agent are silently swept and replaced.

        Parameters
        ----------
        task_id:
            The plan task identifier to lock.
        agent_id:
            Identifier of the calling agent.
        timeout_seconds:
            TTL for this lock. Defaults to ``self.default_timeout_seconds``.
        raise_on_conflict:
            When True, raise ``LockConflictError`` instead of returning None.

        Returns
        -------
        TaskLock on success, None if the task is locked by another agent.
        """
        ttl = timeout_seconds if timeout_seconds is not None else self.default_timeout_seconds
        path = self._lock_path(task_id)

        while True:
            # Optimistic path: try to create the file exclusively
            new_lock = self._make_lock(task_id, agent_id, ttl)
            created = self._create_lock_atomic(path, new_lock)
            if created:
                return new_lock

            # File already exists — inspect it
            existing = self._read_lock(path)

            if existing is None:
                # Corrupt / deleted between our open and read — retry
                continue

            if existing.is_expired():
                # Expired lock: overwrite it (best-effort; two agents may race
                # here, but file-replace is atomic so one will win cleanly)
                self._overwrite_lock(path, new_lock)
                return new_lock

            if existing.agent_id == agent_id:
                # Re-entrant: same agent refreshes the TTL
                self._overwrite_lock(path, new_lock)
                return new_lock

            # Active lock held by a different agent
            if raise_on_conflict:
                raise LockConflictError(task_id, existing)
            return None

    def release(
        self,
        task_id: str,
        agent_id: str,
        *,
        force: bool = False,
    ) -> bool:
        """
        Release the lock on *task_id*.

        Parameters
        ----------
        task_id:
            The task whose lock to release.
        agent_id:
            Must match the lock's ``agent_id`` unless *force* is True.
        force:
            If True, remove the lock regardless of which agent holds it
            (e.g. for admin / clean-up scenarios).

        Returns
        -------
        True if a lock was removed, False if no lock file existed.

        Raises
        ------
        LockNotOwnedError
            When *force* is False and a different agent holds the lock.
        """
        path = self._lock_path(task_id)
        existing = self._read_lock(path)

        if existing is None:
            return False  # nothing to release

        if not force and existing.agent_id != agent_id:
            if not existing.is_expired():
                raise LockNotOwnedError(task_id, agent_id, existing.agent_id)
            # Expired lock from another agent — safe to remove
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return False  # already removed by a concurrent release

    def extend(
        self,
        task_id: str,
        agent_id: str,
        additional_seconds: float,
    ) -> TaskLock | None:
        """
        Extend the TTL of an existing lock by *additional_seconds*.

        Only the agent that currently holds the lock may extend it.

        Returns the updated ``TaskLock``, or ``None`` if no valid lock exists
        for this *agent_id*.

        Raises
        ------
        LockNotOwnedError
            When a different (non-expired) agent holds the lock.
        """
        path = self._lock_path(task_id)
        existing = self._read_lock(path)

        if existing is None or existing.is_expired():
            return None  # no lock to extend

        if existing.agent_id != agent_id:
            raise LockNotOwnedError(task_id, agent_id, existing.agent_id)

        new_expires = existing.expires_at_dt + timedelta(seconds=additional_seconds)
        updated = TaskLock(
            task_id=task_id,
            agent_id=agent_id,
            acquired_at=existing.acquired_at,
            expires_at=new_expires.isoformat(),
            timeout_seconds=existing.timeout_seconds + additional_seconds,
        )
        self._overwrite_lock(path, updated)
        return updated

    # ------------------------------------------------------------------
    # Public API — inspection
    # ------------------------------------------------------------------

    def get_lock(self, task_id: str) -> TaskLock | None:
        """
        Return the active lock for *task_id*, or ``None`` if unlocked / expired.

        Expired lock files are removed automatically.
        """
        path = self._lock_path(task_id)
        lock = self._read_lock(path)
        if lock is None:
            return None
        if lock.is_expired():
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            return None
        return lock

    def is_locked(self, task_id: str) -> bool:
        """Return True if *task_id* has an active (non-expired) lock."""
        return self.get_lock(task_id) is not None

    def list_locks(self) -> list[TaskLock]:
        """
        Return all currently active (non-expired) locks.

        Expired lock files encountered during the scan are removed.
        """
        if not self.locks_dir.exists():
            return []

        active: list[TaskLock] = []
        for path in sorted(self.locks_dir.glob("*.lock")):
            lock = self._read_lock(path)
            if lock is None:
                continue
            if lock.is_expired():
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            else:
                active.append(lock)
        return active

    def sweep_expired(self) -> list[str]:
        """
        Remove all expired lock files.

        Returns a list of the task IDs whose locks were swept.
        """
        if not self.locks_dir.exists():
            return []

        swept: list[str] = []
        for path in list(self.locks_dir.glob("*.lock")):
            lock = self._read_lock(path)
            if lock is not None and lock.is_expired():
                try:
                    path.unlink(missing_ok=True)
                    swept.append(lock.task_id)
                except OSError:
                    pass
        return swept

    # ------------------------------------------------------------------
    # Agent SDK hook integration
    # ------------------------------------------------------------------

    def as_acquire_hook(
        self,
        task_id: str,
        agent_id: str,
        timeout_seconds: float | None = None,
    ):
        """
        Return an async hook function suitable for the Agent SDK's
        ``SessionStart`` event.

        The hook acquires the task lock when the agent session begins.
        If the task is already locked (conflict), the hook raises
        ``LockConflictError`` to abort the session.

        Example
        -------
        .. code-block:: python

            proto = TaskLockProtocol()
            options = ClaudeAgentOptions(
                hooks={
                    "SessionStart": [
                        HookMatcher(
                            matcher=".*",
                            hooks=[proto.as_acquire_hook("task-id", "agent-42")],
                        )
                    ]
                }
            )
        """
        proto = self

        async def _acquire_hook(input_data: dict, tool_use_id: str, context: Any) -> dict:
            lock = proto.acquire(
                task_id,
                agent_id,
                timeout_seconds=timeout_seconds,
                raise_on_conflict=True,
            )
            print(f"[task-lock] acquired lock on '{task_id}' for agent '{agent_id}' "
                  f"(expires in {lock.seconds_remaining():.0f}s)")
            return {}

        return _acquire_hook

    def as_release_hook(self, task_id: str, agent_id: str):
        """
        Return an async hook function suitable for the Agent SDK's
        ``Stop`` or ``SessionEnd`` events.

        The hook releases the task lock when the agent session ends.

        Example
        -------
        .. code-block:: python

            proto = TaskLockProtocol()
            options = ClaudeAgentOptions(
                hooks={
                    "Stop": [
                        HookMatcher(
                            matcher=".*",
                            hooks=[proto.as_release_hook("task-id", "agent-42")],
                        )
                    ]
                }
            )
        """
        proto = self

        async def _release_hook(input_data: dict, tool_use_id: str, context: Any) -> dict:
            released = proto.release(task_id, agent_id, force=False)
            if released:
                print(f"[task-lock] released lock on '{task_id}' for agent '{agent_id}'")
            else:
                print(f"[task-lock] no lock to release for '{task_id}' / '{agent_id}'")
            return {}

        return _release_hook

    def agent_options_with_lock(
        self,
        base_options: Any,
        task_id: str,
        agent_id: str,
        timeout_seconds: float | None = None,
    ) -> Any:
        """
        Return a copy of *base_options* augmented with lock acquire/release hooks.

        - Acquires the lock on ``SessionStart``.
        - Releases it on ``Stop`` (covers both normal completion and interruption).

        Parameters
        ----------
        base_options:
            A ``ClaudeAgentOptions`` instance to augment.
        task_id:
            The plan task this agent session will work on.
        agent_id:
            The agent's identifier (used in the lock record).
        timeout_seconds:
            Lock TTL. Defaults to ``self.default_timeout_seconds``.

        Raises
        ------
        LockConflictError
            At session start, if another agent already holds the lock.
        """
        # Import here to avoid hard dependency when using the protocol
        # without the Agent SDK
        from claude_agent_sdk import HookMatcher  # type: ignore[import]

        acquire_hook = self.as_acquire_hook(task_id, agent_id, timeout_seconds)
        release_hook = self.as_release_hook(task_id, agent_id)

        existing_hooks: dict = dict(getattr(base_options, "hooks", None) or {})

        # Merge with any pre-existing hooks for these events
        start_matchers: list = list(existing_hooks.get("SessionStart", []))
        stop_matchers: list  = list(existing_hooks.get("Stop", []))

        start_matchers.append(HookMatcher(matcher=".*", hooks=[acquire_hook]))
        stop_matchers.append(HookMatcher(matcher=".*", hooks=[release_hook]))

        existing_hooks["SessionStart"] = start_matchers
        existing_hooks["Stop"]         = stop_matchers

        base_options.hooks = existing_hooks
        return base_options

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        n = len(self.list_locks())
        return (
            f"TaskLockProtocol(locks_dir={str(self.locks_dir)!r}, "
            f"default_timeout={self.default_timeout_seconds}s, "
            f"active_locks={n})"
        )


# ---------------------------------------------------------------------------
# State-service integration
# ---------------------------------------------------------------------------


class StateServiceLockClient:
    """Async client that syncs task-lock events to the claw-forge state service.

    Each file-based lock operation (acquire / extend / release) is mirrored to
    the state service via ``PATCH /features/{task_id}`` so that the
    :class:`TaskLockProtocol` dashboards, ``/harness:status``, and
    ``coordinate.py`` all show consistent lock state.

    The client is intentionally *best-effort*: if the state service is
    unreachable the file-based lock still succeeds.  Network errors are
    logged to *stderr* and swallowed so a connectivity blip never blocks
    an agent from starting work.

    Parameters
    ----------
    state_url:
        Base URL of the claw-forge state service.
        Default: ``http://localhost:8888``
    timeout_seconds:
        HTTP request timeout.  Default: 5 s.

    Example
    -------
    .. code-block:: python

        proto  = TaskLockProtocol(default_timeout_seconds=300)
        client = StateServiceLockClient(state_url="http://localhost:8888")

        lock = proto.acquire("TASK-001", agent_id="agent-42")
        if lock:
            await client.notify_acquire("TASK-001", lock)
            # ... do work ...
            proto.release("TASK-001", agent_id="agent-42")
            await client.notify_release("TASK-001", "agent-42", outcome="done")

    Agent SDK integration (one-liner)
    ----------------------------------
    .. code-block:: python

        options = proto.agent_options_with_lock(
            base_options=ClaudeAgentOptions(allowed_tools=["Read", "Edit"]),
            task_id="TASK-001",
            agent_id="agent-42",
            state_client=StateServiceLockClient(),   # ← pass the client here
        )
    """

    def __init__(
        self,
        state_url: str = "http://localhost:8888",
        timeout_seconds: float = 5.0,
    ) -> None:
        if not _HTTPX_AVAILABLE:  # pragma: no cover
            raise ImportError(
                "httpx is required for StateServiceLockClient. "
                "Install it with: pip install httpx"
            )
        self.state_url = state_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    # ------------------------------------------------------------------
    # Notification helpers
    # ------------------------------------------------------------------

    async def notify_acquire(self, task_id: str, lock: "TaskLock") -> bool:
        """Tell the state service that *lock* was acquired for *task_id*.

        Sends:  PATCH /features/{task_id}
        Body:   {"lock_action": "acquire", "agent_id": "...",
                 "timeout_seconds": ..., "acquired_at": "..."}

        Returns True on HTTP 2xx, False on any error.
        """
        return await self._patch(task_id, {
            "lock_action": "acquire",
            "agent_id": lock.agent_id,
            "timeout_seconds": lock.timeout_seconds,
            "acquired_at": lock.acquired_at,
            "expires_at": lock.expires_at,
        })

    async def notify_extend(self, task_id: str, lock: "TaskLock") -> bool:
        """Tell the state service that the lock on *task_id* was extended.

        Sends:  PATCH /features/{task_id}
        Body:   {"lock_action": "extend", "agent_id": "...",
                 "expires_at": "...", "timeout_seconds": ...}

        Returns True on HTTP 2xx, False on any error.
        """
        return await self._patch(task_id, {
            "lock_action": "extend",
            "agent_id": lock.agent_id,
            "expires_at": lock.expires_at,
            "timeout_seconds": lock.timeout_seconds,
        })

    async def notify_release(
        self,
        task_id: str,
        agent_id: str,
        outcome: str = "done",
        notes: str | None = None,
    ) -> bool:
        """Tell the state service that the lock on *task_id* was released.

        Sends:  PATCH /features/{task_id}
        Body:   {"lock_action": "release", "agent_id": "...",
                 "outcome": "done|failed|skipped|handed-off", "notes": "..."}

        *outcome* is forwarded as the feature's new ``status`` when it is
        ``"done"`` or ``"failed"`` so dashboards update automatically.

        Returns True on HTTP 2xx, False on any error.
        """
        payload: dict = {
            "lock_action": "release",
            "agent_id": agent_id,
            "outcome": outcome,
        }
        if notes is not None:
            payload["notes"] = notes
        if outcome == "done":
            payload["status"] = "done"
        return await self._patch(task_id, payload)

    async def get_lock_state(self, task_id: str) -> dict | None:
        """Fetch the current lock record for *task_id* from the state service.

        Sends:  GET /features/{task_id}/lock

        Returns the parsed JSON response dict, or None on error / not found.
        """
        import sys
        url = f"{self.state_url}/features/{task_id}/lock"
        try:
            async with _httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
        except Exception as exc:
            print(
                f"[task-lock] state-service GET {url} failed: {exc}",
                file=sys.stderr,
            )
        return None

    async def list_locks(self) -> list[dict]:
        """Fetch all active locks from the state service.

        Sends:  GET /features/locks

        Returns a list of lock record dicts; empty list on error.
        """
        import sys
        url = f"{self.state_url}/features/locks"
        try:
            async with _httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
                return data.get("locks", data) if isinstance(data, dict) else data
        except Exception as exc:
            print(
                f"[task-lock] state-service GET {url} failed: {exc}",
                file=sys.stderr,
            )
        return []

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _patch(self, task_id: str, payload: dict) -> bool:
        """Send PATCH /features/{task_id} with *payload*.  Returns True on 2xx."""
        import sys
        url = f"{self.state_url}/features/{task_id}"
        try:
            async with _httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.patch(url, json=payload)
                resp.raise_for_status()
                return True
        except Exception as exc:
            print(
                f"[task-lock] state-service PATCH {url} failed: {exc}",
                file=sys.stderr,
            )
            return False

    def __repr__(self) -> str:
        return f"StateServiceLockClient(state_url={self.state_url!r})"


# ---------------------------------------------------------------------------
# Combined async protocol (file lock + state service)
# ---------------------------------------------------------------------------


class AsyncTaskLockProtocol(TaskLockProtocol):
    """Extends :class:`TaskLockProtocol` with automatic state-service sync.

    Every ``acquire``, ``extend``, and ``release`` call is mirrored to the
    claw-forge state service asynchronously.  The file-based lock always
    succeeds or fails first; the network call is best-effort and never blocks
    the return value.

    Parameters
    ----------
    state_client:
        A :class:`StateServiceLockClient` instance.  When *None*, the protocol
        falls back to pure file-based locking (identical to
        :class:`TaskLockProtocol`).
    locks_dir / default_timeout_seconds:
        Forwarded to :class:`TaskLockProtocol`.

    Example
    -------
    .. code-block:: python

        import asyncio
        from harness_skills.task_lock import AsyncTaskLockProtocol, StateServiceLockClient

        async def main():
            proto = AsyncTaskLockProtocol(
                state_client=StateServiceLockClient("http://localhost:8888"),
                default_timeout_seconds=300,
            )

            lock = await proto.async_acquire("TASK-001", agent_id="agent-42")
            if lock is None:
                print("Task locked by another agent — backing off")
                return

            try:
                # ... do work ...
                await asyncio.sleep(1)
            finally:
                await proto.async_release("TASK-001", agent_id="agent-42",
                                          outcome="done")

        asyncio.run(main())
    """

    def __init__(
        self,
        state_client: StateServiceLockClient | None = None,
        locks_dir: Path = _DEFAULT_LOCKS_DIR,
        default_timeout_seconds: float = 300.0,
    ) -> None:
        super().__init__(locks_dir=locks_dir, default_timeout_seconds=default_timeout_seconds)
        self.state_client = state_client

    # ------------------------------------------------------------------
    # Async counterparts of the core public API
    # ------------------------------------------------------------------

    async def async_acquire(
        self,
        task_id: str,
        agent_id: str,
        timeout_seconds: float | None = None,
        raise_on_conflict: bool = False,
    ) -> "TaskLock | None":
        """Acquire a file-based lock and notify the state service.

        Parameters mirror :meth:`TaskLockProtocol.acquire`.

        Returns the ``TaskLock`` on success or ``None`` (/ raises
        ``LockConflictError``) on conflict — identical semantics to the
        synchronous version.
        """
        lock = self.acquire(
            task_id,
            agent_id,
            timeout_seconds=timeout_seconds,
            raise_on_conflict=raise_on_conflict,
        )
        if lock is not None and self.state_client is not None:
            await self.state_client.notify_acquire(task_id, lock)
        return lock

    async def async_release(
        self,
        task_id: str,
        agent_id: str,
        *,
        force: bool = False,
        outcome: str = "done",
        notes: str | None = None,
    ) -> bool:
        """Release a file-based lock and notify the state service.

        Parameters mirror :meth:`TaskLockProtocol.release` plus *outcome* and
        *notes* which are forwarded to the state service as the task result.

        Returns True if a lock was removed.
        """
        released = self.release(task_id, agent_id, force=force)
        if self.state_client is not None:
            await self.state_client.notify_release(
                task_id, agent_id, outcome=outcome, notes=notes
            )
        return released

    async def async_extend(
        self,
        task_id: str,
        agent_id: str,
        additional_seconds: float,
    ) -> "TaskLock | None":
        """Extend a file-based lock TTL and notify the state service.

        Parameters mirror :meth:`TaskLockProtocol.extend`.

        Returns the updated ``TaskLock`` or ``None`` if no valid lock exists.
        """
        lock = self.extend(task_id, agent_id, additional_seconds)
        if lock is not None and self.state_client is not None:
            await self.state_client.notify_extend(task_id, lock)
        return lock

    # ------------------------------------------------------------------
    # Async Agent SDK hooks
    # ------------------------------------------------------------------

    def as_async_acquire_hook(
        self,
        task_id: str,
        agent_id: str,
        timeout_seconds: float | None = None,
    ):
        """Return an async hook for the Agent SDK ``SessionStart`` event.

        Acquires the file-based lock *and* notifies the state service when
        the agent session starts.  Raises ``LockConflictError`` to abort
        the session if the task is already locked.
        """
        proto = self

        async def _acquire_hook(input_data: dict, tool_use_id: str, context: Any) -> dict:
            lock = await proto.async_acquire(
                task_id,
                agent_id,
                timeout_seconds=timeout_seconds,
                raise_on_conflict=True,
            )
            print(
                f"[task-lock] acquired lock on '{task_id}' for agent '{agent_id}' "
                f"(expires in {lock.seconds_remaining():.0f}s)"
            )
            return {}

        return _acquire_hook

    def as_async_release_hook(
        self,
        task_id: str,
        agent_id: str,
        outcome: str = "done",
    ):
        """Return an async hook for the Agent SDK ``Stop`` event.

        Releases the file-based lock and notifies the state service.
        """
        proto = self

        async def _release_hook(input_data: dict, tool_use_id: str, context: Any) -> dict:
            released = await proto.async_release(
                task_id, agent_id, outcome=outcome
            )
            if released:
                print(f"[task-lock] released lock on '{task_id}' for agent '{agent_id}'")
            else:
                print(f"[task-lock] no lock to release for '{task_id}' / '{agent_id}'")
            return {}

        return _release_hook

    def __repr__(self) -> str:
        n = len(self.list_locks())
        return (
            f"AsyncTaskLockProtocol("
            f"state_client={self.state_client!r}, "
            f"locks_dir={str(self.locks_dir)!r}, "
            f"default_timeout={self.default_timeout_seconds}s, "
            f"active_locks={n})"
        )
