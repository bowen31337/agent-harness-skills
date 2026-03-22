# Harness Observe

Tail the **structured NDJSON log stream** produced by `harness_skills.logging_config`
in real time, with optional filtering by **domain prefix** or **exact trace_id**.

Each log entry follows the five-field convention:

| Field | Format | Source |
|---|---|---|
| `timestamp` | ISO-8601 UTC, millisecond precision | auto — formatter |
| `level` | `DEBUG` / `INFO` / `WARN` / `ERROR` / `FATAL` | auto — logging level |
| `domain` | dot-separated string (e.g. `harness.auth`) | caller — `get_logger()` |
| `trace_id` | 32-char lowercase hex (W3C) | context var / auto-gen |
| `message` | non-empty UTF-8 string | caller — log call |

Use this skill to watch logs live while a plan runs, trace a single request across
every domain, or do a targeted post-mortem scan.

---

## Usage

```bash
# Tail everything in real time (pretty, ANSI-coloured)
/harness:observe

# Filter to a domain subtree — matches harness, harness.auth, harness.task_lock, …
/harness:observe --domain harness.auth

# Trace one request end-to-end across every domain
/harness:observe --trace-id 4bf92f3577b34da6a3ce929d0e0e4736

# Combine both filters: trace within a single domain
/harness:observe --domain harness.payments --trace-id 4bf92f3577b34da6a3ce929d0e0e4736

# Show only ERROR and above from the last 200 lines, then exit
/harness:observe --level ERROR --lines 200 --no-follow

# Pipe raw NDJSON to jq (disables colour automatically)
/harness:observe --format json --domain harness | jq '{ts: .timestamp, msg: .message}'

# Non-default log file
/harness:observe --log-file /var/log/harness/app.ndjson --domain harness.gates

# Print last 100 lines without following, emit session summary to stderr
/harness:observe --lines 100 --no-follow --format json
```

---

## Instructions

### Step 1 — Locate the log file

Determine which NDJSON log file to tail.  Check in order:

1. If `--log-file` was passed explicitly, use that path.
2. Otherwise use the default: `logs/harness.ndjson`

Verify the file exists:

```bash
ls -lh logs/harness.ndjson 2>/dev/null || echo "__NOT_FOUND__"
```

If the file is missing and `--follow` mode is active (the default), the command
waits for the file to appear — no manual intervention is needed.  In `--no-follow`
mode a missing file exits immediately with code `1`.

---

### Step 2 — Build the command

Compose the `harness observe` invocation with the required flags.

```bash
uv run harness observe \
  [--log-file PATH]          \   # default: logs/harness.ndjson
  [--domain DOMAIN]          \   # prefix filter (dot-boundary aware)
  [--trace-id TRACE_ID]      \   # exact 32-char hex match
  [--level DEBUG|INFO|WARN|ERROR|FATAL]  \  # minimum severity (default: DEBUG)
  [--lines N]                \   # trailing lines to scan first (default: 50)
  [--follow|--no-follow]     \   # stream continuously (default: --follow)
  [--format pretty|json]     \   # output format (default: pretty)
  [--no-color]                   # strip ANSI codes
```

> **Fallback** — if `uv` is unavailable:
>
> ```bash
> python -m harness_skills.cli.main observe [flags]
> ```

**Exit codes:**

| Code | Meaning |
|---|---|
| `0` | Session ended normally (Ctrl-C in follow mode, or `--no-follow` scan complete) |
| `1` | Log file not found and `--no-follow` was set |
| `2` | Internal error (e.g. unreadable file, unexpected exception) |

---

### Step 3 — Interpret live output (follow mode)

In the default `--follow` mode the command:

1. Prints the last `--lines` (default 50) matching entries from existing content.
2. Emits a separator and a banner to **stderr**:
   ```
   ────────────────────────────────────────────────────────────
   [harness:observe] Tailing logs/harness.ndjson  domain='harness.auth'  (Ctrl-C to stop)
   ```
3. Streams every new matching line as it is appended to the file.
4. Handles log rotation automatically — if the file shrinks, the tail restarts from
   the beginning of the new file.

**Pretty format** (default — human terminal):

```
2026-03-22T14:22:05.123Z  INFO   harness.auth     [4bf92f35]  user signed in  user_id='u-42'
2026-03-22T14:22:05.891Z  ERROR  harness.auth     [4bf92f35]  token expired   ttl_s=0
2026-03-22T14:22:06.042Z  DEBUG  harness.payments [4bf92f35]  charge queued   amount=9.99
```

Column layout: `<timestamp>  <LEVEL>  <domain>  [<trace8>]  <message>  <extra k=v …>`

Level colours (ANSI, disabled automatically when stdout is not a TTY):

| Level | Colour |
|---|---|
| `DEBUG` | cyan |
| `INFO` | green |
| `WARN` | yellow |
| `ERROR` | red |
| `FATAL` | bright red + bold |

**JSON format** (`--format json` — pipe-friendly):

Each emitted line is a validated `LogEntry` JSON object:

```json
{"timestamp":"2026-03-22T14:22:05.123Z","level":"INFO","domain":"harness.auth","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","message":"user signed in","extra":{"user_id":"u-42"}}
```

If an entry fails `LogEntry` schema validation, the raw unparsed line is emitted
unchanged — no data is lost — and the `validation_errors` counter increments in
the session summary.

---

### Step 4 — Domain filter semantics

The `--domain` filter uses **dot-boundary-aware prefix matching**:

| Filter value | Matches | Does NOT match |
|---|---|---|
| `harness` | `harness`, `harness.auth`, `harness.task_lock` | `harness2`, `pay` |
| `harness.auth` | `harness.auth`, `harness.auth.jwt` | `harness`, `harness.payments` |
| `payments` | `payments`, `payments.stripe` | `pay`, `payment` |

Rule: entry domain `D` matches filter `F` when `D == F` or `D.startswith(F + ".")`.

---

### Step 5 — No-follow mode: parse the session summary

When `--no-follow` is passed the command scans the trailing `--lines` entries,
prints matching ones, then emits an `ObserveResponse` JSON object to **stderr** and
exits.

Capture and parse it:

```bash
harness observe --no-follow --domain harness.auth --level WARN \
  2>summary.json
cat summary.json
```

#### `ObserveResponse` fields

| Field | Type | Description |
|---|---|---|
| `command` | str | Always `"harness observe"` |
| `log_file` | str | Path to the tailed NDJSON file |
| `lines_scanned` | int ≥ 0 | Total non-empty lines read (before filtering) |
| `entries_matched` | int ≥ 0 | Lines that passed all active filters |
| `entries_emitted` | int ≥ 0 | Matched entries successfully written to stdout |
| `validation_errors` | int ≥ 0 | Matched entries that failed `LogEntry` schema validation |
| `domain_filter` | str \| null | Active `--domain` prefix, or `null` |
| `trace_id_filter` | str \| null | Active `--trace-id` value, or `null` |
| `min_level` | str | Minimum level filter applied (e.g. `"WARN"`) |

**Example `ObserveResponse`:**

```json
{
  "command": "harness observe",
  "log_file": "logs/harness.ndjson",
  "lines_scanned": 200,
  "entries_matched": 12,
  "entries_emitted": 12,
  "validation_errors": 0,
  "domain_filter": "harness.auth",
  "trace_id_filter": null,
  "min_level": "WARN"
}
```

**Diagnostic signals from the summary:**

| Condition | Meaning | Action |
|---|---|---|
| `entries_matched == 0` | No log lines matched the filters | Widen filters or check the domain name |
| `validation_errors > 0` | Some entries don't conform to the five-field convention | Investigate the logger emitting non-standard entries |
| `entries_matched == lines_scanned` | Every scanned line matched (no filtering effect) | Filters may be too broad; tighten `--domain` or `--level` |

---

### Step 6 — Tracing a request end-to-end

To follow a single request across every domain, obtain its `trace_id` from any
matching log line and then pass it as a filter:

```bash
# 1. Find a trace_id associated with a failure
harness observe --no-follow --level ERROR --format json \
  | jq -r '.trace_id' | head -1

# 2. Replay the full request trace
harness observe --trace-id <TRACE_ID> --lines 0 --no-follow --format json \
  | jq '{ts: .timestamp, domain: .domain, msg: .message}'
```

The `--lines 0` flag scans the *entire* log file from the beginning (not just the
trailing 50 lines), which is important for long-running traces.

---

## Options

| Flag | Default | Effect |
|---|---|---|
| `--log-file PATH` | `logs/harness.ndjson` | NDJSON file to tail |
| `--domain DOMAIN` | *(none)* | Dot-boundary-aware domain prefix filter |
| `--trace-id TRACE_ID` | *(none)* | Exact 32-char W3C trace ID filter |
| `--level LEVEL` | `DEBUG` | Minimum severity threshold (`DEBUG` / `INFO` / `WARN` / `ERROR` / `FATAL`) |
| `--lines N` | `50` | Trailing existing lines to scan before following (`0` = all) |
| `--follow` / `--no-follow` | `--follow` | Stream new entries continuously (`--follow`) or scan and exit (`--no-follow`) |
| `--format pretty\|json` | `pretty` | Output format — ANSI-coloured lines or raw NDJSON |
| `--no-color` | off | Strip ANSI colour codes (auto-disabled when stdout is not a TTY) |

---

## Schema

Log entries are validated against `harness_skills.models.observe.LogEntry`.
Session summaries conform to `harness_skills.models.observe.ObserveResponse`.

Import in Python:

```python
from harness_skills.models.observe import LogEntry, ObserveResponse

# Validate a raw log line
entry = LogEntry.model_validate_json(raw_line)

# Parse a --no-follow session summary
summary = ObserveResponse.model_validate_json(stderr_output)
print(f"Matched {summary.entries_matched} / {summary.lines_scanned} lines")
if summary.validation_errors:
    print(f"⚠️  {summary.validation_errors} entries failed schema validation")
```

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Watch logs live while a plan runs | **`/harness:observe`** ← you are here |
| Trace a single request across domains | **`/harness:observe --trace-id …`** ← you are here |
| Scan for errors after a failure | **`/harness:observe --level ERROR --no-follow`** ← you are here |
| Check the overall status of plans | `/harness:status` |
| Run architecture & principle checks | `/harness:lint` |
| Full quality gate before merge | `/harness:evaluate` or `/check-code` |
| Find relevant files for a plan | `/harness:context` |
| Detect agent conflicts on shared files | `/coordinate` |

---

## Notes

- **Read-only** — this skill never modifies the log file or any other file.
- **Dot-boundary domain matching** — `--domain pay` does **not** match `payments`;
  it only matches `pay` and `pay.*`.  Always use the full domain prefix you intend.
- **Filters are AND-ed** — `--domain` and `--trace-id` can be combined; an entry
  must satisfy *all* active filters to be emitted.
- **NDJSON only** — the file must be newline-delimited JSON.  Lines that cannot be
  parsed as JSON are silently skipped (they don't increment any counter).
- **Log rotation** — in follow mode, if the log file shrinks (e.g. logrotate
  replaced it), the tail automatically reopens from offset 0.
- **CI / non-TTY** — ANSI colour codes are disabled automatically when stdout is
  not a terminal; pass `--no-color` explicitly to force them off in any context.
- **Schema drift** — `validation_errors > 0` in the `ObserveResponse` summary
  signals that some log producers are not following the five-field convention.
  Entries are still emitted as raw JSON so no data is lost.
- **Pipeline-composable** — chain with other harness commands:
  ```bash
  harness observe --no-follow --level ERROR --format json \
    | jq 'select(.domain | startswith("harness.auth"))' \
    | head -20
  ```
