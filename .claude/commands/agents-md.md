---
name: agents-md
description: "Cross-link all generated documentation so agents can navigate between related files via relative paths. Discovers every auto-generated and specification document in the repository, builds a relationship map, appends or refreshes machine-delimited cross-link sections, and regenerates DOCS_INDEX.md as a central navigation hub. Use when: (1) a new generated doc has been added, (2) relationships between docs have changed, (3) DOCS_INDEX.md is stale or missing, (4) onboarding a new agent that needs to discover all documentation, (5) after running /module-boundaries, /define-principles, /logging-convention, /health-check-endpoint, or /harness:evaluate. Triggers on: cross-link docs, update doc index, refresh documentation links, agents-md, docs navigation, generated documentation index."
---

# Agents MD — Documentation Cross-Linker

Discover every generated and specification document, build a relationship graph,
and stitch relative-path navigation links into each file so agents can jump between
related documents without a full codebase search.

---

## What this skill manages

| Artefact | Location | Managed by |
|---|---|---|
| `DOCS_INDEX.md` | repo root | Created / refreshed on every run |
| `<!-- harness:cross-links -->` blocks | inside each generated doc | Appended or replaced on every run |

The cross-link block is delimited so it can be safely replaced on re-runs without
touching hand-written content above it.

---

## Instructions

### Step 1 — Discover generated documents

Collect every document that is either:

**a) Stamped with the `harness:auto-generated` comment:**
```bash
grep -rl "harness:auto-generated" . \
  --include="*.md" \
  --exclude-dir=".git" \
  --exclude-dir="node_modules"
```

**b) Listed in the static manifest** (always include these regardless of markers):

| File | Generator skill |
|---|---|
| `AGENTS.md` | `/browser-automation` |
| `ARCHITECTURE.md` | `/module-boundaries` |
| `PRINCIPLES.md` | `/define-principles` |
| `EVALUATION.md` | `/harness:evaluate` |
| `SPEC.md` | `/logging-convention` |
| `ERROR_HANDLING_RULES.md` | auto-generated for the stack |
| `HEALTH_CHECK_SPEC.md` | `/health-check-endpoint` |
| `docs/plan-to-pr-convention.md` | `/execution-plans` |
| `docs/health-check-endpoint-spec.md` | `/health-check-endpoint` |
| `docs/harness-changelog.md` | `/harness-changelog` |
| `docs/exec-plans/progress.md` | `/progress-log` |
| `docs/design-docs/README.md` | `/create-spec` |

Combine both lists; deduplicate. Store as **DOCS** (list of repo-relative paths).

---

### Step 2 — Build the relationship map

For each document in DOCS, apply the rules below to produce a list of
`(source, target, relationship_label)` triples.

#### Hard-coded relationship rules

```
AGENTS.md
  → ARCHITECTURE.md          "project structure and package map"
  → PRINCIPLES.md            "agent behaviour rules"
  → SPEC.md                  "logging convention"
  → .claude/commands/browser-automation.md   "browser automation skill"
  → .claude/commands/harness/screenshot.md   "screenshot helper skill"
  → .claude/commands/harness/observe.md      "log observation skill"
  → DOCS_INDEX.md            "full documentation index"

ARCHITECTURE.md
  → PRINCIPLES.md            "module boundary rules §11 (MB001–MB014)"
  → ERROR_HANDLING_RULES.md  "error patterns used in these packages"
  → AGENTS.md                "agent-facing quick-start"
  → .claude/commands/module-boundaries.md  "skill that regenerates this file"
  → .claude/commands/check-code.md         "enforces MB* rules on staged files"
  → .claude/commands/review-pr.md          "enforces MB* rules in PR diffs"
  → DOCS_INDEX.md            "full documentation index"

PRINCIPLES.md
  → ARCHITECTURE.md                         "module boundary detail (§11)"
  → docs/plan-to-pr-convention.md           "plan-to-PR traceability (§10)"
  → ERROR_HANDLING_RULES.md                 "code quality and error handling"
  → .claude/commands/define-principles.md   "skill that regenerates this file"
  → .claude/commands/check-code.md          "enforces all principles"
  → .claude/commands/review-pr.md           "enforces all principles in PRs"
  → DOCS_INDEX.md                           "full documentation index"

SPEC.md  (Logging Convention)
  → ERROR_HANDLING_RULES.md              "logging format conventions (§6)"
  → HEALTH_CHECK_SPEC.md                 "related observability specification"
  → PRINCIPLES.md                        "logging provider rule MB011"
  → .claude/commands/logging-convention.md  "skill that regenerated this file"
  → .claude/commands/log-format-linter.md   "CI linter that validates against this spec"
  → DOCS_INDEX.md                        "full documentation index"

ERROR_HANDLING_RULES.md
  → ARCHITECTURE.md          "package structure these rules apply to"
  → PRINCIPLES.md            "code quality and tool usage rules"
  → SPEC.md                  "structured logging spec (§6)"
  → EVALUATION.md            "latest gate run results"
  → DOCS_INDEX.md            "full documentation index"

HEALTH_CHECK_SPEC.md
  → SPEC.md                  "logging convention (observability peer)"
  → AGENTS.md                "agents poll the health endpoint"
  → docs/health-check-endpoint-spec.md            "extended spec with ADR context"
  → .claude/commands/health-check-endpoint.md     "skill that generated this file"
  → .claude/commands/harness/observe.md           "log observation for health events"
  → DOCS_INDEX.md            "full documentation index"

EVALUATION.md
  → PRINCIPLES.md            "principles gate — rules being evaluated"
  → ARCHITECTURE.md          "architecture gate — boundaries being checked"
  → ERROR_HANDLING_RULES.md  "error patterns checked in the lint gate"
  → .claude/commands/harness/evaluate.md  "skill that regenerated this file"
  → .claude/commands/harness/coverage-gate.md     "coverage gate detail"
  → DOCS_INDEX.md            "full documentation index"

docs/plan-to-pr-convention.md
  → ../PRINCIPLES.md                            "rules §10 that formalise this convention"
  → exec-plans/progress.md                      "live plan progress log"
  → ../.claude/commands/execution-plans.md      "skill that manages execution plans"
  → ../.claude/commands/review-pr.md            "enforces plan-to-PR traceability"
  → ../DOCS_INDEX.md                            "full documentation index"

docs/health-check-endpoint-spec.md
  → ../HEALTH_CHECK_SPEC.md                     "canonical root-level spec"
  → ../.claude/commands/health-check-endpoint.md "generating skill"
  → ../DOCS_INDEX.md                            "full documentation index"

docs/harness-changelog.md
  → ../EVALUATION.md                            "current evaluation state"
  → ../.claude/commands/harness-changelog.md    "skill that manages this changelog"
  → ../DOCS_INDEX.md                            "full documentation index"

docs/exec-plans/progress.md
  → ../plan-to-pr-convention.md                 "PR linking convention"
  → ../../.claude/commands/progress-log.md      "skill that manages this log"
  → ../../DOCS_INDEX.md                         "full documentation index"
```

#### Dynamic relationship discovery (supplement hard-coded rules)

For each document in DOCS, scan for references to other docs in DOCS using:

```bash
grep -oE '\[([^\]]+)\]\(([^)]+\.md)\)' <file>
```

Any `target.md` resolved relative to `<file>` that exists in DOCS gets an
additional edge with label `"referenced inline"` — unless the edge already
exists from the hard-coded rules.

---

### Step 3 — Write cross-link blocks into each document

For each file in DOCS:

1. **Read the file.**
2. **Check for an existing cross-link block:**
   ```
   <!-- harness:cross-links — do not edit this block manually -->
   ...
   <!-- /harness:cross-links -->
   ```
3. **Build the replacement block** from the outgoing edges for this file:

```markdown
<!-- harness:cross-links — do not edit this block manually -->

---

## Related Documents

| Document | Relationship |
|---|---|
| [PRINCIPLES.md](PRINCIPLES.md) | agent behaviour rules |
| [ARCHITECTURE.md](ARCHITECTURE.md) | project structure and package map |
| [DOCS_INDEX.md](DOCS_INDEX.md) | full documentation index |

<!-- /harness:cross-links -->
```

4. **Apply the block:**
   - If the file already contains a `<!-- harness:cross-links -->` block: replace it in-place using the Edit tool (old_string = full existing block, new_string = new block).
   - If no block exists: append the block at the end of the file using the Edit tool (append after the last non-blank line).
5. **Preserve the auto-generated header** at the top of the file — do not touch it.

---

### Step 4 — Generate DOCS_INDEX.md

Write (or overwrite) `DOCS_INDEX.md` at the repository root:

```markdown
<!-- harness:auto-generated — do not edit this block manually -->
last_updated: <YYYY-MM-DD>
head: <git rev-parse --short HEAD>
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
| [`/agents-md`](.claude/commands/agents-md.md) | Cross-link all generated docs (this skill) |
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
| [`/module-boundaries`](.claude/commands/module-boundaries.md) | Module boundary enforcement |
| [`/claw-forge-status`](.claude/commands/claw-forge-status.md) | claw-forge orchestrator status |
| [`/create-bug-report`](.claude/commands/create-bug-report.md) | Create structured bug report |

---

*Generated by `/agents-md`. Re-run to refresh after adding new documents or skills.*
```

Use `git rev-parse --short HEAD 2>/dev/null || echo "unknown"` to get the HEAD SHA.
Use today's date for `last_updated`.

---

### Step 5 — Report

Print a summary:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  /agents-md — Documentation Cross-Linker
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Documents discovered: <N>
  Cross-link blocks written/updated: <N>
  Relationship edges added: <N>
  DOCS_INDEX.md: refreshed

  Navigation hub: DOCS_INDEX.md
  Re-run any time: /agents-md

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Flags

| Flag | Behaviour |
|---|---|
| `--dry-run` | Print what would be changed without writing any files |
| `--file <path>` | Update cross-links for a single file only |
| `--no-index` | Skip regenerating DOCS_INDEX.md |
| `--index-only` | Regenerate DOCS_INDEX.md only; skip per-file cross-link updates |

---

## Notes

- **Idempotent** — safe to re-run any time. Existing blocks are replaced, not duplicated.
- **Read-only check** — the skill reads every file before editing it (satisfies PRINCIPLES.md §3.1).
- **Relative paths only** — all links use paths relative to the file being edited so they work in any clone location.
- **Does not commit** — stage and commit with `/checkpoint` after reviewing the diff.
- **Trigger events** — re-run after: `/module-boundaries`, `/define-principles`, `/logging-convention`, `/health-check-endpoint`, `/harness:evaluate`, or any time a new `*.md` file is added to the root or `docs/` directory.
