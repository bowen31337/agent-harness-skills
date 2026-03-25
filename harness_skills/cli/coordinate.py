"""harness coordinate — cross-agent task conflict detection and reordering.

Exit codes:
    0  Report generated.
    1  No agents or tasks found.
    2  Internal error.
"""

from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime, timezone

import click

from harness_skills.cli.fmt import output_format_option, resolve_output_format
from harness_skills.models.base import AgentConflict, Status
from harness_skills.models.coordinate import AgentTask, CoordinateResponse


def _iso_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds")


def _demo_tasks() -> list[AgentTask]:
    """Built-in demo data for testing."""
    return [
        AgentTask(
            agent_id="agent-alpha",
            task_id="TASK-001",
            files=["src/auth/login.py", "src/auth/session.py", "src/models/user.py"],
        ),
        AgentTask(
            agent_id="agent-beta",
            task_id="TASK-002",
            files=["src/models/user.py", "src/api/users.py"],
        ),
        AgentTask(
            agent_id="agent-gamma",
            task_id="TASK-003",
            files=["src/billing/invoice.py", "src/api/billing.py"],
        ),
    ]


def _detect_conflicts(agents: list[AgentTask]) -> list[AgentConflict]:
    """Find file-level conflicts between agents."""
    conflicts: list[AgentConflict] = []
    for i, a in enumerate(agents):
        for b in agents[i + 1 :]:
            shared = set(a.files) & set(b.files)
            for f in sorted(shared):
                conflicts.append(
                    AgentConflict(
                        agent_id=f"{a.agent_id} vs {b.agent_id}",
                        resource=f,
                        conflict_type="file_overlap",
                        message=f"Both {a.task_id} and {b.task_id} modify {f}",
                    )
                )
    return conflicts


def _suggest_order(agents: list[AgentTask], conflicts: list[AgentConflict]) -> tuple[list[str], str]:
    """Heuristic: agents with most conflicts should serialize first."""
    conflict_count: dict[str, int] = {}
    for a in agents:
        conflict_count[a.agent_id] = 0
    for c in conflicts:
        for aid in c.agent_id.split(" vs "):
            conflict_count[aid] = conflict_count.get(aid, 0) + 1
    order = sorted(conflict_count, key=lambda k: -conflict_count[k])
    if conflicts:
        rationale = (
            f"Serialize {order[0]} first (most conflicts: {conflict_count[order[0]]}). "
            f"Remaining agents can run in parallel."
        )
    else:
        rationale = "No conflicts detected. All agents can run in parallel."
    return order, rationale


@click.command("coordinate")
@click.option("--state-url", default="http://localhost:8420", help="State service URL.")
@click.option("--demo", is_flag=True, default=False, help="Use built-in demo data.")
@click.option("--no-locks", is_flag=True, default=False, help="Skip lock display.")
@click.option(
    "--locks-dir",
    type=click.Path(file_okay=False),
    default=".harness/locks",
    help="Lock files directory.",
)
@output_format_option()
def coordinate_cmd(
    state_url: str,
    demo: bool,
    no_locks: bool,
    locks_dir: str,
    output_format: str | None,
) -> None:
    """Detect cross-agent task conflicts and suggest reordering."""
    fmt = resolve_output_format(output_format)

    try:
        if demo:
            agents = _demo_tasks()
        else:
            # Try fetching from state service
            try:
                import requests  # noqa: PLC0415

                r = requests.get(f"{state_url}/agents", timeout=5)
                r.raise_for_status()
                data = r.json()
                agents = [AgentTask(**a) for a in data]
            except Exception:
                resp = CoordinateResponse(
                    status=Status.FAILED,
                    timestamp=_iso_now(),
                    message=f"Cannot reach state service at {state_url}. Use --demo for test data.",
                )
                if fmt == "json":
                    click.echo(json.dumps(resp.model_dump(), indent=2))
                else:
                    click.echo(f"ERROR: {resp.message}", err=True)
                sys.exit(1)

        if not agents:
            resp = CoordinateResponse(
                status=Status.FAILED,
                timestamp=_iso_now(),
                message="No agents or tasks found.",
            )
            if fmt == "json":
                click.echo(json.dumps(resp.model_dump(), indent=2))
            else:
                click.echo(resp.message)
            sys.exit(1)

        conflicts = _detect_conflicts(agents)
        order, rationale = _suggest_order(agents, conflicts)

        resp = CoordinateResponse(
            status=Status.PASSED,
            timestamp=_iso_now(),
            message=f"{len(agents)} agent(s), {len(conflicts)} conflict(s).",
            agents=agents,
            conflicts=conflicts,
            suggested_order=order,
            rationale=rationale,
        )

    except Exception:
        traceback.print_exc()
        resp = CoordinateResponse(
            status=Status.FAILED,
            timestamp=_iso_now(),
            message="Internal error during coordination.",
        )
        if fmt == "json":
            click.echo(json.dumps(resp.model_dump(), indent=2))
        else:
            click.echo(f"ERROR: {resp.message}", err=True)
        sys.exit(2)

    if fmt == "json":
        click.echo(json.dumps(resp.model_dump(), indent=2))
    else:
        click.echo(f"Agents: {len(resp.agents)}  Conflicts: {len(resp.conflicts)}")
        for c in resp.conflicts:
            click.echo(f"  CONFLICT: {c.message}")
        click.echo(f"\nSuggested order: {' → '.join(resp.suggested_order)}")
        click.echo(f"Rationale: {resp.rationale}")

    sys.exit(0)
