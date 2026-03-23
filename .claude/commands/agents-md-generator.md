# AGENTS.md Generator — Context Depth Map

Scan the repository and write (or refresh) the `## Context Depth Map` section
in the root **`AGENTS.md`**, grouping every relevant file into three tiers with
per-level token budgets.

```
/agents-md-generator              # scan cwd and refresh AGENTS.md
/agents-md-generator --dry-run    # print map to stdout; do not write AGENTS.md
/agents-md-generator --budget N   # override per-file token estimate (default: 10 tokens/line)
```

---

## What this skill produces

A fenced block inside `AGENTS.md` that looks like:

```
<!-- harness:context-depth-map -->
### L0 — Root Overview  (budget: ~3 200 tokens)  …
### L1 — Domain Docs    (budget: ~800 tokens / domain)  …
### L2 — File-Level     (budget: ~300 tokens / file)  …
<!-- /harness:context-depth-map -->
```

Agents read this map to decide *which tier to load* before starting work,
instead of doing a full codebase dump.

---

## Instructions

### Step 1 — Collect candidate files

Run these three discovery passes from the repo root.  Collect **paths only**;
do not read file contents.

#### 1a — L0: root-level documentation and configuration

```bash
# All markdown files, YAML config, and pyproject at the repo root (depth = 1)
find . -maxdepth 1 -type f \
  \( -name "*.md" -o -name "*.yaml" -o -name "*.yml" \
     -o -name "*.toml" -o -name "*.json" -o -name "*.txt" \) \
  -not -name ".*" \
  2>/dev/null | sort
```

Keep only files whose names match the pattern:

```
L0_KEEP = {
    # Human-readable docs
    "README.md", "AGENTS.md", "ARCHITECTURE.md", "PRINCIPLES.md",
    "SPEC.md", "ERROR_HANDLING_RULES.md", "EVALUATION.md",
    "HEALTH_CHECK_SPEC.md", "CLAUDE.md", "CONTRIBUTING.md", "CHANGELOG.md",
    # Project config
    "pyproject.toml", "requirements.txt", "claw-forge.yaml",
    "harness.config.yaml", "package.json",
}
```

Anything not in `L0_KEEP` (e.g. lock files, `.env.example`) is silently skipped.

#### 1b — L1: package / domain entry points

```bash
# __init__.py files at depth 2–3 (i.e. top-level packages and their sub-packages)
find . -mindepth 2 -maxdepth 3 -name "__init__.py" \
  -not -path '*/.git/*' -not -path '*/node_modules/*' \
  -not -path '*/__pycache__/*' -not -path '*/dist/*' \
  2>/dev/null | sort

# index.ts / index.js for TypeScript/JS repos
find . -mindepth 2 -maxdepth 3 \( -name "index.ts" -o -name "index.js" \) \
  -not -path '*/.git/*' -not -path '*/node_modules/*' \
  -not -path '*/dist/*' \
  2>/dev/null | sort

# domain-level README files
find . -mindepth 2 -maxdepth 3 -name "README.md" \
  -not -path '*/.git/*' \
  2>/dev/null | sort

# skill command files
find .claude/commands -type f -name "*.md" 2>/dev/null | sort
```

#### 1c — L2: individual source files

```bash
# Python source files, excluding __init__.py already captured in L1
find . -name "*.py" \
  -not -name "__init__.py" \
  -not -path '*/.git/*' -not -path '*/__pycache__/*' \
  -not -path '*/dist/*' -not -path '*/build/*' \
  -not -path '*/migrations/*' \
  2>/dev/null | sort

# TypeScript / JavaScript
find . \( -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" \) \
  -not -path '*/.git/*' -not -path '*/node_modules/*' \
  -not -path '*/dist/*' -not -path '*/build/*' \
  2>/dev/null | sort
```

Exclude test files from L2's *primary listing* but include them in a
collapsible **Tests** sub-section under L2:

```
TEST_PATTERNS = [r'/tests?/', r'_test\.py$', r'\.spec\.(ts|js)$', r'test_.*\.py$']
```

---

### Step 2 — Estimate token budgets

For every file collected, compute a line count **without reading the file**:

```bash
wc -l <path> 2>/dev/null | awk '{print $1}'
```

Convert lines → estimated tokens using:

```
CHARS_PER_LINE   = 60     # conservative average across code + markdown
CHARS_PER_TOKEN  = 4      # OpenAI / Anthropic rule of thumb
tokens_per_line  = CHARS_PER_LINE / CHARS_PER_TOKEN   # = 15
estimated_tokens = lines * tokens_per_line
```

Round to the nearest 50 for display.  Cap displayed values at 9 999.

Compute **tier totals**:

```python
l0_total = sum(est_tokens for f in l0_files)
l1_budget_per_domain = median(est_tokens for domain_init in l1_files)
l2_budget_per_file   = median(est_tokens for f in l2_files)
```

---

### Step 3 — Group L1 files into named domains

Derive the **domain name** from the parent directory of each L1 file:

```python
from pathlib import Path

def domain_name(path: str) -> str:
    p = Path(path)
    # e.g. harness_skills/models/__init__.py → "harness_skills · models"
    parts = [part for part in p.parts[1:-1]]   # strip leading '.' and filename
    return " · ".join(parts) if parts else p.parts[1]
```

Group all L1 files under their top-level package (first component after `./`).

---

### Step 4 — Build the depth-map block

Render the following Markdown.  Use **real numbers** from Steps 1–3;
do not hard-code estimates.

```markdown
<!-- harness:context-depth-map -->
<!-- regenerate: /agents-md-generator  last_updated: <ISO-DATE>  head: <git-sha-short> -->

## Context Depth Map

> **Reading guide**
> Load only the tier(s) relevant to your task.  Prefer patterns + Grep over
> loading entire files.  Budget figures assume ~15 tokens per line.

---

### Tier Summary

| Tier | Scope | Files | Total Est. Tokens | Load when… |
|------|-------|-------|-------------------|-----------|
| **L0** | Root overview — project-wide docs & config | N | ~T | First orientation; always load |
| **L1** | Domain docs — package `__init__` / index | N | ~T each domain | Entering a new package |
| **L2** | File-level — individual source modules | N | ~T each file | Touching specific logic |

---

### L0 — Root Overview  (total budget: ~T tokens)

Load **all** L0 files for project orientation.

| File | Lines | Est. Tokens | Purpose |
|------|-------|-------------|---------|
| `README.md` | L | ~T | … |
| …  |  |  |  |

---

### L1 — Domain Docs  (budget: ~T tokens per domain)

Load the domain(s) relevant to your task.

#### `<domain>` — <one-line description>

| File | Lines | Est. Tokens | Public symbols / purpose |
|------|-------|-------------|--------------------------|
| `…/__init__.py` | L | ~T | exports: … |

…one section per top-level package…

---

### L2 — File-Level Comments  (budget: ~T tokens per file)

Load individual files only when you need to edit or trace through their logic.

#### `<domain>` files

| File | Lines | Est. Tokens | Responsibility |
|------|-------|-------------|----------------|
| `harness_skills/handoff.py` | L | ~T | Agent handoff protocol |
| … |  |  |  |

<details>
<summary>Tests (<N> files, ~T tokens total)</summary>

| File | Lines | Est. Tokens |
|------|-------|-------------|
| … |  |  |

</details>

<!-- /harness:context-depth-map -->
```

---

### Step 5 — Write AGENTS.md

#### Locate or create the auto-generated block

Search for an existing `<!-- harness:context-depth-map -->` block in `AGENTS.md`:

```python
import re

OPEN_TAG  = "<!-- harness:context-depth-map -->"
CLOSE_TAG = "<!-- /harness:context-depth-map -->"

with open("AGENTS.md", "r") as fh:
    content = fh.read()

pattern = re.compile(
    re.escape(OPEN_TAG) + r".*?" + re.escape(CLOSE_TAG),
    re.DOTALL,
)
```

- **If the block exists:** replace it in-place with the newly rendered block.
- **If the block does not exist:** append the new block at the end of `AGENTS.md`.

Preserve the `<!-- harness:auto-generated -->` header block at the top of
`AGENTS.md`; never remove it.

Update `last_updated` in both headers to today's ISO date.

#### Commit message hint (do NOT commit automatically)

```
docs(agents): refresh context depth map [auto]
```

---

### Step 6 — Emit a summary to stdout

After writing (or in `--dry-run` mode), print:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  AGENTS.md — Context Depth Map refreshed
  L0: <N> files  ~<T> tokens total
  L1: <N> files across <D> domains  ~<T> tokens/domain
  L2: <N> source files  ~<T> tokens each  |  <N> test files
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Options

| Flag | Effect |
|---|---|
| `--dry-run` | Print rendered block to stdout; do not modify `AGENTS.md` |
| `--budget N` | Override tokens-per-line estimate (default: 15) |
| `--l2-limit N` | Cap L2 table at N files per domain (default: 30) |
| `--include-tests` | Expand test files inline rather than inside `<details>` |
| `--no-git` | Skip `git rev-parse` for the `head:` metadata field |

---

## When to re-run this skill

| Event | Action |
|---|---|
| Adding or deleting a source file | Re-run `/agents-md-generator` |
| Renaming a top-level package | Re-run `/agents-md-generator` |
| Significantly growing a file (>100 lines added) | Re-run to refresh token estimates |
| Before opening a PR that adds a major feature | Re-run as part of docs-freshness gate |

---

## Notes

- **Idempotent** — running twice produces the same output; safe to run in CI.
- **Read-only scan** — only `wc -l` and path discovery; no file contents loaded.
- **Does not overwrite** non-auto-generated sections of `AGENTS.md`.
- **Token estimates are intentionally approximate** — add 20 % margin when
  planning context-window budgets for downstream agents.
- Pairs well with `/harness:context` (file-ranking for a specific plan) and
  `/doc-freshness-gate` (staleness checks).
