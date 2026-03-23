"""
Stale Plan Detector
===================
Monitors Claude Agent SDK execution plans and flags any that have received
no progress updates beyond a configurable threshold.

Usage
-----
    python stale_plan_detector.py

Configuration
-------------
Set STALE_THRESHOLD_SECONDS (default: 30) to control how long a plan may
be silent before it is considered stale.
"""

from __future__ import annotations

import anyio
import asyncio
import time
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any

from claude_agent_sdk import (
    ClaudeAgentOptions,
    HookMatcher,
    ResultMessage,
    SystemMessage,
    query,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("stale_detector")


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------
class PlanStatus(Enum):
    RUNNING = auto()
    COMPLETED = auto()
    STALE = auto()


@dataclass
class PlanRecord:
    """Mutable record for a single execution plan."""

    plan_id: str
    prompt: str
    started_at: float = field(default_factory=time.monotonic)
    last_progress_at: float = field(default_factory=time.monotonic)
    status: PlanStatus = PlanStatus.RUNNING
    progress_events: list[dict[str, Any]] = field(default_factory=list)

    def update_progress(self, event_type: str, detail: str = "") -> None:
        self.last_progress_at = time.monotonic()
        self.progress_events.append(
            {
                "event_type": event_type,
                "detail": detail,
                "wall_time": datetime.now().isoformat(timespec="seconds"),
            }
        )
        log.info("[%s] progress <- %s  %s", self.plan_id, event_type, detail[:80])

    def seconds_since_progress(self) -> float:
        return time.monotonic() - self.last_progress_at

    def elapsed_total(self) -> float:
        return time.monotonic() - self.started_at


# ---------------------------------------------------------------------------
# Stale-plan registry
# ---------------------------------------------------------------------------
class PlanRegistry:
    """
    Async-safe registry of all tracked execution plans.

    All mutating methods acquire a lock so the registry can be shared
    safely between the plan runners and the background StaleDetector sweep.
    """

    def __init__(self) -> None:
        self._plans: dict[str, PlanRecord] = {}
        self._lock = asyncio.Lock()

    async def register(self, plan_id: str, prompt: str) -> PlanRecord:
        async with self._lock:
            record = PlanRecord(plan_id=plan_id, prompt=prompt)
            self._plans[plan_id] = record
            log.info("[%s] plan registered", plan_id)
            return record

    async def update(self, plan_id: str, event_type: str, detail: str = "") -> None:
        async with self._lock:
            if plan_id in self._plans:
                self._plans[plan_id].update_progress(event_type, detail)

    async def complete(self, plan_id: str) -> None:
        async with self._lock:
            if plan_id in self._plans:
                rec = self._plans[plan_id]
                rec.status = PlanStatus.COMPLETED
                log.info("[%s] plan completed  (%.1fs total)", plan_id, rec.elapsed_total())

    async def mark_stale(self, plan_id: str) -> None:
        async with self._lock:
            if plan_id in self._plans:
                self._plans[plan_id].status = PlanStatus.STALE

    async def all_records(self) -> list[PlanRecord]:
        async with self._lock:
            return list(self._plans.values())


# ---------------------------------------------------------------------------
# Stale-plan report
# ---------------------------------------------------------------------------
@dataclass
class StalePlanReport:
    """Structured report emitted when a plan is flagged as stale."""

    plan_id: str
    prompt: str
    silent_for_seconds: float
    elapsed_total_seconds: float
    threshold_seconds: float
    last_events: list[dict[str, Any]]

    def render(self) -> str:
        sep = "-" * 62
        lines = [
            "",
            sep,
            "  WARNING: STALE PLAN REPORT",
            sep,
            f"  Plan ID          : {self.plan_id}",
            f"  Prompt           : {self.prompt[:72]}",
            f"  Silent for       : {self.silent_for_seconds:.1f}s"
            f"  (threshold: {self.threshold_seconds:.0f}s)",
            f"  Total elapsed    : {self.elapsed_total_seconds:.1f}s",
            "",
            "  Last progress events (most recent 5):",
        ]
        if self.last_events:
            for evt in self.last_events:
                lines.append(
                    f"    * [{evt['wall_time']}]"
                    f" {evt['event_type']}: {evt['detail'][:50]}"
                )
        else:
            lines.append("    (none -- plan produced zero progress events)")
        lines += [sep, ""]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Stale detector  (background sweep task)
# ---------------------------------------------------------------------------
class StaleDetector:
    """
    Periodically scans the registry and flags any RUNNING plan that has
    exceeded *stale_threshold_seconds* without a progress update.

    Parameters
    ----------
    registry:
        The shared PlanRegistry to inspect.
    stale_threshold_seconds:
        How many seconds of silence before a plan is considered stale.
    check_interval_seconds:
        How often the detector sweeps the registry (default: 5 s).
    on_stale:
        Optional async (or sync) callback invoked with the StalePlanReport
        whenever a new stale plan is first detected.
    """

    def __init__(
        self,
        registry: PlanRegistry,
        stale_threshold_seconds: float = 30.0,
        check_interval_seconds: float = 5.0,
        on_stale: Any = None,
    ) -> None:
        self.registry = registry
        self.stale_threshold = stale_threshold_seconds
        self.check_interval = check_interval_seconds
        self.on_stale = on_stale
        self._stop_event = asyncio.Event()
        self._flagged: set[str] = set()   # plans already reported (no duplicates)

    async def run(self) -> None:
        """Run the sweep loop until stop() is called."""
        log.info(
            "StaleDetector started  threshold=%.0fs  sweep-interval=%.0fs",
            self.stale_threshold,
            self.check_interval,
        )
        while not self._stop_event.is_set():
            await self._sweep()
            try:
                await asyncio.wait_for(
                    asyncio.shield(self._stop_event.wait()),
                    timeout=self.check_interval,
                )
            except asyncio.TimeoutError:
                pass  # normal -- time to sweep again

    def stop(self) -> None:
        """Signal the run() loop to exit after its next sleep."""
        self._stop_event.set()

    async def _sweep(self) -> None:
        records = await self.registry.all_records()
        for record in records:
            if record.status is not PlanStatus.RUNNING:
                continue
            silent_for = record.seconds_since_progress()
            if silent_for >= self.stale_threshold and record.plan_id not in self._flagged:
                await self._flag(record, silent_for)

    async def _flag(self, record: PlanRecord, silent_for: float) -> None:
        self._flagged.add(record.plan_id)
        await self.registry.mark_stale(record.plan_id)

        report = StalePlanReport(
            plan_id=record.plan_id,
            prompt=record.prompt,
            silent_for_seconds=silent_for,
            elapsed_total_seconds=record.elapsed_total(),
            threshold_seconds=self.stale_threshold,
            last_events=record.progress_events[-5:],
        )

        log.warning(
            "STALE PLAN [%s]  silent for %.1fs  (threshold %.0fs)",
            record.plan_id,
            silent_for,
            self.stale_threshold,
        )
        print(report.render())

        if self.on_stale is not None:
            if asyncio.iscoroutinefunction(self.on_stale):
                await self.on_stale(report)
            else:
                self.on_stale(report)


# ---------------------------------------------------------------------------
# Tracked plan runner
# ---------------------------------------------------------------------------
class TrackedPlanRunner:
    """
    Wraps a single Claude Agent SDK query() call with progress tracking
    so the StaleDetector can observe it.

    Progress is recorded on every PostToolUse and Notification hook event.
    The plan is marked COMPLETED when a ResultMessage arrives.

    Parameters
    ----------
    plan_id:
        Unique identifier used in logs and reports.
    prompt:
        Task prompt sent to the agent.
    registry:
        Shared PlanRegistry (must already be created by the caller).
    allowed_tools:
        Agent SDK built-in tools the agent may use.
    """

    def __init__(
        self,
        plan_id: str,
        prompt: str,
        registry: PlanRegistry,
        allowed_tools: list[str] | None = None,
    ) -> None:
        self.plan_id = plan_id
        self.prompt = prompt
        self.registry = registry
        self.allowed_tools = allowed_tools or ["Read", "Glob", "Grep", "Bash"]

    async def run(self) -> str | None:
        await self.registry.register(self.plan_id, self.prompt)

        plan_id = self.plan_id
        registry = self.registry

        # Hooks that forward progress events into the registry
        async def on_post_tool_use(
            input_data: dict, tool_use_id: str, context: Any
        ) -> dict:
            tool_name = input_data.get("tool_name", "unknown_tool")
            tool_input = str(input_data.get("tool_input", ""))[:60]
            await registry.update(plan_id, "tool_use", f"{tool_name}({tool_input})")
            return {}

        async def on_notification(
            input_data: dict, tool_use_id: str, context: Any
        ) -> dict:
            message = str(input_data.get("message", ""))
            await registry.update(plan_id, "notification", message)
            return {}

        options = ClaudeAgentOptions(
            allowed_tools=self.allowed_tools,
            permission_mode="dontAsk",
            hooks={
                "PostToolUse": [HookMatcher(matcher=".*", hooks=[on_post_tool_use])],
                "Notification": [HookMatcher(matcher=".*", hooks=[on_notification])],
            },
        )

        result_text: str | None = None
        async for message in query(prompt=self.prompt, options=options):
            if isinstance(message, SystemMessage) and message.subtype == "init":
                await registry.update(
                    plan_id, "session_start", f"session_id={message.session_id}"
                )
            elif isinstance(message, ResultMessage):
                result_text = message.result
                await registry.complete(plan_id)

        return result_text


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------
async def demo() -> None:
    """
    Run two plans concurrently alongside the StaleDetector.

    Plan A  -- a real agent task expected to complete within the threshold.
    Plan B  -- a simulated frozen task that never reports progress, so it
               will be flagged by the detector.

    The stale threshold is set low (15 s) for quick demonstration.
    """
    STALE_THRESHOLD_SECONDS = 15.0   # low for demo; use 60-300 in production

    registry = PlanRegistry()
    stale_reports: list[StalePlanReport] = []

    async def collect_report(report: StalePlanReport) -> None:
        stale_reports.append(report)

    detector = StaleDetector(
        registry=registry,
        stale_threshold_seconds=STALE_THRESHOLD_SECONDS,
        check_interval_seconds=3.0,
        on_stale=collect_report,
    )

    # Plan A: live agent task
    runner_a = TrackedPlanRunner(
        plan_id="plan-A",
        prompt=(
            "List the Python files in the current directory and give a one-line "
            "description of what each one likely does."
        ),
        registry=registry,
        allowed_tools=["Glob", "Bash"],
    )

    # Plan B: frozen task -- registers but never produces progress events
    async def frozen_plan() -> None:
        await registry.register(
            "plan-B",
            "A stubbed-out task that registers but never produces progress.",
        )
        log.info("[plan-B] registered -- no progress will be reported (simulating hang)")
        await asyncio.sleep(STALE_THRESHOLD_SECONDS * 3)  # outlasts the demo window

    # Run everything concurrently
    async with anyio.create_task_group() as tg:
        tg.start_soon(detector.run)
        tg.start_soon(runner_a.run)
        tg.start_soon(frozen_plan)

        # Give the demo enough time for plan-B to be flagged, then stop
        await asyncio.sleep(STALE_THRESHOLD_SECONDS * 2 + 5)
        detector.stop()

    # Final summary
    all_records = await registry.all_records()
    sep = "=" * 62
    print(f"\n{sep}")
    print("  FINAL PLAN SUMMARY")
    print(sep)
    for rec in sorted(all_records, key=lambda r: r.plan_id):
        print(
            f"  {rec.plan_id:<14}  status={rec.status.name:<10}"
            f"  events={len(rec.progress_events):<4}"
            f"  elapsed={rec.elapsed_total():.1f}s"
        )
    print(sep)
    flagged = [r for r in all_records if r.status is PlanStatus.STALE]
    if flagged:
        print(f"\n  {len(flagged)} stale plan(s) flagged: {[r.plan_id for r in flagged]}")
    else:
        print("\n  No stale plans detected.")
    print()


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    anyio.run(demo)
