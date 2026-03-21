"""Typed response model for ``harness update`` (/harness:update)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from harness_skills.models.base import HarnessResponse, Violation


class ArtifactDiff(BaseModel):
    """Change record for a single artifact during a harness update."""

    model_config = ConfigDict(extra="forbid")

    artifact_path: str
    change_type: Literal["created", "updated", "unchanged", "removed"]
    sections_changed: list[str] = Field(
        default_factory=list,
        description="Named sections modified by the three-way merge.",
    )
    manual_edits_preserved: bool = Field(
        default=True,
        description="False if manual edits could not be merged and were overwritten.",
    )


class ChangelogEntry(BaseModel):
    """Single entry appended to docs/harness-changelog.md."""

    model_config = ConfigDict(extra="forbid")

    artifact_path: str
    change_summary: str
    new_domains: list[str] = Field(default_factory=list)
    removed_domains: list[str] = Field(default_factory=list)


class UpdateResponse(HarnessResponse):
    """Response schema for ``harness update`` (/harness:update).

    Emitted after re-scanning the codebase and updating existing harness
    artifacts via three-way merge.
    """

    command: str = "harness update"

    artifacts_diff: list[ArtifactDiff] = Field(default_factory=list)
    new_domains: list[str] = Field(default_factory=list)
    removed_domains: list[str] = Field(default_factory=list)
    changelog_path: str | None = Field(
        default=None,
        description="Path to docs/harness-changelog.md updated by this run.",
    )
    changelog_entries: list[ChangelogEntry] = Field(default_factory=list)
    warnings: list[Violation] = Field(default_factory=list)
