# Principles Report

Scan the entire codebase and list every deviation from the project's golden principles. Reports each violation with its severity, exact file location, and a plain-English explanation. Unlike `/check-code` (which only inspects staged changes), this command walks the full source tree.

## Usage

```
/principles-report
/principles-report --severity blocking
/principles-report --path src/
/principles-report --output principles-report.md
/principles-report --no-summary
```

## Options

| Flag | Description |
|---|---|
| `--severity <level>` | Filter output to `blocking` or `suggestion` violations only (default: both) |
| `--path <dir>` | Restrict scan to a subdirectory (default: `.`) |
| `--output <file>` | Write the report to a file in addition to printing it |
| `--no-summary` | Skip the summary table; print only the violation list |
| `--fix-hints` | Append a suggested fix to each violation entry |

---

## Instructions

### Step 0: Load principles

Read the project's golden rules:

```bash
cat .claude/principles.yaml 2>/dev/null || echo "__NONE__"
```

If the result is `__NONE__` or the file is absent, abort with:

```
⚠️  No principles found — run /define-principles to add golden rules.
```

Parse the YAML and load **all** principles (both `blocking` and `suggestion`).
If `--severity blocking` was passed, discard entries where `severity != "blocking"`.
If `--severity suggestion` was passed, discard entries where `severity != "suggestion"`.

Record the loaded count; it will appear in the summary.

---

### Step 1: Discover source files

Collect the files to scan:

```bash
# Respect --path if provided, else default to repo root
SCAN_ROOT="${PATH_ARG:-.}"

# Gather all tracked source files (excludes build artefacts, .git, __pycache__, etc.)
git ls-files "$SCAN_ROOT" \
  | grep -v -E '(__pycache__|\.pyc$|\.git|node_modules|dist/|build/)' \
  2>/dev/null
```

If `git ls-files` returns nothing (not a git repo), fall back to:

```bash
find "$SCAN_ROOT" -type f \
  -not -path '*/__pycache__/*' \
  -not -path '*/.git/*' \
  -not -name '*.pyc'
```

Record the total file count for the summary line.

---

### Step 2: Evaluate each principle across all files

For every principle loaded in Step 0, read its `rule`, `category`, `severity`, and `applies_to` fields.

Scan each source file and look for patterns that contradict the rule.
Use semantic judgment (read the file content, apply the principle's intent) rather than simple text search.

For **each violation found**, record:

| Field | Description |
|---|---|
| `id` | Principle ID (e.g. `P002`) |
| `severity` | `blocking` or `suggestion` |
| `category` | Category from the principle |
| `file` | Repo-relative file path |
| `line` | Line number (best estimate; range acceptable, e.g. `42–47`) |
| `snippet` | The offending code (≤ 3 lines; truncate longer spans) |
| `reason` | One sentence explaining why this violates the principle |

If a principle does not apply to any file in the scanned set, record it as `SKIP — not applicable`.
If a principle is fully satisfied, record it as `PASS`.

---

### Step 3: Render the report

Print the violation report to stdout using this layout:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Principles Violation Report
  Scanned: <N> files   Principles: <M> loaded
  Generated: <YYYY-MM-DD HH:MM>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  🔴 BLOCKING VIOLATIONS (<count>)
  ─────────────────────────────────────────────────────

  [P001 · architecture · blocking]
  Rule: "All database queries must go through the repository layer"

    ❌ src/api/users.py : 88–91
       │ db.execute("SELECT * FROM users WHERE id = ?", user_id)
       Reason: Direct DB call found outside the repository layer.

    ❌ src/api/orders.py : 144
       │ conn.cursor().execute("UPDATE orders SET status=…")
       Reason: Direct DB call found outside the repository layer.

  ─────────────────────────────────────────────────────

  [P002 · testing · blocking]
  Rule: "Every public API endpoint must have an integration test"

    ❌ src/api/payments.py : 1 (whole file)
       │ @app.post("/payments/charge")
       Reason: No integration test found for the /payments/charge endpoint.

  ─────────────────────────────────────────────────────

  🟡 SUGGESTION VIOLATIONS (<count>)
  ─────────────────────────────────────────────────────

  [P003 · style · suggestion]
  Rule: "Prefer dataclasses over plain dicts for structured data"

    ⚠️  src/services/invoice.py : 55
       │ return {"total": total, "tax": tax, "discount": discount}
       Reason: Returning a plain dict; a dataclass would add type safety here.

  ─────────────────────────────────────────────────────

  ✅ PASSING / SKIPPED
  ─────────────────────────────────────────────────────

  P004 [security · blocking]   ✅ PASS — no hardcoded secrets detected
  P005 [performance · suggestion] ⏭ SKIP — no async I/O files in scanned set

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Summary
  ─────────────────────────────────────────────────────
  Principles checked : <M>
  Files scanned      : <N>

  🔴 Blocking violations  : <count> across <file_count> files
  🟡 Suggestion violations: <count> across <file_count> files
  ✅ Passing              : <count>
  ⏭  Skipped              : <count>

  Overall: ❌ VIOLATIONS FOUND  (or ✅ ALL PRINCIPLES SATISFIED)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Formatting rules:**
- `--no-summary` omits the Summary block.
- If there are zero violations in a severity tier, omit that tier's section entirely.
- If `--fix-hints` is set, append a `Fix:` line under each violation's `Reason:` line with a concrete suggestion (e.g., "Move this query to `UserRepository.find_by_id()`").
- Truncate snippets longer than 3 lines with `… (<N> more lines)`.

---

### Step 4: Write file output (optional)

If `--output <file>` was provided, write the same report (plain text, no ANSI escapes) to that file:

```bash
# Strip ANSI colour codes before writing
OUTPUT_FILE="${OUTPUT_ARG}"
printf '%s\n' "$REPORT_TEXT" > "$OUTPUT_FILE"
echo "Report written to $OUTPUT_FILE"
```

---

### Step 5: Exit with the correct code

- **Zero blocking violations** → exit `0`
- **One or more blocking violations** → exit `1`
- **Suggestion-only violations** → exit `0` (non-blocking)

This makes the command safe to use in CI pipelines:

```yaml
# Example GitHub Actions step
- name: Check golden principles
  run: claude run principles-report --severity blocking
```

---

## Notes

- This command scans **all tracked files**, not just the diff. Use `/check-code` for faster staged-only checks during development.
- Principles with `applies_to: ["review-pr"]` only are still evaluated — the report covers the whole ruleset regardless of `applies_to`.
  To restrict to `check-code`-scoped principles only, you can filter manually in `.claude/principles.yaml`.
- To add or edit principles: run `/define-principles`.
- To enforce principles on a specific PR only: run `/review-pr`.
- IDs in the report are stable; they match the IDs in `.claude/principles.yaml` exactly.
