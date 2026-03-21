# Harness Performance

Attach **performance measurement hooks** to a `claude_agent_sdk` session so agents
can query response times, memory usage, and startup duration — live or after the
session ends.

The hooks are provided by `harness_skills.performance_hooks.PerformanceTracker`
and capture three dimensions of agent performance:

| Dimension | What is measured |
|---|---|
| **Startup duration** | Wall-clock milliseconds from `SessionStart` to the first `PreToolUse` event |
| **Tool response times** | Per-call elapsed ms between `PreToolUse` and `PostToolUse` / `PostToolUseFailure`, with success/failure flag |
| **Memory usage** | Peak heap bytes via `tracemalloc` + RSS delta via `psutil` (falls back to `-1` when psutil is unavailable) |

Use this skill to:

- **Generate** a ready-to-paste Python snippet wiring `PerformanceTracker` into a
  new SDK session
- **Run** the built-in synthetic demo to validate the tracker without an API key
- **Inspect** the `PerformanceReport` dataclass fields available post-session
- **Query** live metrics mid-session (startup, call count, peak memory)
- **Interpret** summary output and tune agent performance

---

## Usage

```bash
# Generate the integration snippet
/harness:performance --generate

# Show the PerformanceReport field reference
/harness:performance --fields

# Run the synthetic (no-API-key) demo and print results
/harness:performance --demo

# Full guide: generate snippet + field reference + demo output
/harness:performance --all
```

---

## Instructions

### Step 1 — Determine mode from flags

| Flag | Action |
|---|---|
| `--generate` | Emit the Python hook-integration snippet (Step 2) |
| `--fields` | Emit the `PerformanceReport` field reference table (Step 3) |
| `--demo` | Run the synthetic demo via `performance_hooks_example.py` (Step 4) |
| `--all` | Execute Steps 2, 3, and 4 in order |
| *(none)* | Default — run Step 2 only (generate snippet) |

---

### Step 2 — Emit the hook-integration snippet (`--generate` or default)

Output the following ready-to-paste block verbatim:

````
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Performance Hook Integration Snippet
  Paste into any file that calls claude_agent_sdk.query()
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

```python
import asyncio
from harness_skills.performance_hooks import PerformanceTracker
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

async def run_agent(prompt: str) -> None:
    tracker = PerformanceTracker()          # one tracker per session

    async for message in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            allowed_tools=["Read", "Glob", "Grep", "Bash"],
            permission_mode="acceptEdits",
            hooks=tracker.hooks(),          # attach performance hooks
        ),
    ):
        if isinstance(message, ResultMessage):
            print(message.result)

    # ── Post-session summary ──────────────────────────────────
    tracker.print_summary()          # human-readable table
    tracker.print_tool_breakdown()   # per-tool timing rows

    # ── Programmatic access ───────────────────────────────────
    report = tracker.summary()       # returns PerformanceReport
    print(f"startup : {report.startup_duration_ms:.0f} ms")
    print(f"p95     : {report.p95_response_ms:.0f} ms")
    print(f"peak    : {report.peak_tracemalloc_bytes // 1024} KB")

asyncio.run(run_agent("Use Bash to echo hello"))
```

What the hooks capture:
  SessionStart         → start wall-clock timer, start tracemalloc, record RSS
  PreToolUse           → record per-tool start time; first call sets startup window
  PostToolUse          → record elapsed ms + success=True → ToolTiming
  PostToolUseFailure   → record elapsed ms + success=False → ToolTiming
  SessionEnd           → stop wall-clock timer, snapshot peak memory and RSS delta

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
````

---

### Step 3 — Emit the `PerformanceReport` field reference (`--fields`)

Output the following table:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  PerformanceReport — Field Reference
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Timing
  ──────────────────────────────────────────────────────
  startup_duration_ms   float | None   SessionStart → first PreToolUse
  session_duration_ms   float | None   SessionStart → SessionEnd

  Tool statistics
  ──────────────────────────────────────────────────────
  tool_count            int            Total tool calls (success + failure)
  tool_timings          list[ToolTiming]
    .tool_name          str            Name of the tool ("Read", "Bash", …)
    .elapsed_ms         float          Wall-clock ms for this call
    .success            bool           False when PostToolUseFailure fired

  Response-time percentiles  (None when tool_count == 0)
  ──────────────────────────────────────────────────────
  mean_response_ms      float | None   Arithmetic mean of all tool elapsed_ms
  median_response_ms    float | None   50th percentile
  min_response_ms       float | None   Fastest tool call
  max_response_ms       float | None   Slowest tool call
  p95_response_ms       float | None   95th percentile (linear interpolation)

  Memory
  ──────────────────────────────────────────────────────
  peak_tracemalloc_bytes  int          Peak heap bytes (tracemalloc); -1 if off
  delta_rss_bytes         int          end_rss − start_rss via psutil; -1 if unavailable
  memory_snapshots        list[MemorySnapshot]
    .label                str          "session_start" or "session_end"
    .tracemalloc_bytes    int          Heap at that moment
    .rss_bytes            int          RSS at that moment; -1 if unavailable

  Live-query helpers (callable mid-session)
  ──────────────────────────────────────────────────────
  tracker.get_startup_duration_ms()   → float | None
  tracker.get_response_times()        → list[ToolTiming]
  tracker.get_peak_memory_bytes()     → int

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### Step 4 — Run the synthetic demo (`--demo`)

Execute the built-in example script which runs all scenarios, including a
no-API-key synthetic path that fires mock hook events and prints real output:

```bash
uv run python performance_hooks_example.py 2>&1
```

> **Fallback** — if `uv` is unavailable:
> ```bash
> python performance_hooks_example.py 2>&1
> ```

Capture and display the full output.

If the script exits with a non-zero code, show the error and suggest:

```
Possible causes:
  • Missing dependency  → pip install psutil
  • tracemalloc not available in this Python build (rare)
  • ANTHROPIC_API_KEY not set (only Scenario 4 runs without it — that is expected)
```

---

### Step 5 — Emit structured data (agent-readable)

After human-readable output, always emit a fenced JSON block so downstream
agents can consume metrics without re-running the script:

```json
{
  "command": "harness performance",
  "tracker_class": "harness_skills.performance_hooks.PerformanceTracker",
  "dimensions": ["startup_duration_ms", "tool_response_times", "memory_usage"],
  "hooks": {
    "SessionStart":        "_on_session_start",
    "PreToolUse":          "_on_pre_tool_use",
    "PostToolUse":         "_on_post_tool_use",
    "PostToolUseFailure":  "_on_post_tool_use_failure",
    "SessionEnd":          "_on_session_end"
  },
  "live_query_methods": [
    "get_startup_duration_ms()",
    "get_response_times()",
    "get_peak_memory_bytes()"
  ],
  "report_fields": {
    "timing": ["startup_duration_ms", "session_duration_ms"],
    "tools":  ["tool_count", "tool_timings"],
    "percentiles": ["mean_response_ms", "median_response_ms",
                    "min_response_ms", "max_response_ms", "p95_response_ms"],
    "memory": ["peak_tracemalloc_bytes", "delta_rss_bytes", "memory_snapshots"]
  },
  "output_path": null,
  "psutil_required": false,
  "notes": "psutil is optional; delta_rss_bytes returns -1 when unavailable"
}
```

---

### Step 6 — Highlight actionable insights

Append a short **Insights** section:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Insights
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Startup duration
    → A startup_duration_ms > 500 ms usually indicates a slow first tool
      dispatch. Consider pre-warming the agent or reducing prompt length.

  High p95 response time
    → If p95_response_ms is 2–5× the median, look for outlier tool calls
      in tool_timings (often Bash commands with blocking I/O).

  Memory growth
    → A large delta_rss_bytes (> 50 MB) suggests the agent is loading or
      caching large files. Review Glob/Read patterns and add path filters.

  Tracking without psutil
    → If delta_rss_bytes == -1, install psutil for RSS tracking:
        pip install psutil

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Options

| Flag | Default | Effect |
|---|---|---|
| `--generate` | on (default) | Emit the Python hook-integration snippet (Step 2) |
| `--fields` | off | Emit the `PerformanceReport` field reference table (Step 3) |
| `--demo` | off | Run `performance_hooks_example.py` synthetic demo (Step 4) |
| `--all` | off | Run Steps 2, 3, and 4 in sequence |

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Wire performance measurement into a new SDK session | **`/harness:performance --generate`** ← you are here |
| Inspect all `PerformanceReport` fields | **`/harness:performance --fields`** |
| Validate tracker works without an API key | **`/harness:performance --demo`** |
| Track artifact reads, CLI command frequency, gate failures | `/harness:telemetry` |
| Measure CLI command adoption and gate effectiveness | `/harness:effectiveness` |
| Check code quality gates (ruff, mypy, pytest) | `/check-code` |
| Detect whether a plan is making progress | `/harness:detect-stale` |

---

## Notes

- **No output file** — `PerformanceTracker` holds all data in memory; it does not
  write to disk. Use `tracker.summary()` to access data programmatically.
- **One tracker per session** — each `PerformanceTracker` instance is scoped to
  a single `query()` call. Create a new instance for each session.
- **tracemalloc overhead** — enabling tracemalloc adds ~2–5 % CPU overhead. For
  production agents where this matters, disable it by subclassing and overriding
  `_on_session_start` to skip `tracemalloc.start()`.
- **psutil is optional** — `delta_rss_bytes` is `-1` when psutil is not installed;
  all other metrics work without it.
- **Thread safety** — the tracker is not thread-safe. Do not share a single
  instance across concurrent agent sessions.
- **Synthetic testing** — call hook methods directly to test without an API key:
  ```python
  await tracker._on_session_start({}, "sess-1", None)
  await tracker._on_pre_tool_use({"tool_name": "Bash"}, "t1", None)
  await tracker._on_post_tool_use({}, "t1", None)
  await tracker._on_session_end({}, "sess-1", None)
  report = tracker.summary()
  ```
