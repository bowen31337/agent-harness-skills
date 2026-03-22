# Type Safety Gate

Run the project's type checker in strict mode and enforce **zero errors**. Supports TypeScript (`tsc --strict`) and Python (`mypy --strict`). Exits non-zero if any type error is found, making this safe to use as a blocking CI gate.

## Instructions

### Step 1: Detect project type

```bash
# Check for TypeScript project
ls tsconfig.json 2>/dev/null && echo "TS_PROJECT=1" || echo "TS_PROJECT=0"

# Check for Python project
ls pyproject.toml setup.cfg setup.py 2>/dev/null | head -1 && echo "PY_PROJECT=1" || echo "PY_PROJECT=0"
```

Rules:
- If `tsconfig.json` is found → **TypeScript** mode.
- If `pyproject.toml` / `setup.cfg` / `setup.py` is found → **Python** mode.
- If both exist → run **both** checkers and report separately.
- If neither exists → print a warning and exit 0 (nothing to check).

---

### Step 2 (TypeScript): Ensure `strict` is enabled in tsconfig.json

Read `tsconfig.json`:

```bash
cat tsconfig.json
```

Verify that the `compilerOptions` block contains `"strict": true`.
If it is missing or set to `false`:

1. Inform the user that strict mode is not enabled.
2. Patch the file to add / set `"strict": true` under `compilerOptions`.
3. Print: `⚙️  tsconfig.json patched — "strict": true added.`

---

### Step 3 (TypeScript): Run `tsc --noEmit`

```bash
# Use locally installed tsc if available, fall back to npx
if command -v tsc &>/dev/null; then
  tsc --noEmit 2>&1
  TSC_EXIT=$?
elif [ -f node_modules/.bin/tsc ]; then
  node_modules/.bin/tsc --noEmit 2>&1
  TSC_EXIT=$?
else
  npx --no-install tsc --noEmit 2>&1
  TSC_EXIT=$?
fi
```

Capture all output as `TSC_OUTPUT`.

---

### Step 2 (Python): Ensure mypy is available

```bash
uv run mypy --version 2>/dev/null || echo "MYPY_MISSING=1"
```

If mypy is not installed:

1. Print: `⚙️  mypy not found — adding to dev dependencies.`
2. Run:
   ```bash
   uv add --dev mypy
   ```

---

### Step 3 (Python): Check for mypy configuration

Look for a `[tool.mypy]` section in `pyproject.toml`:

```bash
grep -n "\[tool\.mypy\]" pyproject.toml 2>/dev/null || echo "MYPY_CONFIG_MISSING=1"
```

If the section is **missing**, append a strict baseline config to `pyproject.toml`:

```toml
# ---------------------------------------------------------------------------
# Mypy — strict type checking
# ---------------------------------------------------------------------------
[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_configs = true
ignore_missing_imports = true
```

Print: `⚙️  [tool.mypy] strict config added to pyproject.toml.`

---

### Step 4 (Python): Run mypy

```bash
uv run mypy . --no-error-summary 2>&1
MYPY_EXIT=$?
```

Capture all output as `MYPY_OUTPUT`.

---

### Step 5: Evaluate results and generate the gate report

Count errors for each checker:

- **TypeScript**: Count lines matching `error TS\d+` in `TSC_OUTPUT`.
- **Python**: Count lines matching `error:` in `MYPY_OUTPUT`.

Format the gate report:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Type Safety Gate
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Language   Checker          Errors   Status
  ─────────  ───────────────  ───────  ──────
  TypeScript tsc --strict     0        ✅ PASS
  Python     mypy --strict    3        ❌ FAIL

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Gate result: FAILED  (zero errors required)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Then list every error, grouped by file:

```
Python — mypy errors (3):
  harness_skills/runner.py:42: error: Argument 1 to "run" has incompatible type "str"; expected "int"
  harness_skills/runner.py:87: error: Item "None" of "Optional[str]" has no attribute "split"
  harness_skills/cli/main.py:15: error: Missing return statement
```

---

### Step 6: Auto-fix suggestions

For each error, provide a concrete, copy-paste-ready fix suggestion:

- **Missing return type** → add `-> ReturnType` annotation.
- **Incompatible argument type** → show the corrected call with the right type.
- **Untyped function** → show a typed version of the signature.
- **`Optional[X]` unguarded access** → show a guard (`if x is not None:`) or assert.

Keep suggestions concise (1-3 lines each).

---

### Step 7: Exit code

| Condition                     | Exit code |
|-------------------------------|-----------|
| All checkers: 0 errors        | `0`       |
| Any checker: ≥ 1 error        | `1`       |
| Checker not found / crashed   | `2`       |

Print the final line:

```
Exit: <code>  (<reason>)
```

---

## Flags

| Flag                  | Effect                                                       |
|-----------------------|--------------------------------------------------------------|
| `--python-only`       | Skip TypeScript check even if `tsconfig.json` exists        |
| `--ts-only`           | Skip Python check even if `pyproject.toml` exists           |
| `--no-patch`          | Never modify `tsconfig.json` or `pyproject.toml`            |
| `--no-fix-suggestions`| Omit the auto-fix suggestions section                        |
| `--strict-off`        | Run with default strictness instead of `--strict` / `strict=true` (not recommended) |

---

## Notes

- This gate is **non-destructive by default**: it only patches config files when strict settings are missing and `--no-patch` is not given.
- The gate is safe to run repeatedly; subsequent runs on a clean codebase will show all-pass instantly.
- To wire this into CI, run `/ci-pipeline` — the generated workflow includes a `--gate types` option for `harness evaluate`.
- For ongoing code quality (lint + format + tests + types), run `/check-code` which also invokes mypy.
