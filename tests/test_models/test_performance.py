"""Tests for harness_skills.models.performance and PerformanceTracker.

Coverage targets
----------------
ToolTimingModel
  - valid construction, field constraints (ge=0 on elapsed_ms, min_length on
    tool_name), extra-fields forbidden
MemorySnapshotModel
  - valid construction, sentinel -1 accepted, negative < -1 rejected
PerformanceReportModel
  - default empty report, tool_timings list, all Optional fields default None,
    extra-fields forbidden, JSON round-trip
PerformanceResponse
  - default values, nested report, psutil_available flag, JSON serialisation

PerformanceTracker (synthetic / no-API-key path)
  - session lifecycle: start → pre-tool → post-tool → end
  - startup_duration_ms computed correctly
  - ToolTiming records created for success and failure paths
  - get_response_times() returns copy
  - get_peak_memory_bytes() returns int >= -1
  - summary() produces correct PerformanceReport
  - print_summary() and print_tool_breakdown() do not raise
  - hooks() dict contains the five expected keys
  - mid-session live queries (get_startup_duration_ms before first tool → None)
"""

from __future__ import annotations

import asyncio
import json

import pytest
from pydantic import ValidationError

from harness_skills.models.performance import (
    MemorySnapshotModel,
    PerformanceReportModel,
    PerformanceResponse,
    ToolTimingModel,
)
from harness_skills.performance_hooks import PerformanceTracker


# ===========================================================================
# ToolTimingModel
# ===========================================================================


class TestToolTimingModel:
    def test_valid_construction(self) -> None:
        t = ToolTimingModel(tool_name="Read", elapsed_ms=42.5, success=True)
        assert t.tool_name == "Read"
        assert t.elapsed_ms == 42.5
        assert t.success is True

    def test_zero_elapsed_accepted(self) -> None:
        t = ToolTimingModel(tool_name="Bash", elapsed_ms=0.0, success=False)
        assert t.elapsed_ms == 0.0
        assert t.success is False

    def test_negative_elapsed_rejected(self) -> None:
        with pytest.raises(ValidationError, match="elapsed_ms"):
            ToolTimingModel(tool_name="Bash", elapsed_ms=-1.0, success=True)

    def test_empty_tool_name_rejected(self) -> None:
        with pytest.raises(ValidationError, match="tool_name"):
            ToolTimingModel(tool_name="", elapsed_ms=10.0, success=True)

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            ToolTimingModel(
                tool_name="Read",
                elapsed_ms=10.0,
                success=True,
                unknown="oops",
            )

    def test_json_round_trip(self) -> None:
        t = ToolTimingModel(tool_name="Glob", elapsed_ms=123.456, success=True)
        data = json.loads(t.model_dump_json())
        assert data["tool_name"] == "Glob"
        assert data["elapsed_ms"] == pytest.approx(123.456)
        assert data["success"] is True


# ===========================================================================
# MemorySnapshotModel
# ===========================================================================


class TestMemorySnapshotModel:
    def test_valid_construction(self) -> None:
        s = MemorySnapshotModel(
            label="session_start",
            tracemalloc_bytes=4096,
            rss_bytes=1_048_576,
        )
        assert s.label == "session_start"
        assert s.tracemalloc_bytes == 4096
        assert s.rss_bytes == 1_048_576

    def test_sentinel_minus_one_accepted(self) -> None:
        s = MemorySnapshotModel(
            label="session_end",
            tracemalloc_bytes=-1,
            rss_bytes=-1,
        )
        assert s.tracemalloc_bytes == -1
        assert s.rss_bytes == -1

    def test_below_minus_one_rejected_for_tracemalloc(self) -> None:
        with pytest.raises(ValidationError, match="tracemalloc_bytes"):
            MemorySnapshotModel(
                label="snap",
                tracemalloc_bytes=-2,
                rss_bytes=0,
            )

    def test_below_minus_one_rejected_for_rss(self) -> None:
        with pytest.raises(ValidationError, match="rss_bytes"):
            MemorySnapshotModel(
                label="snap",
                tracemalloc_bytes=0,
                rss_bytes=-2,
            )

    def test_empty_label_rejected(self) -> None:
        with pytest.raises(ValidationError, match="label"):
            MemorySnapshotModel(
                label="",
                tracemalloc_bytes=0,
                rss_bytes=0,
            )

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            MemorySnapshotModel(
                label="snap",
                tracemalloc_bytes=0,
                rss_bytes=0,
                extra_field="bad",
            )


# ===========================================================================
# PerformanceReportModel
# ===========================================================================


class TestPerformanceReportModel:
    def test_default_empty_report(self) -> None:
        r = PerformanceReportModel()
        assert r.startup_duration_ms is None
        assert r.session_duration_ms is None
        assert r.tool_count == 0
        assert r.tool_timings == []
        assert r.mean_response_ms is None
        assert r.median_response_ms is None
        assert r.min_response_ms is None
        assert r.max_response_ms is None
        assert r.p95_response_ms is None
        assert r.peak_tracemalloc_bytes == -1
        assert r.delta_rss_bytes == -1
        assert r.memory_snapshots == []

    def test_full_report_construction(self) -> None:
        timing = ToolTimingModel(tool_name="Bash", elapsed_ms=200.0, success=True)
        snap = MemorySnapshotModel(
            label="session_start", tracemalloc_bytes=1024, rss_bytes=2048
        )
        r = PerformanceReportModel(
            startup_duration_ms=55.0,
            session_duration_ms=500.0,
            tool_count=1,
            tool_timings=[timing],
            mean_response_ms=200.0,
            median_response_ms=200.0,
            min_response_ms=200.0,
            max_response_ms=200.0,
            p95_response_ms=200.0,
            peak_tracemalloc_bytes=8192,
            delta_rss_bytes=4096,
            memory_snapshots=[snap],
        )
        assert r.tool_count == 1
        assert r.tool_timings[0].tool_name == "Bash"
        assert r.startup_duration_ms == pytest.approx(55.0)
        assert r.memory_snapshots[0].label == "session_start"

    def test_negative_startup_rejected(self) -> None:
        with pytest.raises(ValidationError, match="startup_duration_ms"):
            PerformanceReportModel(startup_duration_ms=-1.0)

    def test_negative_tool_count_rejected(self) -> None:
        with pytest.raises(ValidationError, match="tool_count"):
            PerformanceReportModel(tool_count=-1)

    def test_negative_peak_tracemalloc_below_minus_one_rejected(self) -> None:
        with pytest.raises(ValidationError, match="peak_tracemalloc_bytes"):
            PerformanceReportModel(peak_tracemalloc_bytes=-2)

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            PerformanceReportModel(unknown_field="oops")

    def test_json_round_trip(self) -> None:
        timing = ToolTimingModel(tool_name="Read", elapsed_ms=99.9, success=True)
        r = PerformanceReportModel(
            startup_duration_ms=30.0,
            tool_count=1,
            tool_timings=[timing],
            mean_response_ms=99.9,
        )
        data = json.loads(r.model_dump_json())
        assert data["startup_duration_ms"] == pytest.approx(30.0)
        assert data["tool_count"] == 1
        assert data["tool_timings"][0]["tool_name"] == "Read"
        assert data["mean_response_ms"] == pytest.approx(99.9)
        assert data["session_duration_ms"] is None

    def test_json_contains_all_keys(self) -> None:
        r = PerformanceReportModel()
        data = json.loads(r.model_dump_json())
        expected_keys = {
            "startup_duration_ms",
            "session_duration_ms",
            "tool_count",
            "tool_timings",
            "mean_response_ms",
            "median_response_ms",
            "min_response_ms",
            "max_response_ms",
            "p95_response_ms",
            "peak_tracemalloc_bytes",
            "delta_rss_bytes",
            "memory_snapshots",
        }
        assert expected_keys.issubset(data.keys())


# ===========================================================================
# PerformanceResponse
# ===========================================================================


class TestPerformanceResponse:
    def test_default_values(self) -> None:
        resp = PerformanceResponse()
        assert resp.command == "harness performance"
        assert resp.tracker_class == "harness_skills.performance_hooks.PerformanceTracker"
        assert "startup_duration_ms" in resp.dimensions
        assert "tool_response_times" in resp.dimensions
        assert "memory_usage" in resp.dimensions
        assert resp.report is None
        assert resp.psutil_available is False
        assert "psutil" in resp.notes

    def test_with_nested_report(self) -> None:
        report = PerformanceReportModel(startup_duration_ms=100.0, tool_count=2)
        resp = PerformanceResponse(report=report, psutil_available=True)
        assert resp.report is not None
        assert resp.report.startup_duration_ms == pytest.approx(100.0)
        assert resp.psutil_available is True

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            PerformanceResponse(unknown="bad")

    def test_json_serialisation(self) -> None:
        resp = PerformanceResponse(psutil_available=True)
        data = json.loads(resp.model_dump_json())
        assert data["command"] == "harness performance"
        assert data["psutil_available"] is True
        assert data["report"] is None
        assert isinstance(data["dimensions"], list)
        assert len(data["dimensions"]) == 3

    def test_json_with_nested_report(self) -> None:
        report = PerformanceReportModel(tool_count=3, mean_response_ms=150.0)
        resp = PerformanceResponse(report=report)
        data = json.loads(resp.model_dump_json())
        assert data["report"]["tool_count"] == 3
        assert data["report"]["mean_response_ms"] == pytest.approx(150.0)


# ===========================================================================
# PerformanceTracker — synthetic hook tests (no API key required)
# ===========================================================================


class TestPerformanceTrackerSynthetic:
    """Exercise PerformanceTracker by calling hook methods directly."""

    @pytest.fixture
    def tracker(self) -> PerformanceTracker:
        return PerformanceTracker()

    # ── hooks() dict ────────────────────────────────────────────────────────

    def test_hooks_dict_contains_five_events(self, tracker: PerformanceTracker) -> None:
        h = tracker.hooks()
        assert set(h.keys()) == {
            "SessionStart",
            "PreToolUse",
            "PostToolUse",
            "PostToolUseFailure",
            "SessionEnd",
        }

    def test_hooks_values_are_callable(self, tracker: PerformanceTracker) -> None:
        for cb in tracker.hooks().values():
            assert callable(cb)

    # ── Pre-session live queries ─────────────────────────────────────────────

    def test_startup_is_none_before_session_start(
        self, tracker: PerformanceTracker
    ) -> None:
        assert tracker.get_startup_duration_ms() is None

    def test_response_times_empty_before_session(
        self, tracker: PerformanceTracker
    ) -> None:
        assert tracker.get_response_times() == []

    def test_peak_memory_returns_int(self, tracker: PerformanceTracker) -> None:
        # Returns -1 (not tracing yet) or a non-negative int if tracing globally
        v = tracker.get_peak_memory_bytes()
        assert isinstance(v, int)
        assert v >= -1

    # ── Full session lifecycle ───────────────────────────────────────────────

    def _run_synthetic_session(
        self,
        tracker: PerformanceTracker,
        *,
        startup_sleep: float = 0.02,
        tool_pairs: list[tuple[str, float]] | None = None,
        fail_tool: bool = False,
    ) -> None:
        """Fire synthetic hook events synchronously via asyncio.run."""

        async def _inner() -> None:
            await tracker._on_session_start({}, "sess-1", None)
            import asyncio as _asyncio
            await _asyncio.sleep(startup_sleep)

            pairs = tool_pairs or [("Read", 0.01), ("Bash", 0.02)]
            for i, (name, dur) in enumerate(pairs):
                tid = f"t{i}"
                await tracker._on_pre_tool_use({"tool_name": name}, tid, None)
                await _asyncio.sleep(dur)
                await tracker._on_post_tool_use({}, tid, None)

            if fail_tool:
                await tracker._on_pre_tool_use({"tool_name": "Write"}, "fail", None)
                await _asyncio.sleep(0.005)
                await tracker._on_post_tool_use_failure({}, "fail", None)

            await tracker._on_session_end({}, "sess-1", None)

        asyncio.run(_inner())

    def test_startup_duration_is_positive(self, tracker: PerformanceTracker) -> None:
        self._run_synthetic_session(tracker, startup_sleep=0.02)
        ms = tracker.get_startup_duration_ms()
        assert ms is not None
        assert ms >= 10.0  # generous lower bound for CI

    def test_tool_count_matches_invocations(
        self, tracker: PerformanceTracker
    ) -> None:
        self._run_synthetic_session(
            tracker,
            tool_pairs=[("Read", 0.01), ("Bash", 0.01), ("Glob", 0.01)],
        )
        report = tracker.summary()
        assert report.tool_count == 3

    def test_tool_count_includes_failure(
        self, tracker: PerformanceTracker
    ) -> None:
        self._run_synthetic_session(
            tracker,
            tool_pairs=[("Read", 0.01)],
            fail_tool=True,
        )
        report = tracker.summary()
        assert report.tool_count == 2  # Read + Write(failed)

    def test_failed_tool_has_success_false(
        self, tracker: PerformanceTracker
    ) -> None:
        self._run_synthetic_session(
            tracker,
            tool_pairs=[("Read", 0.01)],
            fail_tool=True,
        )
        timings = tracker.get_response_times()
        failed = [t for t in timings if not t.success]
        assert len(failed) == 1
        assert failed[0].tool_name == "Write"

    def test_successful_tool_has_success_true(
        self, tracker: PerformanceTracker
    ) -> None:
        self._run_synthetic_session(
            tracker, tool_pairs=[("Bash", 0.01)]
        )
        timings = tracker.get_response_times()
        assert all(t.success for t in timings)

    def test_elapsed_ms_is_positive_for_each_timing(
        self, tracker: PerformanceTracker
    ) -> None:
        self._run_synthetic_session(
            tracker, tool_pairs=[("Read", 0.02), ("Bash", 0.03)]
        )
        for t in tracker.get_response_times():
            assert t.elapsed_ms > 0

    def test_session_duration_ms_is_positive(
        self, tracker: PerformanceTracker
    ) -> None:
        self._run_synthetic_session(tracker)
        report = tracker.summary()
        assert report.session_duration_ms is not None
        assert report.session_duration_ms > 0

    # ── summary() percentile fields ──────────────────────────────────────────

    def test_summary_percentiles_none_when_no_tools(
        self, tracker: PerformanceTracker
    ) -> None:
        asyncio.run(tracker._on_session_start({}, "s", None))
        asyncio.run(tracker._on_session_end({}, "s", None))
        r = tracker.summary()
        assert r.tool_count == 0
        assert r.mean_response_ms is None
        assert r.median_response_ms is None
        assert r.min_response_ms is None
        assert r.max_response_ms is None
        assert r.p95_response_ms is None

    def test_summary_percentiles_present_with_tools(
        self, tracker: PerformanceTracker
    ) -> None:
        self._run_synthetic_session(
            tracker, tool_pairs=[("Read", 0.01), ("Bash", 0.02)]
        )
        r = tracker.summary()
        assert r.mean_response_ms is not None
        assert r.median_response_ms is not None
        assert r.min_response_ms is not None
        assert r.max_response_ms is not None
        assert r.p95_response_ms is not None

    def test_min_le_mean_le_max(self, tracker: PerformanceTracker) -> None:
        self._run_synthetic_session(
            tracker, tool_pairs=[("Read", 0.01), ("Bash", 0.05), ("Glob", 0.03)]
        )
        r = tracker.summary()
        assert r.min_response_ms <= r.mean_response_ms  # type: ignore[operator]
        assert r.mean_response_ms <= r.max_response_ms  # type: ignore[operator]

    def test_p95_le_max(self, tracker: PerformanceTracker) -> None:
        self._run_synthetic_session(
            tracker, tool_pairs=[("Read", 0.01), ("Bash", 0.05)]
        )
        r = tracker.summary()
        assert r.p95_response_ms <= r.max_response_ms  # type: ignore[operator]

    # ── memory fields ────────────────────────────────────────────────────────

    def test_memory_snapshots_created(self, tracker: PerformanceTracker) -> None:
        self._run_synthetic_session(tracker)
        r = tracker.summary()
        labels = [s.label for s in r.memory_snapshots]
        assert "session_start" in labels
        assert "session_end" in labels

    def test_peak_tracemalloc_bytes_gte_minus_one(
        self, tracker: PerformanceTracker
    ) -> None:
        self._run_synthetic_session(tracker)
        r = tracker.summary()
        assert r.peak_tracemalloc_bytes >= -1

    # ── get_response_times() returns copy ───────────────────────────────────

    def test_get_response_times_returns_copy(
        self, tracker: PerformanceTracker
    ) -> None:
        self._run_synthetic_session(
            tracker, tool_pairs=[("Read", 0.01)]
        )
        copy1 = tracker.get_response_times()
        copy2 = tracker.get_response_times()
        assert copy1 is not copy2
        assert len(copy1) == len(copy2)

    # ── print helpers do not raise ───────────────────────────────────────────

    def test_print_summary_does_not_raise(
        self, tracker: PerformanceTracker, capsys
    ) -> None:
        self._run_synthetic_session(tracker)
        tracker.print_summary()  # must not raise
        out = capsys.readouterr().out
        assert "Performance Summary" in out

    def test_print_tool_breakdown_does_not_raise(
        self, tracker: PerformanceTracker, capsys
    ) -> None:
        self._run_synthetic_session(
            tracker, tool_pairs=[("Bash", 0.01)]
        )
        tracker.print_tool_breakdown()
        out = capsys.readouterr().out
        assert "Bash" in out

    def test_print_tool_breakdown_empty_session(
        self, tracker: PerformanceTracker, capsys
    ) -> None:
        tracker.print_tool_breakdown()
        out = capsys.readouterr().out
        assert "no tool calls" in out

    # ── tool_name extraction from data dict ──────────────────────────────────

    def test_tool_name_extracted_from_name_key(
        self, tracker: PerformanceTracker
    ) -> None:
        """PreToolUse data may use 'name' instead of 'tool_name'."""

        async def _run() -> None:
            await tracker._on_session_start({}, "s", None)
            await tracker._on_pre_tool_use({"name": "Grep"}, "t0", None)
            await tracker._on_post_tool_use({}, "t0", None)
            await tracker._on_session_end({}, "s", None)

        asyncio.run(_run())
        timings = tracker.get_response_times()
        assert timings[0].tool_name == "Grep"

    def test_tool_name_defaults_to_unknown(
        self, tracker: PerformanceTracker
    ) -> None:
        """PreToolUse data with no name key → 'unknown'."""

        async def _run() -> None:
            await tracker._on_session_start({}, "s", None)
            await tracker._on_pre_tool_use({}, "t0", None)
            await tracker._on_post_tool_use({}, "t0", None)
            await tracker._on_session_end({}, "s", None)

        asyncio.run(_run())
        timings = tracker.get_response_times()
        assert timings[0].tool_name == "unknown"

    # ── unmatched post-tool does not raise ───────────────────────────────────

    def test_post_tool_without_pre_tool_does_not_raise(
        self, tracker: PerformanceTracker
    ) -> None:
        asyncio.run(tracker._on_post_tool_use({}, "ghost-id", None))
        # No timing recorded for unmatched tool id
        assert tracker.get_response_times() == []
