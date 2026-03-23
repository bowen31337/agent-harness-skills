"""Typed response models for the stale execution-plan detector.

A plan is *stale* when one or more of its tasks has not received a progress
update for longer than a configurable threshold.  The detector emits a
``StalePlanResponse`` that agents can act on immediately.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from harness_skills.models.base import HarnessResponse, Severity

# Type alias for artifact-level severity (includes the "healthy" baseline state)
ArtifactSeverity = Literal["healthy", "INFO", "WARNING", "ERROR", "CRITICAL"]


# ── Per-task staleness detail ──────────────────────────────────────────────────


class StaleTask(BaseModel):
    """A single task flagged as stale within an execution plan."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    task_id: str = Field(description="Unique identifier of the task.")
    title: str = Field(description="Human-readable task title.")
    status: Literal["pending", "in_progress", "completed", "blocked"] = Field(
        description="Last-known task status at the time of detection."
    )
    assigned_agent: str | None = Field(
        default=None,
        description="Agent currently responsible for this task, if any.",
    )
    last_updated: datetime = Field(
        description="UTC timestamp of the most recent progress update on this task."
    )
    idle_seconds: float = Field(
        ge=0.0,
        description="Seconds elapsed since the last progress update.",
    )
    threshold_seconds: float = Field(
        ge=0.0,
        description="The staleness threshold (seconds) configured at detection time.",
    )
    severity: Severity = Field(
        description=(
            "INFO  → idle < 2× threshold; "
            "WARNING → idle < 4× threshold; "
            "ERROR   → idle < 8× threshold; "
            "CRITICAL → idle ≥ 8× threshold."
        )
    )
    recommendation: str | None = Field(
        default=None,
        description="LLM-generated actionable recommendation for this task.",
    )


# ── Plan-level staleness summary ──────────────────────────────────────────────


class StalePlanSummary(BaseModel):
    """High-level summary of staleness across the whole plan."""

    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(description="Identifier for the execution plan being evaluated.")
    total_tasks: int = Field(ge=0)
    stale_tasks: int = Field(ge=0)
    healthy_tasks: int = Field(ge=0)
    threshold_seconds: float = Field(ge=0.0, description="Configured staleness threshold.")
    most_idle_task_id: str | None = Field(
        default=None,
        description="task_id of the task with the longest idle period.",
    )
    max_idle_seconds: float | None = Field(
        default=None, ge=0.0, description="Longest idle duration in the plan."
    )
    overall_health: Literal["healthy", "degraded", "critical"] = Field(
        description=(
            "healthy   → 0 stale tasks; "
            "degraded  → 1–49 % stale; "
            "critical  → ≥50 % stale."
        )
    )


# ── Artifact freshness models ──────────────────────────────────────────────────


class ArtifactStalenessEntry(BaseModel):
    """Staleness detail for a single canonical harness artifact file."""

    model_config = ConfigDict(extra="forbid")

    file: str = Field(description="Relative path to the artifact file.")
    last_updated: str | None = Field(
        default=None,
        description=(
            "Value of the last_updated field extracted from the file's "
            "``<!-- harness:auto-generated -->`` front-matter block, "
            "or None when the field is absent or the file is missing."
        ),
    )
    age_days: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Age of the artifact in whole days relative to today.  "
            "None when the file is missing or the timestamp cannot be parsed."
        ),
    )
    severity: ArtifactSeverity = Field(
        description=(
            "healthy  → age ≤ threshold; "
            "INFO     → threshold < age ≤ 2× threshold; "
            "WARNING  → 2× threshold < age ≤ 4× threshold, or timestamp missing; "
            "ERROR    → file absent from repository; "
            "CRITICAL → age > 4× threshold."
        )
    )


class ArtifactStalenessSummary(BaseModel):
    """Summary of artifact freshness across all canonical harness files."""

    model_config = ConfigDict(extra="forbid")

    threshold_days: int = Field(
        ge=0,
        description="Maximum artifact age in days before the artifact is considered stale.",
    )
    artifacts_checked: int = Field(ge=0, description="Total number of artifact files inspected.")
    stale_artifacts: int = Field(
        ge=0,
        description="Number of artifacts flagged as non-healthy (INFO, WARNING, ERROR, CRITICAL).",
    )
    missing_artifacts: int = Field(
        ge=0, description="Number of expected artifact files that were not found on disk."
    )
    results: list[ArtifactStalenessEntry] = Field(
        default_factory=list,
        description="Per-file staleness detail, in the order the files were inspected.",
    )


# ── Top-level response ─────────────────────────────────────────────────────────


class StalePlanResponse(HarnessResponse):
    """Response schema emitted by the stale-plan detector.

    Contains per-task detail, a plan-level summary, and an optional
    LLM-generated narrative analysis explaining the staleness pattern
    and suggested recovery actions.  When artifact scanning is enabled
    (the default), also contains a freshness report for canonical harness
    artifact files.
    """

    command: str = "harness detect-stale"

    summary: StalePlanSummary = Field(
        description="Aggregate staleness metrics for the plan."
    )
    stale_task_details: list[StaleTask] = Field(
        default_factory=list,
        description="Full detail for every task that exceeded the staleness threshold.",
    )
    llm_analysis: str | None = Field(
        default=None,
        description=(
            "Narrative analysis from Claude explaining why the plan may be stalled "
            "and what recovery actions are recommended."
        ),
    )
    analysis_model: str | None = Field(
        default=None,
        description="Model ID used for the LLM analysis, e.g. 'claude-opus-4-6'.",
    )
    artifact_staleness: ArtifactStalenessSummary | None = Field(
        default=None,
        description=(
            "Freshness report for canonical harness artifact files "
            "(AGENTS.md, ARCHITECTURE.md, PRINCIPLES.md, EVALUATION.md). "
            "None when artifact scanning is disabled via --skip-artifacts."
        ),
    )
