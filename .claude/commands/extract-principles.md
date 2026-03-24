---
name: extract-principles
description: "Recurring code pattern miner that extracts candidate golden principles with frequency data. Scans source files across multiple categories (async/await, error-handling, naming, testing, type-safety, logging, architecture) and counts how often each structural or stylistic pattern recurs across the codebase. For each pattern that clears a configurable frequency threshold it generates a candidate principle entry — complete with file count, percentage, confidence tier, and representative examples — and writes the results to docs/candidate-principles.yaml for human review before promotion to .claude/principles.yaml. Use when: (1) bootstrapping principles for a new or under-documented project, (2) auditing whether current principles cover the patterns actually present in the codebase, (3) discovering emergent conventions that have not yet been codified, (4) periodically refreshing the principles backlog with recently introduced patterns. Triggers on: extract principles, mine patterns, discover principles, candidate principles, recurring patterns, frequency analysis, pattern frequency, codebase conventions, audit principles, bootstrap principles."
---

# Extract Principles

Scans the codebase for **recurring code patterns** across multiple categories, ranks them by
frequency, and generates **candidate golden principles** with supporting frequency data.
Candidates are written to `docs/candidate-principles.yaml` for human review; use
`/define-principles --from-file` to promote approved candidates into `.claude/principles.yaml`.

---

## Workflow

**Full scan — detect all pattern categories and write candidates?**
→ [Default flow](#instructions) — runs all detectors → frequency ranking → write candidates

**Preview candidates without writing any files?**
→ `/extract-principles --dry-run`

**Scan only specific categories?**
→ `/extract-principles --category async,error-handling,naming`

**Raise or lower the frequency threshold before a pattern becomes a candidate?**
→ `/extract-principles --min-pct 60`   (default: 40 %)

**Print ranked frequency stats only, skip candidate generation?**
→ `/extract-principles --stats-only`

**Auto-promote all HIGH-confidence candidates directly into `.claude/principles.yaml`?**
→ `/extract-principles --auto-promote`

---

## Usage

```bash
# Full scan of current directory (default)
/extract-principles

# Target a sub-directory
/extract-principles --dir src/

# Scan only async and error-handling patterns
/extract-principles --category async,error-handling

# Require at least 60 % of files to exhibit a pattern before it becomes a candidate
/extract-principles --min-pct 60

# Require at least N sample files before trusting a pattern (default: 5)
/extract-principles --min-files 5

# Preview candidates without writing docs/candidate-principles.yaml
/extract-principles --dry-run

# Print frequency stats only; do not generate candidates
/extract-principles --stats-only

# Auto-promote HIGH-confidence candidates into .claude/principles.yaml
/extract-principles --auto-promote

# Write candidates to a custom output path
/extract-principles --output path/to/candidates.yaml

# Append new candidates to an existing candidate file instead of replacing it
/extract-principles --merge

# Set explicit ID prefix for auto-promoted candidates (default: next P-series)
/extract-principles --id-prefix CAND
```

---

## Instructions

### Step 1 — Parse arguments

```
scan_dir    = args["--dir"]          or "."
categories  = args["--category"]     or "all"   # comma-separated; "all" = every category
min_pct     = float(args["--min-pct"]  or 40.0) # minimum frequency % for candidacy
min_files   = int(args["--min-files"]  or 5)    # minimum sample size
dry_run     = "--dry-run"     in args
stats_only  = "--stats-only"  in args
auto_promote= "--auto-promote" in args
output      = args["--output"] or "docs/candidate-principles.yaml"
merge       = "--merge" in args
id_prefix   = args["--id-prefix"] or ""  # empty = auto-assign P-series on promote
```

If `categories` is not `"all"`, split into a list:
```python
active_categories = [c.strip() for c in categories.split(",")]
```

Supported category names: `async`, `error-handling`, `naming`, `testing`,
`type-safety`, `logging`, `architecture`, `style`.

---

### Step 2 — Collect source files

```bash
find <scan_dir> \
  -type f \
  \( -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.go" \) \
  -not -path "*/node_modules/*" \
  -not -path "*/.venv/*" \
  -not -path "*/__pycache__/*" \
  -not -path "*/.git/*" \
  -not -path "*/dist/*" \
  -not -path "*/build/*" \
  -not -path "*/.tox/*" \
  2>/dev/null
```

Count totals by extension:

```
total_files   = len(all_files)
python_files  = [f for f in all_files if f.endswith(".py")]
ts_files      = [f for f in all_files if f.endswith((".ts", ".tsx"))]
js_files      = [f for f in all_files if f.endswith(".js")]
go_files      = [f for f in all_files if f.endswith(".go")]
```

If `total_files < min_files`, print a warning:

```
⚠️  Only <N> source files found under '<scan_dir>'.
   Results may not be statistically representative.
   Use --min-files 1 to proceed anyway, or --dir to target a larger directory.
```

and exit 0 if `total_files == 0`.

---

### Step 3 — Run pattern detectors

Run each active detector below.  Each detector returns a list of
`PatternResult` objects:

```
PatternResult:
  category      : str              # e.g. "async"
  pattern_id    : str              # stable slug, e.g. "async-await-usage"
  description   : str              # one-line human summary
  files_matched : list[str]        # file paths where the pattern was found
  files_scanned : int              # total files in scope for this detector
  frequency_pct : float            # len(files_matched) / files_scanned * 100
  representative_examples: list[str]  # up to 3 "file:line — snippet" strings
  candidate_rule: str              # draft principle text (imperative mood)
  confidence    : str              # "LOW" | "MEDIUM" | "HIGH"
```

**Confidence tiers:**

| Tier   | Condition |
|--------|-----------|
| HIGH   | frequency_pct ≥ 70 % AND files_matched ≥ 10 |
| MEDIUM | frequency_pct ≥ 40 % AND files_matched ≥ 5 |
| LOW    | frequency_pct < 40 % OR files_matched < 5 |

Only patterns with `frequency_pct ≥ min_pct` AND `files_matched ≥ min_files`
are included in the candidate output (all patterns are shown in the stats table).

---

#### Detector A — `async` category (Python)

Scan `python_files`.

| Pattern ID | Detection heuristic | Candidate rule (when True) |
|---|---|---|
| `async-await-usage` | File contains `async def` | All I/O-bound functions must be declared `async def` and awaited at call sites. |
| `anyio-over-asyncio` | File imports `anyio` or uses `anyio.run` / `anyio.to_thread` | All async entry-points must use `anyio.run()` instead of `asyncio.run()` so the codebase remains backend-agnostic. |
| `asyncio-lock-shared-state` | File contains `asyncio.Lock()` | All mutable state shared between coroutines must be protected by an `asyncio.Lock` acquired with `async with`. |
| `graceful-shutdown-event` | File contains `asyncio.Event()` and `_stop_event` or `stop_event` | Background poll loops must implement graceful shutdown using an `asyncio.Event` stop-flag rather than a bare `while True: await asyncio.sleep()`. |
| `httpx-async-client` | File imports `httpx` and contains `AsyncClient` | All outbound HTTP calls in async code must use `httpx.AsyncClient` with an explicit `timeout` parameter. |
| `no-blocking-in-async` | File contains `requests.get\|requests.post\|time.sleep` inside a function also containing `async def` | Blocking calls (`requests.*`, `time.sleep`, synchronous file I/O) are forbidden inside `async def` functions; offload with `await anyio.to_thread.run_sync`. |

---

#### Detector B — `error-handling` category (Python)

Scan `python_files`.

| Pattern ID | Detection heuristic | Candidate rule (when True) |
|---|---|---|
| `structured-exceptions` | File defines a class inheriting from a base error (e.g. `AppError`, `HarnessError`, `BaseException` subclass with `code` or `message` fields) | All application errors must subclass a common base exception and carry `code`, `message`, and `context` fields. |
| `raise-from-cause` | File contains `raise .* from ` | When catching and re-raising an exception, always use `raise NewError(...) from original_exc` to preserve the cause chain. |
| `no-bare-except` | File does NOT contain `except Exception:` or `except:` without narrowing | Do not catch bare `Exception`; catch the most specific exception type applicable and let unhandled errors propagate to the top-level handler. |
| `error-code-enum` | File defines a `StrEnum` or `Enum` with members matching `[A-Z_]+` and contains the word `error` or `Error` in the class name | Error codes must be declared as members of an `ErrorCode` `StrEnum`; never inline raw error code strings in business logic or test assertions. |
| `typed-error-context` | Files that raise structured errors include `context: dict` or `context={}` in the raise site | Every structured exception must include a `context` dict with at minimum the entity ID and operation name so log aggregators can correlate errors automatically. |

---

#### Detector C — `naming` category (Python)

Scan `python_files`.

| Pattern ID | Detection heuristic | Candidate rule (when True) |
|---|---|---|
| `get-set-is-has-prefixes` | File contains functions starting with `get_`, `is_`, `has_`, or `set_` | Accessor/predicate functions must use the `get_*`, `is_*`, `has_*`, `set_*` prefix convention to communicate intent and side-effect contract at a glance. |
| `private-leading-underscore` | File contains methods or functions matching `_[a-z][a-z0-9_]+` (single-underscore private) | Internal helpers not part of a module's public API must carry a single leading underscore to signal that callers outside the module should not depend on them. |
| `class-role-suffix` | Classes in file end with `Config`, `Gate`, `Runner`, `Evaluator`, `Record`, `Lock`, `Reporter`, `Response`, or `Error` | Class names must carry a role-reflecting suffix (e.g. `*Config`, `*Gate`, `*Runner`) so the class's responsibility is clear from its name alone. |
| `id-suffix-on-identifiers` | Fields or variables named `<noun>_id` (e.g. `task_id`, `plan_id`, `agent_id`) appear more than the bare `id` as a non-primary-key field | All foreign-key and reference identifier fields must use the `_id` suffix (e.g. `task_id`, not `task` or `taskId`). |
| `upper-snake-constants` | File contains module-level identifiers matching `[A-Z][A-Z0-9_]{2,}` = ... | Module-level constants must use `UPPER_SNAKE_CASE`; private constants must additionally carry a leading underscore (`_UPPER_SNAKE_CASE`). |

---

#### Detector D — `testing` category (Python)

Scan `python_files` filtered to `tests/` subdirectories or files matching `test_*.py` / `*_test.py`.

| Pattern ID | Detection heuristic | Candidate rule (when True) |
|---|---|---|
| `aaa-structure` | Test functions contain two or more blank lines separating logical blocks | All tests must follow the Arrange-Act-Assert (AAA) structure with a blank line separating each phase. |
| `test-name-pattern` | Test functions match `test_<unit>_<scenario>_<expected>` (at least three `_`-separated segments) | Test function names must follow `test_<unit>_<scenario>_<expected_outcome>` so the failure message alone communicates what broke. |
| `narrow-fixture-scope` | `@pytest.fixture` decorators do not include `scope="session"` or `scope="module"` | Fixtures must be scoped as narrowly as possible (`function` > `class` > `module` > `session`); session-scoped fixtures that mutate shared state are forbidden. |
| `mock-at-boundary` | `patch(` targets are external library paths (e.g. `requests`, `httpx`, `subprocess`) not internal module paths | Mocks must only be applied at the boundary of the unit under test (HTTP client, subprocess, file I/O); mocking internal helpers couples tests to implementation. |
| `no-duplicate-literals` | The same string literal (len ≥ 10) appears in more than one test function | Test-only string constants must be extracted to the top of the test file or to `tests/constants.py`; no string literal may appear in more than one test. |

---

#### Detector E — `type-safety` category (Python)

Scan `python_files`.

| Pattern ID | Detection heuristic | Candidate rule (when True) |
|---|---|---|
| `return-type-annotations` | Public functions (no leading underscore) in file contain `->` return type annotation | All public functions and methods must declare an explicit return type annotation. |
| `parameter-type-annotations` | Function signatures in file include `: <type>` for at least 70 % of parameters | All function parameters must carry explicit type annotations; `Any` is permitted only when the type genuinely cannot be constrained. |
| `pydantic-over-plain-dict` | File imports `BaseModel` or `dataclass` and avoids returning naked `dict` literals with more than 3 keys | Prefer Pydantic `BaseModel` or `dataclasses.dataclass` over plain `dict` for any structured value returned from or passed between functions. |
| `future-annotations-first` | `from __future__ import annotations` is the first import in every Python module that has type annotations | Every Python module that uses type annotations must start with `from __future__ import annotations` to enable deferred evaluation and avoid forward-reference issues. |

---

#### Detector F — `logging` category (Python)

Scan `python_files`.

| Pattern ID | Detection heuristic | Candidate rule (when True) |
|---|---|---|
| `module-level-logger` | File contains `logger = logging.getLogger(__name__)` or `logger = get_logger(...)` at module scope (not inside a function) | Loggers must be obtained at module scope using `logger = get_logger(__name__)` (or `logging.getLogger(__name__)`), never inside a function body. |
| `no-print-in-production` | Files outside `tests/` do NOT contain `print(` or `sys.stdout.write(` | `print()` and `sys.stdout.write()` are forbidden in production code; all diagnostic output must go through the structured logger. |
| `structured-extra-fields` | Log calls pass keyword arguments via `extra={}` or use a structured logger that accepts `**kwargs` | Structured log fields beyond `level`, `ts`, and `msg` must be passed in the `extra={}` dict, not interpolated into the message string, so they are machine-parseable. |
| `trace-id-propagation` | File references `trace_id` in log calls or imports a `set_trace_id` / `get_trace_id` helper | Every log record in a request/task context must include a `trace_id` field propagated from the incoming context for end-to-end log correlation. |

---

#### Detector G — `architecture` category (Python)

Scan `python_files`.

| Pattern ID | Detection heuristic | Candidate rule (when True) |
|---|---|---|
| `imports-from-package-root` | Imports of sibling packages go through `<pkg>.__init__` not `<pkg>.<module>` (no deep imports) | All cross-package imports must go through the package root (`from harness_skills.models import X`), never directly from a sub-module (`from harness_skills.models.base import X`). |
| `validation-at-boundary` | `BaseModel` or Pydantic parse calls appear in route/handler/adapter code but not in domain service methods | Data validation must occur exclusively at system boundaries (request handlers, external adapters); domain services must receive already-validated typed objects. |
| `no-os-environ-in-domain` | `os.environ.get` or `os.getenv` calls appear only in bootstrap/entry-point files, not in domain classes | Secrets and configuration values must be injected as constructor or function parameters; domain code must never call `os.environ` directly. |
| `shared-utilities-used` | Imports of known shared utilities (e.g. `harness_skills.logging_config`, `harness_skills.task_lock`) are present rather than re-implemented | Before writing a new helper, check whether an equivalent exists in the shared packages; hand-rolling a duplicate is a blocking violation. |

---

#### Detector H — `style` category (Python)

Scan `python_files`.

| Pattern ID | Detection heuristic | Candidate rule (when True) |
|---|---|---|
| `context-managers-for-resources` | File uses `with` statements for file I/O, locks, and HTTP clients rather than manual `open/close` | All resource acquisition (file handles, locks, HTTP clients, DB connections) must use the `with` / `async with` context-manager form to guarantee clean-up on exceptions. |
| `no-magic-numbers` | File does NOT contain bare numeric literals (other than 0, 1, -1) outside of `constants.py` | Every numeric literal with domain or configuration meaning must be extracted to a named `UPPER_SNAKE_CASE` constant; only 0, 1, and -1 used in arithmetic are exempt. |
| `no-hardcoded-strings` | Files outside `tests/` and `constants.py` do NOT contain string literals matching known config patterns (URLs, queue names, hostnames) | Configuration strings (base URLs, hostnames, queue names, feature-flag keys) must be sourced from environment variables via a typed config object, never hardcoded inline. |
| `dataclasses-for-structured-data` | File uses `@dataclass` or `BaseModel` rather than plain `dict` for structured return values | Use `dataclasses.dataclass` or `pydantic.BaseModel` for any structured value with more than two fields; never return a naked `dict` from a public function. |

---

### Step 4 — Print frequency stats table

Always print the stats table regardless of `--dry-run` or `--stats-only`:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Extract Principles — Pattern Frequency Report
  Directory : <scan_dir>    Files scanned : <total_files>    Threshold : <min_pct>%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Category         Pattern ID                     Files  Pct    Conf    Candidate?
  ───────────────  ─────────────────────────────  ─────  ─────  ──────  ──────────
  async            async-await-usage              42/45  93.3%  HIGH    ✅ YES
  async            anyio-over-asyncio             38/45  84.4%  HIGH    ✅ YES
  async            no-blocking-in-async           39/45  86.7%  HIGH    ✅ YES
  async            httpx-async-client             21/45  46.7%  MEDIUM  ✅ YES
  async            asyncio-lock-shared-state       8/45  17.8%  LOW     ❌ NO  (below threshold)
  error-handling   structured-exceptions          35/40  87.5%  HIGH    ✅ YES
  error-handling   raise-from-cause               29/40  72.5%  HIGH    ✅ YES
  error-handling   no-bare-except                 36/40  90.0%  HIGH    ✅ YES
  error-handling   error-code-enum                12/40  30.0%  LOW     ❌ NO  (below threshold)
  naming           get-set-is-has-prefixes        41/45  91.1%  HIGH    ✅ YES
  naming           upper-snake-constants          40/45  88.9%  HIGH    ✅ YES
  naming           private-leading-underscore     38/45  84.4%  HIGH    ✅ YES
  naming           class-role-suffix              27/45  60.0%  MEDIUM  ✅ YES
  naming           id-suffix-on-identifiers       30/45  66.7%  MEDIUM  ✅ YES
  testing          test-name-pattern              18/20  90.0%  HIGH    ✅ YES
  testing          aaa-structure                  14/20  70.0%  HIGH    ✅ YES
  testing          narrow-fixture-scope           12/20  60.0%  MEDIUM  ✅ YES
  testing          mock-at-boundary               11/20  55.0%  MEDIUM  ✅ YES
  testing          no-duplicate-literals           7/20  35.0%  LOW     ❌ NO  (below threshold)
  type-safety      return-type-annotations        43/45  95.6%  HIGH    ✅ YES
  type-safety      parameter-type-annotations     38/45  84.4%  HIGH    ✅ YES
  type-safety      pydantic-over-plain-dict        31/45  68.9%  MEDIUM  ✅ YES
  type-safety      future-annotations-first       35/45  77.8%  HIGH    ✅ YES
  logging          module-level-logger            32/40  80.0%  HIGH    ✅ YES
  logging          no-print-in-production         37/40  92.5%  HIGH    ✅ YES
  logging          structured-extra-fields         18/40  45.0%  MEDIUM  ✅ YES
  logging          trace-id-propagation           14/40  35.0%  LOW     ❌ NO  (below threshold)
  architecture     imports-from-package-root      33/45  73.3%  HIGH    ✅ YES
  architecture     validation-at-boundary         22/45  48.9%  MEDIUM  ✅ YES
  architecture     no-os-environ-in-domain        38/45  84.4%  HIGH    ✅ YES
  architecture     shared-utilities-used          29/45  64.4%  MEDIUM  ✅ YES
  style            context-managers-for-resources 36/45  80.0%  HIGH    ✅ YES
  style            no-magic-numbers               28/45  62.2%  MEDIUM  ✅ YES
  style            no-hardcoded-strings           34/45  75.6%  HIGH    ✅ YES
  style            dataclasses-for-structured-data 30/45 66.7%  MEDIUM  ✅ YES

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  <C> candidate(s) above threshold  ·  <S> patterns below threshold  ·  <T> total
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Replace the example values with actual counts from the real scan.
Sort rows within each category block by `frequency_pct` descending.

If `--stats-only` is set, stop here and exit 0.

---

### Step 5 — Cross-reference against existing principles

Load `.claude/principles.yaml`:

```bash
cat .claude/principles.yaml 2>/dev/null || echo "__ABSENT__"
```

For each candidate pattern, check whether a principle whose `rule` text semantically covers
the same pattern already exists by scanning for key terms from `pattern_id` in existing
principle rules.  If a match is found, mark the candidate:

```
already_covered_by : "P013"   # existing principle ID, or null
```

Filter candidates where `already_covered_by` is non-null from the write output (they are
still shown in the stats table but labelled `⏭ COVERED`).

Print a cross-reference summary:

```
  Cross-reference against .claude/principles.yaml:
  ─────────────────────────────────────────────────
  ✅ NEW          <N> patterns not yet covered by any principle
  ⏭ COVERED      <M> patterns already covered — skipped
  ─────────────────────────────────────────────────
```

---

### Step 6 — Build candidate entries

For each qualifying candidate (above threshold AND not already covered), build a
`CandidatePrinciple` entry:

```python
{
  "pattern_id":    "async-await-usage",
  "category":      "async",
  "severity":      "blocking",         # blocking for HIGH; suggestion for MEDIUM/LOW
  "applies_to":    ["review-pr", "check-code"],
  "rule":          "<candidate_rule text from detector>",
  "confidence":    "HIGH",             # HIGH / MEDIUM / LOW
  "frequency_pct": 93.3,
  "files_matched": 42,
  "files_scanned": 45,
  "representative_examples": [
    "harness_skills/stale_plan_detector.py:12 — async def run(self) -> None:",
    "harness_skills/handoff.py:8 — async def _fetch_state(self, url: str) -> dict:",
    "harness_tools/cli/run.py:5 — async def main() -> None:"
  ],
  "already_covered_by": null,
  "generated_by":  "extract-principles",
  "scanned_at":    "<ISO-8601 UTC timestamp>"
}
```

**Severity mapping:**
- `HIGH` confidence → `"blocking"`
- `MEDIUM` confidence → `"suggestion"`
- `LOW` confidence → `"suggestion"` (included only if threshold was lowered with `--min-pct`)

---

### Step 7 — Write `docs/candidate-principles.yaml`

Unless `--dry-run` is set, write (or merge into) the output file.

Create the `docs/` directory if it does not exist:

```bash
mkdir -p docs
```

Obtain the current HEAD short hash:

```bash
git rev-parse --short HEAD 2>/dev/null || echo "no-git"
```

If `--merge` is set AND the output file already exists, read the existing candidates
and only append entries whose `pattern_id` is not already present.

Write the YAML file with this top-level structure:

```yaml
# docs/candidate-principles.yaml
# Generated by /extract-principles — review candidates and promote with:
#   /define-principles --from-file docs/candidate-principles.yaml
# Do not edit pattern_id, frequency_pct, or files_matched fields manually.

generated_at: "2026-03-24T00:00:00Z"
generated_from_head: "abc1234"
scan_dir: "."
files_scanned: 45
candidate_count: 28
threshold_pct: 40.0

candidates:
  - pattern_id: "async-await-usage"
    category: "async"
    severity: "blocking"
    applies_to:
      - "review-pr"
      - "check-code"
    rule: >
      All I/O-bound functions must be declared `async def` and awaited at call
      sites; synchronous I/O in a coroutine is a blocking violation.
    confidence: "HIGH"
    frequency_pct: 93.3
    files_matched: 42
    files_scanned: 45
    representative_examples:
      - "harness_skills/stale_plan_detector.py:12 — async def run(self) -> None:"
      - "harness_skills/handoff.py:8 — async def _fetch_state(self, url: str) -> dict:"
      - "harness_tools/cli/run.py:5 — async def main() -> None:"
    already_covered_by: null
    generated_by: "extract-principles"
    scanned_at: "2026-03-24T00:00:00Z"

  # … additional candidates …
```

If `--dry-run` is set, print the YAML to stdout prefixed with:

```
[dry-run] Would write to <output>:
```

---

### Step 8 — Optionally auto-promote HIGH-confidence candidates

If `--auto-promote` is set, use `scripts/import_principles.py` logic to merge all
`confidence: HIGH` candidates into `.claude/principles.yaml`:

```python
from pathlib import Path
import sys
sys.path.insert(0, "scripts")
from import_principles import (
    PrincipleEntry,
    load_existing_principles,
    merge_principles,
    write_principles,
)

existing = load_existing_principles(Path(".claude/principles.yaml"))

to_promote = [c for c in candidates if c["confidence"] == "HIGH"]

new_entries = [
    PrincipleEntry(
        id=id_prefix + str(next_id).zfill(3) if id_prefix else "",
        category=c["category"],
        severity=c["severity"],
        applies_to=c["applies_to"],
        rule=c["rule"],
    )
    for c in to_promote
]

merge_result = merge_principles(existing, new_entries)
if not merge_result.has_errors:
    write_principles(existing + merge_result.added, Path(".claude/principles.yaml"))
```

Print a promotion summary:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Auto-Promote Summary (HIGH confidence only)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ✅ Promoted (<N>):
     <id>  [<category>]  🔴 blocking  — <first 60 chars of rule>
     …

  ⚠️  Skipped (<M>) — ID already exists or below threshold:
     <pattern_id>  — <reason>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

If `--auto-promote` is not set, print a reminder:

```
  💡 To promote candidates into .claude/principles.yaml, run:
     /define-principles --from-file <output>
  Or re-run with --auto-promote to promote HIGH-confidence candidates automatically.
```

---

### Step 9 — Emit the machine-readable manifest

Always append a fenced JSON block so downstream agents can parse the results:

```json
{
  "command": "extract-principles",
  "scan_dir": ".",
  "scanned_at": "<ISO-8601 timestamp>",
  "files_scanned": 45,
  "threshold_pct": 40.0,
  "patterns_detected": 35,
  "patterns_above_threshold": 28,
  "patterns_already_covered": 4,
  "candidates_written": 24,
  "auto_promoted": 0,
  "confidence_breakdown": {
    "HIGH": 14,
    "MEDIUM": 10,
    "LOW": 0
  },
  "categories_scanned": ["async", "error-handling", "naming", "testing", "type-safety", "logging", "architecture", "style"],
  "outputs": {
    "candidate_file": "docs/candidate-principles.yaml",
    "principles_file": ".claude/principles.yaml"
  },
  "dry_run": false
}
```

---

### Step 10 — Print final summary

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅  Extract Principles complete
  <C> candidate(s) written → <output>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  HIGH confidence    : <N>  (auto-promotable)
  MEDIUM confidence  : <N>  (review recommended)
  LOW confidence     : <N>  (borderline — consider raising --min-pct)
  Already covered    : <N>  (existing principles cover these)

  Next steps:
    • Review docs/candidate-principles.yaml and remove any candidates you don't want.
    • Promote approved candidates:
        /define-principles --from-file <output>
    • Or auto-promote HIGH-confidence candidates in one step:
        /extract-principles --auto-promote
    • Re-run after adding principles to see what gaps remain:
        /extract-principles --stats-only
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### Step 11 — Exit behaviour

| Outcome | Exit code |
|---|---|
| Candidates written successfully | `0` |
| Dry-run completed | `0` |
| Stats-only completed | `0` |
| No source files found in scan_dir | `0` (with warning) |
| All candidates already covered — nothing new | `0` (with info message) |
| Merge error writing .claude/principles.yaml (`--auto-promote`) | `1` |
| scan_dir not found or not readable | `2` |
| Import error (scripts/import_principles.py missing) | `2` |

---

## Options

| Flag | Effect |
|---|---|
| `--dir <path>` | Root directory to scan (default: `.`) |
| `--category <list>` | Comma-separated category names to scan (default: `all`) |
| `--min-pct <N>` | Minimum frequency % for a pattern to become a candidate (default: `40`) |
| `--min-files <N>` | Minimum matching-file count for candidacy (default: `5`) |
| `--dry-run` | Preview candidates without writing any files |
| `--stats-only` | Print frequency table and exit; do not generate candidates |
| `--auto-promote` | Automatically promote HIGH-confidence candidates into `.claude/principles.yaml` |
| `--merge` | Append new candidates to an existing `docs/candidate-principles.yaml` instead of replacing it |
| `--output <path>` | Override output path (default: `docs/candidate-principles.yaml`) |
| `--id-prefix <prefix>` | ID prefix for auto-promoted entries (default: next available P-series) |

---

## Key files

| Path | Purpose |
|---|---|
| `docs/candidate-principles.yaml` | Output — review and edit before promoting |
| `.claude/principles.yaml` | Target — promoted candidates are merged here |
| `scripts/import_principles.py` | Library used for safe merge during `--auto-promote` |
| `.claude/commands/define-principles.md` | Use to promote candidates interactively or via `--from-file` |

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Discover what conventions actually exist in the codebase | **`/extract-principles`** ← you are here |
| Preview without writing any files | **`/extract-principles --dry-run`** |
| See frequency stats only | **`/extract-principles --stats-only`** |
| Immediately codify all HIGH-confidence patterns | **`/extract-principles --auto-promote`** |
| Add or edit principles interactively | `/define-principles` |
| Detect only import ordering patterns | `/import-ordering` |
| Detect only file naming patterns | `/file-naming-convention` |
| Detect only concurrency patterns | `/concurrency-patterns` |
| Scan codebase for violations of existing principles | `/golden-principles-cleanup` |
| Full quality sweep (lint, types, tests) | `/check-code` |

---

## Notes

- **Detection is statistical.** A pattern flag is set when `frequency_pct ≥ min_pct`
  AND `files_matched ≥ min_files`.  Lower `--min-pct` to surface more candidates;
  raise it to surface only the strongest conventions.
- **Cross-reference is heuristic.** The existing-principle overlap check scans rule
  text for key terms from `pattern_id`.  If a candidate is incorrectly marked
  `COVERED`, remove the `already_covered_by` field before promoting.
- **Candidate rules are starting points.** The `rule` text generated by each detector
  is intentionally concise and imperative.  Before promoting, expand the rule with
  project-specific examples, exemptions, and rationale so that `check-code` and
  `review-pr` can apply it unambiguously.
- **Re-running is safe.** With `--merge`, only new `pattern_id` values are appended
  to an existing `docs/candidate-principles.yaml`.  Without `--merge`, the file is
  fully regenerated from the current scan.
- **`--auto-promote` is irreversible (sort of).** Promoted principles are added to
  `.claude/principles.yaml` with stable IDs.  To remove a mistakenly promoted
  principle, run `/define-principles` and use the **Remove** action.
- **Extend the detectors.** Add new rows to any Detector table in this skill file to
  teach the scanner about project-specific patterns.  Follow the `pattern_id` /
  detection heuristic / candidate rule column format used above.
