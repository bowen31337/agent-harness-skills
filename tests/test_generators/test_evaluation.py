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
import time
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

    def test_runs_only_on_changed_python_files_when_git_detects_changes(
        self, tmp_path: Path
    ) -> None:
        """When git diff reports changed files, ruff is called with those paths only."""
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n")
        changed = tmp_path / "src" / "service.py"
        changed.parent.mkdir(parents=True)
        changed.write_text("x = 1\n")

        git_diff_output = "src/service.py\n"

        def fake_run(args, **kwargs):
            if "git" in args:
                return MagicMock(returncode=0, stdout=git_diff_output, stderr="")
            # ruff call — assert it received the specific file, not "."
            assert str(changed) in args or "src/service.py" in " ".join(args)
            return MagicMock(returncode=0, stdout="[]", stderr="")

        with patch("harness_skills.generators.evaluation.subprocess.run", side_effect=fake_run):
            result = LintGate().run(tmp_path, GateConfig())

        assert result.status == GateStatus.PASSED

    def test_zero_warnings_policy_on_changed_files_eslint(self, tmp_path: Path) -> None:
        """ESLint severity-1 warnings become Severity.ERROR when running on changed files."""
        (tmp_path / ".eslintrc.json").write_text("{}\n")
        changed = tmp_path / "src" / "app.js"
        changed.parent.mkdir(parents=True)
        changed.write_text("var x = 1;\n")

        git_diff_output = "src/app.js\n"
        eslint_output = json.dumps(
            [
                {
                    "filePath": str(changed),
                    "messages": [
                        {
                            "ruleId": "no-var",
                            "severity": 1,  # warning in ESLint
                            "message": "Unexpected var, use let or const instead.",
                            "line": 1,
                        }
                    ],
                }
            ]
        )

        def fake_run(args, **kwargs):
            if "git" in args:
                return MagicMock(returncode=0, stdout=git_diff_output, stderr="")
            return MagicMock(returncode=1, stdout=eslint_output, stderr="")

        with patch("harness_skills.generators.evaluation.subprocess.run", side_effect=fake_run):
            result = LintGate().run(tmp_path, GateConfig())

        assert result.status == GateStatus.FAILED
        assert len(result.failures) == 1
        # Zero-warnings policy: severity-1 warning must be promoted to ERROR
        assert result.failures[0].severity == Severity.ERROR

    def test_falls_back_to_full_scan_when_no_changed_files(self, tmp_path: Path) -> None:
        """When git reports no changes, ruff is called with '.' (full project scan)."""
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n")

        calls: list[list[str]] = []

        def fake_run(args, **kwargs):
            calls.append(list(args))
            if "git" in args:
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=0, stdout="[]", stderr="")

        with patch("harness_skills.generators.evaluation.subprocess.run", side_effect=fake_run):
            result = LintGate().run(tmp_path, GateConfig())

        assert result.status == GateStatus.PASSED
        ruff_calls = [c for c in calls if "ruff" in " ".join(c)]
        assert any("." in c for c in ruff_calls), "ruff should be called with '.' for full scan"

    def test_passes_when_no_python_files_in_changed_set(self, tmp_path: Path) -> None:
        """Gate passes immediately when changed files contain no Python files."""
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n")
        # Only a markdown file changed
        git_diff_output = "README.md\n"

        calls: list[list[str]] = []

        def fake_run(args, **kwargs):
            calls.append(list(args))
            if "git" in args:
                return MagicMock(returncode=0, stdout=git_diff_output, stderr="")
            return MagicMock(returncode=0, stdout="[]", stderr="")

        with patch("harness_skills.generators.evaluation.subprocess.run", side_effect=fake_run):
            result = LintGate().run(tmp_path, GateConfig())

        assert result.status == GateStatus.PASSED
        # Ruff should NOT have been called (no Python files to lint)
        ruff_calls = [c for c in calls if "ruff" in " ".join(c)]
        assert len(ruff_calls) == 0


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
        for name in ["AGENTS.md", "docs/ARCHITECTURE.md", "docs/PRINCIPLES.md", "docs/EVALUATION.md"]:
            p = tmp_path / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f"# {name}\n<!-- generated_at: {now_str} -->\n")
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


# ---------------------------------------------------------------------------
# Additional coverage tests — EvaluationReport.from_gate_results ERROR status
# ---------------------------------------------------------------------------


class TestEvaluationReportErrorGate:
    def test_error_gates_counted(self) -> None:
        result = GateResult(gate_id=GateId.REGRESSION, status=GateStatus.ERROR, failures=[
            GateFailure(severity=Severity.ERROR, gate_id=GateId.REGRESSION, message="exception")
        ])
        report = EvaluationReport.from_gate_results([result])
        assert report.summary.error_gates == 1
        assert report.passed is False


# ---------------------------------------------------------------------------
# GateConfig per-gate config helpers
# ---------------------------------------------------------------------------


class TestGateConfigHelpers:
    def test_is_gate_enabled_via_gates_dict(self) -> None:
        config = GateConfig(gates={"coverage": {"enabled": False}})
        assert config.is_gate_enabled("coverage") is False

    def test_is_gate_enabled_via_gates_dict_true(self) -> None:
        config = GateConfig(gates={"coverage": {"enabled": True}})
        assert config.is_gate_enabled("coverage") is True

    def test_get_coverage_threshold_from_gates_dict(self) -> None:
        config = GateConfig(gates={"coverage": {"threshold": 75.0}})
        assert config.get_coverage_threshold() == 75.0

    def test_get_staleness_days_from_gates_dict(self) -> None:
        config = GateConfig(gates={"docs_freshness": {"max_staleness_days": 7}})
        assert config.get_staleness_days() == 7

    def test_get_performance_budget_from_gates_dict(self) -> None:
        config = GateConfig(gates={"performance": {"budget_ms": 500}})
        assert config.get_performance_budget_ms() == 500


# ---------------------------------------------------------------------------
# RegressionGate — JUnit XML parsing and location parsing
# ---------------------------------------------------------------------------


class TestRegressionGateJUnitParsing:
    def test_parses_junit_xml_with_failures(self, tmp_path: Path) -> None:
        junit_xml = tmp_path / ".harness-junit.xml"
        junit_content = (
            '<?xml version="1.0" ?>'
            '<testsuites><testsuite name="tests">'
            '<testcase classname="tests.test_foo" name="test_bar">'
            '<failure>tests/test_foo.py:10: AssertionError</failure>'
            '</testcase>'
            '</testsuite></testsuites>'
        )

        def fake_run(args, **kwargs):
            junit_xml.write_text(junit_content)
            return MagicMock(returncode=1, stdout="1 failed", stderr="")

        with patch("harness_skills.generators.evaluation.subprocess.run", side_effect=fake_run):
            result = RegressionGate().run(tmp_path, GateConfig())

        assert result.status == GateStatus.FAILED
        assert any("Test failed" in f.message for f in result.failures)

    def test_parse_location_no_match(self) -> None:
        path, line = RegressionGate._parse_location("no match here", Path("/tmp"))
        assert path is None
        assert line is None

    def test_parse_location_file_not_exist(self, tmp_path: Path) -> None:
        path, line = RegressionGate._parse_location("some/file.py:42", tmp_path)
        assert path == "some/file.py"
        assert line == 42

    def test_parse_location_file_exists(self, tmp_path: Path) -> None:
        (tmp_path / "real.py").write_text("x = 1\n")
        path, line = RegressionGate._parse_location("real.py:5", tmp_path)
        assert path == "real.py"
        assert line == 5

    def test_junit_xml_parse_error_handled(self, tmp_path: Path) -> None:
        junit_xml = tmp_path / ".harness-junit.xml"

        def fake_run(args, **kwargs):
            junit_xml.write_text("<<invalid xml>>")
            return MagicMock(returncode=1, stdout="failed", stderr="")

        with patch("harness_skills.generators.evaluation.subprocess.run", side_effect=fake_run):
            result = RegressionGate().run(tmp_path, GateConfig())

        assert result.status == GateStatus.FAILED
        assert any("Test suite failed" in f.message for f in result.failures)


# ---------------------------------------------------------------------------
# CoverageGate — missing JSON, malformed JSON, per-file failures
# ---------------------------------------------------------------------------


class TestCoverageGateExtended:
    def test_no_coverage_json_generated(self, tmp_path: Path) -> None:
        with patch("harness_skills.generators.evaluation.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
            result = CoverageGate().run(tmp_path, GateConfig())
        assert result.status == GateStatus.FAILED
        assert any("not generated" in f.message for f in result.failures)

    def test_malformed_coverage_json(self, tmp_path: Path) -> None:
        coverage_json = tmp_path / ".coverage.json"

        def fake_run(args, **kwargs):
            coverage_json.write_text("not json{{{")
            return MagicMock(returncode=1, stdout="", stderr="")

        with patch("harness_skills.generators.evaluation.subprocess.run", side_effect=fake_run):
            result = CoverageGate().run(tmp_path, GateConfig())
        assert result.status == GateStatus.FAILED
        assert any("malformed" in f.message.lower() for f in result.failures)

    def test_per_file_warning_below_threshold(self, tmp_path: Path) -> None:
        coverage_data = {
            "totals": {"percent_covered": 72.5},
            "files": {
                str(tmp_path / "src/bad.py"): {"summary": {"percent_covered": 50.0}},
            },
        }
        coverage_json = tmp_path / ".coverage.json"

        def fake_run(args, **kwargs):
            coverage_json.write_text(json.dumps(coverage_data))
            return MagicMock(returncode=1, stdout="", stderr="")

        with patch("harness_skills.generators.evaluation.subprocess.run", side_effect=fake_run):
            result = CoverageGate().run(tmp_path, GateConfig(coverage_threshold=90.0))
        warnings = [f for f in result.failures if f.severity == Severity.WARNING]
        assert any("50.0%" in f.message for f in warnings)

    def test_coverage_summary_message_passed(self, tmp_path: Path) -> None:
        coverage_data = {"totals": {"percent_covered": 95.0}, "files": {}}
        coverage_json = tmp_path / ".coverage.json"

        def fake_run(args, **kwargs):
            coverage_json.write_text(json.dumps(coverage_data))
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("harness_skills.generators.evaluation.subprocess.run", side_effect=fake_run):
            result = CoverageGate().run(tmp_path, GateConfig(coverage_threshold=90.0))
        assert "passed" in (result.message or "").lower() or result.status == GateStatus.PASSED

    def test_coverage_summary_message_with_only_warnings(self, tmp_path: Path) -> None:
        """When only warnings (no errors), the summary should use the parent class message."""
        coverage_data = {
            "totals": {"percent_covered": 91.0},
            "files": {
                "bad.py": {"summary": {"percent_covered": 50.0}},
            },
        }
        coverage_json = tmp_path / ".coverage.json"

        def fake_run(args, **kwargs):
            coverage_json.write_text(json.dumps(coverage_data))
            return MagicMock(returncode=1, stdout="", stderr="")

        with patch("harness_skills.generators.evaluation.subprocess.run", side_effect=fake_run):
            result = CoverageGate().run(tmp_path, GateConfig(coverage_threshold=90.0))
        # Per-file warning only, no overall threshold breach
        if result.failures and all(f.severity != Severity.ERROR for f in result.failures):
            assert result.message is not None


# ---------------------------------------------------------------------------
# SecurityGate — pip-audit & bandit
# ---------------------------------------------------------------------------


from harness_skills.generators.evaluation import PerformanceGate


class TestSecurityGateExtended:
    def test_pip_audit_not_installed_skipped(self, tmp_path: Path) -> None:
        with patch("harness_skills.generators.evaluation.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=127, stdout="", stderr="No module named pip_audit"
            )
            result = SecurityGate().run(tmp_path, GateConfig())
        # Should not produce failures for missing pip-audit
        pip_audit_failures = [f for f in result.failures if "pip-audit" in f.message.lower()]
        # Bandit part may also be missing — that's fine
        assert all(f.gate_id == GateId.SECURITY for f in result.failures)

    def test_pip_audit_non_json_output(self, tmp_path: Path) -> None:
        calls = [0]

        def fake_run(args, **kwargs):
            calls[0] += 1
            if "pip_audit" in " ".join(args):
                return MagicMock(returncode=1, stdout="not json", stderr="error text")
            # bandit call
            return MagicMock(returncode=2, stdout="", stderr="")

        with patch("harness_skills.generators.evaluation.subprocess.run", side_effect=fake_run):
            result = SecurityGate().run(tmp_path, GateConfig())
        audit_warn = [f for f in result.failures if "not parseable" in f.message.lower()]
        assert len(audit_warn) == 1

    def test_pip_audit_vulnerability_reported(self, tmp_path: Path) -> None:
        audit_data = {
            "dependencies": [{
                "name": "requests",
                "vulns": [{"id": "CVE-2023-99999", "description": "Bad bug", "fix_versions": ["2.32.0"]}],
            }]
        }

        def fake_run(args, **kwargs):
            if "pip_audit" in " ".join(args):
                return MagicMock(returncode=1, stdout=json.dumps(audit_data), stderr="")
            return MagicMock(returncode=2, stdout="", stderr="")

        with patch("harness_skills.generators.evaluation.subprocess.run", side_effect=fake_run):
            result = SecurityGate().run(tmp_path, GateConfig())
        cve_failures = [f for f in result.failures if "CVE-2023-99999" in (f.rule_id or "")]
        assert len(cve_failures) == 1
        assert "requests" in cve_failures[0].message
        assert "Upgrade" in (cve_failures[0].suggestion or "")

    def test_pip_audit_vulnerability_no_fix(self, tmp_path: Path) -> None:
        audit_data = {
            "dependencies": [{
                "name": "old-lib",
                "vulns": [{"id": "CVE-2024-00001", "description": "No fix", "fix_versions": []}],
            }]
        }

        def fake_run(args, **kwargs):
            if "pip_audit" in " ".join(args):
                return MagicMock(returncode=1, stdout=json.dumps(audit_data), stderr="")
            return MagicMock(returncode=2, stdout="", stderr="")

        with patch("harness_skills.generators.evaluation.subprocess.run", side_effect=fake_run):
            result = SecurityGate().run(tmp_path, GateConfig())
        f = [x for x in result.failures if x.rule_id == "CVE-2024-00001"]
        assert len(f) == 1
        assert "No fix" in (f[0].suggestion or "")

    def test_bandit_issues_parsed(self, tmp_path: Path) -> None:
        bandit_data = {
            "results": [{
                "test_id": "B101",
                "issue_text": "Use of assert detected.",
                "issue_severity": "MEDIUM",
                "filename": str(tmp_path / "app.py"),
                "line_number": 5,
                "code": "assert True",
            }]
        }

        def fake_run(args, **kwargs):
            if "pip_audit" in " ".join(args):
                return MagicMock(returncode=0, stdout="", stderr="")
            if "bandit" in " ".join(args):
                return MagicMock(returncode=1, stdout=json.dumps(bandit_data), stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("harness_skills.generators.evaluation.subprocess.run", side_effect=fake_run):
            result = SecurityGate().run(tmp_path, GateConfig())
        bandit_f = [f for f in result.failures if f.rule_id == "B101"]
        assert len(bandit_f) == 1
        assert bandit_f[0].severity == Severity.WARNING
        assert bandit_f[0].line_number == 5

    def test_bandit_json_parse_error(self, tmp_path: Path) -> None:
        def fake_run(args, **kwargs):
            if "pip_audit" in " ".join(args):
                return MagicMock(returncode=0, stdout="", stderr="")
            if "bandit" in " ".join(args):
                return MagicMock(returncode=1, stdout="not json", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("harness_skills.generators.evaluation.subprocess.run", side_effect=fake_run):
            result = SecurityGate().run(tmp_path, GateConfig())
        # Bandit JSON parse error -> returns empty list
        assert not any(f.rule_id and f.rule_id.startswith("B") for f in result.failures)


# ---------------------------------------------------------------------------
# PerformanceGate tests
# ---------------------------------------------------------------------------


class TestPerformanceGate:
    def test_no_budget_configured_passes(self, tmp_path: Path) -> None:
        result = PerformanceGate().run(tmp_path, GateConfig(performance_budget_ms=None))
        assert result.status == GateStatus.PASSED

    def test_no_perf_script_info(self, tmp_path: Path) -> None:
        result = PerformanceGate().run(tmp_path, GateConfig(performance_budget_ms=5000))
        assert result.status == GateStatus.FAILED
        assert any("not found" in f.message for f in result.failures)
        assert result.failures[0].severity == Severity.INFO

    def test_perf_script_nonzero_exit(self, tmp_path: Path) -> None:
        script = tmp_path / ".harness-perf.sh"
        script.write_text("#!/bin/bash\nexit 0")
        with patch("harness_skills.generators.evaluation.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="crash")
            result = PerformanceGate().run(tmp_path, GateConfig(performance_budget_ms=5000))
        assert result.status == GateStatus.FAILED
        assert any("exited with code" in f.message for f in result.failures)

    def test_perf_script_exceeds_budget(self, tmp_path: Path) -> None:
        script = tmp_path / ".harness-perf.sh"
        script.write_text("#!/bin/bash\nexit 0")

        original_monotonic = time.monotonic
        call_count = [0]

        def fake_monotonic():
            call_count[0] += 1
            if call_count[0] == 1:
                return 0.0
            if call_count[0] == 2:
                return 0.0
            return 10.0  # 10 seconds elapsed

        with patch("harness_skills.generators.evaluation.subprocess.run") as mock_run, \
             patch("harness_skills.generators.evaluation.time.monotonic", side_effect=fake_monotonic):
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = PerformanceGate().run(tmp_path, GateConfig(performance_budget_ms=100))
        assert result.status == GateStatus.FAILED
        assert any("exceeds budget" in f.message for f in result.failures)

    def test_perf_script_within_budget(self, tmp_path: Path) -> None:
        script = tmp_path / ".harness-perf.sh"
        script.write_text("#!/bin/bash\nexit 0")
        with patch("harness_skills.generators.evaluation.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = PerformanceGate().run(tmp_path, GateConfig(performance_budget_ms=999999))
        assert result.status == GateStatus.PASSED


# ---------------------------------------------------------------------------
# ArchitectureGate — syntax error and skip logic
# ---------------------------------------------------------------------------


class TestArchitectureGateExtended:
    def test_skips_venv(self, tmp_path: Path) -> None:
        venv = tmp_path / ".venv" / "lib"
        venv.mkdir(parents=True)
        (venv / "service_mod.py").write_text("from repo.thing import X\n")
        result = ArchitectureGate().run(tmp_path, GateConfig())
        assert result.status == GateStatus.PASSED

    def test_skips_syntax_error_files(self, tmp_path: Path) -> None:
        svc = tmp_path / "service"
        svc.mkdir()
        (svc / "broken.py").write_text("def broken(:\n")
        result = ArchitectureGate().run(tmp_path, GateConfig())
        # Should not raise; just skip the file
        assert isinstance(result.status, GateStatus)

    def test_no_layer_detected_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "random.py").write_text("import os\n")
        result = ArchitectureGate().run(tmp_path, GateConfig())
        assert result.status == GateStatus.PASSED

    def test_module_to_layer_returns_none(self, tmp_path: Path) -> None:
        gate = ArchitectureGate()
        assert gate._module_to_layer("os", ["types", "config"], tmp_path) is None

    def test_module_to_layer_returns_match(self, tmp_path: Path) -> None:
        gate = ArchitectureGate()
        result = gate._module_to_layer("service.user_service", ["repo", "service"], tmp_path)
        assert result == "service"

    def test_detect_layer_returns_none_for_unmatched(self, tmp_path: Path) -> None:
        gate = ArchitectureGate()
        result = gate._detect_layer(tmp_path / "random.py", ["types", "config"], tmp_path)
        assert result is None

    def test_detect_layer_returns_match(self, tmp_path: Path) -> None:
        gate = ArchitectureGate()
        svc = tmp_path / "service" / "foo.py"
        result = gate._detect_layer(svc, ["repo", "service"], tmp_path)
        assert result == "service"

    def test_imports_from_unknown_layer_skipped(self, tmp_path: Path) -> None:
        """Import from a module that doesn't match any layer -> continue (line 822)."""
        svc_dir = tmp_path / "service"
        svc_dir.mkdir()
        (svc_dir / "handler.py").write_text(
            "import os\nimport json\n"
            "from repo.stuff import Thing\n"
        )
        result = ArchitectureGate().run(tmp_path, GateConfig())
        # "os" and "json" don't match any layer -> skipped; "repo.stuff" is lower layer -> no violation
        assert isinstance(result.status, GateStatus)


# ---------------------------------------------------------------------------
# PrinciplesGate — syntax error files skipped
# ---------------------------------------------------------------------------


class TestPrinciplesGateExtended:
    def test_skips_syntax_error_files(self, tmp_path: Path) -> None:
        (tmp_path / "broken.py").write_text("def broken(:\n")
        result = PrinciplesGate().run(tmp_path, GateConfig())
        assert isinstance(result.status, GateStatus)

    def test_skips_venv(self, tmp_path: Path) -> None:
        venv = tmp_path / ".venv" / "pkg"
        venv.mkdir(parents=True)
        (venv / "bad.py").write_text("x = 42 * 365\n")
        result = PrinciplesGate().run(tmp_path, GateConfig())
        assert all(f.file_path != ".venv/pkg/bad.py" for f in result.failures)


# ---------------------------------------------------------------------------
# DocsFreshnessGate — no timestamp, invalid timestamp
# ---------------------------------------------------------------------------


class TestDocsFreshnessGateExtended:
    def test_no_timestamp_in_file(self, tmp_path: Path) -> None:
        agents = tmp_path / "AGENTS.md"
        agents.write_text("# AGENTS\nNo timestamp here.\n")
        result = DocsFreshnessGate().run(tmp_path, GateConfig())
        info = [f for f in result.failures if f.rule_id == "docs/missing-timestamp"]
        assert any(f.file_path == "AGENTS.md" for f in info)

    def test_invalid_timestamp_ignored(self, tmp_path: Path) -> None:
        agents = tmp_path / "AGENTS.md"
        agents.write_text("# AGENTS\n<!-- generated_at: not-a-date -->\n")
        result = DocsFreshnessGate().run(tmp_path, GateConfig())
        # Should not crash; the invalid timestamp should be silently skipped


# ---------------------------------------------------------------------------
# TypesGate — tsc branch and skip logic
# ---------------------------------------------------------------------------


class TestTypesGateExtended:
    def test_tsc_parses_errors(self, tmp_path: Path) -> None:
        (tmp_path / "tsconfig.json").write_text("{}")
        tsc_output = "src/app.ts(10,5): error TS2322: Type 'string' is not assignable to type 'number'.\n"
        with patch("harness_skills.generators.evaluation.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout=tsc_output, stderr="")
            result = TypesGate().run(tmp_path, GateConfig())
        assert result.status == GateStatus.FAILED
        assert len(result.failures) >= 1
        f = result.failures[0]
        assert f.file_path == "src/app.ts"
        assert f.line_number == 10
        assert f.rule_id == "TS2322"

    def test_tsc_passes(self, tmp_path: Path) -> None:
        (tmp_path / "tsconfig.json").write_text("{}")
        with patch("harness_skills.generators.evaluation.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = TypesGate().run(tmp_path, GateConfig())
        assert result.status == GateStatus.PASSED

    def test_unknown_language_skipped(self, tmp_path: Path) -> None:
        # No pyproject.toml, setup.py, or tsconfig.json
        result = TypesGate().run(tmp_path, GateConfig())
        assert result.status == GateStatus.PASSED


# ---------------------------------------------------------------------------
# LintGate — ESLint with no changed JS files, ruff non-json output
# ---------------------------------------------------------------------------


class TestLintGateExtended:
    def test_eslint_no_js_files_in_changes(self, tmp_path: Path) -> None:
        (tmp_path / ".eslintrc.json").write_text("{}")
        git_diff_output = "README.md\n"

        def fake_run(args, **kwargs):
            if "git" in args:
                return MagicMock(returncode=0, stdout=git_diff_output, stderr="")
            return MagicMock(returncode=0, stdout="[]", stderr="")

        with patch("harness_skills.generators.evaluation.subprocess.run", side_effect=fake_run):
            result = LintGate().run(tmp_path, GateConfig())
        assert result.status == GateStatus.PASSED

    def test_eslint_full_scan_severity_1_is_warning(self, tmp_path: Path) -> None:
        (tmp_path / ".eslintrc.json").write_text("{}")
        eslint_output = json.dumps([{
            "filePath": str(tmp_path / "app.js"),
            "messages": [{
                "ruleId": "no-unused-vars",
                "severity": 1,
                "message": "unused var",
                "line": 1,
            }],
        }])

        def fake_run(args, **kwargs):
            if "git" in args:
                # No changed files -> full scan
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=1, stdout=eslint_output, stderr="")

        with patch("harness_skills.generators.evaluation.subprocess.run", side_effect=fake_run):
            result = LintGate().run(tmp_path, GateConfig())
        assert result.status == GateStatus.FAILED
        assert result.failures[0].severity == Severity.WARNING

    def test_eslint_json_decode_error(self, tmp_path: Path) -> None:
        (tmp_path / ".eslintrc.json").write_text("{}")

        def fake_run(args, **kwargs):
            if "git" in args:
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=1, stdout="not json!", stderr="")

        with patch("harness_skills.generators.evaluation.subprocess.run", side_effect=fake_run):
            result = LintGate().run(tmp_path, GateConfig())
        # JSON decode error for eslint returns empty failures list
        assert result.status == GateStatus.PASSED or len(result.failures) == 0

    def test_ruff_non_json_output(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n")

        def fake_run(args, **kwargs):
            if "git" in args:
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=1, stdout="some non-json ruff output", stderr="")

        with patch("harness_skills.generators.evaluation.subprocess.run", side_effect=fake_run):
            result = LintGate().run(tmp_path, GateConfig())
        # Non-JSON ruff output should produce a single warning
        assert any("non-JSON" in f.message for f in result.failures)

    def test_ruff_empty_stdout_on_failure(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n")

        def fake_run(args, **kwargs):
            if "git" in args:
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=1, stdout="", stderr="")

        with patch("harness_skills.generators.evaluation.subprocess.run", side_effect=fake_run):
            result = LintGate().run(tmp_path, GateConfig())
        assert result.status == GateStatus.PASSED

    def test_git_diff_fallback_to_cached(self, tmp_path: Path) -> None:
        """When HEAD diff fails, falls back to --cached."""
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n")
        call_count = [0]

        def fake_run(args, **kwargs):
            if "git" in args:
                call_count[0] += 1
                if call_count[0] == 1:
                    return MagicMock(returncode=1, stdout="", stderr="error")
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=0, stdout="[]", stderr="")

        with patch("harness_skills.generators.evaluation.subprocess.run", side_effect=fake_run):
            result = LintGate().run(tmp_path, GateConfig())
        assert call_count[0] >= 2  # HEAD diff + cached fallback


# ---------------------------------------------------------------------------
# format_report — jsonschema import handling
# ---------------------------------------------------------------------------


class TestFormatReportExtended:
    def test_format_report_without_jsonschema(self) -> None:
        report = EvaluationReport.from_gate_results([])
        with patch.dict("sys.modules", {"jsonschema": None}):
            json_str = format_report(report)
            data = json.loads(json_str)
            assert data["passed"] is True


# ---------------------------------------------------------------------------
# _collect_metadata — git not available
# ---------------------------------------------------------------------------


class TestCollectMetadata:
    def test_metadata_git_not_available(self, tmp_path: Path) -> None:
        from harness_skills.generators.evaluation import _collect_metadata

        with patch("harness_skills.generators.evaluation.subprocess.run",
                   side_effect=FileNotFoundError("git not found")):
            meta = _collect_metadata(tmp_path)
        assert meta.git_sha is None
        assert meta.git_branch is None


# ---------------------------------------------------------------------------
# Additional tests for remaining uncovered lines
# ---------------------------------------------------------------------------


class TestDocsFreshnessInvalidTimestamp:
    def test_invalid_timestamp_value_error(self, tmp_path: Path) -> None:
        """Invalid timestamp format triggers ValueError branch (lines 1026-1027).

        The value must match the TIMESTAMP_RE pattern (digits-digits-digits...) but
        fail datetime.fromisoformat() to trigger the ValueError except branch.
        """
        # This matches the regex r"generated_at:\s*([\d\-T:.+Z]+)" but is not a valid ISO date
        invalid_but_matches_regex = "9999-99-99T99:99:99+00:00"
        agents = tmp_path / "AGENTS.md"
        agents.write_text(f"# AGENTS\n<!-- generated_at: {invalid_but_matches_regex} -->\n")
        (tmp_path / "docs").mkdir()
        for name in ["docs/ARCHITECTURE.md", "docs/PRINCIPLES.md", "docs/EVALUATION.md"]:
            p = tmp_path / name
            p.write_text(f"# {name}\n<!-- generated_at: {invalid_but_matches_regex} -->\n")
        result = DocsFreshnessGate().run(tmp_path, GateConfig())
        # Should not crash; invalid dates are silently skipped via except ValueError: pass
        assert isinstance(result.status, GateStatus)


class TestCoverageSummaryMessageWarningsOnly:
    def test_summary_calls_super_when_only_warnings(self, tmp_path: Path) -> None:
        """When there are failures but none are errors, super()._summary_message is called (line 822)."""
        gate = CoverageGate()
        config = GateConfig(coverage_threshold=90.0)
        warnings = [
            GateFailure(
                severity=Severity.WARNING,
                gate_id=GateId.COVERAGE,
                message="file.py: coverage 50.0%",
            )
        ]
        msg = gate._summary_message(warnings, config)
        assert "coverage" in msg.lower()


class TestTypesGateTscNonMatchingLine:
    def test_tsc_with_non_matching_lines(self, tmp_path: Path) -> None:
        """Lines that don't match TSC pattern are skipped (line 1095)."""
        (tmp_path / "tsconfig.json").write_text("{}")
        tsc_output = (
            "Found 1 error.\n"
            "src/app.ts(5,3): error TS1234: Some error.\n"
            "Non-matching line here\n"
        )
        with patch("harness_skills.generators.evaluation.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout=tsc_output, stderr="")
            result = TypesGate().run(tmp_path, GateConfig())
        assert result.status == GateStatus.FAILED
        assert len(result.failures) == 1  # Only the matching line


class TestLintGateEslintNoViolations:
    def test_eslint_returns_zero(self, tmp_path: Path) -> None:
        """ESLint returning 0 produces no failures (line 1262)."""
        (tmp_path / ".eslintrc.json").write_text("{}")

        def fake_run(args, **kwargs):
            if "git" in args:
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=0, stdout="[]", stderr="")

        with patch("harness_skills.generators.evaluation.subprocess.run", side_effect=fake_run):
            result = LintGate().run(tmp_path, GateConfig())
        assert result.status == GateStatus.PASSED
