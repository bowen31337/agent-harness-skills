"""harness search — agent-driven artifact and symbol lookup.

Exit codes:
    0  Results found.
    1  No results.
    2  Internal error.
"""

from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import click

from harness_skills.cli.fmt import output_format_option, resolve_output_format
from harness_skills.models.base import Status
from harness_skills.models.search import SearchResponse, SearchResult


def _iso_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds")


def _score_match(query: str, name: str) -> float:
    """Score a match: exact=1.0, prefix=0.8, substring=0.5, none=0."""
    q = query.lower()
    n = name.lower()
    if q == n:
        return 1.0
    if n.startswith(q):
        return 0.8
    if q in n:
        return 0.5
    return 0.0


@click.command("search")
@click.argument("query")
@click.option(
    "--symbols-file",
    type=click.Path(),
    default="harness_symbols.json",
    help="Path to the symbol index JSON file.",
)
@click.option(
    "--type",
    "symbol_type",
    type=click.Choice(["function", "class", "method", "constant", "all"], case_sensitive=False),
    default="all",
    help="Filter by symbol type.",
)
@click.option("--max-results", type=int, default=20, help="Maximum results to return.")
@output_format_option()
def search_cmd(
    query: str,
    symbols_file: str,
    symbol_type: str,
    max_results: int,
    output_format: str | None,
) -> None:
    """Search the symbol index for QUERY."""
    fmt = resolve_output_format(output_format)

    try:
        sym_path = Path(symbols_file)
        if not sym_path.exists():
            resp = SearchResponse(
                status=Status.FAILED,
                timestamp=_iso_now(),
                query=query,
                message=f"Symbol index not found: {symbols_file}",
            )
            if fmt == "json":
                click.echo(json.dumps(resp.model_dump(), indent=2))
            else:
                click.echo(f"ERROR: {resp.message}", err=True)
            sys.exit(1)

        data = json.loads(sym_path.read_text())
        symbols = data if isinstance(data, list) else data.get("symbols", [])

        matches: list[SearchResult] = []
        for sym in symbols:
            name = sym.get("name", "")
            kind = sym.get("type", sym.get("kind", "unknown"))
            score = _score_match(query, name)
            if score <= 0:
                continue
            if symbol_type != "all" and kind.lower() != symbol_type.lower():
                continue
            matches.append(
                SearchResult(
                    name=name,
                    kind=kind,
                    file_path=sym.get("file", sym.get("file_path", "")),
                    line_number=sym.get("line", sym.get("line_number", 0)),
                    score=score,
                )
            )

        matches.sort(key=lambda r: (-r.score, r.name))
        matches = matches[:max_results]

        resp = SearchResponse(
            status=Status.PASSED if matches else Status.FAILED,
            timestamp=_iso_now(),
            query=query,
            results=matches,
            total_matches=len(matches),
            message=f"Found {len(matches)} result(s) for '{query}'."
            if matches
            else f"No results for '{query}'.",
        )

    except Exception:
        traceback.print_exc()
        resp = SearchResponse(
            status=Status.FAILED,
            timestamp=_iso_now(),
            query=query,
            message="Internal error during search.",
        )
        if fmt == "json":
            click.echo(json.dumps(resp.model_dump(), indent=2))
        else:
            click.echo(f"ERROR: {resp.message}", err=True)
        sys.exit(2)

    if fmt == "json":
        click.echo(json.dumps(resp.model_dump(), indent=2))
    else:
        if matches:
            for r in resp.results:
                click.echo(f"  [{r.kind}] {r.name} — {r.file_path}:{r.line_number} (score={r.score})")
        else:
            click.echo(resp.message)

    sys.exit(0 if resp.total_matches > 0 else 1)
