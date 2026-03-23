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

---

## Security Protocols

### Secret Handling

Never commit credentials, API keys, tokens, or passwords to source control.
Use environment variables for all sensitive values.

**Required pattern — always use `os.environ`:**

```python
import os

# Good — loaded from the environment
api_key    = os.environ["ANTHROPIC_API_KEY"]
db_url     = os.environ["DATABASE_URL"]
jwt_secret = os.environ["JWT_SECRET"]

# Bad — never do this
api_key = "sk-abc123..."                      # SEC003 — hardcoded API key
db_url  = "postgres://user:pass@host/db"      # SEC006 — credentials in URL
```

The security gate (`/harness:security-check-gate --scan-secrets`) flags these rule IDs:

| Rule ID | Pattern caught |
|---------|----------------|
| SEC001  | Generic `password =` / `secret =` literal assignments |
| SEC002  | PEM private keys (`-----BEGIN … PRIVATE KEY-----`) |
| SEC003  | AI provider API keys (Anthropic, OpenAI, Cohere …) |
| SEC004  | AWS credentials (`AKIA…`) |
| SEC005  | GitHub personal access tokens |
| SEC006  | Database URLs with embedded credentials |
| SEC007  | `Authorization: Bearer <token>` string literals |
| SEC008  | High-entropy hex strings (≥ 32 chars) |

If a secret is accidentally committed, **rotate it immediately** — treat it as
compromised.  Then scrub git history with `git filter-repo` or BFG Repo Cleaner.

**Environment variables used by this service:**

| Variable            | Purpose                                        | Required |
|---------------------|------------------------------------------------|----------|
| `STATE_SERVICE_URL` | claw-forge state service endpoint              | Yes      |
| `FEATURE_ID`        | Current feature ID for state updates           | Yes      |
| `BASE_URL`          | Target URL for browser automation              | Optional |
| `ANTHROPIC_API_KEY` | Anthropic API key for the agent SDK            | Optional |
| `SCREENSHOT_DIR`    | Directory where browser PNGs are saved         | Optional |

---

### Input Validation Patterns

All user-supplied data must be validated before use.  This project uses
**Pydantic ≥ 2.0** as the standard validation layer.

**Always validate request payloads with Pydantic:**

```python
from pydantic import BaseModel, HttpUrl, field_validator

class TaskRequest(BaseModel):
    feature_id: str
    target_url: HttpUrl | None = None
    tags: list[str] = []

    @field_validator("feature_id")
    @classmethod
    def feature_id_alphanumeric(cls, v: str) -> str:
        if not v.replace("-", "").isalnum():
            raise ValueError("feature_id must be alphanumeric with dashes only")
        return v
```

**Unsafe patterns the security gate catches (INV rules):**

| Rule ID | Dangerous pattern | Safe alternative |
|---------|-------------------|-----------------|
| INV001  | `cursor.execute(f"… {request…}")` | Parameterised query: `cursor.execute("…", (value,))` |
| INV002  | `"… %s" % request_data` in SQL context | Parameterised query |
| INV003  | `subprocess.call(user_input, shell=True)` | `subprocess.run([cmd, arg], shell=False)` with validated args |
| INV004  | `eval(request.data)` / `exec(user_input)` | Never pass user input to `eval`/`exec` |
| INV005  | `open(request.args["path"])` (path traversal) | `(Path(root) / path).resolve()` + allow-list check |
| INV006  | `requests.get(request.args["url"])` (SSRF) | Validate scheme + hostname against an explicit allow-list |
| INV007  | `Template(user_input).render()` (SSTI) | Never use user data as a template string |
| INV008  | `pickle.loads(request.body)` | Use JSON or Pydantic for deserialisation |

Run the gate locally before pushing:

```bash
/harness:security-check-gate --scan-secrets --scan-input-validation
```

---

### Auth Conventions

All authenticated requests use **Bearer token** authentication via the
`Authorization` header.

**Standard pattern (using `requests`):**

```python
import os
import requests

def authenticated_get(path: str) -> dict:
    token   = os.environ["API_TOKEN"]          # never hardcode
    base    = os.environ["BASE_URL"]
    resp    = requests.get(
        f"{base}{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()
```

**claw-forge state service (no token — local only):**

```python
import os
import requests

STATE_URL  = os.environ.get("STATE_SERVICE_URL", "http://localhost:8888")
FEATURE_ID = os.environ["FEATURE_ID"]

# Report task complete
requests.patch(
    f"{STATE_URL}/features/{FEATURE_ID}",
    json={"status": "done"},
    timeout=10,
).raise_for_status()

# Request human input
requests.post(
    f"{STATE_URL}/features/{FEATURE_ID}/human-input",
    json={"question": "Which environment should this run against?"},
    timeout=10,
).raise_for_status()
```

**Auth conventions at a glance:**

| Convention       | Rule                                                               |
|------------------|--------------------------------------------------------------------|
| Token source     | Always `os.environ["VAR"]` — never a string literal               |
| Header name      | `Authorization: Bearer <token>`                                    |
| Timeout          | `timeout=30` for external services; `timeout=10` for localhost     |
| TLS              | Production endpoints must use `https://`; `http://` only for localhost |
| Credential rotation | Rotate immediately if a token appears in logs, errors, or commits |
