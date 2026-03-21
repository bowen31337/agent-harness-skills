"""
performance_hooks_example.py
============================
End-to-end demonstration of PerformanceTracker with the Claude Agent SDK.

Shows three usage patterns:

  1. Basic usage   — attach tracker, run agent, print summary.
  2. Live queries  — read individual metrics as the session runs.
  3. Post-session  — inspect the PerformanceReport dataclass directly.

Run
---
    python performance_hooks_example.py

Environment
-----------
    ANTHROPIC_API_KEY  — required for the real Agent SDK scenarios.
"""

from __future__ import annotations

import asyncio
import os

from harness_skills.performance_hooks import PerformanceTracker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _separator(title: str) -> None:
    width = 62
    print(f"\n{'─' * width}")
    print(f"  {title}")
    print(f"{'─' * width}")


# ---------------------------------------------------------------------------
# Scenario 1: Basic usage
# ---------------------------------------------------------------------------

async def scenario_basic() -> None:
    """Attach tracker to a real agent session and print the full summary."""
    _separator("Scenario 1 — Basic usage (attach & summarise)")

    try:
        from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
    except ImportError:
        print("  ✗  claude-agent-sdk not installed — skipping.")
        return

    tracker = PerformanceTracker()

    async for message in query(
        prompt="Use Bash to run: echo hello && sleep 0.1 && echo world",
        options=ClaudeAgentOptions(
            allowed_tools=["Bash"],
            permission_mode="acceptEdits",
            hooks=tracker.hooks(),
        ),
    ):
        if isinstance(message, ResultMessage):
            print(f"  Agent result: {message.result!r}")

    print()
    tracker.print_summary()
    print()
    tracker.print_tool_breakdown()


# ---------------------------------------------------------------------------
# Scenario 2: Live metric queries during the session
# ---------------------------------------------------------------------------

async def scenario_live_queries() -> None:
    """Demonstrate querying metrics before the session ends."""
    _separator("Scenario 2 — Live metric queries")

    try:
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            ClaudeSDKClient,
            ResultMessage,
            TextBlock,
        )
    except ImportError:
        print("  ✗  claude-agent-sdk not installed — skipping.")
        return

    tracker = PerformanceTracker()

    options = ClaudeAgentOptions(
        allowed_tools=["Bash"],
        permission_mode="acceptEdits",
        hooks=tracker.hooks(),
    )

    async with ClaudeSDKClient(options=options) as client:
        await client.query("Run: python3 -c \"import time; time.sleep(0.05); print('done')\"")

        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        # Peek at live metrics after each assistant turn
                        startup = tracker.get_startup_duration_ms()
                        calls = tracker.get_response_times()
                        peak = tracker.get_peak_memory_bytes()
                        print(
                            f"  [live] startup={startup:.0f}ms  "
                            f"calls={len(calls)}  "
                            f"peak_heap={peak // 1024}KB"
                            if startup is not None and peak >= 0
                            else f"  [live] startup=pending  calls={len(calls)}"
                        )

    print()
    tracker.print_summary()


# ---------------------------------------------------------------------------
# Scenario 3: Inspect PerformanceReport dataclass
# ---------------------------------------------------------------------------

async def scenario_report_dataclass() -> None:
    """Show how to access the PerformanceReport dataclass programmatically."""
    _separator("Scenario 3 — Inspect PerformanceReport dataclass")

    try:
        from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
    except ImportError:
        print("  ✗  claude-agent-sdk not installed — skipping.")
        return

    tracker = PerformanceTracker()

    async for _ in query(
        prompt="Use Bash to run three quick commands: date, hostname, uname -s",
        options=ClaudeAgentOptions(
            allowed_tools=["Bash"],
            permission_mode="acceptEdits",
            hooks=tracker.hooks(),
        ),
    ):
        pass  # consume messages; we only care about metrics

    report = tracker.summary()

    print(f"  startup_duration_ms : {report.startup_duration_ms}")
    print(f"  session_duration_ms : {report.session_duration_ms}")
    print(f"  tool_count          : {report.tool_count}")
    print(f"  mean_response_ms    : {report.mean_response_ms}")
    print(f"  median_response_ms  : {report.median_response_ms}")
    print(f"  min_response_ms     : {report.min_response_ms}")
    print(f"  max_response_ms     : {report.max_response_ms}")
    print(f"  p95_response_ms     : {report.p95_response_ms}")
    print(f"  peak_heap_bytes     : {report.peak_tracemalloc_bytes}")
    print(f"  rss_delta_bytes     : {report.delta_rss_bytes}")
    print(f"  memory_checkpoints  : {[s.label for s in report.memory_snapshots]}")

    if report.tool_timings:
        first = report.tool_timings[0]
        print(f"\n  First tool: {first.tool_name!r}  "
              f"elapsed={first.elapsed_ms:.1f}ms  success={first.success}")


# ---------------------------------------------------------------------------
# Fallback: demo without an API key using synthetic hook data
# ---------------------------------------------------------------------------

async def scenario_synthetic() -> None:
    """Exercise PerformanceTracker without a live agent (no API key needed)."""
    _separator("Scenario 4 — Synthetic hook calls (no API key required)")

    tracker = PerformanceTracker()

    # Simulate SessionStart
    await tracker._on_session_start({}, "sess-1", None)
    await asyncio.sleep(0.05)  # 50 ms "startup" delay

    # Simulate two tool calls
    for i, (name, duration) in enumerate([("Read", 0.12), ("Bash", 0.33)]):
        tid = f"tool-{i}"
        await tracker._on_pre_tool_use({"tool_name": name}, tid, None)
        await asyncio.sleep(duration)
        await tracker._on_post_tool_use({}, tid, None)

    # Simulate a failed tool call
    await tracker._on_pre_tool_use({"tool_name": "Write"}, "tool-fail", None)
    await asyncio.sleep(0.02)
    await tracker._on_post_tool_use_failure({}, "tool-fail", None)

    # Simulate SessionEnd
    await tracker._on_session_end({}, "sess-1", None)

    print()
    tracker.print_summary()
    print()
    tracker.print_tool_breakdown()

    # Programmatic assertions for correctness
    r = tracker.summary()
    assert r.startup_duration_ms is not None and r.startup_duration_ms >= 40
    assert r.tool_count == 3                # Read, Bash, Write(failed)
    assert not tracker.get_response_times()[-1].success   # Write failed
    assert r.mean_response_ms is not None
    print("\n  ✓  All assertions passed.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))

    if has_key:
        await scenario_basic()
        await scenario_live_queries()
        await scenario_report_dataclass()
    else:
        print("  ANTHROPIC_API_KEY not set — running synthetic demo only.")

    await scenario_synthetic()


if __name__ == "__main__":
    asyncio.run(main())
