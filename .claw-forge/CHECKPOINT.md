# Checkpoint — 20260320T124355

## Status
- Tests: 238 passing, 52 failing (5 collection errors in tests/plugins + test_task_lock.py)
- Features: 0/1 complete (1 session pending in state DB)
- Snapshot: snapshots/snapshot-20260320T124355.json
- Features: 0/2 complete (2 sessions pending in state DB)
- Snapshot: snapshots/snapshot-20260320T103046.json

## What's working
- State service running at http://localhost:8420 — sessions API responding
- `/harness:plan` — creates execution plans from descriptions or ticket references (commit c7f58a2)
- `/harness:evaluate` — runs all evaluation gates and produces structured pass/fail report (commit 50dab09)
- `/harness:create` — full harness generation from codebase analysis through artifact output (commit 37536e8)
- Task dependency graph via `depends_on` field + `harness status` visualization (commit e5ad1b1)
- Command composition: `harness create --then lint --then evaluate` chaining (commit bfd5015)
- `/harness:checkpoint` — git commit + snapshot + summary
- `/harness:context` — returns minimal file paths/search patterns for a plan or domain (commit 04ecf15)
- `/harness:coordinate` — cross-agent task conflict dashboard (commit 6a34cb0)
- Plan completion report skill — summarizes what was done, debt incurred, and follow-up needed
- Technical debt tracker — logs known shortcuts/TODOs into docs/exec-plans/debt.md with severity and remediation notes
- **NEW**: Git-based checkpoint integration with agent_id/task_id metadata for multi-agent traceability
- Core harness skill CLI, gate plugin infrastructure, data generator, scorer, stale plan detector (238 tests passing)

## What's in progress
- Session `26f70fff-8798-4b59-95b9-5e8bbb775d02` — status: pending
  (project: /Users/bowenli/projects/claw-forge-test/agent-harness-skills, created: 2026-03-19 23:53:06)
- `harness_skills/cli/main.py` — modified (uncommitted changes)

## Known issues
- 52 failing tests:
  - `tests/test_dom_snapshot.py` — TestSkillWrappers and TestAriaLandmarks failures (5 tests)
  - `tests/test_generators/test_evaluation.py` — TestFormatReport JSON formatting failures (4 tests)
  - Additional failures across other test modules (43 tests)
- 5 collection errors (syntax errors) preventing collection of:
  - `tests/test_task_lock.py`
  - `tests/plugins/` (test_gate_plugin, test_integration, test_loader, test_runner)
- Previous merge conflicts in CHECKPOINT.md and task_lock.py — resolved at this checkpoint
- Current feature session remains in pending state

---
_Previous checkpoint: 20260320T113044 — snapshots/snapshot-20260320T113044.json_
- `uv run pytest` fails with sandbox cache permission error — test suite not executable in this environment
- Both sessions remain in pending state — no features completed yet
