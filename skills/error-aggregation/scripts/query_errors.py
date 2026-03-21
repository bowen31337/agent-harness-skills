#!/usr/bin/env python3
"""
query_errors.py — Standalone CLI helper for the error-aggregation skill.

Loads an NDJSON error log, builds the aggregation view, and either:
  • prints a compact JSON summary (--json-summary), or
  • runs a natural-language query through the Claude agent SDK.

This script adds the project root to sys.path automatically so it can be run
from anywhere without installing the package.

Usage
-----
# JSON summary only (no Claude call):
    python skills/error-aggregation/scripts/query_errors.py \\
        --log-file /var/log/harness/errors.ndjson \\
        --json-summary

# Ask a natural-language question:
    python skills/error-aggregation/scripts/query_errors.py \\
        --log-file /var/log/harness/errors.ndjson \\
        --prompt "Which domain has the most rising errors?"

# Restrict the analysis window to 30 minutes:
    python skills/error-aggregation/scripts/query_errors.py \\
        --log-file /var/log/harness/errors.ndjson \\
        --window 30 \\
        --prompt "Are there any critical errors in the deploy domain?"

# Domain overview only (no Claude call):
    python skills/error-aggregation/scripts/query_errors.py \\
        --log-file /var/log/harness/errors.ndjson \\
        --domain-overview
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure project root is importable regardless of CWD.
# ---------------------------------------------------------------------------

_SCRIPT_DIR  = Path(__file__).resolve().parent          # scripts/
_SKILL_DIR   = _SCRIPT_DIR.parent                       # error-aggregation/
_SKILLS_DIR  = _SKILL_DIR.parent                        # skills/
_PROJECT_ROOT = _SKILLS_DIR.parent                      # repo root

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Imports (deferred so path fix above takes effect first)
# ---------------------------------------------------------------------------

from harness_skills.error_aggregation import (   # noqa: E402
    aggregate_errors,
    domain_summary,
    errors_to_json_summary,
    load_errors_from_log,
)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="query_errors",
        description="Query recent harness errors grouped by domain and frequency.",
    )
    p.add_argument(
        "--log-file",
        metavar="PATH",
        help="Path to a newline-delimited JSON (NDJSON) error log file.",
    )
    p.add_argument(
        "--window",
        type=int,
        default=60,
        metavar="MINUTES",
        help="Analysis window in minutes (default: 60).",
    )
    p.add_argument(
        "--prompt",
        default="Summarise the most critical recent errors grouped by domain.",
        metavar="TEXT",
        help="Natural-language question to send to the agent (requires Claude SDK).",
    )
    p.add_argument(
        "--model",
        default="claude-opus-4-6",
        metavar="MODEL",
        help="Claude model ID (default: claude-opus-4-6).",
    )
    p.add_argument(
        "--max-turns",
        type=int,
        default=6,
        metavar="N",
        help="Maximum agent turns (default: 6).",
    )
    p.add_argument(
        "--json-summary",
        action="store_true",
        help="Print the aggregation JSON summary and exit (no Claude call).",
    )
    p.add_argument(
        "--domain-overview",
        action="store_true",
        help="Print a bird's-eye domain overview table and exit (no Claude call).",
    )
    p.add_argument(
        "--top-n",
        type=int,
        default=20,
        metavar="N",
        help="Number of top error groups to include in the JSON summary (default: 20).",
    )
    return p


def _print_domain_overview(rows: list[dict]) -> None:
    """Print a human-readable domain overview table."""
    if not rows:
        print("(no errors in the analysis window)")
        return

    col_w = max(len(r["domain"]) for r in rows) + 2
    header = (
        f"{'Domain':<{col_w}} {'Total':>7}  {'Patterns':>9}  "
        f"{'Severity':<10}  {'Rising':>7}"
    )
    print(header)
    print("─" * len(header))
    for r in rows:
        print(
            f"{r['domain']:<{col_w}} {r['total_errors']:>7}  "
            f"{r['distinct_patterns']:>9}  {r['top_severity']:<10}  "
            f"{r['rising_patterns']:>7}"
        )


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args   = parser.parse_args(argv)

    # ── Load records ──────────────────────────────────────────────────────
    records = []
    if args.log_file:
        records = load_errors_from_log(args.log_file, window_minutes=args.window)
        print(
            f"[query_errors] Loaded {len(records)} record(s) from {args.log_file}",
            file=sys.stderr,
        )
    else:
        print(
            "[query_errors] No --log-file provided; running with an empty record set.",
            file=sys.stderr,
        )

    view = aggregate_errors(records, window_minutes=args.window)
    print(
        f"[query_errors] {view.total_events} event(s) across "
        f"{view.domain_count} domain(s) in the last {args.window} min.",
        file=sys.stderr,
    )

    # ── Output modes that don't require Claude ────────────────────────────
    if args.json_summary:
        print(errors_to_json_summary(view, top_n=args.top_n))
        return

    if args.domain_overview:
        _print_domain_overview(domain_summary(view))
        return

    # ── Agent query (requires Claude SDK) ─────────────────────────────────
    try:
        import anyio
        from harness_skills.error_query_agent import run_error_query
    except ImportError as exc:
        print(
            f"[query_errors] Cannot import agent SDK: {exc}\n"
            "  Install it or use --json-summary / --domain-overview for "
            "SDK-free output.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"\nPrompt: {args.prompt}\n", file=sys.stderr)
    print("─" * 60, file=sys.stderr)

    anyio.run(
        run_error_query,
        args.prompt,
        None,          # records — we pass view directly below
        view,
        args.window,
        args.model,
        args.max_turns,
        True,          # stream_to_stdout
    )


if __name__ == "__main__":
    main()
