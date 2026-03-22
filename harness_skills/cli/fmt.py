"""Shared ``--output-format`` option for all harness CLI commands.

All commands expose a ``--output-format`` flag with consistent semantics:

``table``   Rich ASCII table for interactive terminal use (default when stdout is a TTY).
``json``    Machine-parseable JSON (default when stdout is **not** a TTY).
``yaml``    Same data serialised as YAML — human-friendly and still machine-parseable.

Auto-detection lets scripts and CI pipelines consume structured output without
needing to pass an explicit flag — just pipe the output and JSON is returned
automatically.

Usage
-----
::

    from harness_skills.cli.fmt import output_format_option, resolve_output_format

    @click.command("mycmd")
    @output_format_option()
    def my_cmd(output_format: str | None) -> None:
        fmt = resolve_output_format(output_format)
        if fmt == "json":
            ...
        elif fmt == "yaml":
            ...
        else:  # "table"
            ...
"""

from __future__ import annotations

import sys
from typing import Any

import click

# ---------------------------------------------------------------------------
# Standard help text
# ---------------------------------------------------------------------------

_FORMAT_HELP = (
    "Output format.  "
    "json: machine-parseable structured output.  "
    "yaml: same data as YAML, human-friendly and still machine-parseable.  "
    "table: rich ASCII table for interactive terminal use.  "
    "Defaults to 'table' when stdout is a TTY, 'json' when stdout is not a TTY "
    "(e.g. when piped to a file or another process)."
)


# ---------------------------------------------------------------------------
# Auto-detection
# ---------------------------------------------------------------------------


def resolve_output_format(fmt: str | None) -> str:
    """Return the effective output format, auto-detecting from TTY state when needed.

    When *fmt* is ``None`` (flag not passed), the format is chosen based on
    whether stdout is connected to an interactive terminal:

    * ``"table"`` — stdout is a TTY (interactive use by a human).
    * ``"json"``  — stdout is piped, redirected, or otherwise non-interactive
      (agent / CI / script consumption).

    Parameters
    ----------
    fmt:
        The raw value passed by the Click option, or ``None`` when the flag
        was omitted.

    Returns
    -------
    str
        One of ``"json"``, ``"yaml"``, or ``"table"`` (lower-case).
    """
    if fmt is not None:
        return fmt.lower()
    return "table" if sys.stdout.isatty() else "json"


# ---------------------------------------------------------------------------
# Reusable Click option factory
# ---------------------------------------------------------------------------


def output_format_option(
    choices: tuple[str, ...] = ("json", "yaml", "table"),
    help_extra: str = "",
) -> Any:
    """Return a ``@click.option`` decorator for ``--output-format``.

    Parameters
    ----------
    choices:
        Allowed format values.  Defaults to the standard ``(json, yaml, table)``
        triple.  Pass a subset to restrict the allowed formats for commands
        with specialised output (e.g. ``("json", "table")`` for commands that
        do not meaningfully support YAML serialisation).
    help_extra:
        Optional text appended after the standard help description.
    """
    help_text = _FORMAT_HELP
    if help_extra:
        help_text = help_text + "  " + help_extra
    return click.option(
        "--output-format",
        "output_format",
        type=click.Choice(list(choices), case_sensitive=False),
        default=None,
        show_default=False,
        metavar="FORMAT",
        help=help_text,
    )
