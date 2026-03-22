# Checkpoint

Save the current project state: git commit all changes with a timestamp, export the feature DB state to a JSON snapshot, and write a summary of what's passing.

## Instructions

### Step 1: Run quality checks

```bash
uv run pytest tests/ -q --no-header 2>&1 | tail -5
```

Note which tests pass/fail — this goes in the commit message.

### Step 2: Export feature state

```bash
# Snapshot the state DB
TIMESTAMP=$(date +%Y%m%dT%H%M%S)
SNAPSHOT_FILE=".claw-forge/snapshots/snapshot-${TIMESTAMP}.json"
mkdir -p .claw-forge/snapshots

# Query the state service
curl -s http://localhost:8420/sessions | python3 -m json.tool > "$SNAPSHOT_FILE" 2>/dev/null || \
  echo '{"note": "state service not running at checkpoint time"}' > "$SNAPSHOT_FILE"

echo "Snapshot saved: $SNAPSHOT_FILE"
```

### Step 3: Write checkpoint summary

Create `.claw-forge/CHECKPOINT.md`:

```markdown
# Checkpoint — <TIMESTAMP>

## Status
- Tests: <N> passing, <M> failing
- Features: <completed>/<total> complete
- Snapshot: snapshots/snapshot-<TIMESTAMP>.json

## What's working
<List of completed features based on state DB>

## What's in progress
<List of running/pending features>

## Known issues
<Any failing tests or blocked features>
```

### Step 4: Git commit

```bash
# Stage everything
git add -A

# Commit with structured message
git commit -m "checkpoint: $(date '+%Y-%m-%d %H:%M:%S')

Status:
- Tests: <N> passing
- Features: <completed>/<total>

See .claw-forge/CHECKPOINT.md for details"
```

### Step 5: Confirm

```
✅ Checkpoint saved!

  Commit: <git hash>
  Snapshot: .claw-forge/snapshots/snapshot-<TIMESTAMP>.json
  Summary: .claw-forge/CHECKPOINT.md

To restore to this state:
  git checkout <hash>
```

### Notes

- Checkpoints are safe to create at any time — they never disrupt running agents
- Run /checkpoint before risky operations (provider changes, schema migrations)
- The JSON snapshot is a point-in-time view of the task graph

---

## Git-Based WIP Checkpoint Integration (Multi-Agent)

For automated, per-tool-use checkpoints with full multi-agent traceability, use
`git_checkpoint.py` / `checkpoint_agent.py` instead of (or alongside) the manual
steps above.

### How it works

Every time the agent writes, edits or runs a Bash command, `GitCheckpoint`
automatically:

1. Creates (or checks out) a dedicated WIP branch:
   ```
   wip/<agent_id>/<task_id>
   ```

2. Stages all changes and commits them with a **structured message** that
   includes three Git trailers for traceability:
   ```
   wip(feat/auth-refactor): after Edit [checkpoint #3]

   Automated WIP checkpoint committed by agent harness.

   Checkpoint: #3
   Timestamp:  2026-03-22T10:42:00+00:00
   Tool:       Edit
   Tool Input: file_path=src/auth/token_validator.py

   Plan-Ref: Step 3 — extract and harden TokenValidator class
   Agent-Id: agent-42
   Task-Id:  feat/auth-refactor
   ```

3. Writes `.checkpoint_meta.json` to the repo root with all metadata fields
   so CI, dashboards and other tooling can parse it without walking commits:
   ```json
   {
     "agent_id": "agent-42",
     "task_id": "feat/auth-refactor",
     "plan_ref": "Step 3 — extract and harden TokenValidator class",
     "branch": "wip/agent-42/feat-auth-refactor",
     "commit_sha": "a1b2c3d4...",
     "timestamp": "2026-03-22T10:42:00+00:00",
     "checkpoint_index": 3,
     "tool_name": "Edit",
     "tool_input_summary": "file_path=src/auth/token_validator.py"
   }
   ```

### Quick start

```python
from git_checkpoint import GitCheckpoint
from claude_agent_sdk import query, ClaudeAgentOptions, HookMatcher

cp = GitCheckpoint(
    agent_id="agent-42",          # stable agent identifier
    task_id="feat/auth-refactor", # task / ticket / feature ID
    plan_ref="Step 3 — extract and harden TokenValidator class",
    repo_path="/path/to/repo",    # defaults to cwd
)
cp.ensure_branch()  # creates wip/agent-42/feat-auth-refactor

async for msg in query(
    prompt="Refactor the auth module",
    options=ClaudeAgentOptions(
        allowed_tools=["Read", "Edit", "Write", "Bash"],
        permission_mode="acceptEdits",
        hooks={
            "PostToolUse": [
                HookMatcher(matcher="Edit|Write|Bash", hooks=[cp.as_hook()])
            ]
        },
    ),
):
    ...
```

Or run the bundled end-to-end example:

```bash
AGENT_ID=agent-01 TASK_ID=harness-task-001 python checkpoint_agent.py
```

### Multi-agent traceability

Each `GitCheckpoint` instance stamps its own `agent_id` and `task_id` into
every commit trailer and into `.checkpoint_meta.json`.  This lets you:

- **Audit** exactly which agent made which change, and at which plan step
- **Correlate** commits across parallel agent branches using `Agent-Id:` in
  `git log --grep="Agent-Id: agent-42"`
- **Resume** from any checkpoint with `git checkout <sha>`
- **Diff** two agents' work: `git diff wip/agent-A/task wip/agent-B/task`

### Environment variables (checkpoint_agent.py)

| Variable           | Default            | Purpose                         |
|--------------------|--------------------|---------------------------------|
| `ANTHROPIC_API_KEY`| —                  | Required for API access         |
| `AGENT_ID`         | `"agent-01"`       | Agent identifier in metadata    |
| `TASK_ID`          | `"harness-task-001"` | Task identifier in metadata   |
