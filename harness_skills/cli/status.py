"""harness status — plan status dashboard with JSON / YAML / table output.

Shows all active, completed, and blocked execution plans (and their tasks) in a
single structured report.  Plans are loaded from local YAML/JSON files **and/or**
fetched from the claw-forge state service (http://localhost:8888).

Usage (CLI):
    harness status [--format json|yaml|table]
                   [--plan-file PATH ...]
                   [--state-url URL]
                   [--plan-id PLAN_ID ...]
                   [--status-filter active|completed|blocked|pending|all]
                   [--no-state-service]

Usage (agent tool call):
    harness status --format json
    harness status --format yaml --plan-file plan.yaml
    harness status --format json --status-filter active

Machine-parseable fields:
    .summary.total_plans              — total plan count
    .summary.active_plans             — plans with status "running"
    .summary.blocked_plans            — blocked plans
    .summary.completed_plans          — finished plans
    .summary.overall_completion_pct   — global task completion %
    .plans[].status                   — per-plan status string
    .plans[].task_counts.active       — tasks running in each plan
    .plans[].task_counts.blocked      — blocked tasks in each plan
    .plans[].tasks[].status           — per-task status string
    .plans[].tasks[].assigned_agent   — agent responsible for a task

Exit codes:
    0   Dashboard rendered (even if some plans are blocked).
    1   No plan data found (no files given, state service unreachable).
    2   Internal error (parse failure, schema validation error).
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.error import URLError
from urllib.request import urlopen

import click
import yaml
from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

from harness_skills.cli.fmt import output_format_option, resolve_output_format
from harness_skills.models.base import Status
from harness_skills.models.status import (
    DashboardSummary,
    PlanSnapshot,
    PlanStatusValue,
    StatusDashboardResponse,
    TaskDetail,
    TaskStatusCounts,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_STATE_URL = "http://localhost:8888"
_HTTP_TIMEOUT_S = 5

_PLAN_STATUS_STYLE: dict[str, str] = {
    "running": "bold cyan",
    "done":    "bold green",
    "blocked": "bold red",
    "pending": "dim",
    "cancelled": "dim italic",
}

_TASK_STATUS_ICON: dict[str, str] = {
    "running": "🔵",
    "done":    "✅",
    "blocked": "🔴",
    "pending": "⬜",
    "skipped": "⏭️",
}

_PRIORITY_STYLE: dict[str, str] = {
    "critical": "bold red",
    "high":     "bold yellow",
    "medium":   "",
    "low":      "dim",
}


# ---------------------------------------------------------------------------
# Plan loading helpers
# ---------------------------------------------------------------------------


def _load_plan_file(path: Path) -> PlanSnapshot:
    """Parse a YAML or JSON execution-plan file into a ``PlanSnapshot``."""
    raw: str = path.read_text(encoding="utf-8")

    if path.suffix.lower() in {".yaml", ".yml"}:
        data = yaml.safe_load(raw)
    else:
        data = json.loads(raw)

    # Support both top-level-plan wrapper {"plan": {...}, "tasks": [...]}
    # and a bare task list [...].
    if isinstance(data, list):
        # Bare task list (detect-stale style)
        plan_meta: dict = {"id": path.stem, "title": path.stem, "status": "running"}
        tasks_raw: list = data
    elif isinstance(data, dict) and "plan" in data:
        plan_meta = data.get("plan", {})
        tasks_raw = data.get("tasks", [])
    elif isinstance(data, dict) and "tasks" in data:
        plan_meta = {k: v for k, v in data.items() if k != "tasks"}
        tasks_raw = data.get("tasks", [])
    else:
        raise ValueError(
            f"Unrecognised plan format in {path}: expected a YAML/JSON "
            "dict with 'plan'+'tasks' keys, or a bare task list."
        )

    tasks = [_parse_task(t) for t in tasks_raw]
    counts = _count_tasks(tasks)

    return PlanSnapshot(
        plan_id=str(plan_meta.get("id", path.stem)),
        title=str(plan_meta.get("title", path.stem)),
        status=_normalise_plan_status(plan_meta.get("status", "pending")),
        created_at=_str_or_none(plan_meta.get("created_at")),
        updated_at=_str_or_none(plan_meta.get("updated_at")),
        source_file=str(path),
        task_counts=counts,
        tasks=tasks,
    )


def _parse_task(raw: dict) -> TaskDetail:
    """Map a raw task dict (from YAML/JSON) to a ``TaskDetail``."""
    status_raw = str(raw.get("status", "pending")).lower()
    # Normalise "in_progress" → "running" (state-service vocabulary)
    if status_raw == "in_progress":
        status_raw = "running"
    if status_raw == "completed":
        status_raw = "done"

    lock_raw = str(raw.get("lock_status", "unlocked")).lower()

    return TaskDetail(
        task_id=str(raw.get("id", raw.get("task_id", "?"))),
        title=str(raw.get("title", "")),
        status=status_raw,  # type: ignore[arg-type]
        priority=str(raw.get("priority", "medium")).lower(),  # type: ignore[arg-type]
        assigned_agent=_str_or_none(raw.get("assigned_agent")) or None,
        lock_status=lock_raw,  # type: ignore[arg-type]
        depends_on=list(raw.get("depends_on", [])),
        started_at=_str_or_none(raw.get("started_at")),
        completed_at=_str_or_none(raw.get("completed_at")),
        notes=_str_or_none(raw.get("notes")),
        description=_str_or_none(raw.get("description")),
    )


def _count_tasks(tasks: list[TaskDetail]) -> TaskStatusCounts:
    counts = {"pending": 0, "running": 0, "done": 0, "blocked": 0, "skipped": 0}
    for t in tasks:
        counts[t.status] = counts.get(t.status, 0) + 1
    return TaskStatusCounts(
        total=len(tasks),
        active=counts["running"],
        completed=counts["done"],
        blocked=counts["blocked"],
        pending=counts["pending"],
        skipped=counts["skipped"],
    )


def _normalise_plan_status(raw: object) -> PlanStatusValue:
    mapping = {
        "pending":   "pending",
        "running":   "running",
        "in_progress": "running",
        "done":      "done",
        "completed": "done",
        "blocked":   "blocked",
        "cancelled": "cancelled",
        "canceled":  "cancelled",
    }
    return mapping.get(str(raw).lower(), "pending")  # type: ignore[return-value]


def _str_or_none(val: object) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    return s if s and s.lower() not in {"null", "none", ""} else None


# ---------------------------------------------------------------------------
# State-service fetcher
# ---------------------------------------------------------------------------


def _fetch_state_service_plans(state_url: str) -> tuple[list[PlanSnapshot], bool]:
    """Fetch plans from the claw-forge state service.

    Returns ``(plans, reachable)`` where *reachable* is ``False`` when the
    service could not be contacted.
    """
    base = state_url.rstrip("/")
    plans: list[PlanSnapshot] = []

    try:
        with urlopen(f"{base}/features", timeout=_HTTP_TIMEOUT_S) as resp:
            features = json.loads(resp.read())
    except (URLError, OSError, json.JSONDecodeError):
        return [], False

    # features may be a list of feature/task dicts, or a dict with a list
    if isinstance(features, dict):
        feature_list = features.get("features", features.get("items", [features]))
    else:
        feature_list = features

    # Group features by plan_id if present; fall back to treating all as one plan
    plan_groups: dict[str, list[dict]] = {}
    for feat in feature_list:
        if not isinstance(feat, dict):
            continue
        pid = feat.get("plan_id") or feat.get("plan") or "default"
        plan_groups.setdefault(str(pid), []).append(feat)

    for pid, feats in plan_groups.items():
        tasks = [_parse_task(f) for f in feats]
        counts = _count_tasks(tasks)

        # Derive plan status from task statuses
        if all(t.status == "done" for t in tasks):
            plan_status: PlanStatusValue = "done"
        elif any(t.status == "running" for t in tasks):
            plan_status = "running"
        elif any(t.status == "blocked" for t in tasks):
            plan_status = "blocked"
        else:
            plan_status = "pending"

        plans.append(
            PlanSnapshot(
                plan_id=pid,
                title=feats[0].get("plan_title", pid) if feats else pid,
                status=plan_status,
                source_file=None,
                task_counts=counts,
                tasks=tasks,
            )
        )

    return plans, True


# ---------------------------------------------------------------------------
# Dashboard builder
# ---------------------------------------------------------------------------


def _build_dashboard(
    plans: list[PlanSnapshot],
    *,
    data_source: str,
    state_reachable: Optional[bool],
) -> StatusDashboardResponse:
    """Aggregate plan snapshots into a full ``StatusDashboardResponse``."""
    t = datetime.now(tz=timezone.utc).isoformat()

    total_tasks = sum(p.task_counts.total for p in plans)
    done_tasks  = sum(p.task_counts.completed for p in plans)
    completion  = round(done_tasks / total_tasks * 100, 1) if total_tasks else 0.0

    summary = DashboardSummary(
        total_plans=len(plans),
        active_plans=sum(1 for p in plans if p.status == "running"),
        completed_plans=sum(1 for p in plans if p.status == "done"),
        blocked_plans=sum(1 for p in plans if p.status == "blocked"),
        pending_plans=sum(1 for p in plans if p.status == "pending"),
        cancelled_plans=sum(1 for p in plans if p.status == "cancelled"),
        total_tasks=total_tasks,
        active_tasks=sum(p.task_counts.active for p in plans),
        completed_tasks=done_tasks,
        blocked_tasks=sum(p.task_counts.blocked for p in plans),
        pending_tasks=sum(p.task_counts.pending for p in plans),
        skipped_tasks=sum(p.task_counts.skipped for p in plans),
        overall_completion_pct=completion,
        data_source=data_source,  # type: ignore[arg-type]
        state_service_reachable=state_reachable,
    )

    overall_status = Status.PASSED
    if summary.blocked_plans > 0:
        overall_status = Status.WARNING
    if summary.active_plans == 0 and summary.pending_plans > 0:
        overall_status = Status.RUNNING

    message = (
        f"{summary.total_plans} plan(s) | "
        f"{summary.active_plans} active | "
        f"{summary.completed_plans} done | "
        f"{summary.blocked_plans} blocked | "
        f"{summary.overall_completion_pct}% complete"
    )

    return StatusDashboardResponse(
        status=overall_status,
        timestamp=t,
        message=message,
        summary=summary,
        plans=sorted(plans, key=lambda p: p.plan_id),
    )


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


def _format_json(response: StatusDashboardResponse) -> str:
    return response.model_dump_json(indent=2)


def _format_yaml_output(response: StatusDashboardResponse) -> str:
    data = json.loads(response.model_dump_json())
    return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)


def _print_table_output(response: StatusDashboardResponse) -> None:
    console = Console()
    s = response.summary

    # ── Header ────────────────────────────────────────────────────────────────
    console.print()
    console.print("[bold]harness status[/bold] — Plan Dashboard", highlight=False)
    console.print(
        f"  [dim]{response.timestamp}[/dim]"
        f"  ·  source: [italic]{s.data_source}[/italic]"
    )
    console.print()

    # ── Summary row ───────────────────────────────────────────────────────────
    summary_table = Table(box=box.SIMPLE, show_header=False, expand=False)
    summary_table.add_column("Metric", style="bold dim", min_width=22)
    summary_table.add_column("Value", justify="right", min_width=8)

    summary_table.add_row("Total plans",    str(s.total_plans))
    summary_table.add_row("[cyan]Active[/cyan]",    f"[cyan]{s.active_plans}[/cyan]")
    summary_table.add_row("[green]Completed[/green]", f"[green]{s.completed_plans}[/green]")
    summary_table.add_row("[red]Blocked[/red]",  f"[red]{s.blocked_plans}[/red]")
    summary_table.add_row("Pending",        str(s.pending_plans))
    summary_table.add_row("Cancelled",      str(s.cancelled_plans))
    summary_table.add_row("─" * 22,         "─" * 8)
    summary_table.add_row("Total tasks",    str(s.total_tasks))
    summary_table.add_row("Overall done",   f"[bold]{s.overall_completion_pct}%[/bold]")

    console.print(summary_table)

    if not response.plans:
        console.print("[dim]No plans found.[/dim]")
        console.print()
        return

    # ── Plans overview table ──────────────────────────────────────────────────
    plans_table = Table(
        title="Execution Plans",
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold",
        expand=True,
    )
    plans_table.add_column("Plan ID",   style="bold", min_width=10)
    plans_table.add_column("Title",     min_width=20)
    plans_table.add_column("Status",    min_width=10)
    plans_table.add_column("Tasks",     justify="right", min_width=6)
    plans_table.add_column("Done",      justify="right", min_width=6)
    plans_table.add_column("Active",    justify="right", min_width=6)
    plans_table.add_column("Blocked",   justify="right", min_width=7)
    plans_table.add_column("Done %",    justify="right", min_width=7)
    plans_table.add_column("Source",    min_width=14)

    for plan in response.plans:
        status_style = _PLAN_STATUS_STYLE.get(plan.status, "")
        tc = plan.task_counts
        pct = f"{tc.completion_pct}%"
        source_label = (
            Path(plan.source_file).name if plan.source_file else "state-service"
        )
        plans_table.add_row(
            plan.plan_id,
            plan.title,
            f"[{status_style}]{plan.status}[/{status_style}]",
            str(tc.total),
            str(tc.completed),
            str(tc.active),
            str(tc.blocked),
            pct,
            f"[dim]{source_label}[/dim]",
        )

    console.print(plans_table)

    # ── Per-plan task tables ──────────────────────────────────────────────────
    for plan in response.plans:
        if not plan.tasks:
            continue

        console.print()
        status_style = _PLAN_STATUS_STYLE.get(plan.status, "")
        console.print(
            f"[bold]{plan.plan_id}[/bold] — {plan.title}"
            f"  [[{status_style}]{plan.status}[/{status_style}]]"
        )

        task_table = Table(
            box=box.SIMPLE,
            show_header=True,
            header_style="bold dim",
            expand=True,
        )
        task_table.add_column("",         min_width=3)   # icon
        task_table.add_column("Task ID",  min_width=10)
        task_table.add_column("Title",    min_width=28)
        task_table.add_column("Status",   min_width=9)
        task_table.add_column("Priority", min_width=9)
        task_table.add_column("Agent",    min_width=14)
        task_table.add_column("Deps",     min_width=12)

        for task in plan.tasks:
            icon         = _TASK_STATUS_ICON.get(task.status, "?")
            prio_style   = _PRIORITY_STYLE.get(task.priority, "")
            prio_label   = (
                f"[{prio_style}]{task.priority}[/{prio_style}]"
                if prio_style else task.priority
            )
            agent_label  = task.assigned_agent or "[dim]—[/dim]"
            deps_label   = ", ".join(task.depends_on) if task.depends_on else "[dim]—[/dim]"

            task_table.add_row(
                icon,
                task.task_id,
                task.title,
                task.status,
                prio_label,
                agent_label,
                deps_label,
            )

        console.print(task_table)

    console.print()


# ---------------------------------------------------------------------------
# Click command
# ---------------------------------------------------------------------------


@click.command("status")
@output_format_option(
    help_extra=(
        "json output conforms to the StatusDashboardResponse schema.  "
        "table renders a rich ASCII dashboard for interactive terminal use."
    ),
)
@click.option(
    "--plan-file",
    "plan_files",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    multiple=True,
    help=(
        "Path to a YAML or JSON execution-plan file.  "
        "Repeat the flag to load multiple plans.  "
        "If omitted, plans are fetched from the state service."
    ),
)
@click.option(
    "--state-url",
    default=_DEFAULT_STATE_URL,
    show_default=True,
    envvar="CLAW_FORGE_STATE_URL",
    help=(
        "Base URL of the claw-forge state service.  "
        "Overrideable via the CLAW_FORGE_STATE_URL environment variable."
    ),
)
@click.option(
    "--plan-id",
    "plan_ids",
    multiple=True,
    help=(
        "Filter output to specific plan IDs.  "
        "Repeat to include multiple plans.  "
        "When omitted, all plans are shown."
    ),
)
@click.option(
    "--status-filter",
    "status_filter",
    type=click.Choice(
        ["active", "completed", "blocked", "pending", "cancelled", "all"],
        case_sensitive=False,
    ),
    default="all",
    show_default=True,
    help=(
        "Limit plans shown to those with a specific status.  "
        "'active' = running plans; 'all' = no filter (default)."
    ),
)
@click.option(
    "--no-state-service",
    is_flag=True,
    default=False,
    help=(
        "Skip fetching from the state service even when no --plan-file is given.  "
        "Useful for offline / CI environments."
    ),
)
@click.pass_context
def status_cmd(
    ctx: click.Context,
    output_format: Optional[str],
    plan_files: tuple[Path, ...],
    state_url: str,
    plan_ids: tuple[str, ...],
    status_filter: str,
    no_state_service: bool,
) -> None:
    """Show a status dashboard for all active, completed, and blocked plans.

    Loads execution plans from local YAML/JSON files (``--plan-file``) and/or
    the claw-forge state service, then emits a structured report.

    \b
    Machine-parseable agent pattern (JSON):
        result=$(harness status --format json)
        echo "$result" | jq '.summary.active_plans'
        echo "$result" | jq '.plans[] | select(.status == "blocked")'

    \b
    Filter to blocked plans only:
        harness status --status-filter blocked --format json

    \b
    Load from local plan files:
        harness status --plan-file plan.yaml --plan-file plan2.yaml --format yaml

    \b
    Exit codes:
        0   Report rendered successfully.
        1   No plan data found.
        2   Parse / validation error.
    """
    fmt = resolve_output_format(output_format)
    start_ms = int(time.monotonic() * 1000)
    plans: list[PlanSnapshot] = []
    data_sources: list[str] = []
    state_reachable: Optional[bool] = None

    # ── 1. Load from plan files ───────────────────────────────────────────────
    for path in plan_files:
        try:
            snap = _load_plan_file(path)
            plans.append(snap)
            data_sources.append("file")
        except Exception as exc:  # noqa: BLE001
            click.echo(
                f"[harness status] ERROR loading {path}: {exc}", err=True
            )
            ctx.exit(2)
            return

    # ── 2. Fetch from state service (when no files given or mixed mode) ───────
    if not no_state_service and (not plan_files):
        svc_plans, reachable = _fetch_state_service_plans(state_url)
        state_reachable = reachable
        if reachable:
            plans.extend(svc_plans)
            if svc_plans:
                data_sources.append("state-service")
        else:
            click.echo(
                f"[harness status] State service unreachable at {state_url} "
                "(pass --no-state-service to suppress this warning).",
                err=True,
            )

    # ── 3. Determine data_source label ────────────────────────────────────────
    unique_sources = list(dict.fromkeys(data_sources))
    if not unique_sources:
        source_label = "none"
    elif len(unique_sources) == 1:
        source_label = unique_sources[0]
    else:
        source_label = "mixed"

    # ── 4. Exit early when no plans were found ────────────────────────────────
    if not plans:
        click.echo(
            "[harness status] No plans found.  "
            "Pass --plan-file or ensure the state service has features.",
            err=True,
        )
        ctx.exit(1)
        return

    # ── 5. Apply filters ──────────────────────────────────────────────────────
    if plan_ids:
        plans = [p for p in plans if p.plan_id in plan_ids]

    if status_filter != "all":
        status_map = {
            "active":    "running",
            "completed": "done",
            "blocked":   "blocked",
            "pending":   "pending",
            "cancelled": "cancelled",
        }
        target = status_map.get(status_filter, status_filter)
        plans = [p for p in plans if p.status == target]

    # ── 6. Build dashboard response ───────────────────────────────────────────
    response = _build_dashboard(
        plans,
        data_source=source_label,
        state_reachable=state_reachable,
    )

    end_ms = int(time.monotonic() * 1000)
    response.duration_ms = end_ms - start_ms

    # ── 7. Emit output ────────────────────────────────────────────────────────
    if fmt == "json":
        click.echo(_format_json(response))
    elif fmt == "yaml":
        click.echo(_format_yaml_output(response))
    else:
        _print_table_output(response)
