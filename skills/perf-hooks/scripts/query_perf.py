#!/usr/bin/env python3
"""skills/perf-hooks/scripts/query_perf.py — Quick interactive perf query helper.

A thin CLI wrapper around :mod:`skills.perf_hooks` for ad-hoc inspection of the
shared performance measurement log without having to remember the full
``perf_hooks.py`` sub-command syntax.

Usage
-----
::

    # Print aggregate stats for all agents / metrics (default)
    python skills/perf-hooks/scripts/query_perf.py

    # Filter stats to one agent
    python skills/perf-hooks/scripts/query_perf.py --agent "agent/coder-v1"

    # Filter stats to one metric
    python skills/perf-hooks/scripts/query_perf.py --metric response_time

    # Print raw measurement rows instead of aggregate stats
    python skills/perf-hooks/scripts/query_perf.py --raw

    # Combine filters for raw rows
    python skills/perf-hooks/scripts/query_perf.py --raw \
        --agent "agent/coder-v1" \
        --metric startup

    # Filter raw rows by operation label
    python skills/perf-hooks/scripts/query_perf.py --raw --label "call_llm"

    # Output as JSON (one object per line)
    python skills/perf-hooks/scripts/query_perf.py --raw --json

Exit codes
----------
* ``0`` — measurements found and printed.
* ``1`` — no measurements matched the given filters (or log file does not exist).
* ``2`` — argument / usage error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve the repo root so the script works regardless of cwd.
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent          # scripts/
_SKILLS_DIR = _SCRIPT_DIR.parent.parent                # skills/
_REPO_ROOT  = _SKILLS_DIR.parent                       # repo root

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from skills.perf_hooks import PerfHooks, VALID_METRICS  # noqa: E402


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="query_perf.py",
        description=(
            "Quick interactive query of the agent performance measurement log "
            "(docs/exec-plans/perf.md). "
            "By default prints aggregate stats (min/max/mean/p95/count). "
            "Pass --raw to see individual rows."
        ),
    )
    parser.add_argument(
        "--agent",
        default=None,
        metavar="AGENT_ID",
        help="Restrict output to a specific agent identifier (e.g. 'agent/coder-v1').",
    )
    parser.add_argument(
        "--metric",
        default=None,
        choices=VALID_METRICS,
        metavar="METRIC",
        help=f"Restrict output to one metric kind: {', '.join(VALID_METRICS)}.",
    )
    parser.add_argument(
        "--label",
        default=None,
        metavar="LABEL",
        help="Restrict output to a specific operation label (e.g. 'call_llm'). "
             "Only applicable with --raw.",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print individual measurement rows instead of aggregate stats.",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output raw rows as newline-delimited JSON objects (implies --raw).",
    )
    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args   = parser.parse_args(argv)

    # --json implies --raw
    if args.as_json:
        args.raw = True

    hooks = PerfHooks()

    # ------------------------------------------------------------------ raw
    if args.raw:
        entries = hooks.list(
            agent=args.agent,
            metric=args.metric,
            label=args.label,
        )
        if not entries:
            _warn("(no measurements found)")
            sys.exit(1)

        if args.as_json:
            for e in entries:
                print(json.dumps(e.as_dict()))
            return

        # Pretty-printed table
        col_ts  = 22
        col_ag  = 22
        col_met = 16
        col_lbl = 28
        col_val = 12
        col_u   = 5
        header = (
            f"{'Timestamp':<{col_ts}} {'Agent':<{col_ag}} "
            f"{'Metric':<{col_met}} {'Label':<{col_lbl}} "
            f"{'Value':>{col_val}} {'Unit':<{col_u}}  Notes"
        )
        sep = "-" * (len(header) + 10)
        print(header)
        print(sep)
        for e in entries:
            print(
                f"{e.timestamp:<{col_ts}} {e.agent:<{col_ag}} "
                f"{e.metric:<{col_met}} {e.label:<{col_lbl}} "
                f"{e.value:>{col_val}.3f} {e.unit:<{col_u}}  {e.notes or '—'}"
            )
        print(sep)
        print(f"  {len(entries)} row(s) shown", file=sys.stderr)
        return

    # ------------------------------------------------------------------ stats
    # Capture stdout so we can check if anything was printed.
    from io import StringIO
    buf = StringIO()
    _real_stdout = sys.stdout
    sys.stdout = buf
    try:
        hooks.stats(agent=args.agent, metric=args.metric)
    finally:
        sys.stdout = _real_stdout

    output = buf.getvalue()
    if not output.strip() or output.strip() == "(no measurements found)":
        _warn("(no measurements found)")
        sys.exit(1)

    print(output, end="")


def _warn(msg: str) -> None:
    print(msg, file=sys.stderr)


if __name__ == "__main__":
    main()
