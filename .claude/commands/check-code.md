# Check Code Quality

Run code quality checks using ruff, mypy, and pytest. Report which pass/fail and summarize issues. Also enforces any project-specific principles defined in `.claude/principles.yaml`.

## Instructions

Run all checks and produce a structured report.

### Step 0: Load custom principles

Check for project-specific golden rules:

```bash
cat .claude/principles.yaml 2>/dev/null || echo "__NONE__"
```

Parse the YAML and extract all principles where `applies_to` includes `"check-code"` or `"both"`.
If the file is missing or `__NONE__` is returned, skip this step silently — custom principles are optional.

Pass `--no-principles` flag: if the user invoked this skill with `--no-principles`, skip Step 0 and the custom-principles section of the report entirely.

### Step 1: Run ruff (linting + formatting)

```bash
# Check linting
uv run ruff check . --output-format=concise 2>&1
RUFF_EXIT=$?

# Check formatting
uv run ruff format --check . 2>&1
RUFF_FMT_EXIT=$?
```

### Step 2: Run mypy (type checking)

```bash
uv run mypy . --ignore-missing-imports --no-error-summary 2>&1
MYPY_EXIT=$?
```

### Step 3: Run pytest (tests)

```bash
uv run pytest tests/ -v --tb=short --no-header 2>&1
PYTEST_EXIT=$?
```

### Step 4: Generate report

Format the results as a structured report:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Code Quality Report — claw-forge
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ✅ Ruff lint     — 0 errors, 0 warnings
  ✅ Ruff format   — All files formatted
  ❌ MyPy          — 3 type errors
  ✅ Pytest        — 57 passed, 0 failed

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MyPy Issues:
  claw_forge/cli.py:42: error: Argument 1 to "run" has incompatible type
  ...

Overall: NEEDS ATTENTION (1/3 checks failing)
```

If custom principles were loaded in Step 0, append a **Principles** section to the report:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Project Principles (2 loaded)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Review each principle against the changed files and mark pass/warn/skip:

  P001 [architecture / blocking]
       "All database queries must go through the repository layer"
       → ✅ PASS — no direct DB calls found outside repository layer

  P003 [style / suggestion]
       "Prefer dataclasses over plain dicts for structured data"
       → ⚠️  WARN — claw_forge/runner.py:88 returns a plain dict; consider a dataclass

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Rules:
- `blocking` violations upgrade the overall result to **NEEDS ATTENTION** even if all automated checks pass.
- `suggestion` violations are shown as warnings but do not fail the gate.
- If no changed files are relevant to a principle, mark it `→ ⏭  SKIP — not applicable to changed files`.
- To define or update principles: run `/define-principles`.

### Step 5: Summarize failures

For each failing check, explain:
1. **What failed**: The specific error(s)
2. **Root cause**: Why it's failing
3. **Fix**: Exact command or code change to fix it

### Quick fixes

If you can fix simple issues automatically, do so:

```bash
# Auto-fix ruff issues
uv run ruff check . --fix
uv run ruff format .
```

For mypy errors: show the exact line and suggested type annotation fix.

For pytest failures: show the test name, assertion that failed, and likely cause.

### Exit codes

- All pass → `0`  
- Any failure → `1`

This command is safe to run repeatedly. It never modifies code (unless you choose to apply ruff's auto-fixes).
