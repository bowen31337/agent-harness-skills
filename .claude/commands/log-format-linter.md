# Log Format Linter

Generate structured-log linter rules for a codebase and check every log statement
for compliance with the five required fields: **timestamp**, **level**, **domain**,
**trace_id**, and **message**.

`timestamp` and `level` are managed by the logging framework itself.  `message` is
the human-readable log string.  The fields agents must verify on every call site are:

| Field | Requirement |
|---|---|
| `domain` | Non-empty dot-separated string identifying the service scope (e.g. `"payments.stripe.webhook"`) |
| `trace_id` | 32-character lowercase hex string, W3C Trace Context compatible |

Additional fields can be required via `--fields` (see Options).

---

## Usage

```bash
# Auto-detect framework, check all source files under src/
/log-format-linter check src/

# Check a single file
/log-format-linter check src/api/payments.py

# Print generated rules + examples for a specific framework
/log-format-linter rules python_logging

# Auto-detect which logging framework a codebase uses
/log-format-linter detect src/

# Require extra fields beyond domain + trace_id
/log-format-linter check src/ --fields domain trace_id request_id

# Emit machine-readable JSON (useful for CI integration)
/log-format-linter check src/ --output json
```

---

## Instructions

### Step 1 — Parse the sub-command

Determine which sub-command was requested:

| Sub-command | Action |
|---|---|
| `check <path>` | Scan source files for structured-log violations (→ Step 2) |
| `rules <framework>` | Print generated rules + examples for a framework (→ Step 5) |
| `detect <path>` | Auto-detect the logging framework (→ Step 6) |

If no sub-command is provided, default to `check .` (scan the current directory).

---

### Step 2 — Detect the logging framework

If `--framework` was not explicitly passed, auto-detect it:

```bash
python - <<'EOF'
from log_format_linter import detect_framework
fw = detect_framework(".")
print(fw.value)
EOF
```

Or via the CLI:

```bash
python -m log_format_linter.cli detect . --output json 2>/dev/null
```

Supported frameworks:

| Framework | Language | `--framework` value |
|---|---|---|
| stdlib `logging` | Python | `python_logging` |
| `structlog` | Python | `structlog` |
| `loguru` | Python | `loguru` |
| `winston` | TypeScript/JS | `winston` |
| `pino` | TypeScript/JS | `pino` |
| `bunyan` | TypeScript/JS | `bunyan` |
| `zap` | Go | `zap` |
| `logrus` | Go | `logrus` |
| `zerolog` | Go | `zerolog` |

If detection returns `unknown`, proceed with the default `python_logging` rules and
note the fallback in the output.

---

### Step 3 — Generate linter rules

Generate the rules for the detected (or specified) framework:

```bash
python - <<'EOF'
import json
from log_format_linter import generate_rules, LogFramework, LogLinterConfig

framework = LogFramework("<detected_framework>")
fields = <required_fields>          # e.g. ["domain", "trace_id"]
config = LogLinterConfig(required_fields=fields)
result = generate_rules(framework, config=config)

print(json.dumps({
    "framework": result.framework.value,
    "language": result.language.value,
    "check_strategy": result.rules.get("check_strategy"),
    "patterns": result.rules.get("patterns", {}),
    "description": result.description,
    "examples": result.examples,
}, indent=2))
EOF
```

Or via the CLI:

```bash
python -m log_format_linter.cli rules <framework> \
    --fields <fields...> \
    --output json
```

Capture the generated rules — you will display them in the final report.

---

### Step 4 — Check source files for violations

```bash
python -m log_format_linter.cli check <path> \
    --framework <framework> \
    --fields <fields...> \
    --severity <error|warning|info> \
    --output json \
    2>/dev/null
```

Or programmatically:

```bash
python - <<'EOF'
import json
from pathlib import Path
from log_format_linter import check_directory, check_file, LogLinterConfig, LogFramework

path = Path("<path>")
config = LogLinterConfig(
    required_fields=<fields>,
    framework=LogFramework("<framework>"),
)

if path.is_dir():
    violations = check_directory(path, config=config)
else:
    violations = check_file(path, config=config)

print(json.dumps([
    {
        "file": str(v.file),
        "line": v.line,
        "column": v.column,
        "severity": v.severity.value,
        "rule": v.rule,
        "message": v.message,
        "snippet": v.snippet,
    }
    for v in violations
], indent=2))
EOF
```

Parse the JSON array of violations.  A violation means a log call site is missing
one or more of the required structured fields.

---

### Step 5 — `rules` sub-command (standalone)

When the user invokes `rules <framework>` directly, run Step 3 above and emit the
human-readable report from **Step 7** with zero violations but with the rules and
examples sections populated.  Skip Steps 2 and 4.

---

### Step 6 — `detect` sub-command (standalone)

When the user invokes `detect <path>` directly:

```bash
python -m log_format_linter.cli detect <path> --output json
```

Emit a brief human-readable result:

```
Detected framework: <framework>
Language:           <language>
```

Then emit the machine-readable manifest (Step 8).  No violation scanning is
performed.

---

### Step 7 — Render the human-readable report

#### Header

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Log Format Linter — <PASS ✅ | FAIL ❌>
  <N> violation(s)  ·  framework: <framework>  ·  fields: <fields>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

#### Generated rules summary

```
Generated Rules
────────────────────────────────────────────────────
  Framework:       <framework>
  Language:        <language>
  Check strategy:  <check_strategy>
  Required fields: <fields>

  Detection pattern:
    <log_call pattern>

  Field-presence strategy: <description>
```

#### Good/bad examples (always shown)

```
✅ Compliant examples
────────────────────────────────────────────────────
  <good example 1>
  <good example 2>

❌ Non-compliant examples
────────────────────────────────────────────────────
  <bad example 1>
  <bad example 2>
```

#### Violations section (only when violations > 0)

```
Violations
────────────────────────────────────────────────────
  <file>:<line>:<col>  [<severity>]  <message>
    > <source snippet>

  <file>:<line>:<col>  [<severity>]  <message>
    > <source snippet>

  ...

  <N> violation(s) found in <M> file(s).
```

Group violations by file for readability.  Within each file, show them in
line-number order.

#### Clean result (no violations)

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅ All log statements carry the required structured fields.
  0 violations · <N> files checked · fields: <fields>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### Step 8 — Emit the machine-readable manifest

Always append a fenced JSON block so downstream agents can parse the result
without re-running the linter:

```json
{
  "command": "log-format-linter check",
  "path": "<scanned path>",
  "framework": "<framework>",
  "language": "<language>",
  "required_fields": ["domain", "trace_id"],
  "check_strategy": "<check_strategy>",
  "passed": true,
  "total_violations": 0,
  "files_checked": 12,
  "violations": [],
  "rules": {
    "rule_id": "structured-log-fields",
    "patterns": { ... },
    "examples": { "good": [...], "bad": [...] }
  }
}
```

When violations are present, populate the `violations` array:

```json
{
  "command": "log-format-linter check",
  "path": "src/",
  "framework": "python_logging",
  "language": "python",
  "required_fields": ["domain", "trace_id"],
  "check_strategy": "regex+extra-dict",
  "passed": false,
  "total_violations": 3,
  "files_checked": 8,
  "violations": [
    {
      "file": "src/api/payments.py",
      "line": 44,
      "column": 4,
      "severity": "error",
      "rule": "structured-log-fields",
      "message": "Log call missing required structured fields: ['trace_id']",
      "snippet": "    logger.info('charge created', extra={'domain': 'payments'})"
    }
  ],
  "rules": {
    "rule_id": "structured-log-fields",
    "patterns": {
      "log_call": "\\b(?:logger|logging|log)\\.(debug|info|warning|warn|error|critical|exception)\\s*\\(",
      "extra_kwarg": "\\bextra\\s*=\\s*\\{",
      "required_keys": ["domain", "trace_id"]
    },
    "examples": {
      "good": ["logger.info('user signed in', extra={'domain': 'svc.auth', 'trace_id': ctx.trace_id})"],
      "bad":  ["logger.info('user signed in')"]
    }
  }
}
```

---

### Step 9 — Exit behaviour

| Outcome | Exit code |
|---|---|
| No violations | `0` |
| One or more `error`-severity violations | `1` |
| One or more `warning`-severity violations (no errors) | `0` (but shown in report) |
| Bad path / unknown framework / CLI error | `2` |

---

## Options

| Flag | Effect |
|---|---|
| `--fields FIELD...` | Override required fields (default: `domain trace_id`) |
| `--framework FRAMEWORK` | Override auto-detected logging framework |
| `--severity error\|warning\|info` | Severity assigned to violations (default: `error`) |
| `--ignore PATTERN...` | Glob patterns for files/directories to skip |
| `--output text\|json` | Output format: human-readable text (default) or raw JSON |

---

## Supported check strategies

| Strategy | Frameworks | What it checks |
|---|---|---|
| `regex+extra-dict` | `python_logging` | `extra={"field": ...}` keyword arg |
| `regex+kwargs` | `structlog` | `field=...` keyword arguments |
| `regex+bind-or-kwargs` | `loguru` | `.bind(field=...)` or inline kwargs |
| `regex+object-keys` | `winston`, `pino`, `bunyan` | `{ field: ... }` first object arg |
| `regex+zap-fields` | `zap` | `zap.String("field", ...)` positional args |
| `regex+with-fields` | `logrus` | `.WithFields(logrus.Fields{"field": ...})` |
| `regex+zerolog-chain` | `zerolog` | `.Str("field", ...)` method chain |

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Enforce structured logging in a new service | **`/log-format-linter check src/`** ← you are here |
| See the rules + examples for a framework | **`/log-format-linter rules <framework>`** |
| Identify which logging library is in use | **`/log-format-linter detect src/`** |
| Full code quality sweep (lint, types, tests) | `/check-code` |
| Validate an NDJSON log file at runtime | `log-lint validate <file>` (CLI) |

---

## Notes

- **Read-only** — this skill never modifies source files.
- Detection is **regex-based**, not AST-based.  It handles the common multi-line
  case (up to 6 source lines per call site) but may produce false positives for log
  calls inside strings or comments.
- Files that do not `import` the detected framework are skipped automatically,
  preventing noise from test fixtures or vendored code.
- **CI integration**: run with `--output json` and parse the `passed` field to gate
  the pipeline on structured-log compliance.
- To add more required fields (e.g. `request_id`), use
  `--fields domain trace_id request_id`.
- The `domain` and `trace_id` defaults align with the
  [Logging Convention Spec](../docs/SPEC.md) and its JSON Schema at
  `schemas/log_entry.schema.json`.
