# PRINCIPLES.md
> Mechanical rules for AI agents operating inside the claw-forge agent harness.
> Each rule is stated as a short imperative, followed by its rationale and a concrete example.

---

## 1. Task Lifecycle Rules

### 1.1 Read task context before taking any action

**Rationale:** Acting on incomplete information wastes compute, produces incorrect output, and can corrupt shared state that other agents depend on.

**Example:**
- DO: Read the task spec from the state service (`GET /features/{id}`), confirm the scope, then begin work.
- DON'T: Start writing code the moment a task ID appears in the prompt.

---

### 1.2 Report task complete via PATCH /features/{id} with status=done

**Rationale:** The state service at `http://localhost:8888` is the single source of truth for task progress. Completing work without reporting it leaves the orchestrator blind, may cause the task to be re-queued, and blocks downstream tasks.

**Example:**
- DO:
  ```bash
  curl -s -X PATCH http://localhost:8888/features/feat-42 \
    -H "Content-Type: application/json" \
    -d '{"status": "done"}'
  ```
- DON'T: Finish the work and simply end the conversation without reporting status.

---

### 1.3 Update task status to "in_progress" when starting non-trivial work

**Rationale:** Long-running tasks should signal that work has begun so the orchestrator and other agents do not assume the task is idle or re-assign it.

**Example:**
- DO: PATCH status to `in_progress` before beginning multi-step operations (file generation, API calls, test runs).
- DON'T: Leave status as `pending` while actively working — this creates invisible concurrency conflicts.

---

### 1.4 Never mark a task done until all acceptance criteria are verifiably met

**Rationale:** Premature completion signals corrupt the task graph and give false confidence to downstream agents or humans monitoring progress.

**Example:**
- DO: Run tests, confirm file changes are saved, verify the state service accepted the PATCH, then report done.
- DON'T: PATCH `status=done` immediately after writing code without verifying it compiles or passes tests.

---

### 1.5 Create a checkpoint before any risky or irreversible operation

**Rationale:** Checkpoints (git commit + state snapshot) provide a safe rollback point. Risky operations include schema migrations, dependency upgrades, and provider changes.

**Example:**
- DO: Run `/checkpoint` before upgrading a dependency or changing a state schema.
- DON'T: Run a destructive migration without first committing the current state.

---

## 2. Human Input Rules

### 2.1 Request human input only when genuinely blocked

**Rationale:** Unnecessary interruptions erode trust and slow delivery. Agents that escalate too readily become a burden rather than an asset.

**Example:**
- DO: `POST /features/{id}/human-input` when a required secret is missing, an ambiguous spec has no safe default, or a decision has irreversible consequences.
- DON'T: Pause to ask a human "which file should I edit?" when the task spec names the file explicitly.

---

### 2.2 Prefer autonomous resolution for well-scoped ambiguity

**Rationale:** If the task spec is clear enough that a reasonable interpretation exists, act on it and document the assumption in the task notes. This keeps velocity high.

**Example:**
- DO: Pick the more conservative option (e.g., non-destructive read over destructive write), document the assumption, and proceed.
- DON'T: Block on a question like "should I use tabs or spaces?" — defer to the existing codebase style.

---

### 2.3 When requesting human input, include full context in the request payload

**Rationale:** Humans reviewing agent requests may not have the task in memory. Under-specified requests cause back-and-forth that is worse than the original interruption.

**Example:**
- DO:
  ```json
  {
    "question": "The API key for service X is missing from the environment. Should I use the staging key in .env.example, or pause until production credentials are provided?",
    "context": "Task feat-42 requires calling service X to complete step 3.",
    "options": ["use staging key", "pause"]
  }
  ```
- DON'T: `POST /features/feat-42/human-input` with body `{"question": "what key?"}`.

---

### 2.4 Never fabricate credentials or fill in secrets autonomously

**Rationale:** Guessing or inventing API keys, passwords, or tokens can cause silent failures, security incidents, or charges against the wrong account. This is a human decision.

**Example:**
- DO: Detect the missing credential, request human input, and halt that sub-task until the response arrives.
- DON'T: Set `API_KEY=placeholder` and proceed, hoping the next step will catch it.

---

## 3. File System Rules

### 3.1 Read a file before editing it

**Rationale:** Editing without reading risks overwriting content you did not intend to change. It also ensures your edit targets the correct line numbers and context.

**Example:**
- DO: Use the Read tool to load the file, then use Edit with the exact old string as it appears in the file.
- DON'T: Use Write to overwrite a file you have not read in the current session.

---

### 3.2 Prefer Edit over Write for existing files

**Rationale:** Edit sends only the diff. Write sends the entire file content, which is slower, more error-prone, and risks losing file content if the model's version of the file is stale.

**Example:**
- DO: Use Edit to change a specific function in a 500-line file.
- DON'T: Use Write to re-emit all 500 lines with one small change.

---

### 3.3 Never create files unless they are required to complete the task

**Rationale:** Unnecessary files accumulate as noise in the repository and may conflict with existing structure. They increase review burden and can trigger unintended tooling (linters, build systems).

**Example:**
- DO: Edit `README.md` if you need to update documentation.
- DON'T: Create `README_NEW.md` alongside the existing one.

---

### 3.4 Never create documentation files (*.md) unless explicitly requested

**Rationale:** Auto-generated docs that nobody asked for are rarely accurate, often redundant, and pollute the repository. This file (PRINCIPLES.md) is an exception because it was explicitly requested.

**Example:**
- DO: Create `PRINCIPLES.md` when the task spec says "generate PRINCIPLES.md".
- DON'T: Create `ARCHITECTURE.md` as a side-effect of reading the codebase during an unrelated task.

---

### 3.5 Use absolute file paths in all tool calls

**Rationale:** The working directory resets between Bash invocations. Relative paths silently resolve to wrong locations, causing reads and writes to fail or corrupt the wrong file.

**Example:**
- DO: `/Users/bowenli/projects/claw-forge-test/agent-harness-skills/src/main.py`
- DON'T: `src/main.py` or `./src/main.py`

---

### 3.6 Write temporary files to $TMPDIR, never to /tmp directly

**Rationale:** The sandbox restricts `/tmp` directly. `$TMPDIR` resolves to the correct sandbox-writable path (`/private/tmp/claude-501/`). Using `/tmp` directly will cause permission errors.

**Example:**
- DO: `$TMPDIR/my-scratch-file.json`
- DON'T: `/tmp/my-scratch-file.json`

---

## 4. Git & Version Control Rules

### 4.1 Create new commits rather than amending unless explicitly instructed

**Rationale:** Amending rewrites history. If a pre-commit hook fails, the previous commit is already committed — `--amend` would corrupt it. Creating a new commit is always safe.

**Example:**
- DO: After a hook failure, fix the issue, re-stage, and `git commit` with a new message.
- DON'T: Run `git commit --amend` after a hook failure — the previous commit is intact and should not be changed.

---

### 4.2 Never force-push to main or master

**Rationale:** Force-pushing to protected branches rewrites shared history, breaks other agents' and developers' local branches, and can permanently destroy commits.

**Example:**
- DO: Create a feature branch, push there, and open a PR.
- DON'T: `git push --force origin main` under any circumstances. Warn the user if they request it.

---

### 4.3 Never skip pre-commit hooks

**Rationale:** Hooks enforce code quality gates (linting, tests, secret scanning). Bypassing them with `--no-verify` lets broken or insecure code enter the repository silently.

**Example:**
- DO: If a hook fails, investigate and fix the underlying issue, then commit again.
- DON'T: `git commit --no-verify` to work around a failing lint check.

---

### 4.4 Stage specific files by name; avoid git add -A

**Rationale:** `git add -A` can accidentally stage sensitive files (`.env`, credential dumps, large binaries) that should never be committed.

**Example:**
- DO: `git add src/feature.py tests/test_feature.py`
- DON'T: `git add -A` or `git add .` unless you have confirmed every changed file is safe to commit.

---

### 4.5 Pass commit messages via HEREDOC to ensure correct formatting

**Rationale:** Inline `-m` strings truncate at shell special characters and make multi-line messages error-prone. HEREDOC is reliable.

**Example:**
- DO:
  ```bash
  git commit -m "$(cat <<'EOF'
  feat: add feature X

  Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
  EOF
  )"
  ```
- DON'T: `git commit -m "feat: add feature X\n\nCo-Authored-By: ..."`

---

### 4.6 Never run destructive git operations without explicit instruction

**Rationale:** Commands like `git reset --hard`, `git checkout .`, `git clean -f`, and `git branch -D` destroy work that may not be recoverable. They must only execute when the user explicitly requests them.

**Example:**
- DO: Ask the user to confirm before running `git reset --hard origin/main`.
- DON'T: Run `git checkout .` to "clean up" the working directory as part of routine task work.

---

## 5. Tool Usage Rules

### 5.1 Make independent tool calls in parallel

**Rationale:** Sequential tool calls for independent operations waste wall-clock time. Parallel calls complete in the time of the slowest single call.

**Example:**
- DO: Issue `git status`, `git diff`, and `git log` in a single message as three parallel Bash calls.
- DON'T: Wait for `git status` to complete before issuing `git diff`.

---

### 5.2 Prefer dedicated tools over Bash equivalents

**Rationale:** Dedicated tools (Read, Grep, Glob, Edit, Write) are sandboxed correctly, provide better permission handling, and produce structured output the agent can reason about. Bash commands for the same purpose are more error-prone and harder to audit.

**Example:**
- DO: Use the Grep tool to search for a pattern across files.
- DON'T: `grep -r "pattern" .` via the Bash tool unless the Grep tool cannot accomplish the task.

---

### 5.3 Load deferred tools via ToolSearch before calling them

**Rationale:** Deferred tools are not available until discovered via ToolSearch. Calling a deferred tool without loading it first will fail silently or raise an error.

**Example:**
- DO: Call `ToolSearch` with `query: "select:NotebookEdit"` before using `NotebookEdit`.
- DON'T: Call `NotebookEdit` directly without first discovering it via ToolSearch.

---

### 5.4 Respect sandbox filesystem restrictions

**Rationale:** The sandbox enforces an allowlist of writable paths. Writes outside the allowlist fail. Understanding the sandbox prevents wasted attempts and confusing errors.

**Example:**
- DO: Write output files to the current project directory or `$TMPDIR`.
- DON'T: Attempt to write to `/etc`, `/usr`, or any path outside the sandbox allowlist.

---

### 5.5 Never use interactive git flags (-i) in Bash

**Rationale:** Interactive flags (e.g., `git rebase -i`, `git add -i`) require a TTY and user input that the agent cannot provide. They will hang or error.

**Example:**
- DO: `git rebase origin/main` (non-interactive).
- DON'T: `git rebase -i HEAD~3`.

---

## 6. Communication Rules

### 6.1 Respond with the minimum necessary information

**Rationale:** Verbose output obscures key findings, increases token cost, and makes it harder for humans or orchestrators to parse results. Brevity signals confidence.

**Example:**
- DO: "Tests pass. 3 files changed. PR created: https://github.com/org/repo/pull/42"
- DON'T: Summarize every file you read, every command you ran, and every decision you considered before stating the result.

---

### 6.2 Never fabricate information — cite sources or admit uncertainty

**Rationale:** Hallucinated facts, file paths, or API responses corrupt downstream decisions and erode trust. If you do not know something, say so explicitly.

**Example:**
- DO: "I could not find a claw-forge.yaml in the repository root. The config location is unknown."
- DON'T: "The claw-forge.yaml is at `/config/claw-forge.yaml`." (when you have not verified this)

---

### 6.3 Report absolute file paths in final responses

**Rationale:** Relative paths are ambiguous to humans and other agents who may be operating from a different working directory. Absolute paths are unambiguous.

**Example:**
- DO: `/Users/bowenli/projects/claw-forge-test/agent-harness-skills/src/main.py`
- DON'T: `src/main.py`

---

### 6.4 Do not use emojis in output unless explicitly requested

**Rationale:** Emojis add visual noise without informational value in most agent communication contexts. They can also render incorrectly in some terminals and log systems.

**Example:**
- DO: "Task complete. Status reported to state service."
- DON'T: "Task complete! Status reported to state service."

---

## 7. Code Quality Rules

### 7.1 Run linters and type checkers before marking a coding task done

**Rationale:** Undetected lint or type errors become technical debt that the next agent or developer must fix. Catching them at the source is always cheaper.

**Example:**
- DO: Run `uv run ruff check .` and `uv run mypy .` before reporting a coding task complete.
- DON'T: Ship code without checking it because "it looks right."

---

### 7.2 Run tests before marking a coding task done

**Rationale:** Code that passes static analysis can still have behavioral bugs. Tests are the only reliable signal that the feature works as specified.

**Example:**
- DO: `uv run pytest tests/ -q` and confirm all relevant tests pass.
- DON'T: Skip tests because "I only changed one line."

---

### 7.3 Never commit secrets, credentials, or API keys

**Rationale:** Once a secret is in git history it is effectively public — even after deletion, it lives in clones and git reflog. Credential exposure can cause security incidents and financial damage.

**Example:**
- DO: Store secrets in environment variables or a secrets manager; reference them by name in code.
- DON'T: `API_KEY = "sk-abc123..."` hardcoded in source files.

---

### 7.4 Use the existing codebase's style and patterns for new code

**Rationale:** Consistent code is easier to review, maintain, and extend. Style divergence creates cognitive overhead for every future reader.

**Example:**
- DO: If the codebase uses `async/await` for I/O, write new I/O functions the same way.
- DON'T: Introduce synchronous blocking calls in an async codebase because it's "simpler."

---

## 8. Safety & Security Rules

### 8.1 Never expose credentials in any output, log, or commit

**Rationale:** Credentials in logs, STDOUT, or commits are visible to anyone with access to those artifacts. A secret that touches an output surface should be considered compromised.

**Example:**
- DO: Log `"Using API key: sk-****1234"` (masked) if a log entry is needed for debugging.
- DON'T: `print(f"Connecting with key: {api_key}")` where `api_key` is the full secret value.

---

### 8.2 Prefer non-destructive operations; always prefer reversible over irreversible

**Rationale:** Mistakes happen. An operation that can be undone costs a few minutes. An operation that cannot be undone can cost hours or permanently destroy work.

**Example:**
- DO: Copy a file before modifying it if the modification is high-risk.
- DON'T: Truncate a database table to "reset state" when a soft-delete or archive would work.

---

### 8.3 Validate all externally sourced data before using it

**Rationale:** Data from APIs, user input, or the file system may be malformed, malicious, or stale. Unvalidated external data is the root cause of injection attacks and silent data corruption.

**Example:**
- DO: Parse and validate API responses against an expected schema before passing them to downstream functions.
- DON'T: `eval(user_input)` or `subprocess.run(shell=True, args=user_provided_string)`.

---

### 8.4 Never run `git push --force` to main or master

**Rationale:** This is a separate, explicit rule because the consequences are severe and the action is irreversible on most hosting platforms. It deserves its own entry even though it overlaps with Rule 4.2.

**Example:**
- DO: If force-push is genuinely needed (e.g., removing an accidentally committed secret), escalate to a human via `POST /features/{id}/human-input`.
- DON'T: Execute `git push --force origin main` under any autonomous decision.

---

## 9. Skill Invocation Rules

### 9.1 Check available skills before building custom logic

**Rationale:** Skills in the `.claude/commands/` directory represent pre-tested, approved workflows. Reinventing them wastes time and introduces inconsistency.

**Example:**
- DO: Use `/check-code` to run linting, type checking, and tests rather than assembling the individual commands manually each time.
- DON'T: Write a custom Bash pipeline to run ruff + mypy + pytest when `/check-code` already does this.

---

### 9.2 Invoke a skill via the Skill tool — never by narrating what you would do

**Rationale:** Narrating a skill invocation ("I would run /checkpoint now") does not actually invoke it. The Skill tool must be called to trigger the skill's instructions.

**Example:**
- DO: Call `Skill("checkpoint")` to execute the checkpoint workflow.
- DON'T: Write "Running /checkpoint..." and then manually reproduce the checkpoint steps without calling the Skill tool.

---

### 9.3 Never invoke a skill that is already running in the current turn

**Rationale:** Double-invocation of a skill in the same turn creates duplicate work, duplicate commits, and duplicate state service events.

**Example:**
- DO: If a `<checkpoint>` tag is already present in the current conversation turn, follow its instructions directly.
- DON'T: Call `Skill("checkpoint")` again if the skill has already been loaded and its instructions are visible.

---

### 9.4 Treat skill invocation as a blocking requirement when a slash command is referenced

**Rationale:** When a user or orchestrator references a skill by name (e.g., `/review-pr`, `/create-spec`), they expect that skill's exact workflow to run — not an approximation of it.

**Example:**
- DO: Immediately call `Skill("review-pr")` when the user says `/review-pr 123`.
- DON'T: Begin analyzing the PR diff manually before calling the skill, or skip the skill and improvise.

---

### 9.5 Load deferred skills via ToolSearch before invoking them

**Rationale:** Skills backed by deferred tools require those tools to be loaded first. Invoking a skill whose underlying tool is not yet available will fail.

**Example:**
- DO: Call `ToolSearch(query: "select:EnterWorktree")` before invoking any skill that uses `EnterWorktree`.
- DON'T: Call `EnterWorktree` directly without first verifying it has been loaded.

---

## 10. Plan-to-PR Traceability Rules

> Full convention: `docs/plan-to-pr-convention.md`

### 10.1 Name feature branches with the plan ID prefix

**Rationale:** A branch named `feat/PLAN-001-auth-refresh-token` lets any
agent or reviewer identify the source plan without opening a PR or reading
commit history. It also makes `gh pr list --search` reliable.

**Example:**
- DO: `git checkout -b feat/PLAN-001-auth-refresh-token`
- DON'T: `git checkout -b fix-auth-bug` (no plan reference)

---

### 10.2 Prefix every PR title with `[PLAN-NNN]`

**Rationale:** The bracket prefix is machine-parseable and survives copy/paste.
CI and the harness-evaluate workflow use it to verify traceability without
parsing the PR body.

**Example:**
- DO: `[PLAN-001] Add refresh-token rotation to auth service`
- DON'T: `Add refresh-token rotation` (plan reference missing)

---

### 10.3 Fill in the traceability table in every PR body

**Rationale:** The PR body traceability table (from `.github/pull_request_template.md`)
links the PR to a specific plan file and task list. Without it, the relationship
exists only in the agent's memory — which is not durable.

**Example:**
- DO: Complete the `## Execution Plan` table with Plan ID, plan file path, and
  tasks closed before calling `gh pr create`.
- DON'T: Delete the traceability section or leave placeholder values (`PLAN-XXX`).

---

### 10.4 Include a `Plan: PLAN-NNN` trailer in every commit that belongs to a plan

**Rationale:** `git log --grep="Plan: PLAN-001"` becomes a reliable audit query.
Commit trailers are preserved through rebases and merges, making them more
durable than PR body text.

**Example:**
- DO:
  ```
  feat: rotate refresh tokens on each use

  Plan: PLAN-001
  Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
  ```
- DON'T: Omit the `Plan:` trailer or bury the plan ID in the commit subject only.

---

### 10.5 Update the plan YAML's `linked_prs` field immediately after opening a PR

**Rationale:** The plan file is the canonical record of what was shipped. An
unlinked PR means the plan shows tasks as `done` but the evidence (the PR) is
not recorded. This breaks audit trails and makes the `harness-evaluate` CI
check fail.

**Example:**
- DO: After `gh pr create` returns `https://github.com/org/repo/pull/42`,
  read the plan YAML, append to `linked_prs`, update `updated_at`, and commit
  the updated plan file on the feature branch.
- DON'T: Open the PR and immediately mark the task `done` without writing the
  PR URL back to the plan file.

---

### 10.6 Mark plan tasks `done` only after the PR is open and `linked_prs` is updated

**Rationale:** Marking a task `done` signals to the orchestrator and downstream
tasks that the work is complete and the artefact exists. If the PR is not yet
linked, downstream agents may start work based on a task that has no verifiable
deliverable.

**Example:**
- DO: PR open → `linked_prs` updated → task `lock_status: done` → PATCH state
  service with `status=done`.
- DON'T: Mark the task `done` as soon as the code is written, before the PR
  is created or linked.

---

*Generated for the claw-forge agent harness. State service: http://localhost:8888.*

---

## 11. Module Boundary Rules
> Generated by `/module-boundaries`. IDs MB001–MB014. Last updated: 2026-03-20 (re-run). Re-run `/module-boundaries` to refresh.

10 Python packages scanned. `__all__` has now been declared in all 10 packages.
Open violations (callers that still bypass `__init__` via deep submodule imports) remain
and are listed per-domain in the principles below — migrate them on next touch.

### 11.1 Never bypass a package's `__init__.py` with deep submodule imports (MB001–MB010)

**Rationale:** Importing from internal submodules (`from pkg.internal_module import X`)
couples callers to implementation details, makes refactoring painful, and defeats
the purpose of the package boundary. Every symbol a caller needs must be re-exported
through the package root's `__all__`.

**Status per domain (current, post-fix):**

| Domain | Surface | Open violations |
|--------|---------|-----------------|
| `harness_skills` | ✅ EXPLICIT (`__all__ = []`) | 0 |
| `harness_skills/cli` | ✅ EXPLICIT (`cli`, `PipelineGroup`) | 1 (test imports `_emit`) |
| `harness_skills/gates` | ✅ EXPLICIT (9 public symbols) | 5 (1 deep import + 4 private-symbol tests) |
| `harness_skills/generators` | ✅ EXPLICIT | 7 (cli: evaluate/create/manifest bypasses + 3 test bypasses; manifest/config symbols absent from `__all__`) |
| `harness_skills/models` | ✅ EXPLICIT (gate_configs now included) | ~17 (production + tests) |
| `harness_skills/plugins` | ✅ EXPLICIT | 7 (tests bypass + import `_record_telemetry`) |
| `harness_skills/utils` | ✅ EXPLICIT (`__all__ = []`) | 0 |
| `harness_dashboard` | ✅ EXPLICIT (6 public symbols) | 5 (tests bypass) |
| `dom_snapshot_utility` | ✅ EXPLICIT | 1 (test bypasses) |
| `log_format_linter` | ✅ EXPLICIT | 1 (test bypasses) |

**Example:**
- DO: `from harness_skills.plugins import PluginGateConfig, run_plugin_gates`
- DON'T: `from harness_skills.plugins.gate_plugin import PluginGateConfig` (deep import)
- DON'T: `from harness_skills.plugins.runner import _record_telemetry` (private + deep)

### 11.2 Never import private symbols (`_name`) from outside their defining package (MB002, MB003, MB006)

**Rationale:** A leading underscore signals the symbol is an implementation detail not
subject to the public API contract. Importing it from outside the package creates an
invisible coupling that breaks silently on refactor.

**Open violations:**
- `tests/test_models/test_observe.py:232` — imports `_emit` from `harness_skills.cli.observe`
- `tests/gates/test_coverage.py` — imports `_detect_format`, `_parse_json`, `_parse_lcov`, `_parse_xml`, `_ParseError` from `harness_skills.gates.coverage`
- `tests/gates/test_docs_freshness.py` — imports `_extract_file_refs`, `_looks_like_file_path`, `_parse_generated_at` from `harness_skills.gates.docs_freshness`
- `tests/plugins/test_runner.py:12` — imports `_record_telemetry` from `harness_skills.plugins.runner`

**Example:**
- DO: Refactor tests to exercise behaviour via the public API (`CoverageGate.run()`, etc.).
- DON'T: `from harness_skills.cli.observe import _emit` in a test file.

### 11.3 gate_configs symbols are now part of `harness_skills.models` — use the package root (MB005)

**Rationale:** All `gate_configs` types (`CoverageGateConfig`, `RegressionGateConfig`, etc.)
are now re-exported from `harness_skills/models/__init__.py` and listed in `__all__`.
Callers that still reach into `harness_skills.models.gate_configs` directly must migrate.

**Other open submodule violations in `harness_skills/models` (non-gate_configs):**
- `harness_skills/cli/observe.py:62` — `from harness_skills.models.observe import LogEntry, ObserveResponse`
  → fix: `from harness_skills.models import LogEntry, ObserveResponse`
- `harness_skills/cli/status.py:56-57` — deep into `.models.base` / `.models.status`
- `harness_skills/telemetry_reporter.py:36-37` — deep into `.models.base` / `.models.telemetry`
- `harness_skills/stale_plan_detector.py:52-53` — deep into `.models.base` / `.models.stale`
- `harness_skills/plugins/gate_plugin.py:9`, `harness_skills/plugins/runner.py:4` — deep into `.models.base`
- `harness_skills/gates/runner.py:82` — deep into `.models.base`

**Example:**
- DO: `from harness_skills.models import CoverageGateConfig`
- DON'T: `from harness_skills.models.gate_configs import CoverageGateConfig`

---

### 11.4 Providers Pattern — cross-cutting concerns must flow through designated providers (MB011–MB014)

**Rationale:** Logging, config, and secrets are cross-cutting concerns used by every
domain. Letting each domain call `logging.getLogger()`, open YAML files directly,
or scatter `os.environ.get("API_KEY")` throughout business logic creates invisible
coupling, defeats testability, and makes the security surface impossible to audit.
A *provider* is a single module that owns the bootstrap and exposes a stable API;
all other code is a consumer that receives what it needs through that API.

**Three providers, three rules (see MB011–MB014 in .claude/principles.yaml):**

| Concern | Provider | Correct import | Forbidden |
|---------|----------|----------------|-----------|
| Structured logging | `harness_skills.logging_config` | `get_logger("domain")` | `logging.getLogger()`, `print()` |
| Harness config | `harness_skills.gates.HarnessConfigLoader` | `HarnessConfigLoader(path)` | raw `yaml.safe_load()`, `open()` |
| API secrets / auth | constructor/param injection (bootstrap only) | receive `api_key` as argument | `os.environ.get("KEY")` in domain code |

**Open violations (migrate on next touch):**

*Logging provider (MB011):*
- `stale_plan_detector.py:44` — `log = logging.getLogger("stale_detector")`
- `harness_skills/plugins/loader.py:8` — `logger = logging.getLogger("harness_skills.plugins.loader")`
- `harness_skills/plugins/runner.py:7` — `logger = logging.getLogger("harness_skills.plugins.runner")`

*Secrets/auth provider (MB013):*
- `harness_skills/stale_plan_detector.py:284` — inline `os.environ.get("ANTHROPIC_API_KEY")` inside domain method; accept as constructor param instead.
- `harness_skills/plugins/gate_plugin.py:61` — `{**os.environ, **expanded_env}` inside gate class; move env preparation to the CLI/entry-point layer.

**Migration example — logging:**
```python
# Before (violation)
import logging
logger = logging.getLogger("harness_skills.plugins.loader")

# After (compliant)
from harness_skills.logging_config import get_logger
logger = get_logger("harness_skills.plugins.loader")
```

**Migration example — secrets:**
```python
# Before (violation — domain method reads os.environ directly)
def run(self, api_key: str | None = None) -> None:
    resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")

# After (compliant — key is injected at construction; domain never touches os.environ)
class StaleDetector:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

# Caller (boot / CLI layer — the only place permitted to read os.environ):
detector = StaleDetector(api_key=os.environ["ANTHROPIC_API_KEY"])
```

**General rule (MB014):** When adding a *new* cross-cutting concern (feature flags,
distributed tracing, metrics sink), create the provider module first, define a
principle here, and only then write consuming code. Never let a second implementation
of the same concern exist, even temporarily.
