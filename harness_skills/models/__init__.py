"""harness_skills.models — shared response models.

Every CLI command that emits structured output has a typed Pydantic response
model defined here.  All JSON output is validated through these models before
being written to stdout, ensuring schema conformance at the point of emission.

Command → model mapping
-----------------------
harness create        → CreateResponse
harness evaluate      → EvaluateResponse   (also EvaluationReport in generators/)
harness lint          → LintResponse
harness observe       → LogEntry (per-entry), ObserveResponse (session summary)
harness telemetry     → TelemetryReport
harness update        → UpdateResponse
harness detect-stale  → StalePlanResponse
"""
from harness_skills.models.base import (
    Status, Severity, GateResult, Violation, HarnessResponse,
    ArtifactFreshness, FreshnessScore, FileLocation, TaskInfo, AgentConflict,
)
from harness_skills.models.create import (
    CreateResponse, DetectedStack, GeneratedArtifact,
)
from harness_skills.models.evaluate import EvaluateResponse
from harness_skills.models.lint import LintResponse
from harness_skills.models.observe import LogEntry, ObserveResponse
from harness_skills.models.stale import StalePlanResponse, StalePlanSummary, StaleTask
from harness_skills.models.status import (
    TaskDetail,
    TaskStatusCounts,
    PlanSnapshot,
    DashboardSummary,
    StatusDashboardResponse,
)
from harness_skills.models.telemetry import (
    TelemetryReport, TelemetrySummary, ArtifactMetric, CommandMetric, GateMetric,
)
from harness_skills.models.update import UpdateResponse, ArtifactDiff, ChangelogEntry
from harness_skills.models.gate_configs import (
    BaseGateConfig,
    CoverageGateConfig,
    RegressionGateConfig,
    SecurityGateConfig,
    PerformanceGateConfig,
    ArchitectureGateConfig,
    PrinciplesGateConfig,
    DocsFreshnessGateConfig,
    TypesGateConfig,
    LintGateConfig,
    GATE_CONFIG_CLASSES,
    PROFILE_GATE_DEFAULTS,
)

__all__ = [
    # ── base ────────────────────────────────────────────────────────────────
    "Status",
    "Severity",
    "GateResult",
    "Violation",
    "HarnessResponse",
    "ArtifactFreshness",
    "FreshnessScore",
    "FileLocation",
    "TaskInfo",
    "AgentConflict",
    # ── harness create ──────────────────────────────────────────────────────
    "CreateResponse",
    "DetectedStack",
    "GeneratedArtifact",
    # ── harness evaluate ────────────────────────────────────────────────────
    "EvaluateResponse",
    # ── harness lint ────────────────────────────────────────────────────────
    "LintResponse",
    # ── harness observe ─────────────────────────────────────────────────────
    "LogEntry",
    "ObserveResponse",
    # ── harness detect-stale ────────────────────────────────────────────────
    "StalePlanResponse",
    "StalePlanSummary",
    "StaleTask",
    # ── harness status dashboard ────────────────────────────────────────────
    "TaskDetail",
    "TaskStatusCounts",
    "PlanSnapshot",
    "DashboardSummary",
    "StatusDashboardResponse",
    # ── harness telemetry ───────────────────────────────────────────────────
    "TelemetryReport",
    "TelemetrySummary",
    "ArtifactMetric",
    "CommandMetric",
    "GateMetric",
    # ── harness update ──────────────────────────────────────────────────────
    "UpdateResponse",
    "ArtifactDiff",
    "ChangelogEntry",
    # ── gate configuration models ────────────────────────────────────────────
    "BaseGateConfig",
    "CoverageGateConfig",
    "RegressionGateConfig",
    "SecurityGateConfig",
    "PerformanceGateConfig",
    "ArchitectureGateConfig",
    "PrinciplesGateConfig",
    "DocsFreshnessGateConfig",
    "TypesGateConfig",
    "LintGateConfig",
    "GATE_CONFIG_CLASSES",
    "PROFILE_GATE_DEFAULTS",
]
