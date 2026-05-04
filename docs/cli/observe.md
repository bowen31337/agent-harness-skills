# harness observe

> Real-time NDJSON log tail with domain, trace-id, and level filtering.

`observe` is the live tail for harness's structured logs. It reads the NDJSON log file (default `logs/harness.ndjson`), filters lines by domain prefix or exact trace-ID match, and streams them to stdout in either pretty or raw-JSON form. Filtering is dot-boundary aware: `--domain harness.auth` matches `harness.auth.session` but not `harness.authnz`.

It's the equivalent of `tail -f` over `jq`-filtered JSON — purpose-built for the log shape harness produces (see `harness_skills/logging_config.py` and the `PrettyConventionFormatter`).

## Synopsis

```bash
harness observe [OPTIONS]
```

## Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--log-file` | path | `logs/harness.ndjson` | NDJSON log file to tail. |
| `--domain` | str | — | Domain prefix filter (dot-boundary aware). |
| `--trace-id` | str | — | Exact W3C trace ID match (32 hex chars). |
| `--level` | choice (`DEBUG` / `INFO` / `WARN` / `ERROR` / `FATAL`) | — | Show only this level or above. |
| `--lines` | int | — | Show only the last N lines (then exit unless `--no-follow` is unset). |
| `--format` | choice (`pretty` / `json`) | `pretty` | Pretty for humans, JSON for piping into `jq` / file. |
| `--no-follow` | flag | — | Do not tail; print existing lines and exit. |
| `--timestamp` | flag | — | Include timestamps in pretty output. |

## Workflows

### Tail everything from a specific domain

```bash
harness observe --domain harness.auth --timestamp
```

Streams every log line whose `domain` field starts with `harness.auth.`.

### Follow a single trace across processes

```bash
harness observe --trace-id 4bf92f3577b34da6a3ce929d0e0e4736 --format json
```

Useful when correlating logs across multiple agent worktrees or services.

### Inspect a slice of past errors without tailing

```bash
harness observe --level ERROR --lines 200 --no-follow --format pretty
```

### Pipe into jq for ad-hoc analysis

```bash
harness observe --format json --no-follow | jq 'select(.level=="ERROR") | .message'
```

## Exit codes

`observe` exits `0` on a clean SIGINT / EOF. Errors during file-open or filter setup propagate as Click errors (exit `2`).

## See also

- [`harness telemetry`](telemetry.md) — derived metrics (artifact use, gate effectiveness) from the same log stream.
- `harness_skills/logging_config.py` — log-line schema and formatter the producer side uses.
