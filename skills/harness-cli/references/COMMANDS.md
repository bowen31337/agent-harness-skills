# Command Reference

Agent-tuned summary of all 17 `harness` subcommands. For exhaustive flag lists,
the canonical reference is `docs/cli/<command>.md` in the
`agent-harness-skills` repository.

Each section follows the same shape:

- **Purpose** — one sentence the agent can match against the task.
- **Synopsis** — most useful invocation.
- **Key flags** — the flags an agent will actually need.
- **Output** — what to expect on stdout / disk / exit code.

---

## Generation & Configuration

### `harness create`
- **Purpose**: Initialize (or update the `gates:` block of) `harness.config.yaml`, plus stack-specific scaffolding.
- **Synopsis**: `harness create --profile {starter|standard|advanced} [--stack {python|node|go}] [--dry-run]`
- **Key flags**:
  - `--profile` — gate strictness (`starter` is the safe default).
  - `--dry-run` — print YAML to stdout, write nothing.
  - `--no-merge` — overwrite existing config (destructive).
- **Output**: writes `harness.config.yaml`; report on stdout (`--format text|json`).

### `harness update`
- **Purpose**: Re-scan the repo and refresh generated artifacts using a three-way merge so hand-edits survive.
- **Synopsis**: `harness update [--dry-run]`
- **Output**: updated artifacts in-place; summary of what changed.

### `harness manifest`
- **Purpose**: Generate or validate `harness_manifest.json` (the canonical inventory of skills, gates, and artifacts).
- **Synopsis**: `harness manifest [--validate]`
- **Output**: rewritten `harness_manifest.json` (or validation report).

---

## Quality Gates

### `harness lint`
- **Purpose**: Run targeted lint-style checks (architecture rules, principles, naming, etc.).
- **Synopsis**: `harness lint [--gate <name>] [--format json]`
- **Key flags**:
  - `--gate <name>` — run only one gate (repeatable).
- **Output**: gate report; non-zero exit on failure.

### `harness evaluate`
- **Purpose**: Run **every** enabled gate and emit one structured pass/fail report. The canonical "is this done?" check.
- **Synopsis**: `harness evaluate [--gate <name>...] [--format json|yaml|table]`
- **Key flags**:
  - `--gate <name>` — restrict to specific gates (repeatable).
  - `--coverage-threshold <float>` — overrides config.
  - `--max-staleness-days <int>` — docs-freshness gate threshold.
- **Output**: `EvaluateResponse` JSON (conforms to `evaluation_report.schema.json`).
- **Exit codes**: `0` clean, `1` gate failures, `2` harness error.

### `harness audit`
- **Purpose**: Check artifact freshness (generated docs, manifests, symbol index).
- **Synopsis**: `harness audit [--max-age-days <int>] [--format json]`
- **Output**: list of stale artifacts with last-modified timestamps.

---

## Execution Plans

### `harness plan`
- **Purpose**: Create a new execution plan from a free-form description.
- **Synopsis**: `harness plan "<description>" [--plan-id PLAN-XXX] [--title "..."] [--output-format yaml|json]`
- **Output**: `docs/exec-plans/PLAN-<id>.{yaml,json}`.

### `harness status`
- **Purpose**: Live dashboard of plan progress + gate state.
- **Synopsis**: `harness status [--plan-id PLAN-XXX] [--format json|table]`
- **Output**: progress table or JSON; never mutates state.

### `harness resume`
- **Purpose**: Rehydrate plan state for an incoming agent (context handoff).
- **Synopsis**: `harness resume --task-id <id>` or `harness resume --plan-id PLAN-XXX`
- **Output**: the prior agent's context bundle (prompt, files, decisions) as JSON.

### `harness completion-report`
- **Purpose**: Aggregate plan completion status for a post-mortem.
- **Synopsis**: `harness completion-report --plan-id PLAN-XXX [--format json|markdown]`
- **Output**: per-task pass/fail + summary.

### `harness context`
- **Purpose**: Provision the file/symbol context for the current task (depth-mapped scoping).
- **Synopsis**: `harness context <plan-or-task-id> [--depth-map]`
- **Output**: list of relevant files + symbol summaries.

---

## Observability

### `harness boot`
- **Purpose**: Launch an isolated application instance for an agent worktree (dedicated port + optional DB isolation + health check).
- **Synopsis**: `harness boot [--port <int>] [--health <path>] [--isolate-db]`
- **Output**: backgrounded server process; healthy-when-ready signal.

### `harness observe`
- **Purpose**: Tail structured logs from a running harness instance.
- **Synopsis**: `harness observe [--tail] [--filter <ndjson-jq>]`
- **Output**: NDJSON log stream.

### `harness screenshot`
- **Purpose**: Capture visual artifacts (full page, viewport, element) via Playwright.
- **Synopsis**: `harness screenshot --url <url> [--out <path>] [--selector <css>]`
- **Output**: PNG file path on stdout.

---

## Coordination

### `harness search`
- **Purpose**: Look up symbols / artifacts in the pre-built index. Faster than `grep` for symbol-shaped queries.
- **Synopsis**: `harness search <query> [--kind {symbol|file|gate}] [--format json]`
- **Output**: matching records with file:line.

### `harness coordinate`
- **Purpose**: Cross-agent conflict detection — surface tasks where two agents are touching the same files.
- **Synopsis**: `harness coordinate [--format json]`
- **Output**: conflict graph + recommended sequencing.

### `harness telemetry`
- **Purpose**: Usage analytics for the harness itself (which gates run, time per gate, failure rates).
- **Synopsis**: `harness telemetry [--window <duration>] [--format json]`
- **Output**: rollup JSON; suitable for dashboarding.

---

## See also

- Repo-level docs: `docs/cli/<command>.md` (canonical, kept in sync with source).
- Pipeline composition: [`PIPELINES.md`](PIPELINES.md).
- Output schema details: [`OUTPUT-FORMATS.md`](OUTPUT-FORMATS.md).
