"""Typed response model for ``harness lint`` (/harness:lint)."""

from __future__ import annotations

from pydantic import Field

from harness_skills.models.base import HarnessResponse, Violation


class LintResponse(HarnessResponse):
    """Response schema for ``harness lint`` (/harness:lint).

    Emitted after running all architectural checks and golden-principle
    enforcement rules in a single pass.
    """

    command: str = "harness lint"
    passed: bool = True

    total_violations: int = Field(ge=0, default=0)
    critical_count: int = Field(ge=0, default=0)
    error_count: int = Field(ge=0, default=0)
    warning_count: int = Field(ge=0, default=0)
    info_count: int = Field(ge=0, default=0)
    violations: list[Violation] = Field(default_factory=list)
    files_checked: int = Field(ge=0, default=0)
    rules_applied: list[str] = Field(
        default_factory=list,
        description="Rule IDs evaluated during this lint run.",
    )
