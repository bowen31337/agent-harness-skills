"""harness manifest — inspect and validate ``harness_manifest.json`` files.

Usage (CLI)::

    # Validate manifest in current directory (default path)
    harness manifest validate

    # Validate a specific file
    harness manifest validate path/to/harness_manifest.json

    # Machine-readable JSON report (suitable for CI / agent consumption)
    harness manifest validate --json

Exit codes::

    0   Manifest is valid against ``harness_manifest.schema.json``.
    1   Manifest has one or more schema violations (errors printed to stderr).
    2   File not found or the file contains invalid JSON.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import click

from harness_skills.models.base import Status
from harness_skills.models.manifest import ManifestValidationError, ManifestValidateResponse


# ---------------------------------------------------------------------------
# ``harness manifest`` group
# ---------------------------------------------------------------------------


@click.group("manifest")
def manifest_cmd() -> None:
    """Inspect and validate ``harness_manifest.json`` files.

    \b
    Subcommands:
        validate   Validate a manifest against harness_manifest.schema.json
    """


# ---------------------------------------------------------------------------
# ``harness manifest validate``
# ---------------------------------------------------------------------------


@manifest_cmd.command("validate")
@click.argument(
    "path",
    default="harness_manifest.json",
    metavar="PATH",
    type=click.Path(exists=False, dir_okay=False, path_type=Path),
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    default=False,
    help=(
        "Emit a machine-readable JSON report to stdout instead of "
        "human-readable text.  Output is schema-validated against "
        "ManifestValidateResponse before emission.  Errors still set exit code 1."
    ),
)
@click.pass_context
def validate_cmd(
    ctx: click.Context,
    path: Path,
    output_json: bool,
) -> None:
    """Validate PATH against ``harness_manifest.schema.json``.

    PATH defaults to ``harness_manifest.json`` in the current directory.

    \b
    Validation errors are printed to stderr with JSONPath locations:

        $.artifacts[0].artifact_type  →  'bad_type' is not one of [...]
        $.detected_stack              →  'project_structure' is a required property

    \b
    Examples:
        harness manifest validate
        harness manifest validate .harness/harness_manifest.json
        harness manifest validate --json | jq '.errors'
    """
    # ------------------------------------------------------------------
    # 1. Read the file
    # ------------------------------------------------------------------
    if not path.exists():
        _emit_error(
            output_json=output_json,
            error=f"harness manifest validate: file not found: {path}",
            path=path,
        )
        ctx.exit(2)
        return

    try:
        raw = path.read_text(encoding="utf-8")
        data: dict = json.loads(raw)
    except json.JSONDecodeError as exc:
        _emit_error(
            output_json=output_json,
            error=f"harness manifest validate: invalid JSON in {path}: {exc}",
            path=path,
        )
        ctx.exit(2)
        return

    # ------------------------------------------------------------------
    # 2. Import validator (fail gracefully when jsonschema is missing)
    # ------------------------------------------------------------------
    try:
        from harness_skills.generators.manifest_generator import (  # noqa: PLC0415
            validate_manifest,
        )
    except ImportError as exc:
        _emit_error(output_json=output_json, error=str(exc), path=path)
        ctx.exit(1)
        return

    # ------------------------------------------------------------------
    # 3. Validate
    # ------------------------------------------------------------------
    errors = validate_manifest(data)

    if output_json:
        response = ManifestValidateResponse(
            status=Status.PASSED if not errors else Status.FAILED,
            valid=len(errors) == 0,
            path=str(path),
            error_count=len(errors),
            errors=[
                ManifestValidationError(jsonpath=jp, message=msg)
                for jp, msg in errors
            ],
        )
        click.echo(response.model_dump_json(indent=2))
        if errors:
            ctx.exit(1)
        return

    # Human-readable output
    if not errors:
        click.echo(f"✓  {path}  is valid against harness_manifest.schema.json")
        return

    click.echo(
        f"✗  {path}  failed schema validation — {len(errors)} error(s):",
        err=True,
    )
    for jsonpath, message in errors:
        click.echo(f"  {jsonpath}  →  {message}", err=True)
    ctx.exit(1)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _emit_error(
    *,
    output_json: bool,
    error: str,
    path: Optional[Path] = None,
) -> None:
    """Emit a fatal error in either JSON or human-readable format.

    When *output_json* is ``True`` the error is wrapped in a
    :class:`ManifestValidateResponse` and emitted via ``model_dump_json()``
    so the output is always schema-validated before reaching stdout.
    """
    if output_json:
        response = ManifestValidateResponse(
            status=Status.FAILED,
            valid=False,
            path=str(path) if path is not None else None,
            error_count=1,
            errors=[ManifestValidationError(jsonpath="$", message=error)],
            message=error,
        )
        click.echo(response.model_dump_json(indent=2))
    else:
        click.echo(error, err=True)
