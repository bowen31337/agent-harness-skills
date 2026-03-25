"""harness resume — load the most recent plan state for context handoff.

Exit codes:
    0  State found and presented.
    1  No plan state found.
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
from harness_skills.models.resume import ResumeResponse


def _iso_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds")


def _lazy_load():
    from harness_skills.resume import (  # noqa: PLC0415
        format_hints_only,
        format_resume_context,
        load_plan_state,
    )

    return load_plan_state, format_resume_context, format_hints_only


@click.command("resume")
@click.option(
    "--md-path",
    type=click.Path(),
    default=".claude/plan-progress.md",
    help="Path to Markdown plan progress file.",
)
@click.option(
    "--jsonl-path",
    type=click.Path(),
    default=".plan_progress.jsonl",
    help="Path to JSONL plan progress file.",
)
@click.option(
    "--prefer",
    type=click.Choice(["md", "jsonl"], case_sensitive=False),
    default="md",
    help="Preferred source when both exist.",
)
@click.option("--hints", is_flag=True, default=False, help="Print only search hints.")
@output_format_option(choices=("json", "human"))
def resume_cmd(
    md_path: str,
    jsonl_path: str,
    prefer: str,
    hints: bool,
    output_format: str | None,
) -> None:
    """Load the most recent plan state for context handoff."""
    fmt = resolve_output_format(output_format)

    try:
        load_plan_state, format_resume_context, format_hints_only = _lazy_load()

        state = load_plan_state(
            md_path=Path(md_path),
            jsonl_path=Path(jsonl_path),
            prefer=prefer,
        )

        if state is None or not state.found():
            resp = ResumeResponse(
                status=Status.FAILED,
                timestamp=_iso_now(),
                message="No plan state found.",
            )
            if fmt == "json":
                click.echo(json.dumps(resp.model_dump(), indent=2))
            else:
                click.echo("No plan state found.", err=True)
            sys.exit(1)

        context = format_hints_only(state) if hints else format_resume_context(state)
        source = "md" if Path(md_path).exists() else "jsonl"

        resp = ResumeResponse(
            status=Status.PASSED,
            timestamp=_iso_now(),
            message="Plan state loaded.",
            source=source,
            context_block=context if not hints else "",
            hints_only=context if hints else None,
            plan_id=getattr(state, "plan_id", None),
        )

    except Exception:
        traceback.print_exc()
        resp = ResumeResponse(
            status=Status.FAILED,
            timestamp=_iso_now(),
            message="Internal error loading plan state.",
        )
        if fmt == "json":
            click.echo(json.dumps(resp.model_dump(), indent=2))
        else:
            click.echo(f"ERROR: {resp.message}", err=True)
        sys.exit(2)

    if fmt == "json":
        click.echo(json.dumps(resp.model_dump(), indent=2))
    else:
        click.echo(resp.context_block or resp.hints_only or "")

    sys.exit(0)
