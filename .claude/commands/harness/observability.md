# Harness Observability

Generate an **error aggregation view** — a deduplicated, frequency-sorted
summary of recent error events grouped by *domain* — so agents can quickly
identify which components are failing, how often, and whether problems are
getting worse.

The view is produced by `harness_skills.error_aggregation` (pure Python,
no network required) and optionally narrated by a Claude agent via
`harness_skills.error_query_agent`.

---

## Usage

```bash
# Aggregate errors from the default log (last 60 min) — human-readable table
/harness:observability

# Point at a specific NDJSON error log
/harness:observability --log-file /var/log/harness/errors.ndjson

# Change the analysis window (minutes)
/harness:observability --log-file errors.ndjson --window 30

# Filter to a single domain
/harness:observability --log-file errors.ndjson --domain gate_runner

# Show the top-N error groups (default 20)
/harness:observability --log-file errors.ndjson --top-n 10

# Include per-domain breakdown in the JSON output
/harness:observability --log-file errors.ndjson --by-domain

# Machine-readable JSON only (no table)
/harness:observability --log-file errors.ndjson --format json

# Print the raw JSON aggregation summary and exit (no Claude narration)
/harness:observability --log-file errors.ndjson --json-summary

# Ask a natural-language question about the errors (spawns a Claude sub-agent)
/harness:observability --log-file errors.ndjson \
    --prompt "Which domain has the most rising errors right now?"

# Non-default window with a custom prompt
/harness:observability --log-file errors.ndjson --window 120 \
    --prompt "Summarise the top three critical issues across all domains."
```

---

## Instructions

### Step 1 — Locate the error log file

If `--log-file` is provided, use it directly.  Otherwise probe the default
locations in order:

```bash
for CANDIDATE in \
    .harness/errors.ndjson \
    logs/harness-errors.ndjson \
    /var/log/harness/errors.ndjson \
    /tmp/harness-errors.ndjson; do
  [ -f "$CANDIDATE" ] && echo "$CANDIDATE" && break
done
```

If no file is found, proceed with an **empty record set** and set
`data_source = "empty"` in the output.  Report to the user that no log file
was found and suggest passing `--log-file PATH`.

---

### Step 2 — Run the aggregation

#### 2A — JSON summary only (`--json-summary` flag or for internal use)

```bash
uv run python -m harness_skills.error_query_agent \
    --log-file "${LOG_FILE}" \
    --window "${WINDOW:-60}" \
    --json-summary \
    2>/dev/null
```

> **Fallback** — if `uv` is unavailable:
> ```bash
> python -m harness_skills.error_query_agent \
>     --log-file "${LOG_FILE}" \
>     --window "${WINDOW:-60}" \
>     --json-summary
> ```

Capture the JSON output.  This is the pre-computed aggregation view; no
Claude call is made in this mode.

#### 2B — Claude-narrated query (`--prompt TEXT` flag)

```bash
uv run python -m harness_skills.error_query_agent \
    --log-file "${LOG_FILE}" \
    --window "${WINDOW:-60}" \
    --prompt "${PROMPT}" \
    --model "${MODEL:-claude-opus-4-6}" \
    --max-turns "${MAX_TURNS:-6}" \
    2>&1
```

This spawns a Claude sub-agent that calls `query_recent_errors` and
`get_error_domain_list` tools before composing a structured answer.

#### 2C — Default (no `--prompt`, no `--json-summary`)

Run the aggregation in JSON-summary mode (Step 2A) to obtain structured data,
then render the human-readable dashboard yourself in Step 3.

---

### Step 3 — Parse the aggregation JSON

The `--json-summary` output follows this schema:

```json
{
  "window": {
    "start":        "<ISO-8601>",
    "end":          "<ISO-8601>",
    "total_events": 412,
    "domain_count": 5
  },
  "top_errors": [
    {
      "domain":          "gate_runner",
      "error_type":      "TimeoutError",
      "frequency":       38,
      "severity":        "error",
      "trend":           "rising",
      "first_seen":      "<ISO-8601>",
      "last_seen":       "<ISO-8601>",
      "recency_seconds": 42,
      "sample_message":  "Gate timed out after 30s waiting for coverage report",
      "pattern":         "gate timed out after s waiting for coverage report"
    }
  ],
  "domain_overview": [
    {
      "domain":           "gate_runner",
      "total_errors":     95,
      "distinct_patterns": 4,
      "top_severity":     "error",
      "rising_patterns":  2
    }
  ],
  "by_domain": { ... }   // only present when --by-domain is passed
}
```

Key fields for agent decision-making:

| Field | Use |
|---|---|
| `top_errors[].trend` | `"rising"` = escalating, needs immediate action |
| `top_errors[].severity` | `"critical"` = highest priority |
| `top_errors[].recency_seconds` | Small value = still actively firing |
| `top_errors[].frequency` | Absolute hit count in the window |
| `domain_overview[].rising_patterns` | Domains with growing error rates |

---

### Step 4 — Render the human-readable dashboard

Produce the following output from the parsed data.

**Header:**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Harness Observability — Error Aggregation View
  Window : <start> → <end>   (<N> min)
  Events : <total_events>   Domains : <domain_count>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Domain Overview table** (sorted by `total_errors` descending):

```
Domain Overview
────────────────────────────────────────────────────
  Domain          Errors  Patterns  Severity  Rising
  ─────────────────────────────────────────────────
  gate_runner       95       4       error      2  ⚠️
  lsp               41       3       warning    0
  deploy            18       2       critical   1  🔴
  ...
```

Severity icons:
- `critical` → 🔴
- `error`    → ⚠️  (only when `rising_patterns > 0`)
- `warning`  → (no icon)

**Top Errors table** (capped at `--top-n`, default 20):

```
Top Errors  (last <N> min)
────────────────────────────────────────────────────
  #   Domain        Type            Freq  Sev       Trend    Last seen
  ─────────────────────────────────────────────────────────────────────
   1  gate_runner   TimeoutError      38  error     rising↑   42 s ago
   2  lsp           AttributeError    22  warning   stable    4 min ago
   3  deploy        RuntimeError      18  critical  rising↑   12 s ago
  ...
```

Trend indicators: `rising↑` / `falling↓` / `stable`

If `--domain` is set, print only rows for that domain and add a header note:

```
  (filtered to domain: gate_runner)
```

If no errors were found, print:

```
  ✅  No errors recorded in the last <N> minutes.
```

---

### Step 5 — Emit structured data (agent-readable)

After the human-readable dashboard, always emit the `ErrorAggregationResponse`
as a fenced JSON block so downstream agents can parse it without re-running:

```json
{
  "command":        "harness observability",
  "status":         "warning",
  "timestamp":      "<ISO-8601>",
  "duration_ms":    84,
  "message":        "412 events · 5 domains · top domain: gate_runner (95 errors)",
  "window_start":   "<ISO-8601>",
  "window_end":     "<ISO-8601>",
  "window_minutes": 60,
  "total_events":   412,
  "domain_count":   5,
  "data_source":    "log_file",
  "log_source":     ".harness/errors.ndjson",
  "top_errors": [
    {
      "domain":          "gate_runner",
      "error_type":      "TimeoutError",
      "frequency":       38,
      "severity":        "error",
      "trend":           "rising",
      "first_seen":      "<ISO-8601>",
      "last_seen":       "<ISO-8601>",
      "recency_seconds": 42,
      "sample_message":  "Gate timed out after 30s waiting for coverage report",
      "pattern":         "gate timed out after s waiting for coverage report"
    }
  ],
  "domain_overview": [
    {
      "domain":            "gate_runner",
      "total_errors":      95,
      "distinct_patterns": 4,
      "top_severity":      "error",
      "rising_patterns":   2
    }
  ]
}
```

**`status` field mapping:**

| Condition | `status` |
|---|---|
| No errors at all | `"passed"` |
| Only `warning`-severity groups | `"warning"` |
| Any `error`-severity group | `"warning"` |
| Any `critical`-severity group | `"failed"` |
| Any `rising` group with `critical` severity | `"failed"` |

The schema matches `harness_skills.models.errors.ErrorAggregationResponse`.

Import in Python:
```python
from harness_skills.models.errors import ErrorAggregationResponse
response = ErrorAggregationResponse.model_validate_json(raw_json)
# Iterate top errors
for g in response.top_errors:
    if g.trend == "rising" and g.severity == "critical":
        print(f"🔴 URGENT — {g.domain}: {g.error_type} ×{g.frequency}")
```

---

### Step 6 — Surface actionable insights

After the JSON block, emit a short **Insights** section:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Insights
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Most affected domain : gate_runner (95 errors, 2 rising patterns)
    → Investigate TimeoutError — gate timed out after 30s waiting for
      coverage report.  Check if the coverage gate has a misconfigured
      timeout threshold.

  Rising errors        : 3 pattern(s) across 2 domain(s)
    → gate_runner/TimeoutError (38×, last 42 s ago)
    → deploy/RuntimeError      (18×, last 12 s ago)
    → Prioritise these before stable / falling errors.

  Critical errors      : deploy/RuntimeError (18×)
    → Run /harness:status to check whether any running tasks depend on
      the deploy domain; block them before the issue escalates.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Tip: pass --prompt "<question>" to ask a natural-language question
  about these errors using a Claude sub-agent.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Insight rules (apply all that match):**

| Condition | Insight |
|---|---|
| `domain_overview[0].total_errors > 0` | Surface the top domain with its rising-pattern count |
| Any group with `trend == "rising"` | List every rising group with frequency + recency |
| Any group with `severity == "critical"` | Call out critical groups and suggest `/harness:status` |
| `total_events == 0` | Emit `✅ No errors in the last <N> minutes — system looks healthy.` |
| `domain_count >= 5` | Note breadth: "Errors span N domains — consider a system-wide rollback check" |

Recommendations should be **concrete and actionable**:
- For `TimeoutError` in `gate_runner`: suggest checking timeout thresholds in `harness.config.yaml`
- For `AttributeError`: suggest running `mypy` to catch type mismatches early
- For `RuntimeError` in `deploy`: suggest checking recent deployment logs

---

## Options

| Flag | Default | Effect |
|---|---|---|
| `--log-file PATH` | *(auto-detect)* | Path to a newline-delimited JSON (NDJSON) error log |
| `--window N` | `60` | Analysis window in minutes |
| `--domain NAME` | *(all)* | Filter output to a single domain |
| `--top-n N` | `20` | Maximum error groups to display and include in `top_errors` |
| `--by-domain` | off | Include per-domain detail (up to 10 groups per domain) in JSON output |
| `--prompt TEXT` | *(none)* | Ask a natural-language question via a Claude sub-agent |
| `--model MODEL` | `claude-opus-4-6` | Claude model ID (only used with `--prompt`) |
| `--max-turns N` | `6` | Maximum agent turns for `--prompt` mode |
| `--json-summary` | off | Print the raw aggregation JSON and exit (no dashboard) |
| `--format table\|json` | `table` | Output format: `table` = human-readable + JSON fence; `json` = fence only |

Environment:
- `CLAW_FORGE_STATE_URL` — state service base URL (default: `http://localhost:8888`)

---

## NDJSON log format

Each line of the error log must be a JSON object with these fields:

| Field | Required | Example |
|---|---|---|
| `timestamp` | ✅ | `"2026-03-22T14:05:33.210Z"` |
| `domain` | ✅ | `"gate_runner"` |
| `error_type` | ✅ | `"TimeoutError"` |
| `message` | ✅ | `"Gate timed out after 30s"` |
| `stack_hint` | ✗ | `"gate_runner/runner.py:142"` |
| `severity` | ✗ | `"error"` (default) |

Lines that cannot be parsed are silently skipped.

Write a log entry from Python:

```python
import json, sys
from datetime import datetime, timezone

entry = {
    "timestamp":  datetime.now(tz=timezone.utc).isoformat(),
    "domain":     "gate_runner",
    "error_type": "TimeoutError",
    "message":    "Gate timed out after 30s waiting for coverage report",
    "severity":   "error",
}
print(json.dumps(entry), file=sys.stderr)    # or append to a log file
```

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Identify which domain is generating the most errors | **`/harness:observability`** ← you are here |
| Check error trends (rising / falling) over a window | **`/harness:observability --window N`** |
| Ask a natural-language question about errors | **`/harness:observability --prompt "..."`** |
| Detect cross-agent file conflicts | `/coordinate` |
| Check whether a plan is making progress | `/harness:detect-stale` |
| View plan status (running / blocked / done) | `/harness:status` |
| Verify code quality after a fix | `/harness:lint` |
| Full quality gate before merge | `/harness evaluate` or `/check-code` |
| Understand which files a plan touches | `/harness:context` |
| Analyse harness artifact utilization & gate effectiveness | `/harness:telemetry --analyze` |

---

## Notes

- **Read-only** — this skill never writes to the error log or state service.
- **No network required** — aggregation runs entirely in-process using
  `harness_skills.error_aggregation`.  The state service is not queried
  unless a future `--state-service` flag is added.
- **Deduplication is fingerprint-based** — errors with the same `domain`,
  `error_type`, and normalised message pattern are merged into one group
  regardless of minor message variations (e.g. differing numeric values or
  file paths).
- **Trend detection requires ≥ 4 events** — groups with fewer than 4
  records always report `trend = "stable"`.
- **Empty window** — if `--window 0` is passed or the window is so small
  that no events fall within it, `total_events` is 0 and `top_errors` is
  empty.  The skill still emits a valid JSON envelope.
- **CI-safe** — the JSON-summary mode (`--json-summary`) makes no Claude
  API calls; safe to run in pipelines without an API key.
- **Programmatic use** — embed the aggregation in another agent:
  ```python
  from harness_skills.error_aggregation import load_errors_from_log, aggregate_errors
  from harness_skills.error_query_agent import build_error_tools, run_error_query

  records = load_errors_from_log(".harness/errors.ndjson", window_minutes=60)
  view    = aggregate_errors(records)
  answer  = await run_error_query(
      prompt="Which domain needs immediate attention?",
      view=view,
  )
  ```
