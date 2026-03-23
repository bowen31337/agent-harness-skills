<!-- harness:auto-generated — do not edit this block manually -->
last_updated: 2026-03-23
head: 2c470a0
artifact: docs-index
<!-- /harness:auto-generated -->

# Documentation Index

> Central navigation hub for all generated and specification documents.
> Re-run `/agents-md` any time a new document is added or relationships change.

---

## Agent Reference

| Document | Purpose |
|---|---|
| [AGENTS.md](AGENTS.md) | Browser automation quick-start, screenshot helpers, e2e test runner |
| [CLAUDE.md](CLAUDE.md) | Project stack, build/test commands, claw-forge agent notes |

---

## Architecture & Design

| Document | Purpose |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Domain map, dependency graph, module boundary violations |
| [docs/design-docs/README.md](docs/design-docs/README.md) | Architectural Decision Records (ADR) directory |
| [docs/design-docs/adr/0001-adopt-playwright-for-browser-testing.md](docs/design-docs/adr/0001-adopt-playwright-for-browser-testing.md) | ADR-0001: Playwright for browser testing |

---

## Principles & Rules

| Document | Purpose |
|---|---|
| [PRINCIPLES.md](PRINCIPLES.md) | Mechanical rules for AI agents — task lifecycle, git, safety, skills |
| [ERROR_HANDLING_RULES.md](ERROR_HANDLING_RULES.md) | Structured error model, GateResult patterns, severity levels |

---

## Specifications

| Document | Purpose |
|---|---|
| [SPEC.md](SPEC.md) | Logging convention — five required fields, JSON Schema, adoption guide |
| [HEALTH_CHECK_SPEC.md](HEALTH_CHECK_SPEC.md) | Health check endpoint contract — response format, polling protocol |
| [docs/health-check-endpoint-spec.md](docs/health-check-endpoint-spec.md) | Extended health check spec with ADR context |

---

## Process & Conventions

| Document | Purpose |
|---|---|
| [docs/plan-to-pr-convention.md](docs/plan-to-pr-convention.md) | Plan-to-PR traceability: branch naming, PR title, commit trailers |
| [docs/harness-changelog.md](docs/harness-changelog.md) | Harness changelog — version history |

---

## Execution & Progress

| Document | Purpose |
|---|---|
| [EVALUATION.md](EVALUATION.md) | Latest gate evaluation report — coverage, lint, regression |
| [docs/exec-plans/progress.md](docs/exec-plans/progress.md) | Live execution plan progress log |
| [docs/exec-plans/debt.md](docs/exec-plans/debt.md) | Technical debt backlog |
| [docs/exec-plans/perf.md](docs/exec-plans/perf.md) | Performance improvement plan |

---

## Skill Commands (`.claude/commands/`)

### Core

| Skill | Purpose |
|---|---|
| [`/agents-md`](.claude/commands/agents-md.md) | Cross-link all generated docs (this index was created by this skill) |
| [`/check-code`](.claude/commands/check-code.md) | Run linters, type checker, tests, and enforce principles |
| [`/review-pr`](.claude/commands/review-pr.md) | Review a PR against principles and module boundaries |
| [`/checkpoint`](.claude/commands/checkpoint.md) | Git commit + state snapshot before risky operations |
| [`/module-boundaries`](.claude/commands/module-boundaries.md) | Scan packages, enforce `__all__`, write MB* principles |
| [`/define-principles`](.claude/commands/define-principles.md) | Generate or refresh PRINCIPLES.md |

### Browser & Observability

| Skill | Purpose |
|---|---|
| [`/browser-automation`](.claude/commands/browser-automation.md) | Set up Playwright browser automation |
| [`/harness:screenshot`](.claude/commands/harness/screenshot.md) | Capture browser screenshots |
| [`/harness:observe`](.claude/commands/harness/observe.md) | Tail and filter structured logs |
| [`/dom-snapshot`](.claude/commands/dom-snapshot.md) | Extract DOM snapshot for inspection |

### Planning & Execution

| Skill | Purpose |
|---|---|
| [`/execution-plans`](.claude/commands/execution-plans.md) | Create and manage execution plans |
| [`/harness:context`](.claude/commands/harness/context.md) | Build minimal context manifest for a plan or domain |
| [`/harness:evaluate`](.claude/commands/harness/evaluate.md) | Run all evaluation gates; regenerate EVALUATION.md |
| [`/harness:status`](.claude/commands/harness/status.md) | Show current harness status |
| [`/coordinate`](.claude/commands/coordinate.md) | Cross-agent task conflict dashboard |
| [`/context-handoff`](.claude/commands/context-handoff.md) | Write or resume a session handoff |
| [`/harness:resume`](.claude/commands/harness/resume.md) | Resume from a previous agent session |

### Specifications & Standards

| Skill | Purpose |
|---|---|
| [`/logging-convention`](.claude/commands/logging-convention.md) | Generate SPEC.md (logging convention) |
| [`/log-format-linter`](.claude/commands/log-format-linter.md) | Lint structured log files against SPEC.md |
| [`/health-check-endpoint`](.claude/commands/health-check-endpoint.md) | Generate HEALTH_CHECK_SPEC.md |
| [`/create-spec`](.claude/commands/create-spec.md) | Create a project specification (XML) |
| [`/detect-api-style`](.claude/commands/detect-api-style.md) | Detect REST / GraphQL / gRPC API style |

### Quality Gates

| Skill | Purpose |
|---|---|
| [`/harness:coverage-gate`](.claude/commands/harness/coverage-gate.md) | Evaluate test coverage gate |
| [`/harness:lint`](.claude/commands/harness/lint.md) | Run harness lint checks |
| [`/type-safety-gate`](.claude/commands/type-safety-gate.md) | Enforce type annotation completeness |
| [`/harness:security-check-gate`](.claude/commands/harness/security-check-gate.md) | Run security checks |
| [`/harness:principles-gate`](.claude/commands/harness/principles-gate.md) | Verify principles compliance |
| [`/doc-freshness-gate`](.claude/commands/doc-freshness-gate.md) | Check documentation freshness |
| [`/harness:docs-freshness`](.claude/commands/harness/docs-freshness.md) | Harness docs freshness gate |

### Infrastructure & Lifecycle

| Skill | Purpose |
|---|---|
| [`/harness:boot`](.claude/commands/harness/boot.md) | Boot agent instance in isolated worktree |
| [`/harness:create`](.claude/commands/harness/create.md) | Create a new harness task |
| [`/harness:update`](.claude/commands/harness/update.md) | Update harness task state |
| [`/harness:handoff`](.claude/commands/harness/handoff.md) | Structured handoff between agent sessions |
| [`/harness:task-lock`](.claude/commands/harness/task-lock.md) | Acquire or release a task lock |
| [`/harness:shared-state`](.claude/commands/harness/shared-state.md) | Read / write shared agent state |
| [`/harness:telemetry`](.claude/commands/harness/telemetry.md) | Emit and query harness telemetry |
| [`/harness:performance`](.claude/commands/harness/performance.md) | Run performance benchmarks |
| [`/harness:completion-report`](.claude/commands/harness/completion-report.md) | Generate task completion report |
| [`/harness:effectiveness`](.claude/commands/harness/effectiveness.md) | Effectiveness dashboard |
| [`/harness:detect-stale`](.claude/commands/harness/detect-stale.md) | Detect stale execution plans |
| [`/harness:error-aggregation`](.claude/commands/harness/error-aggregation.md) | Aggregate and query error logs |
| [`/harness-init`](.claude/commands/harness-init.md) | Initialise a new harness project |
| [`/harness-changelog`](.claude/commands/harness-changelog.md) | Update the harness changelog |
| [`/progress-log`](.claude/commands/progress-log.md) | Append to the execution progress log |
| [`/observability`](.claude/commands/observability.md) | Observability stack setup |
| [`/harness:observability`](.claude/commands/harness/observability.md) | Harness observability configuration |
| [`/ci-pipeline`](.claude/commands/ci-pipeline.md) | CI pipeline integration |
| [`/expand-project`](.claude/commands/expand-project.md) | Expand project scaffolding |
| [`/pool-status`](.claude/commands/pool-status.md) | Agent pool status |
| [`/claw-forge-status`](.claude/commands/claw-forge-status.md) | claw-forge orchestrator status |
| [`/create-bug-report`](.claude/commands/create-bug-report.md) | Create structured bug report |

---

*Generated by [`/agents-md`](.claude/commands/agents-md.md) on 2026-03-23. Re-run to refresh after adding new documents or skills.*
