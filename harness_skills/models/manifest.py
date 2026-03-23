"""Typed response models for ``harness manifest validate``."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from harness_skills.models.base import HarnessResponse


class ManifestValidationError(BaseModel):
    """A single schema-validation error returned by ``harness manifest validate``."""

    model_config = ConfigDict(extra="forbid")

    jsonpath: str = Field(description="JSONPath location of the violation (e.g. '$.artifacts[0].artifact_type').")
    message: str = Field(min_length=1, description="Human-readable description of the schema violation.")


class ManifestValidateResponse(HarnessResponse):
    """Response schema for ``harness manifest validate``.

    Emitted as JSON or YAML when ``--output-format json|yaml`` is requested.
    The ``valid`` field is the canonical pass/fail signal for agents and CI
    pipelines; ``errors`` provides JSONPath-located details for each violation.

    Example (valid manifest)::

        {
          "command": "harness manifest validate",
          "status": "passed",
          "timestamp": "2026-03-22T10:00:00+00:00",
          "valid": true,
          "path": "harness_manifest.json",
          "error_count": 0,
          "errors": []
        }

    Example (invalid manifest)::

        {
          "command": "harness manifest validate",
          "status": "failed",
          "valid": false,
          "path": "harness_manifest.json",
          "error_count": 2,
          "errors": [
            {"jsonpath": "$.artifacts[0].artifact_type", "message": "'bad_type' is not one of [...]"},
            {"jsonpath": "$.detected_stack", "message": "'project_structure' is a required property"}
          ]
        }
    """

    command: str = "harness manifest validate"

    valid: bool = Field(
        description="True when the manifest passed all schema checks; False otherwise.",
    )
    path: Optional[str] = Field(
        default=None,
        description="Path to the validated manifest file (as passed on the CLI), or null if not applicable.",
    )
    error_count: int = Field(
        ge=0,
        description="Total number of schema violations found (0 = valid manifest).",
    )
    errors: list[ManifestValidationError] = Field(
        default_factory=list,
        description="Schema violations with JSONPath locations and human-readable messages.",
    )
