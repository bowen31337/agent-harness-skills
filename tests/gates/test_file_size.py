"""
tests/gates/test_file_size.py
================================
Unit tests for :mod:`harness_skills.gates.file_size`.

Covers:
- Violation / GateResult dataclasses
- _matches_any helper
- _collect_files with include/exclude patterns
- _count_lines edge cases (empty, no trailing newline, binary error)
- FileSizeGate.run: hard limit, soft limit, report_only, fail_on_error
- CLI parser defaults and custom values
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness_skills.gates.file_size import (
    FileSizeGate,
    GateResult,
    Violation,
    _collect_files,
    _count_lines,
    _matches_any,
)
from harness_skills.models.gate_configs import FileSizeGateConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_file(path: Path, content: str) -> Path:
    """Write *content* to *path*, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_lines(n: int) -> str:
    """Return a string with exactly *n* newline-terminated lines."""
    return "".join(f"line {i}\n" for i in range(n))


# ---------------------------------------------------------------------------
# Violation dataclass
# ---------------------------------------------------------------------------


class TestViolation:
    def test_summary_error_format(self) -> None:
        v = Violation(
            kind="exceeds_hard_limit",
            severity="error",
            message="file too big",
            file_path=Path("src/big.py"),
            line_count=600,
            limit=500,
        )
        s = v.summary()
        assert "ERROR" in s
        assert "exceeds_hard_limit" in s
        assert "src/big.py" in s
        assert "600" in s
        assert "500" in s

    def test_summary_warning_format(self) -> None:
        v = Violation(
            kind="exceeds_soft_limit",
            severity="warning",
            message="file growing",
            file_path=Path("src/medium.py"),
            line_count=350,
            limit=300,
        )
        s = v.summary()
        assert "WARNING" in s
        assert "exceeds_soft_limit" in s


# ---------------------------------------------------------------------------
# GateResult dataclass
# ---------------------------------------------------------------------------


class TestGateResult:
    def test_errors_and_warnings_filtering(self) -> None:
        violations = [
            Violation("exceeds_hard_limit", "error", "msg", Path("a.py"), 600, 500),
            Violation("exceeds_soft_limit", "warning", "msg", Path("b.py"), 350, 300),
            Violation("exceeds_hard_limit", "error", "msg", Path("c.py"), 700, 500),
        ]
        result = GateResult(passed=False, violations=violations)
        assert len(result.errors()) == 2
        assert len(result.warnings()) == 1

    def test_empty_violations(self) -> None:
        result = GateResult(passed=True)
        assert result.errors() == []
        assert result.warnings() == []


# ---------------------------------------------------------------------------
# _matches_any
# ---------------------------------------------------------------------------


class TestMatchesAny:
    def test_full_path_match(self) -> None:
        assert _matches_any("node_modules/foo.js", ["node_modules/*"])

    def test_basename_match(self) -> None:
        assert _matches_any("deep/dir/foo.min.js", ["*.min.js"])

    def test_no_match(self) -> None:
        assert not _matches_any("src/app.py", ["*.js", "*.ts"])

    def test_empty_patterns(self) -> None:
        assert not _matches_any("anything.py", [])

    def test_exact_basename(self) -> None:
        assert _matches_any("some/path/file.generated.ts", ["*.generated.*"])

    def test_basename_only_match(self) -> None:
        # "foo.py" does not match full path "src/foo.py" but matches basename "foo.py"
        assert _matches_any("src/foo.py", ["foo.py"])


# ---------------------------------------------------------------------------
# _collect_files
# ---------------------------------------------------------------------------


class TestCollectFiles:
    def test_include_patterns(self, tmp_path: Path) -> None:
        write_file(tmp_path / "src" / "app.py", "print('hi')\n")
        write_file(tmp_path / "src" / "style.css", "body {}\n")
        files = _collect_files(tmp_path, ["**/*.py"], [])
        assert len(files) == 1
        assert files[0].name == "app.py"

    def test_exclude_patterns(self, tmp_path: Path) -> None:
        write_file(tmp_path / "src" / "app.py", "x\n")
        write_file(tmp_path / "venv" / "lib.py", "x\n")
        files = _collect_files(tmp_path, ["**/*.py"], ["venv/*"])
        paths_str = [str(f.relative_to(tmp_path)) for f in files]
        assert all("venv" not in p for p in paths_str)

    def test_no_matching_files(self, tmp_path: Path) -> None:
        write_file(tmp_path / "readme.txt", "hello\n")
        files = _collect_files(tmp_path, ["**/*.py"], [])
        assert files == []

    def test_directories_are_excluded(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        # src/ is a directory, not a file — should not appear
        files = _collect_files(tmp_path, ["**/*"], [])
        for f in files:
            assert f.is_file()

    def test_sorted_output(self, tmp_path: Path) -> None:
        write_file(tmp_path / "z.py", "x\n")
        write_file(tmp_path / "a.py", "x\n")
        write_file(tmp_path / "m.py", "x\n")
        files = _collect_files(tmp_path, ["**/*.py"], [])
        names = [f.name for f in files]
        assert names == sorted(names)


# ---------------------------------------------------------------------------
# _count_lines
# ---------------------------------------------------------------------------


class TestCountLines:
    def test_empty_file_returns_zero(self, tmp_path: Path) -> None:
        p = write_file(tmp_path / "empty.py", "")
        assert _count_lines(p) == 0

    def test_single_line_with_newline(self, tmp_path: Path) -> None:
        p = write_file(tmp_path / "one.py", "line1\n")
        assert _count_lines(p) == 1

    def test_single_line_no_newline(self, tmp_path: Path) -> None:
        p = write_file(tmp_path / "one.py", "line1")
        assert _count_lines(p) == 1

    def test_multiple_lines(self, tmp_path: Path) -> None:
        p = write_file(tmp_path / "multi.py", "a\nb\nc\n")
        assert _count_lines(p) == 3

    def test_multiple_lines_no_trailing_newline(self, tmp_path: Path) -> None:
        p = write_file(tmp_path / "multi.py", "a\nb\nc")
        assert _count_lines(p) == 3

    def test_nonexistent_file_returns_zero(self, tmp_path: Path) -> None:
        p = tmp_path / "nope.py"
        assert _count_lines(p) == 0

    def test_binary_content(self, tmp_path: Path) -> None:
        p = tmp_path / "bin.dat"
        p.write_bytes(b"\x00\n\x01\n\x02\n")
        assert _count_lines(p) == 3


# ---------------------------------------------------------------------------
# FileSizeGate — hard limit violations
# ---------------------------------------------------------------------------


class TestHardLimit:
    def test_file_over_hard_limit_fails(self, tmp_path: Path) -> None:
        write_file(tmp_path / "big.py", make_lines(501))
        cfg = FileSizeGateConfig(
            max_lines=500, warn_lines=300,
            include_patterns=["**/*.py"], exclude_patterns=[],
        )
        result = FileSizeGate(cfg).run(tmp_path)
        assert result.passed is False
        assert len(result.errors()) == 1
        v = result.violations[0]
        assert v.kind == "exceeds_hard_limit"
        assert v.severity == "error"
        assert v.line_count == 501
        assert v.limit == 500

    def test_file_exactly_at_hard_limit_passes(self, tmp_path: Path) -> None:
        write_file(tmp_path / "exact.py", make_lines(500))
        cfg = FileSizeGateConfig(
            max_lines=500, warn_lines=300,
            include_patterns=["**/*.py"], exclude_patterns=[],
        )
        result = FileSizeGate(cfg).run(tmp_path)
        assert result.passed is True
        assert len(result.errors()) == 0

    def test_violation_message_mentions_overrun(self, tmp_path: Path) -> None:
        write_file(tmp_path / "big.py", make_lines(520))
        cfg = FileSizeGateConfig(
            max_lines=500, warn_lines=0,
            include_patterns=["**/*.py"], exclude_patterns=[],
        )
        result = FileSizeGate(cfg).run(tmp_path)
        v = result.violations[0]
        assert "20 over" in v.message


# ---------------------------------------------------------------------------
# FileSizeGate — soft limit warnings
# ---------------------------------------------------------------------------


class TestSoftLimit:
    def test_file_over_soft_limit_produces_warning(self, tmp_path: Path) -> None:
        write_file(tmp_path / "medium.py", make_lines(350))
        cfg = FileSizeGateConfig(
            max_lines=500, warn_lines=300,
            include_patterns=["**/*.py"], exclude_patterns=[],
        )
        result = FileSizeGate(cfg).run(tmp_path)
        assert result.passed is True  # soft limit does not block
        assert len(result.warnings()) == 1
        v = result.warnings()[0]
        assert v.kind == "exceeds_soft_limit"
        assert v.severity == "warning"
        assert v.limit == 300

    def test_soft_limit_disabled_when_zero(self, tmp_path: Path) -> None:
        write_file(tmp_path / "medium.py", make_lines(350))
        cfg = FileSizeGateConfig(
            max_lines=500, warn_lines=0,
            include_patterns=["**/*.py"], exclude_patterns=[],
        )
        result = FileSizeGate(cfg).run(tmp_path)
        assert result.violations == []

    def test_soft_limit_message_mentions_headroom(self, tmp_path: Path) -> None:
        write_file(tmp_path / "medium.py", make_lines(400))
        cfg = FileSizeGateConfig(
            max_lines=500, warn_lines=300,
            include_patterns=["**/*.py"], exclude_patterns=[],
        )
        result = FileSizeGate(cfg).run(tmp_path)
        v = result.warnings()[0]
        # headroom = 500 - 400 = 100
        assert "100 lines before" in v.message


# ---------------------------------------------------------------------------
# FileSizeGate — report_only mode
# ---------------------------------------------------------------------------


class TestReportOnly:
    def test_report_only_downgrades_errors_to_warnings(self, tmp_path: Path) -> None:
        write_file(tmp_path / "big.py", make_lines(600))
        cfg = FileSizeGateConfig(
            max_lines=500, warn_lines=300, report_only=True,
            include_patterns=["**/*.py"], exclude_patterns=[],
        )
        result = FileSizeGate(cfg).run(tmp_path)
        # report_only: errors become warnings, so no error-severity violations
        assert all(v.severity == "warning" for v in result.violations)

    def test_report_only_gate_passes(self, tmp_path: Path) -> None:
        write_file(tmp_path / "big.py", make_lines(600))
        cfg = FileSizeGateConfig(
            max_lines=500, warn_lines=300, report_only=True,
            include_patterns=["**/*.py"], exclude_patterns=[],
        )
        result = FileSizeGate(cfg).run(tmp_path)
        assert result.passed is True


# ---------------------------------------------------------------------------
# FileSizeGate — fail_on_error=False
# ---------------------------------------------------------------------------


class TestFailOnErrorFalse:
    def test_gate_passes_with_errors_when_fail_on_error_false(self, tmp_path: Path) -> None:
        write_file(tmp_path / "big.py", make_lines(600))
        cfg = FileSizeGateConfig(
            max_lines=500, warn_lines=300, fail_on_error=False,
            include_patterns=["**/*.py"], exclude_patterns=[],
        )
        result = FileSizeGate(cfg).run(tmp_path)
        assert result.passed is True
        # Violations are still error-severity (unlike report_only)
        assert len(result.errors()) == 1


# ---------------------------------------------------------------------------
# FileSizeGate — sorting and stats
# ---------------------------------------------------------------------------


class TestSortingAndStats:
    def test_violations_sorted_errors_first_then_by_line_count_desc(
        self, tmp_path: Path
    ) -> None:
        write_file(tmp_path / "huge.py", make_lines(700))
        write_file(tmp_path / "big.py", make_lines(600))
        write_file(tmp_path / "medium.py", make_lines(350))
        cfg = FileSizeGateConfig(
            max_lines=500, warn_lines=300,
            include_patterns=["**/*.py"], exclude_patterns=[],
        )
        result = FileSizeGate(cfg).run(tmp_path)
        # 2 errors (huge, big) + 1 warning (medium)
        assert len(result.violations) == 3
        # Errors come first
        assert result.violations[0].severity == "error"
        assert result.violations[1].severity == "error"
        assert result.violations[2].severity == "warning"
        # Among errors, highest line count first
        assert result.violations[0].line_count >= result.violations[1].line_count

    def test_stats_populated(self, tmp_path: Path) -> None:
        write_file(tmp_path / "a.py", make_lines(600))
        write_file(tmp_path / "b.py", make_lines(10))
        cfg = FileSizeGateConfig(
            max_lines=500, warn_lines=300,
            include_patterns=["**/*.py"], exclude_patterns=[],
        )
        result = FileSizeGate(cfg).run(tmp_path)
        assert result.files_scanned == 2
        assert result.stats["files_scanned"] == 2
        assert result.stats["errors"] == 1
        assert result.stats["warnings"] == 0
        assert result.stats["largest_file_lines"] == 600

    def test_gate_result_limits_stored(self, tmp_path: Path) -> None:
        cfg = FileSizeGateConfig(
            max_lines=400, warn_lines=200,
            include_patterns=["**/*.py"], exclude_patterns=[],
        )
        write_file(tmp_path / "x.py", "pass\n")
        result = FileSizeGate(cfg).run(tmp_path)
        assert result.max_lines == 400
        assert result.warn_lines == 200


# ---------------------------------------------------------------------------
# FileSizeGate — no files
# ---------------------------------------------------------------------------


class TestNoFiles:
    def test_empty_directory_passes(self, tmp_path: Path) -> None:
        cfg = FileSizeGateConfig(
            include_patterns=["**/*.py"], exclude_patterns=[],
        )
        result = FileSizeGate(cfg).run(tmp_path)
        assert result.passed is True
        assert result.violations == []
        assert result.files_scanned == 0


# ---------------------------------------------------------------------------
# FileSizeGate — default config
# ---------------------------------------------------------------------------


class TestDefaultConfig:
    def test_default_config_used_when_none(self) -> None:
        gate = FileSizeGate()
        assert gate.config.max_lines == 500
        assert gate.config.warn_lines == 300

    def test_custom_config_used(self) -> None:
        cfg = FileSizeGateConfig(max_lines=100, warn_lines=50)
        gate = FileSizeGate(cfg)
        assert gate.config.max_lines == 100


# ---------------------------------------------------------------------------
# _build_parser — CLI parser tests
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_parser_defaults(self) -> None:
        from harness_skills.gates.file_size import _build_parser

        parser = _build_parser()
        args = parser.parse_args([])
        assert args.root == "."
        assert args.max_lines == 500
        assert args.warn_lines == 300
        assert args.report_only is False
        assert args.fail_on_error is True
        assert args.include_patterns is None
        assert args.exclude_patterns is None
        assert args.quiet is False

    def test_parser_custom_values(self) -> None:
        from harness_skills.gates.file_size import _build_parser

        parser = _build_parser()
        args = parser.parse_args([
            "--root", "/tmp/repo",
            "--max-lines", "400",
            "--warn-lines", "200",
            "--report-only",
            "--no-fail-on-error",
            "--include", "**/*.py",
            "--include", "**/*.js",
            "--exclude", "vendor/*",
            "--quiet",
        ])
        assert args.root == "/tmp/repo"
        assert args.max_lines == 400
        assert args.warn_lines == 200
        assert args.report_only is True
        assert args.fail_on_error is False
        assert args.include_patterns == ["**/*.py", "**/*.js"]
        assert args.exclude_patterns == ["vendor/*"]
        assert args.quiet is True


# ---------------------------------------------------------------------------
# Integration — resolve relative root
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_repo_root_is_resolved(self, tmp_path: Path) -> None:
        write_file(tmp_path / "src" / "app.py", make_lines(10))
        import os
        original = Path.cwd()
        os.chdir(tmp_path.parent)
        try:
            cfg = FileSizeGateConfig(
                max_lines=500, warn_lines=300,
                include_patterns=["**/*.py"], exclude_patterns=[],
            )
            result = FileSizeGate(cfg).run(Path(tmp_path.name))
            assert result.files_scanned == 1
        finally:
            os.chdir(original)

    def test_mixed_hard_and_soft_violations(self, tmp_path: Path) -> None:
        write_file(tmp_path / "huge.py", make_lines(600))
        write_file(tmp_path / "medium.py", make_lines(350))
        write_file(tmp_path / "small.py", make_lines(10))
        cfg = FileSizeGateConfig(
            max_lines=500, warn_lines=300,
            include_patterns=["**/*.py"], exclude_patterns=[],
        )
        result = FileSizeGate(cfg).run(tmp_path)
        assert result.passed is False
        assert len(result.errors()) == 1
        assert len(result.warnings()) == 1
        assert result.files_scanned == 3

    def test_exclude_filters_work_in_gate(self, tmp_path: Path) -> None:
        write_file(tmp_path / "src" / "app.py", make_lines(600))
        write_file(tmp_path / "vendor" / "lib.py", make_lines(600))
        cfg = FileSizeGateConfig(
            max_lines=500, warn_lines=300,
            include_patterns=["**/*.py"], exclude_patterns=["vendor/*"],
        )
        result = FileSizeGate(cfg).run(tmp_path)
        # Only src/app.py should be scanned
        assert result.files_scanned == 1
        assert len(result.errors()) == 1

    def test_largest_file_tracked_in_stats(self, tmp_path: Path) -> None:
        write_file(tmp_path / "small.py", make_lines(10))
        write_file(tmp_path / "big.py", make_lines(200))
        cfg = FileSizeGateConfig(
            max_lines=500, warn_lines=300,
            include_patterns=["**/*.py"], exclude_patterns=[],
        )
        result = FileSizeGate(cfg).run(tmp_path)
        assert result.stats["largest_file_lines"] == 200
        assert "big.py" in result.stats["largest_file"]
