# harness lint

> Run architectural and golden-principle checks in a single pass, without test/coverage/security overhead.

`lint` is the fast feedback loop subset of [`harness evaluate`](evaluate.md). It executes only the gates whose runtime is sub-second on most repos: `architecture` (layer & module-boundary violations), `principles` (golden-principles compliance), and `lint` (ruff / mypy on changed files). No test execution, no coverage measurement, no security scan — those live in the full `evaluate` run.

The intended use case is local or pre-commit feedback: `lint` should be a one-second answer to "is my edit going to fail CI on the cheap stuff?".

## Synopsis

```bash
harness lint [OPTIONS]
```

## Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--gate` | choice (`architecture` / `principles` / `lint`, multiple) | all three | Run only the named gate(s). Repeat the flag for multiple. |
| `--no-principles` | flag | — | Convenience: equivalent to `--gate architecture --gate lint`. |
| `--project-root` | path | `.` | Repository root. |
| `--format` | choice (`json` / `table`) | TTY-aware | Output format. JSON shape matches `evaluate`'s `EvaluateResponse` (subset). |

## Workflows

### Pre-commit hook

```bash
# .git/hooks/pre-commit
harness lint --format json > /dev/null || {
  echo "harness lint failed — run 'harness lint --format table' for details"
  exit 1
}
```

### Just check architecture & ruff on a focused PR

```bash
harness lint --no-principles --format table
```

### Single-gate run for debugging

```bash
harness lint --gate principles --format json | jq '.failures'
```

### Pipeline before a full evaluate

```bash
harness create --then lint --then evaluate
```

The `lint` step gives you a fast fail signal before the slower `evaluate` runs.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | All selected gates passed. |
| `1` | At least one error-severity violation. |
| `2` | Internal error — bad `--gate` ID, missing config, etc. |

## See also

- [`harness evaluate`](evaluate.md) — full gate set, including the slow ones.
- `.claude/principles.yaml` — the source-of-truth file the `principles` gate reads.
