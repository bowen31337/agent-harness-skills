"""Tests for StateServiceLockClient and AsyncTaskLockProtocol in task_lock.py.

These cover the uncovered lines (608+) from the existing test_task_lock.py.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from harness_skills.task_lock import (
    AsyncTaskLockProtocol,
    LockConflictError,
    LockNotOwnedError,
    StateServiceLockClient,
    TaskLock,
    TaskLockProtocol,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_httpx():
    """Mock httpx for StateServiceLockClient tests."""
    with patch.dict("sys.modules", {}):
        yield


# ── TaskLock model edge cases (line 117 = acquired_at_dt, expires_at_dt) ────


class TestTaskLockModelExtra:
    def test_acquired_at_dt(self):
        lock = TaskLock(
            task_id="t1", agent_id="a1",
            acquired_at="2026-01-01T00:00:00+00:00",
            expires_at="2026-01-01T00:05:00+00:00",
            timeout_seconds=300,
        )
        dt = lock.acquired_at_dt
        assert dt.year == 2026

    def test_expires_at_dt(self):
        lock = TaskLock(
            task_id="t1", agent_id="a1",
            acquired_at="2026-01-01T00:00:00+00:00",
            expires_at="2026-01-01T00:05:00+00:00",
            timeout_seconds=300,
        )
        dt = lock.expires_at_dt
        assert dt.year == 2026

    def test_to_dict(self):
        lock = TaskLock(
            task_id="t1", agent_id="a1",
            acquired_at="2026-01-01T00:00:00+00:00",
            expires_at="2026-01-01T00:05:00+00:00",
            timeout_seconds=300,
        )
        d = lock.to_dict()
        assert d["task_id"] == "t1"
        assert isinstance(d, dict)


# ── StateServiceLockClient ──────────────────────────────────────────────────


class TestStateServiceLockClient:
    def test_init(self):
        client = StateServiceLockClient(state_url="http://localhost:9999")
        assert client.state_url == "http://localhost:9999"
        assert client.timeout_seconds == 5.0

    def test_init_strips_trailing_slash(self):
        client = StateServiceLockClient(state_url="http://localhost:9999/")
        assert client.state_url == "http://localhost:9999"

    def test_repr(self):
        client = StateServiceLockClient(state_url="http://localhost:9999")
        r = repr(client)
        assert "StateServiceLockClient" in r
        assert "localhost:9999" in r

    @pytest.mark.asyncio
    async def test_notify_acquire_success(self):
        lock = TaskLock(
            task_id="t1", agent_id="a1",
            acquired_at="2026-01-01T00:00:00+00:00",
            expires_at="2026-01-01T00:05:00+00:00",
            timeout_seconds=300,
        )
        client = StateServiceLockClient(state_url="http://localhost:9999")

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)
        mock_async_client.patch = AsyncMock(return_value=mock_resp)

        with patch("harness_skills.task_lock._httpx") as mock_httpx:
            mock_httpx.AsyncClient.return_value = mock_async_client
            result = await client.notify_acquire("t1", lock)
        assert result is True

    @pytest.mark.asyncio
    async def test_notify_acquire_failure(self):
        lock = TaskLock(
            task_id="t1", agent_id="a1",
            acquired_at="2026-01-01T00:00:00+00:00",
            expires_at="2026-01-01T00:05:00+00:00",
            timeout_seconds=300,
        )
        client = StateServiceLockClient(state_url="http://localhost:9999")

        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)
        mock_async_client.patch = AsyncMock(side_effect=Exception("connection refused"))

        with patch("harness_skills.task_lock._httpx") as mock_httpx:
            mock_httpx.AsyncClient.return_value = mock_async_client
            result = await client.notify_acquire("t1", lock)
        assert result is False

    @pytest.mark.asyncio
    async def test_notify_extend(self):
        lock = TaskLock(
            task_id="t1", agent_id="a1",
            acquired_at="2026-01-01T00:00:00+00:00",
            expires_at="2026-01-01T00:10:00+00:00",
            timeout_seconds=600,
        )
        client = StateServiceLockClient(state_url="http://localhost:9999")

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)
        mock_async_client.patch = AsyncMock(return_value=mock_resp)

        with patch("harness_skills.task_lock._httpx") as mock_httpx:
            mock_httpx.AsyncClient.return_value = mock_async_client
            result = await client.notify_extend("t1", lock)
        assert result is True

    @pytest.mark.asyncio
    async def test_notify_release_done(self):
        client = StateServiceLockClient(state_url="http://localhost:9999")

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)
        mock_async_client.patch = AsyncMock(return_value=mock_resp)

        with patch("harness_skills.task_lock._httpx") as mock_httpx:
            mock_httpx.AsyncClient.return_value = mock_async_client
            result = await client.notify_release("t1", "a1", outcome="done")
        assert result is True

    @pytest.mark.asyncio
    async def test_notify_release_with_notes(self):
        client = StateServiceLockClient(state_url="http://localhost:9999")

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)
        mock_async_client.patch = AsyncMock(return_value=mock_resp)

        with patch("harness_skills.task_lock._httpx") as mock_httpx:
            mock_httpx.AsyncClient.return_value = mock_async_client
            result = await client.notify_release(
                "t1", "a1", outcome="failed", notes="crashed"
            )
        assert result is True

    @pytest.mark.asyncio
    async def test_get_lock_state_200(self):
        client = StateServiceLockClient(state_url="http://localhost:9999")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"task_id": "t1", "agent_id": "a1"}
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)
        mock_async_client.get = AsyncMock(return_value=mock_resp)

        with patch("harness_skills.task_lock._httpx") as mock_httpx:
            mock_httpx.AsyncClient.return_value = mock_async_client
            result = await client.get_lock_state("t1")
        assert result == {"task_id": "t1", "agent_id": "a1"}

    @pytest.mark.asyncio
    async def test_get_lock_state_404(self):
        client = StateServiceLockClient(state_url="http://localhost:9999")

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)
        mock_async_client.get = AsyncMock(return_value=mock_resp)

        with patch("harness_skills.task_lock._httpx") as mock_httpx:
            mock_httpx.AsyncClient.return_value = mock_async_client
            result = await client.get_lock_state("t1")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_lock_state_error(self):
        client = StateServiceLockClient(state_url="http://localhost:9999")

        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)
        mock_async_client.get = AsyncMock(side_effect=Exception("fail"))

        with patch("harness_skills.task_lock._httpx") as mock_httpx:
            mock_httpx.AsyncClient.return_value = mock_async_client
            result = await client.get_lock_state("t1")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_lock_state_non_2xx_raises(self):
        client = StateServiceLockClient(state_url="http://localhost:9999")

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = Exception("500 Internal Server Error")
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)
        mock_async_client.get = AsyncMock(return_value=mock_resp)

        with patch("harness_skills.task_lock._httpx") as mock_httpx:
            mock_httpx.AsyncClient.return_value = mock_async_client
            result = await client.get_lock_state("t1")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_locks_success_dict_response(self):
        client = StateServiceLockClient(state_url="http://localhost:9999")

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"locks": [{"task_id": "t1"}]}
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)
        mock_async_client.get = AsyncMock(return_value=mock_resp)

        with patch("harness_skills.task_lock._httpx") as mock_httpx:
            mock_httpx.AsyncClient.return_value = mock_async_client
            result = await client.list_locks()
        assert result == [{"task_id": "t1"}]

    @pytest.mark.asyncio
    async def test_list_locks_success_list_response(self):
        client = StateServiceLockClient(state_url="http://localhost:9999")

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = [{"task_id": "t1"}]
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)
        mock_async_client.get = AsyncMock(return_value=mock_resp)

        with patch("harness_skills.task_lock._httpx") as mock_httpx:
            mock_httpx.AsyncClient.return_value = mock_async_client
            result = await client.list_locks()
        assert result == [{"task_id": "t1"}]

    @pytest.mark.asyncio
    async def test_list_locks_error(self):
        client = StateServiceLockClient(state_url="http://localhost:9999")

        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)
        mock_async_client.get = AsyncMock(side_effect=Exception("fail"))

        with patch("harness_skills.task_lock._httpx") as mock_httpx:
            mock_httpx.AsyncClient.return_value = mock_async_client
            result = await client.list_locks()
        assert result == []


# ── AsyncTaskLockProtocol ────────────────────────────────────────────────────


class TestAsyncTaskLockProtocol:
    @pytest.fixture
    def proto(self, tmp_path):
        return AsyncTaskLockProtocol(
            state_client=None,
            locks_dir=tmp_path / "locks",
            default_timeout_seconds=120,
        )

    @pytest.fixture
    def mock_client(self):
        client = MagicMock(spec=StateServiceLockClient)
        client.notify_acquire = AsyncMock(return_value=True)
        client.notify_release = AsyncMock(return_value=True)
        client.notify_extend = AsyncMock(return_value=True)
        return client

    @pytest.fixture
    def proto_with_client(self, tmp_path, mock_client):
        return AsyncTaskLockProtocol(
            state_client=mock_client,
            locks_dir=tmp_path / "locks-client",
            default_timeout_seconds=120,
        )

    @pytest.mark.asyncio
    async def test_async_acquire_no_client(self, proto):
        lock = await proto.async_acquire("t1", "a1")
        assert lock is not None
        assert lock.task_id == "t1"

    @pytest.mark.asyncio
    async def test_async_acquire_with_client(self, proto_with_client, mock_client):
        lock = await proto_with_client.async_acquire("t1", "a1")
        assert lock is not None
        mock_client.notify_acquire.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_async_acquire_conflict_no_notify(self, proto_with_client, mock_client):
        await proto_with_client.async_acquire("t1", "a1")
        result = await proto_with_client.async_acquire("t1", "a2")
        assert result is None
        # Only one acquire notification (for the first successful acquire)
        assert mock_client.notify_acquire.await_count == 1

    @pytest.mark.asyncio
    async def test_async_release_no_client(self, proto):
        proto.acquire("t1", "a1")
        released = await proto.async_release("t1", "a1")
        assert released is True

    @pytest.mark.asyncio
    async def test_async_release_with_client(self, proto_with_client, mock_client):
        await proto_with_client.async_acquire("t1", "a1")
        released = await proto_with_client.async_release("t1", "a1")
        assert released is True
        mock_client.notify_release.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_async_release_always_notifies(self, proto_with_client, mock_client):
        """Even when no lock exists, the state service is still notified."""
        released = await proto_with_client.async_release("nonexistent", "a1")
        assert released is False
        mock_client.notify_release.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_async_extend_no_client(self, proto):
        proto.acquire("t1", "a1", timeout_seconds=60)
        lock = await proto.async_extend("t1", "a1", additional_seconds=120)
        assert lock is not None
        assert lock.timeout_seconds == pytest.approx(180.0)

    @pytest.mark.asyncio
    async def test_async_extend_with_client(self, proto_with_client, mock_client):
        await proto_with_client.async_acquire("t1", "a1")
        lock = await proto_with_client.async_extend("t1", "a1", additional_seconds=60)
        assert lock is not None
        mock_client.notify_extend.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_async_extend_no_lock(self, proto_with_client, mock_client):
        lock = await proto_with_client.async_extend("nonexistent", "a1", additional_seconds=60)
        assert lock is None
        mock_client.notify_extend.assert_not_awaited()

    def test_repr(self, proto):
        r = repr(proto)
        assert "AsyncTaskLockProtocol" in r
        assert "state_client=None" in r

    def test_repr_with_client(self, proto_with_client):
        r = repr(proto_with_client)
        assert "AsyncTaskLockProtocol" in r

    # ── Async SDK hooks ──────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_async_acquire_hook(self, proto_with_client, mock_client):
        hook = proto_with_client.as_async_acquire_hook("t1", "a1")
        result = await hook({}, "tid", {})
        assert result == {}
        assert proto_with_client.is_locked("t1")

    @pytest.mark.asyncio
    async def test_async_acquire_hook_conflict(self, proto_with_client, mock_client):
        await proto_with_client.async_acquire("t1", "a1")
        hook = proto_with_client.as_async_acquire_hook("t1", "a2")
        with pytest.raises(LockConflictError):
            await hook({}, "tid", {})

    @pytest.mark.asyncio
    async def test_async_release_hook(self, proto_with_client, mock_client):
        await proto_with_client.async_acquire("t1", "a1")
        hook = proto_with_client.as_async_release_hook("t1", "a1")
        result = await hook({}, "tid", {})
        assert result == {}
        assert not proto_with_client.is_locked("t1")

    @pytest.mark.asyncio
    async def test_async_release_hook_no_lock(self, proto_with_client, mock_client):
        hook = proto_with_client.as_async_release_hook("t1", "a1")
        result = await hook({}, "tid", {})
        assert result == {}


# ── TaskLockProtocol.agent_options_with_lock ─────────────────────────────────


class TestAgentOptionsWithLock:
    def test_agent_options_with_lock(self, tmp_path):
        """Test that agent_options_with_lock merges hooks properly."""
        proto = TaskLockProtocol(
            locks_dir=tmp_path / "locks",
            default_timeout_seconds=120,
        )

        # Mock claude_agent_sdk
        mock_hook_matcher = MagicMock()
        mock_hook_matcher_cls = MagicMock(return_value=mock_hook_matcher)

        with patch.dict("sys.modules", {
            "claude_agent_sdk": MagicMock(HookMatcher=mock_hook_matcher_cls),
        }):
            opts = MagicMock()
            opts.hooks = None
            result = proto.agent_options_with_lock(
                opts, task_id="t1", agent_id="a1"
            )
            assert "SessionStart" in result.hooks
            assert "Stop" in result.hooks

    def test_agent_options_with_existing_hooks(self, tmp_path):
        proto = TaskLockProtocol(
            locks_dir=tmp_path / "locks",
            default_timeout_seconds=120,
        )
        mock_hook_matcher = MagicMock()
        mock_hook_matcher_cls = MagicMock(return_value=mock_hook_matcher)

        with patch.dict("sys.modules", {
            "claude_agent_sdk": MagicMock(HookMatcher=mock_hook_matcher_cls),
        }):
            existing_hook = MagicMock()
            opts = MagicMock()
            opts.hooks = {"SessionStart": [existing_hook], "Stop": []}
            result = proto.agent_options_with_lock(
                opts, task_id="t1", agent_id="a1"
            )
            # Should have the existing hook + our new one
            assert len(result.hooks["SessionStart"]) == 2

    def test_release_concurrent_removal(self, tmp_path):
        """Test release when lock file disappears between read and unlink."""
        proto = TaskLockProtocol(
            locks_dir=tmp_path / "locks",
            default_timeout_seconds=120,
        )
        proto.acquire("t1", "a1")
        path = proto._lock_path("t1")

        # Simulate concurrent removal: delete the file after _read_lock
        original_unlink = path.unlink
        def unlink_then_fail(*args, **kwargs):
            original_unlink(*args, **kwargs)
        path.unlink()  # Remove it before release
        # Now release should return False because the file is gone
        # But _read_lock returns None first
        result = proto.release("t1", "a1")
        assert result is False
