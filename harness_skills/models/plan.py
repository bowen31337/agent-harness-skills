"""Typed response model for ``harness plan``."""

from __future__ import annotations

from pydantic import Field

from harness_skills.models.base import HarnessResponse


class PlanResponse(HarnessResponse):
    """Response schema for ``harness plan``."""

    command: str = "harness plan"
    plan_id: str = ""
    plan_path: str = ""
    title: str = ""
    objective: str = ""
    task_count: int = 0
