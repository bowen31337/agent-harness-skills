# CI Pipeline Integration

Generate GitHub Actions workflow and GitLab CI job that run `harness evaluate` on every pull request / merge request. Writes configuration files and confirms what was created.

## Instructions

### Step 1: Detect existing CI configuration

```bash
# Check for existing GitHub Actions workflows
ls .github/workflows/ 2>/dev/null && echo "GHA_EXISTS=1" || echo "GHA_EXISTS=0"

# Check for existing GitLab CI
ls .gitlab-ci.yml 2>/dev/null && echo "GITLAB_EXISTS=1" || echo "GITLAB_EXISTS=0"

# Check for pyproject.toml / uv.lock to confirm uv-based project
ls pyproject.toml uv.lock 2>/dev/null

# Confirm harness CLI is available
uv run harness --help 2>/dev/null | head -5 || echo "harness CLI not found — check pyproject.toml entry points"
```

Report what you found:
- Whether GitHub Actions and/or GitLab CI already exist
- Whether the project uses uv (pyproject.toml + uv.lock present)
- Whether the harness CLI is installed

### Step 2: Create the GitHub Actions workflow

Create the directory and write the workflow file:

```bash
mkdir -p .github/workflows
```

Write `.github/workflows/harness-evaluate.yml`:

```yaml
# .github/workflows/harness-evaluate.yml
# Runs harness evaluation gates on every pull request.
# Exit codes: 0 = all gates passed, 1 = gate failures, 2 = internal error.
name: Harness Evaluate

on:
  pull_request:
    branches: ["**"]

jobs:
  harness-evaluate:
    name: Evaluation Gates
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          # Full history lets the coverage gate compute diff coverage
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          version: "latest"

      - name: Install dependencies
        run: uv sync --frozen

      - name: Run harness evaluate
        id: evaluate
        run: |
          set +e
          result=$(uv run harness evaluate --format json 2>&1)
          exit_code=$?
          echo "$result" | tee evaluation-report.json
          echo "exit_code=$exit_code" >> "$GITHUB_OUTPUT"
          echo "passed=$(echo "$result" | jq -r '.passed // false')" >> "$GITHUB_OUTPUT"
          exit $exit_code

      - name: Summarize results in job log
        if: always()
        run: |
          if [ ! -f evaluation-report.json ]; then
            echo "No evaluation report found."
            exit 0
          fi

          passed=$(jq -r '.passed // false' evaluation-report.json)
          if [ "$passed" = "true" ]; then
            icon="✅"
            headline="All evaluation gates passed"
          else
            icon="❌"
            headline="Evaluation gates FAILED"
          fi

          {
            echo "## $icon Harness Evaluate — $headline"
            echo ""
            jq -r '
              .summary as $s |
              "| Metric | Value |",
              "|--------|-------|",
              "| Gates passed | \($s.passed_gates)/\($s.total_gates) |",
              "| Blocking failures | \($s.blocking_failures) |",
              "| Total failures | \($s.total_failures) |"
            ' evaluation-report.json
            echo ""

            failure_count=$(jq '[.failures[] | select(.severity == "error")] | length' evaluation-report.json)
            if [ "$failure_count" -gt 0 ]; then
              echo "### Blocking Failures"
              echo ""
              jq -r '
                .failures[] | select(.severity == "error") |
                "- **\(.message)**" +
                (if .file_path then
                  " — `\(.file_path)" +
                  (if .line_number then ":\(.line_number)" else "" end) + "`"
                else "" end) +
                (if .suggestion then "\n  > 💡 \(.suggestion)" else "" end)
              ' evaluation-report.json
            fi
          } >> "$GITHUB_STEP_SUMMARY"

      - name: Upload evaluation report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: harness-evaluation-report
          path: evaluation-report.json
          retention-days: 30
```

### Step 3: Create the GitLab CI job

#### Case A — no `.gitlab-ci.yml` exists yet

Write a standalone `.gitlab-ci.yml`:

```yaml
# .gitlab-ci.yml
# Runs harness evaluation gates on every merge request.
# Exit codes: 0 = all gates passed, 1 = gate failures, 2 = internal error.

stages:
  - evaluate

harness-evaluate:
  stage: evaluate
  image: python:3.12-slim

  variables:
    # Pin uv version for reproducibility; bump as needed.
    UV_VERSION: "0.5.0"
    PIP_NO_CACHE_DIR: "1"

  before_script:
    - pip install --quiet uv==$UV_VERSION
    - uv sync --frozen

  script:
    - |
      set +e
      result=$(uv run harness evaluate --format json 2>&1)
      exit_code=$?
      echo "$result" | tee evaluation-report.json

      # Human-readable summary for CI log
      passed=$(echo "$result" | python3 -c "import json,sys; r=json.load(sys.stdin); print(r.get('passed', False))" 2>/dev/null)
      if [ "$passed" = "True" ]; then
        echo ""
        echo "✅ All evaluation gates passed."
      else
        echo ""
        echo "❌ Evaluation gates FAILED — blocking failures:"
        echo "$result" | python3 - <<'PYEOF'
import json, sys

try:
    r = json.load(sys.stdin)
except Exception as e:
    print(f"Could not parse report: {e}")
    sys.exit(0)

s = r.get("summary", {})
print(f"  Gates: {s.get('passed_gates', '?')}/{s.get('total_gates', '?')} passed")
print(f"  Blocking failures: {s.get('blocking_failures', '?')}")
print()

for f in r.get("failures", []):
    if f.get("severity") == "error":
        loc = f.get("file_path", "")
        if f.get("line_number"):
            loc += f":{f['line_number']}"
        print(f"  [error] {f['message']}" + (f"  —  {loc}" if loc else ""))
        if f.get("suggestion"):
            print(f"    → {f['suggestion']}")
PYEOF
      fi

      exit $exit_code

  artifacts:
    when: always
    paths:
      - evaluation-report.json
    expire_in: 30 days

  # Run only on merge requests (not on every push to branches)
  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
```

#### Case B — `.gitlab-ci.yml` already exists

Append the following job block to the existing file. First show it to the user, then append:

```yaml
# ── Harness evaluate (add to your existing .gitlab-ci.yml) ──────────────────
harness-evaluate:
  stage: test   # Change to match your pipeline's test/validate stage
  image: python:3.12-slim

  variables:
    UV_VERSION: "0.5.0"
    PIP_NO_CACHE_DIR: "1"

  before_script:
    - pip install --quiet uv==$UV_VERSION
    - uv sync --frozen

  script:
    - |
      set +e
      result=$(uv run harness evaluate --format json 2>&1)
      exit_code=$?
      echo "$result" | tee evaluation-report.json

      passed=$(echo "$result" | python3 -c "import json,sys; r=json.load(sys.stdin); print(r.get('passed', False))" 2>/dev/null)
      if [ "$passed" != "True" ]; then
        echo "❌ Evaluation gates FAILED"
        echo "$result" | python3 -c "
import json, sys
r = json.load(sys.stdin)
for f in r.get('failures', []):
    if f.get('severity') == 'error':
        loc = f.get('file_path', '')
        if f.get('line_number'): loc += f':{f[\"line_number\"]}'
        print(f'  [error] {f[\"message\"]}' + (f'  —  {loc}' if loc else ''))
        if f.get('suggestion'): print(f'    → {f[\"suggestion\"]}')
"
      fi
      exit $exit_code

  artifacts:
    when: always
    paths:
      - evaluation-report.json
    expire_in: 30 days

  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
```

Also remind the user to add `evaluate` (or `test`) to the top-level `stages:` list if it isn't already there.

### Step 4: Verify the files were written

```bash
# Confirm GitHub Actions workflow exists
cat .github/workflows/harness-evaluate.yml | head -10

# Confirm GitLab CI job exists (standalone or within existing)
grep -n "harness-evaluate" .gitlab-ci.yml 2>/dev/null || echo "harness-evaluate job not found in .gitlab-ci.yml"
```

### Step 5: Validate YAML syntax

```bash
# Python ships with a YAML parser — use it for quick validation
python3 -c "
import yaml, sys

files = ['.github/workflows/harness-evaluate.yml', '.gitlab-ci.yml']
for f in files:
    try:
        with open(f) as fh:
            yaml.safe_load(fh)
        print(f'✅  {f} — valid YAML')
    except FileNotFoundError:
        print(f'⚠️   {f} — not found (skipping)')
    except yaml.YAMLError as e:
        print(f'❌  {f} — YAML error: {e}')
        sys.exit(1)
"
```

### Step 6: Confirm and summarize

Print a final summary:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  CI Pipeline Integration — complete
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ✅  .github/workflows/harness-evaluate.yml
       Trigger : pull_request (all branches)
       Command : uv run harness evaluate --format json
       Artifact: evaluation-report.json (30 days)

  ✅  .gitlab-ci.yml  (harness-evaluate job)
       Trigger : merge_request_event
       Command : uv run harness evaluate --format json
       Artifact: evaluation-report.json (30 days)

  Both pipelines:
    • Exit 0 → all gates passed, PR/MR unblocked
    • Exit 1 → gate failures written to evaluation-report.json
    • Exit 2 → internal harness error (check runner logs)

  Next steps:
    1. Commit and push these files to your feature branch.
    2. Open a PR/MR to verify the workflow runs.
    3. Inspect the evaluation-report.json artifact for gate details.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Notes

- **Python version**: Both configs use Python 3.12. Change `python-version` / `image` if your project requires a different version.
- **uv version pinning**: The GitLab config pins `UV_VERSION=0.5.0`. Update as needed; GitHub Actions uses `version: "latest"` via the official setup action.
- **Coverage threshold**: To override the default 90% threshold, pass `--coverage-threshold 80` (or your preferred value) to the harness command.
- **Running specific gates only**: Add `--gate regression --gate types` to scope the run (useful for fast PR feedback).
- **Secrets**: If your project needs `ANTHROPIC_API_KEY` or similar, add it as a repository secret (GitHub) or CI/CD variable (GitLab) and reference it with `${{ secrets.ANTHROPIC_API_KEY }}` / `$ANTHROPIC_API_KEY`.
