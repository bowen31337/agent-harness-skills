---
name: error-aggregation
description: "Error aggregation view for agents. Groups recent harness error events by domain and frequency so agents can query the error landscape without parsing raw logs. Pre-computes deduplication, trend detection (rising/falling/stable), and JSON-serialisable summaries. Use when: (1) diagnosing which component is failing most often, (2) investigating a spike in a specific domain, (3) checking whether an error rate is rising or recovering, (4) providing a structured error briefing before a remediation agent runs, (5) summarising errors across a multi-agent pipeline. Triggers on: show me recent errors, what errors are happening, error summary, query errors by domain, which domain is failing, error aggregation, rising errors, error frequency."
---

# Error Aggregation Skill

## Overview

The error aggregation skill groups raw harness error events by **domain** and
**frequency** so you receive a structured, deduplicated view — not a wall of log
lines.  It handles:

- **Deduplication** — identical stack traces and similar messages are merged
  into a single `ErrorGroup`.
- **Trend detection** — each group carries a `trend` of `rising`, `falling`, or
  `stable` based on how event rates compare across the analysis window.
- **Domain breakdown** — groups are indexed by the logical component that
  produced them (e.g. `gate_runner`, `lsp`, `deploy`).
- **JSON serialisation** — the view is pre-serialised into compact JSON for
  embedding in agent context budgets.

---

## Workflow

**Do you want a one-shot CLI summary?**
→ [Run the CLI](#cli-usage)

**Do you want to embed the view inside an agent?**
→ [Programmatic usage](#programmatic-usage)

**Do you want to let Claude query the view interactively?**
→ [Agent query runner](#agent-query-runner)

---

## CLI Usage

```bash
# Summarise the most critical errors from the last 60 minutes:
python -m harness_skills.error_query_agent \
    --log-file /var/log/harness/errors.ndjson \
    --window 60 \
    --prompt "Which domains are producing the most errors right now?"

# Print the raw aggregation JSON and exit (no Claude call):
python -m harness_skills.error_query_agent \
    --log-file /var/log/harness/errors.ndjson \
    --json-summary

# Restrict to a custom window and model:
python -m harness_skills.error_query_agent \
    --log-file /var/log/harness/errors.ndjson \
    --window 30 \
    --model claude-opus-4-6 \
    --prompt "Are there any rising errors in the deploy domain?"
```

The helper script [`scripts/query_errors.py`](scripts/query_errors.py) wraps
the CLI for quick interactive use without installing the full package.

---

## Programmatic Usage

### 1 — Load from an NDJSON log file

```python
from harness_skills.error_aggregation import load_errors_from_log, aggregate_errors, errors_to_json_summary

records = load_errors_from_log("/var/log/harness/errors.ndjson", window_minutes=60)
view    = aggregate_errors(records, window_minutes=60)

# Compact JSON for agent context:
print(errors_to_json_summary(view, top_n=20))
```

### 2 — Build from in-memory records

```python
from datetime import datetime, timezone
from harness_skills.error_aggregation import ErrorRecord, aggregate_errors

records = [
    ErrorRecord(
        timestamp=datetime.now(tz=timezone.utc),
        domain="gate_runner",
        error_type="TimeoutError",
        message="Gate timed out after 30 s",
        severity="error",
    ),
    # … more records …
]
view = aggregate_errors(records, window_minutes=60)
```

### 3 — Query helpers

```python
from harness_skills.error_aggregation import top_errors, errors_by_domain, domain_summary

# Top 10 errors globally:
top_errors(view, n=10)

# Top 5 errors in a specific domain:
top_errors(view, n=5, domain="gate_runner")

# {domain -> [ErrorGroup]} index:
errors_by_domain(view)

# Bird's-eye domain overview (sorted by total error count):
domain_summary(view)
# → [{"domain": "gate_runner", "total_errors": 42, "distinct_patterns": 3,
#     "top_severity": "error", "rising_patterns": 1}, …]
```

---

## Agent Query Runner

The `run_error_query` coroutine wires the aggregation view into a
`ClaudeSDKClient` session with two MCP tools:

| Tool | Description |
|------|-------------|
| `get_error_domain_list` | Lists all active domains with counts and dominant severity. Call this first for a domain overview. |
| `query_recent_errors` | Returns top error groups, optionally filtered to one domain. Accepts `domain` (str) and `limit` (int, max 50). |

```python
import asyncio
from harness_skills.error_query_agent import run_error_query
from harness_skills.error_aggregation import load_errors_from_log, aggregate_errors

records = load_errors_from_log("/var/log/harness/errors.ndjson")
view    = aggregate_errors(records)

result = asyncio.run(
    run_error_query(
        prompt="Which domain has the most rising errors in the last hour?",
        view=view,
        model="claude-opus-4-6",
        max_turns=6,
    )
)
print(result)
```

Or use `build_error_tools` to get the MCP server object and plug it into an
existing agent session:

```python
from harness_skills.error_query_agent import build_error_tools
from claude_agent_sdk import ClaudeAgentOptions

server  = build_error_tools(records=records)
options = ClaudeAgentOptions(
    mcp_servers={"error-aggregation": server},
    allowed_tools=["query_recent_errors", "get_error_domain_list"],
    # … other options …
)
```

---

## NDJSON Log Format

`load_errors_from_log` reads newline-delimited JSON files.  Required fields per
line:

```json
{"timestamp": "2026-03-14T10:00:00Z", "domain": "gate_runner", "error_type": "TimeoutError", "message": "Gate timed out after 30 s"}
```

Optional fields: `stack_hint` (first stack-trace line, improves deduplication),
`severity` (`"error"` | `"warning"` | `"critical"`, default `"error"`).

Lines that cannot be parsed are silently skipped.

---

## Data Structures

### `ErrorRecord`

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | `datetime` | When the event occurred (UTC). |
| `domain` | `str` | Logical component (e.g. `gate_runner`). |
| `error_type` | `str` | Short classification (e.g. `TimeoutError`). |
| `message` | `str` | Full or truncated error message. |
| `stack_hint` | `str` | First stack-trace line (deduplication key). |
| `severity` | `str` | `"error"` \| `"warning"` \| `"critical"`. |

### `ErrorGroup`

| Field | Type | Description |
|-------|------|-------------|
| `domain` | `str` | Originating component. |
| `error_type` | `str` | Error classification. |
| `pattern` | `str` | Normalised fingerprint used for deduplication. |
| `frequency` | `int` | Total occurrences in the analysis window. |
| `first_seen` | `datetime` | Earliest timestamp in the group. |
| `last_seen` | `datetime` | Most-recent timestamp in the group. |
| `sample_message` | `str` | Representative message (most recent). |
| `severity` | `str` | Dominant severity across all records. |
| `trend` | `str` | `"rising"` \| `"falling"` \| `"stable"`. |

### `ErrorAggregationView`

| Field | Type | Description |
|-------|------|-------------|
| `groups` | `list[ErrorGroup]` | All deduplicated groups, sorted by frequency ↓. |
| `by_domain` | `dict[str, list[ErrorGroup]]` | Domain-indexed groups. |
| `window_start` | `datetime` | Start of the analysis window (UTC). |
| `window_end` | `datetime` | End of the analysis window (UTC). |
| `total_events` | `int` | Raw event count processed. |
| `domain_count` | `int` | Number of distinct domains seen. |

---

## Key Files

| Path | Purpose |
|------|---------|
| `harness_skills/error_aggregation.py` | Pure-Python aggregation — `ErrorRecord`, `ErrorGroup`, `ErrorAggregationView`, all helpers. |
| `harness_skills/error_query_agent.py` | Agent SDK interface — MCP tools, `build_error_tools`, `run_error_query`, CLI. |
| `skills/error-aggregation/scripts/query_errors.py` | Standalone CLI helper script. |
