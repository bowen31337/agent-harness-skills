# Define Principles

Add, edit, or remove project-specific golden rules that are enforced by `check-code` and
`review-pr`. Principles are stored in `.claude/principles.yaml` and automatically loaded by
other skills.

---

## Usage

```bash
# Interactive prompt — guided add / edit / remove workflow
/define-principles

# Config-file import — non-interactive bulk import from a YAML file
/define-principles --from-file path/to/import.yaml

# Preview what --from-file would add without writing to disk
/define-principles --from-file path/to/import.yaml --dry-run

# Fail loudly if any imported principle has an ID that already exists
/define-principles --from-file path/to/import.yaml --strict-ids
```

Both workflows write the same `.claude/principles.yaml` format and auto-generate
`docs/PRINCIPLES.md`.  The interactive prompt is a guided editor for the same YAML.

---

## Instructions

### Step 0 — Parse arguments and choose a mode

Inspect the arguments passed after `/define-principles`:

```
if --from-file <path> is present:
    → follow the "Config-file import mode" path (Step 1B)
else:
    → follow the "Interactive prompt mode" path (Step 1A)
```

---

## Mode A — Interactive Prompt

### Step 1A: Load existing principles

Check whether `.claude/principles.yaml` already exists:

```bash
cat .claude/principles.yaml 2>/dev/null || echo "__EMPTY__"
```

If the file is missing or empty, start with an empty principles list.

### Step 2A: Show current state

Display the existing principles in a readable table:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Project Principles — .claude/principles.yaml
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ID     Category       Severity    Rule
  ────────────────────────────────────────
  P001   architecture   blocking    All DB queries must go through the repository layer
  P002   testing        blocking    Every public API endpoint must have an integration test
  P003   style          suggestion  Prefer dataclasses over plain dicts for structured data

  (3 principles loaded)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

If no principles exist yet, show:
```
  (no principles defined — let's add some)
```

### Step 3A: Prompt for action

Ask the engineer what they want to do:

```
What would you like to do?
  [A] Add a new principle
  [E] Edit an existing principle
  [R] Remove a principle
  [D] Done / save and exit
```

Repeat this loop until the engineer chooses **Done**.

---

#### Action: Add a principle

Ask the following questions one at a time:

1. **Category** — What area does this rule cover?
   - Suggested: `architecture`, `testing`, `security`, `performance`, `style`, `naming`, `error-handling`
   - Accept any free-form string

2. **Rule** — State the golden rule in one sentence (imperative mood preferred).
   - Example: "All secrets must be loaded from environment variables, never hardcoded."

3. **Severity** — How serious is a violation?
   - `blocking` — Must be fixed before merge (surfaces in 🔴 BLOCKING section of review-pr)
   - `suggestion` — Nice to have (surfaces in 🟡 SUGGESTIONS section)

4. **Applies to** — Which skills should enforce this?
   - `review-pr`, `check-code`, or `both` (default: `both`)

Auto-assign the next available ID (P001, P002, …).  Never reuse a deleted ID.

---

#### Action: Edit a principle

Ask: "Which principle ID do you want to edit?" Then re-ask only the fields the engineer
wants to change.

---

#### Action: Remove a principle

Ask: "Which principle ID do you want to remove?" Confirm before deleting.

---

## Mode B — Config-file Import

When `--from-file <path>` is provided, skip the interactive prompt entirely and import
principles from the specified YAML file.

### Step 1B: Validate the source file

```bash
python scripts/import_principles.py --from-file <path> [--dry-run] [--strict-ids]
```

The script validates each entry in the source file against the principle schema (see
**Config-file format** below).  Validation rules:

| Field | Required | Valid values |
|---|---|---|
| `category` | ✅ | Any non-empty string |
| `severity` | ✅ | `blocking` or `suggestion` |
| `rule` | ✅ | Any non-empty string (imperative mood preferred) |
| `applies_to` | ❌ | List subset of `["review-pr", "check-code"]` (default: both) |
| `id` | ❌ | Pattern `[A-Z][A-Z0-9]*\d{2,}` (e.g. `P001`, `MB014`). Omit to auto-assign. |

If any entry fails validation, print all errors and exit without writing.

### Step 2B: Merge with existing principles

- Entries without an `id` get the next available P-series ID auto-assigned.
- Entries whose `id` already exists in `.claude/principles.yaml`:
  - **Default**: skip silently (print a ⚠️ warning).
  - **`--strict-ids`**: exit 1 without writing anything.
- IDs are stable — removed principles are never renumbered.

### Step 3B: Report and write

Print a summary of what was added / skipped / errored, then write the merged result to
`.claude/principles.yaml`.  With `--dry-run`, print the summary but skip the write.

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Principle Import Summary
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ✅ Added (2):
     P004  [security]  🔴 blocking  — All secrets must come from environment variables
     P005  [style]     🟡 suggestion — Prefer dataclasses over plain dicts

  ⚠️  Skipped (1):
     P001  — Principle 'P001' already exists — skipped.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Step 4 — Save to `.claude/principles.yaml`

After all edits (interactive or file-import), write the final state to
`.claude/principles.yaml` using this schema:

```yaml
# .claude/principles.yaml
# Project-specific golden rules enforced by check-code and review-pr.
# Edit this file directly or run /define-principles to use the interactive prompt.
version: "1.0"
principles:
  - id: "P001"
    category: "architecture"
    severity: "blocking"
    applies_to: ["review-pr", "check-code"]
    rule: "All database queries must go through the repository layer"

  - id: "P002"
    category: "testing"
    severity: "blocking"
    applies_to: ["review-pr"]
    rule: "Every public API endpoint must have an integration test"

  - id: "P003"
    category: "style"
    severity: "suggestion"
    applies_to: ["review-pr", "check-code"]
    rule: "Prefer dataclasses over plain dicts for structured data"
```

### Step 4.5: Write docs/PRINCIPLES.md with version identifier and generation timestamp

After saving `.claude/principles.yaml`, generate (or update) `docs/PRINCIPLES.md` so
that every harness artifact carries a machine-readable provenance block.

```bash
RUN_DATE=$(date '+%Y-%m-%d')
RUN_TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
HEAD_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "no-git")
SKILL_VERSION=$(python3 -c "from importlib.metadata import version; print(version('harness-skills'))" 2>/dev/null || echo "unknown")
```

Write `docs/PRINCIPLES.md` using this exact structure:

```markdown
<!-- harness:auto-generated — do not edit this block manually -->
last_updated: <RUN_DATE>
generated_at: <RUN_TIMESTAMP>
skill_version: <SKILL_VERSION>
head: <HEAD_HASH>
artifact: principles
<!-- /harness:auto-generated -->

# Project Principles

> Source of truth: `.claude/principles.yaml` — edit principles with `/define-principles`.

| ID | Category | Severity | Applies to | Rule |
|---|---|---|---|---|
| P001 | architecture | 🔴 blocking | review-pr, check-code | All DB queries must go through the repository layer |
| P002 | testing | 🔴 blocking | review-pr | Every public API endpoint must have an integration test |
| P003 | style | 🟡 suggestion | review-pr, check-code | Prefer dataclasses over plain dicts for structured data |

*<N> principles active.*
```

**Rules:**
- Replace the example rows with the actual principles from `.claude/principles.yaml`.
- Severity `blocking` → 🔴 `blocking`; `suggestion` → 🟡 `suggestion`.
- If `docs/PRINCIPLES.md` already exists and has a `<!-- harness:auto-generated … -->`
  block, replace that block in-place and regenerate the table.  Content outside
  the block (e.g., additional narrative sections added by the team) is preserved.
- Stage the file with `git add docs/PRINCIPLES.md` but do **not** auto-commit.

---

## Step 5 — Confirm and show next steps

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅ Principles saved → .claude/principles.yaml
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  3 principles active.

  These will be enforced automatically by:
    • /check-code  — scans staged changes against each principle
    • /review-pr   — includes principles in the review checklist

  To edit again:           /define-principles
  To import from a file:   /define-principles --from-file my-principles.yaml
  To skip enforcement:     /check-code --no-principles
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Config-file format

Engineers can skip the interactive prompt entirely by editing `.claude/principles.yaml`
directly, or by preparing an **import file** and running:

```bash
/define-principles --from-file my-principles.yaml
# or equivalently (for CI / scripting):
python scripts/import_principles.py --from-file my-principles.yaml
```

The import file uses the same YAML schema as `.claude/principles.yaml`:

```yaml
version: "1.0"
principles:
  # 'id' is optional — omit to have it auto-assigned (P001, P002, …)
  - category: "security"
    severity: "blocking"
    applies_to: ["review-pr", "check-code"]
    rule: "All secrets and credentials must be loaded from environment variables"

  # Supply an explicit id if you need a stable cross-repo reference
  - id: "P042"
    category: "testing"
    severity: "blocking"
    applies_to: ["review-pr"]
    rule: "Every public API endpoint must have at least one integration test"

  - category: "style"
    severity: "suggestion"
    rule: "Prefer dataclasses or Pydantic models over plain dicts for structured data"
```

A starter template is available at `.claude/principles.yaml.example`.

---

## Notes

- Principles are **additive**: they extend (not replace) the default checks in `check-code` and `review-pr`.
- IDs are **stable** — removing P002 does not renumber P003 to P002.
- A principle with `applies_to: ["check-code"]` surfaces only in automated runs, not in PR review narratives.
- This file should be committed to version control so the whole team shares the same rules.
- The non-interactive import script (`scripts/import_principles.py`) is CI-safe and exits 0 on success, 1 on validation / ID-collision errors, and 2 on internal errors.
