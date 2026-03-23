---
name: golden-principles-cleanup
description: "Background cleanup task generator for principle violations. Reads .claude/principles.yaml, scans the codebase for violations using the harness principles gate (or text-based fallback), and emits one cleanup task definition per violation cluster into docs/exec-plans/cleanup-tasks.yaml. Each task carries enough context (scope, description, pr_title, pr_body) for an agent to open a focused refactoring PR without any further analysis. Use when: (1) principles have just been added or updated and you want to enforce them across the existing codebase, (2) planning a cleanup sprint and need a structured backlog of refactoring PRs, (3) running post-harness-evaluate cleanup to track principle violations as actionable tasks, (4) generating background work items that can be dispatched to worker agents. Triggers on: generate cleanup tasks, enforce principles, principle violations, refactoring PR backlog, cleanup sprint, background tasks, post-evaluate cleanup."
---

# Golden Principles Cleanup Skill

## Overview

The golden-principles-cleanup skill reads your project's golden rules from
`.claude/principles.yaml`, scans the entire codebase for violations (using the
harness `principles` gate or a text-based fallback), and emits one **cleanup
task definition** per violation cluster into `docs/exec-plans/cleanup-tasks.yaml`.

Each task carries the full context an agent needs to open and complete a
focused refactoring PR:

- `scope` — the list of affected files
- `description` — what to change and why, including affected line numbers and
  concrete refactoring steps
- `pr_title` — a conventional-commit-formatted PR title
- `pr_body` — a complete PR description with What & Why, Changes, and a
  testing checklist

This skill is **read-only** for source files. It never modifies application
code — it only generates the task manifest.

---

## Workflow

```
.claude/principles.yaml
        │
        ▼
 [Step 0] Load principles
        │
        ▼
 [Step 1] Run harness evaluate --gate principles --format json
        │  (falls back to text-based grep scan if harness unavailable)
        ▼
 [Step 2] Group GateFailure items by principle_id
        │
        ▼
 [Step 3] Generate CleanupTask per violation cluster
        │
        ▼
 [Step 4] Write docs/exec-plans/cleanup-tasks.yaml
        │
        ▼
 [Step 5] Publish summary to shared-state.yaml  (optional)
        │
        ▼
 [Step 6] Print summary table
```

**Quick decision guide:**

- Want to see what tasks would be generated without writing a file?
  → Use `--dry-run`
- Only care about must-fix violations?
  → Use `--only-blocking`
- Already generated tasks and want to review them?
  → Use the `list` subcommand

---

## CLI Usage

### Generate cleanup tasks

```bash
# Generate all tasks (harness gate + fallback)
python skills/golden_principles_cleanup.py generate

# Only blocking-severity violations
python skills/golden_principles_cleanup.py generate --only-blocking

# Preview without writing the file
python skills/golden_principles_cleanup.py generate --dry-run

# Custom principles file and output path
python skills/golden_principles_cleanup.py generate \
    --principles-file path/to/principles.yaml \
    --output path/to/cleanup-tasks.yaml

# Generate without publishing to shared-state
python skills/golden_principles_cleanup.py generate --no-publish
```

### List generated tasks

```bash
# Print a summary table of the generated cleanup-tasks.yaml
python skills/golden_principles_cleanup.py list

# List from a custom output path
python skills/golden_principles_cleanup.py list \
    --output path/to/cleanup-tasks.yaml
```

---

## Programmatic Usage

### Generate a manifest

```python
from pathlib import Path
from skills.golden_principles_cleanup import GoldenPrinciplesCleanup

cleanup = GoldenPrinciplesCleanup()

manifest = cleanup.generate_all(
    principles_file=Path(".claude/principles.yaml"),
    output_file=Path("docs/exec-plans/cleanup-tasks.yaml"),
    only_blocking=False,
    dry_run=False,
)

print(f"Generated {manifest.task_count} task(s)")
for task in manifest.tasks:
    print(f"  {task.id}  [{task.severity}]  {task.pr_title}")
```

### Inspect individual tasks

```python
from skills.golden_principles_cleanup import GoldenPrinciplesCleanup, CleanupTask

cleanup = GoldenPrinciplesCleanup()
principles = cleanup.load_principles(Path(".claude/principles.yaml"))
violations = cleanup.run_principles_gate()

if not violations:
    violations = cleanup.fallback_scan(principles)

grouped = cleanup.group_violations(violations, principles)

for principle_id, viols in grouped.items():
    principle = next(p for p in principles if p["id"] == principle_id)
    task: CleanupTask = cleanup.generate_task(principle, viols)
    print(task.model_dump_json(indent=2))
```

### Publish to shared-state

```python
from skills.golden_principles_cleanup import GoldenPrinciplesCleanup

cleanup = GoldenPrinciplesCleanup()
manifest = cleanup.generate_all(
    principles_file=Path(".claude/principles.yaml"),
    output_file=Path("docs/exec-plans/cleanup-tasks.yaml"),
    only_blocking=True,
    dry_run=False,
)
cleanup.publish_to_shared_state(manifest)
```

---

## Output Schema

`docs/exec-plans/cleanup-tasks.yaml` contains a `CleanupTaskManifest`:

| Field | Type | Description |
|-------|------|-------------|
| `generated_at` | `str` | UTC ISO-8601 timestamp when the file was generated |
| `generated_from_head` | `str` | Short git SHA at generation time |
| `task_count` | `int` | Number of tasks in the `tasks` list |
| `tasks` | `list[CleanupTask]` | The cleanup task definitions |

Each `CleanupTask` entry:

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Stable slug: `cleanup-<principle_id>-<slugified-first-file>` |
| `principle_id` | `str` | The violated principle (e.g. `P001`) |
| `principle_category` | `str` | The principle's category (e.g. `architecture`) |
| `severity` | `str` | `blocking` or `suggestion` |
| `title` | `str` | Short imperative description of the fix |
| `scope` | `list[str]` | Sorted list of affected file paths |
| `description` | `str` | Multi-line explanation with rule, files, line numbers, and refactoring steps |
| `pr_title` | `str` | Conventional-commit PR title |
| `pr_body` | `str` | Full PR description (What & Why, Changes, Testing checklist) |
| `generated_at` | `str` | UTC ISO-8601 timestamp for this task |
| `status` | `str` | `pending` (updated by the agent that executes the task) |

### Example entry

```yaml
- id: "cleanup-P001-src-api-views-py"
  principle_id: "P001"
  principle_category: "architecture"
  severity: "blocking"
  title: "Enforce repository layer for all DB queries (P001)"
  scope:
    - "src/api/views.py"
    - "src/api/orders.py"
  description: |
    Principle P001 (architecture/blocking) is violated in 2 file(s).

    Rule: All database queries must go through the repository layer

    Affected files:
      - src/api/views.py:88  — direct db.session usage in view layer
      - src/api/orders.py:42 — Model.query called outside repository

    Refactoring steps:
      1. Create or update src/repositories/user_repository.py with the query logic.
      2. Import and call the repository from the view functions.
      3. Run `/harness:lint --gate principles` to verify zero remaining violations.
      4. Update or add unit/integration tests covering the refactored code.
  pr_title: "refactor: enforce P001 architecture across src/api/views.py, src/api/orders.py"
  pr_body: |
    ## What & Why
    ...
  generated_at: "2026-03-22T10:00:00Z"
  status: "pending"
```

---

## Integration with Other Skills

| Skill | How they interact |
|-------|------------------|
| `/define-principles` | Creates `.claude/principles.yaml` — run it first |
| `/harness:lint` | Validates principle compliance — run after executing a task |
| `/harness:evaluate` | Full gate suite — golden-principles-cleanup can be run as post-processing |
| `shared_state.py` | Receives publish summary if `shared-state.yaml` exists |
| `exec_plan.py` | Cleanup tasks can be registered as execution plan steps |

---

## Key Files

| Path | Purpose |
|------|---------|
| `skills/golden_principles_cleanup.py` | Full implementation — `GoldenPrinciplesCleanup` class, Pydantic models, CLI |
| `skills/golden-principles-cleanup/SKILL.md` | This documentation file |
| `.claude/commands/golden-principles-cleanup.md` | Claude command skill definition |
| `.claude/principles.yaml` | Source of golden rules (created by `/define-principles`) |
| `docs/exec-plans/cleanup-tasks.yaml` | Generated cleanup task manifest (output) |
| `docs/exec-plans/shared-state.yaml` | Shared agent state (receives publish summary) |

---

## Prerequisites

- `PyYAML` must be installed: `pip install pyyaml`
- Pydantic v2 must be installed: `pip install pydantic>=2.0`
- `.claude/principles.yaml` must exist (run `/define-principles` to create it)
- For the harness gate path: `uv` and `harness_skills` package must be available
