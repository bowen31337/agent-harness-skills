# Harness Security Check Gate

Enforce three security checks on a branch and block merges that have
unresolved issues:

1. **Secret scanning** — regex scan of all source files for hardcoded
   credentials, private keys, and API tokens.
2. **Dependency vulnerability audit** — reads a pre-generated pip-audit or
   npm audit JSON report and flags packages with CVEs at or above the
   configured severity threshold (default: **HIGH**).
3. **Input validation verification** — scans Python/JS/TS source files for
   dangerous patterns indicating missing input sanitisation (e.g.
   `eval(request.data)`, raw SQL string formatting with request objects,
   pickle deserialisation of user-supplied bytes).

Any violation with severity `error` causes the gate to exit non-zero and
block the pull request.  Use `--no-fail-on-error` for advisory-only runs.

---

## Usage

```bash
# Run all three sub-checks with defaults
/harness:security-check-gate

# Also enable secret scanning (off by default)
/harness:security-check-gate --scan-secrets

# Lower the CVE severity bar to catch MEDIUM vulnerabilities too
/harness:security-check-gate --severity MEDIUM

# Point at a non-default audit report
/harness:security-check-gate --audit-report reports/pip-audit-report.json

# Advisory mode — report all findings as warnings, never block
/harness:security-check-gate --no-fail-on-error

# Suppress known false positives by ID
/harness:security-check-gate --ignore-ids CVE-2023-12345 hardcoded-password

# Integrate into a full evaluate run
/harness:evaluate --gate security --severity MEDIUM
```

---

## Instructions

### Step 0: Resolve inputs

Collect the following from the invocation (applying defaults where absent):

| Argument | Default | Description |
|---|---|---|
| `--severity` | `HIGH` | Minimum CVE severity to report: `CRITICAL`, `HIGH`, `MEDIUM`, or `LOW` |
| `--scan-secrets` | `false` | Enable hardcoded secret scanning (off by default to avoid noise) |
| `--scan-dependencies` | `true` | Parse the dependency audit report and flag vulnerable packages |
| `--scan-input-validation` | `true` | Detect unsafe input-handling patterns in source files |
| `--fail-on-error` | `true` | Exit non-zero on any error-severity violation (`--no-fail-on-error` for advisory) |
| `--audit-report` | *(auto-detect)* | Path to the dependency audit JSON report; if omitted, the gate searches the project root for known report names |
| `--ignore-ids` | *(none)* | Space-separated list of CVE IDs or rule IDs to suppress |
| `--project-root` | `.` | Repository root for resolving relative paths |

---

### Step 1: Verify prerequisites

Before running the gate, check that the required inputs are in place.

**Dependency audit (when `--scan-dependencies=true`):**

The gate reads an existing audit report — it does not run the package
manager itself.  If no report file is found, the gate emits a *warning*
(not a blocking error) and skips this sub-check.  Remind the user to
generate a fresh report first:

| Stack | Generate command |
|---|---|
| Python / pip-audit | `pip-audit --format json -o pip-audit-report.json` |
| Python / safety | `safety check --json > vulnerability-report.json` |
| JavaScript / npm | `npm audit --json > npm-audit.json` |
| JavaScript / yarn | `yarn audit --json > npm-audit.json` |

If the report is missing, emit:

```
⚠️  No dependency audit report found.
    Generate one first, then re-run the gate.
    Example: pip-audit --format json -o pip-audit-report.json
```

**Secret scanning (when `--scan-secrets=true`):**

No prerequisites — the scanner reads source files directly.

**Input validation (when `--scan-input-validation=true`):**

No prerequisites — the scanner reads source files directly.

---

### Step 2: Run the security gate CLI

```bash
uv run python -m harness_skills.gates.security \
  --root <project-root> \
  --severity <severity-threshold> \
  [--scan-secrets | --no-scan-secrets] \
  [--scan-dependencies | --no-scan-dependencies] \
  [--scan-input-validation | --no-scan-input-validation] \
  [--fail-on-error | --no-fail-on-error] \
  [--ignore-ids <id1> <id2> ...]
```

> **Fallback** — if `uv` is not available:
>
> ```bash
> python -m harness_skills.gates.security \
>   --root <project-root> \
>   --severity <severity-threshold>
> ```

Capture both stdout and the exit code.

---

### Step 3: Parse and render the result

The CLI writes a structured summary to stdout.  Parse the key values and
render them in this format:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Security Gate — <PASS ✅ | FAIL ❌>
  Secrets found          : <N>
  Vulnerable deps        : <N>  (threshold: <SEVERITY>)
  Unsafe input patterns  : <N>
  Total violations       : <N>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**If all checks pass:**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅  Security gate passed — no issues found
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**If secrets are found** (`fail_on_error=true`):

```
🔴 BLOCKING — Hardcoded secrets detected
────────────────────────────────────────────────────
  <file>:<line>  (<rule-id>)  — <message>
  ...

  Remove all hardcoded credentials before merging.
  Use environment variables or a secrets manager instead.
  Hint: git-secrets, truffleHog, or detect-secrets can
  help find historical leaks in the git history.
```

**If vulnerable dependencies are found** (`fail_on_error=true`):

```
🔴 BLOCKING — Vulnerable dependencies detected
────────────────────────────────────────────────────
  <package>==<version>  (<CVE-ID>)  — <description>
  Upgrade to: <fix_versions>
  ...

  Update or patch the affected packages before merging.
  Hint: pip-audit --fix will auto-upgrade where possible.
```

**If unsafe input handling is found** (`fail_on_error=true`):

```
🔴 BLOCKING — Unsafe input handling detected
────────────────────────────────────────────────────
  <file>:<line>  (<rule-id>)  — <message>
  ...

  Validate and sanitise all user-supplied data before use.
  Never pass raw request objects to eval/exec/pickle/subprocess.
```

**If the audit report is missing** (always advisory):

```
🟡 WARNING — Dependency audit report not found
────────────────────────────────────────────────────
  No report found.  Dependency scanning skipped.
  Run: pip-audit --format json -o pip-audit-report.json
```

**Advisory mode** (`--no-fail-on-error`): replace every `🔴 BLOCKING` header
with `🟡 WARNING — advisory only, merge not blocked`.

---

### Step 4: Exit behaviour

| Outcome | Exit code |
|---|---|
| All enabled checks pass | `0` |
| Any error-severity violation (`fail_on_error=true`) | `1` |
| Missing audit report (always advisory) | `0` (warning emitted) |
| Any violation (`fail_on_error=false`) | `0` (warnings emitted) |
| Gate runner internal error | `2` |

Mirror the CLI exit code.

If exit code is `1`, explicitly state:
*"This branch is **not** ready to merge — resolve the security issues listed
above before the pull request can land."*

If exit code is `0` but warnings were emitted, state:
*"The gate is in advisory mode; findings are recorded but the merge is not
blocked."*

---

### Step 5: Suggest next steps on failure

**On hardcoded secrets:**

1. **Remove the secret from source** and replace with an env-var lookup:
   ```python
   import os
   password = os.environ["DB_PASSWORD"]
   ```
2. **Rotate the exposed credential immediately** — assume it is compromised.
3. **Scrub git history** if the commit has already been pushed:
   ```bash
   git filter-repo --path-glob '*.py' --invert-paths  # or BFG Repo Cleaner
   ```
4. **Suppress a known false positive** (only if confirmed safe):
   ```yaml
   # harness.config.yaml
   profiles:
     default:
       gates:
         security:
           ignore_ids: [hardcoded-password]
   ```

**On vulnerable dependencies:**

1. **Auto-upgrade** where pip-audit supports it:
   ```bash
   pip-audit --fix
   ```
2. **Pin to a safe version** manually in `requirements.txt` or `pyproject.toml`.
3. **Ignore a known false positive** (document the justification):
   ```yaml
   # harness.config.yaml
   profiles:
     default:
       gates:
         security:
           ignore_ids: [CVE-2023-12345]  # not exploitable in our usage — see #NNN
   ```

**On unsafe input handling:**

1. **Use parameterised queries** instead of string formatting:
   ```python
   # Bad
   cursor.execute(f"SELECT * FROM t WHERE id = {request.args['id']}")

   # Good
   cursor.execute("SELECT * FROM t WHERE id = ?", (request.args.get("id"),))
   ```
2. **Never pass user input to `eval` or `exec`** — redesign the feature.
3. **Use Pydantic / marshmallow** to validate and coerce request payloads
   before processing.

---

## Options

| Flag | Default | Effect |
|---|---|---|
| `--severity LEVEL` | `HIGH` | Minimum CVE severity to report: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` |
| `--scan-secrets` | `false` | Enable hardcoded secret scanning |
| `--no-scan-secrets` | *(disables scanning)* | Disable secret scanning |
| `--scan-dependencies` | `true` | Enable dependency vulnerability audit |
| `--no-scan-dependencies` | *(disables scanning)* | Disable dependency audit |
| `--scan-input-validation` | `true` | Enable unsafe input handling detection |
| `--no-scan-input-validation` | *(disables scanning)* | Disable input validation check |
| `--no-fail-on-error` | *(blocking by default)* | Downgrade all violations to warnings; gate always exits `0` |
| `--ignore-ids ID…` | *(none)* | CVE, GHSA, PYSEC, or rule IDs to suppress (space-separated) |
| `--project-root PATH` | `.` | Repository root for resolving relative paths |

---

## harness.config.yaml integration

The gate reads its configuration from `harness.config.yaml` when present.
Profile defaults:

| Profile | Enabled | Secrets | Severity | Input validation |
|---|---|---|---|---|
| `starter` | no | — | — | — |
| `standard` | yes | no | `HIGH` | yes |
| `advanced` | yes | yes | `MEDIUM` | yes |

Override per-project:

```yaml
# harness.config.yaml
active_profile: standard

profiles:
  standard:
    gates:
      security:
        enabled: true
        fail_on_error: true
        severity_threshold: HIGH      # CRITICAL | HIGH | MEDIUM | LOW
        scan_dependencies: true       # run against pip-audit-report.json
        scan_secrets: false           # set true to scan for hardcoded creds
        scan_input_validation: true   # detect eval/pickle/sql injection patterns
        ignore_ids: []                # e.g. [CVE-2023-12345, hardcoded-password]
```

A flag passed at invocation time **always takes precedence** over the YAML
value.

---

## CI/CD integration

### GitHub Actions — standalone security gate

Add `.github/workflows/security-gate.yml` to enforce the gate on every pull
request.  The workflow:

1. Runs `pip-audit --format json -o pip-audit-report.json` to generate fresh
   dependency data.
2. Runs `python -m harness_skills.gates.security --severity HIGH --scan-secrets`.
3. Exits non-zero → GitHub marks the check as **failed** → merge is blocked.
4. Posts a violation summary to the GitHub Step Summary.

```yaml
name: Security Gate
on: [pull_request]

jobs:
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install pip-audit harness-skills
      - run: pip-audit --format json -o pip-audit-report.json || true
      - run: |
          python -m harness_skills.gates.security \
            --severity ${{ vars.SECURITY_SEVERITY || 'HIGH' }} \
            --scan-secrets
```

### GitLab CI — `security-gate` job

```yaml
security-gate:
  stage: test
  script:
    - pip install pip-audit harness-skills
    - pip-audit --format json -o pip-audit-report.json || true
    - python -m harness_skills.gates.security --severity HIGH --scan-secrets
  only:
    - merge_requests
```

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Run all three security sub-checks on a PR right now | **`/harness:security-check-gate`** ← you are here |
| Run all 9 quality gates at once | `/harness:evaluate` |
| Enforce code-coverage threshold | `/harness:coverage-gate` |
| Detect stale docs or plans | `/harness:detect-stale` |
| Check coding principles only | `/harness:lint` |

---

## Notes

- **Read-only** — this skill never modifies source files, dependencies, or
  the state service.
- **Dependency audit requires a prior scan** — the gate reads an existing
  report; it does not invoke `pip-audit` or `npm audit` itself.  Generate
  fresh audit data before the gate runs in CI.
- **Secret scanning is opt-in** — default `scan_secrets=false` avoids
  spurious failures on projects that have not yet audited their codebase
  for leaked credentials.  Enable it once you have resolved any existing
  issues.
- **Missing audit report is advisory** — if no pip-audit / npm audit JSON
  file is found, the gate emits a *warning* (not a blocking error) and skips
  the dependency sub-check.  This avoids blocking projects that have not yet
  integrated `pip-audit` into their pipeline.
- **Input validation patterns are heuristic** — the scanner detects well-known
  anti-patterns (``eval``, ``exec``, ``pickle.loads``, ``subprocess.*``,
  raw SQL formatting) but cannot catch all forms of missing validation.
  Treat its output as a starting point, not an exhaustive audit.
- **Suppress false positives responsibly** — before adding an ID to
  ``ignore_ids``, confirm the vulnerability is genuinely not exploitable in
  your usage and document the justification in a comment referencing an issue
  or PR.
- **Exit code `2`** is reserved for internal gate errors (e.g. unexpected
  exception in the runner).  Distinguish it from `1` (policy violation) in
  CI scripts.
- **Supported secret patterns**: hardcoded-password, hardcoded-api-key,
  hardcoded-token, pem-private-key, aws-access-key-id,
  github-personal-access-token.
- **Supported unsafe input patterns**: eval-user-input, exec-user-input,
  sql-string-format, pickle-user-input, shell-injection.
