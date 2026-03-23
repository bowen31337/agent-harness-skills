# AGENTS.md

<!-- harness:auto-generated — do not edit this block manually -->
last_updated: 2026-03-22
head: 157af7b
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

<!-- harness:git-workflow — do not edit this block manually -->

---

## Git Workflow

> Full convention: [docs/plan-to-pr-convention.md](docs/plan-to-pr-convention.md)

### Branch naming

```
feat/PLAN-NNN-<kebab-slug-of-title>
```

Examples:
- `feat/PLAN-001-auth-refresh-token`
- `feat/PLAN-007-logging-structured-output`

The `PLAN-NNN` prefix lets reviewers and CI identify the source plan without
opening the PR body.

### Commit message format

```
<type>: <imperative short description>

<body — what and why, not how>

Plan: PLAN-NNN
Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

- **type**: `feat` | `fix` | `chore` | `docs` | `refactor` | `test`
- **Plan trailer**: required for every commit that belongs to an execution plan
- **Co-Authored-By trailer**: always include the agent attribution line
- Use a HEREDOC when passing the commit message via `git commit -m` to preserve
  multi-line formatting and trailers exactly

### PR process

1. **Title**: `[PLAN-NNN] <imperative short description>`
   Machine-parseable prefix — `gh pr list --search "[PLAN-001]"` returns all PRs for a plan.
2. **Body**: must include the traceability table:
   ```markdown
   ## Execution Plan
   | Field        | Value |
   |--------------|-------|
   | Plan ID      | `PLAN-NNN` |
   | Plan file    | `docs/exec-plans/PLAN-NNN-<slug>.yaml` |
   | Tasks closed | TASK-NNN, TASK-NNN |
   | Plan status  | running |
   ```
3. **After `gh pr create`**: update the plan YAML `linked_prs` list with the
   returned PR URL, then commit the updated plan file on the feature branch.
4. **Before marking a task `done`**: verify the checklist in
   `docs/plan-to-pr-convention.md §6`.

### Quick traceability queries

```bash
# All PRs for a plan
gh pr list --search "[PLAN-001]" --json number,title,url,state

# Plan for a given PR (from PR body)
gh pr view 42 --json body | jq '.body' | grep "Plan ID"

# All open plan PRs in this repo
grep -r "pr_url" docs/exec-plans/ | grep -v "Example"

# Verify all plan tasks have a linked PR
python skills/exec_plan.py verify-prs PLAN-001
```

<!-- /harness:git-workflow -->
