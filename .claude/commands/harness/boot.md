<<<<<<< HEAD
# Harness Boot

Generate a per-worktree boot script that launches an isolated application instance for the
current agent task, then optionally execute the script and wait for its health check to pass.

Each invocation writes a self-contained `boot_<worktree_id>.sh` to the project root.
The script exports `PORT`, optional database-isolation variables, and any extra environment
variables before launching the application.  After launch it polls a configurable health
endpoint until the instance is ready or the timeout is exceeded.

Use this skill whenever an agent task needs its own running application instance — for
integration tests, browser automation, API smoke checks, or any scenario where a live
server must be available.

---

## Usage

```bash
# Minimal — auto-detect worktree ID and use defaults
/harness:boot

# Specify the start command explicitly
/harness:boot --cmd "uvicorn myapp.main:app"

# Specify a port (default: auto-assigned from worktree ID hash)
/harness:boot --port 8101

# SQLite file isolation (one DB file per worktree)
/harness:boot --db-isolation file

# PostgreSQL schema isolation (one schema per worktree)
/harness:boot --db-isolation schema --db-schema "wt_abc123"

# Custom health path and timeout
/harness:boot --health-path /api/healthz --health-timeout 60

# Write the script but do not execute it
/harness:boot --no-boot

# Write and execute — also emit health_check_spec.json
/harness:boot --cmd "python -m myapp" --emit-spec

# Override the log file path
/harness:boot --log-file /tmp/harness_app.log
```

---

## Instructions

### Step 1 — Resolve the worktree ID

The worktree ID is a short, filesystem-safe identifier for the current agent task.
Resolve it in this priority order:

```bash
# 1. Explicit environment variable (set by claw-forge when launching the agent)
if [ -n "${HARNESS_WORKTREE_ID:-}" ]; then
    WORKTREE_ID="$HARNESS_WORKTREE_ID"

# 2. Git worktree path basename (works inside a git worktree)
elif WORKTREE_PATH=$(git rev-parse --show-toplevel 2>/dev/null); then
    WORKTREE_ID=$(basename "$WORKTREE_PATH" | sed 's/[^a-zA-Z0-9_-]/_/g' | cut -c1-32)

# 3. Short git commit hash (always available)
elif GIT_SHA=$(git rev-parse --short HEAD 2>/dev/null); then
    WORKTREE_ID="wt_${GIT_SHA}"

# 4. Fallback — timestamp-based
else
    WORKTREE_ID="wt_$(date +%s)"
fi

echo "[harness:boot] Worktree ID: $WORKTREE_ID"
```

If `--worktree-id` was passed explicitly, use that value and skip all detection.

---

### Step 2 — Resolve the start command

Look up the start command in this priority order:

1. **Explicit `--cmd` argument** — use as-is.
2. **`harness.config.yaml` `boot.start_command` key** — read with:
   ```bash
   python -c "
   import yaml, sys
   try:
       cfg = yaml.safe_load(open('harness.config.yaml'))
       cmd = cfg.get('boot', {}).get('start_command', '')
       print(cmd)
   except Exception:
       pass
   "
   ```
3. **Stack heuristics** — infer from detected stack:

   | Detected stack | Default start command |
   |---|---|
   | FastAPI / Uvicorn | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
   | Flask | `flask run --host 0.0.0.0 --port $PORT` |
   | Django | `python manage.py runserver 0.0.0.0:$PORT` |
   | Next.js | `next start -p $PORT` |
   | Express / Node | `node server.js` |
   | Generic Python | `python -m http.server $PORT` |
   | Unknown | (prompt the user — see Step 2a) |

4. **Step 2a — Request the start command** — if no start command can be resolved,
   emit a clear error and request human input:

   ```bash
   echo "[harness:boot] ERROR: No start command found." >&2
   echo "  Provide one via --cmd, or add 'boot.start_command' to harness.config.yaml." >&2
   exit 1
   ```

---

### Step 3 — Allocate a port

Each worktree receives a deterministic port so that re-running the skill produces the
same port (preventing orphaned processes on retries).

```python
import hashlib

BASE_PORT = 8100
PORT_RANGE = 900   # 8100–8999; avoids conflict with state service at 8420

def worktree_port(worktree_id: str, base: int = BASE_PORT, span: int = PORT_RANGE) -> int:
    digest = int(hashlib.sha256(worktree_id.encode()).hexdigest(), 16)
    return base + (digest % span)
```

If `--port` is passed, use the explicit value (no hashing).

After choosing a port, verify it is not already bound:

```python
import socket

def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False
```

If the deterministic port is occupied, linearly scan upward (up to 20 attempts) for the
next free port:

```python
port = worktree_port(worktree_id)
for attempt in range(20):
    if port_is_free(port):
        break
    port += 1
else:
    raise RuntimeError("No free port found in range 8100–9099")
```

---

### Step 4 — Build the `BootConfig`

Assemble a `BootConfig` from the resolved values:

```python
from harness_skills.boot import (
    BootConfig,
    DatabaseIsolation,
    HealthCheckMethod,
    IsolationConfig,
)

db_isolation_map = {
    "none":      DatabaseIsolation.NONE,
    "schema":    DatabaseIsolation.SCHEMA,
    "file":      DatabaseIsolation.FILE,
    "container": DatabaseIsolation.CONTAINER,
}

isolation = IsolationConfig(
    port=port,
    db_isolation=db_isolation_map.get(db_isolation_arg, DatabaseIsolation.NONE),
    db_schema=db_schema_arg or f"wt_{worktree_id}",
    db_file=db_file_arg or f"/tmp/harness_{worktree_id}.db",
    extra_env=extra_env_dict,   # parsed from --env KEY=VALUE flags
)

config = BootConfig(
    worktree_id=worktree_id,
    start_command=start_command,
    isolation=isolation,
    health_path=health_path_arg,        # default: "/health"
    health_method=HealthCheckMethod.GET,
    health_timeout_s=float(health_timeout_arg),   # default: 30
    health_interval_s=1.0,
    working_dir=working_dir_arg or "",
    log_file=log_file_arg or "",
)
```

---

### Step 5 — Generate and write the boot script

```python
from harness_skills.boot import generate_boot_script
import os, stat

script_content = generate_boot_script(config)
script_path = f"boot_{worktree_id}.sh"

with open(script_path, "w") as fh:
    fh.write(script_content)

# Make executable
os.chmod(script_path, os.stat(script_path).st_mode | stat.S_IXUSR | stat.S_IXGRP)

print(f"[harness:boot] Script written → {script_path}")
```

---

### Step 6 — Optionally emit `health_check_spec.json`

When `--emit-spec` is passed (or when `--no-boot` is used, so something else needs to
know how to probe the instance), write a machine-readable spec:

```python
from harness_skills.boot import generate_health_check_spec
import json, dataclasses

spec = generate_health_check_spec(config)
spec_path = f"health_check_spec_{worktree_id}.json"

with open(spec_path, "w") as fh:
    json.dump(dataclasses.asdict(spec), fh, indent=2)

print(f"[harness:boot] Health check spec → {spec_path}")
```

The spec JSON looks like:

```json
{
  "url": "http://localhost:8237/health",
  "method": "GET",
  "expected_codes": [200, 201, 202, 203, 204, 205, 206, 207, 208, 226],
  "timeout_s": 5.0,
  "interval_s": 1.0,
  "max_wait_s": 30.0,
  "headers": {}
}
```

Downstream agents or CI scripts can read this file to poll the instance without needing
to know port allocation details.

---

### Step 7 — Boot the instance (unless `--no-boot`)

When `--no-boot` is **not** set, use `boot_instance()` to launch the process and wait
for the health check to pass:

```python
from harness_skills.boot import boot_instance

result = boot_instance(config)

if result.ready:
    print(
        f"[harness:boot] ✓ Instance ready\n"
        f"  PID:        {result.pid}\n"
        f"  Port:       {result.port}\n"
        f"  Health URL: {result.health_url}\n"
        f"  Elapsed:    {result.elapsed_s:.1f}s"
    )
else:
    import sys
    print(
        f"[harness:boot] ✗ Boot failed\n"
        f"  Error:   {result.error}\n"
        f"  Elapsed: {result.elapsed_s:.1f}s",
        file=sys.stderr,
    )
    sys.exit(1)
```

---

### Step 8 — Emit the boot summary

After a successful boot (or after script generation when `--no-boot`), display a
structured summary:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Harness Boot — worktree: <worktree_id>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Script        boot_<worktree_id>.sh
  Port          <port>
  DB isolation  <none | file | schema | container>
  Health URL    http://localhost:<port><health_path>
  Status        ✓ ready  (elapsed: <N>s)   [or: script written, not started]

  Environment
  ────────────────────────────────────────────────────
  PORT=<port>
  <DB_SCHEMA=wt_...>           (schema isolation only)
  <DATABASE_URL=sqlite:///...> (file isolation only)
  <EXTRA_KEY=value>            (each --env pair)

  Artifacts
  ────────────────────────────────────────────────────
  boot_<worktree_id>.sh            (executable boot script)
  health_check_spec_<id>.json      (emitted with --emit-spec)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Tip: re-run with --no-boot to regenerate the script
  without starting a new process.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### Step 9 — Register with the state service (optional)

If the state service is reachable and a feature ID is available, record the running
instance so other agents can discover it:

```bash
FEATURE_ID="${HARNESS_FEATURE_ID:-}"
STATE_URL="${CLAW_FORGE_STATE_URL:-http://localhost:8888}"

if [ -n "$FEATURE_ID" ]; then
    curl -sf -X PATCH "$STATE_URL/features/$FEATURE_ID" \
        -H "Content-Type: application/json" \
        -d "{
              \"boot_port\": $PORT,
              \"boot_pid\": $APP_PID,
              \"boot_health_url\": \"$HEALTH_URL\",
              \"boot_script\": \"$SCRIPT_PATH\"
            }" \
    && echo "[harness:boot] Registered instance with state service" \
    || echo "[harness:boot] Warning: state service update failed (non-fatal)"
fi
```

Registration failure is non-fatal — the instance is still usable.

---

## Options

| Flag | Default | Effect |
|---|---|---|
| `--worktree-id ID` | auto-detected | Override the worktree identifier |
| `--cmd COMMAND` | auto-detected | Shell command that starts the application |
| `--port PORT` | hash-derived (8100–8999) | TCP port the instance should bind to |
| `--db-isolation MODE` | `none` | Database isolation: `none`, `file`, `schema`, `container` |
| `--db-schema NAME` | `wt_<worktree_id>` | Schema name (only with `--db-isolation schema`) |
| `--db-file PATH` | `/tmp/harness_<id>.db` | SQLite file path (only with `--db-isolation file`) |
| `--health-path PATH` | `/health` | URL path of the health check endpoint |
| `--health-timeout N` | `30` | Seconds to wait for health check before failing |
| `--no-boot` | off | Write the script but do not execute it |
| `--emit-spec` | off | Write `health_check_spec_<id>.json` alongside the boot script |
| `--log-file PATH` | — | Redirect application stdout/stderr to this file |
| `--working-dir DIR` | — | Working directory for the application process |
| `--env KEY=VALUE` | — | Extra environment variable to inject (repeatable) |

---

## Output artifacts

| Artifact | Description |
|---|---|
| `boot_<worktree_id>.sh` | Self-contained boot script; `chmod +x` ready to execute |
| `health_check_spec_<worktree_id>.json` | Machine-readable health check specification (only with `--emit-spec` or `--no-boot`) |

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Agent needs a live app instance for integration tests | **`/harness:boot`** ← you are here |
| Generate the script without launching anything | **`/harness:boot --no-boot`** |
| Run all quality gates (includes boot if configured) | `/harness:evaluate` |
| Open a browser against the booted instance | `/browser-automation` |
| Show health and status of running plans | `/harness:status` |

---

## Notes

- **Port determinism** — the same worktree ID always produces the same base port,
  so the skill is safe to re-run inside a retry loop without accumulating orphaned
  processes.
- **Isolation is opt-in** — the default `--db-isolation none` shares whatever database
  is already configured.  Use `file` for SQLite apps or `schema` for PostgreSQL apps
  that need full state isolation per agent.
- **Script is idempotent** — re-running `/harness:boot --no-boot` regenerates
  `boot_<id>.sh` from the same config.  The script itself is deterministic for a given
  `BootConfig`.
- **State service is optional** — Step 9 registration is best-effort; unreachable
  service is logged but does not fail the skill.
- **Never auto-commits** — boot scripts are ephemeral; add `boot_*.sh` and
  `health_check_spec_*.json` to `.gitignore` if they should not appear in commits.
- **CI usage** — in CI environments set `HARNESS_WORKTREE_ID` to the job ID or
  pipeline run ID for collision-free port allocation across parallel jobs.
||||||| 7446a2f
=======
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
>>>>>>> feat/skill-invocatio-skill-registers-as-harness-boot-for-lau
