"""Typed response model for ``harness create`` (/harness:create)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from harness_skills.models.base import HarnessResponse, Violation


class DetectedStack(BaseModel):
    """Summary of the technology stack detected by the scanner."""

    model_config = ConfigDict(extra="forbid")

    primary_language: str
    secondary_languages: list[str] = Field(default_factory=list)
    framework: str | None = None
    project_structure: str = Field(
        description="monorepo | polyrepo | single-app"
    )
    test_framework: str | None = None
    ci_platform: str | None = None
    database: str | None = None
    api_style: str | None = None


class GeneratedArtifact(BaseModel):
    """A single artifact generated during ``harness create``."""

    model_config = ConfigDict(extra="forbid")

    artifact_path: str = Field(description="Repo-relative path of the generated file.")
    artifact_type: str = Field(
        description="Category: AGENTS.md | ARCHITECTURE.md | PRINCIPLES.md | "
        "EVALUATION.md | harness.config.yaml | schema | ci_pipeline | other"
    )
    token_count: int | None = Field(default=None, ge=0)
    overwritten: bool = Field(
        default=False,
        description="True if a prior version was replaced.",
    )


class CreateResponse(HarnessResponse):
    """Response schema for ``harness create``.

    Emitted after full harness generation from codebase analysis through
    all artifact output.
    """

    command: str = "harness create"

    detected_stack: DetectedStack
    domains_detected: list[str] = Field(
        description="Detected subsystem/domain boundaries (e.g. ['auth', 'billing']).",
        default_factory=list,
    )
    artifacts_generated: list[GeneratedArtifact] = Field(default_factory=list)
    manifest_path: str | None = Field(
        default=None,
        description="Path to the generated harness_manifest.json.",
    )
    schema_path: str | None = Field(
        default=None,
        description="Path to the generated harness_manifest.schema.json.",
    )
    symbols_index_path: str | None = Field(
        default=None,
        description="Path to the generated harness_symbols.json.",
    )
    warnings: list[Violation] = Field(
        default_factory=list,
        description="Non-fatal warnings emitted during generation.",
    )
