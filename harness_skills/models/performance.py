"""harness_skills/models/performance.py
======================================
Pydantic models for the performance-measurement hooks layer.

These models provide validated, serialisable representations of the data
structures produced by :mod:`harness_skills.performance_hooks` and
:mod:`skills.perf_hooks`, making it easy for downstream agents and CI
pipelines to consume performance metrics as structured JSON.

Classes
-------
ToolTimingModel
    Single tool-call timing record (name, elapsed ms, success flag).
MemorySnapshotModel
    Point-in-time memory reading (tracemalloc heap bytes + RSS bytes).
PerformanceReportModel
    Aggregated session-level report with timing, tool stats, percentiles,
    and memory data.  Maps directly to the dataclass returned by
    :py:meth:`harness_skills.performance_hooks.PerformanceTracker.summary`.
PerformanceResponse
    Top-level API response envelope for the ``harness performance`` skill,
    consumed by agents and CI pipelines as structured JSON.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# ToolTimingModel
# ---------------------------------------------------------------------------


class ToolTimingModel(BaseModel):
    """Validated representation of a single tool-call timing record.

    Mirrors :class:`harness_skills.performance_hooks.ToolTiming` but as a
    Pydantic model so it can be serialised, validated, and transported across
    process boundaries.
    """

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(
        ...,
        min_length=1,
        description="Name of the tool that was invoked (e.g. 'Read', 'Bash').",
    )
    elapsed_ms: float = Field(
        ...,
        ge=0.0,
        description="Wall-clock elapsed time for this tool call in milliseconds.",
    )
    success: bool = Field(
        ...,
        description=(
            "True when PostToolUse fired successfully; "
            "False when PostToolUseFailure fired."
        ),
    )


# ---------------------------------------------------------------------------
# MemorySnapshotModel
# ---------------------------------------------------------------------------


class MemorySnapshotModel(BaseModel):
    """Validated representation of a point-in-time memory snapshot.

    Mirrors :class:`harness_skills.performance_hooks.MemorySnapshot` as a
    Pydantic model.  Both integer fields use ``-1`` as a sentinel when the
    underlying measurement source (tracemalloc or psutil) is unavailable.
    """

    model_config = ConfigDict(extra="forbid")

    label: str = Field(
        ...,
        min_length=1,
        description=(
            "Snapshot label — typically 'session_start' or 'session_end'."
        ),
    )
    tracemalloc_bytes: int = Field(
        ...,
        ge=-1,
        description=(
            "Current traced-heap bytes as reported by tracemalloc. "
            "-1 when tracemalloc is not running."
        ),
    )
    rss_bytes: int = Field(
        ...,
        ge=-1,
        description=(
            "Process RSS in bytes as reported by psutil. "
            "-1 when psutil is not installed."
        ),
    )


# ---------------------------------------------------------------------------
# PerformanceReportModel
# ---------------------------------------------------------------------------


class PerformanceReportModel(BaseModel):
    """Aggregated performance data for a completed agent session.

    All fields mirror the
    :class:`~harness_skills.performance_hooks.PerformanceReport` dataclass.
    Fields that cannot be computed (e.g. when no tools were called) are
    ``None``; fields that depend on optional libraries (psutil / tracemalloc)
    use ``-1`` as a sentinel.

    Timing
    ------
    startup_duration_ms
        Milliseconds from ``SessionStart`` to the first ``PreToolUse`` event.
        ``None`` until the first tool call is observed.
    session_duration_ms
        Total wall-clock duration from ``SessionStart`` to ``SessionEnd``.
        ``None`` when the session has not yet ended.

    Tool statistics
    ---------------
    tool_count
        Total tool calls recorded (success + failure combined).
    tool_timings
        Per-call records in invocation order.

    Response-time percentiles (all ``None`` when ``tool_count == 0``)
    -----------------------------------------------------------------
    mean_response_ms, median_response_ms, min_response_ms,
    max_response_ms, p95_response_ms

    Memory
    ------
    peak_tracemalloc_bytes
        Peak traced-heap bytes since session start.  ``-1`` when tracemalloc
        is unavailable.
    delta_rss_bytes
        ``end_rss - start_rss`` via psutil.  ``-1`` when psutil is unavailable.
    memory_snapshots
        Ordered list of snapshots taken during the session.
    """

    model_config = ConfigDict(extra="forbid")

    # ── Timing ──────────────────────────────────────────────────────────────
    startup_duration_ms: Optional[float] = Field(
        default=None,
        ge=0.0,
        description=(
            "Milliseconds from SessionStart to the first PreToolUse event. "
            "None until the first tool call is observed."
        ),
    )
    session_duration_ms: Optional[float] = Field(
        default=None,
        ge=0.0,
        description=(
            "Total wall-clock milliseconds from SessionStart to SessionEnd. "
            "None when the session has not yet ended."
        ),
    )

    # ── Tool stats ───────────────────────────────────────────────────────────
    tool_count: int = Field(
        default=0,
        ge=0,
        description="Total number of tool calls recorded (success + failure).",
    )
    tool_timings: List[ToolTimingModel] = Field(
        default_factory=list,
        description="Per-call timing records in invocation order.",
    )

    # ── Response-time percentiles ────────────────────────────────────────────
    mean_response_ms: Optional[float] = Field(
        default=None,
        ge=0.0,
        description=(
            "Arithmetic mean of all tool elapsed_ms values. "
            "None when tool_count == 0."
        ),
    )
    median_response_ms: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="50th-percentile elapsed_ms. None when tool_count == 0.",
    )
    min_response_ms: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Fastest tool call in ms. None when tool_count == 0.",
    )
    max_response_ms: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Slowest tool call in ms. None when tool_count == 0.",
    )
    p95_response_ms: Optional[float] = Field(
        default=None,
        ge=0.0,
        description=(
            "95th-percentile elapsed_ms (linear interpolation). "
            "None when tool_count == 0."
        ),
    )

    # ── Memory ───────────────────────────────────────────────────────────────
    peak_tracemalloc_bytes: int = Field(
        default=-1,
        ge=-1,
        description=(
            "Peak traced-heap bytes since session start (tracemalloc). "
            "-1 when tracemalloc was not started or is unavailable."
        ),
    )
    delta_rss_bytes: int = Field(
        default=-1,
        ge=-1,
        description=(
            "RSS at session end minus RSS at session start (psutil). "
            "-1 when psutil is unavailable."
        ),
    )
    memory_snapshots: List[MemorySnapshotModel] = Field(
        default_factory=list,
        description="Ordered list of memory snapshots taken during the session.",
    )


# ---------------------------------------------------------------------------
# PerformanceResponse
# ---------------------------------------------------------------------------


class PerformanceResponse(BaseModel):
    """Top-level API response envelope for the ``harness performance`` skill.

    Emitted as the machine-readable JSON block at the end of every
    ``/harness:performance`` invocation so downstream agents can consume
    metrics without re-running the script.

    Fields
    ------
    command
        Fixed skill identifier — always ``"harness performance"``.
    tracker_class
        Fully-qualified Python name of the tracker implementation.
    dimensions
        The three performance dimensions captured by the tracker.
    report
        Populated once the tracker has collected data (i.e. after
        ``tracker.summary()`` has been called).  ``None`` in the snippet /
        field-reference output modes.
    psutil_available
        ``True`` when psutil is installed and RSS tracking is active.
    notes
        Human-readable caveat for consumers about optional dependencies.
    """

    model_config = ConfigDict(extra="forbid")

    command: str = Field(
        default="harness performance",
        description="Fixed skill command identifier.",
    )
    tracker_class: str = Field(
        default="harness_skills.performance_hooks.PerformanceTracker",
        description="Fully-qualified name of the tracker implementation.",
    )
    dimensions: List[str] = Field(
        default_factory=lambda: [
            "startup_duration_ms",
            "tool_response_times",
            "memory_usage",
        ],
        description="Performance dimensions captured by the tracker.",
    )
    report: Optional[PerformanceReportModel] = Field(
        default=None,
        description=(
            "Populated when the tracker has collected data "
            "(i.e. after tracker.summary() has been called). "
            "None in snippet / field-reference output modes."
        ),
    )
    psutil_available: bool = Field(
        default=False,
        description="True when psutil is installed and RSS tracking is active.",
    )
    notes: str = Field(
        default="psutil is optional; delta_rss_bytes returns -1 when unavailable",
        description="Human-readable caveat for consumers.",
    )
