# Harness Detect-Stale

Scan an execution plan for tasks with **no progress updates beyond a configurable
idle threshold** and emit a structured `StalePlanResponse`.  When stale tasks are
found, an optional Claude-powered narrative diagnoses the root cause and recommends
concrete recovery steps.

In addition to plan-task staleness, the skill scans **all generated artifact files**
(AGENTS.md, ARCHITECTURE.md, PRINCIPLES.md, EVALUATION.md) for two types of risk:

1. **Age-based staleness** — artifact's `last_updated` date exceeds the threshold.
2. **Source-file drift** — source files *referenced* inside the artifact have been
   modified since the artifact was last updated, indicating the documentation may no
   longer accurately describe the code it documents.

Each artifact receives a composite **staleness score** (0.0 = fresh, 1.0 = severely
stale) that blends age (60 %) with drift ratio (40 %), giving agents a single
sortable signal for prioritising documentation refresh work.

Use this skill whenever you need a fast answer to:
- *"Is this plan still making progress, or has it quietly stalled?"*
- *"Which of my generated docs are out of date or describe code that has changed?"*

---

## Usage

```bash
# Detect stale tasks — default threshold: 1 800 s (30 min)
/harness:detect-stale --plan-file plan.json

# Custom threshold (10 minutes) with pretty-printed output
/harness:detect-stale --plan-file plan.json --threshold 600 --pretty

# Skip the Claude LLM analysis (fast, offline-friendly)
/harness:detect-stale --plan-file plan.json --skip-llm

# Tag the plan with a human-readable ID
/harness:detect-stale --plan-file plan.json --plan-id sprint-42

# Emit only raw JSON (no progress output on stderr)
/harness:detect-stale --plan-file plan.json --skip-llm 2>/dev/null
```

---

## Instructions

### Step 1 — Locate or build the plan file

Check whether a `plan.json` (or equivalent) already exists in the working directory:

```bash
ls -1 *.json plan*.json .claude/plan*.json 2>/dev/null || echo "__NONE__"
```

If no plan file is found, check the state service for a live plan:

```bash
STATE_URL="${CLAW_FORGE_STATE_URL:-http://localhost:8888}"
curl -sf "$STATE_URL/features" 2>/dev/null
```

If the state service is unreachable and no plan file is available, inform the user
that a `plan.json` input file is required and show the expected schema (Step 2).

---

### Step 2 — Validate the plan file schema

The plan file must be a JSON **array** of task objects.  Each object must include:

| Field | Type | Required | Description |
|---|---|---|---|
| `task_id` | string | ✅ | Unique task identifier |
| `title` | string | ✅ | Human-readable task title |
| `status` | enum | ✅ | `pending` \| `in_progress` \| `completed` \| `blocked` |
| `last_updated` | ISO-8601 datetime | ✅ | UTC timestamp of most recent progress update |
| `assigned_agent` | string | — | Agent currently responsible |
| `depends_on` | string[] | — | List of `task_id`s this task depends on |

Example minimal plan:

```json
[
  {
    "task_id": "t1",
    "title": "Scaffold auth module",
    "status": "in_progress",
    "assigned_agent": "agent-alpha",
    "last_updated": "2026-03-13T08:00:00Z"
  },
  {
    "task_id": "t2",
    "title": "Write integration tests",
    "status": "pending",
    "last_updated": "2026-03-13T09:30:00Z",
    "depends_on": ["t1"]
  }
]
```

---

### Step 3 — Run the detector

```bash
uv run python -m harness_skills.stale_plan_detector \
  --plan-file plan.json \
  --threshold 1800 \
  --pretty \
  2>&1
```

> **Fallback** — if the module is not importable:
>
> ```bash
> python -m harness_skills.stale_plan_detector \
>   --plan-file plan.json \
>   --threshold 1800 \
>   --pretty
> ```

Capture both stdout (structured JSON) and stderr (progress/LLM stream).

**Exit codes:**

| Code | Meaning |
|---|---|
| `0` | All tasks healthy — no stale tasks detected |
| `1` | One or more stale tasks detected |
| `2` | Input error (bad JSON, missing required field, etc.) |

---

### Step 4 — Parse and render the response

The detector emits a `StalePlanResponse` JSON object.  Key fields:

| Field | Use |
|---|---|
| `status` | `passed` (healthy) \| `failed` (stale tasks found) |
| `summary.overall_health` | `healthy` \| `degraded` \| `critical` |
| `summary.stale_tasks` | Count of stale tasks |
| `summary.total_tasks` | Total task count |
| `summary.threshold_seconds` | Configured threshold |
| `summary.most_idle_task_id` | Task ID with the longest idle period |
| `summary.max_idle_seconds` | Longest idle duration (seconds) |
| `stale_task_details[]` | Full per-task staleness detail |
| `llm_analysis` | Claude narrative (null if `--skip-llm`) |
| `analysis_model` | Model used for analysis |

Severity mapping per stale task:

| `severity` | Condition |
|---|---|
| `INFO` | idle < 2× threshold |
| `WARNING` | idle < 4× threshold |
| `ERROR` | idle < 8× threshold |
| `CRITICAL` | idle ≥ 8× threshold |

---

### Step 5 — Render the human-readable report

Produce the following output based on the parsed response:

**When all tasks are healthy (`overall_health == "healthy"`):**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Stale Plan Detector — ✅ HEALTHY
  Plan: <plan_id>  ·  <N> tasks  ·  threshold: <T>s
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅ All <N> tasks are making progress.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**When stale tasks exist (`overall_health == "degraded" | "critical"`):**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Stale Plan Detector — ⚠ DEGRADED | 🔴 CRITICAL
  Plan: <plan_id>  ·  <N> tasks  ·  threshold: <T>s
  <stale_count> stale  ·  <healthy_count> healthy
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Stale Tasks (most idle first)
────────────────────────────────────────────────────
  🔴 CRITICAL  t1  "Scaffold auth module"
               status=in_progress  agent=agent-alpha
               idle=14 400s  (4.0× threshold)

  🟡 WARNING   t3  "Update DB schema"
               status=pending  agent=unassigned
               idle=4 200s  (2.3× threshold)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

If `llm_analysis` is present, append it in a clearly labelled section:

```
  Claude Analysis  (model: claude-opus-4-6)
  ─────────────────────────────────────────
  <narrative text from llm_analysis>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Severity → display icon mapping:

| Severity | Icon |
|---|---|
| `CRITICAL` | 🔴 CRITICAL |
| `ERROR` | 🟠 ERROR |
| `WARNING` | 🟡 WARNING |
| `INFO` | 🔵 INFO |

---

### Step 6 — Emit structured data (agent-readable)

After the human-readable section, always emit the raw `StalePlanResponse` as a
fenced JSON block so downstream agents can act on it without re-running the detector:

```json
{
  "command": "harness detect-stale",
  "status": "failed",
  "message": "2 stale task(s) detected in plan 'sprint-42'.",
  "duration_ms": 312,
  "summary": {
    "plan_id": "sprint-42",
    "total_tasks": 5,
    "stale_tasks": 2,
    "healthy_tasks": 3,
    "threshold_seconds": 1800,
    "most_idle_task_id": "t1",
    "max_idle_seconds": 14400,
    "overall_health": "critical"
  },
  "stale_task_details": [
    {
      "task_id": "t1",
      "title": "Scaffold auth module",
      "status": "in_progress",
      "assigned_agent": "agent-alpha",
      "last_updated": "2026-03-13T08:00:00Z",
      "idle_seconds": 14400,
      "threshold_seconds": 1800,
      "severity": "critical",
      "recommendation": null
    }
  ],
  "llm_analysis": "Task t1 … (narrative)",
  "analysis_model": "claude-opus-4-6"
}
```

The schema matches `harness_skills.models.stale.StalePlanResponse`.
Consumers should check `summary.overall_health` first; if not `healthy`, iterate
`stale_task_details` sorted by `idle_seconds` descending to prioritise the most
urgent tasks.

---

### Step 6.5 — Scan harness artifact files for staleness and source-file drift

In addition to scanning plan tasks, scan **all generated artifact files** for two
documentation-risk categories:

**1. Age-based staleness** — compare the artifact's `last_updated` front-matter
date against the threshold.

**2. Source-file drift** — extract every source-file path the artifact *references*
(Python imports, backtick spans, explicit file paths) and check whether any of those
files have been modified since the artifact's `last_updated` date.  A file modified
after the doc signals that the documentation may no longer be accurate.

**Default artifact staleness threshold: 30 days** (overridable via
`--artifact-threshold-days`).

**Artifacts tracked:** AGENTS.md, ARCHITECTURE.md, PRINCIPLES.md, EVALUATION.md plus
any `AGENTS.md` discovered in subdirectories.

#### Age severity classification

| Condition | Severity |
|---|---|
| `age ≤ threshold` | `healthy` |
| `threshold < age ≤ 2×threshold` | `INFO` — consider refreshing |
| `2×threshold < age ≤ 4×threshold` | `WARNING` — overdue for update |
| `age > 4×threshold` | `CRITICAL` — severely out of date |
| `last_updated` field missing | `WARNING` — artifact lacks version identifier |
| File missing entirely | `ERROR` — expected artifact absent from repository |

#### Staleness score formula

Each artifact receives a composite **staleness score** in `[0.0, 1.0]`:

```
age_score   = min(1.0, age_days / (4 × threshold_days))
drift_ratio = (missing_refs + drifted_refs) / total_refs
staleness_score = 0.6 × age_score + 0.4 × drift_ratio
```

- `0.0` = completely fresh, no drift detected
- `1.0` = severely old artifact AND all referenced files have changed

#### Source-file reference extraction

The detector looks for three pattern types inside each artifact:

| Pattern | Example in doc | Mapped path |
|---|---|---|
| Python `from … import` | `from tests.browser.agent_driver import AgentDriver` | `tests/browser/agent_driver.py` |
| Backtick span with extension | `` `requirements.txt` `` | `requirements.txt` |
| Explicit path pattern | `tests/browser/conftest.py` | `tests/browser/conftest.py` |

Only local paths with tracked extensions (`.py .ts .yaml .json .md .sh …`) are
checked.  URLs, version numbers, and paths inside `.git/`, `.venv/`, `node_modules/`
are automatically excluded.

Include artifact staleness results in the `StalePlanResponse` JSON under
`artifact_staleness`.  Each result now carries `drift` and `staleness_score`:

```json
"artifact_staleness": {
  "threshold_days": 30,
  "artifacts_checked": 4,
  "stale_artifacts": 1,
  "missing_artifacts": 0,
  "results": [
    {
      "file": "AGENTS.md",
      "last_updated": "2026-03-22",
      "age_days": 1,
      "severity": "healthy",
      "staleness_score": 0.002,
      "drift": {
        "referenced_files": ["tests/browser/agent_driver.py", "requirements.txt"],
        "missing_files": [],
        "drifted_files": [],
        "drift_ratio": 0.0,
        "staleness_score": 0.002
      }
    },
    {
      "file": "ARCHITECTURE.md",
      "last_updated": "2025-11-01",
      "age_days": 139,
      "severity": "CRITICAL",
      "staleness_score": 0.892,
      "drift": {
        "referenced_files": ["harness_skills/stale_plan_detector.py", "harness_skills/models/stale.py"],
        "missing_files": [],
        "drifted_files": [
          {
            "path": "harness_skills/stale_plan_detector.py",
            "exists": true,
            "mtime_date": "2026-03-23",
            "days_newer_than_doc": 143
          }
        ],
        "drift_ratio": 0.5,
        "staleness_score": 0.892
      }
    },
    {
      "file": "PRINCIPLES.md",
      "last_updated": "2026-02-14",
      "age_days": 37,
      "severity": "INFO",
      "staleness_score": 0.185,
      "drift": null
    },
    {
      "file": "EVALUATION.md",
      "last_updated": "2026-03-18",
      "age_days": 5,
      "severity": "healthy",
      "staleness_score": 0.012,
      "drift": {
        "referenced_files": [],
        "missing_files": [],
        "drifted_files": [],
        "drift_ratio": 0.0,
        "staleness_score": 0.012
      }
    }
  ]
}
```

Add a corresponding **Artifact Freshness** section to the human-readable report.
When drift is detected, list the drifted files indented below the artifact line:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Artifact Freshness  (threshold: 30 days)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅  AGENTS.md          last_updated=2026-03-22   age=1d    score=0.002
  🔴  ARCHITECTURE.md    last_updated=2025-11-01   age=139d  CRITICAL  score=0.892
      ↳ drift: 1/2 referenced file(s) changed  (ratio=50%)
         📝  harness_skills/stale_plan_detector.py  (143d newer)
  🔵  PRINCIPLES.md      last_updated=2026-02-14   age=37d   INFO  score=0.185
  ✅  EVALUATION.md      last_updated=2026-03-18   age=5d    score=0.012
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  1 stale artifact(s) found
  → Run /harness:update to refresh all artifact timestamps.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

If `--skip-artifacts` is passed, omit this section entirely.

---

### Step 7 — Recommended recovery actions

After presenting the report, suggest concrete next steps based on severity:

| `overall_health` | Recommended action |
|---|---|
| `healthy` | No action needed. |
| `degraded` | Investigate stale `WARNING`/`ERROR` tasks; ping assigned agents. |
| `critical` | Immediately reassign or restart stale tasks; check for deadlocks via `/coordinate`. |

If any stale task has `status == "blocked"`, recommend running `/coordinate` to
check whether a dependency is holding it up.

---

## Options

| Flag | Default | Effect |
|---|---|---|
| `--plan-file PATH` | *(required)* | JSON file with the task array |
| `--threshold SECONDS` | `1800` | Idle threshold in seconds — tasks idle longer are flagged |
| `--plan-id STRING` | `default-plan` | Label used in the response envelope and LLM prompt |
| `--model MODEL` | `claude-opus-4-6` | Anthropic model for LLM narrative analysis |
| `--api-key KEY` | `$ANTHROPIC_API_KEY` | Anthropic API key |
| `--skip-llm` | off | Skip Claude analysis (fast, offline-safe) |
| `--pretty` | off | Pretty-print JSON output (2-space indent) |
| `--artifact-threshold-days N` | `30` | Max artifact age in days before flagging as stale |
| `--skip-artifacts` | off | Skip the artifact freshness scan entirely |

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Check whether a plan is making progress | **`/harness:detect-stale`** ← you are here |
| Detect which agents conflict on files | `/coordinate` |
| Verify code quality after edits | `/harness:lint` |
| Full quality gate before merge | `/harness evaluate` or `/check-code` |
| Understand which files a plan touches | `/harness:context` |

---

## Notes

- **Completed tasks are never flagged** — only `pending`, `in_progress`, and
  `blocked` tasks are evaluated for staleness.
- **Threshold is strict-greater-than** — a task idle for exactly the threshold
  value is *not* stale (`idle > threshold`, not `idle >= threshold`).
- **LLM analysis requires `ANTHROPIC_API_KEY`** — if the key is absent and
  `--skip-llm` is not passed, the detector logs a warning and proceeds without
  analysis rather than failing.
- **CI-safe exit codes** — exit `0` = healthy, `1` = stale tasks found.  Wire
  `1` as a soft gate (warn-only) in CI unless you want hard failures.
- This skill is **read-only** — it never modifies the plan file or the state service.
