"""
performance_hooks.py
====================
SDK hook integration for measuring agent session performance.

Attaches lightweight async hooks to a ``claude_agent_sdk`` session and records:

* **Startup duration** — wall-clock milliseconds from ``SessionStart`` to the
  first ``PreToolUse`` event (i.e. time before the agent touches any tool).
* **Tool response times** — per-call elapsed milliseconds between ``PreToolUse``
  and ``PostToolUse`` / ``PostToolUseFailure``, including success/failure flag
  and tool name.
* **Memory usage** — peak heap bytes tracked by :mod:`tracemalloc` plus the
  RSS delta between session start and session end (via :mod:`psutil` when
  available, falling back to ``-1`` if not installed).

Usage
-----
    from harness_skills.performance_hooks import PerformanceTracker
    from claude_agent_sdk import ClaudeAgentOptions, query

    tracker = PerformanceTracker()

    async for msg in query(
        prompt="…",
        options=ClaudeAgentOptions(hooks=tracker.hooks()),
    ):
        pass

    tracker.print_summary()
    report = tracker.summary()

Live queries (mid-session)
--------------------------
    startup_ms  = tracker.get_startup_duration_ms()   # None until first tool
    times       = tracker.get_response_times()         # list[ToolTiming]
    peak_bytes  = tracker.get_peak_memory_bytes()      # -1 before session start

See ``examples/performance_hooks_example.py`` for full runnable scenarios including a
synthetic (no-API-key) demo.
"""

from __future__ import annotations

import asyncio
import statistics
import time
import tracemalloc
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ToolTiming:
    """Timing record for a single tool invocation."""

    tool_name: str
    elapsed_ms: float
    success: bool


@dataclass
class MemorySnapshot:
    """Point-in-time memory reading."""

    label: str
    tracemalloc_bytes: int   # current heap as tracked by tracemalloc
    rss_bytes: int           # process RSS; -1 when psutil is unavailable


@dataclass
class PerformanceReport:
    """Aggregated performance data for a completed agent session."""

    # Timing
    startup_duration_ms: Optional[float]
    session_duration_ms: Optional[float]

    # Tool stats
    tool_count: int
    tool_timings: List[ToolTiming]

    # Response time percentiles (None when tool_count == 0)
    mean_response_ms: Optional[float]
    median_response_ms: Optional[float]
    min_response_ms: Optional[float]
    max_response_ms: Optional[float]
    p95_response_ms: Optional[float]

    # Memory
    peak_tracemalloc_bytes: int   # -1 when tracemalloc was not started
    delta_rss_bytes: int          # end_rss - start_rss; -1 when unavailable
    memory_snapshots: List[MemorySnapshot] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_ms() -> float:
    """Current wall-clock time in milliseconds."""
    return time.perf_counter() * 1_000


def _rss_bytes() -> int:
    """Current process RSS in bytes, or -1 when psutil is unavailable."""
    try:
        import psutil  # type: ignore[import]
        return psutil.Process().memory_info().rss
    except Exception:
        return -1


def _tracemalloc_current() -> int:
    """Current traced heap in bytes, or -1 when tracemalloc is not running."""
    if not tracemalloc.is_tracing():
        return -1
    current, _ = tracemalloc.get_traced_memory()
    return current


def _tracemalloc_peak() -> int:
    """Peak traced heap in bytes, or -1 when tracemalloc is not running."""
    if not tracemalloc.is_tracing():
        return -1
    _, peak = tracemalloc.get_traced_memory()
    return peak


def _p95(values: List[float]) -> float:
    """95th-percentile of *values* (linear interpolation)."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = 0.95 * (len(sorted_vals) - 1)
    lo = int(idx)
    hi = lo + 1
    if hi >= len(sorted_vals):
        return sorted_vals[-1]
    return sorted_vals[lo] + (idx - lo) * (sorted_vals[hi] - sorted_vals[lo])


# ---------------------------------------------------------------------------
# PerformanceTracker
# ---------------------------------------------------------------------------


class PerformanceTracker:
    """
    Collect response-time, startup, and memory metrics for an agent session.

    Instantiate once per session, pass ``tracker.hooks()`` to
    ``ClaudeAgentOptions``, and call ``tracker.summary()`` or
    ``tracker.print_summary()`` after the session completes.
    """

    def __init__(self) -> None:
        # Session-level timing
        self._session_start_ms: Optional[float] = None
        self._session_end_ms: Optional[float] = None
        self._first_tool_ms: Optional[float] = None

        # Per-tool in-flight tracking: tool_id → start time
        self._tool_start: Dict[str, float] = {}
        self._tool_name_map: Dict[str, str] = {}

        # Completed tool records
        self._timings: List[ToolTiming] = []

        # Memory bookmarks
        self._start_rss: int = -1
        self._memory_snapshots: List[MemorySnapshot] = []

    # ------------------------------------------------------------------
    # Hook callbacks
    # ------------------------------------------------------------------

    async def _on_session_start(
        self,
        data: Any,
        session_id: Any,
        result: Any,
    ) -> None:
        self._session_start_ms = _now_ms()
        tracemalloc.start()
        self._start_rss = _rss_bytes()
        self._memory_snapshots.append(
            MemorySnapshot(
                label="session_start",
                tracemalloc_bytes=_tracemalloc_current(),
                rss_bytes=self._start_rss,
            )
        )

    async def _on_pre_tool_use(
        self,
        data: Any,
        tool_id: Any,
        result: Any,
    ) -> None:
        now = _now_ms()
        tid = str(tool_id)

        # Record startup window on first tool call
        if self._first_tool_ms is None and self._session_start_ms is not None:
            self._first_tool_ms = now

        # Resolve tool name from hook payload dict
        tool_name = "unknown"
        if isinstance(data, dict):
            tool_name = str(data.get("tool_name", data.get("name", "unknown")))

        self._tool_start[tid] = now
        self._tool_name_map[tid] = tool_name

    async def _on_post_tool_use(
        self,
        data: Any,
        tool_id: Any,
        result: Any,
    ) -> None:
        self._record_tool(str(tool_id), success=True)

    async def _on_post_tool_use_failure(
        self,
        data: Any,
        tool_id: Any,
        result: Any,
    ) -> None:
        self._record_tool(str(tool_id), success=False)

    async def _on_session_end(
        self,
        data: Any,
        session_id: Any,
        result: Any,
    ) -> None:
        self._session_end_ms = _now_ms()
        self._memory_snapshots.append(
            MemorySnapshot(
                label="session_end",
                tracemalloc_bytes=_tracemalloc_peak(),
                rss_bytes=_rss_bytes(),
            )
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _record_tool(self, tid: str, *, success: bool) -> None:
        start = self._tool_start.pop(tid, None)
        if start is None:
            return
        elapsed = _now_ms() - start
        name = self._tool_name_map.pop(tid, "unknown")
        self._timings.append(ToolTiming(tool_name=name, elapsed_ms=elapsed, success=success))

    # ------------------------------------------------------------------
    # Live query API
    # ------------------------------------------------------------------

    def get_startup_duration_ms(self) -> Optional[float]:
        """
        Milliseconds from ``SessionStart`` to the first ``PreToolUse`` event.

        Returns ``None`` if no tool has been called yet.
        """
        if self._session_start_ms is None or self._first_tool_ms is None:
            return None
        return self._first_tool_ms - self._session_start_ms

    def get_response_times(self) -> List[ToolTiming]:
        """All completed tool timings recorded so far (copy)."""
        return list(self._timings)

    def get_peak_memory_bytes(self) -> int:
        """
        Peak traced heap in bytes since the session started.

        Returns ``-1`` if the session has not started or tracemalloc is not
        available.
        """
        return _tracemalloc_peak()

    # ------------------------------------------------------------------
    # Summary / report
    # ------------------------------------------------------------------

    def summary(self) -> PerformanceReport:
        """Return a :class:`PerformanceReport` with all collected metrics."""
        elapsed_list = [t.elapsed_ms for t in self._timings]

        if elapsed_list:
            mean_ms = statistics.mean(elapsed_list)
            median_ms = statistics.median(elapsed_list)
            min_ms = min(elapsed_list)
            max_ms = max(elapsed_list)
            p95_ms = _p95(elapsed_list)
        else:
            mean_ms = median_ms = min_ms = max_ms = p95_ms = None

        # Session wall time
        session_ms: Optional[float] = None
        if self._session_start_ms is not None and self._session_end_ms is not None:
            session_ms = self._session_end_ms - self._session_start_ms

        # RSS delta
        end_rss = -1
        if self._memory_snapshots:
            end_rss = self._memory_snapshots[-1].rss_bytes
        delta_rss = (
            end_rss - self._start_rss
            if end_rss >= 0 and self._start_rss >= 0
            else -1
        )

        return PerformanceReport(
            startup_duration_ms=self.get_startup_duration_ms(),
            session_duration_ms=session_ms,
            tool_count=len(self._timings),
            tool_timings=list(self._timings),
            mean_response_ms=mean_ms,
            median_response_ms=median_ms,
            min_response_ms=min_ms,
            max_response_ms=max_ms,
            p95_response_ms=p95_ms,
            peak_tracemalloc_bytes=_tracemalloc_peak(),
            delta_rss_bytes=delta_rss,
            memory_snapshots=list(self._memory_snapshots),
        )

    # ------------------------------------------------------------------
    # Human-readable output
    # ------------------------------------------------------------------

    def print_summary(self) -> None:
        """Print a formatted performance summary to stdout."""
        r = self.summary()
        bar = "─" * 54
        print(f"\n{'━' * 54}")
        print("  Performance Summary")
        print(f"{'━' * 54}")

        def _fmt(v: Optional[float], unit: str = "ms") -> str:
            return f"{v:.1f} {unit}" if v is not None else "n/a"

        print(f"  Startup duration   : {_fmt(r.startup_duration_ms)}")
        print(f"  Session duration   : {_fmt(r.session_duration_ms)}")
        print(f"  Tools invoked      : {r.tool_count}")
        print(f"  {bar}")
        print(f"  Response times ─ mean    : {_fmt(r.mean_response_ms)}")
        print(f"  Response times ─ median  : {_fmt(r.median_response_ms)}")
        print(f"  Response times ─ min     : {_fmt(r.min_response_ms)}")
        print(f"  Response times ─ max     : {_fmt(r.max_response_ms)}")
        print(f"  Response times ─ p95     : {_fmt(r.p95_response_ms)}")
        print(f"  {bar}")

        heap = r.peak_tracemalloc_bytes
        rss  = r.delta_rss_bytes
        print(f"  Peak heap (tracemalloc)  : {'n/a' if heap < 0 else f'{heap // 1024} KB'}")
        print(f"  RSS delta                : {'n/a' if rss  < 0 else f'{rss  // 1024} KB'}")
        print(f"{'━' * 54}\n")

    def print_tool_breakdown(self) -> None:
        """Print per-tool timing table to stdout."""
        if not self._timings:
            print("  (no tool calls recorded)")
            return

        col_w = max(len(t.tool_name) for t in self._timings)
        print(f"\n  {'Tool':<{col_w}}   {'ms':>8}   Status")
        print(f"  {'─' * col_w}   {'─' * 8}   {'─' * 7}")
        for t in self._timings:
            status = "✓ ok" if t.success else "✗ fail"
            print(f"  {t.tool_name:<{col_w}}   {t.elapsed_ms:>8.1f}   {status}")
        print()

    # ------------------------------------------------------------------
    # Hooks dict
    # ------------------------------------------------------------------

    def hooks(self) -> Dict[str, Any]:
        """
        Return a hooks dictionary compatible with ``ClaudeAgentOptions(hooks=…)``.

        Example::

            tracker = PerformanceTracker()
            options = ClaudeAgentOptions(hooks=tracker.hooks())
            async for msg in query(prompt="…", options=options):
                pass
        """
        return {
            "SessionStart": self._on_session_start,
            "PreToolUse": self._on_pre_tool_use,
            "PostToolUse": self._on_post_tool_use,
            "PostToolUseFailure": self._on_post_tool_use_failure,
            "SessionEnd": self._on_session_end,
        }
