<!-- harness:auto-generated — do not edit this block manually -->
last_updated: 2026-03-22
head: 27f437b
artifact: evaluation
<!-- /harness:auto-generated -->

# Evaluation Report

> Profile: `starter` · Config: `harness.config.yaml`
> Last run: 2026-03-22  ·  Branch: feat/evaluation-gate-skill-generates-an-evaluation-md-defini  ·  SHA: 27f437b

---

## PR Completion Criteria

All agents **must** satisfy the following criteria before opening a pull request.
Items marked 🔴 **BLOCKING** prevent merge; 🟡 **ADVISORY** items are strongly recommended.

| # | Gate | Requirement | Severity |
|---|---|---|---|
| 1 | **regression** | All tests pass — zero failures in the full suite | 🔴 BLOCKING |
| 2 | **coverage** | Project-wide line coverage ≥ **80 %** | 🔴 BLOCKING |
| 3 | **docs_freshness** | `AGENTS.md` updated within the last **30 days** | 🔴 BLOCKING |
| 4 | **lint** | No ruff violations (non-blocking; advisory warnings only) | 🟡 ADVISORY |

> Gates disabled in the `starter` profile and therefore **not** required for this PR:
> `security`, `performance`, `architecture`, `principles`, `types`
>
> Upgrade to the `standard` or `advanced` profile in `harness.config.yaml` to enable them.

---

### Criteria Definitions

#### 1. Regression Gate — 🔴 BLOCKING

| Setting | Value |
|---|---|
| Tool | `pytest` |
| Timeout | 120 s |
| `fail_on_error` | `true` |

**Requirement:** `pytest tests/` must exit with code `0` — no test may fail or error.

**How to verify:**
```bash
pytest tests/ -v
```

**Fix:** Resolve all failing tests before opening a PR. Do not `xfail` or skip tests to
work around failures without understanding their root cause.

---

#### 2. Coverage Gate — 🔴 BLOCKING

| Setting | Value |
|---|---|
| Tool | `pytest-cov` (auto-detected) |
| Threshold | **80 %** line coverage |
| Branch coverage | `false` (line-only for starter) |
| `fail_on_error` | `true` |

**Requirement:** Project-wide line coverage reported by `pytest --cov` must be ≥ 80 %.

**How to verify:**
```bash
pytest --cov=harness_skills --cov-report=term-missing tests/
```

**Fix:** Add tests for uncovered lines. Never reduce coverage below the threshold —
not even temporarily. Exclude files via `harness.config.yaml → coverage.exclude_patterns`
only when there is a documented reason.

---

#### 3. Docs Freshness Gate — 🔴 BLOCKING

| Setting | Value |
|---|---|
| Tracked files | `AGENTS.md` |
| Max staleness | **30 days** |
| `fail_on_error` | `true` |

**Requirement:** Every file listed under `docs_freshness.tracked_files` must have a
`last_updated` date within the past 30 days.

**How to verify:**
```bash
harness evaluate --gate docs_freshness
# or:
uv run python -m harness_skills.cli.main evaluate --gate docs_freshness
```

**Fix:** If `AGENTS.md` is stale, update its content and refresh its
`<!-- harness:auto-generated -->` block, or run `/harness:update` to regenerate it.

---

#### 4. Lint Gate — 🟡 ADVISORY (non-blocking)

| Setting | Value |
|---|---|
| Tool | `ruff` |
| `fail_on_error` | `false` |
| Auto-fix | `false` |

**Requirement:** No ruff violations are emitted. This gate is advisory — a lint failure
will **not** block merge, but violations should be addressed before the PR is reviewed.

**How to verify:**
```bash
uv run ruff check .
uv run ruff format --check .
```

**Auto-fix (optional):**
```bash
uv run ruff check . --fix
uv run ruff format .
```

---

## Merge Readiness Decision Table

| Blocking failures | Warnings / Advisory | Decision |
|---|---|---|
| 0 | 0 | ✅ **Ready to merge** |
| 0 | > 0 | 🟡 **May merge** — address warnings before review |
| > 0 | any | 🔴 **Not ready** — fix all blocking violations first |

---

## Summary

| Metric | Value |
|---|---|
| Result | ❌ FAIL |
| Gates run | 4 |
| Passed | 1 |
| Failed | 2 |
| Skipped | 1 |
| Blocking failures | 57 |
| Total violations | 583 |
| Branch | feat/evaluation-gate-skill-generates-an-evaluation-md-defini |
| SHA | 27f437b |
| Generated at | 2026-03-22 |

---

## Gate Results

| Gate | Status | Duration | Failures |
|---|---|---|---|
| regression | ❌ FAILED | 3120 ms | 57 |
| coverage | ⏭ skipped (no coverage data) | — | 0 |
| docs_freshness | ✅ PASSED | 5 ms | 0 |
| lint | ❌ FAILED (advisory) | 1800 ms | 526 |
| security | ⏭ disabled (starter) | — | — |
| performance | ⏭ disabled (starter) | — | — |
| architecture | ⏭ disabled (starter) | — | — |
| principles | ⏭ disabled (starter) | — | — |
| types | ⏭ disabled (starter) | — | — |

### 🔴 Blocking Violations — Must fix before merge

```
[regression] · tests/test_task_lock.py:516
"SyntaxError: merge conflict markers (||||||| 817eb11) make this file
unparseable — the file was never fully resolved after a git merge."
→ Remove all conflict markers (<<<<<<, =======, |||||||, >>>>>>>) and keep
  only the intended final content; then re-run pytest.

[regression] · tests/gates/test_coverage.py (collection error)
"ImportError: cannot import name 'BaseGateConfig' from
'harness_skills.models.gate_configs'"
→ Add BaseGateConfig to harness_skills/models/gate_configs.py (or alias the
  name that runner.py expects), then verify the import chain resolves cleanly.

[regression] · tests/gates/test_runner_plugin_integration.py (collection error)
"ImportError: cannot import name 'BaseGateConfig' from
'harness_skills.models.gate_configs' (same root cause)"
→ Same fix as above — resolving BaseGateConfig will unblock all three
  affected test modules at once.

[regression] · tests/gates/test_docs_freshness.py (collection error)
"ImportError: cannot import name 'BaseGateConfig' from
'harness_skills.models.gate_configs' (same root cause)"
→ Same fix as above.

[regression] · tests/test_dom_snapshot.py (25 failures)
"Multiple assertions fail in TestImages, TestVisibleText, TestSnapshotToText,
TestSnapshotFromUrl, TestSkillWrappers, and TestAriaLandmarks — the
DomSnapshot implementation does not match what the test suite expects."
→ Review the recent changes to harness_skills/dom_snapshot.py (or the
  equivalent module) and align the implementation with the contracts the
  tests define, or update the tests if the contract itself changed.

[regression] · tests/test_generators/test_evaluation.py (4 failures)
"TestFormatReport tests fail — format_report() does not return valid JSON
or is missing required keys (schema_version, gate_results, failures, etc.)."
→ Ensure the EvaluationReport generator in harness_skills/generators/
  evaluation.py produces output that matches evaluation_report.schema.json.
```

### 🟡 Warnings — Advisory

```
[lint] · (global — 526 violations across the codebase)
"ruff found 526 style/quality violations. Highlights include:
  PTH123 open() should be replaced by Path.open() (.harness/perf_summary.py:13)
  PTH120 os.path.dirname() should be replaced by Path.parent (checkpoint_agent.py:62)
  PTH100 os.path.abspath() should be replaced by Path.resolve() (checkpoint_agent.py:62)
  I001   Import block is un-sorted or un-formatted (multiple files)"
→ Run: uv run ruff check . --fix && uv run ruff format .
  Review any remaining violations that require manual fixes.
```

---

<!-- CUSTOM-START -->
<!-- Add any project-specific notes or exceptions below this line.
     This section is preserved verbatim when /harness:evaluate regenerates the file. -->
<!-- CUSTOM-END -->
