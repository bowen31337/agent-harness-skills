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
