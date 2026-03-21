"""Tests for harness_skills.plugins.runner.run_plugin_gates."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from harness_skills.models.base import Status
from harness_skills.plugins.gate_plugin import PluginGateConfig
from harness_skills.plugins.runner import run_plugin_gates, _record_telemetry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EXIT_0 = "exit 0" if sys.platform != "win32" else "exit /b 0"
_EXIT_1 = "exit 1" if sys.platform != "win32" else "exit /b 1"


def _cfg(gate_id: str = "g", command: str = _EXIT_0, **kwargs) -> PluginGateConfig:
    return PluginGateConfig.model_validate({
        "gate_id": gate_id,
        "gate_name": gate_id.replace("_", " ").title(),
        "command": command,
        **kwargs,
    })


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRunPluginGates:
    def test_empty_list_returns_empty(self):
        assert run_plugin_gates([]) == []

    def test_single_passing_gate(self):
        results = run_plugin_gates([_cfg(command=_EXIT_0)])
        assert len(results) == 1
        assert results[0].status == Status.PASSED

    def test_single_failing_gate(self):
        results = run_plugin_gates([_cfg(command=_EXIT_1)])
        assert len(results) == 1
        assert results[0].status == Status.FAILED

    def test_all_gates_run_even_after_failure(self):
        """A failed gate must not stop subsequent gates from executing."""
        gates = [
            _cfg(gate_id="gate_a", command=_EXIT_1, fail_on_error=True),
            _cfg(gate_id="gate_b", command=_EXIT_0),
        ]
        results = run_plugin_gates(gates)
        assert len(results) == 2
        assert results[0].status == Status.FAILED
        assert results[1].status == Status.PASSED

    def test_results_in_declaration_order(self):
        """Results must appear in the same order as the input gates list."""
        gates = [
            _cfg(gate_id="first", command=_EXIT_0),
            _cfg(gate_id="second", command=_EXIT_1),
            _cfg(gate_id="third", command=_EXIT_0),
        ]
        results = run_plugin_gates(gates)
        assert [r.gate_id for r in results] == ["first", "second", "third"]

    def test_gate_ids_propagated(self):
        gates = [_cfg(gate_id="my_gate")]
        results = run_plugin_gates(gates)
        assert results[0].gate_id == "my_gate"

    def test_telemetry_called_for_failing_gate(self):
        """_record_telemetry must be called once per failed gate."""
        with patch("harness_skills.plugins.runner._record_telemetry") as mock_tel:
            gates = [_cfg(command=_EXIT_1, fail_on_error=True)]
            run_plugin_gates(gates)
        mock_tel.assert_called_once()

    def test_telemetry_called_for_warning_gate(self):
        """_record_telemetry must also be called for WARNING status gates."""
        with patch("harness_skills.plugins.runner._record_telemetry") as mock_tel:
            gates = [_cfg(command=_EXIT_1, fail_on_error=False)]
            run_plugin_gates(gates)
        mock_tel.assert_called_once()

    def test_telemetry_not_called_for_passing_gate(self):
        """_record_telemetry must NOT be called when all gates pass."""
        with patch("harness_skills.plugins.runner._record_telemetry") as mock_tel:
            gates = [_cfg(command=_EXIT_0)]
            run_plugin_gates(gates)
        mock_tel.assert_not_called()

    def test_telemetry_error_does_not_propagate(self):
        """An exception inside _record_telemetry must not surface to callers."""
        with patch(
            "harness_skills.plugins.runner._record_telemetry",
            side_effect=RuntimeError("telemetry exploded"),
        ):
            gates = [_cfg(command=_EXIT_1)]
            # Should not raise — result list still returned correctly
            results = run_plugin_gates(gates)
        assert len(results) == 1
        assert results[0].status == Status.FAILED

    def test_multiple_failures_each_call_telemetry(self):
        """Each failing gate triggers its own telemetry call."""
        with patch("harness_skills.plugins.runner._record_telemetry") as mock_tel:
            gates = [
                _cfg(gate_id="fail_a", command=_EXIT_1),
                _cfg(gate_id="fail_b", command=_EXIT_1),
                _cfg(gate_id="pass_c", command=_EXIT_0),
            ]
            run_plugin_gates(gates)
        assert mock_tel.call_count == 2


class TestRecordTelemetry:
    def test_increments_session_gates_counter(self, tmp_path):
        """_record_telemetry should increment the session gate counter."""
        from harness_skills.telemetry import HarnessTelemetry
        import harness_skills.plugins.runner as runner_module

        tel = HarnessTelemetry(output_path=str(tmp_path / "telemetry.json"))
        tel._start_session("test-session")

        with patch(
            "harness_skills.plugins.runner._get_shared", return_value=tel
        ):
            cfg = _cfg(gate_id="tracked_gate", command=_EXIT_1)
            # Build a minimal GateResult to pass in
            from harness_skills.models.base import GateResult
            result = GateResult(
                gate_id=cfg.gate_id,
                gate_name=cfg.gate_name,
                status=Status.FAILED,
                message="Gate failed.",
            )
            _record_telemetry(cfg, result)

        assert tel._session_gates["tracked_gate"] == 1

    def test_telemetry_flush_called(self, tmp_path):
        """_record_telemetry should flush telemetry to disk."""
        from harness_skills.telemetry import HarnessTelemetry
        from harness_skills.models.base import GateResult

        tel = HarnessTelemetry(output_path=str(tmp_path / "telemetry.json"))
        tel._start_session("test-session")

        with patch("harness_skills.plugins.runner._get_shared", return_value=tel):
            with patch.object(tel, "flush") as mock_flush:
                cfg = _cfg(gate_id="g2")
                result = GateResult(
                    gate_id=cfg.gate_id,
                    gate_name=cfg.gate_name,
                    status=Status.FAILED,
                    message="Gate failed.",
                )
                _record_telemetry(cfg, result)
        mock_flush.assert_called_once()
