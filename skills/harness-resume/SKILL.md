---
name: harness:resume
description: "Load and present the most recent plan state for agent context handoff. Reads .claude/plan-progress.md (primary) or .plan_progress.jsonl (fallback) and formats the structured plan state — task, status, accomplished work, in-progress items, next steps, and search hints — so a new agent session can orient itself immediately. Search hints are presented as actionable pointers (file paths, grep patterns, key symbols) that the resuming agent verifies with its own Read/Grep/Glob tools. Use when: (1) starting a new session that continues previous agent work, (2) quickly checking what the current plan state is, (3) injecting saved plan state into an agent system prompt via the SDK, (4) bridging sessions after a context window limit or session restart, (5) presenting a handoff summary before a new agent begins. Triggers on: harness resume, load plan state, what was I working on, resume previous session, show plan progress, continue from last session, where did I leave off, read handoff, present context handoff."
---

# harness:resume

## Overview

`harness:resume` reads the most-recent saved plan state and presents it as a
structured context block so a new agent session can pick up exactly where the
previous one left off.

It is the *reading* complement to the `context-handoff` skill's write side:
where `context-handoff` tells an **ending** agent how to write a handoff,
`harness:resume` gives a **starting** agent the tools to consume it.

Two sources are supported:

| Source | Path | Notes |
|--------|------|-------|
| Markdown | `.claude/plan-progress.md` | Primary; latest-wins (overwritten each session) |
| JSONL | `.plan_progress.jsonl` | Fallback; append-only audit trail |

---

## Workflow

**Do you want to read and display the current plan state?**
→ [CLI usage](#cli-usage)

**Do you want to inject plan state into an agent session at startup?**
→ [SDK integration](#sdk-integration)

**Do you want to verify search hints right now?**
→ [Rebuilding context from hints](#rebuilding-context-from-hints)

---

## CLI Usage

```bash
# Display full plan state (default):
python -m harness_skills.resume

# Print only search hints (fast orientation):
python -m harness_skills.resume --hints

# Machine-readable JSON:
python -m harness_skills.resume --json

# Read from a non-default path:
python -m harness_skills.resume --md-path .claude/other-progress.md

# Prefer JSONL over Markdown:
python -m harness_skills.resume --prefer jsonl
```

The helper script [`scripts/resume.py`](scripts/resume.py) wraps the CLI for
use without installing the full package.

---

## SDK Integration

Use `resume_agent_options` to inject plan state into a new agent session's
system prompt before the first turn:

```python
from harness_skills.resume import load_plan_state, resume_agent_options
from claude_agent_sdk import ClaudeAgentOptions, query

# Load state and inject into options
state = load_plan_state()
options, state = resume_agent_options(
    ClaudeAgentOptions(allowed_tools=["Read", "Glob", "Grep"]),
    state=state,
)

# The system prompt now contains the full plan state + rebuild instructions
async for msg in query(prompt="Continue from where we left off.", options=options):
    print(msg)
```

Or load state yourself and pass it in:

```python
from pathlib import Path
from harness_skills.resume import load_plan_state, resume_agent_options

state = load_plan_state(
    md_path=Path(".claude/plan-progress.md"),
    jsonl_path=Path(".plan_progress.jsonl"),
    prefer="md",   # "md" | "jsonl"
)

if not state.found():
    print("No saved plan state — starting fresh.")
else:
    options, _ = resume_agent_options(base_options, state=state)
```

---

## Rebuilding Context from Hints

After loading the plan state, a resuming agent should **verify** the hints
rather than trusting them as ground truth:

```python
from harness_skills.resume import load_plan_state

state = load_plan_state()
hints = state.search_hints

# 1. Read key files
for path in hints.file_paths:
    # → call Read tool on each path

# 2. Grep key patterns
for pattern in hints.grep_patterns:
    # → call Grep tool with each pattern

# 3. Glob key directories
for directory in hints.directories:
    # → call Glob on f"{directory}/**/*"

# 4. Search key symbols
for symbol in hints.symbols:
    # → call Grep tool with each symbol name
```

---

## Programmatic API

### `load_plan_state`

```python
from harness_skills.resume import load_plan_state, PlanState

state: PlanState = load_plan_state(
    md_path=Path(".claude/plan-progress.md"),   # optional override
    jsonl_path=Path(".plan_progress.jsonl"),     # optional override
    prefer="md",                                  # "md" | "jsonl"
)

state.found()          # True when a file was read successfully
state.task             # overall task description
state.status           # "in_progress" | "blocked" | "done"
state.timestamp        # ISO-8601 UTC string
state.accomplished     # list[str] — completed items
state.in_progress      # list[str] — partially-done items
state.next_steps       # list[str] — ordered next actions
state.search_hints     # SearchHints — file_paths, directories, grep_patterns, symbols
state.open_questions   # list[str]
state.artifacts        # list[str] — files created/modified
state.notes            # str — free-form context
state.source           # "markdown" | "jsonl" | "none"
```

### `format_resume_context`

```python
from harness_skills.resume import load_plan_state, format_resume_context

state = load_plan_state()
print(format_resume_context(state))   # human-readable context block
```

### `format_hints_only`

```python
from harness_skills.resume import load_plan_state, format_hints_only

state = load_plan_state()
print(format_hints_only(state))   # compact search-hints-only view
```

### `build_resume_prompt`

```python
from harness_skills.resume import load_plan_state, build_resume_prompt

state  = load_plan_state()
prompt = build_resume_prompt(state)   # system-prompt addendum (empty string if no state)
```

---

## `PlanState` Fields

| Field | Type | Description |
|-------|------|-------------|
| `task` | `str` | High-level task description. |
| `status` | `str` | `"in_progress"` \| `"blocked"` \| `"done"`. |
| `session_id` | `str` | Session that wrote the last handoff. |
| `timestamp` | `str` | ISO-8601 UTC timestamp of the last save. |
| `accomplished` | `list[str]` | Items completed in the previous session. |
| `in_progress` | `list[str]` | Partially-done work with % complete notes. |
| `next_steps` | `list[str]` | Ordered actions for the resuming agent. |
| `search_hints` | `SearchHints` | File paths, directories, grep patterns, symbols. |
| `open_questions` | `list[str]` | Unresolved decisions or blockers. |
| `artifacts` | `list[str]` | Files created or significantly modified. |
| `notes` | `str` | Free-form context. |
| `source` | `str` | `"markdown"` \| `"jsonl"` \| `"none"`. |

## `SearchHints` Fields

| Field | Type | Description |
|-------|------|-------------|
| `file_paths` | `list[str]` | Relative paths to read first. |
| `directories` | `list[str]` | Directories to explore with Glob. |
| `grep_patterns` | `list[str]` | Regex patterns for the Grep tool. |
| `symbols` | `list[str]` | Class/function/variable names to search for. |

---

## Key Files

| Path | Purpose |
|------|---------|
| `harness_skills/resume.py` | All public API — `load_plan_state`, `PlanState`, `SearchHints`, `format_resume_context`, `format_hints_only`, `build_resume_prompt`, `resume_agent_options`, CLI. |
| `skills/harness-resume/scripts/resume.py` | Standalone CLI helper (no package install needed). |
| `.claude/plan-progress.md` | Primary plan state source (written by `context-handoff` skill). |
| `.plan_progress.jsonl` | Append-only audit trail fallback source. |
| `harness_skills/handoff.py` | `HandoffDocument` / `HandoffProtocol` — used internally for Markdown parsing. |
