"""
tests/gates/test_security.py
==============================
Unit and integration tests for :mod:`harness_skills.gates.security`.

Test strategy
-------------
**Secret scanning (scan_secrets)**
* Each :data:`~harness_skills.gates.security._SECRET_PATTERNS` rule fires on a
  minimal synthetic fixture that contains only the target pattern.
* Benign files (no secrets, template placeholders, placeholder strings) produce
  zero violations.
* ``ignore_ids`` suppresses the corresponding rule.
* ``fail_on_error=False`` downgrades all findings from ``error`` to ``warning``
  and the sub-gate still passes.
* Binary files are not scanned (no NUL-containing files are inspected).
* Files inside ``_SKIP_DIRS`` directories are skipped.
* The ``summary()`` method returns a human-readable one-liner.

**Dependency vulnerability audit (audit_dependencies)**
* A clean ``pip-audit`` run (mocked ``returncode=0``, empty JSON) → passes.
* A run with one HIGH vulnerability → produces an ``error`` violation.
* Severity below ``severity_threshold`` → violation suppressed.
* CVE in ``ignore_ids`` → violation suppressed.
* ``pip-audit`` not installed (``FileNotFoundError``) → advisory warning, gate passes.
* ``pip-audit`` timeout → advisory warning, gate passes.
* ``pip-audit`` exits with unexpected code (e.g. 2) → advisory warning, gate passes.
* Malformed JSON → gate passes without crashing.
* ``fail_on_error=False`` → findings become warnings.

**Input validation verification (verify_input_validation)**
* Each :data:`~harness_skills.gates.security._INPUT_VALIDATION_PATTERNS` rule
  fires on a synthetic Python file that imports Flask and contains the
  dangerous pattern.
* A clean Python file (no dangerous patterns) → zero violations.
* ``ignore_ids`` suppresses specific rules.
* Files that do NOT import a web framework are skipped (AST pre-filter).
* Non-Python files are not scanned.
* Unparseable (syntax-error) Python files fall through to regex scan.
* ``fail_on_error=False`` downgrades findings.

**SecurityGate (integration)**
* ``run()`` aggregates results from all three sub-gates.
* Selecting a single sub-gate via ``gates=("secrets",)`` runs only that gate.
* ``scan_secrets=False`` skips the secrets sub-gate even if it is in ``gates``.
* ``scan_dependencies=False`` skips the dependency sub-gate.
* ``GateResult`` stats are populated correctly.
* ``passed`` is ``False`` when any sub-gate fails.
* ``passed`` is ``True`` when all sub-gates pass.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from harness_skills.gates.security import (
    ALL_SUB_GATES,
    GateResult,
    SecurityGate,
    SecurityViolation,
    SubGateResult,
    _ast_has_request_import,
    _collect_python_files,
    _is_text_file,
    _repo_rel,
    _should_scan,
    audit_dependencies,
    scan_secrets,
    verify_input_validation,
)
from harness_skills.models.gate_configs import SecurityGateConfig


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _write(tmp_path: Path, name: str, content: str) -> Path:
    """Write *content* to *tmp_path / name* and return the path."""
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def _cfg(**kwargs) -> SecurityGateConfig:
    """Return a :class:`SecurityGateConfig` with sane test defaults."""
    defaults = {
        "severity_threshold": "HIGH",
        "scan_secrets": True,
        "scan_dependencies": True,
        "fail_on_error": True,
        "ignore_ids": [],
    }
    defaults.update(kwargs)
    return SecurityGateConfig(**defaults)


# ---------------------------------------------------------------------------
# Shared helper tests
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_repo_rel_within_root(self, tmp_path: Path) -> None:
        child = tmp_path / "src" / "app.py"
        assert _repo_rel(child, tmp_path) == "src/app.py"

    def test_repo_rel_outside_root(self, tmp_path: Path) -> None:
        outside = Path("/etc/passwd")
        result = _repo_rel(outside, tmp_path)
        assert result == "/etc/passwd"

    def test_is_text_file_text(self, tmp_path: Path) -> None:
        f = tmp_path / "hello.txt"
        f.write_text("hello world", encoding="utf-8")
        assert _is_text_file(f) is True

    def test_is_text_file_binary(self, tmp_path: Path) -> None:
        f = tmp_path / "data.bin"
        f.write_bytes(b"\x00\x01\x02\x03")
        assert _is_text_file(f) is False

    def test_should_scan_py(self, tmp_path: Path) -> None:
        f = tmp_path / "app.py"
        f.touch()
        assert _should_scan(f) is True

    def test_should_scan_skip_venv(self, tmp_path: Path) -> None:
        f = tmp_path / ".venv" / "lib" / "site-packages" / "pkg.py"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.touch()
        assert _should_scan(f) is False

    def test_should_scan_skip_git(self, tmp_path: Path) -> None:
        f = tmp_path / ".git" / "config"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.touch()
        assert _should_scan(f) is False

    def test_collect_python_files_excludes_venv(self, tmp_path: Path) -> None:
        (tmp_path / "app.py").write_text("x = 1")
        venv_file = tmp_path / ".venv" / "lib" / "foo.py"
        venv_file.parent.mkdir(parents=True, exist_ok=True)
        venv_file.write_text("x = 1")
        files = _collect_python_files(tmp_path)
        assert any(f.name == "app.py" for f in files)
        assert not any(".venv" in str(f) for f in files)

    def test_ast_has_request_import_flask(self, tmp_path: Path) -> None:
        import ast

        source = "from flask import request\n\n@app.route('/')\ndef view(): pass\n"
        tree = ast.parse(source)
        assert _ast_has_request_import(tree) is True

    def test_ast_has_request_import_no_framework(self, tmp_path: Path) -> None:
        import ast

        source = "import os\nimport sys\n"
        tree = ast.parse(source)
        assert _ast_has_request_import(tree) is False

    def test_security_violation_summary(self) -> None:
        v = SecurityViolation(
            kind="secret_detected",
            severity="error",
            sub_gate="secrets",
            message="Hardcoded token",
            rule_id="SEC001",
            file_path=Path("src/app.py"),
            line_number=42,
        )
        s = v.summary()
        assert "ERROR" in s
        assert "SEC001" in s
        assert "src/app.py" in s
        assert "42" in s


# ---------------------------------------------------------------------------
# Sub-gate 1: Secret scanning
# ---------------------------------------------------------------------------


class TestScanSecrets:
    # ── Rule fires ──────────────────────────────────────────────────────────

    def test_sec001_generic_password(self, tmp_path: Path) -> None:
        _write(tmp_path, "config.py", 'password = "SuperSecret123!"\n')
        result = scan_secrets(tmp_path, _cfg())
        rule_ids = {v.rule_id for v in result.violations}
        assert "SEC001" in rule_ids
        assert not result.passed

    def test_sec002_private_key(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "key.py",
            '"""-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAK...\n"""\n',
        )
        result = scan_secrets(tmp_path, _cfg())
        rule_ids = {v.rule_id for v in result.violations}
        assert "SEC002" in rule_ids

    def test_sec003_aws_credentials(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "aws.py",
            'AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"\n',
        )
        result = scan_secrets(tmp_path, _cfg())
        rule_ids = {v.rule_id for v in result.violations}
        assert "SEC003" in rule_ids

    def test_sec004_openai_key(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "ai.py",
            'OPENAI_API_KEY = "sk-abcdefghijklmnopqrstuvwxyz1234567890abcd"\n',
        )
        result = scan_secrets(tmp_path, _cfg())
        rule_ids = {v.rule_id for v in result.violations}
        assert "SEC004" in rule_ids

    def test_sec005_github_pat(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "ci.py",
            'token = "ghp_' + "A" * 36 + '"\n',
        )
        result = scan_secrets(tmp_path, _cfg())
        rule_ids = {v.rule_id for v in result.violations}
        assert "SEC005" in rule_ids

    def test_sec006_database_url(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "settings.py",
            'DATABASE_URL = "postgres://admin:s3cr3t@db.example.com:5432/prod"\n',
        )
        result = scan_secrets(tmp_path, _cfg())
        rule_ids = {v.rule_id for v in result.violations}
        assert "SEC006" in rule_ids

    def test_sec007_bearer_token(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "auth.py",
            'AUTH_HEADER = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9xxxxxxxx"\n',
        )
        result = scan_secrets(tmp_path, _cfg())
        rule_ids = {v.rule_id for v in result.violations}
        assert "SEC007" in rule_ids

    def test_sec008_hex_secret(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "app.py",
            'secret_key = "a3f1e2d4c5b6a7f8e9d0c1b2a3f4e5d6c7b8a9f0e1d2c3b4a5f6e7d8c9b0a1b2"\n',
        )
        result = scan_secrets(tmp_path, _cfg())
        rule_ids = {v.rule_id for v in result.violations}
        assert "SEC008" in rule_ids

    # ── No false positive on clean file ─────────────────────────────────────

    def test_clean_file_passes(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "clean.py",
            """\
            import os

            SECRET_KEY = os.environ["SECRET_KEY"]
            DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///dev.db")
            """,
        )
        result = scan_secrets(tmp_path, _cfg())
        assert result.passed
        assert result.violations == []

    # ── ignore_ids suppresses specific rule ─────────────────────────────────

    def test_ignore_ids_suppresses_rule(self, tmp_path: Path) -> None:
        _write(tmp_path, "cfg.py", 'password = "MyPassword12345!"\n')
        result = scan_secrets(tmp_path, _cfg(ignore_ids=["SEC001"]))
        assert "SEC001" not in {v.rule_id for v in result.violations}

    # ── fail_on_error=False → advisory mode ─────────────────────────────────

    def test_fail_on_error_false_makes_advisory(self, tmp_path: Path) -> None:
        _write(tmp_path, "cfg.py", 'password = "HardCodedSecret99!"\n')
        result = scan_secrets(tmp_path, _cfg(fail_on_error=False))
        assert result.passed  # gate passes in advisory mode
        assert all(v.severity == "warning" for v in result.violations)

    # ── Binary files are not scanned ─────────────────────────────────────────

    def test_binary_file_skipped(self, tmp_path: Path) -> None:
        f = tmp_path / "data.bin"
        f.write_bytes(b"\x00\x01\x02password = 'abc'\x03")
        result = scan_secrets(tmp_path, _cfg())
        assert result.passed

    # ── Files inside skip dirs are not scanned ───────────────────────────────

    def test_skip_venv_directory(self, tmp_path: Path) -> None:
        venv_file = tmp_path / ".venv" / "lib" / "cfg.py"
        venv_file.parent.mkdir(parents=True, exist_ok=True)
        venv_file.write_text('password = "ShouldBeIgnored123!"\n', encoding="utf-8")
        result = scan_secrets(tmp_path, _cfg())
        assert result.passed

    # ── File path and line number are populated ──────────────────────────────

    def test_file_path_and_line_number_populated(self, tmp_path: Path) -> None:
        _write(tmp_path, "app.py", 'x = 1\npassword = "SomeSecret!"\n')
        result = scan_secrets(tmp_path, _cfg())
        assert result.violations
        v = result.violations[0]
        assert v.file_path is not None
        assert v.line_number == 2

    # ── YAML and .env files are scanned ─────────────────────────────────────

    def test_yaml_file_scanned(self, tmp_path: Path) -> None:
        _write(tmp_path, "config.yaml", 'db:\n  password: "HardCodedPwd123!"\n')
        result = scan_secrets(tmp_path, _cfg())
        assert not result.passed

    def test_env_file_scanned(self, tmp_path: Path) -> None:
        _write(tmp_path, ".env", 'API_KEY="sk-abcdefgh1234567890abcdef1234567890ab"\n')
        result = scan_secrets(tmp_path, _cfg())
        assert not result.passed


# ---------------------------------------------------------------------------
# Sub-gate 2: Dependency vulnerability audit
# ---------------------------------------------------------------------------


def _pip_audit_output(vulns: list[dict]) -> str:
    """Build a pip-audit JSON response with the supplied vulnerabilities."""
    deps = []
    for v in vulns:
        deps.append(
            {
                "name": v.get("name", "example-pkg"),
                "version": v.get("version", "1.0.0"),
                "vulns": [
                    {
                        "id": v.get("id", "CVE-2024-99999"),
                        "description": v.get("desc", "A test vulnerability"),
                        "severity": v.get("severity", "HIGH"),
                        "fix_versions": v.get("fix", ["2.0.0"]),
                    }
                ],
            }
        )
    return json.dumps({"dependencies": deps})


class TestAuditDependencies:
    # ── Clean run ────────────────────────────────────────────────────────────

    def test_clean_run_passes(self, tmp_path: Path) -> None:
        output = json.dumps({"dependencies": []})
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=output, stderr="")
            result = audit_dependencies(tmp_path, _cfg())
        assert result.passed
        assert result.violations == []

    # ── Vulnerability detected ────────────────────────────────────────────────

    def test_high_vuln_detected(self, tmp_path: Path) -> None:
        output = _pip_audit_output(
            [{"name": "vuln-pkg", "version": "1.0", "severity": "HIGH"}]
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout=output, stderr="")
            result = audit_dependencies(tmp_path, _cfg())
        assert not result.passed
        assert result.violations[0].kind == "vulnerable_dependency"
        assert result.violations[0].severity == "error"
        assert "CVE-2024-99999" in result.violations[0].message

    def test_critical_vuln_detected(self, tmp_path: Path) -> None:
        output = _pip_audit_output(
            [{"severity": "CRITICAL", "id": "CVE-2024-11111"}]
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout=output, stderr="")
            result = audit_dependencies(tmp_path, _cfg(severity_threshold="MEDIUM"))
        assert not result.passed

    # ── Severity below threshold is suppressed ───────────────────────────────

    def test_low_vuln_below_high_threshold_suppressed(self, tmp_path: Path) -> None:
        output = _pip_audit_output([{"severity": "LOW", "id": "CVE-2024-22222"}])
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout=output, stderr="")
            result = audit_dependencies(tmp_path, _cfg(severity_threshold="HIGH"))
        assert result.passed
        assert result.violations == []

    def test_medium_below_high_threshold_suppressed(self, tmp_path: Path) -> None:
        output = _pip_audit_output([{"severity": "MEDIUM", "id": "CVE-2024-33333"}])
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout=output, stderr="")
            result = audit_dependencies(tmp_path, _cfg(severity_threshold="HIGH"))
        assert result.passed

    def test_medium_at_medium_threshold_reported(self, tmp_path: Path) -> None:
        output = _pip_audit_output([{"severity": "MEDIUM", "id": "CVE-2024-44444"}])
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout=output, stderr="")
            result = audit_dependencies(tmp_path, _cfg(severity_threshold="MEDIUM"))
        assert not result.passed

    # ── ignore_ids suppresses specific CVE ───────────────────────────────────

    def test_ignore_ids_suppresses_cve(self, tmp_path: Path) -> None:
        output = _pip_audit_output([{"id": "CVE-2024-55555", "severity": "HIGH"}])
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout=output, stderr="")
            result = audit_dependencies(
                tmp_path, _cfg(ignore_ids=["CVE-2024-55555"])
            )
        assert result.passed
        assert result.violations == []

    # ── Tool not installed ────────────────────────────────────────────────────

    def test_tool_not_found_advisory_pass(self, tmp_path: Path) -> None:
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = audit_dependencies(tmp_path, _cfg())
        assert result.passed
        assert result.violations[0].kind == "tool_not_found"
        assert result.violations[0].severity == "warning"

    # ── Timeout ──────────────────────────────────────────────────────────────

    def test_timeout_advisory_pass(self, tmp_path: Path) -> None:
        import subprocess

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("pip_audit", 120)):
            result = audit_dependencies(tmp_path, _cfg())
        assert result.passed
        assert result.violations[0].rule_id == "DEP001"

    # ── Unexpected exit code ─────────────────────────────────────────────────

    def test_unexpected_exit_code_advisory_pass(self, tmp_path: Path) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=2, stdout="", stderr="crash")
            result = audit_dependencies(tmp_path, _cfg())
        assert result.passed
        assert result.violations[0].rule_id == "DEP002"

    # ── Malformed JSON ────────────────────────────────────────────────────────

    def test_malformed_json_passes(self, tmp_path: Path) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="{INVALID", stderr="")
            result = audit_dependencies(tmp_path, _cfg())
        assert result.passed

    # ── fail_on_error=False → advisory mode ──────────────────────────────────

    def test_fail_on_error_false_advisory(self, tmp_path: Path) -> None:
        output = _pip_audit_output([{"severity": "HIGH"}])
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout=output, stderr="")
            result = audit_dependencies(tmp_path, _cfg(fail_on_error=False))
        assert result.passed
        assert all(v.severity == "warning" for v in result.violations)

    # ── CVE fields are populated ──────────────────────────────────────────────

    def test_cve_field_populated(self, tmp_path: Path) -> None:
        cve = "CVE-2024-77777"
        output = _pip_audit_output([{"id": cve, "severity": "HIGH"}])
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout=output, stderr="")
            result = audit_dependencies(tmp_path, _cfg())
        v = result.violations[0]
        assert v.cve == cve
        assert v.rule_id == cve

    # ── Suggestion includes fix version ──────────────────────────────────────

    def test_suggestion_includes_fix_version(self, tmp_path: Path) -> None:
        output = _pip_audit_output(
            [{"name": "mypkg", "fix": ["3.1.4"], "severity": "HIGH"}]
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout=output, stderr="")
            result = audit_dependencies(tmp_path, _cfg())
        assert result.violations
        assert "3.1.4" in (result.violations[0].suggestion or "")


# ---------------------------------------------------------------------------
# Sub-gate 3: Input validation verification
# ---------------------------------------------------------------------------

#: Minimal Flask app header used in synthetic fixtures.
_FLASK_HEADER = "from flask import request, Flask\napp = Flask(__name__)\n\n"


def _flask_file(tmp_path: Path, name: str, body: str) -> Path:
    """Write a Flask route file to *tmp_path*."""
    return _write(tmp_path, name, _FLASK_HEADER + body)


class TestVerifyInputValidation:
    # ── Rule fires on dangerous patterns ────────────────────────────────────

    def test_inv001_sql_fstring(self, tmp_path: Path) -> None:
        _flask_file(
            tmp_path,
            "views.py",
            textwrap.dedent(
                """\
                @app.route('/search')
                def search():
                    q = request.args.get('q')
                    cursor.execute(f"SELECT * FROM items WHERE name = '{q}'")
                """
            ),
        )
        result = verify_input_validation(tmp_path, _cfg())
        rule_ids = {v.rule_id for v in result.violations}
        assert "INV001" in rule_ids

    def test_inv002_sql_direct_request(self, tmp_path: Path) -> None:
        _flask_file(
            tmp_path,
            "views.py",
            textwrap.dedent(
                """\
                @app.route('/user')
                def get_user():
                    cursor.execute("SELECT * FROM users WHERE id = " + request.args['id'])
                """
            ),
        )
        result = verify_input_validation(tmp_path, _cfg())
        rule_ids = {v.rule_id for v in result.violations}
        assert "INV002" in rule_ids

    def test_inv003_subprocess_request(self, tmp_path: Path) -> None:
        _flask_file(
            tmp_path,
            "views.py",
            textwrap.dedent(
                """\
                import subprocess
                @app.route('/run')
                def run_cmd():
                    subprocess.run(request.form['cmd'], shell=True)
                """
            ),
        )
        result = verify_input_validation(tmp_path, _cfg())
        rule_ids = {v.rule_id for v in result.violations}
        assert "INV003" in rule_ids

    def test_inv004_eval_request(self, tmp_path: Path) -> None:
        _flask_file(
            tmp_path,
            "views.py",
            textwrap.dedent(
                """\
                @app.route('/calc')
                def calc():
                    return str(eval(request.args.get('expr')))
                """
            ),
        )
        result = verify_input_validation(tmp_path, _cfg())
        rule_ids = {v.rule_id for v in result.violations}
        assert "INV004" in rule_ids

    def test_inv005_open_request(self, tmp_path: Path) -> None:
        _flask_file(
            tmp_path,
            "views.py",
            textwrap.dedent(
                """\
                @app.route('/file')
                def read_file():
                    with open(request.args['path']) as f:
                        return f.read()
                """
            ),
        )
        result = verify_input_validation(tmp_path, _cfg())
        rule_ids = {v.rule_id for v in result.violations}
        assert "INV005" in rule_ids

    def test_inv006_ssrf_requests(self, tmp_path: Path) -> None:
        _flask_file(
            tmp_path,
            "proxy.py",
            textwrap.dedent(
                """\
                import requests as http
                @app.route('/fetch')
                def fetch():
                    return http.get(request.args['url']).text
                """
            ),
        )
        result = verify_input_validation(tmp_path, _cfg())
        rule_ids = {v.rule_id for v in result.violations}
        assert "INV006" in rule_ids

    def test_inv007_ssti_render_template_string(self, tmp_path: Path) -> None:
        _flask_file(
            tmp_path,
            "views.py",
            textwrap.dedent(
                """\
                from flask import render_template_string
                @app.route('/greet')
                def greet():
                    return render_template_string(request.args['tmpl'])
                """
            ),
        )
        result = verify_input_validation(tmp_path, _cfg())
        rule_ids = {v.rule_id for v in result.violations}
        assert "INV007" in rule_ids

    def test_inv008_pickle_loads_request(self, tmp_path: Path) -> None:
        _flask_file(
            tmp_path,
            "views.py",
            textwrap.dedent(
                """\
                import pickle
                @app.route('/load')
                def load():
                    return str(pickle.loads(request.data))
                """
            ),
        )
        result = verify_input_validation(tmp_path, _cfg())
        rule_ids = {v.rule_id for v in result.violations}
        assert "INV008" in rule_ids

    # ── Clean file passes ────────────────────────────────────────────────────

    def test_clean_flask_file_passes(self, tmp_path: Path) -> None:
        _flask_file(
            tmp_path,
            "views.py",
            textwrap.dedent(
                """\
                from flask import abort, jsonify

                @app.route('/user/<int:user_id>')
                def get_user(user_id: int):
                    user = db.get_user(user_id)
                    if user is None:
                        abort(404)
                    return jsonify(user.to_dict())
                """
            ),
        )
        result = verify_input_validation(tmp_path, _cfg())
        assert result.passed

    # ── Non-framework file is skipped ────────────────────────────────────────

    def test_non_framework_file_skipped(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "util.py",
            textwrap.dedent(
                """\
                import os
                def run(cmd):
                    # no framework import — should be skipped
                    subprocess.run(request.args['x'])
                """
            ),
        )
        result = verify_input_validation(tmp_path, _cfg())
        # The file has no web-framework import — AST pre-filter skips it
        assert result.passed

    # ── Non-Python files are not scanned ────────────────────────────────────

    def test_non_python_file_not_scanned(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "views.js",
            "const sql = `SELECT * FROM t WHERE id = ${req.query.id}`;\n",
        )
        result = verify_input_validation(tmp_path, _cfg())
        assert result.passed  # JS files not in scope

    # ── ignore_ids suppresses specific rule ─────────────────────────────────

    def test_ignore_ids_suppresses_inv004(self, tmp_path: Path) -> None:
        _flask_file(
            tmp_path,
            "views.py",
            "@app.route('/calc')\ndef calc():\n    return str(eval(request.args['expr']))\n",
        )
        result = verify_input_validation(tmp_path, _cfg(ignore_ids=["INV004"]))
        assert "INV004" not in {v.rule_id for v in result.violations}

    # ── fail_on_error=False → advisory mode ─────────────────────────────────

    def test_fail_on_error_false_advisory(self, tmp_path: Path) -> None:
        _flask_file(
            tmp_path,
            "views.py",
            "@app.route('/eval')\ndef ev():\n    return eval(request.args['x'])\n",
        )
        result = verify_input_validation(tmp_path, _cfg(fail_on_error=False))
        assert result.passed
        assert all(v.severity == "warning" for v in result.violations)

    # ── Syntax-error Python files fall through to regex scan ─────────────────

    def test_syntax_error_file_still_scanned(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "broken.py",
            textwrap.dedent(
                """\
                from flask import request
                def view(
                    cursor.execute(f"SELECT * FROM t WHERE x = '{request.args['x']}'")
                """
            ),
        )
        result = verify_input_validation(tmp_path, _cfg())
        # Broken AST falls through to regex — INV001 or similar should fire
        rule_ids = {v.rule_id for v in result.violations}
        assert "INV001" in rule_ids

    # ── File path and line number are populated ──────────────────────────────

    def test_file_path_and_line_number(self, tmp_path: Path) -> None:
        _flask_file(
            tmp_path,
            "views.py",
            "\n\n\n@app.route('/')\ndef v():\n    return eval(request.args['x'])\n",
        )
        result = verify_input_validation(tmp_path, _cfg())
        v = next((x for x in result.violations if x.rule_id == "INV004"), None)
        assert v is not None
        assert v.file_path is not None
        assert v.line_number is not None and v.line_number > 0


# ---------------------------------------------------------------------------
# SecurityGate integration
# ---------------------------------------------------------------------------


class TestSecurityGate:
    # ── Default construction ─────────────────────────────────────────────────

    def test_default_config(self) -> None:
        gate = SecurityGate()
        assert gate.config is not None
        assert gate.gates == ALL_SUB_GATES

    # ── All sub-gates pass on empty repo ────────────────────────────────────

    def test_empty_repo_passes(self, tmp_path: Path) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps({"dependencies": []}),
                stderr="",
            )
            cfg = SecurityGateConfig(
                scan_secrets=True,
                scan_dependencies=True,
                severity_threshold="HIGH",
            )
            result = SecurityGate(cfg).run(tmp_path)
        assert result.passed

    # ── Selecting a single sub-gate ──────────────────────────────────────────

    def test_run_only_secrets_gate(self, tmp_path: Path) -> None:
        _write(tmp_path, "clean.py", "x = 1\n")
        cfg = SecurityGateConfig(scan_secrets=True, scan_dependencies=False)
        result = SecurityGate(cfg, gates=("secrets",)).run(tmp_path)
        sub_gate_names = {sg.sub_gate for sg in result.sub_gate_results}
        assert "secrets" in sub_gate_names
        assert "dependencies" not in sub_gate_names
        assert "input-validation" not in sub_gate_names

    def test_run_only_input_validation_gate(self, tmp_path: Path) -> None:
        _write(tmp_path, "app.py", "x = 1\n")
        cfg = SecurityGateConfig(scan_secrets=False, scan_dependencies=False)
        result = SecurityGate(cfg, gates=("input-validation",)).run(tmp_path)
        sub_gate_names = {sg.sub_gate for sg in result.sub_gate_results}
        assert "input-validation" in sub_gate_names
        assert "secrets" not in sub_gate_names

    # ── scan_secrets=False skips secrets sub-gate ────────────────────────────

    def test_scan_secrets_false_skips_secrets(self, tmp_path: Path) -> None:
        _write(tmp_path, "cfg.py", 'password = "HardCodedPwd999!"\n')
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps({"dependencies": []}),
                stderr="",
            )
            cfg = SecurityGateConfig(
                scan_secrets=False,
                scan_dependencies=True,
            )
            result = SecurityGate(cfg).run(tmp_path)
        # No secrets sub-gate → should still pass (secret ignored)
        assert result.passed
        sub_gate_names = {sg.sub_gate for sg in result.sub_gate_results}
        assert "secrets" not in sub_gate_names

    # ── scan_dependencies=False skips dependency sub-gate ────────────────────

    def test_scan_dependencies_false_skips_deps(self, tmp_path: Path) -> None:
        cfg = SecurityGateConfig(scan_secrets=False, scan_dependencies=False)
        result = SecurityGate(cfg, gates=("secrets", "dependencies")).run(tmp_path)
        sub_gate_names = {sg.sub_gate for sg in result.sub_gate_results}
        assert "dependencies" not in sub_gate_names

    # ── Stats are populated ──────────────────────────────────────────────────

    def test_stats_populated(self, tmp_path: Path) -> None:
        _write(tmp_path, "cfg.py", 'password = "SomeSecret2024!"\n')
        cfg = SecurityGateConfig(scan_secrets=True, scan_dependencies=False)
        result = SecurityGate(cfg, gates=("secrets",)).run(tmp_path)
        assert "total" in result.stats
        assert "errors" in result.stats
        assert "warnings" in result.stats

    # ── passed=False when any sub-gate fails ─────────────────────────────────

    def test_failed_sub_gate_fails_overall(self, tmp_path: Path) -> None:
        _write(tmp_path, "cfg.py", 'password = "HardCodedSecret123!"\n')
        cfg = SecurityGateConfig(
            scan_secrets=True,
            scan_dependencies=False,
            fail_on_error=True,
        )
        result = SecurityGate(cfg, gates=("secrets",)).run(tmp_path)
        assert not result.passed

    # ── passed=True when all sub-gates pass ─────────────────────────────────

    def test_all_pass_overall_pass(self, tmp_path: Path) -> None:
        _write(tmp_path, "app.py", 'import os\nSECRET = os.environ["SECRET"]\n')
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps({"dependencies": []}),
                stderr="",
            )
            cfg = SecurityGateConfig(scan_secrets=True, scan_dependencies=True)
            result = SecurityGate(cfg).run(tmp_path)
        assert result.passed

    # ── Sub-gate results list is correct length ──────────────────────────────

    def test_sub_gate_results_count(self, tmp_path: Path) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps({"dependencies": []}),
                stderr="",
            )
            cfg = SecurityGateConfig(scan_secrets=True, scan_dependencies=True)
            result = SecurityGate(cfg, gates=ALL_SUB_GATES).run(tmp_path)
        # 3 sub-gates configured and enabled
        assert len(result.sub_gate_results) == 3

    # ── GateResult __str__ ───────────────────────────────────────────────────

    def test_gate_result_str_contains_gate_name(self, tmp_path: Path) -> None:
        sg = SubGateResult(passed=True, sub_gate="secrets")
        gr = GateResult(passed=True, sub_gate_results=[sg])
        s = str(gr)
        assert "SecurityGate" in s
        assert "secrets" in s
