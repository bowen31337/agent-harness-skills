"""Typed response model for ``harness context`` (/harness:context).

Schema: harness_skills.models.context.ContextManifest

Consumers iterate ``files`` in order, loading only as many as their token
budget allows, and apply ``patterns`` with Grep to extract targeted sections
rather than reading entire files.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from harness_skills.models.base import HarnessResponse


class ContextManifestFile(BaseModel):
    """A single ranked file entry in the ContextManifest."""

    path: str
    score: int = Field(ge=0, default=0)
    estimated_lines: int = Field(ge=0, default=0)
    sources: list[str] = Field(default_factory=list)
    rationale: str = ""


class SearchPattern(BaseModel):
    """A targeted grep/ripgrep pattern for extracting relevant sections."""

    label: str
    pattern: str
    flags: str = "-i"
    rationale: str = ""


class SkipEntry(BaseModel):
    """A candidate file that was excluded from the manifest."""

    path: str
    reason: str = ""


class ContextStats(BaseModel):
    """Aggregate statistics for a ContextManifest run."""

    total_candidate_files: int = Field(ge=0, default=0)
    returned_files: int = Field(ge=0, default=0)
    total_estimated_lines: int = Field(ge=0, default=0)
    state_service_used: bool = False


class ContextManifest(HarnessResponse):
    """Response schema for ``harness context`` (/harness:context).

    An ordered list of ranked file paths and search patterns covering the
    scope of a given plan ID or domain — without loading any file contents
    into the context window.

    Agents should:
    1. Iterate ``files`` in score order.
    2. Load only as many files as their token budget allows.
    3. Apply ``patterns`` with Grep/ripgrep to extract targeted sections from
       the remaining candidates rather than reading full file contents.
    """

    command: str = "harness context"
    input: str = Field(default="", description="Original plan ID or domain argument.")
    keywords: list[str] = Field(
        default_factory=list,
        description="Extracted keywords used to drive file discovery.",
    )
    files: list[ContextManifestFile] = Field(
        default_factory=list,
        description="Ranked list of relevant file paths.",
    )
    patterns: list[SearchPattern] = Field(
        default_factory=list,
        description="Targeted search patterns keyed by keyword.",
    )
    skip_list: list[SkipEntry] = Field(
        default_factory=list,
        description="Candidates excluded by the built-in or user-supplied skip rules.",
    )
    stats: ContextStats = Field(default_factory=ContextStats)
