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
