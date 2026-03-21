"""
Error Aggregation View
======================
Pure-Python aggregation layer that groups recent error events by *domain* and
*frequency* so agents can query the error landscape without parsing raw logs.

All heavy lifting (deduplication, trend detection, JSON serialisation) happens
here so the Claude analyser receives pre-computed, JSON-serialisable summaries
rather than raw log lines.

Key exports
-----------
  ErrorRecord             — dataclass for a single observed error event
  ErrorGroup              — dataclass for a deduplicated, aggregated group
  ErrorAggregationView    — container returned by ``aggregate_errors``
  aggregate_errors        — group a list of ErrorRecords by domain + pattern
  top_errors              — return the N most frequent groups (globally or per domain)
  errors_by_domain        — organise groups into a {domain -> [ErrorGroup]} dict
  errors_to_json_summary  — serialise the view to compact JSON for agent context
  load_errors_from_log    — optional helper: parse newline-delimited JSON log files
"""

from __future__ import annotations

import dataclasses
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Core data structures
# ---------------------------------------------------------------------------


@dataclass
class ErrorRecord:
    """A single observed error event emitted by a harness component."""

    # When the error occurred (UTC).  Accepts a datetime or an ISO-8601 string.
    timestamp: datetime

    # Logical domain that produced the error, e.g. "gate_runner", "lsp", "deploy".
    domain: str

    # Short classification: "TypeError", "TimeoutError", "AssertionError", etc.
    error_type: str

    # Full (or truncated) error message.
    message: str

    # Optional: first line of the stack trace, used as a deduplication key.
    stack_hint: str = ""

    # Pre-assigned severity label if available from the log source.
    severity: str = "error"   # "error" | "warning" | "critical"

    def __post_init__(self) -> None:
        if isinstance(self.timestamp, str):
            self.timestamp = datetime.fromisoformat(self.timestamp)
        # Normalise to UTC-aware datetime.
        if self.timestamp.tzinfo is None:
            self.timestamp = self.timestamp.replace(tzinfo=timezone.utc)


@dataclass
class ErrorGroup:
    """
    Aggregated view of ErrorRecords that share the same domain, error_type,
    and (optionally) a normalised message pattern.
    """

    domain: str
    error_type: str

    # Normalised fingerprint used for grouping (whitespace/numbers stripped).
    pattern: str

    # Total occurrences in the analysis window.
    frequency: int

    # Earliest and latest timestamps seen in this group.
    first_seen: datetime
    last_seen: datetime

    # Representative sample message (from the most recent record).
    sample_message: str

    # Dominant severity across all records in the group.
    severity: str

    # Trend indicator: "rising" | "falling" | "stable"
    trend: str = "stable"

    @property
    def age_seconds(self) -> float:
        """Seconds since the first occurrence of this group."""
        now = datetime.now(tz=timezone.utc)
        return (now - self.first_seen).total_seconds()

    @property
    def recency_seconds(self) -> float:
        """Seconds since the most recent occurrence."""
        now = datetime.now(tz=timezone.utc)
        return (now - self.last_seen).total_seconds()


@dataclass
class ErrorAggregationView:
    """
    Top-level container produced by ``aggregate_errors``.  Carries both the
    raw groups and quick-access indexes for agent queries.
    """

    # All deduplicated groups, sorted by frequency (descending).
    groups: list[ErrorGroup]

    # {domain -> [ErrorGroup]} index for domain-scoped queries.
    by_domain: dict[str, list[ErrorGroup]]

    # The time window that was analysed (UTC).
    window_start: datetime
    window_end: datetime

    # Total raw events that fed into this view.
    total_events: int

    # Number of distinct domains observed.
    domain_count: int


# ---------------------------------------------------------------------------
# Fingerprinting helpers
# ---------------------------------------------------------------------------

# Patterns to strip when normalising messages for grouping.
_STRIP_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b0x[0-9a-fA-F]+\b"),          # hex addresses
    re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[^\s]*"),  # timestamps
    re.compile(r"\b\d+\b"),                      # bare integers
    re.compile(r"'[^']{1,80}'"),                 # short quoted strings
    re.compile(r'"[^"]{1,80}"'),                 # short double-quoted strings
    re.compile(r"/[\w/._-]{3,}"),                # file paths
    re.compile(r"\s+"),                          # collapse whitespace
]


def _fingerprint(message: str, stack_hint: str = "") -> str:
    """
    Return a normalised fingerprint for deduplication.
    Uses *stack_hint* when available (more stable than message text).
    """
    if stack_hint:
        source = stack_hint
    else:
        source = message
    fp = source.lower()
    for pattern in _STRIP_PATTERNS:
        fp = pattern.sub(" ", fp)
    return fp.strip()[:200]


# ---------------------------------------------------------------------------
# Trend detection
# ---------------------------------------------------------------------------


def _detect_trend(timestamps: list[datetime]) -> str:
    """
    Split the event timestamps into two equal halves and compare counts.
    Returns "rising", "falling", or "stable".
    """
    if len(timestamps) < 4:
        return "stable"

    sorted_ts = sorted(timestamps)
    mid = len(sorted_ts) // 2
    first_half = len(sorted_ts[:mid])
    second_half = len(sorted_ts[mid:])

    ratio = second_half / first_half if first_half else float("inf")
    if ratio >= 1.5:
        return "rising"
    if ratio <= 0.67:
        return "falling"
    return "stable"


def _dominant_severity(severities: list[str]) -> str:
    order = {"critical": 0, "error": 1, "warning": 2}
    return min(severities, key=lambda s: order.get(s, 99))


# ---------------------------------------------------------------------------
# Core aggregation
# ---------------------------------------------------------------------------


def aggregate_errors(
    records: list[ErrorRecord],
    window_minutes: int = 60,
    now: Optional[datetime] = None,
) -> ErrorAggregationView:
    """
    Aggregate *records* into deduplicated :class:`ErrorGroup` objects.

    Parameters
    ----------
    records:
        Raw error events to process.
    window_minutes:
        Only events within this many minutes of *now* are included.
    now:
        Reference time for the window (default: current UTC time).

    Returns
    -------
    ErrorAggregationView
        Fully populated view, ready for serialisation or agent queries.
    """
    if now is None:
        now = datetime.now(tz=timezone.utc)

    window_start = now - timedelta(minutes=window_minutes)

    # Filter to the requested time window.
    in_window = [r for r in records if r.timestamp >= window_start]

    # Group by (domain, error_type, fingerprint).
    buckets: dict[tuple[str, str, str], list[ErrorRecord]] = defaultdict(list)
    for rec in in_window:
        fp = _fingerprint(rec.message, rec.stack_hint)
        key = (rec.domain.lower(), rec.error_type, fp)
        buckets[key].append(rec)

    groups: list[ErrorGroup] = []
    for (domain, error_type, pattern), recs in buckets.items():
        timestamps = [r.timestamp for r in recs]
        most_recent = max(recs, key=lambda r: r.timestamp)

        groups.append(
            ErrorGroup(
                domain=domain,
                error_type=error_type,
                pattern=pattern,
                frequency=len(recs),
                first_seen=min(timestamps),
                last_seen=max(timestamps),
                sample_message=most_recent.message,
                severity=_dominant_severity([r.severity for r in recs]),
                trend=_detect_trend(timestamps),
            )
        )

    # Sort by frequency descending, then by most-recent occurrence.
    groups.sort(key=lambda g: (-g.frequency, -g.last_seen.timestamp()))

    by_domain: dict[str, list[ErrorGroup]] = defaultdict(list)
    for g in groups:
        by_domain[g.domain].append(g)

    return ErrorAggregationView(
        groups=groups,
        by_domain=dict(by_domain),
        window_start=window_start,
        window_end=now,
        total_events=len(in_window),
        domain_count=len(by_domain),
    )


# ---------------------------------------------------------------------------
# Convenience query helpers
# ---------------------------------------------------------------------------


def top_errors(
    view: ErrorAggregationView,
    n: int = 10,
    domain: Optional[str] = None,
) -> list[ErrorGroup]:
    """
    Return the *n* most frequent :class:`ErrorGroup` objects.

    Parameters
    ----------
    view:   The aggregation view to query.
    n:      Maximum number of groups to return.
    domain: If provided, restrict results to this domain only.
    """
    if domain is not None:
        source = view.by_domain.get(domain.lower(), [])
    else:
        source = view.groups
    return source[:n]


def errors_by_domain(view: ErrorAggregationView) -> dict[str, list[ErrorGroup]]:
    """Return the ``by_domain`` index from *view* (convenience alias)."""
    return view.by_domain


def domain_summary(view: ErrorAggregationView) -> list[dict]:
    """
    Return a list of {domain, total_errors, distinct_patterns, top_severity}
    records sorted by total error count, for a bird's-eye overview.
    """
    rows: list[dict] = []
    for domain, groups in view.by_domain.items():
        total = sum(g.frequency for g in groups)
        sev = _dominant_severity([g.severity for g in groups])
        rows.append(
            {
                "domain": domain,
                "total_errors": total,
                "distinct_patterns": len(groups),
                "top_severity": sev,
                "rising_patterns": sum(1 for g in groups if g.trend == "rising"),
            }
        )
    rows.sort(key=lambda r: -r["total_errors"])
    return rows


# ---------------------------------------------------------------------------
# JSON serialisation for agent context
# ---------------------------------------------------------------------------


def _group_to_dict(g: ErrorGroup) -> dict:
    return {
        "domain":         g.domain,
        "error_type":     g.error_type,
        "frequency":      g.frequency,
        "severity":       g.severity,
        "trend":          g.trend,
        "first_seen":     g.first_seen.isoformat(),
        "last_seen":      g.last_seen.isoformat(),
        "recency_seconds": round(g.recency_seconds),
        "sample_message": g.sample_message[:300],  # cap for context budget
        "pattern":        g.pattern[:120],
    }


def errors_to_json_summary(
    view: ErrorAggregationView,
    top_n: int = 20,
    include_domain_breakdown: bool = True,
) -> str:
    """
    Produce a compact JSON summary of the error aggregation view.

    Used as pre-computed context for the Claude agent calls so the model
    receives structured data rather than raw log lines.

    Parameters
    ----------
    view:                     The aggregation view to serialise.
    top_n:                    How many top error groups to include globally.
    include_domain_breakdown: Whether to include per-domain detail.
    """
    summary: dict = {
        "window": {
            "start":        view.window_start.isoformat(),
            "end":          view.window_end.isoformat(),
            "total_events": view.total_events,
            "domain_count": view.domain_count,
        },
        "top_errors": [_group_to_dict(g) for g in view.groups[:top_n]],
        "domain_overview": domain_summary(view),
    }

    if include_domain_breakdown:
        summary["by_domain"] = {
            domain: [_group_to_dict(g) for g in groups[:10]]
            for domain, groups in view.by_domain.items()
        }

    return json.dumps(summary, indent=2)


# ---------------------------------------------------------------------------
# Optional: load errors from a newline-delimited JSON log file
# ---------------------------------------------------------------------------


def load_errors_from_log(
    log_path: str | Path,
    window_minutes: int = 60,
) -> list[ErrorRecord]:
    """
    Parse a newline-delimited JSON (NDJSON) log file into :class:`ErrorRecord`
    objects.

    Each line must be a JSON object with at minimum:
      ``{"timestamp": "<iso8601>", "domain": "...", "error_type": "...", "message": "..."}``

    Optional fields: ``stack_hint``, ``severity``.
    Lines that cannot be parsed are silently skipped.
    """
    path = Path(log_path)
    if not path.exists():
        return []

    now = datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(minutes=window_minutes)
    records: list[ErrorRecord] = []

    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                ts = datetime.fromisoformat(obj["timestamp"])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts < cutoff:
                    continue
                records.append(
                    ErrorRecord(
                        timestamp=ts,
                        domain=str(obj["domain"]),
                        error_type=str(obj.get("error_type", "UnknownError")),
                        message=str(obj.get("message", "")),
                        stack_hint=str(obj.get("stack_hint", "")),
                        severity=str(obj.get("severity", "error")),
                    )
                )
            except (KeyError, ValueError, json.JSONDecodeError):
                continue

    return records
