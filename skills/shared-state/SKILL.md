---
name: shared-state
description: "Shared agent state publisher and query tool. Agents publish intermediate results (discovered endpoints, schema changes, test results, or arbitrary structured data) into docs/exec-plans/shared-state.yaml so other concurrently-running agents can read them. All writes are protected by an advisory file lock for safe concurrent access. Use when: (1) an agent has discovered API endpoints that other agents need, (2) an agent has applied schema changes that downstream agents should know about, (3) an agent has run tests and wants to share pass/fail counts or coverage data, (4) any agent wants to leave structured breadcrumbs for agents that run later, (5) querying what intermediate state has already been published before starting a task. Triggers on: publish result, share intermediate result, discovered endpoints, schema changes, test results, shared state, agent breadcrumbs, inter-agent communication, query shared state."
---

# Shared State Skill

## Overview

The shared-state skill lets agents **publish** intermediate results into
`docs/exec-plans/shared-state.yaml` and **query** results published by
other agents.  It is the primary mechanism for loose-coupled, file-based
inter-agent communication in the claw-forge harness.

All writes use an **exclusive advisory file lock** (`fcntl.LOCK_EX`) so
concurrent agents can safely call `publish` without corrupting the file.

---

## Workflow

**Do you want to publish a result from the CLI?**
→ [CLI usage — publish](#cli-usage)

**Do you want to query what other agents have published?**
→ [CLI usage — query / list](#cli-usage)

**Do you want to publish or query from Python?**
→ [Programmatic usage](#programmatic-usage)

---

## CLI Usage

### Publish a result

```bash
# Publish discovered endpoints (inline JSON)
python skills/shared_state.py publish \
    --agent coding-03abe8fb \
    --type discovered_endpoints \
    --data '{"endpoints": ["/api/v1/users", "/api/v1/orders"]}' \
    --notes "Found during route exploration"

# Publish schema changes (pipe JSON from stdin)
echo '{"table": "users", "added_columns": ["verified_at"]}' | \
python skills/shared_state.py publish \
    --agent coding-48dd7f13 \
    --type schema_changes

# Publish test results
python skills/shared_state.py publish \
    --agent coding-bae7b81c \
    --type test_results \
    --data '{"passed": 142, "failed": 3, "coverage_delta": "+2.1%"}'

# Publish arbitrary structured data
python skills/shared_state.py publish \
    --agent coding-e4908d0c \
    --type other \
    --data '{"feature_flags_enabled": ["dark_mode", "new_checkout"]}'
```

### Query published results

```bash
# All results of a given type (human-readable table)
python skills/shared_state.py query --type schema_changes

# All results from a specific agent (JSON output for piping)
python skills/shared_state.py query --agent coding-48dd7f13 --json

# Combined filter: type + agent
python skills/shared_state.py query \
    --type discovered_endpoints \
    --agent coding-03abe8fb

# List every published result
python skills/shared_state.py list

# Dump the raw intermediate_results YAML
python skills/shared_state.py dump
```

---

## Programmatic Usage

### Publish

```python
from skills.shared_state import SharedState

ss = SharedState()

# Discovered endpoints
ss.publish(
    agent_id="coding-03abe8fb",
    result_type="discovered_endpoints",
    data={"endpoints": ["/api/v1/users", "/api/v1/orders"]},
    notes="Found during route exploration",
)

# Schema change
ss.publish(
    agent_id="coding-48dd7f13",
    result_type="schema_changes",
    data={"table": "users", "added_columns": ["verified_at"]},
)

# Test results
ss.publish(
    agent_id="coding-bae7b81c",
    result_type="test_results",
    data={"passed": 142, "failed": 3, "coverage_delta": "+2.1%"},
)
```

### Query

```python
from skills.shared_state import SharedState

ss = SharedState()

# All schema changes (across all agents)
for result in ss.query(result_type="schema_changes"):
    print(result["agent_id"], result["timestamp"], result["data"])

# Everything a specific agent has published
for result in ss.query(agent_id="coding-48dd7f13"):
    print(result["type"], result["data"])

# Every published result
all_results = ss.list_all()

# Render a summary table (returns a string)
print(ss.render_table(all_results))

# Dump the section as YAML
print(ss.dump_raw())
```

---

## Result Entry Schema

Each entry written to `intermediate_results` in `shared-state.yaml` has
the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `agent_id` | `str` | ID of the publishing agent (e.g. `coding-03abe8fb`). |
| `type` | `str` | One of the four result types below. |
| `timestamp` | `str` | UTC ISO-8601 timestamp of publication. |
| `data` | `any` | Arbitrary JSON-serialisable payload. |
| `notes` | `str` | Optional human-readable description (omitted if empty). |

### Result types

| Type | Typical payload |
|------|----------------|
| `discovered_endpoints` | `{"endpoints": [...]}` |
| `schema_changes` | `{"table": "...", "added_columns": [...], "removed_columns": [...]}` |
| `test_results` | `{"passed": N, "failed": N, "coverage_delta": "..."}` |
| `other` | Any structured data that doesn't fit the above categories. |

---

## Concurrency & Safety

- Writes use **`fcntl.LOCK_EX`** (exclusive advisory lock) so that parallel
  agents can call `publish` simultaneously without race conditions.
- The lock is acquired on the open file handle and released in a `finally`
  block, so a crash mid-write will not permanently block other agents.
- `query`, `list_all`, and `dump_raw` are read-only and do not acquire a
  lock — they may occasionally read a microsecond-stale view on Linux, but
  this is acceptable for the coordination use-case.

---

## Prerequisites

- `PyYAML` must be installed (`uv add pyyaml`).
- `docs/exec-plans/shared-state.yaml` must exist.  If it is missing, run
  the **coordinate** skill first to regenerate it.

---

## Key Files

| Path | Purpose |
|------|---------|
| `skills/shared_state.py` | Full implementation — `SharedState` class, CLI, lock logic. |
| `docs/exec-plans/shared-state.yaml` | The shared state file that is read and written. |
