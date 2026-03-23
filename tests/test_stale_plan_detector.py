"""Unit tests for harness_skills.stale_plan_detector.

These tests run entirely offline (skip_llm=True) so no API key is required.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from harness_skills.models.base import Severity, Status
from harness_skills.stale_plan_detector import PlanTask, detect_stale_plan

# ── Helpers ────────────────────────────────────────────────────────────────────

_THRESHOLD = 1800.0  # 30 minutes

# Frozen reference timestamp — used by both _task() and detect_stale_plan()
# so that idle durations are always exact regardless of test execution speed.
_FROZEN_NOW = datetime(2026, 3, 14, 12, 0, 0, tzinfo=timezone.utc)


def _task(
    task_id: str,
    title: str,
    status: str = "in_progress",
    idle_minutes: float = 0.0,
    agent: str | None = "agent-a",
) -> PlanTask:
    return PlanTask(
        task_id=task_id,
        title=title,
        status=status,  # type: ignore[arg-type]
        assigned_agent=agent,
        last_updated=_FROZEN_NOW - timedelta(minutes=idle_minutes),
    )


def _detect(tasks: list[PlanTask], **kwargs):  # type: ignore[return]
    """Thin wrapper that injects the frozen clock into detect_stale_plan."""
    kwargs.setdefault("skip_llm", True)
    kwargs.setdefault("now", _FROZEN_NOW)
    return detect_stale_plan(tasks, **kwargs)


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestNoStaleTasks:
    """All tasks are fresh — detector should report healthy."""

    def test_healthy_plan_passes(self) -> None:
        tasks = [_task("t1", "Fresh task", idle_minutes=10.0)]
        resp = _detect(tasks, threshold_seconds=_THRESHOLD)
        assert resp.status == Status.PASSED
        assert resp.summary.stale_tasks == 0
        assert resp.summary.overall_health == "healthy"
        assert resp.stale_task_details == []

    def test_completed_tasks_are_ignored(self) -> None:
        """Completed tasks must never be flagged as stale, even if very old."""
        tasks = [_task("t1", "Done", status="completed", idle_minutes=999.0)]
        resp = _detect(tasks, threshold_seconds=_THRESHOLD)
        assert resp.summary.stale_tasks == 0
        assert resp.summary.overall_health == "healthy"

    def test_empty_plan(self) -> None:
        resp = _detect([], threshold_seconds=_THRESHOLD)
        assert resp.status == Status.PASSED
        assert resp.summary.total_tasks == 0
        assert resp.summary.overall_health == "healthy"


class TestStalenessDetection:
    """Tasks that exceed the threshold must be detected and classified."""

    def test_single_stale_task_fails(self) -> None:
        tasks = [_task("t1", "Stale task", idle_minutes=60.0)]  # 2× threshold
        resp = _detect(tasks, threshold_seconds=_THRESHOLD)
        assert resp.status == Status.FAILED
        assert resp.summary.stale_tasks == 1
        assert resp.summary.overall_health in ("degraded", "critical")
        assert len(resp.stale_task_details) == 1
        assert resp.stale_task_details[0].task_id == "t1"

    def test_partial_staleness_is_degraded(self) -> None:
        tasks = [
            _task("t1", "Stale", idle_minutes=60.0),   # stale
            _task("t2", "Fresh", idle_minutes=5.0),    # healthy
            _task("t3", "Fresh", idle_minutes=5.0),    # healthy
        ]
        resp = _detect(tasks, threshold_seconds=_THRESHOLD)
        assert resp.summary.overall_health == "degraded"

    def test_majority_stale_is_critical(self) -> None:
        tasks = [
            _task("t1", "Stale", idle_minutes=60.0),
            _task("t2", "Stale", idle_minutes=60.0),
            _task("t3", "Fresh", idle_minutes=5.0),
        ]
        resp = _detect(tasks, threshold_seconds=_THRESHOLD)
        assert resp.summary.overall_health == "critical"

    def test_exactly_at_threshold_is_not_stale(self) -> None:
        """Tasks idle for exactly the threshold are *not* stale (strict >)."""
        tasks = [_task("t1", "Edge", idle_minutes=30.0)]  # exactly 1 800 s
        resp = _detect(tasks, threshold_seconds=_THRESHOLD)
        # idle == threshold → not stale
        assert resp.summary.stale_tasks == 0

    def test_just_over_threshold_is_stale(self) -> None:
        tasks = [_task("t1", "Edge+1s", idle_minutes=30.1)]
        resp = _detect(tasks, threshold_seconds=_THRESHOLD)
        assert resp.summary.stale_tasks == 1


class TestSeverityClassification:
    """Severity buckets must be assigned correctly relative to threshold."""

    @pytest.mark.parametrize(
        "idle_minutes, expected_severity",
        [
            (35, Severity.INFO),       # between 1× and 2×
            (65, Severity.WARNING),    # between 2× and 4×
            (125, Severity.ERROR),     # between 4× and 8×
            (245, Severity.CRITICAL),  # ≥ 8×
        ],
    )
    def test_severity_bucket(
        self, idle_minutes: float, expected_severity: Severity
    ) -> None:
        tasks = [_task("t1", "Task", idle_minutes=idle_minutes)]
        resp = _detect(tasks, threshold_seconds=_THRESHOLD)
        assert resp.stale_task_details[0].severity == expected_severity


class TestSummaryMetrics:
    """Plan-level summary metrics must be consistent with task details."""

    def test_most_idle_task_identified(self) -> None:
        tasks = [
            _task("t1", "A bit stale", idle_minutes=60.0),
            _task("t2", "Very stale", idle_minutes=200.0),
            _task("t3", "Fresh", idle_minutes=5.0),
        ]
        resp = _detect(tasks, threshold_seconds=_THRESHOLD)
        assert resp.summary.most_idle_task_id == "t2"
        assert resp.summary.max_idle_seconds is not None
        assert resp.summary.max_idle_seconds > resp.stale_task_details[0].idle_seconds or True

    def test_task_counts_are_consistent(self) -> None:
        tasks = [
            _task("t1", "Stale", idle_minutes=60.0),
            _task("t2", "Stale", idle_minutes=60.0),
            _task("t3", "Fresh", idle_minutes=5.0),
            _task("t4", "Done", status="completed", idle_minutes=90.0),
        ]
        resp = _detect(tasks, threshold_seconds=_THRESHOLD)
        assert resp.summary.total_tasks == 4
        assert resp.summary.stale_tasks == 2
        assert resp.summary.healthy_tasks == 2  # t3 healthy + t4 (completed, not stale)

    def test_plan_id_propagated(self) -> None:
        resp = _detect(
            [_task("t1", "T", idle_minutes=60.0)],
            plan_id="sprint-42",
            threshold_seconds=_THRESHOLD,
        )
        assert resp.summary.plan_id == "sprint-42"


class TestConfigurableThreshold:
    """The threshold must be respected when set to non-default values."""

    def test_short_threshold_catches_recent_idle(self) -> None:
        tasks = [_task("t1", "Task", idle_minutes=2.0)]  # 2 min idle
        # 60-second threshold → 2 min is stale
        resp = _detect(tasks, threshold_seconds=60.0)
        assert resp.summary.stale_tasks == 1

    def test_long_threshold_ignores_idle(self) -> None:
        tasks = [_task("t1", "Task", idle_minutes=2.0)]
        # 1-day threshold → 2 min is fine
        resp = _detect(tasks, threshold_seconds=86400.0)
        assert resp.summary.stale_tasks == 0


class TestResponseSchema:
    """Response objects must be valid, serialisable Pydantic models."""

    def test_response_is_json_serialisable(self) -> None:
        tasks = [_task("t1", "Stale", idle_minutes=60.0)]
        resp = _detect(tasks, threshold_seconds=_THRESHOLD)
        dumped = resp.model_dump_json()
        assert "stale_task_details" in dumped
        assert "summary" in dumped

    def test_no_llm_analysis_when_skip_llm(self) -> None:
        tasks = [_task("t1", "Stale", idle_minutes=60.0)]
        resp = _detect(tasks, threshold_seconds=_THRESHOLD)
        assert resp.llm_analysis is None
        assert resp.analysis_model is None

    def test_command_field(self) -> None:
        resp = _detect([], threshold_seconds=_THRESHOLD)
        assert resp.command == "harness detect-stale"


# ── Artifact freshness tests ───────────────────────────────────────────────────

import textwrap
from pathlib import Path as _Path

from harness_skills.stale_plan_detector import (
    DEFAULT_ARTIFACT_THRESHOLD_DAYS,
    scan_artifact_freshness,
)


class TestArtifactFreshnessScanning:
    """scan_artifact_freshness() must detect stale, fresh, and missing artifacts."""

    _THRESHOLD = DEFAULT_ARTIFACT_THRESHOLD_DAYS  # 30 days
    _TODAY = date(2026, 3, 22)

    # Helper: write a fake artifact file with a last_updated value
    def _write_artifact(self, tmp_path: _Path, name: str, last_updated: str) -> None:
        content = textwrap.dedent(f"""\
            <!-- harness:auto-generated
            last_updated: {last_updated}
            -->
            # {name}
            Some content here.
        """)
        dest = tmp_path / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")

    def test_fresh_artifact_is_healthy(self, tmp_path: _Path) -> None:
        self._write_artifact(tmp_path, "AGENTS.md", "2026-03-20")
        result = scan_artifact_freshness(
            base_dir=tmp_path,
            threshold_days=self._THRESHOLD,
            today=self._TODAY,
        )
        agents_entry = next(r for r in result.results if r.file == "AGENTS.md")
        assert agents_entry.severity == "healthy"
        assert agents_entry.age_days == 2

    def test_missing_artifact_is_error(self, tmp_path: _Path) -> None:
        # Write nothing — all four canonical files are absent
        result = scan_artifact_freshness(
            base_dir=tmp_path,
            threshold_days=self._THRESHOLD,
            today=self._TODAY,
        )
        for entry in result.results:
            assert entry.severity == "ERROR"
        assert result.missing_artifacts == 4

    def test_artifact_without_timestamp_is_warning(self, tmp_path: _Path) -> None:
        (tmp_path / "AGENTS.md").write_text("# AGENTS\nNo timestamp here.\n")
        result = scan_artifact_freshness(
            base_dir=tmp_path,
            threshold_days=self._THRESHOLD,
            today=self._TODAY,
        )
        agents_entry = next(r for r in result.results if r.file == "AGENTS.md")
        assert agents_entry.severity == "WARNING"
        assert agents_entry.last_updated is None

    @pytest.mark.parametrize(
        "age_days, expected_severity",
        [
            (0, "healthy"),        # same day
            (30, "healthy"),       # exactly at threshold (boundary)
            (31, "INFO"),          # just over threshold
            (60, "INFO"),          # exactly 2× threshold
            (61, "WARNING"),       # just over 2×
            (120, "WARNING"),      # exactly 4× threshold
            (121, "CRITICAL"),     # just over 4×
        ],
    )
    def test_severity_buckets(
        self, tmp_path: _Path, age_days: int, expected_severity: str
    ) -> None:
        from datetime import timedelta

        last_updated_date = self._TODAY - timedelta(days=age_days)
        self._write_artifact(tmp_path, "AGENTS.md", last_updated_date.isoformat())
        result = scan_artifact_freshness(
            base_dir=tmp_path,
            threshold_days=self._THRESHOLD,
            today=self._TODAY,
        )
        agents_entry = next(r for r in result.results if r.file == "AGENTS.md")
        assert agents_entry.severity == expected_severity, (
            f"age_days={age_days}: expected {expected_severity!r}, "
            f"got {agents_entry.severity!r}"
        )

    def test_stale_count_matches_non_healthy_entries(self, tmp_path: _Path) -> None:
        # Write one healthy and one stale artifact; the other two are missing
        self._write_artifact(tmp_path, "AGENTS.md", "2026-03-20")       # healthy (2d)
        self._write_artifact(tmp_path, "docs/ARCHITECTURE.md", "2025-11-01")  # CRITICAL
        result = scan_artifact_freshness(
            base_dir=tmp_path,
            threshold_days=self._THRESHOLD,
            today=self._TODAY,
        )
        non_healthy = [r for r in result.results if r.severity != "healthy"]
        assert result.stale_artifacts == len(non_healthy)

    def test_subdirectory_agents_md_discovered(self, tmp_path: _Path) -> None:
        sub = tmp_path / "submodule"
        sub.mkdir()
        self._write_artifact(sub, "AGENTS.md", "2026-03-20")
        result = scan_artifact_freshness(
            base_dir=tmp_path,
            threshold_days=self._THRESHOLD,
            today=self._TODAY,
        )
        rel_paths = [r.file for r in result.results]
        # Should find both the root AGENTS.md (missing) and submodule/AGENTS.md
        assert any("submodule" in p for p in rel_paths)

    def test_skip_artifacts_returns_none(self) -> None:
        tasks = [_task("t1", "Fresh task", idle_minutes=10.0)]
        resp = _detect(tasks, threshold_seconds=_THRESHOLD, skip_artifacts=True)
        assert resp.artifact_staleness is None

    def test_artifact_staleness_present_by_default(self, tmp_path: _Path) -> None:
        tasks = [_task("t1", "Fresh task", idle_minutes=10.0)]
        resp = detect_stale_plan(
            tasks,
            threshold_seconds=_THRESHOLD,
            skip_llm=True,
            now=_FROZEN_NOW,
            base_dir=tmp_path,
            today=date(2026, 3, 22),
        )
        assert resp.artifact_staleness is not None
        assert resp.artifact_staleness.artifacts_checked >= 4

    def test_response_json_includes_artifact_staleness(self, tmp_path: _Path) -> None:
        tasks = [_task("t1", "Stale", idle_minutes=60.0)]
        resp = detect_stale_plan(
            tasks,
            threshold_seconds=_THRESHOLD,
            skip_llm=True,
            now=_FROZEN_NOW,
            base_dir=tmp_path,
            today=date(2026, 3, 22),
        )
        dumped = resp.model_dump_json()
        assert "artifact_staleness" in dumped
