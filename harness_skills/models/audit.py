"""Typed response model for ``harness audit``."""

from __future__ import annotations

from pydantic import Field

from harness_skills.models.base import ArtifactFreshness, HarnessResponse


class AuditResponse(HarnessResponse):
    """Response schema for ``harness audit``."""

    command: str = "harness audit"
    artifacts: list[ArtifactFreshness] = Field(default_factory=list)
    total_artifacts: int = 0
    current_count: int = 0
    stale_count: int = 0
    outdated_count: int = 0
    obsolete_count: int = 0
