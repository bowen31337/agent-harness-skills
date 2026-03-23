---
name: detect-env-vars
description: >
  Codebase analysis skill that detects environment variable patterns from
  .env.example / .env.sample template files, YAML/TOML/JSON/INI config files
  that use ${VAR} interpolation, and source code references (os.environ,
  os.getenv, process.env, os.Getenv, ENV[]) across Python, JavaScript,
  TypeScript, Go, Ruby, and Shell. Produces a structured, de-duplicated
  inventory of every environment variable the project depends on.
  Use when: (1) onboarding to a new project and need to know what env vars to
  set, (2) auditing which services / files read a given variable, (3) generating
  .env documentation, (4) validating that .env.example is complete against
  actual code usage. Triggers on: env var, environment variable, .env.example,
  process.env, os.environ, os.getenv, config variables, secret inventory,
  required environment, dotenv.
---

# Detect Environment Variables

## Overview

The `detect-env-vars` skill scans a project directory and builds a complete,
structured inventory of every environment variable in use.  It reads from
**three independent source types** and merges the results:

| Source | Examples | What is captured |
|--------|----------|------------------|
| **dotenv template** | `.env.example`, `.env.sample`, `.env.dist` | Variable names, example values, comments, required vs. optional |
| **config files** | `*.yaml`, `*.yml`, `*.toml`, `*.json`, `*.ini` | `${VAR}` / `$VAR` interpolation references |
| **source code** | `*.py`, `*.js`, `*.ts`, `*.go`, `*.rb`, `*.sh` | `os.environ`, `os.getenv`, `process.env`, `os.Getenv`, `ENV[]` calls |

---

## Quick Start

```python
from harness_skills.env_var_detector import detect_env_vars

result = detect_env_vars(".")          # scan current directory
print(result.unique_var_names)         # sorted, de-duplicated names
print(result.total_vars_found)         # total occurrences (not unique)
print(result.dotenv_files_found)       # .env.example paths scanned
print(result.source_files_scanned)     # number of source files inspected
```

```python
# Granular scanning
from harness_skills.env_var_detector import (
    scan_dotenv_file,
    scan_config_file,
    scan_source_file,
)
from pathlib import Path

root = Path(".")

# Parse a single .env.example
entries = scan_dotenv_file(Path(".env.example"), root)
for e in entries:
    status = "required" if e.required else "optional"
    print(f"  [{status}] {e.name}={e.default_value}  # {e.comment}")

# Extract ${VAR} refs from a YAML config
entries = scan_config_file(Path("config/app.yaml"), root)

# Scan a Python file for os.environ references
entries = scan_source_file(Path("app/settings.py"), root, "python")
```

---

## Function Reference

### `detect_env_vars(path, *, skip_dirs, include_config, include_source)`

Recursively scans *path* and returns an
[`EnvVarDetectionResult`](#envvardetectionresult).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | `str \| Path` | `"."` | Root directory (or single file) to scan |
| `skip_dirs` | `frozenset[str]` | `None` | Extra directory names to skip (merged with built-in skip list: `.git`, `.venv`, `node_modules`, `__pycache__`, …) |
| `include_config` | `bool` | `True` | Set `False` to skip config-file scanning |
| `include_source` | `bool` | `True` | Set `False` to skip source-code scanning |

### `scan_dotenv_file(path, root)`

Parses a single `.env.example`-style file.

- `KEY=value` lines → `required=True`
- `# KEY=value` lines → `required=False` (documented optional variable)
- Preceding comment lines are attached to the next variable as `comment`

### `scan_config_file(path, root)`

Scans any text-based config file for `${VAR_NAME}` and `$VAR_NAME` patterns.

### `scan_source_file(path, root, language)`

Scans a single source file.  Supported `language` values:
`"python"`, `"javascript"`, `"typescript"`, `"go"`, `"ruby"`, `"shell"`.

---

## Data Models

### `EnvVarEntry`

```python
class EnvVarEntry(BaseModel):
    name: str               # e.g. DATABASE_URL
    source: EnvVarSource    # dotenv_example | config_file | source_code
    file_path: str          # repo-relative path
    line_number: int | None
    default_value: str | None
    comment: str | None
    required: bool          # False = commented-out optional variable
```

### `EnvVarDetectionResult`

```python
class EnvVarDetectionResult(HarnessResponse):
    command: str                     # "detect-env-vars"
    status: Status                   # always "passed"
    scanned_path: str
    env_vars: list[EnvVarEntry]      # one per occurrence
    unique_var_names: list[str]      # sorted, de-duplicated names
    dotenv_files_found: list[str]
    config_files_found: list[str]
    source_files_scanned: int
    total_vars_found: int
```

---

## Detection Patterns

### Python
| Pattern | Regex |
|---------|-------|
| `os.environ['KEY']` | `os\.environ\[['"]KEY['"]` |
| `os.environ.get('KEY')` | `os\.environ\.get\(['"]KEY['"]` |
| `os.getenv('KEY')` | `os\.getenv\(['"]KEY['"]` |

### JavaScript / TypeScript
| Pattern | Regex |
|---------|-------|
| `process.env.KEY` | `process\.env\.KEY` |
| `process.env['KEY']` | `process\.env\[['"]KEY['"]` |

### Go
| Pattern | Regex |
|---------|-------|
| `os.Getenv("KEY")` | `os\.Getenv\("KEY"\)` |
| `os.LookupEnv("KEY")` | `os\.LookupEnv\("KEY"\)` |

### Ruby
| Pattern | Regex |
|---------|-------|
| `ENV['KEY']` | `ENV\[['"]KEY['"]` |
| `ENV.fetch('KEY')` | `ENV\.fetch\(['"]KEY['"]` |

### Config files
| Pattern | Notes |
|---------|-------|
| `${VAR_NAME}` | Shell-style brace substitution |
| `$VAR_NAME` | Bare dollar (min 3 chars to reduce false-positives) |

---

## Key Files

| Path | Purpose |
|------|---------|
| `harness_skills/env_var_detector.py` | Core detection logic — three scanners + `detect_env_vars()` |
| `harness_skills/models/env_vars.py` | Pydantic models: `EnvVarEntry`, `EnvVarDetectionResult`, `EnvVarSource` |
| `tests/test_env_var_detector.py` | Full test suite (40+ test cases) |
| `.claude/commands/detect-env-vars.md` | Agent slash-command documentation |

---

## Notes

- The skill is **read-only** — it never modifies project files.
- Variables found in multiple files produce one `EnvVarEntry` each (the `env_vars`
  list may contain duplicates across files); `unique_var_names` is always de-duplicated.
- The built-in skip list prevents scanning `.git`, `.venv`, `node_modules`,
  `__pycache__`, `dist`, `build`, `.claw-forge`, and `.tox`.
- Related skills: `/detect-api-style`, `/module-boundaries`, `/harness:context`.
