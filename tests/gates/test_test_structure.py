"""
tests/gates/test_test_structure.py
==================================
Tests for the P007 test_structure scanner that checks test files follow
arrange-act-assert pattern (at least one assert per test function) and
use descriptive test names (test_ prefix + verb).
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from harness_skills.gates.principles import (
    GateConfig,
    PrinciplesGate,
    _scan_test_structure,
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


class TestScanTestStructure:
    def test_detects_missing_assert(self, tmp_path):
        """A test function without any assert -> violation."""
        _write_py(tmp_path, "test_example.py", '''\
            def test_does_something():
                x = 1 + 1
        ''')
        violations = _scan_test_structure(tmp_path, "P007", "warning")
        assert len(violations) >= 1
        assert any("no assert" in v.message.lower() for v in violations)
        assert all(v.rule_id == "principles/test-structure" for v in violations)

    def test_clean_test_with_assert(self, tmp_path):
        """A test function with an assert -> no violation for missing assert."""
        _write_py(tmp_path, "test_example.py", '''\
            def test_adds_numbers():
                result = 1 + 1
                assert result == 2
        ''')
        violations = _scan_test_structure(tmp_path, "P007", "warning")
        assert violations == []

    def test_only_scans_test_files(self, tmp_path):
        """Non-test files should be ignored entirely."""
        _write_py(tmp_path, "src/helper.py", '''\
            def test_something():
                x = 1
        ''')
        violations = _scan_test_structure(tmp_path, "P007", "warning")
        assert violations == []

    def test_pytest_raises_counts_as_assert(self, tmp_path):
        """Using pytest.raises should count as an assertion."""
        _write_py(tmp_path, "test_errors.py", '''\
            import pytest
            def test_raises_value_error():
                with pytest.raises(ValueError):
                    int("not_a_number")
        ''')
        violations = _scan_test_structure(tmp_path, "P007", "warning")
        assert violations == []

    def test_detects_bad_naming(self, tmp_path):
        """A test function with non-descriptive name -> violation."""
        _write_py(tmp_path, "test_example.py", '''\
            def test_1():
                assert True
        ''')
        violations = _scan_test_structure(tmp_path, "P007", "warning")
        assert len(violations) >= 1
        assert any("descriptive name" in v.message.lower() for v in violations)

    def test_clean_naming(self, tmp_path):
        """A test function with descriptive name -> no naming violation."""
        _write_py(tmp_path, "test_example.py", '''\
            def test_returns_empty_list():
                assert [] == []
        ''')
        violations = _scan_test_structure(tmp_path, "P007", "warning")
        assert violations == []

    def test_violation_has_suggestion(self, tmp_path):
        """Each violation should include a remediation suggestion."""
        _write_py(tmp_path, "test_example.py", '''\
            def test_something():
                x = 1
        ''')
        violations = _scan_test_structure(tmp_path, "P007", "warning")
        assert len(violations) >= 1
        assert all(v.suggestion for v in violations)

    def test_line_numbers_reported(self, tmp_path):
        """Violations should include correct line numbers."""
        _write_py(tmp_path, "test_example.py", '''\
            def test_first():
                assert True

            def test_second():
                x = 1
        ''')
        violations = _scan_test_structure(tmp_path, "P007", "warning")
        assert len(violations) >= 1
        assert any(v.line_number == 4 for v in violations)


# ---------------------------------------------------------------------------
# Integration: P007 registered in gate
# ---------------------------------------------------------------------------


class TestP007Integration:
    def test_p007_registered_and_runs_via_gate(self, tmp_path):
        """P007 should be discoverable and runnable through PrinciplesGate."""
        _write_py(tmp_path, "test_example.py", '''\
            def test_does_nothing():
                x = 1
        ''')
        gate = PrinciplesGate(GateConfig(
            rules=["test_structure"],
            fail_on_critical=False,
        ))
        result = gate.run(tmp_path)
        assert any(
            v.rule_id == "principles/test-structure"
            for v in result.violations
        )

    def test_p007_not_run_when_not_in_rules(self, tmp_path):
        """P007 should NOT run when rules don't include it."""
        _write_py(tmp_path, "test_example.py", '''\
            def test_does_nothing():
                x = 1
        ''')
        gate = PrinciplesGate(GateConfig(
            rules=["no_magic_numbers"],
            fail_on_critical=False,
        ))
        result = gate.run(tmp_path)
        assert not any(
            v.rule_id == "principles/test-structure"
            for v in result.violations
        )
