"""Typed response model for ``harness coordinate``."""

from __future__ import annotations

from pydantic import BaseModel, Field

from harness_skills.models.base import AgentConflict, HarnessResponse


class AgentTask(BaseModel):
    """Represents one agent's active task."""

    agent_id: str
    task_id: str
    files: list[str] = Field(default_factory=list)
    status: str = "active"


class CoordinateResponse(HarnessResponse):
    """Response schema for ``harness coordinate``."""

    command: str = "harness coordinate"
    agents: list[AgentTask] = Field(default_factory=list)
    conflicts: list[AgentConflict] = Field(default_factory=list)
    suggested_order: list[str] = Field(default_factory=list)
    rationale: str = ""
