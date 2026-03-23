"""
tests/test_task_lock.py — pytest test suite for TaskLockProtocol.

Run with:
    pytest tests/test_task_lock.py -v
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

from harness_skills.task_lock import (
    LockConflictError,
    LockNotOwnedError,
    TaskLock,
    TaskLockProtocol,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def proto(tmp_path: Path) -> TaskLockProtocol:
    """A fresh TaskLockProtocol backed by a temporary directory."""
    return TaskLockProtocol(locks_dir=tmp_path / "locks", default_timeout_seconds=120)


@pytest.fixture
def short_proto(tmp_path: Path) -> TaskLockProtocol:
    """A TaskLockProtocol with a very short default TTL (1 second) for expiry tests."""
    return TaskLockProtocol(locks_dir=tmp_path / "locks-short", default_timeout_seconds=1)


# ---------------------------------------------------------------------------
# TaskLock model tests
# ---------------------------------------------------------------------------


class TestTaskLockModel:
    def test_fields_present(self, proto: TaskLockProtocol) -> None:
        lock = proto.acquire("task/model-test", agent_id="agent-X")
        assert lock is not None
        assert lock.task_id == "task/model-test"
        assert lock.agent_id == "agent-X"
        assert lock.timeout_seconds == 120.0
        assert lock.acquired_at != ""
        assert lock.expires_at != ""

    def test_is_expired_false_for_fresh_lock(self, proto: TaskLockProtocol) -> None:
        lock = proto.acquire("task/expiry-false", agent_id="agent-X")
        assert lock is not None
        assert not lock.is_expired()

    def test_seconds_remaining_positive(self, proto: TaskLockProtocol) -> None:
        lock = proto.acquire("task/remaining", agent_id="agent-X")
        assert lock is not None
        assert lock.seconds_remaining() > 0

    def test_to_json_roundtrip(self, proto: TaskLockProtocol) -> None:
        lock = proto.acquire("task/json", agent_id="agent-X")
        assert lock is not None
        restored = TaskLock.from_json(lock.to_json())
        assert restored.task_id == lock.task_id
        assert restored.agent_id == lock.agent_id
        assert restored.acquired_at == lock.acquired_at
        assert restored.expires_at == lock.expires_at
        assert restored.timeout_seconds == lock.timeout_seconds

    def test_to_json_has_expected_keys(self, proto: TaskLockProtocol) -> None:
        lock = proto.acquire("task/json-keys", agent_id="agent-X")
        assert lock is not None
        d = json.loads(lock.to_json())
        assert set(d.keys()) >= {
            "task_id", "agent_id", "acquired_at", "expires_at", "timeout_seconds"
        }

    def test_repr_contains_task_and_agent(self, proto: TaskLockProtocol) -> None:
        lock = proto.acquire("task/repr-test", agent_id="agent-Z")
        assert lock is not None
        r = repr(lock)
        assert "task/repr-test" in r
        assert "agent-Z" in r

    def test_repr_expired_lock(self, short_proto: TaskLockProtocol) -> None:
        lock = short_proto.acquire("task/repr-expired", agent_id="agent-Z")
        assert lock is not None
        time.sleep(1.1)
        r = repr(lock)
        assert "EXPIRED" in r


# ---------------------------------------------------------------------------
# acquire() — happy path
# ---------------------------------------------------------------------------


class TestAcquireHappyPath:
    def test_acquire_returns_task_lock(self, proto: TaskLockProtocol) -> None:
        lock = proto.acquire("task/happy", agent_id="agent-A")
        assert isinstance(lock, TaskLock)

    def test_acquire_creates_lock_file(self, proto: TaskLockProtocol) -> None:
        proto.acquire("task/file-exists", agent_id="agent-A")
        lock_files = list(proto.locks_dir.glob("*.lock"))
        assert len(lock_files) == 1

    def test_lock_file_contains_valid_json(self, proto: TaskLockProtocol) -> None:
        proto.acquire("task/valid-json", agent_id="agent-A")
        (lock_file,) = proto.locks_dir.glob("*.lock")
        parsed = json.loads(lock_file.read_text())
        assert parsed["task_id"] == "task/valid-json"
        assert parsed["agent_id"] == "agent-A"
        assert "acquired_at" in parsed
        assert "expires_at" in parsed
        assert parsed["timeout_seconds"] == 120.0

    def test_custom_timeout_persisted(self, proto: TaskLockProtocol) -> None:
        lock = proto.acquire("task/custom-ttl", agent_id="agent-A", timeout_seconds=60)
        assert lock is not None
        assert lock.timeout_seconds == 60.0

    def test_task_id_sanitisation(self, proto: TaskLockProtocol) -> None:
        """Slashes and spaces in task IDs must not create sub-directories."""
        proto.acquire("feature/auth refactor", agent_id="agent-A")
        files = list(proto.locks_dir.glob("*.lock"))
        assert len(files) == 1
        # No sub-directory created
        assert files[0].parent == proto.locks_dir


# ---------------------------------------------------------------------------
# acquire() — re-entrant (same agent)
# ---------------------------------------------------------------------------


class TestReentrantAcquire:
    def test_same_agent_refreshes_ttl(self, proto: TaskLockProtocol) -> None:
        lock1 = proto.acquire("task/reentrant", agent_id="agent-A", timeout_seconds=10)
        assert lock1 is not None
        # Second acquire should succeed and refresh expires_at
        lock2 = proto.acquire("task/reentrant", agent_id="agent-A", timeout_seconds=10)
        assert lock2 is not None
        # The TTL should be at least as long as the first
        assert lock2.seconds_remaining() >= lock1.seconds_remaining() - 1

    def test_only_one_lock_file_after_reentrant(self, proto: TaskLockProtocol) -> None:
        proto.acquire("task/one-file", agent_id="agent-A")
        proto.acquire("task/one-file", agent_id="agent-A")
        assert len(list(proto.locks_dir.glob("*.lock"))) == 1


# ---------------------------------------------------------------------------
# acquire() — conflict detection
# ---------------------------------------------------------------------------


class TestConflictDetection:
    def test_different_agent_returns_none(self, proto: TaskLockProtocol) -> None:
        proto.acquire("task/conflict", agent_id="agent-A")
        result = proto.acquire("task/conflict", agent_id="agent-B")
        assert result is None

    def test_different_agent_raises_on_conflict(self, proto: TaskLockProtocol) -> None:
        proto.acquire("task/raise-conflict", agent_id="agent-A")
        with pytest.raises(LockConflictError) as exc_info:
            proto.acquire("task/raise-conflict", agent_id="agent-B", raise_on_conflict=True)
        err = exc_info.value
        assert err.task_id == "task/raise-conflict"
        assert err.holder.agent_id == "agent-A"

    def test_lock_conflict_error_message(self, proto: TaskLockProtocol) -> None:
        proto.acquire("task/err-msg", agent_id="agent-A")
        with pytest.raises(LockConflictError) as exc_info:
            proto.acquire("task/err-msg", agent_id="agent-B", raise_on_conflict=True)
        assert "agent-A" in str(exc_info.value)
        assert "task/err-msg" in str(exc_info.value)

    def test_distinct_tasks_do_not_conflict(self, proto: TaskLockProtocol) -> None:
        proto.acquire("task/alpha", agent_id="agent-A")
        lock = proto.acquire("task/beta", agent_id="agent-B")
        assert lock is not None


# ---------------------------------------------------------------------------
# Auto-expiry
# ---------------------------------------------------------------------------


class TestAutoExpiry:
    def test_expired_lock_replaced_by_another_agent(self, short_proto: TaskLockProtocol) -> None:
        lock_a = short_proto.acquire("task/expiry", agent_id="agent-A", timeout_seconds=1)
        assert lock_a is not None
        time.sleep(1.1)
        lock_b = short_proto.acquire("task/expiry", agent_id="agent-B", timeout_seconds=60)
        assert lock_b is not None
        assert lock_b.agent_id == "agent-B"

    def test_only_one_lock_file_after_expiry_replacement(self, short_proto: TaskLockProtocol) -> None:
        short_proto.acquire("task/one-expired", agent_id="agent-A", timeout_seconds=1)
        time.sleep(1.1)
        short_proto.acquire("task/one-expired", agent_id="agent-B", timeout_seconds=60)
        assert len(list(short_proto.locks_dir.glob("*.lock"))) == 1

    def test_get_lock_returns_none_for_expired(self, short_proto: TaskLockProtocol) -> None:
        short_proto.acquire("task/get-expired", agent_id="agent-A", timeout_seconds=1)
        time.sleep(1.1)
        assert short_proto.get_lock("task/get-expired") is None

    def test_get_lock_removes_expired_file(self, short_proto: TaskLockProtocol) -> None:
        short_proto.acquire("task/cleanup", agent_id="agent-A", timeout_seconds=1)
        time.sleep(1.1)
        short_proto.get_lock("task/cleanup")
        assert not any(short_proto.locks_dir.glob("*.lock"))


# ---------------------------------------------------------------------------
# release()
# ---------------------------------------------------------------------------


class TestRelease:
    def test_release_removes_lock_file(self, proto: TaskLockProtocol) -> None:
        proto.acquire("task/release", agent_id="agent-A")
        released = proto.release("task/release", agent_id="agent-A")
        assert released is True
        assert not list(proto.locks_dir.glob("*.lock"))

    def test_release_returns_false_if_no_lock(self, proto: TaskLockProtocol) -> None:
        result = proto.release("task/no-lock", agent_id="agent-A")
        assert result is False

    def test_release_wrong_agent_raises(self, proto: TaskLockProtocol) -> None:
        proto.acquire("task/wrong-agent", agent_id="agent-A")
        with pytest.raises(LockNotOwnedError) as exc_info:
            proto.release("task/wrong-agent", agent_id="agent-B")
        err = exc_info.value
        assert err.task_id == "task/wrong-agent"
        assert err.requesting_agent == "agent-B"
        assert err.actual_agent == "agent-A"

    def test_release_force_removes_any_lock(self, proto: TaskLockProtocol) -> None:
        proto.acquire("task/force-release", agent_id="agent-A")
        released = proto.release("task/force-release", agent_id="agent-B", force=True)
        assert released is True
        assert not proto.is_locked("task/force-release")

    def test_release_expired_lock_by_different_agent_ok(
        self, short_proto: TaskLockProtocol
    ) -> None:
        """Releasing an expired lock held by another agent should succeed (expired = unowned)."""
        short_proto.acquire("task/exp-rel", agent_id="agent-A", timeout_seconds=1)
        time.sleep(1.1)
        # agent-B can release the expired lock of agent-A
        released = short_proto.release("task/exp-rel", agent_id="agent-B")
        assert released is True


# ---------------------------------------------------------------------------
# extend()
# ---------------------------------------------------------------------------


class TestExtend:
    def test_extend_increases_expiry(self, proto: TaskLockProtocol) -> None:
        lock = proto.acquire("task/extend", agent_id="agent-A", timeout_seconds=30)
        assert lock is not None
        before = lock.seconds_remaining()
        updated = proto.extend("task/extend", agent_id="agent-A", additional_seconds=120)
        assert updated is not None
        assert updated.seconds_remaining() > before

    def test_extend_preserves_acquired_at(self, proto: TaskLockProtocol) -> None:
        lock = proto.acquire("task/ext-at", agent_id="agent-A")
        assert lock is not None
        updated = proto.extend("task/ext-at", agent_id="agent-A", additional_seconds=60)
        assert updated is not None
        assert updated.acquired_at == lock.acquired_at

    def test_extend_accumulates_timeout_seconds(self, proto: TaskLockProtocol) -> None:
        proto.acquire("task/ext-accum", agent_id="agent-A", timeout_seconds=30)
        updated = proto.extend("task/ext-accum", agent_id="agent-A", additional_seconds=60)
        assert updated is not None
        assert updated.timeout_seconds == pytest.approx(90.0)

    def test_extend_wrong_agent_raises(self, proto: TaskLockProtocol) -> None:
        proto.acquire("task/ext-wrong", agent_id="agent-A")
        with pytest.raises(LockNotOwnedError):
            proto.extend("task/ext-wrong", agent_id="agent-B", additional_seconds=60)

    def test_extend_no_lock_returns_none(self, proto: TaskLockProtocol) -> None:
        result = proto.extend("task/ext-missing", agent_id="agent-A", additional_seconds=60)
        assert result is None

    def test_extend_expired_lock_returns_none(self, short_proto: TaskLockProtocol) -> None:
        short_proto.acquire("task/ext-expired", agent_id="agent-A", timeout_seconds=1)
        time.sleep(1.1)
        result = short_proto.extend("task/ext-expired", agent_id="agent-A", additional_seconds=60)
        assert result is None


# ---------------------------------------------------------------------------
# get_lock() / is_locked()
# ---------------------------------------------------------------------------


class TestInspection:
    def test_get_lock_returns_active_lock(self, proto: TaskLockProtocol) -> None:
        proto.acquire("task/get", agent_id="agent-A")
        lock = proto.get_lock("task/get")
        assert lock is not None
        assert lock.agent_id == "agent-A"

    def test_get_lock_returns_none_when_unlocked(self, proto: TaskLockProtocol) -> None:
        assert proto.get_lock("task/unlocked") is None

    def test_is_locked_true_when_active(self, proto: TaskLockProtocol) -> None:
        proto.acquire("task/is-locked", agent_id="agent-A")
        assert proto.is_locked("task/is-locked") is True

    def test_is_locked_false_when_absent(self, proto: TaskLockProtocol) -> None:
        assert proto.is_locked("task/absent") is False

    def test_is_locked_false_after_release(self, proto: TaskLockProtocol) -> None:
        proto.acquire("task/post-release", agent_id="agent-A")
        proto.release("task/post-release", agent_id="agent-A")
        assert proto.is_locked("task/post-release") is False


# ---------------------------------------------------------------------------
# list_locks()
# ---------------------------------------------------------------------------


class TestListLocks:
    def test_empty_when_no_locks(self, proto: TaskLockProtocol) -> None:
        assert proto.list_locks() == []

    def test_returns_all_active_locks(self, proto: TaskLockProtocol) -> None:
        for i in range(3):
            proto.acquire(f"task/list-{i}", agent_id=f"agent-{i}")
        locks = proto.list_locks()
        assert len(locks) == 3

    def test_does_not_include_expired(self, short_proto: TaskLockProtocol) -> None:
        short_proto.acquire("task/list-expired", agent_id="agent-X", timeout_seconds=1)
        short_proto.acquire("task/list-active", agent_id="agent-Y", timeout_seconds=120)
        time.sleep(1.1)
        active = short_proto.list_locks()
        task_ids = [lk.task_id for lk in active]
        assert "task/list-expired" not in task_ids
        assert "task/list-active" in task_ids

    def test_list_locks_cleans_up_expired_files(self, short_proto: TaskLockProtocol) -> None:
        short_proto.acquire("task/gc-expired", agent_id="agent-X", timeout_seconds=1)
        time.sleep(1.1)
        short_proto.list_locks()
        # The expired file should have been removed during the scan
        assert not any(short_proto.locks_dir.glob("*.lock"))


# ---------------------------------------------------------------------------
# sweep_expired()
# ---------------------------------------------------------------------------


class TestSweepExpired:
    def test_sweep_removes_expired_files(self, short_proto: TaskLockProtocol) -> None:
        for i in range(3):
            short_proto.acquire(f"task/sweep-{i}", agent_id="agent-X", timeout_seconds=1)
        time.sleep(1.1)
        swept = short_proto.sweep_expired()
        assert len(swept) == 3
        assert not any(short_proto.locks_dir.glob("*.lock"))

    def test_sweep_returns_task_ids(self, short_proto: TaskLockProtocol) -> None:
        short_proto.acquire("task/sweep-id", agent_id="agent-X", timeout_seconds=1)
        time.sleep(1.1)
        swept = short_proto.sweep_expired()
        assert "task/sweep-id" in swept

    def test_sweep_preserves_active_locks(self, short_proto: TaskLockProtocol) -> None:
        short_proto.acquire("task/sweep-expired", agent_id="agent-X", timeout_seconds=1)
        short_proto.acquire("task/sweep-active", agent_id="agent-Y", timeout_seconds=120)
        time.sleep(1.1)
        swept = short_proto.sweep_expired()
        assert "task/sweep-expired" in swept
        assert "task/sweep-active" not in swept
        assert short_proto.is_locked("task/sweep-active")

    def test_sweep_empty_dir_returns_empty_list(self, proto: TaskLockProtocol) -> None:
        result = proto.sweep_expired()
        assert result == []

    def test_sweep_nonexistent_dir_returns_empty_list(self, tmp_path: Path) -> None:
        proto = TaskLockProtocol(locks_dir=tmp_path / "nonexistent", default_timeout_seconds=1)
        assert proto.sweep_expired() == []


# ---------------------------------------------------------------------------
# repr / __repr__
# ---------------------------------------------------------------------------


class TestRepr:
    def test_repr_contains_key_info(self, proto: TaskLockProtocol) -> None:
        proto.acquire("task/repr", agent_id="agent-A")
        r = repr(proto)
        assert "TaskLockProtocol" in r
        assert "120" in r       # default_timeout
        assert "active_locks=1" in r

    def test_repr_no_locks(self, proto: TaskLockProtocol) -> None:
        r = repr(proto)
        assert "active_locks=0" in r


# ---------------------------------------------------------------------------
# Agent SDK hook integration (async)
# ---------------------------------------------------------------------------


class TestSdkHooks:
    def test_acquire_hook_acquires_lock(self, proto: TaskLockProtocol) -> None:
        hook = proto.as_acquire_hook("task/hook-acq", agent_id="agent-SDK")

        async def run():
            await hook({}, "tid", {})

        asyncio.run(run())
        assert proto.is_locked("task/hook-acq")

    def test_release_hook_releases_lock(self, proto: TaskLockProtocol) -> None:
        proto.acquire("task/hook-rel", agent_id="agent-SDK")
        hook = proto.as_release_hook("task/hook-rel", agent_id="agent-SDK")

        async def run():
            await hook({}, "tid", {})

        asyncio.run(run())
        assert not proto.is_locked("task/hook-rel")

    def test_acquire_hook_raises_on_conflict(self, proto: TaskLockProtocol) -> None:
        """If another agent holds the lock, the acquire hook should raise LockConflictError."""
        proto.acquire("task/hook-conflict", agent_id="agent-A")
        hook = proto.as_acquire_hook(
            "task/hook-conflict", agent_id="agent-B"
        )

        async def run():
            await hook({}, "tid", {})

        with pytest.raises(LockConflictError):
            asyncio.run(run())

    def test_release_hook_no_op_if_no_lock(self, proto: TaskLockProtocol) -> None:
        """Release hook on a non-existent lock should not raise."""
        hook = proto.as_release_hook("task/hook-noop", agent_id="agent-X")

        async def run():
            await hook({}, "tid", {})

        asyncio.run(run())  # Should complete without error


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_acquire_after_release(self, proto: TaskLockProtocol) -> None:
        proto.acquire("task/cycle", agent_id="agent-A")
        proto.release("task/cycle", agent_id="agent-A")
        lock = proto.acquire("task/cycle", agent_id="agent-B")
        assert lock is not None
        assert lock.agent_id == "agent-B"

    def test_multiple_distinct_tasks_independent(self, proto: TaskLockProtocol) -> None:
        proto.acquire("task/x", agent_id="agent-A")
        proto.acquire("task/y", agent_id="agent-A")
        proto.acquire("task/z", agent_id="agent-A")
        assert len(proto.list_locks()) == 3

    def test_lock_dir_created_on_first_acquire(self, tmp_path: Path) -> None:
        locks_dir = tmp_path / "new" / "nested" / "locks"
        proto = TaskLockProtocol(locks_dir=locks_dir, default_timeout_seconds=60)
        proto.acquire("task/mkdir", agent_id="agent-A")
        assert locks_dir.exists()

    def test_list_locks_empty_dir(self, tmp_path: Path) -> None:
        locks_dir = tmp_path / "empty"
        proto = TaskLockProtocol(locks_dir=locks_dir, default_timeout_seconds=60)
        assert proto.list_locks() == []

    def test_acquire_uses_default_timeout(self, proto: TaskLockProtocol) -> None:
        lock = proto.acquire("task/default-ttl", agent_id="agent-A")
        assert lock is not None
        assert lock.timeout_seconds == 120.0

    def test_get_lock_after_second_acquire_same_agent(self, proto: TaskLockProtocol) -> None:
        proto.acquire("task/second", agent_id="agent-A", timeout_seconds=60)
        proto.acquire("task/second", agent_id="agent-A", timeout_seconds=120)
        lock = proto.get_lock("task/second")
        assert lock is not None
        # TTL should now be 120
        assert lock.timeout_seconds == pytest.approx(120.0)
