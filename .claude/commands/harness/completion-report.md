# Harness Completion Report

Generate a **post-execution plan completion report** that answers three
questions after one or more execution plans have run:

1. **What was done?** — every completed task with timing and agent attribution.
2. **What technical debt was incurred?** — skipped tasks and tasks with
   debt-marker keywords (`TODO`, `FIXME`, `HACK`, `WORKAROUND`, etc.) in
   their notes.
3. **What follow-up is needed?** — blocked, pending, skipped, and
   still-running tasks that require action after the plan run.

Plans are sourced from:
- Local YAML / JSON plan files (`--plan-file`)
- The claw-forge state service (`GET /features` at `CLAW_FORGE_STATE_URL`)
- Both simultaneously (mixed mode)

Use this skill at the end of a plan run — or whenever you need a structured
answer to: *"What happened, what shortcuts were taken, and what's left to do?"*

---

## Usage

```bash
# Table report (interactive terminal)
/harness:completion-report

# Machine-parseable JSON (agents / CI)
/harness:completion-report --output-format json

# YAML (human-friendly, still machine-parseable)
/harness:completion-report --output-format yaml

# Load from a specific plan file
/harness:completion-report --plan-file plan.yaml

# Load multiple plan files
/harness:completion-report --plan-file plan-a.yaml --plan-file plan-b.yaml --output-format json

# Filter to a single plan by ID
/harness:completion-report --plan-id PLAN-001 --output-format json

# Only show high-severity and critical debt
/harness:completion-report --min-debt-severity high

# Skip the state service (offline / CI)
/harness:completion-report --plan-file plan.yaml --no-state-service

# Custom state service URL
/harness:completion-report --state-url http://localhost:9999 --output-format json

# Pipeline composition — status check then completion report
harness status --then completion-report --output-format json
```

---

## Instructions

### Step 1 — Locate plan files or verify the state service

Check whether local plan files exist:

```bash
ls -1 *.yaml *.yml *.json plan*.yaml .claude/plan*.yaml 2>/dev/null || echo "__NONE__"
```

If no local files are found, probe the state service:

```bash
STATE_URL="${CLAW_FORGE_STATE_URL:-http://localhost:8888}"
curl -sf "$STATE_URL/features" 2>/dev/null | head -c 200 || echo "__UNREACHABLE__"
```

If both are unavailable, report to the user that no plan data is accessible.

---

### Step 2 — Run the completion-report command

```bash
uv run harness completion-report --output-format json 2>&1
```

> **Fallback** — if `uv` is unavailable:
>
> ```bash
> python -m harness_skills.cli.main completion-report --output-format json
> ```
>
> Or with a local plan file:
>
> ```bash
> uv run harness completion-report --plan-file plan.yaml --output-format json
> ```

Capture stdout (structured JSON/YAML/table) and stderr (warnings, diagnostics).

**Exit codes:**

| Code | Meaning |
|---|---|
| `0` | Report rendered successfully |
| `1` | No plan data found |
| `2` | Parse or validation error |

---

### Step 3 — Parse the response

The command emits a `PlanCompletionReport` JSON object.  Key fields:

#### Top-level envelope

| Field | Use |
|---|---|
| `command` | Always `"harness completion-report"` |
| `status` | `passed` (100 % done, no debt) \| `warning` (debt or blocked tasks) |
| `timestamp` | ISO-8601 UTC timestamp |
| `duration_ms` | Command execution time |
| `message` | One-line human summary |

#### `summary` — aggregate metrics

| Field | Type | Use |
|---|---|---|
| `total_plans` | int | Total number of plans analysed |
| `fully_completed_plans` | int | Plans where every task is `done` |
| `partial_plans` | int | Plans with at least one non-done task |
| `total_tasks` | int | Total tasks across all plans |
| `completed_tasks` | int | Tasks that reached `done` |
| `skipped_tasks` | int | Tasks that were skipped |
| `blocked_tasks` | int | Tasks that are blocked |
| `pending_tasks` | int | Tasks not yet started |
| `running_tasks` | int | Tasks still in `running` state at report time |
| `overall_completion_pct` | float | Global task completion % (0–100) |
| `total_debt_items` | int | Total debt items across all plans |
| `total_follow_up_items` | int | Total follow-up items across all plans |
| `data_source` | enum | `file` \| `state-service` \| `mixed` \| `none` |
| `state_service_reachable` | bool\|null | Whether the state service responded |

#### `completed_tasks[]` — what was done

| Field | Use |
|---|---|
| `task_id` | Unique task identifier |
| `title` | Human-readable task title |
| `plan_id` | Parent plan identifier |
| `assigned_agent` | Agent that completed the task (`null` = unassigned) |
| `started_at` | ISO-8601 UTC start timestamp |
| `completed_at` | ISO-8601 UTC completion timestamp |
| `duration_min` | Wall-clock duration in minutes (`null` if timestamps unavailable) |
| `notes` | Free-form notes attached to the task |

#### `debt[]` — technical debt incurred

| Field | Use |
|---|---|
| `plan_id` | Parent plan identifier |
| `source_task_id` | Task that produced the debt |
| `source_task_title` | Title of the source task |
| `description` | Human-readable debt description |
| `severity` | `critical` \| `high` \| `medium` \| `low` |

Debt items are generated for:
- **Skipped tasks** — work that was deliberately deferred.
- **Tasks with debt-marker notes** — notes containing `TODO`, `FIXME`, `HACK`,
  `DEBT`, `WORKAROUND`, `SHORTCUT`, `INCOMPLETE`, `REVISIT`, `REFACTOR`,
  `TEMPORARY`, `TEMP`, or `WIP` (case-insensitive).

#### `follow_up[]` — actions required after the plan

| Field | Use |
|---|---|
| `plan_id` | Parent plan identifier |
| `task_id` | Unique task identifier |
| `title` | Human-readable task title |
| `category` | `blocked` \| `pending` \| `skipped` \| `dependency` \| `incomplete` |
| `priority` | `critical` \| `high` \| `medium` \| `low` |
| `reason` | Short explanation of why follow-up is required |
| `depends_on` | Task IDs that must be resolved first |
| `assigned_agent` | Agent last assigned to this task (`null` = unassigned) |

---

### Step 4 — Render the human-readable report

Produce the following output based on the parsed response.

**Header + overview block:**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  harness completion-report  —  Plan Completion Report
  2026-03-20T12:34:56Z  ·  source: file
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Total plans         :  2
  Fully completed     :  1
  Partial             :  1
  Total tasks         :  8
  Completed           :  6      75.0%
  Skipped             :  1
  Blocked             :  1
  Debt items          :  2
  Follow-up items     :  3
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Completed tasks table:**

```
Plan       Task ID    Title                      Agent         Duration
────────── ────────── ────────────────────────── ─────────     ────────
PLAN-001   TASK-001   Scaffold module            agent-alpha   45.2 min
PLAN-001   TASK-002   Write tests                agent-beta    120.0 min
PLAN-002   TASK-001   Deploy to staging          agent-gamma   —
```

**Technical debt table (if any):**

```
Severity   Plan       Task       Task Title              Description
────────── ────────── ────────── ───────────────────────  ──────────────────────────
high       PLAN-001   TASK-003   Review auth flow        TODO in task notes: TODO: revisit token expiry logic
medium     PLAN-002   TASK-002   DB migrations           Task was skipped and not completed: DB migrations.
```

**Follow-up required table (if any):**

```
    Category     Plan       Task ID    Title                 Priority  Reason
── ──────────── ────────── ────────── ────────────────────  ────────  ──────────────────────────
🔴  blocked      PLAN-002   TASK-004   Deploy to prod        high      Task is blocked.
⬜  pending      PLAN-001   TASK-005   Write docs            low       Task was not started.
⏭️  skipped      PLAN-002   TASK-002   DB migrations         medium    Task was skipped during execution.
```

---

### Step 5 — Emit structured data (agent-readable)

After the human-readable section, always emit the raw `PlanCompletionReport`
as a fenced JSON block so downstream agents can act without re-running:

```json
{
  "command": "harness completion-report",
  "status": "warning",
  "timestamp": "2026-03-20T12:34:56Z",
  "duration_ms": 87,
  "message": "2 plan(s) | 75.0% done | 2 debt item(s) | 3 follow-up(s)",
  "summary": {
    "total_plans": 2,
    "fully_completed_plans": 1,
    "partial_plans": 1,
    "total_tasks": 8,
    "completed_tasks": 6,
    "skipped_tasks": 1,
    "blocked_tasks": 1,
    "pending_tasks": 0,
    "running_tasks": 0,
    "overall_completion_pct": 75.0,
    "total_debt_items": 2,
    "total_follow_up_items": 3,
    "data_source": "file",
    "state_service_reachable": null
  },
  "plans": [...],
  "completed_tasks": [...],
  "debt": [...],
  "follow_up": [...]
}
```

---

### Step 6 — Recommended actions

After presenting the report, suggest next steps based on the summary:

| `summary` condition | Recommended action |
|---|---|
| `total_debt_items > 0` | Review `debt[]` items — create follow-up tickets for each debt item |
| `blocked_tasks > 0` | Unblock tasks — run `/coordinate` to detect dependency deadlocks |
| `pending_tasks > 0` and `overall_completion_pct < 100` | Re-run the plan or schedule the remaining tasks |
| `running_tasks > 0` | Check whether agents are still active — resume with `/harness:resume` |
| `overall_completion_pct == 100` and `total_debt_items == 0` | Clean run — consider tagging a release |
| `state_service_reachable == false` | State service offline — restart or pass `--plan-file` instead |

---

## Options

| Flag | Default | Effect |
|---|---|---|
| `--output-format json\|yaml\|table` | `table` (TTY) / `json` (non-TTY) | Output format |
| `--plan-file PATH` | *(none)* | Load plan from file; repeat for multiple files |
| `--state-url URL` | `http://localhost:8888` | State service base URL |
| `--plan-id PLAN_ID` | *(all)* | Filter to specific plan ID(s); repeat to include multiple |
| `--no-state-service` | off | Skip state service fetch (offline / CI mode) |
| `--min-debt-severity critical\|high\|medium\|low` | `low` | Minimum severity for debt items to include |

Environment:
- `CLAW_FORGE_STATE_URL` — overrides `--state-url` default

---

## Schema

The JSON/YAML output conforms to `harness_skills.models.completion.PlanCompletionReport`.

Import in Python:
```python
from harness_skills.models.completion import PlanCompletionReport
report = PlanCompletionReport.model_validate_json(raw_json)
print(report.summary.overall_completion_pct)
print([d.severity for d in report.debt])
print([f.category for f in report.follow_up])
```

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Post-run completion summary with debt and follow-up | **`/harness:completion-report`** ← you are here |
| Live snapshot of all plan statuses | `/harness:status` |
| Check whether a plan is stale | `/harness:detect-stale` |
| Detect which agents conflict on files | `/coordinate` |
| Verify code quality after edits | `/harness:lint` |
| Full quality gate before merge | `/harness:evaluate` or `/check-code` |
| Resume an interrupted plan | `/harness:resume` |

---

## Notes

- **Read-only** — this skill never modifies plan files or the state service.
- **Debt detection is heuristic** — keywords are matched against the raw
  `notes` field of each task.  False positives are possible; review the
  `debt[].description` field to confirm.
- **`duration_min` accuracy** — derived from `started_at` / `completed_at`
  ISO-8601 timestamps in the plan file.  If these timestamps are absent,
  `duration_min` is `null`.
- **`status == "warning"`** when any debt or blocked tasks exist; `"passed"`
  only when overall completion is 100 % and no debt was detected.
- **`--min-debt-severity`** filters debt items *before* they are counted in
  `summary.total_debt_items` — useful in CI where you only want to gate on
  critical debt.
- **Pipeline-composable** — chain with other harness commands:
  ```bash
  harness status --then completion-report --output-format json
  ```
