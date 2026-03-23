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
    DocumentationDrift,
    SourceFileDrift,
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

# File extensions whose files are tracked for drift detection
_TRACKED_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".ts", ".tsx", ".js", ".jsx",
    ".go", ".rs", ".java", ".rb",
    ".yaml", ".yml", ".json", ".toml", ".cfg", ".ini",
    ".sh", ".bash",
    ".md", ".txt", ".rst",
    ".sql", ".html", ".css", ".scss",
})

# Directories to ignore when validating referenced-file existence
_DRIFT_SKIP_DIRS: frozenset[str] = frozenset({
    ".git", "node_modules", ".venv", "venv", "__pycache__",
    ".claw-forge", ".mypy_cache", ".ruff_cache", "dist", "build",
})

# Regex: inline backtick code span  (single line only)
_BACKTICK_RE = re.compile(r"`([^`\n]+)`")

# Regex: Python "from x.y.z import ..." — captures the dotted module name
_PY_FROM_IMPORT_RE = re.compile(
    r"\bfrom\s+([\w][\w]*(?:\.[\w]+)+)\s+import",
    re.MULTILINE,
)

# Regex: explicit file paths with known extensions in text / code blocks
_EXPLICIT_FILE_RE = re.compile(
    r"\b((?:[\w][\w\-]*/)*[\w][\w.\-]*"
    r"\.(?:py|ts|tsx|js|jsx|go|rs|java|yaml|yml|json|toml|cfg|ini|sh|md|txt|sql|html|css|scss))\b"
)


def _is_ignored_path(rel: str) -> bool:
    """Return True for paths under well-known ignore directories."""
    ignored_prefixes = (".git/", "node_modules/", ".venv/", ".claw-forge/")
    return any(rel.startswith(p) for p in ignored_prefixes)


def _module_to_path(module: str) -> str:
    """Convert a Python dotted module name to a relative file path.

    Example: ``'tests.browser.agent_driver'`` → ``'tests/browser/agent_driver.py'``
    """
    return module.replace(".", "/") + ".py"


def _extract_file_references(content: str) -> list[str]:
    """Extract source-file path references from a markdown artifact's content.

    Detects three reference patterns:

    1. **Python import statements** — ``from tests.browser.agent_driver import …``
       is mapped to ``tests/browser/agent_driver.py``.
    2. **Backtick code spans** — content inside `` `…` `` that ends with a
       tracked file extension (e.g., `` `requirements.txt` ``).
    3. **Explicit file-path patterns** — bare paths with known extensions
       appearing in prose or code blocks.

    Returns a deduplicated, sorted list of relative path strings.
    URLs, version numbers, and other non-path patterns are excluded.
    """
    candidates: set[str] = set()

    # 1. Python from-import → module path
    for m in _PY_FROM_IMPORT_RE.finditer(content):
        candidates.add(_module_to_path(m.group(1)))

    # 2. Backtick spans — take those ending with a tracked extension
    for m in _BACKTICK_RE.finditer(content):
        span = m.group(1).strip().lstrip("./")
        _, ext = os.path.splitext(span)
        if ext.lower() in _TRACKED_EXTENSIONS:
            # Reject spans that look like commands/shell lines
            if not any(c in span for c in (" ", "\t", ";", "|", "&", ">")):
                candidates.add(span)

    # 3. Explicit file-path patterns in plain text / code
    for m in _EXPLICIT_FILE_RE.finditer(content):
        path = m.group(1).lstrip("./")
        if path:
            candidates.add(path)

    # Post-filter: remove URLs, version-like strings, and whitespace-containing
    result: set[str] = set()
    for path in candidates:
        if " " in path or "://" in path:
            continue
        # Skip bare version numbers like "3.12" or "2.0.0"
        if re.match(r"^\d+\.\d", path):
            continue
        # Skip paths whose first segment is a known skip-dir
        first_part = path.split("/")[0]
        if first_part in _DRIFT_SKIP_DIRS or first_part.startswith("."):
            continue
        result.add(path)

    return sorted(result)


def _check_source_drift(
    referenced_files: list[str],
    last_updated: date | None,
    base_dir: Path,
) -> tuple[list[str], list[SourceFileDrift]]:
    """Identify which referenced source files are missing or have drifted.

    A file is considered *drifted* when it exists and its modification date is
    strictly after the artifact's ``last_updated`` date.

    Parameters
    ----------
    referenced_files:
        Relative paths extracted from the artifact's content.
    last_updated:
        The artifact's ``last_updated`` date.  When ``None`` drift direction
        cannot be determined, so only missing-file detection runs.
    base_dir:
        Repository root used to resolve relative paths.

    Returns
    -------
    missing_files:
        Paths from ``referenced_files`` that do not exist on disk.
    drifted_files:
        ``SourceFileDrift`` records for files newer than ``last_updated``.
    """
    missing_files: list[str] = []
    drifted_files: list[SourceFileDrift] = []

    for path in referenced_files:
        if _is_ignored_path(path):
            continue

        full_path = base_dir / path
        if not full_path.exists():
            missing_files.append(path)
            continue

        if not full_path.is_file():
            continue  # directories are not individually trackable

        mtime_date = date.fromtimestamp(full_path.stat().st_mtime)

        if last_updated is not None:
            days_newer = (mtime_date - last_updated).days
            if days_newer > 0:
                drifted_files.append(
                    SourceFileDrift(
                        path=path,
                        exists=True,
                        mtime_date=mtime_date.isoformat(),
                        days_newer_than_doc=days_newer,
                    )
                )

    return missing_files, drifted_files


def _compute_staleness_score(
    age_days: int | None,
    threshold_days: int,
    drift_ratio: float,
) -> float:
    """Compute a composite staleness score in ``[0.0, 1.0]``.

    The score blends **artifact age** (60 % weight, saturates at 4 × threshold)
    with **source-file drift ratio** (40 % weight).

    - ``0.0`` = completely fresh, no referenced files have drifted.
    - ``1.0`` = severely old and all referenced files have been modified.
    """
    if age_days is None:
        age_score = 0.5  # unknown age → moderate penalty
    else:
        age_score = min(1.0, age_days / max(4.0 * threshold_days, 1.0))

    return round(0.6 * age_score + 0.4 * drift_ratio, 3)


# ── Artifact freshness scanner ─────────────────────────────────────────────────


def _artifact_severity(age_days: int, threshold_days: int) -> str:
    """Map artifact age → severity string (includes 'healthy' baseline)."""
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
    skip_drift: bool = False,
) -> ArtifactStaleness:
    """Scan canonical harness artifact files for staleness.

    In addition to age-based staleness (comparing ``last_updated`` against
    ``threshold_days``), this function performs **drift detection**: it extracts
    all source-file paths that each artifact references and checks whether any
    of those files have been modified since the artifact was last updated.

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
    skip_drift:
        When ``True``, skip source-file drift detection (faster; no mtime
        calls).  ``ArtifactResult.drift`` will be ``None`` for all results.

    Returns
    -------
    ArtifactStaleness
        Fully populated freshness report with drift analysis, ready to embed
        in ``StalePlanResponse``.
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
                ArtifactResult(
                    file=rel_path,
                    last_updated=None,
                    age_days=None,
                    severity="ERROR",
                    drift=None,
                    staleness_score=1.0,
                )
            )
            continue

        try:
            content = full_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            results.append(
                ArtifactResult(
                    file=rel_path,
                    last_updated=None,
                    age_days=None,
                    severity="ERROR",
                    drift=None,
                    staleness_score=1.0,
                )
            )
            continue

        m = _LAST_UPDATED_RE.search(content)
        if not m:
            score = _compute_staleness_score(None, threshold_days, 0.0)
            results.append(
                ArtifactResult(
                    file=rel_path,
                    last_updated=None,
                    age_days=None,
                    severity="WARNING",
                    drift=None,
                    staleness_score=score,
                )
            )
            continue

        date_str = m.group(1)
        try:
            updated = date.fromisoformat(date_str)
        except ValueError:
            score = _compute_staleness_score(None, threshold_days, 0.0)
            results.append(
                ArtifactResult(
                    file=rel_path,
                    last_updated=date_str,
                    age_days=None,
                    severity="WARNING",
                    drift=None,
                    staleness_score=score,
                )
            )
            continue

        age_days = (ref_today - updated).days
        severity = _artifact_severity(age_days, threshold_days)

        # ── Drift detection ────────────────────────────────────────────────────
        drift_result: DocumentationDrift | None = None
        if not skip_drift:
            referenced = _extract_file_references(content)
            # Exclude the artifact file itself from its own drift check
            referenced = [r for r in referenced if r != rel_path]

            missing, drifted = _check_source_drift(referenced, updated, base)

            drift_count = len(missing) + len(drifted)
            drift_ratio = drift_count / max(len(referenced), 1) if referenced else 0.0
            staleness_score = _compute_staleness_score(age_days, threshold_days, drift_ratio)

            drift_result = DocumentationDrift(
                referenced_files=referenced,
                missing_files=missing,
                drifted_files=drifted,
                drift_ratio=round(drift_ratio, 3),
                staleness_score=staleness_score,
            )
        else:
            staleness_score = _compute_staleness_score(age_days, threshold_days, 0.0)

        results.append(
            ArtifactResult(
                file=rel_path,
                last_updated=date_str,
                age_days=age_days,
                severity=severity,
                drift=drift_result,
                staleness_score=staleness_score,
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


# ── Human-readable report renderer ────────────────────────────────────────────

_SEP = "━" * 54
_THIN = "─" * 52

# Severity → display icon + label
_SEVERITY_ICONS: dict[str, str] = {
    "CRITICAL": "🔴 CRITICAL",
    "critical": "🔴 CRITICAL",
    "ERROR":    "🟠 ERROR",
    "error":    "🟠 ERROR",
    "WARNING":  "🟡 WARNING",
    "warning":  "🟡 WARNING",
    "INFO":     "🔵 INFO",
    "info":     "🔵 INFO",
}

_ARTIFACT_ICONS: dict[str, str] = {
    "healthy":  "✅",
    "INFO":     "🔵",
    "WARNING":  "🟡",
    "ERROR":    "🟠",
    "CRITICAL": "🔴",
}


def _render_human_report(response: StalePlanResponse) -> None:  # noqa: C901
    """Print a human-readable staleness report to stderr."""
    s = response.summary
    health = s.overall_health

    # ── Banner ─────────────────────────────────────────────────────────────────
    if health == "healthy":
        status_line = "✅ HEALTHY"
    elif health == "critical":
        status_line = "🔴 CRITICAL"
    else:
        status_line = "⚠ DEGRADED"

    click.echo(_SEP, err=True)
    click.echo(f"  Stale Plan Detector — {status_line}", err=True)
    click.echo(
        f"  Plan: {s.plan_id}  ·  {s.total_tasks} tasks  ·  threshold: {s.threshold_seconds:.0f}s",
        err=True,
    )
    if health != "healthy":
        click.echo(
            f"  {s.stale_tasks} stale  ·  {s.healthy_tasks} healthy",
            err=True,
        )
    click.echo(_SEP, err=True)

    # ── All-healthy shortcut ───────────────────────────────────────────────────
    if health == "healthy":
        click.echo(f"  ✅ All {s.total_tasks} tasks are making progress.", err=True)
        click.echo(_SEP, err=True)
    else:
        # ── Stale task table ───────────────────────────────────────────────────
        click.echo("", err=True)
        click.echo("Stale Tasks (most idle first)", err=True)
        click.echo(_THIN, err=True)

        sorted_tasks = sorted(response.stale_task_details, key=lambda t: -t.idle_seconds)
        for t in sorted_tasks:
            severity_val = t.severity.value if hasattr(t.severity, "value") else str(t.severity)
            icon = _SEVERITY_ICONS.get(severity_val.upper(), severity_val.upper())
            agent_str = t.assigned_agent or "unassigned"
            multiplier = t.idle_seconds / t.threshold_seconds if t.threshold_seconds else 0
            click.echo(
                f"  {icon:<14}  {t.task_id}  \"{t.title}\"",
                err=True,
            )
            click.echo(
                f"               status={t.status}  agent={agent_str}",
                err=True,
            )
            click.echo(
                f"               idle={t.idle_seconds:.0f}s  ({multiplier:.1f}× threshold)",
                err=True,
            )
            click.echo("", err=True)

        click.echo(_SEP, err=True)

    # ── LLM analysis ───────────────────────────────────────────────────────────
    if response.llm_analysis:
        model_label = response.analysis_model or "unknown model"
        click.echo(f"  Claude Analysis  (model: {model_label})", err=True)
        click.echo(f"  {'─' * 41}", err=True)
        # Indent each line of the narrative
        for line in response.llm_analysis.splitlines():
            click.echo(f"  {line}", err=True)
        click.echo(_SEP, err=True)

    # ── Artifact freshness ─────────────────────────────────────────────────────
    if response.artifact_staleness is not None:
        af = response.artifact_staleness
        click.echo(_SEP, err=True)
        click.echo(f"  Artifact Freshness  (threshold: {af.threshold_days} days)", err=True)
        click.echo(_SEP, err=True)
        for r in af.results:
            icon = _ARTIFACT_ICONS.get(r.severity, "❓")
            age_str = f"age={r.age_days}d" if r.age_days is not None else "age=?"
            date_str = f"last_updated={r.last_updated}" if r.last_updated else "last_updated=MISSING"
            sev_suffix = f"  {r.severity}" if r.severity not in ("healthy",) else ""
            score_str = f"  score={r.staleness_score:.3f}" if r.staleness_score is not None else ""
            click.echo(
                f"  {icon}  {r.file:<22}  {date_str:<30}  {age_str}{sev_suffix}{score_str}",
                err=True,
            )
            # ── Drift detail (indented) ────────────────────────────────────────
            if r.drift is not None and (r.drift.drifted_files or r.drift.missing_files):
                d = r.drift
                total_refs = len(d.referenced_files)
                drift_files_count = len(d.drifted_files) + len(d.missing_files)
                click.echo(
                    f"      ↳ drift: {drift_files_count}/{total_refs} referenced file(s) changed"
                    f"  (ratio={d.drift_ratio:.0%})",
                    err=True,
                )
                for df in sorted(d.drifted_files, key=lambda x: -(x.days_newer_than_doc or 0)):
                    click.echo(
                        f"         📝  {df.path}  ({df.days_newer_than_doc}d newer)",
                        err=True,
                    )
                for mf in d.missing_files:
                    click.echo(f"         ❌  {mf}  (missing)", err=True)
        click.echo(_SEP, err=True)
        if af.stale_artifacts:
            click.echo(f"  {af.stale_artifacts} stale artifact(s) found", err=True)
            click.echo("  → Run /harness:update to refresh all artifact timestamps.", err=True)
        else:
            click.echo("  ✅ All artifacts are fresh.", err=True)
        click.echo(_SEP, err=True)

    # ── Recovery recommendations ───────────────────────────────────────────────
    health_val = health if isinstance(health, str) else health.value
    if health_val == "healthy":
        click.echo("  ✅ No action needed — all tasks are making progress.", err=True)
    elif health_val == "degraded":
        click.echo(
            "  ⚠  Recommended: Investigate WARNING/ERROR tasks; ping assigned agents.",
            err=True,
        )
    else:
        click.echo(
            "  🔴 Recommended: Immediately reassign or restart stale tasks.",
            err=True,
        )
        click.echo(
            "     Check for deadlocks via /coordinate.",
            err=True,
        )

    # If any task is blocked, suggest /coordinate
    blocked = [t for t in response.stale_task_details if t.status == "blocked"]
    if blocked:
        ids = ", ".join(t.task_id for t in blocked)
        click.echo(
            f"  ℹ  Blocked task(s) detected ({ids}): run /coordinate to check dependencies.",
            err=True,
        )

    click.echo(_SEP, err=True)


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

    # ── Render human-readable report to stderr ─────────────────────────────────
    _render_human_report(response)

    # ── Emit structured JSON to stdout ─────────────────────────────────────────
    indent = 2 if pretty else None
    click.echo(response.model_dump_json(indent=indent))

    # Exit 1 if any tasks are stale so CI pipelines can gate on the result
    sys.exit(0 if response.summary.stale_tasks == 0 else 1)


if __name__ == "__main__":
    cli()
