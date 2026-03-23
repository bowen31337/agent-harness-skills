"""
task_lock_example.py — Runnable demonstrations of the Task Lock Protocol.

Run with:
    python examples/task_lock_example.py

Each section is self-contained and prints its own results.  No external
services are required — locks are stored under /tmp/demo-task-locks/.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from harness_tools.task_lock import LockConflictError, TaskLock, TaskLockProtocol  # noqa: F401

# Use a sandbox-writable temp directory so the demo does not pollute the project workspace
DEMO_DIR = Path(os.environ.get("TMPDIR", "/private/tmp/claude-501")) / "demo-task-locks"

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

DIVIDER = "─" * 60


def section(title: str) -> None:
    print(f"\n{DIVIDER}")
    print(f"  {title}")
    print(DIVIDER)


# ---------------------------------------------------------------------------
# 1. Basic acquire / release
# ---------------------------------------------------------------------------


def demo_basic() -> None:
    section("1. Basic acquire / release")

    proto = TaskLockProtocol(locks_dir=DEMO_DIR, default_timeout_seconds=120)

    lock = proto.acquire("feature/auth-refactor", agent_id="agent-A")
    assert lock is not None
    print(f"  acquired : {lock!r}")
    print(f"  remaining: {lock.seconds_remaining():.1f}s")

    # Same agent can re-acquire (TTL is refreshed)
    lock2 = proto.acquire("feature/auth-refactor", agent_id="agent-A")
    assert lock2 is not None
    print(f"  re-enter : {lock2!r}")

    released = proto.release("feature/auth-refactor", agent_id="agent-A")
    print(f"  released : {released}")


# ---------------------------------------------------------------------------
# 2. Conflict detection — return-None mode
# ---------------------------------------------------------------------------


def demo_conflict_none() -> None:
    section("2. Conflict detection — return None")

    proto = TaskLockProtocol(locks_dir=DEMO_DIR, default_timeout_seconds=120)

    # agent-A acquires
    proto.acquire("task/conflict-demo", agent_id="agent-A")

    # agent-B tries the same task
    result = proto.acquire("task/conflict-demo", agent_id="agent-B")
    if result is None:
        lock = proto.get_lock("task/conflict-demo")
        print(f"  agent-B blocked — lock held by: {lock.agent_id!r}, "
              f"expires in {lock.seconds_remaining():.0f}s")
    else:
        print(f"  unexpected success: {result!r}")

    proto.release("task/conflict-demo", agent_id="agent-A")


# ---------------------------------------------------------------------------
# 3. Conflict detection — raise_on_conflict mode
# ---------------------------------------------------------------------------


def demo_conflict_raise() -> None:
    section("3. Conflict detection — raise LockConflictError")

    proto = TaskLockProtocol(locks_dir=DEMO_DIR, default_timeout_seconds=120)
    proto.acquire("task/raise-demo", agent_id="agent-A")

    try:
        proto.acquire("task/raise-demo", agent_id="agent-B", raise_on_conflict=True)
    except LockConflictError as exc:
        print(f"  LockConflictError caught: {exc}")
    finally:
        proto.release("task/raise-demo", agent_id="agent-A")


# ---------------------------------------------------------------------------
# 4. TTL extend mid-task
# ---------------------------------------------------------------------------


def demo_extend() -> None:
    section("4. Extend lock TTL mid-task")

    proto = TaskLockProtocol(locks_dir=DEMO_DIR, default_timeout_seconds=30)
    lock = proto.acquire("task/long-running", agent_id="agent-A")
    assert lock is not None
    print(f"  initial expires_at : {lock.expires_at}")

    updated = proto.extend("task/long-running", agent_id="agent-A", additional_seconds=120)
    assert updated is not None
    print(f"  extended expires_at: {updated.expires_at}")
    print(f"  total TTL          : {updated.timeout_seconds:.0f}s")

    proto.release("task/long-running", agent_id="agent-A")


# ---------------------------------------------------------------------------
# 5. Auto-expiry — short-lived lock swept on next acquire
# ---------------------------------------------------------------------------


def demo_auto_expiry() -> None:
    section("5. Auto-expiry (short TTL)")

    proto = TaskLockProtocol(locks_dir=DEMO_DIR, default_timeout_seconds=1)

    # agent-A acquires a 1-second lock
    lock = proto.acquire("task/expiry-demo", agent_id="agent-A", timeout_seconds=1)
    assert lock is not None
    print(f"  agent-A acquired: {lock!r}")

    print("  sleeping 2s …")
    time.sleep(2)

    # agent-B acquires after expiry — succeeds
    lock_b = proto.acquire("task/expiry-demo", agent_id="agent-B", timeout_seconds=60)
    assert lock_b is not None
    print(f"  agent-B acquired after expiry: {lock_b!r}")

    proto.release("task/expiry-demo", agent_id="agent-B")


# ---------------------------------------------------------------------------
# 6. Sweep expired locks
# ---------------------------------------------------------------------------


def demo_sweep() -> None:
    section("6. sweep_expired()")

    proto = TaskLockProtocol(locks_dir=DEMO_DIR, default_timeout_seconds=1)

    for i in range(3):
        proto.acquire(f"task/sweep-{i}", agent_id="agent-X", timeout_seconds=1)

    print("  sleeping 2s for locks to expire …")
    time.sleep(2)

    swept = proto.sweep_expired()
    print(f"  swept {len(swept)} expired locks: {swept}")
    print(f"  active locks remaining: {len(proto.list_locks())}")


# ---------------------------------------------------------------------------
# 7. List all active locks
# ---------------------------------------------------------------------------


def demo_list() -> None:
    section("7. list_locks()")

    proto = TaskLockProtocol(locks_dir=DEMO_DIR, default_timeout_seconds=120)

    tasks = ["task/ui", "task/api", "task/db"]
    agents = ["agent-A", "agent-B", "agent-C"]

    for task, agent in zip(tasks, agents):
        proto.acquire(task, agent_id=agent)

    locks = proto.list_locks()
    print(f"  {len(locks)} active lock(s):")
    for lk in locks:
        print(f"    {lk.task_id:<20} → held by {lk.agent_id:<12} "
              f"expires in {lk.seconds_remaining():.0f}s")

    for task, agent in zip(tasks, agents):
        proto.release(task, agent_id=agent)


# ---------------------------------------------------------------------------
# 8. Agent SDK hook integration (async)
# ---------------------------------------------------------------------------


async def demo_hooks_async() -> None:
    section("8. Agent SDK hook integration")

    proto = TaskLockProtocol(locks_dir=DEMO_DIR, default_timeout_seconds=120)

    acquire_hook = proto.as_acquire_hook("task/sdk-demo", agent_id="agent-SDK")
    release_hook = proto.as_release_hook("task/sdk-demo", agent_id="agent-SDK")

    print("  calling acquire hook …")
    await acquire_hook({}, "tool-use-id", {})

    lock = proto.get_lock("task/sdk-demo")
    print(f"  lock active: {lock!r}")

    print("  calling release hook …")
    await release_hook({}, "tool-use-id", {})

    print(f"  lock after release: {proto.get_lock('task/sdk-demo')}")


def demo_hooks() -> None:
    asyncio.run(demo_hooks_async())


# ---------------------------------------------------------------------------
# 9. agent_options_with_lock (shows augmentation without live SDK)
# ---------------------------------------------------------------------------


def demo_agent_options() -> None:
    section("9. agent_options_with_lock() — augment ClaudeAgentOptions")

    print(
        "  This demo requires `claude_agent_sdk` to be installed.\n"
        "  Showing the pattern without importing the SDK:\n"
    )
    print(
        "      from claude_agent_sdk import ClaudeAgentOptions\n"
        "      from harness_tools.task_lock import TaskLockProtocol\n"
        "\n"
        "      proto = TaskLockProtocol(default_timeout_seconds=300)\n"
        "      base  = ClaudeAgentOptions(allowed_tools=['Read', 'Edit'])\n"
        "\n"
        "      options = proto.agent_options_with_lock(\n"
        "          base_options=base,\n"
        "          task_id='feature/auth-refactor',\n"
        "          agent_id='agent-42',\n"
        "      )\n"
        "      # options.hooks now contains:\n"
        "      #   SessionStart → acquire lock (raises LockConflictError on conflict)\n"
        "      #   Stop         → release lock\n"
    )


# ---------------------------------------------------------------------------
# 10. repr / state inspection
# ---------------------------------------------------------------------------


def demo_repr() -> None:
    section("10. TaskLockProtocol repr")

    proto = TaskLockProtocol(locks_dir=DEMO_DIR, default_timeout_seconds=300)
    proto.acquire("task/repr-demo", agent_id="agent-Z")
    print(f"  {proto!r}")
    proto.release("task/repr-demo", agent_id="agent-Z")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    DEMO_DIR.mkdir(parents=True, exist_ok=True)

    demo_basic()
    demo_conflict_none()
    demo_conflict_raise()
    demo_extend()
    demo_auto_expiry()
    demo_sweep()
    demo_list()
    demo_hooks()
    demo_agent_options()
    demo_repr()

    print(f"\n{DIVIDER}")
    print("  All demos complete.")
    print(DIVIDER)
