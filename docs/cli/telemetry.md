# harness telemetry

> Report artifact utilization, command frequency, and gate effectiveness from collected hook telemetry.

`telemetry` reads `docs/harness-telemetry.json` (an append-only file the harness's `PostToolUse` / `Stop` hooks write during agent sessions) and derives three actionable views:

1. **Artifact utilization** — which generated artifacts agents actually read, and which are cold (good signal for what to deprecate).
2. **Command frequency** — which `harness` sub-commands and slash-commands get invoked, and how often.
3. **Gate effectiveness** — which gates flagged failures vs. which were silent (silent gates are a tuning candidate).

The output drives team retros, gate-config tuning, and decisions about what generated content is worth maintaining.

## Synopsis

```bash
harness telemetry [OPTIONS]
```

## Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--telemetry-file` | path | `docs/harness-telemetry.json` | Telemetry input file. Gitignored — local-only by design. |
| `--format` | choice (`table` / `json`) | `table` | Output format. |
| `--min-reads` | int | `0` | Hide artifacts with fewer than N reads. Useful for cutting noise on long-tail files. |
| `--top-n` | int | — | Cap the artifact list at the top N most-used. |

## Workflows

### Quick "what's not pulling its weight?" check

```bash
harness telemetry --min-reads 5 --format table
```

Anything not appearing here has been read fewer than 5 times across all collected sessions — likely candidates for deletion or de-emphasis in `AGENTS.md`.

### Top-10 most-used artifacts

```bash
harness telemetry --top-n 10 --format json | jq '.artifacts[]'
```

### CI / dashboard ingest

```bash
harness telemetry --format json > telemetry-snapshot.json
# Feed into a Grafana / Looker dashboard
```

### Find silent gates

```bash
harness telemetry --format json | jq '.gates[] | select(.failure_count == 0)'
```

A gate that never fails after months of runs may be either perfectly tuned or vestigial — worth a review.

## Exit codes

`telemetry` exits `0` on success. It exits `1` if cold/unused artifacts or silent gates are detected (advisory non-zero — useful in CI to nudge regular review). `2` for internal errors (file unreadable, malformed JSON).

## See also

- [`harness observe`](observe.md) — raw log stream; `telemetry` is the derived-metric view.
- The `harness_skills/telemetry_reporter.py` module exposes `build_report` / `render_report` for embedding the same logic in custom tools.
