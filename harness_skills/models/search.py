"""Typed response model for ``harness search``."""

from __future__ import annotations

from pydantic import BaseModel, Field

from harness_skills.models.base import HarnessResponse


class SearchResult(BaseModel):
    """A single symbol search result."""

    name: str
    kind: str  # function, class, method, constant
    file_path: str
    line_number: int = 0
    score: float = 0.0


class SearchResponse(HarnessResponse):
    """Response schema for ``harness search``."""

    command: str = "harness search"
    query: str = ""
    results: list[SearchResult] = Field(default_factory=list)
    total_matches: int = 0
