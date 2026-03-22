<<<<<<< HEAD
# Execution Plans

Create and manage execution plans, then produce PRs that are fully traceable back
to their source plan. Every PR must reference the plan that authorised it; every
plan file must record the PR URL immediately after opening.

Full convention specification: `docs/plan-to-pr-convention.md`

---

## When to use

- Before starting any multi-task feature that will result in one or more PRs
- When creating a PR for a planned task (to embed plan metadata and write the URL back)
- To verify all tasks in a plan have a linked PR before closing the plan
- To query which PR delivered a specific task or which plan authorised a given PR

---

## Instructions

### Step 0: Check for an existing plan

If you already have a plan ID (e.g. `PLAN-003`), skip to Step 2.

List existing plans to avoid duplicates:

```bash
ls docs/exec-plans/PLAN-*.yaml 2>/dev/null || echo "(no plans yet)"
```

### Step 1: Initialise a new plan

Create a new plan file from the template. The plan ID is auto-assigned unless you
supply `--plan-id` explicitly.

```bash
python skills/exec_plan.py init \
  --title "Short imperative description of the feature" \
  --plan-id PLAN-NNN   # omit to auto-assign the next ID
```

Expected output:

```
[exec-plan] Initialised PLAN-003 → docs/exec-plans/PLAN-003.yaml
```

Open the generated file and **fill in the task list** before claiming any tasks.
Replace the stub `TASK-001` entry with real tasks, set `depends_on` for any
ordering constraints, and list `coordination.hotspot_files` if multiple tasks
touch the same files.

```bash
# Confirm the plan looks correct
python skills/exec_plan.py status --plan PLAN-NNN
python skills/exec_plan.py graph  --plan PLAN-NNN
```

### Step 2: Create the feature branch

Branch names MUST follow the convention so CI can identify the source plan:

```bash
PLAN_ID="PLAN-NNN"
SLUG="short-kebab-description"   # matches the plan title, lowercase, hyphens
git checkout -b "feat/${PLAN_ID}-${SLUG}"
```

Example: `feat/PLAN-003-rate-limit-api`

### Step 3: Claim a task before starting work

Claiming locks the task so no other agent starts it simultaneously.

```bash
python skills/exec_plan.py ready --plan PLAN-NNN   # list tasks ready to start
python skills/exec_plan.py claim \
  --plan PLAN-NNN \
  --task TASK-NNN \
  --agent "$AGENT_ID"            # your agent identifier, e.g. coding-03abe8fb
```

Work on the task. When done, mark it complete:

```bash
python skills/exec_plan.py done \
  --plan PLAN-NNN \
  --task TASK-NNN \
  --agent "$AGENT_ID" \
  --notes "Optional: brief notes on what was done"
```

### Step 4: Commit with the Plan trailer

Every commit that belongs to a plan MUST include a `Plan:` trailer so
`git log --grep="Plan: PLAN-NNN"` is independently searchable.

```bash
git commit -m "$(cat <<'EOF'
feat: <imperative description matching the task title>

<Optional paragraph explaining why, not what.>

Plan: PLAN-NNN
Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

### Step 5: Open the PR with plan metadata in the title and body

PR title MUST include the plan ID in brackets — this makes it machine-parseable:

```bash
PLAN_ID="PLAN-NNN"
PLAN_FILE="docs/exec-plans/PLAN-NNN-slug.yaml"
TASKS_CLOSED="TASK-001, TASK-002"   # space-separated IDs addressed by this PR
PLAN_STATUS="running"               # pending | running | done

gh pr create \
  --title "[${PLAN_ID}] <imperative short description>" \
  --body "$(cat <<EOF
## Summary
<!-- 1-3 bullets describing WHAT changed and WHY -->
-

## Execution Plan

| Field        | Value |
|--------------|-------|
| Plan ID      | \`${PLAN_ID}\` |
| Plan file    | \`${PLAN_FILE}\` |
| Tasks closed | ${TASKS_CLOSED} |
| Plan status  | ${PLAN_STATUS} |

## Test plan
- [ ] Linter passes (\`uv run ruff check .\`)
- [ ] Type checker passes (\`uv run mypy .\`)
- [ ] Unit tests pass (\`uv run pytest tests/ -q\`)
- [ ] Manually verified: <describe>

## Checklist
- [ ] Plan file updated with this PR's URL (\`linked_prs\` field)
- [ ] Task statuses in plan file set to \`done\` for all tasks addressed
- [ ] No secrets or credentials in changed files
- [ ] PRINCIPLES.md rules followed
EOF
)"
```

> If this PR was NOT generated from an execution plan, replace the Execution Plan
> section with: `No execution plan — ad-hoc change.`

### Step 6: Write the PR URL back to the plan file

Immediately after `gh pr create` returns the PR URL, record it in the plan YAML.
**This is mandatory** — it closes the traceability loop.

```bash
PR_URL="<paste URL from gh pr create output>"
PR_NUMBER="<number from URL>"
TASKS="TASK-001 TASK-002"   # space-separated

python skills/exec_plan.py link-pr \
  --plan PLAN-NNN \
  --pr-url  "$PR_URL" \
  --pr-number "$PR_NUMBER" \
  --agent "$AGENT_ID" \
  --tasks $TASKS
```

Then commit the updated plan file on the feature branch:

```bash
git add docs/exec-plans/PLAN-NNN*.yaml
git commit -m "$(cat <<'EOF'
chore: link PR #<NUMBER> to PLAN-NNN

Plan: PLAN-NNN
Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
git push
```

> The write-back commit must be on the **feature branch**, not on `main`, so
> reviewers can verify traceability is complete in the PR diff.

### Step 7: Verify traceability before closing the plan

Before marking a task `done` or reporting the feature complete, confirm every
task has at least one linked PR:

```bash
python skills/exec_plan.py verify-prs --plan PLAN-NNN
```

Expected output when complete:

```
[exec-plan] PLAN-NNN traceability check
  ✅ TASK-001 — covered by PR #42
  ✅ TASK-002 — covered by PR #42
  ✅ TASK-003 — covered by PR #45
All 3 tasks have a linked PR.
```

If any tasks are missing:

```
  ❌ TASK-004 — no linked PR found
1 task(s) missing a PR link. Open PRs or run `link-pr` for completed tasks.
```

### Step 8: Query traceability

**Find all PRs for a plan:**

```bash
gh pr list --search "[PLAN-NNN]" --json number,title,url,state
```

**Find the plan for a PR:**

```bash
# From PR body
gh pr view <NUMBER> --json body | jq -r '.body' | grep "Plan ID"

# From git log
git log --grep="Plan: PLAN-" --format="%H %s" <branch>
```

**Find all plan files with open PRs:**

```bash
grep -r "pr_url" docs/exec-plans/
```

---

## Pre-merge verification checklist

Before marking the coding task `done` in the state service, confirm:

- [ ] Branch follows `feat/PLAN-NNN-<slug>` naming
- [ ] PR title includes `[PLAN-NNN]`
- [ ] PR body traceability table is filled in (not placeholder text)
- [ ] Every commit body includes `Plan: PLAN-NNN` trailer
- [ ] Plan YAML `linked_prs` updated with PR URL and tasks addressed
- [ ] All addressed tasks have `lock_status: done` in plan YAML
- [ ] `python skills/exec_plan.py verify-prs --plan PLAN-NNN` reports zero gaps

---

## Convention enforcement by CI

The `harness-evaluate` CI workflow (`.github/workflows/harness-evaluate.yml`)
automatically checks:

1. PR title matches `^\[PLAN-\d{3}\]` **or** body contains `No execution plan`.
2. The plan file path in the traceability table exists in the repository.
3. The plan file's `linked_prs` list contains an entry for this PR number.

PRs that fail these checks are labelled `missing-plan-link` and require a human
override to merge.

---

## Quick-reference command cheat-sheet

| Goal | Command |
|------|---------|
| Create new plan | `python skills/exec_plan.py init --title "..."` |
| Show plan status | `python skills/exec_plan.py status --plan PLAN-NNN` |
| Show dependency graph | `python skills/exec_plan.py graph --plan PLAN-NNN` |
| List ready tasks | `python skills/exec_plan.py ready --plan PLAN-NNN` |
| Claim a task | `python skills/exec_plan.py claim --plan PLAN-NNN --task TASK-NNN --agent $ID` |
| Mark task done | `python skills/exec_plan.py done --plan PLAN-NNN --task TASK-NNN --agent $ID` |
| Release a stuck lock | `python skills/exec_plan.py release --plan PLAN-NNN --task TASK-NNN --agent $ID` |
| Link PR to plan | `python skills/exec_plan.py link-pr --plan PLAN-NNN --pr-url URL --pr-number N --agent $ID --tasks TASK-NNN` |
| Verify all tasks linked | `python skills/exec_plan.py verify-prs --plan PLAN-NNN` |

---

*Convention version 1.0 — see `docs/plan-to-pr-convention.md` for the full spec.*
||||||| 0e893bd
=======
# Execution Plans

Generate a fully-populated execution plan YAML in `docs/exec-plans/` with canonical
planning sections: **objective**, **approach**, **steps**, **context assembly**,
**progress log**, **known debt**, and **completion criteria**.

Use this skill at the start of any non-trivial feature, bug-fix, or refactor to
capture the agent's intent before touching code.  The resulting plan file is the
single source of truth for what the agent intends to do, how it will verify
completion, and which open debt items are relevant.

---

## Usage

```bash
# Minimal — auto-assign next PLAN-NNN ID
/execution-plans --title "Add OAuth2 login flow"

# Provide an explicit plan ID
/execution-plans --title "Rate-limit API endpoints" --plan-id PLAN-007

# Supply all narrative fields inline
/execution-plans \
  --title "Refactor auth middleware" \
  --objective "Extract token verification into AuthService so all callers are covered" \
  --approach "Move verify_token() from middleware into AuthService; update all call sites; add unit tests" \
  --step "Read existing middleware and service layer" \
  --step "Move verify_token into AuthService" \
  --step "Update middleware to delegate to AuthService" \
  --step "Add / update unit tests" \
  --step "Run /harness:evaluate" \
  --criterion "All tests pass with coverage ≥ 80 %" \
  --criterion "No new lint errors" \
  --criterion "PR reviewed and merged"

# Preview — print template to stdout without writing a file
/execution-plans --title "My Plan" --dry-run
```

---

## Instructions

### Step 1 — Resolve the plan ID

Determine the plan ID to use:

```bash
PLANS_DIR="docs/exec-plans"
mkdir -p "$PLANS_DIR"

if [ -n "$PLAN_ID" ]; then
  # Explicit ID supplied — validate it looks like PLAN-NNN
  echo "$PLAN_ID" | grep -Eq '^[A-Za-z]+-[0-9]+$' \
    || { echo "ERROR: --plan-id must match PLAN-NNN (e.g. PLAN-007)"; exit 1; }
else
  # Auto-assign next incremental ID
  LAST=$(ls "$PLANS_DIR"/PLAN-*.yaml 2>/dev/null \
         | sed 's/.*PLAN-//' | sed 's/\.yaml//' | sort -n | tail -1)
  NEXT=$(( ${LAST:-0} + 1 ))
  PLAN_ID=$(printf "PLAN-%03d" "$NEXT")
fi

PLAN_FILE="$PLANS_DIR/$PLAN_ID.yaml"

if [ -f "$PLAN_FILE" ] && [ "$DRY_RUN" != "true" ]; then
  echo "ERROR: $PLAN_FILE already exists. Use a different --plan-id."
  exit 1
fi
```

---

### Step 2 — Gather context for the plan

Before writing the file, assemble the context that will populate
`context_assembly.key_files` and `context_assembly.key_patterns`.

Run `/harness:context` if a domain is known (recommended):

```bash
# Derive domain keywords from the plan title
DOMAIN=$(echo "$TITLE" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')
/harness:context "$DOMAIN" --max-files 10 --format json > /tmp/ctx_manifest.json 2>/dev/null || true
```

Parse the returned `files[].path` list into `key_files` and `patterns[].pattern`
into `key_patterns`.  If `/harness:context` is unavailable or returns no results,
leave both lists empty — the agent will populate them manually.

---

### Step 3 — Assemble relevant known debt

Scan `docs/exec-plans/debt.md` for open entries whose `Area / File` or
`Description` column mentions keywords from the plan title:

```bash
grep -i "$KEYWORD" docs/exec-plans/debt.md 2>/dev/null \
  | grep -v "^| ID" | grep -v "^|---" \
  | awk -F'|' '{print $2, $4}' | head -10
```

For each matching debt entry, record its `DEBT-NNN` ID and a one-sentence
`relevance` note.

---

### Step 4 — Write the plan file

Call `skills/exec_plan.py init` with all resolved values:

```bash
python skills/exec_plan.py init \
  --title    "$TITLE" \
  --plan-id  "$PLAN_ID" \
  --objective  "$OBJECTIVE" \
  --approach   "$APPROACH" \
  $(for STEP in "${STEPS[@]}"; do echo "--step \"$STEP\""; done) \
  $(for C in "${CRITERIA[@]}"; do echo "--criterion \"$C\""; done)
```

After the file is written, patch `context_assembly` and `known_debt` directly
(the CLI init command initialises them to empty stubs):

```python
import yaml
from pathlib import Path

path = Path("docs/exec-plans") / f"{plan_id}.yaml"
with path.open(encoding="utf-8") as fh:
    data = yaml.safe_load(fh)

data["context_assembly"]["key_files"]    = key_files    # list[str] from Step 2
data["context_assembly"]["key_patterns"] = key_patterns # list[dict] from Step 2
data["known_debt"] = known_debt                         # list[dict] from Step 3

with path.open("w", encoding="utf-8") as fh:
    yaml.dump(data, fh, allow_unicode=True, sort_keys=False)
```

In `--dry-run` mode, print the assembled YAML to stdout instead of writing.

---

### Step 5 — Initialise the progress log

Create (or verify) the progress log file and append an initialisation entry:

```bash
LOG_FILE=".claw-forge/progress.log"
mkdir -p "$(dirname "$LOG_FILE")"

if [ ! -f "$LOG_FILE" ]; then
  cat > "$LOG_FILE" <<EOF
# Progress Log
# Started: $(date -u '+%Y-%m-%dT%H:%M:%SZ')
# Plan: $TITLE ($PLAN_ID)
# ──────────────────────────────────────────────
EOF
fi

TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
echo "[$TIMESTAMP] [✅ DONE] Step 0 — Execution plan initialised: $PLAN_FILE" >> "$LOG_FILE"
```

Skip this step in `--dry-run` mode.

---

### Step 6 — Emit a creation summary

Print a structured summary to stdout:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Execution Plan Created
  ID:     <PLAN_ID>
  Title:  <title>
  File:   <PLANS_DIR>/<PLAN_ID>.yaml
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Sections populated
  ──────────────────────────────────────────────────────────
  objective          ✅  <first ~80 chars of objective>
  approach           ✅  <first ~80 chars of approach>
  steps              ✅  <N> step(s)
  context_assembly   ✅  <N> file(s) · <M> pattern(s)
  progress_log       ✅  .claw-forge/progress.log
  known_debt         ✅  <N> open debt item(s) referenced
  completion_criteria ✅  <N> criterion/criteria

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Next steps
  • Edit <PLAN_ID>.yaml to refine narrative sections.
  • Add tasks with: python skills/exec_plan.py ...
  • Check for conflicts:  /coordinate
  • Start executing and log progress: /progress-log
  • Run quality gates before merge: /harness:evaluate
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

In `--dry-run` mode, prefix the header with `[DRY-RUN]` and replace "File:" with
"Would write:".

---

## Options

| Flag | Default | Effect |
|---|---|---|
| `--title TITLE` | *(required)* | Human-readable plan title |
| `--plan-id ID` | auto | Explicit plan ID (`PLAN-NNN`). Auto-incremented from existing plans if omitted. |
| `--objective TEXT` | stub | Concise statement of what the plan achieves |
| `--approach TEXT` | stub | Technical strategy, architecture decisions, trade-offs |
| `--step TEXT` | 3 stub steps | Ordered step (repeat for multiple steps) |
| `--criterion TEXT` | 3 stub criteria | Completion criterion (repeat for multiple) |
| `--dry-run` | off | Print the assembled YAML to stdout; do not write to disk or touch progress log |

---

## Template sections reference

| Section | Purpose | Owner |
|---|---|---|
| `objective` | What the plan achieves and why | Agent fills at creation; human may refine |
| `approach` | Technical strategy and constraints | Agent fills at creation |
| `steps` | Ordered high-level actions | Agent fills at creation; updated during execution |
| `context_assembly` | Files and patterns to read first | Auto-populated by `/harness:context`; agent refines |
| `progress_log` | Path to the append-only progress log | Fixed at `.claw-forge/progress.log`; maintained by `/progress-log` |
| `known_debt` | Relevant open DEBT-NNN items | Auto-detected from `docs/exec-plans/debt.md`; agent verifies |
| `completion_criteria` | Verifiable done conditions | Agent fills at creation; treated as contract |
| `tasks` | Fine-grained task coordination (multi-agent) | Populated separately via `exec_plan.py` commands |

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Start a new feature, bug-fix, or refactor | **`/execution-plans`** ← you are here |
| Find relevant files for an existing plan | `/harness:context` |
| Log progress as steps complete | `/progress-log` |
| Check for conflicts with other agents | `/coordinate` |
| Run all quality gates before merge | `/harness:evaluate` |
| Show current plan dashboard | `/harness:status` |

---

## Notes

- **Never auto-commits** — review the generated plan file before committing.
- **Template is a contract** — completion criteria are reviewed by `/harness:evaluate`
  and `/harness:status`; avoid weakening them after the plan is shared.
- **Idempotent dry-run** — `--dry-run` makes no filesystem changes; safe to run
  repeatedly as a preview.
- **Progress log is shared** — multiple plans in a session write to the same
  `.claw-forge/progress.log`; each entry is prefixed with the plan ID in the
  initialisation header.
- **Debt is advisory** — `known_debt` entries are informational; the plan does not
  require resolving them unless a completion criterion says so.
>>>>>>> feat/execution-plans-skill-generates-execution-plan-template
