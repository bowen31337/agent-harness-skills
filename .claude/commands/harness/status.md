# Harness Status

Generate a **plan status dashboard** showing all active, completed, and blocked
execution plans with full per-task detail and machine-parseable status fields.

Plans are sourced from:
- Local YAML / JSON plan files (``--plan-file``)
- The claw-forge state service (``GET /features`` at `CLAW_FORGE_STATE_URL`)
- Both simultaneously (mixed mode)

Use this skill whenever you need a structured answer to: *"What is the current
state of every plan — what is running, what is blocked, what is done?"*

---

## Usage

```bash
# Table dashboard (interactive terminal)
/harness:status

# Machine-parseable JSON (agents / CI)
/harness:status --format json

# YAML (human-friendly, still machine-parseable)
/harness:status --format yaml

# Load from a specific plan file
/harness:status --plan-file plan.yaml

# Load multiple plan files
/harness:status --plan-file plan-a.yaml --plan-file plan-b.yaml --format json

# Filter to a single plan by ID
/harness:status --plan-id PLAN-001 --format json

# Show only blocked plans
/harness:status --status-filter blocked

# Show only active (running) plans
/harness:status --status-filter active --format json

# Skip the state service (offline / CI)
/harness:status --plan-file plan.yaml --no-state-service

# Custom state service URL
/harness:status --state-url http://localhost:9999 --format json
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

### Step 2 — Run the dashboard command

```bash
uv run harness status --format json 2>&1
```

> **Fallback** — if `uv` is unavailable:
>
> ```bash
> python -m harness_skills.cli.main status --format json
> ```
>
> Or with a local plan file:
>
> ```bash
> uv run harness status --plan-file plan.yaml --format json
> ```

Capture stdout (structured JSON/YAML/table) and stderr (warnings, diagnostics).

**Exit codes:**

| Code | Meaning |
|---|---|
| `0` | Dashboard rendered successfully |
| `1` | No plan data found |
| `2` | Parse or validation error |

---

### Step 3 — Parse the response

The command emits a `StatusDashboardResponse` JSON object.  Key fields:

#### Top-level envelope

| Field | Use |
|---|---|
| `command` | Always `"harness status"` |
| `status` | `passed` (all healthy) \| `warning` (blocked plans) \| `running` (work in progress) |
| `timestamp` | ISO-8601 UTC timestamp |
| `duration_ms` | Command execution time |
| `message` | One-line human summary |

#### `summary` — aggregate metrics

| Field | Type | Use |
|---|---|---|
| `total_plans` | int | Total number of plans loaded |
| `active_plans` | int | Plans with status `running` |
| `completed_plans` | int | Plans with status `done` |
| `blocked_plans` | int | Plans with status `blocked` |
| `pending_plans` | int | Plans with status `pending` |
| `cancelled_plans` | int | Plans with status `cancelled` |
| `total_tasks` | int | Total tasks across all plans |
| `active_tasks` | int | Tasks currently running |
| `completed_tasks` | int | Tasks that are done |
| `blocked_tasks` | int | Tasks that are blocked |
| `overall_completion_pct` | float | Global task completion % (0–100) |
| `data_source` | enum | `file` \| `state-service` \| `mixed` \| `none` |
| `state_service_reachable` | bool\|null | Whether the state service responded |

#### `plans[]` — per-plan snapshots

| Field | Use |
|---|---|
| `plan_id` | Unique plan identifier (e.g. `PLAN-001`) |
| `title` | Human-readable plan title |
| `status` | `pending` \| `running` \| `done` \| `blocked` \| `cancelled` |
| `created_at` | ISO-8601 UTC creation timestamp |
| `updated_at` | ISO-8601 UTC last-update timestamp |
| `source_file` | Path to the source YAML/JSON file (`null` = state service) |
| `task_counts.total` | Total tasks in this plan |
| `task_counts.active` | Tasks currently running |
| `task_counts.completed` | Tasks that are done |
| `task_counts.blocked` | Tasks that are blocked |
| `task_counts.completion_pct` | Per-plan task completion % |
| `tasks[]` | Full task detail list (see below) |

#### `plans[].tasks[]` — per-task detail

| Field | Use |
|---|---|
| `task_id` | Unique task identifier (e.g. `TASK-001`) |
| `title` | Human-readable task title |
| `status` | `pending` \| `running` \| `done` \| `blocked` \| `skipped` |
| `priority` | `critical` \| `high` \| `medium` \| `low` |
| `assigned_agent` | Agent currently responsible (null = unassigned) |
| `lock_status` | `unlocked` \| `locked` \| `done` |
| `depends_on` | List of `task_id`s this task depends on |
| `started_at` | ISO-8601 UTC start timestamp |
| `completed_at` | ISO-8601 UTC completion timestamp |

---

### Step 4 — Render the human-readable dashboard

Produce the following output based on the parsed response.

**Header block:**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  harness status  —  Plan Dashboard
  2026-03-20T12:34:56Z  ·  source: file
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Total plans  :  3
  Active       :  1
  Completed    :  1
  Blocked      :  1
  Tasks done   :  67.5%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Plans overview table:**

```
Plan ID    Title              Status     Tasks  Done  Active  Blocked  Done %
────────── ─────────────────  ─────────  ─────  ────  ──────  ───────  ──────
PLAN-001   Auth module        running       5     3       1       0    60.0%
PLAN-002   DB migrations      done          3     3       0       0   100.0%
PLAN-003   UI refactor        blocked       4     2       0       2    50.0%
```

**Per-plan task breakdown (for each plan):**

```
PLAN-001 — Auth module  [running]
  ✅  TASK-001  Scaffold module       done      high    agent-alpha  —
  🔵  TASK-002  Write tests           running   medium  agent-beta   TASK-001
  ⬜  TASK-003  Review docs           pending   low     —            TASK-002
```

Task status icons:

| Status | Icon |
|---|---|
| `running` | 🔵 |
| `done` | ✅ |
| `blocked` | 🔴 |
| `pending` | ⬜ |
| `skipped` | ⏭️ |

---

### Step 5 — Emit structured data (agent-readable)

After the human-readable section, always emit the raw `StatusDashboardResponse`
as a fenced JSON block so downstream agents can act without re-running:

```json
{
  "command": "harness status",
  "status": "warning",
  "timestamp": "2026-03-20T12:34:56Z",
  "duration_ms": 142,
  "message": "3 plan(s) | 1 active | 1 done | 1 blocked | 67.5% complete",
  "summary": {
    "total_plans": 3,
    "active_plans": 1,
    "completed_plans": 1,
    "blocked_plans": 1,
    "pending_plans": 0,
    "cancelled_plans": 0,
    "total_tasks": 12,
    "active_tasks": 1,
    "completed_tasks": 8,
    "blocked_tasks": 2,
    "pending_tasks": 1,
    "skipped_tasks": 0,
    "overall_completion_pct": 66.7,
    "data_source": "file",
    "state_service_reachable": null
  },
  "plans": [
    {
      "plan_id": "PLAN-001",
      "title": "Auth module",
      "status": "running",
      "created_at": "2026-03-19T08:00:00Z",
      "updated_at": "2026-03-20T11:00:00Z",
      "source_file": "plan-001.yaml",
      "task_counts": {
        "total": 5,
        "active": 1,
        "completed": 3,
        "blocked": 0,
        "pending": 1,
        "skipped": 0
      },
      "tasks": [
        {
          "task_id": "TASK-001",
          "title": "Scaffold module",
          "status": "done",
          "priority": "high",
          "assigned_agent": "agent-alpha",
          "lock_status": "done",
          "depends_on": [],
          "started_at": "2026-03-19T08:00:00Z",
          "completed_at": "2026-03-19T10:00:00Z",
          "notes": null,
          "description": null
        }
      ]
    }
  ]
}
```

Consumers should check `summary.blocked_plans` first; if non-zero, iterate
`plans[]` filtering by `status == "blocked"` and then `tasks[]` filtering by
`status == "blocked"` to find the specific bottleneck.

---

### Step 6 — Recommended actions

After presenting the dashboard, suggest next steps based on the overall state:

| `summary` condition | Recommended action |
|---|---|
| `blocked_plans > 0` | Check blocked tasks — run `/coordinate` to detect dependency deadlocks |
| `active_plans == 0` and `pending_plans > 0` | No agents are running — check agent pool health |
| `overall_completion_pct == 100` | All plans done — consider running `/harness evaluate` for final gate |
| `state_service_reachable == false` | State service offline — restart or pass `--plan-file` instead |

---

## Options

| Flag | Default | Effect |
|---|---|---|
| `--format json\|yaml\|table` | `table` | Output format |
| `--plan-file PATH` | *(none)* | Load plan from file; repeat for multiple files |
| `--state-url URL` | `http://localhost:8888` | State service base URL |
| `--plan-id PLAN_ID` | *(all)* | Filter to specific plan ID(s); repeat to include multiple |
| `--status-filter FILTER` | `all` | Limit to `active`, `completed`, `blocked`, `pending`, `cancelled`, or `all` |
| `--no-state-service` | off | Skip state service fetch (offline / CI mode) |

Environment:
- `CLAW_FORGE_STATE_URL` — overrides `--state-url` default

---

## Schema

The JSON/YAML output conforms to `harness_skills.models.status.StatusDashboardResponse`.

Import in Python:
```python
from harness_skills.models.status import StatusDashboardResponse
response = StatusDashboardResponse.model_validate_json(raw_json)
print(response.summary.overall_completion_pct)
```

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Snapshot of all plan statuses | **`/harness:status`** ← you are here |
| Check whether a plan is *stale* | `/harness:detect-stale` |
| Detect which agents conflict on files | `/coordinate` |
| Verify code quality after edits | `/harness:lint` |
| Full quality gate before merge | `/harness evaluate` or `/check-code` |
| Understand which files a plan touches | `/harness:context` |

---

## Notes

- **Read-only** — this skill never modifies plan files or the state service.
- **Status normalisation** — `in_progress` and `completed` (state-service
  vocabulary) are automatically mapped to `running` and `done` for consistency.
- **Mixed-source mode** — when both `--plan-file` and state-service plans are
  loaded, `summary.data_source` is `"mixed"` and each plan's `source_file`
  field identifies the origin.
- **CI exit codes** — exit `0` even when plans are blocked (the blocked count
  is surfaced in `summary.blocked_plans`); exit `1` only when *no plan data*
  was found at all.
- **Pipeline-composable** — chain with other harness commands:
  ```bash
  harness status --format json --then evaluate
  ```
