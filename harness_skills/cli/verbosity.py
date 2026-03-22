"""Verbosity helpers shared across all harness CLI commands.

Verbosity levels (ascending detail)
------------------------------------
quiet
    Only machine-parseable results (JSON / YAML / structured data) reach
    stdout.  All human-readable informational output — banners, success
    messages, progress lines — is suppressed.  Best for CI pipelines and
    shell scripting: ``result=$(harness evaluate --format json
    --verbosity quiet)``.

normal
    Standard user-facing messages.  **Default.**

verbose
    Adds rationale, context, and timing to human-readable output.  Useful
    when debugging a failing gate or understanding why the tool made a
    particular decision.

debug
    Everything in *verbose*, plus DEBUG-level structured log entries via
    ``harness_skills.logging_config``.  Shows internal state and
    gate-runner internals.

Usage
-----
::

    from harness_skills.cli.verbosity import (
        VERBOSITY_OPTION,
        VerbosityLevel,
        get_verbosity,
        apply_verbosity,
        vecho,
    )

    # Attach the shared option to any Click command or group
    @click.command()
    @VERBOSITY_OPTION
    @click.pass_context
    def my_cmd(ctx, verbosity, ...):
        v = get_verbosity(ctx)
        apply_verbosity(v)
        vecho("Config written.", verbosity=v)                    # suppressed in quiet
        vecho("Gate rationale: ...", verbosity=v,
              min_level=VerbosityLevel.verbose)                  # verbose+
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import click

# ---------------------------------------------------------------------------
# Level enum and ordering
# ---------------------------------------------------------------------------


class VerbosityLevel:
    """String constants for the four verbosity levels.

    Using a plain namespace class instead of ``enum.Enum`` keeps ``Choice``
    validation simple (no ``.value`` unwrapping needed) and avoids import
    overhead on every CLI invocation.
    """

    quiet: str   = "quiet"
    normal: str  = "normal"
    verbose: str = "verbose"
    debug: str   = "debug"

    # All valid values, in ascending detail order
    CHOICES: tuple[str, ...] = ("quiet", "normal", "verbose", "debug")


#: Numeric rank for comparison (higher = more detail).
_RANK: dict[str, int] = {
    VerbosityLevel.quiet:   0,
    VerbosityLevel.normal:  1,
    VerbosityLevel.verbose: 2,
    VerbosityLevel.debug:   3,
}

#: Mapping of verbosity level → stdlib logging level.
_LOG_LEVEL_MAP: dict[str, int] = {
    VerbosityLevel.quiet:   logging.ERROR,   # suppress almost all logging noise
    VerbosityLevel.normal:  logging.INFO,
    VerbosityLevel.verbose: logging.INFO,
    VerbosityLevel.debug:   logging.DEBUG,
}

# ---------------------------------------------------------------------------
# Shared Click option
# ---------------------------------------------------------------------------

#: Drop-in Click option decorator.  Attach to any command or group with
#: ``@VERBOSITY_OPTION``.  The parameter name in the callback is ``verbosity``.
VERBOSITY_OPTION = click.option(
    "--verbosity",
    type=click.Choice(VerbosityLevel.CHOICES, case_sensitive=False),
    default=VerbosityLevel.normal,
    show_default=True,
    envvar="HARNESS_VERBOSITY",
    help=(
        "Control output detail level.  "
        "quiet: machine-parseable results only (banners and status lines suppressed).  "
        "normal: standard messages (default).  "
        "verbose: adds rationale, context, and timing.  "
        "debug: enables DEBUG logging and exposes internal state."
    ),
)

# ---------------------------------------------------------------------------
# Context helpers
# ---------------------------------------------------------------------------


def get_verbosity(ctx: click.Context) -> str:
    """Return the active verbosity level for *ctx*.

    Walks up the Click context tree so that a ``--verbosity`` set on the
    parent group is visible to subcommand callbacks.  Falls back to
    ``VerbosityLevel.normal`` when no ancestor carries the option.

    The value is also stored on ``ctx.obj`` (a plain ``dict``) by the group
    callback, which makes it reachable even across ``PipelineGroup`` stage
    boundaries.

    Parameters
    ----------
    ctx:
        The current Click context (typically the subcommand context).

    Returns
    -------
    str
        One of ``VerbosityLevel.CHOICES``.
    """
    # 1. Check ctx.obj dict (set by the group callback; survives pipeline stages)
    if isinstance(ctx.obj, dict) and "verbosity" in ctx.obj:
        return ctx.obj["verbosity"]

    # 2. Walk up the context tree
    current: Optional[click.Context] = ctx
    while current is not None:
        raw = current.params.get("verbosity")
        if raw is not None:
            return str(raw)
        current = current.parent

    return VerbosityLevel.normal


def apply_verbosity(verbosity: str) -> None:
    """Configure the stdlib root logger to match *verbosity*.

    Call this once per CLI invocation, as early as possible (e.g. in the
    group callback), so all subsequent log entries respect the chosen level.

    Parameters
    ----------
    verbosity:
        One of ``VerbosityLevel.CHOICES``.
    """
    from harness_skills.logging_config import configure  # noqa: PLC0415

    configure(level=_LOG_LEVEL_MAP.get(verbosity, logging.INFO))


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def vecho(
    msg: str,
    *,
    verbosity: str,
    min_level: str = VerbosityLevel.normal,
    err: bool = False,
    **kwargs: Any,
) -> None:
    """Emit *msg* via ``click.echo`` only when *verbosity* ≥ *min_level*.

    Parameters
    ----------
    msg:
        The message to emit.
    verbosity:
        The active verbosity level (from :func:`get_verbosity`).
    min_level:
        The minimum verbosity required to show this message.  Defaults to
        ``normal``, meaning the message is hidden in ``quiet`` mode.
        Pass ``quiet`` to always show a message (e.g. hard errors).
    err:
        When *True*, emit to stderr (forwarded to ``click.echo``).
    **kwargs:
        Additional keyword arguments forwarded to ``click.echo``.

    Examples
    --------
    ::

        v = get_verbosity(ctx)

        # Always visible (even in quiet mode)
        vecho("Fatal: config not found.", verbosity=v, min_level=VerbosityLevel.quiet, err=True)

        # Hidden in quiet mode, shown in normal/verbose/debug
        vecho("Config written: harness.config.yaml", verbosity=v)

        # Only in verbose / debug
        vecho("  Merged 3 new gates into existing config.", verbosity=v,
              min_level=VerbosityLevel.verbose)

        # Only in debug
        vecho(f"  Raw gate config: {config!r}", verbosity=v,
              min_level=VerbosityLevel.debug)
    """
    if _RANK.get(verbosity, 1) >= _RANK.get(min_level, 1):
        click.echo(msg, err=err, **kwargs)


def at_least(verbosity: str, min_level: str) -> bool:
    """Return *True* when *verbosity* is at least as detailed as *min_level*.

    Useful for guarding Rich console output that can't easily go through
    :func:`vecho`::

        if at_least(verbosity, VerbosityLevel.verbose):
            console.print("[dim]gate timing: 42 ms[/dim]")
    """
    return _RANK.get(verbosity, 1) >= _RANK.get(min_level, 1)
