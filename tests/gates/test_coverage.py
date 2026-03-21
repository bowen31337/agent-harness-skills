"""
tests/gates/test_coverage.py
==============================
Unit tests for :mod:`harness_skills.gates.coverage`.

Test strategy
-------------
* **Fixture helpers** write temporary coverage report files so the real
  file-existence and parsing logic runs against the actual filesystem.
* Each supported format (XML/coverage.py, XML/JaCoCo, JSON, lcov) is
  exercised independently.
* Threshold boundary conditions are tested: exactly at threshold (pass),
  one hundredth below (fail), and well above (pass).
* Error paths — missing file, corrupt XML/JSON, unknown format — are each
  covered by dedicated test cases.
* ``fail_on_error=False`` behaviour is verified: violations become warnings
  and the gate still passes.
* A small integration section runs the gate end-to-end and checks
  :class:`~harness_skills.gates.coverage.GateResult` attributes.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from harness_skills.gates.coverage import (
    CoverageGate,
    GateResult,
    Violation,
    _detect_format,
    _parse_json,
    _parse_lcov,
    _parse_xml,
    _ParseError,
)
from harness_skills.models.gate_configs import CoverageGateConfig


# ---------------------------------------------------------------------------
# Helpers — report writers
# ---------------------------------------------------------------------------


def write_coverage_py_xml(path: Path, line_rate: float) -> Path:
    """Write a coverage.py-style XML report with the given *line_rate* (0–1)."""
    path.write_text(
        textwrap.dedent(f"""\
            <?xml version="1.0" ?>
            <coverage version="7.0" line-rate="{line_rate}" branch-rate="0.0"
                      lines-covered="0" lines-valid="0" timestamp="0">
              <packages/>
            </coverage>
        """),
        encoding="utf-8",
    )
    return path


def write_jacoco_xml(path: Path, covered: int, missed: int) -> Path:
    """Write a minimal JaCoCo-style XML report."""
    path.write_text(
        textwrap.dedent(f"""\
            <?xml version="1.0" encoding="UTF-8"?>
            <report name="test">
              <counter type="LINE" missed="{missed}" covered="{covered}"/>
            </report>
        """),
        encoding="utf-8",
    )
    return path


def write_coverage_json(path: Path, percent_covered: float) -> Path:
    """Write a coverage.py JSON report with the given *percent_covered*."""
    data = {
        "meta": {"version": "7.0"},
        "totals": {
            "covered_lines": 91,
            "num_statements": 100,
            "percent_covered": percent_covered,
            "missing_lines": 100 - int(percent_covered),
            "excluded_lines": 0,
        },
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def write_lcov(path: Path, lines_found: int, lines_hit: int) -> Path:
    """Write a minimal LCOV tracefile."""
    path.write_text(
        textwrap.dedent(f"""\
            TN:
            SF:src/main.py
            DA:1,1
            LF:{lines_found}
            LH:{lines_hit}
            end_of_record
        """),
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# _detect_format
# ---------------------------------------------------------------------------


class TestDetectFormat:
    def test_xml_extension(self, tmp_path: Path):
        assert _detect_format(tmp_path / "coverage.xml") == "xml"

    def test_json_extension(self, tmp_path: Path):
        assert _detect_format(tmp_path / "coverage.json") == "json"

    def test_info_extension(self, tmp_path: Path):
        assert _detect_format(tmp_path / "lcov.info") == "lcov"

    def test_out_extension(self, tmp_path: Path):
        assert _detect_format(tmp_path / "lcov.out") == "lcov"

    def test_lcov_extension(self, tmp_path: Path):
        assert _detect_format(tmp_path / "coverage.lcov") == "lcov"

    def test_unknown_extension_defaults_to_xml(self, tmp_path: Path):
        assert _detect_format(tmp_path / "coverage.dat") == "xml"

    def test_case_insensitive(self, tmp_path: Path):
        assert _detect_format(tmp_path / "Coverage.XML") == "xml"


# ---------------------------------------------------------------------------
# _parse_xml — coverage.py format
# ---------------------------------------------------------------------------


class TestParseXmlCoveragePy:
    def test_full_coverage(self, tmp_path: Path):
        f = write_coverage_py_xml(tmp_path / "cov.xml", 1.0)
        assert _parse_xml(f) == pytest.approx(100.0)

    def test_zero_coverage(self, tmp_path: Path):
        f = write_coverage_py_xml(tmp_path / "cov.xml", 0.0)
        assert _parse_xml(f) == pytest.approx(0.0)

    def test_partial_coverage(self, tmp_path: Path):
        f = write_coverage_py_xml(tmp_path / "cov.xml", 0.923)
        assert _parse_xml(f) == pytest.approx(92.3)

    def test_invalid_line_rate_raises(self, tmp_path: Path):
        f = tmp_path / "cov.xml"
        f.write_text('<coverage line-rate="not-a-number"/>', encoding="utf-8")
        with pytest.raises(_ParseError, match="Invalid line-rate"):
            _parse_xml(f)

    def test_corrupt_xml_raises(self, tmp_path: Path):
        f = tmp_path / "cov.xml"
        f.write_text("<<< not xml >>>", encoding="utf-8")
        with pytest.raises(_ParseError, match="XML parse error"):
            _parse_xml(f)


# ---------------------------------------------------------------------------
# _parse_xml — JaCoCo format
# ---------------------------------------------------------------------------


class TestParseXmlJaCoCo:
    def test_perfect_coverage(self, tmp_path: Path):
        f = write_jacoco_xml(tmp_path / "jacoco.xml", covered=100, missed=0)
        assert _parse_xml(f) == pytest.approx(100.0)

    def test_zero_coverage(self, tmp_path: Path):
        f = write_jacoco_xml(tmp_path / "jacoco.xml", covered=0, missed=100)
        assert _parse_xml(f) == pytest.approx(0.0)

    def test_partial_coverage(self, tmp_path: Path):
        f = write_jacoco_xml(tmp_path / "jacoco.xml", covered=75, missed=25)
        assert _parse_xml(f) == pytest.approx(75.0)

    def test_no_coverage_data_raises(self, tmp_path: Path):
        f = tmp_path / "empty.xml"
        f.write_text("<report name='x'/>", encoding="utf-8")
        with pytest.raises(_ParseError, match="No recognisable coverage data"):
            _parse_xml(f)

    def test_multiple_line_counters_aggregated(self, tmp_path: Path):
        """Multiple <counter type="LINE"> elements must be summed."""
        f = tmp_path / "multi.xml"
        f.write_text(
            textwrap.dedent("""\
                <?xml version="1.0"?>
                <report name="x">
                  <counter type="LINE" missed="10" covered="40"/>
                  <counter type="LINE" missed="10" covered="40"/>
                </report>
            """),
            encoding="utf-8",
        )
        # 80 covered / 100 total = 80 %
        assert _parse_xml(f) == pytest.approx(80.0)


# ---------------------------------------------------------------------------
# _parse_json
# ---------------------------------------------------------------------------


class TestParseJson:
    def test_full_coverage(self, tmp_path: Path):
        f = write_coverage_json(tmp_path / "cov.json", 100.0)
        assert _parse_json(f) == pytest.approx(100.0)

    def test_fractional_coverage(self, tmp_path: Path):
        f = write_coverage_json(tmp_path / "cov.json", 87.5)
        assert _parse_json(f) == pytest.approx(87.5)

    def test_missing_totals_key_raises(self, tmp_path: Path):
        f = tmp_path / "cov.json"
        f.write_text('{"meta": {}}', encoding="utf-8")
        with pytest.raises(_ParseError, match="percent_covered"):
            _parse_json(f)

    def test_corrupt_json_raises(self, tmp_path: Path):
        f = tmp_path / "cov.json"
        f.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(_ParseError, match="JSON parse error"):
            _parse_json(f)

    def test_invalid_percent_covered_type_raises(self, tmp_path: Path):
        f = tmp_path / "cov.json"
        f.write_text('{"totals": {"percent_covered": "not-a-float"}}', encoding="utf-8")
        with pytest.raises(_ParseError, match="Invalid percent_covered"):
            _parse_json(f)


# ---------------------------------------------------------------------------
# _parse_lcov
# ---------------------------------------------------------------------------


class TestParseLcov:
    def test_full_coverage(self, tmp_path: Path):
        f = write_lcov(tmp_path / "lcov.info", lines_found=100, lines_hit=100)
        assert _parse_lcov(f) == pytest.approx(100.0)

    def test_zero_coverage(self, tmp_path: Path):
        f = write_lcov(tmp_path / "lcov.info", lines_found=200, lines_hit=0)
        assert _parse_lcov(f) == pytest.approx(0.0)

    def test_partial_coverage(self, tmp_path: Path):
        f = write_lcov(tmp_path / "lcov.info", lines_found=200, lines_hit=150)
        assert _parse_lcov(f) == pytest.approx(75.0)

    def test_multiple_sections_aggregated(self, tmp_path: Path):
        """LF/LH entries across multiple SF: sections are summed."""
        f = tmp_path / "multi.info"
        f.write_text(
            textwrap.dedent("""\
                TN:
                SF:src/a.py
                LF:100
                LH:80
                end_of_record
                TN:
                SF:src/b.py
                LF:50
                LH:50
                end_of_record
            """),
            encoding="utf-8",
        )
        # (80 + 50) / (100 + 50) = 130/150 ≈ 86.67 %
        assert _parse_lcov(f) == pytest.approx(130 / 150 * 100)

    def test_no_lf_entries_raises(self, tmp_path: Path):
        f = tmp_path / "empty.info"
        f.write_text("TN:\nSF:src/x.py\nend_of_record\n", encoding="utf-8")
        with pytest.raises(_ParseError, match="No LF:"):
            _parse_lcov(f)


# ---------------------------------------------------------------------------
# CoverageGate — missing report
# ---------------------------------------------------------------------------


class TestMissingReport:
    def test_missing_file_produces_violation(self, tmp_path: Path):
        cfg = CoverageGateConfig(coverage_file="nonexistent.xml")
        result = CoverageGate(cfg).run(tmp_path)
        assert len(result.violations) == 1
        assert result.violations[0].kind == "missing_report"

    def test_missing_file_fails_gate(self, tmp_path: Path):
        result = CoverageGate().run(tmp_path)
        assert not result.passed

    def test_missing_file_fail_on_error_false_passes(self, tmp_path: Path):
        cfg = CoverageGateConfig(fail_on_error=False)
        result = CoverageGate(cfg).run(tmp_path)
        assert result.passed
        assert result.violations[0].severity == "warning"

    def test_missing_file_violation_summary_contains_path(self, tmp_path: Path):
        cfg = CoverageGateConfig(coverage_file="missing.xml")
        result = CoverageGate(cfg).run(tmp_path)
        summary = result.violations[0].summary()
        assert "missing_report" in summary

    def test_absolute_coverage_file_path(self, tmp_path: Path):
        """An absolute path that doesn't exist should still produce missing_report."""
        cfg = CoverageGateConfig(coverage_file=str(tmp_path / "abs_missing.xml"))
        result = CoverageGate(cfg).run(tmp_path)
        assert result.violations[0].kind == "missing_report"


# ---------------------------------------------------------------------------
# CoverageGate — parse errors
# ---------------------------------------------------------------------------


class TestParseErrors:
    def test_corrupt_xml_produces_parse_error_violation(self, tmp_path: Path):
        cov = tmp_path / "coverage.xml"
        cov.write_text("<<< corrupt >>>", encoding="utf-8")
        result = CoverageGate().run(tmp_path)
        assert result.violations[0].kind == "parse_error"
        assert not result.passed

    def test_parse_error_fail_on_error_false_passes(self, tmp_path: Path):
        cov = tmp_path / "coverage.xml"
        cov.write_text("<<< corrupt >>>", encoding="utf-8")
        cfg = CoverageGateConfig(fail_on_error=False)
        result = CoverageGate(cfg).run(tmp_path)
        assert result.passed
        assert result.violations[0].severity == "warning"


# ---------------------------------------------------------------------------
# CoverageGate — threshold enforcement (XML / coverage.py)
# ---------------------------------------------------------------------------


class TestThresholdEnforcement:
    def test_coverage_above_threshold_passes(self, tmp_path: Path):
        write_coverage_py_xml(tmp_path / "coverage.xml", line_rate=0.95)
        cfg = CoverageGateConfig(threshold=90.0)
        result = CoverageGate(cfg).run(tmp_path)
        assert result.passed
        assert result.violations == []

    def test_coverage_exactly_at_threshold_passes(self, tmp_path: Path):
        write_coverage_py_xml(tmp_path / "coverage.xml", line_rate=0.90)
        cfg = CoverageGateConfig(threshold=90.0)
        result = CoverageGate(cfg).run(tmp_path)
        assert result.passed
        assert result.violations == []

    def test_coverage_below_threshold_fails(self, tmp_path: Path):
        write_coverage_py_xml(tmp_path / "coverage.xml", line_rate=0.8999)
        cfg = CoverageGateConfig(threshold=90.0)
        result = CoverageGate(cfg).run(tmp_path)
        assert not result.passed
        assert result.violations[0].kind == "below_threshold"

    def test_coverage_below_threshold_violation_contains_values(self, tmp_path: Path):
        write_coverage_py_xml(tmp_path / "coverage.xml", line_rate=0.75)
        cfg = CoverageGateConfig(threshold=90.0)
        result = CoverageGate(cfg).run(tmp_path)
        v = result.violations[0]
        assert "75." in v.message
        assert "90." in v.message

    def test_fail_on_error_false_below_threshold_passes(self, tmp_path: Path):
        write_coverage_py_xml(tmp_path / "coverage.xml", line_rate=0.50)
        cfg = CoverageGateConfig(threshold=90.0, fail_on_error=False)
        result = CoverageGate(cfg).run(tmp_path)
        assert result.passed
        assert result.violations[0].severity == "warning"

    def test_custom_threshold_respected(self, tmp_path: Path):
        write_coverage_py_xml(tmp_path / "coverage.xml", line_rate=0.70)
        cfg = CoverageGateConfig(threshold=65.0)
        result = CoverageGate(cfg).run(tmp_path)
        assert result.passed, "70 % should pass a 65 % threshold"

    def test_zero_threshold_always_passes(self, tmp_path: Path):
        write_coverage_py_xml(tmp_path / "coverage.xml", line_rate=0.0)
        cfg = CoverageGateConfig(threshold=0.0)
        result = CoverageGate(cfg).run(tmp_path)
        assert result.passed

    def test_hundred_percent_threshold_exact_match_passes(self, tmp_path: Path):
        write_coverage_py_xml(tmp_path / "coverage.xml", line_rate=1.0)
        cfg = CoverageGateConfig(threshold=100.0)
        result = CoverageGate(cfg).run(tmp_path)
        assert result.passed


# ---------------------------------------------------------------------------
# CoverageGate — JSON format
# ---------------------------------------------------------------------------


class TestJsonFormat:
    def test_above_threshold_json(self, tmp_path: Path):
        write_coverage_json(tmp_path / "cov.json", 92.0)
        cfg = CoverageGateConfig(threshold=90.0, coverage_file="cov.json")
        result = CoverageGate(cfg).run(tmp_path)
        assert result.passed
        assert result.report_format == "json"

    def test_below_threshold_json_fails(self, tmp_path: Path):
        write_coverage_json(tmp_path / "cov.json", 88.0)
        cfg = CoverageGateConfig(threshold=90.0, coverage_file="cov.json")
        result = CoverageGate(cfg).run(tmp_path)
        assert not result.passed

    def test_explicit_json_format_flag(self, tmp_path: Path):
        """--format json should parse a file regardless of its extension."""
        write_coverage_json(tmp_path / "report.dat", 95.0)
        cfg = CoverageGateConfig(
            threshold=90.0,
            coverage_file="report.dat",
            report_format="json",
        )
        result = CoverageGate(cfg).run(tmp_path)
        assert result.passed
        assert result.report_format == "json"


# ---------------------------------------------------------------------------
# CoverageGate — lcov format
# ---------------------------------------------------------------------------


class TestLcovFormat:
    def test_above_threshold_lcov(self, tmp_path: Path):
        write_lcov(tmp_path / "lcov.info", 200, 190)
        cfg = CoverageGateConfig(threshold=90.0, coverage_file="lcov.info")
        result = CoverageGate(cfg).run(tmp_path)
        assert result.passed
        assert result.report_format == "lcov"

    def test_below_threshold_lcov_fails(self, tmp_path: Path):
        write_lcov(tmp_path / "lcov.info", 200, 160)  # 80 %
        cfg = CoverageGateConfig(threshold=90.0, coverage_file="lcov.info")
        result = CoverageGate(cfg).run(tmp_path)
        assert not result.passed

    def test_explicit_lcov_format_flag(self, tmp_path: Path):
        write_lcov(tmp_path / "coverage.dat", 100, 95)
        cfg = CoverageGateConfig(
            threshold=90.0,
            coverage_file="coverage.dat",
            report_format="lcov",
        )
        result = CoverageGate(cfg).run(tmp_path)
        assert result.passed
        assert result.report_format == "lcov"


# ---------------------------------------------------------------------------
# CoverageGate — JaCoCo XML format
# ---------------------------------------------------------------------------


class TestJaCoCoXmlFormat:
    def test_above_threshold_jacoco(self, tmp_path: Path):
        write_jacoco_xml(tmp_path / "coverage.xml", covered=92, missed=8)
        cfg = CoverageGateConfig(threshold=90.0)
        result = CoverageGate(cfg).run(tmp_path)
        assert result.passed

    def test_below_threshold_jacoco_fails(self, tmp_path: Path):
        write_jacoco_xml(tmp_path / "coverage.xml", covered=80, missed=20)
        cfg = CoverageGateConfig(threshold=90.0)
        result = CoverageGate(cfg).run(tmp_path)
        assert not result.passed


# ---------------------------------------------------------------------------
# CoverageGate — GateResult attributes
# ---------------------------------------------------------------------------


class TestGateResultAttributes:
    def test_actual_coverage_set_on_pass(self, tmp_path: Path):
        write_coverage_py_xml(tmp_path / "coverage.xml", line_rate=0.95)
        result = CoverageGate().run(tmp_path)
        assert result.actual_coverage == pytest.approx(95.0)

    def test_actual_coverage_set_on_fail(self, tmp_path: Path):
        write_coverage_py_xml(tmp_path / "coverage.xml", line_rate=0.80)
        result = CoverageGate().run(tmp_path)
        assert result.actual_coverage == pytest.approx(80.0)

    def test_actual_coverage_none_on_parse_error(self, tmp_path: Path):
        (tmp_path / "coverage.xml").write_text("bad xml", encoding="utf-8")
        result = CoverageGate().run(tmp_path)
        assert result.actual_coverage is None

    def test_threshold_in_result(self, tmp_path: Path):
        write_coverage_py_xml(tmp_path / "coverage.xml", line_rate=0.95)
        cfg = CoverageGateConfig(threshold=85.0)
        result = CoverageGate(cfg).run(tmp_path)
        assert result.threshold == 85.0

    def test_stats_delta_positive_on_pass(self, tmp_path: Path):
        write_coverage_py_xml(tmp_path / "coverage.xml", line_rate=0.95)
        cfg = CoverageGateConfig(threshold=90.0)
        result = CoverageGate(cfg).run(tmp_path)
        assert result.stats["delta"] == pytest.approx(5.0, abs=0.1)

    def test_stats_delta_negative_on_fail(self, tmp_path: Path):
        write_coverage_py_xml(tmp_path / "coverage.xml", line_rate=0.80)
        cfg = CoverageGateConfig(threshold=90.0)
        result = CoverageGate(cfg).run(tmp_path)
        assert result.stats["delta"] == pytest.approx(-10.0, abs=0.1)

    def test_coverage_file_path_in_result(self, tmp_path: Path):
        write_coverage_py_xml(tmp_path / "coverage.xml", line_rate=0.95)
        result = CoverageGate().run(tmp_path)
        assert result.coverage_file == (tmp_path / "coverage.xml").resolve()

    def test_report_format_in_result(self, tmp_path: Path):
        write_coverage_py_xml(tmp_path / "coverage.xml", line_rate=0.95)
        result = CoverageGate().run(tmp_path)
        assert result.report_format == "xml"

    def test_errors_helper_returns_error_severity(self, tmp_path: Path):
        write_coverage_py_xml(tmp_path / "coverage.xml", line_rate=0.70)
        cfg = CoverageGateConfig(threshold=90.0, fail_on_error=True)
        result = CoverageGate(cfg).run(tmp_path)
        assert len(result.errors()) == 1
        assert all(v.severity == "error" for v in result.errors())

    def test_warnings_helper_returns_warning_severity(self, tmp_path: Path):
        write_coverage_py_xml(tmp_path / "coverage.xml", line_rate=0.70)
        cfg = CoverageGateConfig(threshold=90.0, fail_on_error=False)
        result = CoverageGate(cfg).run(tmp_path)
        assert len(result.warnings()) == 1
        assert all(v.severity == "warning" for v in result.warnings())


# ---------------------------------------------------------------------------
# CoverageGate — default configuration
# ---------------------------------------------------------------------------


class TestDefaultConfig:
    def test_default_threshold_is_90(self):
        cfg = CoverageGateConfig()
        assert cfg.threshold == 90.0

    def test_default_coverage_file_is_xml(self):
        cfg = CoverageGateConfig()
        assert cfg.coverage_file == "coverage.xml"

    def test_default_format_is_auto(self):
        cfg = CoverageGateConfig()
        assert cfg.report_format == "auto"

    def test_default_fail_on_error_is_true(self):
        cfg = CoverageGateConfig()
        assert cfg.fail_on_error is True

    def test_gate_uses_default_config_when_none_passed(self, tmp_path: Path):
        """CoverageGate() with no args should use a 90 % threshold."""
        write_coverage_py_xml(tmp_path / "coverage.xml", line_rate=0.91)
        result = CoverageGate().run(tmp_path)
        assert result.passed
        assert result.threshold == 90.0


# ---------------------------------------------------------------------------
# Integration: end-to-end scenarios
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_healthy_project_passes(self, tmp_path: Path):
        """95 % coverage against default 90 % threshold should pass cleanly."""
        write_coverage_py_xml(tmp_path / "coverage.xml", line_rate=0.95)
        result = CoverageGate().run(tmp_path)
        assert result.passed
        assert result.violations == []
        assert result.actual_coverage == pytest.approx(95.0, abs=0.01)

    def test_low_coverage_project_fails(self, tmp_path: Path):
        """60 % coverage against default 90 % threshold must fail."""
        write_coverage_py_xml(tmp_path / "coverage.xml", line_rate=0.60)
        result = CoverageGate().run(tmp_path)
        assert not result.passed
        assert len(result.violations) == 1
        assert result.violations[0].kind == "below_threshold"
        assert "60." in result.violations[0].message
        assert "90." in result.violations[0].message

    def test_violation_summary_contains_kind(self, tmp_path: Path):
        write_coverage_py_xml(tmp_path / "coverage.xml", line_rate=0.80)
        result = CoverageGate().run(tmp_path)
        summary = result.violations[0].summary()
        assert "below_threshold" in summary

    def test_no_report_then_report_added(self, tmp_path: Path):
        """First run fails (missing report); second run after writing passes."""
        cfg = CoverageGateConfig(threshold=80.0)

        result_before = CoverageGate(cfg).run(tmp_path)
        assert not result_before.passed
        assert result_before.violations[0].kind == "missing_report"

        write_coverage_py_xml(tmp_path / "coverage.xml", line_rate=0.85)
        result_after = CoverageGate(cfg).run(tmp_path)
        assert result_after.passed
        assert result_after.violations == []

    def test_lcov_and_json_same_coverage_same_verdict(self, tmp_path: Path):
        """Both lcov and JSON parsers should agree on an 88 % coverage value."""
        write_lcov(tmp_path / "lcov.info", lines_found=100, lines_hit=88)
        write_coverage_json(tmp_path / "cov.json", percent_covered=88.0)

        cfg_lcov = CoverageGateConfig(
            threshold=90.0, coverage_file="lcov.info"
        )
        cfg_json = CoverageGateConfig(
            threshold=90.0, coverage_file="cov.json"
        )

        result_lcov = CoverageGate(cfg_lcov).run(tmp_path)
        result_json = CoverageGate(cfg_json).run(tmp_path)

        assert result_lcov.passed == result_json.passed  # both fail
        assert not result_lcov.passed
