from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel


class Status(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WARNING = "warning"
    RUNNING = "running"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class FreshnessScore(str, Enum):
    CURRENT = "current"
    STALE = "stale"
    OUTDATED = "outdated"
    OBSOLETE = "obsolete"


class Violation(BaseModel):
    rule_id: str
    severity: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    column: Optional[int] = None
    message: str
    suggestion: Optional[str] = None


class GateResult(BaseModel):
    gate_id: str
    gate_name: str
    status: Status
    duration_ms: Optional[int] = None
    violations: list[Violation] = []
    message: Optional[str] = None


class HarnessResponse(BaseModel):
    command: str
    status: Status
    timestamp: Optional[str] = None
    duration_ms: Optional[int] = None
    version: Optional[str] = None
    message: Optional[str] = None


class ArtifactFreshness(BaseModel):
    artifact_path: str
    artifact_type: str
    freshness: FreshnessScore
    last_generated: Optional[str] = None
    staleness_score: Optional[float] = None
    stale_references: list[str] = []


class FileLocation(BaseModel):
    file_path: str
    start_line: Optional[int] = None
    end_line: Optional[int] = None


class TaskInfo(BaseModel):
    task_id: str
    description: str
    status: Status
    dependencies: list[str] = []


class AgentConflict(BaseModel):
    agent_id: str
    resource: str
    conflict_type: str
    message: Optional[str] = None
