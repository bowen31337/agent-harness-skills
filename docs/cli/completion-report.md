# harness completion-report

> Aggregate plan-completion status into a structured report covering what was done, what was skipped (debt), and what still needs follow-up.

`completion-report` is the post-execution counterpart to [`harness plan`](plan.md). After an agent — or a sequence of agents — works through one or more execution plans, this command consolidates the outcome into a single `PlanCompletionReport` answering three questions:

1. **What was done?** Completed tasks, with timing data when timestamps are available.
2. **What technical debt was incurred?** Skipped tasks plus tasks whose notes contain TODO / FIXME / HACK markers, ranked by severity.
3. **What follow-up is needed?** Blocked, pending, and incomplete tasks the next session should pick up.

It can pull plan data from local YAML/JSON files, the claw-forge state service, or both — and output JSON / YAML / table for downstream pipelines.

## Synopsis

```bash
harness completion-report [OPTIONS]
```

## Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--plan-file` | path (multiple) | — | Path(s) to YAML or JSON plan files. Repeat the flag to include several. |
| `--plan-id` | str (multiple) | — | Filter the output to specific plan IDs. Without this, all plans found are reported. |
| `--state-url` | str | `http://localhost:8888` (env: `CLAW_FORGE_STATE_URL`) | Base URL of the state service. |
| `--no-state-service` | flag | — | Skip fetching from the state service and use only `--plan-file` inputs. |
| `--min-debt-severity` | choice (`critical` / `high` / `medium` / `low`) | `low` | Minimum severity for debt items to appear in the report. |
| `--output-format` | choice (`json` / `yaml` / `table`) | `table` | Output format. JSON / YAML round-trip cleanly through `PlanCompletionReport.model_validate_json`. |

## Workflows

### End-of-session report from local plan files

```bash
harness completion-report \
  --no-state-service \
  --plan-file docs/exec-plans/PLAN-001.yaml \
  --plan-file docs/exec-plans/PLAN-002.yaml \
  --output-format table
```

### CI-friendly JSON for downstream tooling

```bash
harness completion-report --output-format json > completion.json
# Parses cleanly into PlanCompletionReport:
python -c "import json; from harness_skills.models.completion import PlanCompletionReport; \
  print(PlanCompletionReport.model_validate_json(open('completion.json').read()))"
```

### Critical-debt-only summary

```bash
harness completion-report --min-debt-severity critical --output-format table
```

Surfaces only the highest-severity skipped tasks and `TODO/FIXME` markers — useful for triage triage emails or release-readiness reviews.

### Cross-agent rollup via state service

```bash
# Default: pulls all known plans from the state service
harness completion-report --output-format json
```

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Report rendered successfully. |
| `1` | No plan data found from any source. |
| `2` | Internal error — failed to parse a plan file, state service unreachable while no `--no-state-service`, etc. |

## See also

- [`harness plan`](plan.md) — produces the YAML/JSON plan files this command consumes.
- [`harness status`](status.md) — live, in-flight view of the same plans (this command is the post-mortem view).
- [`harness resume`](resume.md) — when the report flags follow-up work, `resume` reconstructs the next session's context.
