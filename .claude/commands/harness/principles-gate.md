# Harness Principles Gate

Enforce **golden-principles compliance** by running the violation scanner
against `.claude/principles.yaml` and failing on any `blocking`-severity
violation.

The gate loads the project's principle definitions, maps each principle's
YAML `severity` to a scanner output level, runs built-in AST scanners for
auto-detectable violations, and exits non-zero when critical violations are
found — preventing merge until all blocking principles are satisfied.

Default behaviour: **fail on critical (blocking) violations only**.
Non-critical violations are reported as warnings but do not block.

---

## Usage

```bash
# Run with defaults — fail on blocking violations
/harness:principles-gate

# Advisory mode — report all violations as warnings, never block
/harness:principles-gate --no-fail-on-critical

# Fail on ALL error-severity violations (not just blocking ones)
/harness:principles-gate --fail-on-error

# Point at a custom principles file
/harness:principles-gate --principles-file path/to/custom-principles.yaml

# Run only specific scanners
/harness:principles-gate --rules no_magic_numbers no_hardcoded_urls

# Output JSON (for CI integrations)
/harness:principles-gate --format json

# Integrate into a full evaluate run
/harness:evaluate --gate principles
```

---

## Instructions

### Step 0: Resolve inputs

Collect the following from the invocation (applying defaults where absent):

| Argument | Default | Description |
|---|---|---|
| `--fail-on-critical` | `true` | Fail the gate on blocking-severity violations |
| `--no-fail-on-critical` | *(flag)* | Disable critical-violation blocking (advisory mode) |
| `--fail-on-error` | `false` | Fail on ALL error violations (superset of fail-on-critical) |
| `--principles-file` | `.claude/principles.yaml` | Path to principles YAML relative to project root |
| `--rules` | `all` | Space-separated list of scanner names to run |
| `--format` | `text` | Output format: `text` or `json` |
| `--project-root` | `.` | Repository root for resolving relative paths |

---

### Step 1: Verify the principles file exists

Check that `.claude/principles.yaml` (or the custom path) is present.

If missing, emit:

```
⚠️  No principles file found at '.claude/principles.yaml'.
    Run /define-principles to create project-specific golden rules.
    The gate will run with built-in defaults only.
```

Do **not** exit — the gate still runs built-in scanners even without a
principles file.

---

### Step 2: Run the principles gate CLI

```bash
uv run python -m harness_skills.gates.principles \
  --root <project-root> \
  --principles-file <principles-file> \
  [--no-fail-on-critical] \
  [--fail-on-error] \
  [--rules <rule1> <rule2> ...] \
  [--format text|json]
```

> **Fallback** — if `uv` is not available:
>
> ```bash
> python -m harness_skills.gates.principles \
>   --root <project-root> \
>   --principles-file <principles-file>
> ```

Capture both stdout and the exit code.

---

### Step 3: Parse and render the result

The CLI emits a summary block.  Render it in this format:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Principles Gate — <PASS ✅ | FAIL ❌>
  Principles loaded  : <N>
  Scanners run       : <N>
  Total violations   : <N>
  Blocking (errors)  : <N>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

For each violation, show:

```
🔴 [P011] Magic number 42 — extract to a named constant.
  src/config.py:87
   → Replace 42 with a named constant such as `MAX_RETRIES = 42`
     in a `constants.py` module.
```

Severity icons:

| Severity | Icon | Meaning |
|---|---|---|
| `error` | 🔴 | Blocking — must fix before merge |
| `warning` | 🟡 | Advisory — should fix, does not block |
| `info` | 🔵 | Suggestion — consider addressing |

**If the gate passes** (no blocking violations):

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅  Principles gate passed — no blocking violations
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**If the gate fails** (blocking violations present), add:

```
🔴 BLOCKING — principles violations found, merge prevented
────────────────────────────────────────────────────────
  <N> blocking violation(s) must be resolved before merging.
  Run /define-principles to review or update project rules.
```

**Advisory mode** (`--no-fail-on-critical`): replace every `🔴 BLOCKING`
header with `🟡 WARNING — advisory only, merge not blocked`.

---

### Step 4: Exit behaviour

| Outcome | Exit code |
|---|---|
| No blocking violations | `0` |
| Blocking violations present (`fail_on_critical=true`) | `1` |
| No principles file + no violations from built-in scanners | `0` |
| Gate runner internal error | `2` |
| Advisory mode (any violations) | `0` (warnings emitted) |

Mirror the CLI exit code.

If exit code is `1`, explicitly state:
*"This branch is **not** ready to merge — resolve all 🔴 blocking violations
before the pull request can land."*

---

### Step 5: Suggest next steps on failure

When blocking violations are found, suggest concrete actions per violation type:

**Magic numbers (P011)**:
1. Identify all numeric literals flagged by the scanner
2. Extract each to a named constant in `constants.py`:
   ```python
   # src/<pkg>/constants.py
   MAX_RETRY_ATTEMPTS = 3
   DEFAULT_PAGE_SIZE = 20
   ```
3. Replace inline occurrences with the constant name

**Hard-coded URLs (P012)**:
1. Move URLs to `src/config.py` via environment variables:
   ```python
   # src/config.py
   import os
   API_BASE_URL = os.environ["API_BASE_URL"]
   ```
2. Or add them to `harness.config.yaml` for non-secret config values

**Function naming (P014)**:
```bash
# Find non-snake_case functions
grep -rn "def [A-Z]" src/ tests/
```

**Class naming (P016)**:
- Rename classes to `PascalCase` — all words capitalised, no underscores

**File naming (P017)**:
```bash
# Find non-snake_case Python files
find . -name "*.py" | grep -E "[A-Z]"
```

**Review or update project principles**:
```bash
/define-principles   # interactive principle editor
```

---

## Built-in scanners

| Scanner | Principle | What it detects |
|---|---|---|
| `no_magic_numbers` | P011 | Numeric literals outside whitelist `{0, 1, -1, 2, 100, 1000}` |
| `no_hardcoded_urls` | P012 | Hard-coded `http://` or `https://` string literals |
| `function_naming` | P014 | Non-`snake_case` function / method names |
| `variable_naming` | P015 | Single-letter variable names outside loop counters |
| `class_naming` | P016 | Non-`PascalCase` class names |
| `file_naming` | P017 | Non-`snake_case.py` Python file names |

All scanners operate on Python source files only (`*.py`), skipping
`.venv/`, `__pycache__/`, `.git/`, and other non-source directories.

---

## Severity model

Violations inherit their severity from the matched principle's YAML `severity`
field:

| YAML severity | Gate severity | Default behaviour |
|---|---|---|
| `blocking` | `error` | Fails gate (🔴 blocks merge) |
| `warning` | `warning` | Advisory only (🟡 does not block) |
| `suggestion` | `info` | Informational (🔵 does not block) |

Override with `--no-fail-on-critical` (fully advisory) or `--fail-on-error`
(fail on all non-info violations).

---

## harness.config.yaml integration

The gate reads its configuration from `harness.config.yaml`:

```yaml
# harness.config.yaml
active_profile: standard

profiles:
  standard:
    gates:
      principles:
        enabled: true
        fail_on_error: true
        fail_on_critical: true          # always fail on blocking violations
        principles_file: .claude/principles.yaml
        rules:
          - all                         # run every built-in scanner
```

### Per-profile defaults

| Profile | `fail_on_error` | `fail_on_critical` | Blocking violations |
|---|---|---|---|
| `starter` | `false` | `true` | Fail |
| `standard` | `true` | `true` | Fail |
| `advanced` | `true` | `true` | Fail |

---

## CI/CD integration

### GitHub Actions

```yaml
# .github/workflows/principles-gate.yml
name: Principles Gate
on: [pull_request]
jobs:
  principles:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
      - name: Run principles compliance gate
        run: |
          uv run python -m harness_skills.gates.principles \
            --root . \
            --format json \
            > principles-report.json
      - name: Upload report
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: principles-report
          path: principles-report.json
```

### GitLab CI

```yaml
# .gitlab-ci.yml (add to existing pipeline)
principles-gate:
  stage: quality
  script:
    - uv run python -m harness_skills.gates.principles --root .
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
  allow_failure: false   # blocking gate
```

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Enforce golden principles on a PR right now | **`/harness:principles-gate`** ← you are here |
| Define or edit project principles | `/define-principles` |
| Run all 9 quality gates at once | `/harness:evaluate` |
| Architecture + principles + lint only | `/harness:lint` |
| Enforce coverage threshold | `/harness:coverage-gate` |
| Bootstrap the full harness | `/harness:create` |

---

## Notes

- **Read-only** — this skill never modifies source files.
- **Python only** — current scanners operate on `*.py` files; JavaScript,
  Go, and other language support is planned.
- **Principles file is optional** — if `.claude/principles.yaml` is absent,
  the gate still runs the built-in scanners with default severities.
- **`fail_on_critical` always applies** — even in `fail_on_error=false`
  (advisory) mode, `fail_on_critical=true` will still fail the gate on
  `blocking` violations.  Use `--no-fail-on-critical` to disable this.
- **Exit code `2`** is reserved for internal gate errors.  Distinguish it
  from `1` (policy violation) in CI scripts.
