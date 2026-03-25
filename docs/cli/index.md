# CLI Commands

The harness CLI provides 17 commands organized into categories:

## Generation & Configuration
- `harness create` — Generate harness config and artifacts
- `harness update` — Re-scan and update artifacts (three-way merge)

## Quality Gates
- `harness lint` — Run architecture and principles checks
- `harness evaluate` — Run all quality gates
- `harness audit` — Check artifact freshness

## Execution Plans
- `harness plan` — Create execution plan from description
- `harness status` — Show plan and gate dashboard
- `harness resume` — Load plan state for context handoff

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
