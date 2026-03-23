"""Tests for harness_skills.generators.import_convention_detector.

Covers:
    - detect_import_conventions()  scans a directory tree
    - generate_import_principle()  builds a principle dict from scan results
    - _classify_import()           internal group classification
    - _is_sorted()                 alphabetical-sort helper
    - _analyse_file()              per-file statistics
    - Edge cases: empty dirs, parse errors, relative imports, mixed patterns
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness_skills.generators.import_convention_detector import (
    ImportConventionResult,
    _analyse_file,
    _classify_import,
    _is_sorted,
    detect_import_conventions,
    generate_import_principle,
)

# ---------------------------------------------------------------------------
# Helpers for building temporary Python files
# ---------------------------------------------------------------------------

_IDEAL_FILE = """\
from __future__ import annotations

import os
import sys

import requests

from harness_skills.models import Foo
"""

_NO_FUTURE_FILE = """\
import os
import sys

import requests
"""

_WRONG_ORDER_FILE = """\
from __future__ import annotations

import requests

import os
"""

_RELATIVE_IMPORT_FILE = """\
from __future__ import annotations

import os

from .utils import helper
"""

_UNSORTED_FILE = """\
from __future__ import annotations

import sys
import os
"""

_PARSE_ERROR_FILE = """\
def broken(:
    pass
"""

_EMPTY_FILE = ""


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# _is_sorted
# ---------------------------------------------------------------------------


class TestIsSorted:
    def test_empty_list(self):
        assert _is_sorted([]) is True

    def test_single_element(self):
        assert _is_sorted(["z"]) is True

    def test_already_sorted(self):
        assert _is_sorted(["alpha", "beta", "gamma"]) is True

    def test_not_sorted(self):
        assert _is_sorted(["beta", "alpha"]) is False

    def test_case_insensitive(self):
        # "Alpha" < "beta" when lowered → sorted
        assert _is_sorted(["Alpha", "beta"]) is True
        assert _is_sorted(["beta", "Alpha"]) is False


# ---------------------------------------------------------------------------
# _analyse_file
# ---------------------------------------------------------------------------


class TestAnalyseFile:
    def test_ideal_file_future_annotations_first(self, tmp_path):
        p = _write(tmp_path, "ideal.py", _IDEAL_FILE)
        stats = _analyse_file(p, frozenset(["harness_skills"]))
        assert stats.future_annotations_first is True

    def test_ideal_file_group_order_correct(self, tmp_path):
        p = _write(tmp_path, "ideal.py", _IDEAL_FILE)
        stats = _analyse_file(p, frozenset(["harness_skills"]))
        assert stats.group_order_correct is True

    def test_ideal_file_blank_line_separation(self, tmp_path):
        p = _write(tmp_path, "ideal.py", _IDEAL_FILE)
        stats = _analyse_file(p, frozenset(["harness_skills"]))
        assert stats.blank_line_separation is True

    def test_ideal_file_sorted_within_groups(self, tmp_path):
        p = _write(tmp_path, "ideal.py", _IDEAL_FILE)
        stats = _analyse_file(p, frozenset(["harness_skills"]))
        assert stats.sorted_within_groups is True

    def test_no_future_annotations(self, tmp_path):
        p = _write(tmp_path, "no_future.py", _NO_FUTURE_FILE)
        stats = _analyse_file(p, frozenset())
        assert stats.future_annotations_first is False

    def test_wrong_group_order(self, tmp_path):
        p = _write(tmp_path, "wrong_order.py", _WRONG_ORDER_FILE)
        stats = _analyse_file(p, frozenset())
        assert stats.group_order_correct is False

    def test_relative_import_detected(self, tmp_path):
        p = _write(tmp_path, "rel.py", _RELATIVE_IMPORT_FILE)
        stats = _analyse_file(p, frozenset())
        assert stats.has_relative_imports is True

    def test_no_relative_import(self, tmp_path):
        p = _write(tmp_path, "no_rel.py", _NO_FUTURE_FILE)
        stats = _analyse_file(p, frozenset())
        assert stats.has_relative_imports is False

    def test_unsorted_within_group(self, tmp_path):
        p = _write(tmp_path, "unsorted.py", _UNSORTED_FILE)
        stats = _analyse_file(p, frozenset())
        assert stats.sorted_within_groups is False

    def test_parse_error_flagged(self, tmp_path):
        p = _write(tmp_path, "broken.py", _PARSE_ERROR_FILE)
        stats = _analyse_file(p, frozenset())
        assert stats.parse_error is True

    def test_empty_file_no_error(self, tmp_path):
        p = _write(tmp_path, "empty.py", _EMPTY_FILE)
        stats = _analyse_file(p, frozenset())
        assert stats.parse_error is False

    def test_empty_file_no_future_annotations(self, tmp_path):
        p = _write(tmp_path, "empty.py", _EMPTY_FILE)
        stats = _analyse_file(p, frozenset())
        assert stats.future_annotations_first is False


# ---------------------------------------------------------------------------
# detect_import_conventions — basic scanning
# ---------------------------------------------------------------------------


class TestDetectImportConventions:
    def test_empty_directory_returns_zero_files(self, tmp_path):
        result = detect_import_conventions(tmp_path)
        assert result.files_scanned == 0
        assert result.files_with_parse_errors == 0

    def test_single_ideal_file_all_true(self, tmp_path):
        _write(tmp_path, "ideal.py", _IDEAL_FILE)
        result = detect_import_conventions(
            tmp_path, known_first_party=["harness_skills"]
        )
        assert result.files_scanned == 1
        assert result.uses_future_annotations_first is True
        assert result.uses_group_order is True
        assert result.uses_blank_line_separation is True
        assert result.uses_sorted_within_groups is True

    def test_single_parse_error_file(self, tmp_path):
        _write(tmp_path, "broken.py", _PARSE_ERROR_FILE)
        result = detect_import_conventions(tmp_path)
        assert result.files_scanned == 1
        assert result.files_with_parse_errors == 1
        # No valid files → majority flags stay False
        assert result.uses_future_annotations_first is False

    def test_majority_vote_future_annotations(self, tmp_path):
        # 3 files with future annotations, 1 without → majority True
        for i in range(3):
            _write(tmp_path, f"good_{i}.py", _IDEAL_FILE)
        _write(tmp_path, "bad.py", _NO_FUTURE_FILE)
        result = detect_import_conventions(
            tmp_path, known_first_party=["harness_skills"]
        )
        assert result.uses_future_annotations_first is True

    def test_minority_vote_future_annotations(self, tmp_path):
        # 1 file with future annotations, 3 without → majority False
        _write(tmp_path, "good.py", _IDEAL_FILE)
        for i in range(3):
            _write(tmp_path, f"bad_{i}.py", _NO_FUTURE_FILE)
        result = detect_import_conventions(
            tmp_path, known_first_party=["harness_skills"]
        )
        assert result.uses_future_annotations_first is False

    def test_relative_imports_majority(self, tmp_path):
        for i in range(2):
            _write(tmp_path, f"rel_{i}.py", _RELATIVE_IMPORT_FILE)
        _write(tmp_path, "abs.py", _IDEAL_FILE)
        result = detect_import_conventions(tmp_path, known_first_party=["harness_skills"])
        assert result.uses_relative_imports is True

    def test_no_relative_imports_majority(self, tmp_path):
        for i in range(3):
            _write(tmp_path, f"abs_{i}.py", _IDEAL_FILE)
        _write(tmp_path, "rel.py", _RELATIVE_IMPORT_FILE)
        result = detect_import_conventions(
            tmp_path, known_first_party=["harness_skills"]
        )
        assert result.uses_relative_imports is False

    def test_files_scanned_count(self, tmp_path):
        for i in range(5):
            _write(tmp_path, f"f{i}.py", _IDEAL_FILE)
        result = detect_import_conventions(
            tmp_path, known_first_party=["harness_skills"]
        )
        assert result.files_scanned == 5

    def test_excludes_venv_directory(self, tmp_path):
        venv = tmp_path / ".venv" / "lib"
        venv.mkdir(parents=True)
        _write(venv, "hidden.py", _NO_FUTURE_FILE)
        _write(tmp_path, "real.py", _IDEAL_FILE)
        result = detect_import_conventions(
            tmp_path, known_first_party=["harness_skills"]
        )
        # Only real.py should be counted, not hidden.py inside .venv
        assert result.files_scanned == 1

    def test_auto_detects_first_party_packages(self, tmp_path):
        # Create a local package (directory with __init__.py)
        pkg = tmp_path / "mypackage"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        _write(tmp_path, "main.py", _IDEAL_FILE)
        result = detect_import_conventions(tmp_path)
        assert "mypackage" in result.detected_first_party

    def test_known_first_party_overrides_autodetect(self, tmp_path):
        _write(tmp_path, "main.py", _IDEAL_FILE)
        result = detect_import_conventions(
            tmp_path, known_first_party=["custom_pkg"]
        )
        assert result.detected_first_party == ["custom_pkg"]

    def test_min_files_threshold_prevents_majority_flags(self, tmp_path):
        _write(tmp_path, "good.py", _IDEAL_FILE)
        result = detect_import_conventions(
            tmp_path,
            known_first_party=["harness_skills"],
            min_files=5,  # require 5 files before setting majority flags
        )
        # Only 1 file scanned — below threshold → all majority flags False
        assert result.uses_future_annotations_first is False
        assert result.uses_group_order is False

    def test_parse_errors_excluded_from_majority(self, tmp_path):
        # 2 parse errors + 1 ideal → 1 valid file; majority should reflect that
        for i in range(2):
            _write(tmp_path, f"broken_{i}.py", _PARSE_ERROR_FILE)
        _write(tmp_path, "good.py", _IDEAL_FILE)
        result = detect_import_conventions(
            tmp_path, known_first_party=["harness_skills"]
        )
        assert result.files_with_parse_errors == 2
        assert result.uses_future_annotations_first is True  # 1/1 valid → 100%


# ---------------------------------------------------------------------------
# generate_import_principle
# ---------------------------------------------------------------------------


class TestGenerateImportPrinciple:
    def _full_result(self) -> ImportConventionResult:
        """Return a result with all majority flags set to True."""
        return ImportConventionResult(
            files_scanned=10,
            files_with_parse_errors=0,
            future_annotations_first_count=9,
            group_order_correct_count=10,
            blank_line_separation_count=9,
            sorted_within_groups_count=8,
            relative_imports_count=7,
            uses_future_annotations_first=True,
            uses_group_order=True,
            uses_blank_line_separation=True,
            uses_sorted_within_groups=True,
            uses_relative_imports=True,
            detected_first_party=["harness_skills"],
        )

    def test_returns_dict(self):
        result = self._full_result()
        principle = generate_import_principle(result)
        assert isinstance(principle, dict)

    def test_default_principle_id(self):
        principle = generate_import_principle(self._full_result())
        assert principle["id"] == "P013"

    def test_custom_principle_id(self):
        principle = generate_import_principle(
            self._full_result(), principle_id="P042"
        )
        assert principle["id"] == "P042"

    def test_category_is_style(self):
        principle = generate_import_principle(self._full_result())
        assert principle["category"] == "style"

    def test_severity_is_suggestion(self):
        principle = generate_import_principle(self._full_result())
        assert principle["severity"] == "suggestion"

    def test_default_applies_to(self):
        principle = generate_import_principle(self._full_result())
        assert "review-pr" in principle["applies_to"]
        assert "check-code" in principle["applies_to"]

    def test_custom_applies_to(self):
        principle = generate_import_principle(
            self._full_result(), applies_to=["check-code"]
        )
        assert principle["applies_to"] == ["check-code"]

    def test_rule_mentions_isort_when_group_order_true(self):
        principle = generate_import_principle(self._full_result())
        assert "isort" in principle["rule"].lower() or "four-group" in principle["rule"].lower()

    def test_rule_mentions_future_annotations(self):
        principle = generate_import_principle(self._full_result())
        assert "__future__" in principle["rule"]

    def test_rule_mentions_blank_line(self):
        principle = generate_import_principle(self._full_result())
        assert "blank line" in principle["rule"]

    def test_rule_mentions_relative_imports(self):
        principle = generate_import_principle(self._full_result())
        assert "relative" in principle["rule"].lower()

    def test_rule_mentions_alphabetical(self):
        principle = generate_import_principle(self._full_result())
        assert "alphabetical" in principle["rule"].lower() or "sorted" in principle["rule"].lower()

    def test_rule_includes_file_count(self):
        principle = generate_import_principle(self._full_result())
        assert "10" in principle["rule"]

    def test_rule_includes_first_party_package(self):
        principle = generate_import_principle(self._full_result())
        assert "harness_skills" in principle["rule"]

    def test_generated_by_field(self):
        principle = generate_import_principle(self._full_result())
        assert principle["generated_by"] == "import_convention_detector"

    def test_files_scanned_field(self):
        principle = generate_import_principle(self._full_result())
        assert principle["files_scanned"] == 10

    def test_files_with_errors_field(self):
        principle = generate_import_principle(self._full_result())
        assert principle["files_with_parse_errors"] == 0

    def test_no_future_annotations_rule_omits_future_line(self):
        result = self._full_result()
        result.uses_future_annotations_first = False
        principle = generate_import_principle(result)
        assert "__future__" not in principle["rule"]

    def test_no_blank_separation_rule_omits_blank_line(self):
        result = self._full_result()
        result.uses_blank_line_separation = False
        principle = generate_import_principle(result)
        assert "blank line" not in principle["rule"]

    def test_no_relative_imports_rule_omits_relative_line(self):
        result = self._full_result()
        result.uses_relative_imports = False
        principle = generate_import_principle(result)
        assert "relative" not in principle["rule"].lower()

    def test_minimal_result_still_produces_principle(self):
        result = ImportConventionResult(files_scanned=0)
        principle = generate_import_principle(result)
        assert "id" in principle
        assert "rule" in principle


# ---------------------------------------------------------------------------
# Integration: detect then generate
# ---------------------------------------------------------------------------


class TestDetectThenGenerate:
    def test_end_to_end_ideal_codebase(self, tmp_path):
        for i in range(5):
            _write(tmp_path, f"module_{i}.py", _IDEAL_FILE)
        result = detect_import_conventions(
            tmp_path, known_first_party=["harness_skills"]
        )
        principle = generate_import_principle(result, principle_id="P013")

        assert principle["id"] == "P013"
        assert "four-group" in principle["rule"] or "isort" in principle["rule"].lower()
        assert "__future__" in principle["rule"]
        assert "blank line" in principle["rule"]
        assert principle["files_scanned"] == 5

    def test_end_to_end_mixed_codebase(self, tmp_path):
        # 3 ideal + 2 non-future → still majority future-annotations
        for i in range(3):
            _write(tmp_path, f"good_{i}.py", _IDEAL_FILE)
        for i in range(2):
            _write(tmp_path, f"bad_{i}.py", _NO_FUTURE_FILE)
        result = detect_import_conventions(
            tmp_path, known_first_party=["harness_skills"]
        )
        principle = generate_import_principle(result)
        assert "__future__" in principle["rule"]
        assert principle["files_scanned"] == 5
