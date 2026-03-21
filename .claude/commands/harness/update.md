# Harness Update

Re-scan the codebase and **update existing harness artifacts** — skill definitions,
`CLAUDE.md`, `harness.config.yaml`, `AGENTS.md` files, and related docs — while
**preserving any manual edits** the team has made since the last generation pass.

Use this skill whenever the project has drifted from its harness baseline: new files
were added, dependencies changed, or the stack evolved and existing artifacts are out
of date.

---

## Usage

```bash
# Full update — re-scan everything, update all artifacts
/harness:update

# Dry-run — show what would change without writing anything
/harness:update --dry-run

# Limit scope to specific artifact types
/harness:update --only skills
/harness:update --only config
/harness:update --only agents-md

# Skip a specific artifact type
/harness:update --skip skills

# Force overwrite even of manually-edited sections (use carefully)
/harness:update --force

# Write a changelog entry after updating
/harness:update --changelog
```

---

## Instructions

### Step 1 — Snapshot current artifact state

Before touching anything, record the pre-update state so diffs can be computed and
manual edits can be identified.

```bash
RUN_DATE=$(date '+%Y-%m-%d')
RUN_TIME=$(date '+%H:%M:%S')
HEAD_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "no-git")

echo "Harness update starting: $RUN_DATE $RUN_TIME  HEAD=$HEAD_HASH"

# List all tracked harness artifacts
ARTIFACTS=(
  "CLAUDE.md"
  "harness.config.yaml"
  "AGENTS.md"
  "ARCHITECTURE.md"
  "PRINCIPLES.md"
  "EVALUATION.md"
  ".claude/commands/harness/context.md"
  ".claude/commands/harness/lint.md"
  ".claude/commands/harness/telemetry.md"
  ".claude/commands/harness/detect-stale.md"
  ".claude/commands/harness/update.md"
)

for f in "${ARTIFACTS[@]}"; do
  if [ -f "$f" ]; then
    echo "EXISTS  $f  ($(wc -l < "$f") lines)"
  else
    echo "MISSING $f"
  fi
done
```

---

### Step 2 — Detect the project stack

Re-run stack detection to identify what languages, frameworks, and tools are present.
Compare results against what is currently recorded in `harness.config.yaml`.

```bash
echo "=== Stack detection ==="

# Language indicators
[ -f "requirements.txt" ] || [ -f "pyproject.toml" ] || [ -f "setup.py" ] \
  && echo "lang: python"
[ -f "package.json" ] && echo "lang: typescript/javascript"
[ -f "go.mod" ]        && echo "lang: go"
[ -f "Cargo.toml" ]    && echo "lang: rust"
[ -f "pom.xml" ]       && echo "lang: java/kotlin"

# Framework indicators
[ -f "manage.py" ]              && echo "framework: django"
grep -q '"fastapi"' requirements.txt 2>/dev/null && echo "framework: fastapi"
grep -q '"flask"'   requirements.txt 2>/dev/null && echo "framework: flask"
grep -q '"next"'    package.json     2>/dev/null && echo "framework: nextjs"
grep -q '"react"'   package.json     2>/dev/null && echo "framework: react"

# Test runner
[ -f "pytest.ini" ] || [ -f "conftest.py" ] && echo "test: pytest"
grep -q '"jest"'    package.json 2>/dev/null  && echo "test: jest"
grep -q '"vitest"'  package.json 2>/dev/null  && echo "test: vitest"

# Build tools
[ -f "Makefile" ]   && echo "build: make"
[ -f "Dockerfile" ] && echo "infra: docker"
```

Read `harness.config.yaml` (if it exists) and compare detected stack against the
`stack` section.  Note any drift as "new" or "removed" entries.

---

### Step 3 — Identify manual edits (preserve them)

For each existing artifact, check whether it contains **user-authored content** that
must be preserved.  Look for the following markers:

| Marker | Meaning |
|---|---|
| `<!-- TODO: ... -->` | User placeholder — preserve as-is |
| `<!-- CUSTOM: ... -->` | Explicitly user-edited section — never overwrite |
| Lines that differ from the last generated baseline (git diff) | May be manual |
| `CLAUDE.md` sections under `## Build & Test` or `## Project Overview` | Treat as user-owned |

```bash
# Check git blame / diff for each artifact to identify manual changes
for f in CLAUDE.md harness.config.yaml AGENTS.md; do
  if [ -f "$f" ]; then
    DIFF=$(git diff HEAD -- "$f" 2>/dev/null || echo "__no-git__")
    if [ -n "$DIFF" ] && [ "$DIFF" != "__no-git__" ]; then
      echo "MANUALLY MODIFIED (unstaged): $f"
    fi

    # Also check committed changes since last harness run
    LAST_HARNESS_COMMIT=$(git log --oneline --grep="harness" -1 --format="%H" 2>/dev/null)
    if [ -n "$LAST_HARNESS_COMMIT" ]; then
      COMMITTED_DIFF=$(git diff "$LAST_HARNESS_COMMIT" HEAD -- "$f" 2>/dev/null)
      [ -n "$COMMITTED_DIFF" ] && echo "CHANGED SINCE LAST HARNESS COMMIT: $f"
    fi
  fi
done
```

**Rule**: Never overwrite content between `<!-- CUSTOM-START -->` and
`<!-- CUSTOM-END -->` tags unless `--force` is passed.

---

### Step 4 — Update `CLAUDE.md`

Re-generate the auto-managed sections while preserving user content.

Sections to **auto-update** (replace with fresh content):

| Section | Source |
|---|---|
| `## Stack` | Step 2 detection results |
| `## Build & Test` | Only if currently contains the default placeholder `<!-- TODO: ... -->` |
| `## claw-forge Agent Notes` | Always regenerated from `harness.config.yaml` |

Sections to **never touch**:

- `## Project Overview` (unless it still contains the default `<!-- TODO: ... -->`)
- Any section below a `<!-- CUSTOM-START -->` marker

**Update algorithm:**

```python
import pathlib, re

claude_md = pathlib.Path("CLAUDE.md")
content = claude_md.read_text() if claude_md.exists() else ""

# Regenerate the Stack section
new_stack = build_stack_section()   # from Step 2 results
content = replace_section(content, "## Stack", new_stack)

# Regenerate claw-forge Agent Notes section
new_notes = build_agent_notes()     # from harness.config.yaml
content = replace_section(content, "## claw-forge Agent Notes", new_notes)

# Only touch Build & Test if it still has the default placeholder
if "<!-- TODO: " in get_section(content, "## Build & Test"):
    new_build = build_build_section()   # inferred from Makefile / pyproject / package.json
    content = replace_section(content, "## Build & Test", new_build)

claude_md.write_text(content)
print("CLAUDE.md updated")
```

Helper `replace_section(content, heading, new_body)` replaces the body between
`heading` and the next `##` heading (or EOF).

---

### Step 5 — Update `harness.config.yaml`

Re-scan and patch `harness.config.yaml` to reflect current project state.

Fields to **always refresh**:

```yaml
# These fields are always regenerated from the filesystem
updated_at: "<RUN_DATE>T<RUN_TIME>Z"
stack:
  languages: [<detected>]
  frameworks: [<detected>]
  test_runners: [<detected>]
  build_tools: [<detected>]
agents_md_files:
  - <list of AGENTS.md paths found under src/ and service dirs>
skill_count: <current count of .claude/commands/**/*.md>
```

Fields to **preserve if already set**:

```yaml
# Never overwrite if user has customised these
state_url: <existing value>
feature_id: <existing value>
principles_file: <existing value>
custom_gates: <existing value>
```

If `harness.config.yaml` does not exist, create it from scratch using the full
schema (see the `harness.config.yaml` template in `app_spec.example.xml`).

---

### Step 6 — Refresh `AGENTS.md` files

Scan for `AGENTS.md` files in service/module directories and update the auto-managed
header block while leaving the body intact.

```bash
# Find all AGENTS.md files (exclude venv, node_modules, dist, build, .git)
find . -name "AGENTS.md" \
  -not -path '*/.git/*' \
  -not -path '*/node_modules/*' \
  -not -path '*/__pycache__/*' \
  -not -path '*/.venv/*' \
  -not -path '*/dist/*' \
  -not -path '*/build/*' \
  2>/dev/null
```

For each `AGENTS.md`, regenerate the auto-managed front-matter block:

```markdown
<!-- harness:auto-generated — do not edit this block manually -->
last_updated: <RUN_DATE>
head: <HEAD_HASH>
service: <directory name>
<!-- /harness:auto-generated -->
```

Leave everything else in the file unchanged.

---

### Step 6.5 — Refresh front-matter in ARCHITECTURE.md, PRINCIPLES.md, and EVALUATION.md

Apply the **same auto-generated front-matter block** used for `AGENTS.md` to the
other three canonical harness artifacts, creating stub files for any that do not
yet exist.

For each of `ARCHITECTURE.md`, `PRINCIPLES.md`, and `EVALUATION.md`:

```bash
for ARTIFACT_FILE in ARCHITECTURE.md PRINCIPLES.md EVALUATION.md; do
  ARTIFACT_KIND=$(echo "$ARTIFACT_FILE" | sed 's/\.md$//' | tr '[:upper:]' '[:lower:]')

  if [ -f "$ARTIFACT_FILE" ]; then
    # File exists — replace the auto-generated block, preserve everything else
    python3 - <<'PYEOF'
import pathlib, re, sys, os

artifact_file = os.environ["ARTIFACT_FILE"]
run_date      = os.environ["RUN_DATE"]
head_hash     = os.environ["HEAD_HASH"]
artifact_kind = os.environ["ARTIFACT_KIND"]

BLOCK_START = "<!-- harness:auto-generated — do not edit this block manually -->"
BLOCK_END   = "<!-- /harness:auto-generated -->"
NEW_BLOCK   = (
    f"{BLOCK_START}\n"
    f"last_updated: {run_date}\n"
    f"head: {head_hash}\n"
    f"artifact: {artifact_kind}\n"
    f"{BLOCK_END}"
)

path    = pathlib.Path(artifact_file)
content = path.read_text()

if BLOCK_START in content:
    content = re.sub(
        re.escape(BLOCK_START) + r".*?" + re.escape(BLOCK_END),
        NEW_BLOCK,
        content,
        flags=re.DOTALL,
    )
else:
    content = NEW_BLOCK + "\n\n" + content

path.write_text(content)
print(f"Updated front-matter in {artifact_file}")
PYEOF
  else
    # File does not exist — create a minimal stub with front-matter
    cat > "$ARTIFACT_FILE" <<STUB
<!-- harness:auto-generated — do not edit this block manually -->
last_updated: ${RUN_DATE}
head: ${HEAD_HASH}
artifact: ${ARTIFACT_KIND}
<!-- /harness:auto-generated -->

<!-- TODO: fill in ${ARTIFACT_FILE} content -->
STUB
    echo "Created stub: $ARTIFACT_FILE"
  fi
done
```

**Rules:**
- The front-matter block is always the very first content in the file.
- If the file already has an existing `<!-- harness:auto-generated … -->` block,
  it is replaced in-place; everything below it is preserved verbatim.
- If no block exists, it is prepended.
- Stub files created here carry a `<!-- TODO: … -->` body — `harness:update`
  will **not** overwrite that body on future runs unless `--force` is passed
  (same preservation rules as `AGENTS.md`).

---

### Step 7 — Sync skill stubs for new file types

Check if any new file type patterns have appeared in the codebase since the last
harness run that do not yet have a corresponding skill in `.claude/commands/`.

```bash
# Extensions present in project (top 10 by file count)
find . -type f \
  -not -path '*/.git/*' -not -path '*/node_modules/*' \
  -not -path '*/.venv/*' -not -path '*/dist/*' \
  | sed 's/.*\.//' | sort | uniq -c | sort -rn | head -10
```

For each extension that maps to a known skill category but has no matching skill
stub, report it as a suggestion (do **not** auto-create skills):

```
  Suggestion: no skill found for *.graphql files.
              Consider adding a /harness:graphql-lint skill.
```

---

### Step 8 — Compute and display the diff summary

After all writes are complete (or in `--dry-run` mode, after all planned writes are
determined), produce a structured diff summary.

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Harness Update — diff summary
  Run: <RUN_DATE> <RUN_TIME>  ·  HEAD: <HEAD_HASH>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Artifact                    Action        Lines Δ
  ─────────────────────────────────────────────────
  CLAUDE.md                   updated       +3 / -1
  harness.config.yaml         updated       +5 / -2
  AGENTS.md                   updated       +1 / -1
  ARCHITECTURE.md             created       +7 / -0
  PRINCIPLES.md               updated       +1 / -1
  EVALUATION.md               created       +7 / -0
  src/auth/AGENTS.md          unchanged     —
  .claude/commands/…          unchanged     —
  ─────────────────────────────────────────────────
  4 updated · 2 unchanged · 2 created · 0 skipped

  Preserved manual edits in:
  └─ CLAUDE.md  §§ "## Project Overview" (user content)

  Skill inventory:  <N> skills  (was <M>)

  Suggestions
  ─────────────────────────────────────────────────
  • No skill found for *.graphql — consider /harness:graphql-lint

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Artifacts staged (not committed).
  Tip: run /harness:lint to validate · /checkpoint to snapshot.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

In `--dry-run` mode prefix each action with `[DRY-RUN]` and write nothing.

---

### Step 9 — Stage artifacts (do NOT auto-commit)

```bash
git add CLAUDE.md harness.config.yaml AGENTS.md ARCHITECTURE.md PRINCIPLES.md EVALUATION.md \
  $(find . -name "AGENTS.md" -not -path '*/.git/*' \
    -not -path '*/node_modules/*' -not -path '*/.venv/*' 2>/dev/null)
git status --short
```

Do **not** commit.  Harness owners decide when to include the update in a commit.

---

### Step 10 — Optional changelog entry

If `--changelog` was passed, invoke `/harness:changelog` to append an entry for
this update run:

```
  → Running /harness:changelog to record this update…
```

---

## Options

| Flag | Default | Effect |
|---|---|---|
| `--dry-run` | off | Print planned changes; write nothing |
| `--only ARTIFACT` | *(all)* | Restrict to `skills`, `config`, `agents-md`, or `claude-md` |
| `--skip ARTIFACT` | *(none)* | Skip a specific artifact type |
| `--force` | off | Overwrite `<!-- CUSTOM -->` blocks and user-edited sections |
| `--changelog` | off | Run `/harness:changelog` after updating |
| `--no-stage` | off | Skip `git add` at the end |
| `--state-url URL` | `http://localhost:8888` | Override the state service URL |

---

## Preserving manual edits — rules summary

| Content | Default behaviour | With `--force` |
|---|---|---|
| `<!-- TODO: ... -->` placeholder | Replace with generated content | Same |
| `<!-- CUSTOM-START/END -->` block | **Preserve exactly** | Overwrite |
| `## Project Overview` (non-default body) | **Preserve exactly** | Overwrite |
| `## Build & Test` (non-default body) | **Preserve exactly** | Overwrite |
| `harness.config.yaml` custom keys | **Preserve exactly** | Overwrite |
| `AGENTS.md` body below front-matter | **Preserve exactly** | Overwrite |

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Project stack/files changed, re-sync harness | **`/harness:update`** ← you are here |
| First-time harness setup | `bash harness-init.sh` |
| Record harness changes in the changelog | `/harness:changelog` |
| Validate architecture & principles | `/harness:lint` |
| Snapshot the project for handoff | `/checkpoint` |
| Find relevant files for a plan | `/harness:context` |

---

## Notes

- **Idempotent** — running `/harness:update` twice on an unchanged codebase produces
  no changes on the second run.
- **Never auto-commits** — always review the staged diff before committing.
- **Read-only scan phase** — Steps 1–3 only read files; writes begin at Step 4.
- **State service optional** — if unreachable, all features that query it are skipped
  gracefully with a warning; no errors are thrown.
- **Git not required** — if the directory is not a git repo, git-dependent steps
  (`git diff`, `git log`, `git add`) are silently skipped and the update proceeds
  using filesystem-only information.
