# Harness Coverage Gate

Enforce a **minimum line-coverage threshold** on a branch and block merges that
fall below the bar.

The gate reads an existing coverage report (XML, JSON, or LCOV), compares the
measured percentage against the configured threshold, and exits non-zero when
coverage is insufficient — causing any CI system hooked to this exit code to
block the pull request.

Default threshold: **90 %**.  Override with `--threshold N`.

---

## Usage

```bash
# Run with default threshold (90 %)
/harness:coverage-gate

# Raise or lower the bar
/harness:coverage-gate --threshold 85
/harness:coverage-gate --threshold 95

# Point at a non-default coverage file
/harness:coverage-gate --coverage-file reports/coverage.xml

# Use a specific report format instead of auto-detecting
/harness:coverage-gate --format lcov --coverage-file lcov.info

# Advisory mode — report below-threshold as a warning, do not block
/harness:coverage-gate --no-fail-on-error

# Integrate into a full evaluate run (threshold override only for coverage)
/harness:evaluate --gate coverage --coverage-threshold 85
```

---

## Instructions

### Step 0: Resolve inputs

Collect the following from the invocation (applying defaults where absent):

| Argument | Default | Description |
|---|---|---|
| `--threshold` | `90.0` | Minimum required line-coverage % (0–100) |
| `--coverage-file` | `coverage.xml` | Path to the coverage report (relative to project root) |
| `--format` | `auto` | Report format: `auto`, `xml`, `json`, `lcov` |
| `--fail-on-error` | `true` | Exit non-zero on failure (`--no-fail-on-error` for advisory) |
| `--project-root` | `.` | Repository root for resolving relative paths |

---

### Step 1: Verify a coverage report exists

Before running the gate, check that the coverage report is present.  If it is
missing, remind the user to run their test suite with coverage collection enabled
first.  Provide the correct command for the detected stack:

| Stack | Generate command |
|---|---|
| Python / pytest | `pytest --cov --cov-report=xml` |
| Python / coverage.py | `coverage run -m pytest && coverage xml` |
| JavaScript / Jest | `jest --coverage` (produces `coverage/lcov.info`) |
| Go | `go test ./... -coverprofile=coverage.out` |
| JVM / Maven | `mvn test` (JaCoCo plugin produces `target/site/jacoco/jacoco.xml`) |

If no report file exists and the user did not supply `--coverage-file`, emit:

```
⚠️  No coverage report found at 'coverage.xml'.
    Run your tests with coverage enabled first, then re-run the gate.
    Example: pytest --cov --cov-report=xml
```

Then exit with code `1`.

---

### Step 2: Run the coverage gate CLI

```bash
uv run python -m harness_skills.gates.coverage \
  --root <project-root> \
  --threshold <threshold> \
  --coverage-file <coverage-file> \
  --format <format> \
  [--no-fail-on-error]
```

> **Fallback** — if `uv` is not available:
>
> ```bash
> python -m harness_skills.gates.coverage \
>   --root <project-root> \
>   --threshold <threshold> \
>   --coverage-file <coverage-file> \
>   --format <format>
> ```

Capture both stdout and the exit code.

---

### Step 3: Parse and render the result

The CLI writes a multi-line human-readable summary to stdout.  Parse the key
values and render them in this format:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Coverage Gate — <PASS ✅ | FAIL ❌>
  Measured : <actual>%
  Required : <threshold>%
  Delta    : <actual − threshold> pp   (<above threshold | below threshold>)
  Report   : <path/to/coverage-file>  [<format>]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**If the gate passes** (`actual >= threshold`):

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅  Coverage gate passed — <actual>% ≥ <threshold>%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**If the gate fails** (`actual < threshold`), add a BLOCKING section:

```
🔴 BLOCKING — Coverage too low, merge prevented
────────────────────────────────────────────────────
  Measured  : <actual>%
  Required  : <threshold>%
  Shortfall : <threshold − actual> pp

  Add tests to cover the uncovered lines before merging.
  Hint: run `pytest --cov --cov-report=term-missing` to identify gaps.
```

**If the report is missing**:

```
🔴 BLOCKING — Coverage report not found
────────────────────────────────────────────────────
  Expected at: <path>
  Run `pytest --cov --cov-report=xml` first.
```

**If the report cannot be parsed**:

```
🔴 BLOCKING — Coverage report parse error
────────────────────────────────────────────────────
  File   : <path>
  Reason : <error message>
  Verify the file is a valid coverage.py XML / JSON / LCOV tracefile.
```

**Advisory mode** (`--no-fail-on-error`): replace every `🔴 BLOCKING` header
with `🟡 WARNING — advisory only, merge not blocked`.

---

### Step 4: Exit behaviour

| Outcome | Exit code |
|---|---|
| Coverage ≥ threshold | `0` |
| Coverage < threshold (`fail_on_error=true`) | `1` |
| Report missing (`fail_on_error=true`) | `1` |
| Report parse error (`fail_on_error=true`) | `1` |
| Any violation (`fail_on_error=false`) | `0` (warnings emitted) |
| Gate runner internal error | `2` |

Mirror the CLI exit code.

If exit code is `1`, explicitly state:
*"This branch is **not** ready to merge — coverage must reach **<threshold>%** before
the pull request can land."*

If exit code is `0` but warnings were emitted, state:
*"Coverage is below the advisory threshold but the gate is in warning-only mode."*

---

### Step 5: Suggest next steps on failure

When the gate fails, suggest concrete actions:

1. **Identify uncovered lines**
   ```bash
   pytest --cov --cov-report=term-missing
   ```
2. **Find the files with lowest coverage**
   ```bash
   coverage report --sort=cover | head -20
   ```
3. **Generate an HTML report** for a visual gap-analysis
   ```bash
   coverage html && open htmlcov/index.html
   ```
4. **Temporarily lower the threshold** (only if justified — record the reason):
   ```yaml
   # harness.config.yaml
   profiles:
     default:
       gates:
         coverage:
           threshold: 85   # reduced from 90 — see issue #NNN
   ```

---

## Options

| Flag | Default | Effect |
|---|---|---|
| `--threshold N` | `90.0` | Minimum required line-coverage % (0–100). Fractions accepted (e.g. `87.5`). |
| `--coverage-file PATH` | `coverage.xml` | Path to the coverage report, relative to `--project-root`. |
| `--format FORMAT` | `auto` | Report format. `auto` detects from file extension. Valid: `auto`, `xml`, `json`, `lcov`. |
| `--no-fail-on-error` | *(blocking by default)* | Downgrade violations to warnings; gate always exits `0`. |
| `--project-root PATH` | `.` | Repository root for resolving `--coverage-file`. |

---

## harness.config.yaml integration

The gate reads its threshold from `harness.config.yaml` when present.
Profile defaults:

| Profile | Threshold | Branch coverage |
|---|---|---|
| `starter` | 60 % | off |
| `standard` | 80 % | on |
| `advanced` | 90 % | on |

Override per-project:

```yaml
# harness.config.yaml
active_profile: standard

profiles:
  standard:
    gates:
      coverage:
        enabled: true
        threshold: 90          # override standard default of 80
        branch_coverage: true
        coverage_file: coverage.xml
        report_format: auto
        fail_on_error: true
```

A `--threshold` flag passed at invocation time **always takes precedence** over
the YAML value.

---

## CI/CD integration

### GitHub Actions — standalone coverage gate

Add `.github/workflows/coverage-gate.yml` (already provided in this repo) to
enforce the gate on every pull request.  The workflow:

1. Runs `pytest --cov --cov-report=xml` to generate `coverage.xml`.
2. Runs `python -m harness_skills.gates.coverage --threshold $COVERAGE_THRESHOLD`.
3. Exits non-zero → GitHub marks the check as **failed** → merge is blocked.
4. Posts a coverage badge and delta summary to the GitHub Step Summary.

Customise the threshold via the repository variable `COVERAGE_THRESHOLD`
(Settings → Variables) or by editing the workflow's `env:` block.

### GitLab CI — `coverage-gate` job

The `coverage-gate` job in `.gitlab-ci.yml` runs on every merge request event,
produces `coverage-report.json`, and fails the pipeline when coverage is below
the threshold — blocking the MR from being merged via GitLab's protected branch
settings.

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Enforce coverage on a PR right now | **`/harness:coverage-gate`** ← you are here |
| Run all 9 quality gates at once | `/harness:evaluate` |
| Identify stale docs or plans | `/harness:detect-stale` |
| Check coding principles only | `/harness:lint` |
| Bootstrap the full harness | `/harness:create` |

---

## Notes

- **Read-only** — this skill never modifies source files or tests.
- **Requires a prior test run** — the gate reads an existing report; it does not
  run the test suite itself.  Always generate fresh coverage data before the gate
  runs in CI (see Step 1 above).
- **Line coverage only** (default) — branch coverage is opt-in via
  `branch_coverage: true` in `harness.config.yaml`.  The CLI gate currently
  enforces line coverage regardless of `branch_coverage`; branch coverage
  awareness is a planned enhancement.
- **Format auto-detection** — determined by file extension:
  `.xml` → `xml`, `.json` → `json`, `.info` / `.out` / `.lcov` → `lcov`.
  Unrecognised extensions fall back to `xml`.
- **Supported parsers**:
  - XML: coverage.py (`line-rate` attribute) and JaCoCo (`<counter type="LINE">`)
  - JSON: coverage.py (`totals.percent_covered`)
  - LCOV: sums all `LF:` / `LH:` counters across the tracefile
- **Threshold precision** — comparisons use floating-point arithmetic.
  `87.999... < 88.0` → gate fails.  Pass an exact value to avoid surprises.
- **Exit code `2`** is reserved for internal gate errors (e.g., unexpected
  exception in the runner).  Distinguish it from `1` (policy violation) in
  CI scripts.
