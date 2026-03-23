# Golden Principles Cleanup

Scan the codebase against all principles in `.claude/principles.yaml`, then generate a set of background **cleanup task definitions** — one per violation cluster — that other agents can pick up and execute as refactoring PRs. Results are written to `docs/exec-plans/cleanup-tasks.yaml`.

---

## Instructions

### Step 0: Load principles

Read `.claude/principles.yaml`:

```bash
cat .claude/principles.yaml 2>/dev/null || echo "__ABSENT__"
```

If the output is `__ABSENT__` or the file is missing, **abort immediately** with:

```
ERROR: .claude/principles.yaml not found.
Run /define-principles first to define your project's golden rules.
```

Parse the YAML and extract the `principles` list. Note the `version`, each
principle's `id`, `category`, `severity`, `applies_to`, and `rule`.

---

### Step 1: Run the principles gate

Execute the harness principles gate and capture the JSON output:

```bash
uv run python -m harness_skills.cli.main evaluate \
  --format json \
  --gate principles \
  2>&1
```

Parse the JSON output. Extract the `failures` array — each entry is a
`GateFailure` with fields:
- `rule_id` — matches a principle `id` (e.g. `P001`)
- `file_path` — source file where the violation was found
- `line_number` — line number (may be null)
- `message` — human-readable description
- `severity` — `error` | `warning` | `info`
- `suggestion` — actionable fix hint

**If the command fails** (non-zero exit, missing binary, or parse error), fall
back to the manual scan in Step 1-fallback.

---

### Step 1-fallback: Manual text scan

If the harness gate is unavailable, scan source files manually:

```bash
find . \
  -type f \
  \( -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" \) \
  -not -path "*/node_modules/*" \
  -not -path "*/.venv/*" \
  -not -path "*/__pycache__/*" \
  2>/dev/null
```

For each principle, search for patterns that could indicate a violation. Use
the principle's `rule` text as the heuristic:
- `"repository layer"` → grep for direct `db.session` / `db.query` / `Model.objects` in non-repository files
- `"integration test"` → check that each `@router.get/post/put/delete` route has a corresponding test file
- `"dataclasses"` → grep for functions returning plain `dict` literals with more than three keys
- For unknown rules, flag any file that imports from a layer the rule restricts

Produce GateFailure-style dicts with the same fields as above, using
`rule_id = principle["id"]` and `severity` mapped from principle `severity`
(`blocking` → `error`, `suggestion` → `warning`).

---

### Step 2: Group violations by principle

Cluster all GateFailure items by `rule_id` / `principle_id`:

```
P001 → [
  {file_path: "src/api/views.py", line_number: 88, message: "...", ...},
  {file_path: "src/api/orders.py", line_number: 42, message: "...", ...},
]
P003 → [
  {file_path: "src/utils/helpers.py", line_number: 12, message: "...", ...},
]
```

If `--only-blocking` is set, discard any cluster whose matching principle has
`severity: suggestion`.

If a principle has **no violations**, skip it — do not generate a task for a
passing principle.

---

### Step 3: Generate cleanup task definitions

For each principle cluster with at least one violation, generate a
`CleanupTask` object:

**`id`**: `cleanup-<principle_id>-<slugified-first-file>`
- Slugify: lowercase, replace `/`, `.`, and non-alphanumeric chars with `-`,
  strip leading/trailing dashes.
- Example: `cleanup-P001-src-api-views-py`

**`principle_id`**: the principle's `id` (e.g. `P001`)

**`principle_category`**: the principle's `category` (e.g. `architecture`)

**`severity`**: the principle's `severity` value (`blocking` or `suggestion`)

**`title`**: short imperative phrase describing the fix
- Pattern: `"Enforce <category> rule: <first ~8 words of rule>"`
- Example: `"Enforce repository layer for all DB queries (P001)"`

**`scope`**: sorted list of all affected file paths from the violation cluster

**`description`**: multi-line explanation structured as:

```
Principle <id> (<category>/<severity>) is violated in <N> file(s).

Rule: <full rule text>

Affected files:
  - <file_path>:<line_number>  — <message>
  - ...

Refactoring steps:
  1. <concrete action derived from the rule and suggestion fields>
  2. Run `/harness:lint --gate principles` to verify zero remaining violations.
  3. Update or add unit/integration tests covering the refactored code.
```

**`pr_title`**: `"refactor: enforce <principle_id> <category> across <scope-summary>"`
- `scope-summary`: if 1 file → the file name; if 2–3 → comma-separated names; if 4+ → `"<N> files"`
- Example: `"refactor: enforce P001 architecture across src/api/views.py, src/api/orders.py"`

**`pr_body`**: full PR description template:

```
## What & Why

Enforces principle <principle_id> (<category>/<severity>):
"<rule text>"

This PR was generated automatically by `/golden-principles-cleanup` after
detecting <N> violation(s) across the following files:
<bulleted list of scope files>

## Changes

- <concrete change description per file, based on the rule and suggestions>
- Updated affected call-sites to use the new abstraction

## Testing

- [ ] All refactored code has unit tests
- [ ] No violations remain: `uv run python -m harness_skills.cli.main evaluate --gate principles --format json`
- [ ] `/harness:lint` passes with 0 blocking violations
- [ ] Existing test suite passes: `pytest tests/ -v`

## Checklist

- [ ] PR title follows conventional commits (`refactor:` prefix)
- [ ] No unrelated changes included
- [ ] PRINCIPLES.md is up to date (run `/define-principles` if needed)
```

**`generated_at`**: current UTC ISO-8601 timestamp (e.g. `"2026-03-22T10:00:00Z"`)

**`status`**: `"pending"`

---

### Step 4: Write `docs/exec-plans/cleanup-tasks.yaml`

Unless `--dry-run` is set, write the output file. Create `docs/exec-plans/`
if it does not exist.

```bash
mkdir -p docs/exec-plans
```

Obtain the current HEAD short hash:

```bash
git rev-parse --short HEAD 2>/dev/null || echo "no-git"
```

Write `docs/exec-plans/cleanup-tasks.yaml` (or the `--output` path) with this
top-level structure:

```yaml
generated_at: "2026-03-22T10:00:00Z"
generated_from_head: "abc1234"
task_count: 3
tasks:
  - id: "cleanup-P001-src-api-views-py"
    principle_id: "P001"
    principle_category: "architecture"
    severity: "blocking"
    title: "Enforce repository layer for all DB queries (P001)"
    scope:
      - "src/api/views.py"
      - "src/api/orders.py"
    description: |
      Principle P001 (architecture/blocking) is violated in 2 file(s).
      ...
    pr_title: "refactor: enforce P001 architecture across src/api/views.py, src/api/orders.py"
    pr_body: |
      ## What & Why
      ...
    generated_at: "2026-03-22T10:00:00Z"
    status: "pending"
```

If `--dry-run` is set, print the YAML to stdout instead of writing the file,
prefixed with a header line:

```
[dry-run] Would write to docs/exec-plans/cleanup-tasks.yaml:
```

---

### Step 5: Optionally publish to shared-state

Unless `--no-publish` is set, check whether the shared-state file exists:

```bash
test -f docs/exec-plans/shared-state.yaml && echo "EXISTS" || echo "ABSENT"
```

If it exists, publish a summary:

```bash
python skills/shared_state.py publish \
    --agent golden-principles-cleanup \
    --type other \
    --data '{"cleanup_tasks_generated": N, "output": "docs/exec-plans/cleanup-tasks.yaml", "principles_scanned": P, "violations_found": V}'
```

Replace `N` with the number of tasks generated, `P` with the number of
principles scanned, and `V` with the total number of violations found.

If the shared-state file is absent, skip this step silently.

---

### Step 6: Display summary

Print a formatted summary table:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Golden Principles Cleanup — <N> task(s) generated
  Principles scanned: <P>  ·  Violations found: <V>  ·  Output: docs/exec-plans/cleanup-tasks.yaml
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Task ID                                  Principle  Severity   Files  PR Title
  ────────────────────────────────────────────────────────────────────────────────
  cleanup-P001-src-api-views-py            P001       blocking   2      refactor: enforce P001 architecture across ...
  cleanup-P003-src-utils-helpers-py        P003       suggestion 1      refactor: enforce P003 style across ...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Next steps:
    • Each task in cleanup-tasks.yaml can be dispatched to a worker agent.
    • To apply one task: open the pr_body as a PR description and follow the Changes section.
    • Re-run after fixing: /golden-principles-cleanup (tasks for passing principles will disappear)
    • To validate: /harness:lint --gate principles
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

If **zero violations** were found across all principles:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅ No violations found — all principles pass.
  0 cleanup tasks generated. docs/exec-plans/cleanup-tasks.yaml was not modified.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Options

| Flag | Effect |
|------|--------|
| `--principles-file PATH` | Override path to principles YAML (default: `.claude/principles.yaml`) |
| `--output PATH` | Override output path (default: `docs/exec-plans/cleanup-tasks.yaml`) |
| `--only-blocking` | Only generate tasks for `severity: blocking` principles; skip `suggestion` |
| `--dry-run` | Print tasks to stdout without writing the output file |
| `--no-publish` | Skip the shared-state publish step even if shared-state.yaml exists |

---

## Programmatic invocation

```bash
# Generate all tasks (default)
python skills/golden_principles_cleanup.py generate

# Only blocking violations, custom output path
python skills/golden_principles_cleanup.py generate \
    --only-blocking \
    --output /tmp/cleanup-blocking.yaml

# Dry-run preview
python skills/golden_principles_cleanup.py generate --dry-run

# List generated tasks from an existing file
python skills/golden_principles_cleanup.py list \
    --output docs/exec-plans/cleanup-tasks.yaml
```

---

## When to use this skill

| Scenario | Action |
|----------|--------|
| Principles were just added or updated | Run immediately after `/define-principles` |
| Planning a cleanup sprint | Run to generate the backlog of refactoring PRs |
| Post `/harness:evaluate` clean-up | Run to convert gate failures into structured tasks |
| Dispatching work to worker agents | Each task in `cleanup-tasks.yaml` is self-contained |

---

## Notes

- This skill is **read-only** for source files — it never modifies application code.
- Each generated task carries enough context (`description`, `pr_body`) for an
  agent to open and complete a refactoring PR without any further analysis.
- Re-running after fixes will regenerate the file with only remaining violations.
- A principle with `applies_to: ["review-pr"]` is still scanned — this skill
  enforces all principles across the entire codebase, not just changed files.
- To add or update principles, run `/define-principles` first.
