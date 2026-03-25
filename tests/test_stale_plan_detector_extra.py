"""Additional tests for harness_skills.stale_plan_detector — covering uncovered lines.

Targets: _extract_last_updated OSError, unparseable dates, _build_task_lines,
_stream_llm_analysis, CLI entry point, skipped dirs in artifact scan.
"""

from __future__ import annotations

import json
import textwrap
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from harness_skills.models.base import Severity, Status
from harness_skills.stale_plan_detector import (
    PlanTask,
    _artifact_severity,
    _build_task_lines,
    _extract_last_updated,
    _severity_for_idle,
    cli,
    detect_stale_plan,
    scan_artifact_freshness,
)
from harness_skills.models.stale import StaleTask


_FROZEN_NOW = datetime(2026, 3, 14, 12, 0, 0, tzinfo=timezone.utc)
_THRESHOLD = 1800.0


def _task(task_id, title, status="in_progress", idle_minutes=0.0, agent=None):
    return PlanTask(
        task_id=task_id,
        title=title,
        status=status,
        assigned_agent=agent,
        last_updated=_FROZEN_NOW - timedelta(minutes=idle_minutes),
    )


# ── _extract_last_updated ───────────────────────────────────────────────────


class TestExtractLastUpdated:
    def test_returns_none_on_os_error(self, tmp_path):
        # Non-existent file
        result = _extract_last_updated(tmp_path / "nonexistent.md")
        assert result is None

    def test_returns_none_when_no_match(self, tmp_path):
        f = tmp_path / "no_date.md"
        f.write_text("# Title\nNo date here.\n")
        assert _extract_last_updated(f) is None

    def test_extracts_last_updated(self, tmp_path):
        f = tmp_path / "dated.md"
        f.write_text("last_updated: 2026-03-01\n# Title\n")
        assert _extract_last_updated(f) == "2026-03-01"


# ── _artifact_severity ──────────────────────────────────────────────────────


class TestArtifactSeverity:
    def test_healthy(self):
        assert _artifact_severity(10, 30) == "healthy"

    def test_info(self):
        assert _artifact_severity(31, 30) == "INFO"

    def test_warning(self):
        assert _artifact_severity(61, 30) == "WARNING"

    def test_critical(self):
        assert _artifact_severity(121, 30) == "CRITICAL"


# ── _build_task_lines ────────────────────────────────────────────────────────


class TestBuildTaskLines:
    def test_formats_stale_tasks(self):
        tasks = [
            StaleTask(
                task_id="t1", title="Task 1", status="in_progress",
                assigned_agent="agent-a",
                last_updated=_FROZEN_NOW - timedelta(hours=2),
                idle_seconds=7200.0, threshold_seconds=1800.0,
                severity=Severity.WARNING,
            ),
            StaleTask(
                task_id="t2", title="Task 2", status="blocked",
                assigned_agent=None,
                last_updated=_FROZEN_NOW - timedelta(hours=5),
                idle_seconds=18000.0, threshold_seconds=1800.0,
                severity=Severity.CRITICAL,
            ),
        ]
        lines = _build_task_lines(tasks)
        assert "t1" in lines
        assert "t2" in lines
        assert "agent=agent-a" in lines
        assert "unassigned" in lines
        # Most idle first
        assert lines.index("t2") < lines.index("t1")

    def test_empty_list(self):
        assert _build_task_lines([]) == ""


# ── Artifact scan: unparseable date ─────────────────────────────────────────


class TestArtifactUnparseableDate:
    def test_unparseable_date_is_warning(self, tmp_path):
        f = tmp_path / "AGENTS.md"
        f.write_text("last_updated: not-a-date\n")
        result = scan_artifact_freshness(
            base_dir=tmp_path,
            threshold_days=30,
            today=date(2026, 3, 22),
        )
        agents = next(r for r in result.results if r.file == "AGENTS.md")
        assert agents.severity == "WARNING"
        assert agents.last_updated == "not-a-date"
        assert agents.age_days is None


# ── Artifact scan: skip hidden dirs ─────────────────────────────────────────


class TestArtifactSkipDirs:
    def test_skips_hidden_dirs(self, tmp_path):
        # Put an AGENTS.md in .git which should be skipped
        hidden = tmp_path / ".git" / "AGENTS.md"
        hidden.parent.mkdir(parents=True)
        hidden.write_text("last_updated: 2026-03-20\n")
        result = scan_artifact_freshness(
            base_dir=tmp_path,
            threshold_days=30,
            today=date(2026, 3, 22),
        )
        files = [r.file for r in result.results]
        assert not any(".git" in f for f in files)

    def test_skips_node_modules(self, tmp_path):
        nm = tmp_path / "node_modules" / "AGENTS.md"
        nm.parent.mkdir(parents=True)
        nm.write_text("last_updated: 2026-03-20\n")
        result = scan_artifact_freshness(
            base_dir=tmp_path,
            threshold_days=30,
            today=date(2026, 3, 22),
        )
        files = [r.file for r in result.results]
        assert not any("node_modules" in f for f in files)


# ── detect_stale_plan: naive timestamp handling ─────────────────────────────


class TestNaiveTimestamp:
    def test_naive_timestamp_treated_as_utc(self):
        task = PlanTask(
            task_id="t1",
            title="Naive task",
            status="in_progress",
            last_updated=datetime(2026, 3, 14, 11, 0, 0),  # naive
        )
        resp = detect_stale_plan(
            [task],
            threshold_seconds=_THRESHOLD,
            skip_llm=True,
            now=_FROZEN_NOW,
            skip_artifacts=True,
        )
        # 60 minutes idle → stale
        assert resp.summary.stale_tasks == 1


# ── detect_stale_plan: LLM integration (mocked) ─────────────────────────────


class TestStreamLlmAnalysis:
    def test_stream_llm_analysis(self):
        from harness_skills.stale_plan_detector import _stream_llm_analysis
        from harness_skills.models.stale import StalePlanSummary, StaleTask

        stale_tasks = [
            StaleTask(
                task_id="t1", title="Stale task", status="in_progress",
                assigned_agent="agent-a",
                last_updated=_FROZEN_NOW - timedelta(hours=2),
                idle_seconds=7200.0, threshold_seconds=1800.0,
                severity=Severity.WARNING,
            )
        ]
        summary = StalePlanSummary(
            plan_id="test-plan", total_tasks=1, stale_tasks=1,
            healthy_tasks=0, threshold_seconds=1800.0,
            overall_health="degraded",
        )

        # Mock the client and streaming
        mock_delta = MagicMock()
        mock_delta.type = "text_delta"
        mock_delta.text = "Analysis text"

        mock_event = MagicMock()
        mock_event.type = "content_block_delta"
        mock_event.delta = mock_delta

        mock_stream = MagicMock()
        mock_stream.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream.__exit__ = MagicMock(return_value=False)
        mock_stream.__iter__ = MagicMock(return_value=iter([mock_event]))

        mock_client = MagicMock()
        mock_client.messages.stream.return_value = mock_stream

        result = _stream_llm_analysis(stale_tasks, summary, mock_client, "test-model")
        assert "Analysis text" in result


class TestLLMAnalysis:
    def test_no_api_key_skips_llm(self):
        task = _task("t1", "Stale", idle_minutes=60)
        with patch.dict("os.environ", {}, clear=True):
            resp = detect_stale_plan(
                [task],
                threshold_seconds=_THRESHOLD,
                skip_llm=False,
                now=_FROZEN_NOW,
                api_key=None,
                skip_artifacts=True,
            )
        assert resp.llm_analysis is None

    def test_api_error_handled_gracefully(self):
        import anthropic

        task = _task("t1", "Stale", idle_minutes=60)
        mock_client = MagicMock()
        mock_client.messages.stream.side_effect = anthropic.APIError(
            message="rate limit",
            request=MagicMock(),
            body=None,
        )

        with patch("harness_skills.stale_plan_detector.anthropic.Anthropic",
                    return_value=mock_client):
            resp = detect_stale_plan(
                [task],
                threshold_seconds=_THRESHOLD,
                skip_llm=False,
                now=_FROZEN_NOW,
                api_key="sk-test-key",
                skip_artifacts=True,
            )
        assert resp.llm_analysis is None


# ── CLI ──────────────────────────────────────────────────────────────────────


class TestCLI:
    def test_valid_plan_no_stale(self, tmp_path):
        plan = [
            {
                "task_id": "t1",
                "title": "Fresh",
                "status": "in_progress",
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
        ]
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--plan-file", str(plan_file),
            "--skip-llm",
            "--skip-artifacts",
        ])
        assert result.exit_code == 0

    def test_stale_plan_exits_1(self, tmp_path):
        old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        plan = [
            {
                "task_id": "t1",
                "title": "Stale",
                "status": "in_progress",
                "last_updated": old,
            }
        ]
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--plan-file", str(plan_file),
            "--skip-llm",
            "--skip-artifacts",
        ])
        assert result.exit_code == 1

    def test_invalid_json_exits_2(self, tmp_path):
        plan_file = tmp_path / "bad.json"
        plan_file.write_text("{not json")

        runner = CliRunner()
        result = runner.invoke(cli, ["--plan-file", str(plan_file)])
        assert result.exit_code == 2

    def test_non_array_json_exits_2(self, tmp_path):
        plan_file = tmp_path / "obj.json"
        plan_file.write_text('{"not": "array"}')

        runner = CliRunner()
        result = runner.invoke(cli, ["--plan-file", str(plan_file)])
        assert result.exit_code == 2

    def test_invalid_task_object_exits_2(self, tmp_path):
        plan_file = tmp_path / "bad_task.json"
        plan_file.write_text('[{"bad_field": true}]')

        runner = CliRunner()
        result = runner.invoke(cli, ["--plan-file", str(plan_file)])
        assert result.exit_code == 2

    def test_pretty_output(self, tmp_path):
        plan = [
            {
                "task_id": "t1",
                "title": "Fresh",
                "status": "in_progress",
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
        ]
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--plan-file", str(plan_file),
            "--skip-llm",
            "--skip-artifacts",
            "--pretty",
        ])
        assert result.exit_code == 0
        # Pretty output has indentation
        assert "  " in result.output
