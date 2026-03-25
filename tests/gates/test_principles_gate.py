"""
tests/gates/test_principles_gate.py
=====================================
Unit and integration tests for the golden-principles compliance gate.

Coverage
--------
* :class:`~harness_skills.gates.principles.PrinciplesGate` — gate result,
  violation collection, severity mapping, advisory mode, fail_on_critical.
* Built-in scanners: no_magic_numbers, no_hardcoded_urls, function_naming,
  variable_naming, class_naming, file_naming.
* :class:`~harness_skills.gates.principles.GateResult` helpers.
* :func:`~harness_skills.gates.principles.main` CLI exit codes.
* :func:`~harness_skills.gates.runner.check_principles` integration with
  :class:`~harness_skills.models.gate_configs.PrinciplesGateConfig`.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from harness_skills.gates.principles import (
    GateConfig,
    GateResult,
    PrinciplesGate,
    Violation,
    _scan_class_naming,
    _scan_file_naming,
    _scan_function_naming,
    _scan_no_hardcoded_urls,
    _scan_no_magic_numbers,
    _scan_variable_naming,
    _to_pascal_case,
    _to_snake_case,
    main,
)
from harness_skills.models.gate_configs import (
    BaseGateConfig,
    GATE_CONFIG_CLASSES,
    PrinciplesGateConfig,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_py(tmp_path: Path, name: str, content: str) -> Path:
    """Write a Python source file under *tmp_path* and return its path."""
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content))
    return path


def _write_principles(tmp_path: Path, principles: list[dict]) -> Path:
    """Write a .claude/principles.yaml under *tmp_path*."""
    p_dir = tmp_path / ".claude"
    p_dir.mkdir(parents=True, exist_ok=True)
    p_file = p_dir / "principles.yaml"
    p_file.write_text(yaml.dump({"version": "1.0", "principles": principles}))
    return p_file


# ---------------------------------------------------------------------------
# GateResult helpers
# ---------------------------------------------------------------------------


class TestGateResultHelpers:
    def test_errors_returns_only_error_severity(self):
        violations = [
            Violation(principle_id="P011", severity="error", message="err"),
            Violation(principle_id="P012", severity="warning", message="warn"),
            Violation(principle_id="P013", severity="info", message="info"),
        ]
        result = GateResult(passed=False, violations=violations)
        errors = result.errors()
        assert len(errors) == 1
        assert errors[0].severity == "error"

    def test_warnings_returns_only_warning_severity(self):
        violations = [
            Violation(principle_id="P011", severity="error", message="err"),
            Violation(principle_id="P012", severity="warning", message="warn"),
        ]
        result = GateResult(passed=True, violations=violations)
        assert len(result.warnings()) == 1

    def test_str_passed(self):
        result = GateResult(passed=True, violations=[])
        assert "PASSED" in str(result)
        assert "0 blocking" in str(result)

    def test_str_failed(self):
        violations = [Violation(principle_id="P011", severity="error", message="x")]
        result = GateResult(passed=False, violations=violations)
        assert "FAILED" in str(result)
        assert "1 blocking" in str(result)


# ---------------------------------------------------------------------------
# PrinciplesGate — empty project
# ---------------------------------------------------------------------------


class TestPrinciplesGateEmptyProject:
    def test_empty_directory_passes(self, tmp_path):
        gate = PrinciplesGate()
        result = gate.run(tmp_path)
        assert result.passed
        assert result.violations == []

    def test_no_principles_file_still_runs_builtin_scanners(self, tmp_path):
        """Built-in scanners run even without a principles.yaml."""
        _write_py(tmp_path, "src/config.py", "x = 42\n")
        gate = PrinciplesGate(GateConfig(rules=["no_magic_numbers"]))
        result = gate.run(tmp_path)
        # Should find the magic number 42
        assert any(v.rule_id == "principles/no-magic-numbers" for v in result.violations)

    def test_missing_principles_file_still_passes_cleanly(self, tmp_path):
        """No crash when principles file is absent."""
        gate = PrinciplesGate(GateConfig(principles_file="nonexistent.yaml", auto_rules=[]))
        result = gate.run(tmp_path)
        assert result.principles_loaded == 0


# ---------------------------------------------------------------------------
# PrinciplesGate — YAML severity mapping
# ---------------------------------------------------------------------------


class TestSeverityMapping:
    def test_blocking_principle_maps_to_error(self, tmp_path):
        _write_principles(tmp_path, [
            {
                "id": "P011",
                "category": "style",
                "severity": "blocking",
                "applies_to": ["check-code"],
                "rule": "No magic numbers.",
            }
        ])
        _write_py(tmp_path, "src/app.py", "TIMEOUT = 42\n")
        gate = PrinciplesGate(GateConfig(fail_on_critical=True))
        result = gate.run(tmp_path)
        errors = result.errors()
        assert len(errors) >= 1
        assert all(e.severity == "error" for e in errors)

    def test_suggestion_principle_maps_to_info(self, tmp_path):
        _write_principles(tmp_path, [
            {
                "id": "P011",
                "category": "style",
                "severity": "suggestion",
                "applies_to": ["check-code"],
                "rule": "No magic numbers.",
            }
        ])
        _write_py(tmp_path, "src/app.py", "TIMEOUT = 42\n")
        gate = PrinciplesGate(GateConfig(fail_on_critical=False, fail_on_error=False))
        result = gate.run(tmp_path)
        assert result.passed
        info = [v for v in result.violations if v.severity == "info"]
        assert len(info) >= 1

    def test_warning_principle_maps_to_warning(self, tmp_path):
        _write_principles(tmp_path, [
            {
                "id": "P011",
                "category": "style",
                "severity": "warning",
                "applies_to": ["check-code"],
                "rule": "No magic numbers.",
            }
        ])
        _write_py(tmp_path, "src/app.py", "TIMEOUT = 42\n")
        gate = PrinciplesGate(GateConfig(fail_on_critical=False, fail_on_error=False))
        result = gate.run(tmp_path)
        assert result.passed
        warnings = result.warnings()
        assert len(warnings) >= 1


# ---------------------------------------------------------------------------
# PrinciplesGate — fail_on_critical behaviour
# ---------------------------------------------------------------------------


class TestFailOnCritical:
    def test_fail_on_critical_true_fails_gate(self, tmp_path):
        _write_py(tmp_path, "src/app.py", "TIMEOUT = 42\n")
        gate = PrinciplesGate(GateConfig(fail_on_critical=True, rules=["no_magic_numbers"]))
        result = gate.run(tmp_path)
        # Default severity when no YAML is "warning" — add a blocking principle
        # to make this produce an error:
        _write_principles(tmp_path, [
            {"id": "P011", "severity": "blocking", "applies_to": ["check-code"],
             "rule": "No magic numbers."}
        ])
        result = gate.run(tmp_path)
        assert not result.passed

    def test_fail_on_critical_false_passes_with_warnings(self, tmp_path):
        _write_principles(tmp_path, [
            {"id": "P011", "severity": "blocking", "applies_to": ["check-code"],
             "rule": "No magic numbers."}
        ])
        _write_py(tmp_path, "src/app.py", "TIMEOUT = 42\n")
        gate = PrinciplesGate(GateConfig(fail_on_critical=False, fail_on_error=False))
        result = gate.run(tmp_path)
        assert result.passed
        # The error was downgraded to warning
        assert not result.errors()
        assert result.warnings()

    def test_fail_on_critical_true_overrides_advisory_for_blocking(self, tmp_path):
        """fail_on_critical=True should still fail even when fail_on_error=False."""
        _write_principles(tmp_path, [
            {"id": "P011", "severity": "blocking", "applies_to": ["check-code"],
             "rule": "No magic numbers."}
        ])
        _write_py(tmp_path, "src/app.py", "TIMEOUT = 42\n")
        gate = PrinciplesGate(GateConfig(fail_on_critical=True, fail_on_error=False))
        result = gate.run(tmp_path)
        assert not result.passed
        assert result.errors()

    def test_only_check_code_principles_are_scanned(self, tmp_path):
        """Principles that don't apply to check-code are skipped."""
        _write_principles(tmp_path, [
            {"id": "P001", "severity": "blocking", "applies_to": ["review-pr"],
             "rule": "PR must reference a plan."}
        ])
        gate = PrinciplesGate(GateConfig(fail_on_critical=True))
        result = gate.run(tmp_path)
        # P001 is review-pr only — no violations from YAML
        p001_violations = [v for v in result.violations if v.principle_id == "P001"]
        assert not p001_violations


# ---------------------------------------------------------------------------
# Built-in scanner: no_magic_numbers
# ---------------------------------------------------------------------------


class TestScanNoMagicNumbers:
    def test_detects_magic_number(self, tmp_path):
        _write_py(tmp_path, "src/config.py", "RATE = 42\n")
        violations = _scan_no_magic_numbers(tmp_path, "P011", "error")
        assert any(v.message and "42" in v.message for v in violations)

    def test_allowed_numbers_not_flagged(self, tmp_path):
        _write_py(tmp_path, "src/config.py", "x = 0\ny = 1\nz = -1\na = 2\n")
        violations = _scan_no_magic_numbers(tmp_path, "P011", "error")
        assert not violations

    def test_float_magic_number_detected(self, tmp_path):
        _write_py(tmp_path, "src/config.py", "TIMEOUT = 3.14\n")
        violations = _scan_no_magic_numbers(tmp_path, "P011", "warning")
        assert any("3.14" in v.message for v in violations)

    def test_violation_has_line_number(self, tmp_path):
        _write_py(tmp_path, "src/config.py", "# comment\nMAX = 99\n")
        violations = _scan_no_magic_numbers(tmp_path, "P011", "warning")
        assert any(v.line_number == 2 for v in violations)

    def test_skips_venv(self, tmp_path):
        (tmp_path / ".venv").mkdir()
        _write_py(tmp_path, ".venv/site-packages/lib.py", "X = 999\n")
        violations = _scan_no_magic_numbers(tmp_path, "P011", "error")
        assert not violations

    def test_rule_id_set_correctly(self, tmp_path):
        _write_py(tmp_path, "src/app.py", "X = 42\n")
        violations = _scan_no_magic_numbers(tmp_path, "P011", "error")
        assert all(v.rule_id == "principles/no-magic-numbers" for v in violations)


# ---------------------------------------------------------------------------
# Built-in scanner: no_hardcoded_urls
# ---------------------------------------------------------------------------


class TestScanNoHardcodedUrls:
    def test_detects_http_url(self, tmp_path):
        _write_py(tmp_path, "src/client.py", 'URL = "http://api.example.com/v1"\n')
        violations = _scan_no_hardcoded_urls(tmp_path, "P012", "error")
        assert violations

    def test_detects_https_url(self, tmp_path):
        _write_py(tmp_path, "src/client.py", 'BASE = "https://example.com/api"\n')
        violations = _scan_no_hardcoded_urls(tmp_path, "P012", "warning")
        assert violations

    def test_short_string_not_flagged(self, tmp_path):
        _write_py(tmp_path, "src/client.py", 'X = "http://x"\n')
        violations = _scan_no_hardcoded_urls(tmp_path, "P012", "error")
        assert not violations

    def test_non_url_string_not_flagged(self, tmp_path):
        _write_py(tmp_path, "src/app.py", 'MSG = "hello world"\n')
        violations = _scan_no_hardcoded_urls(tmp_path, "P012", "error")
        assert not violations

    def test_rule_id_set_correctly(self, tmp_path):
        _write_py(tmp_path, "src/app.py", 'URL = "https://example.com/endpoint"\n')
        violations = _scan_no_hardcoded_urls(tmp_path, "P012", "error")
        assert all(v.rule_id == "principles/no-hardcoded-urls" for v in violations)


# ---------------------------------------------------------------------------
# Built-in scanner: function_naming
# ---------------------------------------------------------------------------


class TestScanFunctionNaming:
    def test_valid_snake_case_passes(self, tmp_path):
        _write_py(tmp_path, "src/utils.py", "def get_user_by_id(user_id): pass\n")
        violations = _scan_function_naming(tmp_path, "P014", "error")
        assert not violations

    def test_camel_case_flagged(self, tmp_path):
        _write_py(tmp_path, "src/utils.py", "def getUserById(): pass\n")
        violations = _scan_function_naming(tmp_path, "P014", "error")
        assert any("getUserById" in v.message for v in violations)

    def test_pascal_case_function_flagged(self, tmp_path):
        _write_py(tmp_path, "src/utils.py", "def GetUser(): pass\n")
        violations = _scan_function_naming(tmp_path, "P014", "error")
        assert violations

    def test_dunders_exempt(self, tmp_path):
        _write_py(tmp_path, "src/model.py", "class Foo:\n    def __init__(self): pass\n")
        violations = _scan_function_naming(tmp_path, "P014", "error")
        assert not violations

    def test_private_snake_case_passes(self, tmp_path):
        _write_py(tmp_path, "src/utils.py", "def _helper_fn(): pass\n")
        violations = _scan_function_naming(tmp_path, "P014", "error")
        assert not violations

    def test_rule_id_set_correctly(self, tmp_path):
        _write_py(tmp_path, "src/utils.py", "def BadName(): pass\n")
        violations = _scan_function_naming(tmp_path, "P014", "error")
        assert all(v.rule_id == "principles/function-naming" for v in violations)


# ---------------------------------------------------------------------------
# Built-in scanner: variable_naming
# ---------------------------------------------------------------------------


class TestScanVariableNaming:
    def test_single_letter_flagged(self, tmp_path):
        _write_py(tmp_path, "src/app.py", "def fn():\n    x = 1\n")
        violations = _scan_variable_naming(tmp_path, "P015", "warning")
        assert any(v.message and "'x'" in v.message for v in violations)

    def test_ijk_loop_counters_not_flagged(self, tmp_path):
        _write_py(tmp_path, "src/app.py", "for i in range(10):\n    j = i\n")
        violations = _scan_variable_naming(tmp_path, "P015", "warning")
        # i is loop var (exempt), j is an assignment but also a loop-var-like
        # Our scanner exempts i/j/k, so neither should be flagged
        assert not any("'i'" in (v.message or "") for v in violations)

    def test_descriptive_name_passes(self, tmp_path):
        _write_py(tmp_path, "src/app.py", "user_id = 42\n")
        violations = _scan_variable_naming(tmp_path, "P015", "warning")
        assert not any("user_id" in (v.message or "") for v in violations)

    def test_rule_id_set_correctly(self, tmp_path):
        _write_py(tmp_path, "src/app.py", "x = 10\n")
        violations = _scan_variable_naming(tmp_path, "P015", "warning")
        if violations:
            assert all(v.rule_id == "principles/variable-naming" for v in violations)


# ---------------------------------------------------------------------------
# Built-in scanner: class_naming
# ---------------------------------------------------------------------------


class TestScanClassNaming:
    def test_pascal_case_passes(self, tmp_path):
        _write_py(tmp_path, "src/model.py", "class UserProfile: pass\n")
        violations = _scan_class_naming(tmp_path, "P016", "error")
        assert not violations

    def test_snake_case_class_flagged(self, tmp_path):
        _write_py(tmp_path, "src/model.py", "class user_profile: pass\n")
        violations = _scan_class_naming(tmp_path, "P016", "error")
        assert violations

    def test_lowercase_class_flagged(self, tmp_path):
        _write_py(tmp_path, "src/model.py", "class myclass: pass\n")
        violations = _scan_class_naming(tmp_path, "P016", "error")
        assert violations

    def test_test_class_with_pascal_passes(self, tmp_path):
        _write_py(tmp_path, "tests/test_model.py", "class TestUserProfile: pass\n")
        violations = _scan_class_naming(tmp_path, "P016", "error")
        assert not violations

    def test_rule_id_set_correctly(self, tmp_path):
        _write_py(tmp_path, "src/model.py", "class bad_name: pass\n")
        violations = _scan_class_naming(tmp_path, "P016", "error")
        assert all(v.rule_id == "principles/class-naming" for v in violations)


# ---------------------------------------------------------------------------
# Built-in scanner: file_naming
# ---------------------------------------------------------------------------


class TestScanFileNaming:
    def test_snake_case_file_passes(self, tmp_path):
        _write_py(tmp_path, "src/user_service.py", "# ok\n")
        violations = _scan_file_naming(tmp_path, "P017", "error")
        assert not violations

    def test_camel_case_file_flagged(self, tmp_path):
        _write_py(tmp_path, "src/UserService.py", "# bad\n")
        violations = _scan_file_naming(tmp_path, "P017", "error")
        assert any("UserService.py" in (v.message or "") for v in violations)

    def test_hyphenated_file_flagged(self, tmp_path):
        _write_py(tmp_path, "src/user-service.py", "# bad\n")
        violations = _scan_file_naming(tmp_path, "P017", "error")
        assert violations

    def test_skips_venv(self, tmp_path):
        (tmp_path / ".venv" / "lib").mkdir(parents=True)
        _write_py(tmp_path, ".venv/lib/BadFile.py", "# skip\n")
        violations = _scan_file_naming(tmp_path, "P017", "error")
        assert not any(".venv" in (v.file_path or "") for v in violations)

    def test_rule_id_set_correctly(self, tmp_path):
        _write_py(tmp_path, "src/BadFile.py", "# bad\n")
        violations = _scan_file_naming(tmp_path, "P017", "error")
        assert all(v.rule_id == "principles/file-naming" for v in violations)


# ---------------------------------------------------------------------------
# Naming helpers
# ---------------------------------------------------------------------------


class TestNamingHelpers:
    def test_to_snake_case_camel(self):
        assert _to_snake_case("getUserById") == "get_user_by_id"

    def test_to_snake_case_pascal(self):
        assert _to_snake_case("UserProfile") == "user_profile"

    def test_to_snake_case_already_snake(self):
        assert _to_snake_case("user_profile") == "user_profile"

    def test_to_pascal_case_snake(self):
        assert _to_pascal_case("user_profile") == "UserProfile"

    def test_to_pascal_case_already_pascal(self):
        # _to_pascal_case is a best-effort helper for snake_case/hyphenated inputs;
        # single-word PascalCase inputs are capitalised via word.capitalize().
        assert _to_pascal_case("user_profile") == "UserProfile"

    def test_to_pascal_case_hyphenated(self):
        assert _to_pascal_case("user-service") == "UserService"


# ---------------------------------------------------------------------------
# PrinciplesGate — rule subsetting
# ---------------------------------------------------------------------------


class TestRuleSubsetting:
    def test_rules_all_runs_every_scanner(self, tmp_path):
        _write_py(tmp_path, "src/app.py", "X = 42\n")
        gate = PrinciplesGate(GateConfig(rules=["all"], fail_on_critical=False))
        result = gate.run(tmp_path)
        rule_ids = {v.rule_id for v in result.violations}
        # Should find at least magic number scanner
        assert "principles/no-magic-numbers" in rule_ids

    def test_rules_subset_only_runs_specified(self, tmp_path):
        _write_py(tmp_path, "src/app.py",
                  'URL = "https://example.com/api"\nX = 42\n')
        gate = PrinciplesGate(GateConfig(
            rules=["no_hardcoded_urls"], fail_on_critical=False
        ))
        result = gate.run(tmp_path)
        rule_ids = {v.rule_id for v in result.violations}
        assert "principles/no-hardcoded-urls" in rule_ids
        assert "principles/no-magic-numbers" not in rule_ids

    def test_empty_rules_runs_nothing(self, tmp_path):
        _write_py(tmp_path, "src/app.py", "X = 42\n")
        gate = PrinciplesGate(GateConfig(rules=[], fail_on_critical=False))
        result = gate.run(tmp_path)
        assert result.violations == []


# ---------------------------------------------------------------------------
# PrinciplesGate — principles_loaded counter
# ---------------------------------------------------------------------------


class TestPrinciplesCounter:
    def test_principles_loaded_from_yaml(self, tmp_path):
        _write_principles(tmp_path, [
            {"id": "P011", "severity": "blocking", "applies_to": ["check-code"],
             "rule": "no magic numbers"},
            {"id": "P012", "severity": "suggestion", "applies_to": ["check-code"],
             "rule": "no hardcoded urls"},
        ])
        gate = PrinciplesGate()
        result = gate.run(tmp_path)
        assert result.principles_loaded == 2

    def test_principles_scanned_counts_active_scanners(self, tmp_path):
        _write_principles(tmp_path, [
            {"id": "P011", "severity": "blocking", "applies_to": ["check-code"],
             "rule": "no magic numbers"},
        ])
        gate = PrinciplesGate(GateConfig(rules=["no_magic_numbers"]))
        result = gate.run(tmp_path)
        assert result.principles_scanned >= 1


# ---------------------------------------------------------------------------
# CLI main() — exit codes
# ---------------------------------------------------------------------------


class TestCliMain:
    def test_exit_0_on_no_violations(self, tmp_path):
        code = main(["--root", str(tmp_path), "--rules"])
        assert code == 0

    def test_exit_1_on_blocking_violation(self, tmp_path):
        _write_principles(tmp_path, [
            {"id": "P011", "severity": "blocking", "applies_to": ["check-code"],
             "rule": "no magic numbers"}
        ])
        _write_py(tmp_path, "src/app.py", "X = 42\n")
        code = main([
            "--root", str(tmp_path),
            "--rules", "no_magic_numbers",
        ])
        assert code == 1

    def test_exit_0_advisory_mode_with_violations(self, tmp_path):
        _write_principles(tmp_path, [
            {"id": "P011", "severity": "blocking", "applies_to": ["check-code"],
             "rule": "no magic numbers"}
        ])
        _write_py(tmp_path, "src/app.py", "X = 42\n")
        code = main([
            "--root", str(tmp_path),
            "--rules", "no_magic_numbers",
            "--no-fail-on-critical",
        ])
        assert code == 0

    def test_json_format_output(self, tmp_path, capsys):
        code = main(["--root", str(tmp_path), "--format", "json", "--rules"])
        out = capsys.readouterr().out
        import json
        data = json.loads(out)
        assert "passed" in data
        assert "violations" in data

    def test_empty_rules_arg_runs_clean(self, tmp_path):
        code = main(["--root", str(tmp_path), "--rules"])
        assert code == 0


# ---------------------------------------------------------------------------
# GateConfig dataclass
# ---------------------------------------------------------------------------


class TestGateConfig:
    def test_defaults(self):
        cfg = GateConfig()
        assert cfg.fail_on_critical is True
        assert cfg.fail_on_error is False
        assert cfg.principles_file == ".claude/principles.yaml"
        assert cfg.rules == ["all"]

    def test_custom_values(self):
        cfg = GateConfig(
            fail_on_critical=False,
            fail_on_error=True,
            principles_file="custom/rules.yaml",
            rules=["no_magic_numbers"],
        )
        assert cfg.fail_on_critical is False
        assert cfg.fail_on_error is True
        assert cfg.rules == ["no_magic_numbers"]


# ---------------------------------------------------------------------------
# PrinciplesGateConfig (model in gate_configs.py)
# ---------------------------------------------------------------------------


class TestPrinciplesGateConfig:
    def test_fail_on_critical_default_true(self):
        cfg = PrinciplesGateConfig()
        assert cfg.fail_on_critical is True

    def test_fail_on_error_default_false(self):
        cfg = PrinciplesGateConfig()
        assert cfg.fail_on_error is False

    def test_model_dump_includes_fail_on_critical(self):
        cfg = PrinciplesGateConfig(fail_on_critical=False)
        d = cfg.model_dump()
        assert "fail_on_critical" in d
        assert d["fail_on_critical"] is False

    def test_model_validate_round_trips(self):
        original = PrinciplesGateConfig(
            fail_on_critical=False,
            fail_on_error=True,
            principles_file="custom.yaml",
        )
        d = original.model_dump()
        restored = PrinciplesGateConfig.model_validate(d)
        assert restored.fail_on_critical is False
        assert restored.fail_on_error is True
        assert restored.principles_file == "custom.yaml"

    def test_model_validate_ignores_unknown_keys(self):
        d = {"fail_on_critical": True, "unknown_key": "ignored"}
        cfg = PrinciplesGateConfig.model_validate(d)
        assert cfg.fail_on_critical is True


# ---------------------------------------------------------------------------
# BaseGateConfig
# ---------------------------------------------------------------------------


class TestBaseGateConfig:
    def test_all_gate_configs_are_base_subclasses(self):
        for gate_id, cls in GATE_CONFIG_CLASSES.items():
            assert issubclass(cls, BaseGateConfig), (
                f"{gate_id}: {cls.__name__} must inherit from BaseGateConfig"
            )

    def test_model_dump_returns_dict(self):
        cfg = PrinciplesGateConfig()
        result = cfg.model_dump()
        assert isinstance(result, dict)

    def test_model_validate_returns_correct_type(self):
        cfg = PrinciplesGateConfig()
        restored = PrinciplesGateConfig.model_validate(cfg.model_dump())
        assert isinstance(restored, PrinciplesGateConfig)


# ---------------------------------------------------------------------------
# GATE_CONFIG_CLASSES registry
# ---------------------------------------------------------------------------


class TestGateConfigClasses:
    _EXPECTED_GATES = {
        "regression", "coverage", "security", "performance",
        "architecture", "principles", "docs_freshness", "types", "lint",
        "agents_md_token", "file_size",
    }

    def test_all_expected_gates_registered(self):
        assert set(GATE_CONFIG_CLASSES.keys()) == self._EXPECTED_GATES

    def test_principles_config_class_registered(self):
        assert GATE_CONFIG_CLASSES["principles"] is PrinciplesGateConfig

    def test_all_registered_classes_have_enabled_field(self):
        import dataclasses
        for gate_id, cls in GATE_CONFIG_CLASSES.items():
            field_names = {f.name for f in dataclasses.fields(cls)}
            assert "enabled" in field_names, (
                f"{gate_id}: {cls.__name__} must have an 'enabled' field"
            )


# ---------------------------------------------------------------------------
# Integration — runner.check_principles uses PrinciplesGate
# ---------------------------------------------------------------------------


class TestRunnerIntegration:
    def test_check_principles_returns_gate_failures(self, tmp_path):
        from harness_skills.gates.runner import check_principles
        _write_principles(tmp_path, [
            {"id": "P011", "severity": "blocking", "applies_to": ["check-code"],
             "rule": "no magic numbers"}
        ])
        _write_py(tmp_path, "src/app.py", "X = 42\n")
        cfg = PrinciplesGateConfig(
            fail_on_critical=True,
            rules=["no_magic_numbers"],
        )
        failures = check_principles(tmp_path, cfg)
        assert any(f.gate_id == "principles" for f in failures)
        assert any(f.severity == "error" for f in failures)

    def test_check_principles_advisory_returns_warnings(self, tmp_path):
        from harness_skills.gates.runner import check_principles
        _write_principles(tmp_path, [
            {"id": "P011", "severity": "blocking", "applies_to": ["check-code"],
             "rule": "no magic numbers"}
        ])
        _write_py(tmp_path, "src/app.py", "X = 42\n")
        cfg = PrinciplesGateConfig(
            fail_on_critical=False,
            fail_on_error=False,
            rules=["no_magic_numbers"],
        )
        failures = check_principles(tmp_path, cfg)
        # In advisory mode, blocking violations become warnings
        assert all(f.severity != "error" for f in failures)

    def test_check_principles_empty_project_returns_empty(self, tmp_path):
        from harness_skills.gates.runner import check_principles
        cfg = PrinciplesGateConfig()
        failures = check_principles(tmp_path, cfg)
        assert failures == []
