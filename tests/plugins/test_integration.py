"""Integration tests: full pipeline from YAML config → GateResult list."""

from __future__ import annotations

import sys
import textwrap

import pytest
import yaml

from harness_skills.models.base import Status
from harness_skills.models.evaluate import EvaluateResponse
from harness_skills.plugins.loader import load_plugin_gates
from harness_skills.plugins.runner import run_plugin_gates


_EXIT_0 = "exit 0" if sys.platform != "win32" else "exit /b 0"
_EXIT_1 = "exit 1" if sys.platform != "win32" else "exit /b 1"


def _load_config(yaml_text: str) -> dict:
    return yaml.safe_load(textwrap.dedent(yaml_text))


# ---------------------------------------------------------------------------
# Integration: YAML → load → run
# ---------------------------------------------------------------------------


class TestFullPipeline:
    def test_single_passing_gate_end_to_end(self):
        raw = f"""
        active_profile: starter
        profiles:
          starter:
            gates:
              build:
                enabled: true
              plugins:
                - gate_id: smoke_check
                  gate_name: "Smoke Check"
                  command: "{_EXIT_0}"
        """
        config = _load_config(raw)
        profile_config = config["profiles"][config["active_profile"]]
        gates = load_plugin_gates(profile_config)
        results = run_plugin_gates(gates)

        assert len(results) == 1
        assert results[0].gate_id == "smoke_check"
        assert results[0].status == Status.PASSED

    def test_passing_gate_feeds_into_evaluate_response(self):
        raw = f"""
        active_profile: starter
        profiles:
          starter:
            gates:
              plugins:
                - gate_id: api_lint
                  gate_name: "API Lint"
                  command: "{_EXIT_0}"
        """
        config = _load_config(raw)
        profile_config = config["profiles"][config["active_profile"]]
        gates = load_plugin_gates(profile_config)
        plugin_results = run_plugin_gates(gates)

        response = EvaluateResponse(
            status=Status.PASSED,
            gates=plugin_results,
        )
        assert response.total_gates == 1
        assert response.passed_gates == 1
        assert response.failed_gates == 0

    def test_failing_gate_feeds_into_evaluate_response(self):
        raw = f"""
        active_profile: starter
        profiles:
          starter:
            gates:
              plugins:
                - gate_id: bad_gate
                  gate_name: "Bad Gate"
                  command: "{_EXIT_1}"
                  fail_on_error: true
        """
        config = _load_config(raw)
        profile_config = config["profiles"][config["active_profile"]]
        gates = load_plugin_gates(profile_config)
        plugin_results = run_plugin_gates(gates)

        response = EvaluateResponse(
            status=Status.FAILED,
            message="One or more plugin gates failed.",
            gates=plugin_results,
        )
        assert response.failed_gates == 1
        assert response.passed_gates == 0

    def test_profile_isolation_starter_vs_advanced(self):
        """Gates in the advanced profile must NOT load when starter is active."""
        raw = f"""
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
                  command: "{_EXIT_0}"
        """
        config = _load_config(raw)
        active = config["active_profile"]
        profile_config = config["profiles"][active]
        gates = load_plugin_gates(profile_config)
        assert len(gates) == 1
        assert gates[0].gate_id == "starter_gate"

    def test_multiple_profiles_each_have_own_plugins(self):
        raw = f"""
        profiles:
          starter:
            gates:
              plugins:
                - gate_id: gate_s
                  gate_name: "Starter"
                  command: "{_EXIT_0}"
          advanced:
            gates:
              plugins:
                - gate_id: gate_a1
                  gate_name: "Advanced 1"
                  command: "{_EXIT_0}"
                - gate_id: gate_a2
                  gate_name: "Advanced 2"
                  command: "{_EXIT_0}"
        """
        config = _load_config(raw)
        starter_gates = load_plugin_gates(config["profiles"]["starter"])
        advanced_gates = load_plugin_gates(config["profiles"]["advanced"])

        assert [g.gate_id for g in starter_gates] == ["gate_s"]
        assert [g.gate_id for g in advanced_gates] == ["gate_a1", "gate_a2"]

    def test_empty_plugins_list_in_yaml(self):
        raw = """
        profiles:
          starter:
            gates:
              plugins: []
        """
        config = _load_config(raw)
        gates = load_plugin_gates(config["profiles"]["starter"])
        assert gates == []
        results = run_plugin_gates(gates)
        assert results == []

    def test_real_harness_config_yaml_loads_without_error(self):
        """The actual harness.config.yaml (with plugins: []) must parse cleanly."""
        import pathlib
        config_path = (
            pathlib.Path(__file__).parent.parent.parent / "harness.config.yaml"
        )
        assert config_path.exists(), "harness.config.yaml not found"

        with open(config_path) as f:
            config = yaml.safe_load(f)

        active = config.get("active_profile", "starter")
        profile_config = config["profiles"][active]
        gates = load_plugin_gates(profile_config)

        # The shipped config has plugins: [] — expect empty list, no errors
        assert isinstance(gates, list)
        # Running an empty list must also succeed
        results = run_plugin_gates(gates)
        assert results == []
