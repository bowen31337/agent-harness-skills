# Harness Changelog

Tracks every harness update run — skills added or modified, config tweaks, doc edits.
Each entry is anchored to a git commit hash so you can `git checkout <hash>` to inspect
the exact state at that point in time.

---

## 2026-03-24 — `91d17ed` — feat/architecture-do-skill-generates-an-artifact-changelog-d

> Run at 13:42:47  ·  Diffed from `0bae125`

### Skills  (71 total)
- ✅ `agents-md-generator.md` — Added
- ✅ `agents-md.md` — Added
- ✅ `architecture.md` — Added
- ✅ `boundary-validation.md` — Added
- ✅ `concurrency-patterns.md` — Added
- ✅ `context-handoff.md` — Added
- ✅ `design-docs.md` — Added
- ✅ `detect-api-style.md` — Added
- ✅ `detect-env-vars.md` — Added
- ✅ `doc-freshness-gate.md` — Added
- ✅ `execution-plans.md` — Added
- ✅ `file-naming-convention.md` — Added
- ✅ `file-size-gate.md` — Added
- ✅ `generate-docs.md` — Added
- ✅ `golden-principles-cleanup.md` — Added
- ✅ `harness/agents-md-token-gate.md` — Added
- ✅ `harness/audit.md` — Added
- ✅ `harness/boot.md` — Added
- ✅ `harness/completion-report.md` — Added
- ✅ `harness/docs-freshness.md` — Added
- ✅ `harness/env-isolation.md` — Added
- ✅ `harness/error-aggregation.md` — Added
- ✅ `harness/handoff.md` — Added
- ✅ `harness/observability.md` — Added
- ✅ `harness/observe.md` — Added
- ✅ `harness/plan.md` — Added
- ✅ `harness/principles-gate.md` — Added
- ✅ `harness/regression-gate.md` — Added
- ✅ `harness/security-check-gate.md` — Added
- ✅ `harness/shared-state.md` — Added
- ✅ `harness/symbol-index.md` — Added
- ✅ `harness/task-lock.md` — Added
- ✅ `harness/type-safety-gate.md` — Added
- ✅ `health-check-endpoint.md` — Added
- ✅ `import-ordering.md` — Added
- ✅ `log-format-linter.md` — Added
- ✅ `logging-convention.md` — Added
- ✅ `module-boundaries.md` — Added
- ✅ `observability.md` — Added
- ✅ `principles-report.md` — Added
- ✅ `providers-pattern.md` — Added
- ✅ `type-safety-gate.md` — Added
- 📝 `checkpoint.md` — Modified
- 📝 `create-spec.md` — Modified
- 📝 `define-principles.md` — Modified
- 📝 `expand-project.md` — Modified
- 📝 `harness-changelog.md` — Modified
- 📝 `harness/create.md` — Modified
- 📝 `harness/detect-stale.md` — Modified
- 📝 `harness/evaluate.md` — Modified
- 📝 `harness/lint.md` — Modified
- 📝 `harness/performance.md` — Modified
- 📝 `harness/telemetry.md` — Modified
- 📝 `harness/update.md` — Modified

### Config
- 📝 `CLAUDE.md` — Modified
- 📝 `README.md` — Modified

### Docs
- ✅ `docs/ARCHITECTURE.md` — Added
- ✅ `docs/DOCS_INDEX.md` — Added
- ✅ `docs/ERROR_HANDLING_RULES.md` — Added
- ✅ `docs/EVALUATION.md` — Added
- ✅ `docs/HEALTH_CHECK_SPEC.md` — Added
- ✅ `docs/PRINCIPLES.md` — Added
- ✅ `docs/SPEC.md` — Added
- 📝 `docs/agent_tool_desig_guidelines.md` — Modified
- ✅ `docs/agents/browser.md` — Added
- ✅ `docs/agents/cli-commands.md` — Added
- ✅ `docs/agents/coordination.md` — Added
- ✅ `docs/agents/gates.md` — Added
- ✅ `docs/agents/logging.md` — Added
- ✅ `docs/agents/skills.md` — Added
- ✅ `docs/design-docs/README.md` — Added
- ✅ `docs/design-docs/adr/0001-adopt-playwright-for-browser-testing.md` — Added
- ✅ `docs/design-docs/drafts/.gitkeep` — Added
- ✅ `docs/design-docs/template.md` — Added
- ✅ `docs/exec-plans/cleanup-tasks.yaml` — Added
- 📝 `docs/exec-plans/plan-template.yaml` — Modified
- 📝 `docs/exec-plans/shared-state.yaml` — Modified
- ✅ `docs/generated/api/index.md` — Added
- ✅ `docs/generated/graphs/index.md` — Added
- ✅ `docs/generated/index.md` — Added
- ✅ `docs/generated/schemas/index.md` — Added
- 📝 `docs/harness-changelog.md` — Modified
- ❌ `docs/harness-init.sh` — Removed
- 📝 `docs/plan-to-pr-convention.md` — Modified

### Spec
- ✅ `spec/app_spec.example.xml` — Added
- ✅ `spec/app_spec.txt` — Added

### Commits
- `91d17ed` — Skill generates background cleanup task definitions that age: Skill generates background c…
- `5f9c529` — Skill generates concurrency and async patterns rule based on: Skill generates concurrency …
- `822e39b` — Skill supports custom principle definitions allowing enginee: Skill supports custom princi…
- `d521973` — Skill generates naming convention rules for functions, varia: Skill generates naming conve…
- `037507f` — Skill generates import ordering and grouping rules matching : Skill generates import order…
- `5bb30d6` — Skill generates a no-magic-numbers and no-hardcoded-strings : Skill generates a no-magic-n…
- `2cccee2` — refactor: reorganize project root — move docs, scripts, shims, and schemas to proper direc…
- `7862c8c` — refactor: package root Python in harness_tools; relocate specs under docs/
- `2f24b40` — refactor: group root specs and examples into spec/ and examples/
- `6cd4098` — chore: expand .gitignore and stop tracking generated/local artifacts
- `adae816` — chore: gitignore .venv, __pycache__, *.pyc and remove from tracking
- `63a79bb` — architecture-do-skill-supports-custom-layer-definitions: squash merge (conflicts auto-reso…
- `a4bf1c9` — agents-md-gener-skill-generates-per-domain-agents-md-fi: squash merge (conflicts auto-reso…
- `55590fc` — skill-invocatio-skill-supports-command-composition-wher: squash merge (conflicts auto-reso…
- `6feb3ec` — skill-invocatio-skill-registers-as-harness-update-for-r: squash merge (conflicts auto-reso…
- `6ea4c40` — skill-invocatio-skill-registers-as-harness-plan-for-cre: squash merge from feature branch
- `43efc2a` — skill-invocatio-skill-registers-as-harness-lint-for-run: squash merge (conflicts auto-reso…
- `1ea2ca8` — skill-invocatio-skill-registers-as-harness-evaluate-for: squash merge (conflicts auto-reso…
- `791b541` — skill-invocatio-skill-registers-as-harness-create-for-f: squash merge (conflicts auto-reso…
- `44dc980` — skill-invocatio-skill-registers-as-harness-boot-for-lau: squash merge (conflicts auto-reso…
- `e20f108` — skill-invocatio-skill-generates-typed-pydantic-response: squash merge (conflicts auto-reso…
- `9b626b0` — skill-invocatio-cli-commands-support-verbosity-levels-q: squash merge (conflicts auto-reso…
- `861aab4` — skill-invocatio-all-cli-commands-support-a-output-forma: squash merge (conflicts auto-reso…
- `25f6862` — observability-a-skill-generates-telemetry-hooks-that-tr: squash merge (conflicts auto-reso…
- `77cf124` — observability-a-skill-generates-structured-logging-conf: squash merge (conflicts auto-reso…
- `6a71b9c` — observability-a-skill-generates-performance-measurement: squash merge (conflicts auto-reso…
- `7e49dfb` — observability-a-skill-generates-log-format-linter-rules: squash merge (conflicts auto-reso…
- `5763309` — observability-a-skill-generates-environment-isolation-c: squash merge (conflicts auto-reso…
- `088249e` — observability-a-skill-generates-browser-automation-inte: squash merge (conflicts auto-reso…
- `b6dae29` — observability-a-skill-generates-an-error-aggregation-vi: squash merge (conflicts auto-reso…
- `4dc03fe` — observability-a-skill-generates-an-effectiveness-scorin: squash merge (conflicts auto-reso…
- `c5b8b45` — observability-a-skill-generates-a-health-check-endpoint: squash merge (conflicts auto-reso…
- `641e9fd` — observability-a-skill-generates-a-harness-telemetry-com: squash merge (conflicts auto-reso…
- `a91bb6a` — observability-a-skill-generates-a-harness-screenshot-co: squash merge (conflicts auto-reso…
- `e2ac280` — observability-a-skill-generates-a-harness-boot-command: squash merge (conflicts auto-resol…
- `ab20e77` — observability-a-skill-generates-a-dom-snapshot-utility: squash merge (conflicts auto-resol…
- `218bbb0` — golden-principl-skill-supports-custom-principle-definit: squash merge (conflicts auto-reso…
- `3db3832` — golden-principl-skill-generates-test-writing-principles: squash merge (conflicts auto-reso…
- `fd20594` — golden-principl-skill-generates-naming-convention-rules: squash merge (conflicts auto-reso…
- `4c24526` — golden-principl-skill-generates-import-ordering-and-gro: squash merge (conflicts auto-reso…
- `76a2b85` — golden-principl-skill-generates-error-handling-pattern: squash merge (conflicts auto-resol…
- `dc6b7d6` — golden-principl-skill-generates-concurrency-and-async-p: squash merge (conflicts auto-reso…
- `705292a` — golden-principl-skill-generates-boundary-level-validati: squash merge from feature branch
- `94cf4ed` — golden-principl-skill-generates-background-cleanup-task: squash merge (conflicts auto-reso…
- `0fc75e7` — golden-principl-skill-generates-a-principles-md-file-li: squash merge (conflicts auto-reso…
- `61bfb9f` — golden-principl-skill-generates-a-principle-violation-r: squash merge (conflicts auto-reso…
- `ea4cfcf` — golden-principl-skill-generates-a-prefer-shared-utiliti: squash merge (conflicts auto-reso…
- `0c1622e` — golden-principl-skill-generates-a-no-magic-numbers-and: squash merge (conflicts auto-resol…
- `17562d9` — execution-plans-skill-generates-progress-log-format-whe: squash merge (conflicts auto-reso…
- `16c159c` — execution-plans-skill-generates-git-based-checkpoint-in: squash merge (conflicts auto-reso…
- `c15fa5b` — execution-plans-skill-generates-execution-plan-template: squash merge (conflicts auto-reso…
- `1b67de6` — execution-plans-skill-generates-docs-exec-plans-directo: squash merge (conflicts auto-reso…
- `0651b23` — execution-plans-skill-generates-context-handoff-protoco: squash merge (conflicts auto-reso…
- `6975a84` — execution-plans-skill-generates-a-task-lock-protocol-wh: squash merge (conflicts auto-reso…
- `2b004e0` — execution-plans-skill-generates-a-stale-plan-detector-t: squash merge (conflicts auto-reso…
- `01a97bb` — execution-plans-skill-generates-a-shared-state-file-doc: squash merge (conflicts auto-reso…
- `080b83a` — execution-plans-skill-generates-a-plan-to-pr-linking-co: squash merge (conflicts auto-reso…
- `e32a332` — execution-plans-skill-generates-a-plan-status-dashboard: squash merge (conflicts auto-reso…
- `22ed13e` — execution-plans-skill-generates-a-plan-completion-repor: squash merge (conflicts auto-reso…
- `dd9b319` — execution-plans-skill-generates-a-harness-plan-command: squash merge (conflicts auto-resol…
- `ceb0468` — execution-plans-skill-generates-a-harness-coordinate-co: squash merge (conflicts auto-reso…
- `2545e3c` — execution-plans-skill-generates-a-harness-context-comma: squash merge (conflicts auto-reso…
- `9b8e141` — execution-plans-execution-plans-support-task-dependenci: squash merge (conflicts auto-reso…
- `c2da097` — evaluation-gate-skill-supports-custom-evaluation-gates: squash merge (conflicts auto-resol…
- `00eb073` — evaluation-gate-skill-generates-per-gate-configuration: squash merge (conflicts auto-resol…
- `c3552cc` — evaluation-gate-skill-generates-an-evaluation-md-defini: squash merge (conflicts auto-reso…
- `2502231` — evaluation-gate-skill-generates-an-architectural-compli: squash merge (conflicts auto-reso…
- `523d816` — evaluation-gate-skill-generates-a-type-safety-gate-that: squash merge (conflicts auto-reso…
- `117e9e5` — evaluation-gate-skill-generates-a-security-check-gate-c: squash merge (conflicts auto-reso…
- `fb01e30` — evaluation-gate-skill-generates-a-regression-test-gate: squash merge (conflicts auto-resol…
- `c67b2a7` — evaluation-gate-skill-generates-a-performance-benchmark: squash merge (conflicts auto-reso…
- `bfe251f` — evaluation-gate-skill-generates-a-lint-gate-that-runs-a: squash merge (conflicts auto-reso…
- `44f91f9` — evaluation-gate-skill-generates-a-harness-evaluate-comm: squash merge (conflicts auto-reso…
- `c44b4ad` — evaluation-gate-skill-generates-a-golden-principles-com: squash merge (conflicts auto-reso…
- `61aab66` — evaluation-gate-skill-generates-a-gate-failure-report-a: squash merge (conflicts auto-reso…
- `054d924` — evaluation-gate-skill-generates-a-documentation-freshne: squash merge (conflicts auto-reso…
- `c236d04` — evaluation-gate-skill-generates-a-coverage-gate-with-co: squash merge (conflicts auto-reso…
- `578b6a6` — codebase-analys-skill-produces-a-harness-manifest-json: squash merge (conflicts auto-resol…
- `ed6cc56` — codebase-analys-skill-maps-directory-tree-into-candidat: squash merge (conflicts auto-reso…
- `ae917c4` — codebase-analys-skill-generates-a-symbol-index-harness: squash merge from feature branch
- `67a9cc6` — codebase-analys-skill-generates-a-harness-manifest-sche: squash merge (conflicts auto-reso…
- `9862d07` — codebase-analys-skill-detects-primary-language-s-and-fr: squash merge (conflicts auto-reso…
- `bb63142` — codebase-analys-skill-detects-environment-variable-patt: squash merge (conflicts auto-reso…
- `29415ae` — architecture-do-skill-infers-dependency-direction-betwe: squash merge (conflicts auto-reso…
- `bed7cc5` — architecture-do-skill-generates-module-boundary-rules-w: squash merge (conflicts auto-reso…
- `ed883d4` — architecture-do-skill-generates-linter-rules-that-mecha: squash merge (conflicts auto-reso…
- `30d84fa` — architecture-do-skill-generates-file-size-limit-rules-c: squash merge (conflicts auto-reso…
- `60c833d` — architecture-do-skill-generates-file-naming-convention: squash merge from feature branch
- `220e10a` — architecture-do-skill-generates-docs-generated-director: squash merge (conflicts auto-reso…
- `e1ff6c7` — architecture-do-skill-generates-docs-design-docs-direct: squash merge from feature branch
- `40b0310` — architecture-do-skill-generates-ci-validation-script-th: squash merge (conflicts auto-reso…
- `733d572` — architecture-do-skill-generates-architecture-md-with-a: squash merge (conflicts auto-resol…
- `cfd5995` — architecture-do-skill-generates-an-artifact-changelog-d: squash merge from feature branch
- `aff5c92` — architecture-do-skill-generates-a-structural-test-suite: squash merge (conflicts auto-reso…
- `6aa956d` — architecture-do-skill-generates-a-providers-pattern-def: squash merge from feature branch
- `b7780b9` — architecture-do-skill-generates-a-layered-architecture: squash merge (conflicts auto-resol…
- `01fb7f1` — architecture-do-skill-generates-a-harness-lint-command: squash merge from feature branch
- `043edd6` — architecture-do-skill-embeds-a-version-identifier-and-g: squash merge (conflicts auto-reso…
- `9492f80` — architecture-do-skill-documents-the-one-way-dependency: squash merge from feature branch
- `478118e` — agents-md-gener-skill-supports-regeneration-mode-that-r: squash merge (conflicts auto-reso…
- `75ee3a2` — agents-md-gener-skill-includes-testing-conventions-sect: squash merge (conflicts auto-reso…
- `371937a` — agents-md-gener-skill-includes-security-protocols-secti: squash merge (conflicts auto-reso…
- `fa114cf` — agents-md-gener-skill-includes-git-workflow-section-wit: squash merge (conflicts auto-reso…
- `8bf9c0b` — agents-md-gener-skill-includes-error-handling-patterns: squash merge from feature branch
- `c413f43` — agents-md-gener-skill-includes-detected-build-test-and: squash merge (conflicts auto-resol…
- `1159f37` — agents-md-gener-skill-includes-code-conventions-section: squash merge from feature branch
- `e7de591` — agents-md-gener-skill-includes-architecture-overview-se: squash merge (conflicts auto-reso…
- `2a61401` — agents-md-gener-skill-generates-a-tiered-agents-md-syst: squash merge (conflicts auto-reso…
- `7980124` — agents-md-gener-skill-generates-a-context-depth-map-in: squash merge (conflicts auto-resol…
- `bb6759c` — agents-md-gener-skill-flags-stale-documentation-risks-b: squash merge (conflicts auto-reso…
- `8ef277e` — agents-md-gener-skill-enforces-token-budget-awareness-w: squash merge from feature branch
- `2ea4c1b` — agents-md-gener-skill-cross-links-all-generated-documen: squash merge from feature branch
- `2c470a0` — Skill generates a type safety gate that runs the type checke: Skill generates a type safet…
- `ba54194` — Skill generates a security check gate covering secret scanni: Skill generates a security c…
- `9c50a8d` — Skill generates a coverage gate with configurable threshold : Skill generates a coverage g…
- `6ffc3d7` — Skill generates an architectural compliance gate that runs t: Skill generates an architect…
- `94f3438` — Skill generates a performance benchmark gate with configurab: Skill generates a performanc…
- `65d54de` — Skill generates a golden principles compliance gate that run: Skill generates a golden pri…
- `7a07a0b` — Skill generates a documentation freshness gate that verifies: Skill generates a documentat…
- `afd3a9f` — Skill generates per-gate configuration in harness.config.yam: Skill generates per-gate con…
- `1ea5cf8` — Skill generates a lint gate that runs all configured linters: Skill generates a lint gate …
- `d6116bb` — Skill generates a harness evaluate command that runs all gat: Skill generates a harness ev…
- `5f1c0c9` — Skill generates structured logging configuration matching th: Skill generates structured l…
- `5ee6c24` — Skill generates CI pipeline integration as GitHub Actions wo: Skill generates CI pipeline …
- `65e7a8d` — Skill generates a logging convention document specifying req: Skill generates a logging co…
- `c7687b3` — Skill generates a gate failure report as structured JSON (wi: Skill generates a gate failu…
- `1e5b7b2` — Skill supports custom evaluation gates allowing engineers to: Skill supports custom evalua…
- `37ff72d` — Skill generates log format linter rules ensuring all log sta: Skill generates log format l…
- `ae74b75` — Skill generates a per-worktree boot script that launches an : Skill generates a per-worktr…
- `aff5394` — Skill generates observability stack templates (optional) for: Skill generates observabilit…
- `d7407f3` — Skill generates observability stack templates (optional) for: Skill generates observabilit…
- `b02aa88` — Skill generates an error aggregation view so agents can quer: Skill generates an error agg…
- `e573afe` — Skill generates a harness boot command that starts the isola: Skill generates a harness bo…
- `1fb93da` — Skill generates a health check endpoint specification that a: Skill generates a health che…
- `41acaf7` — Skill generates a harness observe command that tails structu: Skill generates a harness ob…
- `97d5456` — Skill generates a harness observe command that tails structu: Skill generates a harness ob…
- `6ab6243` — Skill generates browser automation integration config (Playw: Skill generates browser auto…
- `39faadd` — Skill generates a DOM snapshot utility that agents can invok: Skill generates a DOM snapsh…
- `651d5ed` — Skill generates a stale plan detector that flags execution p: Skill generates a stale plan…
- `d49e774` — Skill generates performance measurement hooks so agents can : Skill generates performance …
- `6085c2e` — Skill generates a harness screenshot command that captures t: Skill generates a harness sc…
- `b0049c1` — Skill generates a harness screenshot command that captures t: Skill generates a harness sc…
- `ca81d84` — Skill generates an effectiveness scoring system that correla: Skill generates an effective…
- `ca11dc3` — Skill generates telemetry hooks that track which harness art: Skill generates telemetry ho…
- `67f831d` — Skill generates a harness telemetry command that reports art: Skill generates a harness te…
- `c7e0d99` — Skill generates context handoff protocol where ending agent : Skill generates context hand…
- `5bbdbeb` — Skill generates docs/exec-plans/ directory structure with te: Skill generates docs/exec-pl…
- `523b756` — Skill generates execution plan template with sections: objec: Skill generates execution pl…
- `cee361c` — Skill generates a harness plan command that creates a new ex: Skill generates a harness pl…
- `e8715ea` — Skill generates progress log format where agents append time: Skill generates progress log…
- `6f44238` — Skill generates a plan status dashboard command (harness sta: Skill generates a plan statu…
- `feaa463` — Skill generates git-based checkpoint integration where agent: Skill generates git-based ch…
- `9f9858b` — checkpoint: 2026-03-22 20:10:12
- `65a7abf` — Skill generates typed pydantic response models for every CLI: Skill generates typed pydant…
- `b7e94d8` — Skill generates a harness resume command that loads the most: Skill generates a harness re…
- `4539331` — Skill generates a technical debt tracker where agents log kn: Skill generates a technical …
- `d239df3` — Skill generates a technical debt tracker where agents log kn: Skill generates a technical …
- `5149508` — Skill generates a plan completion report summarizing what wa: Skill generates a plan compl…
- `8bdabc0` — Skill generates a plan-to-PR linking convention where each P: Skill generates a plan-to-PR…
- `a824834` — Skill generates a task lock protocol where agents acquire a : Skill generates a task lock …
- `3fb08e5` — Execution plan templates include a context assembly section : Execution plan templates inc…
- `887af11` — Skill generates a harness context command that, given a plan: Skill generates a harness co…
- `5b98c10` — Execution plans support task dependencies via a depends_on f: Execution plans support task…
- `f795b1e` — Skill registers as /harness:lint for running all architectur: Skill registers as /harness:…
- `2bc24da` — Skill generates a shared state file (docs/exec-plans/shared-: Skill generates a shared sta…
- `f576fff` — Skill registers as /harness:evaluate for running all evaluat: Skill registers as /harness:…
- `8efdc55` — Skill generates a harness coordinate command that shows cros: Skill generates a harness co…
- `047b4aa` — Skill registers as /harness:update for re-scanning codebase : Skill registers as /harness:…
- `157af7b` — Skill registers as /harness:boot for launching an isolated a: Skill registers as /harness:…
- `fa4dd09` — Skill registers as /harness:status for showing current state: Skill registers as /harness:…
- `7890b21` — Skill generates a harness.config.yaml with config profiles (: Skill generates a harness.co…
- `daecff7` — Skill registers as /harness:resume for loading most recent p: Skill registers as /harness:…
- `5f55474` — Skill registers as /harness:screenshot for capturing applica: Skill registers as /harness:…
- `d330979` — All CLI commands support a --output-format flag (json, yaml: All CLI commands support a --…
- `5c2c812` — CLI commands support --verbosity levels (quiet, normal, verb: CLI commands support --verbo…
- `0e893bd` — Skill registers as /harness:plan for creating a new executio: Skill registers as /harness:…
- `7446a2f` — Skill registers as /harness:status for showing current state: Skill registers as /harness:…
- `e0f047c` — Skill generates a harness.config.yaml with config profiles (: Skill generates a harness.co…
- `22f4812` — Skill supports command composition where harness create, har: Skill supports command compo…
- `593a28d` — Skill generates a harness init shell script for teams not us: Skill generates a harness in…
- `9c7e5db` — Apply stashed changes from harness update skill branch
- `266d724` — Initial commit

---

## 2026-03-20 — `0bae125` — feat/architecture-do-skill-generates-an-artifact-changelog-d

> Run at 15:04:18  ·  Diffed from `af3945f`

### Skills  (16 total)
- ✅ `harness-init.md` — Added
- ✅ `harness/context.md` — Added
- ✅ `harness/coverage-gate.md` — Added
- ✅ `harness/create.md` — Added
- ✅ `harness/detect-stale.md` — Added
- ✅ `harness/effectiveness.md` — Added
- ✅ `harness/evaluate.md` — Added
- ✅ `harness/performance.md` — Added
- ✅ `harness/resume.md` — Added
- ✅ `harness/screenshot.md` — Added
- ✅ `harness/status.md` — Added
- ✅ `harness/telemetry.md` — Added
- ✅ `harness/update.md` — Added
- ✅ `progress-log.md` — Added

### Config
- 📝 `CLAUDE.md` — Modified
- 📝 `claw-forge.yaml` — Modified

### Docs
- 📝 `docs/exec-plans/debt.md` — Modified
- ✅ `docs/exec-plans/perf-timers.json` — Added
- ✅ `docs/exec-plans/perf.md` — Added
- ✅ `docs/exec-plans/plan-template.yaml` — Added
- ✅ `docs/exec-plans/progress.md` — Added
- 📝 `docs/exec-plans/shared-state.yaml` — Modified
- 📝 `docs/harness-changelog.md` — Modified
- 📝 `docs/harness-telemetry.json` — Modified
- ✅ `docs/health-check-endpoint-spec.md` — Added
- ✅ `docs/plan-to-pr-convention.md` — Added

### Spec
- 📝 `spec/app_spec.txt` — Modified

### Commits
- `0bae125` — Skill generates a prefer-shared-utilities-over-hand-rolled-helpers rule with pointers to existing utility packages in the codebase
- `6e5d546` — Skill generates boundary-level validation rules specifying that data validation happens at system boundaries (API input, external services) not deep in business logic
- `d7b64b1` — Skill generates concurrency and async patterns rule based on detected framework conventions
- `463ebe9` — Skill generates error handling pattern rules specifying structured errors, error codes, and logging format conventions
- `393f78e` — Skill generates naming convention rules for functions, variables, files, and database columns derived from existing codebase style analysis
- `af7a52b` — Skill generates import ordering and grouping rules matching existing conventions detected from the most common patterns
- `5b67710` — Skill generates a no-magic-numbers and no-hardcoded-strings rule with config pattern guidance and constant extraction conventions
- `eb88a13` — Skill generates test writing principles covering arrange-act-assert structure, test naming conventions, fixture patterns, and mock boundary rules
- `ff12233` — Skill generates an EVALUATION.md defining all completion criteria agents must satisfy before opening a PR
- `651cbbb` — Skill generates a coverage gate with configurable threshold (default 90%) that blocks PRs falling below the bar
- `431fb75` — Skill generates a security check gate covering secret scanning, dependency vulnerability audit, and input validation verification
- `bb4c9d3` — Skill generates an architectural compliance gate that runs the structural test suite from the architecture enforcement component
- `6e3ad10` — Skill generates a golden principles compliance gate that runs the principle violation scanner and fails on critical violations
- `6e701f0` — Skill generates a type safety gate that runs the type checker (TypeScript strict, mypy, etc.) with zero errors required
- `e143cf2` — Skill generates a harness evaluate command that runs all gates in sequence and produces a structured JSON pass/fail report
- `3d96792` — Skill generates CI pipeline integration as GitHub Actions workflow and GitLab CI job that runs harness evaluate on every PR
- `5a260e5` — Skill generates a gate failure report as structured JSON (severity, gate_id, file_path, line_number, suggestion fields)
- `90d4b2e` — Skill generates structured logging configuration matching the detected framework
- `b12a96c` — Skill generates environment isolation configuration with separate ports, database schemas, or containers per worktree
- `cef32da` — Skill generates performance measurement hooks so agents can query response times, memory usage, and startup duration
- `b0f446e` — Skill generates performance measurement hooks so agents can query response times, memory usage, and startup duration
- `60b8ef8` — Skill generates context handoff protocol where ending agent sessions write a structured summary to the plan progress log
- `1b7fb48` — Skill generates an error aggregation view so agents can query recent errors grouped by domain and frequency
- `48e0810` — Skill generates an error aggregation view so agents can query recent errors grouped by domain and frequency
- `7d77cb3` — Skill generates telemetry hooks that track which harness artifacts agents actually read and which gate failures are most common
- `fd47305` — Skill generates a harness plan command that creates a new execution plan from a feature description or ticket
- `e08124c` — Skill generates execution plan template with sections: objective, approach, steps, context assembly, progress log, known debt, completion criteria
- `5996285` — checkpoint: 2026-03-20 12:43:55
- `819a374` — Skill registers as /harness:resume for loading most recent plan state and presenting it for context handoff
- `b9a4287` — Add harness:resume skill for loading plan state at session start
- `75fa4e2` — Skill generates a plan-to-PR linking convention where each PR references its source execution plan for full traceability
- `328516b` — Skill generates a harness resume command that loads the most recent plan state and presents it as agent context
- `0920cf3` — Skill registers as /harness:create for full harness generation from codebase analysis through all artifact output
- `449ed61` — Skill generates a technical debt tracker where agents log known shortcuts or TODOs into docs/exec-plans/debt.md
- `3c3cc3a` — Skill generates a plan completion report summarizing what was done, what debt was incurred, and what follow-up is needed
- `04ecf15` — Skill generates a harness context command that returns a minimal set of file paths and search patterns given a plan ID or domain name
- `6a34cb0` — Skill generates a harness coordinate command that shows cross-agent task status and identifies conflicts
- `f0a201c` — Skill registers as /harness:evaluate for running all evaluation gates and producing a structured pass/fail report
- `3b4cbef` — Skill registers as /harness:plan for creating a new execution plan from a description or ticket reference
- `fb52704` — Skill generates a harness.config.yaml with config profiles (starter, standard, advanced)
- `a610246` — Skill generates a harness boot command that starts the isolated app instance and waits for health check to pass
- `00c78f7` — Skill generates a harness observe command that tails structured logs filtered by domain or trace_id in real time
- `6442fa6` — Skill generates browser automation integration config (Playwright or Puppeteer) so agents can drive the UI and capture screenshots
- `435b9e7` — Skill generates performance measurement hooks so agents can query response times, memory usage, and startup duration
- `4e8b5fe` — Skill generates an error aggregation view so agents can query recent errors grouped by domain and frequency
- `03bd6eb` — Skill generates a harness screenshot command that captures the current application state as a visual artifact for PR evidence
- `0877719` — Skill generates telemetry hooks that track which harness artifacts agents actually read
- `471f380` — Skill generates a harness telemetry command that reports artifact utilization rates, command call frequency, and gate effectiveness scores
- `06a91d3` — Skill generates a harness plan command that creates a new execution plan from a feature description or ticket
- `a79850f` — Skill generates a harness resume command that loads the most recent plan state and presents it as agent context
- `563c7f8` — Skill generates a plan completion report summarizing what was done, what debt was incurred, and what follow-up is needed
- `160b518` — Skill generates a plan-to-PR linking convention where each PR references its source execution plan for full traceability
- `817eb11` — Execution plan templates include a context assembly section with grep patterns, file globs, and symbol references
- `e5ad1b1` — Execution plans support task dependencies via a depends_on field; harness status displays a dependency graph
- `37536e8` — Skill registers as /harness:create for full harness generation from codebase analysis through all artifact output
- `50dab09` — Skill registers as /harness:evaluate for running all evaluation gates and producing a structured pass/fail report
- `c7f58a2` — Skill registers as /harness:plan for creating a new execution plan from a description or ticket reference
- `c0dec24` — Skill registers as /harness:status for showing current state of all plans, gates, and harness health metrics
- `e5b8de2` — Skill registers as /harness:screenshot for capturing application state as a visual artifact
- `4b04e50` — CLI commands support --verbosity levels (quiet, normal, verbose, debug) controlling output detail
- `8e612d9` — Skill registers as /harness:screenshot for capturing application state as a visual artifact
- `d0c63e4` — Skill supports custom evaluation gates allowing engineers to define project-specific gates via a plugin interface in harness.config.yaml
- `2daf81a` — Skill generates log format linter rules ensuring all log statements follow the structured pattern
- `1474120` — Skill generates environment isolation configuration with separate ports, database schemas, or containers per worktree
- `29a60ed` — Skill generates a health check endpoint specification that agents can poll to verify the application is running correctly
- `1b86def` — Skill generates browser automation integration config (Playwright or Puppeteer)
- `ab87162` — Skill generates performance measurement hooks so agents can query response times, memory usage, and startup duration
- `6443b0b` — Skill generates an effectiveness scoring system that correlates harness artifact usage with PR quality metrics
- `1f26b49` — Skill generates a harness screenshot command that captures the current application state as a visual artifact for PR evidence
- `1262263` — Skill generates observability stack templates (optional) for lightweight log aggregation in local dev using file-based collectors
- `12db90e` — Skill generates telemetry hooks that track which harness artifacts agents actually read
- `28ffa17` — Skill generates docs/exec-plans/ directory structure with templates for execution plan artifacts
- `ad7311f` — Skill generates progress log format where agents append timestamped entries as they complete steps within a plan
- `304e000` — Skill generates a harness plan command that creates a new execution plan from a feature description or ticket
- `d15e69a` — Skill generates a plan status dashboard command (harness status) showing all active, completed, and blocked plans
- `f87bea3` — Skill generates git-based checkpoint integration where agents commit work-in-progress to a branch with plan reference in the commit message
- `8bff389` — Skill generates a harness resume command that loads the most recent plan state and presents it as agent context
- `455a9c3` — Skill generates a technical debt tracker where agents log known shortcuts or TODOs into docs/exec-plans/debt.md

---

## 2026-03-14 — `af3945f` — feat/coding-5378ef56

> Run at 19:16:22  ·  Diffed from `280d7a4`

### Skills  (16 total)

- ✅ `harness/context.md` — Added  *(plan-ID / domain → minimal file-path + search-pattern manifest for agent-driven context assembly)*
- ✅ `harness/lint.md` — Added  *(architectural + principles lint gate via harness evaluate)*

### Config

- No config changes

### Docs

- ✅ `docs/exec-plans/shared-state.yaml` — Added  *(shared multi-agent coordination state)*
- ✅ `scripts/harness-init-standalone.sh` — Added  *(standalone CLI init script for non-Claude Code teams)*

### Spec

- No spec changes

### Commits

- `af3945f` — Skill generates a plan-to-PR linking convention where each PR references its source execution plan for full traceability
- `ea93a22` — Execution plan templates include a context assembly section with grep patterns, file globs, and symbol references that agents can use to independently rebuild task context using search tools
- `1989f55` — Skill generates a task lock protocol where agents acquire a lock on a plan task before starting work, preventing concurrent modification by multiple agents; locks include agent_id, timestamp, and auto-expire after a configurable timeout
- `73e2a02` — Execution plans support task dependencies via a depends_on field, and harness status displays a dependency graph showing which tasks are blocked, ready, or in-progress
- `09cbbc1` — Skill generates a harness coordinate command that shows cross-agent task status, identifies conflicts (two agents modifying the same files), and suggests task reordering to minimize merge conflicts
- `44d20f1` — Skill registers as /harness:create for full harness generation from codebase analysis through all artifact output
- `90f0888` — Skill registers as /harness:evaluate for running all evaluation gates and producing a structured pass/fail report

---

## 2026-03-13 — `74b33e7` — main

> Run at 21:54:10  ·  Diffed from `e17a209`

### Skills  (14 total)

- ✅ `browser-automation.md` — Added
- 📝 `check-code.md` — Modified
- ✅ `ci-pipeline.md` — Added
- ✅ `coordinate.md` — Added
- ✅ `define-principles.md` — Added
- ✅ `dom-snapshot.md` — Added
- 📝 `review-pr.md` — Modified

### Config

- No config changes

### Docs

- ✅ `docs/exec-plans/debt.md` — Added
- ✅ `docs/harness-telemetry.json` — Added

### Spec

- No spec changes

### Commits

- `74b33e7` — coding(coding-8152f30d): completed
- `f2166a2` — merge: feat/coding-9cfd80f8 (squash)
- `9622b72` — coding(coding-5ab9926e): completed
- `0afde84` — coding(coding-23fd392f): completed
- `77acf9e` — coding(coding-1a1f9009): completed
- `449d858` — merge: feat/coding-c65f2e99 (squash)
- `89fee67` — coding(coding-52516970): completed
- `f002a5c` — coding(coding-d22991cc): completed
- `6829b66` — coding(coding-6ccfb721): completed
- `61d2534` — coding(coding-5610a2fc): completed
- `16980f4` — coding(coding-3a066bd7): completed
- `97c0372` — coding(coding-c14bb315): completed
- `70b21a8` — coding(coding-077b5fbf): completed
- `02db1c0` — coding(coding-fb563322): completed
- `bad8e80` — merge: feat/coding-ce33a8f9 (squash)
- `f86e2ee` — merge: feat/coding-be04bd18 (squash)
- `e0acf14` — coding(coding-a2f043c1): completed
- `446699b` — merge: feat/coding-7f0a2b30 (squash)
- `1326732` — merge: feat/coding-7fc5a724 (squash)
- `29753b0` — merge: feat/coding-922f93bc (squash)
- `a080e15` — coding(coding-fa6a1082): completed
- `5cc0459` — merge: feat/coding-8d971ef5 (squash)
- `858f3a6` — merge: feat/coding-83b9902a (squash)
- `7cd286f` — merge: feat/coding-a56066c6 (squash)
- `f2ed7a9` — merge: feat/coding-60d05f55 (squash)
- `d6df71c` — merge: feat/coding-b9c0f255 (squash)
- `e52365e` — merge: feat/coding-849cdebf (squash)
- `545bd76` — merge: feat/coding-53e43e39 (squash)
- `e0c2287` — merge: feat/coding-cf1423f6 (squash)
- `ed3a84e` — merge: feat/coding-e113552a (squash)

---

## 2026-03-13 — `e17a209` — feat/coding-bae7b81c

> Run at 00:00:00  ·  Diffed from `4781a17`

### Skills  (9 total)

- ✅ `check-code.md` — Added
- ✅ `checkpoint.md` — Added
- ✅ `claw-forge-status.md` — Added
- ✅ `create-bug-report.md` — Added
- ✅ `create-spec.md` — Added
- ✅ `expand-project.md` — Added
- ✅ `harness-changelog.md` — Added
- ✅ `pool-status.md` — Added
- ✅ `review-pr.md` — Added

### Config

- No config changes

### Docs

- ✅ `docs/agent_tool_desig_guidelines.md` — Added
- ✅ `docs/harness-changelog.md` — Added

### Spec

- 📝 `spec/app_spec.txt` — Modified

### Commits

- `e17a209` — update spec
- `4781a17` — Initial commit: agent tool design guidelines and claw-forge harness config

---

