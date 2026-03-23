# Multi-Agent Coordination — agent-harness-skills

← [AGENTS.md](../../AGENTS.md)

This project uses four complementary mechanisms so agents can work in parallel without
stepping on each other: **handoff**, **task locking**, **shared state**, and
**stale-plan detection**.  All are backed by the state service at `http://localhost:8888`.

---

## Mechanisms at a Glance

| Mechanism | Module | Skill doc | Use when |
|-----------|--------|-----------|----------|
| Handoff | `harness_skills.handoff` | `.claude/commands/harness/handoff.md` | Passing work between agents |
| Task lock | `harness_skills.task_lock` | `.claude/commands/harness/task-lock.md` | Exclusive resource access |
| Shared state | `harness_skills.` *(shared_state skill)* | `.claude/commands/harness/shared-state.md` | Cross-agent read/write store |
| Stale-plan detection | `harness_skills.stale_plan_detector` | `.claude/commands/harness/detect-stale.md` | Detect abandoned / outdated plans |
| Resume | `harness_skills.resume` | `.claude/commands/harness/resume.md` | Resume an interrupted plan |

---

## 1 · Handoff

A `HandoffDocument` captures the full context one agent needs to continue another's work.

```python
from harness_skills.handoff import HandoffDocument, HandoffProtocol, SearchHints

doc = HandoffDocument(
    task_id="feat-42",
    summary="Implemented CoverageGate; tests pass.  Next: wire into GateEvaluator.",
    artefacts=["harness_skills/gates/coverage.py", "tests/gates/test_coverage.py"],
    search_hints=SearchHints(symbols=["CoverageGate"], files=["harness_skills/gates/"]),
    next_steps=["Add CoverageGate to GateEvaluator.run_all()", "Update CHANGELOG"],
)
HandoffProtocol.write(doc)          # writes .harness/handoff/<task_id>.json
```

Receiving agent:

```python
doc = HandoffProtocol.read("feat-42")
print(doc.summary)
print(doc.next_steps)
```

Top-level helper scripts: `handoff.py` and `skills/write_handoff.py`.

---

## 2 · Task Lock

Cross-process mutual exclusion via an advisory lock file.  Use to protect shared
resources (e.g. state service writes, test-database resets).

```python
from harness_skills.task_lock import TaskLock

with TaskLock("migrate-db"):
    # only one agent/process can hold this lock at a time
    run_migrations()
```

`TaskLock` is re-exported from the top-level `task_lock.py` shim.
`coordinate.py` uses it internally for multi-agent task coordination.

---

## 3 · Shared State

A lightweight key/value store persisted to the state service.

```bash
# From .claude/commands/harness/shared-state.md skill
harness shared-state set  feat-42.phase "testing"
harness shared-state get  feat-42.phase
harness shared-state list feat-42.*
```

Or programmatically via the skills layer:

```python
from skills.shared_state import SharedState

state = SharedState(task_id="feat-42")
state.set("phase", "testing")
phase = state.get("phase")
```

---

## 4 · Stale-Plan Detection

Detects plans that have not advanced in too long, or whose tasks have become
inconsistent with HEAD.

```python
from harness_skills.stale_plan_detector import detect_stale_plan, PlanTask

report = detect_stale_plan(plan_id="feat-42", max_idle_minutes=60)
if report.is_stale:
    print(report.reason)   # e.g. "No progress in 90 min"
```

Skill: `/harness:detect-stale`.

---

## 5 · Resume

When an agent is interrupted mid-plan, `resume` loads the last saved state and returns
the next actionable step.

```python
from harness_skills.resume import load_plan_state, resume_agent_options

state = load_plan_state("feat-42")
options = resume_agent_options(state)
print(options.next_action)
```

Skill: `/harness:resume`.

---

## State Service API

```
PATCH  http://localhost:8888/features/{id}          # update task status
       body: {"status": "done"}

POST   http://localhost:8888/features/{id}/human-input   # request human input
       body: {"prompt": "Which approach do you prefer?", "options": ["A", "B"]}
```

---

## Boot & Sandbox Isolation

Before running in a sandboxed environment, call `boot_instance`:

```python
from harness_skills.boot import BootConfig, IsolationConfig, boot_instance

cfg = BootConfig(
    task_id="feat-42",
    isolation=IsolationConfig(network=False, filesystem="readonly"),
)
boot_instance(cfg)
```

Skill: `.claude/commands/harness/boot.md`.

---

## Deeper References

- **Handoff protocol spec** → `skills/context-handoff/` directory
- **Handoff examples** → `examples/handoff_example.py`
- **Full plan example** → `examples/plan_example.json`
- **Handoff skill doc** → `.claude/commands/harness/handoff.md` (15 KB)
- **Task-lock skill doc** → `.claude/commands/harness/task-lock.md` (13 KB)
- **Resume skill doc** → `.claude/commands/harness/resume.md` (11 KB)
- **Stale-plan skill doc** → `.claude/commands/harness/detect-stale.md` (11 KB)
- **Boot skill doc** → `.claude/commands/harness/boot.md` (14 KB)
- **Coordinate script** → `coordinate.py` (multi-agent dashboard)
- **Context handoff skill** → `.claude/commands/context-handoff.md`
- **Execution plans** → `.claude/commands/execution-plans.md`
- **Architecture** → [ARCHITECTURE.md](../../ARCHITECTURE.md)
