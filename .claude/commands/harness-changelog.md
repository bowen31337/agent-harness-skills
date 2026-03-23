# Harness Changelog

Generate or update `docs/harness-changelog.md` with a timestamped entry recording every change made to the harness in this update run — skills added/modified/removed, config tweaks, and doc edits. Enables teams to review harness evolution over time.

## Instructions

### Step 1: Determine the diff range

Find the git hash recorded in the *last* changelog entry so we only capture new changes. If no changelog exists yet, diff against the initial commit.

```bash
# Check whether the changelog already exists
CHANGELOG="docs/harness-changelog.md"

if [ -f "$CHANGELOG" ]; then
  # Extract the most-recently recorded git hash (first 7-char hash found in file)
  LAST_HASH=$(grep -oE '[0-9a-f]{7,40}' "$CHANGELOG" | head -1)
  echo "Last recorded hash: $LAST_HASH"
else
  # First run — use the repo's root commit as the base
  LAST_HASH=$(git rev-list --max-parents=0 HEAD)
  echo "No changelog yet — diffing from initial commit: $LAST_HASH"
fi

HEAD_HASH=$(git rev-parse --short HEAD)
HEAD_BRANCH=$(git rev-parse --abbrev-ref HEAD)
RUN_DATE=$(date '+%Y-%m-%d')
RUN_TIME=$(date '+%H:%M:%S')

echo "Head: $HEAD_HASH  Branch: $HEAD_BRANCH  Date: $RUN_DATE $RUN_TIME"
```

### Step 2: Collect changed files

```bash
# Files changed between LAST_HASH and HEAD
git diff --name-status "$LAST_HASH" HEAD -- \
  '.claude/commands/' \
  'claw-forge.yaml' \
  'CLAUDE.md' \
  'docs/' \
  'README.md' \
  'spec/app_spec.txt' \
  'spec/app_spec.example.xml' 2>/dev/null || \
git diff --name-status "$LAST_HASH"..HEAD 2>/dev/null

echo "---"

# Commits in range
git log --oneline "$LAST_HASH"..HEAD 2>/dev/null || \
git log --oneline -10
```

Categorize output into four groups:

| Group | Paths matched |
|-------|---------------|
| **Skills** | `.claude/commands/*.md` |
| **Config** | `claw-forge.yaml`, `CLAUDE.md`, `.env.example` |
| **Docs** | `docs/**`, `README.md` |
| **Spec** | `spec/app_spec.txt`, `spec/app_spec.example.xml` |

For each changed file record the status letter:
- `A` → ✅ Added
- `M` → 📝 Modified
- `D` → ❌ Removed
- `R` → 🔀 Renamed

### Step 3: Count the skill inventory

```bash
echo "Current skill count:"
ls .claude/commands/*.md 2>/dev/null | wc -l

echo "Skill list:"
ls .claude/commands/*.md 2>/dev/null | xargs -I{} basename {}
```

### Step 4: Build the new changelog entry

Compose a markdown block using the data collected above:

```markdown
## <RUN_DATE> — `<HEAD_HASH>` — <HEAD_BRANCH>

> Run at <RUN_TIME>  ·  Diffed from `<LAST_HASH>`

### Skills  (<N> total)
- <STATUS_ICON> `<filename>` — <Added|Modified|Removed>
<!-- repeat for each changed skill; if none: "- No skill changes" -->

### Config
- <STATUS_ICON> `<filename>`
<!-- repeat; if none: "- No config changes" -->

### Docs
- <STATUS_ICON> `<filename>`
<!-- repeat; if none: "- No doc changes" -->

### Spec
- <STATUS_ICON> `<filename>`
<!-- repeat; if none: "- No spec changes" -->

### Commits
- `<hash>` — <message>
<!-- repeat for each commit in range; if none: "- No new commits" -->

---
```

### Step 5: Write / append to the changelog

```bash
CHANGELOG="docs/harness-changelog.md"
mkdir -p docs

if [ ! -f "$CHANGELOG" ]; then
  # Bootstrap the file with a header
  cat > "$CHANGELOG" <<'HEADER'
# Harness Changelog

Tracks every harness update run — skills added or modified, config tweaks, doc edits.
Each entry is anchored to a git commit hash so you can `git checkout <hash>` to inspect
the exact state at that point in time.

---

HEADER
fi

# Prepend the new entry (newest-first ordering)
ENTRY="<composed entry from Step 4>"

# Write entry at top (after the file header, before any existing entries)
# Use python3 for reliable in-place prepend after the header block
python3 - "$CHANGELOG" "$ENTRY" <<'PY'
import sys, pathlib

changelog_path = pathlib.Path(sys.argv[1])
new_entry      = sys.argv[2]

content = changelog_path.read_text()

# Insert after the trailing "---\n" of the file header
marker = "---\n\n"
idx = content.find(marker)
if idx == -1:
    content = content + "\n" + new_entry + "\n"
else:
    insert_at = idx + len(marker)
    content = content[:insert_at] + new_entry + "\n\n" + content[insert_at:]

changelog_path.write_text(content)
print("Changelog updated.")
PY
```

### Step 6: Stage and confirm (do NOT auto-commit)

```bash
git add docs/harness-changelog.md
git status --short docs/harness-changelog.md
```

Output a confirmation card:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Harness Changelog — entry recorded
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Date   : <RUN_DATE> <RUN_TIME>
  Hash   : <HEAD_HASH>  (<HEAD_BRANCH>)
  Diff   : <LAST_HASH>..<HEAD_HASH>

  Changes captured
  ├─ Skills   : <N added> added · <N modified> modified · <N removed> removed
  ├─ Config   : <N> file(s)
  ├─ Docs     : <N> file(s)
  └─ Commits  : <N> commit(s) in range

  Artifact   : docs/harness-changelog.md  (staged, not committed)

  Tip: run /checkpoint to bundle this with a full project snapshot.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Notes

- The skill is **idempotent** — re-running on the same HEAD hash produces a duplicate-safe entry (the diff range will be empty and is marked "No new commits").
- It **never auto-commits** — harness owners decide when to include the changelog in a commit.
- Run this skill at the end of every harness update session before handing off to team members.
- The `docs/harness-changelog.md` file should be committed alongside harness changes so the artifact stays in sync with the git history.
