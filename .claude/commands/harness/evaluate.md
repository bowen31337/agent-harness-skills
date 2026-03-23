# Harness Evaluate

Run **all evaluation gates** in a single pass and emit a structured
`EvaluationReport` — the definitive quality signal for a branch before it is
merged or handed off.

Gates covered (in execution order):

| Gate | What it checks |
|---|---|
| `regression` | Test suite — no new failures allowed |
| `coverage` | Line-coverage threshold (default 90 %) |
| `security` | Vulnerability scan (known CVEs, secrets in source) |
| `performance` | Benchmark regressions against baseline |
| `architecture` | Import-layer violations and coupling rules |
| `principles` | Custom golden rules from `.claude/principles.yaml` |
| `docs_freshness` | Harness artefact staleness (default 30 days) |
| `types` | Static type checking (mypy / pyright) |
| `lint` | Code-style rules (ruff) |
| *(plugin gates)* | Project-specific checks defined in `harness.config.yaml` |

Use this skill any time you want the authoritative answer to:
*"Is this branch ready to ship?"*

---

## Usage

```bash
# Run all gates — human-readable table
/harness:evaluate

# Run all gates — machine-readable JSON (agent/CI usage)
/harness:evaluate --format json

# Run a subset of gates
/harness:evaluate --gate regression --gate coverage --gate security

# Override thresholds
/harness:evaluate --coverage-threshold 85 --max-staleness-days 14

# Point at a non-default project root
/harness:evaluate --project-root /path/to/repo
```

---

## Instructions

### Step 0: Resolve project root

If `--project-root` is supplied, use that.  Otherwise default to `.` (current
working directory).

---

### Step 1: Run the harness evaluation CLI

```bash
harness evaluate \
  --format json \
  2>&1
```

> **Fallback** — if `harness` is not on `PATH`:
>
> ```bash
> uv run python -m harness_skills.cli.main evaluate \
>   --format json \
>   2>&1
> ```

If individual gates are selected via `--gate`, append one `--gate <id>` flag per
requested gate:

```bash
harness evaluate --format json --gate regression --gate coverage
```

If `--coverage-threshold` or `--max-staleness-days` are supplied, pass them
through:

```bash
harness evaluate --format json --coverage-threshold 85 --max-staleness-days 14
```

Capture the full JSON stdout.  The output conforms to
`harness_skills/schemas/evaluation_report.schema.json`.

Key fields to extract:

| Field | Use |
|---|---|
| `passed` | Overall pass / fail |
| `summary.total_gates` | How many gates ran |
| `summary.passed_gates` | Passing count |
| `summary.failed_gates` | Failing count |
| `summary.skipped_gates` | Skipped count |
| `summary.blocking_failures` | `error`-severity violations — must fix |
| `summary.total_failures` | All violation count (all severities) |
| `gate_results[]` | Per-gate status, duration, failure count, message |
| `failures[]` | Flat list of every `GateFailure` across all gates |
| `metadata` | Provenance — `generated_at`, `git_sha`, `git_branch` |

Each `GateFailure` carries:
- `severity` — `error` \| `warning` \| `info`
- `gate_id` — which gate produced it
- `rule_id` — specific rule identifier (optional)
- `file_path` + `line_number` — location (null when not file-specific)
- `message` — human-readable description
- `suggestion` — actionable fix hint
- `context` — optional code snippet (optional)

---

### Step 2: Render the evaluation report

Output a structured report in this exact format:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Harness Evaluate — <PASS ✅ | FAIL ❌>
  <N> gate(s) run  ·  <P> passed  ·  <F> failed  ·  <S> skipped
  <B> blocking failure(s)  ·  <T> total violation(s)
  Branch: <git_branch>   SHA: <git_sha (first 8 chars)>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Gate Results
────────────────────────────────────────────────────
  regression      <PASSED|FAILED|SKIPPED>  <N ms>  <K failure(s)>
  coverage        <PASSED|FAILED|SKIPPED>  <N ms>  <K failure(s)>
  security        <PASSED|FAILED|SKIPPED>  <N ms>  <K failure(s)>
  performance     <PASSED|FAILED|SKIPPED>  <N ms>  <K failure(s)>
  architecture    <PASSED|FAILED|SKIPPED>  <N ms>  <K failure(s)>
  principles      <PASSED|FAILED|SKIPPED>  <N ms>  <K failure(s)>
  docs_freshness  <PASSED|FAILED|SKIPPED>  <N ms>  <K failure(s)>
  types           <PASSED|FAILED|SKIPPED>  <N ms>  <K failure(s)>
  lint            <PASSED|FAILED|SKIPPED>  <N ms>  <K failure(s)>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Rules for per-gate status:
- `passed` → ✅ on the row
- `failed` → ❌ on the row
- `skipped` → ⏭ on the row
- `error` (gate itself crashed) → ⚠️ on the row

If there are **blocking violations** (`severity == "error"`), add a BLOCKING
section **immediately after** the gate table:

```
🔴 BLOCKING — Must fix before merge
────────────────────────────────────────────────────
  [regression] · tests/test_api.py:42
  "test_create_user failed: AssertionError: expected 201, got 500"
  → Check the route handler for unhandled exceptions and add error handling.

  [security] SEC001 · src/auth/tokens.py:17
  "Hardcoded secret key detected"
  → Move the secret to an environment variable and rotate the exposed value.
```

If there are **warnings** (`severity == "warning"`):

```
🟡 WARNINGS — Advisory, non-blocking
────────────────────────────────────────────────────
  [coverage] · (global)
  "Line coverage 87.3 % is below the 90 % threshold"
  → Add tests for the uncovered branches in src/payments/processor.py.

  [lint] RUF013 · src/utils/helpers.py:12
  "Use `X | None` instead of `Optional[X]`"
  → Replace Optional[str] with str | None (Python 3.10+ union syntax).
```

If there are **info** items (`severity == "info"`):

```
🔵 INFO
────────────────────────────────────────────────────
  [docs_freshness] · docs/exec-plans/progress.md
  "Artefact last updated 28 days ago (threshold: 30 days)"
  → Consider refreshing this document soon.
```

If **all gates pass**:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅ All evaluation gates passed.
  0 violations · <N> gate(s) · ready to merge
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### Step 3: Emit structured data (agent-readable)

After the human-readable report, emit the raw `EvaluationReport` as a fenced
JSON block so downstream agents can parse it without re-running the gates.
Output the full JSON response from the CLI verbatim:

```json
{
  "schema_version": "1.0",
  "passed": false,
  "summary": {
    "total_gates": 9,
    "passed_gates": 7,
    "failed_gates": 2,
    "skipped_gates": 0,
    "error_gates": 0,
    "total_failures": 4,
    "blocking_failures": 2
  },
  "gate_results": [
    {
      "gate_id": "regression",
      "status": "failed",
      "duration_ms": 8420,
      "failure_count": 1,
      "message": "1 test failed",
      "failures": [
        {
          "severity": "error",
          "gate_id": "regression",
          "message": "test_create_user failed: AssertionError: expected 201, got 500",
          "file_path": "tests/test_api.py",
          "line_number": 42,
          "suggestion": "Check the route handler for unhandled exceptions and add error handling.",
          "rule_id": null,
          "context": null
        }
      ]
    }
  ],
  "failures": [],
  "metadata": {
    "generated_at": "2026-03-20T10:30:00Z",
    "schema_version": "1.0",
    "harness_version": "0.1.0",
    "project_root": ".",
    "git_sha": "a1b2c3d4",
    "git_branch": "feat/my-feature"
  }
}
```

The schema matches `harness_skills/schemas/evaluation_report.schema.json`.
Consumers should:
1. Check `passed` first.
2. If `false`, read `summary.blocking_failures` for scope.
3. Iterate `failures` ordered by `severity` descending (`error` → `warning` → `info`),
   then by `gate_id` in execution order.

---

### Step 3.5: Write EVALUATION.md with version identifier and generation timestamp

After emitting the structured JSON block, write (or update) `EVALUATION.md` so
every harness artifact carries a machine-readable provenance block that enables
staleness detection.

```bash
RUN_DATE=$(date '+%Y-%m-%d')
RUN_TIME=$(date '+%H:%M:%SZ')
RUN_TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
HEAD_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "no-git")
HEAD_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "no-git")
SKILL_VERSION=$(python3 -c "from importlib.metadata import version; print(version('harness-skills'))" 2>/dev/null || echo "unknown")
```

Write `EVALUATION.md` using this exact structure:

```markdown
<!-- harness:auto-generated — do not edit this block manually -->
last_updated: <RUN_DATE>
generated_at: <RUN_TIMESTAMP>
skill_version: <SKILL_VERSION>
head: <HEAD_HASH>
artifact: evaluation
<!-- /harness:auto-generated -->

# Evaluation Report

> Last run: <RUN_DATE> <RUN_TIME>  ·  Branch: <HEAD_BRANCH>  ·  SHA: <HEAD_HASH>

## Summary

| Metric | Value |
|---|---|
| Result | ✅ PASS / ❌ FAIL |
| Gates run | <total_gates> |
| Passed | <passed_gates> |
| Failed | <failed_gates> |
| Skipped | <skipped_gates> |
| Blocking failures | <blocking_failures> |
| Total violations | <total_failures> |

## Gate Results

| Gate | Status | Duration | Failures |
|---|---|---|---|
| regression | ✅ / ❌ / ⏭ | <N ms> | <K> |
| coverage | … | … | … |
| security | … | … | … |
| performance | … | … | … |
| architecture | … | … | … |
| principles | … | … | … |
| docs_freshness | … | … | … |
| types | … | … | … |
| lint | … | … | … |

*Populate table rows from `gate_results[]` in the `EvaluationReport`.*
```

**Rules:**
- If `EVALUATION.md` already exists and has a `<!-- harness:auto-generated … -->`
  block, replace that block and the Summary + Gate Results sections in-place.
  Any content below a `<!-- CUSTOM-START -->` marker is preserved verbatim.
- Stage the file with `git add EVALUATION.md` but do **not** auto-commit.
- In `--format json` mode (CI/agent invocations), still write the file but
  suppress the ASCII banner to keep stdout clean.

---

### Step 4: Exit behaviour

| Outcome | Exit code |
|---|---|
| All gates passed | `0` |
| Any `error`-severity violation | `1` |
| Gate runner internal error | `2` |

Mirror the CLI exit code.  If `passed == false` and `blocking_failures > 0`,
explicitly state: *"This branch is **not** ready to merge — fix the blocking
violations listed above before proceeding."*

If `passed == false` but `blocking_failures == 0` (only warnings/info), state:
*"This branch may be merged but the warnings above are recommended to address."*

---

## Options

| Flag | Default | Effect |
|---|---|---|
| `--gate GATE_ID` | *(all)* | Run only the specified gate(s). Repeat for multiple. Built-in IDs: `regression`, `coverage`, `security`, `performance`, `architecture`, `principles`, `docs_freshness`, `types`, `lint`. Plugin gate IDs (defined in `harness.config.yaml`) are also accepted. |
| `--coverage-threshold N` | `90.0` | Minimum line-coverage % for the `coverage` gate |
| `--max-staleness-days N` | `30` | Max artefact age (days) for the `docs_freshness` gate |
| `--project-root PATH` | `.` | Override the repository root |
| `--format json` | `table` | Emit only the raw JSON `EvaluationReport` with no human-readable header |
| `--format yaml` | `table` | Emit the same data serialised as YAML (human-friendly, machine-parseable) |
| `--format table` | `table` | Render a rich ASCII table (default, interactive terminal use) |

Multiple `--gate` flags may be combined.

---

## Custom Plugin Gates

Engineers can define **project-specific evaluation gates** directly in
`harness.config.yaml` without writing any Python code.  Plugin gates run a
shell command and treat exit code `0` as a pass, any other code as a failure.

```yaml
profiles:
  starter:
    gates:
      plugins:
        - gate_id: check_migrations
          gate_name: "DB Migration Safety"
          command: "python scripts/check_migrations.py"
          timeout_seconds: 30
          fail_on_error: true     # blocks merge on failure
          severity: error
          env:
            DATABASE_URL: "${DATABASE_URL}"   # expands from os.environ

        - gate_id: api_health
          gate_name: "API Health Check"
          command: "curl -sf http://localhost:8000/health"
          timeout_seconds: 10
          fail_on_error: false    # advisory — non-blocking
          severity: warning
```

**Plugin gate fields:**

| Field | Required | Default | Description |
|---|---|---|---|
| `gate_id` | ✅ | — | Unique identifier (lowercase, `^[a-z][a-z0-9_]*$`) |
| `gate_name` | ✅ | — | Human-readable display name |
| `command` | ✅ | — | Shell command to execute; exit 0 = pass |
| `timeout_seconds` | | `60` | Abort after this many seconds (1–3600) |
| `fail_on_error` | | `true` | `false` → advisory warning, does not block merge |
| `severity` | | `"error"` | Violation severity: `error` \| `warning` \| `info` |
| `env` | | `{}` | Extra env vars; values support `${VAR}` expansion |

Plugin gates appear in the `gate_results[]` array of the `EvaluationReport`
alongside built-in gates and are rendered in the same table output.  Multiple
plugin gates all execute even when one fails.

**Profile isolation:** Plugin gates are loaded from the *active* profile only.
Gates defined under `profiles.advanced.gates.plugins` are ignored when
`active_profile: starter`.

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Full quality gate before merge / hand-off | **`/harness:evaluate`** ← you are here |
| Fast architectural + principles sweep only | `/harness:lint` |
| Detect stale plans / blocked progress | `/harness:detect-stale` |
| Review a PR for principle compliance | `/review-pr` |
| Add / edit / remove principles | `/define-principles` |
| Usage analytics and gate effectiveness | `/harness:telemetry --analyze` |

---

## Notes

- **Read-only** — this skill never auto-fixes code.  For lint auto-fixes run
  `uv run ruff check . --fix && uv run ruff format .` separately.
- **Sequential gate execution** — gates run in declaration order.  A failing
  early gate (e.g., `regression`) does not stop later gates from running; all
  results are always collected.
- **Gate skipping** — a gate is `skipped` when disabled in `harness.config.yaml`
  or when its required tooling (e.g., `mypy`) is not installed.  Skipped gates
  do not contribute to `passed`/`failed` counts and never block a merge.
- **Coverage gate** — requires a previous test run with coverage data
  (e.g., `pytest --cov`). If no `.coverage` file or coverage XML is found,
  the gate is skipped with an info message.
- **Security gate** — uses static analysis; it does not execute code and will
  not catch every runtime vulnerability.  Supplement with dynamic scanning in CI.
- **Performance gate** — requires a baseline file (e.g., `benchmarks/baseline.json`).
  If none exists, the gate is skipped.
- **Principles gate** — loads `.claude/principles.yaml`.  If absent, the gate
  is skipped silently.
- **Schema version** — always `"1.0"`.  Consumers should check `schema_version`
  before parsing for forward-compatibility.
- Commit this file to version control so the whole team shares the same
  evaluation configuration.
