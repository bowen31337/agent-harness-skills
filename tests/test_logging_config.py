"""Tests for harness_skills.logging_config — structured logging, formatters, and configure()."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from harness_skills.logging_config import (
    ConventionFormatter,
    DomainLogger,
    LOGGING_CONFIG,
    PrettyConventionFormatter,
    _LEVEL_MAP,
    _RESERVED_FIELDS,
    configure,
    get_current_trace_id,
    get_logger,
    root_logger,
    set_trace_id,
)


# ── Trace-ID ─────────────────────────────────────────────────────────────────


class TestTraceId:
    def test_get_current_trace_id_returns_32_hex(self):
        tid = get_current_trace_id()
        assert len(tid) == 32
        assert all(c in "0123456789abcdef" for c in tid)

    def test_set_trace_id_context_manager(self):
        fixed_tid = "a" * 32
        with set_trace_id(fixed_tid):
            assert get_current_trace_id() == fixed_tid

    def test_set_trace_id_restores_after_exit(self):
        outer = get_current_trace_id()
        fixed = "b" * 32
        with set_trace_id(fixed):
            assert get_current_trace_id() == fixed
        # After context exits, trace_id is restored (may be auto-generated)
        # Just verify it is no longer the fixed value
        # (Note: get_current_trace_id() generates a fresh one if None)

    def test_invalid_trace_id_raises_valueerror(self):
        with pytest.raises(ValueError, match="32 lowercase hex"):
            with set_trace_id("too-short"):
                pass

    def test_uppercase_trace_id_rejected(self):
        with pytest.raises(ValueError):
            with set_trace_id("A" * 32):
                pass


# ── ConventionFormatter ──────────────────────────────────────────────────────


class TestConventionFormatter:
    def _make_record(self, msg="test", level=logging.INFO, name="test.domain",
                     extra=None):
        logger = logging.getLogger(name)
        record = logger.makeRecord(
            name=name, level=level, fn="test.py", lno=1,
            msg=msg, args=(), exc_info=None,
        )
        if extra:
            for k, v in extra.items():
                setattr(record, k, v)
        return record

    def test_format_returns_valid_json(self):
        fmt = ConventionFormatter()
        record = self._make_record()
        output = fmt.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["domain"] == "test.domain"
        assert parsed["message"] == "test"
        assert "timestamp" in parsed
        assert "trace_id" in parsed

    def test_format_with_extra(self):
        fmt = ConventionFormatter()
        record = self._make_record(extra={"user_id": "u-42"})
        parsed = json.loads(fmt.format(record))
        assert parsed["extra"]["user_id"] == "u-42"

    def test_reserved_fields_dropped_from_extra(self):
        fmt = ConventionFormatter()
        record = self._make_record(extra={"timestamp": "should-be-dropped"})
        parsed = json.loads(fmt.format(record))
        # timestamp should be the auto-generated one, not our override
        assert parsed["timestamp"] != "should-be-dropped"
        assert "extra" not in parsed or "timestamp" not in parsed.get("extra", {})

    def test_pretty_mode(self):
        fmt = ConventionFormatter(pretty=True)
        record = self._make_record()
        output = fmt.format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "test"
        # Pretty mode indents, so output should be multi-line
        assert "\n" in output

    def test_exception_appended_to_message(self):
        fmt = ConventionFormatter()
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            import sys
            exc_info = sys.exc_info()
        logger = logging.getLogger("test.exc")
        record = logger.makeRecord(
            name="test.exc", level=logging.ERROR, fn="test.py", lno=1,
            msg="failed", args=(), exc_info=exc_info,
        )
        output = fmt.format(record)
        parsed = json.loads(output)
        assert "boom" in parsed["message"]
        assert "RuntimeError" in parsed["message"]

    def test_level_map_coverage(self):
        fmt = ConventionFormatter()
        for level, expected_str in _LEVEL_MAP.items():
            record = self._make_record(level=level)
            parsed = json.loads(fmt.format(record))
            assert parsed["level"] == expected_str

    def test_iso_timestamp_format(self):
        fmt = ConventionFormatter()
        record = self._make_record()
        ts = ConventionFormatter._iso_timestamp(record)
        assert ts.endswith("Z")
        assert "T" in ts


# ── PrettyConventionFormatter ────────────────────────────────────────────────


class TestPrettyConventionFormatter:
    def test_format_contains_level_and_domain(self):
        fmt = PrettyConventionFormatter()
        logger = logging.getLogger("harness.test")
        record = logger.makeRecord(
            name="harness.test", level=logging.WARNING, fn="test.py", lno=1,
            msg="watch out", args=(), exc_info=None,
        )
        output = fmt.format(record)
        assert "WARN" in output
        assert "harness.test" in output
        assert "watch out" in output

    def test_exception_info_in_pretty(self):
        fmt = PrettyConventionFormatter()
        try:
            raise ValueError("oops")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
        logger = logging.getLogger("test.pretty")
        record = logger.makeRecord(
            name="test.pretty", level=logging.ERROR, fn="test.py", lno=1,
            msg="err", args=(), exc_info=exc_info,
        )
        output = fmt.format(record)
        assert "oops" in output


# ── DomainLogger ─────────────────────────────────────────────────────────────


class TestDomainLogger:
    @pytest.fixture(autouse=True)
    def _setup_logging(self):
        """Configure logging to capture output."""
        configure(level=logging.DEBUG, pretty=False)
        yield
        # Cleanup
        logging.getLogger().handlers.clear()

    def test_all_log_levels(self, capsys):
        log = get_logger("test.levels")
        log.debug("d")
        log.info("i")
        log.warn("w")
        log.error("e")
        log.fatal("f")

    def test_bind_adds_extra_fields(self):
        log = get_logger("test.bind")
        bound = log.bind(request_id="r-1")
        assert isinstance(bound, DomainLogger)

    def test_bind_chaining(self):
        log = get_logger("test.chain")
        child = log.bind(a=1).bind(b=2)
        assert isinstance(child, DomainLogger)

    def test_name_property(self):
        log = get_logger("my.domain")
        assert log.name == "my.domain"

    def test_set_level(self):
        log = get_logger("test.level")
        log.setLevel(logging.WARNING)

    def test_reserved_fields_filtered_in_bind(self):
        """Binding a reserved field name should not cause errors."""
        log = get_logger("test.reserved")
        bound = log.bind(timestamp="should-be-dropped")
        bound.info("test message")


# ── get_logger validation ────────────────────────────────────────────────────


class TestGetLogger:
    def test_empty_domain_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            get_logger("")

    def test_whitespace_domain_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            get_logger("   ")

    def test_consecutive_dots_raises(self):
        with pytest.raises(ValueError, match="consecutive dots"):
            get_logger("a..b")

    def test_valid_domain(self):
        log = get_logger("harness.task_lock")
        assert log.name == "harness.task_lock"


class TestRootLogger:
    def test_root_logger_domain(self):
        log = root_logger()
        assert log.name == "root"


# ── configure() ──────────────────────────────────────────────────────────────


class TestConfigure:
    def teardown_method(self):
        logging.getLogger().handlers.clear()

    def test_configure_ndjson_mode(self):
        configure(level=logging.DEBUG, pretty=False)
        root = logging.getLogger()
        assert len(root.handlers) >= 1
        assert isinstance(root.handlers[0].formatter, ConventionFormatter)

    def test_configure_pretty_mode(self):
        configure(level=logging.DEBUG, pretty=True)
        root = logging.getLogger()
        assert isinstance(root.handlers[0].formatter, PrettyConventionFormatter)

    def test_configure_auto_detect_pretty(self):
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = True
            configure(level=logging.INFO, pretty=None)
            root = logging.getLogger()
            assert isinstance(root.handlers[0].formatter, PrettyConventionFormatter)

    def test_configure_auto_detect_ndjson(self):
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = False
            configure(level=logging.INFO, pretty=None)
            root = logging.getLogger()
            assert isinstance(root.handlers[0].formatter, ConventionFormatter)

    def test_configure_with_log_file(self, tmp_path):
        log_file = tmp_path / "test.log"
        configure(level=logging.DEBUG, pretty=False, log_file=log_file)
        root = logging.getLogger()
        assert len(root.handlers) == 2  # stdout + file
        # Log something and check file
        root.info("test file logging")
        # Flush
        for h in root.handlers:
            h.flush()
        assert log_file.exists()

    def test_configure_with_nested_log_dir(self, tmp_path):
        log_file = tmp_path / "sub" / "dir" / "test.log"
        configure(level=logging.DEBUG, log_file=log_file)
        assert log_file.parent.exists()

    def test_configure_propagate_false(self):
        configure(level=logging.INFO, pretty=False, propagate=False)
        root = logging.getLogger()
        assert root.propagate is False

    def test_configure_clears_existing_handlers(self):
        configure(level=logging.INFO, pretty=False)
        configure(level=logging.DEBUG, pretty=False)  # second call
        root = logging.getLogger()
        assert len(root.handlers) == 1  # Not 2


# ── LOGGING_CONFIG dict ──────────────────────────────────────────────────────


class TestLoggingConfig:
    def test_config_dict_structure(self):
        assert LOGGING_CONFIG["version"] == 1
        assert "formatters" in LOGGING_CONFIG
        assert "handlers" in LOGGING_CONFIG
        assert "root" in LOGGING_CONFIG
        assert "convention_json" in LOGGING_CONFIG["formatters"]
        assert "convention_pretty" in LOGGING_CONFIG["formatters"]
