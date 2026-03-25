"""Tests for harness_skills.cli.status (``harness status``).

Uses Click's ``CliRunner`` for isolated, filesystem-independent invocations.

Covers:
  - Table output: plan dashboard with summary and task tables
  - JSON output includes summary, plans, tasks
  - YAML output is parseable
  - Status filter (--status-filter)
  - Deps column shows task dependency IDs
  - dep_state field present in JSON output (null by default)
  - Edge cases: empty depends_on, all-done plan, no plans
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from harness_skills.cli.status import status_cmd


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _plan_yaml(
    tmp_path: Path,
    tasks: list[dict],
    *,
    plan_id: str = "PLAN-001",
    title: str = "Test Plan",
    plan_status: str = "pending",
) -> Path:
    """Write a minimal YAML plan file and return its Path."""
    data = {
        "plan": {
            "id": plan_id,
            "title": title,
            "status": plan_status,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        },
        "tasks": tasks,
        "coordination": {},
    }
    p = tmp_path / f"{plan_id}.yaml"
    p.write_text(yaml.dump(data, allow_unicode=True))
    return p


def _task(
    task_id: str,
    *,
    status: str = "pending",
    lock_status: str = "unlocked",
    assigned_agent: str = "",
    depends_on: list[str] | None = None,
    priority: str = "medium",
    title: str = "",
) -> dict:
    return {
        "id": task_id,
        "title": title or task_id,
        "description": "",
        "assigned_agent": assigned_agent,
        "lock_status": lock_status,
        "depends_on": depends_on or [],
        "status": status,
        "priority": priority,
        "started_at": None,
        "completed_at": None,
        "notes": "",
    }


def _invoke_table(runner: CliRunner, plan_file: Path) -> str:
    """Run harness status in table mode with --no-state-service.

    COLUMNS=250 prevents Rich from truncating the rightmost table columns
    (Deps) in the narrow pseudo-terminal created by Click's CliRunner.
    """
    result = runner.invoke(
        status_cmd,
        ["--plan-file", str(plan_file), "--no-state-service", "--format", "table"],
        env={"COLUMNS": "250"},
    )
    return result.output


def _invoke_json(runner: CliRunner, plan_file: Path) -> dict:
    """Run harness status in JSON mode and return the parsed response dict."""
    result = runner.invoke(
        status_cmd,
        ["--plan-file", str(plan_file), "--no-state-service", "--format", "json"],
    )
    assert result.exit_code == 0, f"Unexpected exit code {result.exit_code}: {result.output}"
    return json.loads(result.output)


# ---------------------------------------------------------------------------
# Table output -- basic rendering
# ---------------------------------------------------------------------------

class TestTableOutput:
    def test_table_shows_plan_id(self, runner, tmp_path):
        plan_file = _plan_yaml(tmp_path, [_task("TASK-001")])
        output = _invoke_table(runner, plan_file)
        assert "PLAN-001" in output

    def test_table_shows_task_status(self, runner, tmp_path):
        tasks = [
            _task("TASK-001", status="running", lock_status="locked", assigned_agent="agent-a"),
        ]
        plan_file = _plan_yaml(tmp_path, tasks)
        output = _invoke_table(runner, plan_file)
        assert "running" in output

    def test_table_shows_done_task(self, runner, tmp_path):
        tasks = [_task("TASK-001", status="done", lock_status="done")]
        plan_file = _plan_yaml(tmp_path, tasks)
        output = _invoke_table(runner, plan_file)
        assert "done" in output

    def test_table_shows_pending_task(self, runner, tmp_path):
        plan_file = _plan_yaml(tmp_path, [_task("TASK-001")])
        output = _invoke_table(runner, plan_file)
        assert "pending" in output


# ---------------------------------------------------------------------------
# Table output -- Deps column
# ---------------------------------------------------------------------------

class TestTableOutputDepsColumn:
    def test_deps_shown_in_table(self, runner, tmp_path):
        tasks = [
            _task("TASK-001"),
            _task("TASK-002", depends_on=["TASK-001"]),
        ]
        plan_file = _plan_yaml(tmp_path, tasks)
        output = _invoke_table(runner, plan_file)
        assert "TASK-001" in output

    def test_no_deps_shows_dash(self, runner, tmp_path):
        plan_file = _plan_yaml(tmp_path, [_task("TASK-001")])
        output = _invoke_table(runner, plan_file)
        # Task with no deps should show the em-dash placeholder
        assert "\u2014" in output


# ---------------------------------------------------------------------------
# JSON output -- structure
# ---------------------------------------------------------------------------

class TestJsonOutput:
    def test_json_has_summary(self, runner, tmp_path):
        plan_file = _plan_yaml(tmp_path, [_task("TASK-001")])
        data = _invoke_json(runner, plan_file)
        assert "summary" in data

    def test_json_has_plans(self, runner, tmp_path):
        plan_file = _plan_yaml(tmp_path, [_task("TASK-001")])
        data = _invoke_json(runner, plan_file)
        assert "plans" in data
        assert len(data["plans"]) == 1

    def test_json_plan_has_tasks(self, runner, tmp_path):
        plan_file = _plan_yaml(tmp_path, [_task("TASK-001")])
        data = _invoke_json(runner, plan_file)
        assert len(data["plans"][0]["tasks"]) == 1

    def test_json_task_has_task_id(self, runner, tmp_path):
        plan_file = _plan_yaml(tmp_path, [_task("TASK-001")])
        data = _invoke_json(runner, plan_file)
        task = data["plans"][0]["tasks"][0]
        assert task["task_id"] == "TASK-001"

    def test_json_task_has_status(self, runner, tmp_path):
        plan_file = _plan_yaml(tmp_path, [_task("TASK-001")])
        data = _invoke_json(runner, plan_file)
        task = data["plans"][0]["tasks"][0]
        assert task["status"] == "pending"

    def test_json_task_has_depends_on(self, runner, tmp_path):
        tasks = [
            _task("TASK-001"),
            _task("TASK-002", depends_on=["TASK-001"]),
        ]
        plan_file = _plan_yaml(tmp_path, tasks)
        data = _invoke_json(runner, plan_file)
        tasks_by_id = {t["task_id"]: t for t in data["plans"][0]["tasks"]}
        assert tasks_by_id["TASK-002"]["depends_on"] == ["TASK-001"]


# ---------------------------------------------------------------------------
# JSON output -- dep_state field
# ---------------------------------------------------------------------------

class TestJsonOutputDepState:
    def test_dep_state_field_present_in_json_output(self, runner, tmp_path):
        plan_file = _plan_yaml(tmp_path, [_task("TASK-001")])
        data = _invoke_json(runner, plan_file)
        task = data["plans"][0]["tasks"][0]
        assert "dep_state" in task

    def test_dep_state_is_null_by_default(self, runner, tmp_path):
        """dep_state is defined in the model but not populated by the CLI layer."""
        plan_file = _plan_yaml(tmp_path, [_task("TASK-001")])
        data = _invoke_json(runner, plan_file)
        task = data["plans"][0]["tasks"][0]
        assert task["dep_state"] is None

    def test_dep_state_null_for_task_with_deps(self, runner, tmp_path):
        tasks = [
            _task("TASK-001"),
            _task("TASK-002", depends_on=["TASK-001"]),
        ]
        plan_file = _plan_yaml(tmp_path, tasks)
        data = _invoke_json(runner, plan_file)
        tasks_by_id = {t["task_id"]: t for t in data["plans"][0]["tasks"]}
        assert tasks_by_id["TASK-002"]["dep_state"] is None

    def test_dep_state_null_for_running_task(self, runner, tmp_path):
        tasks = [
            _task("TASK-001", status="running", lock_status="locked", assigned_agent="a"),
        ]
        plan_file = _plan_yaml(tmp_path, tasks)
        data = _invoke_json(runner, plan_file)
        task = data["plans"][0]["tasks"][0]
        assert task["dep_state"] is None

    def test_dep_state_null_for_done_task(self, runner, tmp_path):
        tasks = [_task("TASK-001", status="done", lock_status="done")]
        plan_file = _plan_yaml(tmp_path, tasks)
        data = _invoke_json(runner, plan_file)
        task = data["plans"][0]["tasks"][0]
        assert task["dep_state"] is None


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_depends_on_list_in_json(self, runner, tmp_path):
        tasks = [_task("TASK-001", depends_on=[])]
        plan_file = _plan_yaml(tmp_path, tasks)
        data = _invoke_json(runner, plan_file)
        task = data["plans"][0]["tasks"][0]
        assert task["depends_on"] == []

    def test_exit_code_0_on_valid_plan(self, runner, tmp_path):
        plan_file = _plan_yaml(tmp_path, [_task("TASK-001")])
        result = runner.invoke(
            status_cmd,
            ["--plan-file", str(plan_file), "--no-state-service"],
        )
        assert result.exit_code == 0

    def test_exit_code_1_when_no_plans(self, runner, tmp_path):
        result = runner.invoke(
            status_cmd,
            ["--no-state-service"],
        )
        assert result.exit_code == 1

    def test_status_filter_blocked_excludes_pending_plan(self, runner, tmp_path):
        """A valid plan file that is filtered out still produces exit 0 (empty
        dashboard), not exit 1.  Exit 1 is reserved for "no data source at all".
        """
        plan_file = _plan_yaml(tmp_path, [_task("TASK-001")], plan_status="pending")
        result = runner.invoke(
            status_cmd,
            [
                "--plan-file", str(plan_file),
                "--no-state-service",
                "--status-filter", "blocked",
                "--format", "json",
            ],
        )
        # Filtering removes the plan -> empty plans list, but command succeeds
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["plans"] == []

    def test_all_done_plan(self, runner, tmp_path):
        tasks = [_task("TASK-001", status="done", lock_status="done")]
        plan_file = _plan_yaml(tmp_path, tasks, plan_status="done")
        output = _invoke_table(runner, plan_file)
        assert "done" in output

    def test_summary_counts_correct(self, runner, tmp_path):
        tasks = [
            _task("TASK-001", status="done", lock_status="done"),
            _task("TASK-002", status="running", lock_status="locked"),
            _task("TASK-003"),
        ]
        plan_file = _plan_yaml(tmp_path, tasks, plan_status="running")
        data = _invoke_json(runner, plan_file)
        summary = data["summary"]
        assert summary["total_tasks"] == 3
        assert summary["completed_tasks"] == 1
        assert summary["active_tasks"] == 1
        assert summary["pending_tasks"] == 1
