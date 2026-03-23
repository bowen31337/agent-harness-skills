---
name: logging-convention
description: "Generates a versioned SPEC.md (or SPEC.json) logging convention document specifying the five required fields every log entry must carry: timestamp, level, domain, trace_id, message. Validates existing NDJSON log files against the convention. Use when bootstrapping a new service that needs a structured logging standard, generating a canonical SPEC.md, or producing a machine-readable JSON Schema for cross-language log validation. Triggers on: logging convention, log spec, log entry fields, structured logging, trace_id, NDJSON, log schema, observability contract, generate SPEC.md, logging standard."
---

# Logging Convention Skill

## Overview

The Logging Convention skill generates a **versioned, language-agnostic logging
convention document** that defines the exact structure every log entry must follow.
It also validates existing NDJSON log files against the convention.

| Capability | Description |
|-----------|-------------|
| **Generate SPEC.md** | Write a full convention document with field definitions, examples, JSON Schema, and adoption guide |
| **Generate JSON Schema** | Emit a draft-2020-12 JSON Schema for cross-language validator integration |
| **Validate log file** | Run `log-lint validate` and report any non-conforming lines |

The five required fields:

| Field | Type | Constraint |
|-------|------|-----------|
| `timestamp` | ISO-8601 UTC string | Millisecond precision, trailing `Z` required |
| `level` | Enum string | `DEBUG` · `INFO` · `WARN` · `ERROR` · `FATAL` |
| `domain` | Dot-separated string | Non-empty; no consecutive dots; e.g. `payments.stripe.webhook` |
| `trace_id` | Hex string | Exactly 32 lowercase hex chars; W3C Trace Context compatible |
| `message` | UTF-8 string | Non-empty; no maximum length |

---

## Workflow

```
invoke /logging-convention [args]
         │
         ├─ --format json OR --with-schema?
         │         └─ Write schemas/log_entry.schema.json
         │
         ├─ --validate <logfile>?
         │         └─ Run log-lint, print summary, mirror exit code
         │
         └─ default (Markdown generation)
                   └─ Write SPEC.md to --output path
```

---

## CLI Usage

```bash
# Generate SPEC.md in the current directory
python skills/logging-convention/scripts/generate_spec.py

# Write to a custom path
python skills/logging-convention/scripts/generate_spec.py \
    --output docs/logging/SPEC.md

# Also emit the JSON Schema
python skills/logging-convention/scripts/generate_spec.py \
    --with-schema

# Emit only the JSON Schema (no Markdown)
python skills/logging-convention/scripts/generate_spec.py \
    --format json

# Bump the convention version
python skills/logging-convention/scripts/generate_spec.py \
    --version 2.0.0

# Print to stdout
python skills/logging-convention/scripts/generate_spec.py \
    --stdout

# Validate an existing NDJSON log file
python skills/logging-convention/scripts/generate_spec.py \
    --validate service.log
```

---

## Generated Document Sections

The SPEC.md produced by this skill contains the following sections in order:

1. **Header** — version, status, generated date, scope statement
2. **Required Fields** — summary table of the five required fields
3. **Field Reference** — one subsection per field with pattern, semantics, valid/invalid examples
4. **Compliant Example** — a complete, valid NDJSON entry (pretty-printed + single-line)
5. **Non-Compliant Examples** — six common violations with error messages
6. **JSON Schema** — embedded draft-2020-12 schema for copy-paste integration
7. **Adoption Guide** — language-specific snippets (Python, TypeScript, Go, Java)
8. **CLI Reference** — `log-lint` commands and CI integration example
9. **Changelog** — versioned change history

---

## Field Reference

### `timestamp`

- **Type:** `string`
- **Pattern:** `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$`
- **Rejection:** `None`, naive (no timezone), non-UTC offset, not a datetime
- **Valid:** `"2026-03-22T14:22:05.123Z"`
- **Invalid:** `"2026-03-22 14:22:05"`, `"2026-03-22T14:22:05+05:30"`

### `level`

- **Type:** `string` (UPPERCASE)
- **Allowed:** `DEBUG` · `INFO` · `WARN` · `ERROR` · `FATAL`
- **Rejection:** Any value outside the allowed set (case-insensitive input normalized on write)

| Value | Semantic Meaning |
|-------|-----------------|
| `DEBUG` | Verbose developer info; disabled in production by default |
| `INFO` | Normal operational events |
| `WARN` | Recoverable anomaly; service continues |
| `ERROR` | Unrecoverable failure in one operation; service stays up |
| `FATAL` | Unrecoverable failure requiring process exit |

### `domain`

- **Type:** `string`
- **Pattern:** `^[a-zA-Z0-9_]+(\.[a-zA-Z0-9_]+)*$`
- **Convention:** reverse-hierarchical, dot-separated, lowercase preferred
- **Rejection:** empty string, whitespace-only, consecutive dots (`..`)

| Domain | Meaning |
|--------|---------|
| `payments` | Top-level payments service |
| `payments.stripe` | Stripe integration |
| `payments.stripe.webhook` | Webhook handler |
| `auth.jwt` | JWT handling in auth service |
| `http.server` | HTTP middleware layer |

### `trace_id`

- **Type:** `string`
- **Pattern:** `^[0-9a-f]{32}$`
- **Compatibility:** W3C Trace Context `traceparent` — low 32 hex chars
- **Auto-generation:** Library generates a random ID when caller passes `None`
- **Rejection:** uppercase hex, UUID hyphens, wrong length

```
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ ← use these 32 chars
```

### `message`

- **Type:** `string`
- **Constraint:** non-empty UTF-8; no max length
- **Rejection:** empty string, whitespace-only
- **Best practice:** use static strings; move dynamic values to `extra`

```json
✅  {"message": "Charge succeeded", "extra": {"amount": 1999}}
❌  {"message": "Charge of $19.99 USD succeeded"}
```

---

## Compliant Entry (NDJSON)

```json
{"timestamp":"2026-03-22T14:22:05.123Z","level":"INFO","domain":"payments.stripe.webhook","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","message":"Charge succeeded","extra":{"amount":1999,"currency":"usd","customer_id":"cus_abc123"}}
```

---

## JSON Schema (draft-2020-12)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.com/logging-convention/log_entry.schema.json",
  "title": "LogEntry",
  "type": "object",
  "required": ["timestamp", "level", "domain", "trace_id", "message"],
  "additionalProperties": false,
  "properties": {
    "timestamp": { "type": "string", "format": "date-time" },
    "level":     { "type": "string", "enum": ["DEBUG","INFO","WARN","ERROR","FATAL"] },
    "domain":    { "type": "string", "pattern": "^[a-zA-Z0-9_]+(\\.[a-zA-Z0-9_]+)*$", "minLength": 1 },
    "trace_id":  { "type": "string", "pattern": "^[0-9a-f]{32}$" },
    "message":   { "type": "string", "minLength": 1 },
    "extra":     { "type": "object", "additionalProperties": true }
  }
}
```

---

## Output Example

After a successful run:

```
✅  SPEC.md written → SPEC.md
    Version  : 1.0.0
    Fields   : timestamp · level · domain · trace_id · message
    Schema   : schemas/log_entry.schema.json
```

After `--validate service.log`:

```
📋  Validation: service.log
    Lines:    1 234
    Valid:    1 230  ✅
    Invalid:      4  ❌

    Line   12  missing field: trace_id
    Line   45  level "VERBOSE" not in allowed set
    Line  210  timestamp missing UTC offset (Z)
    Line  891  trace_id "ABC123" is not 32 lowercase hex chars
```

---

## Key Files

| Path | Purpose |
|------|---------|
| `.claude/commands/logging-convention.md` | Claude slash-command definition |
| `skills/logging-convention/SKILL.md` | This file — implementation documentation |
| `skills/logging-convention/scripts/generate_spec.py` | CLI script to generate SPEC.md / schema |
| `spec/logging_convention_spec.txt` | Source project specification (128 features across 9 categories) |
| `schemas/log_entry.schema.json` | Generated JSON Schema output |
| `SPEC.md` | Generated convention document (primary output) |

---

## Options

| Flag | Effect |
|------|--------|
| `--output <path>` | Write SPEC.md to this path (default: `SPEC.md`) |
| `--version <semver>` | Convention version header (default: `1.0.0`) |
| `--with-schema` | Also write `schemas/log_entry.schema.json` |
| `--format json` | Write JSON Schema only |
| `--stdout` | Print to stdout instead of writing a file |
| `--validate <logfile>` | Validate NDJSON log file and report violations |
