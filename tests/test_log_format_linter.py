"""
Tests for log_format_linter — rule generator, checker, detector, and CLI.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from log_format_linter import (
    GeneratorResult,
    Language,
    LogFramework,
    LogLinterConfig,
    LogViolation,
    ViolationSeverity,
    check_directory,
    check_file,
    detect_framework,
    generate_rules,
)
from log_format_linter.cli import main as cli_main


def _write(tmp_path: Path, filename: str, content: str) -> Path:
    p = tmp_path / filename
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


class TestLogLinterConfig:
    def test_defaults(self):
        cfg = LogLinterConfig()
        assert cfg.required_fields == ["domain", "trace_id"]
        assert cfg.severity == ViolationSeverity.ERROR

    def test_custom_fields(self):
        cfg = LogLinterConfig(required_fields=["trace_id", "request_id"])
        assert "trace_id" in cfg.required_fields


class TestDetectFramework:
    def test_detects_python_logging(self, tmp_path):
        _write(tmp_path, "app.py", "import logging\n")
        assert detect_framework(tmp_path) == LogFramework.PYTHON_LOGGING

    def test_detects_structlog(self, tmp_path):
        _write(tmp_path, "app.py", "import structlog\n")
        assert detect_framework(tmp_path) == LogFramework.STRUCTLOG

    def test_detects_winston(self, tmp_path):
        _write(tmp_path, "app.ts", "import winston from 'winston';\n")
        assert detect_framework(tmp_path) == LogFramework.WINSTON

    def test_detects_zap(self, tmp_path):
        _write(tmp_path, "app.go", 'import "go.uber.org/zap"\n')
        assert detect_framework(tmp_path) == LogFramework.ZAP

    def test_unknown_when_no_match(self, tmp_path):
        _write(tmp_path, "app.py", "x = 1\n")
        assert detect_framework(tmp_path) == LogFramework.UNKNOWN


class TestGenerateRules:
    @pytest.mark.parametrize("framework,expected_lang", [
        (LogFramework.PYTHON_LOGGING, Language.PYTHON),
        (LogFramework.STRUCTLOG, Language.PYTHON),
        (LogFramework.WINSTON, Language.TYPESCRIPT),
        (LogFramework.ZAP, Language.GO),
        (LogFramework.LOGRUS, Language.GO),
    ])
    def test_language_mapping(self, framework, expected_lang):
        result = generate_rules(framework)
        assert result.language == expected_lang

    def test_returns_generator_result(self):
        result = generate_rules(LogFramework.PYTHON_LOGGING)
        assert isinstance(result, GeneratorResult)

    def test_python_logging_check_strategy(self):
        result = generate_rules(LogFramework.PYTHON_LOGGING)
        assert result.rules["check_strategy"] == "regex+extra-dict"

    def test_structlog_check_strategy(self):
        result = generate_rules(LogFramework.STRUCTLOG)
        assert result.rules["check_strategy"] == "regex+kwargs"

    def test_winston_has_eslint_snippet(self):
        result = generate_rules(LogFramework.WINSTON)
        assert "eslint_config_snippet" in result.rules

    def test_examples_contain_good_and_bad(self):
        result = generate_rules(LogFramework.PYTHON_LOGGING)
        types = {e["type"] for e in result.examples}
        assert "good" in types
        assert "bad" in types

    @pytest.mark.parametrize("fw", [
        LogFramework.PYTHON_LOGGING, LogFramework.STRUCTLOG, LogFramework.LOGURU,
        LogFramework.WINSTON, LogFramework.PINO, LogFramework.BUNYAN,
        LogFramework.ZAP, LogFramework.LOGRUS, LogFramework.ZEROLOG,
    ])
    def test_all_frameworks_have_rules(self, fw):
        result = generate_rules(fw)
        assert result.rules, f"Expected non-empty rules for {fw.value}"


class TestCheckFilePythonLogging:
    def _config(self, **kw) -> LogLinterConfig:
        return LogLinterConfig(framework=LogFramework.PYTHON_LOGGING, **kw)

    def test_compliant_call_no_violations(self, tmp_path):
        p = _write(tmp_path, "app.py", """
            import logging
            logger = logging.getLogger("svc.auth")
            logger.info("user login", extra={"domain": "svc.auth", "trace_id": "abc"})
        """)
        assert check_file(p, config=self._config()) == []

    def test_missing_extra_kwarg_is_violation(self, tmp_path):
        p = _write(tmp_path, "app.py", """
            import logging
            logger = logging.getLogger("svc")
            logger.info("something happened")
        """)
        violations = check_file(p, config=self._config())
        assert len(violations) == 1

    def test_partial_fields_is_violation(self, tmp_path):
        p = _write(tmp_path, "app.py", """
            import logging
            logger = logging.getLogger("svc")
            logger.error("fail", extra={"domain": "svc"})
        """)
        violations = check_file(p, config=self._config())
        assert len(violations) == 1
        assert "trace_id" in violations[0].message

    def test_file_without_import_skipped(self, tmp_path):
        p = _write(tmp_path, "utils.py", "def log_something(): pass\n")
        assert check_file(p, config=self._config()) == []

    def test_violation_has_correct_line_number(self, tmp_path):
        p = _write(tmp_path, "app.py",
            "import logging\n"
            "logger = logging.getLogger('x')\n"
            "\n"
            "logger.info('no fields here')\n")
        violations = check_file(p, config=self._config())
        assert violations[0].line == 4

    def test_multiple_violations(self, tmp_path):
        p = _write(tmp_path, "app.py", """
            import logging
            log = logging.getLogger("svc")
            log.info("first call")
            log.error("second call")
            log.debug("third call")
        """)
        violations = check_file(p, config=self._config())
        assert len(violations) == 3

    def test_severity_propagated(self, tmp_path):
        p = _write(tmp_path, "app.py", "import logging\nlogging.warning('oops')\n")
        cfg = self._config(severity=ViolationSeverity.WARNING)
        violations = check_file(p, config=cfg)
        assert all(v.severity == ViolationSeverity.WARNING for v in violations)


class TestCheckDirectory:
    def test_scans_nested_files(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        _write(sub, "a.py", "import logging\nlogging.info('no fields')\n")
        _write(sub, "b.py", "import logging\nlogging.warning('also no fields')\n")
        config = LogLinterConfig(framework=LogFramework.PYTHON_LOGGING)
        violations = check_directory(tmp_path, config=config)
        assert len(violations) == 2

    def test_ignore_patterns_respected(self, tmp_path):
        _write(tmp_path, "main.py", "import logging\nlogging.info('ignored')\n")
        config = LogLinterConfig(
            framework=LogFramework.PYTHON_LOGGING,
            ignore_patterns=["main.py"],
        )
        assert check_directory(tmp_path, config=config) == []

    def test_empty_directory_no_violations(self, tmp_path):
        config = LogLinterConfig(framework=LogFramework.PYTHON_LOGGING)
        assert check_directory(tmp_path, config=config) == []


class TestCLICheck:
    def test_exit_0_when_clean(self, tmp_path):
        p = _write(tmp_path, "app.py", """
            import logging
            log = logging.getLogger("svc")
            log.info("ok", extra={"domain": "svc", "trace_id": "abc"})
        """)
        code = cli_main(["check", str(p), "--framework", "python_logging"])
        assert code == 0

    def test_exit_1_when_violations(self, tmp_path):
        p = _write(tmp_path, "app.py", "import logging\nlogging.info('oops')\n")
        code = cli_main(["check", str(p), "--framework", "python_logging"])
        assert code == 1

    def test_exit_2_on_bad_path(self, tmp_path):
        code = cli_main(["check", str(tmp_path / "nonexistent.py")])
        assert code == 2

    def test_json_output_structure(self, tmp_path, capsys):
        p = _write(tmp_path, "app.py", "import logging\nlogging.info('bare')\n")
        cli_main(["check", str(p), "--framework", "python_logging", "--output", "json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "summary" in data
        assert "violations" in data
        assert data["summary"]["total_violations"] >= 1

    def test_ignore_flag(self, tmp_path):
        _write(tmp_path, "app.py", "import logging\nlogging.info('bare')\n")
        code = cli_main(["check", str(tmp_path), "--framework", "python_logging",
                         "--ignore", "app.py"])
        assert code == 0


class TestCLIRules:
    def test_json_output(self, capsys):
        code = cli_main(["rules", "python_logging", "--output", "json"])
        assert code == 0
        data = json.loads(capsys.readouterr().out)
        assert data["framework"] == "python_logging"

    def test_invalid_framework_exits_2(self):
        code = cli_main(["rules", "serilog"])
        assert code == 2

    @pytest.mark.parametrize("fw", [
        "python_logging", "structlog", "loguru",
        "winston", "pino", "bunyan",
        "zap", "logrus", "zerolog",
    ])
    def test_all_frameworks_produce_output(self, fw, capsys):
        code = cli_main(["rules", fw, "--output", "json"])
        assert code == 0
        data = json.loads(capsys.readouterr().out)
        assert data["framework"] == fw


class TestCLIDetect:
    def test_detects_python_logging(self, tmp_path, capsys):
        _write(tmp_path, "app.py", "import logging\n")
        code = cli_main(["detect", str(tmp_path)])
        assert code == 0
        assert "python_logging" in capsys.readouterr().out

    def test_json_output(self, tmp_path, capsys):
        _write(tmp_path, "app.py", "import structlog\n")
        cli_main(["detect", str(tmp_path), "--output", "json"])
        data = json.loads(capsys.readouterr().out)
        assert data["framework"] == "structlog"

    def test_missing_path_exits_2(self, tmp_path):
        code = cli_main(["detect", str(tmp_path / "no_such_dir")])
        assert code == 2


class TestRoundTrip:
    def test_compliant_python_source_passes(self, tmp_path):
        p = _write(tmp_path, "app.py",
            "import logging\n"
            "logging.info('x', extra={'domain': 'svc', 'trace_id': 'abc'})\n")
        config = LogLinterConfig(framework=LogFramework.PYTHON_LOGGING)
        result = generate_rules(LogFramework.PYTHON_LOGGING, config=config)
        assert check_file(p, config=result.config) == []

    def test_noncompliant_python_source_fails(self, tmp_path):
        p = _write(tmp_path, "app.py", "import logging\nlogging.info('x')\n")
        config = LogLinterConfig(framework=LogFramework.PYTHON_LOGGING)
        result = generate_rules(LogFramework.PYTHON_LOGGING, config=config)
        assert len(check_file(p, config=result.config)) >= 1
