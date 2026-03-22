---
name: debt-tracker
description: "Technical debt tracker so agents can log known shortcuts, compromises, or TODOs into docs/exec-plans/debt.md with a severity level and clear remediation notes. Debt items are auto-assigned sequential DEBT-NNN IDs, and the summary table is rebuilt on every write. Use when: (1) identifying a shortcut or workaround taken during implementation, (2) logging a TODO that cannot be addressed in the current plan, (3) noting a security, reliability, or maintainability concern for later remediation, (4) resolving a previously logged debt item with a description of what was done, (5) printing a current debt summary to check overall health, (6) reviewing which items are open or already resolved, (7) triaging debt by severity before a release or sprint planning session. Triggers on: log debt, technical debt, record debt, track debt, known shortcut, TODO tracker, debt item, debt entry, remediation, debt summary, DEBT-NNN, open debt, resolve debt, mark resolved, severity high, severity critical, debt tracker, shortcuts taken, known compromise, debt log, debt register."
---

# Technical Debt Tracker Skill

## Overview

The **debt-tracker** skill gives every agent a shared register for known
technical debt: shortcuts accepted under time pressure, security gaps deferred
to a later sprint, and architectural compromises that need revisiting.

Each debt item is written to **`docs/exec-plans/debt.md`** as a Markdown table
row with a sequential `DEBT-NNN` identifier, a four-level severity rating, a
short description, and explicit remediation notes.  The summary table at the
bottom of that file is rebuilt automatically on every write.

Key properties:

- **Self-initialising** — `docs/exec-plans/debt.md` is created from a
  canonical template on the first write if it does not already exist.
- **ID-assigned** — IDs are derived from the highest existing `DEBT-NNN` in
  the file, so parallel agents do not collide as long as their writes do not
  overlap within the same millisecond.
- **Two-section layout** — open items live under `## Open Debt`; resolved items
  are moved to `## Resolved Debt` by the `resolve` command.
- **Summary rebuilt on every write** — the `## Debt Summary` table always
  reflects current counts without any manual editing.

---

## Workflow

**Do you want to record a new shortcut, compromise, or TODO?**
→ [Log a debt item](#logging-a-debt-item)

**Do you want to mark an existing item as fixed?**
→ [Resolve a debt item](#resolving-a-debt-item)

**Do you want an overview of current debt health?**
→ [Print a summary](#printing-a-summary)

---

## Logging a Debt Item

### CLI

```bash
# High-severity auth gap
python skills/debt_tracker.py log \
    --severity high \
    --area "src/auth/middleware.py" \
    --description "Auth token validated only in middleware — service-layer callers bypass it" \
    --remediation "Move validation into AuthService.verify(); make middleware delegate to it" \
    --logged-by "agent/planner-v1"

# Medium-severity config shortcut
python skills/debt_tracker.py log \
    --severity medium \
    --area "src/api/rate_limit.py" \
    --description "Rate limit is a hard-coded 100 req/min constant — not configurable per tenant" \
    --remediation "Load limit from tenant config / env var; add integration test for custom limits" \
    --logged-by "agent/coder-v1"

# Low-severity polish item with an explicit timestamp
python skills/debt_tracker.py log \
    --severity low \
    --area "skills/debt_tracker.py" \
    --description "No async support; all file I/O is blocking" \
    --remediation "Wrap file reads/writes with anyio.to_thread.run_sync" \
    --logged-by "agent/coder-v1" \
    --logged-at "2026-03-22 10:00 UTC"
```

### Programmatic

```python
from skills.debt_tracker import DebtTracker

tracker = DebtTracker()

debt_id = tracker.log(
    severity="high",
    area="src/auth/middleware.py",
    description="Auth token validated only in middleware — service-layer callers bypass it",
    remediation="Move validation into AuthService.verify(); make middleware delegate to it",
    logged_by="agent/planner-v1",
)
print(f"Logged {debt_id}")   # e.g. "Logged DEBT-004"
```

`log()` prints a confirmation line to stdout and returns the assigned
`DEBT-NNN` string so it can be referenced in commit messages or progress log
entries.

---

## Resolving a Debt Item

### CLI

```bash
python skills/debt_tracker.py resolve \
    --id DEBT-001 \
    --resolution "Moved token validation into AuthService.verify(); middleware now delegates; all tests green" \
    --resolved-by "agent/coder-v1"
```

### Programmatic

```python
tracker.resolve(
    id_="DEBT-001",
    resolution="Moved token validation into AuthService.verify(); all tests green",
    resolved_by="agent/coder-v1",
)
```

`resolve()` removes the row from the `## Open Debt` table, appends it to
`## Resolved Debt`, and rebuilds the summary.  It raises `ValueError` if no
open entry with the given ID is found.

---

## Printing a Summary

### CLI

```bash
python skills/debt_tracker.py summary
```

Example output:

```
=== Technical Debt Summary ===
  Total open : 3
  Critical  : 0
  High      : 1
  Medium    : 1
  Low       : 1
  Resolved  : 2
```

### Programmatic

```python
tracker.summary()    # prints to stdout
```

---

## Severity Levels

| Severity | Emoji | Meaning | SLA |
|----------|-------|---------|-----|
| `critical` | 🔴 **critical** | Blocks correctness, security, or production safety | Remediate before next release |
| `high` | 🟠 **high** | Degrades reliability or maintainability significantly | Remediate within 1–2 sprints |
| `medium` | 🟡 **medium** | Noticeable friction or tech-debt accumulation | Remediate within the quarter |
| `low` | 🟢 **low** | Minor polish or nice-to-have | Track and batch into a cleanup sprint |

---

## Debt File Format

The tracker maintains `docs/exec-plans/debt.md` with three sections:

```markdown
# Technical Debt Tracker

> Agents append entries below using `skills/debt_tracker.py`.

---

## Severity Key
…

---

## Open Debt

<!-- agents append new entries here — do not remove this comment -->

| ID | Severity | Area / File | Description | Remediation Notes | Logged By | Logged At | Status |
|----|----------|-------------|-------------|-------------------|-----------|-----------|--------|
| DEBT-001 | 🟠 **high** | src/auth/middleware.py | Auth token validated only … | Move validation into … | agent/planner-v1 | 2026-03-22 10:00 UTC | open |

---

## Resolved Debt

<!-- move entries here when remediation is complete -->

| ID | Severity | Area / File | Description | Resolution | Resolved By | Resolved At |
|----|----------|-------------|-------------|------------|-------------|-------------|

---

## Debt Summary

_Updated automatically by `skills/debt_tracker.py` on each run._

| Metric | Count |
|--------|-------|
| Total open | 1 |
| Critical | 0 |
| High | 1 |
| Medium | 0 |
| Low | 0 |
| Resolved (all time) | 0 |
```

The two HTML comments (`<!-- agents append new entries here … -->` and
`<!-- move entries here when remediation is complete -->`) are load-bearing
anchors — do not remove or rename them.

---

## Data Structures

### `DebtTracker`

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `log` | `(severity, area, description, remediation, logged_by, logged_at=None) → str` | `DEBT-NNN` | Append a new open-debt entry; rebuilds summary. |
| `resolve` | `(id_, resolution, resolved_by, resolved_at=None) → None` | — | Move entry from Open to Resolved; rebuilds summary. Raises `ValueError` if ID not found. |
| `summary` | `() → None` | — | Print plain-text debt summary to stdout. |

Constructor accepts an optional `debt_file: Path` to override the default
`docs/exec-plans/debt.md` location (useful in tests).

---

## Key Files

| Path | Purpose |
|------|---------|
| `skills/debt_tracker.py` | Full implementation — `DebtTracker`, severity helpers, CLI entry-point. |
| `skills/debt-tracker/SKILL.md` | This document — agent routing metadata and usage guide. |
| `docs/exec-plans/debt.md` | Generated debt register; auto-created on first write. |
