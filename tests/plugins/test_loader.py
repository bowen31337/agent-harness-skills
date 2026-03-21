"""Tests for harness_skills.plugins.loader.load_plugin_gates."""

from __future__ import annotations

import logging

import pytest

from harness_skills.plugins.gate_plugin import PluginGateConfig
from harness_skills.plugins.loader import load_plugin_gates


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _profile(plugins) -> dict:
    """Build a minimal profile config dict with the given plugins value."""
    return {"gates": {"plugins": plugins}}


def _valid_plugin(**overrides) -> dict:
    base = {"gate_id": "my_gate", "gate_name": "My Gate", "command": "exit 0"}
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLoadPluginGates:
    def test_no_gates_key_returns_empty(self):
        result = load_plugin_gates({})
        assert result == []

    def test_no_plugins_key_returns_empty(self):
        result = load_plugin_gates({"gates": {}})
        assert result == []

    def test_plugins_none_returns_empty(self):
        result = load_plugin_gates({"gates": {"plugins": None}})
        assert result == []

    def test_empty_plugins_list_returns_empty(self):
        result = load_plugin_gates(_profile([]))
        assert result == []

    def test_single_valid_plugin(self):
        result = load_plugin_gates(_profile([_valid_plugin()]))
        assert len(result) == 1
        assert isinstance(result[0], PluginGateConfig)
        assert result[0].gate_id == "my_gate"

    def test_multiple_valid_plugins_returned_in_order(self):
        plugins = [
            _valid_plugin(gate_id="gate_a"),
            _valid_plugin(gate_id="gate_b"),
            _valid_plugin(gate_id="gate_c"),
        ]
        result = load_plugin_gates(_profile(plugins))
        assert [r.gate_id for r in result] == ["gate_a", "gate_b", "gate_c"]

    def test_invalid_entry_skipped(self, caplog):
        plugins = [
            _valid_plugin(gate_id="gate_a"),
            {"gate_id": "INVALID ID", "gate_name": "Bad", "command": "x"},  # bad gate_id
            _valid_plugin(gate_id="gate_b"),
        ]
        with caplog.at_level(logging.WARNING, logger="harness_skills.plugins.loader"):
            result = load_plugin_gates(_profile(plugins))
        assert [r.gate_id for r in result] == ["gate_a", "gate_b"]
        assert any("failed schema validation" in r.message for r in caplog.records)

    def test_non_mapping_entry_skipped(self, caplog):
        plugins = [
            _valid_plugin(gate_id="gate_a"),
            "not_a_dict",  # invalid
            _valid_plugin(gate_id="gate_b"),
        ]
        with caplog.at_level(logging.WARNING, logger="harness_skills.plugins.loader"):
            result = load_plugin_gates(_profile(plugins))
        assert [r.gate_id for r in result] == ["gate_a", "gate_b"]
        assert any("not a mapping" in r.message for r in caplog.records)

    def test_duplicate_gate_id_second_is_skipped(self, caplog):
        plugins = [
            _valid_plugin(gate_id="dup_gate", gate_name="First"),
            _valid_plugin(gate_id="dup_gate", gate_name="Second"),
        ]
        with caplog.at_level(logging.WARNING, logger="harness_skills.plugins.loader"):
            result = load_plugin_gates(_profile(plugins))
        assert len(result) == 1
        assert result[0].gate_name == "First"
        assert any("Duplicate" in r.message for r in caplog.records)

    def test_plugins_not_list_returns_empty(self, caplog):
        with caplog.at_level(logging.WARNING, logger="harness_skills.plugins.loader"):
            result = load_plugin_gates({"gates": {"plugins": "bad_value"}})
        assert result == []
        assert any("must be a list" in r.message for r in caplog.records)

    def test_gates_not_dict_returns_empty(self, caplog):
        with caplog.at_level(logging.WARNING, logger="harness_skills.plugins.loader"):
            result = load_plugin_gates({"gates": "bad_gates"})
        assert result == []

    def test_defaults_applied_when_optional_fields_omitted(self):
        plugins = [{"gate_id": "minimal", "gate_name": "Minimal", "command": "exit 0"}]
        result = load_plugin_gates(_profile(plugins))
        assert len(result) == 1
        cfg = result[0]
        assert cfg.timeout_seconds == 60
        assert cfg.fail_on_error is True
        assert cfg.severity == "error"
        assert cfg.env == {}

    def test_all_optional_fields_pass_through(self):
        plugins = [{
            "gate_id": "full_gate",
            "gate_name": "Full Gate",
            "command": "echo ok",
            "timeout_seconds": 120,
            "fail_on_error": False,
            "severity": "warning",
            "env": {"MY_VAR": "value"},
        }]
        result = load_plugin_gates(_profile(plugins))
        cfg = result[0]
        assert cfg.timeout_seconds == 120
        assert cfg.fail_on_error is False
        assert cfg.severity == "warning"
        assert cfg.env == {"MY_VAR": "value"}
