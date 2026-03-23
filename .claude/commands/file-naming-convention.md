---
name: file-naming-convention
description: "File naming convention detector and linter-config generator. Scans the repository to infer per-extension naming rules (kebab-case, snake_case, PascalCase, camelCase, etc.), writes a versioned FILE-NAMING.md spec, and emits a ready-to-use .ls-lint.yml linter config. Use when: (1) bootstrapping a new project that needs consistent file naming, (2) documenting the existing naming convention for team review, (3) generating a CI-enforceable linter config from observed patterns, (4) auditing a codebase for naming violations. Triggers on: file naming convention, naming rules, file name linter, ls-lint, snake_case files, kebab-case files, PascalCase components, file name standard, naming spec, enforce file names."
---

# File Naming Convention

Scans the repository to detect the dominant **file naming style** per extension, produces a versioned `FILE-NAMING.md` specification, and emits a `.ls-lint.yml` linter config that enforces the detected (or specified) conventions in CI.

---

## Workflow

**Detect conventions and generate everything?**
→ [Default flow](#instructions) — runs detect → spec → linter config

**Generate the spec doc only?**
→ `/file-naming-convention --spec-only`

**Generate the linter config only?**
→ `/file-naming-convention --lint-only`

**Check a directory against detected or existing rules?**
→ `/file-naming-convention check <path>`

**Print the inferred rules without writing any files?**
→ `/file-naming-convention --dry-run`

---

## Usage

```bash
# Detect conventions and write FILE-NAMING.md + .ls-lint.yml (default)
/file-naming-convention

# Target a sub-directory instead of the repo root
/file-naming-convention --dir src/

# Set the spec version header
/file-naming-convention --version 1.2.0

# Write spec only — skip linter config generation
/file-naming-convention --spec-only

# Write linter config only — skip spec generation
/file-naming-convention --lint-only

# Dry run — print detected rules and preview outputs; write nothing
/file-naming-convention --dry-run

# Check a path against the current .ls-lint.yml (or detected rules)
/file-naming-convention check src/

# Emit machine-readable JSON instead of Markdown
/file-naming-convention --output json
```

---

## Instructions

### Step 1 — Parse arguments

Determine the operating mode and options:

```
mode       = "check" if "check <path>" in args else "generate"
check_path = args["check"] or None
scan_dir   = args["--dir"]      or "."
version    = args["--version"]  or "1.0.0"
spec_only  = "--spec-only"  in args
lint_only  = "--lint-only"  in args
dry_run    = "--dry-run"    in args
json_out   = args["--output"] == "json"
```

If `mode == "check"`, jump to [Step 6 — Check mode](#step-6--check-mode).

---

### Step 2 — Scan the repository for file names

Collect all tracked file paths under `scan_dir`, excluding common noise directories:

```bash
# List every file git knows about under scan_dir
git ls-files -- "<scan_dir>" 2>/dev/null \
  | grep -v -E "^(\.git|node_modules|\.venv|venv|__pycache__|dist|build|\.next|\.nuxt)/"
```

If the directory is not a git repo, fall back to:

```bash
find "<scan_dir>" -type f \
  -not -path "*/.git/*" \
  -not -path "*/node_modules/*" \
  -not -path "*/__pycache__/*" \
  -not -path "*/.venv/*" \
  -not -path "*/dist/*" \
  -not -path "*/build/*"
```

Collect the base name (no directory prefix) and extension for every file.

---

### Step 3 — Classify naming style per extension

For each file extension group, score each naming style based on observed base names.

**Naming styles and their detection patterns:**

| Style | Regex pattern | Example |
|---|---|---|
| `kebab-case` | `^[a-z][a-z0-9]*(-[a-z0-9]+)*$` | `my-component.tsx` |
| `snake_case` | `^[a-z][a-z0-9]*(_[a-z0-9]+)*$` | `my_module.py` |
| `camelCase` | `^[a-z][a-zA-Z0-9]*$` | `myService.ts` |
| `PascalCase` | `^[A-Z][a-zA-Z0-9]*$` | `MyComponent.tsx` |
| `UPPER_CASE` | `^[A-Z][A-Z0-9]*(_[A-Z0-9]+)*$` | `MAX_RETRIES.env` |
| `point.case` | `^[a-z][a-z0-9]*(\.[a-z0-9]+)+$` | `api.config.js` |
| `mixed` | (multiple styles present at ≥ 20% each) | — |

**Scoring algorithm:**

For each extension, count how many file base names (without extension) match each style pattern. Compute the percentage each style represents. The **dominant style** is the one exceeding **60 %** of files in that group.

If no style reaches 60 %, classify the group as **mixed** and list the top two styles.

Extensions with fewer than 3 file samples are labelled **insufficient-data** and omitted from generated rules.

**Pseudo-code:**

```python
from collections import defaultdict
import re

PATTERNS = {
    "kebab-case":  re.compile(r'^[a-z][a-z0-9]*(-[a-z0-9]+)*$'),
    "snake_case":  re.compile(r'^[a-z][a-z0-9]*(_[a-z0-9]+)*$'),
    "camelCase":   re.compile(r'^[a-z][a-zA-Z0-9]+$'),
    "PascalCase":  re.compile(r'^[A-Z][a-zA-Z0-9]+$'),
    "UPPER_CASE":  re.compile(r'^[A-Z][A-Z0-9]*(_[A-Z0-9]+)*$'),
    "point.case":  re.compile(r'^[a-z][a-z0-9]*(\.[a-z0-9]+)+$'),
}

counts    = defaultdict(lambda: defaultdict(int))  # ext → style → count
totals    = defaultdict(int)                        # ext → total files

for path in file_list:
    stem, ext = split_stem_ext(path)               # e.g. "my-component", ".tsx"
    ext = ext.lower()
    totals[ext] += 1
    for style, pat in PATTERNS.items():
        if pat.match(stem):
            counts[ext][style] += 1

rules = {}
for ext, total in totals.items():
    if total < 3:
        rules[ext] = {"style": "insufficient-data", "sample_count": total}
        continue
    dominant = max(counts[ext], key=counts[ext].get)
    pct      = counts[ext][dominant] / total
    if pct >= 0.60:
        rules[ext] = {"style": dominant, "confidence": round(pct, 2), "sample_count": total}
    else:
        top2 = sorted(counts[ext], key=counts[ext].get, reverse=True)[:2]
        rules[ext] = {"style": "mixed", "top_styles": top2, "sample_count": total}
```

---

### Step 4 — Generate the spec document (FILE-NAMING.md)

Skip this step if `--lint-only` was passed.

Write `FILE-NAMING.md` in the repo root (or `--dir` target) with the following sections:

#### Header

```markdown
# File Naming Convention Specification
> **Version:** <version>
> **Status:** Active
> **Generated:** <ISO-8601 date>
> **Scope:** All source files tracked in this repository

This document is the single source of truth for file naming conventions.
Every file added to this repository MUST follow the rules below.
Non-conforming names will be rejected by the CI linter (`.ls-lint.yml`).
```

#### Convention Table

```markdown
## Detected Conventions

| Extension | Required style | Confidence | Sample count |
|-----------|---------------|------------|--------------|
| `.py`     | `snake_case`  | 94 %       | 48 files     |
| `.tsx`    | `PascalCase`  | 87 %       | 23 files     |
| `.ts`     | `camelCase`   | 72 %       | 31 files     |
| `.md`     | `kebab-case`  | 100 %      | 12 files     |
| `.yml`    | `kebab-case`  | 83 %       | 6 files      |

> Extensions with fewer than 3 samples are not listed.
> Mixed extensions require manual review — see Notes.
```

#### Style Reference

```markdown
## Style Reference

| Style | Pattern | Valid examples | Invalid examples |
|-------|---------|----------------|-----------------|
| `kebab-case` | `^[a-z][a-z0-9]*(-[a-z0-9]+)*$` | `my-component`, `auth-utils` | `MyComponent`, `my_component` |
| `snake_case` | `^[a-z][a-z0-9]*(_[a-z0-9]+)*$` | `my_module`, `auth_utils` | `MyModule`, `my-module` |
| `camelCase` | `^[a-z][a-zA-Z0-9]+$` | `myService`, `authUtils` | `MyService`, `my-service` |
| `PascalCase` | `^[A-Z][a-zA-Z0-9]+$` | `MyComponent`, `AuthUtils` | `myComponent`, `my-component` |
| `UPPER_CASE` | `^[A-Z][A-Z0-9]*(_[A-Z0-9]+)*$` | `MAX_RETRIES`, `BASE_URL` | `maxRetries`, `max-retries` |
| `point.case` | `^[a-z][a-z0-9]*(\.[a-z0-9]+)+$` | `api.config`, `babel.config` | `apiConfig`, `api-config` |
```

#### Exceptions Section

```markdown
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
| `FILE-NAMING.md` | This file |

Add project-specific exceptions to `.ls-lint.yml` under the `ignore` key.
```

#### Enforcement Section

```markdown
## Enforcement

The conventions above are enforced automatically by `.ls-lint.yml` using
[ls-lint](https://ls-lint.org).  Run locally:

```bash
# Install (once)
npm install -g @ls-lint/ls-lint
# or: brew install ls-lint

# Check the entire repo
ls-lint

# Check a specific directory
ls-lint --dir src/
```

CI integration: the linter runs on every pull request.  A non-zero exit code
blocks the merge.
```

#### Changelog Section

```markdown
## Changelog

| Version | Date | Change |
|---------|------|--------|
| <version> | <date> | Initial convention document generated from codebase scan |
```

After writing, print:

```
✅  FILE-NAMING.md written → FILE-NAMING.md
    Version    : <version>
    Extensions : <N> rules generated
    Mixed      : <M> extensions flagged for manual review
```

---

### Step 5 — Generate the linter config (.ls-lint.yml)

Skip this step if `--spec-only` was passed.

Write `.ls-lint.yml` in the repo root with rules derived from Step 3.

**ls-lint style mapping:**

| Detected style | ls-lint value |
|---|---|
| `kebab-case` | `kebab-case` |
| `snake_case` | `snake_case` |
| `camelCase` | `camelCase` |
| `PascalCase` | `PascalCase` |
| `UPPER_CASE` | `regex:^[A-Z][A-Z0-9]*(_[A-Z0-9]+)*$` |
| `point.case` | `point` |

**Generated `.ls-lint.yml` structure:**

```yaml
# .ls-lint.yml — generated by /file-naming-convention <version> on <date>
# Docs: https://ls-lint.org
# Re-generate: /file-naming-convention --lint-only

ls:
  # Source files — one entry per detected extension
  .py:   snake_case
  .tsx:  PascalCase
  .ts:   camelCase | PascalCase   # multiple styles allowed with |
  .md:   kebab-case
  .yml:  kebab-case
  .yaml: kebab-case
  .json: kebab-case | snake_case

  # Config files at the root (apply to specific dirs if needed)
  .env:
    .env: regex:^\.[a-z]+(\.[a-z]+)*$

ignore:
  # Ecosystem-mandated file names exempt from the rules
  - README.md
  - CHANGELOG.md
  - CHANGELOG
  - LICENSE
  - Makefile
  - Dockerfile
  - Procfile
  - CLAUDE.md
  - FILE-NAMING.md
  - .ls-lint.yml
  - .gitignore
  - .gitattributes
  - .editorconfig
  - node_modules
  - .git
  - __pycache__
  - .venv
  - venv
  - dist
  - build
  - .next
  - .nuxt
```

For extensions classified as **mixed**, emit a comment noting that manual review is needed and skip generating a rule for that extension:

```yaml
  # ⚠️  .jsx — mixed styles detected (PascalCase 52%, camelCase 48%)
  #   Review manually and uncomment one of:
  #   .jsx: PascalCase
  #   .jsx: camelCase
  #   .jsx: PascalCase | camelCase
```

After writing, print:

```
✅  .ls-lint.yml written → .ls-lint.yml
    Rules   : <N> extension(s) configured
    Mixed   : <M> extension(s) skipped (manual review needed — see comments)
    Ignored : <K> ecosystem files exempted
```

---

### Step 6 — Check mode

When `mode == "check"`, run ls-lint against the given path using the existing `.ls-lint.yml` (or, if absent, the rules inferred in Step 3):

```bash
# If ls-lint is available
ls-lint --dir "<check_path>" 2>&1

# Fallback: validate with Python regex using detected rules
python - <<'EOF'
import re, sys
from pathlib import Path

STYLE_RE = {
    "kebab-case": re.compile(r'^[a-z][a-z0-9]*(-[a-z0-9]+)*$'),
    "snake_case":  re.compile(r'^[a-z][a-z0-9]*(_[a-z0-9]+)*$'),
    "camelCase":   re.compile(r'^[a-z][a-zA-Z0-9]+$'),
    "PascalCase":  re.compile(r'^[A-Z][a-zA-Z0-9]+$'),
}
# Load rules from .ls-lint.yml or use detected_rules dict
# ... (apply per-extension validation, collect violations)
EOF
```

Collect violations (file, expected style, actual name) and render the report below.

---

### Step 7 — Render the human-readable report

#### Header

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  File Naming Convention — <PASS ✅ | FAIL ❌>
  <N> violation(s)  ·  <M> extensions enforced  ·  dir: <scan_dir>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

#### Detected rules summary

```
Detected Rules
────────────────────────────────────────────────────
  Extension  Style         Confidence  Samples
  ─────────  ────────────  ──────────  ───────
  .py        snake_case      94 %        48
  .tsx       PascalCase      87 %        23
  .ts        camelCase       72 %        31
  .md        kebab-case     100 %        12
  .yml       kebab-case      83 %         6

  ⚠️  Mixed (manual review needed):
    .jsx — PascalCase 52% vs camelCase 48%
```

#### Violations section (only when violations > 0)

```
Violations
────────────────────────────────────────────────────
  src/components/myButton.tsx    expected: PascalCase   got: camelCase
  src/utils/AuthHelpers.py       expected: snake_case   got: PascalCase
  docs/API Reference.md          expected: kebab-case   got: space-separated

  3 violation(s) found across 3 file(s).
```

#### Clean result (no violations)

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅ All file names comply with the detected conventions.
  0 violations · <N> files checked · <M> extensions enforced
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### Step 8 — Emit the machine-readable manifest

Always append a fenced JSON block so downstream agents can parse results without re-running the skill:

```json
{
  "command": "file-naming-convention",
  "scan_dir": ".",
  "version": "1.0.0",
  "scanned_at": "<ISO-8601 timestamp>",
  "files_scanned": 142,
  "extensions_with_rules": 6,
  "extensions_mixed": 1,
  "passed": true,
  "total_violations": 0,
  "outputs": {
    "spec": "FILE-NAMING.md",
    "linter_config": ".ls-lint.yml"
  },
  "rules": {
    ".py":   { "style": "snake_case",  "confidence": 0.94, "sample_count": 48 },
    ".tsx":  { "style": "PascalCase",  "confidence": 0.87, "sample_count": 23 },
    ".ts":   { "style": "camelCase",   "confidence": 0.72, "sample_count": 31 },
    ".md":   { "style": "kebab-case",  "confidence": 1.00, "sample_count": 12 },
    ".yml":  { "style": "kebab-case",  "confidence": 0.83, "sample_count":  6 },
    ".jsx":  { "style": "mixed", "top_styles": ["PascalCase", "camelCase"], "sample_count": 21 }
  },
  "violations": []
}
```

When violations are present:

```json
{
  "passed": false,
  "total_violations": 3,
  "violations": [
    {
      "file": "src/components/myButton.tsx",
      "expected_style": "PascalCase",
      "actual_stem": "myButton",
      "extension": ".tsx"
    }
  ]
}
```

---

### Step 9 — Exit behaviour

| Outcome | Exit code |
|---|---|
| No violations, all outputs written | `0` |
| One or more naming violations | `1` |
| Mixed-only result (no clear convention, nothing written) | `0` (with warnings) |
| Scan directory not found / not readable | `2` |
| ls-lint not installed (check mode, no fallback) | `2` |

---

## Options

| Flag | Effect |
|---|---|
| `--dir <path>` | Root directory to scan (default: `.`) |
| `--version <semver>` | Version stamp for `FILE-NAMING.md` (default: `1.0.0`) |
| `--spec-only` | Write `FILE-NAMING.md` only; skip `.ls-lint.yml` |
| `--lint-only` | Write `.ls-lint.yml` only; skip `FILE-NAMING.md` |
| `--dry-run` | Print detected rules and preview outputs; write nothing |
| `--output json` | Print machine-readable JSON instead of styled text |
| `check <path>` | Check files at path against detected or existing rules |

---

## Key outputs

| File | Purpose |
|---|---|
| `FILE-NAMING.md` | Versioned convention spec (human-readable) |
| `.ls-lint.yml` | ls-lint config (machine-enforceable in CI) |

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Bootstrap file naming rules for a new project | **`/file-naming-convention`** ← you are here |
| Check for violations in a single directory | **`/file-naming-convention check src/`** |
| Regenerate the linter config after refactoring | **`/file-naming-convention --lint-only`** |
| Full code quality sweep (lint, types, tests) | `/check-code` |
| Detect the API style of a project | `/detect-api-style` |
| Enforce structured log fields | `/log-format-linter` |

---

## Notes

- **Read-only by default in dry-run** — pass `--dry-run` to preview without writing any files.
- **Detection is statistical**, not prescriptive. Projects with inconsistent existing conventions will produce **mixed** results for affected extensions. Review those manually.
- **ls-lint must be installed** for the `check` sub-command to run natively. If not available, the skill falls back to a Python regex validator with equivalent rules.
- **Single-word file names** (e.g. `index.ts`, `main.py`, `app.go`) match all styles — they are counted but excluded from confidence scoring to avoid skewing results.
- **Test files** (e.g. `*.test.ts`, `*.spec.py`) are scanned separately from their parent extension group when they represent > 20 % of total files for that extension, as test naming often differs from source naming.
- **Dot-files** (e.g. `.eslintrc`, `.env`) are excluded from convention scoring but included in the `ignore` list of the generated `.ls-lint.yml`.
- To lock a convention before the codebase grows, use `--dry-run` first, adjust the preview, then re-run without `--dry-run`.
- The generated `.ls-lint.yml` is idempotent — re-running the skill updates the file in place without losing hand-edited exceptions in the `ignore` list.
