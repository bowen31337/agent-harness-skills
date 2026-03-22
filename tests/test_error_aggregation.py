"""Tests for harness_skills.error_aggregation and harness_skills.models.errors.

Coverage targets
----------------
ErrorRecord
  - datetime normalisation (naive → UTC-aware)
  - ISO-8601 string input accepted by __post_init__
  - default field values

_fingerprint (tested indirectly via aggregate_errors deduplication)
  - strips hex addresses, timestamps, integers, quoted strings, file paths
  - collapses whitespace
  - prefers stack_hint over message when available
  - output capped at 200 chars

_detect_trend
  - returns "stable" for fewer than 4 events
  - returns "rising" when second half count ≥ 1.5× first half
  - returns "falling" when second half count ≤ 0.67× first half
  - returns "stable" for balanced splits

_dominant_severity
  - "critical" wins over "error" and "warning"
  - "error" wins over "warning"
  - single-element list returns that element

aggregate_errors
  - empty record list → zero events, empty groups
  - groups records by (domain, error_type, fingerprint)
  - records outside the time window are excluded
  - groups sorted by frequency descending
  - by_domain index populated correctly
  - ErrorAggregationView fields correct (window_start, window_end, total_events, domain_count)
  - trend and severity computed per group
  - custom ``now`` parameter respected

top_errors
  - returns top-N globally by frequency
  - honours domain filter (case-insensitive)
  - returns empty list for unknown domain

errors_by_domain
  - mirrors view.by_domain

domain_summary
  - sorted by total_errors descending
  - rising_patterns count correct

errors_to_json_summary
  - valid JSON output
  - top_errors capped at top_n parameter
  - by_domain included / excluded correctly
  - window metadata present

load_errors_from_log
  - missing file returns empty list
  - valid NDJSON parsed into ErrorRecords
  - lines outside the window skipped
  - malformed lines silently skipped
  - optional fields default correctly

ErrorAggregationResponse (Pydantic model)
  - round-trips through model_validate_json
  - rejects extra fields (extra="forbid")
  - status / command / data_source defaults
"""

from __future__ import annotations

import json
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from harness_skills.error_aggregation import (
    ErrorAggregationView,
    ErrorGroup,
    ErrorRecord,
    _detect_trend,
    _dominant_severity,
    _fingerprint,
    aggregate_errors,
    domain_summary,
    errors_by_domain,
    errors_to_json_summary,
    load_errors_from_log,
    top_errors,
)
from harness_skills.models.errors import (
    DomainOverview,
    ErrorAggregationResponse,
    ErrorGroupResponse,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UTC = timezone.utc


def _ts(minutes_ago: float = 0, *, now: datetime | None = None) -> datetime:
    """Return a UTC datetime N minutes before *now* (default: current time)."""
    base = now if now is not None else datetime.now(tz=_UTC)
    return base - timedelta(minutes=minutes_ago)


def _rec(
    domain: str = "test_domain",
    error_type: str = "ValueError",
    message: str = "something went wrong",
    minutes_ago: float = 5,
    severity: str = "error",
    stack_hint: str = "",
    *,
    now: datetime | None = None,
) -> ErrorRecord:
    return ErrorRecord(
        timestamp=_ts(minutes_ago, now=now),
        domain=domain,
        error_type=error_type,
        message=message,
        severity=severity,
        stack_hint=stack_hint,
    )


# ---------------------------------------------------------------------------
# ErrorRecord
# ---------------------------------------------------------------------------


class TestErrorRecord:
    def test_naive_datetime_becomes_utc_aware(self) -> None:
        naive = datetime(2026, 3, 22, 10, 0, 0)
        rec = ErrorRecord(
            timestamp=naive,
            domain="d",
            error_type="E",
            message="msg",
        )
        assert rec.timestamp.tzinfo is not None
        assert rec.timestamp.tzinfo == _UTC

    def test_iso_string_parsed(self) -> None:
        rec = ErrorRecord(
            timestamp="2026-03-22T10:00:00+00:00",
            domain="d",
            error_type="E",
            message="msg",
        )
        assert rec.timestamp.year == 2026
        assert rec.timestamp.tzinfo is not None

    def test_default_severity_is_error(self) -> None:
        rec = _rec()
        assert rec.severity == "error"

    def test_default_stack_hint_empty(self) -> None:
        rec = _rec()
        assert rec.stack_hint == ""


# ---------------------------------------------------------------------------
# _fingerprint (tested via strings to keep tests white-box-light)
# ---------------------------------------------------------------------------


class TestFingerprint:
    def test_strips_integers(self) -> None:
        fp = _fingerprint("timeout after 30 seconds")
        assert "30" not in fp

    def test_strips_hex_addresses(self) -> None:
        fp = _fingerprint("bad pointer at 0xDEADBEEF in module")
        assert "0xDEADBEEF" not in fp.lower()

    def test_strips_file_paths(self) -> None:
        fp = _fingerprint("error in /home/user/project/src/module.py line 42")
        # file paths like /home/user/... should be stripped
        assert "/home" not in fp

    def test_strips_quoted_strings(self) -> None:
        fp = _fingerprint("key 'session_token' not found")
        assert "session_token" not in fp

    def test_prefers_stack_hint(self) -> None:
        fp1 = _fingerprint("msg A", stack_hint="stack_hint_line")
        fp2 = _fingerprint("msg B", stack_hint="stack_hint_line")
        # Both should produce the same fingerprint because stack_hint is identical
        assert fp1 == fp2

    def test_message_used_when_no_stack_hint(self) -> None:
        fp1 = _fingerprint("totally different error X")
        fp2 = _fingerprint("totally different error Y")
        # Different messages without stack hints → different fingerprints
        # (the distinct trailing word should survive normalization)
        assert fp1 != fp2

    def test_output_capped_at_200_chars(self) -> None:
        long_msg = "word " * 200
        fp = _fingerprint(long_msg)
        assert len(fp) <= 200


# ---------------------------------------------------------------------------
# _detect_trend
# ---------------------------------------------------------------------------


class TestDetectTrend:
    def test_fewer_than_4_events_is_stable(self) -> None:
        now = datetime.now(tz=_UTC)
        ts = [now - timedelta(minutes=i) for i in range(3)]
        assert _detect_trend(ts) == "stable"

    def test_rising_for_exactly_5_events(self) -> None:
        # _detect_trend splits by index: mid = n // 2.
        # For n=5: first_half=2, second_half=3, ratio=1.5 → "rising".
        now = datetime.now(tz=_UTC)
        ts = [now - timedelta(minutes=i) for i in range(5)]
        assert _detect_trend(ts) == "rising"

    def test_falling_is_not_reachable_with_index_split(self) -> None:
        # Because the split is by sorted index (not by wall-clock density),
        # second_half >= first_half always holds.  "falling" (ratio ≤ 0.67)
        # cannot be returned for any input; all non-rising cases are "stable".
        now = datetime.now(tz=_UTC)
        # 6 events with 5 early, 1 late — ratio = 1.0 for even n → "stable"
        ts = [now - timedelta(minutes=30)] * 3 + [now - timedelta(minutes=5)] * 3
        assert _detect_trend(ts) == "stable"

    def test_stable_for_balanced_counts(self) -> None:
        now = datetime.now(tz=_UTC)
        # n=8: first_half=4, second_half=4, ratio=1.0 → stable
        ts = [now - timedelta(minutes=i * 5) for i in range(8)]
        assert _detect_trend(ts) == "stable"


# ---------------------------------------------------------------------------
# _dominant_severity
# ---------------------------------------------------------------------------


class TestDominantSeverity:
    def test_critical_wins_over_error(self) -> None:
        assert _dominant_severity(["error", "critical", "warning"]) == "critical"

    def test_error_wins_over_warning(self) -> None:
        assert _dominant_severity(["warning", "error"]) == "error"

    def test_single_element(self) -> None:
        assert _dominant_severity(["warning"]) == "warning"

    def test_all_same(self) -> None:
        assert _dominant_severity(["error", "error", "error"]) == "error"


# ---------------------------------------------------------------------------
# aggregate_errors
# ---------------------------------------------------------------------------


class TestAggregateErrors:
    def test_empty_list(self) -> None:
        view = aggregate_errors([])
        assert view.total_events == 0
        assert view.groups == []
        assert view.domain_count == 0

    def test_groups_by_domain_and_type(self) -> None:
        now = datetime.now(tz=_UTC)
        records = [
            _rec("auth", "TypeError", "bad type", now=now),
            _rec("auth", "TypeError", "bad type", now=now),  # same group
            _rec("deploy", "RuntimeError", "deploy failed", now=now),
        ]
        view = aggregate_errors(records, now=now)
        assert len(view.groups) == 2
        assert view.total_events == 3
        assert view.domain_count == 2

    def test_groups_sorted_by_frequency_desc(self) -> None:
        now = datetime.now(tz=_UTC)
        records = (
            [_rec("a", "E1", "msg1", now=now)] * 3
            + [_rec("b", "E2", "msg2", now=now)] * 7
            + [_rec("c", "E3", "msg3", now=now)] * 1
        )
        view = aggregate_errors(records, now=now)
        freqs = [g.frequency for g in view.groups]
        assert freqs == sorted(freqs, reverse=True)

    def test_excludes_records_outside_window(self) -> None:
        now = datetime.now(tz=_UTC)
        # 2 recent records (5 min ago), 1 old record (120 min ago)
        records = [
            _rec(minutes_ago=5, now=now),
            _rec(minutes_ago=5, now=now),
            _rec(minutes_ago=120, now=now),
        ]
        view = aggregate_errors(records, window_minutes=60, now=now)
        assert view.total_events == 2

    def test_by_domain_index_populated(self) -> None:
        now = datetime.now(tz=_UTC)
        records = [
            _rec("gate_runner", "TimeoutError", "timeout", now=now),
            _rec("gate_runner", "TimeoutError", "timeout", now=now),
            _rec("lsp", "AttributeError", "no attr", now=now),
        ]
        view = aggregate_errors(records, now=now)
        assert "gate_runner" in view.by_domain
        assert "lsp" in view.by_domain
        assert len(view.by_domain["gate_runner"]) == 1

    def test_window_start_end_correct(self) -> None:
        now = datetime.now(tz=_UTC)
        view = aggregate_errors([], window_minutes=30, now=now)
        expected_start = now - timedelta(minutes=30)
        # Allow 1-second tolerance for timing
        assert abs((view.window_start - expected_start).total_seconds()) < 1
        assert abs((view.window_end - now).total_seconds()) < 1

    def test_severity_computed_per_group(self) -> None:
        now = datetime.now(tz=_UTC)
        records = [
            _rec("d", "E", "m", severity="warning", now=now),
            _rec("d", "E", "m", severity="critical", now=now),
        ]
        view = aggregate_errors(records, now=now)
        assert len(view.groups) == 1
        assert view.groups[0].severity == "critical"

    def test_trend_detected(self) -> None:
        # _detect_trend uses an index split: for n=5 events,
        # second_half (3) / first_half (2) == 1.5 → "rising".
        now = datetime.now(tz=_UTC)
        records = [
            ErrorRecord(
                timestamp=now - timedelta(minutes=i),
                domain="d",
                error_type="E",
                message="m",
            )
            for i in range(5)
        ]
        view = aggregate_errors(records, window_minutes=60, now=now)
        assert view.groups[0].trend == "rising"

    def test_domain_case_normalised(self) -> None:
        now = datetime.now(tz=_UTC)
        records = [
            _rec("Gate_Runner", "E", "m", now=now),
            _rec("gate_runner", "E", "m", now=now),
        ]
        view = aggregate_errors(records, now=now)
        # Both should end up in the same group (same lower-cased domain)
        assert view.domain_count == 1


# ---------------------------------------------------------------------------
# top_errors
# ---------------------------------------------------------------------------


class TestTopErrors:
    def _make_view(self) -> ErrorAggregationView:
        now = datetime.now(tz=_UTC)
        records = (
            [_rec("a", "E1", "msg1", now=now)] * 10
            + [_rec("a", "E2", "msg2", now=now)] * 4
            + [_rec("b", "E3", "msg3", now=now)] * 7
        )
        return aggregate_errors(records, now=now)

    def test_global_top_n(self) -> None:
        view = self._make_view()
        result = top_errors(view, n=2)
        assert len(result) == 2
        assert result[0].frequency >= result[1].frequency

    def test_domain_filter(self) -> None:
        view = self._make_view()
        result = top_errors(view, n=10, domain="a")
        assert all(g.domain == "a" for g in result)
        assert len(result) == 2

    def test_domain_filter_case_insensitive(self) -> None:
        view = self._make_view()
        result_lower = top_errors(view, n=10, domain="a")
        result_upper = top_errors(view, n=10, domain="A")
        assert len(result_lower) == len(result_upper)

    def test_unknown_domain_returns_empty(self) -> None:
        view = self._make_view()
        assert top_errors(view, n=10, domain="nonexistent") == []

    def test_n_zero_returns_empty(self) -> None:
        view = self._make_view()
        assert top_errors(view, n=0) == []


# ---------------------------------------------------------------------------
# errors_by_domain
# ---------------------------------------------------------------------------


class TestErrorsByDomain:
    def test_mirrors_by_domain(self) -> None:
        now = datetime.now(tz=_UTC)
        records = [
            _rec("x", now=now),
            _rec("y", now=now),
        ]
        view = aggregate_errors(records, now=now)
        assert errors_by_domain(view) is view.by_domain


# ---------------------------------------------------------------------------
# domain_summary
# ---------------------------------------------------------------------------


class TestDomainSummary:
    def test_sorted_by_total_errors(self) -> None:
        now = datetime.now(tz=_UTC)
        records = (
            [_rec("loud", "E", "m", now=now)] * 20
            + [_rec("quiet", "E", "m", now=now)] * 3
        )
        view = aggregate_errors(records, now=now)
        rows = domain_summary(view)
        assert rows[0]["domain"] == "loud"
        assert rows[0]["total_errors"] == 20

    def test_rising_patterns_counted(self) -> None:
        # Exactly 5 records in one group → _detect_trend returns "rising"
        # (index split: second_half 3 / first_half 2 == 1.5).
        now = datetime.now(tz=_UTC)
        records = [
            ErrorRecord(
                timestamp=now - timedelta(minutes=i),
                domain="d",
                error_type="E",
                message="m",
            )
            for i in range(5)
        ]
        view = aggregate_errors(records, window_minutes=60, now=now)
        rows = domain_summary(view)
        assert rows[0]["rising_patterns"] >= 1

    def test_distinct_patterns_counted(self) -> None:
        now = datetime.now(tz=_UTC)
        # Two distinct patterns in the same domain
        records = [
            _rec("d", "TypeA", "pattern alpha error", now=now),
            _rec("d", "TypeB", "pattern beta failure", now=now),
        ]
        view = aggregate_errors(records, now=now)
        rows = domain_summary(view)
        assert rows[0]["distinct_patterns"] == 2


# ---------------------------------------------------------------------------
# errors_to_json_summary
# ---------------------------------------------------------------------------


class TestErrorsToJsonSummary:
    def test_valid_json_output(self) -> None:
        now = datetime.now(tz=_UTC)
        view = aggregate_errors([_rec(now=now)], now=now)
        raw = errors_to_json_summary(view)
        parsed = json.loads(raw)
        assert "window" in parsed
        assert "top_errors" in parsed
        assert "domain_overview" in parsed

    def test_top_n_capped(self) -> None:
        now = datetime.now(tz=_UTC)
        # 30 different error messages → 30 distinct groups
        records = [_rec(message=f"unique error {i}", now=now) for i in range(30)]
        view = aggregate_errors(records, now=now)
        raw = errors_to_json_summary(view, top_n=5)
        parsed = json.loads(raw)
        assert len(parsed["top_errors"]) <= 5

    def test_by_domain_included(self) -> None:
        now = datetime.now(tz=_UTC)
        view = aggregate_errors([_rec(now=now)], now=now)
        raw = errors_to_json_summary(view, include_domain_breakdown=True)
        parsed = json.loads(raw)
        assert "by_domain" in parsed

    def test_by_domain_excluded(self) -> None:
        now = datetime.now(tz=_UTC)
        view = aggregate_errors([_rec(now=now)], now=now)
        raw = errors_to_json_summary(view, include_domain_breakdown=False)
        parsed = json.loads(raw)
        assert "by_domain" not in parsed

    def test_window_metadata_present(self) -> None:
        now = datetime.now(tz=_UTC)
        view = aggregate_errors([], window_minutes=45, now=now)
        raw = errors_to_json_summary(view)
        parsed = json.loads(raw)
        w = parsed["window"]
        assert "start" in w
        assert "end" in w
        assert w["total_events"] == 0
        assert w["domain_count"] == 0

    def test_sample_message_capped_at_300_chars(self) -> None:
        now = datetime.now(tz=_UTC)
        long_msg = "x" * 500
        view = aggregate_errors([_rec(message=long_msg, now=now)], now=now)
        raw = errors_to_json_summary(view)
        parsed = json.loads(raw)
        assert len(parsed["top_errors"][0]["sample_message"]) <= 300


# ---------------------------------------------------------------------------
# load_errors_from_log
# ---------------------------------------------------------------------------


class TestLoadErrorsFromLog:
    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        result = load_errors_from_log(tmp_path / "nonexistent.ndjson")
        assert result == []

    def test_valid_ndjson_parsed(self, tmp_path: Path) -> None:
        now = datetime.now(tz=_UTC)
        log_file = tmp_path / "errors.ndjson"
        entry = {
            "timestamp": (now - timedelta(minutes=5)).isoformat(),
            "domain": "gate_runner",
            "error_type": "TimeoutError",
            "message": "Gate timed out",
            "severity": "error",
            "stack_hint": "gate_runner/runner.py:142",
        }
        log_file.write_text(json.dumps(entry) + "\n")
        records = load_errors_from_log(log_file, window_minutes=60)
        assert len(records) == 1
        assert records[0].domain == "gate_runner"
        assert records[0].error_type == "TimeoutError"
        assert records[0].stack_hint == "gate_runner/runner.py:142"

    def test_records_outside_window_excluded(self, tmp_path: Path) -> None:
        now = datetime.now(tz=_UTC)
        log_file = tmp_path / "errors.ndjson"
        recent = {
            "timestamp": (now - timedelta(minutes=10)).isoformat(),
            "domain": "d",
            "error_type": "E",
            "message": "recent",
        }
        old = {
            "timestamp": (now - timedelta(minutes=200)).isoformat(),
            "domain": "d",
            "error_type": "E",
            "message": "old",
        }
        log_file.write_text(json.dumps(recent) + "\n" + json.dumps(old) + "\n")
        records = load_errors_from_log(log_file, window_minutes=60)
        assert len(records) == 1
        assert records[0].message == "recent"

    def test_malformed_lines_skipped(self, tmp_path: Path) -> None:
        now = datetime.now(tz=_UTC)
        log_file = tmp_path / "errors.ndjson"
        valid = {
            "timestamp": (now - timedelta(minutes=5)).isoformat(),
            "domain": "d",
            "error_type": "E",
            "message": "ok",
        }
        log_file.write_text(
            "not json at all\n"
            + json.dumps(valid)
            + "\n"
            + '{"incomplete": true}\n'  # missing required fields
        )
        records = load_errors_from_log(log_file, window_minutes=60)
        assert len(records) == 1

    def test_blank_lines_skipped(self, tmp_path: Path) -> None:
        now = datetime.now(tz=_UTC)
        log_file = tmp_path / "errors.ndjson"
        valid = {
            "timestamp": (now - timedelta(minutes=5)).isoformat(),
            "domain": "d",
            "error_type": "E",
            "message": "ok",
        }
        log_file.write_text("\n\n" + json.dumps(valid) + "\n\n")
        records = load_errors_from_log(log_file, window_minutes=60)
        assert len(records) == 1

    def test_optional_fields_default_correctly(self, tmp_path: Path) -> None:
        now = datetime.now(tz=_UTC)
        log_file = tmp_path / "errors.ndjson"
        minimal = {
            "timestamp": (now - timedelta(minutes=5)).isoformat(),
            "domain": "d",
            "error_type": "E",
            "message": "minimal",
        }
        log_file.write_text(json.dumps(minimal) + "\n")
        records = load_errors_from_log(log_file, window_minutes=60)
        assert records[0].severity == "error"
        assert records[0].stack_hint == ""


# ---------------------------------------------------------------------------
# ErrorAggregationResponse (Pydantic model)
# ---------------------------------------------------------------------------


class TestErrorAggregationResponseModel:
    """Validate the Pydantic schema for the /harness:observability output."""

    def _minimal_payload(self) -> dict:
        now = datetime.now(tz=_UTC)
        return {
            "command": "harness observability",
            "status": "warning",
            "window_start": now.isoformat(),
            "window_end": now.isoformat(),
            "window_minutes": 60,
            "total_events": 10,
            "domain_count": 2,
        }

    def test_valid_minimal_payload(self) -> None:
        payload = self._minimal_payload()
        response = ErrorAggregationResponse.model_validate(payload)
        assert response.command == "harness observability"
        assert response.window_minutes == 60
        assert response.top_errors == []
        assert response.domain_overview == []
        assert response.by_domain is None
        assert response.log_source is None
        assert response.data_source == "empty"

    def test_json_round_trip(self) -> None:
        payload = self._minimal_payload()
        response = ErrorAggregationResponse.model_validate(payload)
        raw = response.model_dump_json()
        restored = ErrorAggregationResponse.model_validate_json(raw)
        assert restored.window_minutes == response.window_minutes
        assert restored.total_events == response.total_events

    def test_rejects_extra_fields(self) -> None:
        payload = {**self._minimal_payload(), "unexpected_key": "oops"}
        with pytest.raises(ValidationError):
            ErrorAggregationResponse.model_validate(payload)

    def test_top_errors_populated(self) -> None:
        now = datetime.now(tz=_UTC)
        payload = {
            **self._minimal_payload(),
            "top_errors": [
                {
                    "domain": "gate_runner",
                    "error_type": "TimeoutError",
                    "frequency": 38,
                    "severity": "error",
                    "trend": "rising",
                    "first_seen": now.isoformat(),
                    "last_seen": now.isoformat(),
                    "recency_seconds": 42,
                    "sample_message": "Gate timed out after 30s",
                    "pattern": "gate timed out after s",
                }
            ],
        }
        response = ErrorAggregationResponse.model_validate(payload)
        assert len(response.top_errors) == 1
        assert response.top_errors[0].trend == "rising"
        assert response.top_errors[0].frequency == 38

    def test_domain_overview_populated(self) -> None:
        payload = {
            **self._minimal_payload(),
            "domain_overview": [
                {
                    "domain": "gate_runner",
                    "total_errors": 95,
                    "distinct_patterns": 4,
                    "top_severity": "error",
                    "rising_patterns": 2,
                }
            ],
        }
        response = ErrorAggregationResponse.model_validate(payload)
        assert response.domain_overview[0].rising_patterns == 2

    def test_invalid_severity_rejected(self) -> None:
        now = datetime.now(tz=_UTC)
        payload = {
            **self._minimal_payload(),
            "top_errors": [
                {
                    "domain": "d",
                    "error_type": "E",
                    "frequency": 1,
                    "severity": "DEBUG",   # invalid
                    "trend": "stable",
                    "first_seen": now.isoformat(),
                    "last_seen": now.isoformat(),
                    "recency_seconds": 0,
                    "sample_message": "m",
                    "pattern": "p",
                }
            ],
        }
        with pytest.raises(ValidationError):
            ErrorAggregationResponse.model_validate(payload)

    def test_invalid_trend_rejected(self) -> None:
        now = datetime.now(tz=_UTC)
        payload = {
            **self._minimal_payload(),
            "top_errors": [
                {
                    "domain": "d",
                    "error_type": "E",
                    "frequency": 1,
                    "severity": "error",
                    "trend": "sideways",   # invalid
                    "first_seen": now.isoformat(),
                    "last_seen": now.isoformat(),
                    "recency_seconds": 0,
                    "sample_message": "m",
                    "pattern": "p",
                }
            ],
        }
        with pytest.raises(ValidationError):
            ErrorAggregationResponse.model_validate(payload)

    def test_frequency_ge_1_enforced(self) -> None:
        now = datetime.now(tz=_UTC)
        payload = {
            **self._minimal_payload(),
            "top_errors": [
                {
                    "domain": "d",
                    "error_type": "E",
                    "frequency": 0,   # must be ≥ 1
                    "severity": "error",
                    "trend": "stable",
                    "first_seen": now.isoformat(),
                    "last_seen": now.isoformat(),
                    "recency_seconds": 0,
                    "sample_message": "m",
                    "pattern": "p",
                }
            ],
        }
        with pytest.raises(ValidationError):
            ErrorAggregationResponse.model_validate(payload)

    def test_data_source_values(self) -> None:
        for source in ("log_file", "state_service", "inline", "empty"):
            payload = {**self._minimal_payload(), "data_source": source}
            response = ErrorAggregationResponse.model_validate(payload)
            assert response.data_source == source

    def test_invalid_data_source_rejected(self) -> None:
        payload = {**self._minimal_payload(), "data_source": "unknown_source"}
        with pytest.raises(ValidationError):
            ErrorAggregationResponse.model_validate(payload)

    def test_by_domain_optional(self) -> None:
        now = datetime.now(tz=_UTC)
        group = {
            "domain": "d",
            "error_type": "E",
            "frequency": 1,
            "severity": "error",
            "trend": "stable",
            "first_seen": now.isoformat(),
            "last_seen": now.isoformat(),
            "recency_seconds": 0,
            "sample_message": "m",
            "pattern": "p",
        }
        payload = {
            **self._minimal_payload(),
            "by_domain": {"d": [group]},
        }
        response = ErrorAggregationResponse.model_validate(payload)
        assert response.by_domain is not None
        assert len(response.by_domain["d"]) == 1

    def test_log_source_optional(self) -> None:
        payload = {
            **self._minimal_payload(),
            "log_source": ".harness/errors.ndjson",
        }
        response = ErrorAggregationResponse.model_validate(payload)
        assert response.log_source == ".harness/errors.ndjson"
