"""Tests for harness_skills.models.lock — 100% coverage target."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from harness_skills.models.lock import (
    LockAcquireRequest,
    LockExtendRequest,
    LockListResponse,
    LockOperationResponse,
    LockRecord,
    LockReleaseRequest,
    LockStateResponse,
)


# ── LockAcquireRequest ──────────────────────────────────────────────────────


class TestLockAcquireRequest:
    def test_minimal(self):
        r = LockAcquireRequest(agent_id="agent-1")
        assert r.lock_action == "acquire"
        assert r.timeout_seconds == 300.0
        assert r.acquired_at is None

    def test_full(self):
        r = LockAcquireRequest(
            agent_id="agent-1",
            timeout_seconds=600,
            acquired_at="2025-01-01T00:00:00Z",
        )
        assert r.timeout_seconds == 600
        assert r.acquired_at == "2025-01-01T00:00:00Z"

    def test_timeout_must_be_positive(self):
        with pytest.raises(ValidationError):
            LockAcquireRequest(agent_id="a", timeout_seconds=0)
        with pytest.raises(ValidationError):
            LockAcquireRequest(agent_id="a", timeout_seconds=-1)

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            LockAcquireRequest(agent_id="a", bogus="x")

    def test_roundtrip(self):
        r = LockAcquireRequest(agent_id="a1")
        assert LockAcquireRequest.model_validate(r.model_dump()) == r


# ── LockExtendRequest ───────────────────────────────────────────────────────


class TestLockExtendRequest:
    def test_create(self):
        r = LockExtendRequest(agent_id="a", additional_seconds=120)
        assert r.lock_action == "extend"
        assert r.additional_seconds == 120

    def test_additional_seconds_must_be_positive(self):
        with pytest.raises(ValidationError):
            LockExtendRequest(agent_id="a", additional_seconds=0)

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            LockExtendRequest(agent_id="a", additional_seconds=1, extra="no")

    def test_roundtrip(self):
        r = LockExtendRequest(agent_id="b", additional_seconds=60)
        assert LockExtendRequest.model_validate(r.model_dump()) == r


# ── LockReleaseRequest ──────────────────────────────────────────────────────


class TestLockReleaseRequest:
    def test_defaults(self):
        r = LockReleaseRequest(agent_id="a")
        assert r.lock_action == "release"
        assert r.outcome == "done"
        assert r.notes is None

    def test_all_outcomes(self):
        for outcome in ("done", "failed", "skipped", "handed-off"):
            r = LockReleaseRequest(agent_id="a", outcome=outcome)
            assert r.outcome == outcome

    def test_invalid_outcome(self):
        with pytest.raises(ValidationError):
            LockReleaseRequest(agent_id="a", outcome="unknown")

    def test_with_notes(self):
        r = LockReleaseRequest(agent_id="a", notes="all good")
        assert r.notes == "all good"

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            LockReleaseRequest(agent_id="a", extra="no")

    def test_roundtrip(self):
        r = LockReleaseRequest(agent_id="a", outcome="failed", notes="err")
        assert LockReleaseRequest.model_validate(r.model_dump()) == r


# ── LockRecord ──────────────────────────────────────────────────────────────


class TestLockRecord:
    def _make(self, **kwargs):
        defaults = dict(
            task_id="task-1",
            agent_id="agent-1",
            acquired_at="2025-06-01T12:00:00+00:00",
            expires_at="2025-06-01T12:05:00+00:00",
            timeout_seconds=300,
        )
        defaults.update(kwargs)
        return LockRecord(**defaults)

    def test_minimal(self):
        r = self._make()
        assert r.state_service_url is None

    def test_full(self):
        r = self._make(state_service_url="http://localhost:8888")
        assert r.state_service_url == "http://localhost:8888"

    def test_timeout_must_be_positive(self):
        with pytest.raises(ValidationError):
            self._make(timeout_seconds=0)

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            self._make(extra="nope")

    def test_seconds_remaining_with_now(self):
        r = self._make(expires_at="2025-06-01T12:05:00+00:00")
        remaining = r.seconds_remaining(now_iso="2025-06-01T12:03:00+00:00")
        assert remaining == pytest.approx(120.0)

    def test_seconds_remaining_without_now(self):
        # expires far in the future → remaining should be positive
        r = self._make(expires_at="2099-01-01T00:00:00+00:00")
        assert r.seconds_remaining() > 0

    def test_is_expired_true(self):
        r = self._make(expires_at="2020-01-01T00:00:00+00:00")
        assert r.is_expired(now_iso="2025-01-01T00:00:00+00:00") is True

    def test_is_expired_false(self):
        r = self._make(expires_at="2099-01-01T00:00:00+00:00")
        assert r.is_expired(now_iso="2025-01-01T00:00:00+00:00") is False

    def test_is_expired_exactly_zero(self):
        r = self._make(expires_at="2025-06-01T12:05:00+00:00")
        assert r.is_expired(now_iso="2025-06-01T12:05:00+00:00") is True

    def test_roundtrip(self):
        r = self._make()
        assert LockRecord.model_validate(r.model_dump()) == r


# ── LockStateResponse ───────────────────────────────────────────────────────


class TestLockStateResponse:
    def test_unlocked(self):
        r = LockStateResponse(task_id="t1", locked=False)
        assert r.lock is None
        assert r.message is None

    def test_locked(self):
        lock = LockRecord(
            task_id="t1",
            agent_id="a1",
            acquired_at="2025-01-01T00:00:00Z",
            expires_at="2025-01-01T00:05:00Z",
            timeout_seconds=300,
        )
        r = LockStateResponse(task_id="t1", locked=True, lock=lock, message="ok")
        assert r.locked is True
        assert r.lock is not None

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            LockStateResponse(task_id="t", locked=False, extra="x")

    def test_roundtrip(self):
        r = LockStateResponse(task_id="t", locked=False)
        assert LockStateResponse.model_validate(r.model_dump()) == r


# ── LockOperationResponse ───────────────────────────────────────────────────


class TestLockOperationResponse:
    def test_acquire_success(self):
        lock = LockRecord(
            task_id="t1",
            agent_id="a1",
            acquired_at="2025-01-01T00:00:00Z",
            expires_at="2025-01-01T00:05:00Z",
            timeout_seconds=300,
        )
        r = LockOperationResponse(
            success=True, action="acquire", task_id="t1", lock=lock
        )
        assert r.success is True
        assert r.conflict_holder is None

    def test_acquire_conflict(self):
        blocker = LockRecord(
            task_id="t1",
            agent_id="other",
            acquired_at="2025-01-01T00:00:00Z",
            expires_at="2025-01-01T00:05:00Z",
            timeout_seconds=300,
        )
        r = LockOperationResponse(
            success=False,
            action="acquire",
            task_id="t1",
            conflict_holder=blocker,
            message="locked by other",
        )
        assert r.success is False
        assert r.conflict_holder is not None

    def test_release(self):
        r = LockOperationResponse(
            success=True, action="release", task_id="t1"
        )
        assert r.lock is None

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            LockOperationResponse(
                success=True, action="acquire", task_id="t", extra="no"
            )

    def test_roundtrip(self):
        r = LockOperationResponse(success=True, action="extend", task_id="t")
        assert LockOperationResponse.model_validate(r.model_dump()) == r


# ── LockListResponse ────────────────────────────────────────────────────────


class TestLockListResponse:
    def test_empty(self):
        r = LockListResponse(snapshot_time="2025-01-01T00:00:00Z", total_active=0)
        assert r.locks == []

    def test_with_locks(self):
        lock = LockRecord(
            task_id="t1",
            agent_id="a1",
            acquired_at="2025-01-01T00:00:00Z",
            expires_at="2025-01-01T00:05:00Z",
            timeout_seconds=300,
        )
        r = LockListResponse(
            snapshot_time="2025-01-01T00:00:00Z", total_active=1, locks=[lock]
        )
        assert len(r.locks) == 1

    def test_total_active_ge_zero(self):
        with pytest.raises(ValidationError):
            LockListResponse(snapshot_time="2025-01-01T00:00:00Z", total_active=-1)

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            LockListResponse(
                snapshot_time="2025-01-01T00:00:00Z", total_active=0, extra="no"
            )

    def test_roundtrip(self):
        r = LockListResponse(snapshot_time="2025-01-01T00:00:00Z", total_active=0)
        assert LockListResponse.model_validate(r.model_dump()) == r
