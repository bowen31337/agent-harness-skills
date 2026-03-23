# AGENTS.md — tests/

## Purpose

Test suite for the entire agent-harness-skills framework. Covers unit tests for all packages (`models`, `gates`, `generators`, `plugins`, `cli`), integration tests for the plugin gate system, and Playwright-based end-to-end browser tests. All tests run via `pytest`.

---

## Key Files

| Path | What it tests |
|------|--------------|
| `browser/agent_driver.py` | `AgentDriver` — context-manager Playwright wrapper with auto-cleanup |
| `browser/screenshot_helper.py` | `capture_screenshot`, `visit_and_capture` helpers |
| `browser/conftest.py` | Autouse fixture: captures full-page PNG on any browser test failure → `screenshots/failures/<test-nodeid>.png` |
| `test_models/test_create_response.py` | `CreateResponse` / `CreateConfigResponse` Pydantic validation |
| `test_models/test_manifest.py` | `ManifestValidateResponse` and `ManifestValidationError` |
| `test_models/test_observe.py` | `LogEntry` and `ObserveResponse` |
| `test_models/test_performance.py` | Performance-related model validation |
| `test_cli/test_create_cmd.py` | `harness create` CLI command |
| `test_cli/test_status_cmd.py` | `harness status` CLI command |
| `test_cli/test_verbosity.py` | `VerbosityLevel`, `get_verbosity`, `vecho` |
| `test_cli/test_context_cmd.py` | `harness context` CLI command |
| `test_cli/test_completion_report.py` | `harness completion-report` CLI command |
| `test_generators/test_evaluation.py` | `EvaluationReport`, `run_all_gates` |
| `test_generators/test_config_generator.py` | Config generation artifact |
| `test_generators/test_manifest_generator.py` | Manifest generation |
| `gates/test_coverage.py` | `CoverageGate` with XML/JSON/lcov inputs |
| `gates/test_docs_freshness.py` | `DocsFreshnessGate` staleness logic |
| `gates/test_runner_plugin_integration.py` | `GateEvaluator` + plugin runner integration |
| `plugins/test_gate_plugin.py` | `PluginGateConfig` validation |
| `plugins/test_loader.py` | `load_plugin_gates` from YAML |
| `plugins/test_runner.py` | `run_plugin_gates` execution |
| `plugins/test_integration.py` | Full plugin round-trip |
| `test_boot.py` | `BootConfig`, `BootResult`, sandbox isolation |
| `test_handoff.py` | `HandoffDocument`, `HandoffTracker`, append-only semantics |
| `test_task_lock.py` | `TaskLock` acquire/release/conflict scenarios |
| `test_stale_plan_detector.py` | `detect_stale_plan` edge cases |
| `test_error_aggregation.py` | `aggregate_errors`, `load_errors_from_log` |
| `test_telemetry.py` / `test_telemetry_reporter.py` | Telemetry pipeline |
| `test_perf_hooks.py` | `PerformanceTracker` timer lifecycle |
| `test_progress_log.py` | Progress log append semantics |
| `test_log_format_linter.py` | `check_file`, `detect_framework`, `generate_rules` |
| `test_health_check_endpoint.py` | Health-check HTTP endpoint contract |
| `test_scorer.py` | `compute_scores` effectiveness scoring |
| `test_exec_plan.py` | Execution plan tracking |
| `test_git_checkpoint.py` | Git checkpoint utilities |

---

## Internal Patterns

- **pytest + pytest-playwright** — all tests use `pytest`; browser tests additionally require `pytest-playwright` and a Chromium binary.
- **`AgentDriver` as context manager** — browser tests must use `with AgentDriver.launch() as driver:`; never instantiate without the context manager.
- **Failure screenshots auto-captured** — `conftest.py` autouse fixture writes `screenshots/failures/<test-nodeid>.png` on any browser test failure; attach this dir as a CI artifact.
- **`BASE_URL` override** — browser and integration tests respect `BASE_URL` env var (default `http://localhost:3000`) for environment targeting.
- **Isolation via tmp directories** — tests that write files must use `tmp_path` (pytest fixture) or `tempfile.TemporaryDirectory`; never write to the repo root.
- **Mock LLM calls** — tests touching `error_query_agent` must mock `run_error_query`; no live Anthropic API calls in the test suite.

---

## Domain-Specific Constraints

- **Never import private symbols (`_`-prefixed) across package boundaries in tests** — currently 39 known violations tracked in `ARCHITECTURE.md`; do not add more.
- **Browser tests in `tests/browser/` only** — Playwright imports must not appear outside this subdirectory.
- **`screenshots/` and `videos/` are gitignored** — never commit files from these directories, even if a test produces them.
- **Run browser tests headed locally only** — `pytest tests/browser/ --headed` is for local debugging; CI always runs headless.
- **Test commands:**
  ```bash
  pytest tests/ -v                        # all tests
  pytest tests/browser/ -v               # browser e2e only
  pytest tests/browser/ --headed         # headed (local debug)
  BASE_URL=https://staging.example.com pytest tests/browser/ -v
  ```
