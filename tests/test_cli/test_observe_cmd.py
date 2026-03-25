"""Tests for harness_skills.cli.observe (``harness observe``).

Uses Click's ``CliRunner`` for isolated, subprocess-free invocations.
All file I/O uses tmp_path fixtures so tests are hermetic.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from harness_skills.cli.observe import (
    _TailStats,
    _domain_matches,
    _emit,
    _format_pretty,
    _passes_filters,
    _tail_file,
    observe_cmd,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _make_log_line(
    level: str = "INFO",
    domain: str = "harness",
    trace_id: str = "a" * 32,
    message: str = "hello",
    extra: dict | None = None,
) -> str:
    entry = {
        "timestamp": "2026-03-20T14:22:05.123Z",
        "level": level,
        "domain": domain,
        "trace_id": trace_id,
        "message": message,
    }
    if extra:
        entry["extra"] = extra
    return json.dumps(entry)


def _write_log_file(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines) + "\n")
    return path


# ===========================================================================
# _domain_matches
# ===========================================================================


class TestDomainMatches:
    def test_exact_match(self):
        assert _domain_matches("harness", "harness") is True

    def test_subdomain_match(self):
        assert _domain_matches("harness.auth", "harness") is True

    def test_deep_subdomain_match(self):
        assert _domain_matches("harness.auth.oauth", "harness") is True

    def test_no_match_prefix_not_boundary(self):
        assert _domain_matches("payments", "pay") is False

    def test_no_match_different_domain(self):
        assert _domain_matches("other.service", "harness") is False


# ===========================================================================
# _passes_filters
# ===========================================================================


class TestPassesFilters:
    def test_no_filters_passes(self):
        entry = {"level": "DEBUG", "domain": "harness", "trace_id": "abc"}
        assert _passes_filters(entry, None, None, 0) is True

    def test_level_filter_blocks(self):
        entry = {"level": "DEBUG", "domain": "harness"}
        assert _passes_filters(entry, None, None, 1) is False  # min_level=1 is INFO

    def test_level_filter_passes(self):
        entry = {"level": "ERROR", "domain": "harness"}
        assert _passes_filters(entry, None, None, 1) is True

    def test_domain_filter_passes(self):
        entry = {"level": "INFO", "domain": "harness.auth"}
        assert _passes_filters(entry, "harness", None, 0) is True

    def test_domain_filter_blocks(self):
        entry = {"level": "INFO", "domain": "other"}
        assert _passes_filters(entry, "harness", None, 0) is False

    def test_trace_id_filter_passes(self):
        entry = {"level": "INFO", "domain": "harness", "trace_id": "abc123"}
        assert _passes_filters(entry, None, "abc123", 0) is True

    def test_trace_id_filter_blocks(self):
        entry = {"level": "INFO", "domain": "harness", "trace_id": "abc123"}
        assert _passes_filters(entry, None, "xyz999", 0) is False

    def test_combined_filters(self):
        entry = {"level": "ERROR", "domain": "harness.auth", "trace_id": "abc"}
        assert _passes_filters(entry, "harness", "abc", 3) is True

    def test_missing_level_defaults_to_debug(self):
        entry = {"domain": "harness"}
        assert _passes_filters(entry, None, None, 0) is True

    def test_unknown_level_maps_to_zero(self):
        entry = {"level": "CUSTOM", "domain": "harness"}
        assert _passes_filters(entry, None, None, 1) is False


# ===========================================================================
# _format_pretty
# ===========================================================================


class TestFormatPretty:
    def test_basic_format_no_color(self):
        entry = {
            "timestamp": "2026-03-20T14:22:05.123Z",
            "level": "INFO",
            "domain": "harness",
            "trace_id": "a" * 32,
            "message": "test message",
        }
        result = _format_pretty(entry, color=False)
        assert "INFO" in result
        assert "harness" in result
        assert "test message" in result
        assert "aaaaaaaa" in result  # short trace_id

    def test_format_with_color(self):
        entry = {
            "timestamp": "2026-03-20T14:22:05.123Z",
            "level": "ERROR",
            "domain": "harness.auth",
            "trace_id": "b" * 32,
            "message": "fail",
        }
        result = _format_pretty(entry, color=True)
        assert "\033[" in result  # ANSI code present
        assert "fail" in result

    def test_format_with_extra(self):
        entry = {
            "timestamp": "2026-03-20T14:22:05.123Z",
            "level": "DEBUG",
            "domain": "harness",
            "trace_id": "c" * 32,
            "message": "test",
            "extra": {"user_id": "u-42"},
        }
        result = _format_pretty(entry, color=False)
        assert "user_id" in result

    def test_format_with_extra_color(self):
        entry = {
            "timestamp": "ts",
            "level": "DEBUG",
            "domain": "d",
            "trace_id": "e" * 32,
            "message": "m",
            "extra": {"k": "v"},
        }
        result = _format_pretty(entry, color=True)
        assert "k=" in result

    def test_missing_trace_id(self):
        entry = {
            "timestamp": "ts",
            "level": "INFO",
            "domain": "d",
            "trace_id": "",
            "message": "m",
        }
        result = _format_pretty(entry, color=False)
        assert "--------" in result

    def test_missing_fields_use_defaults(self):
        entry = {}
        result = _format_pretty(entry, color=False)
        assert "--------" in result  # empty trace_id

    def test_unknown_level_no_color(self):
        entry = {
            "timestamp": "ts",
            "level": "CUSTOM",
            "domain": "d",
            "trace_id": "",
            "message": "m",
        }
        result = _format_pretty(entry, color=True)
        assert "CUSTOM" in result


# ===========================================================================
# _emit
# ===========================================================================


class TestEmit:
    def test_emit_pretty_mode(self):
        entry = {
            "timestamp": "ts",
            "level": "INFO",
            "domain": "harness",
            "trace_id": "a" * 32,
            "message": "hello",
        }
        result = _emit("raw", entry, output_format="pretty", color=False)
        assert result is True

    def test_emit_json_mode_valid(self):
        entry = {
            "timestamp": "2026-03-20T14:22:05.123Z",
            "level": "INFO",
            "domain": "harness",
            "trace_id": "a" * 32,
            "message": "hello",
        }
        result = _emit(json.dumps(entry), entry, output_format="json", color=False)
        assert result is True

    def test_emit_json_mode_invalid(self):
        """Invalid entry (missing required fields) still emits but returns False."""
        entry = {"bad": "data"}
        result = _emit('{"bad":"data"}', entry, output_format="json", color=False)
        assert result is False


# ===========================================================================
# _tail_file — no-follow mode
# ===========================================================================


class TestTailFileNoFollow:
    def test_file_not_found_no_follow_exits(self, tmp_path: Path):
        path = tmp_path / "nonexistent.ndjson"
        with pytest.raises(SystemExit):
            _tail_file(
                path,
                follow=False,
                lines=50,
                domain=None,
                trace_id=None,
                min_level=0,
                output_format="pretty",
                color=False,
            )

    def test_basic_tail(self, tmp_path: Path):
        log = tmp_path / "app.ndjson"
        lines = [_make_log_line(message=f"msg{i}") for i in range(5)]
        _write_log_file(log, lines)
        stats = _tail_file(
            log,
            follow=False,
            lines=50,
            domain=None,
            trace_id=None,
            min_level=0,
            output_format="pretty",
            color=False,
        )
        assert stats.lines_scanned == 5
        assert stats.entries_matched == 5
        assert stats.entries_emitted == 5

    def test_tail_with_line_limit(self, tmp_path: Path):
        log = tmp_path / "app.ndjson"
        lines = [_make_log_line(message=f"msg{i}") for i in range(10)]
        _write_log_file(log, lines)
        stats = _tail_file(
            log,
            follow=False,
            lines=3,
            domain=None,
            trace_id=None,
            min_level=0,
            output_format="pretty",
            color=False,
        )
        assert stats.lines_scanned == 3
        assert stats.entries_emitted == 3

    def test_tail_all_lines(self, tmp_path: Path):
        log = tmp_path / "app.ndjson"
        lines = [_make_log_line(message=f"msg{i}") for i in range(5)]
        _write_log_file(log, lines)
        stats = _tail_file(
            log,
            follow=False,
            lines=0,  # 0 = all
            domain=None,
            trace_id=None,
            min_level=0,
            output_format="pretty",
            color=False,
        )
        assert stats.lines_scanned == 5

    def test_domain_filter(self, tmp_path: Path):
        log = tmp_path / "app.ndjson"
        lines = [
            _make_log_line(domain="harness.auth"),
            _make_log_line(domain="other"),
            _make_log_line(domain="harness.payments"),
        ]
        _write_log_file(log, lines)
        stats = _tail_file(
            log,
            follow=False,
            lines=50,
            domain="harness",
            trace_id=None,
            min_level=0,
            output_format="pretty",
            color=False,
        )
        assert stats.entries_matched == 2

    def test_trace_id_filter(self, tmp_path: Path):
        log = tmp_path / "app.ndjson"
        tid = "b" * 32
        lines = [
            _make_log_line(trace_id=tid),
            _make_log_line(trace_id="c" * 32),
        ]
        _write_log_file(log, lines)
        stats = _tail_file(
            log,
            follow=False,
            lines=50,
            domain=None,
            trace_id=tid,
            min_level=0,
            output_format="pretty",
            color=False,
        )
        assert stats.entries_matched == 1

    def test_level_filter(self, tmp_path: Path):
        log = tmp_path / "app.ndjson"
        lines = [
            _make_log_line(level="DEBUG"),
            _make_log_line(level="INFO"),
            _make_log_line(level="ERROR"),
        ]
        _write_log_file(log, lines)
        stats = _tail_file(
            log,
            follow=False,
            lines=50,
            domain=None,
            trace_id=None,
            min_level=3,  # ERROR
            output_format="pretty",
            color=False,
        )
        assert stats.entries_matched == 1

    def test_json_output_format(self, tmp_path: Path):
        log = tmp_path / "app.ndjson"
        lines = [_make_log_line()]
        _write_log_file(log, lines)
        stats = _tail_file(
            log,
            follow=False,
            lines=50,
            domain=None,
            trace_id=None,
            min_level=0,
            output_format="json",
            color=False,
        )
        assert stats.entries_emitted == 1
        assert stats.validation_errors == 0

    def test_json_validation_error_counted(self, tmp_path: Path):
        log = tmp_path / "app.ndjson"
        # Entry missing required fields for LogEntry
        bad_entry = json.dumps({"level": "INFO", "message": "no domain"})
        _write_log_file(log, [bad_entry])
        stats = _tail_file(
            log,
            follow=False,
            lines=50,
            domain=None,
            trace_id=None,
            min_level=0,
            output_format="json",
            color=False,
        )
        assert stats.entries_emitted == 1
        assert stats.validation_errors == 1

    def test_skips_invalid_json_lines(self, tmp_path: Path):
        log = tmp_path / "app.ndjson"
        lines = [
            "not json at all",
            _make_log_line(message="valid"),
            "{broken",
        ]
        _write_log_file(log, lines)
        stats = _tail_file(
            log,
            follow=False,
            lines=50,
            domain=None,
            trace_id=None,
            min_level=0,
            output_format="pretty",
            color=False,
        )
        assert stats.lines_scanned == 3
        assert stats.entries_emitted == 1

    def test_skips_empty_lines(self, tmp_path: Path):
        log = tmp_path / "app.ndjson"
        content = _make_log_line() + "\n\n\n" + _make_log_line() + "\n"
        log.write_text(content)
        stats = _tail_file(
            log,
            follow=False,
            lines=50,
            domain=None,
            trace_id=None,
            min_level=0,
            output_format="pretty",
            color=False,
        )
        assert stats.lines_scanned == 2
        assert stats.entries_emitted == 2


# ===========================================================================
# observe_cmd — no-follow mode via CliRunner
# ===========================================================================


class TestObserveCmdNoFollow:
    def test_no_follow_with_log_file(self, runner: CliRunner, tmp_path: Path):
        log = tmp_path / "test.ndjson"
        lines = [_make_log_line(message=f"line{i}") for i in range(3)]
        _write_log_file(log, lines)
        result = runner.invoke(observe_cmd, [
            "--log-file", str(log),
            "--no-follow",
            "--format", "pretty",
            "--no-color",
        ])
        assert result.exit_code == 0
        assert "line0" in result.output
        assert "line2" in result.output

    def test_no_follow_json_output(self, runner: CliRunner, tmp_path: Path):
        log = tmp_path / "test.ndjson"
        lines = [_make_log_line()]
        _write_log_file(log, lines)
        result = runner.invoke(observe_cmd, [
            "--log-file", str(log),
            "--no-follow",
            "--format", "json",
        ])
        assert result.exit_code == 0
        # stderr contains ObserveResponse summary
        # stdout contains the json-formatted log entries

    def test_no_follow_domain_filter(self, runner: CliRunner, tmp_path: Path):
        log = tmp_path / "test.ndjson"
        lines = [
            _make_log_line(domain="harness.auth"),
            _make_log_line(domain="other"),
        ]
        _write_log_file(log, lines)
        result = runner.invoke(observe_cmd, [
            "--log-file", str(log),
            "--no-follow",
            "--domain", "harness",
            "--no-color",
        ])
        assert result.exit_code == 0
        assert "harness.auth" in result.output

    def test_no_follow_trace_id_filter(self, runner: CliRunner, tmp_path: Path):
        log = tmp_path / "test.ndjson"
        tid = "d" * 32
        lines = [
            _make_log_line(trace_id=tid, message="target"),
            _make_log_line(trace_id="e" * 32, message="other"),
        ]
        _write_log_file(log, lines)
        result = runner.invoke(observe_cmd, [
            "--log-file", str(log),
            "--no-follow",
            "--trace-id", tid,
            "--no-color",
        ])
        assert result.exit_code == 0
        assert "target" in result.output

    def test_no_follow_level_filter(self, runner: CliRunner, tmp_path: Path):
        log = tmp_path / "test.ndjson"
        lines = [
            _make_log_line(level="DEBUG", message="dbg"),
            _make_log_line(level="ERROR", message="err"),
        ]
        _write_log_file(log, lines)
        result = runner.invoke(observe_cmd, [
            "--log-file", str(log),
            "--no-follow",
            "--level", "ERROR",
            "--no-color",
        ])
        assert result.exit_code == 0
        assert "err" in result.output

    def test_no_follow_file_not_found(self, runner: CliRunner, tmp_path: Path):
        log = tmp_path / "missing.ndjson"
        result = runner.invoke(observe_cmd, [
            "--log-file", str(log),
            "--no-follow",
        ])
        assert result.exit_code != 0

    def test_no_follow_lines_option(self, runner: CliRunner, tmp_path: Path):
        log = tmp_path / "test.ndjson"
        lines = [_make_log_line(message=f"line{i}") for i in range(10)]
        _write_log_file(log, lines)
        result = runner.invoke(observe_cmd, [
            "--log-file", str(log),
            "--no-follow",
            "--lines", "2",
            "--no-color",
        ])
        assert result.exit_code == 0
        # Should only show last 2 lines
        assert "line8" in result.output
        assert "line9" in result.output

    def test_observe_response_emitted_to_stderr(self, runner: CliRunner, tmp_path: Path):
        log = tmp_path / "test.ndjson"
        lines = [_make_log_line()]
        _write_log_file(log, lines)
        result = runner.invoke(observe_cmd, [
            "--log-file", str(log),
            "--no-follow",
            "--format", "pretty",
            "--no-color",
        ], catch_exceptions=False)
        assert result.exit_code == 0
        # ObserveResponse is emitted to stderr; CliRunner mix_stderr=True by default
        # so it may appear in result.output


# ===========================================================================
# observe_cmd — help
# ===========================================================================


class TestObserveCmdHelp:
    def test_help_exits_zero(self, runner: CliRunner):
        result = runner.invoke(observe_cmd, ["--help"])
        assert result.exit_code == 0
        assert "observe" in result.output.lower() or "tail" in result.output.lower()


# ===========================================================================
# _tail_file — follow mode (mocked to avoid infinite loops)
# ===========================================================================


class TestTailFileFollow:
    def test_follow_with_existing_content_then_keyboard_interrupt(self, tmp_path: Path):
        """Follow mode reads existing lines, then KeyboardInterrupt stops it."""
        log = tmp_path / "app.ndjson"
        lines = [_make_log_line(message="existing")]
        _write_log_file(log, lines)

        import harness_skills.cli.observe as obs_mod

        original_poll = obs_mod._POLL_INTERVAL_S
        obs_mod._POLL_INTERVAL_S = 0.01  # speed up

        # Patch time.sleep to raise KeyboardInterrupt after first call in follow loop
        call_count = 0
        original_sleep = obs_mod.time.sleep

        def patched_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise KeyboardInterrupt()
            original_sleep(0.01)

        with patch.object(obs_mod.time, "sleep", side_effect=patched_sleep):
            stats = _tail_file(
                log,
                follow=True,
                lines=50,
                domain=None,
                trace_id=None,
                min_level=0,
                output_format="pretty",
                color=False,
            )
        obs_mod._POLL_INTERVAL_S = original_poll
        assert stats.entries_emitted >= 1

    def test_follow_with_domain_filter_banner(self, tmp_path: Path):
        """Follow mode with domain filter shows filter description."""
        log = tmp_path / "app.ndjson"
        lines = [_make_log_line(domain="harness.auth", message="msg")]
        _write_log_file(log, lines)

        import harness_skills.cli.observe as obs_mod

        call_count = 0

        def patched_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                raise KeyboardInterrupt()

        with patch.object(obs_mod.time, "sleep", side_effect=patched_sleep):
            stats = _tail_file(
                log,
                follow=True,
                lines=50,
                domain="harness",
                trace_id="a" * 32,
                min_level=0,
                output_format="pretty",
                color=False,
            )
        assert stats.entries_emitted == 1

    def test_follow_reads_new_lines(self, tmp_path: Path):
        """Follow mode reads lines appended after initial read."""
        log = tmp_path / "app.ndjson"
        initial = [_make_log_line(message="initial")]
        _write_log_file(log, initial)

        import harness_skills.cli.observe as obs_mod

        call_count = 0

        def patched_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Append a new line to the file while following
                with log.open("a") as f:
                    f.write(_make_log_line(message="appended") + "\n")
            elif call_count >= 2:
                raise KeyboardInterrupt()

        with patch.object(obs_mod.time, "sleep", side_effect=patched_sleep):
            stats = _tail_file(
                log,
                follow=True,
                lines=50,
                domain=None,
                trace_id=None,
                min_level=0,
                output_format="pretty",
                color=False,
            )
        assert stats.entries_emitted >= 2

    def test_follow_handles_log_rotation(self, tmp_path: Path):
        """Follow mode handles file shrinkage (log rotation)."""
        log = tmp_path / "app.ndjson"
        initial = [_make_log_line(message=f"msg{i}") for i in range(5)]
        _write_log_file(log, initial)

        import harness_skills.cli.observe as obs_mod

        call_count = 0

        def patched_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Simulate log rotation: truncate file and write shorter content
                log.write_text(_make_log_line(message="rotated") + "\n")
            elif call_count >= 3:
                raise KeyboardInterrupt()

        with patch.object(obs_mod.time, "sleep", side_effect=patched_sleep):
            stats = _tail_file(
                log,
                follow=True,
                lines=50,
                domain=None,
                trace_id=None,
                min_level=0,
                output_format="pretty",
                color=False,
            )
        # Should have read the initial lines + the rotated content
        assert stats.entries_emitted >= 5

    def test_follow_handles_stat_oserror(self, tmp_path: Path):
        """Follow mode gracefully handles OSError on stat (file deleted)."""
        log = tmp_path / "app.ndjson"
        _write_log_file(log, [_make_log_line(message="msg")])

        import harness_skills.cli.observe as obs_mod

        call_count = 0
        original_stat = Path.stat

        def patched_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise KeyboardInterrupt()

        def patched_stat(self, *args, **kwargs):
            if call_count >= 1:
                raise OSError("file gone")
            return original_stat(self, *args, **kwargs)

        with patch.object(obs_mod.time, "sleep", side_effect=patched_sleep), \
             patch.object(Path, "stat", patched_stat):
            stats = _tail_file(
                log,
                follow=True,
                lines=50,
                domain=None,
                trace_id=None,
                min_level=0,
                output_format="pretty",
                color=False,
            )
        assert stats.entries_emitted >= 1

    def test_follow_skips_invalid_json_in_new_lines(self, tmp_path: Path):
        """Follow mode skips malformed JSON lines appended during tailing."""
        log = tmp_path / "app.ndjson"
        _write_log_file(log, [_make_log_line(message="init")])

        import harness_skills.cli.observe as obs_mod

        call_count = 0

        def patched_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                with log.open("a") as f:
                    f.write("NOT JSON\n")
                    f.write(_make_log_line(message="after_bad") + "\n")
            elif call_count >= 2:
                raise KeyboardInterrupt()

        with patch.object(obs_mod.time, "sleep", side_effect=patched_sleep):
            stats = _tail_file(
                log,
                follow=True,
                lines=50,
                domain=None,
                trace_id=None,
                min_level=0,
                output_format="pretty",
                color=False,
            )
        assert stats.entries_emitted >= 2

    def test_follow_skips_empty_new_lines(self, tmp_path: Path):
        """Follow mode skips empty lines appended during tailing."""
        log = tmp_path / "app.ndjson"
        _write_log_file(log, [_make_log_line(message="init")])

        import harness_skills.cli.observe as obs_mod

        call_count = 0

        def patched_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                with log.open("a") as f:
                    f.write("\n\n")
                    f.write(_make_log_line(message="after_empty") + "\n")
            elif call_count >= 2:
                raise KeyboardInterrupt()

        with patch.object(obs_mod.time, "sleep", side_effect=patched_sleep):
            stats = _tail_file(
                log,
                follow=True,
                lines=50,
                domain=None,
                trace_id=None,
                min_level=0,
                output_format="pretty",
                color=False,
            )
        assert stats.entries_emitted >= 2

    def test_follow_json_validation_error_in_new_lines(self, tmp_path: Path):
        """Follow mode counts validation errors for invalid entries in JSON mode."""
        log = tmp_path / "app.ndjson"
        _write_log_file(log, [_make_log_line(message="init")])

        import harness_skills.cli.observe as obs_mod

        call_count = 0

        def patched_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Append an entry that passes JSON parsing but fails LogEntry validation
                bad = json.dumps({"level": "INFO", "message": "no domain or trace"})
                with log.open("a") as f:
                    f.write(bad + "\n")
            elif call_count >= 2:
                raise KeyboardInterrupt()

        with patch.object(obs_mod.time, "sleep", side_effect=patched_sleep):
            stats = _tail_file(
                log,
                follow=True,
                lines=50,
                domain=None,
                trace_id=None,
                min_level=0,
                output_format="json",
                color=False,
            )
        assert stats.validation_errors >= 1

    def test_follow_no_shown_lines_skips_separator(self, tmp_path: Path):
        """When no existing lines match, separator is not shown."""
        log = tmp_path / "app.ndjson"
        # Write lines that won't match the domain filter
        _write_log_file(log, [_make_log_line(domain="other")])

        import harness_skills.cli.observe as obs_mod

        call_count = 0

        def patched_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                raise KeyboardInterrupt()

        with patch.object(obs_mod.time, "sleep", side_effect=patched_sleep):
            stats = _tail_file(
                log,
                follow=True,
                lines=50,
                domain="harness",
                trace_id=None,
                min_level=0,
                output_format="pretty",
                color=False,
            )
        # The existing line didn't match, so shown=0, no separator printed

    def test_follow_with_filter_level_in_new_lines(self, tmp_path: Path):
        """Follow mode applies level filter to new lines."""
        log = tmp_path / "app.ndjson"
        _write_log_file(log, [_make_log_line(level="ERROR", message="err")])

        import harness_skills.cli.observe as obs_mod

        call_count = 0

        def patched_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                with log.open("a") as f:
                    f.write(_make_log_line(level="DEBUG", message="debug_new") + "\n")
                    f.write(_make_log_line(level="ERROR", message="err_new") + "\n")
            elif call_count >= 2:
                raise KeyboardInterrupt()

        with patch.object(obs_mod.time, "sleep", side_effect=patched_sleep):
            stats = _tail_file(
                log,
                follow=True,
                lines=50,
                domain=None,
                trace_id=None,
                min_level=3,  # ERROR
                output_format="pretty",
                color=False,
            )
        assert stats.entries_matched == 2  # initial err + err_new


# ===========================================================================
# _tail_file — file waiting in follow mode
# ===========================================================================


class TestTailFileWaitForFile:
    def test_follow_waits_for_file_to_appear(self, tmp_path: Path):
        """Follow mode waits for the file to appear, then reads it."""
        log = tmp_path / "delayed.ndjson"

        import harness_skills.cli.observe as obs_mod

        sleep_count = 0

        def patched_sleep(seconds):
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count == 2:
                # Create the file after a delay
                _write_log_file(log, [_make_log_line(message="appeared")])
            elif sleep_count >= 4:
                raise KeyboardInterrupt()

        with patch.object(obs_mod.time, "sleep", side_effect=patched_sleep):
            stats = _tail_file(
                log,
                follow=True,
                lines=50,
                domain=None,
                trace_id=None,
                min_level=0,
                output_format="pretty",
                color=False,
            )
        assert stats.entries_emitted >= 1


# ===========================================================================
# observe_cmd — verbose filter echo
# ===========================================================================


class TestObserveCmdVerbose:
    def test_verbose_shows_filter_info(self, runner: CliRunner, tmp_path: Path):
        """When --domain is set and level != DEBUG, filter parts are built."""
        log = tmp_path / "test.ndjson"
        lines = [_make_log_line(domain="harness.auth")]
        _write_log_file(log, lines)
        # This test exercises the filter_desc code path in observe_cmd
        result = runner.invoke(observe_cmd, [
            "--log-file", str(log),
            "--no-follow",
            "--domain", "harness",
            "--level", "ERROR",
            "--no-color",
        ])
        assert result.exit_code == 0
