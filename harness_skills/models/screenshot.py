"""Typed response model for ``harness screenshot``."""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from harness_skills.models.base import HarnessResponse


class ScreenshotResponse(HarnessResponse):
    """Response schema for ``harness screenshot``."""

    command: str = "harness screenshot"
    file_path: Optional[str] = None
    dimensions: Optional[str] = None
    base64_data: Optional[str] = None
    existing_screenshots: list[str] = Field(default_factory=list)
