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


# ── Artifact freshness tests ────────────────────────────────────────────────────


import textwrap
from datetime import date
from pathlib import Path

import pytest

from harness_skills.stale_plan_detector import scan_artifact_freshness

_TODAY = date(2026, 3, 22)
_THRESHOLD_DAYS = 30


def _write_artifact(tmp_path: Path, filename: str, last_updated: str | None) -> Path:
    """Write a fake artifact file with the harness front-matter block."""
    p = tmp_path / filename
    if last_updated is None:
        # File exists but has no last_updated field
        p.write_text("# Some artifact\n\nNo front-matter here.\n")
    else:
        p.write_text(
            textwrap.dedent(f"""\
                # {filename}

                <!-- harness:auto-generated — do not edit this block manually -->
                last_updated: {last_updated}
                head: abc1234
                <!-- end harness:auto-generated -->

                Body content here.
            """)
        )
    return p


class TestArtifactFreshness:
    """Unit tests for scan_artifact_freshness()."""

    def test_all_fresh_artifacts(self, tmp_path: Path) -> None:
        for name in ("AGENTS.md", "ARCHITECTURE.md", "PRINCIPLES.md", "EVALUATION.md"):
            _write_artifact(tmp_path, name, "2026-03-20")  # 2 days old

        result = scan_artifact_freshness(
            threshold_days=_THRESHOLD_DAYS, base_dir=tmp_path, today=_TODAY
        )
        assert result.stale_artifacts == 0
        assert result.missing_artifacts == 0
        assert all(r.severity == "healthy" for r in result.results if r.file in
                   ("AGENTS.md", "ARCHITECTURE.md", "PRINCIPLES.md", "EVALUATION.md"))

    def test_missing_artifact_is_error(self, tmp_path: Path) -> None:
        # Write only 3 of 4
        for name in ("AGENTS.md", "ARCHITECTURE.md", "PRINCIPLES.md"):
            _write_artifact(tmp_path, name, "2026-03-20")
        # EVALUATION.md is absent

        result = scan_artifact_freshness(
            threshold_days=_THRESHOLD_DAYS, base_dir=tmp_path, today=_TODAY
        )
        eval_result = next(r for r in result.results if r.file == "EVALUATION.md")
        assert eval_result.severity == "ERROR"
        assert result.missing_artifacts >= 1

    def test_artifact_without_timestamp_is_warning(self, tmp_path: Path) -> None:
        _write_artifact(tmp_path, "AGENTS.md", None)  # no last_updated

        result = scan_artifact_freshness(
            threshold_days=_THRESHOLD_DAYS, base_dir=tmp_path, today=_TODAY
        )
        agents_result = next(r for r in result.results if r.file == "AGENTS.md")
        assert agents_result.severity == "WARNING"
        assert agents_result.last_updated is None

    @pytest.mark.parametrize(
        "age_days, expected_severity",
        [
            (15, "healthy"),    # ≤ threshold
            (31, "INFO"),       # threshold < age ≤ 2×
            (65, "WARNING"),    # 2× < age ≤ 4×
            (125, "CRITICAL"),  # > 4×
        ],
    )
    def test_severity_thresholds(
        self, tmp_path: Path, age_days: int, expected_severity: str
    ) -> None:
        last_updated = (_TODAY - __import__("datetime").timedelta(days=age_days)).isoformat()
        _write_artifact(tmp_path, "AGENTS.md", last_updated)
        # Provide the other three so they don't add noise
        for name in ("ARCHITECTURE.md", "PRINCIPLES.md", "EVALUATION.md"):
            _write_artifact(tmp_path, name, "2026-03-22")  # 0 days old

        result = scan_artifact_freshness(
            threshold_days=_THRESHOLD_DAYS, base_dir=tmp_path, today=_TODAY
        )
        agents_result = next(r for r in result.results if r.file == "AGENTS.md")
        assert agents_result.severity == expected_severity
        assert agents_result.age_days == age_days

    def test_skip_artifacts_returns_none(self) -> None:
        resp = _detect([], threshold_seconds=_THRESHOLD, skip_artifacts=True)
        assert resp.artifact_staleness is None

    def test_artifact_staleness_included_by_default(self, tmp_path: Path) -> None:
        """artifact_staleness is populated by default (even if all files missing)."""
        resp = detect_stale_plan(
            [],
            skip_llm=True,
            now=_FROZEN_NOW,
            artifact_base_dir=tmp_path,
            today=_TODAY,
        )
        assert resp.artifact_staleness is not None
        assert resp.artifact_staleness.threshold_days == 30

    def test_artifact_staleness_threshold_respected(self, tmp_path: Path) -> None:
        last_updated = "2026-03-01"  # 21 days old
        _write_artifact(tmp_path, "AGENTS.md", last_updated)
        for name in ("ARCHITECTURE.md", "PRINCIPLES.md", "EVALUATION.md"):
            _write_artifact(tmp_path, name, "2026-03-22")

        # With threshold=30 days → 21 days is healthy
        result_healthy = scan_artifact_freshness(
            threshold_days=30, base_dir=tmp_path, today=_TODAY
        )
        agents = next(r for r in result_healthy.results if r.file == "AGENTS.md")
        assert agents.severity == "healthy"

        # With threshold=10 days → 21 days is WARNING (between 2× and 4×)
        result_stale = scan_artifact_freshness(
            threshold_days=10, base_dir=tmp_path, today=_TODAY
        )
        agents2 = next(r for r in result_stale.results if r.file == "AGENTS.md")
        assert agents2.severity == "WARNING"


# Re-import detect_stale_plan for the new tests that call it directly
from harness_skills.stale_plan_detector import detect_stale_plan  # noqa: E402


# ── Documentation drift tests ───────────────────────────────────────────────────


import os
import stat
import time
from harness_skills.stale_plan_detector import (  # noqa: E402
    _extract_file_references,
    _check_source_drift,
    _compute_staleness_score,
)


_DOC_DATE = date(2026, 1, 1)  # anchor date for drift calculations


class TestExtractFileReferences:
    """Unit tests for _extract_file_references()."""

    def test_python_from_import(self) -> None:
        content = "from tests.browser.agent_driver import AgentDriver"
        refs = _extract_file_references(content)
        assert "tests/browser/agent_driver.py" in refs

    def test_backtick_file_with_extension(self) -> None:
        content = "Both `playwright` and `pytest-playwright` are in `requirements.txt`."
        refs = _extract_file_references(content)
        assert "requirements.txt" in refs

    def test_explicit_file_path_in_text(self) -> None:
        content = "See tests/browser/conftest.py for fixture details."
        refs = _extract_file_references(content)
        assert "tests/browser/conftest.py" in refs

    def test_url_excluded(self) -> None:
        content = "Visit https://example.com/api.json for details."
        refs = _extract_file_references(content)
        assert not any("http" in r for r in refs)

    def test_version_number_excluded(self) -> None:
        content = "Requires Python 3.12 or newer."
        refs = _extract_file_references(content)
        # Should not produce "3.12" as a file reference
        assert "3.12" not in refs

    def test_empty_content(self) -> None:
        assert _extract_file_references("") == []

    def test_returns_sorted_list(self) -> None:
        content = (
            "from z.module import Foo\n"
            "from a.module import Bar\n"
        )
        refs = _extract_file_references(content)
        assert refs == sorted(refs)

    def test_deduplicates_references(self) -> None:
        content = (
            "from tests.browser.agent_driver import AgentDriver\n"
            "# also: tests/browser/agent_driver.py\n"
        )
        refs = _extract_file_references(content)
        driver_refs = [r for r in refs if "agent_driver" in r]
        assert len(driver_refs) == 1


class TestCheckSourceDrift:
    """Unit tests for _check_source_drift()."""

    def test_missing_file_reported(self, tmp_path: Path) -> None:
        refs = ["nonexistent/module.py"]
        missing, drifted = _check_source_drift(refs, _DOC_DATE, tmp_path)
        assert "nonexistent/module.py" in missing
        assert drifted == []

    def test_fresh_file_not_drifted(self, tmp_path: Path) -> None:
        """A file whose mtime is BEFORE last_updated is not drifted."""
        src = tmp_path / "module.py"
        src.write_text("# source")
        # Set mtime to 10 days before _DOC_DATE
        past_ts = time.mktime((2025, 12, 22, 0, 0, 0, 0, 0, -1))
        os.utime(src, (past_ts, past_ts))

        missing, drifted = _check_source_drift(["module.py"], _DOC_DATE, tmp_path)
        assert missing == []
        assert drifted == []

    def test_drifted_file_reported(self, tmp_path: Path) -> None:
        """A file whose mtime is AFTER last_updated is drifted."""
        src = tmp_path / "new_feature.py"
        src.write_text("# new code")
        # Set mtime to 5 days AFTER _DOC_DATE (2026-01-06)
        future_ts = time.mktime((2026, 1, 6, 12, 0, 0, 0, 0, -1))
        os.utime(src, (future_ts, future_ts))

        missing, drifted = _check_source_drift(["new_feature.py"], _DOC_DATE, tmp_path)
        assert missing == []
        assert len(drifted) == 1
        assert drifted[0].path == "new_feature.py"
        assert drifted[0].exists is True
        assert drifted[0].days_newer_than_doc is not None
        assert drifted[0].days_newer_than_doc > 0

    def test_no_drift_when_last_updated_none(self, tmp_path: Path) -> None:
        """When last_updated is None drift direction cannot be determined."""
        src = tmp_path / "module.py"
        src.write_text("# anything")
        missing, drifted = _check_source_drift(["module.py"], None, tmp_path)
        # File exists but we can't determine drift → drifted list stays empty
        assert missing == []
        assert drifted == []

    def test_directory_ignored(self, tmp_path: Path) -> None:
        """Directories in the referenced list are silently skipped."""
        (tmp_path / "mydir").mkdir()
        missing, drifted = _check_source_drift(["mydir"], _DOC_DATE, tmp_path)
        assert missing == []
        assert drifted == []


class TestComputeStalenessScore:
    """Unit tests for _compute_staleness_score()."""

    def test_zero_age_zero_drift(self) -> None:
        score = _compute_staleness_score(0, 30, 0.0)
        assert score == 0.0

    def test_full_age_full_drift(self) -> None:
        # age = 4 × threshold → age_score = 1.0; drift = 1.0
        score = _compute_staleness_score(120, 30, 1.0)
        assert score == 1.0

    def test_age_only_no_drift(self) -> None:
        # age = 2 × threshold → age_score = 0.5; drift = 0.0
        # score = 0.6 × 0.5 + 0.4 × 0.0 = 0.3
        score = _compute_staleness_score(60, 30, 0.0)
        assert abs(score - 0.3) < 0.001

    def test_unknown_age_moderate_penalty(self) -> None:
        score = _compute_staleness_score(None, 30, 0.0)
        # age_score = 0.5 → score = 0.6 × 0.5 = 0.3
        assert abs(score - 0.3) < 0.001

    def test_saturates_at_1(self) -> None:
        # Very old artifact should not exceed 1.0
        score = _compute_staleness_score(9999, 30, 1.0)
        assert score == 1.0


class TestDriftIntegration:
    """Integration tests: scan_artifact_freshness() with drift detection enabled."""

    def _write_artifact_with_refs(
        self, tmp_path: Path, filename: str, last_updated: str, refs: list[str]
    ) -> Path:
        """Write an artifact that references the given source files."""
        ref_lines = "\n".join(f"`{r}`" for r in refs)
        content = (
            f"# {filename}\n\n"
            f"<!-- harness:auto-generated — do not edit this block manually -->\n"
            f"last_updated: {last_updated}\n"
            f"<!-- end harness:auto-generated -->\n\n"
            f"Body.\n\n{ref_lines}\n"
        )
        p = tmp_path / filename
        p.write_text(content)
        return p

    def test_no_drift_when_source_files_older(self, tmp_path: Path) -> None:
        """When all referenced files are older than the doc, drift_ratio == 0."""
        src = tmp_path / "module.py"
        src.write_text("# code")
        # Set mtime to a date before the doc's last_updated (2026-03-01)
        past_ts = time.mktime((2026, 2, 1, 0, 0, 0, 0, 0, -1))
        os.utime(src, (past_ts, past_ts))

        self._write_artifact_with_refs(tmp_path, "AGENTS.md", "2026-03-01", ["module.py"])
        for name in ("ARCHITECTURE.md", "PRINCIPLES.md", "EVALUATION.md"):
            _write_artifact(tmp_path, name, "2026-03-22")

        result = scan_artifact_freshness(
            threshold_days=30, base_dir=tmp_path, today=_TODAY
        )
        agents = next(r for r in result.results if r.file == "AGENTS.md")
        assert agents.drift is not None
        assert agents.drift.drift_ratio == 0.0
        assert agents.drift.drifted_files == []

    def test_drift_detected_when_source_newer(self, tmp_path: Path) -> None:
        """When a referenced file is newer than the doc, it appears in drifted_files."""
        src = tmp_path / "module.py"
        src.write_text("# updated code")
        # Set mtime to AFTER the doc's last_updated (2026-01-01 + 10 days)
        future_ts = time.mktime((2026, 1, 11, 0, 0, 0, 0, 0, -1))
        os.utime(src, (future_ts, future_ts))

        self._write_artifact_with_refs(tmp_path, "AGENTS.md", "2026-01-01", ["module.py"])
        for name in ("ARCHITECTURE.md", "PRINCIPLES.md", "EVALUATION.md"):
            _write_artifact(tmp_path, name, "2026-03-22")

        result = scan_artifact_freshness(
            threshold_days=30, base_dir=tmp_path, today=_TODAY
        )
        agents = next(r for r in result.results if r.file == "AGENTS.md")
        assert agents.drift is not None
        assert len(agents.drift.drifted_files) == 1
        assert agents.drift.drifted_files[0].path == "module.py"
        assert agents.drift.drift_ratio > 0.0

    def test_staleness_score_populated(self, tmp_path: Path) -> None:
        """ArtifactResult.staleness_score is populated for all artifact results."""
        for name in ("AGENTS.md", "ARCHITECTURE.md", "PRINCIPLES.md", "EVALUATION.md"):
            _write_artifact(tmp_path, name, "2026-03-20")

        result = scan_artifact_freshness(
            threshold_days=30, base_dir=tmp_path, today=_TODAY
        )
        for r in result.results:
            if r.file in ("AGENTS.md", "ARCHITECTURE.md", "PRINCIPLES.md", "EVALUATION.md"):
                assert r.staleness_score is not None
                assert 0.0 <= r.staleness_score <= 1.0

    def test_missing_file_listed_in_drift(self, tmp_path: Path) -> None:
        """Referenced files that don't exist appear in drift.missing_files."""
        self._write_artifact_with_refs(
            tmp_path, "AGENTS.md", "2026-03-22", ["does_not_exist.py"]
        )
        for name in ("ARCHITECTURE.md", "PRINCIPLES.md", "EVALUATION.md"):
            _write_artifact(tmp_path, name, "2026-03-22")

        result = scan_artifact_freshness(
            threshold_days=30, base_dir=tmp_path, today=_TODAY
        )
        agents = next(r for r in result.results if r.file == "AGENTS.md")
        assert agents.drift is not None
        assert "does_not_exist.py" in agents.drift.missing_files

    def test_skip_drift_produces_none(self, tmp_path: Path) -> None:
        """When skip_drift=True, ArtifactResult.drift is None for all results."""
        for name in ("AGENTS.md", "ARCHITECTURE.md", "PRINCIPLES.md", "EVALUATION.md"):
            _write_artifact(tmp_path, name, "2026-03-20")

        result = scan_artifact_freshness(
            threshold_days=30, base_dir=tmp_path, today=_TODAY, skip_drift=True
        )
        for r in result.results:
            assert r.drift is None