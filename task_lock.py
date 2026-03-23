"""
task_lock.py — Public façade **and** operator CLI for the Task Lock Protocol.

Re-exports the full API from ``harness_skills.task_lock`` so callers can do:

    from task_lock import TaskLockProtocol, TaskLock, LockConflictError

without caring about the internal package layout.

Quick-start
-----------
    from task_lock import TaskLockProtocol

    proto = TaskLockProtocol(default_timeout_seconds=300)

    # Acquire before work
    lock = proto.acquire("feature/auth-refactor", agent_id="agent-42")
    if lock is None:
        print("Task locked by another agent — backing off")
    else:
        try:
            ...  # do work
        finally:
            proto.release("feature/auth-refactor", agent_id="agent-42")

See ``examples/task_lock_example.py`` for full usage patterns including:
  - extend mid-task
  - raise_on_conflict mode
  - Agent SDK hook integration

Operator CLI
------------
Run ``python task_lock.py <subcommand> [options]`` to manage locks from the
shell without writing any Python.

Subcommands
~~~~~~~~~~~
  list      Print all active (non-expired) locks.
  sweep     Remove all expired lock files and print the swept task IDs.
  acquire   Acquire (or refresh) a lock on a task.
  release   Release the lock on a task.
  status    Show whether a specific task is locked and who holds it.

Global options
~~~~~~~~~~~~~~
  --locks-dir PATH    Directory where lock files are stored.
                      Default: .claude/task-locks
  --timeout SECONDS   Default TTL in seconds (used by ``acquire``).
                      Default: 300

Examples
~~~~~~~~
    # List all locks in the default directory
    python task_lock.py list

    # Check whether task "feature/auth" is locked
    python task_lock.py status --task-id feature/auth

    # Acquire a 10-minute lock on "feature/auth" as "agent-42"
    python task_lock.py acquire --task-id feature/auth --agent-id agent-42 --timeout 600

    # Release the lock (must be the lock holder, or use --force)
    python task_lock.py release --task-id feature/auth --agent-id agent-42

    # Force-release a lock held by any agent (admin use)
    python task_lock.py release --task-id feature/auth --agent-id agent-42 --force

    # Remove all expired lock files
    python task_lock.py sweep

    # Use a custom lock directory
    python task_lock.py --locks-dir /tmp/my-locks list
"""

from harness_skills.task_lock import (
    LockConflictError,
    LockNotOwnedError,
    TaskLock,
    TaskLockProtocol,
)

__all__ = [
    "TaskLock",
    "TaskLockProtocol",
    "LockConflictError",
    "LockNotOwnedError",
]


# ---------------------------------------------------------------------------
# Operator CLI
# ---------------------------------------------------------------------------


def _build_parser():
    import argparse

    parser = argparse.ArgumentParser(
        prog="python task_lock.py",
        description="Task Lock Protocol — operator CLI for claw-forge agents.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--locks-dir",
        default=".claude/task-locks",
        metavar="PATH",
        help="Directory where .lock files are stored (default: .claude/task-locks)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        metavar="SECONDS",
        help="Default lock TTL in seconds for the 'acquire' subcommand (default: 300)",
    )

    sub = parser.add_subparsers(dest="command", metavar="subcommand")
    sub.required = True

    # -- list -----------------------------------------------------------------
    sub.add_parser(
        "list",
        help="Print all currently active (non-expired) locks.",
    )

    # -- sweep ----------------------------------------------------------------
    sub.add_parser(
        "sweep",
        help="Remove all expired lock files and print the swept task IDs.",
    )

    # -- status ---------------------------------------------------------------
    status_p = sub.add_parser(
        "status",
        help="Show whether a specific task is locked and who holds it.",
    )
    status_p.add_argument(
        "--task-id",
        required=True,
        metavar="TASK_ID",
        help="The task identifier to inspect.",
    )

    # -- acquire --------------------------------------------------------------
    acq_p = sub.add_parser(
        "acquire",
        help="Acquire (or refresh) an exclusive lock on a task.",
    )
    acq_p.add_argument(
        "--task-id",
        required=True,
        metavar="TASK_ID",
        help="The task identifier to lock.",
    )
    acq_p.add_argument(
        "--agent-id",
        required=True,
        metavar="AGENT_ID",
        help="Identifier for the calling agent.",
    )
    acq_p.add_argument(
        "--timeout",
        type=float,
        dest="acq_timeout",
        metavar="SECONDS",
        help="TTL for this specific lock (overrides --timeout global flag).",
    )

    # -- release --------------------------------------------------------------
    rel_p = sub.add_parser(
        "release",
        help="Release the lock on a task.",
    )
    rel_p.add_argument(
        "--task-id",
        required=True,
        metavar="TASK_ID",
        help="The task identifier whose lock to release.",
    )
    rel_p.add_argument(
        "--agent-id",
        required=True,
        metavar="AGENT_ID",
        help="Must match the current lock holder unless --force is set.",
    )
    rel_p.add_argument(
        "--force",
        action="store_true",
        help="Release the lock regardless of which agent holds it.",
    )

    return parser


def _cmd_list(proto: TaskLockProtocol) -> int:
    locks = proto.list_locks()
    if not locks:
        print("  (no active locks)")
        return 0
    w_task = max(len(lk.task_id) for lk in locks)
    w_agent = max(len(lk.agent_id) for lk in locks)
    header = f"  {'TASK_ID':<{w_task}}  {'AGENT_ID':<{w_agent}}  ACQUIRED_AT               EXPIRES_IN"
    print(header)
    print("  " + "─" * (len(header) - 2))
    for lk in locks:
        remaining = lk.seconds_remaining()
        mins, secs = divmod(int(remaining), 60)
        exp_str = f"{mins}m {secs:02d}s" if mins else f"{secs}s"
        print(
            f"  {lk.task_id:<{w_task}}  {lk.agent_id:<{w_agent}}"
            f"  {lk.acquired_at[:19]}  {exp_str}"
        )
    return 0


def _cmd_sweep(proto: TaskLockProtocol) -> int:
    swept = proto.sweep_expired()
    if not swept:
        print("  Nothing to sweep — no expired lock files found.")
        return 0
    print(f"  Swept {len(swept)} expired lock(s):")
    for task_id in swept:
        print(f"    • {task_id}")
    return 0


def _cmd_status(proto: TaskLockProtocol, task_id: str) -> int:
    lock = proto.get_lock(task_id)
    if lock is None:
        print(f"  🟢  '{task_id}' is NOT locked (free to acquire)")
        return 0
    remaining = lock.seconds_remaining()
    mins, secs = divmod(int(remaining), 60)
    exp_str = f"{mins}m {secs:02d}s" if mins else f"{secs}s"
    print(
        f"  🔴  '{task_id}' is LOCKED\n"
        f"       agent_id   : {lock.agent_id}\n"
        f"       acquired_at: {lock.acquired_at}\n"
        f"       expires_at : {lock.expires_at}\n"
        f"       remaining  : {exp_str}"
    )
    return 0


def _cmd_acquire(
    proto: TaskLockProtocol,
    task_id: str,
    agent_id: str,
    timeout_seconds: float,
) -> int:
    try:
        lock = proto.acquire(
            task_id,
            agent_id=agent_id,
            timeout_seconds=timeout_seconds,
            raise_on_conflict=True,
        )
    except LockConflictError as exc:
        print(f"  ❌  Could not acquire lock: {exc}")
        return 1

    if lock is None:
        # Shouldn't happen with raise_on_conflict=True, but guard anyway
        print(f"  ❌  '{task_id}' is locked by another agent.")
        return 1

    remaining = lock.seconds_remaining()
    mins, secs = divmod(int(remaining), 60)
    exp_str = f"{mins}m {secs:02d}s" if mins else f"{secs}s"
    print(
        f"  ✅  Lock acquired\n"
        f"       task_id    : {lock.task_id}\n"
        f"       agent_id   : {lock.agent_id}\n"
        f"       acquired_at: {lock.acquired_at}\n"
        f"       expires_at : {lock.expires_at}\n"
        f"       remaining  : {exp_str}"
    )
    return 0


def _cmd_release(
    proto: TaskLockProtocol,
    task_id: str,
    agent_id: str,
    force: bool,
) -> int:
    try:
        released = proto.release(task_id, agent_id=agent_id, force=force)
    except LockNotOwnedError as exc:
        print(f"  ❌  {exc}\n  Tip: use --force to remove regardless of owner.")
        return 1

    if released:
        print(f"  ✅  Lock on '{task_id}' released.")
    else:
        print(f"  ℹ️   No active lock found for '{task_id}'.")
    return 0


def main() -> None:
    import sys
    from pathlib import Path

    parser = _build_parser()
    args = parser.parse_args()

    proto = TaskLockProtocol(
        locks_dir=Path(args.locks_dir),
        default_timeout_seconds=args.timeout,
    )

    if args.command == "list":
        sys.exit(_cmd_list(proto))

    elif args.command == "sweep":
        sys.exit(_cmd_sweep(proto))

    elif args.command == "status":
        sys.exit(_cmd_status(proto, args.task_id))

    elif args.command == "acquire":
        ttl = args.acq_timeout if args.acq_timeout is not None else args.timeout
        sys.exit(_cmd_acquire(proto, args.task_id, args.agent_id, ttl))

    elif args.command == "release":
        sys.exit(_cmd_release(proto, args.task_id, args.agent_id, args.force))


if __name__ == "__main__":
    main()
