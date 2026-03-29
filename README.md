# Agent Harness Skills

**A model-agnostic framework for AI agent orchestration, quality gates, and multi-agent coordination.**

This repository provides production-grade skills, tools, and coordination primitives that any AI coding agent can use — whether it's Claude Code, Gemini CLI, OpenAI Codex, LangChain agents, or a custom SDK. Skills are defined as Markdown + Python, so no vendor lock-in is required.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Quick Start](#quick-start)
- [Using Skills from Different Agents](#using-skills-from-different-agents)
  - [Claude Code](#claude-code)
  - [Gemini CLI](#gemini-cli)
  - [OpenAI Codex CLI](#openai-codex-cli)
  - [Claude Agent SDK (Programmatic)](#claude-agent-sdk-programmatic)
  - [LangChain / LangGraph Agents](#langchain--langgraph-agents)
  - [Custom Agent Frameworks](#custom-agent-frameworks)
- [Skills Catalog](#skills-catalog)
- [Multi-Agent Coordination](#multi-agent-coordination)
- [Quality Gates](#quality-gates)
- [Project Structure](#project-structure)
- [Configuration](#configuration)
- [Examples](#examples)
- [Contributing](#contributing)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Agent Layer                           │
│  Claude Code │ Gemini CLI │ Codex │ LangChain │ Custom  │
└──────┬───────┴─────┬──────┴───┬───┴─────┬─────┴────┬───┘
       │             │          │         │          │
       ▼             ▼          ▼         ▼          ▼
┌─────────────────────────────────────────────────────────┐
│              Skill Definitions (Markdown)                │
│         .claude/commands/*.md  +  skills/*/SKILL.md      │
└──────────────────────┬──────────────────────────────────┘
                       │
       ┌───────────────┼───────────────┐
       ▼               ▼               ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│  harness_   │ │  harness_   │ │    dom_      │
│  skills/    │ │  tools/     │ │  snapshot_   │
│  (core)     │ │  (CLIs)     │ │  utility/    │
└─────────────┘ └─────────────┘ └─────────────┘
       │               │
       ▼               ▼
┌─────────────────────────────────────────────────────────┐
│   Coordination Layer: Handoff │ Task Lock │ Shared State │
└─────────────────────────────────────────────────────────┘
```

**Key design principles:**

- **Structured tools over free-form output** — Schema-enforce correctness; tool-enforce format.
- **Progressive disclosure** — Minimum viable context first; let the agent pull depth on demand.
- **Tool lifecycle** — Provision, validate, evolve, and retire tools as model capabilities change.
- **Multi-agent readiness** — File-based coordination primitives from day one (no central server required).

---

## Quick Start

```bash
# 1. Clone and install
git clone <repo-url> && cd agent-harness-skills
pip install -e ".[dev]"            # or: uv pip install -e ".[dev]"

# 2. Configure
cp .env.example .env               # add your API keys
# Edit claw-forge.yaml for model providers and skill settings

# 3. Run tests
pytest tests/ -v

# 4. (Optional) Install Playwright for browser automation
playwright install chromium
```

---

## Using Skills from Different Agents

Skills in this repo are defined at two levels:

| Level | Location | Format | Purpose |
|-------|----------|--------|---------|
| **Skill commands** | `.claude/commands/*.md` | Markdown with frontmatter | Agent-facing instructions (what to do, when, how) |
| **Skill implementations** | `skills/*/SKILL.md` + Python modules | Markdown docs + Python | Reusable logic callable from any runtime |
| **Orchestration tools** | `harness_tools/*.py` | Python CLI modules | Thin wrappers for shell/CI invocation |
| **Core framework** | `harness_skills/` | Python package | Pydantic models, gates, CLI, coordination |

### Claude Code

Claude Code natively loads `.claude/commands/` as slash commands. This is the **zero-config** path.

**Invoke skills as slash commands:**

```
# In Claude Code CLI or IDE extension
> /harness:status              # Show live harness dashboard
> /harness:evaluate            # Run all quality gates
> /harness:handoff             # Write a handoff document for the next agent
> /check-code                  # Scan for module boundary violations
> /browser-automation          # Set up Playwright + AgentDriver
> /create-spec                 # Generate an XML project specification
```

**Use the harness CLI directly:**

```bash
# From the terminal inside Claude Code
harness status
harness evaluate
harness lint
harness observe --tail 50
```

**Programmatic access in Claude Code subagents:**

```python
from harness_skills.handoff import HandoffDocument, HandoffProtocol, SearchHints
from harness_skills.task_lock import TaskLock
from harness_skills.boot import boot_instance, BootConfig

# Lock a resource before mutating shared state
with TaskLock("migrate-db"):
    run_migration()

# Write a handoff for the next agent session
doc = HandoffDocument(
    task_id="feat-42",
    summary="Implemented CoverageGate; tests pass.",
    search_hints=SearchHints(symbols=["CoverageGate"], files=["harness_skills/gates/"]),
    next_steps=["Wire into GateEvaluator.run_all()", "Update CHANGELOG"],
)
HandoffProtocol.write(doc)
```

### Gemini CLI

Gemini CLI uses `GEMINI.md` for project instructions and activates skills via its `activate_skill` tool. To integrate:

**1. Create a `GEMINI.md` in the repo root** that mirrors `CLAUDE.md` instructions:

```markdown
# GEMINI.md

## Skills
Skills are defined in `.claude/commands/` as Markdown files.
Use `activate_skill` to load any skill by name.

## Tool Mapping
| Claude Code Tool | Gemini CLI Equivalent |
|------------------|----------------------|
| Read             | read_file            |
| Edit             | edit_file            |
| Write            | write_file           |
| Bash             | run_shell            |
| Grep             | search_content       |
| Glob             | find_files           |
```

**2. Reference skills by reading the Markdown directly:**

```
# In Gemini CLI
> Read the skill at .claude/commands/harness/evaluate.md and follow its instructions
> Run: python -m harness_skills.cli evaluate
```

**3. Use the Python APIs** — they work identically regardless of which agent calls them:

```python
from harness_skills.gates import run_gates
results = run_gates("harness.config.yaml")
```

### OpenAI Codex CLI

Codex CLI reads `AGENTS.md` for agent-facing instructions. This repo already ships an `AGENTS.md`.

**1. Point Codex at the harness tools:**

```markdown
# In AGENTS.md (already provided)
## Available Tools
- Run `harness evaluate` to execute quality gates
- Run `harness status` for live dashboard
- Run `python harness_tools/coordinate.py` for multi-agent conflict detection
```

**2. Invoke skills via shell commands:**

```bash
# Codex can run these directly
python -m harness_skills.cli evaluate
python -m harness_skills.cli status
python -m harness_skills.cli lint
python harness_tools/handoff.py --task-id feat-42 --summary "Done with auth module"
```

**3. Read skill definitions for context:**

Codex agents can read `.claude/commands/harness/evaluate.md` to understand what a gate evaluation entails, then execute the corresponding Python module.

### Claude Agent SDK (Programmatic)

For agents built with the [Claude Agent SDK](https://docs.anthropic.com/en/docs/agents), skills are consumed as Python imports:

```python
"""Full agent lifecycle: boot → work → handoff"""
import anyio
from claude_agent_sdk import ClaudeAgentOptions, query, SystemMessage

from harness_skills.boot import boot_instance, BootConfig
from harness_skills.handoff import HandoffDocument, HandoffProtocol, SearchHints
from harness_skills.task_lock import TaskLock
from harness_skills.performance_hooks import PerformanceTracker

async def run_agent():
    # Boot with isolation
    config = BootConfig(project_root=".", isolation="schema")
    boot_instance(config)

    # Track performance
    tracker = PerformanceTracker()
    tracker.start("full-task")

    # Do work with exclusive resource access
    with TaskLock("shared-db"):
        result = await query(
            model="claude-sonnet-4-6",
            system=[SystemMessage(text="You are a coding agent.")],
            prompt="Implement the auth middleware.",
            options=ClaudeAgentOptions(max_tokens=4096),
        )

    tracker.stop("full-task")

    # Hand off to next session
    HandoffProtocol.write(HandoffDocument(
        task_id="auth-middleware",
        summary=result.text[:500],
        next_steps=["Add tests", "Update docs"],
    ))

anyio.run(run_agent)
```

See `examples/handoff_example.py` and `examples/task_lock_example.py` for complete runnable demos.

### LangChain / LangGraph Agents

LangChain agents can wrap harness skills as LangChain tools:

```python
from langchain_core.tools import tool
from harness_skills.handoff import HandoffDocument, HandoffProtocol, SearchHints
from harness_skills.task_lock import TaskLock
from harness_skills.gates import run_gates

@tool
def evaluate_quality_gates(config_path: str = "harness.config.yaml") -> str:
    """Run all configured quality gates and return results."""
    results = run_gates(config_path)
    return results.model_dump_json(indent=2)

@tool
def acquire_task_lock(resource: str) -> str:
    """Acquire an advisory lock on a shared resource."""
    lock = TaskLock(resource)
    lock.acquire()
    return f"Lock acquired: {resource}"

@tool
def write_handoff(task_id: str, summary: str, next_steps: list[str]) -> str:
    """Write a structured handoff document for the next agent."""
    doc = HandoffDocument(
        task_id=task_id,
        summary=summary,
        next_steps=next_steps,
    )
    HandoffProtocol.write(doc)
    return f"Handoff written: {task_id}"

# Use in a LangGraph agent
from langgraph.prebuilt import create_react_agent
agent = create_react_agent(model, [evaluate_quality_gates, acquire_task_lock, write_handoff])
```

### Custom Agent Frameworks

For any agent framework, the integration pattern is the same:

**1. Read skill definitions** from `.claude/commands/*.md` — these are plain Markdown files describing what each skill does, when to use it, and step-by-step instructions.

**2. Call Python APIs** from `harness_skills/`:

```python
# Core imports available to any Python agent
from harness_skills.handoff import HandoffDocument, HandoffProtocol, SearchHints
from harness_skills.task_lock import TaskLock, TaskLockProtocol
from harness_skills.boot import boot_instance, BootConfig, IsolationConfig
from harness_skills.performance_hooks import PerformanceTracker
from harness_skills.stale_plan_detector import detect_stale_plan
from harness_skills.error_aggregation import aggregate_errors
from harness_skills.gates import run_gates, GateEvaluator
from harness_skills.logging_config import configure, get_logger, set_trace_id
```

**3. Or invoke via CLI** if your framework prefers shell commands:

```bash
harness evaluate          # Run quality gates
harness status            # Dashboard
harness lint              # Static analysis
harness observe           # Tail structured logs
python harness_tools/handoff.py --task-id <id> --summary "<text>"
python harness_tools/coordinate.py --check-conflicts
python harness_tools/task_lock.py --acquire <resource>
```

**4. For non-Python agents**, read the YAML/JSON coordination files directly:

```
.harness/handoff/<task-id>.json    # Handoff documents
docs/exec-plans/shared-state.yaml  # Cross-agent key-value store
docs/exec-plans/perf-timers.json   # Performance timer state
```

---

## Skills Catalog

### Harness Core Skills (`/harness:*`)

| Skill | Purpose |
|-------|---------|
| `boot` | Boot an agent instance with sandbox isolation |
| `create` | Scaffold a complete harness from a profile |
| `evaluate` | Run all configured quality gates |
| `lint` | Static analysis (ruff + mypy) |
| `observe` | Tail / query structured logs |
| `status` | Live harness status dashboard |
| `update` | Incremental harness updates |
| `context` | Provision minimal agent context for current task |
| `handoff` | Write a `HandoffDocument` and transfer work |
| `resume` | Resume an interrupted plan |
| `shared-state` | Cross-agent key-value store |
| `task-lock` | Advisory mutual exclusion |
| `detect-stale` | Find abandoned or outdated plans |
| `completion-report` | Structured completion report |
| `error-aggregation` | Aggregate and analyse error logs |
| `telemetry` | Aggregate and report metrics |
| `screenshot` | Capture browser screenshots |
| `effectiveness` | Effectiveness metrics dashboard |

### Quality Gate Skills

| Skill | Purpose |
|-------|---------|
| `coverage-gate` | Enforce minimum line/branch coverage |
| `security-check-gate` | CVE and secret scanning |
| `docs-freshness` | Detect stale documentation |
| `performance` | Performance benchmarks |
| `principles-gate` | Enforce golden rules from `principles.yaml` |
| `type-safety-gate` | Type-checking enforcement |
| `regression-gate` | Test suite pass/fail |

### Top-Level Skills

| Skill | Purpose |
|-------|---------|
| `browser-automation` | Playwright setup + `AgentDriver` |
| `ci-pipeline` | GitHub Actions / GitLab CI generation |
| `observability` | Vector / Loki / Grafana stack |
| `check-code` | Module boundary violation scan |
| `coordinate` | Multi-agent conflict dashboard |
| `create-spec` | XML project specification |
| `define-principles` | Golden rules management |
| `logging-convention` | Structured logging spec generator |
| `review-pr` | Pull request review |

See [docs/agents/skills.md](docs/agents/skills.md) for the full catalog with invocation patterns.

---

## Multi-Agent Coordination

Four file-based mechanisms enable agents to work in parallel safely — no central server required:

| Mechanism | Module | Use When |
|-----------|--------|----------|
| **Handoff** | `harness_skills.handoff` | Passing work between agent sessions |
| **Task Lock** | `harness_skills.task_lock` | Exclusive access to shared resources |
| **Shared State** | `docs/exec-plans/shared-state.yaml` | Cross-agent read/write key-value store |
| **Stale Plan Detection** | `harness_skills.stale_plan_detector` | Finding abandoned plans |

```python
# Handoff: agent A writes, agent B reads
from harness_skills.handoff import HandoffDocument, HandoffProtocol
HandoffProtocol.write(HandoffDocument(task_id="feat-1", summary="Done.", next_steps=["Test"]))
doc = HandoffProtocol.read("feat-1")

# Task Lock: mutual exclusion across processes
from harness_skills.task_lock import TaskLock
with TaskLock("database-migration"):
    run_dangerous_operation()

# Shared State: publish results for other agents
from harness_skills.shared_state import publish, query
publish("agent-a", "discovered_endpoints", ["/api/users", "/api/auth"])
results = query("discovered_endpoints")
```

See [docs/agents/coordination.md](docs/agents/coordination.md) for detailed patterns.

---

## Quality Gates

Quality gates run automated checks before work is marked complete. Configure them in `harness.config.yaml`:

```yaml
active_profile: starter    # starter | standard | advanced

profiles:
  starter:
    gates:
      regression:    { enabled: true, fail_on_error: true }
      coverage:      { enabled: true, threshold: 80 }
      docs_freshness: { enabled: true }
  standard:
    # Adds: security, type-safety, principles, architecture
  advanced:
    # All gates + OpenTelemetry + multi-agent coordination
```

Run gates: `harness evaluate` or `/harness:evaluate`

See [docs/agents/gates.md](docs/agents/gates.md) for gate configuration details.

---

## Project Structure

```
agent-harness-skills/
├── .claude/commands/          # 42 skill commands (Markdown slash-commands)
│   ├── harness/               #   31 harness-specific skills
│   └── *.md                   #   11 top-level skills
├── skills/                    # Skill implementations (SKILL.md + Python)
│   ├── boot/
│   ├── shared-state/
│   ├── context-handoff/
│   ├── perf-hooks/
│   └── ...
├── harness_skills/            # Core framework (Python package)
│   ├── cli/                   #   `harness` CLI entry point
│   ├── gates/                 #   Quality gate runners
│   ├── models/                #   Pydantic response models
│   ├── generators/            #   Artifact generators
│   ├── plugins/               #   Custom YAML-driven gate plugins
│   └── *.py                   #   Handoff, task lock, boot, logging, etc.
├── harness_tools/             # Orchestration CLI wrappers
├── harness_dashboard/         # Effectiveness scoring + terminal dashboard
├── dom_snapshot_utility/      # Browser-free DOM inspection
├── log_format_linter/         # Structured-log linter
├── examples/                  # Runnable SDK demos
├── docs/                      # Architecture, principles, guides
│   ├── agents/                #   Agent-facing documentation
│   ├── guides/                #   Design guidelines
│   └── exec-plans/            #   Runtime state + shared state
├── spec/                      # Project XML/text specs
├── tests/                     # pytest + pytest-playwright
├── claw-forge.yaml            # Model providers, skills, state config
├── harness.config.yaml        # Quality gate profiles
├── AGENTS.md                  # Agent-facing reference
└── CLAUDE.md                  # Claude Code project instructions
```

---

## Configuration

### `claw-forge.yaml` — Agent & Provider Config

Controls model aliases, provider pool, skill injection, and state service:

```yaml
model_aliases:
  opus:   claude-opus-4-6
  sonnet: claude-sonnet-4-6

providers:
  claude-oauth:    { type: anthropic_oauth, priority: 1 }
  anthropic-direct: { type: anthropic, priority: 2 }
  # local-ollama:  { type: ollama, model: qwen2.5:32b }

agent:
  default_model: claude-sonnet-4-6
  max_concurrent_agents: 5

skills: [pyright, systematic-debug, git-workflow, perf-hooks]
```

### `harness.config.yaml` — Quality Gate Profiles

Three maturity levels: **starter** (essential gates), **standard** (+ security, type-safety), **advanced** (full suite + telemetry).

### `.env` — API Keys

```bash
ANTHROPIC_OAUTH_TOKEN=...   # From `claude setup-token`
ANTHROPIC_API_KEY=...       # Direct API access
```

---

## Examples

Runnable demos in `examples/`:

| Example | What It Demonstrates |
|---------|---------------------|
| [`handoff_example.py`](examples/handoff_example.py) | Full context handoff lifecycle (agent A writes, agent B reads) |
| [`task_lock_example.py`](examples/task_lock_example.py) | Cross-process mutual exclusion with TTL |
| [`context_handoff_example.py`](examples/context_handoff_example.py) | Session resumption with search hints |
| [`performance_hooks_example.py`](examples/performance_hooks_example.py) | Performance measurement across agent steps |

```bash
# Run any example
uv pip install -e .
python examples/handoff_example.py
```

---

## Further Reading

- **[Agent Tool Design Guidelines](docs/guides/agent-tool-design-guidelines.md)** — 10 principles for building tools agents use reliably
- **[Architecture](docs/ARCHITECTURE.md)** — Domain map, dependency graph, layer analysis
- **[Principles](docs/PRINCIPLES.md)** — 63 mechanical rules for agent code quality
- **[Skills Catalog](docs/agents/skills.md)** — Full catalog with invocation patterns
- **[Coordination Patterns](docs/agents/coordination.md)** — Multi-agent handoff, locking, shared state
- **[Quality Gates](docs/agents/gates.md)** — Gate configuration and custom plugins

---

## Contributing

1. Read the [design guidelines](docs/guides/agent-tool-design-guidelines.md) before adding or changing skills.
2. Skills go in `.claude/commands/` (Markdown) with implementations in `skills/` or `harness_skills/`.
3. Every skill needs a `SKILL.md` with frontmatter (`name`, `description`, trigger keywords).
4. Run `harness evaluate` before submitting — all gates must pass.
5. See repository settings for license.
