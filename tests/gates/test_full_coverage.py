"""
tests/gates/test_full_coverage.py
==================================
Additional tests to reach 100% coverage for gate modules and core modules.

Each section targets specific uncovered lines identified via --cov-report=term-missing.
"""

from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ===========================================================================
# 1. harness_skills/gates/types.py — uncovered: 291, 317, 412, 477-478,
#    497-556, 590-647
# ===========================================================================


class TestTypesGatePyrightPath:
    """Cover _run_pyright (lines 497-556) and _build_parser (590-647)."""

    def _make_proc(self, returncode, stdout, stderr=""):
        m = MagicMock()
        m.returncode = returncode
        m.stdout = stdout
        m.stderr = stderr
        return m

    def test_pyright_json_output_parsed(self, tmp_path):
        from harness_skills.gates.types import TypesGate
        from harness_skills.models.gate_configs import TypesGateConfig

        cfg = TypesGateConfig(checker="pyright")
        gate = TypesGate(cfg)
        pyright_json = json.dumps({
            "generalDiagnostics": [
                {
                    "severity": "error",
                    "rule": "reportGeneralTypeIssues",
                    "message": "Type mismatch",
                    "file": "/project/src/foo.py",
                    "range": {"start": {"line": 9, "character": 0}},
                },
                {
                    "severity": "warning",
                    "message": "Unused var",
                    "file": "/project/src/bar.py",
                    "range": {"start": {"line": 4, "character": 0}},
                },
                {
                    "severity": "information",
                    "message": "Type info",
                    "file": None,
                    "range": {"start": {}},
                },
            ]
        })
        mock_proc = self._make_proc(1, pyright_json)
        with patch("harness_skills.gates.types.subprocess.run", return_value=mock_proc):
            result = gate.run(tmp_path)
        assert result.checker == "pyright"
        assert result.error_count == 1
        assert result.passed is False

    def test_pyright_json_with_ignore_codes(self, tmp_path):
        from harness_skills.gates.types import TypesGate
        from harness_skills.models.gate_configs import TypesGateConfig

        cfg = TypesGateConfig(checker="pyright", ignore_errors=["reportGeneralTypeIssues"])
        gate = TypesGate(cfg)
        pyright_json = json.dumps({
            "generalDiagnostics": [
                {
                    "severity": "error",
                    "rule": "reportGeneralTypeIssues",
                    "message": "Type mismatch",
                    "file": "/project/src/foo.py",
                    "range": {"start": {"line": 9}},
                },
            ]
        })
        mock_proc = self._make_proc(1, pyright_json)
        with patch("harness_skills.gates.types.subprocess.run", return_value=mock_proc):
            result = gate.run(tmp_path)
        assert result.error_count == 0
        assert result.passed is True

    def test_pyright_falls_back_to_text_on_invalid_json(self, tmp_path):
        from harness_skills.gates.types import TypesGate
        from harness_skills.models.gate_configs import TypesGateConfig

        cfg = TypesGateConfig(checker="pyright")
        gate = TypesGate(cfg)
        # Non-JSON output triggers JSONDecodeError fallback to text parsing
        text_output = "/project/src/foo.py:8:4: error: Type mismatch  (reportGeneralTypeIssues)\n"
        mock_proc = self._make_proc(1, text_output)
        with patch("harness_skills.gates.types.subprocess.run", return_value=mock_proc):
            result = gate.run(tmp_path)
        assert result.checker == "pyright"
        assert result.error_count == 1

    def test_pyright_not_found_falls_back_to_npx(self, tmp_path):
        from harness_skills.gates.types import TypesGate
        from harness_skills.models.gate_configs import TypesGateConfig

        cfg = TypesGateConfig(checker="pyright")
        gate = TypesGate(cfg)
        pyright_json = json.dumps({"generalDiagnostics": []})
        npx_proc = self._make_proc(0, pyright_json)

        call_count = [0]

        def side_effect(cmd, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise FileNotFoundError("pyright not found")
            return npx_proc

        with patch("harness_skills.gates.types.subprocess.run", side_effect=side_effect):
            result = gate.run(tmp_path)
        assert result.passed is True
        assert result.checker == "pyright"

    def test_pyright_and_npx_both_not_found(self, tmp_path):
        from harness_skills.gates.types import TypesGate
        from harness_skills.models.gate_configs import TypesGateConfig

        cfg = TypesGateConfig(checker="pyright", fail_on_error=True)
        gate = TypesGate(cfg)

        with patch(
            "harness_skills.gates.types.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            result = gate.run(tmp_path)
        assert result.passed is False
        assert result.violations[0].kind == "checker_not_found"
        assert result.checker == "pyright"

    def test_pyright_not_found_advisory_mode(self, tmp_path):
        from harness_skills.gates.types import TypesGate
        from harness_skills.models.gate_configs import TypesGateConfig

        cfg = TypesGateConfig(checker="pyright", fail_on_error=False)
        gate = TypesGate(cfg)

        with patch(
            "harness_skills.gates.types.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            result = gate.run(tmp_path)
        assert result.passed is True
        assert result.violations[0].severity == "warning"

    def test_pyright_fail_on_error_false_downgrades(self, tmp_path):
        from harness_skills.gates.types import TypesGate
        from harness_skills.models.gate_configs import TypesGateConfig

        cfg = TypesGateConfig(checker="pyright", fail_on_error=False)
        gate = TypesGate(cfg)
        pyright_json = json.dumps({
            "generalDiagnostics": [
                {
                    "severity": "error",
                    "message": "Type mismatch",
                    "file": "/src/foo.py",
                    "range": {"start": {"line": 0}},
                },
            ]
        })
        mock_proc = self._make_proc(1, pyright_json)
        with patch("harness_skills.gates.types.subprocess.run", return_value=mock_proc):
            result = gate.run(tmp_path)
        assert result.passed is True
        # errors downgraded to warnings
        assert result.error_count == 0


class TestTypesGateTscNotFound:
    """Cover tsc FileNotFoundError path (line 477-478)."""

    def test_tsc_not_found_error(self, tmp_path):
        from harness_skills.gates.types import TypesGate
        from harness_skills.models.gate_configs import TypesGateConfig

        cfg = TypesGateConfig(checker="tsc", fail_on_error=True)
        gate = TypesGate(cfg)
        with patch(
            "harness_skills.gates.types.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            result = gate.run(tmp_path)
        assert result.passed is False
        assert result.violations[0].kind == "checker_not_found"
        assert result.checker == "tsc"

    def test_tsc_not_found_advisory(self, tmp_path):
        from harness_skills.gates.types import TypesGate
        from harness_skills.models.gate_configs import TypesGateConfig

        cfg = TypesGateConfig(checker="tsc", fail_on_error=False)
        gate = TypesGate(cfg)
        with patch(
            "harness_skills.gates.types.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            result = gate.run(tmp_path)
        assert result.passed is True
        assert result.violations[0].severity == "warning"


class TestTypesGateUnknownCheckerAdvisory:
    """Cover unknown checker with fail_on_error=False (line 412)."""

    def test_unknown_checker_advisory_passes(self, tmp_path):
        from harness_skills.gates.types import TypesGate
        from harness_skills.models.gate_configs import TypesGateConfig

        cfg = TypesGateConfig(checker="badchecker", fail_on_error=False)
        gate = TypesGate(cfg)
        result = gate.run(tmp_path)
        assert result.passed is True
        assert result.violations[0].severity == "warning"


class TestTypesGateParseTscWarning:
    """Cover tsc warning parsing (line 291 — warning severity branch)."""

    def test_tsc_warning_line(self):
        from harness_skills.gates.types import _parse_tsc_output

        output = "src/index.ts(15,1): warning TS6133: 'unusedVar' is declared but its value is never read.\n"
        violations = _parse_tsc_output(output, set(), fail_on_error=True)
        assert len(violations) == 1
        assert violations[0].severity == "warning"


class TestParseTscNonMatchingLines:
    """Cover _parse_tsc_output non-matching lines (line 291)."""

    def test_non_matching_tsc_lines_skipped(self):
        from harness_skills.gates.types import _parse_tsc_output

        output = "some random log line\nsrc/index.ts(5,3): error TS2304: Cannot find name 'x'.\n"
        violations = _parse_tsc_output(output, set(), fail_on_error=True)
        assert len(violations) == 1


class TestParsePyrightNonMatchingLines:
    """Cover _parse_pyright_output non-matching lines (line 317)."""

    def test_non_matching_pyright_lines_skipped(self):
        from harness_skills.gates.types import _parse_pyright_output

        output = "some random log line\n/project/src/foo.py:8:4: error: Type of 'x' is incompatible  (reportGeneralTypeIssues)\n"
        violations = _parse_pyright_output(output, set(), fail_on_error=True)
        assert len(violations) == 1


class TestTypesGateAutoDetectSetupCfg:
    """Cover setup.cfg detection path (line 317 — .mypy.ini branch)."""

    def test_auto_detects_mypy_via_dot_mypy_ini(self, tmp_path):
        from harness_skills.gates.types import _detect_checker

        (tmp_path / ".mypy.ini").write_text("[mypy]\n")
        assert _detect_checker(tmp_path, "auto") == "mypy"

    def test_auto_detects_mypy_via_setup_cfg(self, tmp_path):
        from harness_skills.gates.types import _detect_checker

        (tmp_path / "setup.cfg").write_text("[metadata]\n")
        assert _detect_checker(tmp_path, "auto") == "mypy"


class TestTypesGateBuildParser:
    """Cover _build_parser (lines 590-647)."""

    def test_build_parser_creates_parser(self):
        from harness_skills.gates.types import _build_parser

        p = _build_parser()
        args = p.parse_args(["--root", "/tmp", "--checker", "mypy", "--strict",
                            "--ignore-error", "import", "--no-fail-on-error",
                            "--quiet", "src/"])
        assert args.root == "/tmp"
        assert args.checker == "mypy"
        assert args.strict is True
        assert args.ignore_errors == ["import"]
        assert args.fail_on_error is False
        assert args.quiet is True
        assert args.paths == ["src/"]


class TestTypeViolationSummaryFilePath:
    """Cover summary with file_path but no line_number (line 104-107)."""

    def test_summary_with_file_but_no_line(self):
        from harness_skills.gates.types import TypeViolation

        v = TypeViolation(
            kind="type_error",
            severity="error",
            message="err",
            file_path=Path("src/foo.py"),
            line_number=None,
        )
        s = v.summary()
        assert "src/foo.py" in s
        assert ":" not in s.split("[src/foo.py")[1].split("]")[0]


# ===========================================================================
# 2. harness_skills/gates/principles.py — uncovered: custom_principles,
#    no_hardcoded_strings, prefer_shared_utilities, test_structure,
#    _render_text, _render_json, _build_arg_parser, main exception path
# ===========================================================================


def _write_py(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content))
    return path


class TestPrinciplesCustomPrinciples:
    """Cover custom_principles injection (lines 298-306)."""

    def test_custom_principle_regex_scan(self, tmp_path):
        import yaml
        from harness_skills.gates.principles import PrinciplesGate, GateConfig

        # Write principles YAML
        p_dir = tmp_path / ".claude"
        p_dir.mkdir(parents=True, exist_ok=True)
        p_file = p_dir / "principles.yaml"
        p_file.write_text(yaml.dump({"version": "1.0", "principles": []}))

        # Write a file with TODO
        _write_py(tmp_path, "src/app.py", "# TODO: fix this\nresult = 1\n")

        cfg = GateConfig(
            rules=[],
            custom_principles=[
                {"id": "CUSTOM-TODO", "pattern": r"TODO", "severity": "warning", "file_glob": "*.py"},
            ],
        )
        gate = PrinciplesGate(cfg)
        result = gate.run(tmp_path)
        customs = [v for v in result.violations if v.principle_id == "CUSTOM-TODO"]
        assert len(customs) >= 1
        assert "Custom pattern match" in customs[0].message

    def test_custom_principle_bad_regex_skipped(self, tmp_path):
        import yaml
        from harness_skills.gates.principles import PrinciplesGate, GateConfig

        p_dir = tmp_path / ".claude"
        p_dir.mkdir(parents=True, exist_ok=True)
        (p_dir / "principles.yaml").write_text(yaml.dump({"version": "1.0", "principles": []}))
        _write_py(tmp_path, "src/app.py", "hello\n")

        cfg = GateConfig(
            rules=[],
            custom_principles=[
                {"id": "BAD-RE", "pattern": "[invalid(", "severity": "warning"},
            ],
        )
        gate = PrinciplesGate(cfg)
        result = gate.run(tmp_path)
        # Bad regex is skipped, no crash
        assert result.passed


class TestPrinciplesNoHardcodedStrings:
    """Cover _scan_no_hardcoded_strings (lines 620-693)."""

    def test_detects_absolute_path(self, tmp_path):
        from harness_skills.gates.principles import _scan_no_hardcoded_strings

        _write_py(tmp_path, "src/config.py", 'path = "/etc/myapp/config.yaml"\n')
        violations = _scan_no_hardcoded_strings(tmp_path, "P013", "warning")
        assert any("/etc/myapp/config.yaml" in v.message for v in violations)

    def test_constant_assignment_allowed(self, tmp_path):
        from harness_skills.gates.principles import _scan_no_hardcoded_strings

        _write_py(tmp_path, "src/config.py", 'DEFAULT_PATH = "/etc/myapp/config.yaml"\n')
        violations = _scan_no_hardcoded_strings(tmp_path, "P013", "warning")
        assert not violations


class TestPrinciplesPreferSharedUtilities:
    """Cover _scan_prefer_shared_utilities (lines 872-917)."""

    def test_detects_duplicate_function(self, tmp_path):
        from harness_skills.gates.principles import _scan_prefer_shared_utilities

        _write_py(tmp_path, "src/a.py", "def my_helper():\n    pass\n")
        _write_py(tmp_path, "src/b.py", "def my_helper():\n    pass\n")
        violations = _scan_prefer_shared_utilities(tmp_path, "P018", "warning")
        assert len(violations) >= 2
        assert all("my_helper" in v.message for v in violations)

    def test_no_duplicate_across_test_files(self, tmp_path):
        from harness_skills.gates.principles import _scan_prefer_shared_utilities

        _write_py(tmp_path, "tests/test_a.py", "def setup():\n    pass\n")
        _write_py(tmp_path, "tests/test_b.py", "def setup():\n    pass\n")
        violations = _scan_prefer_shared_utilities(tmp_path, "P018", "warning")
        assert not violations

    def test_dunder_methods_exempt(self, tmp_path):
        from harness_skills.gates.principles import _scan_prefer_shared_utilities

        _write_py(tmp_path, "src/a.py", "class A:\n    def __init__(self):\n        pass\n")
        _write_py(tmp_path, "src/b.py", "class B:\n    def __init__(self):\n        pass\n")
        violations = _scan_prefer_shared_utilities(tmp_path, "P018", "warning")
        assert not violations


class TestPrinciplesTestStructure:
    """Cover _scan_test_structure and _body_has_assert (lines 926-1000)."""

    def test_test_without_assert_flagged(self, tmp_path):
        from harness_skills.gates.principles import _scan_test_structure

        _write_py(tmp_path, "test_app.py", "def test_foo():\n    x = 1\n")
        violations = _scan_test_structure(tmp_path, "P019", "warning")
        no_assert = [v for v in violations if "no assert" in v.message]
        assert len(no_assert) == 1

    def test_test_with_assert_passes(self, tmp_path):
        from harness_skills.gates.principles import _scan_test_structure

        _write_py(tmp_path, "test_app.py", "def test_foo():\n    assert True\n")
        violations = _scan_test_structure(tmp_path, "P019", "warning")
        no_assert = [v for v in violations if "no assert" in v.message]
        assert not no_assert

    def test_test_with_pytest_raises_passes(self, tmp_path):
        from harness_skills.gates.principles import _scan_test_structure

        _write_py(tmp_path, "test_app.py",
                  "import pytest\ndef test_err():\n    with pytest.raises(ValueError):\n        pass\n")
        violations = _scan_test_structure(tmp_path, "P019", "warning")
        no_assert = [v for v in violations if "no assert" in v.message]
        assert not no_assert

    def test_non_test_file_skipped(self, tmp_path):
        from harness_skills.gates.principles import _scan_test_structure

        _write_py(tmp_path, "app.py", "def test_foo():\n    x = 1\n")
        violations = _scan_test_structure(tmp_path, "P019", "warning")
        assert not violations


class TestPrinciplesRenderText:
    """Cover _render_text (lines 1061-1096)."""

    def test_render_text_passed(self):
        from harness_skills.gates.principles import GateResult, _render_text

        result = GateResult(passed=True, violations=[])
        text = _render_text(result)
        assert "PASS" in text

    def test_render_text_failed_with_violations(self):
        from harness_skills.gates.principles import GateResult, Violation, _render_text

        result = GateResult(
            passed=False,
            violations=[
                Violation(
                    principle_id="P011", severity="error",
                    message="Magic number found", file_path="src/foo.py",
                    line_number=42, suggestion="Use a constant",
                ),
                Violation(
                    principle_id="P012", severity="warning",
                    message="Hardcoded URL",
                ),
            ],
        )
        text = _render_text(result)
        assert "FAIL" in text
        assert "P011" in text
        assert "src/foo.py:42" in text
        assert "BLOCKING" in text


class TestPrinciplesRenderJson:
    """Cover _render_json (lines 1099-1110)."""

    def test_render_json_valid(self):
        from harness_skills.gates.principles import GateResult, Violation, _render_json

        result = GateResult(
            passed=True,
            violations=[
                Violation(principle_id="P011", severity="warning", message="warn"),
            ],
            principles_loaded=2,
            principles_scanned=1,
        )
        output = _render_json(result)
        data = json.loads(output)
        assert data["passed"] is True
        assert data["principles_loaded"] == 2
        assert len(data["violations"]) == 1


class TestPrinciplesMainExceptionPath:
    """Cover main() exception handler (lines 1127-1129)."""

    def test_main_returns_2_on_exception(self, tmp_path):
        from harness_skills.gates.principles import main

        with patch("harness_skills.gates.principles.PrinciplesGate.run", side_effect=RuntimeError("boom")):
            code = main(["--root", str(tmp_path)])
        assert code == 2


class TestPrinciplesBuildArgParser:
    """Cover _build_arg_parser (lines 1031-1058 approximately)."""

    def test_build_arg_parser(self):
        from harness_skills.gates.principles import _build_arg_parser

        p = _build_arg_parser()
        args = p.parse_args(["--root", "/tmp", "--format", "json",
                            "--no-fail-on-critical", "--fail-on-error",
                            "--principles-file", "custom.yaml",
                            "--rules", "no_magic_numbers"])
        assert args.root == "/tmp"
        assert args.format == "json"
        assert args.no_fail_on_critical is True
        assert args.fail_on_error is True


# ===========================================================================
# 3. harness_skills/gates/performance.py — uncovered: 62-63, 149, 198-204,
#    234-247, 454, 545, 573, 611, 665, 696, 712-769
# ===========================================================================


class TestPerformanceYamlNotAvailable:
    """Cover yaml unavailable fallback (lines 62-63)."""

    def test_load_thresholds_json_fallback(self, tmp_path):
        from harness_skills.gates.performance import _load_thresholds

        # Write a JSON thresholds file
        thresholds = {"version": "1.0", "defaults": {}, "rules": []}
        path = tmp_path / "thresholds.json"
        path.write_text(json.dumps(thresholds))
        result = _load_thresholds(path)
        assert result["version"] == "1.0"


class TestPerformanceResultStr:
    """Cover PerformanceGateResult.__str__ (lines 234-247)."""

    def test_str_with_violations(self):
        from harness_skills.gates.performance import (
            PerformanceGateResult, ThresholdViolation,
        )

        result = PerformanceGateResult(
            passed=False,
            violations=[
                ThresholdViolation(
                    rule_id="api_endpoint_latency",
                    description="Too slow",
                    severity="error",
                    span_name="GET /api/users",
                    measured_ms=600,
                    threshold_ms=500,
                    suggestion="Optimize the query",
                ),
            ],
            rules_evaluated=1,
            spans_evaluated=5,
        )
        s = str(result)
        assert "FAILED" in s
        assert "api_endpoint_latency" in s
        assert "Optimize" in s

    def test_str_passed(self):
        from harness_skills.gates.performance import PerformanceGateResult

        result = PerformanceGateResult(passed=True, rules_evaluated=2, spans_evaluated=10)
        s = str(result)
        assert "PASSED" in s


class TestPerformancePrintViolations:
    """Cover print_violations (lines 198-204)."""

    def test_print_no_violations(self, capsys):
        from harness_skills.gates.performance import PerformanceGateResult

        PerformanceGateResult(passed=True).print_violations()
        captured = capsys.readouterr().out
        assert "No threshold violations" in captured

    def test_print_with_violations(self, capsys):
        from harness_skills.gates.performance import (
            PerformanceGateResult, ThresholdViolation,
        )

        result = PerformanceGateResult(
            passed=False,
            violations=[
                ThresholdViolation(
                    rule_id="test_rule",
                    description="desc",
                    severity="error",
                    span_name="span1",
                    measured_ms=100,
                    threshold_ms=50,
                    suggestion="Fix it",
                ),
            ],
        )
        result.print_violations()
        captured = capsys.readouterr().out
        assert "test_rule" in captured
        assert "Fix it" in captured


class TestPerformanceThresholdViolationSummary:
    """Cover ThresholdViolation.summary (line 149)."""

    def test_summary_format(self):
        from harness_skills.gates.performance import ThresholdViolation

        v = ThresholdViolation(
            rule_id="api_latency",
            description="desc",
            severity="error",
            span_name="GET /api",
            measured_ms=600.5,
            threshold_ms=500.0,
            percentile="p99",
        )
        s = v.summary()
        assert "ERROR" in s
        assert "api_latency" in s
        assert "p99" in s


class TestPerformanceLoadSpansNonList:
    """Cover _load_spans_file with non-list JSON (line 454 approx)."""

    def test_non_list_json_raises(self, tmp_path):
        from harness_skills.gates.performance import _load_spans_file

        path = tmp_path / "spans.json"
        path.write_text('{"not": "a list"}')
        with pytest.raises(ValueError, match="JSON array"):
            _load_spans_file(path)


class TestPerformanceOutputFile:
    """Cover output_file writing (line 696)."""

    def test_output_file_written(self, tmp_path):
        from harness_skills.gates.performance import PerformanceGate, SpanRecord
        from harness_skills.models.gate_configs import PerformanceGateConfig

        # Write thresholds
        thresholds = {
            "version": "1.0",
            "defaults": {"percentile": "p99"},
            "rules": [],
        }
        th_path = tmp_path / "thresholds.yml"
        th_path.write_text(json.dumps(thresholds))

        output_path = tmp_path / "report" / "perf.json"
        cfg = PerformanceGateConfig(
            thresholds_file=str(th_path),
            output_file=str(output_path),
        )
        gate = PerformanceGate(cfg)
        result = gate.run(spans=[], repo_root=tmp_path)
        assert result.passed
        assert output_path.exists()
        report = json.loads(output_path.read_text())
        assert "summary" in report


class TestPerformanceBuildParser:
    """Cover _build_parser (lines 712-769)."""

    def test_build_parser_defaults(self):
        from harness_skills.gates.performance import _build_parser

        p = _build_parser()
        args = p.parse_args([])
        assert args.thresholds_file == ".harness/perf-thresholds.yml"
        assert args.spans_file == "perf-spans.json"

    def test_build_parser_all_options(self):
        from harness_skills.gates.performance import _build_parser

        p = _build_parser()
        args = p.parse_args([
            "--thresholds", "my-thresholds.yml",
            "--spans", "my-spans.json",
            "--baseline", "baseline.json",
            "--output", "report.json",
            "--root", "/tmp",
            "--no-fail-on-error",
            "--quiet",
        ])
        assert args.thresholds_file == "my-thresholds.yml"
        assert args.baseline_file == "baseline.json"
        assert args.no_fail_on_error is True
        assert args.quiet is True


class TestPerformanceBaselineRegression:
    """Cover _check_baseline_regression (lines 545, 573 approx)."""

    def test_baseline_regression_detected(self, tmp_path):
        from harness_skills.gates.performance import PerformanceGate, SpanRecord
        from harness_skills.models.gate_configs import PerformanceGateConfig

        # Write thresholds with baseline enabled
        thresholds = {
            "version": "1.0",
            "defaults": {"percentile": "p99"},
            "rules": [],
            "baseline": {
                "enabled": True,
                "regression_threshold_pct": 10.0,
                "severity": "warning",
            },
        }
        th_path = tmp_path / "thresholds.yml"
        th_path.write_text(json.dumps(thresholds))

        # Write baseline spans (fast)
        baseline = [
            {"name": "GET /api", "span_type": "http_endpoint", "duration_ms": 100},
            {"name": "GET /api", "span_type": "http_endpoint", "duration_ms": 100},
        ]
        baseline_path = tmp_path / "baseline.json"
        baseline_path.write_text(json.dumps(baseline))

        # Current spans (slow — 50% regression)
        current_spans = [
            SpanRecord("GET /api", "http_endpoint", duration_ms=150),
            SpanRecord("GET /api", "http_endpoint", duration_ms=150),
        ]

        cfg = PerformanceGateConfig(
            thresholds_file=str(th_path),
            baseline_file=str(baseline_path),
        )
        gate = PerformanceGate(cfg)
        result = gate.run(spans=current_spans, repo_root=tmp_path)
        regression_violations = [v for v in result.violations if v.rule_id == "baseline_regression"]
        assert len(regression_violations) >= 1


class TestPerformanceSpansFromFile:
    """Cover spans loaded from config.spans_file path (line 611)."""

    def test_spans_file_missing(self, tmp_path):
        from harness_skills.gates.performance import PerformanceGate
        from harness_skills.models.gate_configs import PerformanceGateConfig

        thresholds = {"version": "1.0", "defaults": {}, "rules": []}
        th_path = tmp_path / "thresholds.yml"
        th_path.write_text(json.dumps(thresholds))

        cfg = PerformanceGateConfig(
            thresholds_file=str(th_path),
            spans_file="missing-spans.json",
        )
        gate = PerformanceGate(cfg)
        result = gate.run(repo_root=tmp_path)
        assert not result.passed
        assert result.violations[0].rule_id == "spans_file_missing"


class TestPerformanceDisabledRule:
    """Cover rule with enabled=false (line 665 approx)."""

    def test_disabled_rule_skipped(self, tmp_path):
        from harness_skills.gates.performance import PerformanceGate, SpanRecord
        from harness_skills.models.gate_configs import PerformanceGateConfig

        thresholds = {
            "version": "1.0",
            "defaults": {},
            "rules": [
                {
                    "id": "disabled_rule",
                    "enabled": False,
                    "selector": {"type": "http_endpoint"},
                    "threshold": {"value": 100, "operator": "lte"},
                },
            ],
        }
        th_path = tmp_path / "thresholds.yml"
        th_path.write_text(json.dumps(thresholds))

        spans = [SpanRecord("GET /api", "http_endpoint", duration_ms=200)]
        cfg = PerformanceGateConfig(thresholds_file=str(th_path))
        gate = PerformanceGate(cfg)
        result = gate.run(spans=spans, repo_root=tmp_path)
        # Disabled rule is not evaluated
        assert result.rules_evaluated == 0


# ===========================================================================
# 4. harness_skills/gates/security.py — uncovered: 255-256, 357, 362, 366,
#    370, 374, 378, 505-506, 543, 661-729
# ===========================================================================


class TestSecurityScanFileOSError:
    """Cover OSError path in _scan_file_for_secrets (line 255-256)."""

    def test_oserror_returns_empty(self, tmp_path):
        from harness_skills.gates.security import _scan_file_for_secrets

        path = tmp_path / "doesntexist.py"
        result = _scan_file_for_secrets(path, [], "error")
        assert result == []


class TestSecurityParsePipAuditEdgeCases:
    """Cover edge cases in _parse_pip_audit_report (lines 357-378)."""

    def test_non_list_vulns_skipped(self):
        from harness_skills.gates.security import _parse_pip_audit_report

        data = [{"name": "pkg", "version": "1.0", "vulns": "not_a_list"}]
        result = _parse_pip_audit_report(data, "HIGH", [], "error")
        assert result == []

    def test_non_dict_vuln_skipped(self):
        from harness_skills.gates.security import _parse_pip_audit_report

        data = [{"name": "pkg", "version": "1.0", "vulns": ["not_a_dict"]}]
        result = _parse_pip_audit_report(data, "HIGH", [], "error")
        assert result == []

    def test_non_list_aliases_handled(self):
        from harness_skills.gates.security import _parse_pip_audit_report

        data = [{"name": "pkg", "version": "1.0", "vulns": [
            {"id": "CVE-1", "aliases": "not_a_list", "severity": "HIGH"},
        ]}]
        result = _parse_pip_audit_report(data, "HIGH", [], "error")
        assert len(result) == 1

    def test_non_list_fix_versions_handled(self):
        from harness_skills.gates.security import _parse_pip_audit_report

        data = [{"name": "pkg", "version": "1.0", "vulns": [
            {"id": "CVE-1", "fix_versions": "not_a_list", "severity": "HIGH"},
        ]}]
        result = _parse_pip_audit_report(data, "HIGH", [], "error")
        assert len(result) == 1

    def test_non_string_severity_defaults_to_high(self):
        from harness_skills.gates.security import _parse_pip_audit_report

        data = [{"name": "pkg", "version": "1.0", "vulns": [
            {"id": "CVE-1", "severity": 123},
        ]}]
        result = _parse_pip_audit_report(data, "HIGH", [], "error")
        assert len(result) == 1

    def test_non_dict_pkg_skipped(self):
        from harness_skills.gates.security import _parse_pip_audit_report

        data = ["not_a_dict", {"name": "pkg", "version": "1.0", "vulns": []}]
        result = _parse_pip_audit_report(data, "HIGH", [], "error")
        assert result == []


class TestSecurityInputValidationOSError:
    """Cover OSError in _scan_file_for_unsafe_input (line 505-506)."""

    def test_oserror_returns_empty(self, tmp_path):
        from harness_skills.gates.security import _scan_file_for_unsafe_input

        path = tmp_path / "doesntexist.py"
        result = _scan_file_for_unsafe_input(path, [], "error")
        assert result == []


class TestSecurityDependencyAuditorParseError:
    """Cover audit report parse error (line 543)."""

    def test_corrupt_audit_report(self, tmp_path):
        from harness_skills.gates.security import _DependencyAuditor

        (tmp_path / "pip-audit-report.json").write_text("{bad json")
        auditor = _DependencyAuditor("HIGH", [], True)
        result = auditor.audit(tmp_path)
        assert len(result) == 1
        assert result[0].kind == "missing_audit_report"


class TestSecurityBuildParser:
    """Cover _build_parser (lines 661-729)."""

    def test_build_parser_defaults(self):
        from harness_skills.gates.security import _build_parser

        p = _build_parser()
        args = p.parse_args([])
        assert args.severity_threshold == "HIGH"
        assert args.scan_secrets is False
        assert args.scan_dependencies is True

    def test_build_parser_all_options(self):
        from harness_skills.gates.security import _build_parser

        p = _build_parser()
        args = p.parse_args([
            "--root", "/tmp",
            "--severity", "MEDIUM",
            "--scan-secrets",
            "--no-scan-dependencies",
            "--no-scan-input-validation",
            "--no-fail-on-error",
            "--ignore-ids", "CVE-1234", "hardcoded-password",
            "--quiet",
        ])
        assert args.severity_threshold == "MEDIUM"
        assert args.scan_secrets is True
        assert args.scan_dependencies is False
        assert args.scan_input_validation is False
        assert args.fail_on_error is False
        assert args.ignore_ids == ["CVE-1234", "hardcoded-password"]


# ===========================================================================
# 5. harness_skills/gates/coverage.py — uncovered: 231-232, 294-295,
#    397-407, 476-529
# ===========================================================================


class TestCoverageJaCoCoMalformedCounter:
    """Cover malformed JaCoCo counter values (lines 231-232)."""

    def test_malformed_counter_values_skipped(self, tmp_path):
        from harness_skills.gates.coverage import _parse_xml

        f = tmp_path / "jacoco.xml"
        f.write_text(
            '<?xml version="1.0"?>\n'
            '<report name="x">\n'
            '  <counter type="LINE" missed="abc" covered="def"/>\n'
            '  <counter type="LINE" missed="5" covered="95"/>\n'
            '</report>\n'
        )
        result = _parse_xml(f)
        assert result == pytest.approx(95.0)


class TestCoverageLcovOSError:
    """Cover lcov read error (lines 294-295)."""

    def test_unreadable_lcov_raises(self, tmp_path):
        from harness_skills.gates.coverage import _parse_lcov, _ParseError

        path = tmp_path / "nonexistent.info"
        with pytest.raises(_ParseError, match="Cannot read"):
            _parse_lcov(path)


class TestCoverageUnknownFormat:
    """Cover unknown format path (lines 397-407)."""

    def test_unknown_format_violation(self, tmp_path):
        from harness_skills.gates.coverage import CoverageGate
        from harness_skills.models.gate_configs import CoverageGateConfig

        (tmp_path / "cov.dat").write_text("data")
        cfg = CoverageGateConfig(
            coverage_file="cov.dat",
            report_format="badformat",
        )
        result = CoverageGate(cfg).run(tmp_path)
        assert result.violations[0].kind == "parse_error"
        assert "Unknown coverage report format" in result.violations[0].message

    def test_unknown_format_advisory_passes(self, tmp_path):
        from harness_skills.gates.coverage import CoverageGate
        from harness_skills.models.gate_configs import CoverageGateConfig

        (tmp_path / "cov.dat").write_text("data")
        cfg = CoverageGateConfig(
            coverage_file="cov.dat",
            report_format="badformat",
            fail_on_error=False,
        )
        result = CoverageGate(cfg).run(tmp_path)
        assert result.passed


class TestCoverageBuildParser:
    """Cover _build_parser (lines 476-529)."""

    def test_build_parser(self):
        from harness_skills.gates.coverage import _build_parser

        p = _build_parser()
        args = p.parse_args(["--root", "/tmp", "--threshold", "85",
                            "--coverage-file", "cov.json", "--format", "json",
                            "--no-fail-on-error", "--quiet"])
        assert args.root == "/tmp"
        assert args.threshold == 85.0
        assert args.report_format == "json"
        assert args.fail_on_error is False


# ===========================================================================
# 6. harness_skills/gates/docs_freshness.py — uncovered: 22, 76, 118-122,
#    132-133, 138
# ===========================================================================


class TestDocsFreshnessGateConfigValidation:
    """Cover GateConfig.__post_init__ validation (line 22)."""

    def test_invalid_staleness_days_raises(self):
        from harness_skills.gates.docs_freshness import GateConfig

        with pytest.raises(ValueError, match="max_staleness_days must be >= 1"):
            GateConfig(max_staleness_days=0)

    def test_negative_staleness_raises(self):
        from harness_skills.gates.docs_freshness import GateConfig

        with pytest.raises(ValueError, match="max_staleness_days must be >= 1"):
            GateConfig(max_staleness_days=-5)


class TestDocsFreshnessWarningsHelper:
    """Cover GateResult.warnings (line 76)."""

    def test_warnings_returns_warning_severity(self, tmp_path):
        from harness_skills.gates.docs_freshness import DocsFreshnessGate, GateConfig

        (tmp_path / "AGENTS.md").write_text("# AGENTS\nNo date.\n")
        gate = DocsFreshnessGate(GateConfig(fail_on_error=False))
        result = gate.run(tmp_path)
        assert len(result.warnings()) >= 1
        assert all(v.severity == "warning" for v in result.warnings())


class TestDocsFreshnessBarePathRef:
    """Cover bare path extraction (lines 118-122)."""

    def test_bare_path_detected(self, tmp_path):
        from harness_skills.gates.docs_freshness import _extract_file_refs

        content = "Check src/models/user.py for details.\n"
        refs = _extract_file_refs(content)
        paths = [p for p, _ in refs]
        assert "src/models/user.py" in paths


class TestDocsFreshnessInvalidTimestamp:
    """Cover invalid date parsing (lines 132-133)."""

    def test_invalid_date_returns_none(self):
        from harness_skills.gates.docs_freshness import _parse_generated_at

        result = _parse_generated_at("generated_at: 2025-13-45")
        assert result is None


class TestDocsFreshnessLastUpdatedAlias:
    """Cover last_updated alias in regex (line 138 approx)."""

    def test_last_updated_alias(self):
        from harness_skills.gates.docs_freshness import _parse_generated_at
        from datetime import date

        result = _parse_generated_at("last_updated: 2025-06-01")
        assert result == date(2025, 6, 1)


class TestDocsFreshnessLooksLikeFilePath:
    """Cover edge cases in _looks_like_file_path."""

    def test_long_path_rejected(self):
        from harness_skills.gates.docs_freshness import _looks_like_file_path

        assert not _looks_like_file_path("a" * 261)

    def test_mailto_rejected(self):
        from harness_skills.gates.docs_freshness import _looks_like_file_path

        assert not _looks_like_file_path("mailto:user@example.com")

    def test_curly_brace_rejected(self):
        from harness_skills.gates.docs_freshness import _looks_like_file_path

        assert not _looks_like_file_path("{variable}")

    def test_slash_prefix_rejected(self):
        from harness_skills.gates.docs_freshness import _looks_like_file_path

        assert not _looks_like_file_path("/absolute/path")


# ===========================================================================
# 7. harness_skills/gates/regression.py — uncovered: 190, 425-475
# ===========================================================================


class TestRegressionParseJunitNoSuites:
    """Cover empty suites path (line 190)."""

    def test_no_testsuite_elements(self, tmp_path):
        from harness_skills.gates.regression import _parse_junit_xml

        f = tmp_path / "empty.xml"
        f.write_text('<?xml version="1.0"?>\n<results/>\n')
        violations, stats = _parse_junit_xml(f, "error")
        assert violations == []
        assert stats == {}


class TestRegressionBuildParser:
    """Cover _build_parser (lines 425-475)."""

    def test_build_parser_defaults(self):
        from harness_skills.gates.regression import _build_parser

        p = _build_parser()
        args = p.parse_args([])
        assert args.root == "."
        assert args.timeout_seconds == 300

    def test_build_parser_all_options(self):
        from harness_skills.gates.regression import _build_parser

        p = _build_parser()
        args = p.parse_args([
            "--root", "/tmp",
            "--timeout", "60",
            "--test-paths", "tests/unit", "tests/integration",
            "--no-fail-on-error",
            "--quiet",
        ])
        assert args.root == "/tmp"
        assert args.timeout_seconds == 60
        assert args.test_paths == ["tests/unit", "tests/integration"]
        assert args.fail_on_error is False


# ===========================================================================
# 8. harness_skills/telemetry_reporter.py — uncovered due to circular import
#    We test via mocking the circular import chain
# ===========================================================================


def _get_telemetry_module():
    """Import harness_skills.telemetry_reporter, handling circular import."""
    import sys as _sys

    if "harness_skills.telemetry_reporter" in _sys.modules:
        return _sys.modules["harness_skills.telemetry_reporter"]

    # Pre-populate mocks to break the circular import chain
    mock_verbosity = MagicMock()
    mock_verbosity.VerbosityLevel = MagicMock()
    mock_verbosity.get_verbosity = MagicMock()
    mock_verbosity.vecho = MagicMock()
    mocks = {}
    for mod_name in [
        "harness_skills.cli",
        "harness_skills.cli.main",
        "harness_skills.cli.verbosity",
    ]:
        if mod_name not in _sys.modules:
            _sys.modules[mod_name] = mock_verbosity
            mocks[mod_name] = mock_verbosity

    try:
        import harness_skills.telemetry_reporter as tr_mod
        return tr_mod
    except ImportError:
        return None


class TestTelemetryReporterCoreFunctions:
    """Test telemetry_reporter functions by importing only what we need."""

    def test_load_telemetry_corrupt_file(self, tmp_path):
        """Cover _load_telemetry with corrupt JSON file (line 91)."""
        path = tmp_path / "telemetry.json"
        path.write_text("{bad json")

        tr_mod = _get_telemetry_module()
        assert tr_mod is not None, "telemetry_reporter could not be imported"
        with patch.object(tr_mod, "click", MagicMock()):
            result = tr_mod._load_telemetry(path)
        assert result["schema_version"] is None

    def test_categorise_artifact_unused(self):
        tr_mod = _get_telemetry_module()
        cat, rec = tr_mod._categorise_artifact(0, 0.0, 0.2, 0.6, 0.0)
        assert cat == "unused"
        assert rec is not None

    def test_categorise_artifact_warm(self):
        tr_mod = _get_telemetry_module()
        cat, rec = tr_mod._categorise_artifact(5, 0.15, 0.2, 0.6, 0.4)
        assert cat == "warm"
        assert rec is None

    def test_gate_signal_silent(self):
        tr_mod = _get_telemetry_module()
        signal, rec = tr_mod._gate_signal(0.0)
        assert signal == "silent"
        assert rec is not None

    def test_gate_signal_low(self):
        tr_mod = _get_telemetry_module()
        signal, rec = tr_mod._gate_signal(0.15)
        assert signal == "low"
        assert rec is not None

    def test_gate_signal_medium(self):
        tr_mod = _get_telemetry_module()
        signal, rec = tr_mod._gate_signal(0.45)
        assert signal == "medium"
        assert rec is None

    def test_gate_signal_high(self):
        tr_mod = _get_telemetry_module()
        signal, rec = tr_mod._gate_signal(0.7)
        assert signal == "high"
        assert rec is None

    def test_bar_function(self):
        tr_mod = _get_telemetry_module()
        result = tr_mod._bar(0.5, width=10)
        assert len(result) == 10
        assert result.count("\u2588") == 5

    def test_render_report_with_silent_gates(self, tmp_path):
        tr_mod = _get_telemetry_module()
        path = tmp_path / "tel.json"
        data = {
            "schema_version": "1.0",
            "last_updated": "2026-03-22T00:00:00+00:00",
            "totals": {
                "artifact_reads": {"a.md": 100, "b.md": 1},
                "cli_command_invocations": {"cmd1": 10},
                "gate_failures": {"ruff": 10, "dead_gate": 0},
            },
            "sessions": [],
        }
        path.write_text(json.dumps(data))
        report = tr_mod.build_report(path)
        text = tr_mod.render_report(report)
        assert "Gate Effectiveness" in text

    def test_render_report_long_path_truncated(self, tmp_path):
        tr_mod = _get_telemetry_module()
        long_name = "x" * 60 + ".md"
        path = tmp_path / "tel.json"
        data = {
            "schema_version": "1.0",
            "last_updated": "2026-03-22T00:00:00+00:00",
            "totals": {
                "artifact_reads": {long_name: 10},
                "cli_command_invocations": {},
                "gate_failures": {},
            },
            "sessions": [],
        }
        path.write_text(json.dumps(data))
        report = tr_mod.build_report(path)
        text = tr_mod.render_report(report)
        assert "Artifact Utilization" in text


# ===========================================================================
# 9. harness_skills/handoff.py — uncovered: 199, 209, 557-591, 672-678,
#    686, 694-728, 741-746, 783
# ===========================================================================


class TestHandoffTrackerInit:
    """Cover HandoffTracker.__init__ (lines 672-678)."""

    def test_tracker_defaults(self, tmp_path):
        from harness_skills.handoff import HandoffTracker

        tracker = HandoffTracker(task="My task")
        assert tracker.task == "My task"
        assert tracker.plan_id == "my-task"
        assert tracker.agent_id == "unknown"
        assert tracker.write_progress_log is True

    def test_tracker_empty_task_uses_unnamed(self, tmp_path):
        from harness_skills.handoff import HandoffTracker

        tracker = HandoffTracker(task="", plan_id="")
        assert tracker.plan_id == "unnamed"

    def test_tracker_custom_plan_id(self, tmp_path):
        from harness_skills.handoff import HandoffTracker

        tracker = HandoffTracker(task="t", plan_id="my-plan")
        assert tracker.plan_id == "my-plan"


class TestHandoffTrackerSystemPrompt:
    """Cover HandoffTracker.system_prompt_addendum (line 686)."""

    def test_system_prompt_addendum(self, tmp_path):
        from harness_skills.handoff import HandoffTracker

        tracker = HandoffTracker(
            task="Build auth",
            handoff_path=tmp_path / "progress.md",
        )
        prompt = tracker.system_prompt_addendum()
        assert "Build auth" in prompt
        assert "HANDOFF PROTOCOL" in prompt


class TestHandoffTrackerHooks:
    """Cover HandoffTracker.hooks (lines 741-746)."""

    def test_hooks_returns_empty_without_sdk(self):
        from harness_skills.handoff import HandoffTracker

        tracker = HandoffTracker(task="test")
        # claude_agent_sdk is not installed, so hooks() returns {}
        result = tracker.hooks()
        assert result == {}


class TestHandoffTrackerStopHook:
    """Cover _make_stop_hook (lines 694-728)."""

    def test_stop_hook_no_handoff(self, tmp_path, capsys):
        import asyncio
        from harness_skills.handoff import HandoffTracker

        tracker = HandoffTracker(
            task="test",
            handoff_path=tmp_path / "missing.md",
            jsonl_path=tmp_path / "audit.jsonl",
        )
        hook = tracker._make_stop_hook()
        result = asyncio.get_event_loop().run_until_complete(hook({}, "tool_id", None))
        assert result == {}

    def test_stop_hook_with_handoff(self, tmp_path):
        import asyncio
        from harness_skills.handoff import HandoffTracker, HandoffProtocol, HandoffDocument, SearchHints

        # Write a handoff file
        doc = HandoffDocument(
            session_id="s1",
            timestamp="2026-03-22T00:00:00Z",
            task="Test task",
            accomplished=["Did thing"],
            next_steps=["Do next thing"],
            search_hints=SearchHints(file_paths=["src/foo.py"]),
        )
        hp = HandoffProtocol(handoff_path=tmp_path / "progress.md")
        hp.write_handoff(doc)

        tracker = HandoffTracker(
            task="Test task",
            plan_id="test-plan",
            agent_id="test-agent",
            handoff_path=tmp_path / "progress.md",
            jsonl_path=tmp_path / "audit.jsonl",
            write_progress_log=False,  # skip progress log
        )
        hook = tracker._make_stop_hook()
        result = asyncio.get_event_loop().run_until_complete(hook({}, "tool_id", None))
        assert result == {}
        # JSONL file should be created
        assert (tmp_path / "audit.jsonl").exists()


class TestHandoffAppendProgressLog:
    """Cover _append_progress_log_entry (lines 557-591)."""

    def test_append_progress_log_no_import(self, tmp_path):
        """When skills.progress_log is not importable, it's a no-op."""
        from harness_skills.handoff import _append_progress_log_entry, HandoffDocument, SearchHints

        doc = HandoffDocument(
            session_id="s1",
            timestamp="2026-03-22T00:00:00Z",
            task="Test",
            status="done",
            accomplished=["item"],
            next_steps=["next"],
            search_hints=SearchHints(file_paths=["src/foo.py"]),
        )
        # Should not raise — silently no-ops when skills.progress_log unavailable
        _append_progress_log_entry(doc, plan_id="p1", agent_id="a1")


class TestHandoffFromMarkdownEdgeCases:
    """Cover from_markdown with partial sections."""

    def test_from_markdown_no_notes_section(self):
        from harness_skills.handoff import HandoffDocument

        md = textwrap.dedent("""\
            ---
            session_id: x
            timestamp: '2026-01-01T00:00:00Z'
            task: test
            status: in_progress
            ---

            ## Accomplished
            - did thing

            ## In Progress
            *(none)*

            ## Next Steps
            - next thing

            ## Search Hints
            *(no hints recorded)*

            ## Open Questions
            *(none)*

            ## Artifacts
            *(none)*
        """)
        doc = HandoffDocument.from_markdown(md)
        assert doc.accomplished == ["did thing"]
        assert doc.notes == ""


class TestHandoffGetSearchHintsEmpty:
    """Cover get_search_hints with empty file (line 783)."""

    def test_empty_jsonl_returns_none(self, tmp_path):
        from harness_skills.handoff import HandoffTracker

        path = tmp_path / "empty.jsonl"
        path.write_text("\n\n")
        result = HandoffTracker.get_search_hints(jsonl_path=path)
        assert result is None


# ===========================================================================
# 10. harness_skills/plugins/loader.py — uncovered: 47-63
# ===========================================================================


class TestLoadAllGates:
    """Cover load_all_gates function (lines 47-63)."""

    def test_load_all_gates_no_plugins_key(self):
        from harness_skills.plugins.loader import load_all_gates

        result = load_all_gates({})
        assert isinstance(result, list)

    def test_load_all_gates_with_config_gates(self):
        from harness_skills.plugins.loader import load_all_gates

        profile = {
            "gates": {
                "plugins": [
                    {"gate_id": "my_gate", "gate_name": "My Gate", "command": "exit 0"},
                ],
            },
        }
        result = load_all_gates(profile)
        assert len(result) >= 1
        assert result[0].gate_id == "my_gate"

    def test_load_all_gates_merges_entry_points(self):
        from harness_skills.plugins.loader import load_all_gates
        from harness_skills.plugins.gate_plugin import PluginGateConfig

        # Mock discover_plugins to return a plugin with gate_config
        mock_cls = MagicMock()
        mock_cls.gate_config.return_value = PluginGateConfig(
            gate_id="ep_gate", gate_name="EP Gate", command="echo ok"
        )

        with patch(
            "harness_skills.plugins.discovery.discover_plugins",
            return_value={"ep_gate": mock_cls},
        ):
            result = load_all_gates({})
        assert any(g.gate_id == "ep_gate" for g in result)

    def test_load_all_gates_skips_duplicate_from_entry_points(self):
        from harness_skills.plugins.loader import load_all_gates
        from harness_skills.plugins.gate_plugin import PluginGateConfig

        profile = {
            "gates": {
                "plugins": [
                    {"gate_id": "dup_gate", "gate_name": "Config Gate", "command": "exit 0"},
                ],
            },
        }
        mock_cls = MagicMock()
        mock_cls.gate_config.return_value = PluginGateConfig(
            gate_id="dup_gate", gate_name="EP Gate", command="echo ok"
        )
        with patch(
            "harness_skills.plugins.discovery.discover_plugins",
            return_value={"dup_gate": mock_cls},
        ):
            result = load_all_gates(profile)
        assert len([g for g in result if g.gate_id == "dup_gate"]) == 1
        assert result[0].gate_name == "Config Gate"

    def test_load_all_gates_entry_point_error_handled(self, caplog):
        import logging
        from harness_skills.plugins.loader import load_all_gates

        mock_cls = MagicMock()
        mock_cls.gate_config.side_effect = RuntimeError("broken plugin")

        with patch(
            "harness_skills.plugins.discovery.discover_plugins",
            return_value={"broken_gate": mock_cls},
        ):
            with caplog.at_level(logging.WARNING, logger="harness_skills.plugins.loader"):
                result = load_all_gates({})
        assert result == []

    def test_load_all_gates_no_gate_config_attr(self):
        from harness_skills.plugins.loader import load_all_gates

        mock_cls = MagicMock(spec=[])  # no gate_config attribute
        with patch(
            "harness_skills.plugins.discovery.discover_plugins",
            return_value={"no_config_gate": mock_cls},
        ):
            result = load_all_gates({})
        # Plugin without gate_config is skipped
        assert not any(g.gate_id == "no_config_gate" for g in result)

    def test_load_all_gates_non_plugin_gate_config(self):
        from harness_skills.plugins.loader import load_all_gates

        mock_cls = MagicMock()
        mock_cls.gate_config.return_value = "not a PluginGateConfig"

        with patch(
            "harness_skills.plugins.discovery.discover_plugins",
            return_value={"bad_return": mock_cls},
        ):
            result = load_all_gates({})
        assert not any(getattr(g, "gate_id", None) == "bad_return" for g in result)

    def test_load_all_gates_discovery_import_error(self):
        """Cover ImportError fallback when discovery module unavailable."""
        from harness_skills.plugins import loader as loader_mod
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "harness_skills.plugins.discovery":
                raise ImportError("no discovery")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            result = loader_mod.load_all_gates({})
        assert isinstance(result, list)
