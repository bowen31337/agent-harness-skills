"""harness_skills.models — shared response models."""
from harness_skills.models.base import (
    Status, Severity, GateResult, Violation, HarnessResponse,
    ArtifactFreshness, FreshnessScore, FileLocation, TaskInfo, AgentConflict,
)
from harness_skills.models.create import CreateConfigResponse, CreateResponse
from harness_skills.models.manifest import ManifestValidateResponse, ManifestValidationError
from harness_skills.models.context import (
    ContextManifest, ContextManifestFile, ContextStats, SearchPattern, SkipEntry,
)
from harness_skills.models.observe import LogEntry, ObserveResponse
from harness_skills.models.lock import (
    LockAcquireRequest, LockExtendRequest, LockReleaseRequest,
    LockRecord, LockStateResponse, LockOperationResponse, LockListResponse,
)
from harness_skills.models.stale import (
    ArtifactResult, ArtifactStaleness, StaleTask, StalePlanSummary, StalePlanResponse,
    SourceFileDrift, DocumentationDrift,
)
from harness_skills.task_lock import (
    TaskLock, TaskLockProtocol, LockConflictError, LockNotOwnedError,
)
from harness_skills.models.errors import (
    ErrorGroupResponse,
    DomainOverview,
    ErrorAggregationResponse,
)
from harness_skills.models.docs import (
    GeneratedDocsReport,
    GeneratedDocsCategories,
    SchemaCategoryResult,
    APICategoryResult,
    GraphCategoryResult,
    SchemaEntity,
    RouteEntity,
    DependencyEdge,
)

__all__ = [
    # base
    "Status", "Severity", "GateResult", "Violation", "HarnessResponse",
    "ArtifactFreshness", "FreshnessScore", "FileLocation", "TaskInfo", "AgentConflict",
    # create
    "CreateConfigResponse", "CreateResponse",
    # manifest
    "ManifestValidateResponse", "ManifestValidationError",
    # context
    "ContextManifest", "ContextManifestFile", "ContextStats", "SearchPattern", "SkipEntry",
    # observe
    "LogEntry", "ObserveResponse",
    # lock (models)
    "LockAcquireRequest", "LockExtendRequest", "LockReleaseRequest",
    "LockRecord", "LockStateResponse", "LockOperationResponse", "LockListResponse",
    # stale plan detection
    "ArtifactResult", "ArtifactStaleness", "StaleTask", "StalePlanSummary", "StalePlanResponse",
    "SourceFileDrift", "DocumentationDrift",
    # task lock
    "TaskLock", "TaskLockProtocol", "LockConflictError", "LockNotOwnedError",
    # errors
    "ErrorGroupResponse", "DomainOverview", "ErrorAggregationResponse",
    # docs generation
    "GeneratedDocsReport", "GeneratedDocsCategories",
    "SchemaCategoryResult", "APICategoryResult", "GraphCategoryResult",
    "SchemaEntity", "RouteEntity", "DependencyEdge",
]
