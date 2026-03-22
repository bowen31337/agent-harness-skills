"""Stale execution-plan detector powered by the Anthropic Claude API.

Usage
-----
Run as a standalone script::

    python -m harness_skills.stale_plan_detector \\
        --plan-file plan.json \\
        --threshold 1800          # 30 minutes (default)
        --api-key  sk-ant-...     # falls back to ANTHROPIC_API_KEY env var

Or call programmatically::

    from harness_skills.stale_plan_detector import detect_stale_plan, PlanTask
    from datetime import datetime, timezone, timedelta

    tasks = [
        PlanTask(
            task_id="t1",
            title="Implement auth module",
            status="in_progress",
            assigned_agent="agent-alpha",
            last_updated=datetime.now(tz=timezone.utc) - timedelta(hours=2),
        ),
    ]
    response = detect_stale_plan(tasks, threshold_seconds=1800)
    print(response.model_dump_json(indent=2))

How staleness severity is assigned
-----------------------------------
Given a threshold T (default 1 800 s / 30 min):

    idle < 2T  →  INFO
    idle < 4T  →  WARNING
    idle < 8T  →  ERROR
    idle ≥ 8T  →  CRITICAL
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

import anthropic
import click
from pydantic import BaseModel, ConfigDict, Field

from harness_skills.models.base import Severity, Status
from harness_skills.models.stale import (
    ArtifactResult,
    ArtifactStaleness,
    StalePlanResponse,
    StalePlanSummary,
    StaleTask,
)

# ── Default configuration ──────────────────────────────────────────────────────

DEFAULT_THRESHOLD_SECONDS: float = 1800.0   # 30 minutes
DEFAULT_MODEL: str = "claude-opus-4-6"
DEFAULT_PLAN_ID: str = "default-plan"
DEFAULT_ARTIFACT_THRESHOLD_DAYS: int = 30

# Canonical artifact files every harness project should maintain
_CANONICAL_ARTIFACTS: tuple[str, ...] = (
    "AGENTS.md",
    "ARCHITECTURE.md",
    "PRINCIPLES.md",
    "EVALUATION.md",
)

# Pattern that matches `last_updated: YYYY-MM-DD` in front-matter
_LAST_UPDATED_RE = re.compile(r"^last_updated:\s*(\d{4}-\d{2}-\d{2})", re.MULTILINE)


# ── Artifact freshness scanner ─────────────────────────────────────────────────


def _artifact_severity(
    age_days: int | None,
    threshold_days: int,
    *,
    missing: bool = False,
    no_timestamp: bool = False,
) -> str:
    """Return the freshness severity label for a single artifact."""
    if missing:
        return "ERROR"
    if no_timestamp or age_days is None:
        return "WARNING"
    if age_days <= threshold_days:
        return "healthy"
    if age_days <= 2 * threshold_days:
        return "INFO"
    if age_days <= 4 * threshold_days:
        return "WARNING"
    return "CRITICAL"


def scan_artifact_freshness(
    *,
    threshold_days: int = DEFAULT_ARTIFACT_THRESHOLD_DAYS,
    base_dir: str | Path | None = None,
    today: date | None = None,
) -> ArtifactStaleness:
    """Scan canonical harness artifact files for staleness.

    Parameters
    ----------
    threshold_days:
        Maximum age (in calendar days) before an artifact is considered stale.
    base_dir:
        Directory to search for artifact files.  Defaults to the current
        working directory (``Path.cwd()``).
    today:
        Reference date for age calculation.  Defaults to ``date.today()``.
        Pass an explicit value in tests to get deterministic results.

    Returns
    -------
    ArtifactStaleness
        Fully populated freshness report, ready to embed in ``StalePlanResponse``.
    """
    base = Path(base_dir) if base_dir else Path.cwd()
    ref_today = today or date.today()

    results: list[ArtifactResult] = []

    # Collect canonical top-level artifacts + any AGENTS.md in subdirectories
    files_to_check: list[str] = list(_CANONICAL_ARTIFACTS)
    for sub_agents in sorted(base.rglob("AGENTS.md")):
        rel = str(sub_agents.relative_to(base))
        if rel not in files_to_check and not _is_ignored_path(rel):
            files_to_check.append(rel)

    for rel_path in files_to_check:
        full_path = base / rel_path

        if not full_path.exists():
            results.append(
                ArtifactResult(file=rel_path, last_updated=None, age_days=None, severity="ERROR")
            )
            continue

        try:
            content = full_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            results.append(
                ArtifactResult(file=rel_path, last_updated=None, age_days=None, severity="ERROR")
            )
            continue

        m = _LAST_UPDATED_RE.search(content)
        if not m:
            results.append(
                ArtifactResult(file=rel_path, last_updated=None, age_days=None, severity="WARNING")
            )
            continue

        date_str = m.group(1)
        try:
            updated = date.fromisoformat(date_str)
        except ValueError:
            results.append(
                ArtifactResult(file=rel_path, last_updated=date_str, age_days=None, severity="WARNING")
            )
            continue

        age_days = (ref_today - updated).days
        severity = _artifact_severity(age_days, threshold_days)
        results.append(
            ArtifactResult(
                file=rel_path,
                last_updated=date_str,
                age_days=age_days,
                severity=severity,
            )
        )

    stale_count = sum(1 for r in results if r.severity != "healthy")
    missing_count = sum(1 for r in results if r.severity == "ERROR")

    return ArtifactStaleness(
        threshold_days=threshold_days,
        artifacts_checked=len(results),
        stale_artifacts=stale_count,
        missing_artifacts=missing_count,
        results=results,
    )


def _is_ignored_path(rel: str) -> bool:
    """Return True for paths under well-known ignore directories."""
    ignored_prefixes = (".git/", "node_modules/", ".venv/", ".claw-forge/")
    return any(rel.startswith(p) for p in ignored_prefixes)


# ── Input schema ───────────────────────────────────────────────────────────────


class PlanTask(BaseModel):
    """A single task from an execution plan, as provided by the caller."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    task_id: str
    title: str
    status: Literal["pending", "in_progress", "completed", "blocked"]
    assigned_agent: str | None = None
    last_updated: datetime = Field(
        description="UTC timestamp of the most recent progress update on this task."
    )
    depends_on: list[str] = Field(default_factory=list)


# ── Severity calculation ───────────────────────────────────────────────────────


def _severity_for_idle(idle_seconds: float, threshold: float) -> Severity:
    """Map idle duration → severity bucket."""
    if idle_seconds < 2 * threshold:
        return Severity.INFO
    if idle_seconds < 4 * threshold:
        return Severity.WARNING
    if idle_seconds < 8 * threshold:
        return Severity.ERROR
    return Severity.CRITICAL


# ── LLM analysis ──────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an expert engineering-process analyst embedded in an agent harness system.
Your job is to diagnose *why* an execution plan has stalled and recommend concrete,
actionable recovery steps.

Rules:
- Be specific about each stale task.  Name the task ID and assigned agent.
- Identify likely root causes (blocked dependency, resource contention, agent crash,
  unclear acceptance criteria, etc.).
- Recommend exactly ONE primary action per stale task.
- If all stale tasks share a single root cause, say so and give a single unified fix.
- Keep the total response under 400 words.
- Output plain prose — no markdown headers, no bullet lists.
"""

_USER_TEMPLATE = """\
Execution plan "{plan_id}" has {stale_count} stale task(s) out of {total} total.
Staleness threshold: {threshold_s:.0f} seconds.

Stale tasks (most critical first):
{task_lines}

Provide a concise narrative diagnosis and recovery recommendation.
"""


def _build_task_lines(stale_tasks: list[StaleTask]) -> str:
    lines: list[str] = []
    for t in sorted(stale_tasks, key=lambda x: -x.idle_seconds):
        agent_str = f"agent={t.assigned_agent}" if t.assigned_agent else "unassigned"
        lines.append(
            f"  [{t.severity.upper()}] {t.task_id} ({t.title!r}) — "
            f"status={t.status}, {agent_str}, "
            f"idle={t.idle_seconds:.0f}s"
        )
    return "\n".join(lines)


def _stream_llm_analysis(
    stale_tasks: list[StaleTask],
    summary: StalePlanSummary,
    client: anthropic.Anthropic,
    model: str,
) -> str:
    """Stream a narrative analysis from Claude; return the full text."""
    task_lines = _build_task_lines(stale_tasks)
    user_message = _USER_TEMPLATE.format(
        plan_id=summary.plan_id,
        stale_count=summary.stale_tasks,
        total=summary.total_tasks,
        threshold_s=summary.threshold_seconds,
        task_lines=task_lines,
    )

    full_text: list[str] = []

    click.echo("  ↳ Streaming LLM analysis…", err=True)

    with client.messages.stream(
        model=model,
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        for event in stream:
            if event.type == "content_block_delta":
                delta = event.delta
                if delta.type == "text_delta":
                    full_text.append(delta.text)
                    # Live progress indicator on stderr so JSON stdout stays clean
                    click.echo(delta.text, nl=False, err=True)

        # Flush the live indicator line
        click.echo("", err=True)

    return "".join(full_text)


# ── Core detection logic ───────────────────────────────────────────────────────


def detect_stale_plan(
    tasks: list[PlanTask],
    *,
    threshold_seconds: float = DEFAULT_THRESHOLD_SECONDS,
    plan_id: str = DEFAULT_PLAN_ID,
    model: str = DEFAULT_MODEL,
    api_key: str | None = None,
    skip_llm: bool = False,
    skip_artifacts: bool = False,
    artifact_threshold_days: int = DEFAULT_ARTIFACT_THRESHOLD_DAYS,
    artifact_base_dir: str | Path | None = None,
    now: datetime | None = None,
    today: date | None = None,
) -> StalePlanResponse:
    """Detect stale tasks in an execution plan and optionally analyse them with Claude.

    Parameters
    ----------
    tasks:
        All tasks in the execution plan.
    threshold_seconds:
        Tasks idle longer than this are flagged as stale.
    plan_id:
        Identifier used in the response and passed to the LLM.
    model:
        Anthropic model ID for the LLM analysis step.
    api_key:
        Anthropic API key.  Falls back to ``ANTHROPIC_API_KEY`` env var.
    skip_llm:
        If *True*, skip the Claude analysis step (useful for offline tests).
    skip_artifacts:
        If *True*, omit the artifact freshness scan from the response.
    artifact_threshold_days:
        Maximum artifact age (days) before flagging as stale.
    artifact_base_dir:
        Root directory to search for artifact files.  Defaults to ``Path.cwd()``.
    now:
        Reference timestamp for computing idle durations.  Defaults to
        ``datetime.now(tz=timezone.utc)`` at call time.  Pass an explicit
        value in tests to freeze time and get deterministic results.
    today:
        Reference date for artifact age calculation.  Defaults to ``date.today()``.
        Pass an explicit value in tests to get deterministic results.

    Returns
    -------
    StalePlanResponse
        Fully populated, schema-validated Pydantic response object.
    """
    start_ns = time.monotonic_ns()
    now = now if now is not None else datetime.now(tz=timezone.utc)

    # ── 1. Classify each task ──────────────────────────────────────────────────
    stale_task_details: list[StaleTask] = []

    for task in tasks:
        # Skip tasks that are already done — they cannot be "stale"
        if task.status == "completed":
            continue

        last_updated = task.last_updated
        if last_updated.tzinfo is None:
            last_updated = last_updated.replace(tzinfo=timezone.utc)

        idle_seconds = (now - last_updated).total_seconds()
        if idle_seconds <= threshold_seconds:
            continue  # healthy

        severity = _severity_for_idle(idle_seconds, threshold_seconds)
        stale_task_details.append(
            StaleTask(
                task_id=task.task_id,
                title=task.title,
                status=task.status,
                assigned_agent=task.assigned_agent,
                last_updated=last_updated,
                idle_seconds=round(idle_seconds, 2),
                threshold_seconds=threshold_seconds,
                severity=severity,
            )
        )

    # ── 2. Build plan-level summary ────────────────────────────────────────────
    total_tasks = len(tasks)
    stale_count = len(stale_task_details)
    healthy_count = total_tasks - stale_count

    # Determine overall health bucket
    if stale_count == 0:
        overall_health: Literal["healthy", "degraded", "critical"] = "healthy"
    elif stale_count / max(total_tasks, 1) >= 0.5:
        overall_health = "critical"
    else:
        overall_health = "degraded"

    # Find the most idle task
    most_idle: StaleTask | None = (
        max(stale_task_details, key=lambda t: t.idle_seconds)
        if stale_task_details
        else None
    )

    summary = StalePlanSummary(
        plan_id=plan_id,
        total_tasks=total_tasks,
        stale_tasks=stale_count,
        healthy_tasks=healthy_count,
        threshold_seconds=threshold_seconds,
        most_idle_task_id=most_idle.task_id if most_idle else None,
        max_idle_seconds=most_idle.idle_seconds if most_idle else None,
        overall_health=overall_health,
    )

    # ── 3. LLM narrative analysis (streaming) ─────────────────────────────────
    llm_analysis: str | None = None

    if stale_task_details and not skip_llm:
        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not resolved_key:
            click.echo(
                "WARNING: ANTHROPIC_API_KEY not set — skipping LLM analysis.", err=True
            )
        else:
            client = anthropic.Anthropic(api_key=resolved_key)
            try:
                llm_analysis = _stream_llm_analysis(
                    stale_task_details, summary, client, model
                )
            except anthropic.APIError as exc:
                click.echo(f"WARNING: LLM analysis failed — {exc}", err=True)

    # ── 4. Attach per-task LLM recommendations (if analysis ran) ──────────────
    # The full narrative is stored in llm_analysis; individual recommendations
    # are left as None unless a caller wants to parse and distribute them.

    # ── 5. Determine top-level status ─────────────────────────────────────────
    top_status = Status.FAILED if stale_count > 0 else Status.PASSED
    top_message = (
        f"{stale_count} stale task(s) detected in plan '{plan_id}'."
        if stale_count > 0
        else None
    )

    # ── 6. Artifact freshness scan ─────────────────────────────────────────────
    artifact_staleness_result: ArtifactStaleness | None = None
    if not skip_artifacts:
        artifact_staleness_result = scan_artifact_freshness(
            threshold_days=artifact_threshold_days,
            base_dir=artifact_base_dir,
            today=today,
        )

    duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000

    return StalePlanResponse(
        command="harness detect-stale",
        status=top_status,
        message=top_message,
        duration_ms=int(duration_ms),
        summary=summary,
        stale_task_details=stale_task_details,
        llm_analysis=llm_analysis,
        analysis_model=model if llm_analysis else None,
        artifact_staleness=artifact_staleness_result,
    )


# ── CLI entry-point ────────────────────────────────────────────────────────────


@click.command("detect-stale")
@click.option(
    "--plan-file",
    "-f",
    required=True,
    type=click.Path(exists=True, readable=True),
    help=(
        "Path to a JSON file containing an array of task objects.  "
        "Each object must have: task_id, title, status, last_updated (ISO-8601), "
        "and optionally assigned_agent, depends_on."
    ),
)
@click.option(
    "--threshold",
    "-t",
    default=DEFAULT_THRESHOLD_SECONDS,
    show_default=True,
    type=float,
    help="Staleness threshold in seconds.  Tasks idle longer than this are flagged.",
)
@click.option(
    "--plan-id",
    default=DEFAULT_PLAN_ID,
    show_default=True,
    help="Identifier for the execution plan (used in the response envelope).",
)
@click.option(
    "--model",
    default=DEFAULT_MODEL,
    show_default=True,
    help="Anthropic model to use for the narrative analysis.",
)
@click.option(
    "--api-key",
    default=None,
    envvar="ANTHROPIC_API_KEY",
    help="Anthropic API key.  Falls back to ANTHROPIC_API_KEY environment variable.",
)
@click.option(
    "--skip-llm",
    is_flag=True,
    default=False,
    help="Skip the Claude LLM analysis step (fast, offline-friendly).",
)
@click.option(
    "--pretty",
    is_flag=True,
    default=False,
    help="Pretty-print the JSON output (2-space indent).",
)
@click.option(
    "--artifact-threshold-days",
    default=DEFAULT_ARTIFACT_THRESHOLD_DAYS,
    show_default=True,
    type=int,
    help="Max artifact age in days before flagging as stale.",
)
@click.option(
    "--skip-artifacts",
    is_flag=True,
    default=False,
    help="Skip the artifact freshness scan entirely.",
)
def cli(
    plan_file: str,
    threshold: float,
    plan_id: str,
    model: str,
    api_key: str | None,
    skip_llm: bool,
    pretty: bool,
    artifact_threshold_days: int,
    skip_artifacts: bool,
) -> None:
    """Detect stale tasks in an execution plan and (optionally) analyse them with Claude.

    Exits with code 0 when all tasks are healthy, 1 when stale tasks are detected,
    and 2 on input errors.

    \b
    Example plan.json:
        [
          {
            "task_id": "t1",
            "title": "Scaffold auth module",
            "status": "in_progress",
            "assigned_agent": "agent-alpha",
            "last_updated": "2026-03-13T08:00:00Z"
          }
        ]
    """
    # ── Load & validate plan file ──────────────────────────────────────────────
    try:
        with open(plan_file) as fh:
            raw = json.load(fh)
    except json.JSONDecodeError as exc:
        click.echo(f"ERROR: Could not parse {plan_file}: {exc}", err=True)
        sys.exit(2)

    if not isinstance(raw, list):
        click.echo("ERROR: Plan file must contain a JSON array of task objects.", err=True)
        sys.exit(2)

    try:
        tasks = [PlanTask.model_validate(item) for item in raw]
    except Exception as exc:  # noqa: BLE001
        click.echo(f"ERROR: Invalid task object in plan file: {exc}", err=True)
        sys.exit(2)

    # ── Run detector ───────────────────────────────────────────────────────────
    click.echo(
        f"Detecting stale tasks in '{plan_id}' "
        f"({len(tasks)} tasks, threshold={threshold:.0f}s)…",
        err=True,
    )

    response = detect_stale_plan(
        tasks,
        threshold_seconds=threshold,
        plan_id=plan_id,
        model=model,
        api_key=api_key,
        skip_llm=skip_llm,
        skip_artifacts=skip_artifacts,
        artifact_threshold_days=artifact_threshold_days,
    )

    # ── Emit structured JSON to stdout ─────────────────────────────────────────
    indent = 2 if pretty else None
    click.echo(response.model_dump_json(indent=indent))

    # Exit 1 if any tasks are stale so CI pipelines can gate on the result
    sys.exit(0 if response.summary.stale_tasks == 0 else 1)


if __name__ == "__main__":
    cli()
