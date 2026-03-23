# AGENTS.md — skills/

## Purpose

Agent-callable skill modules. Each subdirectory is a self-contained skill that an agent can invoke via CLI or programmatic Python API to perform a specific task (progress tracking, handoff, DOM inspection, screenshot capture, error aggregation, etc.). Skills are the primary extension point for agent workflows.

---

## Key Files

| Skill Directory | `SKILL.md` | CLI Script | Purpose |
|----------------|-----------|-----------|---------|
| `boot/` | `SKILL.md` | — | Per-worktree app launcher with health checks and DB isolation |
| `progress-log/` | `SKILL.md` | — | Append-only execution plan tracking (Markdown table in `docs/exec-plans/progress.md`) |
| `context-handoff/` | `SKILL.md` | `scripts/read_handoff.py` | Multi-session handoff with search hints; writes `.claude/plan-progress.md` |
| `harness-resume/` | `SKILL.md` | `scripts/resume.py` | Load and present saved plan state for incoming agents |
| `debt-tracker/` | `SKILL.md` | — | Log shortcuts / compromises into `docs/exec-plans/debt.md` with severity levels |
| `error-aggregation/` | `SKILL.md` | `scripts/query_errors.py` | Group recent log errors by domain and trend; JSON output |
| `dom-snapshot/` | `SKILL.md` | `scripts/snapshot_dom.py` | Browser-free page structure inspection via BeautifulSoup |
| `perf-hooks/` | `SKILL.md` | — | Timer and memory hooks; appends to `docs/exec-plans/perf.md` |
| `shared-state/` | `SKILL.md` | — | Publish intermediate results to `docs/exec-plans/shared-state.yaml` for inter-agent communication |
| `screenshot/` | `SKILL.md` | `scripts/capture_screenshot.py` | Capture visual page state via Playwright / Pillow / terminal backends |
| `logging-convention/` | `SKILL.md` | `scripts/generate_spec.py` | Generate versioned `SPEC.md` / JSON Schema for structured logging |

---

## Internal Patterns

- **One skill per directory** — each skill is entirely self-contained; no skill may import another skill.
- **`SKILL.md` is required** — every skill directory must contain a `SKILL.md` describing its name, purpose, workflow, CLI usage, and programmatic API.
- **Dual interface** — skills expose both a CLI (`python skills/<skill>/scripts/<cmd>.py`) and a programmatic Python API for use in agent code.
- **Append-only shared files** — skills that write to `docs/exec-plans/` use `O_APPEND` semantics or `fcntl.LOCK_EX`; never truncate or overwrite these files.
- **Artifact paths are conventional** — `progress.md`, `debt.md`, `perf.md`, `shared-state.yaml` are fixed paths; do not parameterise them unless the `SKILL.md` explicitly documents the override.
- **No inter-skill dependencies** — if two skills share logic, extract it into `harness_skills` top-level utilities, not into a shared skill module.

---

## Domain-Specific Constraints

- **Skills are agent-facing, not library code** — they are designed to be invoked by an agent in a task session, not imported by framework code.
- **`shared-state.yaml` is ephemeral** — it lives only for the duration of a multi-agent session; never treat it as persistent storage.
- **Screenshot artifacts must not be committed** — `screenshots/` and `videos/` are gitignored; never stage files from these directories.
- **`dom-snapshot` skill calls `dom_snapshot_utility`** — it must go through the `dom_snapshot_skill.py` façade in `harness_skills`, not import `dom_snapshot_utility` directly, to maintain the boundary.
- **`context-handoff` is write-once per session** — call `HandoffTracker.write()` once at agent teardown; multiple calls per session create confusing duplicate entries.
- **Principle SK001** — new skills must include a `SKILL.md` and at least one runnable CLI script before being considered complete.
