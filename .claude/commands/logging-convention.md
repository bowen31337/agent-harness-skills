---
name: logging-convention
description: "Language-agnostic logging convention document generator. Produces a versioned SPEC.md (or SPEC.json) defining the five required fields every log entry must carry: timestamp (ISO-8601 UTC), level (DEBUG/INFO/WARN/ERROR/FATAL), domain (dot-separated service scope), trace_id (W3C-compatible 32-hex-char ID), and message (non-empty UTF-8 string). Includes field validation rules, compliant/non-compliant NDJSON examples, JSON Schema snippet, adoption guide (Python, TypeScript, Go, Java), and a log-lint CLI reference. Use when: (1) bootstrapping a new service that needs a structured logging standard, (2) generating the canonical SPEC.md for a logging-convention library, (3) documenting an existing log format for team review, (4) producing a machine-readable JSON Schema for cross-language log validation. Triggers on: logging convention, log spec, log entry fields, structured logging, trace_id, NDJSON, log schema, observability contract, generate SPEC.md, logging standard, log format document."
---

# Logging Convention Skill

Generates a versioned, language-agnostic **logging convention document** that specifies
exactly what every log entry must contain.  The output is a self-contained `SPEC.md` (or
`SPEC.json`) that teams can adopt across any stack without reading implementation code.

---

## Workflow

**Generate a Markdown spec file?**
→ [Generate SPEC.md](#generate-specmd)

**Generate a machine-readable JSON Schema?**
→ [Generate JSON Schema](#generate-json-schema)

**Validate an existing log file against the convention?**
→ [Validate log file](#validate-a-log-file)

**Need language-specific adoption snippets?**
→ [Adoption guide](#adoption-guide)

---

## Usage

```bash
# Write SPEC.md to the current directory (default)
/logging-convention

# Write to a custom path
/logging-convention --output docs/logging/SPEC.md

# Also emit a JSON Schema alongside the spec
/logging-convention --with-schema

# Bump the convention version (default: 1.0.0)
/logging-convention --version 2.0.0

# Emit only the JSON Schema (no Markdown)
/logging-convention --format json

# Print to stdout instead of writing a file
/logging-convention --stdout
```

---

## Generate SPEC.md

When invoked, produce a `SPEC.md` file at the target path containing all sections below.

### Step 1 — Resolve output path

```
output_path = args["--output"] or "SPEC.md"
version     = args["--version"] or "1.0.0"
```

### Step 2 — Write the document

Emit a document with the following structure (expand each section fully):

```
# Logging Convention Specification
> Version: <version> · Generated: <ISO-8601 date>

## Overview
## Required Fields
## Field Reference (one subsection per field)
## Compliant Example
## Non-Compliant Examples
## JSON Schema
## Adoption Guide
## CLI Reference (log-lint)
## Changelog
```

Sections are described in detail in [Document Sections](#document-sections) below.

### Step 3 — Confirm write

After writing, print:

```
✅  SPEC.md written → <output_path>
    Version  : <version>
    Fields   : timestamp · level · domain · trace_id · message
    Schema   : <schema_path or "not requested">
```

---

## Document Sections

### Header

```markdown
# Logging Convention Specification
> **Version:** 1.0.0
> **Status:** Active
> **Generated:** 2026-03-22
> **Scope:** All services and libraries in this repository

This document is the single source of truth for structured log entry format.
Every log entry emitted by any service, library, or script MUST conform to this
specification.  Non-conforming entries will be rejected by the CI linter.
```

---

### Required Fields Table

```markdown
## Required Fields

Every log entry MUST include all five fields below.  No field may be omitted or null.

| Field       | Type   | Format / Constraint                          | Example                                |
|-------------|--------|----------------------------------------------|----------------------------------------|
| `timestamp` | string | ISO-8601 UTC, millisecond precision (`Z`)    | `"2026-03-22T14:22:05.123Z"`           |
| `level`     | string | One of: `DEBUG INFO WARN ERROR FATAL`        | `"INFO"`                               |
| `domain`    | string | Dot-separated, non-empty, no consecutive dots| `"payments.stripe.webhook"`            |
| `trace_id`  | string | Exactly 32 lowercase hex characters          | `"4bf92f3577b34da6a3ce929d0e0e4736"`   |
| `message`   | string | Non-empty UTF-8, no length limit             | `"Charge succeeded"`                   |

An optional `extra` object MAY be added for additional key-value pairs.
Keys inside `extra` MUST NOT shadow any of the five required field names.
```

---

### Field Reference Subsections

Emit one subsection per field:

#### `timestamp`

```markdown
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
```

#### `level`

```markdown
### `level`

**Type:** `string`
**Allowed values:** `DEBUG` · `INFO` · `WARN` · `ERROR` · `FATAL`
**Case:** UPPERCASE only (input may be case-insensitive; normalized on write)

| Value   | Semantic meaning                                              |
|---------|---------------------------------------------------------------|
| `DEBUG` | Verbose developer information; disabled in production by default |
| `INFO`  | Normal operational events; expected in steady-state operation |
| `WARN`  | Recoverable anomaly; service continues but investigation is advised |
| `ERROR` | Unrecoverable failure in a single operation; service stays up |
| `FATAL` | Unrecoverable failure requiring process exit                  |

Any value outside this set is rejected with a validation error.
```

#### `domain`

```markdown
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
```

#### `trace_id`

```markdown
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
```

#### `message`

```markdown
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
```

---

### Compliant Example

```markdown
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
```

---

### Non-Compliant Examples

```markdown
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
```

---

### JSON Schema

```markdown
## JSON Schema

The canonical schema is published at `schemas/log_entry.schema.json` and at the
stable public URL `docs/schema/log_entry.schema.json`.

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
```

---

### Adoption Guide

```markdown
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
```

---

### CLI Reference

```markdown
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
```

---

### Changelog Section

```markdown
## Changelog

| Version | Date       | Type     | Change |
|---------|------------|----------|--------|
| 1.0.0   | 2026-03-22 | Initial  | First stable release of the logging convention |
```

---

## Generate JSON Schema

When `--format json` or `--with-schema` is passed, write the JSON Schema from the
[JSON Schema section](#json-schema) to `schemas/log_entry.schema.json` (or
`--output` path if specified).

Confirm with:

```
✅  JSON Schema written → schemas/log_entry.schema.json
    Draft   : 2020-12
    Required: timestamp · level · domain · trace_id · message
```

---

## Validate a Log File

When `--validate <logfile>` is passed, run the `log-lint` CLI against the file and
print a summary:

```bash
log-lint validate "$logfile" --output=json 2>&1
```

Report:

```
📋  Validation: <logfile>
    Lines:    1 234
    Valid:    1 230  ✅
    Invalid:      4  ❌

    Line   12  missing field: trace_id
    Line   45  level "VERBOSE" not in allowed set
    Line  210  timestamp missing UTC offset (Z)
    Line  891  trace_id "ABC123" is not 32 lowercase hex chars
```

Exit code mirrors `log-lint` (0 = all valid, 1 = any violation).

---

## Data Structures

### `LogEntry`

| Field       | Type            | Required | Default                    |
|-------------|-----------------|----------|----------------------------|
| `timestamp` | `datetime` (UTC)| ✅ Yes   | `utcnow()` (auto-set)      |
| `level`     | `str`           | ✅ Yes   | —                          |
| `domain`    | `str`           | ✅ Yes   | —                          |
| `trace_id`  | `str` (32 hex)  | ✅ Yes   | auto-generated if not given|
| `message`   | `str`           | ✅ Yes   | —                          |
| `extra`     | `dict` or `None`| ❌ No    | `None`                     |

### Validation Rules Summary

| Field       | Rejection condition |
|-------------|---------------------|
| `timestamp` | `None`, naive (no timezone), not a `datetime` |
| `level`     | Any value outside `{DEBUG, INFO, WARN, ERROR, FATAL}` |
| `domain`    | Empty string, whitespace-only, or contains `..` |
| `trace_id`  | Not exactly 32 lowercase hex characters |
| `message`   | Empty string or whitespace-only |
| `extra`     | Any key that shadows a required field name |

---

## Key Files

| Path | Purpose |
|------|---------|
| `SPEC.md` | Generated convention document (output of this skill) |
| `schemas/log_entry.schema.json` | Canonical JSON Schema (draft-2020-12) |
| `skills/logging-convention/SKILL.md` | Full skill implementation documentation |
| `logging_convention_spec.txt` | Source project specification (128 features) |
| `harness_skills/` | Python reference implementation package |

---

## Options

| Flag | Effect |
|------|--------|
| `--output <path>` | Write SPEC.md to this path (default: `SPEC.md`) |
| `--version <semver>` | Set the convention version header (default: `1.0.0`) |
| `--with-schema` | Also write `schemas/log_entry.schema.json` |
| `--format json` | Write JSON Schema only (no Markdown) |
| `--stdout` | Print to stdout instead of writing a file |
| `--validate <logfile>` | Run `log-lint validate` against a log file and report |

---

## When to use this skill

| Scenario | Recommended skill |
|----------|-------------------|
| Generate logging convention doc for a new repo | **`/logging-convention`** ← you are here |
| Lint/validate a log file in CI | `/logging-convention --validate service.log` |
| Inspect live page structure | `/dom-snapshot` |
| Check code quality before merge | `/check-code` |
| Detect conflicts with other agents | `/coordinate` |
