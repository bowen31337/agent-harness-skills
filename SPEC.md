# Logging Convention Specification
> **Version:** 1.0.0
> **Status:** Active
> **Generated:** 2026-03-22
> **Scope:** All services and libraries in this repository

This document is the single source of truth for structured log entry format.
Every log entry emitted by any service, library, or script MUST conform to this
specification.  Non-conforming entries will be rejected by the CI linter.

---

## Table of Contents

1. [Overview](#overview)
2. [Required Fields](#required-fields)
3. [Field Reference](#field-reference)
4. [Compliant Example](#compliant-example)
5. [Non-Compliant Examples](#non-compliant-examples)
6. [JSON Schema](#json-schema)
7. [Adoption Guide](#adoption-guide)
8. [Observability Stack Templates](#observability-stack-templates)
9. [CLI Reference](#cli-reference-log-lint)
10. [Changelog](#changelog)

---

## Overview

Structured logging is the foundation of observable systems.  This specification
defines a minimal, portable log entry format that:

- Works with any language or runtime
- Is compatible with W3C Trace Context for distributed tracing
- Can be validated automatically in CI via `log-lint`
- Integrates with lightweight, file-based log collectors for local development

Every log entry is written as a single-line JSON object (NDJSON) to `stdout` or
a designated log file.  Downstream collectors (Promtail, Vector, Filebeat, etc.)
tail those files and forward entries to a central store.

---

## Required Fields

Every log entry MUST include all five fields below.  No field may be omitted or null.

| Field       | Type   | Format / Constraint                           | Example                                  |
|-------------|--------|-----------------------------------------------|------------------------------------------|
| `timestamp` | string | ISO-8601 UTC, millisecond precision (`Z`)     | `"2026-03-22T14:22:05.123Z"`             |
| `level`     | string | One of: `DEBUG INFO WARN ERROR FATAL`         | `"INFO"`                                 |
| `domain`    | string | Dot-separated, non-empty, no consecutive dots | `"payments.stripe.webhook"`              |
| `trace_id`  | string | Exactly 32 lowercase hex characters           | `"4bf92f3577b34da6a3ce929d0e0e4736"`     |
| `message`   | string | Non-empty UTF-8, no length limit              | `"Charge succeeded"`                     |

An optional `extra` object MAY be added for additional key-value pairs.
Keys inside `extra` MUST NOT shadow any of the five required field names.

---

## Field Reference

### `timestamp`

**Type:** `string`
**Format:** ISO-8601 UTC with millisecond precision
**Pattern:** `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$`

The moment the log entry was created, expressed in Coordinated Universal Time.
Always include the trailing `Z` (Zulu / UTC offset).  Sub-millisecond precision
is allowed but not required.  Naive timestamps (no timezone suffix) are rejected.

**Valid:**   `"2026-03-22T14:22:05.123Z"`
**Invalid:** `"2026-03-22 14:22:05"` — missing `T` separator and `Z` suffix
**Invalid:** `"2026-03-22T14:22:05+05:30"` — non-UTC offset not permitted

---

### `level`

**Type:** `string`
**Allowed values:** `DEBUG` · `INFO` · `WARN` · `ERROR` · `FATAL`
**Case:** UPPERCASE only (input may be case-insensitive; normalized on write)

| Value   | Semantic meaning                                                    |
|---------|---------------------------------------------------------------------|
| `DEBUG` | Verbose developer information; disabled in production by default    |
| `INFO`  | Normal operational events; expected in steady-state operation       |
| `WARN`  | Recoverable anomaly; service continues but investigation is advised |
| `ERROR` | Unrecoverable failure in a single operation; service stays up       |
| `FATAL` | Unrecoverable failure requiring process exit                        |

Any value outside this set is rejected with a validation error.

---

### `domain`

**Type:** `string`
**Pattern:** `^[a-zA-Z0-9_]+(\.[a-zA-Z0-9_]+)*$`
**Convention:** reverse-hierarchical, dot-separated, lowercase preferred

Identifies the originating service scope of the log entry.  Structure the
domain from coarse to fine, separated by dots:

```
<service>.<subsystem>.<component>
```

**Examples:**

| Domain                     | Meaning                                      |
|----------------------------|----------------------------------------------|
| `payments`                 | Top-level payments service                   |
| `payments.stripe`          | Stripe integration within payments           |
| `payments.stripe.webhook`  | Webhook handler inside Stripe integration    |
| `auth.jwt`                 | JWT handling inside the auth service         |
| `http.server`              | HTTP layer (e.g. middleware-generated entry) |

**Invalid:** `""` — empty string
**Invalid:** `"payments..stripe"` — consecutive dots
**Invalid:** `"payments "` — trailing space

---

### `trace_id`

**Type:** `string`
**Pattern:** `^[0-9a-f]{32}$`
**Compatibility:** W3C Trace Context `traceparent` header (low 32 hex chars = trace ID)

A 128-bit identifier expressed as 32 lowercase hexadecimal characters with no
hyphens or spaces.  Every log entry within a single request or causal chain
MUST share the same `trace_id`, enabling log correlation across services and
domains.

**Auto-generation:** If the caller does not supply a `trace_id`, the library
generates a random one using a cryptographically secure source.

**W3C interop:**
Extract from an incoming `traceparent` header:
```
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ ← use these 32 chars
```

**Valid:**   `"4bf92f3577b34da6a3ce929d0e0e4736"`
**Invalid:** `"4BF92F3577B34DA6A3CE929D0E0E4736"` — uppercase hex rejected
**Invalid:** `"4bf92f35-77b3-4da6-a3ce-929d0e0e4736"` — UUID hyphens not allowed
**Invalid:** `"4bf92f35"` — too short (8 chars instead of 32)

---

### `message`

**Type:** `string`
**Constraint:** non-empty UTF-8; no maximum length enforced at the contract layer

A human-readable description of the event.  Messages SHOULD be static strings
with dynamic values moved to `extra` keys — this enables log aggregation tools
to group distinct events reliably.

**Recommended (static message + extra fields):**
```json
{ "message": "Charge succeeded", "extra": { "amount": 1999, "currency": "usd" } }
```

**Discouraged (dynamic message):**
```json
{ "message": "Charge of $19.99 USD succeeded for customer cus_abc123" }
```

**Invalid:** `""` — empty string
**Invalid:** `"   "` — whitespace-only string

---

## Compliant Example

A log entry that passes all five field validations:

```json
{
  "timestamp": "2026-03-22T14:22:05.123Z",
  "level":     "INFO",
  "domain":    "payments.stripe.webhook",
  "trace_id":  "4bf92f3577b34da6a3ce929d0e0e4736",
  "message":   "Charge succeeded",
  "extra": {
    "amount":      1999,
    "currency":    "usd",
    "customer_id": "cus_abc123"
  }
}
```

As a single NDJSON line (as written to log files and stdout):

```
{"timestamp":"2026-03-22T14:22:05.123Z","level":"INFO","domain":"payments.stripe.webhook","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","message":"Charge succeeded","extra":{"amount":1999,"currency":"usd","customer_id":"cus_abc123"}}
```

---

## Non-Compliant Examples

Each example below illustrates a common violation and the exact error it produces.

| # | Violation | Offending value | Error message |
|---|-----------|-----------------|---------------|
| 1 | Missing `trace_id` field | *(absent)* | `trace_id is required` |
| 2 | Naive timestamp (no UTC offset) | `"2026-03-22T14:22:05.123"` | `timestamp must be ISO-8601 UTC (trailing Z required)` |
| 3 | Invalid level | `"VERBOSE"` | `level must be one of DEBUG, INFO, WARN, ERROR, FATAL` |
| 4 | Empty domain | `""` | `domain must be a non-empty dot-separated string` |
| 5 | Uppercase trace_id | `"4BF92F3577B34DA6A3CE929D0E0E4736"` | `trace_id must be 32 lowercase hex characters` |
| 6 | Whitespace-only message | `"   "` | `message must be a non-empty string` |

---

## JSON Schema

The canonical schema is published at `schemas/log_entry.schema.json`.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id":     "https://example.com/logging-convention/log_entry.schema.json",
  "title":   "LogEntry",
  "type":    "object",
  "required": ["timestamp", "level", "domain", "trace_id", "message"],
  "additionalProperties": false,
  "properties": {
    "timestamp": {
      "type":        "string",
      "format":      "date-time",
      "description": "ISO-8601 UTC timestamp with millisecond precision"
    },
    "level": {
      "type": "string",
      "enum": ["DEBUG", "INFO", "WARN", "ERROR", "FATAL"],
      "description": "Severity level of the log entry"
    },
    "domain": {
      "type":        "string",
      "pattern":     "^[a-zA-Z0-9_]+(\\.[a-zA-Z0-9_]+)*$",
      "minLength":   1,
      "description": "Dot-separated originating service scope"
    },
    "trace_id": {
      "type":        "string",
      "pattern":     "^[0-9a-f]{32}$",
      "description": "W3C-compatible 32-character lowercase hex trace identifier"
    },
    "message": {
      "type":        "string",
      "minLength":   1,
      "description": "Human-readable description of the logged event"
    },
    "extra": {
      "type":                 "object",
      "additionalProperties": true,
      "description":          "Optional additional key-value pairs; keys must not shadow required fields"
    }
  }
}
```

---

## Adoption Guide

### Python

```python
from logging_convention import get_logger, configure, StdoutTransport, set_trace_id

# 1. Configure once at service startup
configure([StdoutTransport()])

# 2. Create a domain-bound logger
log = get_logger("payments.stripe.webhook")

# 3. Wrap each request with a trace context
with set_trace_id("4bf92f3577b34da6a3ce929d0e0e4736"):
    log.info("Charge succeeded", amount=1999, currency="usd")
    # → {"timestamp":"…","level":"INFO","domain":"payments.stripe.webhook",
    #    "trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","message":"Charge succeeded",
    #    "extra":{"amount":1999,"currency":"usd"}}
```

### TypeScript / Node.js

```typescript
import { createLogger } from "logging-convention";

const log = createLogger("payments.stripe.webhook");

log.info("Charge succeeded", {
  traceId: "4bf92f3577b34da6a3ce929d0e0e4736",
  extra:   { amount: 1999, currency: "usd" },
});
```

### Go

```go
import "github.com/your-org/logging-convention"

logger := convention.NewLogger("payments.stripe.webhook")
logger.Info(ctx, "Charge succeeded",
    convention.Field("amount", 1999),
    convention.Field("currency", "usd"),
)
// trace_id is extracted from ctx (OpenTelemetry span or custom header)
```

### Java

```java
import com.example.logging.LogEntry;
import com.example.logging.Logger;

Logger logger = Logger.forDomain("payments.stripe.webhook");
logger.info("Charge succeeded",
    Map.of("amount", 1999, "currency", "usd"));
// trace_id propagated via MDC / OpenTelemetry context
```

---

## Observability Stack Templates

> **Scope:** Local development only.  These templates spin up a lightweight,
> file-based log aggregation pipeline on a single machine with zero cloud
> dependencies.  They are **not** intended for production use.

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  Services / Scripts                                         │
│  (write NDJSON to ./logs/<service>.log)                     │
└──────────────────────────┬──────────────────────────────────┘
                           │  tail / inotify
          ┌────────────────▼────────────────┐
          │  File-Based Collector           │
          │  (Promtail · Vector · Filebeat) │
          └────────────────┬────────────────┘
                           │  HTTP / gRPC
          ┌────────────────▼────────────────┐
          │  Local Aggregator               │
          │  (Loki · Elasticsearch · Seq)   │
          └────────────────┬────────────────┘
                           │
          ┌────────────────▼────────────────┐
          │  Query / Visualise              │
          │  (Grafana · Kibana · Seq UI)    │
          └─────────────────────────────────┘
```

All services write structured NDJSON logs to the `./logs/` directory.  The
collector tails those files, parses the five required fields, and ships entries
to the local aggregator.  No network egress leaves the developer's machine.

---

### Option A — Promtail + Loki + Grafana (recommended)

Lightest-weight stack.  Loki indexes only labels (not full text); Grafana ships
with a built-in Loki data source.

#### `docker-compose.observability.yml`

```yaml
version: "3.9"

volumes:
  loki_data:

services:
  # ── Loki ───────────────────────────────────────────────────────────────────
  loki:
    image: grafana/loki:2.9.4
    ports:
      - "3100:3100"
    command: -config.file=/etc/loki/config.yaml
    volumes:
      - ./observability/loki-config.yaml:/etc/loki/config.yaml:ro
      - loki_data:/loki
    healthcheck:
      test: ["CMD-SHELL", "wget -q --spider http://localhost:3100/ready || exit 1"]
      interval: 10s
      retries: 5

  # ── Promtail ───────────────────────────────────────────────────────────────
  promtail:
    image: grafana/promtail:2.9.4
    volumes:
      - ./logs:/var/log/app:ro                           # ← host log directory
      - ./observability/promtail-config.yaml:/etc/promtail/config.yaml:ro
    command: -config.file=/etc/promtail/config.yaml
    depends_on:
      loki:
        condition: service_healthy

  # ── Grafana ────────────────────────────────────────────────────────────────
  grafana:
    image: grafana/grafana:10.3.3
    ports:
      - "3000:3000"
    environment:
      GF_AUTH_ANONYMOUS_ENABLED: "true"
      GF_AUTH_ANONYMOUS_ORG_ROLE: Admin
    volumes:
      - ./observability/grafana-datasources.yaml:/etc/grafana/provisioning/datasources/loki.yaml:ro
    depends_on:
      - loki
```

#### `observability/loki-config.yaml`

```yaml
auth_enabled: false

server:
  http_listen_port: 3100

ingester:
  lifecycler:
    ring:
      kvstore:
        store: inmemory
      replication_factor: 1
  chunk_idle_period: 5m
  chunk_retain_period: 30s

schema_config:
  configs:
    - from: 2024-01-01
      store: boltdb-shipper
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 24h

storage_config:
  boltdb_shipper:
    active_index_directory: /loki/index
    cache_location:          /loki/cache
    shared_store:            filesystem
  filesystem:
    directory: /loki/chunks

limits_config:
  reject_old_samples:         true
  reject_old_samples_max_age: 168h

compactor:
  working_directory: /loki/compactor
  shared_store:      filesystem
```

#### `observability/promtail-config.yaml`

```yaml
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml          # tracks read position across restarts

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: app_logs
    static_configs:
      - targets:
          - localhost
        labels:
          job: app
          __path__: /var/log/app/*.log   # tails every *.log in the mounted dir

    pipeline_stages:
      # Parse NDJSON ──────────────────────────────────────────────────────────
      - json:
          expressions:
            timestamp: timestamp
            level:     level
            domain:    domain
            trace_id:  trace_id
            message:   message

      # Promote required fields to Loki labels ────────────────────────────────
      - labels:
          level:    ""
          domain:   ""

      # Re-stamp the log line's timestamp from the parsed field ───────────────
      - timestamp:
          source: timestamp
          format: RFC3339Milli

      # Set the log line body to the human-readable message ───────────────────
      - output:
          source: message
```

#### `observability/grafana-datasources.yaml`

```yaml
apiVersion: 1
datasources:
  - name:   Loki
    type:   loki
    access: proxy
    url:    http://loki:3100
    isDefault: true
```

**Quick-start:**

```bash
mkdir -p logs observability
# Place the config files above in ./observability/
docker compose -f docker-compose.observability.yml up -d
# Open http://localhost:3000  → Explore → Loki
# Example query: {job="app"} | json | level="ERROR"
```

---

### Option B — Vector + Elasticsearch + Kibana

More powerful full-text search; heavier on RAM (~512 MB for ES).

#### `docker-compose.observability-elk.yml`

```yaml
version: "3.9"

volumes:
  es_data:

services:
  # ── Elasticsearch ──────────────────────────────────────────────────────────
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.12.2
    environment:
      discovery.type:         single-node
      xpack.security.enabled: "false"
      ES_JAVA_OPTS:           "-Xms256m -Xmx256m"
    ports:
      - "9200:9200"
    volumes:
      - es_data:/usr/share/elasticsearch/data
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:9200/_cluster/health || exit 1"]
      interval: 15s
      retries: 10

  # ── Vector ─────────────────────────────────────────────────────────────────
  vector:
    image: timberio/vector:0.37.0-debian
    volumes:
      - ./logs:/var/log/app:ro
      - ./observability/vector.toml:/etc/vector/vector.toml:ro
    depends_on:
      elasticsearch:
        condition: service_healthy

  # ── Kibana ─────────────────────────────────────────────────────────────────
  kibana:
    image: docker.elastic.co/kibana/kibana:8.12.2
    environment:
      ELASTICSEARCH_HOSTS: '["http://elasticsearch:9200"]'
    ports:
      - "5601:5601"
    depends_on:
      - elasticsearch
```

#### `observability/vector.toml`

```toml
# ── Sources ────────────────────────────────────────────────────────────────
[sources.app_logs]
type     = "file"
include  = ["/var/log/app/*.log"]
read_from = "beginning"

# ── Transforms ─────────────────────────────────────────────────────────────
[transforms.parse_json]
type   = "remap"
inputs = ["app_logs"]
source = '''
  # Parse NDJSON line
  . = parse_json!(string!(.message))

  # Validate required fields exist
  assert!(exists(.timestamp), "missing timestamp")
  assert!(exists(.level),     "missing level")
  assert!(exists(.domain),    "missing domain")
  assert!(exists(.trace_id),  "missing trace_id")
  assert!(exists(.message),   "missing message")
'''

[transforms.add_meta]
type   = "remap"
inputs = ["parse_json"]
source = '''
  .collector = "vector"
  .env       = get_env_var!("APP_ENV") ?? "local"
'''

# ── Sinks ──────────────────────────────────────────────────────────────────
[sinks.elasticsearch]
type        = "elasticsearch"
inputs      = ["add_meta"]
endpoints   = ["http://elasticsearch:9200"]
index       = "logs-%Y.%m.%d"          # daily rolling index
compression = "none"

  [sinks.elasticsearch.encoding]
  codec = "json"

# Also echo to stdout for `docker compose logs vector`
[sinks.console]
type   = "console"
inputs = ["parse_json"]
target = "stdout"

  [sinks.console.encoding]
  codec = "json"
```

**Quick-start:**

```bash
docker compose -f docker-compose.observability-elk.yml up -d
# Open http://localhost:5601
# Create index pattern: logs-*  (time field: timestamp)
# Discover → filter: level: ERROR  or  domain: payments.*
```

---

### Option C — Filebeat + Seq (Windows / Mac friendly, single UI)

Seq provides a built-in structured log UI with no separate visualisation layer.
Ideal for small teams or solo developers on macOS/Windows.

#### `docker-compose.observability-seq.yml`

```yaml
version: "3.9"

volumes:
  seq_data:

services:
  # ── Seq ────────────────────────────────────────────────────────────────────
  seq:
    image: datalust/seq:2024.1
    environment:
      ACCEPT_EULA: Y
    ports:
      - "5341:80"      # Seq UI
      - "5342:5341"    # Seq ingestion
    volumes:
      - seq_data:/data

  # ── Filebeat ───────────────────────────────────────────────────────────────
  filebeat:
    image: docker.elastic.co/beats/filebeat:8.12.2
    user: root
    volumes:
      - ./logs:/var/log/app:ro
      - ./observability/filebeat.yml:/usr/share/filebeat/filebeat.yml:ro
    depends_on:
      - seq
```

#### `observability/filebeat.yml`

```yaml
filebeat.inputs:
  - type: log
    enabled: true
    paths:
      - /var/log/app/*.log
    json.keys_under_root: true        # parse NDJSON fields to top level
    json.add_error_key:   true
    json.message_key:     message

processors:
  - timestamp:
      field:   timestamp
      layouts: ["2006-01-02T15:04:05.000Z"]
      target:  "@timestamp"

  - drop_fields:
      fields: ["log", "input", "agent", "ecs"]
      ignore_missing: true

output.elasticsearch:
  # Seq exposes an ES-compatible bulk ingest endpoint
  hosts:    ["http://seq:9200"]
  index:    "logs"
  protocol: http
```

**Quick-start:**

```bash
docker compose -f docker-compose.observability-seq.yml up -d
# Open http://localhost:5341
# Seq filter examples:
#   @Level = 'ERROR'
#   domain like 'payments.%'
#   trace_id = '4bf92f3577b34da6a3ce929d0e0e4736'
```

---

### Shared Helper — `make observe`

Add to your project `Makefile` to launch whichever stack you prefer:

```makefile
OBSERVE_STACK ?= loki   # override: make observe OBSERVE_STACK=elk

observe:
	@mkdir -p logs
	docker compose -f docker-compose.observability-$(OBSERVE_STACK).yml up -d
	@echo "✅  Observability stack ($(OBSERVE_STACK)) is up."
	@echo "    Grafana (Loki) : http://localhost:3000"
	@echo "    Kibana  (ELK)  : http://localhost:5601"
	@echo "    Seq            : http://localhost:5341"

observe-down:
	docker compose \
	  -f docker-compose.observability-loki.yml \
	  -f docker-compose.observability-elk.yml \
	  -f docker-compose.observability-seq.yml \
	  down --remove-orphans 2>/dev/null || true
```

---

### Stack Comparison

| Feature                  | Promtail + Loki + Grafana | Vector + ES + Kibana | Filebeat + Seq |
|--------------------------|--------------------------|----------------------|----------------|
| RAM footprint            | ~150 MB                  | ~512 MB              | ~200 MB        |
| Full-text search         | Label-based only         | ✅ Yes               | ✅ Yes         |
| Config complexity        | Low                      | Medium               | Low            |
| Best for                 | Trace-ID correlation     | Ad-hoc log analysis  | Solo dev / Win |
| Log retention            | Configurable chunks      | Daily rolling index  | Ring buffer    |
| Separate visualiser      | Grafana                  | Kibana               | Built-in       |
| Auth required (dev mode) | No                       | No                   | No             |

---

## CLI Reference (`log-lint`)

Install: `pip install logging-convention`

| Command | Description |
|---------|-------------|
| `log-lint validate <file>` | Validate every NDJSON line; exit 1 on any violation |
| `log-lint validate --strict <file>` | Also fail on unknown top-level keys |
| `log-lint validate --output=json <file>` | Emit machine-readable validation results |
| `log-lint stats <file>` | Summary: total lines, counts by level, unique domains, unique trace_ids |
| `log-lint trace <trace_id> <file>` | Extract all entries matching a given trace_id |
| `log-lint domain <domain> <file>` | Filter entries by domain prefix |
| `log-lint convert --from=logfmt --to=json <file>` | Convert logfmt to compliant NDJSON |
| `log-lint check-schema` | Print active JSON Schema version and public URL |

**Pipe support:** Replace `<file>` with `-` to read from stdin:

```bash
kubectl logs my-pod | log-lint validate -
```

**CI integration example (GitHub Actions):**

```yaml
- name: Validate logs
  run: log-lint validate --output=json service.log
```

---

## Changelog

| Version | Date       | Type    | Change                                         |
|---------|------------|---------|------------------------------------------------|
| 1.0.0   | 2026-03-22 | Initial | First stable release of the logging convention |
