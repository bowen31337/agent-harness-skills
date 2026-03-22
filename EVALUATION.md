<!-- harness:auto-generated — do not edit this block manually -->
last_updated: 2026-03-22
head: 157af7b
artifact: evaluation
<!-- /harness:auto-generated -->

# Evaluation Report

> Last run: 2026-03-22 18:58:35Z  ·  Branch: main  ·  SHA: 157af7b

## Summary

| Metric | Value |
|---|---|
| Result | ❌ FAIL |
| Gates run | 9 |
| Passed | 1 |
| Failed | 3 |
| Skipped | 5 |
| Blocking failures | 2 |
| Total violations | 5191 |

## Gate Results

| Gate | Status | Duration | Failures |
|---|---|---|---|
| regression | ❌ FAILED | ~16000ms | 66 |
| coverage | ❌ FAILED | ~17000ms | 1 |
| security | ⏭ SKIPPED | — | 0 |
| performance | ⏭ SKIPPED | — | 0 |
| architecture | ⏭ SKIPPED | — | 0 |
| principles | ⏭ SKIPPED | — | 0 |
| docs_freshness | ✅ PASSED | ~5ms | 0 |
| types | ⏭ SKIPPED | — | 0 |
| lint | ❌ FAILED | ~5000ms | 5124 |

## Blocking Violations

### [regression] Merge conflict in test_task_lock.py
- **File:** `tests/test_task_lock.py:516`
- **Rule:** SyntaxError — merge conflict markers left in source
- **Fix:** Resolve the outstanding git merge conflict before tests can be collected.

### [regression] ImportError in gates runner
- **File:** `tests/gates/test_docs_freshness.py`
- **Rule:** ImportError — `BaseGateConfig` missing from `harness_skills.models.gate_configs`
- **Fix:** Add or re-export `BaseGateConfig` from `harness_skills/models/gate_configs.py`.

### [regression] 6 additional collection failures
- **Files:** `tests/gates/test_coverage.py`, `tests/gates/test_runner_plugin_integration.py`, `tests/test_cli/test_completion_report.py`, `tests/test_cli/test_manifest_cmd.py`, `tests/test_cli/test_output_format.py`, `tests/test_cli/test_verbosity.py`
- **Fix:** Resolve the root `SyntaxError` and `ImportError` above — these likely cascade.

### [regression] 58 test failures
- **Clusters:** `test_dom_snapshot.py` (21), `test_observe.py` (4), `test_evaluation.py` (4), `test_integration.py` (1), others (28)
- **Fix:** Run `python -m pytest tests/test_dom_snapshot.py --tb=short` to diagnose the largest cluster first.

### [coverage] 23% line coverage — below 80% threshold
- **Uncovered:** 3390 of 4420 lines
- **Fix:** Add tests for `harness_skills/gates/`, `harness_skills/cli/`, and `harness_skills/generators/`.

## Advisory Warnings

### [lint] 5124 lint violations (non-blocking)
- **Top rules:** `invalid-syntax` (2075), `f-string-missing-placeholders` (620), `non-pep604-annotation-optional` (512), `unsorted-imports` (433)
- **Fix:** Run `python -m ruff check . --fix` to auto-fix 2070 violations. Resolve merge conflicts first — many `invalid-syntax` hits are conflict markers.
