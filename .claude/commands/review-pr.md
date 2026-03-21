# Review PR

Review the current git diff or a specified PR. Check for tests, type annotations, coverage, docstrings, and security issues. Also enforces project-specific principles from `.claude/principles.yaml`. Produce a structured review.

## Instructions

### Step 0: Load custom principles

Check for project-specific golden rules:

```bash
cat .claude/principles.yaml 2>/dev/null || echo "__NONE__"
```

Parse the YAML and extract all principles where `applies_to` includes `"review-pr"` or `"both"`.
If the file is missing or returns `__NONE__`, skip this step silently — custom principles are optional.

Keep the loaded principles in context; they will be used in Steps 2 and 3.

### Step 1: Get the diff

```bash
# Review current uncommitted changes
git diff HEAD

# Or review a specific PR (if gh CLI available)
# gh pr diff <PR_NUMBER>

# Or review last commit
git diff HEAD~1 HEAD
```

If a PR number is provided as an argument, use `gh pr diff <number>`.

### Step 2: Analyze the diff

For each changed file, check:

#### ✅ Project Principles (custom, from `.claude/principles.yaml`)

If principles were loaded in Step 0, evaluate each one against the diff:
- `blocking` violations → add to 🔴 BLOCKING ISSUES
- `suggestion` violations → add to 🟡 SUGGESTIONS
- Not applicable → note as SKIP in the Looks Good section

#### ✅ Tests
- Are there corresponding test files for new code?
- Do tests cover happy path AND error cases?
- Are edge cases handled?
- Test coverage estimate: count test functions vs public functions

#### ✅ Type annotations
- Every function/method has parameter types and return type
- No `Any` unless justified
- Pydantic models used for complex data structures

#### ✅ Docstrings
- Public functions have docstrings
- Complex logic has inline comments
- `Args:` and `Returns:` sections where helpful

#### ✅ Security
- No hardcoded credentials or API keys
- Input validation on all external data
- SQL queries use parameterized statements
- No shell injection vulnerabilities (avoid `shell=True`)
- Secrets come from environment variables

#### ✅ Performance
- No N+1 query patterns
- Async functions for I/O operations
- No blocking calls in async context

#### ✅ Style
- Consistent with existing codebase patterns
- Variable names are descriptive
- Functions do one thing (single responsibility)
- No dead code

### Step 3: Structured review output

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  PR Review — <title/description>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Files changed: <N>
  Lines added: +<N> | Lines removed: -<N>

  VERDICT: ✅ APPROVE / ❌ REQUEST CHANGES / 💬 COMMENT

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  🔴 BLOCKING ISSUES (must fix before merge):
    1. <file>:<line> — <issue>

  🟡 SUGGESTIONS (non-blocking):
    1. <file>:<line> — <suggestion>

  ✅ LOOKS GOOD:
    - Tests: covered
    - Types: annotated
    - Security: no issues found
    - Principles: P001 ✅  P002 ✅  P003 ⏭ (skipped — not applicable)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

> If no `.claude/principles.yaml` exists, omit the Principles line entirely.
> To define principles: run `/define-principles`.

### Step 4: Post to state service (optional)

If the state service is running, log the review:

```bash
curl -s -X POST http://localhost:8420/sessions/$SESSION_ID/events \
  -H "Content-Type: application/json" \
  -d '{"type": "review.completed", "payload": {"verdict": "approve", "issues": 0}}'
```

### Verdicts

- **APPROVE**: No blocking issues, safe to merge
- **REQUEST CHANGES**: Blocking issues found, must be addressed
- **COMMENT**: Observations only, no changes required
