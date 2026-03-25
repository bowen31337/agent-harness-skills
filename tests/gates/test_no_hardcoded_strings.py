"""
tests/gates/test_no_hardcoded_strings.py
=========================================
Tests for the P018 no_hardcoded_strings scanner that detects hardcoded
config-like string literals (file paths, email addresses) outside of
named constants, docstrings, and comments.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from harness_skills.gates.principles import (
    GateConfig,
    PrinciplesGate,
    _scan_no_hardcoded_strings,
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


class TestScanNoHardcodedStrings:
    def test_detects_hardcoded_file_path(self, tmp_path):
        """A bare absolute file path in a variable -> violation."""
        _write_py(tmp_path, "src/config.py", '''\
            config_path = "/etc/myapp/config.yaml"
        ''')
        violations = _scan_no_hardcoded_strings(tmp_path, "P018", "warning")
        assert len(violations) >= 1
        assert any("/etc/myapp/config.yaml" in v.message for v in violations)
        assert all(v.rule_id == "principles/no-hardcoded-strings" for v in violations)

    def test_detects_hardcoded_email(self, tmp_path):
        """An email address literal -> violation."""
        _write_py(tmp_path, "src/notify.py", '''\
            admin_email = "admin@example.com"
        ''')
        violations = _scan_no_hardcoded_strings(tmp_path, "P018", "warning")
        assert len(violations) >= 1
        assert any("admin@example.com" in v.message for v in violations)

    def test_allows_upper_snake_case_constant(self, tmp_path):
        """Strings assigned to UPPER_SNAKE_CASE names are allowed."""
        _write_py(tmp_path, "src/constants.py", '''\
            DEFAULT_CONFIG_PATH = "/etc/myapp/config.yaml"
            ADMIN_EMAIL = "admin@example.com"
        ''')
        violations = _scan_no_hardcoded_strings(tmp_path, "P018", "warning")
        assert violations == []

    def test_allows_docstrings(self, tmp_path):
        """Config-like strings inside docstrings are allowed."""
        _write_py(tmp_path, "src/module.py", '''\
            def load_config():
                """Load config from /etc/myapp/config.yaml."""
                pass
        ''')
        violations = _scan_no_hardcoded_strings(tmp_path, "P018", "warning")
        assert violations == []

    def test_allows_module_docstrings(self, tmp_path):
        """Config-like strings inside module-level docstrings are allowed."""
        _write_py(tmp_path, "src/module.py", '''\
            """
            Module that reads /etc/myapp/config.yaml for settings.
            Contact: admin@example.com
            """
            x = 1
        ''')
        violations = _scan_no_hardcoded_strings(tmp_path, "P018", "warning")
        assert violations == []

    def test_no_violation_for_short_strings(self, tmp_path):
        """Short strings (< 4 chars) are not flagged."""
        _write_py(tmp_path, "src/module.py", '''\
            x = "hi"
            y = "/a"
        ''')
        violations = _scan_no_hardcoded_strings(tmp_path, "P018", "warning")
        assert violations == []

    def test_violation_has_suggestion(self, tmp_path):
        """Each violation should include a remediation suggestion."""
        _write_py(tmp_path, "src/paths.py", '''\
            log_dir = "/var/log/myapp/output"
        ''')
        violations = _scan_no_hardcoded_strings(tmp_path, "P018", "warning")
        assert len(violations) >= 1
        assert all(v.suggestion and "constant" in v.suggestion.lower() for v in violations)

    def test_no_violation_for_normal_strings(self, tmp_path):
        """Regular strings that don't look like config values -> no violation."""
        _write_py(tmp_path, "src/app.py", '''\
            name = "hello world"
            label = "submit_button"
        ''')
        violations = _scan_no_hardcoded_strings(tmp_path, "P018", "warning")
        assert violations == []


# ---------------------------------------------------------------------------
# Integration: P018 registered in gate
# ---------------------------------------------------------------------------


class TestP018Integration:
    def test_p018_registered_and_runs_via_gate(self, tmp_path):
        """P018 should be discoverable and runnable through PrinciplesGate."""
        _write_py(tmp_path, "src/config.py", '''\
            path = "/etc/myapp/settings.yaml"
        ''')
        gate = PrinciplesGate(GateConfig(
            rules=["no_hardcoded_strings"],
            fail_on_critical=False,
        ))
        result = gate.run(tmp_path)
        assert any(
            v.rule_id == "principles/no-hardcoded-strings"
            for v in result.violations
        )

    def test_p018_not_run_when_not_in_rules(self, tmp_path):
        """P018 should NOT run when rules don't include it."""
        _write_py(tmp_path, "src/config.py", '''\
            path = "/etc/myapp/settings.yaml"
        ''')
        gate = PrinciplesGate(GateConfig(
            rules=["no_magic_numbers"],
            fail_on_critical=False,
        ))
        result = gate.run(tmp_path)
        assert not any(
            v.rule_id == "principles/no-hardcoded-strings"
            for v in result.violations
        )
