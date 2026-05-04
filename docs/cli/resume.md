# harness resume

> Load the most recent plan-progress state into a context block ready to feed a new agent session.

When an agent session is interrupted (context window limit, manual stop, runaway), the harness writes plan-progress to two files: `.claude/plan-progress.md` (human-readable) and `.plan_progress.jsonl` (append-only audit log). `resume` reads from those files and reconstructs the minimum context the next session needs to pick up cleanly: where the previous session left off, what was committed, what's still in flight, and search hints to re-locate the relevant code.

It's the bookend to [`harness context`](context.md): `context` scopes a *new* session by plan; `resume` scopes a *continuing* session by recent progress.

## Synopsis

```bash
harness resume [OPTIONS]
```

## Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--md-path` | path | `.claude/plan-progress.md` | Markdown plan-progress file. Authoritative when both sources exist and `--prefer md`. |
| `--jsonl-path` | path | `.plan_progress.jsonl` | JSONL audit-log file. Authoritative when `--prefer jsonl`. |
| `--prefer` | choice (`md` / `jsonl`) | `md` | Source preference when both files exist. |
| `--hints` | flag | — | Print only the search hints (paths, symbols, keywords) — skip the full context block. |
| `--output-format` | choice (`json` / `human`) | `human` | Output format. `json` is suitable for piping into the next session's prompt assembler. |

## Workflows

### Drop the previous session's context into the next

```bash
harness resume --output-format json | jq '.context_block' > resume.txt
# Feed resume.txt to the new session
```

### Just the hints — let the agent read the rest

```bash
harness resume --hints
```

Prints a short list of recently-touched files and search keywords; the new agent uses [`harness search`](search.md) / Read to fetch full context on demand.

### Force-prefer the structured audit log

```bash
harness resume --prefer jsonl --output-format json
```

Useful when `.claude/plan-progress.md` may have been hand-edited and you want the canonical machine record.

### Combined with `context` for a fresh-but-resuming session

```bash
harness context PLAN-42 --format json > context.json
harness resume --output-format json > resume.json
# Combine in the new session prompt
```

## Exit codes

| Code | Meaning |
|---|---|
| `0` | State found and presented. |
| `1` | No plan-progress state found in either source. |
| `2` | Internal error — file unreadable, parse failure, etc. |

## See also

- [`harness context`](context.md) — scope a session by plan, not by progress.
- [`harness completion-report`](completion-report.md) — post-mortem rollup once work is actually finished.
