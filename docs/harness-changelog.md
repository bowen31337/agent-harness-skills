# Harness Changelog

Tracks every harness update run — skills added or modified, config tweaks, doc edits.
Each entry is anchored to a git commit hash so you can `git checkout <hash>` to inspect
the exact state at that point in time.

---

## 2026-03-23 — `0e893bd` — feat/architecture-do-skill-generates-an-artifact-changelog-d

> Run at 07:48:24  ·  Diffed from `0bae125`

### Skills  (18 total)
- ✅ `detect-api-style.md` — Added
- ✅ `module-boundaries.md` — Added
- 📝 `define-principles.md` — Modified
- 📝 `harness/create.md` — Modified
- 📝 `harness/detect-stale.md` — Modified
- 📝 `harness/evaluate.md` — Modified
- 📝 `harness/update.md` — Modified

### Config
- 📝 `harness-init.sh` — Modified
- 📝 `harness.config.yaml` — Modified

### Docs
- 📝 `docs/agent_tool_desig_guidelines.md` — Modified
- 📝 `docs/harness-changelog.md` — Modified
- ✅ `docs/design-docs/README.md` — Added
- ✅ `docs/design-docs/adr/0001-adopt-playwright-for-browser-testing.md` — Added
- ✅ `docs/design-docs/drafts/.gitkeep` — Added
- ✅ `docs/design-docs/template.md` — Added

### Spec
- No spec changes

### Commits
- `0e893bd` — Skill registers as /harness:plan for creating a new execution plan from a description or ticket reference
- `7446a2f` — Skill registers as /harness:status for showing current state of all plans, gates, and harness health metrics
- `e0f047c` — Skill generates a harness.config.yaml with config profiles (starter, standard, advanced) providing progressive complexity; starter profile enables only essential gates and documentation, standard adds architecture enforcement, advanced unlocks all features including telemetry and multi-agent coordination
- `22f4812` — Skill supports command composition where harness create, harness lint, and harness evaluate can be chained in a single invocation (e.g., harness create --then lint --then evaluate), reducing the number of separate tool invocations agents must reason about
- `593a28d` — Skill generates a harness init shell script for teams not using Claude Code providing the same functionality via standalone CLI
- `9c7e5db` — Apply stashed changes from harness update skill branch

---


## 2026-03-20 — `0bae125` — feat/architecture-do-skill-generates-an-artifact-changelog-d

> Run at 15:04:18  ·  Diffed from `af3945f`

### Skills  (16 total)
- ✅ `harness-init.md` — Added
- ✅ `harness/context.md` — Added
- ✅ `harness/coverage-gate.md` — Added
- ✅ `harness/create.md` — Added
- ✅ `harness/detect-stale.md` — Added
- ✅ `harness/effectiveness.md` — Added
- ✅ `harness/evaluate.md` — Added
- ✅ `harness/performance.md` — Added
- ✅ `harness/resume.md` — Added
- ✅ `harness/screenshot.md` — Added
- ✅ `harness/status.md` — Added
- ✅ `harness/telemetry.md` — Added
- ✅ `harness/update.md` — Added
- ✅ `progress-log.md` — Added

### Config
- 📝 `CLAUDE.md` — Modified
- 📝 `claw-forge.yaml` — Modified

### Docs
- 📝 `docs/exec-plans/debt.md` — Modified
- ✅ `docs/exec-plans/perf-timers.json` — Added
- ✅ `docs/exec-plans/perf.md` — Added
- ✅ `docs/exec-plans/plan-template.yaml` — Added
- ✅ `docs/exec-plans/progress.md` — Added
- 📝 `docs/exec-plans/shared-state.yaml` — Modified
- 📝 `docs/harness-changelog.md` — Modified
- 📝 `docs/harness-telemetry.json` — Modified
- ✅ `docs/health-check-endpoint-spec.md` — Added
- ✅ `docs/plan-to-pr-convention.md` — Added

### Spec
- 📝 `app_spec.txt` — Modified

### Commits
- `0bae125` — Skill generates a prefer-shared-utilities-over-hand-rolled-helpers rule with pointers to existing utility packages in the codebase
- `6e5d546` — Skill generates boundary-level validation rules specifying that data validation happens at system boundaries (API input, external services) not deep in business logic
- `d7b64b1` — Skill generates concurrency and async patterns rule based on detected framework conventions
- `463ebe9` — Skill generates error handling pattern rules specifying structured errors, error codes, and logging format conventions
- `393f78e` — Skill generates naming convention rules for functions, variables, files, and database columns derived from existing codebase style analysis
- `af7a52b` — Skill generates import ordering and grouping rules matching existing conventions detected from the most common patterns
- `5b67710` — Skill generates a no-magic-numbers and no-hardcoded-strings rule with config pattern guidance and constant extraction conventions
- `eb88a13` — Skill generates test writing principles covering arrange-act-assert structure, test naming conventions, fixture patterns, and mock boundary rules
- `ff12233` — Skill generates an EVALUATION.md defining all completion criteria agents must satisfy before opening a PR
- `651cbbb` — Skill generates a coverage gate with configurable threshold (default 90%) that blocks PRs falling below the bar
- `431fb75` — Skill generates a security check gate covering secret scanning, dependency vulnerability audit, and input validation verification
- `bb4c9d3` — Skill generates an architectural compliance gate that runs the structural test suite from the architecture enforcement component
- `6e3ad10` — Skill generates a golden principles compliance gate that runs the principle violation scanner and fails on critical violations
- `6e701f0` — Skill generates a type safety gate that runs the type checker (TypeScript strict, mypy, etc.) with zero errors required
- `e143cf2` — Skill generates a harness evaluate command that runs all gates in sequence and produces a structured JSON pass/fail report
- `3d96792` — Skill generates CI pipeline integration as GitHub Actions workflow and GitLab CI job that runs harness evaluate on every PR
- `5a260e5` — Skill generates a gate failure report as structured JSON (severity, gate_id, file_path, line_number, suggestion fields)
- `90d4b2e` — Skill generates structured logging configuration matching the detected framework
- `b12a96c` — Skill generates environment isolation configuration with separate ports, database schemas, or containers per worktree
- `cef32da` — Skill generates performance measurement hooks so agents can query response times, memory usage, and startup duration
- `b0f446e` — Skill generates performance measurement hooks so agents can query response times, memory usage, and startup duration
- `60b8ef8` — Skill generates context handoff protocol where ending agent sessions write a structured summary to the plan progress log
- `1b7fb48` — Skill generates an error aggregation view so agents can query recent errors grouped by domain and frequency
- `48e0810` — Skill generates an error aggregation view so agents can query recent errors grouped by domain and frequency
- `7d77cb3` — Skill generates telemetry hooks that track which harness artifacts agents actually read and which gate failures are most common
- `fd47305` — Skill generates a harness plan command that creates a new execution plan from a feature description or ticket
- `e08124c` — Skill generates execution plan template with sections: objective, approach, steps, context assembly, progress log, known debt, completion criteria
- `5996285` — checkpoint: 2026-03-20 12:43:55
- `819a374` — Skill registers as /harness:resume for loading most recent plan state and presenting it for context handoff
- `b9a4287` — Add harness:resume skill for loading plan state at session start
- `75fa4e2` — Skill generates a plan-to-PR linking convention where each PR references its source execution plan for full traceability
- `328516b` — Skill generates a harness resume command that loads the most recent plan state and presents it as agent context
- `0920cf3` — Skill registers as /harness:create for full harness generation from codebase analysis through all artifact output
- `449ed61` — Skill generates a technical debt tracker where agents log known shortcuts or TODOs into docs/exec-plans/debt.md
- `3c3cc3a` — Skill generates a plan completion report summarizing what was done, what debt was incurred, and what follow-up is needed
- `04ecf15` — Skill generates a harness context command that returns a minimal set of file paths and search patterns given a plan ID or domain name
- `6a34cb0` — Skill generates a harness coordinate command that shows cross-agent task status and identifies conflicts
- `f0a201c` — Skill registers as /harness:evaluate for running all evaluation gates and producing a structured pass/fail report
- `3b4cbef` — Skill registers as /harness:plan for creating a new execution plan from a description or ticket reference
- `fb52704` — Skill generates a harness.config.yaml with config profiles (starter, standard, advanced)
- `a610246` — Skill generates a harness boot command that starts the isolated app instance and waits for health check to pass
- `00c78f7` — Skill generates a harness observe command that tails structured logs filtered by domain or trace_id in real time
- `6442fa6` — Skill generates browser automation integration config (Playwright or Puppeteer) so agents can drive the UI and capture screenshots
- `435b9e7` — Skill generates performance measurement hooks so agents can query response times, memory usage, and startup duration
- `4e8b5fe` — Skill generates an error aggregation view so agents can query recent errors grouped by domain and frequency
- `03bd6eb` — Skill generates a harness screenshot command that captures the current application state as a visual artifact for PR evidence
- `0877719` — Skill generates telemetry hooks that track which harness artifacts agents actually read
- `471f380` — Skill generates a harness telemetry command that reports artifact utilization rates, command call frequency, and gate effectiveness scores
- `06a91d3` — Skill generates a harness plan command that creates a new execution plan from a feature description or ticket
- `a79850f` — Skill generates a harness resume command that loads the most recent plan state and presents it as agent context
- `563c7f8` — Skill generates a plan completion report summarizing what was done, what debt was incurred, and what follow-up is needed
- `160b518` — Skill generates a plan-to-PR linking convention where each PR references its source execution plan for full traceability
- `817eb11` — Execution plan templates include a context assembly section with grep patterns, file globs, and symbol references
- `e5ad1b1` — Execution plans support task dependencies via a depends_on field; harness status displays a dependency graph
- `37536e8` — Skill registers as /harness:create for full harness generation from codebase analysis through all artifact output
- `50dab09` — Skill registers as /harness:evaluate for running all evaluation gates and producing a structured pass/fail report
- `c7f58a2` — Skill registers as /harness:plan for creating a new execution plan from a description or ticket reference
- `c0dec24` — Skill registers as /harness:status for showing current state of all plans, gates, and harness health metrics
- `e5b8de2` — Skill registers as /harness:screenshot for capturing application state as a visual artifact
- `4b04e50` — CLI commands support --verbosity levels (quiet, normal, verbose, debug) controlling output detail
- `8e612d9` — Skill registers as /harness:screenshot for capturing application state as a visual artifact
- `d0c63e4` — Skill supports custom evaluation gates allowing engineers to define project-specific gates via a plugin interface in harness.config.yaml
- `2daf81a` — Skill generates log format linter rules ensuring all log statements follow the structured pattern
- `1474120` — Skill generates environment isolation configuration with separate ports, database schemas, or containers per worktree
- `29a60ed` — Skill generates a health check endpoint specification that agents can poll to verify the application is running correctly
- `1b86def` — Skill generates browser automation integration config (Playwright or Puppeteer)
- `ab87162` — Skill generates performance measurement hooks so agents can query response times, memory usage, and startup duration
- `6443b0b` — Skill generates an effectiveness scoring system that correlates harness artifact usage with PR quality metrics
- `1f26b49` — Skill generates a harness screenshot command that captures the current application state as a visual artifact for PR evidence
- `1262263` — Skill generates observability stack templates (optional) for lightweight log aggregation in local dev using file-based collectors
- `12db90e` — Skill generates telemetry hooks that track which harness artifacts agents actually read
- `28ffa17` — Skill generates docs/exec-plans/ directory structure with templates for execution plan artifacts
- `ad7311f` — Skill generates progress log format where agents append timestamped entries as they complete steps within a plan
- `304e000` — Skill generates a harness plan command that creates a new execution plan from a feature description or ticket
- `d15e69a` — Skill generates a plan status dashboard command (harness status) showing all active, completed, and blocked plans
- `f87bea3` — Skill generates git-based checkpoint integration where agents commit work-in-progress to a branch with plan reference in the commit message
- `8bff389` — Skill generates a harness resume command that loads the most recent plan state and presents it as agent context
- `455a9c3` — Skill generates a technical debt tracker where agents log known shortcuts or TODOs into docs/exec-plans/debt.md

---

## 2026-03-14 — `af3945f` — feat/coding-5378ef56

> Run at 19:16:22  ·  Diffed from `280d7a4`

### Skills  (16 total)

- ✅ `harness/context.md` — Added  *(plan-ID / domain → minimal file-path + search-pattern manifest for agent-driven context assembly)*
- ✅ `harness/lint.md` — Added  *(architectural + principles lint gate via harness evaluate)*

### Config

- No config changes

### Docs

- ✅ `docs/exec-plans/shared-state.yaml` — Added  *(shared multi-agent coordination state)*
- ✅ `docs/harness-init.sh` — Added  *(standalone CLI init script for non-Claude Code teams)*

### Spec

- No spec changes

### Commits

- `af3945f` — Skill generates a plan-to-PR linking convention where each PR references its source execution plan for full traceability
- `ea93a22` — Execution plan templates include a context assembly section with grep patterns, file globs, and symbol references that agents can use to independently rebuild task context using search tools
- `1989f55` — Skill generates a task lock protocol where agents acquire a lock on a plan task before starting work, preventing concurrent modification by multiple agents; locks include agent_id, timestamp, and auto-expire after a configurable timeout
- `73e2a02` — Execution plans support task dependencies via a depends_on field, and harness status displays a dependency graph showing which tasks are blocked, ready, or in-progress
- `09cbbc1` — Skill generates a harness coordinate command that shows cross-agent task status, identifies conflicts (two agents modifying the same files), and suggests task reordering to minimize merge conflicts
- `44d20f1` — Skill registers as /harness:create for full harness generation from codebase analysis through all artifact output
- `90f0888` — Skill registers as /harness:evaluate for running all evaluation gates and producing a structured pass/fail report

---

## 2026-03-14 — `280d7a4` — feat/coding-886b39ee

> Run at 19:08:09  ·  Diffed from `d4656f1`

### Skills  (14 total)

- No skill changes

### Config

- No config changes

### Docs

- ✅ `docs/harness-init.sh` — Added  *(standalone CLI init script for non-Claude Code teams)*

### Spec

- No spec changes

### Commits

- `280d7a4` — Skill registers as /harness:screenshot for capturing application state as a visual artifact

---

## 2026-03-14 — `d4656f1` — feat/coding-e4908d0c

> Run at 19:07:53  ·  Diffed from `74b33e7`

### Skills  (14 total)

- ✅ `harness-changelog.md` — Added

### Config

- 📝 `harness.config.yaml` — Modified  *(profiles: starter → standard → advanced)*

### Docs

- 📝 `docs/exec-plans/debt.md` — Modified
- 📝 `docs/harness-changelog.md` — Modified

### Spec

- No spec changes

### Commits

- `d4656f1` — All CLI commands support a --output-format flag (json, yaml, table) defaulting to table for humans and json when stdout is not a TTY, enabling structured consumption by agents and scripts
- `4481f54` — CLI commands support --verbosity levels (quiet, normal, verbose, debug) controlling output detail; quiet mode emits only machine-parseable results, verbose mode includes rationale and context
- `2e471bf` — coding(coding-e5f71cd2): completed

---
## 2026-03-13 — `74b33e7` — main

> Run at 21:54:10  ·  Diffed from `e17a209`

### Skills  (14 total)

- ✅ `browser-automation.md` — Added
- 📝 `check-code.md` — Modified
- ✅ `ci-pipeline.md` — Added
- ✅ `coordinate.md` — Added
- ✅ `define-principles.md` — Added
- ✅ `dom-snapshot.md` — Added
- 📝 `review-pr.md` — Modified

### Config

- No config changes

### Docs

- ✅ `docs/exec-plans/debt.md` — Added
- ✅ `docs/harness-telemetry.json` — Added

### Spec

- No spec changes

### Commits

- `74b33e7` — coding(coding-8152f30d): completed
- `f2166a2` — merge: feat/coding-9cfd80f8 (squash)
- `9622b72` — coding(coding-5ab9926e): completed
- `0afde84` — coding(coding-23fd392f): completed
- `77acf9e` — coding(coding-1a1f9009): completed
- `449d858` — merge: feat/coding-c65f2e99 (squash)
- `89fee67` — coding(coding-52516970): completed
- `f002a5c` — coding(coding-d22991cc): completed
- `6829b66` — coding(coding-6ccfb721): completed
- `61d2534` — coding(coding-5610a2fc): completed
- `16980f4` — coding(coding-3a066bd7): completed
- `97c0372` — coding(coding-c14bb315): completed
- `70b21a8` — coding(coding-077b5fbf): completed
- `02db1c0` — coding(coding-fb563322): completed
- `bad8e80` — merge: feat/coding-ce33a8f9 (squash)
- `f86e2ee` — merge: feat/coding-be04bd18 (squash)
- `e0acf14` — coding(coding-a2f043c1): completed
- `446699b` — merge: feat/coding-7f0a2b30 (squash)
- `1326732` — merge: feat/coding-7fc5a724 (squash)
- `29753b0` — merge: feat/coding-922f93bc (squash)
- `a080e15` — coding(coding-fa6a1082): completed
- `5cc0459` — merge: feat/coding-8d971ef5 (squash)
- `858f3a6` — merge: feat/coding-83b9902a (squash)
- `7cd286f` — merge: feat/coding-a56066c6 (squash)
- `f2ed7a9` — merge: feat/coding-60d05f55 (squash)
- `d6df71c` — merge: feat/coding-b9c0f255 (squash)
- `e52365e` — merge: feat/coding-849cdebf (squash)
- `545bd76` — merge: feat/coding-53e43e39 (squash)
- `e0c2287` — merge: feat/coding-cf1423f6 (squash)
- `ed3a84e` — merge: feat/coding-e113552a (squash)

---

## 2026-03-13 — `e17a209` — feat/coding-bae7b81c

> Run at 00:00:00  ·  Diffed from `4781a17`

### Skills  (9 total)

- ✅ `check-code.md` — Added
- ✅ `checkpoint.md` — Added
- ✅ `claw-forge-status.md` — Added
- ✅ `create-bug-report.md` — Added
- ✅ `create-spec.md` — Added
- ✅ `expand-project.md` — Added
- ✅ `harness-changelog.md` — Added
- ✅ `pool-status.md` — Added
- ✅ `review-pr.md` — Added

### Config

- No config changes

### Docs

- ✅ `docs/agent_tool_desig_guidelines.md` — Added
- ✅ `docs/harness-changelog.md` — Added

### Spec

- 📝 `app_spec.txt` — Modified

### Commits

- `e17a209` — update spec
- `4781a17` — Initial commit: agent tool design guidelines and claw-forge harness config

---

