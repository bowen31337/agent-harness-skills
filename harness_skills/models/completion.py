"""Typed response models for the harness completion-report command.

``PlanCompletionReport`` aggregates one or more execution-plan snapshots into a
structured post-execution report that answers three questions:

1. **What was done?**   — completed tasks with timing and agent attribution.
2. **What debt was incurred?**  — skipped tasks and tasks with debt markers in
   their notes (TODO, FIXME, hack, workaround, etc.).
3. **What follow-up is needed?**  — blocked, pending, and skipped tasks that
   require action after the plan run.

Plans are sourced from:
- Local YAML/JSON plan files (``--plan-file``)
- The claw-forge state service (``GET /features``, ``GET /agents``)
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from harness_skills.models.base import HarnessResponse


# ── Shared type aliases ────────────────────────────────────────────────────────

DebtSeverity = Literal["critical", "high", "medium", "low"]
FollowUpCategory = Literal["blocked", "pending", "skipped", "dependency", "incomplete"]


# ── Completed task summary ─────────────────────────────────────────────────────


class CompletedTaskSummary(BaseModel):
    """Condensed record for a single completed task."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(description="Unique task identifier (e.g. TASK-001).")
    title: str = Field(description="Human-readable task title.")
    plan_id: str = Field(description="Identifier of the parent plan.")
    assigned_agent: Optional[str] = Field(
        default=None,
        description="Agent responsible for the task, or null if unassigned.",
    )
    started_at: Optional[str] = Field(
        default=None,
        description="ISO-8601 UTC timestamp when the task started.",
    )
    completed_at: Optional[str] = Field(
        default=None,
        description="ISO-8601 UTC timestamp when the task completed.",
    )
    duration_min: Optional[float] = Field(
        default=None,
        description=(
            "Wall-clock duration in minutes (rounded to 1 dp), "
            "derived from started_at and completed_at.  null when timestamps "
            "are unavailable."
        ),
    )
    notes: Optional[str] = Field(
        default=None,
        description="Free-form notes attached to the task.",
    )


# ── Technical debt item ────────────────────────────────────────────────────────


class TechnicalDebtItem(BaseModel):
    """A single technical-debt item discovered during plan analysis.

    Debt items are surfaced from two sources:

    * **Skipped tasks** — any task with ``status == "skipped"`` contributes a
      debt item because the skipped work was deferred.
    * **Debt markers in notes** — tasks whose ``notes`` field contains any of
      the following keywords (case-insensitive):
      TODO, FIXME, HACK, DEBT, WORKAROUND, SHORTCUT, INCOMPLETE,
      REVISIT, REFACTOR, TEMPORARY, TEMP, WIP.
    """

    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(description="Identifier of the parent plan.")
    source_task_id: str = Field(description="Task that produced this debt item.")
    source_task_title: str = Field(description="Title of the source task.")
    description: str = Field(description="Human-readable description of the debt.")
    severity: DebtSeverity = Field(
        default="medium",
        description="Estimated severity: critical | high | medium | low.",
    )


# ── Follow-up item ─────────────────────────────────────────────────────────────


class FollowUpItem(BaseModel):
    """A task or action that requires attention after the plan run.

    Follow-up items are generated for every task that was not completed:

    * ``blocked``  — the task is blocked and needs manual unblocking.
    * ``pending``  — the task was never started; it needs scheduling.
    * ``skipped``  — intentionally skipped; should be revisited.
    * ``dependency`` — a blocked task whose dependency is itself unfinished.
    * ``incomplete`` — a running task that did not reach ``done``.
    """

    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(description="Identifier of the parent plan.")
    task_id: str = Field(description="Unique task identifier.")
    title: str = Field(description="Human-readable task title.")
    category: FollowUpCategory = Field(
        description=(
            "Why follow-up is needed: "
            "blocked | pending | skipped | dependency | incomplete."
        )
    )
    priority: str = Field(
        default="medium",
        description="Task priority: critical | high | medium | low.",
    )
    reason: Optional[str] = Field(
        default=None,
        description="Short explanation of why follow-up is required.",
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="Task IDs that must be resolved before this task can proceed.",
    )
    assigned_agent: Optional[str] = Field(
        default=None,
        description="Agent last assigned to this task, or null if unassigned.",
    )


# ── Per-plan completion summary ────────────────────────────────────────────────


class PlanCompletionSummary(BaseModel):
    """High-level completion metrics for a single execution plan."""

    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(description="Unique plan identifier.")
    title: str = Field(description="Human-readable plan title.")
    status: str = Field(description="Final plan status.")
    total_tasks: int = Field(ge=0, description="Total tasks in the plan.")
    completed_tasks: int = Field(ge=0, description="Tasks with status 'done'.")
    skipped_tasks: int = Field(ge=0, description="Tasks with status 'skipped'.")
    blocked_tasks: int = Field(ge=0, description="Tasks with status 'blocked'.")
    pending_tasks: int = Field(ge=0, description="Tasks with status 'pending'.")
    running_tasks: int = Field(
        ge=0,
        description="Tasks still in 'running' state (incomplete at report time).",
    )
    completion_pct: float = Field(
        ge=0.0, le=100.0, description="Percentage of tasks that are done (0–100)."
    )
    debt_item_count: int = Field(
        ge=0, description="Number of technical-debt items identified in this plan."
    )
    follow_up_count: int = Field(
        ge=0, description="Number of follow-up items identified in this plan."
    )


# ── Cross-plan aggregate summary ──────────────────────────────────────────────


class CompletionReportSummary(BaseModel):
    """Aggregate metrics rolled up across *all* plans in a completion report."""

    model_config = ConfigDict(extra="forbid")

    total_plans: int = Field(ge=0, description="Total number of plans analysed.")
    fully_completed_plans: int = Field(
        ge=0,
        description="Plans where every task reached 'done' status.",
    )
    partial_plans: int = Field(
        ge=0,
        description="Plans with at least one non-done task.",
    )

    total_tasks: int = Field(ge=0, description="Total tasks across all plans.")
    completed_tasks: int = Field(ge=0, description="Tasks with status 'done'.")
    skipped_tasks: int = Field(ge=0, description="Tasks with status 'skipped'.")
    blocked_tasks: int = Field(ge=0, description="Tasks with status 'blocked'.")
    pending_tasks: int = Field(ge=0, description="Tasks not yet started.")
    running_tasks: int = Field(
        ge=0,
        description="Tasks still marked 'running' at report time.",
    )

    overall_completion_pct: float = Field(
        ge=0.0,
        le=100.0,
        description="Percentage of all tasks that are done (0–100).",
    )

    total_debt_items: int = Field(
        ge=0, description="Total technical-debt items across all plans."
    )
    total_follow_up_items: int = Field(
        ge=0, description="Total follow-up items across all plans."
    )

    data_source: Literal["file", "state-service", "mixed", "none"] = Field(
        default="none",
        description=(
            "Where plan data was loaded from: "
            "file = local YAML/JSON, "
            "state-service = claw-forge REST API, "
            "mixed = both sources, "
            "none = no plans found."
        ),
    )
    state_service_reachable: Optional[bool] = Field(
        default=None,
        description=(
            "Whether the claw-forge state service responded to a health probe.  "
            "null when no probe was attempted."
        ),
    )


# ── Top-level response ─────────────────────────────────────────────────────────


class PlanCompletionReport(HarnessResponse):
    """Full response emitted by ``harness completion-report``.

    Contains per-plan completion summaries, a list of completed tasks with
    timing data, identified technical-debt items, and follow-up action items —
    all wrapped in the standard ``HarnessResponse`` envelope.

    Machine-parseable fields for CI / agent consumers
    --------------------------------------------------
    - ``summary.overall_completion_pct``  — global task completion %
    - ``summary.total_debt_items``        — debt count (0 = no debt incurred)
    - ``summary.total_follow_up_items``   — follow-up action count
    - ``summary.fully_completed_plans``   — plans with 100 % done
    - ``completed_tasks[]``               — every done task with timing
    - ``debt[]``                          — debt items ordered by severity
    - ``follow_up[]``                     — follow-up items ordered by priority
    - ``plans[].completion_pct``          — per-plan task completion %
    - ``plans[].debt_item_count``         — debt items per plan
    - ``plans[].follow_up_count``         — follow-up items per plan
    """

    command: str = "harness completion-report"

    summary: CompletionReportSummary = Field(
        description="Aggregate metrics rolled up across all plans."
    )
    plans: list[PlanCompletionSummary] = Field(
        default_factory=list,
        description="Per-plan completion summary, ordered by plan_id.",
    )
    completed_tasks: list[CompletedTaskSummary] = Field(
        default_factory=list,
        description="All completed tasks across every plan, ordered by plan_id then task_id.",
    )
    debt: list[TechnicalDebtItem] = Field(
        default_factory=list,
        description=(
            "Technical-debt items identified during analysis, "
            "ordered by severity (critical first) then plan_id."
        ),
    )
    follow_up: list[FollowUpItem] = Field(
        default_factory=list,
        description=(
            "Follow-up action items for unresolved tasks, "
            "ordered by category then priority then plan_id."
        ),
    )

    # ── Convenience views ──────────────────────────────────────────────────────

    @property
    def critical_debt(self) -> list[TechnicalDebtItem]:
        """All debt items with severity ``critical``."""
        return [d for d in self.debt if d.severity == "critical"]

    @property
    def blocked_follow_up(self) -> list[FollowUpItem]:
        """Follow-up items for blocked tasks."""
        return [f for f in self.follow_up if f.category == "blocked"]
