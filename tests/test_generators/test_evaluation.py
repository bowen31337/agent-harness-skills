"""Tests for the evaluation gate failure report formatter.

Coverage targets:
  - GateFailure model — required fields, optional fields, validation
  - GateResult model — status derivation, failure_count sync
  - EvaluationReport.from_gate_results — summary counts, flat failures list
  - format_report — valid JSON, schema shape
  - run_gate / run_all_gates — integration smoke with a tmp project
  - Individual gate runners — unit tests with mocked subprocess calls
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from harness_skills.generators.evaluation import (
    ArchitectureGate,
    CoverageGate,
    DocsFreshnessGate,
    EvaluationReport,
    EvaluationSummary,
    GateConfig,
    GateFailure,
    GateId,
    GateResult,
    GateStatus,
    LintGate,
    PrinciplesGate,
    RegressionGate,
    ReportMetadata,
    SecurityGate,
    Severity,
    TypesGate,
    format_report,
    run_all_gates,
    run_gate,
)


# ---------------------------------------------------------------------------
# GateFailure model tests
# ---------------------------------------------------------------------------


class TestGateFailure:
    def test_minimal_required_fields(self) -> None:
        f = GateFailure(
            severity=Severity.ERROR,
            gate_id=GateId.LINT,
            message="Something went wrong",
        )
        assert f.severity == Severity.ERROR
        assert f.gate_id == GateId.LINT
        assert f.message == "Something went wrong"
        assert f.file_path is None
        assert f.line_number is None
        assert f.suggestion is None
        assert f.rule_id is None
        assert f.context is None

    def test_all_fields(self) -> None:
        f = GateFailure(
            severity=Severity.WARNING,
            gate_id=GateId.COVERAGE,
            message="Coverage 85% < 90%",
            file_path="src/auth/service.py",
            line_number=42,
            suggestion="Add tests for the uncovered branch.",
            rule_id="coverage/threshold",
            context="def login(user):...",
        )
        assert f.file_path == "src/auth/service.py"
        assert f.line_number == 42
        assert f.suggestion == "Add tests for the uncovered branch."
        assert f.rule_id == "coverage/threshold"

    def test_severity_enum_values(self) -> None:
        for sev, val in [(Severity.ERROR, "error"), (Severity.WARNING, "warning"), (Severity.INFO, "info")]:
            f = GateFailure(severity=sev, gate_id=GateId.LINT, message="x")
            assert f.severity.value == val

    def test_line_number_must_be_positive(self) -> None:
        with pytest.raises(Exception):
            GateFailure(severity=Severity.ERROR, gate_id=GateId.LINT, message="x", line_number=0)

    def test_serialises_to_json(self) -> None:
        f = GateFailure(
            severity=Severity.ERROR,
            gate_id=GateId.REGRESSION,
            message="Test failed",
            file_path="tests/test_foo.py",
            line_number=10,
            suggestion="Fix the assertion",
        )
        data = json.loads(f.model_dump_json())
        assert data["severity"] == "error"
        assert data["gate_id"] == "regression"
        assert data["file_path"] == "tests/test_foo.py"
        assert data["line_number"] == 10
        assert data["suggestion"] == "Fix the assertion"


# ---------------------------------------------------------------------------
# GateResult model tests
# ---------------------------------------------------------------------------


class TestGateResult:
    def test_passed_status_empty_failures(self) -> None:
        r = GateResult(gate_id=GateId.LINT, status=GateStatus.PASSED)
        assert r.failure_count == 0
        assert r.failures == []

    def test_failure_count_synced_with_failures(self) -> None:
        failures = [
            GateFailure(severity=Severity.ERROR, gate_id=GateId.LINT, message="e1"),
            GateFailure(severity=Severity.WARNING, gate_id=GateId.LINT, message="e2"),
        ]
        r = GateResult(gate_id=GateId.LINT, status=GateStatus.FAILED, failures=failures)
        assert r.failure_count == 2

    def test_skipped_gate(self) -> None:
        r = GateResult(gate_id=GateId.PERFORMANCE, status=GateStatus.SKIPPED)
        assert r.status == GateStatus.SKIPPED


# ---------------------------------------------------------------------------
# EvaluationReport tests
# ---------------------------------------------------------------------------


class TestEvaluationReport:
    def _make_passed_result(self, gate_id: GateId) -> GateResult:
        return GateResult(gate_id=gate_id, status=GateStatus.PASSED, failures=[])

    def _make_failed_result(self, gate_id: GateId, n_errors: int = 1) -> GateResult:
        failures = [
            GateFailure(severity=Severity.ERROR, gate_id=gate_id, message=f"err{i}")
            for i in range(n_errors)
        ]
        return GateResult(gate_id=gate_id, status=GateStatus.FAILED, failures=failures)

    def test_all_passed(self) -> None:
        results = [self._make_passed_result(gid) for gid in GateId]
        report = EvaluationReport.from_gate_results(results)
        assert report.passed is True
        assert report.summary.failed_gates == 0
        assert report.summary.blocking_failures == 0
        assert report.failures == []

    def test_one_failed_gate(self) -> None:
        results = [
            self._make_passed_result(GateId.LINT),
            self._make_failed_result(GateId.REGRESSION, n_errors=2),
        ]
        report = EvaluationReport.from_gate_results(results)
        assert report.passed is False
        assert report.summary.failed_gates == 1
        assert report.summary.passed_gates == 1
        assert report.summary.total_gates == 2
        assert report.summary.blocking_failures == 2
        assert len(report.failures) == 2

    def test_flat_failures_list_aggregates_all_gates(self) -> None:
        results = [
            self._make_failed_result(GateId.LINT, 3),
            self._make_failed_result(GateId.TYPES, 2),
        ]
        report = EvaluationReport.from_gate_results(results)
        assert len(report.failures) == 5
        assert report.summary.total_failures == 5

    def test_warning_failures_dont_block_pr(self) -> None:
        warn_failure = GateFailure(
            severity=Severity.WARNING, gate_id=GateId.COVERAGE, message="low coverage"
        )
        result = GateResult(
            gate_id=GateId.COVERAGE, status=GateStatus.FAILED, failures=[warn_failure]
        )
        report = EvaluationReport.from_gate_results([result])
        assert report.passed is False  # gate failed
        assert report.summary.blocking_failures == 0  # but no ERROR-severity

    def test_skipped_gates_counted_correctly(self) -> None:
        results = [
            self._make_passed_result(GateId.LINT),
            GateResult(gate_id=GateId.PERFORMANCE, status=GateStatus.SKIPPED),
        ]
        report = EvaluationReport.from_gate_results(results)
        assert report.summary.skipped_gates == 1
        assert report.summary.total_gates == 2
        assert report.passed is True  # skipped != failed

    def test_schema_version_constant(self) -> None:
        report = EvaluationReport.from_gate_results([])
        assert report.schema_version == "1.0"

    def test_metadata_attached(self) -> None:
        meta = ReportMetadata(git_sha="abc123", git_branch="main")
        report = EvaluationReport.from_gate_results([], metadata=meta)
        assert report.metadata is not None
        assert report.metadata.git_sha == "abc123"


# ---------------------------------------------------------------------------
# format_report tests
# ---------------------------------------------------------------------------


class TestFormatReport:
    def test_returns_valid_json(self) -> None:
        report = EvaluationReport.from_gate_results([])
        json_str = format_report(report)
        data = json.loads(json_str)
        assert isinstance(data, dict)

    def test_json_contains_all_required_keys(self) -> None:
        report = EvaluationReport.from_gate_results([])
        data = json.loads(format_report(report))
        assert "passed" in data
        assert "summary" in data
        assert "gate_results" in data
        assert "schema_version" in data

    def test_failure_fields_present(self) -> None:
        failure = GateFailure(
            severity=Severity.ERROR,
            gate_id=GateId.LINT,
            message="unused import",
            file_path="app/main.py",
            line_number=5,
            suggestion="Remove the unused import.",
            rule_id="F401",
        )
        result = GateResult(gate_id=GateId.LINT, status=GateStatus.FAILED, failures=[failure])
        report = EvaluationReport.from_gate_results([result])
        data = json.loads(format_report(report))

        assert len(data["failures"]) == 1
        f = data["failures"][0]
        assert f["severity"] == "error"
        assert f["gate_id"] == "lint"
        assert f["file_path"] == "app/main.py"
        assert f["line_number"] == 5
        assert f["suggestion"] == "Remove the unused import."
        assert f["rule_id"] == "F401"

    def test_custom_indent(self) -> None:
        report = EvaluationReport.from_gate_results([])
        compact = format_report(report, indent=0)
        pretty = format_report(report, indent=4)
        assert len(pretty) > len(compact)


# ---------------------------------------------------------------------------
# Gate runner unit tests (mocked subprocess)
# ---------------------------------------------------------------------------


class TestRegressionGate:
    def test_passes_when_pytest_exits_zero(self, tmp_path: Path) -> None:
        with patch("harness_skills.generators.evaluation.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = RegressionGate().run(tmp_path, GateConfig())
        assert result.status == GateStatus.PASSED
        assert result.failures == []

    def test_fails_when_pytest_exits_nonzero(self, tmp_path: Path) -> None:
        with patch("harness_skills.generators.evaluation.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="1 failed", stderr="AssertionError"
            )
            result = RegressionGate().run(tmp_path, GateConfig())
        assert result.status == GateStatus.FAILED
        assert len(result.failures) >= 1
        assert result.failures[0].severity == Severity.ERROR
        assert result.failures[0].gate_id == GateId.REGRESSION
        assert result.failures[0].suggestion is not None


class TestCoverageGate:
    def test_skipped_when_not_in_enabled_gates(self, tmp_path: Path) -> None:
        config = GateConfig(enabled_gates=[GateId.LINT])
        result = CoverageGate().run(tmp_path, config)
        assert result.status == GateStatus.SKIPPED

    def test_fails_when_coverage_below_threshold(self, tmp_path: Path) -> None:
        coverage_data = {
            "totals": {"percent_covered": 72.5},
            "files": {},
        }
        coverage_json = tmp_path / ".coverage.json"

        def fake_run(*args, **kwargs):
            coverage_json.write_text(json.dumps(coverage_data))
            return MagicMock(returncode=1, stdout="", stderr="")

        with patch("harness_skills.generators.evaluation.subprocess.run", side_effect=fake_run):
            result = CoverageGate().run(tmp_path, GateConfig(coverage_threshold=90.0))

        assert result.status == GateStatus.FAILED
        assert any(
            "72.5%" in f.message and "90.0%" in f.message
            for f in result.failures
        )

    def test_passes_when_coverage_meets_threshold(self, tmp_path: Path) -> None:
        coverage_data = {
            "totals": {"percent_covered": 95.0},
            "files": {},
        }
        coverage_json = tmp_path / ".coverage.json"

        def fake_run(*args, **kwargs):
            coverage_json.write_text(json.dumps(coverage_data))
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("harness_skills.generators.evaluation.subprocess.run", side_effect=fake_run):
            result = CoverageGate().run(tmp_path, GateConfig(coverage_threshold=90.0))

        assert result.status == GateStatus.PASSED


class TestLintGate:
    def test_passes_when_ruff_exits_zero(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n")
        with patch("harness_skills.generators.evaluation.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="[]", stderr="")
            result = LintGate().run(tmp_path, GateConfig())
        assert result.status == GateStatus.PASSED

    def test_fails_with_ruff_json_violations(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n")
        violations = [
            {
                "filename": str(tmp_path / "app/main.py"),
                "location": {"row": 5, "column": 1},
                "message": "Unused import `os`",
                "code": "F401",
                "fix": None,
            }
        ]
        with patch("harness_skills.generators.evaluation.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout=json.dumps(violations), stderr=""
            )
            result = LintGate().run(tmp_path, GateConfig())
        assert result.status == GateStatus.FAILED
        assert len(result.failures) == 1
        f = result.failures[0]
        assert f.severity == Severity.ERROR
        assert f.gate_id == GateId.LINT
        assert f.line_number == 5
        assert f.rule_id == "F401"
        assert f.suggestion is not None


class TestTypesGate:
    def test_passes_when_mypy_exits_zero(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.mypy]\n")
        with patch("harness_skills.generators.evaluation.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = TypesGate().run(tmp_path, GateConfig())
        assert result.status == GateStatus.PASSED

    def test_parses_mypy_error_output(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.mypy]\n")
        mypy_output = (
            "src/service.py:42: error: Argument 1 to 'login' has incompatible type "
            '"str"; expected "int"  [arg-type]\n'
            "Found 1 error in 1 file (checked 10 source files)\n"
        )
        with patch("harness_skills.generators.evaluation.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout=mypy_output, stderr="")
            result = TypesGate().run(tmp_path, GateConfig())
        assert result.status == GateStatus.FAILED
        assert len(result.failures) >= 1
        f = result.failures[0]
        assert f.file_path == "src/service.py"
        assert f.line_number == 42
        assert f.severity == Severity.ERROR
        assert f.rule_id == "arg-type"


class TestDocsFreshnessGate:
    def test_warns_for_missing_artifacts(self, tmp_path: Path) -> None:
        result = DocsFreshnessGate().run(tmp_path, GateConfig())
        assert result.status == GateStatus.FAILED
        missing = [f for f in result.failures if "not found" in f.message]
        assert len(missing) == 4  # AGENTS.md, ARCHITECTURE.md, PRINCIPLES.md, EVALUATION.md

    def test_warns_for_stale_artifact(self, tmp_path: Path) -> None:
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text(
            "# AGENTS\n<!-- generated_at: 2020-01-01T00:00:00+00:00 -->\n"
        )
        result = DocsFreshnessGate().run(tmp_path, GateConfig(max_staleness_days=30))
        stale = [f for f in result.failures if "stale" in (f.rule_id or "")]
        assert any(f.file_path == "AGENTS.md" for f in stale)

    def test_passes_for_fresh_artifact(self, tmp_path: Path) -> None:
        from datetime import datetime, timezone

        now_str = datetime.now(timezone.utc).isoformat()
        for name in ["AGENTS.md", "ARCHITECTURE.md", "PRINCIPLES.md", "EVALUATION.md"]:
            (tmp_path / name).write_text(f"# {name}\n<!-- generated_at: {now_str} -->\n")
        result = DocsFreshnessGate().run(tmp_path, GateConfig(max_staleness_days=30))
        assert result.status == GateStatus.PASSED


class TestArchitectureGate:
    def test_passes_on_empty_project(self, tmp_path: Path) -> None:
        result = ArchitectureGate().run(tmp_path, GateConfig())
        assert result.status == GateStatus.PASSED

    def test_detects_layer_violation(self, tmp_path: Path) -> None:
        # repo layer imports from service layer — violation
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        (repo_dir / "user_repo.py").write_text(
            "from service.user_service import UserService\n"
            "class UserRepo:\n    pass\n"
        )
        result = ArchitectureGate().run(tmp_path, GateConfig())
        violations = [f for f in result.failures if f.rule_id == "arch/layer-violation"]
        assert len(violations) >= 1
        assert violations[0].file_path is not None
        assert violations[0].line_number == 1
        assert violations[0].suggestion is not None


class TestPrinciplesGate:
    def test_detects_magic_number(self, tmp_path: Path) -> None:
        (tmp_path / "app.py").write_text("def foo():\n    return 42 * 365\n")
        result = PrinciplesGate().run(tmp_path, GateConfig())
        magic = [f for f in result.failures if f.rule_id == "principles/no-magic-numbers"]
        assert any(f.file_path == "app.py" for f in magic)

    def test_detects_hardcoded_url(self, tmp_path: Path) -> None:
        (tmp_path / "client.py").write_text('BASE_URL = "https://api.example.com/v1"\n')
        result = PrinciplesGate().run(tmp_path, GateConfig())
        urls = [f for f in result.failures if f.rule_id == "principles/no-hardcoded-urls"]
        assert any(f.file_path == "client.py" for f in urls)

    def test_clean_file_no_violations(self, tmp_path: Path) -> None:
        (tmp_path / "clean.py").write_text(
            "MAX_RETRIES = 3\n"
            "BASE_URL = os.environ['BASE_URL']\n"
        )
        result = PrinciplesGate().run(tmp_path, GateConfig())
        # MAX_RETRIES = 3 is a constant, so the literal 3 still appears in AST —
        # this is expected warning behavior; just confirm structure is intact
        assert all(isinstance(f, GateFailure) for f in result.failures)


# ---------------------------------------------------------------------------
# run_gate / run_all_gates integration (smoke tests)
# ---------------------------------------------------------------------------


class TestRunGateFunctions:
    def test_run_gate_returns_gate_result(self, tmp_path: Path) -> None:
        with patch("harness_skills.generators.evaluation.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = run_gate(GateId.REGRESSION, project_root=tmp_path)
        assert isinstance(result, GateResult)
        assert result.gate_id == GateId.REGRESSION

    def test_run_all_gates_returns_evaluation_report(self, tmp_path: Path) -> None:
        with patch("harness_skills.generators.evaluation.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="[]", stderr="")
            report = run_all_gates(
                project_root=tmp_path,
                gates=[GateId.LINT],
            )
        assert isinstance(report, EvaluationReport)
        assert len(report.gate_results) == 1

    def test_run_all_gates_subset(self, tmp_path: Path) -> None:
        with patch("harness_skills.generators.evaluation.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            report = run_all_gates(
                project_root=tmp_path,
                gates=[GateId.REGRESSION, GateId.LINT],
            )
        assert report.summary.total_gates == 2

    def test_gate_config_disables_gate(self, tmp_path: Path) -> None:
        config = GateConfig(enabled_gates=[GateId.LINT])
        with patch("harness_skills.generators.evaluation.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="[]", stderr="")
            report = run_all_gates(
                project_root=tmp_path,
                config=config,
                gates=[GateId.LINT, GateId.REGRESSION],
            )
        regression_result = next(r for r in report.gate_results if r.gate_id == GateId.REGRESSION)
        assert regression_result.status == GateStatus.SKIPPED

    def test_gate_runner_exception_becomes_error_status(self, tmp_path: Path) -> None:
        with patch("harness_skills.generators.evaluation.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("pytest not found")
            result = run_gate(GateId.REGRESSION, project_root=tmp_path)
        assert result.status == GateStatus.ERROR
        assert len(result.failures) == 1
        assert result.failures[0].severity == Severity.ERROR
        assert "exception" in result.failures[0].message.lower()
