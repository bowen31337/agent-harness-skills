# Harness Regression Gate

Enforce a **zero-tolerance policy** on existing test failures: every test in the
suite must pass before a change is accepted.

The gate invokes the pytest test suite, parses the JUnit XML report for
per-test failure details, and exits non-zero when any test fails — causing any
CI system hooked to this exit code to block the pull request.

This is the first gate in every harness profile and cannot be disabled in
`strict` mode.  Merge only when the suite is green.

---

## Usage

```bash
# Run the full test suite (pytest auto-discovery)
/harness:regression-gate

# Restrict to specific paths
/harness:regression-gate --test-paths tests/unit tests/integration

# Add extra pytest arguments (e.g. stop on first failure)
/harness:regression-gate --extra-args -x

# Set a custom timeout
/harness:regression-gate --timeout 120

# Advisory mode — report failures as warnings, do not block
/harness:regression-gate --no-fail-on-error

# Run as part of a full evaluate pass
/harness:evaluate --gate regression
```

---

## Instructions

### Step 0: Resolve inputs

Collect the following from the invocation (applying defaults where absent):

| Argument | Default | Description |
|---|---|---|
| `--test-paths` | _(empty — auto-discover)_ | Pytest path arguments (e.g. `tests/unit`) |
| `--timeout` | `300` | Maximum seconds allowed for the suite to run |
| `--extra-args` | _(none)_ | Extra arguments forwarded verbatim to pytest |
| `--fail-on-error` | `true` | Exit non-zero when any test fails |
| `--project-root` | `.` | Repository root where pytest is invoked |

---

### Step 1: Verify the test suite is discoverable

Before running the gate, confirm that a test suite exists:

```bash
# Check for test files
find . -name "test_*.py" -o -name "*_test.py" | head -5
ls tests/ 2>/dev/null | head -5
```

If **no test files are found**, emit a `WARNING` and exit 0 (advisory):

```
⚠  No test files discovered.
   Create test files matching test_*.py or *_test.py patterns.
   Run `pytest --collect-only` to verify pytest can find your tests.
```

---

### Step 2: Run the test suite

Invoke pytest with a JUnit XML report so failures are machine-parseable:

```bash
pytest \
  --tb=short \
  --junitxml=.harness-regression-junit.xml \
  -q \
  [TEST_PATHS...] \
  [EXTRA_ARGS...]
```

**Timeout handling**: wrap the invocation with a configurable timeout
(default: 300 s).  If the suite exceeds this limit, treat it as a gate
failure with the `timeout` violation kind and clean up the JUnit XML if it
was partially written.

**Configuration source**: if `harness.config.yaml` is present, read the
`gates.regression` block and merge it with the CLI arguments (CLI takes
precedence):

```yaml
# harness.config.yaml — example regression gate configuration
profiles:
  standard:
    gates:
      regression:
        enabled: true
        fail_on_error: true
        timeout_seconds: 300
        extra_args: []
        test_paths: []
```

---

### Step 3: Parse results

#### 3a — All tests passed (pytest exit code 0)

1. Parse `.harness-regression-junit.xml` for aggregate stats
   (`total`, `failed`, `errors`, `skipped`).
2. Delete `.harness-regression-junit.xml`.
3. Emit the success banner (see §4a) and exit 0.

#### 3b — Some tests failed (pytest exit code ≠ 0)

Parse `.harness-regression-junit.xml` for per-test failure details:

```xml
<!-- Each failing testcase has a <failure> or <error> child element -->
<testcase classname="tests.test_auth" name="test_login_invalid_password">
  <failure message="AssertionError: expected 401, got 200">
    tests/test_auth.py:42: AssertionError
  </failure>
</testcase>
```

For each `<failure>` element:
- Extract `classname`, `name` → test identifier.
- Search the element text for `<file>.py:<line>` patterns → file/line hint.
- Produce a `Violation(kind="test_failed", ...)`.

For each `<error>` element (setup/teardown failures):
- Produce a `Violation(kind="suite_error", ...)`.

**Fallback**: if no JUnit XML is present after a non-zero exit code
(pytest not installed, import error, etc.), produce a single
`suite_error` violation with a generic message.

Always delete `.harness-regression-junit.xml` after parsing (success or failure).

---

### Step 4: Render output

#### 4a — Pass

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅  Regression Gate — PASSED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Tests   : 42 total  ·  0 failed  ·  0 errors  ·  2 skipped
  Duration: 8 340 ms
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  All existing tests pass.  Safe to merge. ✔
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

#### 4b — Fail

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ❌  Regression Gate — FAILED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Tests   : 42 total  ·  2 failed  ·  1 error  ·  2 skipped
  Duration: 12 100 ms

  Violations (3 blocking)
  ────────────────────────────────────────────────────
  [ERROR  ] test_failed       [tests/test_auth.py:42] — Test failed: tests.test_auth.test_login_invalid_password
             → Fix the failing assertion in tests/test_auth.py at line 42.
               Run `pytest -x` locally for the full traceback.

  [ERROR  ] test_failed       [tests/test_user.py:87] — Test failed: tests.test_user.test_email_validation
             → Fix the failing assertion in tests/test_user.py at line 87.

  [ERROR  ] suite_error       [tests/conftest.py:5]  — Test error: tests.test_db.test_connect — RuntimeError: setup failed
             → Fix the setup/teardown error in tests/conftest.py.
               Run `pytest -x` locally to reproduce.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ❌  3 existing test(s) are broken.  Do NOT merge.
  Fix all failures before this PR can be accepted.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

#### 4c — Advisory (--no-fail-on-error)

Same layout as §4b but with `⚠ WARNING` labels instead of `❌ ERROR` and a
different footer:

```
  ⚠  3 test(s) are failing (advisory only — fail_on_error: false).
     These failures will not block the merge today, but fix them soon.
```

#### 4d — Timeout

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ❌  Regression Gate — TIMED OUT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [ERROR] timeout — Test suite timed out after 300s. No result is available.
          → Increase timeout_seconds in harness.config.yaml, or use
            extra_args: ["-k", "not slow"] to skip long-running tests.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### Step 5: Emit machine-readable result

After the human-readable banner, emit a JSON block for downstream
consumers:

```json
{
  "gate": "regression",
  "status": "failed",
  "passed": false,
  "total_tests": 42,
  "failed_tests": 2,
  "error_tests": 1,
  "skipped_tests": 2,
  "duration_ms": 12100,
  "violations": [
    {
      "kind": "test_failed",
      "severity": "error",
      "message": "Test failed: tests.test_auth.test_login_invalid_password",
      "file_path": "tests/test_auth.py",
      "line_number": 42,
      "suggestion": "Fix the failing assertion in tests/test_auth.py at line 42. Run `pytest -x` locally for the full traceback."
    }
  ]
}
```

---

### Step 6: Exit

| Condition | Exit code |
|---|---|
| All tests pass | `0` |
| Any tests fail and `fail_on_error=true` | `1` |
| Any tests fail and `fail_on_error=false` (advisory) | `0` |
| Timeout and `fail_on_error=true` | `1` |
| Timeout and `fail_on_error=false` | `0` |

---

## Programmatic usage

The gate can also be invoked directly from Python:

```python
from pathlib import Path
from harness_skills.gates.regression import RegressionGate
from harness_skills.models.gate_configs import RegressionGateConfig

cfg = RegressionGateConfig(
    timeout_seconds=120,
    extra_args=["-x"],          # stop on first failure
    fail_on_error=True,
)
result = RegressionGate(cfg).run(repo_root=Path("."))

if not result.passed:
    for v in result.violations:
        print(v.summary())
    raise SystemExit(1)
```

Or via the CLI:

```bash
python -m harness_skills.gates.regression --root . --timeout 120 -- -x
```

---

## Configuration reference

`gates.regression` block in `harness.config.yaml`:

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `true` | Set to `false` to skip the gate entirely |
| `fail_on_error` | bool | `true` | `false` → emit warnings, never block |
| `timeout_seconds` | int | `300` | Max seconds for the suite to run |
| `extra_args` | list[str] | `[]` | Extra pytest arguments (e.g. `["-k", "not slow"]`) |
| `test_paths` | list[str] | `[]` | Pytest path args; empty = auto-discover |

---

## Options

| Flag | Effect |
|---|---|
| `--test-paths PATH…` | Restrict pytest to specific directories or files |
| `--timeout N` | Override `timeout_seconds` (default: 300) |
| `--extra-args ARG…` | Extra arguments forwarded to pytest |
| `--fail-on-error` / `--no-fail-on-error` | Toggle blocking mode |
| `--project-root PATH` | Repository root (default: `.`) |
| `--quiet` | Suppress per-violation output |

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Verify existing tests before merging | **`/harness:regression-gate`** ← you are here |
| Enforce minimum coverage on changed code | `/harness:coverage-gate` |
| Run all quality gates in one pass | `/harness:evaluate` |
| Detect architecture violations | `/harness:lint` |
| Review a PR end-to-end | `/review-pr` |

---

## Notes

- **Read-only** — this gate never modifies source code.  It only invokes the
  test runner and reports what it finds.
- **JUnit XML cleanup** — the temporary report (`.harness-regression-junit.xml`)
  is always deleted after parsing, whether the run passes or fails.
- **CI-safe** — the gate uses the same Python interpreter that is running
  (`sys.executable`) so it respects any active virtualenv.
- **First gate** — regression is always the first gate in the evaluation order.
  A failing suite stops subsequent gates from producing misleading results
  (e.g. coverage numbers are unreliable if tests are broken).
- **Skipped tests** — tests marked `pytest.mark.skip` or `pytest.mark.xfail`
  do not count as failures and will not block the gate.
