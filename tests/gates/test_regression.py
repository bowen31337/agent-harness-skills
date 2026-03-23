"""
tests/gates/test_regression.py
================================
Unit and integration tests for :mod:`harness_skills.gates.regression`.

Test strategy
-------------
* **Fixture helpers** build minimal JUnit XML files on the temporary
  filesystem so the real parsing logic runs against actual file content.
* **subprocess stubbing** via ``monkeypatch`` replaces
  ``subprocess.run`` so tests run instantly without executing a real
  pytest process.
* Each violation kind (``test_failed``, ``suite_error``, ``timeout``) is
  exercised by dedicated test cases.
* Threshold / boundary cases: all pass, one fail, all fail, mix of
  failures and errors.
* ``fail_on_error=False`` behaviour is verified: violations become
  warnings and the gate still passes.
* ``test_paths`` and ``extra_args`` propagation is verified against the
  captured subprocess command.
* A small integration section runs :class:`RegressionGate` end-to-end
  against a real temporary pytest project so the complete path through
  pytest -> JUnit XML -> :class:`GateResult` is exercised.
"""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from harness_skills.gates.regression import (
    GateResult,
    RegressionGate,
    Violation,
    _parse_junit_xml,
)
from harness_skills.models.gate_configs import RegressionGateConfig


# ---------------------------------------------------------------------------
# Helpers — JUnit XML writers
# ---------------------------------------------------------------------------
# NOTE: These helpers write XML strings using explicit f-string concatenation
# (not textwrap.dedent) to guarantee the <?xml ...?> declaration appears at
# column 0 with no leading whitespace — a requirement of the XML spec that
# xml.etree.ElementTree strictly enforces.


def write_passing_junit(path: Path, n_tests: int = 3) -> Path:
    """Write a JUnit XML report where *n_tests* all pass."""
    case_tags = "\n".join(
        f'    <testcase classname="tests.test_foo" name="test_{i}" time="0.01"/>'
        for i in range(n_tests)
    )
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<testsuites>\n"
        f'  <testsuite name="pytest" tests="{n_tests}" errors="0"'
        f' failures="0" skipped="0" time="0.05">\n'
        f"{case_tags}\n"
        "  </testsuite>\n"
        "</testsuites>\n"
    )
    path.write_text(xml, encoding="utf-8")
    return path


def write_failing_junit(
    path: Path,
    failures: list[tuple[str, str, str | None, int | None]],
    n_total: int | None = None,
) -> Path:
    """Write a JUnit XML report with the given *failures*.

    Parameters
    ----------
    failures:
        List of ``(classname, testname, file_path, line_number)`` tuples.
        ``file_path`` and ``line_number`` are embedded in the failure text
        to exercise the file/line extraction regex.
    n_total:
        Total test count (defaults to len(failures)).
    """
    total = n_total if n_total is not None else len(failures)
    case_lines: list[str] = []
    for classname, testname, fp, ln in failures:
        if fp and ln:
            loc_text = f"{fp}:{ln}: AssertionError"
        elif fp:
            loc_text = f"AssertionError in {fp}"
        else:
            loc_text = ""
        case_lines.append(
            f'    <testcase classname="{classname}" name="{testname}" time="0.01">\n'
            f'      <failure message="assert False">{loc_text}\nassert False</failure>\n'
            f"    </testcase>"
        )

    inner = "\n".join(case_lines)
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<testsuites>\n"
        f'  <testsuite name="pytest" tests="{total}" errors="0"'
        f' failures="{len(failures)}" skipped="0" time="0.05">\n'
        f"{inner}\n"
        "  </testsuite>\n"
        "</testsuites>\n"
    )
    path.write_text(xml, encoding="utf-8")
    return path


def write_error_junit(path: Path, classname: str, testname: str) -> Path:
    """Write a JUnit XML report with one test-error element."""
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<testsuites>\n"
        '  <testsuite name="pytest" tests="1" errors="1" failures="0"'
        ' skipped="0" time="0.01">\n'
        f'    <testcase classname="{classname}" name="{testname}" time="0.0">\n'
        '      <error message="RuntimeError: setup failed">\n'
        "        tests/conftest.py:42: RuntimeError\n"
        "      </error>\n"
        "    </testcase>\n"
        "  </testsuite>\n"
        "</testsuites>\n"
    )
    path.write_text(xml, encoding="utf-8")
    return path


def write_mixed_junit(path: Path) -> Path:
    """Write a JUnit XML with one pass, one failure, one error, one skip."""
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<testsuites>\n"
        '  <testsuite name="pytest" tests="4" errors="1" failures="1"'
        ' skipped="1" time="0.1">\n'
        '    <testcase classname="tests.test_a" name="test_pass" time="0.01"/>\n'
        '    <testcase classname="tests.test_a" name="test_fail" time="0.01">\n'
        '      <failure message="AssertionError">tests/test_a.py:10: assert False</failure>\n'
        "    </testcase>\n"
        '    <testcase classname="tests.test_b" name="test_err" time="0.0">\n'
        '      <error message="RuntimeError">tests/conftest.py:5: RuntimeError</error>\n'
        "    </testcase>\n"
        '    <testcase classname="tests.test_a" name="test_skip" time="0.0">\n'
        "      <skipped/>\n"
        "    </testcase>\n"
        "  </testsuite>\n"
        "</testsuites>\n"
    )
    path.write_text(xml, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Subprocess mock helpers
# ---------------------------------------------------------------------------


def _make_completed(returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout="", stderr="")


# ---------------------------------------------------------------------------
# Tests — _parse_junit_xml
# ---------------------------------------------------------------------------


class TestParseJunitXml:
    def test_passing_report_returns_empty_violations(self, tmp_path: Path) -> None:
        xml = write_passing_junit(tmp_path / "junit.xml", n_tests=5)
        violations, stats = _parse_junit_xml(xml, "error")
        assert violations == []
        assert stats["total"] == 5
        assert stats["failed"] == 0
        assert stats["skipped"] == 0

    def test_failing_report_produces_violation_per_failure(self, tmp_path: Path) -> None:
        xml = write_failing_junit(
            tmp_path / "junit.xml",
            failures=[
                ("tests.test_foo", "test_one", "tests/test_foo.py", 12),
                ("tests.test_bar", "test_two", "tests/test_bar.py", 34),
            ],
        )
        violations, stats = _parse_junit_xml(xml, "error")
        assert len(violations) == 2
        assert all(v.kind == "test_failed" for v in violations)
        assert all(v.severity == "error" for v in violations)
        assert violations[0].file_path == "tests/test_foo.py"
        assert violations[0].line_number == 12
        assert violations[1].file_path == "tests/test_bar.py"
        assert violations[1].line_number == 34

    def test_failure_without_location_has_none_file_line(self, tmp_path: Path) -> None:
        xml = write_failing_junit(
            tmp_path / "junit.xml",
            failures=[("tests.test_x", "test_noloc", None, None)],
        )
        violations, _ = _parse_junit_xml(xml, "error")
        assert len(violations) == 1
        assert violations[0].file_path is None
        assert violations[0].line_number is None

    def test_error_testcase_produces_suite_error_violation(self, tmp_path: Path) -> None:
        xml = write_error_junit(tmp_path / "junit.xml", "tests.test_c", "test_broken")
        violations, stats = _parse_junit_xml(xml, "error")
        assert len(violations) == 1
        assert violations[0].kind == "suite_error"
        assert "test_broken" in violations[0].message

    def test_warning_severity_when_fail_on_error_false(self, tmp_path: Path) -> None:
        xml = write_failing_junit(
            tmp_path / "junit.xml",
            failures=[("tests.test_w", "test_warn", None, None)],
        )
        violations, _ = _parse_junit_xml(xml, "warning")
        assert all(v.severity == "warning" for v in violations)

    def test_mixed_report_stats(self, tmp_path: Path) -> None:
        xml = write_mixed_junit(tmp_path / "junit.xml")
        violations, stats = _parse_junit_xml(xml, "error")
        assert stats["total"] == 4
        assert stats["failed"] == 1
        assert stats["errors"] == 1
        assert stats["skipped"] == 1
        # one <failure> element + one <error> element
        assert len(violations) == 2

    def test_corrupt_xml_returns_empty(self, tmp_path: Path) -> None:
        xml = tmp_path / "bad.xml"
        xml.write_text("<not valid xml <<>>", encoding="utf-8")
        violations, stats = _parse_junit_xml(xml, "error")
        assert violations == []
        assert stats == {}


# ---------------------------------------------------------------------------
# Tests — Violation.summary()
# ---------------------------------------------------------------------------


class TestViolationSummary:
    def test_summary_with_file_and_line(self) -> None:
        v = Violation(
            kind="test_failed",
            severity="error",
            message="Test failed: test_foo",
            file_path="tests/test_foo.py",
            line_number=42,
        )
        s = v.summary()
        assert "[ERROR  ]" in s
        assert "tests/test_foo.py:42" in s
        assert "Test failed" in s

    def test_summary_without_location(self) -> None:
        v = Violation(kind="suite_error", severity="error", message="pytest error")
        s = v.summary()
        assert "suite_error" in s
        # No file bracket when file_path is None
        assert "[" not in s.split("—")[0].split("]", 1)[-1].strip()

    def test_summary_timeout(self) -> None:
        v = Violation(kind="timeout", severity="error", message="timed out after 300s")
        s = v.summary()
        assert "timeout" in s


# ---------------------------------------------------------------------------
# Tests — GateResult helpers
# ---------------------------------------------------------------------------


class TestGateResult:
    def test_errors_filters_by_severity(self) -> None:
        r = GateResult(
            passed=False,
            violations=[
                Violation(kind="test_failed", severity="error", message="e1"),
                Violation(kind="test_failed", severity="warning", message="w1"),
            ],
        )
        assert len(r.errors()) == 1
        assert len(r.warnings()) == 1

    def test_passed_result_has_no_violations(self) -> None:
        r = GateResult(passed=True)
        assert r.violations == []
        assert r.errors() == []


# ---------------------------------------------------------------------------
# Tests — RegressionGate.run() with subprocess mocking
# ---------------------------------------------------------------------------


class TestRegressionGateRunPass:
    """Tests for the happy path: all tests pass."""

    def test_passes_when_returncode_zero(self, tmp_path: Path) -> None:
        cfg = RegressionGateConfig()
        gate = RegressionGate(cfg)

        junit = tmp_path / ".harness-regression-junit.xml"

        def fake_run(cmd, **kwargs):  # noqa: ANN001
            write_passing_junit(junit, n_tests=5)
            return _make_completed(0)

        with patch("harness_skills.gates.regression.subprocess.run", side_effect=fake_run):
            result = gate.run(tmp_path)

        assert result.passed is True
        assert result.violations == []
        assert result.total_tests == 5
        assert result.failed_tests == 0

    def test_junit_xml_cleaned_up_on_pass(self, tmp_path: Path) -> None:
        cfg = RegressionGateConfig()
        gate = RegressionGate(cfg)
        junit = tmp_path / ".harness-regression-junit.xml"

        def fake_run(cmd, **kwargs):  # noqa: ANN001
            write_passing_junit(junit)
            return _make_completed(0)

        with patch("harness_skills.gates.regression.subprocess.run", side_effect=fake_run):
            gate.run(tmp_path)

        assert not junit.exists(), "JUnit XML should be removed after a successful run"


class TestRegressionGateRunFail:
    """Tests for the fail path: one or more tests fail."""

    def test_fails_when_returncode_nonzero(self, tmp_path: Path) -> None:
        cfg = RegressionGateConfig()
        gate = RegressionGate(cfg)
        junit = tmp_path / ".harness-regression-junit.xml"

        def fake_run(cmd, **kwargs):  # noqa: ANN001
            write_failing_junit(
                junit,
                failures=[("tests.test_foo", "test_bar", "tests/test_foo.py", 7)],
            )
            return _make_completed(1)

        with patch("harness_skills.gates.regression.subprocess.run", side_effect=fake_run):
            result = gate.run(tmp_path)

        assert result.passed is False
        assert len(result.violations) == 1
        assert result.violations[0].kind == "test_failed"
        assert result.violations[0].file_path == "tests/test_foo.py"
        assert result.violations[0].line_number == 7

    def test_multiple_failures_produce_multiple_violations(self, tmp_path: Path) -> None:
        cfg = RegressionGateConfig()
        gate = RegressionGate(cfg)
        junit = tmp_path / ".harness-regression-junit.xml"

        def fake_run(cmd, **kwargs):  # noqa: ANN001
            write_failing_junit(
                junit,
                failures=[
                    ("tests.a", "test_1", "tests/a.py", 10),
                    ("tests.b", "test_2", "tests/b.py", 20),
                    ("tests.c", "test_3", None, None),
                ],
                n_total=10,
            )
            return _make_completed(1)

        with patch("harness_skills.gates.regression.subprocess.run", side_effect=fake_run):
            result = gate.run(tmp_path)

        assert result.passed is False
        assert len(result.violations) == 3
        assert result.total_tests == 10

    def test_fallback_violation_when_no_junit_xml(self, tmp_path: Path) -> None:
        """Gate produces a generic suite_error when JUnit XML is absent."""
        cfg = RegressionGateConfig()
        gate = RegressionGate(cfg)

        with patch(
            "harness_skills.gates.regression.subprocess.run",
            return_value=_make_completed(1),
        ):
            result = gate.run(tmp_path)

        assert result.passed is False
        assert len(result.violations) == 1
        assert result.violations[0].kind == "suite_error"
        assert "non-zero" in result.violations[0].message

    def test_junit_xml_cleaned_up_on_failure(self, tmp_path: Path) -> None:
        cfg = RegressionGateConfig()
        gate = RegressionGate(cfg)
        junit = tmp_path / ".harness-regression-junit.xml"

        def fake_run(cmd, **kwargs):  # noqa: ANN001
            write_failing_junit(junit, failures=[("t", "t1", None, None)])
            return _make_completed(1)

        with patch("harness_skills.gates.regression.subprocess.run", side_effect=fake_run):
            gate.run(tmp_path)

        assert not junit.exists(), "JUnit XML should be removed after a failing run"


class TestRegressionGateTimeout:
    def test_timeout_returns_failed_result(self, tmp_path: Path) -> None:
        cfg = RegressionGateConfig(timeout_seconds=5)
        gate = RegressionGate(cfg)

        with patch(
            "harness_skills.gates.regression.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["pytest"], timeout=5),
        ):
            result = gate.run(tmp_path)

        assert result.passed is False
        assert len(result.violations) == 1
        assert result.violations[0].kind == "timeout"
        assert "5s" in result.violations[0].message

    def test_timeout_passes_when_fail_on_error_false(self, tmp_path: Path) -> None:
        cfg = RegressionGateConfig(timeout_seconds=5, fail_on_error=False)
        gate = RegressionGate(cfg)

        with patch(
            "harness_skills.gates.regression.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["pytest"], timeout=5),
        ):
            result = gate.run(tmp_path)

        assert result.passed is True
        assert result.violations[0].severity == "warning"


class TestRegressionGateFailOnErrorFalse:
    """fail_on_error=False should downgrade violations to warnings and pass."""

    def test_failures_become_warnings_and_gate_passes(self, tmp_path: Path) -> None:
        cfg = RegressionGateConfig(fail_on_error=False)
        gate = RegressionGate(cfg)
        junit = tmp_path / ".harness-regression-junit.xml"

        def fake_run(cmd, **kwargs):  # noqa: ANN001
            write_failing_junit(junit, failures=[("t", "t1", None, None)])
            return _make_completed(1)

        with patch("harness_skills.gates.regression.subprocess.run", side_effect=fake_run):
            result = gate.run(tmp_path)

        assert result.passed is True
        assert all(v.severity == "warning" for v in result.violations)


class TestRegressionGateCommandConstruction:
    """Verify that test_paths and extra_args are forwarded to pytest."""

    def _capture_cmd(self, cfg: RegressionGateConfig, tmp_path: Path) -> list[str]:
        captured: list[list[str]] = []

        def fake_run(cmd, **kwargs):  # noqa: ANN001
            captured.append(list(cmd))
            return _make_completed(0)

        with patch("harness_skills.gates.regression.subprocess.run", side_effect=fake_run):
            RegressionGate(cfg).run(tmp_path)

        return captured[0]

    def test_default_config_runs_pytest(self, tmp_path: Path) -> None:
        cmd = self._capture_cmd(RegressionGateConfig(), tmp_path)
        assert "pytest" in " ".join(cmd)
        assert "--tb=short" in cmd
        assert "-q" in cmd

    def test_test_paths_appended_to_command(self, tmp_path: Path) -> None:
        cfg = RegressionGateConfig(test_paths=["tests/unit", "tests/integration"])
        cmd = self._capture_cmd(cfg, tmp_path)
        assert "tests/unit" in cmd
        assert "tests/integration" in cmd

    def test_extra_args_forwarded(self, tmp_path: Path) -> None:
        cfg = RegressionGateConfig(extra_args=["-k", "not slow", "-x"])
        cmd = self._capture_cmd(cfg, tmp_path)
        assert "-k" in cmd
        assert "not slow" in cmd
        assert "-x" in cmd

    def test_junit_xml_flag_present(self, tmp_path: Path) -> None:
        cmd = self._capture_cmd(RegressionGateConfig(), tmp_path)
        junit_flags = [a for a in cmd if a.startswith("--junitxml=")]
        assert len(junit_flags) == 1
        assert ".harness-regression-junit.xml" in junit_flags[0]


# ---------------------------------------------------------------------------
# Tests — RegressionGateConfig defaults and validation
# ---------------------------------------------------------------------------


class TestRegressionGateConfig:
    def test_default_values(self) -> None:
        cfg = RegressionGateConfig()
        assert cfg.enabled is True
        assert cfg.fail_on_error is True
        assert cfg.timeout_seconds == 300
        assert cfg.extra_args == []
        assert cfg.test_paths == []

    def test_custom_timeout(self) -> None:
        cfg = RegressionGateConfig(timeout_seconds=60)
        assert cfg.timeout_seconds == 60

    def test_pydantic_model_dump(self) -> None:
        cfg = RegressionGateConfig(timeout_seconds=120, extra_args=["-v"])
        d = cfg.model_dump()
        assert d["timeout_seconds"] == 120
        assert d["extra_args"] == ["-v"]

    def test_pydantic_model_validate(self) -> None:
        cfg = RegressionGateConfig.model_validate(
            {"timeout_seconds": 60, "test_paths": ["tests/"], "fail_on_error": False}
        )
        assert cfg.timeout_seconds == 60
        assert cfg.test_paths == ["tests/"]
        assert cfg.fail_on_error is False

    def test_model_validate_ignores_unknown_fields(self) -> None:
        """BaseGateConfig has extra='ignore' so unknown keys don't raise."""
        cfg = RegressionGateConfig.model_validate({"unknown_key": "value"})
        assert cfg.timeout_seconds == 300


# ---------------------------------------------------------------------------
# Integration tests — real pytest invocation
# ---------------------------------------------------------------------------


class TestRegressionGateIntegration:
    """Run RegressionGate against a minimal real pytest project.

    These tests actually invoke pytest in a subprocess.  They are fast
    because the test files are tiny and kept in a tmp_path.
    """

    def _write_project(self, root: Path, test_src: str) -> None:
        """Write a minimal pytest project to *root*."""
        (root / "tests").mkdir(parents=True, exist_ok=True)
        (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
        (root / "tests" / "test_sample.py").write_text(test_src, encoding="utf-8")

    def test_all_passing_tests_gate_passes(self, tmp_path: Path) -> None:
        self._write_project(
            tmp_path,
            textwrap.dedent("""\
                def test_one():
                    assert 1 + 1 == 2

                def test_two():
                    assert "hello".upper() == "HELLO"
            """),
        )
        cfg = RegressionGateConfig(timeout_seconds=60)
        result = RegressionGate(cfg).run(tmp_path)

        assert result.passed is True
        assert result.violations == []
        assert result.total_tests == 2
        assert result.failed_tests == 0

    def test_failing_test_gate_fails(self, tmp_path: Path) -> None:
        self._write_project(
            tmp_path,
            textwrap.dedent("""\
                def test_pass():
                    assert True

                def test_fail():
                    assert False, "intentional failure"
            """),
        )
        cfg = RegressionGateConfig(timeout_seconds=60)
        result = RegressionGate(cfg).run(tmp_path)

        assert result.passed is False
        assert len(result.violations) >= 1
        failing = [v for v in result.violations if v.kind == "test_failed"]
        assert len(failing) >= 1
        assert "test_fail" in failing[0].message

    def test_failing_with_fail_on_error_false_passes(self, tmp_path: Path) -> None:
        self._write_project(
            tmp_path,
            "def test_fail():\n    assert False\n",
        )
        cfg = RegressionGateConfig(timeout_seconds=60, fail_on_error=False)
        result = RegressionGate(cfg).run(tmp_path)

        assert result.passed is True
        assert all(v.severity == "warning" for v in result.violations)

    def test_extra_args_k_filter_only_runs_matching_tests(self, tmp_path: Path) -> None:
        self._write_project(
            tmp_path,
            textwrap.dedent("""\
                def test_included():
                    assert True

                def test_excluded():
                    assert False, "this should not run"
            """),
        )
        cfg = RegressionGateConfig(
            timeout_seconds=60,
            extra_args=["-k", "included"],
        )
        result = RegressionGate(cfg).run(tmp_path)

        assert result.passed is True

    def test_specific_test_paths(self, tmp_path: Path) -> None:
        """test_paths restricts pytest to only the given directory."""
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "__init__.py").write_text("", encoding="utf-8")
        (tmp_path / "tests" / "test_good.py").write_text(
            "def test_ok():\n    assert True\n", encoding="utf-8"
        )
        # A separate dir with a failing test that should NOT be run
        (tmp_path / "other").mkdir()
        (tmp_path / "other" / "test_bad.py").write_text(
            "def test_bad():\n    assert False\n", encoding="utf-8"
        )
        cfg = RegressionGateConfig(
            timeout_seconds=60,
            test_paths=["tests"],
        )
        result = RegressionGate(cfg).run(tmp_path)

        assert result.passed is True
