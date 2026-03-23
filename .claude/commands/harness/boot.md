# Harness Boot

Generate a **per-worktree boot command** that starts an isolated application instance
and waits for its health check to pass before returning.

Each agent worktree gets its own TCP port and, for database-backed apps, its own schema
or SQLite file — so concurrent agents never share state.  The skill supports two modes:

- **Script mode** (default) — emit a self-contained `boot_<worktree_id>.sh` bash script
  that any CI runner or human operator can execute later.
- **Run mode** (`--run`) — generate the script *and* execute it immediately, streaming
  logs and returning a structured `BootResult` once the health check passes (or times
  out).

---

## Usage

```bash
# Generate a boot script (print to stdout, do not execute)
/harness:boot --worktree-id abc123 --start-cmd "uvicorn myapp.main:app" --port 8001

# Write the script to disk
/harness:boot --worktree-id abc123 --start-cmd "uvicorn myapp.main:app" --port 8001 \
    --output boot_abc123.sh

# Generate AND immediately boot the instance (run mode)
/harness:boot --worktree-id abc123 --start-cmd "uvicorn myapp.main:app" --port 8001 \
    --run

# Override the health endpoint path and timeout
/harness:boot --worktree-id abc123 --start-cmd "python manage.py runserver 8002" \
    --port 8002 --health-path /api/healthz --timeout 60

# Use HEAD instead of GET for the health probe (lighter-weight)
/harness:boot --worktree-id abc123 --start-cmd "..." --port 8001 --health-method HEAD

# PostgreSQL schema isolation (separate schema per worktree)
/harness:boot --worktree-id abc123 --start-cmd "..." --port 8001 \
    --db-isolation schema --db-schema worktree_abc123

# SQLite file isolation (separate DB file per worktree)
/harness:boot --worktree-id abc123 --start-cmd "..." --port 8001 \
    --db-isolation file --db-file /tmp/harness_abc123.db

# Pass extra environment variables to the app
/harness:boot --worktree-id abc123 --start-cmd "..." --port 8001 \
    --env FEATURE_FLAGS=beta --env LOG_LEVEL=debug

# Redirect app output to a log file
/harness:boot --worktree-id abc123 --start-cmd "..." --port 8001 \
    --log-file /tmp/harness_abc123.log --run

# Run from a specific directory
/harness:boot --worktree-id abc123 --start-cmd "npm start" --port 3001 \
    --working-dir /workspace/myapp --run

# Emit only the raw JSON BootResult (agent/CI mode)
/harness:boot --worktree-id abc123 --start-cmd "..." --port 8001 --run --format json
```

---

## Instructions

### Step 1 — Resolve the worktree ID

If `--worktree-id` is provided, use it directly.  Otherwise, auto-detect it from git:

```bash
WORKTREE_ID=$(git rev-parse --short HEAD 2>/dev/null || echo "local")
echo "Resolved worktree ID: $WORKTREE_ID"
```

The worktree ID is used in:
- The generated script filename (`boot_<worktree_id>.sh`)
- Log prefixes (`[harness:boot] worktree=<id>`)
- Auto-generated database schema and file names

---

### Step 2 — Build the BootConfig

Assemble a `BootConfig` from the resolved arguments:

```python
from harness_skills.boot import (
    BootConfig,
    DatabaseIsolation,
    HealthCheckMethod,
    IsolationConfig,
)

isolation = IsolationConfig(
    port=PORT,                           # --port (required)
    db_isolation=DatabaseIsolation(DB_ISOLATION),  # --db-isolation (default: "none")
    db_schema=DB_SCHEMA,                 # --db-schema (used when db_isolation=schema)
    db_file=DB_FILE,                     # --db-file   (used when db_isolation=file)
    extra_env=EXTRA_ENV,                 # --env KEY=VAL pairs (default: {})
)

config = BootConfig(
    worktree_id=WORKTREE_ID,
    start_command=START_COMMAND,         # --start-cmd (required)
    isolation=isolation,
    health_path=HEALTH_PATH,             # --health-path (default: "/health")
    health_method=HealthCheckMethod(HEALTH_METHOD),  # --health-method (default: "GET")
    health_timeout_s=float(TIMEOUT),     # --timeout (default: 30.0)
    health_interval_s=INTERVAL,          # --interval (default: 1.0)
    working_dir=WORKING_DIR,             # --working-dir (default: "")
    log_file=LOG_FILE,                   # --log-file (default: "")
)
```

**Validation rules:**
- `--port` must be an integer in the range 1024–65535.
- `--db-isolation` must be one of `none`, `schema`, `file`, `container`.
- `--health-method` must be `GET` or `HEAD`.
- `--timeout` must be a positive float.
- When `--db-isolation schema`, `--db-schema` defaults to `worktree_<worktree_id>` if omitted.
- When `--db-isolation file`, `--db-file` defaults to `/tmp/harness_<worktree_id>.db` if omitted.

---

### Step 3 — Generate the boot script

Call `generate_boot_script` to produce the bash script content:

```python
from harness_skills.boot import generate_boot_script

script_content = generate_boot_script(config)
```

The generated script:
1. Exports `PORT` and any isolation environment variables (`DB_SCHEMA`, `DATABASE_URL`).
2. Exports any `extra_env` key/value pairs.
3. Changes to `working_dir` (if set).
4. Launches the application in the background (`&`), redirecting to `log_file` if set.
5. Polls `http://localhost:<port><health_path>` with `curl` every `health_interval_s`
   seconds.
6. Exits `0` when a `2xx` response is received; exits `1` if the timeout is reached
   (and kills the background process first).

**Script filename:** `boot_<worktree_id>.sh`

---

### Step 4 — Write the script to disk (if `--output` is provided)

```python
import os

script_path = OUTPUT or f"boot_{config.worktree_id}.sh"
with open(script_path, "w") as fh:
    fh.write(script_content)
os.chmod(script_path, 0o755)
print(f"[harness:boot] Script written to: {script_path}")
```

If `--output` is not provided and `--run` is not set, print the script content to
stdout (for piping or review) without writing a file.

---

### Step 5 — Generate the health check spec

Always generate and emit the machine-readable `HealthCheckSpec`, regardless of whether
`--run` is active.  Downstream agents use this spec to poll the endpoint independently.

```python
from harness_skills.boot import generate_health_check_spec

spec = generate_health_check_spec(config)
```

The spec captures:
- `url` — full health endpoint URL (e.g. `http://localhost:8001/health`)
- `method` — HTTP method for probing
- `expected_codes` — HTTP 2xx codes accepted as healthy (200–299)
- `timeout_s` — per-request timeout (5 s)
- `interval_s` — seconds between retries
- `max_wait_s` — total wait budget

---

### Step 6 — Boot the instance (run mode only)

Only execute this step when `--run` is set.

```python
from harness_skills.boot import boot_instance

result = boot_instance(config)
```

`boot_instance` blocks until the health check passes or `health_timeout_s` elapses.
It always returns a `BootResult`; inspect `result.ready` to determine success.

**On success (`result.ready == True`):**
- `result.pid` — PID of the running process
- `result.port` — port it is bound to
- `result.health_url` — URL that passed the health check
- `result.elapsed_s` — seconds from start to health pass

**On failure (`result.ready == False`):**
- `result.error` — human-readable diagnostic message
- The subprocess has already been killed

---

### Step 7 — Emit the human-readable summary

#### Script mode (no `--run`)

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  harness boot  —  Boot Script Generated
  Worktree : <worktree_id>
  Port     : <port>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Start command : <start_command>
  Health URL    : http://localhost:<port><health_path>
  Health method : <GET|HEAD>
  Timeout       : <timeout_s>s   Interval: <interval_s>s
  DB isolation  : <none|schema|file|container>
  Log file      : <log_file | inherited streams>

  ── Generated script ──────────────────────────────────
  <script content printed verbatim>
  ──────────────────────────────────────────────────────

  Script written to: <output_path>        ← only if --output was given

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  To execute:  bash boot_<worktree_id>.sh
  Health spec: see JSON block below
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

#### Run mode (with `--run`)

**On success:**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  harness boot  —  Instance Ready  ✅
  Worktree : <worktree_id>
  Port     : <port>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  PID          : <pid>
  Health URL   : <health_url>
  Elapsed      : <elapsed_s>s
  DB isolation : <isolation_type>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Instance is healthy — ready to accept traffic.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**On failure:**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  harness boot  —  Boot Failed  ❌
  Worktree : <worktree_id>
  Port     : <port>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Error   : <error>
  Elapsed : <elapsed_s>s

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Troubleshooting tips
  • Check the log file for startup errors: <log_file>
  • Confirm the port is not already in use:
      lsof -i :<port>
  • Increase the timeout with --timeout <seconds>
  • Verify the start command is correct:
      <start_command>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### Step 8 — Emit machine-readable JSON

Always emit the following JSON block after the human-readable summary, regardless of
mode.  This is the canonical `BootResult` envelope consumed by downstream agents.

#### Script mode

```json
{
  "command": "harness boot",
  "mode": "script",
  "worktree_id": "<worktree_id>",
  "script_path": "<output_path | null>",
  "health_check_spec": {
    "url": "http://localhost:<port><health_path>",
    "method": "<GET|HEAD>",
    "expected_codes": [200, 201, 202, 203, 204, 205, 206, 207, 208, 226],
    "timeout_s": 5.0,
    "interval_s": <interval_s>,
    "max_wait_s": <timeout_s>
  },
  "boot_result": null
}
```

#### Run mode

```json
{
  "command": "harness boot",
  "mode": "run",
  "worktree_id": "<worktree_id>",
  "script_path": "<output_path | null>",
  "health_check_spec": {
    "url": "http://localhost:<port><health_path>",
    "method": "<GET|HEAD>",
    "expected_codes": [200, 201, 202, 203, 204, 205, 206, 207, 208, 226],
    "timeout_s": 5.0,
    "interval_s": <interval_s>,
    "max_wait_s": <timeout_s>
  },
  "boot_result": {
    "worktree_id": "<worktree_id>",
    "pid": <pid>,
    "port": <port>,
    "health_url": "http://localhost:<port><health_path>",
    "ready": <true|false>,
    "elapsed_s": <elapsed>,
    "error": "<error message or empty string>"
  }
}
```

When `--format json` is passed, emit **only** this JSON block (no human-readable header).

---

## Options

| Flag | Default | Effect |
|---|---|---|
| `--worktree-id ID` | auto (git short SHA) | Identifier for this agent worktree |
| `--start-cmd CMD` | *(required)* | Shell command to start the application |
| `--port PORT` | *(required)* | TCP port the application will bind to |
| `--health-path PATH` | `/health` | URL path of the health check endpoint |
| `--health-method METHOD` | `GET` | HTTP method for health probes (`GET` or `HEAD`) |
| `--timeout SECS` | `30.0` | Maximum seconds to wait for the health check |
| `--interval SECS` | `1.0` | Seconds between health check polls |
| `--db-isolation TYPE` | `none` | Database isolation strategy: `none`, `schema`, `file`, `container` |
| `--db-schema NAME` | `worktree_<id>` | PostgreSQL schema name (only with `--db-isolation schema`) |
| `--db-file PATH` | `/tmp/harness_<id>.db` | SQLite file path (only with `--db-isolation file`) |
| `--env KEY=VAL` | *(none)* | Extra environment variable; repeat for multiple |
| `--working-dir DIR` | *(inherited)* | Working directory for the application process |
| `--log-file PATH` | *(inherited streams)* | File to redirect application stdout/stderr |
| `--output PATH` | *(stdout)* | Write the generated boot script to this path |
| `--run` | off | Generate the script *and* immediately execute it |
| `--format json` | human | Emit only raw JSON; suppress human-readable header |

---

## Database isolation reference

| `--db-isolation` | Environment variable set | Use when |
|---|---|---|
| `none` | *(none)* | App has no database, or isolation is handled externally |
| `schema` | `DB_SCHEMA=<name>` | App connects to PostgreSQL and reads `DB_SCHEMA` |
| `file` | `DATABASE_URL=sqlite:///<path>` | App uses SQLite and reads `DATABASE_URL` |
| `container` | *(none — external)* | Container orchestrator provides a dedicated DB container |

---

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Script generated successfully **or** instance booted and health check passed |
| `1` | Health check timed out (run mode) or invalid arguments |
| `2` | Process failed to start (run mode) |

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Start an isolated app instance before running browser tests | **`/harness:boot`** ← you are here |
| Check if an already-running instance is healthy | probe `health_check_spec.url` directly |
| Capture a DOM snapshot of a running instance | `/harness:screenshot` |
| Run all quality gates on the current branch | `/harness:evaluate` |
| Show active plan / task status | `/harness:status` |
| Coordinate concurrent agent worktrees | `/coordinate` |

---

## Notes

- **Idempotent script generation** — calling `/harness:boot` twice with the same
  arguments produces an identical script. The script itself is not idempotent: running
  it twice will launch a second process on the same port.
- **Port conflicts** — it is the caller's responsibility to ensure each worktree uses a
  unique port. A common convention is `BASE_PORT + worktree_index`.
- **Health check contract** — the application must expose a health endpoint that returns
  HTTP 2xx when ready. See `docs/health-check-endpoint-spec.md` for the full response
  schema.
- **Process ownership** — in run mode, `boot_instance` launches a background subprocess
  owned by the current process. If the parent exits, the subprocess may be orphaned;
  ensure your CI pipeline or agent harness sends a `SIGTERM` on cleanup.
- **Container isolation** — when `--db-isolation container` is chosen, the boot script
  emits a comment noting that `DATABASE_URL` must already be set by the container
  orchestrator. No automatic container lifecycle management is performed.
- **`--format json` in CI** — pipe the JSON block into `jq` to extract the PID or port:
  ```bash
  PORT=$(/harness:boot ... --run --format json | jq -r '.boot_result.port')
  ```
