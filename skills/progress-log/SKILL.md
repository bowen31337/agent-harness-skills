---
name: progress-log
description: "Append-only agent progress log for tracking step completion within a plan. Agents call this skill to record timestamped entries as they start, finish, fail, or skip individual steps in an execution plan. All entries accumulate in docs/exec-plans/progress.md as a Markdown table — safe for concurrent writes from multiple agents. Use when: (1) starting work on a plan step, (2) marking a step done with a completion note, (3) recording a step failure with error detail, (4) skipping a step that is not applicable, (5) reviewing what steps have been completed so far, (6) generating a per-plan done/total progress summary, (7) coordinating progress visibility across parallel agents. Triggers on: log progress, append progress, mark step done, record step started, step failed, step skipped, progress entry, progress log, plan progress, track step, update progress, what steps are done, show progress, progress summary."
---

# Agent Progress Log Skill

## Overview

The progress-log skill gives every agent a shared, append-only record of plan
execution.  Each call writes one row to `docs/exec-plans/progress.md` — a
Markdown table that any agent or human can read at a glance.

Key properties:

- **Append-only** — rows are never edited or deleted, so the full history is
  always preserved.
- **Concurrent-safe** — multiple agents may append simultaneously; `O_APPEND`
  writes on POSIX filesystems are atomic up to `PIPE_BUF`.
- **Self-initialising** — the file and its parent directory are created
  automatically on the first write.
- **Readable at a glance** — status cells carry emoji labels so the table
  renders clearly in both terminals and GitHub/GitLab previews.

---

## Workflow

**Do you want to record that a step started, finished, failed, or was skipped?**
→ [Append an entry](#appending-an-entry)

**Do you want to review what has been logged so far?**
→ [List entries](#listing-entries)

**Do you want a per-plan done/total summary?**
→ [Print summary](#printing-a-summary)

---

## Appending an Entry

### CLI

```bash
# Step started
python skills/progress_log.py append \
    --plan-id "feature/auth-refactor" \
    --step   "1. Scaffold AuthService" \
    --status  started \
    --agent  "agent/coder-v1"

# Step completed successfully
python skills/progress_log.py append \
    --plan-id "feature/auth-refactor" \
    --step   "1. Scaffold AuthService" \
    --status  done \
    --message "Created src/auth/service.py; all tests green" \
    --agent  "agent/coder-v1"

# Step failed — include error detail in --message
python skills/progress_log.py append \
    --plan-id "feature/auth-refactor" \
    --step   "2. Wire middleware" \
    --status  failed \
    --message "Import cycle detected; needs arch review" \
    --agent  "agent/coder-v1"

# Step intentionally skipped
python skills/progress_log.py append \
    --plan-id "feature/auth-refactor" \
    --step   "4. Migrate legacy tokens" \
    --status  skipped \
    --message "Not applicable — no legacy tokens in this deployment" \
    --agent  "agent/coder-v1"
```

### Programmatic

```python
from skills.progress_log import ProgressLog

log = ProgressLog()

entry = log.append(
    plan_id="feature/auth-refactor",
    step="1. Scaffold AuthService",
    status="done",
    agent="agent/coder-v1",
    message="Created src/auth/service.py; all tests green",
)
print(entry.timestamp, entry.status)
```

`append()` returns a `ProgressEntry` and also prints a confirmation line to
`stderr` so it is visible in agent logs without polluting `stdout`.

---

## Listing Entries

### CLI

```bash
# All entries across all plans
python skills/progress_log.py list

# Entries for one plan only
python skills/progress_log.py list --plan-id "feature/auth-refactor"
```

### Programmatic

```python
from skills.progress_log import ProgressLog

log = ProgressLog()

# All entries (oldest first)
entries = log.list()

# Filtered to one plan
entries = log.list(plan_id="feature/auth-refactor")

for e in entries:
    print(e.timestamp, e.step, e.status, e.message)
```

---

## Printing a Summary

The summary command reports the **latest** recorded status per `(plan_id, step)`
pair, then aggregates counts by plan.

### CLI

```bash
# Summary across all plans
python skills/progress_log.py summary

# Summary for one plan
python skills/progress_log.py summary --plan-id "feature/auth-refactor"
```

Example output:

```
Plan ID                         Total  ✅ done  ❌ failed  ⏭️  skipped  🔵 started
-----------------------------------------------------------------------
feature/auth-refactor               5        3          1            0           1
```

### Programmatic

```python
log.summary()                                    # all plans → stdout
log.summary(plan_id="feature/auth-refactor")     # one plan → stdout
```

---

## Entry Statuses

| Status | Emoji | Meaning |
|--------|-------|---------|
| `started` | 🔵 started | Agent has begun work on the step. |
| `done` | ✅ done | Step completed successfully. |
| `failed` | ❌ failed | Step could not be completed; see `message` for detail. |
| `skipped` | ⏭️  skipped | Step intentionally bypassed (e.g. not applicable). |

A step's *effective* status is its **most-recently logged** status — append a
`done` row after a `started` row to advance the state.

---

## Log File Format

Entries are written to `docs/exec-plans/progress.md` as Markdown table rows:

```markdown
# Agent Progress Log

> Auto-generated by `skills/progress_log.py` — do not edit manually.

<!-- agents append new rows here — do not remove this comment -->

| Timestamp (UTC) | Plan ID | Step | Status | Agent | Message |
|-----------------|---------|------|--------|-------|---------|
| 2026-03-20T09:00:00Z | feature/auth-refactor | 1. Scaffold AuthService | 🔵 started | agent/coder-v1 | — |
| 2026-03-20T09:14:22Z | feature/auth-refactor | 1. Scaffold AuthService | ✅ done | agent/coder-v1 | Created src/auth/service.py; all tests green |
| 2026-03-20T09:15:01Z | feature/auth-refactor | 2. Wire middleware | ❌ failed | agent/coder-v1 | Import cycle detected; needs arch review |
```

Pipe characters inside field values are escaped as `\|` so they do not break
the table.

---

## Data Structures

### `ProgressEntry`

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | `str` | ISO-8601 UTC string (e.g. `2026-03-20T09:00:00Z`). |
| `plan_id` | `str` | Plan / feature identifier (e.g. `feature/auth-refactor`). |
| `step` | `str` | Human-readable step label (e.g. `3. Write unit tests`). |
| `status` | `str` | Canonical status key: `started`, `done`, `failed`, or `skipped`. |
| `agent` | `str` | Identifier of the agent that wrote the entry. |
| `message` | `str` | Optional free-text detail; empty string when not supplied. |

`ProgressEntry.as_dict()` returns all fields as a plain `dict[str, str]`.

### `ProgressLog`

| Method | Signature | Description |
|--------|-----------|-------------|
| `append` | `(plan_id, step, status, agent, message="", timestamp=None) → ProgressEntry` | Write a new row; timestamp defaults to now (UTC). |
| `list` | `(plan_id=None) → list[ProgressEntry]` | Return entries in file order, optionally filtered by plan. |
| `summary` | `(plan_id=None) → None` | Print per-plan aggregated counts to stdout. |

Constructor accepts an optional `log_file: Path` to override the default
`docs/exec-plans/progress.md` location (useful in tests).

---

## Key Files

| Path | Purpose |
|------|---------|
| `skills/progress_log.py` | Full implementation — `ProgressEntry`, `ProgressLog`, CLI entry-point. |
| `docs/exec-plans/progress.md` | Generated log file; auto-created on first write. |
