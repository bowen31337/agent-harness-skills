"""Typed response model for ``harness screenshot``."""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from harness_skills.models.base import HarnessResponse


class ScreenshotResponse(HarnessResponse):
    """Response schema for ``harness screenshot``."""

    command: str = "harness screenshot"
    file_path: str | None = None
    dimensions: str | None = None
    base64_data: str | None = None
    existing_screenshots: list[str] = Field(default_factory=list)
