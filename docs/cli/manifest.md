# harness manifest

> Inspect and validate `harness_manifest.json` files.

`manifest` is a Click command group. Its primary subcommand is `validate`, which checks a manifest against `harness_manifest.schema.json` (the JSON Schema bundled with the package). The manifest itself is produced by [`harness create`](create.md) and refreshed by [`harness update`](update.md); validation is the integrity check before downstream tooling — agents, dashboards, CI gates — consumes it.

## Synopsis

```bash
harness manifest <subcommand> [OPTIONS] [ARGS]
```

## Subcommands

### harness manifest validate

Validate a manifest file against the bundled JSON Schema.

```bash
harness manifest validate [PATH] [--json]
```

#### Arguments

| Argument | Type | Default | Description |
|---|---|---|---|
| `PATH` | path | `harness_manifest.json` | Path to the manifest file to validate. |

#### Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--json` | flag | — | Emit a machine-readable JSON validation report instead of human text. |

#### Exit codes

| Code | Meaning |
|---|---|
| `0` | Manifest is valid. |
| `1` | Manifest exists but violates the schema (missing required keys, wrong types, etc.). |
| `2` | File not found, not readable, or not valid JSON. |

## Workflows

### CI validation step

```bash
harness manifest validate harness_manifest.json --json > validation.json
# exit 0 = ship; exit 1 = schema violations; exit 2 = file problems.
```

The JSON report has shape `{"valid": bool, "error_count": int, "errors": [...]}` — easy to integrate with PR comment bots.

### Local human-friendly check

```bash
harness manifest validate
# Without --json: prints a readable summary to stdout.
```

### Validate a manifest at a non-default path

```bash
harness manifest validate spec/test_fixtures/sample_manifest.json --json
```

## See also

- [`harness create`](create.md) — produces `harness_manifest.json` initially.
- [`harness update`](update.md) — refreshes `harness_manifest.json` after stack changes.
- The schema itself lives at `harness_skills/schemas/harness_manifest.schema.json` if you need to consult it directly.
