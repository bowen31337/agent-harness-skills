# AGENTS.md

<!-- harness:auto-generated — do not edit this block manually -->
last_updated: 2026-03-23
head: 2c470a0
service: agent-harness-skills
<!-- /harness:auto-generated -->

Agent-facing reference for this repository.

---

## Browser Automation

Framework: **Playwright** (Python)
Browser:   Chromium (headless)
Base URL:  `http://localhost:3000` (override with `BASE_URL` env var)
Screenshots saved to: `./screenshots/`

### Quick start

```python
from tests.browser.agent_driver import AgentDriver

# Context-manager form (recommended — always cleans up the browser)
with AgentDriver.launch() as driver:
    page = driver.new_page()
    page.goto("/")                          # relative to BASE_URL
    driver.screenshot(page, "home")         # → screenshots/home-<timestamp>.png

# Or navigate to an absolute URL
with AgentDriver.launch(base_url="http://localhost:8080") as driver:
    page = driver.new_page()
    page.goto("http://localhost:8080/login")
    driver.screenshot(page, "login")
```

### Screenshot helper (lower level)

```python
from tests.browser.screenshot_helper import capture_screenshot, visit_and_capture

# Capture the current state of any page
path = capture_screenshot(page, "checkout-step-2")

# Navigate + capture in one call
path = visit_and_capture(page, "/dashboard", "dashboard")
```

### Running e2e tests

```bash
# All browser tests
pytest tests/browser/ -v

# Single test file
pytest tests/browser/test_smoke.py -v

# Run headed (shows browser window — useful for local debugging)
pytest tests/browser/ --headed

# Target a different environment
BASE_URL=https://staging.example.com pytest tests/browser/ -v
```

### Environment variables

| Variable         | Default                   | Purpose                                  |
|------------------|---------------------------|------------------------------------------|
| `BASE_URL`       | `http://localhost:3000`   | Base URL for relative `goto()` calls     |
| `SCREENSHOT_DIR` | `./screenshots`           | Directory where PNGs are saved           |

### Recording video (for post-mortems)

Pass `record_video=True` to `AgentDriver.launch()` to save a `.webm` session
recording to `./videos/`:

```python
with AgentDriver.launch(record_video=True) as driver:
    page = driver.new_page()
    page.goto("/checkout")
    driver.screenshot(page, "checkout")
# video is written when the context closes (i.e. on __exit__)
```

### Failure screenshots (pytest-playwright)

`tests/browser/conftest.py` registers an `autouse` fixture that captures a
full-page PNG whenever a browser test fails.  Screenshots land in:

```
screenshots/failures/<test-nodeid>.png
```

Upload this directory as a CI artefact to inspect failures without re-running.

### Capturing screenshots from an agent task

1. Start the dev server (if needed): `python -m uvicorn app:app --reload` or equivalent
2. Set `BASE_URL` if targeting staging/CI
3. Call `driver.screenshot(page, '<meaningful-label>')`
4. Find the PNG at `screenshots/<label>-<timestamp>.png`
5. Attach the path in your task result or claw-forge state update

### Install / setup (first time)

```bash
pip install playwright pytest-playwright
playwright install chromium   # downloads the Chromium binary
```

Both `playwright` and `pytest-playwright` are already listed in `requirements.txt`.

---

<!-- harness:context-depth-map -->
<!-- regenerate: /agents-md-generator  last_updated: 2026-03-23  head: 2c470a0 -->

## Context Depth Map

> **Reading guide** — Load only the tier(s) relevant to your task.
> Prefer `Grep` patterns over loading entire files.
> Token estimates assume **~15 tokens per line** (60 chars ÷ 4 chars/token).
> Add a 20 % margin when planning context-window budgets.

---

### Tier Summary

| Tier | Scope | Files | Est. Tokens | Load when… |
|------|-------|-------|-------------|-----------|
| **L0** | Root overview — project-wide docs & config | 8 | ~31,450 total | First orientation; always load |
| **L1** | Domain docs — package `__init__` & skill commands | 32 | ~150–800 each | Entering a package or skill domain |
| **L2** | File-level — individual source modules | 48 | ~150–17,400 each | Touching specific logic |

---

### L0 — Root Overview  (total budget: ~31,450 tokens)

Load **all** L0 files for initial project orientation.
These are the authoritative single sources of truth for project-wide conventions.

| File | Lines | Est. Tokens | Purpose |
|------|-------|-------------|---------|
| `README.md` | 27 | ~400 | One-paragraph summary & quick links |
| `ARCHITECTURE.md` | 244 | ~3,650 | Domain map, package public APIs, dependency rules |
| `PRINCIPLES.md` | 702 | ~10,550 | Design principles every agent must respect |
| `SPEC.md` | 346 | ~5,200 | Structured-logging NDJSON contract (5 required fields) |
| `ERROR_HANDLING_RULES.md` | 343 | ~5,150 | Error propagation, retry, and surfacing rules |
| `EVALUATION.md` | 35 | ~550 | Gate evaluation framework overview |
| `HEALTH_CHECK_SPEC.md` | 364 | ~5,450 | `/health` endpoint contract for all services |
| `CLAUDE.md` | 33 | ~500 | claw-forge agent notes (state service URL, skills list) |

**Recommended load order:** `README` → `ARCHITECTURE` → `PRINCIPLES` → domain-specific docs.

---

### L1 — Domain Docs  (budget: ~150–800 tokens per entry)

Load the matching domain(s) for the feature you are working on.
Each entry is a package `__init__.py` (exports + purpose) or a skill command file.

#### `harness_skills` — Core Framework  (~2,650 tokens total for all sub-packages)

| File | Lines | Est. Tokens | Public exports / purpose |
|------|-------|-------------|--------------------------|
| `harness_skills/__init__.py` | 8 | ~150 | Empty public surface; all symbols owned by sub-packages |
| `harness_skills/models/__init__.py` | 49 | ~750 | `Status`, `GateResult`, `HarnessResponse`, `LogEntry`, `TelemetryReport`, … |
| `harness_skills/gates/__init__.py` | 53 | ~800 | `CoverageGate`, `DocsFreshnessGate`, `GateEvaluator`, `run_gates` |
| `harness_skills/generators/__init__.py` | 21 | ~300 | `EvaluationReport`, `run_all_gates` |
| `harness_skills/plugins/__init__.py` | 26 | ~400 | `PluginGateRunner`, `load_plugin_gates`, `run_plugin_gates` |
| `harness_skills/cli/__init__.py` | 12 | ~200 | `cli`, `PipelineGroup` — `harness` CLI entry point |
| `harness_skills/utils/__init__.py` | 3 | ~50 | Internal helpers only; no public API |

#### `dom_snapshot_utility` — Browser-Free DOM Inspection  (~600 tokens)

| File | Lines | Est. Tokens | Public exports / purpose |
|------|-------|-------------|--------------------------|
| `dom_snapshot_utility/__init__.py` | 41 | ~600 | `DOMSnapshot`, `PageMeta`, `Heading`, `Link`, `Button`, `Form`, `AriaRegion`, … |

#### `harness_dashboard` — Effectiveness Scoring & Dashboards  (~450 tokens)

| File | Lines | Est. Tokens | Public exports / purpose |
|------|-------|-------------|--------------------------|
| `harness_dashboard/__init__.py` | 31 | ~450 | Terminal dashboards (Rich), PR effectiveness metrics, dataset generators |

#### `log_format_linter` — Structured-Log Validation  (~600 tokens)

| File | Lines | Est. Tokens | Public exports / purpose |
|------|-------|-------------|--------------------------|
| `log_format_linter/__init__.py` | 39 | ~600 | Framework detection, per-framework linting rules, violation reporting |

#### `.claude/commands/` — Skill Library  (26 skills, ~200–400 tokens each)

| Skill file | Est. Tokens | Capability |
|------------|-------------|------------|
| `harness/context.md` | ~350 | Context manifest (file ranking by plan/domain) |
| `harness/boot.md` | ~250 | Agent bootstrap & sandbox isolation |
| `harness/handoff.md` | ~300 | Agent session handoff protocol |
| `harness/resume.md` | ~250 | Agent resume orchestration |
| `harness/lint.md` | ~200 | Architecture & principles linting |
| `harness/evaluate.md` | ~300 | Full quality gate runner |
| `harness/task-lock.md` | ~200 | Cross-process task locking |
| `harness/telemetry.md` | ~250 | Telemetry aggregation |
| `harness/status.md` | ~200 | Pool / harness status dashboard |
| `agents-md-generator.md` | ~350 | ← this skill: regenerate this depth map |
| *(20 more in `.claude/commands/`)* | ~200 each | See full list: `ls .claude/commands/` |

---

### L2 — File-Level Comments  (budget: ~150–17,400 tokens per file)

Load individual files only when you need to edit or trace through their logic.
Start with the smallest file that covers your change; avoid loading siblings unless needed.

#### `harness_skills` — root helper modules

| File | Lines | Est. Tokens | Responsibility |
|------|-------|-------------|----------------|
| `harness_skills/handoff.py` | 796 | ~11,950 | `HandoffDocument`, `HandoffProtocol`, `SearchHints` — agent handoff |
| `harness_skills/task_lock.py` | 1,035 | ~15,550 | `TaskLock`, `TaskLockProtocol` — cross-process synchronisation |
| `harness_skills/stale_plan_detector.py` | 926 | ~13,900 | `detect_stale_plan`, `PlanTask` — out-of-sync plan detection |
| `harness_skills/boot.py` | 562 | ~8,450 | `BootConfig`, `IsolationConfig`, `boot_instance` — sandbox init |
| `harness_skills/resume.py` | 520 | ~7,800 | `load_plan_state`, `resume_agent_options` — session resume |
| `harness_skills/logging_config.py` | 495 | ~7,450 | `configure`, `get_logger`, `set_trace_id` — NDJSON logging provider |
| `harness_skills/telemetry_reporter.py` | 469 | ~7,050 | Telemetry aggregation CLI command |
| `harness_skills/error_aggregation.py` | 438 | ~6,600 | Error log query and aggregation |
| `harness_skills/performance_hooks.py` | 406 | ~6,100 | `PerformanceTracker` — latency / throughput hooks |
| `harness_skills/error_query_agent.py` | 377 | ~5,650 | `build_error_tools`, `run_error_query` — LLM error analysis |
| `harness_skills/effectiveness_stats.py` | 289 | ~4,350 | Effectiveness statistics aggregation |
| `harness_skills/pr_effectiveness.py` | 278 | ~4,200 | `ArtifactType`, `PRRecord` — PR effectiveness metrics |
| `harness_skills/dom_snapshot_skill.py` | 163 | ~2,450 | DOM snapshot façade — delegates to `dom_snapshot_utility` |

#### `harness_skills/gates` — evaluation gate runners

| File | Lines | Est. Tokens | Responsibility |
|------|-------|-------------|----------------|
| `harness_skills/gates/runner.py` | 1,159 | ~17,400 | `GateEvaluator`, `run_gates` — orchestrates all gate runs |
| `harness_skills/gates/security.py` | 1,009 | ~15,150 | Security compliance gate (SAST, secret scanning) |
| `harness_skills/gates/principles.py` | 845 | ~12,700 | Principles compliance gate |
| `harness_skills/gates/performance.py` | 795 | ~11,950 | Performance benchmark gate |
| `harness_skills/gates/docs_freshness.py` | — | — | `DocsFreshnessGate`, `DocsGateConfig` — staleness check |
| `harness_skills/gates/coverage.py` | — | — | `CoverageGate` — minimum-coverage enforcement |

#### `harness_skills/models` — Pydantic response schemas  (17 files, ~2,838 lines total)

| File | Est. Tokens | Responsibility |
|------|-------------|----------------|
| `models/base.py` | ~350 | `Status`, `Severity`, `GateResult`, `Violation` — foundation types |
| `models/evaluate.py` | ~500 | `EvaluateResponse`, `EvaluationSummary` |
| `models/gate_configs.py` | ~600 | `CoverageGateConfig`, per-gate config schemas |
| `models/context.py` | ~400 | `ContextManifest`, `RankedFile`, `SearchPattern` |
| `models/telemetry.py` | ~2,550 | `TelemetryReport` and related metrics models |
| `models/errors.py` | ~350 | Error and violation models |
| `models/lint.py` | ~350 | `LintResponse`, `LintViolation` |
| `models/lock.py` | ~300 | `TaskLockState` |
| `models/completion.py` | ~300 | `CompletionReport` |
| `models/create.py` | ~250 | `CreateResponse` |
| `models/update.py` | ~850 | `UpdateResponse` |

#### `dom_snapshot_utility` — DOM extraction

| File | Lines | Est. Tokens | Responsibility |
|------|-------|-------------|----------------|
| `dom_snapshot_utility/snapshot.py` | 558 | ~8,400 | Full DOM-to-struct extraction (headings, links, forms, tables, ARIA regions) |

#### `harness_dashboard` — scoring & display

| File | Lines | Est. Tokens | Responsibility |
|------|-------|-------------|----------------|
| `harness_dashboard/scorer.py` | 416 | ~6,250 | PR effectiveness scoring algorithm |
| `harness_dashboard/dashboard.py` | — | — | Rich terminal dashboard renderer |
| `harness_dashboard/data_generator.py` | — | — | Synthetic dataset generation for testing |
| `harness_dashboard/models.py` | 107 | ~1,600 | Dashboard Pydantic models |

#### `log_format_linter` — log validation

| File | Lines | Est. Tokens | Responsibility |
|------|-------|-------------|----------------|
| `log_format_linter/generator.py` | 432 | ~6,500 | NDJSON log sample generator |
| `log_format_linter/checker.py` | — | — | Per-entry field validation against SPEC.md rules |
| `log_format_linter/detector.py` | — | — | Framework auto-detection (Python, TypeScript, Go, Java) |
| `log_format_linter/cli.py` | — | — | `log-lint` CLI entry point |
| `log_format_linter/models.py` | 113 | ~1,700 | `LogEntry`, `LintViolation`, `LintReport` |

<details>
<summary>Tests (17+ files in <code>tests/</code>)</summary>

| Directory | Est. Tokens total | Coverage area |
|-----------|-------------------|---------------|
| `tests/browser/` | ~3,000 | Playwright e2e tests, `AgentDriver`, conftest fixtures |
| `tests/gates/` | ~5,000 | Gate runner unit tests |
| `tests/plugins/` | ~2,000 | Plugin gate system tests |
| `tests/test_generators/` | ~2,000 | Artifact generator tests |
| `tests/test_models/` | ~1,500 | Pydantic schema validation tests |
| `tests/test_cli/` | ~1,500 | CLI command tests |
| `tests/*.py` (root, 17 files) | ~8,000 | Misc unit tests for top-level modules |

</details>

---

### Token Budget Advisory

Typical context-window budgets and what fits:

| Budget | Recommended load strategy |
|--------|--------------------------|
| **8 k tokens** | L0 (README + ARCHITECTURE) + 1 domain L1 `__init__` |
| **32 k tokens** | All L0 + all L1 `__init__` files for your domain |
| **64 k tokens** | All L0 + all L1 + 3–5 targeted L2 source files |
| **128 k tokens** | All L0 + all L1 + full L2 for one domain (e.g. all `gates/`) |
| **200 k tokens** | Full repo load (all tiers) — only when doing cross-domain refactoring |

<!-- /harness:context-depth-map -->
