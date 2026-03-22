"""Tests for skills/exec_plan.py — ExecPlan class.

Covers:
  - _blocked_by()       — dependency resolution
  - ready_tasks()        — tasks ready to start
  - _dep_state()         — computed dependency state string
  - claim()              — task locking with dep validation
  - mark_done()          — marking tasks complete
  - release()            — releasing a lock without completing
  - status_table()       — formatted status table includes Dep State column
  - dependency_graph()   — text tree with labelled nodes
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

# Allow running from the repo root: ``pytest tests/test_exec_plan.py``
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skills.exec_plan import ExecPlan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _make_plan(tmp_path: Path, tasks: list[dict], plan_id: str = "PLAN-TEST") -> ExecPlan:
    """Write a minimal plan YAML to *tmp_path* and return a loaded ExecPlan."""
    data = {
        "plan": {
            "id": plan_id,
            "title": "Test Plan",
            "status": "pending",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        },
        "tasks": tasks,
        "coordination": {},
    }
    plan_file = tmp_path / f"{plan_id}.yaml"
    plan_file.write_text(yaml.dump(data, allow_unicode=True))
    return ExecPlan._load_file(plan_file)


# ---------------------------------------------------------------------------
# _blocked_by
# ---------------------------------------------------------------------------

class TestBlockedBy:
    def test_no_deps_returns_empty_list(self, tmp_path):
        plan = _make_plan(tmp_path, [_task("TASK-001")])
        t = plan._get_task("TASK-001")
        assert plan._blocked_by(t) == []

    def test_done_dep_not_in_blocked_list(self, tmp_path):
        tasks = [
            _task("TASK-001", status="done", lock_status="done"),
            _task("TASK-002", depends_on=["TASK-001"]),
        ]
        plan = _make_plan(tmp_path, tasks)
        t = plan._get_task("TASK-002")
        assert plan._blocked_by(t) == []

    def test_pending_dep_in_blocked_list(self, tmp_path):
        tasks = [
            _task("TASK-001"),
            _task("TASK-002", depends_on=["TASK-001"]),
        ]
        plan = _make_plan(tmp_path, tasks)
        t = plan._get_task("TASK-002")
        assert plan._blocked_by(t) == ["TASK-001"]

    def test_running_dep_in_blocked_list(self, tmp_path):
        tasks = [
            _task("TASK-001", status="running", lock_status="locked", assigned_agent="agent-a"),
            _task("TASK-002", depends_on=["TASK-001"]),
        ]
        plan = _make_plan(tmp_path, tasks)
        t = plan._get_task("TASK-002")
        assert plan._blocked_by(t) == ["TASK-001"]

    def test_multiple_deps_mixed_returns_only_unmet(self, tmp_path):
        tasks = [
            _task("TASK-001", status="done", lock_status="done"),
            _task("TASK-002"),  # pending
            _task("TASK-003", depends_on=["TASK-001", "TASK-002"]),
        ]
        plan = _make_plan(tmp_path, tasks)
        t = plan._get_task("TASK-003")
        assert plan._blocked_by(t) == ["TASK-002"]

    def test_unknown_dep_id_treated_as_unmet(self, tmp_path):
        tasks = [_task("TASK-001", depends_on=["TASK-999"])]
        plan = _make_plan(tmp_path, tasks)
        t = plan._get_task("TASK-001")
        assert plan._blocked_by(t) == ["TASK-999"]


# ---------------------------------------------------------------------------
# ready_tasks
# ---------------------------------------------------------------------------

class TestReadyTasks:
    def test_no_dep_task_is_ready(self, tmp_path):
        plan = _make_plan(tmp_path, [_task("TASK-001")])
        ready_ids = [t["id"] for t in plan.ready_tasks()]
        assert "TASK-001" in ready_ids

    def test_task_with_pending_dep_not_ready(self, tmp_path):
        tasks = [
            _task("TASK-001"),
            _task("TASK-002", depends_on=["TASK-001"]),
        ]
        plan = _make_plan(tmp_path, tasks)
        ready_ids = [t["id"] for t in plan.ready_tasks()]
        assert "TASK-002" not in ready_ids
        assert "TASK-001" in ready_ids

    def test_task_with_done_dep_is_ready(self, tmp_path):
        tasks = [
            _task("TASK-001", status="done", lock_status="done"),
            _task("TASK-002", depends_on=["TASK-001"]),
        ]
        plan = _make_plan(tmp_path, tasks)
        ready_ids = [t["id"] for t in plan.ready_tasks()]
        assert "TASK-002" in ready_ids

    def test_locked_task_not_in_ready_list(self, tmp_path):
        tasks = [
            _task("TASK-001", lock_status="locked", status="running", assigned_agent="a"),
        ]
        plan = _make_plan(tmp_path, tasks)
        assert plan.ready_tasks() == []

    def test_done_task_not_in_ready_list(self, tmp_path):
        plan = _make_plan(tmp_path, [_task("TASK-001", status="done", lock_status="done")])
        assert plan.ready_tasks() == []

    def test_skipped_task_not_in_ready_list(self, tmp_path):
        plan = _make_plan(tmp_path, [_task("TASK-001", status="skipped")])
        assert plan.ready_tasks() == []


# ---------------------------------------------------------------------------
# _dep_state
# ---------------------------------------------------------------------------

class TestDepState:
    def test_pending_no_deps_is_ready(self, tmp_path):
        plan = _make_plan(tmp_path, [_task("TASK-001")])
        t = plan._get_task("TASK-001")
        assert plan._dep_state(t) == "ready"

    def test_pending_with_unmet_deps_is_waiting(self, tmp_path):
        tasks = [
            _task("TASK-001"),
            _task("TASK-002", depends_on=["TASK-001"]),
        ]
        plan = _make_plan(tmp_path, tasks)
        t = plan._get_task("TASK-002")
        assert plan._dep_state(t) == "waiting"

    def test_pending_with_all_deps_done_is_ready(self, tmp_path):
        tasks = [
            _task("TASK-001", status="done", lock_status="done"),
            _task("TASK-002", depends_on=["TASK-001"]),
        ]
        plan = _make_plan(tmp_path, tasks)
        t = plan._get_task("TASK-002")
        assert plan._dep_state(t) == "ready"

    def test_running_task_dep_state_is_running(self, tmp_path):
        plan = _make_plan(
            tmp_path, [_task("TASK-001", status="running", lock_status="locked", assigned_agent="a")]
        )
        t = plan._get_task("TASK-001")
        assert plan._dep_state(t) == "running"

    def test_done_task_dep_state_is_done(self, tmp_path):
        plan = _make_plan(tmp_path, [_task("TASK-001", status="done", lock_status="done")])
        t = plan._get_task("TASK-001")
        assert plan._dep_state(t) == "done"

    def test_blocked_task_dep_state_is_blocked(self, tmp_path):
        plan = _make_plan(tmp_path, [_task("TASK-001", status="blocked")])
        t = plan._get_task("TASK-001")
        assert plan._dep_state(t) == "blocked"

    def test_skipped_task_dep_state_is_skipped(self, tmp_path):
        plan = _make_plan(tmp_path, [_task("TASK-001", status="skipped")])
        t = plan._get_task("TASK-001")
        assert plan._dep_state(t) == "skipped"


# ---------------------------------------------------------------------------
# claim
# ---------------------------------------------------------------------------

class TestClaim:
    def test_claim_sets_status_running_and_lock_locked(self, tmp_path):
        plan = _make_plan(tmp_path, [_task("TASK-001")])
        plan.claim("TASK-001", agent="agent-a")
        t = plan._get_task("TASK-001")
        assert t["status"] == "running"
        assert t["lock_status"] == "locked"
        assert t["assigned_agent"] == "agent-a"

    def test_claim_raises_when_dep_not_done(self, tmp_path):
        tasks = [
            _task("TASK-001"),
            _task("TASK-002", depends_on=["TASK-001"]),
        ]
        plan = _make_plan(tmp_path, tasks)
        with pytest.raises(ValueError, match="TASK-001"):
            plan.claim("TASK-002", agent="agent-a")

    def test_claim_raises_when_already_done(self, tmp_path):
        plan = _make_plan(tmp_path, [_task("TASK-001", status="done", lock_status="done")])
        with pytest.raises(ValueError, match="already done"):
            plan.claim("TASK-001", agent="agent-a")

    def test_claim_raises_when_locked_by_different_agent(self, tmp_path):
        plan = _make_plan(
            tmp_path,
            [_task("TASK-001", status="running", lock_status="locked", assigned_agent="agent-a")],
        )
        with pytest.raises(ValueError, match="agent-a"):
            plan.claim("TASK-001", agent="agent-b")

    def test_claim_same_agent_idempotent(self, tmp_path):
        plan = _make_plan(
            tmp_path,
            [_task("TASK-001", status="running", lock_status="locked", assigned_agent="agent-a")],
        )
        # Should not raise — same agent re-claiming is allowed
        plan.claim("TASK-001", agent="agent-a")

    def test_claim_succeeds_after_dep_done(self, tmp_path):
        tasks = [
            _task("TASK-001", status="done", lock_status="done"),
            _task("TASK-002", depends_on=["TASK-001"]),
        ]
        plan = _make_plan(tmp_path, tasks)
        plan.claim("TASK-002", agent="agent-b")
        t = plan._get_task("TASK-002")
        assert t["status"] == "running"


# ---------------------------------------------------------------------------
# mark_done
# ---------------------------------------------------------------------------

class TestMarkDone:
    def test_mark_done_sets_status_and_lock(self, tmp_path):
        plan = _make_plan(
            tmp_path,
            [_task("TASK-001", status="running", lock_status="locked", assigned_agent="agent-a")],
        )
        plan.mark_done("TASK-001", agent="agent-a")
        t = plan._get_task("TASK-001")
        assert t["status"] == "done"
        assert t["lock_status"] == "done"
        assert t["completed_at"] is not None

    def test_mark_done_closes_plan_when_all_done(self, tmp_path):
        tasks = [
            _task("TASK-001", status="running", lock_status="locked", assigned_agent="agent-a"),
        ]
        plan = _make_plan(tmp_path, tasks)
        plan.mark_done("TASK-001", agent="agent-a")
        assert plan._data["plan"]["status"] == "done"

    def test_mark_done_does_not_close_plan_when_tasks_remain(self, tmp_path):
        tasks = [
            _task("TASK-001", status="running", lock_status="locked", assigned_agent="agent-a"),
            _task("TASK-002"),
        ]
        plan = _make_plan(tmp_path, tasks)
        plan.mark_done("TASK-001", agent="agent-a")
        assert plan._data["plan"]["status"] != "done"

    def test_mark_done_raises_when_wrong_agent(self, tmp_path):
        plan = _make_plan(
            tmp_path,
            [_task("TASK-001", status="running", lock_status="locked", assigned_agent="agent-a")],
        )
        with pytest.raises(ValueError, match="agent-a"):
            plan.mark_done("TASK-001", agent="agent-b")

    def test_mark_done_stores_notes(self, tmp_path):
        plan = _make_plan(
            tmp_path,
            [_task("TASK-001", status="running", lock_status="locked", assigned_agent="agent-a")],
        )
        plan.mark_done("TASK-001", agent="agent-a", notes="All good")
        t = plan._get_task("TASK-001")
        assert t["notes"] == "All good"


# ---------------------------------------------------------------------------
# release
# ---------------------------------------------------------------------------

class TestRelease:
    def test_release_resets_to_pending_unlocked(self, tmp_path):
        plan = _make_plan(
            tmp_path,
            [_task("TASK-001", status="running", lock_status="locked", assigned_agent="agent-a")],
        )
        plan.release("TASK-001", agent="agent-a")
        t = plan._get_task("TASK-001")
        assert t["status"] == "pending"
        assert t["lock_status"] == "unlocked"
        assert t["assigned_agent"] == ""

    def test_release_raises_when_wrong_agent(self, tmp_path):
        plan = _make_plan(
            tmp_path,
            [_task("TASK-001", status="running", lock_status="locked", assigned_agent="agent-a")],
        )
        with pytest.raises(ValueError, match="agent-a"):
            plan.release("TASK-001", agent="agent-b")


# ---------------------------------------------------------------------------
# status_table
# ---------------------------------------------------------------------------

class TestStatusTable:
    def test_contains_dep_state_column_header(self, tmp_path):
        plan = _make_plan(tmp_path, [_task("TASK-001")])
        table = plan.status_table()
        assert "Dep State" in table

    def test_ready_task_shows_ready_label(self, tmp_path):
        plan = _make_plan(tmp_path, [_task("TASK-001")])
        table = plan.status_table()
        assert "ready" in table

    def test_waiting_task_shows_waiting_label(self, tmp_path):
        tasks = [
            _task("TASK-001"),
            _task("TASK-002", depends_on=["TASK-001"]),
        ]
        plan = _make_plan(tmp_path, tasks)
        table = plan.status_table()
        assert "waiting" in table

    def test_done_task_shows_done_in_dep_state(self, tmp_path):
        plan = _make_plan(tmp_path, [_task("TASK-001", status="done", lock_status="done")])
        table = plan.status_table()
        # The dep_state column should contain the literal string "done"
        assert "done" in table

    def test_ready_tasks_summary_line_present(self, tmp_path):
        plan = _make_plan(tmp_path, [_task("TASK-001")])
        table = plan.status_table()
        assert "Ready to start" in table

    def test_no_ready_summary_when_all_locked_or_done(self, tmp_path):
        tasks = [
            _task("TASK-001", status="running", lock_status="locked", assigned_agent="a"),
        ]
        plan = _make_plan(tmp_path, tasks)
        table = plan.status_table()
        assert "Ready to start" not in table


# ---------------------------------------------------------------------------
# dependency_graph
# ---------------------------------------------------------------------------

class TestDependencyGraph:
    def test_root_node_shown_at_top_level(self, tmp_path):
        plan = _make_plan(tmp_path, [_task("TASK-001")])
        graph = plan.dependency_graph()
        assert "TASK-001" in graph

    def test_ready_node_has_green_circle_icon(self, tmp_path):
        plan = _make_plan(tmp_path, [_task("TASK-001")])
        graph = plan.dependency_graph()
        assert "🟢" in graph

    def test_waiting_node_has_hourglass_and_blocker_ids(self, tmp_path):
        tasks = [
            _task("TASK-001"),
            _task("TASK-002", depends_on=["TASK-001"]),
        ]
        plan = _make_plan(tmp_path, tasks)
        graph = plan.dependency_graph()
        assert "⏳" in graph
        assert "TASK-001" in graph
        assert "waiting" in graph

    def test_done_node_has_checkmark_icon(self, tmp_path):
        plan = _make_plan(tmp_path, [_task("TASK-001", status="done", lock_status="done")])
        graph = plan.dependency_graph()
        assert "✅" in graph

    def test_running_node_has_blue_circle_icon(self, tmp_path):
        plan = _make_plan(
            tmp_path,
            [_task("TASK-001", status="running", lock_status="locked", assigned_agent="a")],
        )
        graph = plan.dependency_graph()
        assert "🔵" in graph

    def test_child_indented_under_parent(self, tmp_path):
        tasks = [
            _task("TASK-001"),
            _task("TASK-002", depends_on=["TASK-001"]),
        ]
        plan = _make_plan(tmp_path, tasks)
        graph = plan.dependency_graph()
        lines = graph.splitlines()
        task001_indent = next(
            (len(l) - len(l.lstrip()) for l in lines if "TASK-001" in l), None
        )
        task002_indent = next(
            (len(l) - len(l.lstrip()) for l in lines if "TASK-002" in l), None
        )
        assert task001_indent is not None
        assert task002_indent is not None
        assert task002_indent > task001_indent

    def test_already_visited_node_shows_back_reference(self, tmp_path):
        """Diamond dependency: TASK-003 depends on both TASK-001 and TASK-002.
        When walking TASK-001 → TASK-003 and then TASK-002 → TASK-003,
        the second occurrence should show the back-reference marker.
        """
        tasks = [
            _task("TASK-001"),
            _task("TASK-002"),
            _task("TASK-003", depends_on=["TASK-001", "TASK-002"]),
        ]
        plan = _make_plan(tmp_path, tasks)
        graph = plan.dependency_graph()
        assert "already shown" in graph

    def test_disconnected_all_nodes_appear(self, tmp_path):
        """Two independent task trees — every node must appear in the graph."""
        tasks = [
            _task("TASK-001"),
            _task("TASK-002"),
        ]
        plan = _make_plan(tmp_path, tasks)
        graph = plan.dependency_graph()
        assert "TASK-001" in graph
        assert "TASK-002" in graph
