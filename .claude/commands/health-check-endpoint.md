# Health Check Endpoint

Generate a spec-compliant `GET /health` endpoint for any harness-managed application.
Agents invoke this skill to scaffold the endpoint, validate an existing implementation
against the canonical JSON Schema, and verify that the harness boot poller can reach it.

Full specification: [`docs/health-check-endpoint-spec.md`](../../docs/health-check-endpoint-spec.md)
JSON Schema: [`harness_skills/schemas/health_check_response.schema.json`](../../harness_skills/schemas/health_check_response.schema.json)

---

## Instructions

### Step 1: Detect whether a health endpoint already exists

```bash
# Search for existing /health route registrations
grep -rn \
  --include='*.py' --include='*.ts' --include='*.js' --include='*.go' \
  -E '["'"'"'](/health|/healthz|/healthcheck)["'"'"']|route.*health|health.*route' \
  . 2>/dev/null | grep -v '__pycache__' | grep -v '.pyc'
```

Parse the output:
- **Matches found** → proceed to **Step 2** (validate the existing endpoint).
- **No matches** → proceed to **Step 3** (generate a new endpoint).

---

### Step 2: Validate the existing endpoint against the JSON Schema

#### 2a — Start the app (if not already running)

Check whether the app is already listening:

```bash
PORT="${PORT:-8000}"
curl -s -o /dev/null -w "%{http_code}" --max-time 3 "http://localhost:${PORT}/health" 2>/dev/null || echo "NOT_RUNNING"
```

If the app is not running, boot it with the harness before continuing:

```python
from harness_skills.boot import BootConfig, IsolationConfig, boot_instance

cfg = BootConfig(
    worktree_id=__import__('os').getenv("HARNESS_WORKTREE_ID", "local"),
    start_command="<fill-in your app start command>",
    isolation=IsolationConfig(port=int(__import__('os').getenv("PORT", "8000"))),
    health_path="/health",
    health_timeout_s=30.0,
)
result = boot_instance(cfg)
print(f"ready={result.ready}  pid={result.pid}  error={result.error!r}")
```

#### 2b — Fetch and validate the response

```bash
PORT="${PORT:-8000}"
RESPONSE=$(curl -sf --max-time 5 "http://localhost:${PORT}/health" 2>/dev/null)
echo "$RESPONSE" | python3 -c "
import json, sys, pathlib

schema_path = pathlib.Path('harness_skills/schemas/health_check_response.schema.json')
response    = json.load(sys.stdin)

# Basic field presence checks (jsonschema not always available)
required = {'status', 'timestamp'}
missing  = required - response.keys()
if missing:
    print('FAIL: missing required fields:', missing)
    sys.exit(1)

if response['status'] not in ('healthy', 'degraded', 'unhealthy'):
    print('FAIL: status must be healthy | degraded | unhealthy, got:', response['status'])
    sys.exit(1)

print('OK: status =', response.get('status'))
print('OK: timestamp =', response.get('timestamp'))
print('OK: checks =', len(response.get('checks', [])), 'entries')

# Richer validation when jsonschema is installed
try:
    import jsonschema
    schema = json.loads(schema_path.read_text())
    jsonschema.validate(response, schema)
    print('OK: jsonschema validation passed')
except ImportError:
    print('INFO: install jsonschema for full schema validation')
except jsonschema.ValidationError as exc:
    print('FAIL:', exc.message)
    sys.exit(1)
"
```

If the validation **passes**, print a confirmation card (see Step 5) and stop.
If it **fails**, proceed to Step 3 to regenerate the endpoint.

---

### Step 3: Detect the app framework

```bash
# Python frameworks
grep -rn --include='*.py' -l \
  'fastapi\|flask\|django\|starlette\|aiohttp\|tornado\|sanic' \
  . 2>/dev/null | grep -v '__pycache__' | head -5

# Node/TypeScript frameworks
grep -rn --include='*.ts' --include='*.js' -l \
  'express\|fastify\|koa\|hapi\|next/server' \
  . 2>/dev/null | grep -v 'node_modules' | head -5
```

Use the first result to determine the target framework:
- `fastapi` / `starlette` → **FastAPI**
- `flask` → **Flask**
- `django` → **Django**
- `express` → **Express (TypeScript)**
- Nothing found → **FastAPI** (default for new harness projects)

---

### Step 4: Generate the endpoint file

Write the file most appropriate for the detected framework.  The examples below are
canonical starting points — adapt the import paths to match the project's module layout.

#### FastAPI (default)

Write to `<app_module>/routes/health.py` (create parent dirs as needed):

```python
# <app_module>/routes/health.py
"""Health check endpoint — harness-compatible.

Spec: docs/health-check-endpoint-spec.md
Schema: harness_skills/schemas/health_check_response.schema.json
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

_START_TIME = time.monotonic()


@router.get("/health", tags=["ops"])
@router.head("/health", tags=["ops"])
async def health() -> JSONResponse:
    """Return the instance health status.

    HTTP 200 → healthy or degraded (boot confirmed, harness may send traffic).
    HTTP 503 → unhealthy (harness must not send traffic).
    """
    checks: list[dict] = []
    overall = "healthy"

    # ── database check (example — replace or remove as needed) ────────────────
    # try:
    #     from <app_module>.db import engine          # noqa: PLC0415
    #     import time as _t
    #     t0 = _t.monotonic()
    #     async with engine.connect() as conn:
    #         await conn.execute("SELECT 1")
    #     checks.append({
    #         "name": "database", "status": "pass",
    #         "latency_ms": int((_t.monotonic() - t0) * 1000),
    #         "message": None, "error_code": None,
    #     })
    # except Exception as exc:                         # noqa: BLE001
    #     checks.append({
    #         "name": "database", "status": "fail",
    #         "latency_ms": None,
    #         "message": str(exc),
    #         "error_code": "DB_CONNECTION_REFUSED",
    #     })
    #     overall = "unhealthy"

    body = {
        "status": overall,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": os.getenv("GIT_SHA"),
        "uptime_s": round(time.monotonic() - _START_TIME, 1),
        "checks": checks,
        "instance": {
            "worktree_id": os.getenv("HARNESS_WORKTREE_ID"),
            "port": int(os.getenv("PORT", "8000")),
            "pid": os.getpid(),
            "git_sha": os.getenv("GIT_SHA"),
            "git_branch": os.getenv("GIT_BRANCH"),
            "db_schema": os.getenv("DB_SCHEMA") or os.getenv("DATABASE_URL"),
            "environment": os.getenv("APP_ENV", "unknown"),
        },
    }
    http_status = 200 if overall in ("healthy", "degraded") else 503
    return JSONResponse(content=body, status_code=http_status)
```

Then register the router in the app factory.  Find the factory file:

```bash
grep -rn --include='*.py' -l 'FastAPI()\|app = FastAPI' . 2>/dev/null | grep -v '__pycache__' | head -3
```

Add the import and `include_router` call:

```python
from <app_module>.routes.health import router as health_router
app.include_router(health_router)
```

---

#### Flask

Write to `<app_module>/routes/health.py`:

```python
# <app_module>/routes/health.py
"""Health check endpoint — harness-compatible."""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from flask import Blueprint, jsonify

health_bp = Blueprint("health", __name__)
_START = time.monotonic()


@health_bp.get("/health")
def health():
    body = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": os.getenv("GIT_SHA"),
        "uptime_s": round(time.monotonic() - _START, 1),
        "checks": [],
        "instance": {
            "worktree_id": os.getenv("HARNESS_WORKTREE_ID"),
            "port": int(os.getenv("PORT", "5000")),
            "pid": os.getpid(),
            "git_sha": os.getenv("GIT_SHA"),
            "git_branch": os.getenv("GIT_BRANCH"),
            "db_schema": os.getenv("DB_SCHEMA"),
            "environment": os.getenv("APP_ENV", "unknown"),
        },
    }
    return jsonify(body), 200
```

Register in the app factory:

```python
from <app_module>.routes.health import health_bp
app.register_blueprint(health_bp)
```

---

#### Django

Add to `<app_module>/views/health.py`:

```python
# <app_module>/views/health.py
"""Health check endpoint — harness-compatible."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

from django.http import HttpRequest, JsonResponse


_START = time.monotonic()


def health(request: HttpRequest) -> JsonResponse:
    body = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": os.getenv("GIT_SHA"),
        "uptime_s": round(time.monotonic() - _START, 1),
        "checks": [],
        "instance": {
            "worktree_id": os.getenv("HARNESS_WORKTREE_ID"),
            "port": int(os.getenv("PORT", "8000")),
            "pid": os.getpid(),
            "git_sha": os.getenv("GIT_SHA"),
            "git_branch": os.getenv("GIT_BRANCH"),
            "db_schema": os.getenv("DB_SCHEMA"),
            "environment": os.getenv("APP_ENV", "unknown"),
        },
    }
    return JsonResponse(body)
```

Wire into `urls.py`:

```python
from <app_module>.views.health import health
urlpatterns += [path("health", health)]
```

---

### Step 5: Verify and print the delivery card

After generating (or validating) the endpoint, confirm it responds correctly:

```bash
PORT="${PORT:-8000}"

# Restart the app with the new endpoint (if it was booted in Step 2a)
# — or start it fresh if running locally

HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 \
    "http://localhost:${PORT}/health" 2>/dev/null || echo "ERR")

BODY=$(curl -sf --max-time 5 "http://localhost:${PORT}/health" 2>/dev/null || echo "{}")

echo "HTTP status : $HTTP_STATUS"
echo "Body        : $BODY"

# HEAD probe
HEAD_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X HEAD --max-time 5 \
    "http://localhost:${PORT}/health" 2>/dev/null || echo "ERR")
echo "HEAD status : $HEAD_STATUS"
```

Expected: both `HTTP status` and `HEAD status` are `200`.

Print this delivery card on success:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  /health endpoint — ready
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Endpoint   : GET  http://localhost:<PORT>/health  → 200
               HEAD http://localhost:<PORT>/health  → 200
  Status     : <healthy|degraded|unhealthy>
  Checks     : <N> subsystem(s) reported
  Schema     : validated against health_check_response.schema.json

  BootConfig  (paste into harness_skills.boot.BootConfig)
  ├─ health_path    = "/health"
  ├─ health_method  = GET
  ├─ health_timeout_s = 30
  └─ health_interval_s = 1.0

  Implementation checklist
  ✅ GET /health returns HTTP 200 (healthy/degraded) or 503 (unhealthy)
  ✅ HEAD /health is supported
  ✅ Response body has required fields: status, timestamp
  ✅ instance.worktree_id populated from $HARNESS_WORKTREE_ID
  ✅ instance.port populated from $PORT
  ✅ Responds within 5 seconds

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Options

| Argument | Effect |
|---|---|
| `--port N` | Override the port used for probing (default: `$PORT` or `8000`) |
| `--path /healthz` | Use a non-default health path (default: `/health`) |
| `--framework fastapi\|flask\|django\|express` | Skip auto-detection and use this framework |
| `--skip-boot` | Do not start the app; assume it is already running |
| `--validate-only` | Only validate an existing endpoint; never write files |

---

## Standard `error_code` values

Use these in `CheckResult.error_code` for machine-readable remediation routing:

| Code | Meaning |
|---|---|
| `DB_CONNECTION_REFUSED` | Database TCP connection rejected |
| `DB_AUTH_FAILED` | Database authentication error |
| `MIGRATION_PENDING` | Unapplied migrations detected |
| `MIGRATION_FAILED` | Migration apply error |
| `REDIS_CONNECTION_REFUSED` | Redis TCP connection rejected |
| `REDIS_HIGH_LATENCY` | Redis latency above threshold |
| `DISK_FULL` | Disk usage above 95% |
| `EXTERNAL_API_UNREACHABLE` | Third-party API not responding |
| `PORT_CONFLICT` | Bound port already in use |

---

## Related

| Resource | Purpose |
|---|---|
| `docs/health-check-endpoint-spec.md` | Full specification (status semantics, all fields) |
| `harness_skills/schemas/health_check_response.schema.json` | JSON Schema for response validation |
| `harness_skills/boot.py` | `HealthCheckSpec`, `generate_health_check_spec()`, `boot_instance()` |
| `/harness:boot` skill | Boot an isolated instance and wait for health pass |
| `/harness:status` skill | Query running instance status from the CLI |
