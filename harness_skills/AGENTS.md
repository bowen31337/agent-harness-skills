# AGENTS.md — harness_skills (top-level utilities)

## Purpose

The root `harness_skills` package houses the cross-cutting utility modules that do not belong to any single sub-package. These include the agent lifecycle (boot, handoff, resume), cross-process coordination (task locking, shared state), observability helpers (logging, telemetry, error aggregation), and browser/DOM utilities. All sub-packages (`models`, `gates`, `generators`, `plugins`, `cli`) depend on these top-level modules, never the reverse.

---

## Key Files

| File | Key Types / Functions | Description |
|------|----------------------|-------------|
| `boot.py` | `BootConfig`, `IsolationConfig`, `BootResult` | Per-worktree app instance launcher with sandbox isolation and health-check wait |
| `handoff.py` | `HandoffDocument`, `SearchHints`, `HandoffProtocol`, `HandoffTracker` | Multi-session context handoff — writes `.claude/plan-progress.md` and `.plan_progress.jsonl` |
| `resume.py` | `load_plan_state`, `resume_agent_options` | Reads saved plan state and presents resume options to an incoming agent |
| `task_lock.py` | `TaskLock`, `TaskLockProtocol`, `LockConflictError`, `LockNotOwnedError` | Cross-process task locking via file locks; protocol interface for testing |
| `logging_config.py` | `configure`, `get_logger`, `set_trace_id` | Structured logging provider; produces NDJSON with required 5-field schema |
| `stale_plan_detector.py` | `detect_stale_plan`, `PlanTask` | Detects tasks that were started but never completed across sessions |
| `telemetry_reporter.py` | CLI `telemetry` command | Aggregates and reports harness telemetry data |
| `error_aggregation.py` | `aggregate_errors`, `load_errors_from_log` | Groups recent log errors by domain and trend; JSON-serialisable views |
| `error_query_agent.py` | `build_error_tools`, `run_error_query` | LLM-powered error analysis using Claude tool-use |
| `dom_snapshot_skill.py` | Façade over `dom_snapshot_utility` | Browser-free DOM inspection façade; delegates to `dom_snapshot_utility` package |
| `performance_hooks.py` | `PerformanceTracker` | Timer and memory hooks; appends to `docs/exec-plans/perf.md` |
| `pr_effectiveness.py` | `ArtifactType`, `PRRecord` | PR effectiveness metric models |
| `effectiveness_stats.py` | Aggregation utilities | Aggregates effectiveness scores across PRs |

---

## Internal Patterns

- **Structured logging** — all modules call `get_logger(__name__)` from `logging_config`; never use `print()` or `logging.getLogger()` directly.
- **`set_trace_id`** — set at the top of each agent session to propagate a W3C-compatible trace ID through all log entries.
- **Handoff as append-only** — `HandoffTracker` always appends to `.plan_progress.jsonl`; never overwrites; the last entry wins on resume.
- **Task lock lifecycle** — always acquire via `TaskLock` context manager; `LockConflictError` means another agent owns the task; back off and retry or skip.
- **Boot isolation** — `BootConfig.isolation` controls DB and network sandbox; set `IsolationConfig.db_url` for test-environment separation.
- **DOM snapshot façade** — `dom_snapshot_skill.py` is the only entry-point for DOM inspection from agent tasks; do not import `dom_snapshot_utility` directly in skill scripts.

---

## Domain-Specific Constraints

- **Top-level modules must not import from sub-packages** — `harness_skills.boot`, `handoff`, etc. may not import from `harness_skills.gates`, `cli`, `generators`, or `plugins`.
- **Only `models` as shared types** — when a top-level module needs a response type, it must come from `harness_skills.models`.
- **`error_query_agent.py` requires Anthropic SDK** — `run_error_query` makes live LLM calls; never call it in unit tests without mocking.
- **`performance_hooks.py` writes to `docs/exec-plans/perf-timers.json`** — file must be treated as a cross-process shared resource; always use `fcntl.LOCK_EX` before writing.
- **Principle MB002** — top-level utility modules are shared infrastructure; changes here affect the entire framework; review with extra care.
