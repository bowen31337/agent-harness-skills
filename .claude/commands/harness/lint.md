# Harness Lint

Run **all architectural and golden-principle checks** in a single pass and emit a
structured `LintResponse` report. Covers import-layer violations, custom project
principles, and language-level lint rules — nothing else (no tests, no coverage,
no security scan).

Use this skill any time you want a fast, focused answer to: *"Does this code respect
the architecture and the project's golden rules?"*

---

## Instructions

### Step 0: Load custom principles

Read the project's principles file so we can cross-reference violations later:

```bash
cat .claude/principles.yaml 2>/dev/null || echo "__NONE__"
```

If the output is `__NONE__` or the file is absent, custom principles are not
configured — skip any principle-specific sections in the report silently.

Parse the YAML and extract **all principles** regardless of `applies_to` — this
skill is the authoritative architectural linter, so it enforces every rule.

---

### Step 1: Run the harness evaluation gates

Run **architecture**, **principles**, and **lint** gates via the harness CLI:

```bash
harness evaluate \
  --format json \
  --gate architecture \
  --gate principles \
  --gate lint \
  2>&1
```

> **Fallback** — if `harness` is not on `PATH`:
>
> ```bash
> uv run python -m harness_skills.cli.main evaluate \
>   --format json \
>   --gate architecture \
>   --gate principles \
>   --gate lint \
>   2>&1
> ```

Capture the full JSON output and parse it.  The schema is
`harness_skills/schemas/evaluation_report.schema.json`.

Key fields to extract:

| Field | Use |
|---|---|
| `passed` | Overall pass/fail |
| `summary.blocking_failures` | Count of must-fix violations |
| `summary.total_failures` | Total violation count |
| `gate_results[]` | Per-gate status + duration |
| `failures[]` | Flat list of all `GateFailure` objects |

Each `GateFailure` carries:
- `severity` — `error` \| `warning` \| `info`
- `gate_id` — `architecture` \| `principles` \| `lint`
- `rule_id` — the specific rule that fired
- `file_path` + `line_number` — location
- `message` — human-readable description
- `suggestion` — actionable fix hint

---

### Step 2: Merge with custom principles

For each principle loaded in Step 0, scan the failures list for matching violations
(match on `gate_id == "principles"` and `rule_id` or `message` containing the
principle `id`).

If no failure maps to a principle, mark it as `✅ PASS`.
If a matching failure exists, mark it with the appropriate severity icon:

| `severity` | Icon |
|---|---|
| `error` | 🔴 BLOCKING |
| `warning` | 🟡 WARNING |
| `info` | 🔵 INFO |

---

### Step 3: Render the lint report

Output a structured report in this format:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Harness Lint — <PASS ✅ | FAIL ❌>
  <N> violation(s)  ·  <B> blocking  ·  <W> warnings  ·  <I> info
  Gates: architecture · principles · lint
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Gate Summary
────────────────────────────────────────────────────
  architecture  <PASSED|FAILED>  <N ms>  <K failure(s)>
  principles    <PASSED|FAILED>  <N ms>  <K failure(s)>
  lint          <PASSED|FAILED>  <N ms>  <K failure(s)>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

If there are **blocking violations** (`severity == "error"`), add a blocking
section **before** warnings:

```
🔴 BLOCKING — Must fix before merge
────────────────────────────────────────────────────
  [architecture] ARCH001 · src/api/views.py:88
  "Direct import of db.session in view layer violates layer isolation"
  → Move query into a repository function and import that instead.

  [principles] P001 · src/api/views.py:88
  "All database queries must go through the repository layer"
  → Refactor: call UserRepository.get_by_id() rather than querying db directly.
```

If there are **warnings** (`severity == "warning"`):

```
🟡 SUGGESTIONS — Nice to have
────────────────────────────────────────────────────
  [lint] RUF013 · src/utils/helpers.py:12
  "Use `X | None` instead of `Optional[X]`"
  → Replace Optional[str] with str | None (Python 3.10+ union syntax).
```

If there are **info** items (`severity == "info"`):

```
🔵 INFO
────────────────────────────────────────────────────
  [principles] P005 · (no specific file)
  "Prefer dataclasses over plain dicts for structured data"
  → Consider converting dict return values in src/models/ to @dataclass.
```

If **all gates pass**:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅ All architectural and principle checks passed.
  0 violations · 3 gates · <N> rules applied
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### Step 4: Principles checklist

If `.claude/principles.yaml` was loaded in Step 0, always append a principles
checklist so reviewers can see every rule's status at a glance:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Project Principles — <N> loaded
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  P001 [architecture / blocking]
       "All database queries must go through the repository layer"
       → 🔴 BLOCKING — src/api/views.py:88 violates this rule

  P002 [testing / blocking]
       "Every public API endpoint must have an integration test"
       → ✅ PASS

  P003 [style / suggestion]
       "Prefer dataclasses over plain dicts for structured data"
       → ⏭  SKIP — no changed files match this principle
```

Rules:
- Show **all** principles, not just the failing ones.
- `blocking` + violation → 🔴 BLOCKING (upgrades overall result to FAIL).
- `suggestion` + violation → 🟡 WARNING (does not block, but is shown).
- No violation found → ✅ PASS.
- Principle not applicable to any changed/scanned file → ⏭ SKIP.

---

### Step 5: Emit structured data (agent-readable)

After the human-readable report, emit the raw `LintResponse` as a fenced JSON
block so downstream agents can parse it without re-running the gates:

```json
{
  "command": "harness lint",
  "passed": false,
  "message": "2 blocking violation(s) — architecture, principles",
  "total_violations": 4,
  "critical_count": 0,
  "error_count": 2,
  "warning_count": 1,
  "info_count": 1,
  "files_checked": 23,
  "rules_applied": ["ARCH001", "ARCH002", "P001", "P002", "P003", "RUF013"],
  "violations": [
    {
      "rule_id": "ARCH001",
      "severity": "error",
      "file_path": "src/api/views.py",
      "line": 88,
      "message": "Direct import of db.session in view layer violates layer isolation",
      "suggestion": "Move query into a repository function and import that instead."
    }
  ]
}
```

The schema matches `harness_skills.models.lint.LintResponse` (a `HarnessResponse`
subclass).  Consumers should check `passed` first, then iterate `violations`
ordered by `severity` descending (`error` → `warning` → `info`).

---

### Step 6: Exit behaviour

| Outcome | Exit code |
|---|---|
| All gates passed | `0` |
| Any `error`-severity violation | `1` |
| Gate runner internal error | `2` |

---

## Options

| Flag | Effect |
|---|---|
| `--gate architecture` | Run only the architecture gate (skip principles + lint) |
| `--gate principles` | Run only the principles gate |
| `--gate lint` | Run only the lint gate |
| `--no-principles` | Skip loading `.claude/principles.yaml` and the principles checklist |
| `--project-root PATH` | Override the repository root (default: `.`) |
| `--format json` | Emit only the raw JSON `LintResponse` with no human-readable header |

Multiple `--gate` flags may be combined (same semantics as `harness evaluate --gate`).

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Quick architectural + principles sweep | **`/harness:lint`** ← you are here |
| Full quality gate (tests, coverage, security, …) | `/harness evaluate` or `/check-code` |
| Add / edit / remove principles | `/define-principles` |
| Review a PR for principle compliance | `/review-pr` |

---

## Notes

- This skill is **read-only** — it never auto-fixes code.  To apply lint fixes
  automatically, run `uv run ruff check . --fix && uv run ruff format .` separately.
- The `architecture` gate uses static AST analysis; it does not execute the code.
- Principles enforcement is text-based: the gate scans source files for patterns
  that match or violate each rule.  It will not catch every possible violation, but
  it will catch the most common structural ones.
- To update which principles are enforced, run `/define-principles`.
- This file should be committed to version control so the whole team shares the
  same lint configuration.
