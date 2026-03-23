# Detect Environment Variables

Scan the project for environment variable patterns — from `.env.example` /
`.env.sample` template files, YAML/TOML/JSON config files that use `${VAR}`
interpolation, and source code references (`os.environ`, `os.getenv`,
`process.env`, `os.Getenv`, `ENV[]`).  Produces a structured, de-duplicated
inventory of every environment variable the project depends on.

## Instructions

### Step 1: Scan `.env` template files

Find all `.env.example`, `.env.sample`, and related template files:

```bash
find . \( \
  -name ".env.example" -o \
  -name ".env.sample"  -o \
  -name ".env.template" -o \
  -name ".env.dist"    -o \
  -name "*.env.example" \
\) -not -path "*/.git/*" -not -path "*/.venv/*" -not -path "*/node_modules/*" 2>/dev/null
```

For each file found, parse it:
- `KEY=value` lines → **required** variable with example value
- `# KEY=value` lines → **optional** variable (documented but commented out)
- Lines starting with `# ──` or similar → section headers, use as comment context

Record: variable name, required/optional, example value, any preceding comment.

---

### Step 2: Scan config files for `${VAR}` references

Look for shell-style variable interpolation in YAML, TOML, JSON, and INI files:

```bash
# Find all config files referencing ${VAR} or $VAR
grep -rn '\${[A-Z_][A-Z0-9_]*}' \
  --include="*.yaml" --include="*.yml" \
  --include="*.toml" --include="*.json" \
  --include="*.ini"  --include="*.cfg" \
  . 2>/dev/null | grep -v node_modules | grep -v ".git" | grep -v ".venv"

# Also catch bare $VAR_NAME (min 3 alpha chars to reduce noise)
grep -rn '\$[A-Z_][A-Z0-9_]\{2,\}' \
  --include="*.yaml" --include="*.yml" \
  --include="*.toml" \
  . 2>/dev/null | grep -v node_modules | grep -v ".git"
```

Record: variable name, file, line number.

---

### Step 3: Scan source code for runtime env reads

**Python** — `os.environ`, `os.getenv`, `os.environ.get`:

```bash
grep -rn \
  "os\.environ\.get\|os\.environ\[\|os\.getenv(" \
  --include="*.py" . 2>/dev/null | grep -v ".venv" | grep -v "__pycache__"
```

**JavaScript / TypeScript** — `process.env`:

```bash
grep -rn "process\.env\." \
  --include="*.js" --include="*.ts" --include="*.mjs" --include="*.tsx" \
  . 2>/dev/null | grep -v node_modules | grep -v ".git"
```

**Go** — `os.Getenv` / `os.LookupEnv`:

```bash
grep -rn "os\.Getenv\|os\.LookupEnv" \
  --include="*.go" . 2>/dev/null | grep -v vendor
```

**Ruby** — `ENV[` / `ENV.fetch`:

```bash
grep -rn "ENV\['\|ENV\[\"\|ENV\.fetch(" \
  --include="*.rb" . 2>/dev/null
```

Record: variable name, file, line number.

---

### Step 4: Or use the Python API directly

```python
from harness_skills.env_var_detector import detect_env_vars

result = detect_env_vars(".")

print(f"Total occurrences : {result.total_vars_found}")
print(f"Unique variables  : {len(result.unique_var_names)}")
print(f"dotenv files      : {result.dotenv_files_found}")
print(f"config files      : {result.config_files_found}")
print(f"source files      : {result.source_files_scanned}")
print()
print("All unique variable names:")
for name in result.unique_var_names:
    print(f"  {name}")
```

---

### Step 5: Build and emit the inventory

Aggregate all findings into a structured report:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Environment Variable Inventory
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  📄 Sources scanned
    dotenv templates : .env.example
    config files     : config/app.yaml
    source files     : 42 Python, 8 TypeScript

  📦 Variable summary  (14 unique, 27 total occurrences)

  REQUIRED (defined in .env.example without comment)
  ──────────────────────────────────────────────────
  DATABASE_URL       .env.example:3   (also in app/settings.py:12)
  SECRET_KEY         .env.example:5   (also in app/auth.py:8)

  OPTIONAL (commented out in .env.example)
  ─────────────────────────────────────────
  ANTHROPIC_API_KEY  .env.example:9   "sk-ant-..."
  OPENAI_API_KEY     .env.example:14  "sk-..."
  DEBUG              .env.example:18  "false"

  CONFIG REFERENCES only (not in .env.example)
  ─────────────────────────────────────────────
  DB_HOST            config/app.yaml:7
  DB_PORT            config/app.yaml:8

  CODE REFERENCES only (not in .env.example)
  ────────────────────────────────────────────
  PORT               server/main.py:3
  LOG_LEVEL          server/main.py:4
  SENTRY_DSN         monitoring/init.py:11

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ⚠  3 variables referenced in code but missing from .env.example
     PORT, LOG_LEVEL, SENTRY_DSN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Gap analysis** — after building the inventory:
1. Find all unique names in `source_code` and `config_file` entries.
2. Find all names that appear in `dotenv_example` entries.
3. Report the **difference** (vars in code/config but not documented in `.env.example`) as actionable gaps.

---

### Step 6: Machine-readable output (optional)

If invoked with `--json`, emit:

```json
{
  "command": "detect-env-vars",
  "status": "passed",
  "scanned_path": ".",
  "total_vars_found": 27,
  "unique_var_names": ["ANTHROPIC_API_KEY", "DATABASE_URL", "DEBUG", "..."],
  "dotenv_files_found": [".env.example"],
  "config_files_found": ["config/app.yaml"],
  "source_files_scanned": 50,
  "env_vars": [
    {
      "name": "DATABASE_URL",
      "source": "dotenv_example",
      "file_path": ".env.example",
      "line_number": 3,
      "default_value": "postgres://localhost/mydb",
      "comment": "Primary PostgreSQL connection string",
      "required": true
    }
  ]
}
```

---

### Notes

- This skill is **read-only** — it never modifies project files.
- `.git`, `.venv`, `node_modules`, `__pycache__`, `dist`, `build` are
  always skipped.
- Variables found in multiple files appear multiple times in `env_vars`
  but only once in `unique_var_names`.
- The gap analysis (vars in code but not in `.env.example`) is the most
  actionable output — it shows which secrets a new developer would miss.
- Related skills: `/detect-api-style` (API style detection), `/module-boundaries`
  (architecture), `/harness:context` (full codebase context).

---

### Key files

| Path | Purpose |
|------|---------|
| `harness_skills/env_var_detector.py` | Core detection logic |
| `harness_skills/models/env_vars.py` | Pydantic models |
| `tests/test_env_var_detector.py` | Full test suite |
| `skills/env-vars/SKILL.md` | Programmatic API documentation |
