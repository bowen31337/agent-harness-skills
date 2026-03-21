"""
Error Query Agent
=================
Agent SDK interface that exposes the error aggregation view as queryable tools
so that Claude-powered agents can ask natural-language questions about recent
errors grouped by domain and frequency.

Usage — standalone script
--------------------------
    python -m harness_skills.error_query_agent \\
        --log-file /var/log/harness/errors.ndjson \\
        --window 60 \\
        --prompt "Which domains are producing the most errors right now?"

Usage — from another agent (via MCP / ClaudeSDKClient)
-------------------------------------------------------
    from harness_skills.error_query_agent import build_error_tools, run_error_query

    server = build_error_tools(records=my_error_records)
    await run_error_query(prompt="Show me rising errors in the gate_runner domain",
                          server=server)

Architecture
------------
  1. ``build_error_tools``   — creates an SDK MCP server exposing two tools:
       • ``query_recent_errors``   query top errors (optionally per domain)
       • ``get_error_domain_list`` list all active error domains with counts
  2. ``run_error_query``     — wires the server into a ClaudeSDKClient session
                               and streams the response back to the caller.
  3. ``main``                — thin CLI wrapper for direct invocation.

The aggregation is computed *once* at startup so every tool call within a
session reads from the same pre-computed view (fast, deterministic).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import anyio

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    SystemMessage,
    TextBlock,
    create_sdk_mcp_server,
    tool,
)

from harness_skills.error_aggregation import (
    ErrorAggregationView,
    ErrorRecord,
    aggregate_errors,
    domain_summary,
    errors_to_json_summary,
    load_errors_from_log,
    top_errors,
)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


def _make_query_recent_errors(view: ErrorAggregationView) -> Callable:
    """Return a ``query_recent_errors`` tool bound to *view*."""

    @tool(
        "query_recent_errors",
        (
            "Return recent errors aggregated by domain and frequency. "
            "Optionally filter to a single domain. Returns JSON with the "
            "top error groups, each including domain, error_type, frequency, "
            "severity, trend (rising/falling/stable), and a sample message."
        ),
        {
            "domain": str,
            "limit":  int,
        },
    )
    async def query_recent_errors(args: dict) -> dict:
        domain: Optional[str] = args.get("domain") or None
        limit: int = max(1, min(int(args.get("limit", 10)), 50))

        groups = top_errors(view, n=limit, domain=domain)

        result = {
            "window_start":   view.window_start.isoformat(),
            "window_end":     view.window_end.isoformat(),
            "total_events":   view.total_events,
            "domain_filter":  domain,
            "returned_groups": len(groups),
            "errors": [
                {
                    "domain":          g.domain,
                    "error_type":      g.error_type,
                    "frequency":       g.frequency,
                    "severity":        g.severity,
                    "trend":           g.trend,
                    "first_seen":      g.first_seen.isoformat(),
                    "last_seen":       g.last_seen.isoformat(),
                    "recency_seconds": round(g.recency_seconds),
                    "sample_message":  g.sample_message[:300],
                }
                for g in groups
            ],
        }
        return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

    return query_recent_errors


def _make_get_error_domain_list(view: ErrorAggregationView) -> Callable:
    """Return a ``get_error_domain_list`` tool bound to *view*."""

    @tool(
        "get_error_domain_list",
        (
            "List all domains that produced errors in the current analysis window, "
            "with total error counts, distinct pattern counts, and the dominant "
            "severity for each domain. Sorted by total error count descending. "
            "Use this first to understand which domains to investigate further."
        ),
        {},  # no parameters
    )
    async def get_error_domain_list(args: dict) -> dict:  # noqa: ARG001
        rows = domain_summary(view)
        result = {
            "window_start":  view.window_start.isoformat(),
            "window_end":    view.window_end.isoformat(),
            "domain_count":  view.domain_count,
            "total_events":  view.total_events,
            "domains":       rows,
        }
        return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

    return get_error_domain_list


# ---------------------------------------------------------------------------
# Server factory
# ---------------------------------------------------------------------------


def build_error_tools(
    records: Optional[list[ErrorRecord]] = None,
    view: Optional[ErrorAggregationView] = None,
    window_minutes: int = 60,
) -> object:
    """
    Build and return an SDK MCP server that exposes the error query tools.

    Provide either *records* (raw events, aggregated on the fly) or a
    pre-built *view*.  If both are ``None``, the server returns empty results.

    Parameters
    ----------
    records:        Raw error events to aggregate.
    view:           Pre-computed aggregation view (takes priority over records).
    window_minutes: Analysis window when building from raw records.

    Returns
    -------
    An SDK MCP server object suitable for passing to ``ClaudeAgentOptions.mcp_servers``.
    """
    if view is None:
        view = aggregate_errors(records or [], window_minutes=window_minutes)

    return create_sdk_mcp_server(
        "error-aggregation",
        tools=[
            _make_query_recent_errors(view),
            _make_get_error_domain_list(view),
        ],
    )


# ---------------------------------------------------------------------------
# High-level query runner
# ---------------------------------------------------------------------------


async def run_error_query(
    prompt: str,
    records: Optional[list[ErrorRecord]] = None,
    view: Optional[ErrorAggregationView] = None,
    window_minutes: int = 60,
    model: str = "claude-opus-4-6",
    max_turns: int = 6,
    stream_to_stdout: bool = True,
) -> str:
    """
    Run a natural-language query against the error aggregation view using
    the Claude Agent SDK.

    Parameters
    ----------
    prompt:           Natural-language question (e.g. "Which domain has the most
                      rising errors in the last hour?").
    records:          Raw error events.  Ignored if *view* is provided.
    view:             Pre-computed aggregation view.
    window_minutes:   Analysis window when building from raw records.
    model:            Claude model ID.
    max_turns:        Maximum agent turns before stopping.
    stream_to_stdout: Print assistant text tokens as they arrive.

    Returns
    -------
    str
        The final text result from the agent.
    """
    server = build_error_tools(records=records, view=view, window_minutes=window_minutes)

    # Pre-compute the JSON summary and embed it in the system prompt so the
    # agent has structured context even before it calls any tools.
    if view is None:
        agg_view = aggregate_errors(records or [], window_minutes=window_minutes)
    else:
        agg_view = view

    json_context = errors_to_json_summary(agg_view, top_n=30)

    system_prompt = f"""You are an expert site-reliability assistant analysing a
harness error aggregation view.  The pre-computed summary below contains recent
errors grouped by domain and frequency.  Use the available tools to drill down
into specific domains or fetch more details as needed.

<error_aggregation_summary>
{json_context}
</error_aggregation_summary>

Guidelines:
- Lead with the most actionable finding (highest-frequency or rising errors).
- Group insights by domain; don't list every individual error.
- Call ``get_error_domain_list`` first if you need a domain overview.
- Call ``query_recent_errors`` with a ``domain`` argument to drill into a domain.
- Keep your final answer concise: a short executive summary followed by a
  prioritised list of findings.
"""

    options = ClaudeAgentOptions(
        model=model,
        system_prompt=system_prompt,
        allowed_tools=["query_recent_errors", "get_error_domain_list"],
        mcp_servers={"error-aggregation": server},
        max_turns=max_turns,
        permission_mode="dontAsk",
    )

    result_text = ""

    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        if stream_to_stdout:
                            print(block.text, end="", flush=True)
                        result_text += block.text
            elif isinstance(message, ResultMessage):
                result_text = message.result or result_text

    if stream_to_stdout:
        print()  # trailing newline after streamed output

    return result_text


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="error-query-agent",
        description=(
            "Query recent errors grouped by domain and frequency using Claude."
        ),
    )
    parser.add_argument(
        "--log-file",
        metavar="PATH",
        help="Path to a newline-delimited JSON (NDJSON) error log file.",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=60,
        metavar="MINUTES",
        help="Analysis window in minutes (default: 60).",
    )
    parser.add_argument(
        "--prompt",
        default="Summarise the most critical recent errors grouped by domain.",
        metavar="TEXT",
        help="Natural-language question to send to the agent.",
    )
    parser.add_argument(
        "--model",
        default="claude-opus-4-6",
        metavar="MODEL",
        help="Claude model ID (default: claude-opus-4-6).",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=6,
        metavar="N",
        help="Maximum agent turns (default: 6).",
    )
    parser.add_argument(
        "--json-summary",
        action="store_true",
        help="Print the aggregation JSON summary and exit (no Claude call).",
    )
    return parser


async def _async_main(argv: Optional[list[str]] = None) -> None:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    records: list[ErrorRecord] = []
    if args.log_file:
        records = load_errors_from_log(args.log_file, window_minutes=args.window)
        print(
            f"[error-query-agent] Loaded {len(records)} records from {args.log_file}",
            file=sys.stderr,
        )
    else:
        print(
            "[error-query-agent] No --log-file provided; running with empty record set.",
            file=sys.stderr,
        )

    view = aggregate_errors(records, window_minutes=args.window)

    if args.json_summary:
        print(errors_to_json_summary(view))
        return

    print(
        f"[error-query-agent] Analysing {view.total_events} events across "
        f"{view.domain_count} domain(s) in the last {args.window} minutes.",
        file=sys.stderr,
    )
    print(f"\nPrompt: {args.prompt}\n", file=sys.stderr)
    print("─" * 60, file=sys.stderr)

    await run_error_query(
        prompt=args.prompt,
        view=view,
        model=args.model,
        max_turns=args.max_turns,
        stream_to_stdout=True,
    )


def main(argv: Optional[list[str]] = None) -> None:
    """Synchronous entry point for CLI use."""
    anyio.run(_async_main, argv)


if __name__ == "__main__":
    main()
