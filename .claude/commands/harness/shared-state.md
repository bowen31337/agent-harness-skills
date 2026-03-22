<<<<<<< HEAD
# Harness Shared-State

Generate and manage **`docs/exec-plans/shared-state.yaml`** — a lightweight
coordination bus where agents publish intermediate results (discovered
endpoints, schema changes, test results) that any other agent in the same
run can read and act on.

The file is the single source of truth for cross-agent data that does not
belong in git commits and is too ephemeral for the state service.

---

## What it shows / stores

| Category | Example keys |
|---|---|
| `endpoints` | `GET /users`, `POST /auth/token` — URLs discovered by API-scanning agents |
| `schema_changes` | `users.email nullable=true` — DB or Pydantic model diffs |
| `test_results` | `pytest::test_login pass`, `playwright::auth_flow fail` |
| `config` | Feature flags, environment overrides shared between agents |
| `custom` | Any free-form key → value the task requires |

---

## Usage

```bash
# Initialise (or reset) the shared-state file
/harness:shared-state init

# Publish an intermediate result
/harness:shared-state publish --agent <id> --category endpoints --key "GET /users" --value '{"status":200}'

# Query — print every entry for a category
/harness:shared-state query --category endpoints

# Query — single key lookup
/harness:shared-state query --category schema_changes --key "users.email"

# Dump the whole file as JSON (for piping to other tools)
/harness:shared-state dump --format json

# Merge a second YAML patch into shared-state (idempotent)
/harness:shared-state merge --patch-file /tmp/my-agent-results.yaml

# Show a human-readable summary table
/harness:shared-state status
```

---

## Instructions

### Step 1 — Locate or create the shared-state file

Check if `docs/exec-plans/shared-state.yaml` already exists:

```bash
ls docs/exec-plans/shared-state.yaml 2>/dev/null || echo "__MISSING__"
```

- If present, read and parse it so you preserve the existing `snapshot`,
  `agents`, `conflict_clusters`, and `execution_plan` sections.
- If missing, create the `docs/exec-plans/` directory first:

```bash
mkdir -p docs/exec-plans
```

Then generate the stub file (see **Schema** below).

---

### Step 2 — Initialise the file (`init`)

When running `init`, write `docs/exec-plans/shared-state.yaml` with:

```yaml
snapshot:
  timestamp: '<ISO-8601 UTC now>'
  agent_count: 0
  conflict_count: 0
  high_conflicts: 0
  medium_conflicts: 0
  low_conflicts: 0
  state_service: http://localhost:8888
  state_service_available: false
  source: harness-shared-state-init
agents: []
large_refactor_agents: []
conflict_clusters: []
intermediate_results: []
execution_plan:
  strategy: parallel-with-serialised-hotspots
  slots: []
  post_merge_checklist: []
```

If the file already exists, only overwrite `snapshot.timestamp` and
`snapshot.source`; leave all other top-level keys intact.

---

### Step 3 — Publish a result (`publish`)

Read the current file, locate the `intermediate_results` list, then
**append** (never replace) one entry:

```yaml
- agent_id: '<agent flag value>'
  timestamp: '<ISO-8601 UTC now>'
  category: '<endpoints|schema_changes|test_results|config|custom>'
  key: '<key flag value>'
  value: <parsed JSON / plain string from the value flag>
  ttl_minutes: 60          # optional — callers may set 0 for "keep forever"
```

After appending, write the file back and print a one-line confirmation:

```
✅  published  endpoints / "GET /users"  (agent: coding-abc123)
```

---

### Step 4 — Query results (`query`)

Read the file and filter `intermediate_results` by `category` (required)
and optionally by `key` (exact match) or `agent_id`.

Print a compact table:

```
  Shared-State Query — category: endpoints
  ────────────────────────────────────────────────────────────────────
  Key                  Agent              Timestamp            Value
  ──────────────────────────────────────────────────────────────────
  GET /users           coding-abc123      2026-03-22T10:01:05  {"status":200}
  POST /auth/token     coding-def456      2026-03-22T10:02:11  {"status":201}
  ────────────────────────────────────────────────────────────────────
  2 result(s) found
```

If the file does not exist or `intermediate_results` is empty, print:

```
ℹ️  No results found for category "endpoints"
```

Exit 0 in both cases.

---

### Step 5 — Dump the whole file (`dump`)

When `--format json` is requested, read the YAML file and output it as
compact JSON to stdout (suitable for piping to `jq`).

When `--format yaml` (default), print the raw file contents.

---

### Step 6 — Merge a patch file (`merge`)

Read both the current `shared-state.yaml` and the supplied `--patch-file`.
The patch file must be a YAML document containing only the keys it wants
to update or extend.  Rules:

- `intermediate_results` — **append** all entries from the patch to the
  existing list (no deduplication; callers are responsible for idempotency
  via `key`).
- `agents` — **upsert** by `id`; if an agent already exists update its
  fields, otherwise append.
- `conflict_clusters` — **append** new clusters; skip if `cluster` key
  already present.
- `snapshot` — merge scalar fields; `timestamp` is updated to "now".
- All other keys — deep-merge (patch wins on scalar conflicts).

Print a summary after merge:

```
🔀  merge complete
    intermediate_results: +3 new entries  (total: 7)
    agents:               +1 new  /  2 updated
    conflict_clusters:    +0 new  (total: 6)
```

---

### Step 7 — Status summary (`status`)

Print a human-readable overview of the current file:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Shared-State Status  —  docs/exec-plans/shared-state.yaml
  Snapshot: 2026-03-22T10:05:00  |  Source: harness-shared-state-init
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Agents tracked:        12
  Conflict clusters:      6   (high: 0 / med: 4 / low: 2)
  Intermediate results:   9
    ├─ endpoints          4
    ├─ schema_changes     2
    ├─ test_results       2
    └─ config             1

  State service:         http://localhost:8888  [offline]

  Recent results (last 3):
  ─────────────────────────────────────────────────────────────
  2026-03-22T10:04:55  test_results   coding-xyz  playwright::auth_flow
  2026-03-22T10:03:10  schema_changes coding-abc  users.email
  2026-03-22T10:01:05  endpoints      coding-def  GET /users
```

---

## Schema

Full `shared-state.yaml` schema (all optional sections may be omitted when
empty):

```yaml
# ── Snapshot metadata ──────────────────────────────────────────────
snapshot:
  timestamp: string          # ISO-8601 UTC
  agent_count: integer
  conflict_count: integer
  high_conflicts: integer
  medium_conflicts: integer
  low_conflicts: integer
  state_service: string      # URL
  state_service_available: boolean
  source: string             # "harness-shared-state-init" | "coordinate" | …

# ── Agent roster ────────────────────────────────────────────────────
agents:
  - id: string
    branch: string
    status: running | pending | paused | done | blocked
    files_touched: integer
    notable: boolean         # optional

large_refactor_agents: [string]   # agent id list

# ── Conflict data (populated by /coordinate) ────────────────────────
conflict_clusters:
  - cluster: string          # canonical file path or logical group name
    description: string
    agents_involved: [string]
    recommendation: string

# ── Intermediate results (populated by this skill) ──────────────────
intermediate_results:
  - agent_id: string
    timestamp: string        # ISO-8601 UTC
    category: endpoints | schema_changes | test_results | config | custom
    key: string              # human-readable lookup key
    value: any               # string, mapping, or list
    ttl_minutes: integer     # 0 = keep forever; omit = default 60

# ── Execution plan (populated by /coordinate) ───────────────────────
execution_plan:
  strategy: string
  slots:
    - slot: integer
      run_in_parallel: boolean
      agents: [string] | "all"
      notes: string
  post_merge_checklist: [string]
```

---

## Options

| Flag | Default | Effect |
|---|---|---|
| `--state-file PATH` | `docs/exec-plans/shared-state.yaml` | Override the target file |
| `--agent ID` | `$AGENT_ID` env var | Agent identifier for publish |
| `--category` | _(required for publish/query)_ | Result category |
| `--key` | _(required for publish)_ | Lookup key |
| `--value` | _(required for publish)_ | Result value (JSON or plain string) |
| `--ttl-minutes N` | `60` | Entry expiry (0 = permanent) |
| `--format json\|yaml` | `yaml` | Output format for dump |
| `--patch-file PATH` | _(required for merge)_ | YAML patch to merge in |
| `--no-state-service` | `false` | Skip live state service lookup |

---

## When to use this skill

| Situation | Recommended skill |
|---|---|
| Publish API endpoints found during exploration | `/harness:shared-state publish --category endpoints` |
| Share DB schema diffs with downstream agents | `/harness:shared-state publish --category schema_changes` |
| Record test results another agent should gate on | `/harness:shared-state publish --category test_results` |
| Read what endpoints are already known | `/harness:shared-state query --category endpoints` |
| View overall cross-agent coordination picture | `/coordinate` |
| See plan-level task status (running / blocked / done) | `/harness:status` |
| Initialise a fresh shared-state file at plan start | `/harness:shared-state init` |

---

## Notes

- **Idempotent init** — running `init` multiple times is safe; it never
  deletes existing `intermediate_results` or agent entries.
- **No locking** — this skill writes YAML directly; for concurrent writes
  under heavy parallelism use the state service (`POST /features/{id}/kv`)
  as the authoritative store and treat shared-state.yaml as a cache.
- **TTL enforcement** — stale entries (past `ttl_minutes`) are silently
  filtered from query results but are never auto-deleted from the file;
  run `init` to reset.
- **Coordinate interop** — `/coordinate` populates the `agents`,
  `conflict_clusters`, and `execution_plan` sections of the same file;
  this skill owns only the `intermediate_results` section and never
  overwrites the others.
||||||| 0e893bd
=======
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
>>>>>>> feat/execution-plans-skill-generates-a-shared-state-file-doc
