---
name: import-ordering
description: "Import ordering and grouping rules generator. Scans Python source files to detect the prevailing import ordering and grouping conventions (isort four-group order, blank-line separation, future-annotations-first, alphabetical sorting within groups, relative imports), then generates a principle entry for .claude/principles.yaml that matches the most common patterns found. Use when: (1) bootstrapping import conventions for a new Python project, (2) documenting the existing import style for team review, (3) generating a principles entry that check-code and review-pr can enforce, (4) auditing a codebase for import ordering violations. Triggers on: import ordering, import grouping, isort, import conventions, import rules, import style, import sorting, from __future__ import annotations, first-party imports, third-party imports, stdlib imports."
---

# Import Ordering Skill

Scans Python source files to detect the prevailing **import ordering and grouping conventions**, then writes a principle entry to `.claude/principles.yaml` that matches the most common patterns found across the codebase.

---

## Workflow

**Detect conventions and write the principle?**
→ [Default flow](#instructions) — runs scan → majority-vote → write principle

**Preview what would be written without touching any file?**
→ `/import-ordering --dry-run`

**Target a sub-directory or override first-party packages?**
→ `/import-ordering --dir src/ --first-party mypackage,otherpackage`

**Emit a ruff isort config snippet alongside the principle?**
→ `/import-ordering --with-ruff-config`

**Print detection stats only (no principle written)?**
→ `/import-ordering --stats-only`

---

## Usage

```bash
# Scan the current directory and write a principle entry (default)
/import-ordering

# Target a specific sub-directory
/import-ordering --dir src/

# Override auto-detected first-party package names
/import-ordering --first-party harness_skills,harness_tools

# Require at least N parseable files before setting majority flags
/import-ordering --min-files 5

# Set the principle ID explicitly (default: next available P-series ID)
/import-ordering --principle-id P013

# Preview without writing anything
/import-ordering --dry-run

# Show detection statistics only
/import-ordering --stats-only

# Also emit a ruff [tool.ruff.lint.isort] config snippet
/import-ordering --with-ruff-config

# Write to a custom principles file path
/import-ordering --target .claude/principles.yaml
```

---

## Instructions

### Step 1 — Parse arguments

Determine operating mode and options:

```
scan_dir       = args["--dir"]           or "."
first_party    = args["--first-party"]   or None   # comma-separated list → split
min_files      = int(args["--min-files"] or 1)
principle_id   = args["--principle-id"]  or None   # None = auto-assign
dry_run        = "--dry-run"  in args
stats_only     = "--stats-only" in args
with_ruff      = "--with-ruff-config" in args
target         = args["--target"] or ".claude/principles.yaml"
```

If `first_party` is given as a comma-separated string, split it into a list:
```python
fp_list = [s.strip() for s in first_party.split(",")] if first_party else None
```

---

### Step 2 — Scan Python files and detect conventions

Use `harness_skills.generators.import_convention_detector`:

```python
from harness_skills.generators.import_convention_detector import (
    detect_import_conventions,
    generate_import_principle,
)

result = detect_import_conventions(
    scan_dir,
    known_first_party=fp_list,   # None = auto-detect from __init__.py dirs
    min_files=min_files,
)
```

The scanner classifies every top-level import in every `.py` file under `scan_dir`
(excluding `.git`, `__pycache__`, `.venv`, `venv`, `env`, `node_modules`, `dist`,
`build`, `.tox`, `site-packages`) into one of four **isort groups**:

| Group | Criterion |
|---|---|
| `future` | `from __future__ import …` |
| `stdlib` | Module in `sys.stdlib_module_names` |
| `third_party` | Everything else not first-party |
| `first_party` | Listed in `known_first_party`, or relative import (`from .x import …`) |

For each file the scanner records:

| Flag | Meaning |
|---|---|
| `future_annotations_first` | `from __future__ import annotations` is the very first import |
| `group_order_correct` | All groups appear in `future → stdlib → third_party → first_party` order |
| `blank_line_separation` | Every group boundary has at least one blank line between it |
| `sorted_within_groups` | Imports within every group are alphabetically sorted |
| `has_relative_imports` | At least one `from .module import …` is present |

**Majority-vote rule:** A convention flag is set `True` in the result when more than
50 % of successfully parsed files exhibit that pattern.  Files that fail to parse
(syntax errors) are counted but excluded from the majority calculation.

**Auto-detection of first-party packages:** When `known_first_party` is `None`, the
scanner looks for top-level directories under `scan_dir` that contain an
`__init__.py` and treats them as first-party.

---

### Step 3 — Print detection statistics

Always print the scan summary regardless of `--dry-run` or `--stats-only`:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Import Convention Detector — <scan_dir>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Files scanned          : <files_scanned>
  Files with parse errors: <files_with_parse_errors>
  First-party packages   : <detected_first_party or "(none detected)">

  Convention                     Files  Majority
  ─────────────────────────────  ─────  ────────
  future-annotations-first       <N>    <✅ YES / ❌ NO>
  group order (future→…→fp)      <N>    <✅ YES / ❌ NO>
  blank-line between groups      <N>    <✅ YES / ❌ NO>
  alphabetical within groups     <N>    <✅ YES / ❌ NO>
  relative imports used          <N>    <✅ YES / ❌ NO>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

If `--stats-only` is passed, stop here and exit 0.

---

### Step 4 — Generate the principle entry

```python
principle = generate_import_principle(
    result,
    principle_id=principle_id or "",   # empty = auto-assigned on merge
    applies_to=["review-pr", "check-code"],
)
```

The generated principle dict has these keys:

| Key | Value |
|---|---|
| `id` | Provided `--principle-id` or empty string (auto-assigned during merge) |
| `category` | `"style"` |
| `severity` | `"suggestion"` |
| `applies_to` | `["review-pr", "check-code"]` |
| `rule` | Human-readable rule text built from majority-vote flags (see below) |
| `generated_by` | `"import_convention_detector"` |
| `files_scanned` | `result.files_scanned` |
| `files_with_parse_errors` | `result.files_with_parse_errors` |

**Rule text construction** — one sentence is appended for each `True` flag:

1. **Group order (always present):**
   - True → `"Imports must follow the four-group isort order — future, stdlib, third-party, first-party."`
   - False → `"Imports should be organised into logical groups."`

2. **Blank-line separation** (when True):
   `"Each group must be separated by exactly one blank line; no blank lines within a group."`

3. **Future annotations first** (when True):
   `` "`from __future__ import annotations` must appear as the very first import in every Python module." ``

4. **Alphabetical sorting** (when True):
   `"Imports within each group must be sorted alphabetically."`

5. **Relative imports** (when True):
   `` "Intra-package references must use relative imports (`from .module import Thing`) rather than absolute paths that repeat the package name." ``

6. **Evidence note** (always appended):
   `"Detected from the prevailing pattern across <N> file(s) in the codebase; enforced by isort or ruff [tool.ruff.lint.isort]. First-party packages detected: <pkg1>, <pkg2>."`

Print a preview of the rule:

```
  Generated principle:
  ────────────────────────────────────────────────────────────────
  ID       : <id or "(auto-assigned)">
  Category : style
  Severity : suggestion
  Applies  : review-pr, check-code

  Rule:
    <full rule text, wrapped at 72 chars>
  ────────────────────────────────────────────────────────────────
```

---

### Step 5 — Optionally emit ruff isort config snippet

When `--with-ruff-config` is passed, generate a `[tool.ruff.lint.isort]` snippet
based on the detected settings.  Print it to stdout and (unless `--dry-run`) write
it to `import-ordering-ruff.toml` in the repo root:

```toml
# import-ordering-ruff.toml
# Generated by /import-ordering on <ISO-8601 date>
# Paste this block into your pyproject.toml under [tool.ruff.lint.isort]

[tool.ruff.lint.isort]
known-first-party = [<detected_first_party as quoted list>]
force-sort-within-sections = <true if uses_sorted_within_groups else false>
# lines-after-imports = 2   # uncomment to enforce blank line after all imports
```

After writing:

```
✅  import-ordering-ruff.toml written → import-ordering-ruff.toml
    First-party : <packages>
    Sorted      : <true / false>
```

---

### Step 6 — Write (or dry-run) the principle

If `--dry-run`, print:

```
  DRY RUN — no files were written.
  To apply, re-run without --dry-run.
```

and exit 0.

Otherwise, use `scripts/import_principles.py` logic to merge the principle into
`.claude/principles.yaml`:

```python
from pathlib import Path
import sys
sys.path.insert(0, "scripts")
from import_principles import (
    PrincipleEntry,
    load_existing_principles,
    merge_principles,
    write_principles,
)

target_path = Path(target)
existing    = load_existing_principles(target_path)

entry = PrincipleEntry(
    id=principle.get("id", ""),
    category=principle["category"],
    severity=principle["severity"],
    applies_to=principle["applies_to"],
    rule=principle["rule"],
)

merge_result = merge_principles(existing, [entry])
if merge_result.has_errors:
    for err in merge_result.errors:
        print(err, file=sys.stderr)
    sys.exit(1)

if merge_result.added:
    all_principles = existing + merge_result.added
    write_principles(all_principles, target_path)
    print(f"  Wrote {len(all_principles)} principle(s) → {target_path}")
elif merge_result.skipped:
    skipped_entry, reason = merge_result.skipped[0]
    print(f"  ⚠️  Principle '{skipped_entry.id}' already exists — skipped.")
    print(f"     Reason: {reason}")
```

After writing, print:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅  Import principle written → <target>
      ID       : <assigned id>
      Category : style
      Severity : suggestion
      Applies  : review-pr, check-code
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### Step 7 — Emit the machine-readable manifest

Always append a fenced JSON block so downstream agents can parse the results:

```json
{
  "command": "import-ordering",
  "scan_dir": ".",
  "scanned_at": "<ISO-8601 timestamp>",
  "files_scanned": 48,
  "files_with_parse_errors": 0,
  "detected_first_party": ["harness_skills", "harness_tools"],
  "conventions": {
    "future_annotations_first": true,
    "group_order_correct":      true,
    "blank_line_separation":    true,
    "sorted_within_groups":     true,
    "relative_imports":         false
  },
  "principle": {
    "id":         "P013",
    "category":   "style",
    "severity":   "suggestion",
    "applies_to": ["review-pr", "check-code"]
  },
  "outputs": {
    "principles_file": ".claude/principles.yaml",
    "ruff_snippet":    null
  },
  "dry_run": false
}
```

---

### Step 8 — Exit behaviour

| Outcome | Exit code |
|---|---|
| Principle written (or already existed) | `0` |
| Dry-run completed | `0` |
| Stats-only completed | `0` |
| No Python files found under scan_dir | `0` (with warning) |
| Validation error in generated principle | `1` |
| Strict-ID collision (`--strict-ids`) | `1` |
| scan_dir not found or not readable | `2` |
| Import error (harness_skills not installed) | `2` |

---

## Convention Groups Reference

The four-group ordering enforced by isort (and ruff with `I` rules enabled):

```python
# Group 1 — future
from __future__ import annotations

# Group 2 — stdlib
import os
import sys
from pathlib import Path

# Group 3 — third-party
import pydantic
import requests

# Group 4 — first-party
from harness_skills.models import Foo
from harness_tools.cli import run
```

Each group boundary must be separated by **exactly one blank line**.

Within each group, imports should be **alphabetically sorted** (case-insensitive).

---

## Options

| Flag | Effect |
|---|---|
| `--dir <path>` | Root directory to scan (default: `.`) |
| `--first-party <pkgs>` | Comma-separated list of first-party package names (default: auto-detect) |
| `--min-files <N>` | Minimum parseable files required before setting majority flags (default: `1`) |
| `--principle-id <ID>` | Explicit ID for the generated principle (default: auto-assigned P-series) |
| `--dry-run` | Preview without writing any files |
| `--stats-only` | Print detection stats and exit; do not generate a principle |
| `--with-ruff-config` | Also emit a `[tool.ruff.lint.isort]` TOML snippet |
| `--target <path>` | Target principles file (default: `.claude/principles.yaml`) |
| `--strict-ids` | Exit 1 if the generated principle ID already exists |

---

## Key files

| Path | Purpose |
|---|---|
| `harness_skills/generators/import_convention_detector.py` | Core scanner and principle generator |
| `scripts/import_principles.py` | CLI / library for merging principles into `.claude/principles.yaml` |
| `.claude/principles.yaml` | Project-wide golden rules (output of this skill) |
| `pyproject.toml` | Add `[tool.ruff.lint.isort]` here to enforce the detected rules |

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Generate import ordering rules for a new Python project | **`/import-ordering`** ← you are here |
| Preview what would be detected without writing anything | **`/import-ordering --dry-run`** |
| See raw stats without generating a principle | **`/import-ordering --stats-only`** |
| Define any type of project principle interactively | `/define-principles` |
| Full code quality sweep (lint, types, tests) | `/check-code` |
| Review a PR for principle violations | `/review-pr` |
| Detect file naming conventions | `/file-naming-convention` |
| Generate a structured logging spec | `/logging-convention` |

---

## Notes

- **Detection is statistical.** A convention flag is only set when more than 50 % of
  successfully parsed files exhibit it.  Use `--min-files` to require a larger sample
  before trusting the result.
- **Parse errors are excluded** from the majority calculation but reported in the
  stats.  A file with a syntax error still counts toward `files_scanned`.
- **Auto-detected first-party packages** are any top-level directories directly under
  `scan_dir` that contain an `__init__.py`.  Use `--first-party` to override.
- **Re-running is safe.** If a principle with the same ID already exists in
  `.claude/principles.yaml`, the skill skips it with a warning.  Use `--principle-id`
  with a fresh ID to add an updated entry.
- **Ruff enforcement.** After generating the principle, add
  `ruff check --select I .` to your CI pipeline to enforce it automatically.
  The `--with-ruff-config` flag generates the exact `pyproject.toml` snippet needed.
- **Single-import files** (only one import statement) still contribute to
  `future_annotations_first` and `group_order_correct` counts, but trivially satisfy
  `blank_line_separation` and `sorted_within_groups`.
