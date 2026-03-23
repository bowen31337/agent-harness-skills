"""
tests/gates/test_security.py
==============================
Unit tests for :mod:`harness_skills.gates.security`.

Test strategy
-------------
* **Fixture helpers** write temporary source and audit-report files so the
  real file-system and parsing logic runs against the actual file system.
* Each of the three sub-checks is exercised independently:

  - :class:`~harness_skills.gates.security._SecretScanner` — hardcoded
    credential detection using the built-in regex patterns.
  - :class:`~harness_skills.gates.security._DependencyAuditor` — pip-audit
    JSON report parsing including threshold filtering and ignore lists.
  - :class:`~harness_skills.gates.security._InputValidationChecker` —
    unsafe input-handling pattern detection.

* Severity threshold boundary conditions are verified: a vulnerability at the
  configured threshold is reported; one below is suppressed.
* ``ignore_ids`` suppression is tested for both secret-scanner rule IDs and
  CVE/PYSEC IDs.
* ``fail_on_error=False`` behaviour is verified: all violations become
  *warnings* and the gate always passes.
* A small integration section runs :class:`SecurityGate` end-to-end and
  checks :class:`~harness_skills.gates.security.GateResult` attributes.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from harness_skills.gates.security import (
    GateResult,
    SecurityGate,
    Violation,
    _DependencyAuditor,
    _InputValidationChecker,
    _SecretScanner,
    _find_audit_report,
    _meets_threshold,
    _parse_pip_audit_report,
    _scan_file_for_secrets,
    _scan_file_for_unsafe_input,
    _AUDIT_REPORT_NAMES,
    _SECRET_PATTERNS,
    _UNSAFE_INPUT_PATTERNS,
)
from harness_skills.models.gate_configs import SecurityGateConfig


# ---------------------------------------------------------------------------
# Helpers — file writers
# ---------------------------------------------------------------------------


def write_source_file(path: Path, content: str) -> Path:
    """Write *content* to *path* (creates parent dirs if needed)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


def write_audit_report(path: Path, packages: list[dict]) -> Path:
    """Write a pip-audit JSON report to *path*."""
    path.write_text(json.dumps(packages), encoding="utf-8")
    return path


def make_vuln(
    pkg_name: str = "vulnerable-pkg",
    version: str = "1.0.0",
    vuln_id: str = "CVE-2023-99999",
    description: str = "A test vulnerability.",
    fix_versions: list[str] | None = None,
    severity: str = "HIGH",
    aliases: list[str] | None = None,
) -> dict:
    """Return a single pip-audit package entry with one vulnerability."""
    return {
        "name": pkg_name,
        "version": version,
        "vulns": [
            {
                "id": vuln_id,
                "description": description,
                "fix_versions": fix_versions if fix_versions is not None else ["2.0.0"],
                "severity": severity,
                "aliases": aliases or [],
            }
        ],
    }


# ---------------------------------------------------------------------------
# _meets_threshold
# ---------------------------------------------------------------------------


class TestMeetsThreshold:
    def test_critical_meets_high_threshold(self):
        assert _meets_threshold("CRITICAL", "HIGH") is True

    def test_high_meets_high_threshold(self):
        assert _meets_threshold("HIGH", "HIGH") is True

    def test_medium_does_not_meet_high_threshold(self):
        assert _meets_threshold("MEDIUM", "HIGH") is False

    def test_low_does_not_meet_high_threshold(self):
        assert _meets_threshold("LOW", "HIGH") is False

    def test_medium_meets_medium_threshold(self):
        assert _meets_threshold("MEDIUM", "MEDIUM") is True

    def test_low_does_not_meet_medium_threshold(self):
        assert _meets_threshold("LOW", "MEDIUM") is False

    def test_low_meets_low_threshold(self):
        assert _meets_threshold("LOW", "LOW") is True

    def test_unknown_severity_defaults_to_high(self):
        """Unknown severity should NOT be silently suppressed at HIGH threshold."""
        assert _meets_threshold("UNKNOWN", "HIGH") is True

    def test_unknown_severity_suppressed_at_critical_threshold(self):
        assert _meets_threshold("UNKNOWN", "CRITICAL") is False

    def test_case_insensitive(self):
        assert _meets_threshold("high", "HIGH") is True
        assert _meets_threshold("MEDIUM", "medium") is True


# ---------------------------------------------------------------------------
# Secret scanning — individual pattern tests
# ---------------------------------------------------------------------------


class TestSecretPatterns:
    """Each regex in _SECRET_PATTERNS is exercised with positive and negative samples."""

    def _check_pattern(self, rule_id: str, text: str) -> bool:
        for rid, pattern in _SECRET_PATTERNS:
            if rid == rule_id:
                return bool(pattern.search(text))
        raise KeyError(f"Rule '{rule_id}' not found in _SECRET_PATTERNS")

    # hardcoded-password
    def test_password_matches_real_value(self):
        assert self._check_pattern("hardcoded-password", 'password = "s3cr3tPass!"')

    def test_password_ignores_placeholder(self):
        assert not self._check_pattern("hardcoded-password", 'password = "changeme"')
        assert not self._check_pattern("hardcoded-password", 'password = "your_password"')
        assert not self._check_pattern("hardcoded-password", 'password = "example_pass"')

    def test_password_ignores_short_value(self):
        # Values shorter than 6 chars are not flagged
        assert not self._check_pattern("hardcoded-password", 'password = "abc"')

    def test_passwd_alias_matches(self):
        assert self._check_pattern("hardcoded-password", 'passwd = "superSecure123"')

    # hardcoded-api-key
    def test_api_key_matches(self):
        assert self._check_pattern("hardcoded-api-key", 'api_key = "a1b2c3d4e5f6g7h8"')

    def test_apikey_no_underscore_matches(self):
        assert self._check_pattern("hardcoded-api-key", 'apikey = "long_key_value_here"')

    def test_access_key_matches(self):
        assert self._check_pattern("hardcoded-api-key", 'access_key = "LONGACCESSKEYVAL"')

    def test_api_key_too_short_ignored(self):
        assert not self._check_pattern("hardcoded-api-key", 'api_key = "short"')

    # hardcoded-token
    def test_auth_token_matches(self):
        assert self._check_pattern("hardcoded-token", 'auth_token = "eyJhbGciOiJIUzI1NiJ9"')

    def test_secret_token_matches(self):
        assert self._check_pattern("hardcoded-token", 'secret_token = "mysecrettoken12"')

    # pem-private-key
    def test_rsa_private_key_header_matches(self):
        assert self._check_pattern("pem-private-key", "-----BEGIN RSA PRIVATE KEY-----")

    def test_ec_private_key_header_matches(self):
        assert self._check_pattern("pem-private-key", "-----BEGIN EC PRIVATE KEY-----")

    def test_generic_private_key_header_matches(self):
        assert self._check_pattern("pem-private-key", "-----BEGIN PRIVATE KEY-----")

    # aws-access-key-id
    def test_aws_access_key_matches(self):
        assert self._check_pattern("aws-access-key-id", "AKIAIOSFODNN7EXAMPLE")

    def test_aws_key_wrong_prefix_ignored(self):
        assert not self._check_pattern("aws-access-key-id", "BKIAIOSFODNN7EXAMPLE")

    # github-personal-access-token
    def test_github_pat_matches(self):
        assert self._check_pattern(
            "github-personal-access-token",
            "ghp_" + "A" * 36,
        )

    def test_github_pat_too_short_ignored(self):
        assert not self._check_pattern(
            "github-personal-access-token",
            "ghp_SHORTTOKEN",
        )


# ---------------------------------------------------------------------------
# _scan_file_for_secrets
# ---------------------------------------------------------------------------


class TestScanFileForSecrets:
    def test_clean_file_returns_no_violations(self, tmp_path: Path):
        f = write_source_file(
            tmp_path / "clean.py",
            'password = os.environ["DB_PASSWORD"]\n',
        )
        result = _scan_file_for_secrets(f, [], "error")
        assert result == []

    def test_hardcoded_password_detected(self, tmp_path: Path):
        f = write_source_file(tmp_path / "app.py", 'password = "SuperSecret99!"\n')
        violations = _scan_file_for_secrets(f, [], "error")
        assert len(violations) == 1
        assert violations[0].kind == "hardcoded_secret"
        assert violations[0].rule_id == "hardcoded-password"
        assert violations[0].line_number == 1

    def test_violation_contains_file_path(self, tmp_path: Path):
        f = write_source_file(tmp_path / "cfg.py", 'api_key = "MY_REAL_KEY_1234"\n')
        violations = _scan_file_for_secrets(f, [], "error")
        assert violations[0].file_path == f

    def test_ignore_id_suppresses_violation(self, tmp_path: Path):
        f = write_source_file(tmp_path / "app.py", 'password = "RealPass123"\n')
        violations = _scan_file_for_secrets(f, ["hardcoded-password"], "error")
        assert violations == []

    def test_fail_on_error_false_yields_warning(self, tmp_path: Path):
        f = write_source_file(tmp_path / "app.py", "-----BEGIN RSA PRIVATE KEY-----\n")
        violations = _scan_file_for_secrets(f, [], "warning")
        assert violations[0].severity == "warning"

    def test_multiple_secrets_on_different_lines(self, tmp_path: Path):
        f = write_source_file(
            tmp_path / "multi.py",
            textwrap.dedent("""\
                api_key = "key_abcdefghij"
                auth_token = "tokentokentok"
            """),
        )
        violations = _scan_file_for_secrets(f, [], "error")
        assert len(violations) == 2
        assert {v.line_number for v in violations} == {1, 2}

    def test_pem_key_multiline_detected_on_header_line(self, tmp_path: Path):
        f = write_source_file(
            tmp_path / "key.py",
            textwrap.dedent("""\
                private_key = \"\"\"
                -----BEGIN EC PRIVATE KEY-----
                MHQCAQEEIBkg4EXAMPLEKEY
                -----END EC PRIVATE KEY-----
                \"\"\"
            """),
        )
        violations = _scan_file_for_secrets(f, [], "error")
        assert any(v.rule_id == "pem-private-key" for v in violations)

    def test_aws_access_key_detected(self, tmp_path: Path):
        f = write_source_file(tmp_path / "cfg.py", "key = AKIAIOSFODNN7EXAMPLE\n")
        violations = _scan_file_for_secrets(f, [], "error")
        assert any(v.rule_id == "aws-access-key-id" for v in violations)


# ---------------------------------------------------------------------------
# _SecretScanner (whole-tree scan)
# ---------------------------------------------------------------------------


class TestSecretScanner:
    def test_empty_repo_returns_no_violations(self, tmp_path: Path):
        scanner = _SecretScanner([], fail_on_error=True)
        assert scanner.scan(tmp_path) == []

    def test_clean_repo_returns_no_violations(self, tmp_path: Path):
        write_source_file(
            tmp_path / "app.py",
            'password = os.environ.get("DB_PASS")\n',
        )
        scanner = _SecretScanner([], fail_on_error=True)
        assert scanner.scan(tmp_path) == []

    def test_secret_in_nested_file_detected(self, tmp_path: Path):
        write_source_file(
            tmp_path / "src" / "config.py",
            'api_key = "realapikey99999"\n',
        )
        scanner = _SecretScanner([], fail_on_error=True)
        violations = scanner.scan(tmp_path)
        assert len(violations) == 1
        assert violations[0].kind == "hardcoded_secret"

    def test_venv_directory_skipped(self, tmp_path: Path):
        write_source_file(
            tmp_path / ".venv" / "lib" / "site.py",
            'password = "venv_should_be_skipped"\n',
        )
        scanner = _SecretScanner([], fail_on_error=True)
        assert scanner.scan(tmp_path) == []

    def test_node_modules_directory_skipped(self, tmp_path: Path):
        write_source_file(
            tmp_path / "node_modules" / "pkg" / "index.js",
            'const api_key = "shouldbefiltered123";\n',
        )
        scanner = _SecretScanner([], fail_on_error=True)
        assert scanner.scan(tmp_path) == []

    def test_multiple_files_aggregated(self, tmp_path: Path):
        write_source_file(tmp_path / "a.py", 'password = "pass_from_a"\n')
        write_source_file(tmp_path / "b.py", 'password = "pass_from_b"\n')
        scanner = _SecretScanner([], fail_on_error=True)
        violations = scanner.scan(tmp_path)
        assert len(violations) == 2


# ---------------------------------------------------------------------------
# _find_audit_report
# ---------------------------------------------------------------------------


class TestFindAuditReport:
    def test_returns_none_when_no_report(self, tmp_path: Path):
        assert _find_audit_report(tmp_path) is None

    def test_finds_pip_audit_report(self, tmp_path: Path):
        rpt = tmp_path / "pip-audit-report.json"
        rpt.write_text("[]", encoding="utf-8")
        assert _find_audit_report(tmp_path) == rpt

    def test_finds_npm_audit_report(self, tmp_path: Path):
        rpt = tmp_path / "npm-audit.json"
        rpt.write_text("{}", encoding="utf-8")
        assert _find_audit_report(tmp_path) == rpt

    def test_first_match_returned(self, tmp_path: Path):
        """When multiple report files exist, the first in _AUDIT_REPORT_NAMES wins."""
        first_name = _AUDIT_REPORT_NAMES[0]
        (tmp_path / first_name).write_text("[]", encoding="utf-8")
        (tmp_path / "npm-audit.json").write_text("{}", encoding="utf-8")
        assert _find_audit_report(tmp_path) == tmp_path / first_name


# ---------------------------------------------------------------------------
# _parse_pip_audit_report
# ---------------------------------------------------------------------------


class TestParsePipAuditReport:
    def test_no_vulns_returns_empty(self):
        data = [{"name": "safe-pkg", "version": "1.0.0", "vulns": []}]
        result = _parse_pip_audit_report(data, "HIGH", [], "error")
        assert result == []

    def test_high_severity_vuln_at_high_threshold_reported(self):
        data = [make_vuln(severity="HIGH")]
        result = _parse_pip_audit_report(data, "HIGH", [], "error")
        assert len(result) == 1
        assert result[0].kind == "vulnerable_dependency"

    def test_medium_severity_vuln_suppressed_at_high_threshold(self):
        data = [make_vuln(severity="MEDIUM")]
        result = _parse_pip_audit_report(data, "HIGH", [], "error")
        assert result == []

    def test_medium_severity_vuln_reported_at_medium_threshold(self):
        data = [make_vuln(severity="MEDIUM")]
        result = _parse_pip_audit_report(data, "MEDIUM", [], "error")
        assert len(result) == 1

    def test_critical_vuln_always_reported_above_any_threshold(self):
        data = [make_vuln(severity="CRITICAL")]
        for threshold in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            result = _parse_pip_audit_report(data, threshold, [], "error")
            assert len(result) == 1, f"CRITICAL should be reported at threshold {threshold}"

    def test_unknown_severity_treated_as_high(self):
        data = [make_vuln(severity="UNKNOWN")]
        # Should appear at HIGH threshold
        assert len(_parse_pip_audit_report(data, "HIGH", [], "error")) == 1
        # Should NOT appear at CRITICAL threshold
        assert _parse_pip_audit_report(data, "CRITICAL", [], "error") == []

    def test_ignore_by_primary_id(self):
        data = [make_vuln(vuln_id="CVE-2023-99999")]
        result = _parse_pip_audit_report(data, "HIGH", ["CVE-2023-99999"], "error")
        assert result == []

    def test_ignore_by_alias(self):
        data = [make_vuln(vuln_id="PYSEC-2023-74", aliases=["CVE-2023-32681"])]
        result = _parse_pip_audit_report(data, "HIGH", ["CVE-2023-32681"], "error")
        assert result == []

    def test_violation_message_contains_package_and_version(self):
        data = [make_vuln(pkg_name="requests", version="2.28.0")]
        result = _parse_pip_audit_report(data, "HIGH", [], "error")
        assert "requests" in result[0].message
        assert "2.28.0" in result[0].message

    def test_violation_message_contains_fix_versions(self):
        data = [make_vuln(fix_versions=["2.31.0", "3.0.0"])]
        result = _parse_pip_audit_report(data, "HIGH", [], "error")
        assert "2.31.0" in result[0].message

    def test_long_description_truncated(self):
        long_desc = "X" * 300
        data = [make_vuln(description=long_desc)]
        result = _parse_pip_audit_report(data, "HIGH", [], "error")
        # message should not exceed reasonable length
        assert len(result[0].message) < 400

    def test_rule_id_set_to_vuln_id(self):
        data = [make_vuln(vuln_id="PYSEC-2024-42")]
        result = _parse_pip_audit_report(data, "HIGH", [], "error")
        assert result[0].rule_id == "PYSEC-2024-42"

    def test_fail_on_error_false_yields_warning(self):
        data = [make_vuln(severity="HIGH")]
        result = _parse_pip_audit_report(data, "HIGH", [], "warning")
        assert result[0].severity == "warning"

    def test_non_list_data_returns_empty(self):
        assert _parse_pip_audit_report({"error": "not a list"}, "HIGH", [], "error") == []

    def test_multiple_packages_multiple_vulns(self):
        data = [
            make_vuln("pkg-a", "1.0", "CVE-A"),
            make_vuln("pkg-b", "2.0", "CVE-B"),
        ]
        result = _parse_pip_audit_report(data, "HIGH", [], "error")
        assert len(result) == 2

    def test_vuln_without_fix_versions(self):
        data = [make_vuln(fix_versions=[])]
        result = _parse_pip_audit_report(data, "HIGH", [], "error")
        assert len(result) == 1
        assert "Upgrade to" not in result[0].message

    def test_pkg_without_explicit_severity_defaults_high(self):
        """Vulnerability entries missing 'severity' key should default to HIGH."""
        data = [
            {
                "name": "legacy-pkg",
                "version": "0.1.0",
                "vulns": [
                    {
                        "id": "PYSEC-OLD-1",
                        "description": "Old advisory without severity.",
                        "fix_versions": [],
                        "aliases": [],
                        # 'severity' key intentionally absent
                    }
                ],
            }
        ]
        # Should appear at HIGH threshold
        assert len(_parse_pip_audit_report(data, "HIGH", [], "error")) == 1
        # Should be suppressed at CRITICAL threshold
        assert _parse_pip_audit_report(data, "CRITICAL", [], "error") == []


# ---------------------------------------------------------------------------
# _DependencyAuditor
# ---------------------------------------------------------------------------


class TestDependencyAuditor:
    def test_missing_report_returns_warning_violation(self, tmp_path: Path):
        auditor = _DependencyAuditor("HIGH", [], fail_on_error=True)
        violations = auditor.audit(tmp_path)
        assert len(violations) == 1
        assert violations[0].kind == "missing_audit_report"
        assert violations[0].severity == "warning"  # always advisory

    def test_missing_report_message_lists_expected_names(self, tmp_path: Path):
        auditor = _DependencyAuditor("HIGH", [], fail_on_error=True)
        violations = auditor.audit(tmp_path)
        assert "pip-audit-report.json" in violations[0].message

    def test_corrupt_report_returns_error_violation(self, tmp_path: Path):
        (tmp_path / "pip-audit-report.json").write_text("{not valid json", encoding="utf-8")
        auditor = _DependencyAuditor("HIGH", [], fail_on_error=True)
        violations = auditor.audit(tmp_path)
        assert len(violations) == 1
        assert violations[0].kind == "missing_audit_report"
        assert violations[0].severity == "error"

    def test_clean_report_returns_no_violations(self, tmp_path: Path):
        write_audit_report(
            tmp_path / "pip-audit-report.json",
            [{"name": "safe-lib", "version": "1.0", "vulns": []}],
        )
        auditor = _DependencyAuditor("HIGH", [], fail_on_error=True)
        assert auditor.audit(tmp_path) == []

    def test_high_severity_vuln_reported(self, tmp_path: Path):
        write_audit_report(
            tmp_path / "pip-audit-report.json",
            [make_vuln(severity="HIGH")],
        )
        auditor = _DependencyAuditor("HIGH", [], fail_on_error=True)
        violations = auditor.audit(tmp_path)
        assert len(violations) == 1
        assert violations[0].kind == "vulnerable_dependency"

    def test_medium_vuln_suppressed_at_high_threshold(self, tmp_path: Path):
        write_audit_report(
            tmp_path / "pip-audit-report.json",
            [make_vuln(severity="MEDIUM")],
        )
        auditor = _DependencyAuditor("HIGH", [], fail_on_error=True)
        assert auditor.audit(tmp_path) == []

    def test_ignore_id_suppresses_vuln(self, tmp_path: Path):
        write_audit_report(
            tmp_path / "pip-audit-report.json",
            [make_vuln(vuln_id="CVE-2023-00001")],
        )
        auditor = _DependencyAuditor("HIGH", ["CVE-2023-00001"], fail_on_error=True)
        assert auditor.audit(tmp_path) == []

    def test_fail_on_error_false_yields_warning(self, tmp_path: Path):
        write_audit_report(
            tmp_path / "pip-audit-report.json",
            [make_vuln(severity="HIGH")],
        )
        auditor = _DependencyAuditor("HIGH", [], fail_on_error=False)
        violations = auditor.audit(tmp_path)
        assert violations[0].severity == "warning"


# ---------------------------------------------------------------------------
# Unsafe input handling patterns
# ---------------------------------------------------------------------------


class TestUnsafeInputPatterns:
    """Each regex in _UNSAFE_INPUT_PATTERNS is exercised with positive and negative samples."""

    def _check_pattern(self, rule_id: str, text: str) -> bool:
        for rid, pattern in _UNSAFE_INPUT_PATTERNS:
            if rid == rule_id:
                return bool(pattern.search(text))
        raise KeyError(f"Rule '{rule_id}' not found in _UNSAFE_INPUT_PATTERNS")

    def test_eval_user_input_matches(self):
        assert self._check_pattern("eval-user-input", "result = eval(request.data)")

    def test_eval_with_method_call_matches(self):
        assert self._check_pattern("eval-user-input", "eval(request.get_json()['cmd'])")

    def test_eval_without_request_ignored(self):
        assert not self._check_pattern("eval-user-input", "result = eval('1 + 1')")

    def test_exec_user_input_matches(self):
        assert self._check_pattern("exec-user-input", "exec(request.form['code'])")

    def test_exec_without_request_ignored(self):
        assert not self._check_pattern("exec-user-input", "exec('print(42)')")

    def test_sql_string_format_cursor_matches(self):
        assert self._check_pattern(
            "sql-string-format",
            "cursor.execute('SELECT * FROM t WHERE id=' + request.args.get('id'))",
        )

    def test_sql_string_format_connection_matches(self):
        assert self._check_pattern(
            "sql-string-format",
            "connection.execute(f\"SELECT ... {request.json['q']}\")",
        )

    def test_sql_safe_parameterised_query_ignored(self):
        assert not self._check_pattern(
            "sql-string-format",
            "cursor.execute('SELECT * FROM t WHERE id = ?', (user_id,))",
        )

    def test_pickle_user_input_matches(self):
        assert self._check_pattern("pickle-user-input", "pickle.load(request.data)")
        assert self._check_pattern("pickle-user-input", "pickle.loads(request.get_data())")

    def test_pickle_without_request_ignored(self):
        assert not self._check_pattern("pickle-user-input", "pickle.loads(cached_bytes)")

    def test_shell_injection_os_system_matches(self):
        assert self._check_pattern(
            "shell-injection",
            "os.system('ls ' + request.args.get('dir'))",
        )

    def test_shell_injection_subprocess_run_matches(self):
        assert self._check_pattern(
            "shell-injection",
            "subprocess.run(['cmd', request.form['arg']])",
        )

    def test_shell_injection_without_request_ignored(self):
        assert not self._check_pattern(
            "shell-injection",
            "subprocess.run(['pytest', '--tb=short'])",
        )


# ---------------------------------------------------------------------------
# _scan_file_for_unsafe_input
# ---------------------------------------------------------------------------


class TestScanFileForUnsafeInput:
    def test_clean_file_returns_no_violations(self, tmp_path: Path):
        f = write_source_file(
            tmp_path / "views.py",
            textwrap.dedent("""\
                user_id = int(request.args.get("id", 0))
                cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            """),
        )
        result = _scan_file_for_unsafe_input(f, [], "error")
        assert result == []

    def test_eval_detected(self, tmp_path: Path):
        f = write_source_file(
            tmp_path / "unsafe.py",
            "output = eval(request.data)\n",
        )
        violations = _scan_file_for_unsafe_input(f, [], "error")
        assert len(violations) == 1
        assert violations[0].rule_id == "eval-user-input"
        assert violations[0].kind == "unsafe_input_handling"
        assert violations[0].line_number == 1

    def test_violation_contains_file_path(self, tmp_path: Path):
        f = write_source_file(tmp_path / "bad.py", "exec(request.form['cmd'])\n")
        violations = _scan_file_for_unsafe_input(f, [], "error")
        assert violations[0].file_path == f

    def test_ignore_id_suppresses_violation(self, tmp_path: Path):
        f = write_source_file(tmp_path / "bad.py", "exec(request.form['cmd'])\n")
        violations = _scan_file_for_unsafe_input(f, ["exec-user-input"], "error")
        assert violations == []

    def test_fail_on_error_false_yields_warning(self, tmp_path: Path):
        f = write_source_file(tmp_path / "bad.py", "eval(request.data)\n")
        violations = _scan_file_for_unsafe_input(f, [], "warning")
        assert violations[0].severity == "warning"

    def test_multiple_patterns_on_different_lines(self, tmp_path: Path):
        f = write_source_file(
            tmp_path / "multi.py",
            textwrap.dedent("""\
                eval(request.data)
                os.system('rm ' + request.args.get('path'))
            """),
        )
        violations = _scan_file_for_unsafe_input(f, [], "error")
        assert len(violations) == 2
        rule_ids = {v.rule_id for v in violations}
        assert "eval-user-input" in rule_ids
        assert "shell-injection" in rule_ids


# ---------------------------------------------------------------------------
# _InputValidationChecker (whole-tree scan)
# ---------------------------------------------------------------------------


class TestInputValidationChecker:
    def test_empty_repo_returns_no_violations(self, tmp_path: Path):
        checker = _InputValidationChecker([], fail_on_error=True)
        assert checker.check(tmp_path) == []

    def test_clean_repo_returns_no_violations(self, tmp_path: Path):
        write_source_file(
            tmp_path / "app.py",
            "user_id = int(request.args.get('id', 0))\n",
        )
        checker = _InputValidationChecker([], fail_on_error=True)
        assert checker.check(tmp_path) == []

    def test_unsafe_pattern_in_py_file_detected(self, tmp_path: Path):
        write_source_file(
            tmp_path / "views.py",
            "result = eval(request.data)\n",
        )
        checker = _InputValidationChecker([], fail_on_error=True)
        violations = checker.check(tmp_path)
        assert len(violations) == 1
        assert violations[0].kind == "unsafe_input_handling"

    def test_unsafe_pattern_in_ts_file_detected(self, tmp_path: Path):
        write_source_file(
            tmp_path / "api.ts",
            "eval(request.body.code);\n",
        )
        checker = _InputValidationChecker([], fail_on_error=True)
        violations = checker.check(tmp_path)
        assert len(violations) == 1

    def test_non_source_files_skipped(self, tmp_path: Path):
        # .md file with pattern should not be scanned for input validation
        f = tmp_path / "NOTES.md"
        f.write_text("eval(request.data)\n", encoding="utf-8")
        checker = _InputValidationChecker([], fail_on_error=True)
        # .md is not in _INPUT_SCAN_EXTENSIONS
        assert checker.check(tmp_path) == []

    def test_venv_directory_skipped(self, tmp_path: Path):
        write_source_file(
            tmp_path / "venv" / "lib" / "evil.py",
            "eval(request.data)\n",
        )
        checker = _InputValidationChecker([], fail_on_error=True)
        assert checker.check(tmp_path) == []


# ---------------------------------------------------------------------------
# SecurityGate — disabled sub-checks
# ---------------------------------------------------------------------------


class TestDisabledSubChecks:
    def test_secrets_disabled_does_not_scan(self, tmp_path: Path):
        write_source_file(tmp_path / "app.py", 'password = "S3cr3tPass!"\n')
        cfg = SecurityGateConfig(
            scan_secrets=False,
            scan_dependencies=False,
            scan_input_validation=False,
        )
        result = SecurityGate(cfg).run(tmp_path)
        assert result.passed
        assert result.violations == []
        assert result.stats["secrets_found"] == 0

    def test_dependencies_disabled_skips_audit(self, tmp_path: Path):
        # No audit report on disk → would normally produce a warning
        cfg = SecurityGateConfig(
            scan_secrets=False,
            scan_dependencies=False,
            scan_input_validation=False,
        )
        result = SecurityGate(cfg).run(tmp_path)
        assert result.passed
        assert result.violations == []

    def test_input_validation_disabled_skips_check(self, tmp_path: Path):
        write_source_file(tmp_path / "app.py", "eval(request.data)\n")
        cfg = SecurityGateConfig(
            scan_secrets=False,
            scan_dependencies=False,
            scan_input_validation=False,
        )
        result = SecurityGate(cfg).run(tmp_path)
        assert result.passed
        assert result.violations == []


# ---------------------------------------------------------------------------
# SecurityGate — fail_on_error=False (advisory mode)
# ---------------------------------------------------------------------------


class TestAdvisoryMode:
    def test_secrets_advisory_mode_passes_with_warnings(self, tmp_path: Path):
        write_source_file(tmp_path / "app.py", 'password = "RealPassword123"\n')
        cfg = SecurityGateConfig(
            scan_secrets=True,
            scan_dependencies=False,
            scan_input_validation=False,
            fail_on_error=False,
        )
        result = SecurityGate(cfg).run(tmp_path)
        assert result.passed
        assert len(result.violations) == 1
        assert result.violations[0].severity == "warning"

    def test_vulnerable_deps_advisory_mode_passes_with_warnings(self, tmp_path: Path):
        write_audit_report(
            tmp_path / "pip-audit-report.json",
            [make_vuln(severity="CRITICAL")],
        )
        cfg = SecurityGateConfig(
            scan_secrets=False,
            scan_dependencies=True,
            scan_input_validation=False,
            fail_on_error=False,
        )
        result = SecurityGate(cfg).run(tmp_path)
        assert result.passed
        assert result.violations[0].severity == "warning"

    def test_unsafe_input_advisory_mode_passes_with_warnings(self, tmp_path: Path):
        write_source_file(tmp_path / "app.py", "eval(request.data)\n")
        cfg = SecurityGateConfig(
            scan_secrets=False,
            scan_dependencies=False,
            scan_input_validation=True,
            fail_on_error=False,
        )
        result = SecurityGate(cfg).run(tmp_path)
        assert result.passed
        assert result.violations[0].severity == "warning"


# ---------------------------------------------------------------------------
# SecurityGate — GateResult attributes
# ---------------------------------------------------------------------------


class TestGateResultAttributes:
    def test_stats_contains_expected_keys(self, tmp_path: Path):
        cfg = SecurityGateConfig(
            scan_secrets=False, scan_dependencies=False, scan_input_validation=False
        )
        result = SecurityGate(cfg).run(tmp_path)
        for key in (
            "secrets_found",
            "vulnerable_dependencies",
            "unsafe_input_patterns",
            "total_violations",
            "severity_threshold",
            "scan_secrets",
            "scan_dependencies",
            "scan_input_validation",
        ):
            assert key in result.stats, f"Missing stat key: {key}"

    def test_errors_helper_returns_error_severity(self, tmp_path: Path):
        write_source_file(tmp_path / "app.py", 'password = "RealPass123"\n')
        cfg = SecurityGateConfig(
            scan_secrets=True,
            scan_dependencies=False,
            scan_input_validation=False,
            fail_on_error=True,
        )
        result = SecurityGate(cfg).run(tmp_path)
        assert all(v.severity == "error" for v in result.errors())

    def test_warnings_helper_returns_warning_severity(self, tmp_path: Path):
        write_source_file(tmp_path / "app.py", 'password = "RealPass123"\n')
        cfg = SecurityGateConfig(
            scan_secrets=True,
            scan_dependencies=False,
            scan_input_validation=False,
            fail_on_error=False,
        )
        result = SecurityGate(cfg).run(tmp_path)
        assert all(v.severity == "warning" for v in result.warnings())

    def test_by_kind_filters_correctly(self, tmp_path: Path):
        write_source_file(tmp_path / "app.py", 'password = "RealPass123"\n')
        write_source_file(tmp_path / "views.py", "eval(request.data)\n")
        write_audit_report(
            tmp_path / "pip-audit-report.json",
            [make_vuln(severity="HIGH")],
        )
        cfg = SecurityGateConfig(
            scan_secrets=True,
            scan_dependencies=True,
            scan_input_validation=True,
            fail_on_error=True,
        )
        result = SecurityGate(cfg).run(tmp_path)
        assert all(v.kind == "hardcoded_secret" for v in result.by_kind("hardcoded_secret"))
        assert all(
            v.kind == "vulnerable_dependency"
            for v in result.by_kind("vulnerable_dependency")
        )
        assert all(
            v.kind == "unsafe_input_handling"
            for v in result.by_kind("unsafe_input_handling")
        )

    def test_total_violations_count_matches(self, tmp_path: Path):
        write_source_file(tmp_path / "app.py", 'password = "RealPass123"\n')
        cfg = SecurityGateConfig(
            scan_secrets=True,
            scan_dependencies=False,
            scan_input_validation=False,
        )
        result = SecurityGate(cfg).run(tmp_path)
        assert result.stats["total_violations"] == len(result.violations)

    def test_violation_summary_contains_kind(self, tmp_path: Path):
        write_source_file(tmp_path / "app.py", 'password = "RealPass123"\n')
        cfg = SecurityGateConfig(
            scan_secrets=True,
            scan_dependencies=False,
            scan_input_validation=False,
        )
        result = SecurityGate(cfg).run(tmp_path)
        summary = result.violations[0].summary()
        assert "hardcoded_secret" in summary

    def test_violation_summary_contains_file_path(self, tmp_path: Path):
        write_source_file(tmp_path / "app.py", 'password = "RealPass123"\n')
        cfg = SecurityGateConfig(
            scan_secrets=True,
            scan_dependencies=False,
            scan_input_validation=False,
        )
        result = SecurityGate(cfg).run(tmp_path)
        summary = result.violations[0].summary()
        assert "app.py" in summary

    def test_violation_summary_contains_rule_id(self, tmp_path: Path):
        write_source_file(tmp_path / "app.py", 'password = "RealPass123"\n')
        cfg = SecurityGateConfig(
            scan_secrets=True,
            scan_dependencies=False,
            scan_input_validation=False,
        )
        result = SecurityGate(cfg).run(tmp_path)
        summary = result.violations[0].summary()
        assert "hardcoded-password" in summary


# ---------------------------------------------------------------------------
# SecurityGate — default configuration
# ---------------------------------------------------------------------------


class TestDefaultConfig:
    def test_default_severity_threshold_is_high(self):
        cfg = SecurityGateConfig()
        assert cfg.severity_threshold == "HIGH"

    def test_default_scan_dependencies_is_true(self):
        cfg = SecurityGateConfig()
        assert cfg.scan_dependencies is True

    def test_default_scan_secrets_is_false(self):
        cfg = SecurityGateConfig()
        assert cfg.scan_secrets is False

    def test_default_scan_input_validation_is_true(self):
        cfg = SecurityGateConfig()
        assert cfg.scan_input_validation is True

    def test_default_fail_on_error_is_true(self):
        cfg = SecurityGateConfig()
        assert cfg.fail_on_error is True

    def test_gate_uses_default_config_when_none_passed(self, tmp_path: Path):
        """SecurityGate() with no args should use SecurityGateConfig defaults."""
        result = SecurityGate().run(tmp_path)
        # Default: scan_dependencies=True → missing report → warning (not error)
        # No secrets or input violations in empty repo
        assert result.passed
        assert result.stats["severity_threshold"] == "HIGH"


# ---------------------------------------------------------------------------
# Integration: end-to-end scenarios
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_fully_clean_repo_passes_all_checks(self, tmp_path: Path):
        """A repo with safe code, clean deps, and no unsafe input should pass."""
        write_source_file(
            tmp_path / "app.py",
            textwrap.dedent("""\
                import os
                DB_PASS = os.environ["DB_PASSWORD"]
                user_id = int(request.args.get("id", 0))
                cursor.execute("SELECT * FROM t WHERE id = ?", (user_id,))
            """),
        )
        write_audit_report(
            tmp_path / "pip-audit-report.json",
            [{"name": "safe-lib", "version": "1.0.0", "vulns": []}],
        )
        cfg = SecurityGateConfig(
            scan_secrets=True,
            scan_dependencies=True,
            scan_input_validation=True,
        )
        result = SecurityGate(cfg).run(tmp_path)
        assert result.passed
        assert result.violations == []

    def test_repo_with_all_three_issues_fails(self, tmp_path: Path):
        """A repo with a secret, a CVE, and unsafe input should fail."""
        write_source_file(
            tmp_path / "app.py",
            textwrap.dedent("""\
                password = "HardcodedPass99"
                eval(request.data)
            """),
        )
        write_audit_report(
            tmp_path / "pip-audit-report.json",
            [make_vuln(severity="HIGH")],
        )
        cfg = SecurityGateConfig(
            scan_secrets=True,
            scan_dependencies=True,
            scan_input_validation=True,
            fail_on_error=True,
        )
        result = SecurityGate(cfg).run(tmp_path)
        assert not result.passed
        kinds = {v.kind for v in result.violations}
        assert "hardcoded_secret" in kinds
        assert "vulnerable_dependency" in kinds
        assert "unsafe_input_handling" in kinds

    def test_ignore_list_suppresses_all_known_issues(self, tmp_path: Path):
        """When every violation is ignored, the gate should pass cleanly."""
        write_source_file(tmp_path / "app.py", 'password = "HardcodedPass99"\n')
        write_audit_report(
            tmp_path / "pip-audit-report.json",
            [make_vuln(vuln_id="CVE-2023-KNOWN")],
        )
        cfg = SecurityGateConfig(
            scan_secrets=True,
            scan_dependencies=True,
            scan_input_validation=False,
            fail_on_error=True,
            ignore_ids=["hardcoded-password", "CVE-2023-KNOWN"],
        )
        result = SecurityGate(cfg).run(tmp_path)
        assert result.passed
        assert result.by_kind("hardcoded_secret") == []
        assert result.by_kind("vulnerable_dependency") == []

    def test_missing_report_produces_warning_not_error(self, tmp_path: Path):
        """A missing audit report is always advisory — never blocks the gate."""
        cfg = SecurityGateConfig(
            scan_secrets=False,
            scan_dependencies=True,
            scan_input_validation=False,
            fail_on_error=True,
        )
        result = SecurityGate(cfg).run(tmp_path)
        # Gate should still pass because missing_audit_report is a warning
        assert result.passed
        assert result.violations[0].kind == "missing_audit_report"
        assert result.violations[0].severity == "warning"

    def test_stats_secrets_found_incremented(self, tmp_path: Path):
        write_source_file(tmp_path / "a.py", 'password = "PassA123456"\n')
        write_source_file(tmp_path / "b.py", 'password = "PassB654321"\n')
        cfg = SecurityGateConfig(
            scan_secrets=True,
            scan_dependencies=False,
            scan_input_validation=False,
        )
        result = SecurityGate(cfg).run(tmp_path)
        assert result.stats["secrets_found"] == 2

    def test_stats_vulnerable_deps_count_matches(self, tmp_path: Path):
        write_audit_report(
            tmp_path / "pip-audit-report.json",
            [
                make_vuln("pkg-a", vuln_id="CVE-A"),
                make_vuln("pkg-b", vuln_id="CVE-B"),
            ],
        )
        cfg = SecurityGateConfig(
            scan_secrets=False,
            scan_dependencies=True,
            scan_input_validation=False,
        )
        result = SecurityGate(cfg).run(tmp_path)
        assert result.stats["vulnerable_dependencies"] == 2
