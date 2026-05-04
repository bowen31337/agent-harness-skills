# harness status

> Live dashboard of every active, completed, and blocked execution plan in one structured report.

`status` is the in-flight view of plans: where things stand right now. It reads from local plan files (under `docs/exec-plans/` by default) and/or the claw-forge state service, then aggregates them into a single dashboard. Use it during execution; use [`harness completion-report`](completion-report.md) after.

JSON / YAML output is shaped for dashboards and CI status checks; the table format is for terminal-driven standups.

## Synopsis

```bash
harness status [OPTIONS]
```

## Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--plan-file` | path (multiple) | — | Path(s) to YAML/JSON plan files. Repeat for several. |
| `--plan-id` | str (multiple) | — | Filter the dashboard to specific plan IDs. |
| `--state-url` | str | `http://localhost:8888` | State service URL. |
| `--no-state-service` | flag | — | Skip the state-service fetch; use only `--plan-file` inputs. |
| `--status-filter` | choice (`active` / `completed` / `blocked` / `pending` / `all`) | `all` | Show only plans / tasks in this status. |
| `--format` | choice (`json` / `yaml` / `table`) | TTY-aware | Output format. |

## Workflows

### Standup view (humans)

```bash
harness status --status-filter active --format table
```

### CI status check

```bash
harness status --format json | jq '.plans[] | select(.status=="blocked") | .id'
```

Surfaces any blocked plans for a PR-bot comment.

### Dashboard ingest (offline)

```bash
harness status --no-state-service \
  --plan-file docs/exec-plans/PLAN-001.yaml \
  --plan-file docs/exec-plans/PLAN-002.yaml \
  --format yaml > status-snapshot.yaml
```

### Just one plan

```bash
harness status --plan-id PLAN-RATE-LIMIT --format table
```

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Dashboard rendered. |
| `1` | No plan data found (no `--plan-file` and state service returned nothing). |
| `2` | Internal error — state-service unreachable while no `--no-state-service`, malformed plan file, etc. |

## See also

- [`harness plan`](plan.md) — produces the plan files this command consumes.
- [`harness completion-report`](completion-report.md) — post-execution counterpart.
- [`harness coordinate`](coordinate.md) — focused on conflicts; `status` covers everything.
