"""
tests/gates/test_types.py
==========================
Unit tests for :mod:`harness_skills.gates.types`.

Test strategy
-------------
* **Zero-error policy** — the gate must fail whenever mypy / tsc reports
  *any* error-severity violation, regardless of count.
* **Warning passthrough** — warnings and notes are collected but the gate
  still passes.
* **Checker auto-detection** — correct checker is selected based on project
  markers (``pyproject.toml`` → mypy, ``tsconfig.json`` → tsc).
* **Explicit checker selection** — ``checker="mypy"|"tsc"|"pyright"``
  overrides auto-detection.
* **Strict mode** — ``--strict`` is forwarded to mypy; gate fails on strict
  violations.
* **ignore_errors** — specified codes are filtered from the violation list
  and never trigger a failure.
* **fail_on_error=False** — advisory mode: violations are downgraded to
  warnings and the gate always passes.
* **Checker not found** — missing binary returns a well-formed failure
  rather than an uncaught exception.
* **No source detected** — project with neither pyproject.toml nor
  tsconfig.json results in a graceful skip.
* **Output parsing** — mypy, tsc, and pyright output formats are each
  exercised with multi-error fixtures.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from harness_skills.gates.types import (
    TypesGate,
    TypesGateResult,
    TypeViolation,
    _detect_checker,
    _parse_mypy_output,
    _parse_tsc_output,
    _parse_pyright_output,
)
from harness_skills.models.gate_configs import TypesGateConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_completed_process(returncode: int, stdout: str, stderr: str = ""):
    """Return a mock CompletedProcess with the given fields."""
    mock = MagicMock()
    mock.returncode = returncode
    mock.stdout = stdout
    mock.stderr = stderr
    return mock


# ---------------------------------------------------------------------------
# _detect_checker
# ---------------------------------------------------------------------------


class TestDetectChecker:
    """Auto-detection logic based on project markers."""

    def test_explicit_mypy_overrides_layout(self, tmp_path):
        # No markers present — explicit hint wins
        assert _detect_checker(tmp_path, "mypy") == "mypy"

    def test_explicit_tsc_overrides_layout(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        assert _detect_checker(tmp_path, "tsc") == "tsc"

    def test_auto_detects_mypy_via_pyproject(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        assert _detect_checker(tmp_path, "auto") == "mypy"

    def test_auto_detects_mypy_via_setup_py(self, tmp_path):
        (tmp_path / "setup.py").write_text("from setuptools import setup\n")
        assert _detect_checker(tmp_path, "auto") == "mypy"

    def test_auto_detects_mypy_via_mypy_ini(self, tmp_path):
        (tmp_path / "mypy.ini").write_text("[mypy]\n")
        assert _detect_checker(tmp_path, "auto") == "mypy"

    def test_auto_detects_tsc_via_tsconfig(self, tmp_path):
        (tmp_path / "tsconfig.json").write_text("{}\n")
        assert _detect_checker(tmp_path, "auto") == "tsc"

    def test_auto_returns_empty_when_no_markers(self, tmp_path):
        result = _detect_checker(tmp_path, "auto")
        assert result == ""

    def test_pyproject_takes_priority_over_tsconfig(self, tmp_path):
        """When both markers are present Python wins (mypy first)."""
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        (tmp_path / "tsconfig.json").write_text("{}\n")
        assert _detect_checker(tmp_path, "auto") == "mypy"


# ---------------------------------------------------------------------------
# _parse_mypy_output
# ---------------------------------------------------------------------------


class TestParseMypyOutput:
    """Mypy output parsing edge cases."""

    _SAMPLE = textwrap.dedent("""\
        harness_skills/foo.py:12: error: Argument 1 has incompatible type  [arg-type]
        harness_skills/foo.py:12: note: Expected type "str", got "int"
        harness_skills/bar.py:5: warning: Unused "type: ignore" comment  [unused-ignore]
        harness_skills/baz.py:99: error: Module has no attribute "missing"  [attr-defined]
    """)

    def test_parses_errors(self):
        violations = _parse_mypy_output(self._SAMPLE, set(), fail_on_error=True)
        errors = [v for v in violations if v.severity == "error"]
        assert len(errors) == 2

    def test_parses_note_as_note_severity(self):
        violations = _parse_mypy_output(self._SAMPLE, set(), fail_on_error=True)
        notes = [v for v in violations if v.severity == "note"]
        assert len(notes) == 1
        assert "Expected type" in notes[0].message

    def test_parses_warning_severity(self):
        violations = _parse_mypy_output(self._SAMPLE, set(), fail_on_error=True)
        warnings = [v for v in violations if v.severity == "warning"]
        assert len(warnings) == 1

    def test_captures_error_code(self):
        violations = _parse_mypy_output(self._SAMPLE, set(), fail_on_error=True)
        errors = [v for v in violations if v.severity == "error"]
        codes = {v.error_code for v in errors}
        assert "arg-type" in codes
        assert "attr-defined" in codes

    def test_captures_file_and_line(self):
        violations = _parse_mypy_output(self._SAMPLE, set(), fail_on_error=True)
        first_error = next(v for v in violations if v.severity == "error")
        assert first_error.file_path == Path("harness_skills/foo.py")
        assert first_error.line_number == 12

    def test_ignore_codes_filter_matching_violations(self):
        violations = _parse_mypy_output(
            self._SAMPLE, ignore_set={"attr-defined"}, fail_on_error=True
        )
        codes = {v.error_code for v in violations}
        assert "attr-defined" not in codes
        assert "arg-type" in codes

    def test_fail_on_error_false_downgrades_errors_to_warnings(self):
        violations = _parse_mypy_output(self._SAMPLE, set(), fail_on_error=False)
        # With fail_on_error=False, error lines → "warning"
        assert all(v.severity != "error" for v in violations)

    def test_empty_output_produces_no_violations(self):
        assert _parse_mypy_output("", set(), fail_on_error=True) == []

    def test_non_matching_lines_are_skipped(self):
        output = "mypy: error: Cannot find implementation file\n"
        # This line doesn't match the file:line:level: pattern
        violations = _parse_mypy_output(output, set(), fail_on_error=True)
        assert violations == []


# ---------------------------------------------------------------------------
# _parse_tsc_output
# ---------------------------------------------------------------------------


class TestParseTscOutput:
    """TypeScript compiler output parsing."""

    _SAMPLE = textwrap.dedent("""\
        src/index.ts(10,5): error TS2304: Cannot find name 'foo'.
        src/utils.ts(3,12): error TS2345: Argument of type 'number' is not assignable to parameter of type 'string'.
        src/index.ts(15,1): warning TS6133: 'unusedVar' is declared but its value is never read.
    """)

    def test_parses_errors(self):
        violations = _parse_tsc_output(self._SAMPLE, set(), fail_on_error=True)
        errors = [v for v in violations if v.severity == "error"]
        assert len(errors) == 2

    def test_captures_ts_error_code(self):
        violations = _parse_tsc_output(self._SAMPLE, set(), fail_on_error=True)
        codes = {v.error_code for v in violations}
        assert "TS2304" in codes
        assert "TS2345" in codes

    def test_captures_file_and_line(self):
        violations = _parse_tsc_output(self._SAMPLE, set(), fail_on_error=True)
        first = next(v for v in violations if v.error_code == "TS2304")
        assert first.file_path == Path("src/index.ts")
        assert first.line_number == 10

    def test_ignore_codes_filters_ts_codes(self):
        violations = _parse_tsc_output(
            self._SAMPLE, ignore_set={"TS2304"}, fail_on_error=True
        )
        codes = {v.error_code for v in violations}
        assert "TS2304" not in codes
        assert "TS2345" in codes

    def test_fail_on_error_false_downgrades_errors(self):
        violations = _parse_tsc_output(self._SAMPLE, set(), fail_on_error=False)
        assert all(v.severity == "warning" for v in violations)

    def test_empty_output_produces_no_violations(self):
        assert _parse_tsc_output("", set(), fail_on_error=True) == []


# ---------------------------------------------------------------------------
# _parse_pyright_output
# ---------------------------------------------------------------------------


class TestParsePyrightOutput:
    """Pyright text output parsing."""

    _SAMPLE = textwrap.dedent("""\
        /project/src/foo.py:8:4: error: Type of "x" is incompatible  (reportGeneralTypeIssues)
        /project/src/bar.py:22:1: warning: "y" is not used  (reportUnusedVariable)
        /project/src/baz.py:5:10: information: Type is partially unknown  (reportUnknownMemberType)
    """)

    def test_parses_errors(self):
        violations = _parse_pyright_output(self._SAMPLE, set(), fail_on_error=True)
        errors = [v for v in violations if v.severity == "error"]
        assert len(errors) == 1

    def test_information_maps_to_note(self):
        violations = _parse_pyright_output(self._SAMPLE, set(), fail_on_error=True)
        notes = [v for v in violations if v.severity == "note"]
        assert len(notes) == 1

    def test_captures_rule_code(self):
        violations = _parse_pyright_output(self._SAMPLE, set(), fail_on_error=True)
        codes = {v.error_code for v in violations}
        assert "reportGeneralTypeIssues" in codes

    def test_ignore_codes_suppresses_rule(self):
        violations = _parse_pyright_output(
            self._SAMPLE,
            ignore_set={"reportGeneralTypeIssues"},
            fail_on_error=True,
        )
        codes = {v.error_code for v in violations}
        assert "reportGeneralTypeIssues" not in codes


# ---------------------------------------------------------------------------
# TypesGate.run() — mypy path
# ---------------------------------------------------------------------------


class TestTypesGateMypyRun:
    """End-to-end TypesGate.run() with a mocked mypy subprocess."""

    def _gate_with_mock(self, tmp_path: Path, mypy_stdout: str, returncode: int,
                        **cfg_kwargs):
        """Helper: write pyproject.toml, patch subprocess.run, run the gate."""
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        cfg = TypesGateConfig(**cfg_kwargs)
        gate = TypesGate(cfg)
        mock_proc = _make_completed_process(returncode, mypy_stdout)
        with patch("harness_skills.gates.types.subprocess.run", return_value=mock_proc):
            return gate.run(tmp_path)

    def test_zero_errors_passes(self, tmp_path):
        result = self._gate_with_mock(tmp_path, "Success: no issues found", 0)
        assert result.passed is True
        assert result.error_count == 0
        assert result.checker == "mypy"

    def test_single_error_fails(self, tmp_path):
        output = "src/foo.py:5: error: Incompatible types  [assignment]\n"
        result = self._gate_with_mock(tmp_path, output, 1)
        assert result.passed is False
        assert result.error_count == 1

    def test_multiple_errors_all_collected(self, tmp_path):
        output = textwrap.dedent("""\
            a.py:1: error: err1  [assignment]
            b.py:2: error: err2  [arg-type]
            c.py:3: error: err3  [return-value]
        """)
        result = self._gate_with_mock(tmp_path, output, 1)
        assert result.error_count == 3
        assert result.passed is False

    def test_warnings_alone_do_not_fail_gate(self, tmp_path):
        output = "src/foo.py:5: warning: Unused ignore  [unused-ignore]\n"
        result = self._gate_with_mock(tmp_path, output, 0)
        assert result.passed is True
        assert result.warning_count == 1
        assert result.error_count == 0

    def test_notes_alone_do_not_fail_gate(self, tmp_path):
        output = "src/foo.py:5: note: See https://mypy.rtfd.io for help\n"
        result = self._gate_with_mock(tmp_path, output, 0)
        assert result.passed is True
        assert result.error_count == 0

    def test_strict_mode_passes_flag_to_mypy(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        cfg = TypesGateConfig(strict=True)
        gate = TypesGate(cfg)
        mock_proc = _make_completed_process(0, "")
        with patch(
            "harness_skills.gates.types.subprocess.run", return_value=mock_proc
        ) as mock_run:
            gate.run(tmp_path)
        cmd = mock_run.call_args[0][0]
        assert "--strict" in cmd

    def test_ignore_errors_suppresses_violations(self, tmp_path):
        output = textwrap.dedent("""\
            a.py:1: error: err1  [assignment]
            b.py:2: error: ignored  [import]
        """)
        result = self._gate_with_mock(
            tmp_path, output, 1, ignore_errors=["import"]
        )
        # Only "assignment" should survive
        assert result.error_count == 1
        codes = {v.error_code for v in result.errors()}
        assert "import" not in codes

    def test_fail_on_error_false_makes_gate_pass_despite_errors(self, tmp_path):
        output = "src/foo.py:5: error: bad type  [assignment]\n"
        result = self._gate_with_mock(tmp_path, output, 1, fail_on_error=False)
        assert result.passed is True
        # Error was recorded but downgraded
        assert result.error_count == 0
        assert result.warning_count == 1

    def test_checker_not_found_returns_structured_failure(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        cfg = TypesGateConfig(fail_on_error=True)
        gate = TypesGate(cfg)
        with patch(
            "harness_skills.gates.types.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            result = gate.run(tmp_path)
        assert result.passed is False
        assert result.checker == "mypy"
        assert result.violations[0].kind == "checker_not_found"

    def test_checker_not_found_advisory_mode_passes(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        cfg = TypesGateConfig(fail_on_error=False)
        gate = TypesGate(cfg)
        with patch(
            "harness_skills.gates.types.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            result = gate.run(tmp_path)
        assert result.passed is True


# ---------------------------------------------------------------------------
# TypesGate.run() — tsc path
# ---------------------------------------------------------------------------


class TestTypesGateTscRun:
    """End-to-end TypesGate.run() with a mocked tsc subprocess."""

    def _gate_with_mock(self, tmp_path: Path, tsc_stdout: str, returncode: int,
                        **cfg_kwargs):
        (tmp_path / "tsconfig.json").write_text('{"compilerOptions": {}}\n')
        cfg = TypesGateConfig(**cfg_kwargs)
        gate = TypesGate(cfg)
        mock_proc = _make_completed_process(returncode, tsc_stdout)
        with patch("harness_skills.gates.types.subprocess.run", return_value=mock_proc):
            return gate.run(tmp_path)

    def test_zero_errors_passes(self, tmp_path):
        result = self._gate_with_mock(tmp_path, "", 0)
        assert result.passed is True
        assert result.checker == "tsc"

    def test_single_ts_error_fails(self, tmp_path):
        output = "src/index.ts(5,3): error TS2304: Cannot find name 'x'.\n"
        result = self._gate_with_mock(tmp_path, output, 1)
        assert result.passed is False
        assert result.error_count == 1

    def test_ignore_ts_error_code(self, tmp_path):
        output = textwrap.dedent("""\
            src/a.ts(1,1): error TS2304: Cannot find name 'x'.
            src/b.ts(2,2): error TS2345: Argument mismatch.
        """)
        result = self._gate_with_mock(tmp_path, output, 1, ignore_errors=["TS2304"])
        assert result.error_count == 1
        codes = {v.error_code for v in result.errors()}
        assert "TS2304" not in codes
        assert "TS2345" in codes

    def test_explicit_tsc_checker_config(self, tmp_path):
        """checker='tsc' is honoured even without tsconfig.json on disk."""
        cfg = TypesGateConfig(checker="tsc")
        gate = TypesGate(cfg)
        mock_proc = _make_completed_process(0, "")
        with patch("harness_skills.gates.types.subprocess.run", return_value=mock_proc):
            result = gate.run(tmp_path)
        assert result.checker == "tsc"
        assert result.passed is True


# ---------------------------------------------------------------------------
# TypesGate.run() — no source detected
# ---------------------------------------------------------------------------


class TestTypesGateNoSource:
    """Behaviour when no supported project markers are found."""

    def test_no_markers_returns_graceful_skip(self, tmp_path):
        cfg = TypesGateConfig()  # checker="auto"
        gate = TypesGate(cfg)
        result = gate.run(tmp_path)
        # Gate passes (skipped), not failed
        assert result.passed is True
        assert result.checker is None
        assert result.violations[0].kind == "no_source_detected"

    def test_unknown_explicit_checker_fails(self, tmp_path):
        cfg = TypesGateConfig(checker="badchecker", fail_on_error=True)
        gate = TypesGate(cfg)
        result = gate.run(tmp_path)
        assert result.passed is False
        assert result.violations[0].kind == "no_source_detected"


# ---------------------------------------------------------------------------
# TypesGateConfig
# ---------------------------------------------------------------------------


class TestTypesGateConfig:
    """Configuration model validation."""

    def test_default_config_values(self):
        cfg = TypesGateConfig()
        assert cfg.enabled is True
        assert cfg.fail_on_error is True
        assert cfg.strict is False
        assert cfg.ignore_errors == []
        assert cfg.checker == "auto"
        assert cfg.paths == ["."]

    def test_strict_mode_enabled(self):
        cfg = TypesGateConfig(strict=True)
        assert cfg.strict is True

    def test_ignore_errors_list(self):
        cfg = TypesGateConfig(ignore_errors=["import", "attr-defined"])
        assert "import" in cfg.ignore_errors
        assert "attr-defined" in cfg.ignore_errors

    def test_disabled_gate(self):
        cfg = TypesGateConfig(enabled=False)
        assert cfg.enabled is False

    def test_model_dump_and_validate_roundtrip(self):
        cfg = TypesGateConfig(strict=True, ignore_errors=["import"], paths=["src"])
        dumped = cfg.model_dump()
        restored = TypesGateConfig.model_validate(dumped)
        assert restored.strict is True
        assert restored.ignore_errors == ["import"]
        assert restored.paths == ["src"]

    def test_model_validate_ignores_extra_keys(self):
        data = {
            "strict": True,
            "unknown_future_key": "ignored",
            "enabled": True,
        }
        cfg = TypesGateConfig.model_validate(data)
        assert cfg.strict is True


# ---------------------------------------------------------------------------
# TypeViolation.summary()
# ---------------------------------------------------------------------------


class TestTypeViolationSummary:
    """Human-readable summary format."""

    def test_summary_with_all_fields(self):
        v = TypeViolation(
            kind="type_error",
            severity="error",
            message="Incompatible types",
            file_path=Path("src/foo.py"),
            line_number=42,
            error_code="assignment",
        )
        s = v.summary()
        assert "ERROR" in s
        assert "src/foo.py" in s
        assert "42" in s
        assert "assignment" in s
        assert "Incompatible types" in s

    def test_summary_without_optional_fields(self):
        v = TypeViolation(
            kind="checker_not_found",
            severity="error",
            message="mypy not installed",
        )
        s = v.summary()
        assert "ERROR" in s
        assert "mypy not installed" in s

    def test_summary_note_severity(self):
        v = TypeViolation(
            kind="type_error",
            severity="note",
            message="See docs for details",
        )
        s = v.summary()
        assert "NOTE" in s


# ---------------------------------------------------------------------------
# TypesGateResult helpers
# ---------------------------------------------------------------------------


class TestTypesGateResult:
    """Result helper methods."""

    def _make_result(self) -> TypesGateResult:
        return TypesGateResult(
            passed=False,
            checker="mypy",
            error_count=2,
            warning_count=1,
            violations=[
                TypeViolation(kind="type_error", severity="error", message="err1"),
                TypeViolation(kind="type_error", severity="error", message="err2"),
                TypeViolation(kind="type_error", severity="warning", message="warn1"),
            ],
        )

    def test_errors_filters_correctly(self):
        result = self._make_result()
        assert len(result.errors()) == 2

    def test_warnings_filters_correctly(self):
        result = self._make_result()
        assert len(result.warnings()) == 1

    def test_stats_contains_checker(self):
        gate = TypesGate(TypesGateConfig())
        violations: list[TypeViolation] = []
        result = gate._build_result("mypy", violations)
        assert result.stats["checker"] == "mypy"

    def test_stats_contains_counts(self):
        gate = TypesGate(TypesGateConfig())
        violations = [
            TypeViolation(kind="type_error", severity="error", message="e"),
            TypeViolation(kind="type_error", severity="warning", message="w"),
        ]
        result = gate._build_result("mypy", violations)
        assert result.stats["error_count"] == 1
        assert result.stats["warning_count"] == 1


# ---------------------------------------------------------------------------
# Integration — TypesGate.run() respects config checker=mypy explicitly
# ---------------------------------------------------------------------------


class TestTypesGateExplicitCheckerMypy:
    """Explicit checker='mypy' bypasses auto-detection."""

    def test_explicit_mypy_runs_without_project_markers(self, tmp_path):
        """No pyproject.toml needed when checker is set explicitly."""
        cfg = TypesGateConfig(checker="mypy")
        gate = TypesGate(cfg)
        mock_proc = _make_completed_process(0, "Success: no issues found")
        with patch("harness_skills.gates.types.subprocess.run", return_value=mock_proc):
            result = gate.run(tmp_path)
        assert result.checker == "mypy"
        assert result.passed is True

    def test_zero_error_policy_enforced_strictly(self, tmp_path):
        """Even one error must fail the gate — no threshold, just zero."""
        cfg = TypesGateConfig(checker="mypy")
        gate = TypesGate(cfg)
        # Only a single error line
        output = "module/a.py:1: error: bad  [assignment]\n"
        mock_proc = _make_completed_process(1, output)
        with patch("harness_skills.gates.types.subprocess.run", return_value=mock_proc):
            result = gate.run(tmp_path)
        assert result.passed is False
        assert result.error_count == 1

    def test_ignored_error_code_allows_gate_to_pass(self, tmp_path):
        """When all errors are in ignore_errors the gate passes."""
        cfg = TypesGateConfig(checker="mypy", ignore_errors=["assignment"])
        gate = TypesGate(cfg)
        output = "module/a.py:1: error: bad  [assignment]\n"
        mock_proc = _make_completed_process(1, output)
        with patch("harness_skills.gates.types.subprocess.run", return_value=mock_proc):
            result = gate.run(tmp_path)
        # The error was ignored, so error_count=0 → gate passes
        assert result.error_count == 0
        assert result.passed is True
