# File Naming Convention Specification
> **Version:** 1.0.0
> **Status:** Active
> **Generated:** 2026-03-24T00:00:00Z
> **Scope:** All source files tracked in this repository

This document is the single source of truth for file naming conventions.
Every file added to this repository MUST follow the rules below.
Non-conforming names will be rejected by the CI linter (`.ls-lint.yml`).

---

## Detected Conventions

| Extension | Required style | Confidence | Sample count |
|-----------|---------------|------------|--------------|
| `.py`     | `snake_case`  | 100 %      | 167 files    |
| `.md`     | `kebab-case`  | 91 %       | 97 files     |
| `.yml`    | `kebab-case`  | 92 %       | 12 files     |
| `.yaml`   | `kebab-case`  | 100 %      | 9 files      |
| `.sh`     | `kebab-case`  | 88 %       | 8 files      |
| `.json`   | *(mixed)*     | —          | 12 files     |

> Extensions with fewer than 3 samples are not listed (`.toml`, `.txt`, `.xml`, `.example`).
> Mixed extensions require manual review — see [Notes](#notes).

---

## Style Reference

| Style | Pattern | Valid examples | Invalid examples |
|-------|---------|----------------|-----------------|
| `snake_case` | `^[a-z][a-z0-9]*(_[a-z0-9]+)*$` | `my_module`, `auth_utils`, `stale_plan_detector` | `MyModule`, `my-module`, `myModule` |
| `kebab-case` | `^[a-z][a-z0-9]*(-[a-z0-9]+)*$` | `my-component`, `auth-utils`, `harness-init` | `my_component`, `MyComponent`, `myComponent` |
| `camelCase`  | `^[a-z][a-zA-Z0-9]+$`           | `myService`, `authUtils`                       | `MyService`, `my-service`, `my_service` |
| `PascalCase` | `^[A-Z][a-zA-Z0-9]+$`           | `MyComponent`, `AuthUtils`                     | `myComponent`, `my-component`, `my_component` |
| `UPPER_CASE` | `^[A-Z][A-Z0-9]*(_[A-Z0-9]+)*$` | `MAX_RETRIES`, `BASE_URL`                      | `maxRetries`, `max-retries`, `MaxRetries` |
| `point.case` | `^[a-z][a-z0-9]*(\.[a-z0-9]+)+$`| `api.config`, `babel.config`                   | `apiConfig`, `api-config`, `api_config` |

---

## Extension Rules

### Python (`.py`) → `snake_case`

All Python module files use `snake_case`. This aligns with [PEP 8](https://peps.python.org/pep-0008/#package-and-module-names).

```
✅  stale_plan_detector.py
✅  data_generator.py
✅  logging_config.py
❌  stale-plan-detector.py
❌  stalePlanDetector.py
❌  StalePlanDetector.py
```

### Markdown (`.md`) → `kebab-case`

All Markdown documentation files use `kebab-case`.

```
✅  harness-changelog.md
✅  agent-tool-design-guidelines.md
✅  plan-to-pr-convention.md
❌  harness_changelog.md
❌  harnessChangelog.md
```

### YAML (`.yml`, `.yaml`) → `kebab-case`

All YAML configuration files use `kebab-case`.

```
✅  harness-evaluate.yml
✅  coverage-gate.yml
✅  perf-thresholds.yml
❌  harness_evaluate.yml
❌  harnessEvaluate.yml
```

### Shell scripts (`.sh`) → `kebab-case`

All shell scripts use `kebab-case`.

```
✅  harness-init.sh
✅  worktree-create.sh
✅  harness-lint.sh
❌  harness_init.sh
❌  harnessInit.sh
```

### JSON (`.json`) — ⚠️ Mixed (manual review required)

The 12 JSON files in this repo use a mix of `kebab-case` (config/doc files) and `snake_case`
(schema files with compound extensions like `.schema.json`). Until a convention is agreed upon,
both styles are permitted. Add a project-specific rule to `.ls-lint.yml` once a standard is chosen.

Current observed split:
- `kebab-case` (config / telemetry files): `harness-telemetry.json`, `perf-timers.json`
- `snake_case` (schema files): `log_entry.schema.json`, `harness_manifest.schema.json`
- Compound (`point.case` sub-extension): `evaluation_report.schema.json`, `health_check_response.schema.json`

**Recommended resolution:** adopt `kebab-case` for plain JSON files, and
`snake_case.schema.json` for JSON Schema files.

---

## Exceptions

The following file names are exempt from the rules above because they are mandated
by their ecosystem or tooling:

| File name | Reason |
|-----------|--------|
| `README.md` | Ecosystem convention (GitHub, npm) |
| `CHANGELOG.md` | Ecosystem convention |
| `LICENSE` | Ecosystem convention (no extension) |
| `Makefile` | POSIX / ecosystem convention |
| `Dockerfile` | Docker ecosystem convention |
| `Procfile` | Heroku ecosystem convention |
| `CLAUDE.md` | Claude Code project convention |
| `AGENTS.md` | Claude Code multi-agent convention |
| `SKILL.md` | claw-forge skill convention |
| `FILE-NAMING.md` | This file |
| `conftest.py` | pytest ecosystem convention |
| `pyproject.toml` | Python packaging convention |
| `uv.lock` | uv lockfile convention |
| `.gitlab-ci.yml` | GitLab CI convention |
| `.pre-commit-config.yaml` | pre-commit ecosystem convention |
| `harness_manifest.json` | claw-forge runtime convention |
| `__init__.py` | Python package convention |

Add project-specific exceptions to `.ls-lint.yml` under the `ignore` key.

---

## Enforcement

The conventions above are enforced automatically by `.ls-lint.yml` using
[ls-lint](https://ls-lint.org). Run locally:

```bash
# Install (once)
npm install -g @ls-lint/ls-lint
# or: brew install ls-lint

# Check the entire repo
ls-lint

# Check a specific directory
ls-lint --dir src/
```

CI integration: the linter runs on every pull request via `.github/workflows/`.
A non-zero exit code blocks the merge.

---

## Notes

- **Single-word stems** (e.g. `main.py`, `boot.py`, `runner.py`) are valid in any lowercase style.
  They are included in sample counts but excluded from confidence scoring.
- **Test files** follow the same convention as their parent extension. Python test files use
  `snake_case` (e.g. `test_telemetry.py`, `test_boot.py`) — consistent with source files.
- **Dunder files** (`__init__.py`, `__main__.py`) are ecosystem conventions and are exempt.
- **Dotfiles** (`.gitignore`, `.editorconfig`, etc.) are excluded from convention scoring.
- The generated `.ls-lint.yml` is idempotent — re-running
  `/file-naming-convention --lint-only` updates the file without losing hand-edited exceptions.

---

## Changelog

| Version | Date | Change |
|---------|------|--------|
| 1.0.0 | 2026-03-24 | Initial convention document generated from codebase scan (309 files across 10 extensions) |
