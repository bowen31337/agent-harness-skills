"""Run a list of plugin gates sequentially."""
from __future__ import annotations
import logging
from harness_skills.models.base import GateResult, Status
from harness_skills.plugins.gate_plugin import PluginGateConfig, PluginGateRunner

logger = logging.getLogger("harness_skills.plugins.runner")


def _get_shared():
    from harness_skills.telemetry import HarnessTelemetry
    return HarnessTelemetry._get_shared()


def _record_telemetry(cfg: PluginGateConfig, result: GateResult) -> None:
    try:
        tel = _get_shared()
        tel._session_gates[cfg.gate_id] = tel._session_gates.get(cfg.gate_id, 0) + 1
        tel.flush()
    except Exception:
        pass


def run_plugin_gates(gates: list[PluginGateConfig]) -> list[GateResult]:
    results = []
    for cfg in gates:
        result = PluginGateRunner(cfg).run()
        if result.status in (Status.FAILED, Status.WARNING):
            try:
                _record_telemetry(cfg, result)
            except Exception:
                pass
        results.append(result)
    return results
