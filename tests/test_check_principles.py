"""Unit tests for scripts/check_principles.py — golden principles scanner."""

from __future__ import annotations

from pathlib import Path
import sys
import textwrap

import pytest

# Allow importing directly from scripts/ without installing a package
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from check_principles import (  # noqa: E402
    Principle,
    ScanResult,
    Violation,
    _generic_keyword_check,
    load_principles,
    scan,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _write_principles(tmp_path: Path, content: str) -> Path:
    """Write a principles YAML file under tmp_path/.claude/ and return the path."""
    p = tmp_path / ".claude" / "principles.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def _make_principle(
    pid: str = "P001",
    category: str = "testing",
    severity: str = "blocking",
    applies_to: list[str] | None = None,
    rule: str = "All tests must have assertions",
) -> Principle:
    return Principle(
        id=pid,
        category=category,
        severity=severity,  # type: ignore[arg-type]
        applies_to=applies_to or ["check-code", "review-pr"],
        rule=rule,
    )


# ── load_principles ───────────────────────────────────────────────────────────


class TestLoadPrinciples:
    def test_loads_valid_file(self, tmp_path: Path) -> None:
        p = _write_principles(
            tmp_path,
            """
            version: "1.0"
            principles:
              - id: "P001"
                category: "testing"
                severity: "blocking"
                applies_to: ["check-code"]
                rule: "Every function must have a unit test"
            """,
        )
        principles = load_principles(p)
        assert len(principles) == 1
        assert principles[0].id == "P001"
        assert principles[0].severity == "blocking"

    def test_empty_principles_list_returns_empty(self, tmp_path: Path) -> None:
        p = _write_principles(tmp_path, 'version: "1.0"\nprinciples: []\n')
        assert load_principles(p) == []

    def test_missing_file_exits_with_code_2(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent.yaml"
        with pytest.raises(SystemExit) as exc_info:
            load_principles(missing)
        assert exc_info.value.code == 2

    def test_default_applies_to_when_field_absent(self, tmp_path: Path) -> None:
        p = _write_principles(
            tmp_path,
            """
            version: "1.0"
            principles:
              - id: "P001"
                category: "style"
                severity: "suggestion"
                rule: "Use snake_case for variable names"
            """,
        )
        principles = load_principles(p)
        assert set(principles[0].applies_to) == {"review-pr", "check-code"}

    def test_rule_is_stripped_of_whitespace(self, tmp_path: Path) -> None:
        p = _write_principles(
            tmp_path,
            """
            version: "1.0"
            principles:
              - id: "P001"
                category: "style"
                severity: "suggestion"
                rule: "  leading and trailing spaces  "
            """,
        )
        principles = load_principles(p)
        assert principles[0].rule == "leading and trailing spaces"

    def test_multiple_principles_are_ordered(self, tmp_path: Path) -> None:
        p = _write_principles(
            tmp_path,
            """
            version: "1.0"
            principles:
              - id: "P001"
                category: "arch"
                severity: "blocking"
                applies_to: ["check-code"]
                rule: "Rule one"
              - id: "P002"
                category: "style"
                severity: "suggestion"
                applies_to: ["review-pr"]
                rule: "Rule two"
            """,
        )
        principles = load_principles(p)
        assert len(principles) == 2
        assert principles[0].id == "P001"
        assert principles[1].id == "P002"

    def test_principles_loaded_count_matches(self, tmp_path: Path) -> None:
        lines = "\n".join(
            f"  - id: 'P{i:03d}'\n    category: 'cat'\n    severity: 'blocking'\n"
            f"    applies_to: ['check-code']\n    rule: 'Rule {i}'"
            for i in range(1, 6)
        )
        p = _write_principles(tmp_path, f'version: "1.0"\nprinciples:\n{lines}\n')
        assert len(load_principles(p)) == 5


# ── ScanResult properties ─────────────────────────────────────────────────────


class TestScanResult:
    def test_passed_when_no_violations(self) -> None:
        assert ScanResult().passed is True

    def test_failed_when_blocking_violation_present(self) -> None:
        principle = _make_principle(severity="blocking")
        v = Violation(principle=principle, message="violation")
        result = ScanResult(violations=[v])
        assert result.passed is False

    def test_passed_with_only_suggestion_violations(self) -> None:
        principle = _make_principle(severity="suggestion")
        v = Violation(principle=principle, message="suggestion")
        result = ScanResult(violations=[v])
        assert result.passed is True

    def test_blocking_and_suggestion_segregation(self) -> None:
        bp = _make_principle("P001", severity="blocking")
        sp = _make_principle("P002", severity="suggestion")
        result = ScanResult(violations=[
            Violation(principle=bp, message="blocking"),
            Violation(principle=sp, message="suggestion"),
        ])
        assert len(result.blocking_violations) == 1
        assert len(result.suggestion_violations) == 1

    def test_multiple_blocking_violations(self) -> None:
        p = _make_principle(severity="blocking")
        result = ScanResult(violations=[
            Violation(principle=p, message=f"v{i}") for i in range(3)
        ])
        assert len(result.blocking_violations) == 3
        assert result.passed is False


# ── scan — applies_to filtering ───────────────────────────────────────────────


class TestScanAppliesTo:
    """Principles must only be evaluated in their declared skill context."""

    def test_review_pr_principle_skipped_in_check_code(self) -> None:
        p = _make_principle(applies_to=["review-pr"])
        result = scan([p], {}, skill="check-code")
        assert len(result.violations) == 0

    def test_check_code_principle_skipped_in_review_pr(self) -> None:
        p = _make_principle(applies_to=["check-code"])
        result = scan([p], {}, skill="review-pr")
        assert len(result.violations) == 0

    def test_both_applies_to_runs_in_check_code(self) -> None:
        p = _make_principle(applies_to=["check-code", "review-pr"])
        result = scan([p], {}, skill="check-code")
        assert result.principles_loaded == 1

    def test_both_applies_to_runs_in_review_pr(self) -> None:
        p = _make_principle(applies_to=["check-code", "review-pr"])
        result = scan([p], {}, skill="review-pr")
        assert result.principles_loaded == 1

    def test_principles_loaded_count_is_all_not_just_filtered(self) -> None:
        """principles_loaded must reflect the full list, not the filtered subset."""
        p_check = _make_principle("P001", applies_to=["check-code"])
        p_review = _make_principle("P002", applies_to=["review-pr"])
        result = scan([p_check, p_review], {}, skill="check-code")
        assert result.principles_loaded == 2

    def test_files_scanned_count_matches_input(self) -> None:
        p = _make_principle(applies_to=["check-code"])
        files = {"src/a.py": [(1, "pass")], "src/b.py": [(1, "pass")]}
        result = scan([p], files, skill="check-code")
        assert result.files_scanned == 2


# ── _generic_keyword_check ────────────────────────────────────────────────────


class TestGenericKeywordCheck:
    def test_detects_todo_annotation(self) -> None:
        principle = _make_principle("P007")
        files = {"src/main.py": [(42, "# TODO: P007 fix this later")]}
        violations = _generic_keyword_check(principle, files)
        assert len(violations) == 1
        assert violations[0].line_number == 42
        assert violations[0].file_path == "src/main.py"

    def test_detects_fixme_annotation(self) -> None:
        principle = _make_principle("P007")
        files = {"src/main.py": [(10, "# FIXME(P007): resolve this")]}
        violations = _generic_keyword_check(principle, files)
        assert len(violations) == 1

    def test_detects_hack_annotation(self) -> None:
        principle = _make_principle("P007")
        files = {"src/main.py": [(5, "# HACK: P007 workaround")]}
        violations = _generic_keyword_check(principle, files)
        assert len(violations) == 1

    def test_no_violation_without_principle_id(self) -> None:
        principle = _make_principle("P007")
        files = {"src/main.py": [(1, "# TODO: fix something unrelated")]}
        violations = _generic_keyword_check(principle, files)
        assert len(violations) == 0

    def test_case_insensitive_annotation_keyword(self) -> None:
        principle = _make_principle("P007")
        files = {"src/main.py": [(1, "# todo: P007 lowercase")]}
        violations = _generic_keyword_check(principle, files)
        assert len(violations) == 1

    def test_multiple_files_accumulate_violations(self) -> None:
        principle = _make_principle("P007")
        files = {
            "src/a.py": [(1, "# TODO: P007 in A"), (3, "# normal comment")],
            "src/b.py": [(7, "# FIXME: P007 in B")],
        }
        violations = _generic_keyword_check(principle, files)
        assert len(violations) == 2

    def test_snippet_is_stripped(self) -> None:
        principle = _make_principle("P007")
        files = {"src/main.py": [(1, "  # TODO: P007 snippet test  ")]}
        violations = _generic_keyword_check(principle, files)
        assert violations[0].snippet == "# TODO: P007 snippet test"

    def test_no_false_positive_on_different_id(self) -> None:
        """P007 checker must not fire on a line referencing P008."""
        p007 = _make_principle("P007")
        files = {"src/main.py": [(1, "# TODO: P008 unrelated principle")]}
        violations = _generic_keyword_check(p007, files)
        assert len(violations) == 0

    def test_empty_files_produces_no_violations(self) -> None:
        principle = _make_principle("P007")
        violations = _generic_keyword_check(principle, {})
        assert violations == []
