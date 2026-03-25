"""Tests for harness_skills.cli.lint (``harness lint``).

Uses Click's ``CliRunner`` for isolated, subprocess-free invocations.
All calls to the evaluation gate runner are mocked so tests are fast
and deterministic.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner

from harness_skills.cli.lint import (
    _build_lint_response,
    _print_table_report,
    _print_violation_group,
    _resolve_gates,
    lint_cmd,
)
from harness_skills.generators.evaluation import (
    EvaluationReport,
    EvaluationSummary,
    GateFailure,
    GateId,
    GateResult,
    GateStatus,
    Severity,
)
from harness_skills.models.base import Status


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _make_report(
    passed: bool = True,
    failures: list[GateFailure] | None = None,
    gate_results: list[GateResult] | None = None,
) -> EvaluationReport:
    """Build a minimal EvaluationReport for testing."""
    failures = failures or []
    gate_results = gate_results or []
    return EvaluationReport(
        passed=passed,
        summary=EvaluationSummary(
            total_gates=len(gate_results),
            passed_gates=sum(1 for g in gate_results if g.status == GateStatus.PASSED),
            failed_gates=sum(1 for g in gate_results if g.status == GateStatus.FAILED),
        ),
        gate_results=gate_results,
        failures=failures,
    )


# ===========================================================================
# _resolve_gates
# ===========================================================================


class TestResolveGates:
    def test_default_returns_all_lint_gates(self):
        gates = _resolve_gates((), no_principles=False)
        assert gates == [GateId.ARCHITECTURE, GateId.PRINCIPLES, GateId.LINT]

    def test_selected_gates_filters(self):
        gates = _resolve_gates(("architecture",), no_principles=False)
        assert gates == [GateId.ARCHITECTURE]

    def test_no_principles_removes_principles(self):
        gates = _resolve_gates((), no_principles=True)
        assert GateId.PRINCIPLES not in gates
        assert GateId.ARCHITECTURE in gates
        assert GateId.LINT in gates

    def test_no_principles_with_selected_gates(self):
        gates = _resolve_gates(("principles",), no_principles=True)
        assert gates == []

    def test_selected_multiple_gates(self):
        gates = _resolve_gates(("architecture", "lint"), no_principles=False)
        assert gates == [GateId.ARCHITECTURE, GateId.LINT]


# ===========================================================================
# _build_lint_response
# ===========================================================================


class TestBuildLintResponse:
    def test_passed_report(self):
        report = _make_report(passed=True)
        resp = _build_lint_response(report)
        assert resp.passed is True
        assert resp.status == Status.PASSED
        assert resp.total_violations == 0
        assert "passed" in resp.message.lower()

    def test_failed_report_with_errors(self):
        failures = [
            GateFailure(
                severity=Severity.ERROR,
                gate_id=GateId.ARCHITECTURE,
                message="bad import",
                file_path="src/app.py",
                line_number=10,
                suggestion="Remove import",
                rule_id="arch-001",
            ),
        ]
        report = _make_report(passed=False, failures=failures)
        resp = _build_lint_response(report)
        assert resp.passed is False
        assert resp.status == Status.FAILED
        assert resp.error_count == 1
        assert resp.total_violations == 1
        assert "1 blocking" in resp.message

    def test_warning_and_info_counts(self):
        failures = [
            GateFailure(
                severity=Severity.WARNING,
                gate_id=GateId.LINT,
                message="unused var",
                rule_id="W001",
            ),
            GateFailure(
                severity=Severity.INFO,
                gate_id=GateId.LINT,
                message="style note",
                rule_id="I001",
            ),
        ]
        report = _make_report(passed=True, failures=failures)
        resp = _build_lint_response(report)
        assert resp.warning_count == 1
        assert resp.info_count == 1
        assert resp.error_count == 0
        assert resp.critical_count == 0

    def test_rules_applied_deduplication(self):
        failures = [
            GateFailure(
                severity=Severity.ERROR,
                gate_id=GateId.LINT,
                message="a",
                rule_id="E001",
            ),
            GateFailure(
                severity=Severity.ERROR,
                gate_id=GateId.LINT,
                message="b",
                rule_id="E001",
            ),
        ]
        report = _make_report(passed=False, failures=failures)
        resp = _build_lint_response(report)
        assert resp.rules_applied == ["E001"]

    def test_files_checked_counts_distinct_paths(self):
        failures = [
            GateFailure(
                severity=Severity.ERROR,
                gate_id=GateId.LINT,
                message="a",
                file_path="src/a.py",
            ),
            GateFailure(
                severity=Severity.ERROR,
                gate_id=GateId.LINT,
                message="b",
                file_path="src/a.py",
            ),
            GateFailure(
                severity=Severity.ERROR,
                gate_id=GateId.LINT,
                message="c",
                file_path="src/b.py",
            ),
        ]
        report = _make_report(passed=False, failures=failures)
        resp = _build_lint_response(report)
        assert resp.files_checked == 2

    def test_failure_without_rule_id_uses_gate_id(self):
        failures = [
            GateFailure(
                severity=Severity.ERROR,
                gate_id=GateId.ARCHITECTURE,
                message="no rule_id",
            ),
        ]
        report = _make_report(passed=False, failures=failures)
        resp = _build_lint_response(report)
        assert resp.violations[0].rule_id == "architecture"


# ===========================================================================
# lint_cmd — table output
# ===========================================================================


class TestLintCmdTable:
    @patch("harness_skills.cli.lint.run_all_gates")
    def test_passing_lint_exits_zero(self, mock_gates, runner: CliRunner, tmp_path: Path):
        mock_gates.return_value = _make_report(passed=True)
        result = runner.invoke(lint_cmd, ["--project-root", str(tmp_path)])
        assert result.exit_code == 0

    @patch("harness_skills.cli.lint.run_all_gates")
    def test_failing_lint_exits_one(self, mock_gates, runner: CliRunner, tmp_path: Path):
        failures = [
            GateFailure(
                severity=Severity.ERROR,
                gate_id=GateId.ARCHITECTURE,
                message="import violation",
                file_path="src/x.py",
                line_number=5,
                suggestion="Fix it",
                rule_id="A001",
            ),
        ]
        mock_gates.return_value = _make_report(passed=False, failures=failures)
        result = runner.invoke(lint_cmd, ["--project-root", str(tmp_path)])
        assert result.exit_code == 1

    @patch("harness_skills.cli.lint.run_all_gates")
    def test_table_output_shows_pass_label(self, mock_gates, runner: CliRunner, tmp_path: Path):
        mock_gates.return_value = _make_report(passed=True)
        result = runner.invoke(lint_cmd, ["--project-root", str(tmp_path), "--format", "table"])
        assert "PASS" in result.output or "passed" in result.output.lower()

    @patch("harness_skills.cli.lint.run_all_gates")
    def test_table_output_shows_fail_label(self, mock_gates, runner: CliRunner, tmp_path: Path):
        failures = [
            GateFailure(
                severity=Severity.ERROR,
                gate_id=GateId.LINT,
                message="err",
                rule_id="E1",
            ),
        ]
        mock_gates.return_value = _make_report(passed=False, failures=failures)
        result = runner.invoke(lint_cmd, ["--project-root", str(tmp_path), "--format", "table"])
        assert "FAIL" in result.output or "failed" in result.output.lower()


# ===========================================================================
# lint_cmd — JSON output
# ===========================================================================


class TestLintCmdJson:
    @patch("harness_skills.cli.lint.run_all_gates")
    def test_json_output_is_valid(self, mock_gates, runner: CliRunner, tmp_path: Path):
        mock_gates.return_value = _make_report(passed=True)
        result = runner.invoke(
            lint_cmd, ["--project-root", str(tmp_path), "--format", "json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["passed"] is True
        assert data["command"] == "harness lint"

    @patch("harness_skills.cli.lint.run_all_gates")
    def test_json_output_with_violations(self, mock_gates, runner: CliRunner, tmp_path: Path):
        failures = [
            GateFailure(
                severity=Severity.ERROR,
                gate_id=GateId.ARCHITECTURE,
                message="bad",
                file_path="a.py",
                line_number=1,
                suggestion="fix",
                rule_id="A1",
            ),
        ]
        mock_gates.return_value = _make_report(passed=False, failures=failures)
        result = runner.invoke(
            lint_cmd, ["--project-root", str(tmp_path), "--format", "json"]
        )
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["passed"] is False
        assert data["error_count"] == 1
        assert len(data["violations"]) == 1


# ===========================================================================
# lint_cmd — gate selection options
# ===========================================================================


class TestLintCmdGateSelection:
    @patch("harness_skills.cli.lint.run_all_gates")
    def test_gate_option_filters_gates(self, mock_gates, runner: CliRunner, tmp_path: Path):
        mock_gates.return_value = _make_report(passed=True)
        result = runner.invoke(
            lint_cmd,
            ["--project-root", str(tmp_path), "--gate", "architecture", "--format", "json"],
        )
        assert result.exit_code == 0
        # Verify run_all_gates was called with only the architecture gate
        call_kwargs = mock_gates.call_args
        assert GateId.ARCHITECTURE in call_kwargs.kwargs.get("gates", call_kwargs[1].get("gates", []))

    @patch("harness_skills.cli.lint.run_all_gates")
    def test_no_principles_flag(self, mock_gates, runner: CliRunner, tmp_path: Path):
        mock_gates.return_value = _make_report(passed=True)
        result = runner.invoke(
            lint_cmd,
            ["--project-root", str(tmp_path), "--no-principles", "--format", "json"],
        )
        assert result.exit_code == 0
        call_kwargs = mock_gates.call_args
        gates = call_kwargs.kwargs.get("gates", call_kwargs[1].get("gates", []))
        assert GateId.PRINCIPLES not in gates


# ===========================================================================
# lint_cmd — internal error handling
# ===========================================================================


class TestLintCmdErrors:
    @patch("harness_skills.cli.lint.run_all_gates")
    def test_internal_error_exits_two(self, mock_gates, runner: CliRunner, tmp_path: Path):
        mock_gates.side_effect = RuntimeError("boom")
        result = runner.invoke(lint_cmd, ["--project-root", str(tmp_path)])
        assert result.exit_code == 2
        assert "internal error" in result.output.lower() or "internal error" in (result.output + getattr(result, 'stderr', ''))

    @patch("harness_skills.cli.lint.run_all_gates")
    def test_internal_error_return_reached(self, mock_gates):
        """Use a real context with patched exit to reach return after ctx.exit(2)."""
        mock_gates.side_effect = RuntimeError("boom")
        with click.Context(lint_cmd) as ctx:
            ctx.exit = MagicMock()
            lint_cmd.callback(
                selected_gates=(),
                no_principles=False,
                project_root=Path("."),
                output_format="table",
            )
        ctx.exit.assert_called_with(2)

    def test_invalid_gate_choice(self, runner: CliRunner):
        result = runner.invoke(lint_cmd, ["--gate", "nonexistent"])
        assert result.exit_code != 0


# ===========================================================================
# _print_table_report and _print_violation_group
# ===========================================================================


class TestTableFormatting:
    def test_print_table_report_passing(self):
        """Smoke test: _print_table_report runs without error for a passing report."""
        report = _make_report(
            passed=True,
            gate_results=[
                GateResult(
                    gate_id=GateId.ARCHITECTURE,
                    status=GateStatus.PASSED,
                    duration_ms=42,
                ),
                GateResult(
                    gate_id=GateId.LINT,
                    status=GateStatus.PASSED,
                    duration_ms=10,
                ),
            ],
        )
        resp = _build_lint_response(report)
        # Should not raise
        _print_table_report(resp, report)

    def test_print_table_report_with_violations(self):
        """Smoke test: violations are rendered without error."""
        failures = [
            GateFailure(
                severity=Severity.ERROR,
                gate_id=GateId.ARCHITECTURE,
                message="import violation",
                file_path="src/x.py",
                line_number=10,
                suggestion="Remove it",
                rule_id="A001",
            ),
            GateFailure(
                severity=Severity.WARNING,
                gate_id=GateId.LINT,
                message="unused var",
                rule_id="W001",
            ),
            GateFailure(
                severity=Severity.INFO,
                gate_id=GateId.LINT,
                message="style note",
            ),
        ]
        report = _make_report(
            passed=False,
            failures=failures,
            gate_results=[
                GateResult(
                    gate_id=GateId.ARCHITECTURE,
                    status=GateStatus.FAILED,
                    duration_ms=None,
                    failures=[failures[0]],
                ),
                GateResult(
                    gate_id=GateId.LINT,
                    status=GateStatus.FAILED,
                    failures=failures[1:],
                ),
            ],
        )
        resp = _build_lint_response(report)
        _print_table_report(resp, report)

    def test_print_violation_group_with_location(self, capsys):
        """Violation with file_path and line_number prints location."""
        from rich.console import Console

        from harness_skills.models.base import Violation

        violations = [
            Violation(
                rule_id="R1",
                severity="error",
                file_path="a.py",
                line_number=5,
                message="bad",
                suggestion="fix it",
            ),
        ]
        console = Console()
        _print_violation_group(console, violations)

    def test_print_violation_group_without_location(self, capsys):
        """Violation without file_path."""
        from rich.console import Console

        from harness_skills.models.base import Violation

        violations = [
            Violation(
                rule_id="R2",
                severity="warning",
                message="something",
            ),
        ]
        console = Console()
        _print_violation_group(console, violations)

    def test_print_table_report_skips_non_lint_gates(self):
        """Gate results for non-lint gates (e.g. REGRESSION) are not shown."""
        report = _make_report(
            passed=True,
            gate_results=[
                GateResult(gate_id=GateId.REGRESSION, status=GateStatus.PASSED),
                GateResult(gate_id=GateId.ARCHITECTURE, status=GateStatus.PASSED),
            ],
        )
        resp = _build_lint_response(report)
        # Should not raise; REGRESSION row is skipped
        _print_table_report(resp, report)
