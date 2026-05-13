# Output Formats

Most `harness` subcommands accept `--format json|yaml|table`. This file
documents the parsing contract.

## Default selection

`--format` defaults to whichever value is most useful in the current shell:

| Context | Default |
|---|---|
| Interactive shell (stdout is a TTY) | `table` |
| Non-TTY (pipes, subprocess, CI) | `json` |

**Rule of thumb for agents**: pass `--format json` explicitly when capturing
output programmatically. Do not rely on TTY detection from inside a subagent
or a `subprocess.run(...)` call — the heuristics vary by runtime.

## Schemas

Where a JSON schema exists in the repo, it is the source of truth.

| Command | JSON schema |
|---|---|
| `evaluate` | `schemas/evaluation_report.schema.json` (`EvaluateResponse`) |
| `audit` | `schemas/audit_report.schema.json` |
| `manifest` | `harness_manifest.json` (self-describing) |
| `plan` | `schemas/exec_plan.schema.json` |
| `status` | derived from the plan schema + gate state |
| `search` | `schemas/symbol_record.schema.json` |
| `telemetry` | `schemas/telemetry_event.schema.json` |

If the schema file is absent, fall back to running the command with
`--format json` once and shaping a parser around the observed structure.

## Exit codes

The CLI uses a small, consistent set of exit codes:

| Code | Meaning |
|---|---|
| `0` | Success / gates passed / artifact in-spec |
| `1` | Domain-level failure (gate failed, plan incomplete, conflict detected) |
| `2` | Harness-internal error (bad flag, missing dependency, IO error) |
| `>2` | Reserved for stage-specific signals (see per-command docs) |

When chaining with `--then`, the pipeline aborts on **any** non-zero exit;
the returned code is the failing stage's code.

## Table output

The `table` format uses `rich` for rendering. It is intended for **humans**:

- Includes ANSI color codes when stdout is a TTY.
- Truncates long fields to fit terminal width.
- Sorts rows for readability, not parseability.

Never parse table output. Use `--format json` (or, where supported,
`--format yaml`).

## YAML output

Where supported (`evaluate`, `audit`, `plan`), YAML output is functionally
equivalent to JSON — the same schema, just rendered as YAML. Useful for
human review of large payloads; identical for tooling.
