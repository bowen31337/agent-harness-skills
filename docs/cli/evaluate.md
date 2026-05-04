# harness evaluate

> Run every configured quality gate in sequence and emit a structured pass/fail report.

`evaluate` is the omnibus gate runner. It reads `harness.config.yaml`, executes every enabled gate (coverage, architecture, security, principles, lint, types, performance, docs-freshness, and any custom gates), and produces a single `EvaluateResponse` describing what passed, what failed, and — for failures — concrete `GateFailure` objects with severity, file paths, and suggested remediation.

CI consumes the exit code; humans consume the table format. JSON / YAML output is shaped for `jq`, dashboards, and downstream tooling that needs structured failure data.

## Synopsis

```bash
harness evaluate [OPTIONS]
```

## Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--gate` | str (multiple) | all enabled | Run only the named gate(s). Can be repeated (`--gate coverage --gate types`). Unknown IDs are rejected. |
| `--project-root` | path | `.` | Repository root. All gates resolve paths relative to this. |
| `--coverage-threshold` | float | `90.0` | Minimum line-coverage percent for the coverage gate. Overrides `harness.config.yaml`. |
| `--max-staleness-days` | int | `30` | Max artifact age (in days) before the docs-freshness gate flags them. |
| `--format` | choice (`json` / `yaml` / `table`) | TTY-aware | Output format. JSON conforms to `evaluation_report.schema.json`. |

## Workflows

### Full evaluation in CI

```bash
harness evaluate --format json > evaluation.json
# Exit 0 = ship; exit 1 = at least one gate failed; exit 2 = harness itself errored.
```

### Run only the gates that matter for this PR

```bash
harness evaluate --gate coverage --gate principles --format table
```

### Filter failures by severity

```bash
harness evaluate --format json | jq '.failures[] | select(.severity=="error")'
```

### Tighten the coverage bar for a specific repo

```bash
harness evaluate --coverage-threshold 95 --gate coverage
```

### Pipeline-chain after generating fresh artifacts

```bash
harness create --then evaluate
```

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Every gate passed. |
| `1` | At least one gate reported an error-severity failure. |
| `2` | Internal error — invalid `harness.config.yaml`, unknown `--gate` ID, gate runner crashed, etc. |

## See also

- [`harness lint`](lint.md) — fast subset (`architecture`, `principles`, `lint` only) for tight feedback loops.
- [`harness create`](create.md) — produces the `harness.config.yaml` `evaluate` consumes.
- [`harness audit`](audit.md) — staleness signals that feed the docs-freshness gate.
- [`harness coordinate`](coordinate.md) — when `evaluate` runs in a multi-agent context, `coordinate` first to avoid two agents racing the same gate.
