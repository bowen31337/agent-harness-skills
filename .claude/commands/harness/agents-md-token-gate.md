# Harness AGENTS.md Token-Budget Gate

Scan every `AGENTS.md` file in the repository and **block merges** that
contain any file whose estimated token count exceeds the configured ceiling.

Each `AGENTS.md` is loaded verbatim into every agent's context window.
Verbose files silently consume thousands of tokens before the agent reads
a single line of task-relevant code — the token-budget gate surfaces this
problem at code-review time rather than at runtime.

Token count is estimated with the character-count heuristic:

```
estimated_tokens = ceil(len(file_content) / chars_per_token)
```

where `chars_per_token` defaults to **4.0** (standard English+code
approximation matching OpenAI's guidance for GPT-family models; also a close
approximation for Claude models).

Default ceiling: **800 tokens per file**.  Override with `--max-tokens N`.

---

## Usage

```bash
# Run with default ceiling (800 tokens per AGENTS.md)
/harness:agents-md-token-gate

# Raise or lower the token ceiling
/harness:agents-md-token-gate --max-tokens 500
/harness:agents-md-token-gate --max-tokens 1500

# Also check files like FRONTEND_AGENTS.md and AGENTS_BROWSER.md
/harness:agents-md-token-gate --glob "**/*AGENTS*.md"

# Use a tighter chars-per-token ratio (more conservative estimate)
/harness:agents-md-token-gate --chars-per-token 3.5

# Advisory mode — report over-budget files as warnings, do not block
/harness:agents-md-token-gate --no-fail-on-error

# Integrate into a full evaluate run
/harness:evaluate --gate agents_md_token --max-tokens 800
```

---

## Instructions

### Step 0: Resolve inputs

Collect the following from the invocation (applying defaults where absent):

| Argument | Default | Description |
|---|---|---|
| `--max-tokens` | `800` | Maximum allowed estimated tokens per AGENTS.md file |
| `--glob` | `**/AGENTS.md` | Glob pattern for discovering AGENTS.md files (relative to project root) |
| `--chars-per-token` | `4.0` | Characters-per-token ratio for estimation |
| `--fail-on-error` | `true` | Exit non-zero on any over-budget file (`--no-fail-on-error` for advisory) |
| `--project-root` | `.` | Repository root for glob discovery |

---

### Step 1: Run the AGENTS.md token-budget gate CLI

```bash
uv run python -m harness_skills.gates.agents_md_token \
  --root <project-root> \
  --max-tokens <max-tokens> \
  --glob <glob-pattern> \
  --chars-per-token <chars-per-token> \
  [--fail-on-error | --no-fail-on-error]
```

> **Fallback** — if `uv` is not available:
>
> ```bash
> python -m harness_skills.gates.agents_md_token \
>   --root <project-root> \
>   --max-tokens <max-tokens>
> ```

Capture both stdout and the exit code.

---

### Step 2: Parse and render the result

The CLI writes a human-readable summary to stdout.  Parse the key values and
render them in this format:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  AGENTS.md Token-Budget Gate — <PASS ✅ | FAIL ❌>
  Files checked  : <N>
  Token ceiling  : <max-tokens> tokens/file
  Violations     : <N>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**If the gate passes** (every file is within budget):

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅  Token-budget gate passed — all <N> AGENTS.md file(s) within budget
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Include a per-file breakdown showing token counts even on a pass:

```
  File                       Est. tokens   Limit   Status
  ─────────────────────────────────────────────────────
  AGENTS.md                      642        800      ✅
  sub/AGENTS.md                  381        800      ✅
```

**If any file exceeds the budget** (`fail_on_error=true`):

```
🔴 BLOCKING — AGENTS.md token budget exceeded
────────────────────────────────────────────────────
  File                       Est. tokens   Limit   Excess
  ─────────────────────────────────────────────────────
  AGENTS.md                    1 423        800      +623
  docs/AGENTS.md               2 104        800    +1 304

  Reduce each file's content so its estimated token count
  falls at or below the configured ceiling.
  Hint: run the gate with --no-fail-on-error first to audit
  all files without blocking.
```

**If no AGENTS.md files are found** (always advisory):

```
🟡 WARNING — No AGENTS.md files discovered
────────────────────────────────────────────────────
  Pattern: **/AGENTS.md  under  <project-root>
  Nothing to check.
```

**Advisory mode** (`--no-fail-on-error`): replace every `🔴 BLOCKING`
header with `🟡 WARNING — advisory only, merge not blocked`.

---

### Step 3: Exit behaviour

| Outcome | Exit code |
|---|---|
| All files within budget | `0` |
| Any file over budget (`fail_on_error=true`) | `1` |
| No AGENTS.md files found (always advisory) | `0` (warning emitted) |
| Any violation (`fail_on_error=false`) | `0` (warnings emitted) |
| Gate runner internal error | `2` |

Mirror the CLI exit code.

If exit code is `1`, explicitly state:
*"This branch is **not** ready to merge — reduce AGENTS.md file sizes to
**<max-tokens>** tokens or fewer before the pull request can land."*

---

### Step 4: Suggest next steps on over-budget files

When the gate fails, suggest concrete remediation actions:

1. **Identify the heaviest sections** using `wc -c` and a rough token estimate:
   ```bash
   for f in $(find . -name "AGENTS.md"); do
     chars=$(wc -c < "$f")
     tokens=$(python3 -c "import math; print(math.ceil($chars / 4))")
     echo "$tokens tokens  $f"
   done
   ```

2. **Trim verbose sections** — prioritise these for removal or shortening:
   - Long environment-variable tables (move to `README.md` or a separate doc)
   - Detailed command examples (keep one canonical example, link to docs)
   - Code blocks repeated from existing source files (remove — the agent can
     read the source directly)
   - Historical changelog entries (AGENTS.md should describe *current* state
     only)

3. **Split large AGENTS.md into focused sub-files** and reference them:
   ```markdown
   # AGENTS.md
   ## Quick start
   See [AGENTS_BROWSER.md](./AGENTS_BROWSER.md) for browser-automation notes.
   ```
   Note: if you add extra files, update `--glob` so the gate checks all of
   them.

4. **Raise the ceiling** (only if the current content is genuinely
   necessary — document the justification):
   ```yaml
   # harness.config.yaml
   profiles:
     standard:
       gates:
         agents_md_token:
           max_tokens: 1200   # raised from 800 — content is essential ref material
   ```

5. **Temporarily use advisory mode** to audit without blocking, then address
   issues file by file:
   ```bash
   /harness:agents-md-token-gate --no-fail-on-error
   ```

---

## Options

| Flag | Default | Effect |
|---|---|---|
| `--max-tokens N` | `800` | Maximum allowed estimated tokens per file (integer). |
| `--glob PATTERN` | `**/AGENTS.md` | Glob pattern for discovery, relative to `--project-root`. |
| `--chars-per-token N` | `4.0` | Characters-per-token ratio for estimation (positive float). |
| `--no-fail-on-error` | *(blocking by default)* | Downgrade violations to warnings; gate always exits `0`. |
| `--project-root PATH` | `.` | Repository root for resolving glob discovery. |

---

## harness.config.yaml integration

The gate reads its configuration from `harness.config.yaml` when present.
Profile defaults:

| Profile | Enabled | Max tokens | Fail on error |
|---|---|---|---|
| `starter` | yes | 500 | yes |
| `standard` | yes | 800 | yes |
| `advanced` | yes | 1 500 | yes |

Override per-project:

```yaml
# harness.config.yaml
active_profile: standard

profiles:
  standard:
    gates:
      agents_md_token:
        enabled: true
        fail_on_error: true
        max_tokens: 800          # tokens per AGENTS.md file
        glob_pattern: "**/AGENTS.md"
        chars_per_token: 4.0     # chars-per-token estimation ratio
```

A `--max-tokens` flag passed at invocation time **always takes precedence**
over the YAML value.

---

## CI/CD integration

### GitHub Actions — standalone token-budget gate

Add a step to any existing workflow (or create
`.github/workflows/agents-md-token-gate.yml`):

```yaml
name: AGENTS.md Token-Budget Gate
on: [pull_request]

jobs:
  agents-md-token:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install harness-skills
      - run: |
          python -m harness_skills.gates.agents_md_token \
            --max-tokens ${{ vars.AGENTS_MD_MAX_TOKENS || '800' }}
```

### GitLab CI — `agents-md-token-gate` job

```yaml
agents-md-token-gate:
  stage: lint
  script:
    - pip install harness-skills
    - python -m harness_skills.gates.agents_md_token --max-tokens 800
  only:
    - merge_requests
```

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Enforce AGENTS.md token budgets on a PR right now | **`/harness:agents-md-token-gate`** ← you are here |
| Run all quality gates at once | `/harness:evaluate` |
| Check that AGENTS.md is not stale | `/harness:docs-freshness` |
| Enforce code-coverage threshold | `/harness:coverage-gate` |
| Run security checks | `/harness:security-check-gate` |
| Bootstrap the full harness | `/harness:create` |

---

## Notes

- **Read-only** — this skill never modifies AGENTS.md files or the state
  service.  It only reads and counts.
- **Token counts are estimates** — the `ceil(chars / chars_per_token)` heuristic
  is fast and stack-agnostic but will differ from exact tokeniser output by a
  small margin (typically ±5–10 %).  For repositories where precision matters,
  consider wrapping `tiktoken` or `anthropic.count_tokens()` in a custom plugin
  gate.
- **Symlinks are skipped** — the glob scan does not follow symbolic links, so
  symlinked AGENTS.md files are not counted.  This avoids infinite loops in
  repositories with symlinked sub-trees.
- **No-files-found is advisory** — missing AGENTS.md files are not treated as
  a policy violation; only a warning is emitted and the gate passes.  This
  avoids blocking brand-new repositories that have not yet created their first
  AGENTS.md.
- **Profile defaults are graduated** — the token ceiling tightens as you move
  from `advanced` (1 500) → `standard` (800) → `starter` (500), reflecting
  the expectation that more complex projects need richer documentation while
  simpler projects benefit from stricter discipline.
- **Exit code `2`** is reserved for internal gate errors (e.g. unexpected
  exception in the runner).  Distinguish it from `1` (policy violation) in
  CI scripts.
- **`chars_per_token=4.0`** is the widely-cited approximation for
  English+code mixed content.  Markdown-heavy files (more punctuation, short
  lines) tend to tokenise slightly more tokens per character; pure prose
  slightly fewer.  Adjust via `--chars-per-token` if your AGENTS.md style is
  substantially different from typical mixed content.
