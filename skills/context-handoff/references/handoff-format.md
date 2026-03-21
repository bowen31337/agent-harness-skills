# Handoff Format Reference

## Table of Contents
1. [File Locations](#file-locations)
2. [Field Reference](#field-reference)
3. [Search Hints — Field-by-Field](#search-hints--field-by-field)
4. [Worked Example](#worked-example)
5. [Quality Checklist](#quality-checklist)
6. [Anti-Patterns to Avoid](#anti-patterns-to-avoid)

---

## File Locations

| Format   | Path                      | Used by                        |
|----------|---------------------------|--------------------------------|
| Markdown | `.claude/plan-progress.md`| Agent read/write (this skill)  |
| JSONL    | `.plan_progress.jsonl`    | `HandoffTracker` (Python API)  |

The Markdown file is overwritten each session (latest state wins).
The JSONL file is append-only (full audit trail across all sessions).

---

## Field Reference

### YAML Frontmatter

| Field        | Type   | Required | Notes |
|-------------|--------|----------|-------|
| `session_id` | string | yes      | Agent SDK session ID, or `'unknown'` |
| `timestamp`  | string | yes      | UTC ISO-8601: `2026-03-14T10:30:00Z` |
| `task`       | string | yes      | One-line description of the overall task |
| `status`     | enum   | yes      | `in_progress` \| `blocked` \| `done` |

### Body Sections

| Section          | Purpose |
|-----------------|---------|
| `## Accomplished` | Concrete items **completed** this session. Be specific. |
| `## In Progress`  | Partially done work. Include % complete and what remains. |
| `## Next Steps`   | **Ordered** list — the next agent starts at item 1. |
| `## Search Hints` | Four sub-sections (see below). The most important section. |
| `## Open Questions` | Unresolved decisions or blockers. |
| `## Artifacts`    | Files created or significantly modified. |
| `## Notes`        | Free-form context that doesn't fit the structured fields. |

---

## Search Hints — Field-by-Field

Search hints are the core value of the handoff. They let the next agent *verify* the current state of the code rather than trusting a stale description.

### `### Key Files`
Exact relative file paths the next agent should `Read` first — those most central to the task. Keep to ≤8 files.

```markdown
### Key Files
- src/api/gateway.py — main entry point; rate-limit logic goes in handle_request()
- src/middleware/auth.py — UserAuthMiddleware applies to all /api/* routes
- tests/test_gateway.py — existing integration tests to extend
```

### `### Key Directories`
Top-level directories to explore with `Glob` for orientation.

```markdown
### Key Directories
- src/api/ — HTTP handlers and middleware
- src/models/ — Pydantic request/response schemas
- tests/ — pytest suite; mirrors src/ structure
```

### `### Grep Patterns`
Regex patterns for the `Grep` tool that find the most important code locations.

```markdown
### Grep Patterns
```
class RateLimiter
def handle_request
TODO.*rate.limit
RATE_LIMIT_WINDOW
```
```

**Good patterns:**
- Class/function definitions: `class UserAuthMiddleware`, `def validate_token`
- Config constants: `MAX_REQUESTS_PER_MINUTE`, `REDIS_URL`
- Markers left in code: `TODO.*payment`, `FIXME.*session`
- Import targets: `from src\.middleware import`

### `### Key Symbols`
Names to search for with `Grep`. Shorter than full patterns — let the next agent compose the search.

```markdown
### Key Symbols
- RateLimiter
- handle_request
- RATE_LIMIT_WINDOW
- redis_client
```

---

## Worked Example

Scenario: adding Redis-backed rate limiting to an API gateway; session ended after implementing the core `RateLimiter` class but before wiring it into the request handler.

```markdown
---
session_id: "sess_01JQKW7NM4V2R8BX9FPZD6Y3CH"
timestamp: "2026-03-14T11:42:00Z"
task: "Add Redis-backed rate limiting to the API gateway"
status: "in_progress"
---

## Accomplished
- Implemented `RateLimiter` class in `src/api/rate_limit.py` using a sliding-window algorithm
- Added Redis connection helper `get_redis_client()` in `src/db/redis.py`
- Wrote unit tests for RateLimiter (100% branch coverage) in `tests/unit/test_rate_limit.py`
- Added `RATE_LIMIT_WINDOW` and `MAX_REQUESTS` to `src/config.py`

## In Progress
- Wiring RateLimiter into `handle_request()` in `src/api/gateway.py` (~30% complete)
  - Remaining: call `rate_limiter.check()` before routing, return 429 on exceeded

## Next Steps
- In `src/api/gateway.py`: import RateLimiter, instantiate as module-level singleton, call in handle_request()
- Add integration test in `tests/integration/test_gateway.py` covering 429 response
- Update `docs/api.md` to document rate limit headers (X-RateLimit-Limit, X-RateLimit-Remaining)
- Run full test suite: `pytest tests/ -v`

## Search Hints
### Key Files
- src/api/gateway.py — wire RateLimiter into handle_request() here
- src/api/rate_limit.py — RateLimiter class (complete); study before modifying gateway
- src/db/redis.py — get_redis_client() helper; already imported by rate_limit.py
- src/config.py — RATE_LIMIT_WINDOW and MAX_REQUESTS constants defined here
- tests/unit/test_rate_limit.py — existing unit tests; run to verify nothing regressed

### Key Directories
- src/api/ — all HTTP handlers; gateway.py is the main entry point
- src/db/ — database and cache clients
- tests/ — pytest; unit/ and integration/ subdirectories

### Grep Patterns
```
class RateLimiter
def handle_request
def get_redis_client
RATE_LIMIT_WINDOW
TODO.*rate
```

### Key Symbols
- RateLimiter
- handle_request
- get_redis_client
- RATE_LIMIT_WINDOW
- MAX_REQUESTS

## Open Questions
- Should rate limits be per-IP or per-authenticated-user? Currently per-IP; may need to switch after auth middleware is clearer.
- Redis TTL strategy: use EXPIRE on the sliding window key or rely on natural expiry?

## Artifacts
- src/api/rate_limit.py (new)
- src/db/redis.py (new)
- src/config.py (modified — added RATE_LIMIT_WINDOW, MAX_REQUESTS)
- tests/unit/test_rate_limit.py (new)

## Notes
The RateLimiter uses a sorted set in Redis (key: `rl:{ip}`, score: timestamp).
`check()` removes stale entries with ZREMRANGEBYSCORE then counts with ZCARD before adding
the current request. Atomic via a Lua script — see rate_limit.py for the script string.
```

---

## Quality Checklist

Before writing your handoff, verify:

- [ ] **Next Steps are ordered and actionable** — agent can start at item 1 without guessing
- [ ] **Key Files are ≤8** — only the files the next agent *must* read first
- [ ] **Grep patterns are ready to paste** into the Grep tool as-is
- [ ] **Key Symbols match actual identifiers** in the code (no typos)
- [ ] **No file contents** pasted into the handoff — only paths and patterns
- [ ] **In Progress** entries include % complete and what specifically remains
- [ ] **Open Questions** are genuine blockers or decisions the next agent must make
- [ ] **Artifacts** lists every file created or significantly modified

---

## Anti-Patterns to Avoid

| Anti-pattern | Why it fails | Fix |
|-------------|-------------|-----|
| Pasting file contents | Content goes stale; bloats next agent's context | Use path + grep pattern instead |
| Vague next steps ("continue the work") | Next agent has no starting point | List the exact function/file to modify |
| Too many key files (>10) | Agent reads everything, loses focus | Keep to the 5–8 most critical |
| Generic grep patterns (`*.py`) | Matches too much; no signal | Use class/function names or specific strings |
| Missing % complete in In Progress | Next agent re-does finished work | Always state what's done and what remains |
| status=done when work remains | Misleads orchestrators | Use `in_progress` until fully complete |
