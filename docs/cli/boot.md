# harness boot

> Launch an isolated application instance for an agent worktree, with port assignment, optional database isolation, and a health-check probe loop.

`boot` is the bridge between an agent's worktree and a runnable instance of the application under test. It assigns a non-conflicting TCP port, optionally configures database isolation (so two agents don't trample each other's data), starts the application via the supplied command, and blocks until the health endpoint returns HTTP 2xx — at which point the agent can safely exercise the instance.

The same options also support `--generate-script` mode, which writes the boot recipe to disk (`boot_<worktree-id>.sh`) for human inspection or later replay without launching anything.

## Synopsis

```bash
harness boot --worktree-id <ID> --command "<launch cmd>" [OPTIONS]
```

`--worktree-id` and `--command` are required.

## Options

### Identification

| Flag | Type | Default | Description |
|---|---|---|---|
| `--worktree-id` | str | required | Short identifier for the agent worktree. Embedded in port allocation, log file, and generated-script names. |
| `--command` | str | required | Shell command to launch the application (e.g., `"npm run dev"`). |

### Port & process

| Flag | Type | Default | Description |
|---|---|---|---|
| `--port` | int (1024–65535) | `8000` | TCP port for the isolated instance. |
| `--working-dir` | str | `""` (cwd) | Working directory for the launched subprocess. |
| `--env` | str (multiple) | — | Extra env vars in `KEY=VALUE` form. Repeat for multiple. |
| `--log-file` | str | `""` | Redirect stdout/stderr to this file. |

### Health check

| Flag | Type | Default | Description |
|---|---|---|---|
| `--health-path` | str | `/health` | URL path on the health endpoint. |
| `--health-method` | choice (`GET`/`HEAD`) | `GET` | HTTP method for the probe. |
| `--health-timeout` | float | `30.0` | Max seconds to wait for the first 2xx before declaring boot failed. |
| `--health-interval` | float | `1.0` | Seconds between probe attempts. |

### Database isolation

| Flag | Type | Default | Description |
|---|---|---|---|
| `--db-isolation` | choice (`none`/`schema`/`file`/`container`) | `none` | Strategy for isolating database state per worktree. |
| `--db-schema` | str | `""` | PostgreSQL schema name (only meaningful with `--db-isolation schema`). |
| `--db-file` | str | `""` | SQLite file path (only meaningful with `--db-isolation file`). |

### Mode

| Flag | Type | Default | Description |
|---|---|---|---|
| `--launch` | flag | default | Launch directly via Python subprocess. |
| `--generate-script` | flag | — | Write boot script to disk instead of launching. |
| `--output` | path | — | Destination for generated script (only with `--generate-script`). |
| `--dry-run` | flag | — | Print the generated script to stdout without writing or launching. |

## Workflows

### Smoke-launch a Node app for an agent

```bash
harness boot \
  --worktree-id agent-alpha \
  --command "npm run dev" \
  --port 8123 \
  --health-path /api/health
```

Blocks until `http://localhost:8123/api/health` returns 2xx, then exits `0`.

### Two parallel agents, isolated SQLite databases

```bash
# Agent alpha
harness boot --worktree-id alpha --command "./run.sh" \
  --port 8101 --db-isolation file --db-file /tmp/alpha.sqlite

# Agent beta
harness boot --worktree-id beta --command "./run.sh" \
  --port 8102 --db-isolation file --db-file /tmp/beta.sqlite
```

### Inspect the boot recipe before running it

```bash
harness boot --worktree-id alpha --command "./run.sh" \
  --port 8101 --dry-run
```

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Instance ready (health probe passed) or script written successfully. |
| `1` | Boot failed — health probe didn't return 2xx within `--health-timeout`, validation error, or launch failure. |

## See also

- [`harness coordinate`](coordinate.md) — when running multiple boots in parallel, use `coordinate` to detect lock or task conflicts up front.
- The state service (default `http://localhost:8888`) tracks per-worktree port allocations and lock state for cross-agent visibility.
