"""Typed response models for ``harness observe`` (/harness:observe).

The ``harness observe`` command tails NDJSON structured log files produced by
``harness_skills.logging_config.ConventionFormatter``.  When ``--format json``
is used, every emitted entry is validated against :class:`LogEntry` before it
reaches stdout — ensuring the output always conforms to the five-field logging
convention.

Five-field logging convention (required fields)
------------------------------------------------
+------------+-----------------------------------+----------------------------+
| Field      | Format                            | Source                     |
+============+===================================+============================+
| timestamp  | ISO-8601 UTC, millisecond prec.   | auto — formatter           |
| level      | DEBUG/INFO/WARN/ERROR/FATAL       | auto — logging level       |
| domain     | dot-separated string              | caller — ``get_logger()``  |
| trace_id   | 32-char lowercase hex (W3C)       | context var / auto-gen     |
| message    | non-empty UTF-8 string            | caller — log call          |
+------------+-----------------------------------+----------------------------+

Optional:
  extra — arbitrary caller-supplied key/value pairs (must not shadow the five
          required fields).
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Internal constants (mirrored from logging_config to avoid coupling)
# ---------------------------------------------------------------------------

_TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_VALID_LEVELS = frozenset({"DEBUG", "INFO", "WARN", "WARNING", "ERROR", "FATAL", "CRITICAL"})


# ---------------------------------------------------------------------------
# LogEntry — individual log line schema
# ---------------------------------------------------------------------------


class LogEntry(BaseModel):
    """Schema for a single NDJSON log entry produced by the five-field convention.

    Used by ``harness observe --format json`` to validate each entry before
    emitting it to stdout.  Entries that fail validation are emitted as-is
    (no data loss) and the failure is counted in :class:`ObserveResponse`.

    Convention source: ``harness_skills.logging_config.ConventionFormatter``

    Example
    -------
    ::

        entry = LogEntry.model_validate({
            "timestamp": "2026-03-20T14:22:05.123Z",
            "level": "INFO",
            "domain": "harness.auth",
            "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
            "message": "user signed in",
            "extra": {"user_id": "u-42"},
        })
        click.echo(entry.model_dump_json())
    """

    # Allow unknown top-level keys so future log convention extensions don't
    # cause validation failures in this version.
    model_config = ConfigDict(extra="allow")

    timestamp: str = Field(
        description=(
            "ISO-8601 UTC timestamp with millisecond precision, e.g. "
            "'2026-03-20T14:22:05.123Z'."
        )
    )
    level: str = Field(
        description=(
            "Log severity level.  One of: DEBUG, INFO, WARN, ERROR, FATAL.  "
            "Aliases WARNING and CRITICAL are also accepted."
        )
    )
    domain: str = Field(
        description=(
            "Dot-separated service domain string "
            "(e.g. 'harness.auth', 'harness.task_lock')."
        )
    )
    trace_id: str = Field(
        description="W3C-compatible 32-character lowercase hex trace ID."
    )
    message: str = Field(
        min_length=1,
        description="Non-empty UTF-8 log message.",
    )
    extra: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Optional caller-supplied key/value pairs.  "
            "Must not shadow the five required field names."
        ),
    )

    @field_validator("trace_id")
    @classmethod
    def _validate_trace_id(cls, v: str) -> str:
        if not _TRACE_ID_RE.match(v):
            raise ValueError(
                f"trace_id must be exactly 32 lowercase hex characters; got {v!r}"
            )
        return v

    @field_validator("domain")
    @classmethod
    def _validate_domain(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("domain must be a non-empty string")
        if ".." in v:
            raise ValueError(f"domain must not contain consecutive dots; got {v!r}")
        return v

    @field_validator("level")
    @classmethod
    def _validate_level(cls, v: str) -> str:
        normalised = v.upper()
        if normalised not in _VALID_LEVELS:
            raise ValueError(
                f"level must be one of {sorted(_VALID_LEVELS)}; got {v!r}"
            )
        return v


# ---------------------------------------------------------------------------
# ObserveResponse — session summary
# ---------------------------------------------------------------------------


class ObserveResponse(BaseModel):
    """Summary response for a completed ``harness observe --no-follow`` session.

    Emitted to *stderr* as a single NDJSON line after the observe command
    exits in ``--no-follow`` mode.  Provides aggregate metrics about the
    session so downstream tools can assess filter coverage and schema health
    without re-parsing the full output stream.

    Fields
    ------
    command:
        Always ``"harness observe"``.
    log_file:
        Path to the NDJSON file that was tailed.
    lines_scanned:
        Total non-empty lines read from the file (before any filtering).
    entries_matched:
        Lines that passed all active filters (domain, trace_id, level).
    entries_emitted:
        Matched entries that were successfully emitted to stdout.
    validation_errors:
        Count of matched entries where :class:`LogEntry` validation failed.
        These are still emitted as raw JSON so no data is lost, but the
        non-zero count signals schema drift worth investigating.
    domain_filter:
        The ``--domain`` prefix filter applied, or ``None``.
    trace_id_filter:
        The ``--trace-id`` filter applied, or ``None``.
    min_level:
        The minimum log level filter applied (e.g. ``"INFO"``).
    """

    model_config = ConfigDict(extra="forbid")

    command: str = Field(default="harness observe")
    log_file: str = Field(description="Path to the NDJSON log file that was tailed.")
    lines_scanned: int = Field(
        ge=0,
        description="Total non-empty lines read from the log file (before filtering).",
    )
    entries_matched: int = Field(
        ge=0,
        description="Lines that passed all active filters.",
    )
    entries_emitted: int = Field(
        ge=0,
        description="Matched entries successfully emitted to stdout.",
    )
    validation_errors: int = Field(
        ge=0,
        default=0,
        description=(
            "Matched entries that failed ``LogEntry`` schema validation.  "
            "These are emitted as raw JSON rather than schema-validated output."
        ),
    )
    domain_filter: Optional[str] = Field(
        default=None,
        description="Active ``--domain`` filter, or None if no domain filter was set.",
    )
    trace_id_filter: Optional[str] = Field(
        default=None,
        description="Active ``--trace-id`` filter, or None if no trace filter was set.",
    )
    min_level: str = Field(
        default="DEBUG",
        description="Minimum log level filter applied (e.g. 'INFO', 'ERROR').",
    )
