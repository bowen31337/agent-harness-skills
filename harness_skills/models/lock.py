"""Pydantic models for the Task Lock Protocol state-service integration.

These models describe the payloads exchanged with the claw-forge state service
(``http://localhost:8888``) when an agent acquires, extends, or releases a task
lock.  They complement the file-based ``TaskLock`` / ``TaskLockProtocol`` in
``harness_skills/task_lock.py`` by providing a typed, validated wire format for
the REST layer.

Endpoint summary
----------------
  PATCH /features/{task_id}          — acquire / extend / release a lock
  GET   /features/{task_id}/lock     — inspect the current lock on one task
  GET   /features/locks              — list all active locks across all tasks

Wire payload shapes
-------------------
  acquire  →  LockAcquireRequest
  extend   →  LockExtendRequest
  release  →  LockReleaseRequest
  response ←  LockStateResponse  (for single-task inspection)
  response ←  LockListResponse   (for /features/locks)
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# ── Inbound request models (agent → state service) ───────────────────────────


class LockAcquireRequest(BaseModel):
    """Payload sent to the state service when an agent acquires a task lock.

    Sent as:  PATCH /features/{task_id}
    Body:     {"lock_action": "acquire", "agent_id": "...", "timeout_seconds": 300}
    """

    model_config = ConfigDict(extra="forbid")

    lock_action: Literal["acquire"] = Field(
        default="acquire",
        description="Discriminator field — always 'acquire' for this request type.",
    )
    agent_id: str = Field(
        description="Identifier of the agent requesting the lock."
    )
    timeout_seconds: float = Field(
        default=300.0,
        gt=0,
        description=(
            "Lock TTL in seconds.  The state service auto-expires the lock "
            "after this duration even if the agent never explicitly releases it. "
            "Default: 300 s (5 minutes).  Maximum: 3600 s (1 hour)."
        ),
    )
    acquired_at: Optional[str] = Field(
        default=None,
        description=(
            "ISO-8601 UTC timestamp when the file-based lock was acquired.  "
            "Supplied by the agent so the server clock is not the sole source "
            "of truth.  When omitted the state service uses its own clock."
        ),
    )


class LockExtendRequest(BaseModel):
    """Payload sent when an agent needs more time on an already-held lock.

    Sent as:  PATCH /features/{task_id}
    Body:     {"lock_action": "extend", "agent_id": "...", "additional_seconds": 120}
    """

    model_config = ConfigDict(extra="forbid")

    lock_action: Literal["extend"] = Field(
        default="extend",
        description="Discriminator field — always 'extend' for this request type.",
    )
    agent_id: str = Field(
        description="Must match the agent that currently holds the lock.",
    )
    additional_seconds: float = Field(
        gt=0,
        description="Number of seconds to add to the current lock TTL.",
    )


class LockReleaseRequest(BaseModel):
    """Payload sent when an agent finishes work and surrenders the lock.

    Sent as:  PATCH /features/{task_id}
    Body:     {"lock_action": "release", "agent_id": "...", "outcome": "done"}
    """

    model_config = ConfigDict(extra="forbid")

    lock_action: Literal["release"] = Field(
        default="release",
        description="Discriminator field — always 'release' for this request type.",
    )
    agent_id: str = Field(
        description="Must match the agent that currently holds the lock.",
    )
    outcome: Literal["done", "failed", "skipped", "handed-off"] = Field(
        default="done",
        description=(
            "What happened to the task.  "
            "'done' — completed successfully; "
            "'failed' — agent encountered an unrecoverable error; "
            "'skipped' — agent deliberately skipped the task; "
            "'handed-off' — task is being passed to another agent."
        ),
    )
    notes: Optional[str] = Field(
        default=None,
        description="Optional free-form notes recorded alongside the release event.",
    )


# ── Outbound response models (state service → agent) ────────────────────────


class LockRecord(BaseModel):
    """Canonical lock record returned by the state service."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(description="Unique plan task identifier.")
    agent_id: str = Field(description="Agent currently holding the lock.")
    acquired_at: str = Field(description="ISO-8601 UTC timestamp of acquisition.")
    expires_at: str = Field(description="ISO-8601 UTC timestamp of auto-expiry.")
    timeout_seconds: float = Field(gt=0, description="Configured TTL in seconds.")
    state_service_url: Optional[str] = Field(
        default=None,
        description="URL of the state service that registered this lock.",
    )

    def seconds_remaining(self, now_iso: str | None = None) -> float:
        """Compute remaining TTL.  Pass ``now_iso`` in tests to fix the clock."""
        from datetime import datetime, timezone

        expires = datetime.fromisoformat(self.expires_at)
        if now_iso:
            now = datetime.fromisoformat(now_iso)
        else:
            now = datetime.now(timezone.utc)
        return (expires - now).total_seconds()

    def is_expired(self, now_iso: str | None = None) -> bool:
        return self.seconds_remaining(now_iso) <= 0


class LockStateResponse(BaseModel):
    """Response from GET /features/{task_id}/lock — single-task lock inspection."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(description="Task whose lock was queried.")
    locked: bool = Field(description="True when an active (non-expired) lock exists.")
    lock: Optional[LockRecord] = Field(
        default=None,
        description="Full lock record when ``locked`` is True; null otherwise.",
    )
    message: Optional[str] = Field(
        default=None,
        description="Human-readable status message from the state service.",
    )


class LockOperationResponse(BaseModel):
    """Response from PATCH /features/{task_id} for acquire / extend / release."""

    model_config = ConfigDict(extra="forbid")

    success: bool = Field(
        description="True when the requested lock operation completed successfully."
    )
    action: Literal["acquire", "extend", "release"] = Field(
        description="The operation that was attempted.",
    )
    task_id: str = Field(description="Target task identifier.")
    lock: Optional[LockRecord] = Field(
        default=None,
        description=(
            "The resulting lock record after the operation.  "
            "Present after acquire/extend; null after release."
        ),
    )
    conflict_holder: Optional[LockRecord] = Field(
        default=None,
        description=(
            "When ``success`` is False and the operation was 'acquire', "
            "this field contains the lock held by the blocking agent."
        ),
    )
    message: Optional[str] = Field(
        default=None,
        description="Human-readable result message.",
    )


class LockListResponse(BaseModel):
    """Response from GET /features/locks — all active locks across all tasks."""

    model_config = ConfigDict(extra="forbid")

    snapshot_time: str = Field(
        description="ISO-8601 UTC timestamp when the lock list was captured.",
    )
    total_active: int = Field(
        ge=0,
        description="Number of non-expired locks currently held.",
    )
    locks: list[LockRecord] = Field(
        default_factory=list,
        description="All active lock records, ordered by acquired_at ascending.",
    )
