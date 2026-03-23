# Health Check Endpoint Specification

> Version: 1.0.0
> Date: 2026-03-22
> Status: Canonical

---

## Overview

This document defines the standard health check endpoint contract that agents use to verify an application is running correctly. All services integrated with the agent harness **MUST** implement this specification.

---

## Endpoint

```
GET /health
```

### Optional Sub-Endpoints

| Endpoint         | Purpose                                      |
|------------------|----------------------------------------------|
| `GET /health`    | Overall health (liveness + readiness)        |
| `GET /health/live`   | Liveness — is the process alive?         |
| `GET /health/ready`  | Readiness — is the service ready to serve traffic? |
| `GET /health/startup` | Startup — has the service finished initializing? |

---

## Response Format

All responses **MUST** be `application/json`.

### Fields

| Field        | Type     | Required | Description |
|--------------|----------|----------|-------------|
| `status`     | `string` | Yes      | One of `"ok"`, `"degraded"`, `"down"` |
| `timestamp`  | `string` | Yes      | ISO-8601 UTC timestamp of the check |
| `version`    | `string` | Yes      | Application version (semver or git SHA) |
| `uptime_s`   | `number` | Yes      | Seconds since the process started |
| `checks`     | `object` | No       | Map of named dependency checks (see below) |
| `env`        | `string` | No       | Deployment environment: `production`, `staging`, `local` |

### `checks` Sub-Object (per dependency)

| Field      | Type     | Required | Description |
|------------|----------|----------|-------------|
| `status`   | `string` | Yes      | `"ok"`, `"degraded"`, or `"down"` |
| `latency_ms` | `number` | No    | Round-trip latency to the dependency in milliseconds |
| `error`    | `string` | No       | Human-readable error message if status is not `"ok"` |

---

## Status Semantics

| Status      | HTTP Code | Meaning |
|-------------|-----------|---------|
| `"ok"`      | `200`     | All systems nominal. Safe to route traffic. |
| `"degraded"` | `200`    | Service is alive but one or more non-critical dependencies are unhealthy. Traffic may be routed with caution. |
| `"down"`    | `503`     | Service is not healthy. Do not route traffic. Agents should retry. |

> **Rule:** The top-level `status` is the **worst-case** roll-up of all individual `checks`.

---

## Example Responses

### Healthy

```json
{
  "status": "ok",
  "timestamp": "2026-03-22T14:05:00Z",
  "version": "2.4.1",
  "uptime_s": 3600,
  "env": "production",
  "checks": {
    "database": {
      "status": "ok",
      "latency_ms": 3
    },
    "cache": {
      "status": "ok",
      "latency_ms": 1
    },
    "message_queue": {
      "status": "ok",
      "latency_ms": 12
    }
  }
}
```

### Degraded

```json
{
  "status": "degraded",
  "timestamp": "2026-03-22T14:05:00Z",
  "version": "2.4.1",
  "uptime_s": 120,
  "env": "staging",
  "checks": {
    "database": {
      "status": "ok",
      "latency_ms": 4
    },
    "cache": {
      "status": "degraded",
      "latency_ms": 850,
      "error": "Cache latency exceeds 500 ms threshold"
    }
  }
}
```

### Down

```json
{
  "status": "down",
  "timestamp": "2026-03-22T14:05:00Z",
  "version": "2.4.1",
  "uptime_s": 5,
  "env": "production",
  "checks": {
    "database": {
      "status": "down",
      "error": "Connection refused: postgres:5432"
    }
  }
}
```

---

## HTTP Headers

Responses **MUST** include:

```
Content-Type: application/json
Cache-Control: no-store
```

Authentication **MUST NOT** be required on `/health`. The endpoint must be publicly reachable by agents and load balancers.

---

## Agent Polling Protocol

Agents poll the health endpoint following this protocol:

### Poll Parameters

| Parameter         | Default  | Description |
|-------------------|----------|-------------|
| `interval_s`      | `10`     | Seconds between polls during normal operation |
| `timeout_s`       | `5`      | HTTP request timeout per poll |
| `failure_threshold` | `3`    | Consecutive failures before marking the service `down` |
| `success_threshold` | `1`    | Consecutive successes to return from `down` to `ok` |
| `backoff_max_s`   | `60`     | Maximum backoff interval during failure retries |

### State Machine

```
          success
 [UNKNOWN] ──────► [HEALTHY]
                       │
              failure  │  failure x failure_threshold
                       ▼
                  [UNHEALTHY] ──► alert / escalation
                       │
              success x success_threshold
                       │
                       ▼
                  [HEALTHY]
```

### Retry Back-off (Exponential)

```
wait = min(interval_s * 2^(attempt - 1), backoff_max_s)
```

---

## Implementation Examples

### Python (FastAPI)

```python
import time
from datetime import datetime, timezone
from fastapi import FastAPI, Response

app = FastAPI()
_START = time.monotonic()

@app.get("/health")
async def health(response: Response):
    db_ok = await check_database()
    cache_ok = await check_cache()

    checks = {
        "database": {"status": "ok" if db_ok else "down"},
        "cache":    {"status": "ok" if cache_ok else "degraded"},
    }

    overall = (
        "ok"       if all(c["status"] == "ok" for c in checks.values()) else
        "degraded" if all(c["status"] != "down" for c in checks.values()) else
        "down"
    )

    if overall == "down":
        response.status_code = 503

    return {
        "status":    overall,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version":   "1.0.0",
        "uptime_s":  round(time.monotonic() - _START),
        "env":       "production",
        "checks":    checks,
    }
```

### TypeScript (Express)

```typescript
import express, { Request, Response } from "express";

const app = express();
const START = Date.now();

app.get("/health", async (_req: Request, res: Response) => {
  const [dbOk, cacheOk] = await Promise.all([checkDb(), checkCache()]);

  const checks = {
    database: { status: dbOk    ? "ok" : "down" },
    cache:    { status: cacheOk ? "ok" : "degraded" },
  };

  const statuses = Object.values(checks).map((c) => c.status);
  const overall  = statuses.includes("down")     ? "down"
                 : statuses.includes("degraded") ? "degraded"
                 :                                 "ok";

  res
    .status(overall === "down" ? 503 : 200)
    .set("Cache-Control", "no-store")
    .json({
      status:    overall,
      timestamp: new Date().toISOString(),
      version:   process.env.APP_VERSION ?? "unknown",
      uptime_s:  Math.floor((Date.now() - START) / 1000),
      env:       process.env.NODE_ENV ?? "local",
      checks,
    });
});
```

### Go (net/http)

```go
package main

import (
    "encoding/json"
    "net/http"
    "time"
)

var startTime = time.Now()

func healthHandler(w http.ResponseWriter, r *http.Request) {
    dbOk    := checkDatabase()
    cacheOk := checkCache()

    checks := map[string]map[string]string{
        "database": {"status": statusStr(dbOk)},
        "cache":    {"status": statusStr(cacheOk)},
    }

    overall := "ok"
    for _, c := range checks {
        if c["status"] == "down"     { overall = "down";     break }
        if c["status"] == "degraded" { overall = "degraded" }
    }

    code := http.StatusOK
    if overall == "down" { code = http.StatusServiceUnavailable }

    w.Header().Set("Content-Type", "application/json")
    w.Header().Set("Cache-Control", "no-store")
    w.WriteHeader(code)
    json.NewEncoder(w).Encode(map[string]any{
        "status":    overall,
        "timestamp": time.Now().UTC().Format(time.RFC3339),
        "version":   "1.0.0",
        "uptime_s":  int(time.Since(startTime).Seconds()),
        "checks":    checks,
    })
}
```

---

## JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.com/health-check.schema.json",
  "title": "HealthCheckResponse",
  "type": "object",
  "required": ["status", "timestamp", "version", "uptime_s"],
  "properties": {
    "status":    { "type": "string", "enum": ["ok", "degraded", "down"] },
    "timestamp": { "type": "string", "format": "date-time" },
    "version":   { "type": "string" },
    "uptime_s":  { "type": "number", "minimum": 0 },
    "env":       { "type": "string" },
    "checks": {
      "type": "object",
      "additionalProperties": {
        "type": "object",
        "required": ["status"],
        "properties": {
          "status":     { "type": "string", "enum": ["ok", "degraded", "down"] },
          "latency_ms": { "type": "number", "minimum": 0 },
          "error":      { "type": "string" }
        }
      }
    }
  }
}
```

---

## Compliance Checklist

- [ ] `GET /health` returns JSON with all required fields
- [ ] `status` is one of `"ok"`, `"degraded"`, `"down"`
- [ ] HTTP `503` returned when `status == "down"`
- [ ] `Cache-Control: no-store` header present
- [ ] No authentication required on `/health`
- [ ] `timestamp` is ISO-8601 UTC
- [ ] Endpoint responds within 5 seconds
- [ ] Dependency checks are included under `checks`
- [ ] Top-level `status` reflects worst-case dependency status

---

## Related Documents

- Logging Convention: `SPEC.md`
- CI Pipeline: `.github/workflows/`
- Harness Context: `/harness:context`

<!-- harness:cross-links — do not edit this block manually -->

---

## Related Documents

| Document | Relationship |
|---|---|
| [SPEC.md](SPEC.md) | logging convention (observability peer) |
| [AGENTS.md](../AGENTS.md) | agents poll the health endpoint |
| [health-check-endpoint-spec.md](health-check-endpoint-spec.md) | extended spec with ADR context |
| [.claude/commands/health-check-endpoint.md](../.claude/commands/health-check-endpoint.md) | skill that generated this file |
| [.claude/commands/harness/observe.md](../.claude/commands/harness/observe.md) | log observation for health events |
| [DOCS_INDEX.md](../DOCS_INDEX.md) | full documentation index |

<!-- /harness:cross-links -->
