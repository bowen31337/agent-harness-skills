# harness audit

> Score harness artifacts against current codebase state and flag stale or obsolete ones.

`audit` walks the well-known harness artifacts (`AGENTS.md`, `ARCHITECTURE.md`, `harness.config.yaml`, generated docs, principles file) and compares each artifact's last-modified time against tracked source files. Artifacts that haven't been refreshed since significant code changes are surfaced so you know what to regenerate before relying on them.

The intended workflow is: run `audit` in CI to fail PRs whose source-of-truth artifacts have drifted past the tolerated staleness window, and run it locally before invoking `harness create` / `harness update` to know what's worth regenerating.

## Synopsis

```bash
harness audit [OPTIONS]
```

## Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--project-root` | path | `.` | Root of the project to audit. |
| `--stale-days` | int | `30` | Age (in days) at which an artifact is considered stale. |
| `--outdated-days` | int | `90` | Age at which an artifact is considered outdated. |
| `--outdated-days` is the threshold the `--fail-on-outdated` flag uses. |
| `--obsolete-days` | int | `180` | Age at which an artifact is considered obsolete. |
| `--fail-on-outdated` / `--no-fail-on-outdated` | flag | `True` | Exit `1` when outdated or obsolete artifacts are present. Disable for advisory-only runs. |
| `--output-format` | choice (`json` / `yaml` / `table`) | TTY-aware | Output format. JSON and YAML emit a structured `AuditResponse` suitable for CI consumption. |

## Workflows

### CI gate — fail on outdated artifacts

```bash
harness audit --output-format json > audit-report.json
# exit 1 means at least one artifact is outdated or obsolete
```

### Pre-regeneration sweep

```bash
# Lower the staleness threshold to catch even mildly aged artifacts
harness audit --stale-days 7 --no-fail-on-outdated --output-format table
# Then refresh whatever it flagged:
harness update --project-root .
```

### Custom thresholds for slow-moving repos

```bash
harness audit --stale-days 60 --outdated-days 180 --obsolete-days 365
```

## Exit codes

| Code | Meaning |
|---|---|
| `0` | All artifacts current or merely stale (acceptable). |
| `1` | At least one artifact is outdated or obsolete (only with `--fail-on-outdated`). |
| `2` | Internal error — invalid path, unreadable artifact, etc. |

## See also

- [`harness update`](update.md) — regenerate the artifacts `audit` flags.
- [`harness create`](create.md) — initial generation of the artifacts `audit` tracks.
- The `docs_freshness` gate inside [`harness evaluate`](evaluate.md) integrates the same staleness signals into broader gate runs.
