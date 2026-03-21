---
name: perf-hooks
description: "Performance measurement hooks so agents can record and query response times, memory usage (RSS), and startup duration. All measurements are appended to an agent-shared Markdown audit log (docs/exec-plans/perf.md). Timer state survives process boundaries via a JSON sidecar file, so start and stop calls can come from different shells or agents. Use when: (1) measuring wall-clock elapsed time for any labelled operation (LLM call, index build, embedding batch, etc.), (2) sampling current process resident-set-size at a specific point, (3) recording agent cold-start / initialisation duration, (4) querying or printing aggregate statistics (min / max / mean / p95) for a metric, (5) comparing performance across agents or across plan runs, (6) diagnosing latency regressions between iterations, (7) profiling memory growth through a pipeline. Triggers on: measure response time, time this operation, start timer, stop timer, record elapsed, sample memory, memory usage, RSS, startup duration, cold start, perf hooks, performance measurement, benchmark, latency, how long did it take, how much memory, p95, aggregate stats, perf stats, perf log."
---

# Agent Performance Measurement Hooks

## Overview

The **perf-hooks** skill gives every agent lightweight instrumentation for three
key metrics:

| Metric | Unit | What it measures |
|--------|------|-----------------|
| `response_time` | ms | Wall-clock elapsed time for a labelled operation |
| `memory_rss` | MB | Resident-set-size of the measuring process at a point |
| `startup` | ms | Agent initialisation / cold-start duration |

All measurements are appended to **`docs/exec-plans/perf.md`** — an
append-only Markdown table shared across every agent in a plan.  Active timer
state (start timestamps) lives in **`docs/exec-plans/perf-timers.json`** so a
`start` call in one shell and a matching `stop` in a later shell both resolve
correctly.

---

## Workflow

**Do you want to time a specific operation?**
→ [Response time hooks](#response-time)

**Do you want to capture current process memory?**
→ [Memory sampling](#memory-rss)

**Do you want to record how long agent startup took?**
→ [Startup recording](#startup)

**Do you want to read measurements back or print stats?**
→ [Querying measurements](#querying-measurements)

---

## Response Time

### CLI

```bash
# 1 — start the timer (records epoch to perf-timers.json)
python skills/perf_hooks.py start \
    --label "call_llm" \
    --agent "agent/coder-v1"

# 2 — stop the timer; elapsed ms is appended to perf.md
python skills/perf_hooks.py stop \
    --label "call_llm" \
    --agent "agent/coder-v1" \
    --notes "gpt-4o cache miss"
```

### Programmatic — context manager (recommended)

```python
from skills.perf_hooks import PerfHooks

hooks = PerfHooks()

with hooks.timer("call_llm", agent="agent/coder-v1") as t:
    response = my_llm_call()

print(f"Elapsed: {t.elapsed_ms:.1f} ms")
```

The context manager records the entry in `perf.md` on exit, whether the block
succeeded or raised an exception.

### Programmatic — manual start / stop

```python
hooks.start_timer("build_index", agent="agent/coder-v1")
build_the_index()
elapsed_ms = hooks.stop_timer("build_index", agent="agent/coder-v1")
```

`stop_timer` raises `KeyError` if no matching `start_timer` entry exists.

---

## Memory RSS

### CLI

```bash
python skills/perf_hooks.py sample-memory \
    --label "after_load_index" \
    --agent "agent/coder-v1" \
    --notes "warm cache"
```

### Programmatic

```python
mb = hooks.sample_memory("after_embed", agent="agent/coder-v1")
print(f"RSS: {mb:.1f} MB")
```

The skill reads `/proc/self/status` on Linux and `resource.getrusage` on macOS.
Returns `0.0` on platforms where neither is available.

---

## Startup

### CLI

```bash
# Measure externally then record:
python skills/perf_hooks.py record-startup \
    --agent "agent/coder-v1" \
    --duration-ms 1240.5 \
    --notes "first run, cold disk cache"
```

### Programmatic

```python
import time

_t0 = time.perf_counter()
# … your initialisation code …
duration_ms = (time.perf_counter() - _t0) * 1000.0

hooks.record_startup(agent="agent/coder-v1", duration_ms=duration_ms)
```

`record_startup` always uses the label `"startup"` so all startup entries group
together in `stats` output.

---

## Querying Measurements

### List — print raw rows

```bash
# All measurements
python skills/perf_hooks.py list

# Filter by agent
python skills/perf_hooks.py list --agent "agent/coder-v1"

# Filter by metric kind
python skills/perf_hooks.py list --metric response_time

# Filter by operation label
python skills/perf_hooks.py list --label "call_llm"
```

```python
# Programmatic
entries = hooks.list(agent="agent/coder-v1", metric="response_time")
for e in entries:
    print(e.timestamp, e.label, e.value, e.unit)
```

### Stats — aggregate min / max / mean / p95 / count

```bash
# All metrics, all agents
python skills/perf_hooks.py stats

# One agent only
python skills/perf_hooks.py stats --agent "agent/coder-v1"

# One metric kind only
python skills/perf_hooks.py stats --metric startup
```

```python
hooks.stats(agent="agent/coder-v1", metric="response_time")
```

Example output:

```
Metric           Label                            N         Min         Max        Mean         p95  Unit
--------------------------------------------------------------------------------
response_time    call_llm                        42      312.441    4821.003     893.124    2107.550  ms
response_time    embed_docs                       8       88.002      341.115     201.004     310.000  ms
memory_rss       after_load_index                 5       84.320      102.144      94.611     101.200  MB
startup          startup                          3      680.100     1240.500     960.300    1200.000  ms
```

### Standalone helper script

The companion script [`scripts/query_perf.py`](scripts/query_perf.py) wraps the
CLI for quick interactive use without any package installation:

```bash
# Quick stats dump
python skills/perf-hooks/scripts/query_perf.py

# Filter by agent and metric
python skills/perf-hooks/scripts/query_perf.py \
    --agent "agent/coder-v1" \
    --metric response_time
```

---

## Log File Format

Entries are written to `docs/exec-plans/perf.md` as Markdown table rows:

```markdown
# Agent Performance Measurements

> Auto-generated by `skills/perf_hooks.py` — do not edit manually.

| Timestamp (UTC) | Agent | Metric | Label | Value | Unit | Notes |
|-----------------|-------|--------|-------|-------|------|-------|
| 2026-03-20T09:00:00Z | agent/coder-v1 | ⏱  response_time | call_llm | 893.124 | ms | cache miss |
| 2026-03-20T09:01:10Z | agent/coder-v1 | 🧠 memory_rss | after_load_index | 94.611 | MB | — |
| 2026-03-20T09:01:11Z | agent/coder-v1 | 🚀 startup | startup | 1240.500 | ms | cold disk |
```

Pipe characters inside field values are escaped as `\|`.

---

## Data Structures

### `Measurement`

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | `str` | ISO-8601 UTC string (e.g. `2026-03-20T09:00:00Z`). |
| `agent` | `str` | Agent identifier (e.g. `agent/coder-v1`). |
| `metric` | `str` | Canonical metric key: `response_time`, `memory_rss`, or `startup`. |
| `label` | `str` | Operation label (e.g. `call_llm`). |
| `value` | `float` | Measured value in the metric's unit. |
| `unit` | `str` | `ms` or `MB`. |
| `notes` | `str` | Optional free-text annotation; empty string when not supplied. |

`Measurement.as_dict()` returns all fields as a plain `dict`.

### `PerfHooks`

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `start_timer` | `(label, agent) → float` | Start epoch | Persist timer start to JSON; survives process boundaries. |
| `stop_timer` | `(label, agent, notes="", timestamp=None) → float` | Elapsed ms | Stop timer, record elapsed, remove from JSON. Raises `KeyError` if not started. |
| `timer` | `(label, agent, notes="")` | `_TimerContext` | Context manager; records on exit; exposes `elapsed_ms`. |
| `sample_memory` | `(label, agent, notes="", timestamp=None) → float` | RSS in MB | Sample current process RSS and record. |
| `record_startup` | `(agent, duration_ms, notes="", timestamp=None) → Measurement` | `Measurement` | Record a known startup duration. |
| `list` | `(agent=None, metric=None, label=None) → list[Measurement]` | Row list | Return measurements from file, optionally filtered. |
| `stats` | `(agent=None, metric=None) → None` | — | Print min/max/mean/p95/count table to stdout. |

Constructor accepts optional `perf_file: Path` and `timer_state: Path` to
override the default storage locations (useful in tests).

---

## Metric Reference

| Metric key | Display | Unit | Typical use |
|------------|---------|------|-------------|
| `response_time` | ⏱  response_time | ms | LLM calls, HTTP requests, index queries |
| `memory_rss` | 🧠 memory_rss | MB | After loading large data, embedding batches |
| `startup` | 🚀 startup | ms | Agent or service cold-start duration |

---

## Key Files

| Path | Purpose |
|------|---------|
| `skills/perf_hooks.py` | Full implementation — `Measurement`, `PerfHooks`, timer state helpers, CLI entry-point. |
| `skills/perf-hooks/SKILL.md` | This document — agent routing metadata and usage guide. |
| `skills/perf-hooks/scripts/query_perf.py` | Standalone CLI helper for quick interactive queries. |
| `docs/exec-plans/perf.md` | Generated append-only measurement log; auto-created on first write. |
| `docs/exec-plans/perf-timers.json` | In-flight timer state; entries are removed when `stop_timer` is called. |
