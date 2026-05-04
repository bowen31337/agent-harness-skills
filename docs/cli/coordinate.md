# harness coordinate

> Detect cross-agent task conflicts and suggest a non-conflicting execution order.

When multiple agents work in parallel against the same repo or shared services, two failure modes are common: (1) two agents holding incompatible task locks, and (2) two agents picking up the same task from different plans. `coordinate` reads the lock files and live state and reports both classes of conflict in a single dashboard, plus a suggested reordering that minimizes contention.

It can also operate in `--demo` mode against built-in fixtures, so you can experiment with the report shape without a running state service or any real locks.

## Synopsis

```bash
harness coordinate [OPTIONS]
```

## Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--state-url` | str | `http://localhost:8420` | State service URL (note: `coordinate` uses port `8420`, not the default `8888` other commands use). |
| `--demo` | flag | — | Use built-in demo data instead of querying the state service. Useful for dry-runs and screenshots. |
| `--no-locks` | flag | — | Skip lock-file display (state-service conflicts only). |
| `--locks-dir` | path | `.harness/locks` | Directory containing per-task lock files. |
| `--output-format` | choice (`json` / `yaml` / `table`) | TTY-aware | Output format. |

## Workflows

### Daily standup view

```bash
harness coordinate --output-format table
```

Renders a human-readable table of agents, their current locks, and any conflicts.

### Pre-flight check before kicking off a parallel batch

```bash
harness coordinate --output-format json | jq '.conflicts'
```

If `.conflicts` is non-empty, hold the batch until the colliding agents finish.

### Demo mode for tutorials / dashboards

```bash
harness coordinate --demo --output-format json
```

Returns a synthetic but realistic conflict scenario; safe to embed in docs.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Report generated successfully. |
| `1` | No agents or tasks found from any source. |
| `2` | Internal error — state service unreachable (without `--demo`), corrupt lock file, etc. |

## See also

- [`harness boot`](boot.md) — `coordinate` complements `boot`'s per-worktree isolation by surfacing conflicts that isolation alone can't prevent (e.g., two agents claiming the same task).
- [`harness status`](status.md) — broader plan-status view; `coordinate` is the conflict-focused subset.
