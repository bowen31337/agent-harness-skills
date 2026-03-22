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
