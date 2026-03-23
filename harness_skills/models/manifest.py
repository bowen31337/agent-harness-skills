"""Typed response model for ``harness manifest validate``.

All structured JSON output emitted by ``harness manifest validate --json`` is
constructed from and validated against :class:`ManifestValidateResponse` before
being written to stdout.  This guarantees the output schema is always consistent
and machine-parseable by downstream agents.

Schema contract
---------------
+---------------+--------+-----------------------------------------------------+
| Field         | Type   | Meaning                                             |
+===============+========+=====================================================+
| command       | str    | Always ``"harness manifest validate"``              |
| status        | str    | ``"passed"`` | ``"failed"``                        |
| valid         | bool   | True when all schema checks pass                    |
| path          | str?   | Path to the manifest file that was validated        |
| error_count   | int    | Number of schema violations (0 on success)          |
| errors        | list   | ``{jsonpath, message}`` items — empty on success    |
+---------------+--------+-----------------------------------------------------+

Example — valid manifest::

    {
      "command": "harness manifest validate",
      "status": "passed",
      "valid": true,
      "path": "harness_manifest.json",
      "error_count": 0,
      "errors": []
    }

Example — manifest with violations::

    {
      "command": "harness manifest validate",
      "status": "failed",
      "valid": false,
      "path": "harness_manifest.json",
      "error_count": 2,
      "errors": [
        {"jsonpath": "$.detected_stack", "message": "'project_structure' is a required property"},
        {"jsonpath": "$.schema_version",  "message": "'9.9' is not one of ['1.0']"}
      ]
    }
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from harness_skills.models.base import HarnessResponse, Status


# ---------------------------------------------------------------------------
# Supporting model — one error entry
# ---------------------------------------------------------------------------


class ManifestValidationError(BaseModel):
    """A single schema validation error from ``harness manifest validate``.

    Each entry in :attr:`ManifestValidateResponse.errors` is validated against
    this model before emission, ensuring the error list always has a consistent
    shape that agent code can rely on.
    """

    model_config = ConfigDict(extra="forbid")

    jsonpath: str = Field(
        description=(
            "JSONPath location of the schema violation, "
            "e.g. '$.detected_stack' or '$.artifacts[1].artifact_type'. "
            "Always starts with '$'."
        )
    )
    message: str = Field(
        min_length=1,
        description="Human-readable description of the schema violation.",
    )


# ---------------------------------------------------------------------------
# Top-level response
# ---------------------------------------------------------------------------


class ManifestValidateResponse(HarnessResponse):
    """Response schema emitted by ``harness manifest validate --json``.

    Inherits the standard ``HarnessResponse`` envelope (``command``,
    ``status``, ``timestamp``, ``duration_ms``, ``version``, ``message``) and
    adds manifest-specific fields.

    Machine-parseable fields for agent consumers
    --------------------------------------------
    - ``valid``        — top-level pass/fail boolean
    - ``error_count``  — number of violations (0 = success)
    - ``errors``       — per-violation details with JSONPath locations
    - ``path``         — path of the manifest that was checked

    The output is always produced via ``model_dump_json()`` so it is guaranteed
    to pass Pydantic validation before reaching stdout.
    """

    command: str = "harness manifest validate"

    valid: bool = Field(
        description="True when the manifest passes all schema checks; False otherwise."
    )
    path: Optional[str] = Field(
        default=None,
        description="Path to the ``harness_manifest.json`` file that was validated.",
    )
    error_count: int = Field(
        ge=0,
        default=0,
        description="Number of schema violations found. 0 when valid=True.",
    )
    errors: list[ManifestValidationError] = Field(
        default_factory=list,
        description=(
            "Detailed list of schema violations with JSONPath locations. "
            "Empty when valid=True. "
            "len(errors) == error_count is always guaranteed."
        ),
    )
