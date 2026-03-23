# Harness Boot

Launch an isolated application instance for an agent task — assigns a dedicated
port, sets up optional database isolation (PostgreSQL schema, SQLite file, or
container), and blocks until the health endpoint returns HTTP 2xx.

Use this skill when an agent needs its own running service before executing
tests or interacting with the application.  Each worktree gets a fully isolated
instance so concurrent agents never share state.

---

## Usage

```bash
# Generate a self-contained boot script (write to disk, run later)
/harness:boot --worktree-id task-fb563322 \
              --command "uvicorn myapp.main:app" \
              --port 8001 \
              --health-path /health \
              --generate-script

# Launch directly (Python subprocess) and wait for health check
/harness:boot --worktree-id task-fb563322 \
              --command "uvicorn myapp.main:app" \
              --port 8001 \
              --health-path /health \
              --launch

# PostgreSQL schema isolation
/harness:boot --worktree-id task-fb563322 \
              --command "python -m myapp" \
              --port 8002 \
              --db-isolation schema \
              --db-schema worktree_fb563322 \
              --launch

# SQLite file isolation
/harness:boot --worktree-id task-fb563322 \
              --command "flask run --port 8003" \
              --port 8003 \
              --db-isolation file \
              --launch

# Adjust timeouts and log output
/harness:boot --worktree-id task-fb563322 \
              --command "node server.js" \
              --port 8004 \
              --health-timeout 60 \
              --health-interval 2 \
              --log-file /tmp/harness_fb563322.log \
              --launch

# Dry run — print the generated boot script without writing or launching
/harness:boot --worktree-id task-fb563322 \
              --command "uvicorn myapp.main:app" \
              --port 8001 \
              --dry-run
```

---

## Instructions

### Step 1 — Resolve arguments

Collect the following values from the invocation (or apply defaults):

| Argument | Source | Default |
|---|---|---|
| `worktree_id` | `--worktree-id` flag | **required** |
| `start_command` | `--command` flag | **required** |
| `port` | `--port` flag | `8000` |
| `health_path` | `--health-path` flag | `"/health"` |
| `health_method` | `--health-method` flag | `"GET"` |
| `health_timeout_s` | `--health-timeout` flag | `30` |
| `health_interval_s` | `--health-interval` flag | `1.0` |
| `db_isolation` | `--db-isolation` flag | `"none"` |
| `db_schema` | `--db-schema` flag | `""` (auto-derived when isolation=schema) |
| `db_file` | `--db-file` flag | `""` (auto-derived when isolation=file) |
| `extra_env` | `--env KEY=VALUE` (repeatable) | `{}` |
| `working_dir` | `--working-dir` flag | `""` (inherit) |
| `log_file` | `--log-file` flag | `""` (inherit streams) |
| `mode` | `--generate-script` or `--launch` flag | `--launch` |
| `output` | `--output` flag | `boot_<worktree_id>.sh` |
| `dry_run` | `--dry-run` flag | `false` |

Validate:
- `worktree_id` must be a non-empty string containing only alphanumerics, `-`, or `_`.
- `start_command` must be a non-empty string or list.
- `port` must be in the range 1024–65535.
- `db_isolation` must be one of: `none`, `schema`, `file`, `container`.

If validation fails, emit a descriptive error and exit 1.

---

### Step 2 — Construct the `BootConfig`

Build the configuration object from the resolved arguments:

```python
from harness_skills.boot import (
    BootConfig,
    IsolationConfig,
    DatabaseIsolation,
    HealthCheckMethod,
)

isolation = IsolationConfig(
    port=port,
    db_isolation=DatabaseIsolation(db_isolation),
    db_schema=db_schema,
    db_file=db_file,
    extra_env=extra_env,   # dict parsed from --env KEY=VALUE flags
)

config = BootConfig(
    worktree_id=worktree_id,
    start_command=start_command,
    isolation=isolation,
    health_path=health_path,
    health_method=HealthCheckMethod(health_method.upper()),
    health_timeout_s=health_timeout_s,
    health_interval_s=health_interval_s,
    working_dir=working_dir,
    log_file=log_file,
)
```

---

### Step 3 — Execute the requested mode

#### Mode A — `--generate-script` (write boot script to disk)

```python
from harness_skills.boot import generate_boot_script

script_content = generate_boot_script(config)

output_path = output or f"boot_{config.worktree_id}.sh"

if dry_run:
    print(script_content)
else:
    with open(output_path, "w") as f:
        f.write(script_content)
    import os
    os.chmod(output_path, 0o755)
    print(f"[harness:boot] Script written to {output_path}")
    print(f"[harness:boot] Run with:  bash {output_path}")
```

The generated script:
1. Exports `PORT` and any isolation env-vars (`DB_SCHEMA`, `DATABASE_URL`).
2. Launches the application in the background with `&`.
3. Polls the health endpoint via `curl` every `health_interval_s` seconds.
4. Exits `0` when HTTP 2xx is received; exits `1` and kills the process on
   timeout.

#### Mode B — `--launch` (boot directly from Python, default)

```python
from harness_skills.boot import boot_instance

if dry_run:
    # Print the script that *would* be used without starting the process
    from harness_skills.boot import generate_boot_script
    print(generate_boot_script(config))
else:
    result = boot_instance(config)
    if result.ready:
        print(
            f"[harness:boot] Instance ready\n"
            f"  worktree: {result.worktree_id}\n"
            f"  PID:      {result.pid}\n"
            f"  port:     {result.port}\n"
            f"  URL:      http://localhost:{result.port}{health_path}\n"
            f"  elapsed:  {result.elapsed_s:.1f}s"
        )
    else:
        print(f"[harness:boot] Boot FAILED: {result.error}", file=sys.stderr)
        sys.exit(1)
```

`boot_instance` always returns a `BootResult` — inspect `result.ready` before
proceeding.  When `ready=False` the subprocess is already killed; the error
field contains a diagnostic message.

---

### Step 4 — Emit a boot summary

After a successful launch, display a structured summary:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Harness Boot — instance ready
  Worktree:  <worktree_id>
  Mode:      <launch | generate-script>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Instance details
  ─────────────────────────────────────────────────────
  PID            <pid>
  Port           <port>
  Health URL     http://localhost:<port><health_path>
  DB isolation   <none | schema=<name> | file=<path> | container>
  Log file       <path | inherited>
  Elapsed        <elapsed_s>s
  ─────────────────────────────────────────────────────

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Next steps
  • Run your tests against http://localhost:<port>
  • Kill the instance when done: kill <pid>
  • Or run /harness:evaluate to execute all quality gates
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

In `--dry-run` mode, prefix the header with `[DRY-RUN]` and print the generated
script content instead of instance details.

For `--generate-script` mode, replace "Instance details" with "Script details"
and show the output path instead of PID/elapsed.

On failure (exit code 1), print only the error message to stderr — no summary
block.

---

## Options

| Flag | Default | Effect |
|---|---|---|
| `--worktree-id ID` | **required** | Short identifier for this agent worktree (task-UUID prefix or branch slug) |
| `--command CMD` | **required** | Shell command to launch the application (e.g. `"uvicorn myapp:app"`) |
| `--port PORT` | `8000` | TCP port the instance should bind to |
| `--health-path PATH` | `"/health"` | URL path of the health check endpoint |
| `--health-method METHOD` | `"GET"` | HTTP method for health probes (`GET` or `HEAD`) |
| `--health-timeout SECS` | `30` | Max seconds to wait for health check before declaring boot failed |
| `--health-interval SECS` | `1.0` | Seconds between health probe attempts |
| `--db-isolation TYPE` | `"none"` | Database isolation strategy: `none`, `schema`, `file`, `container` |
| `--db-schema NAME` | `""` | PostgreSQL schema name (only used when `--db-isolation schema`; auto-derived from `worktree_id` when empty) |
| `--db-file PATH` | `""` | SQLite file path (only used when `--db-isolation file`; auto-derived when empty) |
| `--env KEY=VALUE` | — | Extra environment variable to inject; may be repeated |
| `--working-dir DIR` | `""` | Working directory for the subprocess (empty = inherit) |
| `--log-file PATH` | `""` | Redirect app stdout/stderr to this file (empty = inherit streams) |
| `--generate-script` | off | Write a self-contained `boot_<id>.sh` to disk instead of launching directly |
| `--launch` | on | Launch the application directly via Python subprocess (default mode) |
| `--output PATH` | `boot_<worktree_id>.sh` | Destination for the generated script (only used with `--generate-script`) |
| `--dry-run` | off | Print what would happen without writing or launching |

---

## Output artifacts

| Artifact | Mode | Description |
|---|---|---|
| `boot_<worktree_id>.sh` | `--generate-script` | Self-contained bash script that launches and health-checks the instance |
| (running process) | `--launch` | Background subprocess with the application; inspect `BootResult.pid` |
| stdout summary | both | Structured boot summary with PID, port, health URL, and elapsed time |

The skill does **not** write any persistent state file; process lifecycle is the
caller's responsibility.

---

## Schema

The skill is backed by `harness_skills.boot`:

```python
from harness_skills.boot import (
    BootConfig,          # Full configuration for one isolated instance
    IsolationConfig,     # Port, DB, and extra-env isolation settings
    HealthCheckSpec,     # Machine-readable spec of the health endpoint
    BootResult,          # Outcome of boot_instance()
    DatabaseIsolation,   # Enum: NONE | SCHEMA | FILE | CONTAINER
    HealthCheckMethod,   # Enum: GET | HEAD
    generate_boot_script,      # BootConfig -> str (bash script content)
    generate_health_check_spec,# BootConfig -> HealthCheckSpec
    boot_instance,             # BootConfig, timeout? -> BootResult
)
```

`BootResult` fields:

| Field | Type | Description |
|---|---|---|
| `worktree_id` | `str` | Mirrors `BootConfig.worktree_id` |
| `pid` | `int` | PID of the launched process (`0` on pre-launch failure) |
| `port` | `int` | Port the instance is bound to |
| `health_url` | `str` | URL that was polled to confirm readiness |
| `ready` | `bool` | `True` when the health check passed within the timeout |
| `elapsed_s` | `float` | Wall-clock seconds from start to health pass (or timeout) |
| `error` | `str` | Diagnostic message when `ready=False`; empty string on success |

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Start an isolated app instance before running tests | **`/harness:boot`** ← you are here |
| Run all quality gates against a live instance | `/harness:evaluate` |
| Validate architecture & principles | `/harness:lint` |
| Show current gate health metrics | `/harness:status` |
| Bootstrap harness config for a new project | `/harness:create` |
| Capture a DOM/visual snapshot of a running page | `/harness:screenshot` |

---

## Notes

- **Never shared state** — each `worktree_id` gets a dedicated port and
  optional isolated database, so concurrent agents cannot interfere.
- **Always inspect `result.ready`** — `boot_instance` always returns a
  `BootResult`; a `False` ready value means the process was killed and an
  error message is available in `result.error`.
- **Health check is mandatory** — the skill blocks until the health endpoint
  responds with HTTP 2xx or the timeout is reached; there is no "fire and
  forget" mode.
- **Process lifecycle is the caller's responsibility** — the skill does not
  register a shutdown hook; the caller must kill the process when the task
  completes (`kill <pid>`).
- **CI-safe** — generates no network side-effects beyond the health probe loop
  on `localhost`.
- **State service not required** — this skill operates entirely via local
  subprocess management; no calls to the claw-forge state service are made.
- **Idempotent script generation** — running `--generate-script` twice with
  the same `BootConfig` produces an identical file on the second run.
