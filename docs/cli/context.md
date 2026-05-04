# harness context

> Produce a ranked file list and targeted search patterns covering a plan's scope — without loading file contents into the context window.

`context` solves the "what do I need to read?" problem at the start of an agent session. Given a plan ID or a domain keyword, it returns a `ContextManifest`: a curated list of file paths plus search patterns that future Read / Grep calls can use, scoped to a token budget. The agent only consumes the manifest's metadata; full file contents are pulled lazily when actually needed.

Discovery uses three complementary strategies layered together:
- **State-service lookup** — for known plan IDs, fetch the plan's declared scope.
- **Git log** — recent commits touching files matching the domain.
- **Grep** — keyword scan across the working tree.

The resulting list is ranked and capped by `--max-files`, optionally annotated with L0/L1/L2 depth tiers (most-relevant → background).

## Synopsis

```bash
harness context PLAN_ID_OR_DOMAIN [OPTIONS]
```

## Arguments

| Argument | Type | Description |
|---|---|---|
| `PLAN_ID_OR_DOMAIN` | str | Either a plan ID known to the state service or one or more domain keywords (space-separated). |

## Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--max-files` | int | `20` | Cap the returned file list. |
| `--budget` | int | — | Advisory token budget. Affects depth-tier assignment when `--depth-map` is set. |
| `--format` | choice (`json` / `human`) | `human` | Output format. `json` emits a `ContextManifest` for programmatic consumption. |
| `--state-url` | str | `http://localhost:8888` (env: `CLAW_FORGE_STATE_URL`) | State service URL. |
| `--no-git` | flag | — | Skip the git-log discovery strategy (useful in shallow clones or non-git trees). |
| `--include` | str (glob) | — | Restrict candidates to files matching this glob pattern. |
| `--exclude` | str (glob) | — | Extra exclusion pattern, applied on top of repo-wide ignores. |
| `--depth-map` | flag | — | Annotate each file with an L0 / L1 / L2 tier (most → least relevant). |

## Workflows

### Scope an agent before it starts work on a plan

```bash
harness context PLAN-42 --format json --depth-map > context.json
```

The agent reads `context.json`, opens L0 files first, defers L2 reads until needed.

### Domain-keyword exploration

```bash
harness context "auth session jwt" --max-files 10 --format human
```

Surfaces the 10 most-relevant files for "auth/session/jwt"-related work.

### Restrict to a directory and skip git history

```bash
harness context PLAN-42 --include "harness_skills/cli/**" --no-git
```

Useful when the plan's scope is known to be one subtree.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Manifest generated — at least one file was discovered. |
| `1` | No candidate files matched any of the discovery strategies. |
| `2` | Internal error — state service unreachable, glob malformed, etc. |

## See also

- [`harness plan`](plan.md) — defines plan IDs that `context` can scope to.
- [`harness search`](search.md) — symbol-level lookup; complementary to `context`'s file-level discovery.
- [`harness resume`](resume.md) — produces a similar context block for resuming an interrupted session, drawing from plan-progress state instead of plan scope.
