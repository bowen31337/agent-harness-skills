"""harness completion-report — post-execution plan completion report.

Produces a structured report that answers three questions about one or more
finished (or partially finished) execution plans:

1. **What was done?**
   Every task that reached ``done`` status, with timing and agent attribution.

2. **What technical debt was incurred?**
   Skipped tasks and tasks whose notes contain debt markers such as TODO,
   FIXME, HACK, WORKAROUND, etc.

3. **What follow-up is needed?**
   Blocked, pending, skipped, and still-running tasks that require action
   after the plan run.

Usage (CLI):
    harness completion-report [--output-format json|yaml|table]
                              [--plan-file PATH ...]
                              [--state-url URL]
                              [--plan-id PLAN_ID ...]
                              [--no-state-service]
                              [--min-debt-severity critical|high|medium|low]

Usage (agent tool call):
    harness completion-report --output-format json
    harness completion-report --output-format json --plan-file plan.yaml

Machine-parseable fields:
    .summary.overall_completion_pct   — global task completion %
    .summary.total_debt_items         — total debt items (0 = clean run)
    .summary.total_follow_up_items    — total follow-up actions required
    .completed_tasks[]                — every completed task with timing
    .debt[]                           — technical-debt items by severity
    .follow_up[]                      — follow-up action items by priority

Exit codes:
    0   Report rendered successfully.
    1   No plan data found (no files given, state service unreachable).
    2   Internal error (parse failure, schema validation error).
"""

from __future__ import annotations

import json
import re
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

from harness_skills.cli.fmt import output_format_option, resolve_output_format
from harness_skills.models.base import Status
from harness_skills.models.completion import (
    CompletedTaskSummary,
    CompletionReportSummary,
    DebtSeverity,
    FollowUpItem,
    PlanCompletionReport,
    PlanCompletionSummary,
    TechnicalDebtItem,
)
from harness_skills.models.status import (
    PlanSnapshot,
    PlanStatusValue,
    TaskDetail,
    TaskStatusCounts,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_STATE_URL = "http://localhost:8888"
_HTTP_TIMEOUT_S = 5

# Keywords that, when found in task notes, signal technical debt
_DEBT_KEYWORDS: tuple[str, ...] = (
    "todo",
    "fixme",
    "hack",
    "debt",
    "workaround",
    "shortcut",
    "incomplete",
    "revisit",
    "refactor",
    "temporary",
    "temp",
    "wip",
)

_DEBT_KEYWORD_RE = re.compile(
    r"\b(" + "|".join(_DEBT_KEYWORDS) + r")\b",
    re.IGNORECASE,
)

# Severity ordering for sorting (lower index = more severe)
_SEVERITY_ORDER: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}

# Priority ordering for follow-up sorting
_PRIORITY_ORDER: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}

_DEBT_SEVERITY_STYLE: dict[str, str] = {
    "critical": "bold red",
    "high": "bold yellow",
    "medium": "bold",
    "low": "dim",
}

_FOLLOW_UP_CATEGORY_ICON: dict[str, str] = {
    "blocked": "🔴",
    "pending": "⬜",
    "skipped": "⏭️",
    "dependency": "🔗",
    "incomplete": "🔵",
}

_PLAN_STATUS_STYLE: dict[str, str] = {
    "running": "bold cyan",
    "done": "bold green",
    "blocked": "bold red",
    "pending": "dim",
    "cancelled": "dim italic",
}


# ---------------------------------------------------------------------------
# Plan loading (shared with status; reproduced here to keep modules independent)
# ---------------------------------------------------------------------------


def _load_plan_file(path: Path) -> PlanSnapshot:
    """Parse a YAML or JSON execution-plan file into a ``PlanSnapshot``."""
    raw: str = path.read_text(encoding="utf-8")

    if path.suffix.lower() in {".yaml", ".yml"}:
        data = yaml.safe_load(raw)
    else:
        data = json.loads(raw)

    if isinstance(data, list):
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
        "pending": "pending",
        "running": "running",
        "in_progress": "running",
        "done": "done",
        "completed": "done",
        "blocked": "blocked",
        "cancelled": "cancelled",
        "canceled": "cancelled",
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
    """Fetch plans from the claw-forge state service."""
    base = state_url.rstrip("/")
    plans: list[PlanSnapshot] = []

    try:
        with urlopen(f"{base}/features", timeout=_HTTP_TIMEOUT_S) as resp:
            features = json.loads(resp.read())
    except (URLError, OSError, json.JSONDecodeError):
        return [], False

    if isinstance(features, dict):
        feature_list = features.get("features", features.get("items", [features]))
    else:
        feature_list = features

    plan_groups: dict[str, list[dict]] = {}
    for feat in feature_list:
        if not isinstance(feat, dict):
            continue
        pid = feat.get("plan_id") or feat.get("plan") or "default"
        plan_groups.setdefault(str(pid), []).append(feat)

    for pid, feats in plan_groups.items():
        tasks = [_parse_task(f) for f in feats]
        counts = _count_tasks(tasks)

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
# Debt detection helpers
# ---------------------------------------------------------------------------


def _debt_severity_from_priority(priority: str) -> DebtSeverity:
    """Map task priority to a debt severity level."""
    mapping: dict[str, DebtSeverity] = {
        "critical": "critical",
        "high": "high",
        "medium": "medium",
        "low": "low",
    }
    return mapping.get(priority.lower(), "medium")


def _extract_debt_items(
    plan: PlanSnapshot,
    min_severity: str,
) -> list[TechnicalDebtItem]:
    """Scan all tasks in *plan* and return any technical-debt items found."""
    items: list[TechnicalDebtItem] = []
    min_order = _SEVERITY_ORDER.get(min_severity, 2)

    for task in plan.tasks:
        severity: DebtSeverity = _debt_severity_from_priority(task.priority)

        # Skipped tasks are always debt
        if task.status == "skipped":
            if _SEVERITY_ORDER.get(severity, 2) <= min_order:
                items.append(
                    TechnicalDebtItem(
                        plan_id=plan.plan_id,
                        source_task_id=task.task_id,
                        source_task_title=task.title,
                        description=(
                            f"Task was skipped and not completed: {task.title}."
                            + (f"  Notes: {task.notes}" if task.notes else "")
                        ),
                        severity=severity,
                    )
                )

        # Tasks with debt-marker keywords in their notes
        elif task.notes and _DEBT_KEYWORD_RE.search(task.notes):
            if _SEVERITY_ORDER.get(severity, 2) <= min_order:
                match = _DEBT_KEYWORD_RE.search(task.notes)
                keyword = match.group(0).upper() if match else "NOTE"
                items.append(
                    TechnicalDebtItem(
                        plan_id=plan.plan_id,
                        source_task_id=task.task_id,
                        source_task_title=task.title,
                        description=(
                            f"{keyword} in task notes: {task.notes}"
                        ),
                        severity=severity,
                    )
                )

    return items


# ---------------------------------------------------------------------------
# Follow-up item extraction
# ---------------------------------------------------------------------------


def _extract_follow_up_items(plan: PlanSnapshot) -> list[FollowUpItem]:
    """Return follow-up action items for every unresolved task in *plan*."""
    items: list[FollowUpItem] = []

    for task in plan.tasks:
        if task.status == "done":
            continue

        if task.status == "blocked":
            # Determine whether it is blocked due to an incomplete dependency
            category = (
                "dependency"
                if task.depends_on
                else "blocked"
            )
            reason = (
                f"Blocked; depends on: {', '.join(task.depends_on)}"
                if task.depends_on
                else "Task is blocked."
            )
        elif task.status == "pending":
            category = "pending"
            reason = "Task was not started."
        elif task.status == "skipped":
            category = "skipped"
            reason = "Task was skipped during execution."
        elif task.status == "running":
            category = "incomplete"
            reason = "Task was still running when the report was generated."
        else:
            continue

        items.append(
            FollowUpItem(
                plan_id=plan.plan_id,
                task_id=task.task_id,
                title=task.title,
                category=category,  # type: ignore[arg-type]
                priority=task.priority,
                reason=reason,
                depends_on=list(task.depends_on),
                assigned_agent=task.assigned_agent,
            )
        )

    return items


# ---------------------------------------------------------------------------
# Duration computation
# ---------------------------------------------------------------------------


def _duration_min(started_at: Optional[str], completed_at: Optional[str]) -> Optional[float]:
    """Compute task duration in minutes from ISO-8601 timestamps."""
    if not started_at or not completed_at:
        return None
    try:
        start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
        delta = (end - start).total_seconds()
        return round(delta / 60, 1) if delta >= 0 else None
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


def _build_report(
    plans: list[PlanSnapshot],
    *,
    data_source: str,
    state_reachable: Optional[bool],
    min_debt_severity: str,
) -> PlanCompletionReport:
    """Build a ``PlanCompletionReport`` from a list of plan snapshots."""
    ts = datetime.now(tz=timezone.utc).isoformat()

    all_completed: list[CompletedTaskSummary] = []
    all_debt: list[TechnicalDebtItem] = []
    all_follow_up: list[FollowUpItem] = []
    plan_summaries: list[PlanCompletionSummary] = []

    for plan in sorted(plans, key=lambda p: p.plan_id):
        debt_items = _extract_debt_items(plan, min_debt_severity)
        follow_up_items = _extract_follow_up_items(plan)

        for task in plan.tasks:
            if task.status == "done":
                all_completed.append(
                    CompletedTaskSummary(
                        task_id=task.task_id,
                        title=task.title,
                        plan_id=plan.plan_id,
                        assigned_agent=task.assigned_agent,
                        started_at=task.started_at,
                        completed_at=task.completed_at,
                        duration_min=_duration_min(task.started_at, task.completed_at),
                        notes=task.notes,
                    )
                )

        all_debt.extend(debt_items)
        all_follow_up.extend(follow_up_items)

        tc = plan.task_counts
        completion_pct = (
            round(tc.completed / tc.total * 100, 1) if tc.total else 0.0
        )

        plan_summaries.append(
            PlanCompletionSummary(
                plan_id=plan.plan_id,
                title=plan.title,
                status=plan.status,
                total_tasks=tc.total,
                completed_tasks=tc.completed,
                skipped_tasks=tc.skipped,
                blocked_tasks=tc.blocked,
                pending_tasks=tc.pending,
                running_tasks=tc.active,
                completion_pct=completion_pct,
                debt_item_count=len(debt_items),
                follow_up_count=len(follow_up_items),
            )
        )

    # ── Sort debt by severity ─────────────────────────────────────────────────
    all_debt.sort(key=lambda d: (_SEVERITY_ORDER.get(d.severity, 2), d.plan_id))

    # ── Sort follow-up by category priority then task priority ────────────────
    _cat_order = {"blocked": 0, "dependency": 1, "incomplete": 2, "skipped": 3, "pending": 4}
    all_follow_up.sort(
        key=lambda f: (
            _cat_order.get(f.category, 9),
            _PRIORITY_ORDER.get(f.priority, 2),
            f.plan_id,
        )
    )

    # ── Aggregate summary ─────────────────────────────────────────────────────
    total_tasks = sum(p.task_counts.total for p in plans)
    done_tasks = sum(p.task_counts.completed for p in plans)
    overall_pct = round(done_tasks / total_tasks * 100, 1) if total_tasks else 0.0

    fully_completed = sum(
        1 for p in plans if p.task_counts.completed == p.task_counts.total and p.task_counts.total > 0
    )

    summary = CompletionReportSummary(
        total_plans=len(plans),
        fully_completed_plans=fully_completed,
        partial_plans=len(plans) - fully_completed,
        total_tasks=total_tasks,
        completed_tasks=done_tasks,
        skipped_tasks=sum(p.task_counts.skipped for p in plans),
        blocked_tasks=sum(p.task_counts.blocked for p in plans),
        pending_tasks=sum(p.task_counts.pending for p in plans),
        running_tasks=sum(p.task_counts.active for p in plans),
        overall_completion_pct=overall_pct,
        total_debt_items=len(all_debt),
        total_follow_up_items=len(all_follow_up),
        data_source=data_source,  # type: ignore[arg-type]
        state_service_reachable=state_reachable,
    )

    # ── Overall status heuristic ──────────────────────────────────────────────
    if summary.blocked_tasks > 0 or summary.total_debt_items > 0:
        overall_status = Status.WARNING
    elif summary.overall_completion_pct >= 100.0:
        overall_status = Status.PASSED
    else:
        overall_status = Status.WARNING

    message = (
        f"{summary.total_plans} plan(s) | "
        f"{summary.overall_completion_pct}% done | "
        f"{summary.total_debt_items} debt item(s) | "
        f"{summary.total_follow_up_items} follow-up(s)"
    )

    return PlanCompletionReport(
        status=overall_status,
        timestamp=ts,
        message=message,
        summary=summary,
        plans=plan_summaries,
        completed_tasks=all_completed,
        debt=all_debt,
        follow_up=all_follow_up,
    )


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


def _format_json(report: PlanCompletionReport) -> str:
    return report.model_dump_json(indent=2)


def _format_yaml_output(report: PlanCompletionReport) -> str:
    data = json.loads(report.model_dump_json())
    return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)


def _print_table_output(report: PlanCompletionReport) -> None:  # noqa: C901
    console = Console()
    s = report.summary

    # ── Header ────────────────────────────────────────────────────────────────
    console.print()
    console.print(
        "[bold]harness completion-report[/bold] — Plan Completion Report",
        highlight=False,
    )
    console.print(
        f"  [dim]{report.timestamp}[/dim]"
        f"  ·  source: [italic]{s.data_source}[/italic]"
    )
    console.print()

    # ── Overview ──────────────────────────────────────────────────────────────
    overview = Table(box=box.SIMPLE, show_header=False, expand=False)
    overview.add_column("Metric", style="bold dim", min_width=28)
    overview.add_column("Value", justify="right", min_width=8)

    overview.add_row("Total plans", str(s.total_plans))
    overview.add_row(
        "[green]Fully completed[/green]",
        f"[green]{s.fully_completed_plans}[/green]",
    )
    overview.add_row("Partial", str(s.partial_plans))
    overview.add_row("─" * 28, "─" * 8)
    overview.add_row("Total tasks", str(s.total_tasks))
    overview.add_row(
        "[green]Completed[/green]",
        f"[green]{s.completed_tasks}[/green]",
    )
    overview.add_row("[yellow]Skipped[/yellow]", f"[yellow]{s.skipped_tasks}[/yellow]")
    overview.add_row("[red]Blocked[/red]", f"[red]{s.blocked_tasks}[/red]")
    overview.add_row("Pending", str(s.pending_tasks))
    overview.add_row("Still running", str(s.running_tasks))
    overview.add_row("─" * 28, "─" * 8)
    overview.add_row(
        "Overall completion",
        f"[bold]{s.overall_completion_pct}%[/bold]",
    )
    overview.add_row(
        "[yellow]Debt items[/yellow]",
        f"[yellow]{s.total_debt_items}[/yellow]",
    )
    overview.add_row(
        "Follow-up items",
        str(s.total_follow_up_items),
    )
    console.print(overview)

    # ── Per-plan table ────────────────────────────────────────────────────────
    if report.plans:
        plans_table = Table(
            title="Plan Summary",
            box=box.SIMPLE_HEAVY,
            show_header=True,
            header_style="bold",
            expand=True,
        )
        plans_table.add_column("Plan ID", style="bold", min_width=10)
        plans_table.add_column("Title", min_width=20)
        plans_table.add_column("Status", min_width=10)
        plans_table.add_column("Done %", justify="right", min_width=7)
        plans_table.add_column("Tasks", justify="right", min_width=6)
        plans_table.add_column("Done", justify="right", min_width=6)
        plans_table.add_column("Blocked", justify="right", min_width=7)
        plans_table.add_column("Debt", justify="right", min_width=5)
        plans_table.add_column("Follow-up", justify="right", min_width=9)

        for ps in report.plans:
            status_style = _PLAN_STATUS_STYLE.get(ps.status, "")
            plans_table.add_row(
                ps.plan_id,
                ps.title,
                f"[{status_style}]{ps.status}[/{status_style}]",
                f"{ps.completion_pct}%",
                str(ps.total_tasks),
                str(ps.completed_tasks),
                str(ps.blocked_tasks),
                f"[yellow]{ps.debt_item_count}[/yellow]" if ps.debt_item_count else "0",
                str(ps.follow_up_count),
            )

        console.print(plans_table)

    # ── Completed tasks table ─────────────────────────────────────────────────
    if report.completed_tasks:
        done_table = Table(
            title="Completed Tasks",
            box=box.SIMPLE,
            show_header=True,
            header_style="bold dim",
            expand=True,
        )
        done_table.add_column("Plan", min_width=10)
        done_table.add_column("Task ID", min_width=10)
        done_table.add_column("Title", min_width=28)
        done_table.add_column("Agent", min_width=14)
        done_table.add_column("Duration", justify="right", min_width=10)

        for ct in report.completed_tasks:
            dur = f"{ct.duration_min} min" if ct.duration_min is not None else "[dim]—[/dim]"
            agent = ct.assigned_agent or "[dim]—[/dim]"
            done_table.add_row(
                ct.plan_id,
                ct.task_id,
                ct.title,
                agent,
                dur,
            )

        console.print(done_table)

    # ── Technical debt table ──────────────────────────────────────────────────
    if report.debt:
        debt_table = Table(
            title="Technical Debt",
            box=box.SIMPLE,
            show_header=True,
            header_style="bold dim",
            expand=True,
        )
        debt_table.add_column("Severity", min_width=10)
        debt_table.add_column("Plan", min_width=10)
        debt_table.add_column("Task", min_width=10)
        debt_table.add_column("Task Title", min_width=22)
        debt_table.add_column("Description", min_width=40)

        for item in report.debt:
            sev_style = _DEBT_SEVERITY_STYLE.get(item.severity, "")
            sev_label = (
                f"[{sev_style}]{item.severity}[/{sev_style}]"
                if sev_style else item.severity
            )
            debt_table.add_row(
                sev_label,
                item.plan_id,
                item.source_task_id,
                item.source_task_title,
                item.description,
            )

        console.print(debt_table)
    else:
        console.print("[green]No technical debt items identified.[/green]")
        console.print()

    # ── Follow-up table ───────────────────────────────────────────────────────
    if report.follow_up:
        fu_table = Table(
            title="Follow-Up Required",
            box=box.SIMPLE,
            show_header=True,
            header_style="bold dim",
            expand=True,
        )
        fu_table.add_column("", min_width=3)  # icon
        fu_table.add_column("Category", min_width=12)
        fu_table.add_column("Plan", min_width=10)
        fu_table.add_column("Task ID", min_width=10)
        fu_table.add_column("Title", min_width=26)
        fu_table.add_column("Priority", min_width=9)
        fu_table.add_column("Reason", min_width=32)

        for item in report.follow_up:
            icon = _FOLLOW_UP_CATEGORY_ICON.get(item.category, "?")
            fu_table.add_row(
                icon,
                item.category,
                item.plan_id,
                item.task_id,
                item.title,
                item.priority,
                item.reason or "[dim]—[/dim]",
            )

        console.print(fu_table)
    else:
        console.print("[green]No follow-up items required.[/green]")
        console.print()

    console.print()


# ---------------------------------------------------------------------------
# Click command
# ---------------------------------------------------------------------------


@click.command("completion-report")
@output_format_option(
    help_extra=(
        "json output conforms to the PlanCompletionReport schema.  "
        "table renders a rich ASCII report for interactive terminal use."
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
    "--no-state-service",
    is_flag=True,
    default=False,
    help=(
        "Skip fetching from the state service even when no --plan-file is given.  "
        "Useful for offline / CI environments."
    ),
)
@click.option(
    "--min-debt-severity",
    "min_debt_severity",
    type=click.Choice(["critical", "high", "medium", "low"], case_sensitive=False),
    default="low",
    show_default=True,
    help=(
        "Minimum debt-item severity to include in the report.  "
        "'low' = include all debt items (default).  "
        "'high' = only high and critical debt.  "
        "'critical' = only critical debt."
    ),
)
@click.pass_context
def completion_report_cmd(
    ctx: click.Context,
    output_format: Optional[str],
    plan_files: tuple[Path, ...],
    state_url: str,
    plan_ids: tuple[str, ...],
    no_state_service: bool,
    min_debt_severity: str,
) -> None:
    """Generate a post-execution plan completion report.

    Produces a structured report summarising what was done, what technical
    debt was incurred, and what follow-up actions are required.

    \b
    What was done (completed_tasks[]):
        Every task that reached 'done' status, with timing and agent info.

    \b
    What debt was incurred (debt[]):
        Skipped tasks and tasks with TODO / FIXME / HACK markers in notes.

    \b
    What follow-up is needed (follow_up[]):
        Blocked, pending, skipped, and still-running tasks.

    \b
    Machine-parseable agent pattern (JSON):
        result=$(harness completion-report --output-format json --plan-file plan.yaml)
        echo "$result" | jq '.summary.overall_completion_pct'
        echo "$result" | jq '.debt[] | select(.severity == "critical")'
        echo "$result" | jq '.follow_up[] | select(.category == "blocked")'

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
                f"[harness completion-report] ERROR loading {path}: {exc}", err=True
            )
            ctx.exit(2)
            return

    # ── 2. Fetch from state service (when no files given) ─────────────────────
    if not no_state_service and not plan_files:
        svc_plans, reachable = _fetch_state_service_plans(state_url)
        state_reachable = reachable
        if reachable:
            plans.extend(svc_plans)
            if svc_plans:
                data_sources.append("state-service")
        else:
            click.echo(
                f"[harness completion-report] State service unreachable at {state_url} "
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
            "[harness completion-report] No plans found.  "
            "Pass --plan-file or ensure the state service has features.",
            err=True,
        )
        ctx.exit(1)
        return

    # ── 5. Apply plan-ID filter ───────────────────────────────────────────────
    if plan_ids:
        plans = [p for p in plans if p.plan_id in plan_ids]

    # ── 6. Build report ───────────────────────────────────────────────────────
    report = _build_report(
        plans,
        data_source=source_label,
        state_reachable=state_reachable,
        min_debt_severity=min_debt_severity,
    )

    end_ms = int(time.monotonic() * 1000)
    report.duration_ms = end_ms - start_ms

    # ── 7. Emit output ────────────────────────────────────────────────────────
    if fmt == "json":
        click.echo(_format_json(report))
    elif fmt == "yaml":
        click.echo(_format_yaml_output(report))
    else:
        _print_table_output(report)
