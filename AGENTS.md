# AGENTS.md — agent-harness-skills

<!-- harness:auto-generated — do not edit this block manually -->
last_updated: 2026-03-23
head: 157af7b
service: agent-harness-skills
<!-- /harness:auto-generated -->

Agent-facing entry point.  **Load only the section you need** — every heading links to a
dedicated doc that links to still-deeper references.  Avoid loading everything upfront.

---

## What This Repo Is

`agent-harness-skills` is a Python 3.12 framework (`harness_skills`) that ships:

- **Evaluation gates** — coverage, security, docs-freshness, performance, principles
- **Structured logging** — NDJSON format enforced by `log_format_linter`
- **Multi-agent coordination** — handoff, task locking, shared state, stale-plan detection
- **Browser automation** — Playwright-based `AgentDriver` + headless DOM snapshots
- **CLI tooling** — `harness create / evaluate / lint / observe / status`

---

## Domain Docs — Load On Demand

| Task | Domain doc |
|------|------------|
| Run `harness` CLI commands | [docs/agents/cli-commands.md](docs/agents/cli-commands.md) |
| Evaluate code quality / read gate results | [docs/agents/gates.md](docs/agents/gates.md) |
| Coordinate agents (handoff, locks, shared state) | [docs/agents/coordination.md](docs/agents/coordination.md) |
| Browser automation & DOM snapshots | [docs/agents/browser.md](docs/agents/browser.md) |
| Structured logging & observability | [docs/agents/logging.md](docs/agents/logging.md) |
| Skills catalog (34 skills) | [docs/agents/skills.md](docs/agents/skills.md) |

---

## Hard Invariants

1. **Module imports** — always import from the package root, never from sub-modules.
   `from harness_skills.gates import CoverageGate` ✅
   `from harness_skills.gates.coverage import CoverageGate` ❌
   Rules `MB001–MB014` in `.claude/principles.yaml` are **blocking**.

2. **Log format** — every entry must carry five fields: `timestamp`, `level`, `domain`,
   `trace_id`, `message` (one JSON object per line, NDJSON).

3. **Gate violations** use `rule_id: namespace/kebab-slug` format (e.g. `coverage/line-rate`).

4. **State service** lives at `http://localhost:8888`.  PATCH `/features/{id}` with
   `status=done` when a task completes; POST `/features/{id}/human-input` to request input.

---

## Tests

```bash
pytest tests/ -v                     # all tests
pytest tests/browser/ -v             # e2e browser tests only
pytest tests/browser/ --headed       # headed mode — shows browser window
BASE_URL=https://staging.example.com pytest tests/browser/ -v
```

---

## Architecture Deep-Dive

Full domain map, dependency graph, and open boundary violations:
→ [ARCHITECTURE.md](ARCHITECTURE.md)
