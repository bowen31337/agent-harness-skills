"""Typed models for pattern frequency extraction."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PatternFrequencyModel(BaseModel):
    """Pydantic model for a detected code pattern."""

    pattern_name: str
    category: str
    occurrences: int = 0
    example_files: list[str] = Field(default_factory=list)
    suggested_principle: str = ""
