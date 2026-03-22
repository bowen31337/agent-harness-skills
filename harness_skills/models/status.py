"""Typed response models for the harness status dashboard.

``StatusDashboardResponse`` aggregates one or more execution-plan snapshots into
a single structured report that agents and CI scripts can parse without having
to open individual plan YAML files.

Plans are sourced from:
- Local YAML/JSON plan files (``--plan-file``)
- The claw-forge state service (``GET /features``, ``GET /agents``)

Status vocabulary
-----------------
Plan status : ``pending`` | ``running`` | ``done`` | ``blocked`` | ``cancelled``
Task status : ``pending`` | ``running`` | ``done`` | ``blocked`` | ``skipped``
Lock status : ``unlocked`` | ``locked`` | ``done``
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from harness_skills.models.base import HarnessResponse, Status


# ── Task-level detail ──────────────────────────────────────────────────────────


TaskStatus = Literal["pending", "running", "done", "blocked", "skipped"]
PlanStatusValue = Literal["pending", "running", "done", "blocked", "cancelled"]
LockStatus = Literal["unlocked", "locked", "done"]
Priority = Literal["critical", "high", "medium", "low"]
DepState = Literal["ready", "waiting", "running", "done", "skipped", "blocked"]


class TaskDetail(BaseModel):
    """Full detail for a single task within an execution plan."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    task_id: str = Field(description="Unique task identifier (e.g. TASK-001).")
    title: str = Field(description="Human-readable task title.")
    status: TaskStatus = Field(
        description="Current task status: pending | running | done | blocked | skipped."
    )
    priority: Priority = Field(
        default="medium",
        description="Task priority: critical | high | medium | low.",
    )
    assigned_agent: Optional[str] = Field(
        default=None,
        description="ID of the agent currently responsible for this task, or null.",
    )
    lock_status: LockStatus = Field(
        default="unlocked",
        description="Lock state: unlocked | locked | done.",
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="List of task_ids this task depends on.",
    )
    started_at: Optional[str] = Field(
        default=None,
        description="ISO-8601 UTC timestamp when the task started, or null.",
    )
    completed_at: Optional[str] = Field(
        default=None,
        description="ISO-8601 UTC timestamp when the task completed, or null.",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Free-form notes attached to the task.",
    )
    description: Optional[str] = Field(
        default=None,
        description="Extended description of what the task involves.",
    )
    dep_state: Optional[DepState] = Field(
        default=None,
        description=(
            "Computed dependency state: 'ready' (all deps done or no deps), "
            "'waiting' (one or more deps not yet done), or mirrors the task "
            "status for running/done/blocked/skipped tasks. "
            "Populated by the CLI layer before rendering; null in raw YAML/JSON data."
        ),
    )


# ── Task-count roll-up ─────────────────────────────────────────────────────────


class TaskStatusCounts(BaseModel):
    """Aggregate task counts by status for a single plan."""

    model_config = ConfigDict(extra="forbid")

    total: int = Field(ge=0, description="Total number of tasks in the plan.")
    active: int = Field(
        ge=0,
        description="Tasks with status 'running' (in active execution).",
    )
    completed: int = Field(ge=0, description="Tasks with status 'done'.")
    blocked: int = Field(ge=0, description="Tasks with status 'blocked'.")
    pending: int = Field(
        ge=0,
        description="Tasks with status 'pending' (not yet started).",
    )
    skipped: int = Field(ge=0, description="Tasks with status 'skipped'.")

    @property
    def completion_pct(self) -> float:
        """Percentage of tasks that are done (0–100, rounded to 1 dp)."""
        if self.total == 0:
            return 0.0
        return round(self.completed / self.total * 100, 1)


# ── Plan-level snapshot ────────────────────────────────────────────────────────


class PlanSnapshot(BaseModel):
    """A point-in-time snapshot of a single execution plan."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    plan_id: str = Field(description="Unique plan identifier (e.g. PLAN-001).")
    title: str = Field(description="Human-readable plan title.")
    status: PlanStatusValue = Field(
        description=(
            "Overall plan status: "
            "pending | running | done | blocked | cancelled."
        )
    )
    created_at: Optional[str] = Field(
        default=None,
        description="ISO-8601 UTC timestamp when the plan was created.",
    )
    updated_at: Optional[str] = Field(
        default=None,
        description="ISO-8601 UTC timestamp of the most recent plan update.",
    )
    source_file: Optional[str] = Field(
        default=None,
        description="Path to the YAML/JSON file this plan was loaded from.",
    )
    task_counts: TaskStatusCounts = Field(
        description="Aggregate task counts by status."
    )
    tasks: list[TaskDetail] = Field(
        default_factory=list,
        description="Full detail for every task in the plan.",
    )

    @property
    def active_tasks(self) -> list[TaskDetail]:
        return [t for t in self.tasks if t.status == "running"]

    @property
    def blocked_tasks(self) -> list[TaskDetail]:
        return [t for t in self.tasks if t.status == "blocked"]

    @property
    def completed_tasks(self) -> list[TaskDetail]:
        return [t for t in self.tasks if t.status == "done"]

    @property
    def pending_tasks(self) -> list[TaskDetail]:
        return [t for t in self.tasks if t.status == "pending"]


# ── Dashboard summary (across all plans) ─────────────────────────────────────


class DashboardSummary(BaseModel):
    """Aggregate metrics rolled up across *all* plans in a status response."""

    model_config = ConfigDict(extra="forbid")

    total_plans: int = Field(ge=0, description="Total number of plans included.")
    active_plans: int = Field(
        ge=0,
        description="Plans with status 'running'.",
    )
    completed_plans: int = Field(ge=0, description="Plans with status 'done'.")
    blocked_plans: int = Field(ge=0, description="Plans with status 'blocked'.")
    pending_plans: int = Field(ge=0, description="Plans with status 'pending'.")
    cancelled_plans: int = Field(ge=0, description="Plans with status 'cancelled'.")

    total_tasks: int = Field(ge=0, description="Total tasks across all plans.")
    active_tasks: int = Field(ge=0, description="Tasks currently running.")
    completed_tasks: int = Field(ge=0, description="Tasks that are done.")
    blocked_tasks: int = Field(ge=0, description="Tasks that are blocked.")
    pending_tasks: int = Field(ge=0, description="Tasks not yet started.")
    skipped_tasks: int = Field(ge=0, description="Tasks that were skipped.")

    overall_completion_pct: float = Field(
        ge=0.0,
        le=100.0,
        description="Percentage of all tasks (across all plans) that are done.",
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
            "Whether the claw-forge state service responded to a health probe. "
            "null when no probe was attempted."
        ),
    )


# ── Top-level response ─────────────────────────────────────────────────────────


class StatusDashboardResponse(HarnessResponse):
    """Full response emitted by ``harness status``.

    Contains a per-plan snapshot list, aggregate dashboard metrics, and the
    standard ``HarnessResponse`` envelope fields (``command``, ``status``,
    ``timestamp``, ``duration_ms``, ``version``, ``message``).

    Machine-parseable fields for CI / agent consumers
    --------------------------------------------------
    - ``summary.total_plans``                — total plan count
    - ``summary.active_plans``               — plans currently running
    - ``summary.blocked_plans``              — plans that are blocked
    - ``summary.completed_plans``            — plans that finished
    - ``summary.overall_completion_pct``     — global task completion %
    - ``plans[].status``                     — per-plan status string
    - ``plans[].task_counts.active``         — tasks running in each plan
    - ``plans[].task_counts.blocked``        — tasks blocked in each plan
    - ``plans[].task_counts.completion_pct`` — per-plan task completion %
    - ``plans[].tasks[].status``             — per-task status string
    - ``plans[].tasks[].assigned_agent``     — which agent owns the task
    """

    command: str = "harness status"

    summary: DashboardSummary = Field(
        description="Aggregate metrics rolled up across all plans."
    )
    plans: list[PlanSnapshot] = Field(
        default_factory=list,
        description="Snapshot for each execution plan, ordered by plan_id.",
    )

    # Convenience filter views (computed, not stored)
    @property
    def active_plan_list(self) -> list[PlanSnapshot]:
        return [p for p in self.plans if p.status == "running"]

    @property
    def blocked_plan_list(self) -> list[PlanSnapshot]:
        return [p for p in self.plans if p.status == "blocked"]

    @property
    def completed_plan_list(self) -> list[PlanSnapshot]:
        return [p for p in self.plans if p.status == "done"]
