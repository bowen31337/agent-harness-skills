"""Tests for PluginGateConfig and PluginGateRunner."""

from __future__ import annotations

import os
import sys

import pytest
from pydantic import ValidationError

from harness_skills.models.base import Status
from harness_skills.plugins.gate_plugin import PluginGateConfig, PluginGateRunner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**overrides) -> PluginGateConfig:
    """Return a minimal valid PluginGateConfig, with any field overridden."""
    defaults = {
        "gate_id": "sample_gate",
        "gate_name": "Sample Gate",
        "command": "exit 0",
    }
    defaults.update(overrides)
    return PluginGateConfig.model_validate(defaults)


# ---------------------------------------------------------------------------
# PluginGateConfig — validation
# ---------------------------------------------------------------------------


class TestPluginGateConfigValidation:
    def test_valid_full_config(self):
        cfg = PluginGateConfig.model_validate({
            "gate_id": "check_migrations",
            "gate_name": "DB Migration Safety",
            "command": "python scripts/check.py",
            "timeout_seconds": 30,
            "fail_on_error": True,
            "severity": "error",
            "env": {"DATABASE_URL": "${DATABASE_URL}"},
        })
        assert cfg.gate_id == "check_migrations"
        assert cfg.gate_name == "DB Migration Safety"
        assert cfg.timeout_seconds == 30
        assert cfg.fail_on_error is True
        assert cfg.severity == "error"
        assert cfg.env == {"DATABASE_URL": "${DATABASE_URL}"}

    def test_defaults_applied(self):
        cfg = _make_config()
        assert cfg.timeout_seconds == 60
        assert cfg.fail_on_error is True
        assert cfg.severity == "error"
        assert cfg.env == {}

    def test_gate_id_invalid_uppercase(self):
        with pytest.raises(ValidationError, match="gate_id"):
            PluginGateConfig.model_validate({"gate_id": "MyGate", "gate_name": "x", "command": "x"})

    def test_gate_id_invalid_starts_with_digit(self):
        with pytest.raises(ValidationError, match="gate_id"):
            PluginGateConfig.model_validate({"gate_id": "1gate", "gate_name": "x", "command": "x"})

    def test_gate_id_invalid_has_spaces(self):
        with pytest.raises(ValidationError, match="gate_id"):
            PluginGateConfig.model_validate({"gate_id": "my gate", "gate_name": "x", "command": "x"})

    def test_gate_id_valid_with_underscores_digits(self):
        cfg = _make_config(gate_id="check_api_v2")
        assert cfg.gate_id == "check_api_v2"

    def test_gate_name_empty_raises(self):
        with pytest.raises(ValidationError, match="gate_name"):
            PluginGateConfig.model_validate({"gate_id": "g", "gate_name": "   ", "command": "x"})

    def test_gate_name_stripped(self):
        cfg = _make_config(gate_name="  My Gate  ")
        assert cfg.gate_name == "My Gate"

    def test_command_empty_raises(self):
        with pytest.raises(ValidationError, match="command"):
            PluginGateConfig.model_validate({"gate_id": "g", "gate_name": "G", "command": "  "})

    def test_command_stripped(self):
        cfg = _make_config(command="  echo hi  ")
        assert cfg.command == "echo hi"

    def test_unknown_field_raises(self):
        with pytest.raises(ValidationError):
            PluginGateConfig.model_validate({
                "gate_id": "g", "gate_name": "G", "command": "x", "unknown_key": True,
            })

    def test_severity_warning_accepted(self):
        cfg = _make_config(severity="warning")
        assert cfg.severity == "warning"

    def test_severity_info_accepted(self):
        cfg = _make_config(severity="info")
        assert cfg.severity == "info"

    def test_severity_invalid_raises(self):
        with pytest.raises(ValidationError):
            _make_config(severity="critical")  # not in Literal union

    def test_timeout_minimum_enforced(self):
        with pytest.raises(ValidationError):
            _make_config(timeout_seconds=0)

    def test_timeout_maximum_enforced(self):
        with pytest.raises(ValidationError):
            _make_config(timeout_seconds=3601)


# ---------------------------------------------------------------------------
# PluginGateRunner — execution
# ---------------------------------------------------------------------------


# Cross-platform exit-0 / exit-1 commands
_EXIT_0 = "exit 0" if sys.platform != "win32" else "exit /b 0"
_EXIT_1 = "exit 1" if sys.platform != "win32" else "exit /b 1"
_SLEEP_10 = "sleep 10" if sys.platform != "win32" else "timeout 10"


class TestPluginGateRunner:
    def test_passes_on_exit_zero(self):
        cfg = _make_config(command=_EXIT_0)
        result = PluginGateRunner(cfg).run()
        assert result.status == Status.PASSED
        assert result.violations == []
        assert result.gate_id == "sample_gate"

    def test_fails_on_exit_nonzero_fail_on_error_true(self):
        cfg = _make_config(command=_EXIT_1, fail_on_error=True)
        result = PluginGateRunner(cfg).run()
        assert result.status == Status.FAILED
        assert len(result.violations) == 1
        assert "exit_nonzero" in result.violations[0].rule_id

    def test_warning_on_exit_nonzero_fail_on_error_false(self):
        cfg = _make_config(command=_EXIT_1, fail_on_error=False)
        result = PluginGateRunner(cfg).run()
        assert result.status == Status.WARNING
        assert len(result.violations) == 1

    def test_timeout_produces_failed_when_fail_on_error(self):
        cfg = _make_config(command=_SLEEP_10, timeout_seconds=1, fail_on_error=True)
        result = PluginGateRunner(cfg).run()
        assert result.status == Status.FAILED
        assert any("timeout" in v.rule_id for v in result.violations)

    def test_timeout_produces_warning_when_not_fail_on_error(self):
        cfg = _make_config(command=_SLEEP_10, timeout_seconds=1, fail_on_error=False)
        result = PluginGateRunner(cfg).run()
        assert result.status == Status.WARNING

    def test_duration_ms_recorded_on_pass(self):
        cfg = _make_config(command=_EXIT_0)
        result = PluginGateRunner(cfg).run()
        assert result.duration_ms is not None
        assert result.duration_ms >= 0

    def test_duration_ms_recorded_on_fail(self):
        cfg = _make_config(command=_EXIT_1)
        result = PluginGateRunner(cfg).run()
        assert result.duration_ms is not None
        assert result.duration_ms >= 0

    def test_env_override_visible_in_subprocess(self):
        """An env var set in the gate config must be visible to the subprocess."""
        if sys.platform == "win32":
            cmd = "if not defined HARNESS_TEST_VAR (exit 1)"
        else:
            cmd = 'test "$HARNESS_TEST_VAR" = "hello"'
        cfg = _make_config(command=cmd, env={"HARNESS_TEST_VAR": "hello"})
        result = PluginGateRunner(cfg).run()
        assert result.status == Status.PASSED

    def test_env_var_expansion(self):
        """${VAR} references in env values should be expanded from os.environ."""
        os.environ["_HARNESS_EXPAND_SRC"] = "expanded_value"
        if sys.platform == "win32":
            cmd = "if not defined HARNESS_EXPANDED_DEST (exit 1)"
        else:
            cmd = 'test "$HARNESS_EXPANDED_DEST" = "expanded_value"'
        cfg = _make_config(
            command=cmd,
            env={"HARNESS_EXPANDED_DEST": "${_HARNESS_EXPAND_SRC}"},
        )
        result = PluginGateRunner(cfg).run()
        assert result.status == Status.PASSED
        del os.environ["_HARNESS_EXPAND_SRC"]

    def test_severity_propagates_to_violation(self):
        cfg = _make_config(command=_EXIT_1, severity="warning")
        result = PluginGateRunner(cfg).run()
        assert len(result.violations) == 1
        assert result.violations[0].severity == "warning"

    def test_output_truncated_in_violation_message(self):
        """Output longer than 500 chars must be truncated in the violation message."""
        long_output = "x" * 600
        if sys.platform == "win32":
            cmd = f"echo {long_output} && exit 1"
        else:
            cmd = f"echo '{long_output}'; exit 1"
        cfg = _make_config(command=cmd, fail_on_error=True)
        result = PluginGateRunner(cfg).run()
        assert len(result.violations) == 1
        # The violation message must not exceed the truncation boundary (+ellipsis)
        assert len(result.violations[0].message) <= 700  # generous upper bound

    def test_gate_result_gate_id_matches_config(self):
        cfg = _make_config(gate_id="my_custom_gate", command=_EXIT_0)
        result = PluginGateRunner(cfg).run()
        assert result.gate_id == "my_custom_gate"

    def test_gate_result_gate_name_matches_config(self):
        cfg = _make_config(gate_name="My Custom Gate", command=_EXIT_0)
        result = PluginGateRunner(cfg).run()
        assert result.gate_name == "My Custom Gate"
