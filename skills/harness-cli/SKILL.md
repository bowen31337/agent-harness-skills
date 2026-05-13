---
name: harness-cli
description: "Drive the `harness` Python CLI — the agent-harness-skills toolkit that generates per-project harness configs, runs quality gates, manages execution plans, boots isolated app instances, and emits structured telemetry. Use whenever the user (or another agent) asks to scaffold/refresh harness artifacts, gate a worktree's code against architecture or principles rules, plan or resume a multi-step task, boot an isolated server for an agent worktree, capture screenshots or logs, search the symbol index, or chain any of the above into one invocation with `--then`. Triggers on: harness create, harness lint, harness evaluate, harness plan, harness resume, harness status, harness boot, harness observe, harness screenshot, harness search, harness coordinate, harness audit, harness manifest, harness telemetry, harness completion-report, harness context, harness update, run a harness command, agent harness, agent-harness-skills, quality gate, exec plan, worktree boot, --then pipeline."
license: See repository LICENSE
compatibility: Requires Python 3.12+, `uv` (recommended), and the `harness` script on $PATH. Install via `uv tool install agent-harness-skills`.
metadata:
  source: https://github.com/<repo>/agent-harness-skills
  version: "0.1.0"
  cli-entry-point: "harness_skills.cli.main:cli"
---

# harness-cli

A thin agent-facing guide for the `harness` CLI shipped by the
`agent-harness-skills` package. The CLI exposes **17 subcommands** in six
categories and supports `--then` pipeline composition for single-invocation
workflows.

> The detailed per-command reference lives in [`references/COMMANDS.md`](references/COMMANDS.md).
> Pipeline recipes live in [`references/PIPELINES.md`](references/PIPELINES.md).
> Output format conventions live in [`references/OUTPUT-FORMATS.md`](references/OUTPUT-FORMATS.md).

---

## Installation

```bash
# uv is the canonical installer
curl -LsSf https://astral.sh/uv/install.sh | sh   # if not already installed
uv tool install agent-harness-skills

harness --help        # confirm install
harness --version
```

The package registers a `harness` script via `[project.scripts]` in
`pyproject.toml` (`harness = "harness_skills.cli.main:cli"`). Python 3.12+ is
required; `uv` will provision a suitable interpreter automatically.

---

## Command map

Pick the category that matches the task, then open
[`references/COMMANDS.md`](references/COMMANDS.md) for the specific subcommand's
flags and outputs.

| Category | Commands | Use for |
|---|---|---|
| **Generation & Configuration** | `create`, `update`, `manifest` | First-time setup, re-scanning the repo, validating `harness_manifest.json` |
| **Quality Gates** | `lint`, `evaluate`, `audit` | Running architecture/principles checks, full gate suite, artifact-freshness checks |
| **Execution Plans** | `plan`, `status`, `resume`, `completion-report`, `context` | Authoring a plan, viewing the dashboard, handoff between agents, context provisioning |
| **Observability** | `boot`, `observe`, `screenshot` | Booting an isolated instance, tailing structured logs, capturing visual artifacts |
| **Coordination** | `search`, `coordinate`, `telemetry` | Symbol / artifact lookup, cross-agent conflict detection, usage analytics |

If you can't tell which command to reach for, run `harness --help` and skim
the one-line summaries — every subcommand also has its own `harness <cmd> --help`.

---

## Choosing the right entry point

Use this decision flow before invoking anything. Most failures come from
running the wrong subcommand, not from flag mistakes.

1. **No `harness.config.yaml` or `harness_manifest.json` in the repo?**
   → Start with `harness create`. This bootstraps the configuration and
   generates initial artifacts.
2. **Config exists, code has drifted?**
   → `harness update` performs a three-way merge so hand-edits are preserved.
3. **About to claim work is done?**
   → `harness evaluate` runs the full gate suite. For a single targeted gate
   use `harness lint --gate <name>`.
4. **Working through a multi-step task?**
   → `harness plan` writes the plan, `harness status` shows progress,
   `harness resume` rehydrates state when an agent hands off, and
   `harness completion-report` aggregates final status.
5. **Need an isolated server for an agent worktree?**
   → `harness boot` (per-worktree port + optional DB isolation + health check).
6. **Need to look something up across the codebase?**
   → `harness search` (uses the indexed symbol table; faster than `grep`
   for symbol-shaped queries).

---

## Pipeline composition with `--then`

Any subcommand chain can be expressed as a single invocation:

```bash
# scaffold, then gate, then run all evaluations
harness create --then lint --then evaluate

# per-stage flags work as expected
harness create --profile standard --then lint --gate architecture
```

Semantics:

- Stages run in order; a non-zero exit code aborts the remainder.
- A trailing `--then` with no following token is silently dropped (safe to
  programmatically build).
- The exit code of the last successful stage is returned.

More chains in [`references/PIPELINES.md`](references/PIPELINES.md).

---

## Output formats

Most commands accept `--format json|yaml|table`:

- `table` is the default for **interactive** shells (TTY).
- `json` is the default when stdout is **not** a TTY — so CI captures
  structured output automatically.
- Pass `--format json` explicitly whenever you intend to parse the result
  programmatically; do not rely on TTY detection from inside a subagent.

See [`references/OUTPUT-FORMATS.md`](references/OUTPUT-FORMATS.md) for the
schema of each command's JSON payload.

---

## Operating principles for agents

These keep invocations cheap and predictable:

- **Always prefer `--format json` in subagents.** Table output is decorative
  and brittle to parse.
- **Run `harness evaluate` before declaring a task done.** It is the
  canonical "are the gates green?" check.
- **Use `--then` rather than spawning multiple shells.** It preserves
  configuration discovery and produces a single audit trail.
- **Treat the exit code as ground truth.** Non-zero means the gate / step
  failed; do not paper over it with text inspection.
- **Do not edit `harness_manifest.json` by hand.** Regenerate it with
  `harness manifest` or `harness update` — hand edits are blown away on
  the next scan.

---

## When this skill does *not* apply

- The user is asking about a *different* tool whose binary is also called
  `harness` (e.g. Drone Harness CI, Cypress harness mode). Confirm the
  context before triggering — the package name `agent-harness-skills` and
  the `claude-agent-sdk` dependency are reliable disambiguators.
- The user wants to *write* a new skill, not run the CLI. Use the
  `skill-creator` skill instead.
- The user wants to drive the harness via its **Python API** rather than
  the CLI. The CLI is a thin wrapper; importing `harness_skills` directly
  is fine but out of scope for this skill — point them at
  `harness_skills/cli/<command>.py` to see how each command is wired.

---

## Quick reference card

```bash
# bootstrap a new project
harness create

# refresh after code changes
harness update

# gate the worktree
harness lint --gate architecture --format json
harness evaluate --format json

# plan + resume an agent task
harness plan --task "Refactor auth middleware"
harness status
harness resume --task-id <id>

# boot an isolated instance
harness boot --port 8888 --health /healthz

# observability
harness observe --tail
harness screenshot --url http://localhost:8888

# composition
harness create --then lint --then evaluate
```

For every other detail, open the reference files alongside this skill.
