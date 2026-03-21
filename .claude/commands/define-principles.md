# Define Principles

Add, edit, or remove project-specific golden rules that are enforced by `check-code` and `review-pr`. Principles are stored in `.claude/principles.yaml` and automatically loaded by other skills.

## Instructions

### Step 1: Load existing principles

Check whether `.claude/principles.yaml` already exists:

```bash
cat .claude/principles.yaml 2>/dev/null || echo "__EMPTY__"
```

If the file is missing or empty, start with an empty principles list.

### Step 2: Show current state

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

### Step 3: Prompt for action

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

### Action: Add a principle

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

Auto-assign the next available ID (P001, P002, …).

---

### Action: Edit a principle

Ask: "Which principle ID do you want to edit?" Then re-ask only the fields the engineer wants to change.

---

### Action: Remove a principle

Ask: "Which principle ID do you want to remove?" Confirm before deleting.

---

### Step 4: Save to `.claude/principles.yaml`

After all edits, write the final state to `.claude/principles.yaml` using this schema:

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

### Step 4.5: Write PRINCIPLES.md with version identifier and generation timestamp

After saving `.claude/principles.yaml`, generate (or update) `PRINCIPLES.md` so
that every harness artifact carries a machine-readable provenance block.

```bash
RUN_DATE=$(date '+%Y-%m-%d')
HEAD_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "no-git")
```

Write `PRINCIPLES.md` using this exact structure:

```markdown
<!-- harness:auto-generated — do not edit this block manually -->
last_updated: <RUN_DATE>
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
- If `PRINCIPLES.md` already exists and has a `<!-- harness:auto-generated … -->`
  block, replace that block in-place and regenerate the table.  Content outside
  the block (e.g., additional narrative sections added by the team) is preserved.
- Stage the file with `git add PRINCIPLES.md` but do **not** auto-commit.

---

### Step 5: Confirm and show next steps

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅ Principles saved → .claude/principles.yaml
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  3 principles active.

  These will be enforced automatically by:
    • /check-code  — scans staged changes against each principle
    • /review-pr   — includes principles in the review checklist

  To edit again:  /define-principles
  To skip enforcement on one run:  /check-code --no-principles
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Config-file shortcut

Engineers can also skip the interactive prompt entirely by editing `.claude/principles.yaml` directly. The file format is shown above. Both workflows produce the same result — the interactive prompt is just a guided editor for the same YAML.

## Notes

- Principles are **additive**: they extend (not replace) the default checks in `check-code` and `review-pr`.
- IDs are stable — removing P002 does not renumber P003 to P002.
- A principle with `applies_to: ["check-code"]` will only surface in automated runs, not in PR review narratives.
- This file should be committed to version control so the whole team shares the same rules.
