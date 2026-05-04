# harness plan

> Create a new execution plan from a feature description.

`plan` writes a structured plan file (YAML or JSON) under `docs/exec-plans/` describing tasks, expected outcomes, and traceable IDs that the rest of the harness CLI references. Once written, the plan is the single source of truth for [`harness status`](status.md) (live progress), [`harness completion-report`](completion-report.md) (post-mortem), and [`harness context`](context.md) (file-discovery scoping).

A plan ID is auto-generated from a hash of the description if `--plan-id` is not supplied; the title defaults to the first 60 characters of the description.

## Synopsis

```bash
harness plan DESCRIPTION [OPTIONS]
```

## Arguments

| Argument | Type | Description |
|---|---|---|
| `DESCRIPTION` | str (positional) | Free-form description of what the plan covers. Quote it for shells with spaces. |

## Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--plan-id` | str | auto-generated | Custom plan ID. Must be unique within `--output-dir`. |
| `--title` | str | first 60 chars of `DESCRIPTION` | Human-readable plan title. |
| `--output-dir` | path | `docs/exec-plans` | Directory to write the plan file into. |
| `--output-format` | choice (`json` / `yaml`) | `yaml` | Plan-file serialization. Both formats are accepted by every consuming command. |

## Workflows

### Quick start

```bash
harness plan "Implement OIDC trusted publishing for PyPI release"
# Writes docs/exec-plans/PLAN-<hash>.yaml
```

### Reproducible plan ID

```bash
harness plan "Migrate logging to NDJSON" --plan-id PLAN-LOGS-001 --title "NDJSON migration"
```

### JSON-formatted plan for tooling

```bash
harness plan "..." --output-format json --output-dir spec/plans/
```

### Pipeline: plan → context → status

```bash
harness plan "Add rate limiting to /api/v1/users" --plan-id PLAN-RATE-LIMIT
harness context PLAN-RATE-LIMIT --depth-map
# … work happens …
harness status --plan-id PLAN-RATE-LIMIT
harness completion-report --plan-id PLAN-RATE-LIMIT
```

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Plan created. |
| `1` | Plan with the same ID already exists in `--output-dir`. (Won't overwrite by default.) |
| `2` | Internal error — invalid output dir, serialization error, etc. |

## See also

- [`harness status`](status.md) — live view of plans this command produces.
- [`harness completion-report`](completion-report.md) — post-execution rollup.
- [`harness context`](context.md) — file-discovery scoped to a plan ID.
