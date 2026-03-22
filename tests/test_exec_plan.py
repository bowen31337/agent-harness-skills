<<<<<<< HEAD
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
||||||| 0e893bd
=======
"""
tests/test_exec_plan.py — pytest suite for skills/exec_plan.py

Covers:
  - Template sections present after ExecPlan.init()
  - Default stub values for each narrative section
  - Custom values passed to init() are reflected in the file
  - Template file structure matches required schema
  - plan-template.yaml contains all expected section keys
  - CLI: init subcommand accepts and propagates new flags

Run with:
    pytest tests/test_exec_plan.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

# Make sure the project root is on sys.path so we can import skills.exec_plan
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from skills.exec_plan import ExecPlan, _EXEC_PLANS_DIR, _TEMPLATE  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def plans_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect exec-plan storage to a temporary directory for each test."""
    import skills.exec_plan as _ep_mod

    fake_dir = tmp_path / "exec-plans"
    fake_dir.mkdir()

    # Copy the real template into the temp dir so init() can find it
    real_template = _EXEC_PLANS_DIR / "plan-template.yaml"
    fake_template = fake_dir / "plan-template.yaml"
    fake_template.write_bytes(real_template.read_bytes())

    monkeypatch.setattr(_ep_mod, "_EXEC_PLANS_DIR", fake_dir)
    monkeypatch.setattr(_ep_mod, "_TEMPLATE", fake_template)
    return fake_dir


# ---------------------------------------------------------------------------
# Section presence tests
# ---------------------------------------------------------------------------


class TestTemplateSectionsPresent:
    """ExecPlan.init() must write all required narrative sections."""

    REQUIRED_TOP_LEVEL_KEYS = [
        "plan",
        "objective",
        "approach",
        "steps",
        "context_assembly",
        "progress_log",
        "known_debt",
        "completion_criteria",
        "tasks",
        "coordination",
    ]

    def test_all_narrative_sections_exist(self, plans_dir: Path) -> None:
        plan = ExecPlan.init(title="Test Plan", plan_id="PLAN-001")
        with (plans_dir / "PLAN-001.yaml").open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        for key in self.REQUIRED_TOP_LEVEL_KEYS:
            assert key in data, f"Missing top-level key: {key!r}"

    def test_context_assembly_has_sub_keys(self, plans_dir: Path) -> None:
        ExecPlan.init(title="Test Plan", plan_id="PLAN-001")
        with (plans_dir / "PLAN-001.yaml").open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        ca = data["context_assembly"]
        assert "key_files" in ca
        assert "key_patterns" in ca
        assert "notes" in ca

    def test_steps_is_a_list(self, plans_dir: Path) -> None:
        ExecPlan.init(title="Test Plan", plan_id="PLAN-001")
        with (plans_dir / "PLAN-001.yaml").open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert isinstance(data["steps"], list)
        assert len(data["steps"]) > 0

    def test_completion_criteria_is_a_list(self, plans_dir: Path) -> None:
        ExecPlan.init(title="Test Plan", plan_id="PLAN-001")
        with (plans_dir / "PLAN-001.yaml").open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert isinstance(data["completion_criteria"], list)
        assert len(data["completion_criteria"]) > 0

    def test_known_debt_is_a_list(self, plans_dir: Path) -> None:
        ExecPlan.init(title="Test Plan", plan_id="PLAN-001")
        with (plans_dir / "PLAN-001.yaml").open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert isinstance(data["known_debt"], list)

    def test_progress_log_is_string(self, plans_dir: Path) -> None:
        ExecPlan.init(title="Test Plan", plan_id="PLAN-001")
        with (plans_dir / "PLAN-001.yaml").open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert isinstance(data["progress_log"], str)
        assert data["progress_log"] != ""


# ---------------------------------------------------------------------------
# Default stub value tests
# ---------------------------------------------------------------------------


class TestDefaultStubValues:
    """When no narrative kwargs are supplied, stubs must be non-empty placeholders."""

    def test_objective_has_stub_text(self, plans_dir: Path) -> None:
        ExecPlan.init(title="Test Plan", plan_id="PLAN-001")
        with (plans_dir / "PLAN-001.yaml").open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert isinstance(data["objective"], str)
        assert len(data["objective"]) > 0

    def test_approach_has_stub_text(self, plans_dir: Path) -> None:
        ExecPlan.init(title="Test Plan", plan_id="PLAN-001")
        with (plans_dir / "PLAN-001.yaml").open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert isinstance(data["approach"], str)
        assert len(data["approach"]) > 0

    def test_steps_has_three_stubs_by_default(self, plans_dir: Path) -> None:
        ExecPlan.init(title="Test Plan", plan_id="PLAN-001")
        with (plans_dir / "PLAN-001.yaml").open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert len(data["steps"]) == 3

    def test_completion_criteria_has_three_stubs_by_default(self, plans_dir: Path) -> None:
        ExecPlan.init(title="Test Plan", plan_id="PLAN-001")
        with (plans_dir / "PLAN-001.yaml").open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert len(data["completion_criteria"]) == 3

    def test_context_assembly_starts_empty(self, plans_dir: Path) -> None:
        ExecPlan.init(title="Test Plan", plan_id="PLAN-001")
        with (plans_dir / "PLAN-001.yaml").open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert data["context_assembly"]["key_files"] == []
        assert data["context_assembly"]["key_patterns"] == []

    def test_known_debt_starts_empty(self, plans_dir: Path) -> None:
        ExecPlan.init(title="Test Plan", plan_id="PLAN-001")
        with (plans_dir / "PLAN-001.yaml").open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert data["known_debt"] == []

    def test_progress_log_default_path(self, plans_dir: Path) -> None:
        ExecPlan.init(title="Test Plan", plan_id="PLAN-001")
        with (plans_dir / "PLAN-001.yaml").open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert data["progress_log"] == ".claw-forge/progress.log"


# ---------------------------------------------------------------------------
# Custom value tests
# ---------------------------------------------------------------------------


class TestCustomNarrativeValues:
    """Values supplied to init() must appear verbatim in the written file."""

    def test_custom_objective(self, plans_dir: Path) -> None:
        obj = "Extract token verification into AuthService"
        ExecPlan.init(title="Refactor Auth", plan_id="PLAN-001", objective=obj)
        with (plans_dir / "PLAN-001.yaml").open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert data["objective"] == obj

    def test_custom_approach(self, plans_dir: Path) -> None:
        approach = "Move verify_token() from middleware into AuthService"
        ExecPlan.init(title="Refactor Auth", plan_id="PLAN-001", approach=approach)
        with (plans_dir / "PLAN-001.yaml").open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert data["approach"] == approach

    def test_custom_steps(self, plans_dir: Path) -> None:
        steps = ["Read middleware", "Move function", "Update call sites", "Run tests"]
        ExecPlan.init(title="Refactor Auth", plan_id="PLAN-001", steps=steps)
        with (plans_dir / "PLAN-001.yaml").open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert data["steps"] == steps

    def test_custom_completion_criteria(self, plans_dir: Path) -> None:
        criteria = ["All tests pass", "Coverage ≥ 80 %", "PR merged"]
        ExecPlan.init(
            title="Refactor Auth",
            plan_id="PLAN-001",
            completion_criteria=criteria,
        )
        with (plans_dir / "PLAN-001.yaml").open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert data["completion_criteria"] == criteria

    def test_custom_objective_does_not_override_title(self, plans_dir: Path) -> None:
        ExecPlan.init(
            title="My Feature",
            plan_id="PLAN-001",
            objective="Specific objective text",
        )
        with (plans_dir / "PLAN-001.yaml").open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert data["plan"]["title"] == "My Feature"
        assert data["objective"] == "Specific objective text"

    def test_single_step_list(self, plans_dir: Path) -> None:
        ExecPlan.init(title="Quick Fix", plan_id="PLAN-001", steps=["Fix the bug"])
        with (plans_dir / "PLAN-001.yaml").open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert data["steps"] == ["Fix the bug"]

    def test_single_criterion(self, plans_dir: Path) -> None:
        ExecPlan.init(
            title="Quick Fix",
            plan_id="PLAN-001",
            completion_criteria=["Bug no longer reproducible"],
        )
        with (plans_dir / "PLAN-001.yaml").open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert data["completion_criteria"] == ["Bug no longer reproducible"]


# ---------------------------------------------------------------------------
# plan-template.yaml schema validation
# ---------------------------------------------------------------------------


class TestPlanTemplateFile:
    """The checked-in plan-template.yaml must itself contain all required keys."""

    REQUIRED_KEYS = [
        "plan",
        "objective",
        "approach",
        "steps",
        "context_assembly",
        "progress_log",
        "known_debt",
        "completion_criteria",
        "tasks",
        "coordination",
    ]

    def test_template_file_exists(self) -> None:
        assert _TEMPLATE.exists(), f"Template file missing: {_TEMPLATE}"

    def test_template_contains_all_narrative_keys(self) -> None:
        with _TEMPLATE.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        for key in self.REQUIRED_KEYS:
            assert key in data, f"plan-template.yaml missing key: {key!r}"

    def test_template_context_assembly_structure(self) -> None:
        with _TEMPLATE.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        ca = data.get("context_assembly", {})
        assert "key_files" in ca
        assert "key_patterns" in ca
        assert "notes" in ca

    def test_template_steps_is_non_empty_list(self) -> None:
        with _TEMPLATE.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert isinstance(data["steps"], list)
        assert len(data["steps"]) > 0

    def test_template_completion_criteria_is_non_empty_list(self) -> None:
        with _TEMPLATE.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert isinstance(data["completion_criteria"], list)
        assert len(data["completion_criteria"]) > 0

    def test_template_progress_log_is_string(self) -> None:
        with _TEMPLATE.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert isinstance(data["progress_log"], str)


# ---------------------------------------------------------------------------
# Round-trip: plan metadata is still correct after adding narrative sections
# ---------------------------------------------------------------------------


class TestPlanMetadataIntegrity:
    """Adding narrative sections must not corrupt plan-level metadata."""

    def test_plan_id_is_set(self, plans_dir: Path) -> None:
        ExecPlan.init(title="Integrity Check", plan_id="PLAN-042")
        with (plans_dir / "PLAN-042.yaml").open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert data["plan"]["id"] == "PLAN-042"

    def test_plan_title_is_set(self, plans_dir: Path) -> None:
        ExecPlan.init(title="Integrity Check", plan_id="PLAN-042")
        with (plans_dir / "PLAN-042.yaml").open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert data["plan"]["title"] == "Integrity Check"

    def test_plan_status_is_pending(self, plans_dir: Path) -> None:
        ExecPlan.init(title="Integrity Check", plan_id="PLAN-042")
        with (plans_dir / "PLAN-042.yaml").open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert data["plan"]["status"] == "pending"

    def test_tasks_block_has_one_stub(self, plans_dir: Path) -> None:
        ExecPlan.init(title="Integrity Check", plan_id="PLAN-042")
        with (plans_dir / "PLAN-042.yaml").open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert isinstance(data["tasks"], list)
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["id"] == "TASK-001"

    def test_coordination_block_present(self, plans_dir: Path) -> None:
        ExecPlan.init(title="Integrity Check", plan_id="PLAN-042")
        with (plans_dir / "PLAN-042.yaml").open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        coord = data["coordination"]
        assert "strategy" in coord
        assert "hotspot_files" in coord
        assert "merge_order" in coord


# ---------------------------------------------------------------------------
# CLI integration: init sub-command flags
# ---------------------------------------------------------------------------


class TestCLIInitFlags:
    """The `init` CLI sub-command must accept and propagate the new narrative flags."""

    def test_cli_objective_flag(self, plans_dir: Path) -> None:
        from skills.exec_plan import main

        main([
            "init",
            "--title", "CLI Test",
            "--plan-id", "PLAN-001",
            "--objective", "CLI objective text",
        ])
        with (plans_dir / "PLAN-001.yaml").open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert data["objective"] == "CLI objective text"

    def test_cli_step_flag_repeated(self, plans_dir: Path) -> None:
        from skills.exec_plan import main

        main([
            "init",
            "--title", "CLI Test",
            "--plan-id", "PLAN-001",
            "--step", "First step",
            "--step", "Second step",
        ])
        with (plans_dir / "PLAN-001.yaml").open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert data["steps"] == ["First step", "Second step"]

    def test_cli_criterion_flag_repeated(self, plans_dir: Path) -> None:
        from skills.exec_plan import main

        main([
            "init",
            "--title", "CLI Test",
            "--plan-id", "PLAN-001",
            "--criterion", "Tests pass",
            "--criterion", "No lint errors",
        ])
        with (plans_dir / "PLAN-001.yaml").open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert data["completion_criteria"] == ["Tests pass", "No lint errors"]

    def test_cli_approach_flag(self, plans_dir: Path) -> None:
        from skills.exec_plan import main

        main([
            "init",
            "--title", "CLI Test",
            "--plan-id", "PLAN-001",
            "--approach", "Use dependency injection",
        ])
        with (plans_dir / "PLAN-001.yaml").open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert data["approach"] == "Use dependency injection"

    def test_cli_all_flags_together(self, plans_dir: Path) -> None:
        from skills.exec_plan import main

        main([
            "init",
            "--title", "Full CLI Test",
            "--plan-id", "PLAN-001",
            "--objective", "Full objective",
            "--approach", "Full approach",
            "--step", "Step A",
            "--step", "Step B",
            "--criterion", "Criterion X",
        ])
        with (plans_dir / "PLAN-001.yaml").open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert data["objective"] == "Full objective"
        assert data["approach"] == "Full approach"
        assert data["steps"] == ["Step A", "Step B"]
        assert data["completion_criteria"] == ["Criterion X"]
>>>>>>> feat/execution-plans-skill-generates-execution-plan-template
