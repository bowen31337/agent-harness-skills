"""Tests for harness_skills.models.observe — LogEntry and ObserveResponse.

Coverage targets:
  - LogEntry — required fields, optional extra, field validators
  - LogEntry — trace_id validation (32 hex chars)
  - LogEntry — domain validation (non-empty, no consecutive dots)
  - LogEntry — level validation (accepted values + aliases)
  - LogEntry — JSON serialisation round-trip
  - ObserveResponse — required fields, ge=0 constraints, defaults
  - ObserveResponse — model_dump_json produces valid JSON
  - Integration — _emit() validates via LogEntry in json mode
  - Integration — _emit() falls back to raw on ValidationError
"""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from harness_skills.models.observe import LogEntry, ObserveResponse

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_VALID_ENTRY = {
    "timestamp": "2026-03-20T14:22:05.123Z",
    "level": "INFO",
    "domain": "harness.auth",
    "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
    "message": "user signed in",
    "extra": {"user_id": "u-42"},
}


# ---------------------------------------------------------------------------
# LogEntry — construction and field validation
# ---------------------------------------------------------------------------


class TestLogEntry:
    def test_valid_minimal_entry(self) -> None:
        entry = LogEntry(
            timestamp="2026-03-20T14:22:05.123Z",
            level="INFO",
            domain="harness",
            trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
            message="hello",
        )
        assert entry.level == "INFO"
        assert entry.extra is None

    def test_valid_full_entry(self) -> None:
        entry = LogEntry.model_validate(_VALID_ENTRY)
        assert entry.domain == "harness.auth"
        assert entry.extra == {"user_id": "u-42"}

    def test_all_canonical_levels_accepted(self) -> None:
        for lvl in ("DEBUG", "INFO", "WARN", "ERROR", "FATAL"):
            e = LogEntry.model_validate({**_VALID_ENTRY, "level": lvl})
            assert e.level == lvl

    def test_alias_levels_accepted(self) -> None:
        for lvl in ("WARNING", "CRITICAL"):
            e = LogEntry.model_validate({**_VALID_ENTRY, "level": lvl})
            assert e.level == lvl

    def test_invalid_level_rejected(self) -> None:
        with pytest.raises(ValidationError, match="level"):
            LogEntry.model_validate({**_VALID_ENTRY, "level": "VERBOSE"})

    # ── trace_id validator ────────────────────────────────────────────────

    def test_valid_trace_id_accepted(self) -> None:
        entry = LogEntry.model_validate(_VALID_ENTRY)
        assert entry.trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"

    def test_short_trace_id_rejected(self) -> None:
        with pytest.raises(ValidationError, match="trace_id"):
            LogEntry.model_validate({**_VALID_ENTRY, "trace_id": "abc123"})

    def test_uppercase_trace_id_rejected(self) -> None:
        with pytest.raises(ValidationError, match="trace_id"):
            LogEntry.model_validate(
                {**_VALID_ENTRY, "trace_id": "4BF92F3577B34DA6A3CE929D0E0E4736"}
            )

    def test_non_hex_trace_id_rejected(self) -> None:
        with pytest.raises(ValidationError, match="trace_id"):
            LogEntry.model_validate(
                {**_VALID_ENTRY, "trace_id": "zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"}
            )

    # ── domain validator ──────────────────────────────────────────────────

    def test_simple_domain_accepted(self) -> None:
        entry = LogEntry.model_validate({**_VALID_ENTRY, "domain": "harness"})
        assert entry.domain == "harness"

    def test_nested_domain_accepted(self) -> None:
        entry = LogEntry.model_validate({**_VALID_ENTRY, "domain": "harness.auth.tokens"})
        assert entry.domain == "harness.auth.tokens"

    def test_empty_domain_rejected(self) -> None:
        with pytest.raises(ValidationError, match="domain"):
            LogEntry.model_validate({**_VALID_ENTRY, "domain": ""})

    def test_whitespace_only_domain_rejected(self) -> None:
        with pytest.raises(ValidationError, match="domain"):
            LogEntry.model_validate({**_VALID_ENTRY, "domain": "   "})

    def test_consecutive_dots_domain_rejected(self) -> None:
        with pytest.raises(ValidationError, match="domain"):
            LogEntry.model_validate({**_VALID_ENTRY, "domain": "harness..auth"})

    # ── message validator ─────────────────────────────────────────────────

    def test_empty_message_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LogEntry.model_validate({**_VALID_ENTRY, "message": ""})

    # ── extra field ───────────────────────────────────────────────────────

    def test_extra_field_accepted(self) -> None:
        entry = LogEntry.model_validate(
            {**_VALID_ENTRY, "extra": {"request_id": "r-99", "status": 200}}
        )
        assert entry.extra == {"request_id": "r-99", "status": 200}

    def test_extra_none_by_default(self) -> None:
        entry = LogEntry.model_validate({k: v for k, v in _VALID_ENTRY.items() if k != "extra"})
        assert entry.extra is None

    # ── JSON round-trip ───────────────────────────────────────────────────

    def test_json_serialisation_round_trip(self) -> None:
        entry = LogEntry.model_validate(_VALID_ENTRY)
        raw_json = entry.model_dump_json()
        data = json.loads(raw_json)
        assert data["timestamp"] == _VALID_ENTRY["timestamp"]
        assert data["level"] == "INFO"
        assert data["domain"] == "harness.auth"
        assert data["trace_id"] == _VALID_ENTRY["trace_id"]
        assert data["message"] == "user signed in"
        assert data["extra"] == {"user_id": "u-42"}

    def test_json_contains_all_required_keys(self) -> None:
        entry = LogEntry.model_validate(_VALID_ENTRY)
        data = json.loads(entry.model_dump_json())
        for key in ("timestamp", "level", "domain", "trace_id", "message"):
            assert key in data


# ---------------------------------------------------------------------------
# ObserveResponse — construction and validation
# ---------------------------------------------------------------------------


class TestObserveResponse:
    def _make(self, **overrides) -> ObserveResponse:
        defaults = dict(
            log_file="logs/harness.ndjson",
            lines_scanned=100,
            entries_matched=20,
            entries_emitted=20,
        )
        defaults.update(overrides)
        return ObserveResponse(**defaults)

    def test_default_command_field(self) -> None:
        r = self._make()
        assert r.command == "harness observe"

    def test_defaults_for_optional_fields(self) -> None:
        r = self._make()
        assert r.validation_errors == 0
        assert r.domain_filter is None
        assert r.trace_id_filter is None
        assert r.min_level == "DEBUG"

    def test_with_all_fields(self) -> None:
        r = self._make(
            validation_errors=3,
            domain_filter="harness.auth",
            trace_id_filter="4bf92f3577b34da6a3ce929d0e0e4736",
            min_level="ERROR",
        )
        assert r.validation_errors == 3
        assert r.domain_filter == "harness.auth"
        assert r.min_level == "ERROR"

    def test_negative_counts_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._make(lines_scanned=-1)

    def test_negative_validation_errors_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._make(validation_errors=-1)

    def test_json_serialisation(self) -> None:
        r = self._make(entries_matched=5, entries_emitted=5, validation_errors=1)
        data = json.loads(r.model_dump_json())
        assert data["command"] == "harness observe"
        assert data["lines_scanned"] == 100
        assert data["entries_matched"] == 5
        assert data["validation_errors"] == 1

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            ObserveResponse(
                log_file="x",
                lines_scanned=0,
                entries_matched=0,
                entries_emitted=0,
                unknown_field="oops",
            )


# ---------------------------------------------------------------------------
# Integration — _emit() uses LogEntry for JSON validation
# ---------------------------------------------------------------------------


class TestEmitValidation:
    """White-box tests for harness_skills.cli.observe._emit()."""

    def _get_emit(self):
        from harness_skills.cli.observe import _emit
        return _emit

    def test_valid_entry_emitted_as_validated_json(self, capsys) -> None:
        _emit = self._get_emit()
        raw = json.dumps(_VALID_ENTRY)
        result = _emit(raw, _VALID_ENTRY, output_format="json", color=False)
        captured = capsys.readouterr()
        assert result is True
        # Output should be valid JSON containing the same fields
        data = json.loads(captured.out.strip())
        assert data["level"] == "INFO"
        assert data["message"] == "user signed in"

    def test_invalid_entry_falls_back_to_raw(self, capsys) -> None:
        _emit = self._get_emit()
        # Missing required 'message' field → ValidationError
        invalid = {**_VALID_ENTRY, "message": ""}  # empty message fails min_length=1
        raw = json.dumps(invalid)
        result = _emit(raw, invalid, output_format="json", color=False)
        captured = capsys.readouterr()
        assert result is False
        # Should have emitted the raw line unchanged
        assert captured.out.strip() == raw

    def test_invalid_trace_id_falls_back_to_raw(self, capsys) -> None:
        _emit = self._get_emit()
        bad_entry = {**_VALID_ENTRY, "trace_id": "tooshort"}
        raw = json.dumps(bad_entry)
        result = _emit(raw, bad_entry, output_format="json", color=False)
        assert result is False

    def test_pretty_mode_does_not_validate(self, capsys) -> None:
        _emit = self._get_emit()
        # Even a non-conforming entry should return True in pretty mode
        bad_entry = {**_VALID_ENTRY, "trace_id": "tooshort"}
        raw = json.dumps(bad_entry)
        result = _emit(raw, bad_entry, output_format="pretty", color=False)
        assert result is True
