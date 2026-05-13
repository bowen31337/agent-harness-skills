# Pipeline Composition (`--then`)

The `harness` CLI is a `click` group with a custom `PipelineGroup` that
splits the argument list at `--then` boundaries and runs each segment as
an independent invocation.

## Semantics

- Segments execute **in order**, top to bottom.
- A non-zero exit code from any segment **aborts** the remainder.
- The exit code returned is that of the **last executed** stage.
- A trailing bare `--then` (no following token) is silently dropped, so
  programmatic builders can append/strip safely.
- Per-stage flags work exactly as they would in standalone invocations.

## Common chains

### Bootstrap → gate
```bash
harness create --then evaluate
```
Generate the config and immediately run all gates.

### Bootstrap → targeted gate
```bash
harness create --profile standard --then lint --gate architecture
```
Only the architecture gate runs after generation.

### Refresh → audit → re-gate
```bash
harness update --then audit --then evaluate
```
Pick up filesystem drift, flag stale artifacts, then prove the gates are green.

### Plan → context → status
```bash
harness plan "Add OIDC publishing" --plan-id PLAN-OIDC --then context PLAN-OIDC --depth-map --then status --plan-id PLAN-OIDC
```
Author a plan, provision context, then check the dashboard — single invocation.

### Boot → observe (for parallel debugging)
```bash
harness boot --port 8889 --then observe --tail
```
(Foreground `observe` runs only if `boot` returned 0.)

## Pitfalls

- **Don't chain commands that read from a previous command's stdout.** Each
  stage is a separate Click invocation; stdout is not piped between them.
  Use shell pipes or temp files for that.
- **Don't pass `--then` as a value to a subcommand flag.** It is consumed by
  the top-level argument splitter before the subcommand sees it. If you
  need a literal `--then` value, escape via shell quoting and pass through
  an env var instead.
- **Be deliberate about side effects in early stages.** A `create` that
  fails mid-write can leave a partial `harness.config.yaml`. Inspect or
  use `--dry-run` first when iterating.

## Programmatic builders

If a wrapper script is building chains, the safe approach is to flatten a
list of segments with `--then` between them. Empty segments collapse, so:

```python
segments = [
    ["create", "--profile", profile],
    [] if not run_lint else ["lint", "--gate", gate_name],
    ["evaluate", "--format", "json"],
]
args = []
for seg in segments:
    if not seg:
        continue
    if args:
        args.append("--then")
    args.extend(seg)
```

This produces a valid invocation regardless of which optional stages are
included.
