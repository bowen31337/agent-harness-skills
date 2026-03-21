"""
tests/gates/test_runner_plugin_integration.py
=============================================
Integration tests for plugin gate execution through :class:`GateEvaluator`.

Tests that custom ``plugins:`` entries defined in ``harness.config.yaml``
are loaded, validated, and executed as part of the normal gate evaluation
pipeline — contributing to the final :class:`EvaluationSummary`.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest
import yaml

from harness_skills.gates.runner import GateEvaluator, run_gates, EvaluationSummary


# ---------------------------------------------------------------------------
# Platform-safe exit commands
# ---------------------------------------------------------------------------

_EXIT_0 = "exit 0" if sys.platform != "win32" else "exit /b 0"
_EXIT_1 = "exit 1" if sys.platform != "win32" else "exit /b 1"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_config(tmp_path: Path, yaml_text: str) -> Path:
    """Write a harness.config.yaml to *tmp_path* and return its path."""
    cfg_file = tmp_path / "harness.config.yaml"
    cfg_file.write_text(textwrap.dedent(yaml_text))
    return cfg_file


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGateEvaluatorPluginIntegration:
    """Plugin gates run end-to-end through GateEvaluator."""

    def test_passing_plugin_gate_contributes_to_summary(self, tmp_path):
        """A plugin gate that exits 0 should appear as passed in the summary."""
        cfg = _write_config(
            tmp_path,
            f"""
            active_profile: starter
            profiles:
              starter:
                gates:
                  plugins:
                    - gate_id: smoke_check
                      gate_name: "Smoke Check"
                      command: "{_EXIT_0}"
            """,
        )
        evaluator = GateEvaluator(project_root=tmp_path, config_path=cfg)
        # Only run plugin gates (no built-in gate IDs passed) — pass empty list
        summary = evaluator.run(gate_ids=[], profile="starter")

        assert summary.total_gates == 1
        assert summary.passed_gates == 1
        assert summary.failed_gates == 0
        assert summary.passed is True

    def test_failing_plugin_gate_blocks_summary(self, tmp_path):
        """A plugin gate that exits non-zero (fail_on_error: true) should fail the run."""
        cfg = _write_config(
            tmp_path,
            f"""
            active_profile: starter
            profiles:
              starter:
                gates:
                  plugins:
                    - gate_id: bad_gate
                      gate_name: "Bad Gate"
                      command: "{_EXIT_1}"
                      fail_on_error: true
            """,
        )
        evaluator = GateEvaluator(project_root=tmp_path, config_path=cfg)
        summary = evaluator.run(gate_ids=[], profile="starter")

        assert summary.failed_gates == 1
        assert summary.passed is False
        assert summary.blocking_failures == 1

    def test_advisory_plugin_gate_does_not_block_summary(self, tmp_path):
        """A plugin gate with fail_on_error: false should not block the run."""
        cfg = _write_config(
            tmp_path,
            f"""
            active_profile: starter
            profiles:
              starter:
                gates:
                  plugins:
                    - gate_id: advisory_check
                      gate_name: "Advisory Check"
                      command: "{_EXIT_1}"
                      fail_on_error: false
                      severity: warning
            """,
        )
        evaluator = GateEvaluator(project_root=tmp_path, config_path=cfg)
        summary = evaluator.run(gate_ids=[], profile="starter")

        # Advisory gate: non-zero exit → Status.WARNING → treated as "passed"
        assert summary.passed is True
        assert summary.failed_gates == 0

    def test_multiple_plugin_gates_all_passing(self, tmp_path):
        """Multiple passing plugin gates should all appear in the summary."""
        cfg = _write_config(
            tmp_path,
            f"""
            active_profile: starter
            profiles:
              starter:
                gates:
                  plugins:
                    - gate_id: gate_a
                      gate_name: "Gate A"
                      command: "{_EXIT_0}"
                    - gate_id: gate_b
                      gate_name: "Gate B"
                      command: "{_EXIT_0}"
                    - gate_id: gate_c
                      gate_name: "Gate C"
                      command: "{_EXIT_0}"
            """,
        )
        evaluator = GateEvaluator(project_root=tmp_path, config_path=cfg)
        summary = evaluator.run(gate_ids=[], profile="starter")

        assert summary.total_gates == 3
        assert summary.passed_gates == 3
        assert summary.passed is True

    def test_empty_plugins_list_produces_no_extra_gates(self, tmp_path):
        """An empty plugins: [] should not add any gate outcomes."""
        cfg = _write_config(
            tmp_path,
            """
            active_profile: starter
            profiles:
              starter:
                gates:
                  plugins: []
            """,
        )
        evaluator = GateEvaluator(project_root=tmp_path, config_path=cfg)
        summary = evaluator.run(gate_ids=[], profile="starter")

        assert summary.total_gates == 0
        assert summary.passed is True

    def test_plugin_failure_recorded_in_failures_list(self, tmp_path):
        """A failing plugin gate's violation should appear in summary.failures."""
        cfg = _write_config(
            tmp_path,
            f"""
            active_profile: starter
            profiles:
              starter:
                gates:
                  plugins:
                    - gate_id: check_lint
                      gate_name: "Lint Check"
                      command: "{_EXIT_1}"
                      fail_on_error: true
                      severity: error
            """,
        )
        evaluator = GateEvaluator(project_root=tmp_path, config_path=cfg)
        summary = evaluator.run(gate_ids=[], profile="starter")

        assert len(summary.failures) == 1
        failure = summary.failures[0]
        assert failure.gate_id == "check_lint"
        assert failure.severity == "error"

    def test_profile_isolation_only_active_profile_runs(self, tmp_path):
        """Plugin gates from inactive profiles must not execute."""
        cfg = _write_config(
            tmp_path,
            f"""
            active_profile: starter
            profiles:
              starter:
                gates:
                  plugins:
                    - gate_id: starter_gate
                      gate_name: "Starter Gate"
                      command: "{_EXIT_0}"
              advanced:
                gates:
                  plugins:
                    - gate_id: advanced_gate
                      gate_name: "Advanced Gate"
                      command: "{_EXIT_1}"
                      fail_on_error: true
            """,
        )
        evaluator = GateEvaluator(project_root=tmp_path, config_path=cfg)
        # Explicitly request starter profile
        summary = evaluator.run(gate_ids=[], profile="starter")

        assert summary.total_gates == 1
        assert summary.passed is True
        gate_ids = [o.gate_id for o in summary.outcomes]
        assert "starter_gate" in gate_ids
        assert "advanced_gate" not in gate_ids

    def test_run_gates_convenience_function_includes_plugins(self, tmp_path):
        """The top-level run_gates() helper must also execute plugin gates."""
        cfg = _write_config(
            tmp_path,
            f"""
            active_profile: starter
            profiles:
              starter:
                gates:
                  plugins:
                    - gate_id: api_health
                      gate_name: "API Health"
                      command: "{_EXIT_0}"
            """,
        )
        summary = run_gates(
            project_root=tmp_path,
            config_path=cfg,
            gate_ids=[],
            profile="starter",
        )

        assert summary.total_gates == 1
        assert summary.passed is True
        assert summary.outcomes[0].gate_id == "api_health"
