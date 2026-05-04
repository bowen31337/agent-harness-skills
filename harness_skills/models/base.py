from __future__ import annotations

from enum import Enum, StrEnum
from typing import Optional

from pydantic import BaseModel


class Status(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WARNING = "warning"
    RUNNING = "running"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class FreshnessScore(StrEnum):
    CURRENT = "current"
    STALE = "stale"
    OUTDATED = "outdated"
    OBSOLETE = "obsolete"


class Violation(BaseModel):
    rule_id: str
    severity: str
    file_path: str | None = None
    line_number: int | None = None
    column: int | None = None
    message: str
    suggestion: str | None = None


class GateResult(BaseModel):
    gate_id: str
    gate_name: str
    status: Status
    duration_ms: int | None = None
    violations: list[Violation] = []
    message: str | None = None


class HarnessResponse(BaseModel):
    command: str
    status: Status
    timestamp: str | None = None
    duration_ms: int | None = None
    version: str | None = None
    message: str | None = None


class ArtifactFreshness(BaseModel):
    artifact_path: str
    artifact_type: str
    freshness: FreshnessScore
    last_generated: str | None = None
    staleness_score: float | None = None
    stale_references: list[str] = []


class FileLocation(BaseModel):
    file_path: str
    start_line: int | None = None
    end_line: int | None = None


class TaskInfo(BaseModel):
    task_id: str
    description: str
    status: Status
    dependencies: list[str] = []


class AgentConflict(BaseModel):
    agent_id: str
    resource: str
    conflict_type: str
    message: str | None = None
