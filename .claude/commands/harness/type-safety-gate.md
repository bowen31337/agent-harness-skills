# Harness Type-Safety Gate

Enforce a **zero-error policy** on static type checking and block merges that
contain any type errors.

The gate auto-detects the project's type checker from the project layout:

| Project marker | Checker selected |
|---|---|
| `pyproject.toml`, `setup.py`, `mypy.ini` | **mypy** |
| `tsconfig.json` | **tsc** (TypeScript compiler) |
| Explicit `checker:` in `harness.config.yaml` | As configured |

Policy: **zero errors tolerated**.  Warnings and notes are reported but never
cause a failure.  A single error blocks the merge.

---

## Usage

```bash
# Auto-detect checker and run with defaults
/harness:type-safety-gate

# Run mypy in strict mode (disallow_untyped_defs etc.)
/harness:type-safety-gate --strict

# Suppress specific error codes
/harness:type-safety-gate --ignore-error import --ignore-error attr-defined

# TypeScript project
/harness:type-safety-gate --checker tsc

# Advisory mode — report type errors as warnings, do not block
/harness:type-safety-gate --no-fail-on-error

# Integrate into a full evaluate run (types gate only)
/harness:evaluate --gate types
```

---

## Instructions

### Step 0: Resolve inputs

Collect the following from the invocation (applying defaults where absent):

| Argument | Default | Description |
|---|---|---|
| `--checker` | `auto` | Type checker: `auto`, `mypy`, `tsc`, `pyright` |
| `--strict` | `false` | Enable strict mode for mypy (`--strict`) |
| `--ignore-error CODE` | *(none)* | Suppress a specific error code (repeatable) |
| `--fail-on-error` | `true` | Exit non-zero on any type error |
| `--root` | `.` | Repository root for resolving relative paths |
| `paths` | `["."]` | Paths to pass to the checker |

---

### Step 1: Auto-detect (or validate) the type checker

Run auto-detection by checking for project markers in the repository root:

```python
# Python project → mypy
python_markers = [
    "pyproject.toml", "setup.py", "setup.cfg", "mypy.ini", ".mypy.ini"
]
if any((root / m).exists() for m in python_markers):
    checker = "mypy"

# TypeScript project → tsc
elif (root / "tsconfig.json").exists():
    checker = "tsc"

else:
    checker = None  # no checker found — gate skips gracefully
```

If `--checker` is supplied explicitly, skip auto-detection and use that value.

If no checker is found and no explicit override is given, emit:

```
⚠️  Type-safety gate: no supported project detected.
    Add a pyproject.toml (Python) or tsconfig.json (TypeScript) to the root,
    or set checker: mypy|tsc|pyright in harness.config.yaml.
    Gate skipped — no blocking.
```

Then exit with code `0` (graceful skip).

---

### Step 2: Run the type checker

#### Python — mypy

```bash
uv run python -m harness_skills.gates.types \
  --root <project-root> \
  --checker mypy \
  [--strict] \
  [--ignore-error CODE ...] \
  [--no-fail-on-error]
```

> **Fallback** — if `uv` is not available:
>
> ```bash
> python -m harness_skills.gates.types \
>   --root <project-root> \
>   --checker mypy \
>   [--strict]
> ```

#### TypeScript — tsc

```bash
uv run python -m harness_skills.gates.types \
  --root <project-root> \
  --checker tsc \
  [--ignore-error TS2304 ...] \
  [--no-fail-on-error]
```

Capture both stdout and the exit code.

---

### Step 3: Parse and render the result

The CLI writes a multi-line human-readable summary to stdout.  Parse the key
values and render them in this format:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Type-Safety Gate — <PASS ✅ | FAIL ❌>
  Checker  : <mypy | tsc | pyright>
  Errors   : <N>
  Warnings : <N>
  Strict   : <yes | no>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**If the gate passes** (zero errors):

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅  Type-safety gate passed — 0 type errors found
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**If the gate fails** (one or more errors), add a BLOCKING section:

```
🔴 BLOCKING — Type errors found, merge prevented
────────────────────────────────────────────────────
  <N> error(s) must be fixed before this branch can land.

  Top errors:
    src/module.py:12  [assignment]  — Incompatible types in assignment
    src/utils.py:44   [arg-type]    — Argument 1 has incompatible type
    ...

  Fix all type errors then re-run: python -m harness_skills.gates.types
```

List at most **10** errors in the output.  If there are more, append:

```
  … and <N−10> more.  Run the checker locally to see all errors.
```

**If the checker is not installed**:

```
🔴 BLOCKING — Type checker not found
────────────────────────────────────────────────────
  mypy is not installed.
  Install with: uv add mypy
  Then re-run the gate.
```

**Advisory mode** (`--no-fail-on-error`): replace every `🔴 BLOCKING` header
with `🟡 WARNING — advisory only, merge not blocked`.

---

### Step 4: Exit behaviour

| Outcome | Exit code |
|---|---|
| Zero type errors | `0` |
| One or more type errors (`fail_on_error=true`) | `1` |
| Checker not installed (`fail_on_error=true`) | `1` |
| Any violation (`fail_on_error=false`) | `0` (warnings emitted) |
| No supported project detected | `0` (gate skipped) |
| Internal gate error | `2` |

Mirror the CLI exit code.

If exit code is `1`, explicitly state:
*"This branch is **not** ready to merge — all type errors must be resolved
before the pull request can land."*

---

### Step 5: Suggest next steps on failure

When the gate fails, suggest concrete actions based on the checker:

#### mypy failures

1. **Run mypy locally with full output**
   ```bash
   mypy . --show-error-codes
   ```
2. **Run in strict mode** (catches more issues)
   ```bash
   mypy . --strict
   ```
3. **Ignore a specific code temporarily** (record the reason in a comment)
   ```yaml
   # harness.config.yaml
   profiles:
     default:
       gates:
         types:
           ignore_errors:
             - import          # third-party stubs missing — tracked in #NNN
   ```
4. **Add type stubs for missing packages**
   ```bash
   uv add types-requests types-PyYAML
   ```

#### tsc failures

1. **Run tsc locally**
   ```bash
   npx tsc --noEmit
   ```
2. **Fix errors by adding explicit types** — replace `any` with precise types.
3. **Suppress a specific diagnostic** (only if justified)
   ```yaml
   # harness.config.yaml
   profiles:
     default:
       gates:
         types:
           ignore_errors:
             - TS2304    # third-party types missing — tracked in #NNN
   ```

---

## Options

| Flag | Default | Effect |
|---|---|---|
| `--checker CHECKER` | `auto` | Force a specific checker: `auto`, `mypy`, `tsc`, `pyright`. |
| `--strict` | `false` | Enable strict mode (`--strict` for mypy). |
| `--ignore-error CODE` | *(none)* | Suppress an error code (repeatable). mypy: `import`. tsc: `TS2304`. |
| `--no-fail-on-error` | *(blocking by default)* | Downgrade all violations to warnings; gate always exits `0`. |
| `--root PATH` | `.` | Repository root for resolving relative paths. |
| `paths...` | `.` | Paths to check (passed to the type checker). |

---

## harness.config.yaml integration

The gate reads its configuration from `harness.config.yaml` when present.
Profile defaults:

| Profile | Enabled | Strict |
|---|---|---|
| `starter` | `false` | `false` |
| `standard` | `true` | `false` |
| `advanced` | `true` | `true` |

Override per-project:

```yaml
# harness.config.yaml
active_profile: standard

profiles:
  standard:
    gates:
      types:
        enabled: true
        fail_on_error: true
        strict: false
        checker: auto          # auto | mypy | tsc | pyright
        ignore_errors:
          - import             # suppress missing stub warnings
        paths:
          - src/               # only check the src/ directory
```

---

## CI/CD integration

### GitHub Actions — standalone type-safety gate

Add `.github/workflows/type-gate.yml` (already provided in this repo) to
enforce zero type errors on every pull request.  The workflow:

1. Installs dependencies with `uv sync`.
2. Runs `python -m harness_skills.gates.types --root . --checker mypy`.
3. Exits non-zero → GitHub marks the check as **failed** → merge is blocked.
4. Posts an error summary to the GitHub Step Summary.

### GitLab CI — `type-gate` job

The `type-gate` job in `.gitlab-ci.yml` runs on every merge request event and
fails the pipeline when type errors are found — blocking the MR via GitLab's
protected branch settings.

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Enforce zero type errors on a PR right now | **`/harness:type-safety-gate`** ← you are here |
| Run all 9 quality gates at once | `/harness:evaluate` |
| Enforce line coverage | `/harness:coverage-gate` |
| Identify stale docs or plans | `/harness:detect-stale` |
| Bootstrap the full harness | `/harness:create` |

---

## Notes

- **Read-only** — this skill never modifies source files.
- **Zero-error policy** — there is no configurable threshold.  A single
  type error blocks the merge when `fail_on_error: true`.
- **Warnings and notes are informational** — they appear in the output but
  never cause the gate to fail.
- **Graceful skip** — when no supported project is detected the gate exits
  `0` with a warning.  It never produces a false-positive block.
- **Strict mode** applies `--strict` to mypy (enables
  `disallow_untyped_defs`, `disallow_any_generics`, `warn_return_any`, and
  other checks).  For TypeScript, strict mode is controlled by
  `"strict": true` in the project's `tsconfig.json`.
- **`ignore_errors`** is a surgical escape hatch.  Every suppressed code
  should be documented with a comment and a tracking issue.
- **Exit code `2`** is reserved for internal gate errors (e.g., unexpected
  exception).  Distinguish it from `1` (policy violation) in CI scripts.
