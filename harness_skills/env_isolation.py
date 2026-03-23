"""
harness_skills/env_isolation.py
================================
Generates environment isolation configuration artefacts for per-worktree
agent isolation.

Unlike ``boot.py`` — which *launches* a running process — this module produces
*configuration documents* that describe how a worktree should be isolated
before any process is started.  The outputs (dotenv files, docker-compose
overrides, shell export blocks) can be written to disk, committed alongside the
worktree, or fed directly into a CI/CD pipeline.

Public API
----------
    generate_dotenv(spec)                  -> str   (.env file content)
    generate_docker_compose_override(spec) -> str   (docker-compose YAML fragment)
    generate_shell_exports(spec)           -> str   (bash export block)
    generate_env_config(spec, fmt)         -> str   (dispatch by OutputFormat)
    assign_port(worktree_id, taken, base)  -> int   (collision-free port assignment)
    schema_name(worktree_id)               -> str   (safe PostgreSQL identifier)
    container_name(worktree_id)            -> str   (safe Docker container name)

Data models
-----------
    OutputFormat        — dotenv | docker-compose | shell
    DbIsolation         — none | schema | file | container
    EnvIsolationSpec    — full isolation specification for one worktree
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class OutputFormat(str, Enum):
    """Supported output formats for the generated isolation configuration."""

    DOTENV = "dotenv"
    DOCKER_COMPOSE = "docker-compose"
    SHELL = "shell"


class DbIsolation(str, Enum):
    """Database isolation strategy.

    Mirrors :class:`harness_skills.boot.DatabaseIsolation` so that callers
    that only need config generation do not have to import the boot module.
    """

    NONE = "none"           # No database isolation — share a single DB
    SCHEMA = "schema"       # Separate PostgreSQL schema per worktree
    FILE = "file"           # Separate SQLite file per worktree
    CONTAINER = "container" # Separate container (DB URL injected externally)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class EnvIsolationSpec:
    """
    Full isolation specification for a single agent worktree.

    Attributes
    ----------
    worktree_id:
        Short identifier for this agent's worktree (e.g. a task-UUID prefix or
        branch slug).  Used to derive schema names, file paths, and container
        names.
    port:
        TCP port the isolated instance should bind to.
    db_isolation:
        Database isolation strategy.
    db_schema:
        PostgreSQL schema name.  When empty and ``db_isolation=SCHEMA``, the
        value is derived from *worktree_id* via :func:`schema_name`.
    db_file:
        SQLite file path.  When empty and ``db_isolation=FILE``, the path is
        derived from *worktree_id* as ``/tmp/harness_<worktree_id>.db``.
    container_suffix:
        Suffix appended to the Docker service/container name when
        ``db_isolation=CONTAINER``.  When empty, *worktree_id* is used.
    extra_vars:
        Additional ``KEY=value`` pairs to include in every generated output.
    """

    worktree_id: str
    port: int = 8000
    db_isolation: DbIsolation = DbIsolation.NONE
    db_schema: str = ""
    db_file: str = ""
    container_suffix: str = ""
    extra_vars: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

# Maximum length of a PostgreSQL identifier is 63 bytes (NAMEDATALEN - 1).
_PG_MAX_IDENT_LEN = 63
# Docker resource names must match [a-zA-Z0-9][a-zA-Z0-9_.-]* (up to 255 chars).
_DOCKER_MAX_NAME_LEN = 63


def _slugify(value: str) -> str:
    """
    Convert *value* to a lowercase alphanumeric-plus-hyphen slug suitable for
    use in identifiers.  Non-alphanumeric characters are replaced with
    underscores.
    """
    slug = re.sub(r"[^a-z0-9]", "_", value.lower())
    # Collapse consecutive underscores
    slug = re.sub(r"_+", "_", slug)
    return slug.strip("_")


def schema_name(worktree_id: str) -> str:
    """
    Derive a safe PostgreSQL schema name from *worktree_id*.

    The result:
    - starts with ``worktree_``
    - contains only lowercase letters, digits, and underscores
    - is at most :data:`_PG_MAX_IDENT_LEN` characters long
    - never ends with an underscore

    Parameters
    ----------
    worktree_id:
        Raw worktree identifier (may contain hyphens, slashes, etc.).

    Returns
    -------
    str
        A valid PostgreSQL identifier for use as a schema name.
    """
    slug = _slugify(worktree_id)
    name = f"worktree_{slug}"
    # Trim to the PostgreSQL identifier limit and strip trailing underscores.
    return name[:_PG_MAX_IDENT_LEN].rstrip("_")


def container_name(worktree_id: str, suffix: str = "") -> str:
    """
    Derive a safe Docker container / service name from *worktree_id*.

    The result:
    - starts with ``harness_``
    - contains only lowercase letters, digits, and underscores
    - is at most :data:`_DOCKER_MAX_NAME_LEN` characters long

    Parameters
    ----------
    worktree_id:
        Raw worktree identifier.
    suffix:
        Optional suffix to append (after a ``_``); useful for distinguishing
        multiple services within the same worktree (e.g. ``_db``, ``_redis``).

    Returns
    -------
    str
        A valid Docker resource name.
    """
    slug = _slugify(worktree_id)
    if suffix:
        suf = _slugify(suffix)
        name = f"harness_{slug}_{suf}"
    else:
        name = f"harness_{slug}"
    return name[:_DOCKER_MAX_NAME_LEN].rstrip("_")


def assign_port(
    worktree_id: str,
    taken: Optional[list[int]] = None,
    base: int = 8000,
    max_search: int = 200,
) -> int:
    """
    Return a port number for *worktree_id* that does not appear in *taken*.

    Scans ``[base, base + max_search)`` in order and returns the first port
    not present in *taken*.  The *worktree_id* is used to produce a
    deterministic starting offset within the range so that different worktrees
    tend to receive different ports even when called in isolation (without a
    registry).

    Parameters
    ----------
    worktree_id:
        Worktree identifier — used to compute a deterministic offset.
    taken:
        Ports already claimed by other worktrees.  Defaults to an empty list.
    base:
        Lowest port to consider.
    max_search:
        Number of candidate ports to scan before raising :class:`RuntimeError`.

    Returns
    -------
    int
        An available port.

    Raises
    ------
    RuntimeError
        When all ``max_search`` candidates are exhausted.
    """
    taken_set: set[int] = set(taken or [])
    # Compute a deterministic offset from the worktree_id hash so that
    # concurrent worktrees naturally spread across the range.
    offset = abs(hash(worktree_id)) % max_search
    for delta in range(max_search):
        candidate = base + (offset + delta) % max_search
        if candidate not in taken_set:
            return candidate
    raise RuntimeError(
        f"No free port found in [{base}, {base + max_search}) "
        f"for worktree_id={worktree_id!r}"
    )


# ---------------------------------------------------------------------------
# Resolved isolation values
# ---------------------------------------------------------------------------


def _resolved_schema(spec: EnvIsolationSpec) -> str:
    return spec.db_schema or schema_name(spec.worktree_id)


def _resolved_db_file(spec: EnvIsolationSpec) -> str:
    return spec.db_file or f"/tmp/harness_{spec.worktree_id}.db"


def _resolved_container_suffix(spec: EnvIsolationSpec) -> str:
    return spec.container_suffix or spec.worktree_id


# ---------------------------------------------------------------------------
# Dotenv generation
# ---------------------------------------------------------------------------

_DOTENV_HEADER = """\
# -----------------------------------------------------------------------
# harness env-isolation — worktree: {worktree_id}
# Generated by harness_skills.env_isolation
# -----------------------------------------------------------------------
"""


def generate_dotenv(spec: EnvIsolationSpec) -> str:
    """
    Generate a ``.env`` file containing the isolation variables for *spec*.

    The file includes:

    - A header comment identifying the worktree.
    - ``PORT`` set to :attr:`EnvIsolationSpec.port`.
    - Database isolation variables appropriate for the chosen strategy.
    - Any :attr:`EnvIsolationSpec.extra_vars`.

    Parameters
    ----------
    spec:
        Isolation specification for the target worktree.

    Returns
    -------
    str
        Content of the generated ``.env`` file, ready to write to disk or pass
        to ``env $(cat .env) some-command``.
    """
    lines: list[str] = [_DOTENV_HEADER.format(worktree_id=spec.worktree_id)]

    lines.append(f"PORT={spec.port}")

    if spec.db_isolation == DbIsolation.SCHEMA:
        lines.append(f"DB_SCHEMA={_resolved_schema(spec)}")
    elif spec.db_isolation == DbIsolation.FILE:
        db_file = _resolved_db_file(spec)
        lines.append(f"DATABASE_URL=sqlite:///{db_file}")
    elif spec.db_isolation == DbIsolation.CONTAINER:
        cname = container_name(spec.worktree_id, _resolved_container_suffix(spec))
        lines.append(f"DB_CONTAINER={cname}")
        lines.append(
            "# DATABASE_URL should be provided by the container orchestrator"
        )
    # else: DbIsolation.NONE — no extra DB vars

    for key, value in spec.extra_vars.items():
        lines.append(f"{key}={value}")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Docker-compose override generation
# ---------------------------------------------------------------------------

_DC_HEADER = """\
# -----------------------------------------------------------------------
# harness env-isolation — docker-compose override for worktree: {worktree_id}
# Generated by harness_skills.env_isolation
# Merge with your base docker-compose.yml:
#   docker compose -f docker-compose.yml -f {filename} up
# -----------------------------------------------------------------------
"""


def generate_docker_compose_override(spec: EnvIsolationSpec) -> str:
    """
    Generate a docker-compose service-override YAML fragment for *spec*.

    The fragment defines a ``services`` entry named after the worktree with:

    - Port mapping ``<port>:<port>``.
    - Database isolation environment variables inside ``environment:``.
    - ``DB_CONTAINER`` service entry when ``db_isolation=CONTAINER``.

    Parameters
    ----------
    spec:
        Isolation specification for the target worktree.

    Returns
    -------
    str
        Content of the docker-compose override YAML file.  Merge it with the
        project's base ``docker-compose.yml`` using
        ``docker compose -f docker-compose.yml -f <this file> up``.
    """
    svc = container_name(spec.worktree_id)
    filename = f"docker-compose.{spec.worktree_id}.yml"

    env_block_lines: list[str] = [
        f"      PORT: \"{spec.port}\"",
    ]

    db_service_block = ""

    if spec.db_isolation == DbIsolation.SCHEMA:
        env_block_lines.append(
            f"      DB_SCHEMA: \"{_resolved_schema(spec)}\""
        )
    elif spec.db_isolation == DbIsolation.FILE:
        db_file = _resolved_db_file(spec)
        env_block_lines.append(
            f"      DATABASE_URL: \"sqlite:///{db_file}\""
        )
    elif spec.db_isolation == DbIsolation.CONTAINER:
        db_svc = container_name(spec.worktree_id, "db")
        env_block_lines.append(
            f"      DB_CONTAINER: \"{db_svc}\""
        )
        db_service_block = textwrap.dedent(
            f"""
              {db_svc}:
                image: postgres:16
                environment:
                  POSTGRES_DB: "worktree_{_slugify(spec.worktree_id)}"
                  POSTGRES_USER: "harness"
                  POSTGRES_PASSWORD: "harness"
            """
        )

    for key, value in spec.extra_vars.items():
        env_block_lines.append(f"      {key}: \"{value}\"")

    env_block = "\n".join(env_block_lines)

    content = _DC_HEADER.format(worktree_id=spec.worktree_id, filename=filename)
    content += textwrap.dedent(f"""\
        version: "3.9"
        services:
          {svc}:
            ports:
              - "{spec.port}:{spec.port}"
            environment:
        {env_block}
        """)

    if db_service_block:
        content += db_service_block.lstrip("\n")

    return content


# ---------------------------------------------------------------------------
# Shell export generation
# ---------------------------------------------------------------------------

_SHELL_HEADER = """\
#!/usr/bin/env bash
# -----------------------------------------------------------------------
# harness env-isolation — shell exports for worktree: {worktree_id}
# Generated by harness_skills.env_isolation
# Source this file: source .harness_env_{worktree_id}.sh
# -----------------------------------------------------------------------
"""


def generate_shell_exports(spec: EnvIsolationSpec) -> str:
    """
    Generate a bash script of ``export`` statements for *spec*.

    The script can be sourced into a shell session or a CI job to configure
    the isolation variables before launching the application:

    .. code-block:: bash

        source .harness_env_<worktree_id>.sh
        uvicorn myapp.main:app

    Parameters
    ----------
    spec:
        Isolation specification for the target worktree.

    Returns
    -------
    str
        Content of the generated bash export script.
    """
    lines: list[str] = [_SHELL_HEADER.format(worktree_id=spec.worktree_id)]

    lines.append(f'export PORT="{spec.port}"')

    if spec.db_isolation == DbIsolation.SCHEMA:
        lines.append(f'export DB_SCHEMA="{_resolved_schema(spec)}"')
    elif spec.db_isolation == DbIsolation.FILE:
        db_file = _resolved_db_file(spec)
        lines.append(f'export DATABASE_URL="sqlite:///{db_file}"')
    elif spec.db_isolation == DbIsolation.CONTAINER:
        cname = container_name(spec.worktree_id, _resolved_container_suffix(spec))
        lines.append(f'export DB_CONTAINER="{cname}"')
        lines.append(
            "# DATABASE_URL should be injected by the container orchestrator"
        )

    for key, value in spec.extra_vars.items():
        lines.append(f'export {key}="{value}"')

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def generate_env_config(spec: EnvIsolationSpec, fmt: OutputFormat) -> str:
    """
    Generate isolation configuration in the requested *fmt* for *spec*.

    This is the primary dispatch function.  Prefer calling it over the
    format-specific helpers directly so that callers remain format-agnostic.

    Parameters
    ----------
    spec:
        Isolation specification for the target worktree.
    fmt:
        Desired output format.

    Returns
    -------
    str
        Generated configuration content.

    Raises
    ------
    ValueError
        When *fmt* is not a recognised :class:`OutputFormat` member.
    """
    if fmt == OutputFormat.DOTENV:
        return generate_dotenv(spec)
    if fmt == OutputFormat.DOCKER_COMPOSE:
        return generate_docker_compose_override(spec)
    if fmt == OutputFormat.SHELL:
        return generate_shell_exports(spec)
    raise ValueError(f"Unknown output format: {fmt!r}")
