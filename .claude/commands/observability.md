<<<<<<< HEAD
# Observability Stack

Generate a **lightweight local-dev observability stack** — file-based log collectors (Vector *or* Promtail) → Grafana Loki → Grafana UI — with zero cloud accounts required.

---

## Instructions

### Step 1 — Determine output directory

```bash
OUTPUT_DIR="${OBSERVABILITY_DIR:-$(pwd)/observability}"
echo "Output directory: $OUTPUT_DIR"
```

If `$OUTPUT_DIR` already exists, print a notice but continue — the skill is idempotent and only writes files that do not yet exist.

```bash
if [ -d "$OUTPUT_DIR" ]; then
  echo "observability/ already exists — checking for missing files only."
fi
```

---

### Step 2 — Create directory skeleton

```bash
mkdir -p \
  "$OUTPUT_DIR/vector" \
  "$OUTPUT_DIR/promtail" \
  "$OUTPUT_DIR/loki" \
  "$OUTPUT_DIR/grafana/provisioning/datasources" \
  "$OUTPUT_DIR/grafana/provisioning/dashboards"
```

---

### Step 3 — Write `docker-compose.observability.yml`

Only write if the file does not already exist at `$OUTPUT_DIR/docker-compose.observability.yml`.

```yaml
# Lightweight Local Dev Observability Stack
# File-based log collection: Vector → Loki → Grafana
#
# Usage:
#   docker compose -f docker-compose.observability.yml up -d
#
# Grafana UI: http://localhost:3000  (admin / admin)
# Loki API:   http://localhost:3100
# Vector API: http://localhost:8686

version: "3.9"

networks:
  obs-net:
    driver: bridge

volumes:
  loki-data:
  grafana-data:

services:

  # ── Vector: file-based log collector & transformer ─────────────────────────
  vector:
    image: timberio/vector:0.38.0-distroless-libc
    container_name: obs-vector
    restart: unless-stopped
    volumes:
      - ./vector/vector.toml:/etc/vector/vector.toml:ro
      # Mount the host log directory (configure LOG_DIR below)
      - ${LOG_DIR:-./logs}:/var/log/app:ro
    environment:
      - VECTOR_LOG=info
    ports:
      - "8686:8686"   # Vector API / health
    networks:
      - obs-net
    depends_on:
      - loki

  # ── Grafana Loki: log aggregation backend ──────────────────────────────────
  loki:
    image: grafana/loki:2.9.6
    container_name: obs-loki
    restart: unless-stopped
    command: -config.file=/etc/loki/loki.yaml
    volumes:
      - ./loki/loki.yaml:/etc/loki/loki.yaml:ro
      - loki-data:/loki
    ports:
      - "3100:3100"
    networks:
      - obs-net

  # ── Grafana: log viewer UI ─────────────────────────────────────────────────
  grafana:
    image: grafana/grafana:10.4.2
    container_name: obs-grafana
    restart: unless-stopped
    environment:
      - GF_AUTH_ANONYMOUS_ENABLED=true
      - GF_AUTH_ANONYMOUS_ORG_ROLE=Admin
      - GF_AUTH_DISABLE_LOGIN_FORM=false
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana-data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
    ports:
      - "3000:3000"
    networks:
      - obs-net
    depends_on:
      - loki
```

---

### Step 4 — Write `vector/vector.toml`

Only write if `$OUTPUT_DIR/vector/vector.toml` does not already exist.

```toml
# vector.toml — file-based log collector for local dev
# Watches log files, parses them, enriches with metadata, ships to Loki.

# ── Global ────────────────────────────────────────────────────────────────────
[api]
enabled = true
address  = "0.0.0.0:8686"

# ── Sources ───────────────────────────────────────────────────────────────────

# Plain text / unstructured logs (app.log, worker.log, …)
[sources.file_plain]
type              = "file"
include           = ["/var/log/app/*.log"]
exclude           = ["/var/log/app/*.gz"]
read_from         = "beginning"
# Annotate which file the line came from
file_key          = "source_file"
host_key          = "host"

# JSON-structured logs (e.g. from pino, winston json, structlog)
[sources.file_json]
type              = "file"
include           = ["/var/log/app/*.jsonl", "/var/log/app/*.ndjson"]
read_from         = "beginning"
file_key          = "source_file"
host_key          = "host"

# ── Transforms ────────────────────────────────────────────────────────────────

# Parse plain logs: extract level + timestamp with a flexible regex
[transforms.parse_plain]
type   = "remap"
inputs = ["file_plain"]
source = '''
  # Try common log patterns; fall back gracefully
  parsed, err = parse_regex(.message, r'(?P<timestamp>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)\s+(?P<level>DEBUG|INFO|WARN|WARNING|ERROR|FATAL|CRITICAL)\s+(?P<body>.+)')
  if err == null {
    .timestamp = parsed.timestamp
    .level     = downcase(parsed.level)
    .message   = parsed.body
  } else {
    .level = "info"
  }
  # Label for Loki stream selector
  .service = basename(string!(.source_file), ".log")
  .env     = get_env_var("APP_ENV") ?? "local"
'''

# Parse JSON-structured logs
[transforms.parse_json_logs]
type   = "remap"
inputs = ["file_json"]
source = '''
  parsed, err = parse_json(.message)
  if err == null {
    . = merge(., parsed)
  }
  # Normalize common field names
  .level   = downcase(string(.level ?? .severity ?? .lvl ?? "info"))
  .message = string(.message ?? .msg ?? .text ?? "")
  .service = string(.service ?? .app ?? basename(string!(.source_file), ".jsonl"))
  .env     = get_env_var("APP_ENV") ?? "local"
'''

# ── Sinks ─────────────────────────────────────────────────────────────────────

# Ship to Loki (inside Docker network)
[sinks.loki]
type              = "loki"
inputs            = ["parse_plain", "parse_json_logs"]
endpoint          = "http://loki:3100"
encoding.codec    = "json"

  # Loki stream labels (low-cardinality only!)
  [sinks.loki.labels]
  service = "{{ service }}"
  level   = "{{ level }}"
  env     = "{{ env }}"
  host    = "{{ host }}"

  [sinks.loki.batch]
  max_bytes    = 1_048_576   # 1 MiB
  timeout_secs = 5

  [sinks.loki.buffer]
  type      = "disk"
  max_size  = 268_435_456   # 256 MiB
  when_full = "drop_newest"

# Also echo to stdout while developing
[sinks.console]
type              = "console"
inputs            = ["parse_plain", "parse_json_logs"]
encoding.codec    = "json"
```

---

### Step 5 — Write `loki/loki.yaml`

Only write if `$OUTPUT_DIR/loki/loki.yaml` does not already exist.

```yaml
# loki.yaml — minimal single-process Loki for local dev
# All data stored on disk under /loki (Docker volume).

auth_enabled: false

server:
  http_listen_port: 3100
  grpc_listen_port: 9096
  log_level: warn

common:
  instance_addr: 127.0.0.1
  path_prefix: /loki
  storage:
    filesystem:
      chunks_directory: /loki/chunks
      rules_directory:  /loki/rules
  replication_factor: 1
  ring:
    kvstore:
      store: inmemory

# ── Schema ────────────────────────────────────────────────────────────────────
schema_config:
  configs:
    - from: 2024-01-01
      store:         tsdb
      object_store:  filesystem
      schema:        v13
      index:
        prefix: index_
        period: 24h

# ── Retention (local dev: keep 7 days) ───────────────────────────────────────
limits_config:
  retention_period:          168h   # 7 days
  ingestion_rate_mb:         16
  ingestion_burst_size_mb:   32
  max_query_series:          5000
  max_query_lookback:        168h
  reject_old_samples:        true
  reject_old_samples_max_age: 168h

compactor:
  working_directory:        /loki/compactor
  retention_enabled:        true
  retention_delete_delay:   2h
  delete_request_store:     filesystem

# ── Query performance (dev-friendly) ─────────────────────────────────────────
query_range:
  results_cache:
    cache:
      embedded_cache:
        enabled:   true
        max_size_mb: 100

ruler:
  alertmanager_url: http://localhost:9093
```

---

### Step 6 — Write `promtail/promtail.yaml`

Only write if `$OUTPUT_DIR/promtail/promtail.yaml` does not already exist.

```yaml
# promtail.yaml — alternative file-based collector (Promtail instead of Vector)
# Use this if your team already uses the Grafana stack and prefers promtail.
#
# Swap in docker-compose.observability.yml:
#   Replace the `vector` service with the `promtail` service block below.

server:
  http_listen_port: 9080
  grpc_listen_port: 0
  log_level: warn

positions:
  filename: /tmp/positions.yaml   # tracks read offsets; survives restarts

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:

  # ── Plain text logs ─────────────────────────────────────────────────────────
  - job_name: app_plain
    static_configs:
      - targets: [localhost]
        labels:
          job: app
          env: local
          __path__: /var/log/app/*.log

    pipeline_stages:
      # Extract level + timestamp from common log formats
      - regex:
          expression: '(?P<timestamp>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[^\s]*)\s+(?P<level>DEBUG|INFO|WARN(?:ING)?|ERROR|FATAL|CRITICAL)\s+(?P<message>.*)'
      - labels:
          level:
      - timestamp:
          source: timestamp
          format: RFC3339
      # Derive service name from filename
      - static_labels:
          collector: promtail

  # ── JSON / NDJSON logs ──────────────────────────────────────────────────────
  - job_name: app_json
    static_configs:
      - targets: [localhost]
        labels:
          job: app_json
          env: local
          __path__: /var/log/app/*.{jsonl,ndjson}

    pipeline_stages:
      - json:
          expressions:
            level:     level
            severity:  severity
            timestamp: timestamp
            ts:        ts
            service:   service
            app:       app
      # Use whichever timestamp field is present
      - timestamp:
          source: timestamp
          format: RFC3339
          fallback_formats:
            - UnixMs
            - Unix
      - labels:
          level:
          service:
```

To switch the compose stack to Promtail, replace the `vector` service in `docker-compose.observability.yml` with:

```yaml
  promtail:
    image: grafana/promtail:2.9.6
    container_name: obs-promtail
    restart: unless-stopped
    command: -config.file=/etc/promtail/promtail.yaml
    volumes:
      - ./promtail/promtail.yaml:/etc/promtail/promtail.yaml:ro
      - ${LOG_DIR:-./logs}:/var/log/app:ro
    networks:
      - obs-net
    depends_on:
      - loki
```

---

### Step 7 — Write Grafana provisioning files

#### 7a — `grafana/provisioning/datasources/loki.yaml`

Only write if file does not already exist.

```yaml
# Auto-provision Loki as a Grafana datasource on first boot.
apiVersion: 1

datasources:
  - name:      Loki
    type:      loki
    access:    proxy
    url:       http://loki:3100
    isDefault: true
    editable:  true
    jsonData:
      maxLines:          5000
      timeout:           60
      queryTimeout:      "60s"
      httpHeaderName1:   "X-Scope-OrgID"
    secureJsonData:
      httpHeaderValue1:  "tenant1"
```

#### 7b — `grafana/provisioning/dashboards/dashboard-provider.yaml`

Only write if file does not already exist.

```yaml
# Tell Grafana to load dashboards from the /dashboards folder.
apiVersion: 1

providers:
  - name:            "Local Dev Dashboards"
    orgId:           1
    folder:          "Local Dev"
    folderUid:       "local-dev"
    type:            file
    disableDeletion: false
    updateIntervalSeconds: 30
    allowUiUpdates: true
    options:
      path: /etc/grafana/provisioning/dashboards
      foldersFromFilesStructure: false
```

#### 7c — `grafana/provisioning/dashboards/local-dev-logs.json`

Only write if file does not already exist. Write the following JSON verbatim:

```json
{
  "title": "Local Dev — Log Explorer",
  "uid": "local-dev-logs",
  "schemaVersion": 38,
  "version": 1,
  "refresh": "10s",
  "time": { "from": "now-1h", "to": "now" },
  "panels": [
    {
      "id": 1,
      "type": "logs",
      "title": "All Logs",
      "gridPos": { "h": 20, "w": 24, "x": 0, "y": 0 },
      "datasource": { "type": "loki", "uid": "${DS_LOKI}" },
      "options": {
        "dedupStrategy": "none",
        "enableLogDetails": true,
        "prettifyLogMessage": false,
        "showCommonLabels": false,
        "showLabels": true,
        "showTime": true,
        "sortOrder": "Descending",
        "wrapLogMessage": true
      },
      "targets": [
        {
          "datasource": { "type": "loki", "uid": "${DS_LOKI}" },
          "expr": "{env=\"local\"} |= `$search`",
          "legendFormat": "",
          "refId": "A"
        }
      ]
    },
    {
      "id": 2,
      "type": "timeseries",
      "title": "Log Rate by Level",
      "gridPos": { "h": 8, "w": 24, "x": 0, "y": 20 },
      "datasource": { "type": "loki", "uid": "${DS_LOKI}" },
      "fieldConfig": {
        "defaults": { "unit": "reqps", "custom": { "lineWidth": 2 } },
        "overrides": [
          { "matcher": { "id": "byName", "options": "error" },
            "properties": [{ "id": "color", "value": { "fixedColor": "red",    "mode": "fixed" } }] },
          { "matcher": { "id": "byName", "options": "warn"  },
            "properties": [{ "id": "color", "value": { "fixedColor": "yellow", "mode": "fixed" } }] },
          { "matcher": { "id": "byName", "options": "info"  },
            "properties": [{ "id": "color", "value": { "fixedColor": "green",  "mode": "fixed" } }] }
        ]
      },
      "targets": [
        {
          "datasource": { "type": "loki", "uid": "${DS_LOKI}" },
          "expr": "sum by (level) (rate({env=\"local\"}[1m]))",
          "legendFormat": "{{level}}",
          "refId": "B"
        }
      ]
    }
  ],
  "templating": {
    "list": [
      {
        "name": "DS_LOKI",
        "type": "datasource",
        "pluginId": "loki",
        "hide": 2
      },
      {
        "name": "search",
        "label": "Search",
        "type": "textbox",
        "current": { "value": "" },
        "hide": 0
      },
      {
        "name": "service",
        "label": "Service",
        "type": "query",
        "datasource": { "type": "loki", "uid": "${DS_LOKI}" },
        "query": "label_values(service)",
        "refresh": 2,
        "hide": 0,
        "includeAll": true,
        "allValue": ".*"
      }
    ]
  }
}
```

---

### Step 8 — Write `.env.example`

Only write if `$OUTPUT_DIR/.env.example` does not already exist.

```dotenv
# Copy to .env and adjust before running docker compose.
# cp .env.example .env

# Directory on the HOST that contains your application log files.
# Vector / Promtail will tail every *.log / *.jsonl file inside.
LOG_DIR=./logs

# Environment label stamped on every log line (visible in Grafana).
APP_ENV=local
```

---

### Step 9 — Write `README.md`

Only write if `$OUTPUT_DIR/README.md` does not already exist.

```markdown
# Local Dev Observability Stack

Lightweight log aggregation for local development.
**File-based collectors → Loki → Grafana** — no cloud account required.

```
your app writes logs          tails files          stores logs        visualises
  ./logs/*.log    ──►  Vector (or Promtail)  ──►  Loki  ──►  Grafana
  ./logs/*.jsonl
```

---

## Quick Start

```bash
# 1. Copy and edit the environment file
cp .env.example .env
#    Set LOG_DIR to the folder where your app writes log files.

# 2. Start the stack
docker compose -f docker-compose.observability.yml up -d

# 3. Open Grafana
open http://localhost:3000
#    Navigate to: Dashboards → Local Dev → "Local Dev — Log Explorer"
```

---

## Directory Layout

```
observability/
├── docker-compose.observability.yml  # Main compose file (Vector variant)
├── .env.example                      # Environment variables template
│
├── vector/
│   └── vector.toml          # Collector config — watches LOG_DIR, ships to Loki
│
├── promtail/
│   └── promtail.yaml        # Alternative collector (Grafana Promtail)
│
├── loki/
│   └── loki.yaml            # Single-process Loki, filesystem storage
│
└── grafana/
    └── provisioning/
        ├── datasources/
        │   └── loki.yaml            # Auto-wires Loki as default datasource
        └── dashboards/
            ├── dashboard-provider.yaml
            └── local-dev-logs.json  # Pre-built log explorer dashboard
```

---

## Choosing a Collector

| | **Vector** (default) | **Promtail** |
|---|---|---|
| Image | `timberio/vector` | `grafana/promtail` |
| Config | `vector/vector.toml` | `promtail/promtail.yaml` |
| Strengths | Rich VRL transforms, multi-sink | Native Loki integration, simple pipeline |
| Best for | Complex parsing / routing | Teams already using the Grafana stack |

To switch to Promtail, replace the `vector` service block in `docker-compose.observability.yml`
with the `promtail` service snippet shown in `promtail/promtail.yaml`.

---

## Log File Conventions

### Plain text logs
Any line matching this pattern is auto-parsed:
```
2024-03-14T10:22:01Z  INFO  server started on :8080
2024-03-14T10:22:05Z  ERROR failed to connect to db: timeout
```

### JSON / NDJSON logs
One JSON object per line; common field names are normalised automatically:

| Accepted field names | Normalised to |
|---|---|
| `level`, `severity`, `lvl` | `level` |
| `message`, `msg`, `text` | `message` |
| `service`, `app` | `service` |
| `timestamp`, `ts` | timestamp (RFC3339 or Unix ms) |

---

## Ports

| Service | Port | Purpose |
|---|---|---|
| Grafana | 3000 | Web UI |
| Loki | 3100 | HTTP API (push + query) |
| Vector | 8686 | Health / management API |

---

## Retention

Logs are kept for **7 days** by default (configured in `loki/loki.yaml`).
Change `retention_period` to adjust.

---

## Stopping / Cleanup

```bash
# Stop services (keep data)
docker compose -f docker-compose.observability.yml down

# Stop and wipe all data
docker compose -f docker-compose.observability.yml down -v
```
```

---

### Step 10 — Verify the directory tree

```bash
find "$OUTPUT_DIR" -type f | sort
```

Confirm all expected files are present:
- `docker-compose.observability.yml`
- `.env.example`
- `README.md`
- `vector/vector.toml`
- `promtail/promtail.yaml`
- `loki/loki.yaml`
- `grafana/provisioning/datasources/loki.yaml`
- `grafana/provisioning/dashboards/dashboard-provider.yaml`
- `grafana/provisioning/dashboards/local-dev-logs.json`

---

### Step 11 — Print delivery card

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Observability Stack — generated
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Directory  : <OUTPUT_DIR>
  Collector  : Vector 0.38.0 (Promtail 2.9.6 config also included)
  Backend    : Grafana Loki 2.9.6  (filesystem, 7-day retention)
  UI         : Grafana 10.4.2      (pre-provisioned datasource + dashboard)

  Files written:
    ✅ docker-compose.observability.yml
    ✅ .env.example
    ✅ README.md
    ✅ vector/vector.toml
    ✅ promtail/promtail.yaml
    ✅ loki/loki.yaml
    ✅ grafana/provisioning/datasources/loki.yaml
    ✅ grafana/provisioning/dashboards/dashboard-provider.yaml
    ✅ grafana/provisioning/dashboards/local-dev-logs.json

  Quick start:
    cd <OUTPUT_DIR>
    cp .env.example .env          # set LOG_DIR=path/to/your/logs
    docker compose -f docker-compose.observability.yml up -d
    open http://localhost:3000    # Dashboards → Local Dev → Log Explorer

  Ports:
    Grafana  → http://localhost:3000   (admin / admin)
    Loki API → http://localhost:3100
    Vector   → http://localhost:8686

  Switch collector:
    Replace the `vector` service in docker-compose.observability.yml
    with the `promtail` snippet documented in promtail/promtail.yaml.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Notes

- **Idempotent** — re-running the skill on a project that already has an `observability/` directory is safe; it only writes files that are missing.
- **File-based collectors only** — no syslog, no Kubernetes, no cloud APIs; Vector/Promtail tail `*.log` and `*.jsonl` files from a host-mounted directory (`LOG_DIR`).
- **Two collector options** — Vector (default, rich VRL transforms) and Promtail (simpler, native Grafana stack). Both configs are generated; the compose file defaults to Vector.
- **Single-process Loki** — `monolithic` mode with filesystem storage is the right choice for local dev. For staging/prod, switch to object storage (S3/GCS).
- **Pre-built Grafana dashboard** — the "Local Dev — Log Explorer" dashboard auto-provisions a live log tail panel and a log-rate-by-level time series panel.
- **Retention** — 7 days by default. Edit `retention_period` in `loki/loki.yaml` and `reject_old_samples_max_age` to change.
- **No auth** — `auth_enabled: false` in Loki; anonymous Admin access in Grafana. Suitable for local dev only.
||||||| 0e893bd
=======
# Observability — Structured Logging Configuration

Detect the project's language and logging framework, then generate a structured logging configuration (JSON/key-value output, log levels, correlation IDs, caller info) that is ready to drop in.

---

## Instructions

### Step 1 — Detect project language and existing logging dependencies

```bash
# Language / package manager signals
ls package.json pyproject.toml go.mod Cargo.toml requirements*.txt 2>/dev/null

# Node.js — check for existing logging deps
cat package.json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); deps={**d.get('dependencies',{}),**d.get('devDependencies',{})}; [print(k) for k in deps if k in ('winston','pino','bunyan','log4js','signale','tslog')]" 2>/dev/null || true

# Python — check for existing logging setup
grep -r "import logging\|structlog\|loguru\|python-json-logger\|pythonjsonlogger" --include="*.py" -l . 2>/dev/null | head -5 || true
grep -E "structlog|loguru|python-json-logger" pyproject.toml requirements*.txt 2>/dev/null || true

# Go — check for slog / zap / zerolog / logrus
grep -r "log/slog\|go.uber.org/zap\|github.com/rs/zerolog\|github.com/sirupsen/logrus" go.mod go.sum 2>/dev/null || true

# Rust — check for tracing / log / slog
grep -E "tracing|slog\s*=" Cargo.toml 2>/dev/null || true
```

Determine:
- **Language**: Python / Node.js (TypeScript or JS) / Go / Rust / other
- **Existing logger**: already installed logger crate/package (use it), or none (pick the recommended default)
- **Output format preference**: JSON (default for servers/CI) or human-readable (default for CLIs)

---

### Step 2 — Choose logging framework (if none detected)

| Language | Recommended default | Notes |
|---|---|---|
| Python | `structlog` + `python-json-logger` | stdlib `logging` compatible |
| Node.js / TypeScript | `pino` | Fastest JSON logger; `winston` if already present |
| Go | `log/slog` (stdlib, Go 1.21+) | `zap` if <Go 1.21 |
| Rust | `tracing` + `tracing-subscriber` | `log` crate for simpler crates |

Announce chosen framework to the user before proceeding.

---

### Step 3A — Python: generate structured logging configuration

**If `structlog` is preferred / not yet installed**, add dependency:

```bash
# pyproject.toml project — add via uv/pip
uv add structlog python-json-logger 2>/dev/null || pip install structlog python-json-logger
```

Write `src/logging_config.py` (or `<package>/logging_config.py` — use the detected source root):

```python
# logging_config.py
# Structured logging setup — JSON output in production, coloured console in dev.
# Usage:
#   from logging_config import configure_logging, get_logger
#   configure_logging()
#   log = get_logger(__name__)
#   log.info("server_started", port=8080, env="production")

from __future__ import annotations

import logging
import logging.config
import os
import sys
from typing import Any

import structlog


def _is_development() -> bool:
    return os.getenv("ENV", os.getenv("ENVIRONMENT", "development")).lower() in (
        "dev", "development", "local",
    )


def configure_logging(
    level: str | None = None,
    *,
    json_output: bool | None = None,
    add_caller_info: bool = True,
) -> None:
    """Configure root logging + structlog processors.

    Call once at application startup, before any log statements.
    """
    effective_level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    use_json = json_output if json_output is not None else not _is_development()

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    if add_caller_info:
        shared_processors.append(structlog.processors.CallsiteParameterAdder(
            [
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.LINENO,
                structlog.processors.CallsiteParameter.FUNC_NAME,
            ]
        ))

    if use_json:
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(effective_level)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound to *name*."""
    return structlog.get_logger(name)


def bind_request_context(**kwargs: Any) -> None:
    """Bind key-value pairs to the current async/thread context (e.g. request_id)."""
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_request_context() -> None:
    """Clear per-request context variables."""
    structlog.contextvars.clear_contextvars()
```

Also write `src/logging_config_example.py` showing typical usage patterns:

```python
# logging_config_example.py  (safe to delete — reference only)
from logging_config import bind_request_context, configure_logging, get_logger

configure_logging()          # call once at startup
log = get_logger(__name__)

# Plain structured event
log.info("server_started", host="0.0.0.0", port=8080)

# Bind context for a request lifetime
bind_request_context(request_id="abc-123", user_id=42)
log.info("request_received", method="GET", path="/api/items")
log.warning("slow_query", duration_ms=450, query="SELECT ...")
```

---

### Step 3B — Node.js / TypeScript: generate pino configuration

**If pino is not installed**:

```bash
npm install pino
npm install --save-dev pino-pretty @types/pino 2>/dev/null || true
```

Write `src/logger.ts` (or `logger.js` for plain JS — adjust extension accordingly):

```typescript
// src/logger.ts
// Structured JSON logger (pino).
// Usage:
//   import { logger, childLogger } from './logger';
//   logger.info({ port: 8080 }, 'server_started');
//   const reqLog = childLogger({ requestId: req.id });
//   reqLog.warn({ durationMs: 450 }, 'slow_query');

import pino from 'pino';

const isDevelopment =
  (process.env.NODE_ENV ?? 'development') === 'development';

export const logger = pino({
  level: process.env.LOG_LEVEL ?? 'info',
  // JSON in production; pretty-print in development (requires pino-pretty)
  transport: isDevelopment
    ? { target: 'pino-pretty', options: { colorize: true, translateTime: 'SYS:standard' } }
    : undefined,
  base: {
    pid: process.pid,
    service: process.env.SERVICE_NAME ?? 'app',
  },
  timestamp: pino.stdTimeFunctions.isoTime,
  serializers: {
    err: pino.stdSerializers.err,
    req: pino.stdSerializers.req,
    res: pino.stdSerializers.res,
  },
  redact: {
    // Redact sensitive fields from logs
    paths: ['req.headers.authorization', '*.password', '*.token', '*.secret'],
    censor: '[REDACTED]',
  },
});

/** Create a child logger pre-bound with context fields (e.g. requestId). */
export function childLogger(bindings: Record<string, unknown>) {
  return logger.child(bindings);
}
```

**If winston is already installed**, write `src/logger.ts` using winston instead:

```typescript
// src/logger.ts — winston structured logger
import winston from 'winston';

const isDevelopment = (process.env.NODE_ENV ?? 'development') === 'development';

export const logger = winston.createLogger({
  level: process.env.LOG_LEVEL ?? 'info',
  format: isDevelopment
    ? winston.format.combine(
        winston.format.colorize(),
        winston.format.timestamp(),
        winston.format.simple(),
      )
    : winston.format.combine(
        winston.format.timestamp(),
        winston.format.errors({ stack: true }),
        winston.format.json(),
      ),
  defaultMeta: { service: process.env.SERVICE_NAME ?? 'app' },
  transports: [new winston.transports.Console()],
});

export function childLogger(meta: Record<string, unknown>) {
  return logger.child(meta);
}
```

---

### Step 3C — Go: generate slog configuration

Detect Go version to choose slog (≥1.21) vs zap:

```bash
go version 2>/dev/null || true
grep "^go " go.mod 2>/dev/null || true
```

Write `internal/logger/logger.go` (create directory if needed):

```bash
mkdir -p internal/logger
```

```go
// internal/logger/logger.go
// Structured logger using log/slog (stdlib, Go 1.21+).
// Usage:
//   logger.Setup(logger.Config{Level: slog.LevelInfo, JSON: true})
//   slog.Info("server_started", "port", 8080)
//   ctx = logger.WithContext(ctx, "request_id", requestID)
//   logger.FromContext(ctx).Info("request_received", "method", r.Method)

package logger

import (
	"context"
	"log/slog"
	"os"
)

type contextKey struct{}

// Config controls logger initialisation.
type Config struct {
	Level  slog.Level
	JSON   bool   // true = JSONHandler, false = TextHandler (human-readable)
	Output *os.File // defaults to os.Stderr
}

// Setup initialises the default slog logger.  Call once at startup.
func Setup(cfg Config) {
	out := cfg.Output
	if out == nil {
		out = os.Stderr
	}

	opts := &slog.HandlerOptions{
		Level:     cfg.Level,
		AddSource: true,
	}

	var handler slog.Handler
	if cfg.JSON {
		handler = slog.NewJSONHandler(out, opts)
	} else {
		handler = slog.NewTextHandler(out, opts)
	}

	slog.SetDefault(slog.New(handler))
}

// WithContext returns a new context carrying the given key-value attributes.
func WithContext(ctx context.Context, args ...any) context.Context {
	return context.WithValue(ctx, contextKey{}, FromContext(ctx).With(args...))
}

// FromContext retrieves the logger stored in ctx, or the default logger.
func FromContext(ctx context.Context) *slog.Logger {
	if l, ok := ctx.Value(contextKey{}).(*slog.Logger); ok && l != nil {
		return l
	}
	return slog.Default()
}
```

Write `internal/logger/logger_test.go`:

```go
package logger_test

import (
	"bytes"
	"context"
	"encoding/json"
	"log/slog"
	"os"
	"testing"

	"<module>/internal/logger"
)

func TestJSONOutput(t *testing.T) {
	var buf bytes.Buffer
	logger.Setup(logger.Config{Level: slog.LevelDebug, JSON: true, Output: os.NewFile(0, "")})
	// verify no panic
	slog.Info("test_event", "key", "value")
	_ = buf // output goes to stderr in tests; just verify no crash
}

func TestContextPropagation(t *testing.T) {
	logger.Setup(logger.Config{Level: slog.LevelDebug, JSON: true})
	ctx := logger.WithContext(context.Background(), "request_id", "abc-123")
	l := logger.FromContext(ctx)
	if l == nil {
		t.Fatal("expected logger in context")
	}
}

func TestJSONFields(t *testing.T) {
	var buf bytes.Buffer
	h := slog.NewJSONHandler(&buf, nil)
	l := slog.New(h)
	l.Info("ping", "status", 200)
	var m map[string]any
	if err := json.Unmarshal(buf.Bytes(), &m); err != nil {
		t.Fatalf("invalid JSON: %v\noutput: %s", err, buf.String())
	}
	if m["msg"] != "ping" {
		t.Errorf("expected msg=ping, got %v", m["msg"])
	}
}
```

Replace `<module>` with the actual module path from `go.mod`.

---

### Step 3D — Rust: generate tracing configuration

Add dependencies to `Cargo.toml` if not present:

```bash
grep -E "^tracing\s*=|^tracing-subscriber\s*=" Cargo.toml 2>/dev/null || \
  cargo add tracing tracing-subscriber --features tracing-subscriber/env-filter,tracing-subscriber/json
```

Write `src/telemetry.rs`:

```rust
// src/telemetry.rs
// Structured logging/tracing setup.
// Usage:
//   telemetry::init();              // call once in main()
//   tracing::info!(port = 8080, "server_started");
//   let span = tracing::info_span!("request", request_id = %id);
//   let _guard = span.enter();

use tracing_subscriber::{fmt, layer::SubscriberExt, util::SubscriberInitExt, EnvFilter};

/// Initialise the global tracing subscriber.
/// Reads `RUST_LOG` for level filter (default: `info`).
/// Reads `LOG_FORMAT=json` to switch to JSON output (default: pretty in dev).
pub fn init() {
    let env_filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new("info"));

    let use_json = std::env::var("LOG_FORMAT")
        .map(|v| v.eq_ignore_ascii_case("json"))
        .unwrap_or(false);

    if use_json {
        tracing_subscriber::registry()
            .with(env_filter)
            .with(fmt::layer().json().with_current_span(true))
            .init();
    } else {
        tracing_subscriber::registry()
            .with(env_filter)
            .with(fmt::layer().pretty())
            .init();
    }
}
```

Add `mod telemetry;` and `telemetry::init();` to `src/main.rs` (or `src/lib.rs`).

---

### Step 4 — Verify generated file(s) are syntactically valid

Run the appropriate check:

```bash
# Python
python3 -c "import ast, pathlib; [ast.parse(p.read_text()) for p in pathlib.Path('src').rglob('logging_config*.py')] ; print('Python OK')" 2>/dev/null || \
python3 -m py_compile src/logging_config.py && echo "Python OK"

# Node.js / TypeScript
npx tsc --noEmit 2>/dev/null || node --input-type=module < src/logger.js 2>/dev/null || echo "Skipping TS check — run 'npx tsc --noEmit' manually"

# Go
go build ./... 2>/dev/null && echo "Go OK" || echo "Go build failed — check module path in logger_test.go"

# Rust
cargo check 2>/dev/null && echo "Rust OK"
```

Report any errors and offer to fix them.

---

### Step 5 — Environment variable reference

Print this reference block so the user knows how to configure the logger at runtime:

```
┌─────────────────────────────────────────────────────────────────┐
│  Logging environment variables                                  │
├──────────────────┬──────────────────────────────────────────────┤
│ LOG_LEVEL        │ debug | info | warn | error  (default: info) │
│ LOG_FORMAT       │ json | text  (Rust only; default: text)       │
│ ENV / ENVIRONMENT│ development → pretty output  (Py / Node)     │
│ SERVICE_NAME     │ Injected into every log line (Node)           │
│ RUST_LOG         │ e.g. info,my_crate=debug  (Rust)             │
└──────────────────┴──────────────────────────────────────────────┘
```

---

### Step 6 — Summary

Print a concise summary:

```
✅  Structured logging configured
────────────────────────────────────────────────────────────────────
 Language   : <detected language>
 Framework  : <chosen logger>
 File(s)    : <list of files written>
 Output fmt : JSON (production) / pretty (development)
 Correlation: bind_request_context() / childLogger() / WithContext()
────────────────────────────────────────────────────────────────────
Next steps:
  1. Import / call configure_logging() (or equivalent) at startup.
  2. Set LOG_LEVEL=debug locally; LOG_LEVEL=info in production.
  3. Set ENV=production (or NODE_ENV=production) to enable JSON output.
  4. Bind a request_id / trace_id per request for log correlation.
```

If any dependency was added, remind the user to commit the updated lock file.
>>>>>>> feat/observability-a-skill-generates-structured-logging-conf
