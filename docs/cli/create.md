# harness create

> Initialise (or update the gates section of) a project's `harness.config.yaml`, pre-populated with profile-appropriate defaults.

`create` is the entry point for adopting harness-skills in a new project. It writes a `harness.config.yaml` chosen from one of three complexity profiles (`starter` / `standard` / `advanced`), each pre-configured with sensible gate thresholds. If a config already exists, `create` performs a *merge* by default — only the `gates:` block is rewritten, and the rest of the YAML (custom keys, comments) is preserved.

The same command also produces stack-specific scaffolding (CI workflow snippets, `docs/generated/` directory layout) and inline comments calibrated to the project's primary language.

## Synopsis

```bash
harness create [OPTIONS]
```

## Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--profile` | choice (`starter` / `standard` / `advanced`) | `starter` | Complexity profile. `starter` enables the minimum viable gate set; `advanced` enables every gate and the stricter thresholds. |
| `--stack` | choice (`python` / `node` / `go`) | auto-detect | Hint for inline-comment language. Affects only the comments, not the schema. |
| `--output` | path | `harness.config.yaml` | Destination path for the generated YAML. |
| `--dry-run` | flag | — | Print the YAML to stdout without writing to disk. |
| `--no-merge` | flag | — | Overwrite the existing config from scratch, discarding manual edits to the `gates:` block. |
| `--format` | choice (`text` / `json`) | `text` | Output of the *report* about what was written (not the YAML itself, which is always YAML). |

## Workflows

### First-time setup in a new repo

```bash
harness create --profile standard
# Inspect harness.config.yaml, commit when satisfied
```

### Preview before writing

```bash
harness create --profile advanced --dry-run | less
```

### Refresh gate defaults without disturbing custom keys

```bash
harness create --profile standard
# Existing gates: block is replaced; rest of harness.config.yaml is untouched.
```

### Force a clean slate

```bash
harness create --profile starter --no-merge
# Wipes the existing harness.config.yaml entirely. Use with care.
```

### Pipeline-chain into lint and evaluate

```bash
harness create --then lint --then evaluate
```

`--then` is supported by all gate-bearing commands; chains in a single process so the next command sees the just-written config.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Config written (or printed in `--dry-run` / `--format json` mode). |
| `1` | Internal error — invalid profile, unwritable destination, etc. |

## See also

- [`harness update`](update.md) — once `create` has bootstrapped, `update` is the regenerate path that uses three-way merge and tracks changes in `docs/harness-changelog.md`.
- [`harness lint`](lint.md), [`harness evaluate`](evaluate.md) — both consume `harness.config.yaml`.
- [`harness manifest`](manifest.md) — `create` also produces a `harness_manifest.json`; `manifest validate` checks it against schema.
