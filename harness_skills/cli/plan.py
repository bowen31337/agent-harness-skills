"""harness plan — create a new execution plan from a feature description.

Exit codes:
    0  Plan created.
    1  Plan already exists.
    2  Internal error.
"""

from __future__ import annotations

import json
import sys
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

import click
import yaml

from harness_skills.cli.fmt import output_format_option, resolve_output_format
from harness_skills.models.base import Status
from harness_skills.models.plan import PlanResponse


def _iso_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds")


@click.command("plan")
@click.argument("description")
@click.option("--plan-id", default=None, help="Custom plan ID (auto-generated if omitted).")
@click.option("--title", default=None, help="Plan title (defaults to first 60 chars of description).")
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False),
    default="docs/exec-plans",
    help="Directory for plan files.",
)
@output_format_option()
def plan_cmd(
    description: str,
    plan_id: str | None,
    title: str | None,
    output_dir: str,
    output_format: str | None,
) -> None:
    """Create a new execution plan from DESCRIPTION."""
    fmt = resolve_output_format(output_format)

    try:
        pid = plan_id or f"PLAN-{uuid.uuid4().hex[:8]}"
        ptitle = title or description[:60].strip()
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        plan_file = out / f"{pid}.yaml"

        if plan_file.exists():
            resp = PlanResponse(
                status=Status.FAILED,
                timestamp=_iso_now(),
                message=f"Plan {pid} already exists at {plan_file}.",
                plan_id=pid,
                plan_path=str(plan_file),
            )
            if fmt == "json":
                click.echo(json.dumps(resp.model_dump(), indent=2))
            else:
                click.echo(f"ERROR: {resp.message}", err=True)
            sys.exit(1)

        plan_data = {
            "id": pid,
            "title": ptitle,
            "objective": description,
            "status": "draft",
            "created": _iso_now(),
            "approach": "",
            "tasks": [],
            "completion_criteria": [],
            "context_assembly": {
                "file_globs": [],
                "grep_patterns": [],
                "symbol_refs": [],
            },
            "progress_log": [],
        }

        with plan_file.open("w") as f:
            yaml.dump(plan_data, f, default_flow_style=False, sort_keys=False)

        resp = PlanResponse(
            status=Status.PASSED,
            timestamp=_iso_now(),
            message=f"Plan {pid} created at {plan_file}.",
            plan_id=pid,
            plan_path=str(plan_file),
            title=ptitle,
            objective=description,
            task_count=0,
        )

    except Exception:
        traceback.print_exc()
        resp = PlanResponse(
            status=Status.FAILED,
            timestamp=_iso_now(),
            message="Internal error creating plan.",
        )
        if fmt == "json":
            click.echo(json.dumps(resp.model_dump(), indent=2))
        else:
            click.echo(f"ERROR: {resp.message}", err=True)
        sys.exit(2)

    if fmt == "json":
        click.echo(json.dumps(resp.model_dump(), indent=2))
    else:
        click.echo(f"Plan created: {resp.plan_id}")
        click.echo(f"  Path: {resp.plan_path}")
        click.echo(f"  Title: {resp.title}")

    sys.exit(0)
