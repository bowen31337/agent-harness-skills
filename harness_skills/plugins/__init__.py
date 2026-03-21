"""
harness_skills/plugins
======================
Custom evaluation gate plugin system.

Engineers define project-specific gates entirely in ``harness.config.yaml``
under each profile's ``gates.plugins`` list — no Python changes required.

Public API
----------
    load_plugin_gates(profile_config)  → list[PluginGateConfig]
    run_plugin_gates(gates)            → list[GateResult]
    PluginGateConfig                   — validated gate descriptor
    PluginGateRunner                   — single-gate executor
"""

from harness_skills.plugins.gate_plugin import PluginGateConfig, PluginGateRunner
from harness_skills.plugins.loader import load_plugin_gates
from harness_skills.plugins.runner import run_plugin_gates

__all__ = [
    "PluginGateConfig",
    "PluginGateRunner",
    "load_plugin_gates",
    "run_plugin_gates",
]
