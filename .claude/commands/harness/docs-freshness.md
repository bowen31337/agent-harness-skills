# Harness Docs Freshness

Verify that every **AGENTS.md** file in the repository:

1. **References only files that still exist** — flags dead links, backtick paths,
   and bare paths that point to deleted or renamed source files.
2. **Contains a current freshness timestamp** — a `generated_at:` or
   `last_updated:` date within the configured staleness window (default **30 days**).

Use this gate to catch documentation rot before it confuses agents or reviewers.

---

## Usage

```bash
# Run with defaults (30-day staleness threshold, blocking on errors)
/harness:docs-freshness

# Custom staleness threshold — flag docs older than 14 days
/harness:docs-freshness --max-staleness-days 14

# Advisory mode — report violations as warnings, never block
/harness:docs-freshness --no-fail-on-error

# Point at a non-default project root
/harness:docs-freshness --root /path/to/repo

# Integrate into a full quality gate run
/harness:evaluate --gate docs_freshness --max-staleness-days 14
```

---

## Instructions

### Step 1 — Locate AGENTS.md files

Scan the repository tree for all `AGENTS.md` files, excluding virtual
environments and tool caches:

```bash
find . -name "AGENTS.md" \
  -not -path '*/.git/*' \
  -not -path '*/.venv/*' \
  -not -path '*/venv/*' \
  -not -path '*/node_modules/*' \
  -not -path '*/__pycache__/*' \
  2>/dev/null | sort
```

If no `AGENTS.md` files are found, report a clean pass:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Docs Freshness Gate — ✅ PASSED
  No AGENTS.md files found — nothing to check.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### Step 2 — Run the gate CLI

```bash
uv run python -m harness_skills.gates.docs_freshness \
  --root . \
  --max-staleness-days 30 \
  2>&1
```

> **Fallback** — if `uv` is not available:
>
> ```bash
> python -m harness_skills.gates.docs_freshness \
>   --root . \
>   --max-staleness-days 30
> ```

Capture both stdout and the exit code.

**Exit codes:**

| Code | Meaning |
|---|---|
| `0` | Gate passed — no errors found |
| `1` | Gate failed — one or more error-severity violations |
| `2` | Input / configuration error |

> **Note:** With `--no-fail-on-error`, violations are downgraded to warnings
> and the gate always exits `0`.

---

### Step 3 — Check dead references

For each `AGENTS.md`, the gate extracts file paths from:

- Markdown links: `[label](path/to/file.py)`
- Backtick paths: `` `path/to/file.py` ``
- Bare paths: `scripts/deploy.sh` (relative paths with a `/`)

Each extracted path is resolved relative to the `AGENTS.md` file's directory
**and** relative to the repository root.  A path that cannot be found at either
location is flagged as a **dead reference** (`dead_ref` violation).

**Paths that are never flagged:**
- URLs starting with `http://`, `https://`
- Anchor fragments (`#section`)
- Paths starting with `/` (absolute)

---

### Step 4 — Check freshness timestamp

Each `AGENTS.md` must contain a freshness timestamp in one of these forms:

```
<!-- generated_at: 2026-03-20 -->
generated_at: 2026-03-20
> generated_at: 2026-03-20
last_updated: 2026-03-20
```

The harness auto-generated block (`<!-- harness:auto-generated -->`) uses the
`last_updated:` form — both patterns are recognised.

| Condition | Violation |
|---|---|
| No timestamp found | `missing_timestamp` — add one to track content age |
| Age ≤ `max_staleness_days` | ✅ Fresh — no violation |
| Age > `max_staleness_days` | `stale_content` — regenerate or update the file |

---

### Step 5 — Render the human-readable report

**When all checks pass:**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Docs Freshness Gate — ✅ PASSED
  Checked 2 AGENTS.md file(s)  ·  47 reference(s)  ·  threshold: 30 days
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅ All references resolve to existing files.
  ✅ All timestamps are within the 30-day freshness window.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**When violations are found:**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Docs Freshness Gate — ❌ FAILED
  Checked 2 AGENTS.md file(s)  ·  47 reference(s)  ·  threshold: 30 days
  2 error(s)  ·  1 warning(s)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Violations
────────────────────────────────────────────────────
  ❌ dead_ref      AGENTS.md:12
                  Referenced file does not exist: 'src/old_module.py'
                  → Delete or update this reference.

  ❌ stale_content AGENTS.md
                  Content is 45 day(s) old (generated_at: 2026-02-05,
                  threshold: 30 day(s)). Regenerate or update the file.
                  → Run /harness:update to refresh the timestamp.

  ⚠  dead_ref      svc/auth/AGENTS.md:31
                  Referenced file does not exist: 'utils/helpers.py'

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Severity → display icon mapping:

| Severity | Icon |
|---|---|
| `error` | ❌ |
| `warning` | ⚠ |

---

### Step 6 — Emit structured data (agent-readable)

After the human-readable section, emit a fenced JSON block so downstream
agents can act on the result without re-running the gate:

```json
{
  "command": "harness docs-freshness",
  "status": "failed",
  "message": "2 error(s) found across 2 AGENTS.md file(s).",
  "stats": {
    "agents_files": 2,
    "total_refs_checked": 47,
    "dead_refs": 2,
    "stale": 1,
    "missing_timestamps": 0
  },
  "violations": [
    {
      "agents_file": "AGENTS.md",
      "kind": "dead_ref",
      "severity": "error",
      "message": "Referenced file does not exist: 'src/old_module.py'",
      "referenced_path": "src/old_module.py",
      "line_number": 12
    },
    {
      "agents_file": "AGENTS.md",
      "kind": "stale_content",
      "severity": "error",
      "message": "Content is 45 day(s) old (generated_at: 2026-02-05, threshold: 30 day(s)).",
      "referenced_path": null,
      "line_number": null
    }
  ]
}
```

---

### Step 7 — Recommended recovery actions

After the report, suggest concrete next steps based on violations found:

| Violation | Recommended action |
|---|---|
| `dead_ref` | Find the file's new location with `git log --all -- <old-path>` and update the reference, or remove it if the file was intentionally deleted. |
| `stale_content` | Run `/harness:update` to regenerate the timestamp, or manually update `generated_at:` to today's date. |
| `missing_timestamp` | Add `<!-- generated_at: YYYY-MM-DD -->` near the top of the file. Use today's date. |

If no violations are found, state:
*"All AGENTS.md files are fresh and reference valid files. No action needed."*

---

## Options

| Flag | Default | Effect |
|---|---|---|
| `--root PATH` | `.` | Repository root for resolving relative file references |
| `--max-staleness-days N` | `30` | Days before a timestamped AGENTS.md is considered stale |
| `--fail-on-error` | `true` | Exit non-zero on error-severity violations (`--no-fail-on-error` for advisory) |
| `--quiet` | off | Suppress per-violation output; print only the summary line |

---

## harness.config.yaml integration

The gate reads its threshold from `harness.config.yaml` when present.
Profile defaults:

| Profile | `max_staleness_days` | `fail_on_error` |
|---|---|---|
| `starter` | 30 | `true` |
| `standard` | 30 | `true` |
| `advanced` | 14 | `true` |

Override per-project:

```yaml
# harness.config.yaml
active_profile: standard

profiles:
  standard:
    gates:
      docs_freshness:
        enabled: true
        max_staleness_days: 14    # tighter window for this project
        fail_on_error: true
```

A `--max-staleness-days` flag passed at invocation time **always takes precedence**
over the YAML value.

---

## What counts as a file reference?

The gate recognises three reference styles:

| Style | Example | Matched? |
|---|---|---|
| Markdown link | `[module](src/auth/utils.py)` | ✅ |
| Backtick path | `` `harness_skills/gates/runner.py` `` | ✅ |
| Bare path | `scripts/deploy.sh` | ✅ |
| URL | `https://example.com/docs` | ❌ (skipped) |
| Anchor | `#section-heading` | ❌ (skipped) |
| Bare word | `pytest` | ❌ (no extension, no slash) |

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Verify AGENTS.md references and freshness | **`/harness:docs-freshness`** ← you are here |
| Run all 9 quality gates at once | `/harness:evaluate` |
| Check for stale execution plans | `/harness:detect-stale` |
| Enforce coverage on a PR | `/harness:coverage-gate` |
| Lint coding principles | `/harness:lint` |

---

## Notes

- **Read-only** — this skill never modifies files.  Use `/harness:update` to
  regenerate timestamps.
- **Recognised timestamp formats** — `generated_at: YYYY-MM-DD` (manual) and
  `last_updated: YYYY-MM-DD` (harness auto-generated block).  Both are treated
  identically; the gate uses whichever appears first.
- **Reference resolution** — each extracted path is tried relative to the
  `AGENTS.md` directory first, then relative to the repo root.  Only if both
  resolutions fail is the reference flagged as dead.
- **Skipped directories** — `.git`, `.venv`, `venv`, `node_modules`,
  `__pycache__`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `dist`,
  `build`, `.tox`, `.eggs`.
- **CI-safe exit codes** — exit `0` = passed, `1` = failed (violations found),
  `2` = configuration/input error.
- **Advisory mode** (`--no-fail-on-error`) — all violations are downgraded to
  warnings; the gate exits `0` regardless.  Use for informational runs without
  blocking CI.
