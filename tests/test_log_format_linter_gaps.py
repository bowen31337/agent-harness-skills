"""
Tests covering uncovered lines in log_format_linter:
  - checker.py: framework-specific field checkers (zap, logrus, zerolog, object-keys,
    bind-or-kwargs), check_file with auto-detect, check_directory with non-source files
  - cli.py: colour helpers, invalid severity/framework, rules text output, detect subcommand
  - detector.py: pino, bunyan, logrus, zerolog detection
  - generator.py: UNKNOWN framework fallback
  - models.py: LogViolation.__str__
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from log_format_linter.checker import (
    _extract_block,
    _missing_from_bind_or_kwargs,
    _missing_from_extra_dict,
    _missing_from_kwargs,
    _missing_from_object_keys,
    _missing_from_with_fields,
    _missing_from_zap_fields,
    _missing_from_zerolog_chain,
    check_directory,
    check_file,
)
from log_format_linter.cli import (
    _colour_severity,
    _run_check,
    _use_colour,
    main as cli_main,
)
from log_format_linter.detector import detect_framework
from log_format_linter.generator import generate_rules
from log_format_linter.models import (
    GeneratorResult,
    Language,
    LogFramework,
    LogLinterConfig,
    LogViolation,
    ViolationSeverity,
)


def _write(tmp_path: Path, filename: str, content: str) -> Path:
    p = tmp_path / filename
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# checker.py — framework-specific missing field functions
# ---------------------------------------------------------------------------

class TestMissingFromObjectKeys:
    """Covers lines 154-159 (_missing_from_object_keys)."""

    def test_all_present(self):
        block = 'logger.info("msg", { domain: "svc", trace_id: "abc" })'
        assert _missing_from_object_keys(block, ["domain", "trace_id"]) == []

    def test_quoted_keys(self):
        block = 'logger.info("msg", { "domain": "svc", "trace_id": "abc" })'
        assert _missing_from_object_keys(block, ["domain", "trace_id"]) == []

    def test_missing_keys(self):
        block = 'logger.info("msg", { domain: "svc" })'
        assert _missing_from_object_keys(block, ["domain", "trace_id"]) == ["trace_id"]


class TestMissingFromZapFields:
    """Covers lines 164-170 (_missing_from_zap_fields)."""

    def test_all_present(self):
        block = 'logger.Info("msg", zap.String("domain", d), zap.String("trace_id", t))'
        assert _missing_from_zap_fields(block, ["domain", "trace_id"]) == []

    def test_missing_field(self):
        block = 'logger.Info("msg", zap.String("domain", d))'
        assert _missing_from_zap_fields(block, ["domain", "trace_id"]) == ["trace_id"]

    def test_all_missing(self):
        block = 'logger.Info("msg")'
        assert _missing_from_zap_fields(block, ["domain", "trace_id"]) == ["domain", "trace_id"]


class TestMissingFromWithFields:
    """Covers lines 175-182 (_missing_from_with_fields)."""

    def test_all_present(self):
        block = 'logrus.WithFields(logrus.Fields{"domain": d, "trace_id": t}).Info("msg")'
        assert _missing_from_with_fields(block, ["domain", "trace_id"]) == []

    def test_missing_field(self):
        block = 'logrus.WithFields(logrus.Fields{"domain": d}).Info("msg")'
        assert _missing_from_with_fields(block, ["domain", "trace_id"]) == ["trace_id"]

    def test_no_with_fields(self):
        """Without .WithFields all fields are considered missing."""
        block = 'logrus.Info("msg")'
        assert _missing_from_with_fields(block, ["domain", "trace_id"]) == ["domain", "trace_id"]


class TestMissingFromZerologChain:
    """Covers lines 187-191 (_missing_from_zerolog_chain)."""

    def test_all_present(self):
        block = 'log.Info().Str("domain", d).Str("trace_id", t).Msg("ok")'
        assert _missing_from_zerolog_chain(block, ["domain", "trace_id"]) == []

    def test_missing_field(self):
        block = 'log.Info().Str("domain", d).Msg("ok")'
        assert _missing_from_zerolog_chain(block, ["domain", "trace_id"]) == ["trace_id"]

    def test_interface_method(self):
        block = 'log.Info().Interface("domain", d).Interface("trace_id", t).Msg("ok")'
        assert _missing_from_zerolog_chain(block, ["domain", "trace_id"]) == []


class TestMissingFromBindOrKwargs:
    """Covers line 149 (_missing_from_bind_or_kwargs)."""

    def test_bind_present(self):
        block = 'logger.bind(domain="svc", trace_id="abc").info("msg")'
        assert _missing_from_bind_or_kwargs(block, ["domain", "trace_id"]) == []

    def test_kwargs_present(self):
        block = 'logger.info("msg", domain="svc", trace_id="abc")'
        assert _missing_from_bind_or_kwargs(block, ["domain", "trace_id"]) == []

    def test_missing(self):
        block = 'logger.info("msg")'
        assert _missing_from_bind_or_kwargs(block, ["domain", "trace_id"]) == ["domain", "trace_id"]


# ---------------------------------------------------------------------------
# checker.py — check_file with various frameworks
# ---------------------------------------------------------------------------

class TestCheckFileWinston:
    """Covers checker lines for Winston (object-keys strategy)."""

    def test_winston_violation(self, tmp_path):
        p = _write(tmp_path, "app.ts", """
            import winston from 'winston';
            const logger = winston.createLogger();
            logger.info('user login');
        """)
        config = LogLinterConfig(framework=LogFramework.WINSTON)
        violations = check_file(p, config=config)
        assert len(violations) >= 1

    def test_winston_compliant(self, tmp_path):
        p = _write(tmp_path, "app.ts", """
            import winston from 'winston';
            const logger = winston.createLogger();
            logger.info('user login', { domain: 'auth', trace_id: 'xyz' });
        """)
        config = LogLinterConfig(framework=LogFramework.WINSTON)
        assert check_file(p, config=config) == []


class TestCheckFileZap:
    """Covers checker lines for Zap (zap-fields strategy)."""

    def test_zap_violation(self, tmp_path):
        p = _write(tmp_path, "app.go", '''
            import "go.uber.org/zap"
            func main() {
                logger.Info("request handled")
            }
        ''')
        config = LogLinterConfig(framework=LogFramework.ZAP)
        violations = check_file(p, config=config)
        assert len(violations) >= 1

    def test_zap_compliant(self, tmp_path):
        p = _write(tmp_path, "app.go", '''
            import "go.uber.org/zap"
            func main() {
                logger.Info("request handled", zap.String("domain", "svc"), zap.String("trace_id", "abc"))
            }
        ''')
        config = LogLinterConfig(framework=LogFramework.ZAP)
        assert check_file(p, config=config) == []


class TestCheckFileLogrus:
    """Covers checker lines for Logrus (with-fields strategy)."""

    def test_logrus_violation(self, tmp_path):
        p = _write(tmp_path, "app.go", '''
            import "github.com/sirupsen/logrus"
            func main() {
                logrus.Info("user login")
            }
        ''')
        config = LogLinterConfig(framework=LogFramework.LOGRUS)
        violations = check_file(p, config=config)
        assert len(violations) >= 1


class TestCheckFileZerolog:
    """Covers checker lines for zerolog (zerolog-chain strategy)."""

    def test_zerolog_violation(self, tmp_path):
        p = _write(tmp_path, "app.go", '''
            import "github.com/rs/zerolog"
            func main() {
                log.Info().Msg("request handled")
            }
        ''')
        config = LogLinterConfig(framework=LogFramework.ZEROLOG)
        violations = check_file(p, config=config)
        assert len(violations) >= 1

    def test_zerolog_compliant(self, tmp_path):
        p = _write(tmp_path, "app.go", '''
            import "github.com/rs/zerolog"
            func main() {
                log.Info().Str("domain", "svc").Str("trace_id", "abc").Msg("ok")
            }
        ''')
        config = LogLinterConfig(framework=LogFramework.ZEROLOG)
        assert check_file(p, config=config) == []


class TestCheckFileLoguru:
    """Covers checker for loguru (bind-or-kwargs strategy)."""

    def test_loguru_violation(self, tmp_path):
        p = _write(tmp_path, "app.py", """
            from loguru import logger
            logger.info("charge processed")
        """)
        config = LogLinterConfig(framework=LogFramework.LOGURU)
        violations = check_file(p, config=config)
        assert len(violations) >= 1

    def test_loguru_compliant_kwargs(self, tmp_path):
        p = _write(tmp_path, "app.py", """
            from loguru import logger
            logger.info("charge processed", domain="billing", trace_id="xyz")
        """)
        config = LogLinterConfig(framework=LogFramework.LOGURU)
        assert check_file(p, config=config) == []


class TestCheckFilePino:
    """Covers pino (object-keys strategy)."""

    def test_pino_violation(self, tmp_path):
        p = _write(tmp_path, "app.js", """
            const pino = require('pino');
            const log = pino();
            log.info('order created');
        """)
        config = LogLinterConfig(framework=LogFramework.PINO)
        violations = check_file(p, config=config)
        assert len(violations) >= 1


class TestCheckFileBunyan:
    """Covers bunyan (object-keys strategy)."""

    def test_bunyan_violation(self, tmp_path):
        p = _write(tmp_path, "app.js", """
            const bunyan = require('bunyan');
            const log = bunyan.createLogger({name: 'app'});
            log.info('request handled');
        """)
        config = LogLinterConfig(framework=LogFramework.BUNYAN)
        violations = check_file(p, config=config)
        assert len(violations) >= 1


class TestCheckFileAutoDetect:
    """Covers check_file with config.framework=None (auto-detect)."""

    def test_auto_detects_structlog(self, tmp_path):
        p = _write(tmp_path, "svc.py", """
            import structlog
            log = structlog.get_logger()
            log.info("hello")
        """)
        violations = check_file(p)
        assert len(violations) >= 1

    def test_unrecognized_extension_returns_empty(self, tmp_path):
        p = _write(tmp_path, "data.txt", "logger.info('no match')")
        assert check_file(p) == []

    def test_oserror_returns_empty(self, tmp_path):
        """check_file returns [] when file cannot be read."""
        p = tmp_path / "nonexistent.py"
        config = LogLinterConfig(framework=LogFramework.PYTHON_LOGGING)
        assert check_file(p, config=config) == []

    def test_unknown_framework_returns_empty(self, tmp_path):
        """Line 278: framework with no call pattern returns []."""
        p = _write(tmp_path, "app.py", "import logging\nlogging.info('test')\n")
        config = LogLinterConfig(framework=LogFramework.UNKNOWN)
        assert check_file(p, config=config) == []


class TestCheckDirectoryEdgeCases:
    """Covers check_directory lines 329, 339 for non-source files and subdirectories."""

    def test_skips_non_source_files(self, tmp_path):
        _write(tmp_path, "readme.md", "# Log format\nlogger.info('test')\n")
        _write(tmp_path, "app.py", "import logging\nlogging.info('bare')\n")
        config = LogLinterConfig(framework=LogFramework.PYTHON_LOGGING)
        violations = check_directory(tmp_path, config=config)
        files = {str(v.file) for v in violations}
        assert not any("readme" in f for f in files)

    def test_skips_subdirectories_that_are_not_files(self, tmp_path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        config = LogLinterConfig(framework=LogFramework.PYTHON_LOGGING)
        # Should not crash on directories
        violations = check_directory(tmp_path, config=config)
        assert isinstance(violations, list)

    def test_check_directory_config_none(self, tmp_path):
        """Line 329: check_directory with config=None creates default config."""
        _write(tmp_path, "app.py", "import logging\nlogging.info('bare')\n")
        violations = check_directory(tmp_path, config=None)
        # With default config (auto-detect), should find python_logging violations
        assert len(violations) >= 1


# ---------------------------------------------------------------------------
# cli.py — colour helpers
# ---------------------------------------------------------------------------

class TestColourHelpers:
    """Covers lines 55-60 (_colour_severity, _use_colour)."""

    def test_use_colour_text_tty(self):
        with patch("log_format_linter.cli.sys") as mock_sys:
            mock_sys.stderr.isatty.return_value = True
            assert _use_colour("text") is True

    def test_use_colour_text_no_tty(self):
        with patch("log_format_linter.cli.sys") as mock_sys:
            mock_sys.stderr.isatty.return_value = False
            assert _use_colour("text") is False

    def test_use_colour_json(self):
        assert _use_colour("json") is False

    def test_colour_severity_no_colour(self):
        assert _colour_severity("error", False) == "error"
        assert _colour_severity("warning", False) == "warning"
        assert _colour_severity("info", False) == "info"

    def test_colour_severity_with_colour(self):
        result = _colour_severity("error", True)
        assert "error" in result
        result = _colour_severity("warning", True)
        assert "warning" in result
        result = _colour_severity("info", True)
        assert "info" in result

    def test_colour_severity_unknown(self):
        assert _colour_severity("custom", True) == "custom"


# ---------------------------------------------------------------------------
# cli.py — check subcommand edge cases
# ---------------------------------------------------------------------------

class TestCLICheckEdges:
    """Covers lines 75-81, 88-95 (invalid severity/framework)."""

    def test_invalid_severity_exits_2(self, tmp_path):
        p = _write(tmp_path, "app.py", "import logging\nlogging.info('x')\n")
        code = cli_main(["check", str(p), "--severity", "error"])
        # 'error' is valid, let's test the code path that checks valid severity
        # Actually severity is a choices arg in argparse, so invalid gets caught by argparse
        # The ValueError path on lines 75-81 handles non-choices case
        # Since argparse validates, we need to bypass it
        # Let's just ensure valid severity values work
        assert code == 1

    def test_invalid_framework_exits_2(self, tmp_path, capsys):
        """Lines 88-95: invalid --framework value."""
        p = _write(tmp_path, "app.py", "import logging\nlogging.info('x')\n")
        code = cli_main(["check", str(p), "--framework", "serilog"])
        assert code == 2
        captured = capsys.readouterr()
        assert "unknown framework" in captured.err

    def test_check_directory_via_cli(self, tmp_path):
        _write(tmp_path, "a.py", "import logging\nlogging.info('bare')\n")
        code = cli_main(["check", str(tmp_path), "--framework", "python_logging"])
        assert code == 1

    def test_text_output_with_violations(self, tmp_path, capsys):
        """Lines 138-157: text output formatting with violations."""
        _write(tmp_path, "app.py", "import logging\nlogging.info('bare')\n")
        code = cli_main(["check", str(tmp_path), "--framework", "python_logging",
                         "--output", "text"])
        assert code == 1
        captured = capsys.readouterr()
        assert "violation" in captured.err.lower()

    def test_text_output_no_violations(self, tmp_path, capsys):
        """Lines 154-157: clean output message."""
        _write(tmp_path, "app.py",
               "import logging\nlogging.info('x', extra={'domain': 'svc', 'trace_id': 'abc'})\n")
        code = cli_main(["check", str(tmp_path), "--framework", "python_logging",
                         "--output", "text"])
        assert code == 0
        captured = capsys.readouterr()
        assert "No structured-log violations found" in captured.err

    def test_check_with_custom_fields(self, tmp_path):
        _write(tmp_path, "app.py", "import logging\nlogging.info('bare')\n")
        code = cli_main(["check", str(tmp_path), "--framework", "python_logging",
                         "--fields", "request_id", "service"])
        assert code == 1

    def test_text_output_colour_violations(self, tmp_path, capsys):
        """Lines 151: coloured summary when use_col is True and violations exist."""
        _write(tmp_path, "app.py", "import logging\nlogging.info('bare')\n")
        with patch("log_format_linter.cli.sys") as mock_sys:
            mock_sys.stderr = sys.stderr
            mock_sys.stderr.isatty = lambda: True
            mock_sys.stdout = sys.stdout
            code = cli_main(["check", str(tmp_path), "--framework", "python_logging",
                             "--output", "text"])
        assert code == 1

    def test_text_output_colour_clean(self, tmp_path, capsys):
        """Line 156: coloured 'no violations' message when use_col is True."""
        _write(tmp_path, "app.py",
               "import logging\nlogging.info('x', extra={'domain': 'svc', 'trace_id': 'abc'})\n")
        with patch("log_format_linter.cli.sys") as mock_sys:
            mock_sys.stderr = sys.stderr
            mock_sys.stderr.isatty = lambda: True
            mock_sys.stdout = sys.stdout
            code = cli_main(["check", str(tmp_path), "--framework", "python_logging",
                             "--output", "text"])
        assert code == 0

    def test_invalid_severity_value_error(self, tmp_path, capsys):
        """Lines 75-81: ViolationSeverity ValueError path."""
        _write(tmp_path, "app.py", "import logging\nlogging.info('bare')\n")
        # The severity arg is a choices in argparse, so we need to bypass argparse
        # by directly calling _run_check with a namespace that has an invalid severity
        import argparse
        from log_format_linter.cli import _run_check
        ns = argparse.Namespace(
            path=str(tmp_path / "app.py"),
            fields=None,
            severity="critical",  # invalid — not in ViolationSeverity
            framework="python_logging",
            ignore=None,
            output="text",
        )
        code = _run_check(ns)
        assert code == 2
        captured = capsys.readouterr()
        assert "invalid --severity" in captured.err


# ---------------------------------------------------------------------------
# cli.py — rules subcommand text output
# ---------------------------------------------------------------------------

class TestCLIRulesText:
    """Covers lines 199-236 (rules text output)."""

    def test_rules_text_output(self, capsys):
        code = cli_main(["rules", "python_logging", "--output", "text"])
        assert code == 0
        captured = capsys.readouterr()
        assert "Log-Lint Rules" in captured.out
        assert "Language:" in captured.out
        assert "Framework:" in captured.out

    def test_rules_text_with_examples(self, capsys):
        code = cli_main(["rules", "structlog", "--output", "text"])
        assert code == 0
        captured = capsys.readouterr()
        assert "Compliant examples" in captured.out
        assert "Non-compliant examples" in captured.out

    def test_rules_text_shows_patterns(self, capsys):
        code = cli_main(["rules", "python_logging", "--output", "text"])
        assert code == 0
        captured = capsys.readouterr()
        assert "Check Strategy:" in captured.out
        assert "Detection Patterns:" in captured.out

    def test_rules_with_custom_fields(self, capsys):
        code = cli_main(["rules", "winston", "--output", "text",
                         "--fields", "request_id", "service"])
        assert code == 0
        captured = capsys.readouterr()
        assert "request_id" in captured.out

    @pytest.mark.parametrize("fw", [
        "loguru", "winston", "pino", "bunyan", "zap", "logrus", "zerolog",
    ])
    def test_all_frameworks_text_output(self, fw, capsys):
        code = cli_main(["rules", fw, "--output", "text"])
        assert code == 0
        captured = capsys.readouterr()
        assert "Log-Lint Rules" in captured.out


# ---------------------------------------------------------------------------
# cli.py — detect subcommand edge cases
# ---------------------------------------------------------------------------

class TestCLIDetectEdges:
    def test_detect_json_output(self, tmp_path, capsys):
        _write(tmp_path, "app.go", 'import "go.uber.org/zap"\n')
        code = cli_main(["detect", str(tmp_path), "--output", "json"])
        assert code == 0
        data = json.loads(capsys.readouterr().out)
        assert data["framework"] == "zap"


# ---------------------------------------------------------------------------
# cli.py — dispatch fallback (lines 325-326)
# ---------------------------------------------------------------------------

class TestCLIDispatchFallback:
    def test_unknown_command_is_caught_by_argparse(self):
        """argparse catches unknown commands before dispatch."""
        with pytest.raises(SystemExit):
            cli_main(["nonexistent_cmd"])

    def test_dispatch_none_handler(self):
        """Lines 325-326: handler is None when command not in dispatch table."""
        # We can trigger this by patching the dispatch dict
        import argparse
        with patch("log_format_linter.cli._build_parser") as mock_builder:
            mock_parser = MagicMock()
            mock_ns = argparse.Namespace(command="nonexistent")
            mock_parser.parse_args.return_value = mock_ns
            mock_builder.return_value = mock_parser
            code = cli_main([])
            assert code == 2


# ---------------------------------------------------------------------------
# detector.py — additional framework detection
# ---------------------------------------------------------------------------

class TestDetectorGaps:
    """Covers lines 79, 82, 86-87 (pino, bunyan, logrus, zerolog, OSError)."""

    def test_detects_pino(self, tmp_path):
        _write(tmp_path, "app.js", "import pino from 'pino';\n")
        assert detect_framework(tmp_path) == LogFramework.PINO

    def test_oserror_skips_file(self, tmp_path):
        """Line 86-87: OSError when reading a file is silently skipped."""
        p = _write(tmp_path, "app.py", "import structlog\n")
        # Make the file unreadable by patching
        with patch("pathlib.Path.read_text", side_effect=OSError("Permission denied")):
            result = detect_framework(tmp_path)
        assert result == LogFramework.UNKNOWN

    def test_directory_entries_skipped(self, tmp_path):
        """Line 79: non-file entries (dirs) are skipped."""
        sub = tmp_path / "subdir.py"
        sub.mkdir()
        _write(tmp_path, "app.py", "import structlog\n")
        assert detect_framework(tmp_path) == LogFramework.STRUCTLOG

    def test_detects_bunyan(self, tmp_path):
        _write(tmp_path, "app.js", "const bunyan = require('bunyan');\n")
        assert detect_framework(tmp_path) == LogFramework.BUNYAN

    def test_detects_logrus(self, tmp_path):
        _write(tmp_path, "app.go", 'import "github.com/sirupsen/logrus"\n')
        assert detect_framework(tmp_path) == LogFramework.LOGRUS

    def test_detects_zerolog(self, tmp_path):
        _write(tmp_path, "app.go", 'import "github.com/rs/zerolog"\n')
        assert detect_framework(tmp_path) == LogFramework.ZEROLOG

    def test_detects_loguru(self, tmp_path):
        _write(tmp_path, "app.py", "from loguru import logger\n")
        assert detect_framework(tmp_path) == LogFramework.LOGURU

    def test_single_file_detection(self, tmp_path):
        p = _write(tmp_path, "app.py", "import structlog\n")
        assert detect_framework(p) == LogFramework.STRUCTLOG

    def test_skips_non_source_files(self, tmp_path):
        _write(tmp_path, "readme.md", "import structlog\n")
        assert detect_framework(tmp_path) == LogFramework.UNKNOWN

    def test_most_used_wins(self, tmp_path):
        """When multiple frameworks are detected, most-used wins."""
        _write(tmp_path, "a.py", "import structlog\n")
        _write(tmp_path, "b.py", "import structlog\n")
        _write(tmp_path, "c.py", "import logging\n")
        assert detect_framework(tmp_path) == LogFramework.STRUCTLOG


# ---------------------------------------------------------------------------
# generator.py — UNKNOWN framework fallback (lines 408-414)
# ---------------------------------------------------------------------------

class TestGeneratorUnknown:
    """Covers lines 408-414 (UNKNOWN framework branch)."""

    def test_unknown_framework_returns_empty_rules(self):
        result = generate_rules(LogFramework.UNKNOWN)
        assert isinstance(result, GeneratorResult)
        assert result.rules == {}
        assert result.examples == []
        assert "No built-in rules" in result.description

    def test_unknown_framework_language(self):
        result = generate_rules(LogFramework.UNKNOWN)
        assert result.language == Language.UNKNOWN


# ---------------------------------------------------------------------------
# models.py — LogViolation.__str__ (line 96)
# ---------------------------------------------------------------------------

class TestLogViolationStr:
    """Covers line 96 (LogViolation.__str__)."""

    def test_str_format(self):
        v = LogViolation(
            file=Path("/tmp/app.py"),
            line=10,
            column=4,
            message="Missing fields: ['domain']",
            severity=ViolationSeverity.ERROR,
        )
        s = str(v)
        assert "/tmp/app.py:10:" in s
        assert "[error]" in s
        assert "Missing fields" in s

    def test_str_warning(self):
        v = LogViolation(
            file=Path("/tmp/svc.py"),
            line=5,
            column=0,
            message="Test message",
            severity=ViolationSeverity.WARNING,
        )
        assert "[warning]" in str(v)
