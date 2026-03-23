"""
harness_skills/generators/manifest_generator.py
================================================
Generator that writes ``harness_manifest.json`` and copies the canonical
``harness_manifest.schema.json`` alongside it so downstream tools and agents
can validate manifest fragments independently.

Public API
----------
    generate_manifest(detected_stack, domains, artifacts, **metadata)  ->  dict
    validate_manifest(manifest)  ->  list[tuple[str, str]]
    write_manifest(path, detected_stack, domains, artifacts, **metadata)
    write_manifest_schema(path)
    write_manifest_pair(directory, detected_stack, domains, artifacts, **metadata)
        -> tuple[Path, Path]   (manifest_path, schema_path)

Usage::

    from harness_skills.generators.manifest_generator import write_manifest_pair

    manifest_path, schema_path = write_manifest_pair(
        directory=".",
        detected_stack=create_response.detected_stack,
        domains=create_response.domains_detected,
        artifacts=create_response.artifacts_generated,
        git_sha="a1b2c3d",
    )
"""

from __future__ import annotations

import datetime
import json
import shutil
from pathlib import Path
from typing import Any

# Bundled canonical schema lives next to the other harness schemas
_BUNDLED_SCHEMA: Path = Path(__file__).parent.parent / "schemas" / "harness_manifest.schema.json"

_SCHEMA_VERSION = "1.0"
_MANIFEST_FILENAME = "harness_manifest.json"
_SCHEMA_FILENAME = "harness_manifest.schema.json"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ManifestValidationError(ValueError):
    """Raised when a manifest dict fails JSON Schema validation.

    Attributes
    ----------
    errors:
        Ordered list of ``(jsonpath, message)`` tuples, one per schema
        violation.  The JSONPath uses ``$``-rooted dot-notation with bracket
        indices for arrays (e.g. ``$.artifacts[0].artifact_type``).
    """

    def __init__(self, errors: list[tuple[str, str]]) -> None:
        self.errors: list[tuple[str, str]] = errors
        lines = "\n".join(f"  {jp}  →  {msg}" for jp, msg in errors)
        super().__init__(f"harness_manifest.json failed schema validation:\n{lines}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_manifest(
    detected_stack: Any,
    domains: list[str] | None = None,
    artifacts: list[Any] | None = None,
    *,
    patterns: list[str] | None = None,
    conventions: list[str] | None = None,
    git_sha: str | None = None,
    git_branch: str | None = None,
    harness_version: str | None = None,
    project_root: str | None = None,
    manifest_path: str | None = None,
    schema_path: str | None = None,
    symbols_index_path: str | None = None,
) -> dict[str, Any]:
    """Build and return the manifest dict (not yet written to disk).

    Parameters
    ----------
    detected_stack:
        Either a :class:`~harness_skills.models.create.DetectedStack` Pydantic
        model instance **or** a plain ``dict`` with the same fields.
    domains:
        List of detected subsystem / domain boundary strings.
    artifacts:
        List of :class:`~harness_skills.models.create.GeneratedArtifact`
        instances **or** plain ``dict`` objects with ``artifact_path`` and
        ``artifact_type`` fields.
    patterns:
        List of architectural and design patterns detected in the codebase
        (e.g. ``['plugin-architecture', 'gate-pattern', 'cli-command-pattern']``).
    conventions:
        List of coding conventions and practices detected in the codebase
        (e.g. ``['pep8', 'type-annotations', 'pydantic-models', 'pytest-fixtures']``).
    git_sha:
        Short git SHA at generation time.
    git_branch:
        Active git branch at generation time.
    harness_version:
        Version string of the harness-skills package.
    project_root:
        Absolute path of the project root at generation time.
    manifest_path:
        Repo-relative path where the manifest will be written (recorded
        inside the manifest itself for self-referential discovery).
    schema_path:
        Repo-relative path where the schema will be written.
    symbols_index_path:
        Repo-relative path to ``harness_symbols.json``, if generated.

    Returns
    -------
    dict
        A plain Python dict that is valid against ``harness_manifest.schema.json``.
    """
    # Accept either Pydantic models (with .model_dump()) or raw dicts
    stack_dict = _to_dict(detected_stack)
    artifact_list = [_to_dict(a) for a in (artifacts or [])]

    return {
        "schema_version": _SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "git_sha": git_sha,
        "git_branch": git_branch,
        "harness_version": harness_version,
        "project_root": project_root,
        "detected_stack": stack_dict,
        "domains": list(domains or []),
        "patterns": list(patterns or []),
        "conventions": list(conventions or []),
        "artifacts": artifact_list,
        "manifest_path": manifest_path,
        "schema_path": schema_path,
        "symbols_index_path": symbols_index_path,
    }


def validate_manifest(manifest: dict[str, Any]) -> list[tuple[str, str]]:
    """Validate *manifest* against the bundled ``harness_manifest.schema.json``.

    Returns an ordered list of ``(jsonpath, message)`` tuples — one entry per
    schema violation found.  An **empty** list means the manifest is valid.

    The JSONPath strings use ``$``-rooted dot-notation with bracket indices
    for array positions (e.g. ``$.artifacts[0].artifact_type``), making them
    suitable for direct display in CLI error output.

    Parameters
    ----------
    manifest:
        Plain Python dict to validate (e.g. the return value of
        :func:`generate_manifest`).

    Returns
    -------
    list[tuple[str, str]]
        Possibly-empty list of ``(jsonpath, message)`` tuples.

    Raises
    ------
    FileNotFoundError
        If the bundled schema is missing from the package distribution.
    ImportError
        If the ``jsonschema`` package is not installed.
    """
    try:
        from jsonschema import Draft202012Validator  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "The 'jsonschema' package is required for manifest validation. "
            "Install it with: pip install 'jsonschema>=4.18'"
        ) from exc

    if not _BUNDLED_SCHEMA.exists():
        raise FileNotFoundError(
            f"Bundled harness manifest schema not found at {_BUNDLED_SCHEMA}. "
            "Ensure the harness-skills package is installed correctly."
        )

    schema = json.loads(_BUNDLED_SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    errors: list[tuple[str, str]] = []
    for error in sorted(validator.iter_errors(manifest), key=lambda e: list(e.absolute_path)):
        jp = _jsonpath_from_absolute_path(error.absolute_path)
        errors.append((jp, error.message))
    return errors


def write_manifest(
    path: str | Path,
    detected_stack: Any,
    domains: list[str] | None = None,
    artifacts: list[Any] | None = None,
    **metadata: Any,
) -> Path:
    """Serialise, **validate**, and write ``harness_manifest.json`` to *path*.

    Validation is performed against the bundled JSON Schema **before** any
    bytes are written to disk.  If validation fails a
    :class:`ManifestValidationError` is raised and the file is left untouched.

    All keyword arguments beyond *path*, *detected_stack*, *domains*, and
    *artifacts* are forwarded to :func:`generate_manifest` as *metadata*
    (``git_sha``, ``git_branch``, ``harness_version``, etc.).

    Returns
    -------
    Path
        Resolved path of the written file.

    Raises
    ------
    ManifestValidationError
        If the manifest fails JSON Schema validation.
    """
    path = Path(path)
    manifest = generate_manifest(
        detected_stack=detected_stack,
        domains=domains,
        artifacts=artifacts,
        **metadata,
    )

    # Validate BEFORE touching the file so the on-disk state stays consistent.
    errors = validate_manifest(manifest)
    if errors:
        raise ManifestValidationError(errors)

    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path.resolve()


def write_manifest_schema(path: str | Path) -> Path:
    """Copy the bundled canonical schema to *path*.

    The destination is always overwritten — the schema is not user-editable.

    Returns
    -------
    Path
        Resolved path of the written schema file.

    Raises
    ------
    FileNotFoundError
        If the bundled schema is missing from the package distribution.
    """
    if not _BUNDLED_SCHEMA.exists():
        raise FileNotFoundError(
            f"Bundled harness manifest schema not found at {_BUNDLED_SCHEMA}. "
            "Ensure the harness-skills package is installed correctly."
        )
    dest = Path(path)
    shutil.copy2(_BUNDLED_SCHEMA, dest)
    return dest.resolve()


def write_manifest_pair(
    directory: str | Path,
    detected_stack: Any,
    domains: list[str] | None = None,
    artifacts: list[Any] | None = None,
    *,
    patterns: list[str] | None = None,
    conventions: list[str] | None = None,
    manifest_filename: str = _MANIFEST_FILENAME,
    schema_filename: str = _SCHEMA_FILENAME,
    **metadata: Any,
) -> tuple[Path, Path]:
    """Write ``harness_manifest.json`` **and** ``harness_manifest.schema.json``
    into *directory* as an atomic pair.

    The manifest is validated against the bundled JSON Schema **before** either
    file is written.  If validation fails a :class:`ManifestValidationError` is
    raised and neither file is written.

    If the schema write succeeds but the subsequent manifest write raises an
    unexpected I/O error the schema file may remain on disk (it is idempotent
    and always overwritten on the next call).

    Parameters
    ----------
    directory:
        Target directory (must already exist).
    detected_stack:
        Pydantic ``DetectedStack`` or equivalent dict.
    domains:
        Detected domain/subsystem names.
    artifacts:
        ``GeneratedArtifact`` instances or equivalent dicts.
    patterns:
        Architectural and design patterns detected in the codebase.
    conventions:
        Coding conventions and practices detected in the codebase.
    manifest_filename:
        Override the manifest filename (default ``harness_manifest.json``).
    schema_filename:
        Override the schema filename (default ``harness_manifest.schema.json``).
    **metadata:
        Forwarded to :func:`generate_manifest` (``git_sha``, ``git_branch``,
        ``harness_version``, ``project_root``, ``symbols_index_path``, etc.).

    Returns
    -------
    tuple[Path, Path]
        ``(manifest_path, schema_path)`` — resolved absolute paths of the
        two written files.

    Raises
    ------
    ManifestValidationError
        If the manifest fails JSON Schema validation (no files are written).
    FileNotFoundError
        If the bundled schema is missing or *directory* does not exist.
    NotADirectoryError
        If *directory* exists but is not a directory.
    """
    directory = Path(directory)
    if not directory.exists():
        raise FileNotFoundError(f"Target directory does not exist: {directory}")
    if not directory.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {directory}")

    schema_dest = directory / schema_filename
    manifest_dest = directory / manifest_filename

    # Build the manifest dict and validate BEFORE touching disk so that
    # a schema violation never leaves a half-written pair on disk.
    manifest = generate_manifest(
        detected_stack=detected_stack,
        domains=domains,
        artifacts=artifacts,
        patterns=patterns,
        conventions=conventions,
        manifest_path=manifest_filename,
        schema_path=schema_filename,
        **metadata,
    )
    errors = validate_manifest(manifest)
    if errors:
        raise ManifestValidationError(errors)

    # Write schema first — it is idempotent and always overwritten.
    write_manifest_schema(schema_dest)

    # Write manifest (already validated above; skip re-validation in write_manifest
    # by writing directly rather than calling the public write_manifest helper).
    manifest_dest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return manifest_dest.resolve(), schema_dest.resolve()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _to_dict(obj: Any) -> Any:
    """Convert a Pydantic model to a dict, or pass plain dicts/values through."""
    if obj is None:
        return obj
    if isinstance(obj, dict):
        return obj
    # Pydantic v2
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    # Pydantic v1 / dataclasses
    if hasattr(obj, "dict"):
        return obj.dict()
    return obj


def _utc_now() -> str:
    """Return the current UTC time as an ISO-8601 string with timezone offset."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _jsonpath_from_absolute_path(absolute_path: Any) -> str:
    """Convert a ``jsonschema`` ``absolute_path`` deque into a JSONPath string.

    The returned string uses ``$``-rooted dot-notation with bracket indices
    for array positions:

    * ``deque([])``                          → ``"$"``
    * ``deque(['detected_stack'])``          → ``"$.detected_stack"``
    * ``deque(['artifacts', 0, 'artifact_type'])``
                                             → ``"$.artifacts[0].artifact_type"``
    """
    parts: list[str] = []
    for segment in absolute_path:
        if isinstance(segment, int):
            parts.append(f"[{segment}]")
        else:
            parts.append(f".{segment}")
    return "$" + "".join(parts) if parts else "$"
