"""Tests for ``harness completion-report``.

Covers:
    - JSON / YAML / table output formats
    - Non-TTY auto-detection defaults to JSON
    - Completed tasks are captured correctly
    - Technical debt items are identified (skipped tasks + note keywords)
    - ``--min-debt-severity`` filter works
    - Follow-up items are generated for blocked / pending / skipped tasks
    - ``--plan-id`` filter restricts output to the specified plan
    - Missing plan data → exit 1
    - Corrupt plan file → exit 2
    - Schema: ``PlanCompletionReport.model_validate_json`` round-trips cleanly
"""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

import pytest
import yaml
from click.testing import CliRunner

from harness_skills.cli.main import cli
from harness_skills.models.completion import PlanCompletionReport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _write_plan(tmp_path: Path, name: str, data: dict) -> Path:
    p = tmp_path / name
    p.write_text(yaml.dump(data), encoding="utf-8")
    return p


def _simple_plan(
    plan_id: str = "PLAN-001",
    title: str = "Test Plan",
    status: str = "done",
    tasks: list[dict] | None = None,
) -> dict:
    """Return a minimal plan dict with sensible defaults."""
    if tasks is None:
        tasks = [
            {
                "id": "TASK-001",
                "title": "Scaffold module",
                "status": "done",
                "priority": "high",
                "assigned_agent": "agent-alpha",
                "started_at": "2026-03-20T08:00:00Z",
                "completed_at": "2026-03-20T09:00:00Z",
            }
        ]
    return {
        "plan": {"id": plan_id, "title": title, "status": status},
        "tasks": tasks,
    }


def _invoke(runner: CliRunner, extra_args: list[str]) -> "Result":  # type: ignore[name-defined]
    return runner.invoke(
        cli,
        ["completion-report", "--no-state-service"] + extra_args,
    )


# ---------------------------------------------------------------------------
# Output-format tests
# ---------------------------------------------------------------------------


class TestOutputFormats:
    def test_json_produces_parseable_output(self, runner, tmp_path):
        plan = _write_plan(tmp_path, "plan.yaml", _simple_plan())
        result = _invoke(runner, ["--plan-file", str(plan), "--output-format", "json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "summary" in data
        assert "completed_tasks" in data
        assert "debt" in data
        assert "follow_up" in data

    def test_yaml_produces_parseable_output(self, runner, tmp_path):
        plan = _write_plan(tmp_path, "plan.yaml", _simple_plan())
        result = _invoke(runner, ["--plan-file", str(plan), "--output-format", "yaml"])
        assert result.exit_code == 0, result.output
        data = yaml.safe_load(result.output)
        assert "summary" in data
        assert "completed_tasks" in data

    def test_table_produces_human_readable(self, runner, tmp_path):
        plan = _write_plan(tmp_path, "plan.yaml", _simple_plan())
        result = _invoke(runner, ["--plan-file", str(plan), "--output-format", "table"])
        assert result.exit_code == 0, result.output
        # Table output is NOT valid JSON
        with pytest.raises((json.JSONDecodeError, ValueError)):
            json.loads(result.output)
        # Should contain some human-readable content
        assert "completion" in result.output.lower() or "plan" in result.output.lower()

    def test_non_tty_defaults_to_json(self, runner, tmp_path):
        """CliRunner stdout is not a TTY — default should be json."""
        plan = _write_plan(tmp_path, "plan.yaml", _simple_plan())
        result = _invoke(runner, ["--plan-file", str(plan)])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "summary" in data

    def test_invalid_format_rejected(self, runner, tmp_path):
        plan = _write_plan(tmp_path, "plan.yaml", _simple_plan())
        result = _invoke(
            runner, ["--plan-file", str(plan), "--output-format", "xml"]
        )
        assert result.exit_code != 0

    def test_json_schema_round_trips(self, runner, tmp_path):
        """JSON output should parse cleanly into ``PlanCompletionReport``."""
        plan = _write_plan(tmp_path, "plan.yaml", _simple_plan())
        result = _invoke(runner, ["--plan-file", str(plan), "--output-format", "json"])
        assert result.exit_code == 0, result.output
        report = PlanCompletionReport.model_validate_json(result.output)
        assert report.command == "harness completion-report"
        assert report.summary.total_plans == 1


# ---------------------------------------------------------------------------
# Completed tasks
# ---------------------------------------------------------------------------


class TestCompletedTasks:
    def test_done_task_appears_in_completed_tasks(self, runner, tmp_path):
        plan = _write_plan(tmp_path, "plan.yaml", _simple_plan())
        result = _invoke(runner, ["--plan-file", str(plan), "--output-format", "json"])
        data = json.loads(result.output)
        assert len(data["completed_tasks"]) == 1
        ct = data["completed_tasks"][0]
        assert ct["task_id"] == "TASK-001"
        assert ct["plan_id"] == "PLAN-001"
        assert ct["assigned_agent"] == "agent-alpha"

    def test_duration_computed_when_timestamps_present(self, runner, tmp_path):
        plan = _write_plan(tmp_path, "plan.yaml", _simple_plan())
        result = _invoke(runner, ["--plan-file", str(plan), "--output-format", "json"])
        data = json.loads(result.output)
        ct = data["completed_tasks"][0]
        # 08:00 → 09:00 = 60 minutes
        assert ct["duration_min"] == 60.0

    def test_duration_null_when_timestamps_absent(self, runner, tmp_path):
        plan_data = _simple_plan(
            tasks=[{"id": "T1", "title": "No timestamps", "status": "done"}]
        )
        plan = _write_plan(tmp_path, "plan.yaml", plan_data)
        result = _invoke(runner, ["--plan-file", str(plan), "--output-format", "json"])
        data = json.loads(result.output)
        ct = data["completed_tasks"][0]
        assert ct["duration_min"] is None

    def test_non_done_tasks_not_in_completed(self, runner, tmp_path):
        plan_data = _simple_plan(
            tasks=[
                {"id": "T1", "title": "Done task", "status": "done"},
                {"id": "T2", "title": "Pending task", "status": "pending"},
                {"id": "T3", "title": "Blocked task", "status": "blocked"},
            ]
        )
        plan = _write_plan(tmp_path, "plan.yaml", plan_data)
        result = _invoke(runner, ["--plan-file", str(plan), "--output-format", "json"])
        data = json.loads(result.output)
        completed_ids = {ct["task_id"] for ct in data["completed_tasks"]}
        assert "T1" in completed_ids
        assert "T2" not in completed_ids
        assert "T3" not in completed_ids


# ---------------------------------------------------------------------------
# Technical debt detection
# ---------------------------------------------------------------------------


class TestDebtDetection:
    def test_skipped_task_generates_debt(self, runner, tmp_path):
        plan_data = _simple_plan(
            tasks=[{"id": "T1", "title": "Skipped work", "status": "skipped"}]
        )
        plan = _write_plan(tmp_path, "plan.yaml", plan_data)
        result = _invoke(runner, ["--plan-file", str(plan), "--output-format", "json"])
        data = json.loads(result.output)
        assert len(data["debt"]) >= 1
        assert any(d["source_task_id"] == "T1" for d in data["debt"])

    def test_todo_note_generates_debt(self, runner, tmp_path):
        plan_data = _simple_plan(
            tasks=[
                {
                    "id": "T1",
                    "title": "Auth flow",
                    "status": "done",
                    "notes": "TODO: revisit token expiry logic",
                }
            ]
        )
        plan = _write_plan(tmp_path, "plan.yaml", plan_data)
        result = _invoke(runner, ["--plan-file", str(plan), "--output-format", "json"])
        data = json.loads(result.output)
        assert any(d["source_task_id"] == "T1" for d in data["debt"])
        assert any("TODO" in d["description"] for d in data["debt"])

    def test_fixme_note_generates_debt(self, runner, tmp_path):
        plan_data = _simple_plan(
            tasks=[
                {"id": "T1", "title": "DB index", "status": "done", "notes": "FIXME slow query"}
            ]
        )
        plan = _write_plan(tmp_path, "plan.yaml", plan_data)
        result = _invoke(runner, ["--plan-file", str(plan), "--output-format", "json"])
        data = json.loads(result.output)
        assert any("FIXME" in d["description"] for d in data["debt"])

    def test_hack_keyword_generates_debt(self, runner, tmp_path):
        plan_data = _simple_plan(
            tasks=[
                {"id": "T1", "title": "Hotfix", "status": "done", "notes": "hack: temporary workaround"}
            ]
        )
        plan = _write_plan(tmp_path, "plan.yaml", plan_data)
        result = _invoke(runner, ["--plan-file", str(plan), "--output-format", "json"])
        data = json.loads(result.output)
        assert len(data["debt"]) >= 1

    def test_clean_task_no_debt(self, runner, tmp_path):
        plan_data = _simple_plan(
            tasks=[
                {"id": "T1", "title": "Clean task", "status": "done", "notes": "All good!"}
            ]
        )
        plan = _write_plan(tmp_path, "plan.yaml", plan_data)
        result = _invoke(runner, ["--plan-file", str(plan), "--output-format", "json"])
        data = json.loads(result.output)
        assert data["debt"] == []

    def test_min_debt_severity_filters_low(self, runner, tmp_path):
        """With --min-debt-severity critical, only critical-priority skipped tasks appear."""
        plan_data = _simple_plan(
            tasks=[
                # low priority skipped → severity "low" → filtered out
                {"id": "T1", "title": "Low-prio skip", "status": "skipped", "priority": "low"},
                # critical priority skipped → severity "critical" → included
                {"id": "T2", "title": "Critical skip", "status": "skipped", "priority": "critical"},
            ]
        )
        plan = _write_plan(tmp_path, "plan.yaml", plan_data)
        result = _invoke(
            runner,
            ["--plan-file", str(plan), "--output-format", "json", "--min-debt-severity", "critical"],
        )
        data = json.loads(result.output)
        debt_ids = {d["source_task_id"] for d in data["debt"]}
        assert "T2" in debt_ids
        assert "T1" not in debt_ids

    def test_debt_ordered_by_severity(self, runner, tmp_path):
        """Debt items should be returned critical-first."""
        plan_data = _simple_plan(
            tasks=[
                {"id": "T1", "title": "Low skip", "status": "skipped", "priority": "low"},
                {"id": "T2", "title": "Critical skip", "status": "skipped", "priority": "critical"},
                {"id": "T3", "title": "High skip", "status": "skipped", "priority": "high"},
            ]
        )
        plan = _write_plan(tmp_path, "plan.yaml", plan_data)
        result = _invoke(runner, ["--plan-file", str(plan), "--output-format", "json"])
        data = json.loads(result.output)
        severities = [d["severity"] for d in data["debt"]]
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        assert severities == sorted(severities, key=lambda s: order.get(s, 9))


# ---------------------------------------------------------------------------
# Follow-up items
# ---------------------------------------------------------------------------


class TestFollowUpItems:
    def test_blocked_task_generates_follow_up(self, runner, tmp_path):
        plan_data = _simple_plan(
            tasks=[{"id": "T1", "title": "Deploy", "status": "blocked"}]
        )
        plan = _write_plan(tmp_path, "plan.yaml", plan_data)
        result = _invoke(runner, ["--plan-file", str(plan), "--output-format", "json"])
        data = json.loads(result.output)
        fu = data["follow_up"]
        assert any(f["task_id"] == "T1" and f["category"] in ("blocked", "dependency") for f in fu)

    def test_pending_task_generates_follow_up(self, runner, tmp_path):
        plan_data = _simple_plan(
            tasks=[{"id": "T1", "title": "Docs", "status": "pending"}]
        )
        plan = _write_plan(tmp_path, "plan.yaml", plan_data)
        result = _invoke(runner, ["--plan-file", str(plan), "--output-format", "json"])
        data = json.loads(result.output)
        assert any(f["category"] == "pending" and f["task_id"] == "T1" for f in data["follow_up"])

    def test_skipped_task_generates_follow_up(self, runner, tmp_path):
        plan_data = _simple_plan(
            tasks=[{"id": "T1", "title": "Migrations", "status": "skipped"}]
        )
        plan = _write_plan(tmp_path, "plan.yaml", plan_data)
        result = _invoke(runner, ["--plan-file", str(plan), "--output-format", "json"])
        data = json.loads(result.output)
        assert any(f["category"] == "skipped" and f["task_id"] == "T1" for f in data["follow_up"])

    def test_running_task_generates_incomplete_follow_up(self, runner, tmp_path):
        plan_data = _simple_plan(
            status="running",
            tasks=[{"id": "T1", "title": "In progress", "status": "running"}],
        )
        plan = _write_plan(tmp_path, "plan.yaml", plan_data)
        result = _invoke(runner, ["--plan-file", str(plan), "--output-format", "json"])
        data = json.loads(result.output)
        assert any(f["category"] == "incomplete" and f["task_id"] == "T1" for f in data["follow_up"])

    def test_blocked_with_depends_on_is_dependency_category(self, runner, tmp_path):
        plan_data = _simple_plan(
            tasks=[
                {"id": "T1", "title": "Deploy", "status": "blocked", "depends_on": ["T0"]}
            ]
        )
        plan = _write_plan(tmp_path, "plan.yaml", plan_data)
        result = _invoke(runner, ["--plan-file", str(plan), "--output-format", "json"])
        data = json.loads(result.output)
        assert any(f["category"] == "dependency" and f["task_id"] == "T1" for f in data["follow_up"])

    def test_done_tasks_do_not_generate_follow_up(self, runner, tmp_path):
        plan = _write_plan(tmp_path, "plan.yaml", _simple_plan())
        result = _invoke(runner, ["--plan-file", str(plan), "--output-format", "json"])
        data = json.loads(result.output)
        # TASK-001 is done — should not appear in follow_up
        assert not any(f["task_id"] == "TASK-001" for f in data["follow_up"])


# ---------------------------------------------------------------------------
# Summary metrics
# ---------------------------------------------------------------------------


class TestSummaryMetrics:
    def test_completion_pct_all_done(self, runner, tmp_path):
        plan = _write_plan(tmp_path, "plan.yaml", _simple_plan())
        result = _invoke(runner, ["--plan-file", str(plan), "--output-format", "json"])
        data = json.loads(result.output)
        assert data["summary"]["overall_completion_pct"] == 100.0
        assert data["summary"]["fully_completed_plans"] == 1
        assert data["summary"]["partial_plans"] == 0

    def test_completion_pct_partial(self, runner, tmp_path):
        plan_data = _simple_plan(
            status="running",
            tasks=[
                {"id": "T1", "title": "Done", "status": "done"},
                {"id": "T2", "title": "Pending", "status": "pending"},
            ],
        )
        plan = _write_plan(tmp_path, "plan.yaml", plan_data)
        result = _invoke(runner, ["--plan-file", str(plan), "--output-format", "json"])
        data = json.loads(result.output)
        assert data["summary"]["overall_completion_pct"] == 50.0
        assert data["summary"]["partial_plans"] == 1
        assert data["summary"]["fully_completed_plans"] == 0

    def test_multiple_plans_aggregate_correctly(self, runner, tmp_path):
        plan_a = _write_plan(
            tmp_path,
            "plan-a.yaml",
            _simple_plan(plan_id="PLAN-001", tasks=[
                {"id": "T1", "status": "done", "title": "Task A1"},
            ]),
        )
        plan_b = _write_plan(
            tmp_path,
            "plan-b.yaml",
            _simple_plan(plan_id="PLAN-002", tasks=[
                {"id": "T1", "status": "done", "title": "Task B1"},
                {"id": "T2", "status": "pending", "title": "Task B2"},
            ]),
        )
        result = _invoke(
            runner,
            ["--plan-file", str(plan_a), "--plan-file", str(plan_b), "--output-format", "json"],
        )
        data = json.loads(result.output)
        assert data["summary"]["total_plans"] == 2
        assert data["summary"]["total_tasks"] == 3
        assert data["summary"]["completed_tasks"] == 2
        assert data["summary"]["pending_tasks"] == 1

    def test_debt_count_in_summary(self, runner, tmp_path):
        plan_data = _simple_plan(
            tasks=[
                {"id": "T1", "title": "Skip me", "status": "skipped"},
                {"id": "T2", "title": "With TODO", "status": "done", "notes": "TODO: cleanup"},
            ]
        )
        plan = _write_plan(tmp_path, "plan.yaml", plan_data)
        result = _invoke(runner, ["--plan-file", str(plan), "--output-format", "json"])
        data = json.loads(result.output)
        assert data["summary"]["total_debt_items"] == len(data["debt"])
        assert data["summary"]["total_debt_items"] >= 2

    def test_follow_up_count_in_summary(self, runner, tmp_path):
        plan_data = _simple_plan(
            status="running",
            tasks=[
                {"id": "T1", "title": "Done", "status": "done"},
                {"id": "T2", "title": "Blocked", "status": "blocked"},
                {"id": "T3", "title": "Pending", "status": "pending"},
            ],
        )
        plan = _write_plan(tmp_path, "plan.yaml", plan_data)
        result = _invoke(runner, ["--plan-file", str(plan), "--output-format", "json"])
        data = json.loads(result.output)
        assert data["summary"]["total_follow_up_items"] == len(data["follow_up"])
        assert data["summary"]["total_follow_up_items"] == 2


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


class TestFiltering:
    def test_plan_id_filter(self, runner, tmp_path):
        plan_a = _write_plan(
            tmp_path,
            "plan-a.yaml",
            _simple_plan(plan_id="PLAN-001", tasks=[
                {"id": "T1", "title": "A task", "status": "done"},
            ]),
        )
        plan_b = _write_plan(
            tmp_path,
            "plan-b.yaml",
            _simple_plan(plan_id="PLAN-002", tasks=[
                {"id": "T1", "title": "B task", "status": "done"},
            ]),
        )
        result = _invoke(
            runner,
            [
                "--plan-file", str(plan_a),
                "--plan-file", str(plan_b),
                "--plan-id", "PLAN-001",
                "--output-format", "json",
            ],
        )
        data = json.loads(result.output)
        assert data["summary"]["total_plans"] == 1
        assert data["plans"][0]["plan_id"] == "PLAN-001"

    def test_plans_sorted_by_plan_id(self, runner, tmp_path):
        plan_b = _write_plan(
            tmp_path, "b.yaml", _simple_plan(plan_id="PLAN-002", tasks=[
                {"id": "T1", "status": "done", "title": "B"},
            ])
        )
        plan_a = _write_plan(
            tmp_path, "a.yaml", _simple_plan(plan_id="PLAN-001", tasks=[
                {"id": "T1", "status": "done", "title": "A"},
            ])
        )
        result = _invoke(
            runner,
            ["--plan-file", str(plan_a), "--plan-file", str(plan_b), "--output-format", "json"],
        )
        data = json.loads(result.output)
        plan_ids = [p["plan_id"] for p in data["plans"]]
        assert plan_ids == sorted(plan_ids)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_no_plan_data_exits_1(self, runner):
        result = _invoke(runner, [])
        assert result.exit_code == 1

    def test_corrupt_plan_file_exits_2(self, runner, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("not: [valid: yaml: nesting]]]", encoding="utf-8")
        result = _invoke(runner, ["--plan-file", str(bad), "--output-format", "json"])
        assert result.exit_code == 2

    def test_empty_plan_no_tasks(self, runner, tmp_path):
        plan_data = {"plan": {"id": "PLAN-001", "title": "Empty", "status": "done"}, "tasks": []}
        plan = _write_plan(tmp_path, "plan.yaml", plan_data)
        result = _invoke(runner, ["--plan-file", str(plan), "--output-format", "json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["summary"]["total_tasks"] == 0
        assert data["summary"]["overall_completion_pct"] == 0.0
        assert data["completed_tasks"] == []
        assert data["debt"] == []
        assert data["follow_up"] == []
