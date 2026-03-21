"""Typed response models for the harness telemetry reporter.

The reporter reads ``docs/harness-telemetry.json`` (written by
``HarnessTelemetry`` hooks) and derives three kinds of metrics:

  1. **Artifact utilization** — which harness files are read most / least.
  2. **Command frequency**   — how often each slash-command is invoked.
  3. **Gate effectiveness**  — which quality gates catch the most failures.

All models inherit from ``HarnessResponse`` so downstream agents get a
consistent envelope regardless of which harness command produced them.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from harness_skills.models.base import HarnessResponse


# ── Artifact utilization ───────────────────────────────────────────────────────


class ArtifactMetric(BaseModel):
    """Utilization statistics for a single harness artifact."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(description="Relative path (or glob/grep pattern) of the artifact.")
    read_count: int = Field(ge=0, description="Total read events across all sessions.")
    utilization_rate: float = Field(
        ge=0.0,
        le=1.0,
        description="Fraction of total artifact reads attributed to this file (0.0–1.0).",
    )
    category: Literal["hot", "warm", "cold", "unused"] = Field(
        description=(
            "hot    → top-20 % by reads; "
            "warm   → 20–60 %; "
            "cold   → bottom-40 %; "
            "unused → never read (read_count == 0)."
        )
    )
    recommendation: Optional[str] = Field(
        default=None,
        description=(
            "Suggested action: None for hot/warm; "
            "'Consider refactoring' for cold; "
            "'Candidate for removal' for unused."
        ),
    )


# ── Command frequency ──────────────────────────────────────────────────────────


class CommandMetric(BaseModel):
    """Invocation frequency statistics for a single slash-command."""

    model_config = ConfigDict(extra="forbid")

    command: str = Field(description="Slash-command name (without the leading '/').")
    invocation_count: int = Field(ge=0, description="Total invocations across all sessions.")
    frequency_rate: float = Field(
        ge=0.0,
        le=1.0,
        description="Fraction of total command invocations attributed to this command (0.0–1.0).",
    )
    sessions_active: int = Field(
        ge=0,
        description="Number of distinct sessions in which this command was invoked.",
    )


# ── Gate effectiveness ─────────────────────────────────────────────────────────


class GateMetric(BaseModel):
    """Failure-rate and signal-strength statistics for a quality gate."""

    model_config = ConfigDict(extra="forbid")

    gate_id: str = Field(description="Identifier of the quality gate (e.g. 'ruff', 'mypy', 'pytest').")
    failure_count: int = Field(ge=0, description="Total failures recorded across all sessions.")
    effectiveness_score: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Normalised signal strength: failure_count / max(failure_count across gates). "
            "1.0 = highest-signal gate; 0.0 = never fires."
        ),
    )
    signal_strength: Literal["high", "medium", "low", "silent"] = Field(
        description=(
            "high   → effectiveness_score ≥ 0.6; "
            "medium → 0.3–0.6; "
            "low    → 0.0–0.3 (> 0); "
            "silent → effectiveness_score == 0.0."
        )
    )
    recommendation: Optional[str] = Field(
        default=None,
        description=(
            "Suggested action: None for high/medium; "
            "'Review gate configuration' for low; "
            "'Gate may be redundant — consider removal' for silent."
        ),
    )


# ── Top-level summary ──────────────────────────────────────────────────────────


class TelemetrySummary(BaseModel):
    """Aggregate metadata about the telemetry dataset being analysed."""

    model_config = ConfigDict(extra="forbid")

    sessions_analyzed: int = Field(ge=0, description="Number of sessions in the telemetry file.")
    total_artifact_reads: int = Field(ge=0, description="Sum of all artifact read events.")
    total_command_invocations: int = Field(ge=0, description="Sum of all command invocations.")
    total_gate_failures: int = Field(ge=0, description="Sum of all gate failure events.")
    unique_artifacts: int = Field(ge=0, description="Number of distinct artifacts ever read.")
    unique_commands: int = Field(ge=0, description="Number of distinct commands ever invoked.")
    unique_gates: int = Field(ge=0, description="Number of distinct gates ever fired.")
    cold_artifact_count: int = Field(
        ge=0, description="Artifacts in the 'cold' or 'unused' category — redesign/removal candidates."
    )
    silent_gate_count: int = Field(
        ge=0, description="Gates that have never fired — redundancy candidates."
    )
    telemetry_path: str = Field(description="Absolute path to the telemetry JSON file consumed.")
    schema_version: Optional[str] = Field(
        default=None, description="Schema version from the telemetry file."
    )
    last_updated: Optional[str] = Field(
        default=None, description="ISO-8601 timestamp of the last telemetry write."
    )


# ── Top-level response ─────────────────────────────────────────────────────────


class TelemetryReport(HarnessResponse):
    """Response schema emitted by ``/harness:telemetry``.

    Contains per-artifact utilization rates, per-command invocation
    frequencies, per-gate effectiveness scores, and an overall summary
    that highlights underutilised artifacts and silent gates for redesign
    or removal.
    """

    command: str = "harness telemetry"

    summary: TelemetrySummary = Field(
        description="Aggregate metadata about the telemetry dataset."
    )
    artifacts: list[ArtifactMetric] = Field(
        default_factory=list,
        description="Artifact metrics sorted descending by read_count.",
    )
    commands: list[CommandMetric] = Field(
        default_factory=list,
        description="Command metrics sorted descending by invocation_count.",
    )
    gates: list[GateMetric] = Field(
        default_factory=list,
        description="Gate metrics sorted descending by failure_count.",
    )
