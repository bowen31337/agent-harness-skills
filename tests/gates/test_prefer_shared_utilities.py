"""
tests/gates/test_prefer_shared_utilities.py
============================================
Tests for the P032 prefer_shared_utilities scanner that detects duplicate
function names defined across multiple non-test Python files.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from harness_skills.gates.principles import (
    GateConfig,
    PrinciplesGate,
    _scan_prefer_shared_utilities,
)


def _write_py(tmp_path: Path, name: str, content: str) -> Path:
    """Write a Python source file under *tmp_path* and return its path."""
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content))
    return path


# ---------------------------------------------------------------------------
# Direct scanner tests
# ---------------------------------------------------------------------------


class TestScanPreferSharedUtilities:
    def test_duplicate_function_detected(self, tmp_path):
        """Two non-test files with the same function name -> violations."""
        _write_py(tmp_path, "src/utils_a.py", "def format_output(data): pass\n")
        _write_py(tmp_path, "src/utils_b.py", "def format_output(data): pass\n")
        violations = _scan_prefer_shared_utilities(tmp_path, "P032", "warning")
        assert len(violations) >= 2  # one per occurrence
        assert all("format_output" in v.message for v in violations)
        assert all(v.rule_id == "principles/prefer-shared-utilities" for v in violations)

    def test_unique_names_no_violation(self, tmp_path):
        """Files with unique function names -> no violations."""
        _write_py(tmp_path, "src/module_a.py", "def func_alpha(): pass\n")
        _write_py(tmp_path, "src/module_b.py", "def func_beta(): pass\n")
        violations = _scan_prefer_shared_utilities(tmp_path, "P032", "warning")
        assert violations == []

    def test_same_function_same_file_no_violation(self, tmp_path):
        """Same function name in one file only -> no violation."""
        _write_py(tmp_path, "src/helpers.py", "def helper(): pass\n")
        violations = _scan_prefer_shared_utilities(tmp_path, "P032", "warning")
        assert violations == []

    def test_test_files_excluded(self, tmp_path):
        """Duplicate names across test files should NOT be flagged."""
        _write_py(tmp_path, "tests/test_a.py", "def setup_db(): pass\n")
        _write_py(tmp_path, "tests/test_b.py", "def setup_db(): pass\n")
        violations = _scan_prefer_shared_utilities(tmp_path, "P032", "warning")
        assert violations == []

    def test_dunder_methods_excluded(self, tmp_path):
        """Dunder methods like __init__ should not be flagged."""
        _write_py(tmp_path, "src/model_a.py", "class A:\n    def __init__(self): pass\n")
        _write_py(tmp_path, "src/model_b.py", "class B:\n    def __init__(self): pass\n")
        violations = _scan_prefer_shared_utilities(tmp_path, "P032", "warning")
        assert violations == []

    def test_violation_has_suggestion(self, tmp_path):
        """Each violation should include a remediation suggestion."""
        _write_py(tmp_path, "src/a.py", "def compute(): pass\n")
        _write_py(tmp_path, "src/b.py", "def compute(): pass\n")
        violations = _scan_prefer_shared_utilities(tmp_path, "P032", "warning")
        assert all(v.suggestion and "shared utility" in v.suggestion for v in violations)

    def test_violation_has_line_number(self, tmp_path):
        """Each violation should report the correct line number."""
        _write_py(tmp_path, "src/a.py", "# header\ndef duplicate_fn(): pass\n")
        _write_py(tmp_path, "src/b.py", "def duplicate_fn(): pass\n")
        violations = _scan_prefer_shared_utilities(tmp_path, "P032", "warning")
        line_numbers = {v.line_number for v in violations}
        assert 2 in line_numbers  # line 2 in src/a.py
        assert 1 in line_numbers  # line 1 in src/b.py

    def test_skips_venv(self, tmp_path):
        """Files in .venv should be skipped."""
        (tmp_path / ".venv" / "lib").mkdir(parents=True)
        _write_py(tmp_path, ".venv/lib/util.py", "def helper(): pass\n")
        _write_py(tmp_path, "src/util.py", "def helper(): pass\n")
        violations = _scan_prefer_shared_utilities(tmp_path, "P032", "warning")
        assert violations == []


# ---------------------------------------------------------------------------
# Integration: P032 registered in gate
# ---------------------------------------------------------------------------


class TestP032Integration:
    def test_p032_registered_and_runs_via_gate(self, tmp_path):
        """P032 should be discoverable and runnable through PrinciplesGate."""
        _write_py(tmp_path, "src/a.py", "def shared_fn(): pass\n")
        _write_py(tmp_path, "src/b.py", "def shared_fn(): pass\n")
        gate = PrinciplesGate(GateConfig(
            rules=["prefer_shared_utilities"],
            fail_on_critical=False,
        ))
        result = gate.run(tmp_path)
        assert any(
            v.rule_id == "principles/prefer-shared-utilities"
            for v in result.violations
        )

    def test_p032_not_run_when_not_in_rules(self, tmp_path):
        """P032 should NOT run when rules don't include it."""
        _write_py(tmp_path, "src/a.py", "def shared_fn(): pass\n")
        _write_py(tmp_path, "src/b.py", "def shared_fn(): pass\n")
        gate = PrinciplesGate(GateConfig(
            rules=["no_magic_numbers"],
            fail_on_critical=False,
        ))
        result = gate.run(tmp_path)
        assert not any(
            v.rule_id == "principles/prefer-shared-utilities"
            for v in result.violations
        )
