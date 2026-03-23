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
