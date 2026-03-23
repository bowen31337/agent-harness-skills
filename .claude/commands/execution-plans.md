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
