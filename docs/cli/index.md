# CLI Commands

The harness CLI provides 17 commands organized into categories.

## Install

```bash
pip install agent-harness-skills
harness --help
```

Requires Python 3.12+. The package registers a `harness` script via `pyproject.toml` (`harness = "harness_skills.cli.main:cli"`).

## Generation & Configuration
- `harness create` — Generate harness config and artifacts
- `harness update` — Re-scan and update artifacts (three-way merge)
- `harness manifest` — Generate / validate `harness_manifest.json`

## Quality Gates
- `harness lint` — Run architecture and principles checks
- `harness evaluate` — Run all quality gates
- `harness audit` — Check artifact freshness

## Execution Plans
- `harness plan` — Create execution plan from description
- `harness status` — Show plan and gate dashboard
- `harness resume` — Load plan state for context handoff
- `harness completion-report` — Aggregate plan-completion status into a report
- `harness context` — Provision agent context for the current task

## Observability
- `harness boot` — Launch isolated application instance
- `harness observe` — Tail structured logs
- `harness screenshot` — Capture visual artifacts

## Coordination
- `harness search` — Symbol and artifact lookup
- `harness coordinate` — Cross-agent conflict detection
- `harness telemetry` — Usage analytics

## Pipeline Composition

Commands can be chained with `--then`:

```bash
harness create --then lint --then evaluate
```

## Output Formats

Most commands accept `--format json|yaml|table`. JSON is the default when stdout is not a TTY (so CI captures structured output by default); table is the default in an interactive shell.
