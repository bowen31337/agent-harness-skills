# harness update

> Re-scan the codebase and refresh harness artifacts via three-way merge, preserving manual edits.

`update` is the maintenance counterpart to [`harness create`](create.md). Where `create` is the bootstrap, `update` is the refresh: it re-runs the codebase analyzer, regenerates each managed artifact (`AGENTS.md`, `ARCHITECTURE.md`, `harness_manifest.json`, generated docs, etc.), and reconciles the new content with what's on disk using a three-way merge.

The merge respects two kinds of manual content: anything inside `<!-- CUSTOM -->` blocks, and (by default) any non-trivial divergence from the previously-generated baseline. Pass `--force` to overwrite divergent content while still preserving `CUSTOM` blocks.

Every successful run appends a `ChangelogEntry` to `docs/harness-changelog.md` so the trail of regenerations is human-auditable.

## Synopsis

```bash
harness update [OPTIONS]
```

## Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--project-root` | path | `.` | Root of the project to re-scan. |
| `--force` | flag | — | Overwrite manual edits outside `<!-- CUSTOM -->` blocks. Use after large stack changes. |
| `--no-changelog` | flag | — | Skip appending to `docs/harness-changelog.md`. |
| `--output-format` | choice (`json` / `yaml` / `table`) | TTY-aware | Output format for the run report (`UpdateResponse` with per-artifact `ArtifactDiff` entries). |

## Workflows

### Routine refresh after merging a feature branch

```bash
harness update --output-format table
```

Three-way merge keeps your hand-tuned sections; the rest is regenerated.

### Clean overwrite after a major stack migration

```bash
harness update --force --output-format json > update-report.json
```

`--force` blows away non-baseline manual edits *outside* `CUSTOM` blocks. Review the diff in `update-report.json` before committing.

### Audit-only run (don't write changelog)

```bash
harness update --no-changelog --output-format json | jq '.diffs[] | select(.changed)'
```

Useful when running `update` from CI just to detect drift, with the actual regeneration commit happening elsewhere.

### Pre-update sanity check

```bash
harness audit --no-fail-on-outdated   # see what's stale first
harness update                        # then refresh
harness manifest validate             # confirm the new manifest is schema-clean
```

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Artifacts updated successfully (one or more changed). |
| `1` | No changes detected — every artifact already matches the regenerated content. |
| `2` | Internal error — analyzer crashed, regeneration failed, unwritable file, etc. |

## See also

- [`harness create`](create.md) — initial bootstrap; `update` is the refresh path.
- [`harness audit`](audit.md) — run before `update` to know what's stale.
- [`harness manifest`](manifest.md) — run `manifest validate` after `update` to confirm schema cleanliness.
- `docs/harness-changelog.md` — the human-readable trail of every `update` run.
