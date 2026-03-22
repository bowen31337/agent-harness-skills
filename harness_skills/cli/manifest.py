"""harness manifest — inspect and validate ``harness_manifest.json`` files.

Usage (CLI)::

    # Validate manifest in current directory (default path)
    harness manifest validate

    # Validate a specific file
    harness manifest validate path/to/harness_manifest.json

    # Machine-readable JSON report (suitable for CI / agent consumption)
    harness manifest validate --output-format json

    # YAML report
    harness manifest validate --output-format yaml

Exit codes::

    0   Manifest is valid against ``harness_manifest.schema.json``.
    1   Manifest has one or more schema violations (errors printed to stderr).
    2   File not found or the file contains invalid JSON.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click
import yaml

from harness_skills.cli.fmt import output_format_option, resolve_output_format
from harness_skills.cli.verbosity import VerbosityLevel, get_verbosity, vecho
from harness_skills.models.base import Status
from harness_skills.models.manifest import ManifestValidateResponse, ManifestValidationError


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
@output_format_option(
    help_extra=(
        "json: machine-readable ManifestValidateResponse with JSONPath error locations.  "
        "yaml: same report as YAML.  "
        "table: human-readable text with checkmarks/crosses."
    ),
)
@click.option(
    "--json",
    "output_json_flag",
    is_flag=True,
    default=False,
    hidden=True,
    help="[Deprecated] Use --output-format json instead.",
)
@click.pass_context
def validate_cmd(
    ctx: click.Context,
    path: Path,
    output_format: Optional[str],
    output_json_flag: bool,
) -> None:
    """Validate PATH against ``harness_manifest.schema.json``.

    PATH defaults to ``harness_manifest.json`` in the current directory.

    \b
    Validation errors are printed with JSONPath locations:

        $.artifacts[0].artifact_type  →  'bad_type' is not one of [...]
        $.detected_stack              →  'project_structure' is a required property

    \b
    Examples:
        harness manifest validate
        harness manifest validate .harness/harness_manifest.json
        harness manifest validate --output-format json | jq '.errors'
        harness manifest validate --output-format yaml
    """
    verbosity = get_verbosity(ctx)

    # --json flag is a deprecated alias for --output-format json
    if output_json_flag and output_format is None:
        output_format = "json"

    fmt = resolve_output_format(output_format)

    # ------------------------------------------------------------------
    # 1. Read the file
    # ------------------------------------------------------------------
    vecho(f"  Validating: {path}", verbosity=verbosity, min_level=VerbosityLevel.verbose)

    if not path.exists():
        error_msg = f"harness manifest validate: file not found: {path}"
        _emit_error(fmt=fmt, error=error_msg, path=path, verbosity=verbosity)
        ctx.exit(2)
        return

    try:
        raw = path.read_text(encoding="utf-8")
        data: dict = json.loads(raw)
    except json.JSONDecodeError as exc:
        error_msg = f"harness manifest validate: invalid JSON in {path}: {exc}"
        _emit_error(fmt=fmt, error=error_msg, path=path, verbosity=verbosity)
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
        _emit_error(fmt=fmt, error=str(exc), path=path, verbosity=verbosity)
        ctx.exit(1)
        return

    # ------------------------------------------------------------------
    # 3. Validate
    # ------------------------------------------------------------------
    errors = validate_manifest(data)

    vecho(
        f"  Found {len(errors)} error(s) in {path}",
        verbosity=verbosity,
        min_level=VerbosityLevel.verbose,
    )

    if fmt in ("json", "yaml"):
        response = ManifestValidateResponse(
            status=Status.PASSED if not errors else Status.FAILED,
            timestamp=datetime.now(timezone.utc).isoformat(),
            valid=len(errors) == 0,
            path=str(path),
            error_count=len(errors),
            errors=[
                ManifestValidationError(jsonpath=jp, message=msg)
                for jp, msg in errors
            ],
        )
        if fmt == "json":
            click.echo(response.model_dump_json(indent=2))
        else:
            data_out = json.loads(response.model_dump_json())
            click.echo(
                yaml.dump(
                    data_out,
                    default_flow_style=False,
                    sort_keys=False,
                    allow_unicode=True,
                ),
                nl=False,
            )
        if errors:
            ctx.exit(1)
        return

    # Human-readable table output
    if not errors:
        vecho(
            f"✓  {path}  is valid against harness_manifest.schema.json",
            verbosity=verbosity,
        )
        return

    # Validation errors always shown — they explain a non-zero exit code.
    vecho(
        f"✗  {path}  failed schema validation — {len(errors)} error(s):",
        verbosity=verbosity,
        min_level=VerbosityLevel.quiet,
        err=True,
    )
    for jsonpath, message in errors:
        vecho(
            f"  {jsonpath}  →  {message}",
            verbosity=verbosity,
            min_level=VerbosityLevel.quiet,
            err=True,
        )
    ctx.exit(1)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _emit_error(
    *,
    fmt: str,
    error: str,
    path: Optional[Path] = None,
    verbosity: str = VerbosityLevel.normal,
) -> None:
    """Emit a fatal error as a schema-validated ManifestValidateResponse or plain text."""
    if fmt in ("json", "yaml"):
        response = ManifestValidateResponse(
            status=Status.FAILED,
            timestamp=datetime.now(timezone.utc).isoformat(),
            valid=False,
            path=str(path) if path is not None else "",
            error_count=1,
            errors=[ManifestValidationError(jsonpath="$", message=error)],
        )
        if fmt == "json":
            click.echo(response.model_dump_json(indent=2))
        else:
            data_out = json.loads(response.model_dump_json())
            click.echo(
                yaml.dump(
                    data_out,
                    default_flow_style=False,
                    sort_keys=False,
                    allow_unicode=True,
                ),
                nl=False,
            )
    else:
        vecho(error, verbosity=verbosity, min_level=VerbosityLevel.quiet, err=True)
