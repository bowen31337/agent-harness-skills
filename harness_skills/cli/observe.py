"""harness observe — real-time structured log tail with domain / trace_id filtering.

Tails the NDJSON log file produced by ``harness_skills.logging_config`` (field
convention: ``timestamp``, ``level``, ``domain``, ``trace_id``, ``message``,
optional ``extra``).

Filtering
---------
``--domain DOMAIN``
    Prefix match: ``harness`` matches ``harness``, ``harness.auth``,
    ``harness.task_lock``, etc.  Dot-boundary aware so ``pay`` does **not**
    match ``payments``.

``--trace-id TRACE_ID``
    Exact match on the 32-char W3C trace ID.  Both filters may be combined —
    only entries that satisfy *all* active filters are shown.

Output modes
------------
``--format pretty``  (default)
    ANSI-coloured, human-readable line per entry (mirrors
    ``PrettyConventionFormatter``).

``--format json``
    Raw NDJSON — one JSON object per line, suitable for piping to ``jq``.

Examples
--------
::

    # Tail everything in real time (pretty, coloured)
    harness observe

    # Filter to a domain subtree
    harness observe --domain harness.auth

    # Trace a single request end-to-end
    harness observe --trace-id 4bf92f3577b34da6a3ce929d0e0e4736

    # Only show errors from the last 100 lines, then exit
    harness observe --level ERROR --lines 100 --no-follow

    # Pipe raw NDJSON to jq
    harness observe --format json --domain harness | jq .message

    # Point at a non-default log file
    harness observe --log-file /var/log/harness/app.ndjson
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import click
from pydantic import ValidationError

from harness_skills.models.observe import LogEntry, ObserveResponse

# ---------------------------------------------------------------------------
# ANSI colour helpers (replicated from logging_config to avoid importing
# private names; keep in sync if the formatter palette changes)
# ---------------------------------------------------------------------------

_ANSI_RESET = "\033[0m"
_LEVEL_COLOURS: dict[str, str] = {
    "DEBUG": "\033[36m",    # cyan
    "INFO":  "\033[32m",    # green
    "WARN":  "\033[33m",    # yellow
    "ERROR": "\033[31m",    # red
    "FATAL": "\033[1;31m",  # bright red + bold
}
_DOMAIN_COLOUR = "\033[34m"   # blue
_EXTRA_COLOUR  = "\033[90m"   # dark grey

# ---------------------------------------------------------------------------
# Severity ordering (for --level filter)
# ---------------------------------------------------------------------------

_LEVEL_ORDER: dict[str, int] = {
    "DEBUG":    0,
    "INFO":     1,
    "WARN":     2,
    "WARNING":  2,   # stdlib alias
    "ERROR":    3,
    "FATAL":    4,
    "CRITICAL": 4,   # stdlib alias
}

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULT_LOG_FILE = "logs/harness.ndjson"
_POLL_INTERVAL_S  = 0.1   # seconds between file-read attempts in follow mode


# ---------------------------------------------------------------------------
# Stats accumulator (returned by _tail_file in --no-follow mode)
# ---------------------------------------------------------------------------


@dataclass
class _TailStats:
    """Aggregate counters collected during a single observe session."""
    lines_scanned: int = 0
    entries_matched: int = 0
    entries_emitted: int = 0
    validation_errors: int = field(default=0)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _domain_matches(entry_domain: str, filter_domain: str) -> bool:
    """Return True when *entry_domain* is equal to or a sub-domain of *filter_domain*.

    Matching is dot-boundary aware so ``pay`` does **not** match ``payments``.

    Examples
    --------
    >>> _domain_matches("harness.auth", "harness")
    True
    >>> _domain_matches("harness", "harness")
    True
    >>> _domain_matches("payments", "pay")
    False
    """
    return entry_domain == filter_domain or entry_domain.startswith(filter_domain + ".")


def _passes_filters(
    entry: dict,
    domain_filter: Optional[str],
    trace_id_filter: Optional[str],
    min_level: int,
) -> bool:
    """Return *True* when *entry* satisfies every active filter."""
    # Level gate
    raw_level = entry.get("level", "DEBUG").upper()
    if _LEVEL_ORDER.get(raw_level, 0) < min_level:
        return False

    # Domain gate
    if domain_filter and not _domain_matches(entry.get("domain", ""), domain_filter):
        return False

    # Trace-ID gate
    if trace_id_filter and entry.get("trace_id", "") != trace_id_filter:
        return False

    return True


def _format_pretty(entry: dict, *, color: bool) -> str:
    """Render a parsed log entry as a human-readable line.

    Format (mirrors ``PrettyConventionFormatter``)::

        <timestamp>  <LEVEL>  <domain>  [<trace8>]  <message>  <extra k=v …>
    """
    ts       = entry.get("timestamp", "")
    level    = entry.get("level", "?").upper()
    domain   = entry.get("domain", "")
    trace_id = entry.get("trace_id", "")
    message  = entry.get("message", "")
    extra    = entry.get("extra") or {}

    short_tid = trace_id[:8] if trace_id else "--------"

    if color:
        lvl_colour = _LEVEL_COLOURS.get(level, "")
        level_str  = f"{lvl_colour}{level:<5}{_ANSI_RESET}"
        domain_str = f"{_DOMAIN_COLOUR}{domain}{_ANSI_RESET}"
    else:
        level_str  = f"{level:<5}"
        domain_str = domain

    parts: list[str] = [ts, level_str, domain_str, f"[{short_tid}]", message]

    if extra:
        extra_pairs = "  ".join(f"{k}={v!r}" for k, v in extra.items())
        parts.append(
            f"{_EXTRA_COLOUR}{extra_pairs}{_ANSI_RESET}" if color else extra_pairs
        )

    return "  ".join(parts)


def _emit(raw_line: str, entry: dict, *, output_format: str, color: bool) -> bool:
    """Print one matching log entry to stdout.

    When *output_format* is ``"json"``, the entry is first validated against
    :class:`~harness_skills.models.observe.LogEntry` to ensure it conforms to
    the five-field logging convention before emission.  On validation failure
    the raw line is emitted unchanged (no data loss) and ``False`` is returned
    so the caller can count schema drift.

    Returns
    -------
    bool
        ``True`` when the entry passed schema validation (or when output is
        pretty-printed, where validation is not applied); ``False`` when the
        entry failed :class:`LogEntry` validation and was emitted as raw JSON.
    """
    if output_format == "json":
        try:
            validated = LogEntry.model_validate(entry)
            click.echo(validated.model_dump_json())
            return True
        except ValidationError:
            # Emit raw so no data is lost; validation error is counted by caller.
            click.echo(raw_line)
            return False
    else:
        click.echo(_format_pretty(entry, color=color))
        return True


# ---------------------------------------------------------------------------
# Core tail logic
# ---------------------------------------------------------------------------


def _tail_file(
    path: Path,
    *,
    follow: bool,
    lines: int,
    domain: Optional[str],
    trace_id: Optional[str],
    min_level: int,
    output_format: str,
    color: bool,
) -> _TailStats:
    """Open *path*, emit matching existing lines, then follow new writes.

    Parameters
    ----------
    path:          Path to the NDJSON log file.
    follow:        If *True*, keep tailing after existing content is exhausted.
    lines:         How many trailing existing lines to scan before following
                   (0 = all existing lines).
    domain:        Domain-prefix filter (``None`` = no filter).
    trace_id:      Exact trace-ID filter (``None`` = no filter).
    min_level:     Minimum severity level order value.
    output_format: ``"pretty"`` or ``"json"``.
    color:         Whether to emit ANSI colour codes.

    Returns
    -------
    _TailStats
        Aggregate counters for the session.  Only meaningful in
        ``--no-follow`` mode; in follow mode the stats cover all lines
        emitted until Ctrl-C.
    """
    stats = _TailStats()

    # ── Wait for file if following ────────────────────────────────────────────
    if not path.exists():
        msg = f"[harness:observe] Log file not found: {path}"
        if not follow:
            click.echo(msg, err=True)
            sys.exit(1)
        click.echo(msg + "  Waiting for it to appear…", err=True)
        while not path.exists():
            time.sleep(0.5)
        click.echo(f"[harness:observe] Log file appeared: {path}", err=True)

    # ── Read existing content ─────────────────────────────────────────────────
    existing_lines: list[str]
    with path.open(encoding="utf-8", errors="replace") as fh:
        existing_lines = fh.readlines()
        file_pos = fh.tell()

    if lines > 0:
        existing_lines = existing_lines[-lines:]

    shown = 0
    for raw in existing_lines:
        raw = raw.rstrip("\n")
        if not raw:
            continue
        stats.lines_scanned += 1
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if _passes_filters(entry, domain, trace_id, min_level):
            stats.entries_matched += 1
            validated = _emit(raw, entry, output_format=output_format, color=color)
            stats.entries_emitted += 1
            if not validated:
                stats.validation_errors += 1
            shown += 1

    if not follow:
        return stats

    # ── Separator + banner ────────────────────────────────────────────────────
    if shown > 0:
        click.echo("─" * 60, err=True)

    filter_desc = ""
    if domain:
        filter_desc += f"  domain={domain!r}"
    if trace_id:
        filter_desc += f"  trace_id={trace_id[:8]}…"
    click.echo(
        f"[harness:observe] Tailing {path}{filter_desc}  (Ctrl-C to stop)",
        err=True,
    )

    # ── Follow loop ───────────────────────────────────────────────────────────
    with path.open(encoding="utf-8", errors="replace") as fh:
        fh.seek(file_pos)
        try:
            while True:
                raw = fh.readline()
                if not raw:
                    time.sleep(_POLL_INTERVAL_S)
                    # Handle log rotation: if the file has shrunk, reopen from start.
                    try:
                        if path.stat().st_size < fh.tell():
                            fh.seek(0)
                    except OSError:
                        pass
                    continue

                raw = raw.rstrip("\n")
                if not raw:
                    continue
                stats.lines_scanned += 1
                try:
                    entry = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                if _passes_filters(entry, domain, trace_id, min_level):
                    stats.entries_matched += 1
                    validated = _emit(raw, entry, output_format=output_format, color=color)
                    stats.entries_emitted += 1
                    if not validated:
                        stats.validation_errors += 1

        except KeyboardInterrupt:
            click.echo("\n[harness:observe] Stopped.", err=True)

    return stats


# ---------------------------------------------------------------------------
# Click command
# ---------------------------------------------------------------------------


@click.command("observe")
@click.option(
    "--log-file",
    default=_DEFAULT_LOG_FILE,
    show_default=True,
    metavar="PATH",
    help=(
        "Path to the NDJSON structured log file to tail.  "
        "Defaults to logs/harness.ndjson (set by harness_skills/logging.yaml)."
    ),
)
@click.option(
    "--domain",
    default=None,
    metavar="DOMAIN",
    help=(
        "Filter entries by domain prefix (dot-boundary aware).  "
        "E.g. --domain harness matches harness, harness.auth, harness.task_lock, …"
    ),
)
@click.option(
    "--trace-id",
    default=None,
    metavar="TRACE_ID",
    help=(
        "Filter entries by exact trace_id (32-char lowercase hex W3C trace ID).  "
        "Use with --domain to narrow a specific request within a service."
    ),
)
@click.option(
    "--level",
    "min_level_name",
    default="DEBUG",
    show_default=True,
    type=click.Choice(["DEBUG", "INFO", "WARN", "ERROR", "FATAL"], case_sensitive=False),
    help="Minimum severity level to display.  Entries below this level are hidden.",
)
@click.option(
    "--lines",
    default=50,
    show_default=True,
    metavar="N",
    help=(
        "Number of trailing existing lines to scan before entering follow mode.  "
        "0 = print all existing content first."
    ),
)
@click.option(
    "--follow/--no-follow",
    default=True,
    show_default=True,
    help=(
        "Keep tailing the file for new entries after existing content is shown "
        "(like tail -f).  Use --no-follow to print and exit."
    ),
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["pretty", "json"], case_sensitive=False),
    default="pretty",
    show_default=True,
    help=(
        "Output format.  "
        "'pretty' = ANSI-coloured human-readable lines; "
        "'json' = raw NDJSON (one object per line, suitable for jq)."
    ),
)
@click.option(
    "--no-color",
    is_flag=True,
    default=False,
    help="Disable ANSI colour codes (automatically disabled when stdout is not a TTY).",
)
def observe_cmd(
    log_file: str,
    domain: Optional[str],
    trace_id: Optional[str],
    min_level_name: str,
    lines: int,
    follow: bool,
    output_format: str,
    no_color: bool,
) -> None:
    """Tail structured NDJSON logs in real time, filtered by domain or trace_id.

    Reads the 5-field NDJSON log convention (timestamp · level · domain ·
    trace_id · message) produced by harness_skills.logging_config and streams
    matching entries to stdout.

    \b
    Quick examples:

      # Follow all harness logs (pretty, coloured)
      harness observe

    \b
      # Filter to a domain subtree
      harness observe --domain harness.auth

    \b
      # Trace one request end-to-end across every domain
      harness observe --trace-id 4bf92f3577b34da6a3ce929d0e0e4736

    \b
      # Combine both filters: trace within a single domain
      harness observe --domain harness.payments --trace-id 4bf92f3577b34da6a3ce929d0e0e4736

    \b
      # Show only ERROR+ from the last 200 lines, then exit
      harness observe --level ERROR --lines 200 --no-follow

    \b
      # Pipe raw NDJSON to jq (disables colour automatically)
      harness observe --format json --domain harness | jq '{ts: .timestamp, msg: .message}'

    \b
      # Non-default log file
      harness observe --log-file /var/log/harness/app.ndjson --domain harness.gates
    """
    path      = Path(log_file)
    min_level = _LEVEL_ORDER.get(min_level_name.upper(), 0)
    # Enable colour only for pretty mode on a real TTY unless suppressed
    color     = (
        not no_color
        and output_format == "pretty"
        and sys.stdout.isatty()
    )

    stats = _tail_file(
        path,
        follow=follow,
        lines=lines,
        domain=domain,
        trace_id=trace_id,
        min_level=min_level,
        output_format=output_format,
        color=color,
    )

    # In --no-follow mode emit a structured ObserveResponse summary to stderr
    # so downstream tools can assess filter coverage and schema health.
    if not follow:
        summary = ObserveResponse(
            log_file=str(path),
            lines_scanned=stats.lines_scanned,
            entries_matched=stats.entries_matched,
            entries_emitted=stats.entries_emitted,
            validation_errors=stats.validation_errors,
            domain_filter=domain,
            trace_id_filter=trace_id,
            min_level=min_level_name.upper(),
        )
        click.echo(summary.model_dump_json(), err=True)
