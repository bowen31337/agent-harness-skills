<!-- harness:auto-generated — do not edit this block manually -->
last_updated: 2026-03-22
head: 7fd8d5d
artifact: evaluation
<!-- /harness:auto-generated -->

# Evaluation Report

> Last run: 2026-03-22 00:00:00Z  ·  Branch: feat/golden-principl-skill-generates-import-ordering-and-gro  ·  SHA: 7fd8d5d

## Summary

| Metric | Value |
|---|---|
| Result | ✅ PASS |
| Gates run | 3 |
| Passed | 3 |
| Failed | 0 |
| Skipped | 6 |
| Blocking failures | 0 |
| Total violations | 0 |

## Gate Results

| Gate | Status | Duration | Failures |
|---|---|---|---|
| regression | ✅ | ~90ms | 0 |
| coverage | ✅ | ~170ms | 0 (98% on `import_convention_detector`) |
| lint | ✅ | ~200ms | 0 |
| security | ⏭ | — | — |
| performance | ⏭ | — | — |
| architecture | ⏭ | — | — |
| principles | ⏭ | — | — |
| docs_freshness | ⏭ | — | — |
| types | ⏭ | — | — |

## Notes

- **53/53 tests pass** across all test classes:
  `TestIsSorted`, `TestAnalyseFile`, `TestDetectImportConventions`,
  `TestGenerateImportPrinciple`, `TestDetectThenGenerate`
- **98% line coverage** on `harness_skills/generators/import_convention_detector.py`
  (only lines 91–92 and 218–219 uncovered — early-exit / dead-code branches)
- **Lint clean** — all 6 ruff violations resolved:
  `I001` import ordering, `UP035` `collections.abc` migration,
  `B007` unused loop variable, `B905` × 2 `zip(strict=False)`, `SIM102` combined `if`
