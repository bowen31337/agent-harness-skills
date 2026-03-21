"""
harness_skills/boot.py
======================
Harness boot skill — generates per-worktree boot scripts that launch isolated
application instances, and boots those instances while waiting for health
checks to pass before returning.

Isolated means each agent worktree gets its own port assignment and, for
database-backed apps, its own schema or SQLite file so concurrent agents do
not share state.

Public API
----------
    generate_boot_script(config)         -> str
    generate_health_check_spec(config)   -> HealthCheckSpec
    boot_instance(config, timeout)       -> BootResult

Data models
-----------
    IsolationConfig    — port, database, and schema isolation settings
    BootConfig         — full configuration for one isolated instance
    HealthCheckSpec    — machine-readable spec of the health endpoint
    BootResult         — outcome of a boot_instance() call
"""

from __future__ import annotations

import subprocess
import textwrap
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DatabaseIsolation(str, Enum):
    """Strategy used to keep each worktree's database separate."""

    NONE = "none"           # No database isolation — share a single DB
    SCHEMA = "schema"       # Separate schema per worktree (PostgreSQL)
    FILE = "file"           # Separate SQLite file per worktree
    CONTAINER = "container" # Separate container per worktree


class HealthCheckMethod(str, Enum):
    """HTTP method used to probe the health endpoint."""

    GET = "GET"
    HEAD = "HEAD"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class IsolationConfig:
    """
    Environment isolation settings for a single agent worktree.

    Attributes
    ----------
    port:               TCP port the isolated instance should bind to.
    db_isolation:       Strategy for database isolation.
    db_schema:          Schema name (only used when db_isolation=SCHEMA).
    db_file:            Path to SQLite file (only used when db_isolation=FILE).
    extra_env:          Additional environment variables to inject at boot.
    """

    port: int = 8000
    db_isolation: DatabaseIsolation = DatabaseIsolation.NONE
    db_schema: str = ""
    db_file: str = ""
    extra_env: dict[str, str] = field(default_factory=dict)


@dataclass
class BootConfig:
    """
    Full configuration for booting one isolated application instance.

    Attributes
    ----------
    worktree_id:        Short identifier for this agent's worktree (e.g. a
                        task UUID prefix).  Used in log prefixes, schema
                        names, and file paths.
    start_command:      Shell command (or list of argv tokens) that starts
                        the application.  The boot script ``exec``s this.
    isolation:          Port and database isolation settings.
    health_path:        URL path of the health check endpoint
                        (e.g. ``"/health"`` or ``"/api/healthz"``).
    health_method:      HTTP method used to probe the health endpoint.
    health_timeout_s:   Maximum seconds to wait for the health check to
                        return a 2xx status before the boot is declared
                        failed.
    health_interval_s:  Seconds between consecutive health check polls.
    working_dir:        Working directory for the subprocess.  An empty
                        string means "current directory".
    log_file:           Path where the boot script redirects application
                        stdout/stderr.  Empty means inherit the caller's
                        streams.
    """

    worktree_id: str
    start_command: str | list[str]
    isolation: IsolationConfig = field(default_factory=IsolationConfig)
    health_path: str = "/health"
    health_method: HealthCheckMethod = HealthCheckMethod.GET
    health_timeout_s: float = 30.0
    health_interval_s: float = 1.0
    working_dir: str = ""
    log_file: str = ""


@dataclass
class HealthCheckSpec:
    """
    Machine-readable specification of how to probe an instance's health
    endpoint.  Agents can consume this spec to poll the endpoint
    independently of the boot script.

    Attributes
    ----------
    url:            Full URL to probe (e.g. ``"http://localhost:8001/health"``).
    method:         HTTP method to use.
    expected_codes: HTTP status codes that indicate a healthy instance.
    timeout_s:      Per-request timeout in seconds.
    interval_s:     Seconds between retries.
    max_wait_s:     Maximum total seconds to wait before declaring failure.
    headers:        Optional HTTP headers to include in every probe request.
    """

    url: str
    method: HealthCheckMethod = HealthCheckMethod.GET
    expected_codes: list[int] = field(default_factory=lambda: [200])
    timeout_s: float = 5.0
    interval_s: float = 1.0
    max_wait_s: float = 30.0
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class BootResult:
    """
    Outcome returned by :func:`boot_instance`.

    Attributes
    ----------
    worktree_id:    Mirrors :attr:`BootConfig.worktree_id`.
    pid:            Process ID of the launched instance (0 if unknown or if
                    the boot failed before the process was started).
    port:           Port the instance is bound to.
    health_url:     URL that was polled to confirm readiness.
    ready:          ``True`` when the health check passed within the
                    allotted timeout; ``False`` on timeout or error.
    elapsed_s:      Wall-clock seconds from process start to health pass
                    (or to the moment the timeout was reached).
    error:          Human-readable error message when ``ready=False``;
                    empty string on success.
    """

    worktree_id: str
    pid: int
    port: int
    health_url: str
    ready: bool
    elapsed_s: float
    error: str = ""


# ---------------------------------------------------------------------------
# Script generation
# ---------------------------------------------------------------------------

_BOOT_SCRIPT_TEMPLATE = """\
#!/usr/bin/env bash
# -----------------------------------------------------------------------
# harness boot script — worktree: {worktree_id}
# Generated by harness_skills.boot.generate_boot_script()
#
# Usage:  bash {script_name}
#   Starts an isolated application instance on port {port} and exits 0
#   once the health check at {health_url} returns HTTP 2xx.
#   Exits 1 if the health check does not pass within {health_timeout_s}s.
# -----------------------------------------------------------------------
set -euo pipefail

WORKTREE_ID="{worktree_id}"
PORT="{port}"
HEALTH_URL="{health_url}"
HEALTH_TIMEOUT={health_timeout_s}
HEALTH_INTERVAL={health_interval_s}
{working_dir_line}
{log_file_line}
{extra_env_block}
# ── Isolation setup ──────────────────────────────────────────────────────
{isolation_block}
# ── Launch application ───────────────────────────────────────────────────
echo "[harness:boot] Starting instance for worktree=$WORKTREE_ID on port=$PORT"
{launch_block}
APP_PID=$!
echo "[harness:boot] Process started with PID=$APP_PID"

# ── Wait for health check ─────────────────────────────────────────────────
START_TIME=$(date +%s)
while true; do
    NOW=$(date +%s)
    ELAPSED=$(( NOW - START_TIME ))
    if [ "$ELAPSED" -ge "$HEALTH_TIMEOUT" ]; then
        echo "[harness:boot] ERROR: health check timed out after ${{ELAPSED}}s" >&2
        kill "$APP_PID" 2>/dev/null || true
        exit 1
    fi
    HTTP_STATUS=$(curl -s -o /dev/null -w "%{{http_code}}" \\
        -X {health_method} \\
        --max-time 5 \\
        "$HEALTH_URL" 2>/dev/null || echo "000")
    if [[ "$HTTP_STATUS" =~ ^2 ]]; then
        echo "[harness:boot] Ready — health check passed (HTTP $HTTP_STATUS) in ${{ELAPSED}}s"
        exit 0
    fi
    echo "[harness:boot] Waiting for health check (HTTP $HTTP_STATUS, ${{ELAPSED}}s elapsed)…"
    sleep "$HEALTH_INTERVAL"
done
"""


def _build_isolation_block(cfg: BootConfig) -> str:
    """Return shell snippet that sets up DB isolation environment variables."""
    iso = cfg.isolation
    lines: list[str] = []

    if iso.db_isolation == DatabaseIsolation.SCHEMA:
        schema = iso.db_schema or f"worktree_{cfg.worktree_id}"
        lines.append(f'export DB_SCHEMA="{schema}"')
        lines.append(
            f'echo "[harness:boot] Database isolation: schema=$DB_SCHEMA"'
        )
    elif iso.db_isolation == DatabaseIsolation.FILE:
        db_file = iso.db_file or f"/tmp/harness_{cfg.worktree_id}.db"
        lines.append(f'export DATABASE_URL="sqlite:///{db_file}"')
        lines.append(
            f'echo "[harness:boot] Database isolation: file=$DATABASE_URL"'
        )
    elif iso.db_isolation == DatabaseIsolation.CONTAINER:
        lines.append(
            "# Container-level isolation is managed externally; "
            "DATABASE_URL should already be set."
        )
    else:
        lines.append("# No database isolation configured.")

    return "\n".join(lines) if lines else "# No isolation configured."


def _build_launch_block(cfg: BootConfig) -> str:
    """Return the shell line that launches the application process."""
    cmd = (
        " ".join(cfg.start_command)
        if isinstance(cfg.start_command, list)
        else cfg.start_command
    )
    if cfg.log_file:
        return f'{cmd} >> "$LOG_FILE" 2>&1 &'
    return f"{cmd} &"


def generate_boot_script(config: BootConfig) -> str:
    """
    Generate a self-contained bash boot script for an isolated app instance.

    The script:

    1. Sets ``PORT`` and optional ``DB_SCHEMA`` / ``DATABASE_URL`` environment
       variables for isolation.
    2. Launches the application in the background.
    3. Polls the health endpoint with ``curl`` until it returns HTTP 2xx or
       the timeout is exceeded.
    4. Exits ``0`` on success and ``1`` on timeout (killing the background
       process first).

    Parameters
    ----------
    config:   :class:`BootConfig` describing the instance to boot.

    Returns
    -------
    str
        Content of the generated ``boot.sh`` script, ready to be written to
        disk and executed with ``bash boot.sh``.
    """
    port = config.isolation.port
    health_url = f"http://localhost:{port}{config.health_path}"
    script_name = f"boot_{config.worktree_id}.sh"

    working_dir_line = (
        f'cd "{config.working_dir}"' if config.working_dir else "# working dir: inherited"
    )
    log_file_line = (
        f'LOG_FILE="{config.log_file}"' if config.log_file else "# log file: inherited streams"
    )

    extra_env_lines = [
        f'export {k}="{v}"' for k, v in config.isolation.extra_env.items()
    ]
    extra_env_block = (
        "# Extra environment variables\n" + "\n".join(extra_env_lines)
        if extra_env_lines
        else "# No extra environment variables."
    )

    return _BOOT_SCRIPT_TEMPLATE.format(
        worktree_id=config.worktree_id,
        script_name=script_name,
        port=port,
        health_url=health_url,
        health_timeout_s=int(config.health_timeout_s),
        health_interval_s=config.health_interval_s,
        health_method=config.health_method.value,
        working_dir_line=working_dir_line,
        log_file_line=log_file_line,
        extra_env_block=extra_env_block,
        isolation_block=_build_isolation_block(config),
        launch_block=_build_launch_block(config),
    )


# ---------------------------------------------------------------------------
# Health check spec generation
# ---------------------------------------------------------------------------


def generate_health_check_spec(config: BootConfig) -> HealthCheckSpec:
    """
    Generate a :class:`HealthCheckSpec` from a :class:`BootConfig`.

    The spec is machine-readable and can be persisted (e.g. as YAML/JSON)
    or handed directly to :func:`_poll_health_check` for programmatic use.

    Parameters
    ----------
    config:   :class:`BootConfig` for the target instance.

    Returns
    -------
    HealthCheckSpec
        Fully populated spec with the health endpoint URL derived from the
        isolation port and ``health_path``.
    """
    port = config.isolation.port
    url = f"http://localhost:{port}{config.health_path}"
    return HealthCheckSpec(
        url=url,
        method=config.health_method,
        expected_codes=list(range(200, 300)),
        timeout_s=5.0,
        interval_s=config.health_interval_s,
        max_wait_s=config.health_timeout_s,
    )


# ---------------------------------------------------------------------------
# Runtime boot
# ---------------------------------------------------------------------------


def _poll_health_check(spec: HealthCheckSpec) -> tuple[bool, float, str]:
    """
    Poll the health endpoint described by *spec* until it passes or times out.

    Returns
    -------
    (ready, elapsed_s, error)
        *ready* is ``True`` when a probe returned an expected status code.
        *elapsed_s* is wall-clock time elapsed.
        *error* is a human-readable message when *ready* is ``False``.
    """
    start = time.monotonic()

    while True:
        elapsed = time.monotonic() - start
        if elapsed >= spec.max_wait_s:
            return (
                False,
                elapsed,
                f"Health check timed out after {elapsed:.1f}s "
                f"(url={spec.url})",
            )

        try:
            req = urllib.request.Request(spec.url, method=spec.method.value)
            for header, value in spec.headers.items():
                req.add_header(header, value)
            with urllib.request.urlopen(req, timeout=spec.timeout_s) as resp:
                if resp.status in spec.expected_codes:
                    return True, time.monotonic() - start, ""
                error_msg = (
                    f"Unexpected HTTP {resp.status} from {spec.url}"
                )
        except urllib.error.HTTPError as exc:
            if exc.code in spec.expected_codes:
                return True, time.monotonic() - start, ""
            error_msg = f"HTTP {exc.code} from {spec.url}"
        except urllib.error.URLError as exc:
            error_msg = f"Connection error: {exc.reason}"
        except OSError as exc:
            error_msg = f"Request failed: {exc}"

        time.sleep(spec.interval_s)


def boot_instance(
    config: BootConfig,
    timeout: Optional[float] = None,
) -> BootResult:
    """
    Start an isolated application instance and wait for its health check
    to pass before returning.

    The application is launched as a background subprocess using the
    :attr:`BootConfig.start_command`.  The caller's environment is inherited
    and then patched with isolation variables (``PORT``, ``DB_SCHEMA``, etc.)
    derived from :attr:`BootConfig.isolation`.

    Parameters
    ----------
    config:
        Full boot configuration.  The ``start_command`` must be valid for
        the current platform.
    timeout:
        Override for the health-check timeout in seconds.  When ``None``
        (default), :attr:`BootConfig.health_timeout_s` is used.

    Returns
    -------
    BootResult
        Always returns a :class:`BootResult`; inspect ``result.ready`` to
        determine whether the instance became healthy.  When ``ready=False``
        the subprocess is killed and ``error`` contains a diagnostic message.

    Examples
    --------
    ::

        from harness_skills.boot import BootConfig, IsolationConfig, boot_instance

        cfg = BootConfig(
            worktree_id="fb563322",
            start_command="uvicorn myapp.main:app --port 8001",
            isolation=IsolationConfig(port=8001),
            health_path="/healthz",
        )
        result = boot_instance(cfg)
        if result.ready:
            print(f"Instance ready at http://localhost:{result.port}")
        else:
            print(f"Boot failed: {result.error}")
    """
    import os

    if timeout is not None:
        config = BootConfig(
            worktree_id=config.worktree_id,
            start_command=config.start_command,
            isolation=config.isolation,
            health_path=config.health_path,
            health_method=config.health_method,
            health_timeout_s=timeout,
            health_interval_s=config.health_interval_s,
            working_dir=config.working_dir,
            log_file=config.log_file,
        )

    port = config.isolation.port
    health_url = f"http://localhost:{port}{config.health_path}"

    # Build the subprocess environment
    env = os.environ.copy()
    env["PORT"] = str(port)

    iso = config.isolation
    if iso.db_isolation == DatabaseIsolation.SCHEMA:
        env["DB_SCHEMA"] = iso.db_schema or f"worktree_{config.worktree_id}"
    elif iso.db_isolation == DatabaseIsolation.FILE:
        db_file = iso.db_file or f"/tmp/harness_{config.worktree_id}.db"
        env["DATABASE_URL"] = f"sqlite:///{db_file}"

    for key, value in iso.extra_env.items():
        env[key] = value

    # Resolve command
    cmd: str | list[str]
    if isinstance(config.start_command, list):
        cmd = config.start_command
    else:
        cmd = config.start_command

    # Set up stdout/stderr redirection
    stdout = stderr = None
    log_fh = None
    if config.log_file:
        try:
            log_fh = open(config.log_file, "a")  # noqa: SIM115
            stdout = log_fh
            stderr = log_fh
        except OSError:
            pass  # Fall back to inheriting streams

    cwd = config.working_dir or None

    try:
        proc = subprocess.Popen(
            cmd,
            shell=isinstance(cmd, str),
            env=env,
            cwd=cwd,
            stdout=stdout,
            stderr=stderr,
        )
    except (OSError, ValueError) as exc:
        if log_fh:
            log_fh.close()
        return BootResult(
            worktree_id=config.worktree_id,
            pid=0,
            port=port,
            health_url=health_url,
            ready=False,
            elapsed_s=0.0,
            error=f"Failed to start process: {exc}",
        )

    spec = generate_health_check_spec(config)
    ready, elapsed_s, error = _poll_health_check(spec)

    if not ready:
        proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.terminate()

    if log_fh:
        log_fh.close()

    return BootResult(
        worktree_id=config.worktree_id,
        pid=proc.pid,
        port=port,
        health_url=health_url,
        ready=ready,
        elapsed_s=elapsed_s,
        error=error,
    )
