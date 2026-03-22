"""harness boot — launch an isolated application instance for an agent task.

Usage (CLI):
    harness boot --worktree-id ID --command CMD [options]
    harness boot --worktree-id ID --command CMD --generate-script
    harness boot --worktree-id ID --command CMD --dry-run

Assigns a dedicated port, sets up optional database isolation (PostgreSQL
schema, SQLite file, or container), and blocks until the health endpoint
returns HTTP 2xx.  Each worktree gets a fully isolated instance so concurrent
agents never share state.

Exit codes:
    0   Instance ready (--launch) or script written (--generate-script).
    1   Boot failed, validation error, or launch error.
"""

from __future__ import annotations

import os
import sys
from typing import Optional

import click

_DB_ISOLATION_CHOICE = click.Choice(
    ["none", "schema", "file", "container"], case_sensitive=False
)
_HEALTH_METHOD_CHOICE = click.Choice(["GET", "HEAD"], case_sensitive=False)


def _get_boot_api():
    """Lazy import of harness_skills.boot to avoid load-time failures."""
    from harness_skills.boot import (  # noqa: PLC0415
        BootConfig,
        DatabaseIsolation,
        HealthCheckMethod,
        IsolationConfig,
        boot_instance,
        generate_boot_script,
    )

    return (
        BootConfig,
        DatabaseIsolation,
        HealthCheckMethod,
        IsolationConfig,
        boot_instance,
        generate_boot_script,
    )


def _parse_env_pairs(env_list: tuple[str, ...]) -> dict[str, str]:
    """Parse a sequence of ``KEY=VALUE`` strings into a dict.

    Raises :class:`click.BadParameter` if any entry lacks an ``=`` sign.
    """
    result: dict[str, str] = {}
    for entry in env_list:
        if "=" not in entry:
            raise click.BadParameter(
                f"{entry!r} — expected KEY=VALUE format", param_hint="'--env'"
            )
        key, _, value = entry.partition("=")
        result[key] = value
    return result


@click.command("boot")
@click.option(
    "--worktree-id",
    required=True,
    metavar="ID",
    help=(
        "Short identifier for this agent worktree (task-UUID prefix or branch slug).  "
        "Used in log prefixes, schema names, and file paths."
    ),
)
@click.option(
    "--command",
    "start_command",
    required=True,
    metavar="CMD",
    help=(
        "Shell command to launch the application "
        "(e.g. 'uvicorn myapp.main:app --port 8001')."
    ),
)
@click.option(
    "--port",
    default=8000,
    show_default=True,
    type=click.IntRange(1024, 65535),
    help="TCP port the isolated instance should bind to.",
)
@click.option(
    "--health-path",
    default="/health",
    show_default=True,
    help="URL path of the health check endpoint.",
)
@click.option(
    "--health-method",
    type=_HEALTH_METHOD_CHOICE,
    default="GET",
    show_default=True,
    help="HTTP method used to probe the health endpoint.",
)
@click.option(
    "--health-timeout",
    default=30.0,
    show_default=True,
    type=float,
    metavar="SECS",
    help="Max seconds to wait for the health check before declaring boot failed.",
)
@click.option(
    "--health-interval",
    default=1.0,
    show_default=True,
    type=float,
    metavar="SECS",
    help="Seconds between consecutive health probe attempts.",
)
@click.option(
    "--db-isolation",
    type=_DB_ISOLATION_CHOICE,
    default="none",
    show_default=True,
    help=(
        "Database isolation strategy.  "
        "none: shared DB.  "
        "schema: separate PostgreSQL schema per worktree.  "
        "file: separate SQLite file per worktree.  "
        "container: DATABASE_URL already set by orchestrator."
    ),
)
@click.option(
    "--db-schema",
    default="",
    metavar="NAME",
    help=(
        "PostgreSQL schema name.  Only used when --db-isolation=schema.  "
        "Auto-derived from --worktree-id when empty."
    ),
)
@click.option(
    "--db-file",
    default="",
    metavar="PATH",
    help=(
        "SQLite file path.  Only used when --db-isolation=file.  "
        "Auto-derived from --worktree-id when empty."
    ),
)
@click.option(
    "--env",
    "env_list",
    multiple=True,
    metavar="KEY=VALUE",
    help=(
        "Extra environment variable to inject into the instance.  "
        "May be repeated: --env FOO=bar --env BAZ=qux"
    ),
)
@click.option(
    "--working-dir",
    default="",
    metavar="DIR",
    help="Working directory for the subprocess (empty = inherit current directory).",
)
@click.option(
    "--log-file",
    default="",
    metavar="PATH",
    help=(
        "Redirect application stdout/stderr to this file.  "
        "Empty means inherit the caller's streams."
    ),
)
@click.option(
    "--generate-script",
    "mode",
    flag_value="script",
    default=False,
    help="Write a self-contained boot_<id>.sh to disk instead of launching directly.",
)
@click.option(
    "--launch",
    "mode",
    flag_value="launch",
    default=True,
    help="Launch the application directly via Python subprocess (default).",
)
@click.option(
    "--output",
    default=None,
    type=click.Path(dir_okay=False),
    metavar="PATH",
    help=(
        "Destination path for the generated script.  "
        "Only used with --generate-script.  "
        "Defaults to boot_<worktree_id>.sh in the current directory."
    ),
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help=(
        "Print the generated boot script to stdout without writing to disk or "
        "launching the process.  Useful for reviewing the script before committing."
    ),
)
@click.pass_context
def boot_cmd(
    ctx: click.Context,
    worktree_id: str,
    start_command: str,
    port: int,
    health_path: str,
    health_method: str,
    health_timeout: float,
    health_interval: float,
    db_isolation: str,
    db_schema: str,
    db_file: str,
    env_list: tuple[str, ...],
    working_dir: str,
    log_file: str,
    mode: str,
    output: Optional[str],
    dry_run: bool,
) -> None:
    """Launch an isolated application instance for an agent worktree.

    Assigns a dedicated port and optional database isolation, starts the
    application, and blocks until the health endpoint returns HTTP 2xx.
    Each worktree gets its own isolated instance so concurrent agents do
    not share state.

    \b
    Typical usage:
        harness boot --worktree-id task-abc123 \\
                     --command "uvicorn myapp:app" \\
                     --port 8001 \\
                     --health-path /health

    \b
    Generate a reusable boot script instead of launching directly:
        harness boot --worktree-id task-abc123 \\
                     --command "uvicorn myapp:app" \\
                     --port 8001 \\
                     --generate-script

    \b
    Preview the script without writing or launching:
        harness boot --worktree-id task-abc123 \\
                     --command "uvicorn myapp:app" \\
                     --port 8001 \\
                     --dry-run
    """
    try:
        (
            BootConfig,
            DatabaseIsolation,
            HealthCheckMethod,
            IsolationConfig,
            boot_instance,
            generate_boot_script,
        ) = _get_boot_api()
    except Exception as exc:
        click.echo("harness boot: dependency error -- " + str(exc), err=True)
        ctx.exit(1)
        return

    # Parse --env KEY=VALUE pairs
    try:
        extra_env = _parse_env_pairs(env_list)
    except click.BadParameter as exc:
        click.echo(f"harness boot: {exc}", err=True)
        ctx.exit(1)
        return

    # Build configuration
    isolation = IsolationConfig(
        port=port,
        db_isolation=DatabaseIsolation(db_isolation),
        db_schema=db_schema,
        db_file=db_file,
        extra_env=extra_env,
    )

    config = BootConfig(
        worktree_id=worktree_id,
        start_command=start_command,
        isolation=isolation,
        health_path=health_path,
        health_method=HealthCheckMethod(health_method.upper()),
        health_timeout_s=health_timeout,
        health_interval_s=health_interval,
        working_dir=working_dir,
        log_file=log_file,
    )

    # Dry run — print script regardless of mode
    if dry_run:
        script = generate_boot_script(config)
        click.echo("# [DRY-RUN] harness boot — no file written, no process started\n")
        click.echo(script)
        return

    # ── Mode: generate-script ──────────────────────────────────────────────
    if mode == "script":
        script = generate_boot_script(config)
        script_path = output or f"boot_{worktree_id}.sh"
        try:
            with open(script_path, "w", encoding="utf-8") as fh:
                fh.write(script)
            os.chmod(script_path, 0o755)
        except OSError as exc:
            click.echo(f"harness boot: failed to write script: {exc}", err=True)
            ctx.exit(1)
            return

        click.echo(
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"  Harness Boot — script generated\n"
            f"  Worktree: {worktree_id}  ·  Mode: generate-script\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"\n"
            f"  Script details\n"
            f"  ─────────────────────────────────────────────────────\n"
            f"  Output path    {script_path}\n"
            f"  Port           {port}\n"
            f"  Health URL     http://localhost:{port}{health_path}\n"
            f"  DB isolation   {db_isolation}\n"
            f"  ─────────────────────────────────────────────────────\n"
            f"\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"  Next steps\n"
            f"  • Review the script:   cat {script_path}\n"
            f"  • Run it:              bash {script_path}\n"
            f"  • Or launch directly:  harness boot --worktree-id {worktree_id} "
            f"--command ... --launch\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        return

    # ── Mode: launch (default) ─────────────────────────────────────────────
    result = boot_instance(config)

    if not result.ready:
        click.echo(
            f"harness boot: instance failed to become ready — {result.error}",
            err=True,
        )
        ctx.exit(1)
        return

    db_detail: str
    if db_isolation == "schema":
        schema_name = isolation.db_schema or f"worktree_{worktree_id}"
        db_detail = f"schema={schema_name}"
    elif db_isolation == "file":
        db_path = isolation.db_file or f"/tmp/harness_{worktree_id}.db"
        db_detail = f"file={db_path}"
    elif db_isolation == "container":
        db_detail = "container (DATABASE_URL set externally)"
    else:
        db_detail = "none"

    click.echo(
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"  Harness Boot — instance ready\n"
        f"  Worktree: {result.worktree_id}  ·  Mode: launch\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"\n"
        f"  Instance details\n"
        f"  ─────────────────────────────────────────────────────\n"
        f"  PID            {result.pid}\n"
        f"  Port           {result.port}\n"
        f"  Health URL     {result.health_url}\n"
        f"  DB isolation   {db_detail}\n"
        f"  Log file       {log_file or 'inherited'}\n"
        f"  Elapsed        {result.elapsed_s:.1f}s\n"
        f"  ─────────────────────────────────────────────────────\n"
        f"\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"  Next steps\n"
        f"  • Run your tests against http://localhost:{result.port}\n"
        f"  • Kill the instance when done: kill {result.pid}\n"
        f"  • Or run /harness:evaluate to execute all quality gates\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
