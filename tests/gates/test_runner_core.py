"""Tests for harness_skills.gates.runner — config loading, check functions, evaluator.

Covers the uncovered lines: HarnessConfigLoader, dataclass properties,
_plugin_result_to_outcome, GateEvaluator.run(), individual check functions,
and _resolve_layer_definitions.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from harness_skills.gates.runner import (
    EvaluationSummary,
    GateEvaluator,
    GateFailure,
    GateOutcome,
    HarnessConfigLoader,
    _plugin_result_to_outcome,
    _resolve_layer_definitions,
    _run_cmd,
    _repo_rel,
    check_architecture,
    check_coverage,
    check_docs_freshness,
    check_lint,
    check_performance,
    check_principles,
    check_regression,
    check_security,
    check_types,
    run_gates,
)
from harness_skills.models.base import GateResult, Status, Violation
from harness_skills.models.gate_configs import (
    ArchitectureGateConfig,
    CoverageGateConfig,
    DocsFreshnessGateConfig,
    LintGateConfig,
    PerformanceGateConfig,
    PrinciplesGateConfig,
    RegressionGateConfig,
    SecurityGateConfig,
    TypesGateConfig,
)


# ── Dataclass properties ────────────────────────────────────────────────────


class TestDataclassProperties:
    def test_gate_outcome_passed(self):
        o = GateOutcome(gate_id="test", status="passed")
        assert o.passed is True
        assert o.skipped is False

    def test_gate_outcome_skipped(self):
        o = GateOutcome(gate_id="test", status="skipped")
        assert o.skipped is True
        assert o.passed is False

    def test_gate_outcome_failed(self):
        o = GateOutcome(gate_id="test", status="failed")
        assert o.passed is False
        assert o.skipped is False

    def test_evaluation_summary_str_passed(self):
        s = EvaluationSummary(
            passed=True, total_gates=3, passed_gates=2,
            skipped_gates=1, blocking_failures=0,
        )
        text = str(s)
        assert "PASSED" in text
        assert "2/3" in text

    def test_evaluation_summary_str_failed(self):
        s = EvaluationSummary(
            passed=False, total_gates=3, passed_gates=1,
            failed_gates=2, blocking_failures=1,
        )
        text = str(s)
        assert "FAILED" in text


# ── _plugin_result_to_outcome ────────────────────────────────────────────────


class TestPluginResultToOutcome:
    def test_passed_result(self):
        result = GateResult(
            gate_id="custom", gate_name="Custom Gate",
            status=Status.PASSED, duration_ms=100, violations=[],
        )
        outcome = _plugin_result_to_outcome(result)
        assert outcome.status == "passed"
        assert outcome.gate_id == "custom"

    def test_failed_result_with_violations(self):
        v = Violation(
            rule_id="R001", severity="error",
            message="bad code", file_path="a.py",
            line_number=10, suggestion="fix it",
        )
        result = GateResult(
            gate_id="lint", gate_name="Lint",
            status=Status.FAILED, violations=[v],
        )
        outcome = _plugin_result_to_outcome(result)
        assert outcome.status == "failed"
        assert len(outcome.failures) == 1
        assert outcome.failures[0].rule_id == "R001"

    def test_warning_treated_as_passed(self):
        result = GateResult(
            gate_id="advisory", gate_name="Advisory",
            status=Status.WARNING,
        )
        outcome = _plugin_result_to_outcome(result)
        assert outcome.status == "passed"

    def test_skipped_result(self):
        result = GateResult(
            gate_id="skip", gate_name="Skip",
            status=Status.SKIPPED,
        )
        outcome = _plugin_result_to_outcome(result)
        assert outcome.status == "skipped"

    def test_running_result(self):
        result = GateResult(
            gate_id="run", gate_name="Run",
            status=Status.RUNNING,
        )
        outcome = _plugin_result_to_outcome(result)
        assert outcome.status == "skipped"

    def test_no_duration(self):
        result = GateResult(
            gate_id="g", gate_name="G",
            status=Status.PASSED, duration_ms=None,
        )
        outcome = _plugin_result_to_outcome(result)
        assert outcome.duration_ms == 0

    def test_no_message(self):
        result = GateResult(
            gate_id="g", gate_name="G",
            status=Status.PASSED, message=None,
        )
        outcome = _plugin_result_to_outcome(result)
        assert "plugin/g" in outcome.message


# ── HarnessConfigLoader ─────────────────────────────────────────────────────


class TestHarnessConfigLoader:
    def test_missing_config_uses_defaults(self, tmp_path):
        loader = HarnessConfigLoader(tmp_path / "nonexistent.yaml")
        assert loader.active_profile == "starter"
        cfgs = loader.gate_configs()
        assert "coverage" in cfgs
        assert "regression" in cfgs

    def test_loads_valid_yaml(self, tmp_path):
        cfg_file = tmp_path / "harness.config.yaml"
        cfg_file.write_text(yaml.dump({
            "active_profile": "advanced",
            "profiles": {
                "advanced": {
                    "gates": {
                        "coverage": {"threshold": 90, "enabled": True},
                    }
                }
            }
        }))
        loader = HarnessConfigLoader(cfg_file)
        assert loader.active_profile == "advanced"
        cfgs = loader.gate_configs()
        assert cfgs["coverage"].threshold == 90

    def test_malformed_yaml_raises(self, tmp_path):
        cfg_file = tmp_path / "bad.yaml"
        cfg_file.write_text(": : : invalid yaml {{{")
        loader = HarnessConfigLoader(cfg_file)
        with pytest.raises(ValueError, match="Failed to parse"):
            loader.active_profile

    def test_profile_not_in_profiles_returns_defaults(self, tmp_path):
        cfg_file = tmp_path / "harness.config.yaml"
        cfg_file.write_text(yaml.dump({
            "active_profile": "nonexistent",
            "profiles": {}
        }))
        loader = HarnessConfigLoader(cfg_file)
        cfgs = loader.gate_configs()
        assert "coverage" in cfgs

    def test_gate_configs_yaml_override(self, tmp_path):
        cfg_file = tmp_path / "harness.config.yaml"
        cfg_file.write_text(yaml.dump({
            "active_profile": "starter",
            "profiles": {
                "starter": {
                    "gates": {
                        "coverage": {"threshold": 75, "enabled": False},
                    }
                }
            }
        }))
        loader = HarnessConfigLoader(cfg_file)
        cfgs = loader.gate_configs("starter")
        assert cfgs["coverage"].threshold == 75
        assert cfgs["coverage"].enabled is False

    def test_plugin_gates_empty(self, tmp_path):
        cfg_file = tmp_path / "harness.config.yaml"
        cfg_file.write_text(yaml.dump({
            "active_profile": "starter",
            "profiles": {"starter": {"gates": {}}}
        }))
        loader = HarnessConfigLoader(cfg_file)
        assert loader.plugin_gates() == []

    def test_plugin_gates_list(self, tmp_path):
        cfg_file = tmp_path / "harness.config.yaml"
        cfg_file.write_text(yaml.dump({
            "active_profile": "starter",
            "profiles": {
                "starter": {
                    "gates": {
                        "plugins": [
                            {"gate_id": "custom", "command": "echo ok"}
                        ]
                    }
                }
            }
        }))
        loader = HarnessConfigLoader(cfg_file)
        plugins = loader.plugin_gates()
        assert len(plugins) == 1

    def test_ensure_loaded_caches(self, tmp_path):
        cfg_file = tmp_path / "harness.config.yaml"
        cfg_file.write_text(yaml.dump({"active_profile": "starter"}))
        loader = HarnessConfigLoader(cfg_file)
        loader._ensure_loaded()
        assert loader._loaded is True
        loader._ensure_loaded()  # second call is no-op


# ── _resolve_layer_definitions ───────────────────────────────────────────────


class TestResolveLayerDefinitions:
    def test_explicit_layer_definitions(self):
        cfg = ArchitectureGateConfig(
            layer_definitions=[
                {"name": "domain", "rank": 0, "aliases": ["core"]},
                {"name": "infra", "rank": 1, "aliases": []},
            ]
        )
        result = _resolve_layer_definitions(cfg)
        assert len(result) == 2
        assert result[0]["name"] == "domain"
        assert result[0]["aliases"] == ["core"]

    def test_arch_style_preset(self):
        cfg = ArchitectureGateConfig(arch_style="hexagonal")
        result = _resolve_layer_definitions(cfg)
        assert len(result) > 0

    def test_unknown_arch_style_falls_back_to_layer_order(self):
        cfg = ArchitectureGateConfig(
            arch_style="nonexistent_style",
            layer_order=["models", "services", "routes"],
        )
        result = _resolve_layer_definitions(cfg)
        assert len(result) == 3
        assert result[0]["name"] == "models"

    def test_default_layer_order(self):
        cfg = ArchitectureGateConfig()
        result = _resolve_layer_definitions(cfg)
        assert len(result) > 0
        for item in result:
            assert "name" in item
            assert "rank" in item
            assert "aliases" in item


# ── _run_cmd and _repo_rel helpers ──────────────────────────────────────────


class TestHelpers:
    def test_run_cmd(self, tmp_path):
        rc, stdout, stderr = _run_cmd(
            [sys.executable, "-c", "print('hello')"], cwd=tmp_path
        )
        assert rc == 0
        assert "hello" in stdout

    def test_repo_rel_inside(self, tmp_path):
        path = tmp_path / "sub" / "file.py"
        assert _repo_rel(path, tmp_path) == "sub/file.py"

    def test_repo_rel_outside(self, tmp_path):
        path = Path("/some/other/file.py")
        result = _repo_rel(path, tmp_path)
        assert result == "/some/other/file.py"


# ── check_regression ────────────────────────────────────────────────────────


class TestCheckRegression:
    def test_passing_tests(self, tmp_path):
        cfg = RegressionGateConfig(extra_args=[], timeout_seconds=60)
        test_file = tmp_path / "test_sample.py"
        test_file.write_text("def test_ok(): pass\n")
        failures = check_regression(tmp_path, cfg)
        assert failures == []

    def test_timeout(self, tmp_path):
        cfg = RegressionGateConfig(extra_args=[], timeout_seconds=0.001)
        test_file = tmp_path / "test_slow.py"
        test_file.write_text("import time\ndef test_slow(): time.sleep(10)\n")
        failures = check_regression(tmp_path, cfg)
        assert len(failures) == 1
        assert "timed out" in failures[0].message

    def test_failing_tests_no_junit(self, tmp_path):
        cfg = RegressionGateConfig(extra_args=["--override-ini=addopts="], timeout_seconds=30)
        test_file = tmp_path / "test_fail.py"
        test_file.write_text("def test_fail(): assert False\n")
        failures = check_regression(tmp_path, cfg)
        assert len(failures) >= 1

    def test_junit_xml_parsing(self, tmp_path):
        """Test that JUnit XML failures are parsed correctly."""
        cfg = RegressionGateConfig(extra_args=["--override-ini=addopts="], timeout_seconds=30)
        # Create a test that fails
        test_file = tmp_path / "test_junit.py"
        test_file.write_text("def test_junit_fail():\n    assert 1 == 2, 'Expected match'\n")
        failures = check_regression(tmp_path, cfg)
        assert len(failures) >= 1
        # At least one failure should have file info from JUnit
        assert any(f.gate_id == "regression" for f in failures)


# ── check_coverage ──────────────────────────────────────────────────────────


class TestCheckCoverage:
    def test_no_coverage_report(self, tmp_path):
        cfg = CoverageGateConfig(threshold=80, exclude_patterns=[])
        # Don't create any test file so coverage can't generate
        failures = check_coverage(tmp_path, cfg)
        # Either no report generated or threshold not met
        assert len(failures) >= 1

    def test_malformed_coverage_json(self, tmp_path):
        """When coverage JSON is malformed, report error."""
        cfg = CoverageGateConfig(threshold=80, exclude_patterns=[])
        # Pre-create a malformed coverage JSON
        (tmp_path / ".coverage.json").write_text("{bad json")
        with patch("harness_skills.gates.runner._run_cmd", return_value=(0, "", "")):
            failures = check_coverage(tmp_path, cfg)
        assert any("malformed" in f.message.lower() for f in failures)

    def test_below_threshold_with_per_file(self, tmp_path):
        """Test coverage below threshold with per-file advisory warnings."""
        cfg = CoverageGateConfig(threshold=90, exclude_patterns=[])
        cov_data = json.dumps({
            "totals": {"percent_covered": 75.0},
            "files": {
                str(tmp_path / "low_cov.py"): {
                    "summary": {"percent_covered": 30.0}
                },
                str(tmp_path / "ok_cov.py"): {
                    "summary": {"percent_covered": 85.0}
                },
            }
        })
        (tmp_path / ".coverage.json").write_text(cov_data)
        with patch("harness_skills.gates.runner._run_cmd", return_value=(0, "", "")):
            failures = check_coverage(tmp_path, cfg)
        # Should have one overall failure + one per-file advisory for low_cov.py
        assert any("75.0%" in f.message for f in failures)
        assert any("low_cov.py" in (f.file_path or "") for f in failures)

    def test_coverage_at_threshold(self, tmp_path):
        """Test coverage at threshold: should pass."""
        cfg = CoverageGateConfig(threshold=80, exclude_patterns=[])
        cov_data = json.dumps({
            "totals": {"percent_covered": 80.0},
            "files": {}
        })
        (tmp_path / ".coverage.json").write_text(cov_data)
        with patch("harness_skills.gates.runner._run_cmd", return_value=(0, "", "")):
            failures = check_coverage(tmp_path, cfg)
        assert failures == []


# ── check_performance ───────────────────────────────────────────────────────


class TestCheckPerformance:
    def test_no_perf_script(self, tmp_path):
        cfg = PerformanceGateConfig(budget_ms=5000)
        failures = check_performance(tmp_path, cfg)
        assert len(failures) == 1
        assert "not found" in failures[0].message

    def test_perf_script_passes(self, tmp_path):
        cfg = PerformanceGateConfig(budget_ms=30000)
        script = tmp_path / ".harness-perf.sh"
        script.write_text("#!/bin/bash\nexit 0\n")
        script.chmod(0o755)
        failures = check_performance(tmp_path, cfg)
        assert failures == []

    def test_perf_script_fails(self, tmp_path):
        cfg = PerformanceGateConfig(budget_ms=5000)
        script = tmp_path / ".harness-perf.sh"
        script.write_text("#!/bin/bash\nexit 1\n")
        script.chmod(0o755)
        failures = check_performance(tmp_path, cfg)
        assert len(failures) == 1
        assert "exited with code" in failures[0].message

    def test_perf_script_exceeds_budget(self, tmp_path):
        cfg = PerformanceGateConfig(budget_ms=1)  # 1ms budget
        script = tmp_path / ".harness-perf.sh"
        script.write_text("#!/bin/bash\nsleep 0.1\nexit 0\n")
        script.chmod(0o755)
        failures = check_performance(tmp_path, cfg)
        assert len(failures) == 1
        assert "exceeds budget" in failures[0].message


# ── check_docs_freshness ────────────────────────────────────────────────────


class TestCheckDocsFreshness:
    def test_missing_file(self, tmp_path):
        cfg = DocsFreshnessGateConfig(
            tracked_files=["AGENTS.md"],
            max_staleness_days=30,
        )
        failures = check_docs_freshness(tmp_path, cfg)
        assert len(failures) == 1
        assert "not found" in failures[0].message

    def test_no_timestamp(self, tmp_path):
        cfg = DocsFreshnessGateConfig(
            tracked_files=["AGENTS.md"],
            max_staleness_days=30,
        )
        (tmp_path / "AGENTS.md").write_text("# AGENTS\nNo timestamp.\n")
        failures = check_docs_freshness(tmp_path, cfg)
        assert len(failures) == 1
        assert "no embedded" in failures[0].message

    def test_fresh_file(self, tmp_path):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        cfg = DocsFreshnessGateConfig(
            tracked_files=["AGENTS.md"],
            max_staleness_days=30,
        )
        (tmp_path / "AGENTS.md").write_text(
            f"generated_at: {now.isoformat()}\n# AGENTS\n"
        )
        failures = check_docs_freshness(tmp_path, cfg)
        assert failures == []

    def test_stale_file(self, tmp_path):
        cfg = DocsFreshnessGateConfig(
            tracked_files=["AGENTS.md"],
            max_staleness_days=30,
        )
        (tmp_path / "AGENTS.md").write_text(
            "generated_at: 2025-01-01T00:00:00+00:00\n# AGENTS\n"
        )
        failures = check_docs_freshness(tmp_path, cfg)
        assert len(failures) == 1
        assert "days old" in failures[0].message

    def test_invalid_timestamp_no_crash(self, tmp_path):
        cfg = DocsFreshnessGateConfig(
            tracked_files=["AGENTS.md"],
            max_staleness_days=30,
        )
        (tmp_path / "AGENTS.md").write_text(
            "generated_at: not-a-date\n# AGENTS\n"
        )
        # Should not crash — invalid timestamp silently handled
        failures = check_docs_freshness(tmp_path, cfg)
        # The regex won't match "not-a-date" as a proper ISO timestamp,
        # so it falls through to the "no timestamp" branch
        assert isinstance(failures, list)


# ── check_security ──────────────────────────────────────────────────────────


class TestCheckSecurity:
    def test_no_scanners_no_failures(self, tmp_path):
        cfg = SecurityGateConfig(scan_dependencies=False)
        failures = check_security(tmp_path, cfg)
        assert failures == []

    def test_pip_audit_json_parsing(self, tmp_path):
        cfg = SecurityGateConfig(scan_dependencies=True, ignore_ids=[])
        audit_output = json.dumps({
            "dependencies": [
                {
                    "name": "requests",
                    "vulns": [
                        {
                            "id": "CVE-2023-1234",
                            "description": "bad vuln",
                            "fix_versions": ["2.32.0"],
                        }
                    ]
                }
            ]
        })
        bandit_output = json.dumps({"results": []})
        with patch("harness_skills.gates.runner.subprocess.run") as mock_sub:
            mock_sub.side_effect = [
                MagicMock(returncode=1, stdout=audit_output, stderr=""),     # pip-audit
                MagicMock(returncode=0, stdout=bandit_output, stderr=""),    # bandit
            ]
            failures = check_security(tmp_path, cfg)
        assert len(failures) >= 1
        assert "CVE-2023-1234" in failures[0].message

    def test_pip_audit_ignore_ids(self, tmp_path):
        cfg = SecurityGateConfig(
            scan_dependencies=True,
            ignore_ids=["CVE-2023-1234"],
        )
        audit_output = json.dumps({
            "dependencies": [
                {
                    "name": "requests",
                    "vulns": [{"id": "CVE-2023-1234", "description": "bad"}]
                }
            ]
        })
        bandit_output = json.dumps({"results": []})
        with patch("harness_skills.gates.runner.subprocess.run") as mock_sub:
            mock_sub.side_effect = [
                MagicMock(returncode=1, stdout=audit_output, stderr=""),
                MagicMock(returncode=0, stdout=bandit_output, stderr=""),
            ]
            failures = check_security(tmp_path, cfg)
        assert not any("CVE-2023-1234" in f.message for f in failures)

    def test_bandit_findings(self, tmp_path):
        cfg = SecurityGateConfig(scan_dependencies=True, severity_threshold="LOW")
        bandit_output = json.dumps({
            "results": [
                {
                    "test_id": "B101",
                    "issue_severity": "HIGH",
                    "issue_text": "Use of assert",
                    "filename": str(tmp_path / "app.py"),
                    "line_number": 10,
                }
            ]
        })
        audit_ok = json.dumps({"dependencies": []})
        with patch("harness_skills.gates.runner.subprocess.run") as mock_sub:
            mock_sub.side_effect = [
                MagicMock(returncode=0, stdout=audit_ok, stderr=""),         # pip-audit ok
                MagicMock(returncode=1, stdout=bandit_output, stderr=""),    # bandit findings
            ]
            failures = check_security(tmp_path, cfg)
        assert any("B101" in f.message for f in failures)

    def test_no_fix_versions(self, tmp_path):
        cfg = SecurityGateConfig(scan_dependencies=True)
        audit_output = json.dumps({
            "dependencies": [
                {
                    "name": "old_pkg",
                    "vulns": [
                        {"id": "CVE-2023-9999", "description": "no fix", "fix_versions": []}
                    ]
                }
            ]
        })
        bandit_ok = json.dumps({"results": []})
        with patch("harness_skills.gates.runner.subprocess.run") as mock_sub:
            mock_sub.side_effect = [
                MagicMock(returncode=1, stdout=audit_output, stderr=""),
                MagicMock(returncode=0, stdout=bandit_ok, stderr=""),
            ]
            failures = check_security(tmp_path, cfg)
        assert any("No fix" in f.suggestion for f in failures)


# ── check_types ─────────────────────────────────────────────────────────────


class TestCheckTypes:
    def test_mypy_no_errors(self, tmp_path):
        cfg = TypesGateConfig()
        (tmp_path / "pyproject.toml").write_text("[tool.mypy]\n")
        with patch("harness_skills.gates.runner._run_cmd", return_value=(0, "", "")):
            failures = check_types(tmp_path, cfg)
        assert failures == []

    def test_mypy_errors(self, tmp_path):
        cfg = TypesGateConfig(strict=True, ignore_errors=[])
        (tmp_path / "pyproject.toml").write_text("[tool.mypy]\n")
        mypy_output = "app.py:10: error: Incompatible types [assignment]\n"
        with patch("harness_skills.gates.runner._run_cmd",
                    return_value=(1, mypy_output, "")):
            failures = check_types(tmp_path, cfg)
        assert len(failures) == 1
        assert failures[0].file_path == "app.py"
        assert failures[0].line_number == 10
        assert failures[0].rule_id == "assignment"

    def test_mypy_ignore_errors(self, tmp_path):
        cfg = TypesGateConfig(ignore_errors=["assignment"])
        (tmp_path / "pyproject.toml").write_text("[tool.mypy]\n")
        mypy_output = "app.py:10: error: Incompatible types [assignment]\n"
        with patch("harness_skills.gates.runner._run_cmd",
                    return_value=(1, mypy_output, "")):
            failures = check_types(tmp_path, cfg)
        assert failures == []

    def test_tsc_errors(self, tmp_path):
        cfg = TypesGateConfig()
        (tmp_path / "tsconfig.json").write_text("{}")
        tsc_output = "app.ts(5,3): error TS2322: Type 'string' is not assignable.\n"
        with patch("harness_skills.gates.runner._run_cmd",
                    return_value=(1, tsc_output, "")):
            failures = check_types(tmp_path, cfg)
        assert len(failures) == 1
        assert failures[0].rule_id == "TS2322"

    def test_no_project_files(self, tmp_path):
        cfg = TypesGateConfig()
        failures = check_types(tmp_path, cfg)
        assert failures == []


# ── check_lint ──────────────────────────────────────────────────────────────


class TestCheckLint:
    def test_ruff_no_violations(self, tmp_path):
        cfg = LintGateConfig()
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n")
        with patch("harness_skills.gates.runner._run_cmd", return_value=(0, "[]", "")):
            failures = check_lint(tmp_path, cfg)
        assert failures == []

    def test_ruff_violations(self, tmp_path):
        cfg = LintGateConfig(select=["E"], ignore=[], autofix=False)
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n")
        ruff_output = json.dumps([
            {
                "code": "E501",
                "message": "Line too long",
                "filename": str(tmp_path / "app.py"),
                "location": {"row": 5},
                "fix": None,
            }
        ])
        with patch("harness_skills.gates.runner._run_cmd",
                    return_value=(1, ruff_output, "")):
            failures = check_lint(tmp_path, cfg)
        assert len(failures) == 1
        assert failures[0].rule_id == "E501"

    def test_ruff_with_fix(self, tmp_path):
        cfg = LintGateConfig(autofix=True)
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n")
        ruff_output = json.dumps([
            {
                "code": "I001",
                "message": "Import block unsorted",
                "filename": str(tmp_path / "app.py"),
                "location": {"row": 1},
                "fix": {"message": "Sort imports"},
            }
        ])
        with patch("harness_skills.gates.runner._run_cmd",
                    return_value=(1, ruff_output, "")):
            failures = check_lint(tmp_path, cfg)
        assert failures[0].suggestion == "Sort imports"

    def test_eslint_violations(self, tmp_path):
        cfg = LintGateConfig(autofix=False)
        (tmp_path / ".eslintrc.json").write_text("{}")
        eslint_output = json.dumps([
            {
                "filePath": str(tmp_path / "app.js"),
                "messages": [
                    {
                        "severity": 2,
                        "message": "Unexpected var",
                        "line": 3,
                        "ruleId": "no-var",
                    }
                ]
            }
        ])
        with patch("harness_skills.gates.runner._run_cmd",
                    return_value=(1, eslint_output, "")):
            failures = check_lint(tmp_path, cfg)
        assert len(failures) == 1
        assert failures[0].severity == "error"
        assert failures[0].rule_id == "no-var"

    def test_eslint_warning(self, tmp_path):
        cfg = LintGateConfig()
        (tmp_path / ".eslintrc.js").write_text("module.exports = {};")
        eslint_output = json.dumps([
            {
                "filePath": str(tmp_path / "app.js"),
                "messages": [
                    {"severity": 1, "message": "warn", "line": 1, "ruleId": "w1"}
                ]
            }
        ])
        with patch("harness_skills.gates.runner._run_cmd",
                    return_value=(1, eslint_output, "")):
            failures = check_lint(tmp_path, cfg)
        assert failures[0].severity == "warning"

    def test_no_lint_config(self, tmp_path):
        cfg = LintGateConfig()
        failures = check_lint(tmp_path, cfg)
        assert failures == []


# ── check_principles ────────────────────────────────────────────────────────


class TestCheckPrinciples:
    def test_no_violations(self, tmp_path):
        cfg = PrinciplesGateConfig()
        mock_result = MagicMock()
        mock_result.violations = []
        mock_gate = MagicMock()
        mock_gate.run.return_value = mock_result

        with patch("harness_skills.gates.principles.PrinciplesGate", return_value=mock_gate):
            failures = check_principles(tmp_path, cfg)
        assert failures == []

    def test_with_violations(self, tmp_path):
        cfg = PrinciplesGateConfig()
        mock_violation = MagicMock()
        mock_violation.severity = "error"
        mock_violation.message = "Bad pattern"
        mock_violation.file_path = "app.py"
        mock_violation.line_number = 5
        mock_violation.suggestion = "Fix it"
        mock_violation.rule_id = "P001"

        mock_result = MagicMock()
        mock_result.violations = [mock_violation]
        mock_gate = MagicMock()
        mock_gate.run.return_value = mock_result

        with patch("harness_skills.gates.principles.PrinciplesGate", return_value=mock_gate):
            failures = check_principles(tmp_path, cfg)
        assert len(failures) == 1
        assert failures[0].rule_id == "P001"


# ── check_architecture ──────────────────────────────────────────────────────


class TestCheckArchitecture:
    def test_no_violations(self, tmp_path):
        cfg = ArchitectureGateConfig(
            layer_order=["models", "services", "routes"],
        )
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (models_dir / "user.py").write_text("class User: pass\n")
        failures = check_architecture(tmp_path, cfg)
        assert failures == []

    def test_layer_violation_detected(self, tmp_path):
        cfg = ArchitectureGateConfig(
            layer_order=["models", "services", "routes"],
        )
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        # models importing from routes = violation (lower imports higher)
        (models_dir / "user.py").write_text("from routes.api import handler\n")
        routes_dir = tmp_path / "routes"
        routes_dir.mkdir()
        (routes_dir / "__init__.py").write_text("")
        (routes_dir / "api.py").write_text("def handler(): pass\n")
        failures = check_architecture(tmp_path, cfg)
        assert len(failures) >= 1
        assert "Layer violation" in failures[0].message

    def test_report_only_mode(self, tmp_path):
        cfg = ArchitectureGateConfig(
            layer_order=["models", "services"],
            report_only=True,
        )
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (models_dir / "user.py").write_text("from services.svc import do\n")
        services_dir = tmp_path / "services"
        services_dir.mkdir()
        (services_dir / "__init__.py").write_text("")
        (services_dir / "svc.py").write_text("def do(): pass\n")
        failures = check_architecture(tmp_path, cfg)
        if failures:
            assert failures[0].severity == "warning"

    def test_syntax_error_skipped(self, tmp_path):
        cfg = ArchitectureGateConfig(layer_order=["models"])
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (models_dir / "bad.py").write_text("def broken(\n")  # syntax error
        failures = check_architecture(tmp_path, cfg)
        assert failures == []


# ── GateEvaluator.run ────────────────────────────────────────────────────────


class TestGateEvaluatorRun:
    def _write_config(self, tmp_path, data):
        cfg = tmp_path / "harness.config.yaml"
        cfg.write_text(yaml.dump(data))
        return cfg

    def test_disabled_gate_skipped(self, tmp_path):
        cfg = self._write_config(tmp_path, {
            "active_profile": "starter",
            "profiles": {
                "starter": {
                    "gates": {
                        "coverage": {"enabled": False},
                    }
                }
            }
        })
        evaluator = GateEvaluator(project_root=tmp_path, config_path=cfg)
        summary = evaluator.run(gate_ids=["coverage"], profile="starter")
        assert summary.skipped_gates == 1
        assert summary.outcomes[0].status == "skipped"

    def test_gate_exception_handled(self, tmp_path):
        cfg = self._write_config(tmp_path, {
            "active_profile": "starter",
            "profiles": {"starter": {"gates": {}}}
        })
        evaluator = GateEvaluator(project_root=tmp_path, config_path=cfg)

        with patch(
            "harness_skills.gates.runner._GATE_CHECKS",
            {"coverage": MagicMock(side_effect=RuntimeError("boom"))},
        ):
            summary = evaluator.run(gate_ids=["coverage"], profile="starter")
        assert any(o.status == "error" for o in summary.outcomes)
        assert not summary.passed

    def test_fail_on_error_false_downgrades_severity(self, tmp_path):
        cfg = self._write_config(tmp_path, {
            "active_profile": "starter",
            "profiles": {
                "starter": {
                    "gates": {
                        "performance": {"enabled": True, "fail_on_error": False},
                    }
                }
            }
        })
        evaluator = GateEvaluator(project_root=tmp_path, config_path=cfg)

        mock_failures = [
            GateFailure(gate_id="performance", severity="error", message="too slow"),
        ]
        with patch(
            "harness_skills.gates.runner._GATE_CHECKS",
            {"performance": MagicMock(return_value=mock_failures)},
        ):
            summary = evaluator.run(gate_ids=["performance"], profile="starter")
        # error → warning, so still passes
        assert summary.passed is True
        assert summary.outcomes[0].failures[0].severity == "warning"

    def test_run_all_gates_default(self, tmp_path):
        cfg = self._write_config(tmp_path, {
            "active_profile": "starter",
            "profiles": {"starter": {"gates": {}}}
        })
        evaluator = GateEvaluator(project_root=tmp_path, config_path=cfg)
        # Run with gate_ids=None → runs all
        with patch(
            "harness_skills.gates.runner._GATE_CHECKS",
            {"coverage": MagicMock(return_value=[])},
        ):
            summary = evaluator.run(profile="starter")
        assert summary.total_gates >= 1

    def test_unknown_gate_id_skipped(self, tmp_path):
        cfg = self._write_config(tmp_path, {
            "active_profile": "starter",
            "profiles": {"starter": {"gates": {}}}
        })
        evaluator = GateEvaluator(project_root=tmp_path, config_path=cfg)
        summary = evaluator.run(gate_ids=["nonexistent"], profile="starter")
        assert summary.total_gates == 0

    def test_gate_with_warnings_only_passes(self, tmp_path):
        cfg = self._write_config(tmp_path, {
            "active_profile": "starter",
            "profiles": {
                "starter": {
                    "gates": {
                        "coverage": {"enabled": True, "fail_on_error": True},
                    }
                }
            }
        })
        evaluator = GateEvaluator(project_root=tmp_path, config_path=cfg)
        mock_failures = [
            GateFailure(gate_id="coverage", severity="warning", message="low coverage"),
        ]
        with patch(
            "harness_skills.gates.runner._GATE_CHECKS",
            {"coverage": MagicMock(return_value=mock_failures)},
        ):
            summary = evaluator.run(gate_ids=["coverage"], profile="starter")
        # Warnings only → gate passes
        assert summary.passed is True
        assert summary.total_failures == 1
        assert summary.blocking_failures == 0

    def test_gate_with_blocking_errors_fails(self, tmp_path):
        cfg = self._write_config(tmp_path, {
            "active_profile": "starter",
            "profiles": {
                "starter": {
                    "gates": {
                        "coverage": {"enabled": True, "fail_on_error": True},
                    }
                }
            }
        })
        evaluator = GateEvaluator(project_root=tmp_path, config_path=cfg)
        mock_failures = [
            GateFailure(gate_id="coverage", severity="error", message="below threshold"),
        ]
        with patch(
            "harness_skills.gates.runner._GATE_CHECKS",
            {"coverage": MagicMock(return_value=mock_failures)},
        ):
            summary = evaluator.run(gate_ids=["coverage"], profile="starter")
        assert summary.passed is False
        assert summary.failed_gates == 1
        assert summary.blocking_failures == 1

    def test_relative_config_path(self, tmp_path):
        cfg = tmp_path / "harness.config.yaml"
        cfg.write_text(yaml.dump({"active_profile": "starter"}))
        evaluator = GateEvaluator(
            project_root=tmp_path,
            config_path="harness.config.yaml",
        )
        summary = evaluator.run(gate_ids=[], profile="starter")
        assert summary.passed is True


# ── run_gates convenience function ───────────────────────────────────────────


class TestRunGates:
    def test_run_gates_basic(self, tmp_path):
        cfg = tmp_path / "harness.config.yaml"
        cfg.write_text(yaml.dump({"active_profile": "starter"}))
        summary = run_gates(
            project_root=tmp_path,
            config_path=cfg,
            gate_ids=[],
            profile="starter",
        )
        assert isinstance(summary, EvaluationSummary)
        assert summary.passed is True
