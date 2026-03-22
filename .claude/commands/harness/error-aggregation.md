# Harness Error Aggregation

Generate a **structured error aggregation view** that groups recent harness error events
by **domain** and **frequency** so agents can query the error landscape without parsing
raw log lines.

The view pre-computes:

| Feature | Description |
|---|---|
| **Deduplication** | Identical stack traces and similar messages are merged into a single `ErrorGroup` |
| **Trend detection** | Each group carries a `trend` of `rising`, `falling`, or `stable` |
| **Domain breakdown** | Groups are indexed by the logical component that produced them (e.g. `gate_runner`, `lsp`, `deploy`) |
| **JSON serialisation** | The view is pre-serialised into compact JSON for embedding in agent context budgets |

Use this skill to:
- **Diagnose** which component is failing most often
- **Investigate** a spike in a specific domain
- **Check** whether an error rate is rising or recovering
- **Brief** a remediation agent before it starts work
- **Summarise** errors across a multi-agent pipeline

---

## Usage

```bash
# Domain overview — bird's-eye table of all domains (no Claude call)
/harness:error-aggregation --domain-overview

# JSON summary of top 20 errors across all domains (no Claude call)
/harness:error-aggregation --json-summary

# Ask a natural-language question (requires Claude SDK)
/harness:error-aggregation --prompt "Which domains are producing the most errors right now?"

# Restrict the analysis to a specific domain
/harness:error-aggregation --prompt "Are there any rising errors in the deploy domain?"

# Custom log file and time window
/harness:error-aggregation --log-file /var/log/harness/errors.ndjson --window 30 --domain-overview

# Include top-N groups in JSON summary
/harness:error-aggregation --json-summary --top-n 50
```

---

## Instructions

### Step 1 — Locate the log file

Check for an NDJSON error log.  Search in order:

```bash
# 1. Explicit --log-file argument (highest priority)
LOG_FILE="${1:-}"

# 2. Common default paths
for candidate in \
    ".claw-forge/errors.ndjson" \
    "logs/harness-errors.ndjson" \
    "/var/log/harness/errors.ndjson" \
    "harness-errors.ndjson"; do
  if [ -f "$candidate" ]; then
    LOG_FILE="$candidate"
    break
  fi
done

if [ -z "$LOG_FILE" ]; then
  echo "[harness:error-aggregation] No log file found — running with empty record set."
fi
```

---

### Step 2A — Domain overview mode (`--domain-overview`)

When `--domain-overview` is passed, delegate to the query_errors CLI:

```bash
uv run python skills/error-aggregation/scripts/query_errors.py \
  ${LOG_FILE:+--log-file "$LOG_FILE"} \
  --window "${WINDOW:-60}" \
  --domain-overview \
  2>&1
```

> **Fallback** — if `uv` is unavailable:
> ```bash
> python skills/error-aggregation/scripts/query_errors.py \
>   ${LOG_FILE:+--log-file "$LOG_FILE"} \
>   --window "${WINDOW:-60}" \
>   --domain-overview
> ```

The output is a human-readable table:

```
Domain         Total  Patterns   Severity    Rising
──────────────────────────────────────────────────
gate_runner       42         3   error            1
lsp               17         2   warning          0
deploy             8         1   critical         1
```

Skip to **Step 5** after printing the table.

---

### Step 2B — JSON summary mode (`--json-summary`)

When `--json-summary` is passed:

```bash
uv run python skills/error-aggregation/scripts/query_errors.py \
  ${LOG_FILE:+--log-file "$LOG_FILE"} \
  --window "${WINDOW:-60}" \
  --top-n "${TOP_N:-20}" \
  --json-summary \
  2>&1
```

The output is a machine-readable JSON block — emit it directly and skip to **Step 5**.

---

### Step 2C — Agent query mode (default / `--prompt`)

When a `--prompt` is provided or no mode flag is set:

```bash
uv run python -m harness_skills.error_query_agent \
  ${LOG_FILE:+--log-file "$LOG_FILE"} \
  --window "${WINDOW:-60}" \
  --model "${MODEL:-claude-opus-4-6}" \
  --max-turns "${MAX_TURNS:-6}" \
  --prompt "${PROMPT:-Summarise the most critical recent errors grouped by domain.}" \
  2>&1
```

The agent session has two tools available:

| Tool | Description |
|---|---|
| `get_error_domain_list` | Lists all active domains with counts and dominant severity — call first for a domain overview |
| `query_recent_errors` | Returns top error groups, optionally filtered to one domain (`domain` str, `limit` int ≤ 50) |

Stream the agent output to stdout.  Skip to **Step 5** when the agent returns.

---

### Step 3 — Parse the aggregation (programmatic path)

When this skill is invoked from another agent or script, build the view in Python and emit
the structured output:

```python
from harness_skills.error_aggregation import (
    load_errors_from_log,
    aggregate_errors,
    domain_summary,
    errors_to_json_summary,
    top_errors,
)

# Load + aggregate
records = load_errors_from_log(log_file, window_minutes=60)  # [] if no file
view    = aggregate_errors(records, window_minutes=60)

# JSON summary for agent context
print(errors_to_json_summary(view, top_n=20))

# Domain overview
for row in domain_summary(view):
    print(row)

# Top 10 globally
for group in top_errors(view, n=10):
    print(group)

# Top 5 in a specific domain
for group in top_errors(view, n=5, domain="gate_runner"):
    print(group)
```

---

### Step 4 — Render the human-readable dashboard

After parsing, display:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  harness error-aggregation
  window: last 60 min  ·  <N> events  ·  <M> domains
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Domain Overview (sorted by total errors ↓)
────────────────────────────────────────────────────
  Domain         Total  Patterns   Severity    Rising
  ───────────────────────────────────────────────────
  gate_runner       42         3   error            1
  lsp               17         2   warning          0
  deploy             8         1   critical         1

Top Error Groups (global, frequency ↓)
────────────────────────────────────────────────────
  #  Domain       Type            Freq  Sev       Trend  Last seen
  ─────────────────────────────────────────────────────────────────
   1  gate_runner  TimeoutError      28  error    rising  2 min ago
   2  gate_runner  AssertionError    14  error    stable  5 min ago
   3  deploy       ConnectionError    8  critical rising  1 min ago
   4  lsp          TypeError          9  warning  stable  8 min ago
   …

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

If there are **no errors** in the window, print:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  harness error-aggregation — No errors in the last 60 min ✅
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### Step 5 — Emit structured data (agent-readable)

Always emit the raw aggregation as a fenced JSON block after the human-readable section so
downstream agents can consume it without re-running:

```json
{
  "command": "harness error-aggregation",
  "window_minutes": 60,
  "log_file": "/path/to/errors.ndjson",
  "window_start": "2026-03-22T09:00:00Z",
  "window_end":   "2026-03-22T10:00:00Z",
  "total_events": 67,
  "domain_count": 3,
  "domain_overview": [
    {"domain": "gate_runner", "total_errors": 42, "distinct_patterns": 3, "top_severity": "error",    "rising_patterns": 1},
    {"domain": "lsp",         "total_errors": 17, "distinct_patterns": 2, "top_severity": "warning",  "rising_patterns": 0},
    {"domain": "deploy",      "total_errors":  8, "distinct_patterns": 1, "top_severity": "critical", "rising_patterns": 1}
  ],
  "top_errors": [
    {
      "domain":          "gate_runner",
      "error_type":      "TimeoutError",
      "frequency":       28,
      "severity":        "error",
      "trend":           "rising",
      "first_seen":      "2026-03-22T09:02:10Z",
      "last_seen":       "2026-03-22T09:58:01Z",
      "recency_seconds": 119,
      "sample_message":  "Gate timed out after 30 s waiting for assertion",
      "pattern":         "gate timed out after s waiting for assertion"
    }
  ]
}
```

Key fields for downstream agents:

| Field | Use |
|---|---|
| `domain_overview[].rising_patterns` | Non-zero → investigate this domain first |
| `top_errors[].trend` | `"rising"` → escalating; prioritise over `"stable"` |
| `top_errors[].recency_seconds` | Small → very recent; large → may be quieting |
| `top_errors[].frequency` | Higher = more impactful |
| `top_errors[].severity` | `"critical"` > `"error"` > `"warning"` |

---

### Step 6 — Highlight actionable insights

After the JSON block, surface the top findings:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Insights
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Hottest domain    : gate_runner (42 errors, 1 rising pattern)
    → TimeoutError is rising — check gate runner timeout configuration.

  Critical rising   : deploy → ConnectionError (8 occurrences, rising)
    → Connectivity issue in deploy domain — check network/service health.

  Stable noise      : lsp → TypeError (9 occurrences, stable)
    → Not escalating; schedule for normal triage.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Rules:
- **Hottest domain**: domain with the highest `total_errors`.
- **Critical rising**: any `top_errors` entry where `severity == "critical"` and `trend == "rising"` — emit one insight per entry (up to 3).
- **Stable noise**: high-frequency groups with `trend == "stable"` — mention the top 1-2 as lower-priority.
- If all errors are stable and none are critical, print:
  `All error groups are stable — no immediate escalation needed.`
- If no errors exist, print:
  `No errors in the analysis window — system appears healthy.`

---

## Options

| Flag | Default | Effect |
|---|---|---|
| `--log-file PATH` | *(auto-detect)* | Path to NDJSON error log |
| `--window MINUTES` | `60` | Analysis window in minutes |
| `--domain-overview` | off | Print domain overview table and exit (no Claude call) |
| `--json-summary` | off | Print raw aggregation JSON and exit (no Claude call) |
| `--top-n N` | `20` | Number of top error groups in JSON summary |
| `--prompt TEXT` | `"Summarise the most critical recent errors grouped by domain."` | Natural-language question for the agent query runner |
| `--model MODEL` | `claude-opus-4-6` | Claude model to use for agent queries |
| `--max-turns N` | `6` | Maximum agent turns before stopping |

---

## NDJSON Log Format

`--log-file` accepts newline-delimited JSON files.  Required fields per line:

```json
{"timestamp": "2026-03-22T10:00:00Z", "domain": "gate_runner", "error_type": "TimeoutError", "message": "Gate timed out after 30 s"}
```

Optional fields: `stack_hint` (first stack-trace line, improves deduplication),
`severity` (`"error"` | `"warning"` | `"critical"`, default `"error"`).

Lines that cannot be parsed are silently skipped.

---

## Key Files

| Path | Purpose |
|---|---|
| `harness_skills/error_aggregation.py` | Pure-Python aggregation — `ErrorRecord`, `ErrorGroup`, `ErrorAggregationView`, all helpers |
| `harness_skills/error_query_agent.py` | Agent SDK interface — MCP tools, `build_error_tools`, `run_error_query`, CLI |
| `skills/error-aggregation/scripts/query_errors.py` | Standalone CLI helper script |
| `skills/error-aggregation/SKILL.md` | Full skill specification |

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Which domain is failing most right now? | **`/harness:error-aggregation --domain-overview`** ← you are here |
| Is a specific error rate rising or falling? | **`/harness:error-aggregation --prompt "Is TimeoutError rising in gate_runner?"`** |
| Feed a structured error brief to a remediation agent | **`/harness:error-aggregation --json-summary`** |
| Understand overall plan/task health | `/harness:status` |
| Verify code quality after a fix | `/harness:lint` |
| Check test coverage | `/harness:coverage-gate` |
| Full quality gate before merge | `/check-code` |
| Detect cross-agent file conflicts | `/coordinate` |

---

## Notes

- **Read-only** — this skill never modifies log files, the state service, or any source files.
- **SDK-free modes** — `--domain-overview` and `--json-summary` do not call Claude; they work with `python` or `uv run python` only.
- **Empty log is valid** — if no `--log-file` is found, the view is built from an empty record set and all counts are zero.
- **Deduplication is heuristic** — the fingerprint strips timestamps, hex addresses, integers, and short quoted strings before grouping.  Errors that differ only in variable values are merged; structurally different errors are kept separate.
- **Trend detection requires ≥ 4 events** — groups with fewer than 4 occurrences are always marked `"stable"`.
- **Agent session is pre-seeded** — `run_error_query` embeds a pre-computed JSON summary in the system prompt so the model has structured context before it calls any tools.
- **Composable** — `build_error_tools` returns an SDK MCP server object that can be merged into any existing `ClaudeAgentOptions.mcp_servers` dict, enabling the error query tools in any agent session.
