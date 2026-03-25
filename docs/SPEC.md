# Logging Convention Specification
> **Version:** 1.0.0
> **Status:** Active
> **Generated:** 2026-03-22
> **Scope:** All services and libraries in this repository

This document is the single source of truth for structured log entry format.
Every log entry emitted by any service, library, or script MUST conform to this
specification.  Non-conforming entries will be rejected by the CI linter.

---

## Overview

This specification defines a minimal, language-agnostic structured logging contract.
Every log entry is a single JSON object (one per line — NDJSON format) containing
exactly five required fields plus an optional `extra` object for additional context.

The goals are:
- **Consistency** — uniform shape across Python, TypeScript, Go, and Java services
- **Correlability** — `trace_id` links all entries from a single request chain
- **Lintability** — a machine-readable schema enables CI enforcement
- **Human-readability** — five well-named fields are easy to reason about

---

## Required Fields

Every log entry MUST include all five fields below.  No field may be omitted or null.

| Field       | Type   | Format / Constraint                           | Example                                |
|-------------|--------|-----------------------------------------------|----------------------------------------|
| `timestamp` | string | ISO-8601 UTC, millisecond precision (`Z`)     | `"2026-03-22T14:22:05.123Z"`           |
| `level`     | string | One of: `DEBUG INFO WARN ERROR FATAL`         | `"INFO"`                               |
| `domain`    | string | Dot-separated, non-empty, no consecutive dots | `"payments.stripe.webhook"`            |
| `trace_id`  | string | Exactly 32 lowercase hex characters           | `"4bf92f3577b34da6a3ce929d0e0e4736"`   |
| `message`   | string | Non-empty UTF-8, no length limit              | `"Charge succeeded"`                   |

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

| Domain                     | Meaning                                       |
|----------------------------|-----------------------------------------------|
| `payments`                 | Top-level payments service                    |
| `payments.stripe`          | Stripe integration within payments            |
| `payments.stripe.webhook`  | Webhook handler inside Stripe integration     |
| `auth.jwt`                 | JWT handling inside the auth service          |
| `http.server`              | HTTP layer (e.g. middleware-generated entry)  |

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

## CLI Reference (`log-lint`)

Install: `uv add logging-convention`

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

| Version | Date       | Type    | Change |
|---------|------------|---------|--------|
| 1.0.0   | 2026-03-22 | Initial | First stable release of the logging convention |

<!-- harness:cross-links — do not edit this block manually -->

---

## Related Documents

| Document | Relationship |
|---|---|
| [ERROR_HANDLING_RULES.md](ERROR_HANDLING_RULES.md) | logging format conventions (§6) |
| [HEALTH_CHECK_SPEC.md](HEALTH_CHECK_SPEC.md) | related observability specification |
| [PRINCIPLES.md](../PRINCIPLES.md) | logging provider rule MB011 |
| [.claude/commands/logging-convention.md](../.claude/commands/logging-convention.md) | skill that regenerated this file |
| [.claude/commands/log-format-linter.md](../.claude/commands/log-format-linter.md) | CI linter that validates against this spec |
| [DOCS_INDEX.md](../DOCS_INDEX.md) | full documentation index |

<!-- /harness:cross-links -->
