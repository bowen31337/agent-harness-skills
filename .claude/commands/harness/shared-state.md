# Harness: Shared State

Generate and manage `docs/exec-plans/shared-state.yaml` — a lightweight coordination
bus where agents publish intermediate results (discovered endpoints, schema changes,
test results) that peer agents can read at any time without polling the state service.

## Usage

```
/harness:shared-state              # initialize the shared-state file (safe to re-run)
/harness:shared-state publish      # append this agent's latest results
/harness:shared-state query        # print all published results
/harness:shared-state query --type endpoints         # filter to one result type
/harness:shared-state query --agent coding-abc123    # filter to one agent
```

## When to use

- **At plan start** — run `/harness:shared-state` once to create the file before any
  parallel agents begin work.
- **After a discovery step** — an agent that crawls endpoints or introspects a schema
  runs `/harness:shared-state publish` to make its findings available immediately.
- **Before acting on assumptions** — an agent checks `/harness:shared-state query`
  before duplicating work another agent already completed.
- **In the post-merge checklist** — run query to surface any result that needs
  follow-up action.

---

## Instructions

### Step 1 — Ensure the directory exists

```bash
mkdir -p docs/exec-plans
```

---

### Step 2 — Initialize `shared-state.yaml` (first agent only)

Check whether the file already exists before writing it:

```bash
if [ ! -f docs/exec-plans/shared-state.yaml ]; then
  TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
  cat > docs/exec-plans/shared-state.yaml <<EOF
# docs/exec-plans/shared-state.yaml
# Managed by /harness:shared-state — agents append to intermediate_results.
# Do not edit the meta block by hand.

meta:
  schema_version: "1"
  initialized_at: ${TIMESTAMP}
  last_updated_at: ${TIMESTAMP}

# ──────────────────────────────────────────────────────────────────────────────
# intermediate_results — append-only list of agent discoveries.
#
# Supported types:
#   endpoints       — REST / GraphQL / gRPC routes discovered in the codebase
#   schema_changes  — database migrations or Pydantic model diffs
#   test_results    — pytest / playwright run summaries
#   lint_results    — ruff / mypy findings
#   custom          — any other structured payload
#
# Each entry MUST contain: agent_id, published_at, type, summary, data
# ──────────────────────────────────────────────────────────────────────────────
intermediate_results: []
EOF
  echo "✅ Created docs/exec-plans/shared-state.yaml"
else
  echo "ℹ️  docs/exec-plans/shared-state.yaml already exists — skipping init"
fi
```

---

### Step 3 — Publish this agent's intermediate results

After completing a discovery or test step, append a result entry.

**3a. Determine your agent ID**

```bash
# The agent ID is available via the CLAW_FORGE_AGENT_ID env var,
# or fall back to the current git branch name.
AGENT_ID="${CLAW_FORGE_AGENT_ID:-$(git rev-parse --abbrev-ref HEAD)}"
```

**3b. Choose a result type and build the payload**

Use one of the templates below that matches your work, then call the publish script.

*Endpoints discovered:*

```python
# publish_result.py  (run via: python3 publish_result.py)
import yaml, sys
from datetime import datetime, timezone
from pathlib import Path

SHARED_STATE_FILE = Path("docs/exec-plans/shared-state.yaml")
AGENT_ID  = "REPLACE_WITH_AGENT_ID"        # e.g. "coding-abc123"
TIMESTAMP = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

entry = {
    "agent_id":     AGENT_ID,
    "published_at": TIMESTAMP,
    "type":         "endpoints",
    "summary":      "REPLACE — e.g. 'Discovered 12 REST endpoints in src/api/'",
    "data": {
        "endpoints": [
            # "GET /api/users",
            # "POST /api/users",
        ],
        "source_files": [],   # paths scanned
    },
}

state = yaml.safe_load(SHARED_STATE_FILE.read_text()) or {}
state.setdefault("intermediate_results", [])
state["intermediate_results"].append(entry)
state.setdefault("meta", {})["last_updated_at"] = TIMESTAMP

SHARED_STATE_FILE.write_text(
    yaml.dump(state, default_flow_style=False, sort_keys=False, allow_unicode=True)
)
print(f"✅ Published '{entry['type']}' result to {SHARED_STATE_FILE}")
```

*Schema changes detected:*

```python
entry = {
    "agent_id":     AGENT_ID,
    "published_at": TIMESTAMP,
    "type":         "schema_changes",
    "summary":      "REPLACE — e.g. '3 new migrations, 1 column removed'",
    "data": {
        "migrations": [],        # list of migration filenames or descriptions
        "models_changed": [],    # Pydantic / ORM model names
        "breaking": False,       # True if a breaking change is included
    },
}
```

*Test results:*

```python
entry = {
    "agent_id":     AGENT_ID,
    "published_at": TIMESTAMP,
    "type":         "test_results",
    "summary":      "REPLACE — e.g. '47 passed, 2 failed'",
    "data": {
        "passed":        0,
        "failed":        0,
        "skipped":       0,
        "duration_s":    0.0,
        "failing_tests": [],     # list of test node IDs that failed
        "coverage_pct":  None,   # float or null
    },
}
```

*Lint results:*

```python
entry = {
    "agent_id":     AGENT_ID,
    "published_at": TIMESTAMP,
    "type":         "lint_results",
    "summary":      "REPLACE — e.g. 'ruff: 0 errors; mypy: 2 warnings'",
    "data": {
        "tool":     "ruff",      # "ruff" | "mypy" | "eslint" | other
        "errors":   0,
        "warnings": 0,
        "issues":   [],          # list of {file, line, code, message}
    },
}
```

*Custom payload:*

```python
entry = {
    "agent_id":     AGENT_ID,
    "published_at": TIMESTAMP,
    "type":         "custom",
    "summary":      "REPLACE — one-line human-readable description",
    "data": {
        # any JSON-serialisable structure
    },
}
```

**3c. Run the publish script**

```bash
python3 publish_result.py
```

Expected output:

```
✅ Published 'endpoints' result to docs/exec-plans/shared-state.yaml
```

Remove `publish_result.py` after the run — it's a one-shot helper:

```bash
rm -f publish_result.py
```

---

### Step 4 — Query published results

Read what other agents have already published before starting overlapping work.

**Print all results:**

```bash
python3 - <<'EOF'
import yaml
from pathlib import Path

state = yaml.safe_load(Path("docs/exec-plans/shared-state.yaml").read_text()) or {}
results = state.get("intermediate_results", [])

if not results:
    print("No intermediate results published yet.")
else:
    print(f"{'Agent':<22} {'Published':<22} {'Type':<16} Summary")
    print("─" * 90)
    for r in results:
        print(f"{r['agent_id']:<22} {r['published_at']:<22} {r['type']:<16} {r['summary']}")
EOF
```

**Filter by type:**

```bash
FILTER_TYPE="endpoints"   # endpoints | schema_changes | test_results | lint_results | custom
python3 - <<EOF
import yaml
from pathlib import Path

state  = yaml.safe_load(Path("docs/exec-plans/shared-state.yaml").read_text()) or {}
filtered = [r for r in state.get("intermediate_results", []) if r["type"] == "${FILTER_TYPE}"]

if not filtered:
    print("No results of type '${FILTER_TYPE}' found.")
else:
    for r in filtered:
        print(yaml.dump(r, default_flow_style=False, sort_keys=False))
        print("─" * 60)
EOF
```

**Filter by agent:**

```bash
FILTER_AGENT="coding-abc123"
python3 - <<EOF
import yaml
from pathlib import Path

state    = yaml.safe_load(Path("docs/exec-plans/shared-state.yaml").read_text()) or {}
filtered = [r for r in state.get("intermediate_results", []) if r["agent_id"] == "${FILTER_AGENT}"]

if not filtered:
    print("No results from agent '${FILTER_AGENT}'.")
else:
    for r in filtered:
        print(yaml.dump(r, default_flow_style=False, sort_keys=False))
        print("─" * 60)
EOF
```

Expected output (all results):

```
Agent                  Published              Type             Summary
──────────────────────────────────────────────────────────────────────────────────────────
coding-abc123          2026-03-21T10:01:00Z   endpoints        Discovered 12 REST endpoints in src/api/
coding-def456          2026-03-21T10:02:30Z   schema_changes   3 new migrations, 1 column removed
coding-ghi789          2026-03-21T10:04:45Z   test_results     47 passed, 2 failed
```

---

### Step 5 — Commit the updated file

After publishing, stage and commit so peer agents on other branches can rebase and
read your results:

```bash
git add docs/exec-plans/shared-state.yaml
git commit -m "chore(exec-plan): publish ${RESULT_TYPE} results from ${AGENT_ID}

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Step 6 — (Optional) Push intermediate results to the state service

If the state service is running, broadcast your results so agents that haven't
rebased yet can still discover them:

```bash
curl -s -X POST http://localhost:8888/features/${FEATURE_ID}/events \
  -H "Content-Type: application/json" \
  -d "{
    \"type\": \"shared_state.published\",
    \"payload\": {
      \"agent_id\": \"${AGENT_ID}\",
      \"result_type\": \"${RESULT_TYPE}\",
      \"summary\": \"${SUMMARY}\",
      \"file\": \"docs/exec-plans/shared-state.yaml\"
    }
  }" || true
```

---

## File schema reference

```yaml
# docs/exec-plans/shared-state.yaml

meta:
  schema_version: "1"
  initialized_at: <ISO-8601 UTC>   # set once at creation
  last_updated_at: <ISO-8601 UTC>  # updated on every publish

intermediate_results:
  - agent_id:     <string>         # e.g. "coding-abc123" or branch name
    published_at: <ISO-8601 UTC>
    type:         <string>         # endpoints | schema_changes | test_results | lint_results | custom
    summary:      <string>         # one-line human-readable description
    data:         <object>         # type-specific payload (see templates above)
```

---

## Notes

- **Append-only** — never delete or overwrite existing entries; only append new ones.
  This preserves a full history of what each agent discovered and when.
- **Parallel-safe** — multiple agents can publish concurrently because each publish
  is a read-modify-write on a YAML file scoped to the agent's own branch. Conflicts
  only arise in the `intermediate_results` list, which is append-only and trivially
  rebased.
- **No state service required** — the file is a static YAML artifact checked into git.
  Agents that are offline or in isolated worktrees can still read and write it.
- **Consumers should be tolerant** — when reading, use `.get()` with defaults; future
  schema versions may add fields.
- **Keep `data` payloads small** — store file paths and summaries, not raw file
  contents. Link to the relevant source files instead of embedding them.
- **Re-running init is idempotent** — the `[ ! -f ... ]` guard means running
  `/harness:shared-state` a second time is always safe.
