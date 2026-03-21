# Progress Log

Generate and maintain a timestamped progress log for multi-step plans. Agents append entries as they complete each step, creating a persistent audit trail of work done.

## When to use

- At the start of a multi-step plan to initialize the log file
- After each step completes to append a timestamped entry
- To surface progress to humans or downstream agents

## Instructions

### Step 1: Resolve the log file path

Determine where the log lives. Default location is `.claw-forge/progress.log`.
If an argument is provided (e.g. `/progress-log path/to/custom.log`), use that path instead.

```bash
LOG_FILE="${1:-.claw-forge/progress.log}"
mkdir -p "$(dirname "$LOG_FILE")"
```

### Step 2: Initialize the log (first run only)

If the log file does not yet exist, write the header block:

```bash
if [ ! -f "$LOG_FILE" ]; then
  cat > "$LOG_FILE" <<EOF
# Progress Log
# Started: $(date -u '+%Y-%m-%dT%H:%M:%SZ')
# Plan: <PLAN_TITLE>
# ──────────────────────────────────────────────
EOF
  echo "Log initialized: $LOG_FILE"
fi
```

Replace `<PLAN_TITLE>` with the name of the current feature, task, or plan being executed.

### Step 3: Append a timestamped entry

After each step in the plan completes, append one line in this format:

```
[YYYY-MM-DDTHH:MM:SSZ] [STATUS] Step N — <description>
```

**STATUS values:**

| Symbol | Meaning |
|--------|---------|
| `✅ DONE` | Step completed successfully |
| `⏭ SKIP` | Step skipped (not applicable) |
| `❌ FAIL` | Step failed — see notes |
| `🔄 RETRY` | Step retried after failure |
| `⏳ WAIT` | Waiting on human input or external dependency |

**Append command:**

```bash
TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
STATUS="✅ DONE"
STEP_N=1
DESCRIPTION="Cloned repository and installed dependencies"

echo "[$TIMESTAMP] [$STATUS] Step $STEP_N — $DESCRIPTION" >> "$LOG_FILE"
```

Optionally append a detail line (indented, preceded by `  →`) for extra context:

```bash
echo "  → uv install completed in 4.2s, 47 packages" >> "$LOG_FILE"
```

### Step 4: Append a failure note (on error)

When a step fails, log the failure and a brief cause:

```bash
TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
echo "[$TIMESTAMP] [❌ FAIL] Step $STEP_N — $DESCRIPTION" >> "$LOG_FILE"
echo "  → Error: <short error message or exit code>" >> "$LOG_FILE"
```

Do NOT stop logging on failure. Continue appending entries for all subsequent steps.

### Step 5: Append a plan-complete footer

When all steps finish (pass or fail), close the log:

```bash
TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
PASSED=<N>
FAILED=<M>
cat >> "$LOG_FILE" <<EOF
# ──────────────────────────────────────────────
# Finished: $TIMESTAMP
# Result: $PASSED passed, $FAILED failed
EOF
```

### Step 6: Display the log (optional)

Print the current log to the console for human review:

```bash
cat "$LOG_FILE"
```

Expected output:

```
# Progress Log
# Started: 2026-03-20T14:00:00Z
# Plan: Add OAuth2 login flow
# ──────────────────────────────────────────────
[2026-03-20T14:00:12Z] [✅ DONE] Step 1 — Scaffold auth module
  → Created src/auth/__init__.py, src/auth/oauth.py
[2026-03-20T14:01:45Z] [✅ DONE] Step 2 — Add token exchange endpoint
[2026-03-20T14:03:10Z] [❌ FAIL] Step 3 — Run integration tests
  → Error: fixture 'mock_provider' not found (exit 1)
[2026-03-20T14:04:02Z] [🔄 RETRY] Step 3 — Run integration tests (after fixture fix)
[2026-03-20T14:05:30Z] [✅ DONE] Step 3 — Run integration tests
[2026-03-20T14:05:31Z] [⏭ SKIP] Step 4 — Deploy to staging (no staging env configured)
# ──────────────────────────────────────────────
# Finished: 2026-03-20T14:05:31Z
# Result: 3 passed, 0 failed
```

### Step 7: Report to state service (optional)

If the state service is running, post a summary event after the plan completes:

```bash
curl -s -X POST http://localhost:8888/features/$FEATURE_ID/events \
  -H "Content-Type: application/json" \
  -d "{
    \"type\": \"progress.complete\",
    \"payload\": {
      \"log_file\": \"$LOG_FILE\",
      \"passed\": $PASSED,
      \"failed\": $FAILED
    }
  }" || true
```

### Notes

- All timestamps use **UTC ISO-8601** format (`YYYY-MM-DDTHH:MM:SSZ`) for consistency across timezones and agents
- The log file is append-only — never overwrite or truncate it mid-run
- Multiple agents working in parallel can safely append to the same log; each `echo ... >> file` is an atomic OS write
- Keep descriptions concise (one line); put details on the `→` continuation line
- The log is human-readable plain text — no parsing required to skim progress
- To tail the log in real time during a long run: `tail -f .claw-forge/progress.log`
