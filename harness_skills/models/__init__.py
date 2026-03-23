"""harness_skills.models — shared Pydantic response models.

Every CLI command that produces structured output constructs a typed response
model from this package and emits it via ``model_dump_json()`` so the output is
always schema-validated before reaching stdout.

Command → model mapping
-----------------------
+---------------------------+-----------------------------+
| CLI command               | Response model              |
+===========================+=============================+
| harness create            | CreateResponse              |
| harness evaluate          | EvaluateResponse            |
| harness manifest validate | ManifestValidateResponse    |
| harness observe           | ObserveResponse (+ LogEntry)|
| harness status            | StatusDashboardResponse     |
| harness telemetry         | TelemetryReport             |
| harness detect-stale      | StalePlanResponse           |
| harness lint              | LintResponse                |
| harness update            | UpdateResponse              |
+---------------------------+-----------------------------+
"""

from harness_skills.models.base import (
    AgentConflict,
    ArtifactFreshness,
    FileLocation,
    FreshnessScore,
    GateResult,
    HarnessResponse,
    Severity,
    Status,
    TaskInfo,
    Violation,
)
from harness_skills.models.create import (
    CreateResponse,
    DetectedStack,
    GeneratedArtifact,
)
from harness_skills.models.evaluate import EvaluateResponse
from harness_skills.models.lint import LintResponse
from harness_skills.models.manifest import ManifestValidationError, ManifestValidateResponse
from harness_skills.models.observe import LogEntry, ObserveResponse
from harness_skills.models.stale import StalePlanResponse, StalePlanSummary, StaleTask
from harness_skills.models.status import (
    DashboardSummary,
    LockStatus,
    PlanSnapshot,
    PlanStatusValue,
    Priority,
    StatusDashboardResponse,
    TaskDetail,
    TaskStatus,
    TaskStatusCounts,
)
from harness_skills.models.telemetry import (
    ArtifactMetric,
    CommandMetric,
    GateMetric,
    TelemetryReport,
    TelemetrySummary,
)
from harness_skills.models.update import ArtifactDiff, ChangelogEntry, UpdateResponse

__all__ = [
    # ── base ──────────────────────────────────────────────────────────────────
    "AgentConflict",
    "ArtifactFreshness",
    "FileLocation",
    "FreshnessScore",
    "GateResult",
    "HarnessResponse",
    "Severity",
    "Status",
    "TaskInfo",
    "Violation",
    # ── create ────────────────────────────────────────────────────────────────
    "CreateResponse",
    "DetectedStack",
    "GeneratedArtifact",
    # ── evaluate ──────────────────────────────────────────────────────────────
    "EvaluateResponse",
    # ── lint ──────────────────────────────────────────────────────────────────
    "LintResponse",
    # ── manifest ──────────────────────────────────────────────────────────────
    "ManifestValidationError",
    "ManifestValidateResponse",
    # ── observe ───────────────────────────────────────────────────────────────
    "LogEntry",
    "ObserveResponse",
    # ── stale ─────────────────────────────────────────────────────────────────
    "StalePlanResponse",
    "StalePlanSummary",
    "StaleTask",
    # ── status ────────────────────────────────────────────────────────────────
    "DashboardSummary",
    "LockStatus",
    "PlanSnapshot",
    "PlanStatusValue",
    "Priority",
    "StatusDashboardResponse",
    "TaskDetail",
    "TaskStatus",
    "TaskStatusCounts",
    # ── telemetry ─────────────────────────────────────────────────────────────
    "ArtifactMetric",
    "CommandMetric",
    "GateMetric",
    "TelemetryReport",
    "TelemetrySummary",
    # ── update ────────────────────────────────────────────────────────────────
    "ArtifactDiff",
    "ChangelogEntry",
    "UpdateResponse",
]
