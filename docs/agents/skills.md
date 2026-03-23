# Skills Catalog — agent-harness-skills

← [AGENTS.md](../../AGENTS.md)

Skills are Claude Code slash-commands defined as Markdown files under `.claude/commands/`.
Invoke them with `/skill-name` in Claude Code, or call them programmatically via the
agent harness.  34 skills are available.

---

## Harness Core Skills (`/harness:*`)

All located in `.claude/commands/harness/`.

| Skill | Invocation | What it does |
|-------|-----------|-------------|
| Boot | `/harness:boot` | Boot an agent instance with sandbox isolation |
| Create | `/harness:create` | Scaffold a complete harness from a profile |
| Evaluate | `/harness:evaluate` | Run all configured gates; returns `EvaluateResponse` |
| Lint | `/harness:lint` | Static analysis (ruff + mypy) |
| Observe | `/harness:observe` | Tail / query structured logs |
| Status | `/harness:status` | Print the live harness status dashboard |
| Update | `/harness:update` | Incremental harness updates (add/remove gates) |
| Context | `/harness:context` | Provision agent context for the current task |
| Handoff | `/harness:handoff` | Write a `HandoffDocument` and transfer work |
| Resume | `/harness:resume` | Resume an interrupted plan |
| Shared State | `/harness:shared-state` | Read/write the cross-agent key-value store |
| Task Lock | `/harness:task-lock` | Acquire / release an advisory lock |
| Detect Stale | `/harness:detect-stale` | Detect abandoned or outdated plans |
| Completion Report | `/harness:completion-report` | Emit a structured completion report |
| Error Aggregation | `/harness:error-aggregation` | Aggregate and analyse error logs |
| Telemetry | `/harness:telemetry` | Aggregate and report telemetry metrics |
| Screenshot | `/harness:screenshot` | Capture a browser screenshot |
| Observability | `/harness:observability` | Manage the Vector/Loki/Grafana stack |
| Coverage Gate | `/harness:coverage-gate` | Configure / inspect the coverage gate |
| Security Check Gate | `/harness:security-check-gate` | Run CVE / secret scan |
| Docs Freshness | `/harness:docs-freshness` | Check documentation staleness |
| Performance | `/harness:performance` | Run performance benchmarks |
| Principles Gate | `/harness:principles-gate` | Enforce custom golden rules |
| Effectiveness | `/harness:effectiveness` | Show effectiveness metrics dashboard |

---

## Top-Level Skills

Located directly in `.claude/commands/`.

| Skill | Invocation | What it does |
|-------|-----------|-------------|
| Browser Automation | `/browser-automation` | Set up Playwright; generate `AgentDriver` |
| CI Pipeline | `/ci-pipeline` | Generate GitHub Actions / GitLab CI config |
| Observability Stack | `/observability` | Provision Vector → Loki → Grafana |
| Check Code | `/check-code` | Scan for module boundary violations |
| Checkpoint | `/checkpoint` | Create a git checkpoint |
| claw-forge Status | `/claw-forge-status` | Report claw-forge task status |
| Context Handoff | `/context-handoff` | Agent handoff protocol (top-level) |
| Coordinate | `/coordinate` | Multi-agent task conflict dashboard |
| Create Bug Report | `/create-bug-report` | Structured bug report for `claw-forge fix` |
| Create Spec | `/create-spec` | Generate an XML project specification |
| Define Principles | `/define-principles` | Define / update `.claude/principles.yaml` |
| Detect API Style | `/detect-api-style` | Detect REST / RPC / GraphQL API style |
| Doc Freshness Gate | `/doc-freshness-gate` | Check doc freshness (top-level) |
| DOM Snapshot | `/dom-snapshot` | Capture browser-free DOM snapshot |
| Execution Plans | `/execution-plans` | Track agent execution plans |
| Expand Project | `/expand-project` | Scaffold new modules into the project |
| Harness Changelog | `/harness-changelog` | Generate a changelog from harness history |
| Harness Init | `/harness-init` | Full initial harness bootstrap (893 lines) |
| Health Check Endpoint | `/health-check-endpoint` | Generate a `/healthz` endpoint |
| Log Format Linter | `/log-format-linter` | Lint log statements for the 5-field contract |
| Logging Convention | `/logging-convention` | Generate / update `SPEC.md` |
| Module Boundaries | `/module-boundaries` | Refresh `ARCHITECTURE.md` boundary analysis |
| Pool Status | `/pool-status` | Show agent pool status |
| Progress Log | `/progress-log` | Track task progress |
| Review PR | `/review-pr` | Automated PR review |
| Type Safety Gate | `/type-safety-gate` | Strict TypeScript / mypy checks |

---

## How Skills Are Loaded

Skills are **auto-injected** based on the file types in the current task.  The claw-forge
orchestrator reads `claw-forge.yaml` to determine which skills apply.  You can always
invoke any skill manually.

To see which skills are active for the current task:

```bash
/harness:context
```

---

## Writing a New Skill

1. Create a Markdown file in `.claude/commands/<name>.md` (or `harness/<name>.md`)
2. Follow the existing skill doc structure:
   - Front-matter block (`<!-- harness:auto-generated ... -->`)
   - Purpose / description section
   - Input / output specification
   - Usage examples
   - Error handling guidance
3. For skills with runtime logic, create a matching script in `skills/<name>/`
4. Register the skill in `claw-forge.yaml` if it needs auto-injection

---

## Deeper References

- **All harness skill docs** → `.claude/commands/harness/` (24 files)
- **Top-level skill docs** → `.claude/commands/` (10 top-level files)
- **Runtime skill scripts** → `skills/` directory
- **Harness init (full bootstrap)** → `.claude/commands/harness-init.md` (893 lines)
- **Skill principles** → `.claude/principles.yaml` (45 KB, 5 major categories)
- **claw-forge config** → `claw-forge.yaml`
- **Architecture** → [ARCHITECTURE.md](../../ARCHITECTURE.md)
