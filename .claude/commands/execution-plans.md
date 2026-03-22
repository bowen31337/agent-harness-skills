<<<<<<< HEAD
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
||||||| 0e893bd
=======
# Execution Plans

Scaffold and manage the `docs/exec-plans/` directory — the canonical home for
multi-agent execution plan artifacts.  Generates a full directory structure with
plan templates, task dependency graphs, multi-agent coordination metadata, and
shared-state scaffolding.

Use this skill to bootstrap the execution-plans directory on a new project, create
a named plan from the template, inspect which tasks are immediately runnable, or
visualise the task dependency graph.

---

## Usage

```bash
# Scaffold the full docs/exec-plans/ directory with all templates (idempotent)
/execution-plans init

# Create a new plan file from the template
/execution-plans new --title "Add JWT authentication" --id PLAN-001

# Auto-assign the next available PLAN-NNN id
/execution-plans new --title "Migrate database schema"

# List all plans and their statuses
/execution-plans list

# Show which tasks are immediately runnable (all depends_on entries are done)
/execution-plans ready --plan PLAN-001

# Print the ASCII task dependency graph for a plan
/execution-plans graph --plan PLAN-001

# Show which agents currently hold locks across all plans
/execution-plans locks

# Preview what init would create without writing to disk
/execution-plans init --dry-run
```

---

## Instructions

### Step 1 — Ensure docs/exec-plans/ exists

```bash
mkdir -p docs/exec-plans
```

If `docs/exec-plans/` already exists, proceed — this skill is fully idempotent.

---

### Step 2 — Scaffold template files (`init` subcommand)

Write the following files **only if they do not already exist**.  Never overwrite
a file that has been manually edited.

---

#### `docs/exec-plans/README.md`

```markdown
# Execution Plans

This directory contains multi-agent execution plan artifacts managed by the
`/execution-plans` skill.

## Directory layout

| File / pattern            | Purpose |
|---------------------------|---------|
| `plan-template.yaml`      | Blank template — copy and rename to `<PLAN-ID>.yaml` |
| `PLAN-NNN.yaml`           | Active or historical execution plans |
| `shared-state.yaml`       | Real-time multi-agent coordination snapshot |
| `progress.md`             | Running log of cross-plan progress updates |
| `debt.md`                 | Tech-debt items surfaced during execution |
| `perf.md`                 | Performance observations and regressions |

## Key fields in every plan

| Field            | Values                                      | Meaning |
|------------------|---------------------------------------------|---------|
| `assigned_agent` | `""` or agent ID (e.g. `coding-03abe8fb`)   | Agent currently responsible for the task |
| `lock_status`    | `unlocked` \| `locked` \| `done`            | Whether the task is claimable |
| `depends_on`     | `[]` or list of `TASK-NNN` IDs             | Tasks that must be `done` before this one starts |

## Workflow

1. Copy `plan-template.yaml` → `PLAN-NNN.yaml` (or run `/execution-plans new`).
2. Fill in tasks, set `depends_on` lists to express the dependency graph.
3. Run `/execution-plans ready --plan PLAN-NNN` to list immediately runnable tasks.
4. Run `/execution-plans graph --plan PLAN-NNN` to visualise the full graph.
5. Agents claim tasks by setting `lock_status: locked` and `assigned_agent: <id>`.
6. On completion set `lock_status: done` and `status: done`.
7. Run `/coordinate` to detect cross-agent file conflicts before merging.

## Related skills

- `/execution-plans` — this skill (scaffold, create, graph, ready, locks)
- `/coordinate` — cross-agent conflict detection and reordering
- `/harness:status` — gate health and plan status dashboard
- `/harness:resume` — handoff context for incoming agents
- `/progress-log` — append structured progress entries
```

---

#### `docs/exec-plans/plan-template.yaml`

```yaml
# Execution Plan Template — copy and rename to <plan-id>.yaml
# Generated by: /execution-plans new --title "..." --id PLAN-NNN
# ---------------------------------------------------------------------------
# Field reference
# ---------------------------------------------------------------------------
#   assigned_agent  — agent ID currently responsible for the task, or ""
#   lock_status     — unlocked | locked | done
#                       unlocked : no agent holds the task
#                       locked   : an agent has claimed it (see assigned_agent)
#                       done     : task is complete and the lock released
#   depends_on      — list of TASK-NNN IDs that must be `done` before this
#                     task may start; [] means no dependencies (can run now)
# ---------------------------------------------------------------------------

plan:
  id: PLAN-000
  title: "<plan title>"
  created_at: "YYYY-MM-DDTHH:MM:SSZ"
  updated_at: "YYYY-MM-DDTHH:MM:SSZ"
  status: pending          # pending | running | done | blocked | cancelled

  # ---------------------------------------------------------------------------
  # Plan-to-PR traceability  (see docs/plan-to-pr-convention.md)
  # ---------------------------------------------------------------------------
  # Populate linked_prs AFTER each PR is opened.  Agents must update this
  # field immediately after `gh pr create` returns the PR URL.
  # ---------------------------------------------------------------------------
  linked_prs: []
  # Example (fill in after opening PRs):
  # linked_prs:
  #   - pr_url: "https://github.com/org/repo/pull/42"
  #     pr_number: 42
  #     opened_at: "YYYY-MM-DDTHH:MM:SSZ"
  #     opened_by: "<agent-id>"         # e.g. coding-03abe8fb
  #     tasks_addressed:                # TASK IDs closed by this PR
  #       - TASK-001
  #       - TASK-002

# ---------------------------------------------------------------------------
# Task dependency graph
# ---------------------------------------------------------------------------
# Visualised:
#
#   TASK-001 ──► TASK-003 ──► TASK-005
#   TASK-002 ──┘             ▲
#                TASK-004 ───┘
#
# Any task whose depends_on list is empty (or all entries are done) is
# immediately runnable.  Run `/execution-plans ready --plan PLAN-NNN` to list
# them, or `/execution-plans graph --plan PLAN-NNN` to render the full graph.
# ---------------------------------------------------------------------------

tasks:
  - id: TASK-001
    title: "<first task>"
    description: ""
    assigned_agent: ""       # e.g. coding-03abe8fb
    lock_status: unlocked    # unlocked | locked | done
    depends_on: []           # no upstream dependencies — can start immediately
    status: pending          # pending | running | done | blocked | skipped
    priority: medium         # critical | high | medium | low
    started_at: null
    completed_at: null
    notes: ""

  - id: TASK-002
    title: "<second task — runs in parallel with TASK-001>"
    description: ""
    assigned_agent: ""
    lock_status: unlocked
    depends_on: []
    status: pending
    priority: medium
    started_at: null
    completed_at: null
    notes: ""

  - id: TASK-003
    title: "<third task — waits for TASK-001 and TASK-002>"
    description: ""
    assigned_agent: ""
    lock_status: unlocked
    depends_on:
      - TASK-001
      - TASK-002
    status: pending
    priority: medium
    started_at: null
    completed_at: null
    notes: ""

  - id: TASK-004
    title: "<fourth task — independent branch>"
    description: ""
    assigned_agent: ""
    lock_status: unlocked
    depends_on: []
    status: pending
    priority: low
    started_at: null
    completed_at: null
    notes: ""

  - id: TASK-005
    title: "<fifth task — final gate, waits for TASK-003 and TASK-004>"
    description: ""
    assigned_agent: ""
    lock_status: unlocked
    depends_on:
      - TASK-003
      - TASK-004
    status: pending
    priority: high
    started_at: null
    completed_at: null
    notes: ""

# ---------------------------------------------------------------------------
# Multi-agent coordination metadata
# ---------------------------------------------------------------------------
coordination:
  strategy: parallel-with-serialised-hotspots
  hotspot_files: []          # list file paths that multiple tasks will touch
  merge_order: []            # suggested agent merge sequence for hotspots
  post_merge_checklist: []   # steps to run after all tasks complete
```

---

#### `docs/exec-plans/shared-state.yaml`

```yaml
# Shared-state snapshot — updated by /coordinate on each run.
# Do not edit manually; this file is regenerated from live agent/git data.
snapshot:
  timestamp: ""
  agent_count: 0
  conflict_count: 0
  high_conflicts: 0
  medium_conflicts: 0
  low_conflicts: 0
  state_service: http://localhost:8888
  state_service_available: false
  source: git-branch-analysis

agents: []

large_refactor_agents: []

conflict_clusters: []

intermediate_results: []

execution_plan:
  strategy: parallel-with-serialised-hotspots
  slots: []
  post_merge_checklist: []
```

---

#### `docs/exec-plans/progress.md`

```markdown
<!-- harness:auto-generated — do not edit this block manually -->
artifact: progress-log
<!-- /harness:auto-generated -->

# Execution Plans — Progress Log

Append entries below using `/progress-log` or manually.  Most recent entry first.

---

<!-- Add entries above this line -->
```

---

#### `docs/exec-plans/debt.md`

```markdown
<!-- harness:auto-generated — do not edit this block manually -->
artifact: debt-tracker
<!-- /harness:auto-generated -->

# Tech Debt

Items surfaced during plan execution.  Add new rows; do not delete existing ones.

| ID | Description | Severity | Linked task | Status |
|----|-------------|----------|-------------|--------|
| DEBT-001 | *(example)* Replace placeholder with real implementation | low | TASK-001 | open |
```

---

#### `docs/exec-plans/perf.md`

```markdown
<!-- harness:auto-generated — do not edit this block manually -->
artifact: perf-tracker
<!-- /harness:auto-generated -->

# Performance Observations

Record regressions and wins discovered during plan execution.

| Date | Metric | Before | After | Task | Notes |
|------|--------|--------|-------|------|-------|
| YYYY-MM-DD | *(example)* p95 latency | 120 ms | 95 ms | TASK-NNN | |
```

---

### Step 3 — Create a new plan file (`new` subcommand)

1. Determine the plan ID:
   - If `--id PLAN-NNN` was supplied, use it verbatim.
   - Otherwise scan `docs/exec-plans/` for existing `PLAN-*.yaml` files, find the
     highest NNN, and set the new ID to NNN + 1 (zero-padded to three digits).
     Start at `PLAN-001` if none exist.

2. Set `created_at` and `updated_at` to the current UTC timestamp
   (`date -u '+%Y-%m-%dT%H:%M:%SZ'`).

3. Copy `docs/exec-plans/plan-template.yaml` to
   `docs/exec-plans/<PLAN-ID>.yaml` and replace:
   - `PLAN-000` → `<PLAN-ID>`
   - `"<plan title>"` → the value of `--title`
   - `"YYYY-MM-DDTHH:MM:SSZ"` (both occurrences) → current UTC timestamp

4. If the destination file already exists, abort with:

   ```
   ✗ docs/exec-plans/<PLAN-ID>.yaml already exists.
     Use a different --id or edit the file directly.
   ```

5. Print a confirmation:

   ```
   ✔ Created docs/exec-plans/<PLAN-ID>.yaml
     Title: <title>
     Tasks: 5 (edit to match your plan)
     Next:  /execution-plans ready --plan <PLAN-ID>
            /execution-plans graph  --plan <PLAN-ID>
   ```

---

### Step 4 — List plans (`list` subcommand)

Scan `docs/exec-plans/` for all `PLAN-*.yaml` files.  For each file read the
`plan.id`, `plan.title`, `plan.status`, and task counts.  Display:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Execution Plans                          docs/exec-plans/
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  PLAN-ID   Status     Done  Running  Pending  Blocked  Title
  ────────────────────────────────────────────────────────────────────
  PLAN-001  🟡 running   2      1        2        0     Add JWT authentication
  PLAN-002  ⬜ pending   0      0        5        0     Migrate database schema

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Status icons:

| `plan.status`  | Icon |
|----------------|------|
| `pending`      | ⬜ pending |
| `running`      | 🟡 running |
| `done`         | ✅ done |
| `blocked`      | 🔴 blocked |
| `cancelled`    | ⚫ cancelled |

---

### Step 5 — Show ready tasks (`ready` subcommand)

A task is **immediately runnable** when:
- Its `lock_status` is `unlocked`, **and**
- Every task ID in its `depends_on` list has `lock_status: done` (or
  `depends_on` is empty).

Algorithm:

```python
done_ids = {t["id"] for t in tasks if t["lock_status"] == "done"}
ready = [
    t for t in tasks
    if t["lock_status"] == "unlocked"
    and all(dep in done_ids for dep in t["depends_on"])
]
```

Display:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Ready Tasks — PLAN-001  (can start immediately)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  TASK-ID    Priority   Title
  ────────────────────────────────────────────────────────────────────
  TASK-001   medium     <first task>
  TASK-004   low        <fourth task — independent branch>

  2 task(s) ready · 0 locked · 0 done · 3 waiting on dependencies
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

If no tasks are ready (all are locked, done, or blocked), print:

```
  No tasks are ready.  Check for circular dependencies or run /coordinate
  to detect agent lock conflicts.
```

---

### Step 6 — Render dependency graph (`graph` subcommand)

Build and print an ASCII dependency graph for the plan.

**Algorithm:**

1. Build adjacency list: `edges = {task_id: depends_on_list}`.
2. Compute topological layers using Kahn's algorithm (group tasks by generation).
3. Render each generation as a column, with arrows `──►` between dependent tasks.

**Output format:**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Task Dependency Graph — PLAN-001
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Generation 1 (runnable now)   Generation 2              Generation 3
  ──────────────────────────    ──────────────────────    ───────────────
  TASK-001 [unlocked] ──────►  TASK-003 [unlocked] ────► TASK-005 [unlocked]
  TASK-002 [unlocked] ──────►  (waits for 001+002)         (waits for 003+004)
  TASK-004 [unlocked] ─────────────────────────────────►

  Legend:  [unlocked] = claimable  [locked] = held  [done] = complete
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

If a **cycle** is detected, abort with:

```
  ✗ Cycle detected in PLAN-001:
    TASK-003 → TASK-005 → TASK-003
  Fix the depends_on fields to remove the cycle before proceeding.
```

---

### Step 7 — Show agent locks (`locks` subcommand)

Scan all `PLAN-*.yaml` files in `docs/exec-plans/`.  Collect every task where
`lock_status` is `locked`.  Display:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Active Locks
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Plan       Task       Agent              Title
  ────────────────────────────────────────────────────────────────────
  PLAN-001   TASK-002   coding-03abe8fb   <second task>
  PLAN-001   TASK-003   coding-7f615c39   <third task>

  2 lock(s) active · run /coordinate to check for conflicts
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

If no locks are active:

```
  No active locks.  All tasks are unlocked or done.
```

---

## Options

| Flag | Default | Subcommand(s) | Effect |
|------|---------|---------------|--------|
| `--title TEXT` | required | `new` | Plan title |
| `--id PLAN-NNN` | auto-assign | `new` | Explicit plan ID (must match `PLAN-[0-9]+`) |
| `--plan PLAN-NNN` | required | `ready`, `graph` | Plan to inspect |
| `--dry-run` | off | `init`, `new` | Print what would be created; do not write files |

---

## Output artifacts

### `init` subcommand

| Artifact | Description |
|----------|-------------|
| `docs/exec-plans/README.md` | Directory index and workflow guide |
| `docs/exec-plans/plan-template.yaml` | Blank plan template with all metadata fields |
| `docs/exec-plans/shared-state.yaml` | Multi-agent coordination snapshot scaffold |
| `docs/exec-plans/progress.md` | Running cross-plan progress log stub |
| `docs/exec-plans/debt.md` | Tech-debt tracker stub |
| `docs/exec-plans/perf.md` | Performance observations tracker stub |

Pre-existing files are **never overwritten**.  The skill is fully idempotent.

### `new` subcommand

| Artifact | Description |
|----------|-------------|
| `docs/exec-plans/<PLAN-ID>.yaml` | New execution plan pre-populated from the template |

---

## When to use this skill

| Scenario | Recommended skill |
|----------|-------------------|
| Bootstrap `docs/exec-plans/` on a new project | **`/execution-plans init`** ← you are here |
| Create a new execution plan | **`/execution-plans new`** |
| See which tasks can start right now | **`/execution-plans ready`** |
| Visualise the task dependency graph | **`/execution-plans graph`** |
| See which agents hold task locks | **`/execution-plans locks`** |
| Detect cross-agent file conflicts | `/coordinate` |
| Resume an interrupted agent session | `/harness:resume` |
| Log cross-plan progress updates | `/progress-log` |
| Show gate health alongside plan status | `/harness:status` |

---

## Notes

- **Idempotent** — `init` is safe to re-run; it never overwrites existing files.
- **Never auto-commits** — review generated files before committing.
- **Lock discipline** — agents must set `lock_status: locked` with their
  `assigned_agent` ID before editing a task's target files, and `lock_status: done`
  on completion.  Run `/coordinate` if you suspect a stale lock.
- **Dependency graph is in the YAML** — the `depends_on` list is the source of
  truth; the `graph` subcommand renders it for human inspection only.
- **Circular dependency detection** — the `graph` subcommand will abort and name
  the cycle rather than rendering a broken graph.
- **State service not required** — all subcommands operate on local YAML files;
  no network calls are made.
- **Coordination** — after tasks are claimed and agents start working, run
  `/coordinate` regularly to detect emerging file conflicts before they become
  hard merge conflicts.
>>>>>>> feat/execution-plans-skill-generates-docs-exec-plans-directo
