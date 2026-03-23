# Agent Harness Skills

**Documentation and guidelines for AI agent tool design and agent-harness configuration.**

This repository contains practical guidelines for designing tools and skills that AI agents use reliably—synthesized from real-world experience building production agent systems.

## Contents

- **[Agent Tool Design Guidelines](docs/agent_tool_desig_guidelines.md)** — Principles for shaping tools to model abilities, progressive disclosure, tool lifecycle, subagent coordination, and validation.
- **`spec/`** — Project XML/text specs (`app_spec.txt`, logging convention source, etc.).
- **`examples/`** — Runnable agent SDK demos (handoff, task lock, performance hooks).
- **`harness_tools/`** — Orchestration CLIs and SDK demos; repo root exposes thin `*.py` shims with the same names.
- **claw-forge** — Agent harness configuration (model aliases, skills, state, git workflow).

## Highlights

- **Structured tools over free-form output** — Schema-enforce correctness; tool-enforce format.
- **Progressive disclosure** — Minimum viable context first; let the agent pull depth on demand.
- **Tool lifecycle** — Provision, validate, evolve, and retire tools as model capabilities change.
- **Multi-agent readiness** — Design state primitives for coordination from day one.

## Quick Start

1. Copy `.env.example` to `.env` and configure your keys.
2. See `claw-forge.yaml` for model providers, skills, and state settings.
3. Read the [design guidelines](docs/agent_tool_desig_guidelines.md) before adding or changing tools/skills.

## License

See repository settings. Contributions welcome.
