"""Pydantic response models for the harness error aggregation view.

These models are the canonical schema for data produced by
``harness_skills.error_aggregation`` and consumed by the
``/harness:observability`` skill and downstream agents.

All models inherit from Pydantic ``BaseModel`` with strict ``extra="forbid"``
validation so unexpected fields surface immediately rather than being silently
dropped.

The top-level ``ErrorAggregationResponse`` inherits from ``HarnessResponse``
to share the standard ``command / status / timestamp / duration_ms`` envelope
that every harness skill emits.

Import in Python
----------------
    from harness_skills.models.errors import (
        ErrorGroupResponse,
        DomainOverview,
        ErrorAggregationResponse,
    )

    response = ErrorAggregationResponse.model_validate_json(raw_json)
    for group in response.top_errors:
        print(group.domain, group.frequency, group.trend)
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from harness_skills.models.base import HarnessResponse


# ── Per-group ──────────────────────────────────────────────────────────────────


class ErrorGroupResponse(BaseModel):
    """Serialised representation of one deduplicated error group.

    Corresponds to ``harness_skills.error_aggregation.ErrorGroup`` after
    JSON serialisation.  Numbers and timestamps are preserved; long strings
    are capped at the limits documented in the field descriptions.
    """

    model_config = ConfigDict(extra="forbid")

    domain: str = Field(
        description=(
            "Logical domain that produced the error, e.g. 'gate_runner', 'lsp', 'deploy'. "
            "Always lower-cased by the aggregation layer."
        )
    )
    error_type: str = Field(
        description="Short error classification, e.g. 'TypeError', 'TimeoutError'."
    )
    frequency: int = Field(ge=1, description="Occurrence count within the analysis window.")
    severity: Literal["critical", "error", "warning"] = Field(
        description="Dominant severity across all raw records in the group."
    )
    trend: Literal["rising", "falling", "stable"] = Field(
        description=(
            "Frequency trend computed by comparing occurrence counts in the first "
            "vs. second half of the window: 'rising' (≥ 1.5×), 'falling' (≤ 0.67×), "
            "or 'stable'."
        )
    )
    first_seen: datetime = Field(description="UTC timestamp of the earliest occurrence.")
    last_seen: datetime = Field(description="UTC timestamp of the most recent occurrence.")
    recency_seconds: int = Field(
        ge=0, description="Seconds elapsed since the last occurrence (rounded)."
    )
    sample_message: str = Field(
        description=(
            "Representative error message from the most recent record.  "
            "Capped at 300 characters."
        )
    )
    pattern: str = Field(
        description=(
            "Normalised fingerprint used for deduplication — stripped of hex addresses, "
            "timestamps, integers, and quoted strings.  Capped at 120 characters."
        )
    )


# ── Per-domain overview ────────────────────────────────────────────────────────


class DomainOverview(BaseModel):
    """Bird's-eye summary for one error-producing domain.

    Provides a quick way to rank domains by error volume without iterating
    individual groups.
    """

    model_config = ConfigDict(extra="forbid")

    domain: str = Field(description="Domain identifier (lower-cased).")
    total_errors: int = Field(
        ge=0, description="Sum of all group frequencies in this domain."
    )
    distinct_patterns: int = Field(
        ge=0, description="Number of deduplicated error patterns observed."
    )
    top_severity: Literal["critical", "error", "warning"] = Field(
        description="Dominant severity across all groups in this domain."
    )
    rising_patterns: int = Field(
        ge=0,
        description="Number of groups whose trend is 'rising' — needs immediate attention.",
    )


# ── Top-level response ─────────────────────────────────────────────────────────


class ErrorAggregationResponse(HarnessResponse):
    """Response schema emitted by ``/harness:observability``.

    Carries a deduplicated, frequency-sorted view of recent error events
    grouped by domain.  Agents can consume ``top_errors`` for a global
    ranking or ``by_domain`` for domain-scoped drill-down queries.

    The schema intentionally mirrors the structure of
    ``harness_skills.error_aggregation.errors_to_json_summary`` so that
    the skill output can be validated in tests without re-running the CLI.

    Extra fields are forbidden so unexpected keys surface immediately as a
    ``ValidationError`` rather than being silently dropped.

    Typical agent workflow
    ----------------------
    1. Check ``domain_overview`` to identify the noisiest domains.
    2. Iterate ``top_errors`` (or ``by_domain[domain]``) for detailed groups.
    3. Prioritise groups where ``severity == "critical"`` or ``trend == "rising"``.
    4. Use ``recency_seconds`` to distinguish stale from active error bursts.
    """

    model_config = ConfigDict(extra="forbid")

    command: str = "harness observability"

    # ── Window metadata ──────────────────────────────────────────────────────

    window_start: datetime = Field(description="UTC start of the analysis window.")
    window_end: datetime = Field(description="UTC end of the analysis window (≈ now).")
    window_minutes: int = Field(ge=1, description="Duration of the analysis window in minutes.")
    total_events: int = Field(ge=0, description="Total raw error events included in the window.")
    domain_count: int = Field(
        ge=0, description="Number of distinct error-producing domains observed."
    )

    # ── Error data ───────────────────────────────────────────────────────────

    top_errors: list[ErrorGroupResponse] = Field(
        default_factory=list,
        description=(
            "Top error groups globally, sorted by frequency descending.  "
            "Capped at ``top_n`` (default 20)."
        ),
    )
    domain_overview: list[DomainOverview] = Field(
        default_factory=list,
        description="Per-domain summary sorted by total_errors descending.",
    )
    by_domain: Optional[dict[str, list[ErrorGroupResponse]]] = Field(
        default=None,
        description=(
            "Per-domain error groups (up to 10 per domain).  "
            "Included only when ``--by-domain`` is passed."
        ),
    )

    # ── Provenance ───────────────────────────────────────────────────────────

    log_source: Optional[str] = Field(
        default=None,
        description="Absolute or relative path to the NDJSON log file used as input.",
    )
    data_source: Literal["log_file", "state_service", "inline", "empty"] = Field(
        default="empty",
        description=(
            "How the error records were sourced: "
            "'log_file' (--log-file PATH), "
            "'state_service' (fetched from the claw-forge state service), "
            "'inline' (passed programmatically), "
            "'empty' (no source — zero events)."
        ),
    )
