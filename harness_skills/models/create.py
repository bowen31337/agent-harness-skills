"""Typed response models for ``harness create`` (/harness:create)."""

from __future__ import annotations

from typing import Optional

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
    linter: str | None = None
    documentation_files: list[str] = Field(default_factory=list)


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
    patterns_detected: list[str] = Field(
        description="Architectural and design patterns detected (e.g. ['plugin-architecture', 'gate-pattern']).",
        default_factory=list,
    )
    conventions_detected: list[str] = Field(
        description="Coding conventions detected (e.g. ['pep8', 'type-annotations', 'pydantic-models']).",
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


class CreateConfigResponse(HarnessResponse):
    """Response schema for the ``harness create`` config-generator CLI command.

    This is the lightweight response for the YAML config-file writer
    (``harness.config.yaml``).  For the full harness initialisation response
    (AGENTS.md, ARCHITECTURE.md, schemas, etc.) see :class:`CreateResponse`.

    Example (new file)::

        {
          "command": "harness create",
          "status": "passed",
          "timestamp": "2026-03-22T10:00:00+00:00",
          "action": "created",
          "path": "harness.config.yaml",
          "profile": "standard",
          "stack": "python"
        }

    Example (merged into existing file)::

        {
          "command": "harness create",
          "status": "passed",
          "action": "updated",
          "path": "harness.config.yaml",
          "profile": "advanced",
          "stack": null
        }
    """

    command: str = "harness create"

    action: str = Field(
        description=(
            "'created' when a new harness.config.yaml was written from scratch; "
            "'updated' when the gates block was merged into an existing file."
        ),
    )
    path: str = Field(
        description="Destination path of the written or updated harness.config.yaml.",
    )
    profile: str = Field(
        description="Complexity profile used to generate gate defaults (starter | standard | advanced).",
    )
    stack: Optional[str] = Field(
        default=None,
        description="Stack hint used for generation (None = auto-detected from project files).",
    )
