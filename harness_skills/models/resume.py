"""Typed response model for ``harness resume``."""

from __future__ import annotations

from typing import Optional

from harness_skills.models.base import HarnessResponse


class ResumeResponse(HarnessResponse):
    """Response schema for ``harness resume``."""

    command: str = "harness resume"
    source: str = ""  # "md" or "jsonl"
    context_block: str = ""
    hints_only: Optional[str] = None
    plan_id: Optional[str] = None
