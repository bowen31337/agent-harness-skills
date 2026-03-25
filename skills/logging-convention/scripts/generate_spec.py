#!/usr/bin/env python3
"""
generate_spec.py — Logging Convention document generator.

Generates a versioned SPEC.md (or JSON Schema) specifying the five required
log entry fields: timestamp, level, domain, trace_id, message.

Usage:
    python generate_spec.py [--output SPEC.md] [--version 1.0.0]
                            [--with-schema] [--format json]
                            [--stdout] [--validate <logfile>]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONVENTION_VERSION_DEFAULT = "1.0.0"
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

LOG_ENTRY_SCHEMA: dict = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://example.com/logging-convention/log_entry.schema.json",
    "title": "LogEntry",
    "description": (
        "A single structured log entry conforming to the Logging Convention Standard. "
        "All five required fields must be present and valid."
    ),
    "type": "object",
    "required": ["timestamp", "level", "domain", "trace_id", "message"],
    "additionalProperties": False,
    "properties": {
        "timestamp": {
            "type": "string",
            "format": "date-time",
            "description": "ISO-8601 UTC timestamp with millisecond precision (trailing Z required).",
            "examples": ["2026-03-22T14:22:05.123Z"],
        },
        "level": {
            "type": "string",
            "enum": ["DEBUG", "INFO", "WARN", "ERROR", "FATAL"],
            "description": "Severity level of the log entry (uppercase).",
        },
        "domain": {
            "type": "string",
            "pattern": r"^[a-zA-Z0-9_]+(\.[a-zA-Z0-9_]+)*$",
            "minLength": 1,
            "description": "Dot-separated originating service scope (e.g. payments.stripe.webhook).",
            "examples": ["payments.stripe.webhook", "auth.jwt", "http.server"],
        },
        "trace_id": {
            "type": "string",
            "pattern": "^[0-9a-f]{32}$",
            "description": "W3C-compatible 32-character lowercase hex trace identifier.",
            "examples": ["4bf92f3577b34da6a3ce929d0e0e4736"],
        },
        "message": {
            "type": "string",
            "minLength": 1,
            "description": "Human-readable description of the logged event (non-empty UTF-8).",
        },
        "extra": {
            "type": "object",
            "additionalProperties": True,
            "description": (
                "Optional additional key-value pairs. "
                "Keys must not shadow any of the five required field names."
            ),
        },
    },
}


# ---------------------------------------------------------------------------
# SPEC.md generation
# ---------------------------------------------------------------------------

def generate_spec(version: str = CONVENTION_VERSION_DEFAULT) -> str:
    """Return the full SPEC.md content as a string."""
    lines: list[str] = []

    def w(*args: str) -> None:  # append lines
        lines.extend(args)

    w(
        f"# Logging Convention Specification",
        f"",
        f"> **Version:** {version}  ",
        f"> **Status:** Active  ",
        f"> **Generated:** {TODAY}  ",
        f"> **Scope:** All services and libraries in this repository  ",
        f"",
        f"This document is the single source of truth for structured log entry format.",
        f"Every log entry emitted by any service, library, or script **MUST** conform to",
        f"this specification. Non-conforming entries will be rejected by the CI linter.",
        f"",
        f"---",
        f"",
    )

    # ── Required Fields ─────────────────────────────────────────────────────
    w(
        f"## Required Fields",
        f"",
        f"Every log entry MUST include all five fields below. No field may be omitted or null.",
        f"",
        f"| Field       | Type   | Format / Constraint                           | Example                              |",
        f"|-------------|--------|-----------------------------------------------|--------------------------------------|",
        f"| `timestamp` | string | ISO-8601 UTC, millisecond precision (`Z`)     | `\"2026-03-22T14:22:05.123Z\"`         |",
        f"| `level`     | string | One of: `DEBUG INFO WARN ERROR FATAL`         | `\"INFO\"`                             |",
        f"| `domain`    | string | Dot-separated, non-empty, no consecutive dots | `\"payments.stripe.webhook\"`          |",
        f"| `trace_id`  | string | Exactly 32 lowercase hex characters           | `\"4bf92f3577b34da6a3ce929d0e0e4736\"` |",
        f"| `message`   | string | Non-empty UTF-8, no length limit              | `\"Charge succeeded\"`                 |",
        f"",
        f"An optional `extra` object MAY be added for additional key-value pairs.",
        f"Keys inside `extra` MUST NOT shadow any of the five required field names.",
        f"",
        f"---",
        f"",
    )

    # ── Field Reference ──────────────────────────────────────────────────────
    w(
        f"## Field Reference",
        f"",
        f"### `timestamp`",
        f"",
        f"**Type:** `string`  ",
        f"**Format:** ISO-8601 UTC with millisecond precision  ",
        f"**Pattern:** `^\\d{{4}}-\\d{{2}}-\\d{{2}}T\\d{{2}}:\\d{{2}}:\\d{{2}}\\.\\d{{3}}Z$`",
        f"",
        f"The moment the log entry was created, expressed in Coordinated Universal Time.",
        f"Always include the trailing `Z` (Zulu / UTC offset). Sub-millisecond precision",
        f"is allowed but not required. Naive timestamps (no timezone suffix) are rejected.",
        f"",
        f"| Validity | Value | Reason |",
        f"|----------|-------|--------|",
        f'| ✅ Valid   | `"2026-03-22T14:22:05.123Z"` | Correct ISO-8601 UTC |',
        f'| ❌ Invalid | `"2026-03-22 14:22:05"` | Missing `T` separator and `Z` suffix |',
        f'| ❌ Invalid | `"2026-03-22T14:22:05+05:30"` | Non-UTC offset not permitted |',
        f"",
        f"---",
        f"",
        f"### `level`",
        f"",
        f"**Type:** `string`  ",
        f"**Allowed values:** `DEBUG` · `INFO` · `WARN` · `ERROR` · `FATAL`  ",
        f"**Case:** UPPERCASE only (input may be case-insensitive; normalized on write)",
        f"",
        f"| Value   | Semantic Meaning |",
        f"|---------|-----------------|",
        f"| `DEBUG` | Verbose developer information; disabled in production by default |",
        f"| `INFO`  | Normal operational events; expected in steady-state operation |",
        f"| `WARN`  | Recoverable anomaly; service continues but investigation is advised |",
        f"| `ERROR` | Unrecoverable failure in a single operation; service stays up |",
        f"| `FATAL` | Unrecoverable failure requiring process exit |",
        f"",
        f"Any value outside this set is rejected with a validation error.",
        f"",
        f"---",
        f"",
        f"### `domain`",
        f"",
        f"**Type:** `string`  ",
        f"**Pattern:** `^[a-zA-Z0-9_]+(\\.[a-zA-Z0-9_]+)*$`  ",
        f"**Convention:** reverse-hierarchical, dot-separated, lowercase preferred",
        f"",
        f"Identifies the originating service scope. Structure from coarse to fine:",
        f"",
        f"```",
        f"<service>.<subsystem>.<component>",
        f"```",
        f"",
        f"| Domain | Meaning |",
        f"|--------|---------|",
        f"| `payments` | Top-level payments service |",
        f"| `payments.stripe` | Stripe integration within payments |",
        f"| `payments.stripe.webhook` | Webhook handler inside Stripe integration |",
        f"| `auth.jwt` | JWT handling inside the auth service |",
        f"| `http.server` | HTTP layer (middleware-generated entries) |",
        f"",
        f"| Validity | Value | Reason |",
        f"|----------|-------|--------|",
        f'| ✅ Valid   | `"payments.stripe.webhook"` | Valid dot-separated domain |',
        f'| ❌ Invalid | `""` | Empty string |',
        f'| ❌ Invalid | `"payments..stripe"` | Consecutive dots |',
        f'| ❌ Invalid | `"payments "` | Trailing space |',
        f"",
        f"---",
        f"",
        f"### `trace_id`",
        f"",
        f"**Type:** `string`  ",
        f"**Pattern:** `^[0-9a-f]{{32}}$`  ",
        f"**Compatibility:** W3C Trace Context `traceparent` header (low 32 hex chars = trace ID)",
        f"",
        f"A 128-bit identifier expressed as 32 lowercase hexadecimal characters with no",
        f"hyphens or spaces. Every log entry within a single request or causal chain",
        f"MUST share the same `trace_id`, enabling log correlation across services.",
        f"",
        f"**Auto-generation:** When the caller does not supply a `trace_id`, the library",
        f"generates a random one using a cryptographically secure source.",
        f"",
        f"**W3C interop — extract from `traceparent` header:**",
        f"```",
        f"traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
        f"                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^",
        f"                 use these 32 chars as trace_id",
        f"```",
        f"",
        f"| Validity | Value | Reason |",
        f"|----------|-------|--------|",
        f'| ✅ Valid   | `"4bf92f3577b34da6a3ce929d0e0e4736"` | 32 lowercase hex chars |',
        f'| ❌ Invalid | `"4BF92F3577B34DA6A3CE929D0E0E4736"` | Uppercase hex rejected |',
        f'| ❌ Invalid | `"4bf92f35-77b3-4da6-a3ce-929d0e0e4736"` | UUID hyphens not allowed |',
        f'| ❌ Invalid | `"4bf92f35"` | Too short (8 chars instead of 32) |',
        f"",
        f"---",
        f"",
        f"### `message`",
        f"",
        f"**Type:** `string`  ",
        f"**Constraint:** non-empty UTF-8; no maximum length enforced at the contract layer",
        f"",
        f"A human-readable description of the event. Messages SHOULD be static strings",
        f"with dynamic values moved to `extra` keys — this enables log aggregation tools",
        f"to group distinct events reliably.",
        f"",
        f"```json",
        f"// ✅ Recommended — static message + extra fields",
        f'{{ "message": "Charge succeeded", "extra": {{ "amount": 1999, "currency": "usd" }} }}',
        f"",
        f"// ❌ Discouraged — dynamic message makes aggregation harder",
        f'{{ "message": "Charge of $19.99 USD succeeded for customer cus_abc123" }}',
        f"```",
        f"",
        f"| Validity | Value | Reason |",
        f"|----------|-------|--------|",
        f'| ✅ Valid   | `"Charge succeeded"` | Non-empty string |',
        f'| ❌ Invalid | `""` | Empty string |',
        f'| ❌ Invalid | `"   "` | Whitespace-only |',
        f"",
        f"---",
        f"",
    )

    # ── Compliant Example ────────────────────────────────────────────────────
    compliant_entry = {
        "timestamp": "2026-03-22T14:22:05.123Z",
        "level": "INFO",
        "domain": "payments.stripe.webhook",
        "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
        "message": "Charge succeeded",
        "extra": {
            "amount": 1999,
            "currency": "usd",
            "customer_id": "cus_abc123",
        },
    }
    ndjson_line = json.dumps(compliant_entry, separators=(",", ":"))
    pretty_json = json.dumps(compliant_entry, indent=2)

    w(
        f"## Compliant Example",
        f"",
        f"A log entry that passes all five field validations:",
        f"",
        f"```json",
        pretty_json,
        f"```",
        f"",
        f"As a single NDJSON line (as written to log files and stdout):",
        f"",
        f"```",
        ndjson_line,
        f"```",
        f"",
        f"---",
        f"",
    )

    # ── Non-Compliant Examples ───────────────────────────────────────────────
    w(
        f"## Non-Compliant Examples",
        f"",
        f"Each example below illustrates a common violation and the exact error it produces.",
        f"",
        f"| # | Violation | Offending value | Error message |",
        f"|---|-----------|-----------------|---------------|",
        f'| 1 | Missing `trace_id` | *(absent)* | `trace_id is required` |',
        f'| 2 | Naive timestamp | `"2026-03-22T14:22:05.123"` | `timestamp must be ISO-8601 UTC (trailing Z required)` |',
        f'| 3 | Invalid level | `"VERBOSE"` | `level must be one of DEBUG, INFO, WARN, ERROR, FATAL` |',
        f'| 4 | Empty domain | `""` | `domain must be a non-empty dot-separated string` |',
        f'| 5 | Uppercase trace_id | `"4BF92F3577B34DA6A3CE929D0E0E4736"` | `trace_id must be 32 lowercase hex characters` |',
        f'| 6 | Whitespace message | `"   "` | `message must be a non-empty string` |',
        f"",
        f"---",
        f"",
    )

    # ── JSON Schema ──────────────────────────────────────────────────────────
    schema_json = json.dumps(LOG_ENTRY_SCHEMA, indent=2)
    w(
        f"## JSON Schema",
        f"",
        f"The canonical schema is published at `schemas/log_entry.schema.json` and at",
        f"the stable public URL `docs/schema/log_entry.schema.json`.",
        f"",
        f"```json",
        schema_json,
        f"```",
        f"",
        f"---",
        f"",
    )

    # ── Adoption Guide ───────────────────────────────────────────────────────
    w(
        f"## Adoption Guide",
        f"",
        f"### Python",
        f"",
        f"```python",
        f"from logging_convention import get_logger, configure, StdoutTransport, set_trace_id",
        f"",
        f"# 1. Configure once at service startup",
        f"configure([StdoutTransport()])",
        f"",
        f"# 2. Create a domain-bound logger",
        f'log = get_logger("payments.stripe.webhook")',
        f"",
        f"# 3. Wrap each request with a trace context",
        f'with set_trace_id("4bf92f3577b34da6a3ce929d0e0e4736"):',
        f'    log.info("Charge succeeded", amount=1999, currency="usd")',
        f'    # → {{"timestamp":"…","level":"INFO","domain":"payments.stripe.webhook",',
        f'    #    "trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","message":"Charge succeeded",',
        f'    #    "extra":{{"amount":1999,"currency":"usd"}}}}',
        f"```",
        f"",
        f"### TypeScript / Node.js",
        f"",
        f"```typescript",
        f'import {{ createLogger }} from "logging-convention";',
        f"",
        f'const log = createLogger("payments.stripe.webhook");',
        f"",
        f'log.info("Charge succeeded", {{',
        f'  traceId: "4bf92f3577b34da6a3ce929d0e0e4736",',
        f"  extra:   {{ amount: 1999, currency: \"usd\" }},",
        f"}});",
        f"```",
        f"",
        f"### Go",
        f"",
        f"```go",
        f'import "github.com/your-org/logging-convention"',
        f"",
        f'logger := convention.NewLogger("payments.stripe.webhook")',
        f'logger.Info(ctx, "Charge succeeded",',
        f'    convention.Field("amount", 1999),',
        f'    convention.Field("currency", "usd"),',
        f")",
        f"// trace_id is extracted from ctx (OpenTelemetry span or custom header)",
        f"```",
        f"",
        f"### Java",
        f"",
        f"```java",
        f"import com.example.logging.Logger;",
        f"",
        f'Logger logger = Logger.forDomain("payments.stripe.webhook");',
        f'logger.info("Charge succeeded",',
        f'    Map.of("amount", 1999, "currency", "usd"));',
        f"// trace_id propagated via MDC / OpenTelemetry context",
        f"```",
        f"",
        f"---",
        f"",
    )

    # ── CLI Reference ────────────────────────────────────────────────────────
    w(
        f"## CLI Reference (`log-lint`)",
        f"",
        f"Install: `uv add logging-convention`",
        f"",
        f"| Command | Description |",
        f"|---------|-------------|",
        f"| `log-lint validate <file>` | Validate every NDJSON line; exit 1 on any violation |",
        f"| `log-lint validate --strict <file>` | Also fail on unknown top-level keys |",
        f"| `log-lint validate --output=json <file>` | Emit machine-readable validation results |",
        f"| `log-lint stats <file>` | Summary: total lines, counts by level, unique domains, unique trace_ids |",
        f"| `log-lint trace <trace_id> <file>` | Extract all entries matching a given trace_id |",
        f"| `log-lint domain <domain> <file>` | Filter entries by domain prefix |",
        f"| `log-lint convert --from=logfmt --to=json <file>` | Convert logfmt to compliant NDJSON |",
        f"| `log-lint check-schema` | Print active JSON Schema version and public URL |",
        f"",
        f"**Pipe support:** Replace `<file>` with `-` to read from stdin:",
        f"```bash",
        f"kubectl logs my-pod | log-lint validate -",
        f"```",
        f"",
        f"**CI integration example (GitHub Actions):**",
        f"```yaml",
        f"- name: Validate logs",
        f"  run: log-lint validate --output=json service.log",
        f"```",
        f"",
        f"---",
        f"",
    )

    # ── Changelog ────────────────────────────────────────────────────────────
    w(
        f"## Changelog",
        f"",
        f"| Version | Date       | Type    | Change |",
        f"|---------|------------|---------|--------|",
        f"| {version}   | {TODAY} | Initial | First release of the logging convention specification |",
        f"",
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Validation (simple inline validator — no external deps required)
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {"timestamp", "level", "domain", "trace_id", "message"}
ALLOWED_LEVELS = {"DEBUG", "INFO", "WARN", "ERROR", "FATAL"}
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
DOMAIN_RE = re.compile(r"^[a-zA-Z0-9_]+(\.[a-zA-Z0-9_]+)*$")
TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def validate_entry(entry: dict) -> list[str]:
    """Return a list of validation error strings (empty = valid)."""
    errors: list[str] = []

    for field in REQUIRED_FIELDS:
        if field not in entry:
            errors.append(f"missing field: {field}")
            return errors  # can't validate further without required fields

    ts = entry["timestamp"]
    if not isinstance(ts, str) or not TIMESTAMP_RE.match(ts):
        errors.append(
            f"timestamp must be ISO-8601 UTC with millisecond precision and trailing Z "
            f"(got: {ts!r})"
        )

    lvl = entry["level"]
    if lvl not in ALLOWED_LEVELS:
        errors.append(
            f"level must be one of {', '.join(sorted(ALLOWED_LEVELS))} (got: {lvl!r})"
        )

    dom = entry["domain"]
    if not isinstance(dom, str) or not DOMAIN_RE.match(dom):
        errors.append(
            f"domain must be a non-empty dot-separated string matching "
            f"^[a-zA-Z0-9_]+(\\.[a-zA-Z0-9_]+)*$ (got: {dom!r})"
        )

    tid = entry["trace_id"]
    if not isinstance(tid, str) or not TRACE_ID_RE.match(tid):
        errors.append(
            f"trace_id must be exactly 32 lowercase hex characters (got: {tid!r})"
        )

    msg = entry["message"]
    if not isinstance(msg, str) or not msg.strip():
        errors.append(f"message must be a non-empty string (got: {msg!r})")

    extra = entry.get("extra")
    if extra is not None:
        if not isinstance(extra, dict):
            errors.append("extra must be an object (dict)")
        else:
            shadowed = REQUIRED_FIELDS & extra.keys()
            if shadowed:
                errors.append(
                    f"extra keys must not shadow required fields: {sorted(shadowed)}"
                )

    return errors


def validate_file(log_path: str) -> int:
    """Validate an NDJSON log file. Returns exit code (0=ok, 1=violations)."""
    path = Path(log_path)
    if not path.exists():
        print(f"❌  File not found: {log_path}", file=sys.stderr)
        return 2

    total = 0
    violations: list[tuple[int, str]] = []

    with path.open(encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw:
                continue
            total += 1
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError as exc:
                violations.append((lineno, f"invalid JSON: {exc}"))
                continue
            for err in validate_entry(entry):
                violations.append((lineno, err))

    valid = total - len({ln for ln, _ in violations})
    print(f"\n📋  Validation: {log_path}")
    print(f"    Lines:    {total:>6}")
    print(f"    Valid:    {valid:>6}  {'✅' if not violations else ''}")
    print(f"    Invalid:  {len(violations):>6}  {'❌' if violations else '✅'}")

    if violations:
        print()
        for lineno, msg in violations:
            print(f"    Line {lineno:>6}  {msg}")
        return 1

    print(f"\n    All {total} lines conform to the logging convention.")
    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate the Logging Convention SPEC.md document.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--output", default="SPEC.md",
        help="Output path for SPEC.md (default: SPEC.md)",
    )
    parser.add_argument(
        "--version", default=CONVENTION_VERSION_DEFAULT,
        help=f"Convention version header (default: {CONVENTION_VERSION_DEFAULT})",
    )
    parser.add_argument(
        "--with-schema", action="store_true",
        help="Also write schemas/log_entry.schema.json",
    )
    parser.add_argument(
        "--format", choices=["markdown", "json"], default="markdown",
        help="Output format: markdown (default) or json (schema only)",
    )
    parser.add_argument(
        "--stdout", action="store_true",
        help="Print to stdout instead of writing a file",
    )
    parser.add_argument(
        "--validate", metavar="LOGFILE",
        help="Validate an NDJSON log file and report violations",
    )

    args = parser.parse_args()

    # Validate mode
    if args.validate:
        return validate_file(args.validate)

    # JSON Schema only
    if args.format == "json":
        schema_str = json.dumps(LOG_ENTRY_SCHEMA, indent=2)
        if args.stdout:
            print(schema_str)
            return 0
        schema_path = Path(args.output) if args.output != "SPEC.md" else Path("schemas/log_entry.schema.json")
        schema_path.parent.mkdir(parents=True, exist_ok=True)
        schema_path.write_text(schema_str + "\n", encoding="utf-8")
        print(f"✅  JSON Schema written → {schema_path}")
        print(f"    Draft   : 2020-12")
        print(f"    Required: timestamp · level · domain · trace_id · message")
        return 0

    # Markdown generation
    spec_content = generate_spec(version=args.version)

    if args.stdout:
        print(spec_content)
    else:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(spec_content, encoding="utf-8")

        schema_path: Path | None = None
        if args.with_schema:
            schema_path = out.parent / "schemas" / "log_entry.schema.json"
            schema_path.parent.mkdir(parents=True, exist_ok=True)
            schema_path.write_text(json.dumps(LOG_ENTRY_SCHEMA, indent=2) + "\n", encoding="utf-8")

        print(f"\n✅  SPEC.md written → {out}")
        print(f"    Version  : {args.version}")
        print(f"    Fields   : timestamp · level · domain · trace_id · message")
        print(f"    Schema   : {schema_path or 'not requested'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
