"""Tests for harness_skills.cli.status (``harness status``).

Uses Click's ``CliRunner`` for isolated, filesystem-independent invocations.

Covers:
  - Table output: pending tasks show 🟢 ready / ⏳ waiting in Status column
  - Table output: Deps column annotates each dep with ✅ (done) or ⬜ (pending)
  - Dependency graph section present when any task has depends_on
  - Dependency graph absent when no task has depends_on
  - Dependency graph icons for ready / waiting / done / running nodes
  - Back-reference marker for diamond dependency patterns
  - JSON output includes dep_state field populated correctly
  - Edge cases: dangling dep ID, empty depends_on, all-done plan
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
# Table output — Status column dep-state labels
# ---------------------------------------------------------------------------

class TestTableOutputDepState:
    def test_pending_no_deps_shows_ready_in_status_column(self, runner, tmp_path):
        plan_file = _plan_yaml(tmp_path, [_task("TASK-001")])
        output = _invoke_table(runner, plan_file)
        assert "🟢 ready" in output

    def test_pending_with_unmet_dep_shows_waiting_in_status_column(self, runner, tmp_path):
        tasks = [
            _task("TASK-001"),
            _task("TASK-002", depends_on=["TASK-001"]),
        ]
        plan_file = _plan_yaml(tmp_path, tasks)
        output = _invoke_table(runner, plan_file)
        assert "⏳ waiting" in output

    def test_running_task_shows_running_not_ready(self, runner, tmp_path):
        tasks = [
            _task("TASK-001", status="running", lock_status="locked", assigned_agent="agent-a"),
        ]
        plan_file = _plan_yaml(tmp_path, tasks)
        output = _invoke_table(runner, plan_file)
        assert "running" in output
        assert "🟢 ready" not in output

    def test_done_task_shows_done(self, runner, tmp_path):
        tasks = [_task("TASK-001", status="done", lock_status="done")]
        plan_file = _plan_yaml(tmp_path, tasks)
        output = _invoke_table(runner, plan_file)
        assert "done" in output


# ---------------------------------------------------------------------------
# Table output — Deps column annotations
# ---------------------------------------------------------------------------

class TestTableOutputDepsColumn:
    def test_done_dep_shown_with_checkmark(self, runner, tmp_path):
        tasks = [
            _task("TASK-001", status="done", lock_status="done"),
            _task("TASK-002", depends_on=["TASK-001"]),
        ]
        plan_file = _plan_yaml(tmp_path, tasks)
        output = _invoke_table(runner, plan_file)
        assert "✅TASK-001" in output

    def test_undone_dep_shown_with_square(self, runner, tmp_path):
        tasks = [
            _task("TASK-001"),
            _task("TASK-002", depends_on=["TASK-001"]),
        ]
        plan_file = _plan_yaml(tmp_path, tasks)
        output = _invoke_table(runner, plan_file)
        assert "⬜TASK-001" in output

    def test_mixed_deps_shows_both_indicators(self, runner, tmp_path):
        """TASK-003 depends on done TASK-001 and pending TASK-002."""
        tasks = [
            _task("TASK-001", status="done", lock_status="done"),
            _task("TASK-002"),
            _task("TASK-003", depends_on=["TASK-001", "TASK-002"]),
        ]
        plan_file = _plan_yaml(tmp_path, tasks)
        output = _invoke_table(runner, plan_file)
        assert "✅TASK-001" in output
        assert "⬜TASK-002" in output

    def test_no_deps_shows_dash(self, runner, tmp_path):
        plan_file = _plan_yaml(tmp_path, [_task("TASK-001")])
        output = _invoke_table(runner, plan_file)
        # Task with no deps should show the em-dash placeholder
        assert "—" in output


# ---------------------------------------------------------------------------
# Dependency graph section
# ---------------------------------------------------------------------------

class TestDepGraphRendering:
    def test_dep_graph_section_present_when_any_task_has_deps(self, runner, tmp_path):
        tasks = [
            _task("TASK-001"),
            _task("TASK-002", depends_on=["TASK-001"]),
        ]
        plan_file = _plan_yaml(tmp_path, tasks)
        output = _invoke_table(runner, plan_file)
        assert "Dependency graph" in output

    def test_dep_graph_absent_when_no_task_has_deps(self, runner, tmp_path):
        tasks = [_task("TASK-001"), _task("TASK-002")]
        plan_file = _plan_yaml(tmp_path, tasks)
        output = _invoke_table(runner, plan_file)
        assert "Dependency graph" not in output

    def test_dep_graph_shows_ready_node_icon(self, runner, tmp_path):
        tasks = [
            _task("TASK-001"),
            _task("TASK-002", depends_on=["TASK-001"]),
        ]
        plan_file = _plan_yaml(tmp_path, tasks)
        output = _invoke_table(runner, plan_file)
        # TASK-001 is a root with no deps → ready
        assert "🟢" in output

    def test_dep_graph_shows_waiting_node_icon(self, runner, tmp_path):
        tasks = [
            _task("TASK-001"),
            _task("TASK-002", depends_on=["TASK-001"]),
        ]
        plan_file = _plan_yaml(tmp_path, tasks)
        output = _invoke_table(runner, plan_file)
        # TASK-002 has unmet dep → waiting
        assert "⏳" in output

    def test_dep_graph_shows_done_node_icon(self, runner, tmp_path):
        tasks = [
            _task("TASK-001", status="done", lock_status="done"),
            _task("TASK-002", depends_on=["TASK-001"]),
        ]
        plan_file = _plan_yaml(tmp_path, tasks)
        output = _invoke_table(runner, plan_file)
        assert "✅" in output

    def test_dep_graph_shows_running_node_icon(self, runner, tmp_path):
        tasks = [
            _task("TASK-001", status="running", lock_status="locked", assigned_agent="a"),
            _task("TASK-002", depends_on=["TASK-001"]),
        ]
        plan_file = _plan_yaml(tmp_path, tasks)
        output = _invoke_table(runner, plan_file)
        assert "🔵" in output

    def test_dep_graph_waiting_node_shows_blocker_ids(self, runner, tmp_path):
        tasks = [
            _task("TASK-001"),
            _task("TASK-002", depends_on=["TASK-001"]),
        ]
        plan_file = _plan_yaml(tmp_path, tasks)
        output = _invoke_table(runner, plan_file)
        # The graph section should name the blocking dep
        assert "waiting on: TASK-001" in output

    def test_already_shown_back_reference_for_diamond(self, runner, tmp_path):
        """Diamond: TASK-003 depends on TASK-001 and TASK-002.
        Walking TASK-001 → TASK-003 and then TASK-002 → TASK-003 should
        trigger the back-reference marker on the second visit.
        """
        tasks = [
            _task("TASK-001"),
            _task("TASK-002"),
            _task("TASK-003", depends_on=["TASK-001", "TASK-002"]),
        ]
        plan_file = _plan_yaml(tmp_path, tasks)
        output = _invoke_table(runner, plan_file)
        assert "already shown" in output


# ---------------------------------------------------------------------------
# JSON output — dep_state field
# ---------------------------------------------------------------------------

class TestJsonOutputDepState:
    def test_dep_state_field_present_in_json_output(self, runner, tmp_path):
        plan_file = _plan_yaml(tmp_path, [_task("TASK-001")])
        data = _invoke_json(runner, plan_file)
        task = data["plans"][0]["tasks"][0]
        assert "dep_state" in task

    def test_dep_state_ready_for_no_dep_pending_task(self, runner, tmp_path):
        plan_file = _plan_yaml(tmp_path, [_task("TASK-001")])
        data = _invoke_json(runner, plan_file)
        task = data["plans"][0]["tasks"][0]
        assert task["dep_state"] == "ready"

    def test_dep_state_waiting_for_task_with_unmet_dep(self, runner, tmp_path):
        tasks = [
            _task("TASK-001"),
            _task("TASK-002", depends_on=["TASK-001"]),
        ]
        plan_file = _plan_yaml(tmp_path, tasks)
        data = _invoke_json(runner, plan_file)
        tasks_by_id = {t["task_id"]: t for t in data["plans"][0]["tasks"]}
        assert tasks_by_id["TASK-002"]["dep_state"] == "waiting"

    def test_dep_state_ready_when_all_deps_done(self, runner, tmp_path):
        tasks = [
            _task("TASK-001", status="done", lock_status="done"),
            _task("TASK-002", depends_on=["TASK-001"]),
        ]
        plan_file = _plan_yaml(tmp_path, tasks)
        data = _invoke_json(runner, plan_file)
        tasks_by_id = {t["task_id"]: t for t in data["plans"][0]["tasks"]}
        assert tasks_by_id["TASK-002"]["dep_state"] == "ready"

    def test_dep_state_running_for_running_task(self, runner, tmp_path):
        tasks = [
            _task("TASK-001", status="running", lock_status="locked", assigned_agent="a"),
        ]
        plan_file = _plan_yaml(tmp_path, tasks)
        data = _invoke_json(runner, plan_file)
        task = data["plans"][0]["tasks"][0]
        assert task["dep_state"] == "running"

    def test_dep_state_done_for_done_task(self, runner, tmp_path):
        tasks = [_task("TASK-001", status="done", lock_status="done")]
        plan_file = _plan_yaml(tmp_path, tasks)
        data = _invoke_json(runner, plan_file)
        task = data["plans"][0]["tasks"][0]
        assert task["dep_state"] == "done"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_dangling_dep_id_treated_as_unmet(self, runner, tmp_path):
        """A dep ID that doesn't exist in the plan → task stays 'waiting'."""
        tasks = [_task("TASK-001", depends_on=["TASK-999"])]
        plan_file = _plan_yaml(tmp_path, tasks)
        data = _invoke_json(runner, plan_file)
        task = data["plans"][0]["tasks"][0]
        assert task["dep_state"] == "waiting"

    def test_empty_depends_on_list_treated_as_ready(self, runner, tmp_path):
        tasks = [_task("TASK-001", depends_on=[])]
        plan_file = _plan_yaml(tmp_path, tasks)
        data = _invoke_json(runner, plan_file)
        task = data["plans"][0]["tasks"][0]
        assert task["dep_state"] == "ready"

    def test_all_done_plan_no_ready_or_waiting_labels(self, runner, tmp_path):
        tasks = [_task("TASK-001", status="done", lock_status="done")]
        plan_file = _plan_yaml(tmp_path, tasks, plan_status="done")
        output = _invoke_table(runner, plan_file)
        assert "🟢 ready" not in output
        assert "⏳ waiting" not in output

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
        # Filtering removes the plan → empty plans list, but command succeeds
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["plans"] == []
