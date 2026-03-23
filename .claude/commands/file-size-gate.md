# File Size Gate

Scan every source file in the repository and enforce a configurable **line-count limit** to prevent monolithic files that are hard for agents and reviewers to reason about. Produces an error for files that exceed the hard cap, a warning for files approaching it, and emits a machine-readable report. Exits non-zero when blocking violations are found, making it safe to use as a CI gate.

---

## Instructions

### Step 1: Discover source files

Collect all source files under the repository root, honouring the configured include/exclude patterns.

Default **include** extensions (scan these file types):

```
.py  .ts  .tsx  .js  .jsx  .go  .rs  .rb  .java  .kt  .swift  .c  .cpp  .cs
```

Default **exclude** patterns (always skip):

```
.git/          node_modules/    __pycache__/    *.pyc
dist/          build/           .venv/          venv/
vendor/        migrations/      *.min.js        *.min.css
*.generated.*  *.g.ts           *.g.py
```

```bash
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
```

Use `find` or `glob` to enumerate matching files. For each file store its path relative to `REPO_ROOT`.

---

### Step 2: Resolve the active thresholds

Read `harness.config.yaml` (if present) and extract the `file_size` gate configuration block.  Apply the following priority order (highest wins):

1. CLI flags passed to the skill invocation (`--max-lines`, `--warn-lines`).
2. `harness.config.yaml` → active profile → `gates.file_size`.
3. Built-in defaults: **`max_lines = 500`**, **`warn_lines = 300`**.

Example `harness.config.yaml` override:

```yaml
profiles:
  standard:
    gates:
      file_size:
        enabled: true
        max_lines: 400
        warn_lines: 250
        report_only: false
```

If `enabled: false` in the active profile, print:

```
ℹ️  File Size Gate is disabled in the active harness profile — skipping.
```

and exit 0.

---

### Step 3: Count lines in each file

For each discovered file count its lines.  Use a byte-level newline count for accuracy and speed:

```python
data = path.read_bytes()
line_count = data.count(b"\n") + (1 if data and data[-1:] != b"\n" else 0)
```

This matches the line count reported by most text editors and `wc -l`.

Collect three buckets:

| Bucket | Condition |
|--------|-----------|
| `HARD_VIOLATIONS` | `line_count > max_lines` |
| `SOFT_VIOLATIONS` | `warn_lines < line_count ≤ max_lines` (only when `warn_lines > 0`) |
| `OK` | `line_count ≤ warn_lines` |

---

### Step 4: Classify violations by severity

For each file in `HARD_VIOLATIONS`:

```
severity = "warning"  if report_only else "error"
message  = "<rel_path> — <line_count> lines (<overrun> over the <max_lines>-line hard limit). Consider splitting into smaller, focused modules."
```

For each file in `SOFT_VIOLATIONS`:

```
severity = "warning"  (always advisory)
message  = "<rel_path> — <line_count> lines (<overrun_soft> over the <warn_lines>-line soft limit, <headroom> lines before the hard cap). Plan to split before it crosses the hard limit."
```

---

### Step 5: Generate the gate report

Print the following report to stdout.

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  File Size Gate  (hard: <max_lines> lines · soft: <warn_lines> lines)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Hard Limit Violations  (> <max_lines> lines)
────────────────────────────────────────────────────────────────
  #  Lines   File
  ──────────────────────────────────────────────────────────────
   1    823   src/api/routes.py              (+323 over limit)
   2    671   src/models/user.py             (+171 over limit)
   3    512   tests/test_integration.py      (+12 over limit)

Soft Limit Warnings  (<warn_lines>–<max_lines> lines)
────────────────────────────────────────────────────────────────
   1    480   src/services/billing.py        (20 lines to hard cap)
   2    342   src/utils/helpers.py           (158 lines to hard cap)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Summary
  ──────────────────────────────────────────────────────────────
  Files scanned       :  142
  Hard violations     :    3   ❌
  Soft warnings       :    2   ⚠️
  Largest file        :  src/api/routes.py  (823 lines)
  Gate result         :  FAILED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

If there are **no violations at all**, print:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  File Size Gate  (hard: 500 lines · soft: 300 lines)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅  All 142 files are within the configured size limits.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### Step 6: Remediation guidance

For each file in `HARD_VIOLATIONS`, append a refactoring hint:

```
💡 Remediation hints
────────────────────────────────────────────────────────────────
  src/api/routes.py (823 lines)
    → Group related routes into sub-routers / blueprints and import them.
      Common split boundaries: by resource type, by HTTP verb group,
      or by authentication domain.

  src/models/user.py (671 lines)
    → Extract mixins, validators, or serialisers into separate modules
      (e.g. user_validators.py, user_serializers.py).

  tests/test_integration.py (512 lines)
    → Split by feature area: one test file per domain concept or endpoint
      group. Shared fixtures belong in conftest.py.
```

Print a generic fallback hint when no language-specific heuristic applies:

```
  <file> (<N> lines)
    → Identify cohesive groups of functions/classes and move each group
      to its own module. Keep this file as the public re-export surface
      if backward compatibility matters.
```

---

### Step 7: Emit the machine-readable JSON report

Always emit the JSON block after the human-readable report (or instead of it when `--json` is passed):

```json
{
  "gate": "file-size",
  "timestamp": "<ISO-8601 UTC>",
  "config": {
    "max_lines": 500,
    "warn_lines": 300,
    "report_only": false,
    "fail_on_error": true
  },
  "violations": [
    {
      "kind": "exceeds_hard_limit",
      "severity": "error",
      "file": "src/api/routes.py",
      "line_count": 823,
      "limit": 500,
      "overrun": 323,
      "message": "823 lines — 323 over the 500-line hard limit."
    },
    {
      "kind": "exceeds_soft_limit",
      "severity": "warning",
      "file": "src/services/billing.py",
      "line_count": 480,
      "limit": 300,
      "overrun": 180,
      "message": "480 lines — 180 over the 300-line soft limit, 20 lines before the hard cap."
    }
  ],
  "summary": {
    "files_scanned": 142,
    "hard_violations": 3,
    "soft_warnings": 2,
    "largest_file": "src/api/routes.py",
    "largest_file_lines": 823,
    "passed": false
  }
}
```

---

### Step 8: Exit code

| Condition | Exit code |
|-----------|-----------|
| No hard violations | `0` |
| Hard violations found, `fail_on_error=true`, `report_only=false` | `1` |
| Hard violations found but `fail_on_error=false` or `report_only=true` | `0` ¹ |
| Gate disabled in active profile | `0` |

¹ Soft-limit warnings never affect the exit code.

Print the final line:

```
Exit: <code>  (<reason>)
```

---

## Flags

| Flag | Effect |
|------|--------|
| `--max-lines N` | Hard limit in lines (default: **500**) |
| `--warn-lines N` | Soft limit in lines (default: **300**). `0` disables soft warnings. |
| `--report-only` | Downgrade all violations to warnings — gate never exits non-zero. Useful for onboarding existing large codebases. |
| `--no-fail-on-error` | Alias for `--report-only`. |
| `--include GLOB` | Add an extra include pattern (repeatable). When provided, overrides the default include list. |
| `--exclude GLOB` | Add an extra exclude pattern on top of the built-in skip list (repeatable). |
| `--json` | Emit only the machine-readable JSON report; suppress the human-readable output. |
| `--quiet` | Suppress per-file violation lines; print only the summary section. |
| `--path DIR` | Limit scanning to a subdirectory instead of the whole repository root. |

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Gate passed — no blocking hard-limit violations. |
| `1` | Gate failed — one or more files exceed `max_lines` and `fail_on_error=true`. |

---

## Notes

- **Read-only** — this gate never modifies source files.
- **Blank lines are counted** — the line count matches `wc -l` and editor gutters, so blank lines and comments count towards the cap.  This is intentional: cognitive load scales with total file size, not just executable lines.
- **Incremental adoption** — use `--report-only` (or set `report_only: true` in `harness.config.yaml`) when first enabling the gate on an existing codebase.  Fix violations iteratively before switching to blocking mode.
- **Per-profile thresholds** — the `advanced` harness profile uses tighter defaults (400/250) to encourage smaller modules in mature codebases.
- **CI wiring**:
  ```yaml
  - name: File Size Gate
    run: claude --skill file-size-gate --max-lines 500
  ```
  Or reference it via `harness evaluate --gate file_size` when using the harness runner.
- Run `/ci-pipeline` to inject this gate into an existing generated workflow automatically.
- To see which files are growing fastest, combine with `git log --stat` and the `/harness:context` skill.
