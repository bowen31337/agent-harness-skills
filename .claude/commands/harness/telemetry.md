# Harness Telemetry

Generate and attach **telemetry hooks** to a `claude_agent_sdk` session so usage
data is automatically collected and persisted to `docs/harness-telemetry.json`.

The hooks track three categories of harness activity:

| Category | What is recorded |
|---|---|
| **Artifact reads** | Which harness files (`.md`, `.yaml`, `.py`, …) agents open via `Read`, `Glob`, or `Grep` |
| **CLI command invocations** | How often each `/command` skill is called (detected in `UserPromptSubmit`) |
| **Gate failures** | Which quality gates (`ruff`, `mypy`, `pytest`, …) fail most often (parsed from `Bash` output) |

Use this skill to:
- **Analyze** artifact utilization rates, command call frequency, and gate effectiveness scores
- **Identify** underutilized artifacts (`cold`/`unused`) for redesign or removal, and silent
  gates for reconfiguration — via `--analyze` mode backed by `harness_skills.telemetry_reporter`
- **View** the current raw usage dashboard from `docs/harness-telemetry.json`
- **Generate** the hook integration snippet for a new SDK session
- **Reset** all recorded telemetry data

---

## Usage

```bash
# Full analytics report — utilization rates, command frequency, gate effectiveness
/harness:telemetry --analyze

# Analytics with noise filter (hide artifacts with < 3 reads)
/harness:telemetry --analyze --min-reads 3

# Analytics capped to top 10 artifacts
/harness:telemetry --analyze --top-n 10

# Analytics in JSON-only mode (machine-readable TelemetryReport)
/harness:telemetry --analyze --format json

# Show current telemetry totals (raw dashboard, no scoring)
/harness:telemetry

# Show totals + generate integration snippet
/harness:telemetry --generate

# Emit only the raw JSON report
/harness:telemetry --format json

# Reset all telemetry (prompts for confirmation)
/harness:telemetry --reset

# Point at a non-default output file
/harness:telemetry --output-path path/to/custom-telemetry.json
```

---

## Instructions

### Step 1A — Analytics mode (`--analyze`)

When `--analyze` is passed, delegate to `harness_skills.telemetry_reporter` which
derives **rates and scores** from the raw counts — not just totals:

```bash
uv run python -m harness_skills.telemetry_reporter \
  --telemetry-file "${OUTPUT_PATH:-docs/harness-telemetry.json}" \
  --format "${FORMAT:-table}" \
  ${MIN_READS:+--min-reads $MIN_READS} \
  ${TOP_N:+--top-n $TOP_N} \
  2>&1
```

> **Fallback** — if `uv` is unavailable:
> ```bash
> python -m harness_skills.telemetry_reporter --telemetry-file docs/harness-telemetry.json
> ```

The reporter emits a structured `TelemetryReport` JSON block after the human-readable
table.  Key computed fields that go beyond raw counts:

| Field | Description |
|---|---|
| `artifacts[].utilization_rate` | Read count ÷ total reads → `0.0–1.0` |
| `artifacts[].category` | `hot` (top 20 %) · `warm` (20–60 %) · `cold` (bottom 40 %) · `unused` |
| `artifacts[].recommendation` | Action for cold/unused artifacts |
| `commands[].frequency_rate` | Invocations ÷ total invocations → `0.0–1.0` |
| `commands[].sessions_active` | Sessions in which this command appeared |
| `gates[].effectiveness_score` | Failures ÷ max-gate-failures → `0.0–1.0` |
| `gates[].signal_strength` | `high` (≥0.6) · `medium` (0.3–0.6) · `low` (>0) · `silent` |
| `gates[].recommendation` | Action for low/silent gates |
| `summary.cold_artifact_count` | Cold + unused artifact count |
| `summary.silent_gate_count` | Gates that never fired |

**Exit codes for `--analyze`:**

| Code | Meaning |
|---|---|
| `0` | All artifacts warm/hot; all gates active |
| `1` | Cold/unused artifacts or silent gates detected — action recommended |
| `2` | Internal error (unreadable JSON, I/O failure) |

Skip to **Step 5** (emit structured data) after running the reporter.

---

### Step 1B — Read the current telemetry file (default / `--format json` / `--generate` / `--reset`)

```bash
cat docs/harness-telemetry.json 2>/dev/null || echo "__NONE__"
```

If the output is `__NONE__` or the file does not exist, treat all counters as zero
and note that no sessions have been recorded yet.

Parse the JSON.  Expected schema (`schema_version: "1.0"`):

```json
{
  "schema_version": "1.0",
  "last_updated": "<ISO-8601>",
  "totals": {
    "artifact_reads":          { "<path-or-pattern>": <count>, … },
    "cli_command_invocations": { "<command-name>":     <count>, … },
    "gate_failures":           { "<gate-name>":        <count>, … }
  },
  "sessions": [
    {
      "session_id":              "<id>",
      "started_at":              "<ISO-8601>",
      "ended_at":                "<ISO-8601>",
      "artifact_reads":          { … },
      "cli_command_invocations": { … },
      "gate_failures":           { … }
    }
  ]
}
```

---

### Step 2 — Render the human-readable dashboard

Produce the following report from the parsed data:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Harness Telemetry — Usage Dashboard
  Last updated : <last_updated>   Sessions : <N>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Artifact Reads (top 10 — most-read harness files)
────────────────────────────────────────────────────
  <path-or-pattern>   <count>   ████████████
  <path-or-pattern>   <count>   ████████
  …

CLI Command Invocations
────────────────────────────────────────────────────
  <command>   <count>   ██████████████████
  <command>   <count>   ████████
  …

Gate Failures (most common first)
────────────────────────────────────────────────────
  <gate>   <count>   ████████████████████
  <gate>   <count>   ████
  …

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Rules:
- Sort each section **descending** by count.
- Artifact reads: cap the display at the **top 10** entries.
- CLI commands and gate failures: show **all** entries.
- Render a simple bar (`█` characters) proportional to the highest count in that
  section, capped at 30 characters.
- If a section has no data, print `(none recorded)`.
- If the telemetry file was absent, prepend a note:
  `Note: docs/harness-telemetry.json not found — no data yet.`

Alternatively, run the built-in CLI to produce the same output:

```bash
uv run python harness_telemetry.py show 2>&1
```

---

### Step 3 — Generate the hook integration snippet (only if `--generate` is passed)

Emit a ready-to-paste Python snippet that wires `HarnessTelemetry` into a
`claude_agent_sdk` session:

````
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Hook Integration Snippet
  Add this to any file that calls claude_agent_sdk.query()
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

```python
from harness_telemetry import HarnessTelemetry
from claude_agent_sdk import query, ClaudeAgentOptions

# Instantiate once per process — loads existing data from disk automatically.
tel = HarnessTelemetry()          # writes to docs/harness-telemetry.json

async def run_agent(prompt: str) -> None:
    async for message in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            allowed_tools=["Read", "Glob", "Grep", "Bash"],
            hooks=tel.build_hooks(),   # attach telemetry hooks
        ),
    ):
        print(message)

    # Optional: flush immediately after each session.
    # HarnessTelemetry also flushes automatically on the Stop hook.
    tel.flush()
```

What the hooks capture:
  PostToolUse / Read    → artifact_reads   (which files agents open)
  PostToolUse / Glob    → artifact_reads   (glob patterns + returned paths)
  PostToolUse / Grep    → artifact_reads   (search pattern + directory)
  UserPromptSubmit      → cli_command_invocations  (/command at prompt start)
  PostToolUse / Bash    → gate_failures    (ruff / mypy / pytest failures)
  PostToolUseFailure / Bash → gate_failures (hard bash errors)
  Stop                  → flush()          (persist to docs/harness-telemetry.json)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
````

---

### Step 4 — Handle `--reset` (only if flag is passed)

> **Warning**: This permanently wipes all telemetry history.

Ask for explicit confirmation before proceeding:

```
About to reset docs/harness-telemetry.json.
This will erase all recorded sessions and totals.
Type YES to confirm, or anything else to cancel: _
```

If the user confirms, run:

```bash
uv run python harness_telemetry.py reset 2>&1
```

If the module is not available via `uv run`, execute directly:

```bash
python harness_telemetry.py reset 2>&1
```

Report success or failure.

---

### Step 5 — Emit structured data (agent-readable)

After the human-readable dashboard, always emit the raw telemetry as a fenced JSON
block so downstream agents can consume it without re-reading the file:

```json
{
  "command": "harness telemetry",
  "output_path": "docs/harness-telemetry.json",
  "schema_version": "1.0",
  "last_updated": "<ISO-8601>",
  "session_count": 4,
  "totals": {
    "artifact_reads": {
      "PRINCIPLES.md": 12,
      "harness.config.yaml": 9,
      ".claude/principles.yaml": 7,
      "docs/exec-plans/progress.md": 5
    },
    "cli_command_invocations": {
      "check-code": 8,
      "harness:lint": 6,
      "coordinate": 3,
      "checkpoint": 2
    },
    "gate_failures": {
      "ruff": 11,
      "mypy": 7,
      "pytest": 4,
      "ruff-format": 2
    }
  },
  "top_artifact": "PRINCIPLES.md",
  "top_command": "check-code",
  "top_gate_failure": "ruff"
}
```

The `top_*` fields are derived from the highest-count entry in each totals section
(empty string if the section has no data).

---

### Step 6 — Highlight actionable insights

After the JSON block, emit a short **Insights** section that surfaces the three most
useful observations from the data:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Insights
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Most-read artifact   : PRINCIPLES.md (12 reads across 4 sessions)
    → Agents consult this file heavily — keep it concise and scannable.

  Most-invoked command : check-code (8 invocations)
    → Consider automating check-code in CI so agents only run it on demand.

  Most-failing gate    : ruff (11 failures)
    → Run `uv run ruff check . --fix && uv run ruff format .` before committing
      to reduce friction.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Rules:
- If any section has no data, replace that insight line with `(no data yet)`.
- Insight recommendations should be **concrete and actionable**, not generic.
- If `top_gate_failure` is `ruff` or `ruff-format`: suggest the auto-fix command.
- If `top_gate_failure` is `mypy`: suggest adding type annotations to the most
  commonly edited files.
- If `top_gate_failure` is `pytest`: suggest running tests locally before pushing.
- If `top_command` appears ≥ 5 times: suggest automation in CI.
- If `top_artifact` is a principles or config file (`.yaml`, `PRINCIPLES.md`,
  `CLAUDE.md`): suggest making it shorter or adding a summary section at the top.

---

## Options

| Flag | Default | Effect |
|---|---|---|
| `--analyze` | off | Run the full analytics report (utilization rates, frequency, gate effectiveness) |
| `--min-reads N` | `0` | *(analyze mode)* Exclude artifacts with fewer than N reads from display |
| `--top-n N` | *(all)* | *(analyze mode)* Cap the artifact list at N entries |
| `--generate` | off | Emit the Python hook-integration snippet (Step 3) |
| `--reset` | off | Wipe all telemetry data after confirmation (Step 4) |
| `--format table\|json` | `table` | Output format — `table` (human-readable + JSON fence) or `json` (raw JSON only) |
| `--output-path PATH` | `docs/harness-telemetry.json` | Read/write a different telemetry file |
| `--top N` | `10` | *(dashboard mode)* Limit artifact-reads display to top N entries |
| `--no-insights` | off | Skip the Insights section (Step 6, dashboard mode only) |

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Identify underutilized artifacts & silent gates | **`/harness:telemetry --analyze`** ← you are here |
| See raw usage counts (quick dashboard) | **`/harness:telemetry`** |
| Wire telemetry into a new SDK session | **`/harness:telemetry --generate`** |
| Verify architecture & principles compliance | `/harness:lint` |
| Full quality gate (tests, coverage, security) | `/check-code` |
| Detect whether a plan is making progress | `/harness:detect-stale` |
| Detect cross-agent file conflicts | `/coordinate` |

---

## Notes

- **Read-only by default** — `show` mode never modifies any file.  Only `--reset`
  mutates `docs/harness-telemetry.json`, and only after confirmation.
- **Atomic writes** — `HarnessTelemetry.flush()` writes to a `.tmp` file then
  renames it, so a crash mid-write cannot corrupt the JSON.
- **Session deduplication** — if the same `session_id` is seen twice, the later
  record replaces the earlier one.  Totals are always the canonical source of truth.
- **Offline-safe** — no network calls are made.  The telemetry file is local.
- **Hook attachment is optional** — telemetry is only collected when
  `ClaudeAgentOptions(hooks=tel.build_hooks())` is passed to `query()`.  Sessions
  without hooks do not generate any entries.
- **Gate detection is heuristic** — `_GATE_PATTERNS` maps command substrings to
  gate names.  Custom wrappers around `ruff`/`mypy`/`pytest` may not be detected
  unless their output contains the standard failure markers.  Add entries to
  `_GATE_PATTERNS` in `harness_telemetry.py` to extend coverage.
- **Command file discovery** — known CLI commands are populated by scanning
  `.claude/commands/` at startup.  If a new skill is added, the next
  `HarnessTelemetry()` instantiation picks it up automatically.
