---
name: boot
description: "Per-worktree boot script generator and instance launcher. Generates a self-contained bash script that starts an isolated application instance on a dedicated port, optionally isolates the database (PostgreSQL schema, SQLite file, or container), and polls a health endpoint until the instance is ready. Also supports booting the instance directly from Python without writing a script to disk. Use when: (1) starting an app server for an agent worktree so it doesn't collide with other concurrent agents, (2) generating a reproducible boot script to store alongside the worktree, (3) verifying an instance is healthy before running tests, (4) setting up database isolation per task, (5) scripting multi-agent environments where each agent needs its own running service. Triggers on: boot instance, start isolated server, per-worktree boot, generate boot script, health check, isolate database, launch app for agent, worktree isolation."
---

# Boot Skill

## Overview

The boot skill gives every agent worktree its own **isolated application
instance** — a dedicated port, an optional isolated database schema or file, and
a health-check loop that blocks until the app is accepting requests.

Two entry points are provided:

| Entry point | When to use |
|---|---|
| `generate_boot_script(config)` | Write a `boot_<id>.sh` to disk and run it later (e.g. in CI or a pre-task hook). |
| `boot_instance(config)` | Launch and health-check the app directly from Python in the same process. |

---

## Workflow

**Do you need a standalone bash script?**
→ [Generate a boot script](#generate-a-boot-script)

**Do you need to start the app from Python?**
→ [Boot directly from Python](#boot-directly-from-python)

**Do you need database isolation between concurrent agents?**
→ [Configure database isolation](#configure-database-isolation)

---

## Generate a Boot Script

```python
from harness_skills.boot import BootConfig, IsolationConfig, generate_boot_script

config = BootConfig(
    worktree_id="fb563322",          # short task-UUID prefix or branch slug
    start_command="uvicorn myapp.main:app --port 8001",
    isolation=IsolationConfig(port=8001),
    health_path="/healthz",
    health_timeout_s=30,
    log_file="/tmp/harness_fb563322.log",
)

script_content = generate_boot_script(config)

# Write to disk and make executable
with open("boot_fb563322.sh", "w") as f:
    f.write(script_content)
```

The generated script (`boot_<worktree_id>.sh`):

1. Exports `PORT` and any isolation env-vars.
2. Launches the application in the background with `&`.
3. Polls `curl` against the health endpoint every `health_interval_s` seconds.
4. Exits `0` when HTTP 2xx is received; exits `1` and kills the process on
   timeout.

Run it with:

```bash
bash boot_fb563322.sh
```

---

## Boot Directly from Python

```python
from harness_skills.boot import BootConfig, IsolationConfig, boot_instance

cfg = BootConfig(
    worktree_id="fb563322",
    start_command="uvicorn myapp.main:app --port 8001",
    isolation=IsolationConfig(port=8001),
    health_path="/healthz",
    health_timeout_s=30,
)

result = boot_instance(cfg)

if result.ready:
    print(f"Instance ready — PID {result.pid} on port {result.port} "
          f"({result.elapsed_s:.1f}s)")
else:
    print(f"Boot failed: {result.error}")
```

`boot_instance` returns a `BootResult` regardless of success or failure —
always inspect `result.ready` before proceeding.

---

## Configure Database Isolation

### PostgreSQL schema per worktree

```python
from harness_skills.boot import IsolationConfig, DatabaseIsolation

isolation = IsolationConfig(
    port=8001,
    db_isolation=DatabaseIsolation.SCHEMA,
    db_schema="worktree_fb563322",   # omit to auto-derive from worktree_id
)
```

The boot script exports `DB_SCHEMA=worktree_fb563322`.  Your app must honour
that variable when constructing its database connection.

### SQLite file per worktree

```python
isolation = IsolationConfig(
    port=8001,
    db_isolation=DatabaseIsolation.FILE,
    db_file="/tmp/harness_fb563322.db",  # omit to auto-derive
)
```

Exports `DATABASE_URL=sqlite:///...`.

### Container-level isolation

```python
isolation = IsolationConfig(
    port=8001,
    db_isolation=DatabaseIsolation.CONTAINER,
)
```

Assumes `DATABASE_URL` is already set by the container orchestrator; the boot
script emits a comment to that effect.

### No isolation (default)

```python
isolation = IsolationConfig(port=8001)   # db_isolation=DatabaseIsolation.NONE
```

---

## Health Check Spec

Use `generate_health_check_spec` to get a machine-readable spec you can persist
or pass to another component:

```python
from harness_skills.boot import generate_health_check_spec

spec = generate_health_check_spec(cfg)
# spec.url          → "http://localhost:8001/healthz"
# spec.method       → HealthCheckMethod.GET
# spec.expected_codes → [200..299]
# spec.max_wait_s   → 30.0
```

---

## Extra Environment Variables

Inject arbitrary env-vars into the boot script or subprocess:

```python
isolation = IsolationConfig(
    port=8001,
    extra_env={
        "FEATURE_FLAG_PAYMENTS": "false",
        "LOG_LEVEL": "debug",
    },
)
```

---

## Reference: `BootConfig` Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `worktree_id` | `str` | — | Short ID for this worktree (task-UUID prefix or branch slug). Used in log prefixes, schema names, and file paths. |
| `start_command` | `str \| list[str]` | — | Shell command or argv list to launch the app. |
| `isolation` | `IsolationConfig` | `IsolationConfig()` | Port and DB isolation settings. |
| `health_path` | `str` | `"/health"` | URL path of the health endpoint. |
| `health_method` | `HealthCheckMethod` | `GET` | HTTP method for health probes. |
| `health_timeout_s` | `float` | `30.0` | Max seconds to wait before declaring boot failed. |
| `health_interval_s` | `float` | `1.0` | Seconds between health probe attempts. |
| `working_dir` | `str` | `""` | Working directory for the subprocess (empty = inherit). |
| `log_file` | `str` | `""` | Path to redirect app stdout/stderr (empty = inherit streams). |

## Reference: `BootResult` Fields

| Field | Type | Description |
|---|---|---|
| `worktree_id` | `str` | Mirrors `BootConfig.worktree_id`. |
| `pid` | `int` | PID of the launched process (0 on pre-launch failure). |
| `port` | `int` | Port the instance is bound to. |
| `health_url` | `str` | URL that was polled to confirm readiness. |
| `ready` | `bool` | `True` when health check passed within the timeout. |
| `elapsed_s` | `float` | Wall-clock seconds from start to health pass (or timeout). |
| `error` | `str` | Diagnostic message when `ready=False`; empty on success. |

---

## Key Files

| Path | Purpose |
|---|---|
| `harness_skills/boot.py` | All public API — `generate_boot_script`, `boot_instance`, `generate_health_check_spec`, data models. |
