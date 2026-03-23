# AGENTS.md Generator

Generate or update `AGENTS.md` so AI agents have an accurate, up-to-date reference
for working in this repository.  The skill scans the codebase, detects frameworks and
conventions in use, and writes (or refreshes) well-structured sections covering:

- **Browser Automation** — Playwright/Puppeteer helpers, screenshots, e2e commands
- **Testing Conventions** — file naming, assertion style, coverage expectations, fixture patterns

Use this skill whenever `AGENTS.md` is missing, stale, or after significant changes to
the test suite or browser automation setup.

---

## Usage

```bash
# Generate (or update) AGENTS.md with all sections
/agents-md

# Regenerate only the Testing Conventions section
/agents-md --section testing

# Regenerate only the Browser Automation section
/agents-md --section browser

# Preview without writing to disk
/agents-md --dry-run

# Write to a non-default path
/agents-md --output docs/AGENTS.md
```

---

## Instructions

### Step 1 — Detect the test runner and framework

```bash
# Detect Python test runner
[ -f "pytest.ini" ] || [ -f "conftest.py" ] || grep -q "pytest" requirements*.txt 2>/dev/null \
  && echo "test_runner: pytest"

# Detect JavaScript test runner
grep -q '"jest"'   package.json 2>/dev/null && echo "test_runner: jest"
grep -q '"vitest"' package.json 2>/dev/null && echo "test_runner: vitest"

# Detect browser testing framework
grep -q "playwright"       requirements*.txt 2>/dev/null && echo "browser: playwright-python"
grep -q "@playwright/test" package.json      2>/dev/null && echo "browser: playwright-node"
grep -q "puppeteer"        package.json      2>/dev/null && echo "browser: puppeteer"
```

Also scan for:
- `tests/` or `test/` directory layout (subdirectories reveal test categories)
- `conftest.py` files to understand shared fixtures
- `harness.config.yaml` for the configured coverage threshold

---

### Step 2 — Scan test conventions

Inspect the `tests/` directory and up to 5 representative test files to extract
real conventions actually used in this codebase:

```bash
# List test categories
ls tests/ 2>/dev/null

# Sample test file names to infer naming pattern
find tests/ -name "test_*.py" | head -20 2>/dev/null

# Check conftest for shared fixtures
cat tests/conftest.py tests/browser/conftest.py 2>/dev/null | head -80
```

Record:

| Convention | How to detect |
|---|---|
| File naming pattern | File names: `test_<module>.py` vs `<module>.test.ts` etc. |
| Assertion style | Presence of `assert ` vs `expect(` vs `self.assert` |
| Coverage threshold | `harness.config.yaml → coverage.threshold`, `pytest.ini`, `.nycrc` |
| Fixture style | `@pytest.fixture`, `beforeEach`, helper factory functions |
| Special fixtures | `tmp_path`, `monkeypatch`, `autouse=True` fixtures in conftest |

---

### Step 3 — Build the Testing Conventions section

Using the detected conventions, generate the **Testing Conventions** section.
Use the template below, replacing `<…>` tokens with discovered values:

````markdown
## Testing Conventions

Test runner: **<pytest | jest | vitest>**
Coverage threshold: **<N>%** (configured in `harness.config.yaml`)

### Test file naming

| Category | Location | Pattern | Example |
|---|---|---|---|
| Unit (top-level modules) | `tests/` | `test_<module>.py` | `tests/test_exec_plan.py` |
| Gate tests | `tests/gates/` | `test_<gate>.py` | `tests/gates/test_docs_freshness.py` |
| CLI command tests | `tests/test_cli/` | `test_<command>.py` | `tests/test_cli/test_status_cmd.py` |
| Generator tests | `tests/test_generators/` | `test_<generator>.py` | `tests/test_generators/test_config_generator.py` |
| Browser / e2e tests | `tests/browser/` | `test_<feature>.py` | `tests/browser/test_smoke.py` |
| Model tests | `tests/test_models/` | `test_<model>.py` | `tests/test_models/test_gate_configs.py` |

Rules:
- All test files use the `test_` prefix (pytest discovery default).
- Mirror the source module path under `tests/`.  A module at
  `harness_skills/gates/coverage.py` has its tests at
  `tests/gates/test_coverage.py`.
- Browser/e2e tests live in `tests/browser/` and require `pytest-playwright`.

### Assertion style

Use **plain pytest assertions** — never `unittest`-style `self.assert*` methods.

```python
# ✅ correct
assert result.passed
assert len(violations) == 1
assert "dead_ref" in violation.message

# ❌ avoid
self.assertTrue(result.passed)
self.assertEqual(len(violations), 1)
```

Group related assertions in a single test function; each test should exercise
one logical behaviour:

```python
def test_missing_ref_violation(tmp_path):
    agents(tmp_path, TS + "\n[ghost](src/ghost.py)\n")
    r = DocsFreshnessGate().run(tmp_path)
    dead = [v for v in r.violations if v.kind == "dead_ref"]
    assert len(dead) == 1
    assert "src/ghost.py" in dead[0].message
```

### Coverage expectations

| Profile | Line coverage | Branch coverage |
|---|---|---|
| `starter` | **80 %** | optional |
| `standard` | **80 %** | optional |
| `advanced` | **90 %** | enabled |

The active threshold is set in `harness.config.yaml`:

```yaml
gates:
  coverage:
    threshold: 80        # minimum line coverage %
    branch_coverage: false
```

New tests should bring the module they exercise to **≥ 80 % line coverage**.
Aim for **boundary tests** (exactly at threshold, one over) for any
threshold-based logic.

### Fixture patterns

#### `tmp_path` — filesystem isolation

Use the built-in `tmp_path` fixture for any test that reads or writes files.
Never use real project paths in tests.

```python
def test_existing_ref_ok(tmp_path):
    touch(tmp_path / "src" / "models" / "foo.py")
    agents(tmp_path, TS + "\n[foo](src/models/foo.py)\n")
    r = DocsFreshnessGate().run(tmp_path)
    assert not [v for v in r.violations if v.kind == "dead_ref"]
```

#### `monkeypatch` — deterministic state

Use `monkeypatch` to freeze time-dependent values so tests are repeatable:

```python
@pytest.fixture(autouse=True)
def freeze_today(monkeypatch):
    monkeypatch.setattr(
        "harness_skills.gates.docs_freshness._today",
        lambda: date(2025, 6, 15),
    )
```

Mark cross-cutting fixtures `autouse=True` so all tests in the module benefit
automatically.

#### Helper factory functions

Prefer lightweight factory helpers over complex fixtures when the setup is
short and test-local:

```python
def agents(tmp_path, content, sub=""):
    """Write an AGENTS.md file under tmp_path (optionally in a subdirectory)."""
    d = tmp_path / sub if sub else tmp_path
    d.mkdir(parents=True, exist_ok=True)
    f = d / "AGENTS.md"
    f.write_text(textwrap.dedent(content))
    return f

def touch(p: Path) -> Path:
    """Create an empty file, making parent directories as needed."""
    p.parent.mkdir(parents=True, exist_ok=True)
    p.touch()
    return p
```

#### Session-scoped fixtures — expensive resources

Use `scope="session"` for anything expensive to set up (browser instances,
server processes, network connections):

```python
@pytest.fixture(scope="session")
def base_url():
    return os.environ.get("BASE_URL", "http://localhost:3000")
```

#### `autouse` failure hooks

Register failure-capture logic as `autouse` fixtures in `conftest.py` so it
applies automatically to every test in the suite:

```python
# tests/browser/conftest.py
@pytest.fixture(autouse=True)
def screenshot_on_failure(page, request):
    yield
    if request.node.rep_call.failed:
        capture_screenshot(page, f"failures/{request.node.nodeid}")
```

### Running tests

```bash
# All tests
pytest tests/ -v

# Specific category
pytest tests/gates/ -v
pytest tests/browser/ -v

# With coverage report
pytest tests/ --cov=harness_skills --cov-report=term-missing

# Browser tests headed (shows window — useful for local debugging)
pytest tests/browser/ --headed

# Target a different environment
BASE_URL=https://staging.example.com pytest tests/browser/ -v
```
````

---

### Step 4 — Build the Browser Automation section (if applicable)

If a browser testing framework was detected in Step 1, include (or refresh) a
**Browser Automation** section using the same conventions already documented in
the `browser-automation` skill.  See `/browser-automation` for the full
template.

If no browser framework is detected, skip this section.

---

### Step 5 — Assemble and write AGENTS.md

Compose the final `AGENTS.md` in this order:

1. **Auto-generated header block** — always write fresh metadata:

```bash
RUN_DATE=$(date '+%Y-%m-%d')
HEAD_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "no-git")
SERVICE=$(basename "$(pwd)")
```

```markdown
<!-- harness:auto-generated — do not edit this block manually -->
last_updated: <RUN_DATE>
head: <HEAD_HASH>
service: <SERVICE>
<!-- /harness:auto-generated -->

Agent-facing reference for this repository.

---
```

2. **Browser Automation** section (if detected — Step 4)
3. **Testing Conventions** section (always — Step 3)

When updating an existing `AGENTS.md`:
- Re-write the auto-generated header block in-place (between the comment markers).
- Replace sections that already exist with the freshly generated content.
- Preserve any manually-written sections that are not listed above.

When `--section testing` is passed, update only the Testing Conventions section
and the header timestamp; leave all other sections untouched.

When `--dry-run` is passed, print the full file to stdout; do not write to disk.

---

### Step 6 — Emit a summary

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  AGENTS.md Generator — complete
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Sections written
  ─────────────────────────────────────────────────────
  ✅ Auto-generated header   (last_updated: <date>)
  ✅ Browser Automation      (framework: <playwright|none>)
  ✅ Testing Conventions     (runner: <pytest>, coverage: <N>%)
  ─────────────────────────────────────────────────────

  Output: <path>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Next steps
  • Commit: git add <path>
  • Validate freshness: /harness:docs-freshness
  • Run quality gates:  /harness:evaluate
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Options

| Flag | Default | Effect |
|---|---|---|
| `--section SECTION` | all | Regenerate only `testing` or `browser`; leave other sections untouched |
| `--output PATH` | `AGENTS.md` | Destination file path |
| `--dry-run` | off | Print to stdout; do not write to disk |

---

## Output artifacts

| Artifact | Description |
|---|---|
| `AGENTS.md` | Created or updated with Browser Automation and Testing Conventions sections |

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| AGENTS.md is missing or has no testing conventions | **`/agents-md`** ← you are here |
| AGENTS.md exists but testing section is stale | **`/agents-md --section testing`** |
| Check whether AGENTS.md references are still valid | `/harness:docs-freshness` |
| Run all quality gates including docs freshness | `/harness:evaluate` |
| Regenerate just the browser automation section | `/browser-automation` |

---

## Notes

- **Merge-safe** — existing sections not targeted by this invocation are
  preserved verbatim; only the auto-generated header and selected sections are
  replaced.
- **Never auto-commits** — review the generated content before committing.
- **Idempotent** — running `/agents-md` twice on an unchanged codebase produces
  an identical file on the second run (same date, same HEAD, same conventions).
- **Validation** — after writing, run `/harness:docs-freshness` to confirm all
  file references in the new content are resolvable.
