# Doc Freshness Gate

Verify that every `AGENTS.md` file in the repository is **fresh**: all file paths it references exist on disk, and its `last_updated` timestamp is not older than any of the files it mentions. Exits non-zero when stale or broken references are found, making it safe to use as a blocking CI gate.

---

## Instructions

### Step 1: Discover all AGENTS.md files

```bash
find . -name "AGENTS.md" \
  -not -path "./.git/*" \
  -not -path "./node_modules/*" \
  -not -path "./.venv/*"
```

Store each path as an entry in `AGENTS_FILES`. If none are found, print:

```
⚠️  No AGENTS.md files found — nothing to check.
```

and exit 0.

---

### Step 2: For each AGENTS.md — extract the auto-generated metadata block

Look for the harness auto-generated block at the top of the file:

```
<!-- harness:auto-generated — do not edit this block manually -->
last_updated: <YYYY-MM-DD>
head: <git-sha>
service: <name>
<!-- /harness:auto-generated -->
```

Parse out:
- `LAST_UPDATED` — the `last_updated` date (ISO-8601).
- `RECORDED_HEAD` — the `head` SHA recorded at generation time.

If the block is **missing**, record a warning:

```
⚠️  <path>/AGENTS.md — no harness:auto-generated block found; staleness check skipped.
```

---

### Step 3: For each AGENTS.md — extract file references

Scan the Markdown source for every string that looks like a local file path. Collect:

1. **Backtick-quoted paths** — anything inside `` ` `` that contains `/` or ends with a known extension (`.py`, `.ts`, `.js`, `.go`, `.toml`, `.yaml`, `.yml`, `.json`, `.cfg`, `.txt`, `.md`, `.sh`).

   ```bash
   grep -oP '`[^`]*\.(py|ts|js|go|toml|yaml|yml|json|cfg|txt|md|sh)[^`]*`' AGENTS.md \
     | tr -d '`'
   ```

2. **Python import paths** — lines like `from tests.browser.agent_driver import ...`; convert dotted module names to file paths (`tests/browser/agent_driver.py`).

   ```bash
   grep -oP 'from\s+([\w.]+)\s+import' AGENTS.md \
     | grep -oP '[\w.]+(?=\s+import)' \
     | sed 's/\./\//g' \
     | awk '{print $0 ".py"}'
   ```

3. **Inline code-fence paths** — file names appearing after `pytest `, `python `, `uvicorn `, or similar CLI patterns.

   ```bash
   grep -oP '(?<=pytest\s)\S+|(?<=python\s)\S+' AGENTS.md \
     | grep '/'
   ```

Deduplicate and strip any leading `./` to produce a canonical list `REFS`.

---

### Step 4: Check that every referenced file exists

For each path in `REFS`:

```bash
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
test -e "$REPO_ROOT/$ref" && echo "OK $ref" || echo "MISSING $ref"
```

Collect:
- `OK_REFS` — paths that exist.
- `MISSING_REFS` — paths that do not exist.

---

### Step 5: Check staleness against git history

This step requires the repository to be a git repo. Skip gracefully if not:

```bash
git rev-parse --is-inside-work-tree 2>/dev/null || echo "NOT_GIT=1"
```

**5a — Check whether the current HEAD matches the recorded head:**

```bash
CURRENT_HEAD=$(git rev-parse HEAD)
[ "$CURRENT_HEAD" = "$RECORDED_HEAD" ] && echo "HEAD_MATCH=1" || echo "HEAD_MATCH=0"
```

**5b — Find files modified after `last_updated`:**

For each file in `OK_REFS`:

```bash
FILE_MTIME=$(git log -1 --format="%as" -- "$ref" 2>/dev/null)
# %as = author date, short (YYYY-MM-DD)
```

If `FILE_MTIME > LAST_UPDATED`, flag the file as `STALE_REF`.

**5c — Check whether the AGENTS.md itself has been modified after `last_updated`:**

```bash
AGENTS_MTIME=$(git log -1 --format="%as" -- "$AGENTS_FILE" 2>/dev/null)
```

If `AGENTS_MTIME > LAST_UPDATED` and the recorded head differs from the current HEAD, flag the AGENTS.md as `SELF_STALE`.

---

### Step 6: Generate the gate report

Print a report for each AGENTS.md checked:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Doc Freshness Gate
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  File           AGENTS.md refs checked                Status
  ─────────────  ──────────────────────────────────── ──────
  AGENTS.md      tests/browser/agent_driver.py         ✅ exists
  AGENTS.md      tests/browser/screenshot_helper.py    ✅ exists
  AGENTS.md      tests/browser/conftest.py             ✅ exists
  AGENTS.md      pyproject.toml                        ❌ MISSING
  AGENTS.md      tests/browser/test_smoke.py           ✅ exists

  Staleness (last_updated: 2026-01-10, recorded head: 157af7b)
  ─────────────────────────────────────────────────────────────
  AGENTS.md      tests/browser/agent_driver.py         ✅ current  (2026-01-08)
  AGENTS.md      tests/browser/screenshot_helper.py    ⚠️  STALE   (2026-02-14 > 2026-01-10)
  AGENTS.md      tests/browser/conftest.py             ✅ current  (2025-12-30)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Summary
  ─────────────────────────────────────────────────────
  AGENTS.md files scanned :  1
  Total references checked :  5
  Missing files            :  1   ❌
  Stale references         :  1   ⚠️
  Gate result              :  FAILED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### Step 7: Remediation guidance

For every **missing** reference, suggest the most likely fix:

- If the filename matches a file elsewhere in the repo (different directory), show the correct path:
  ```bash
  find . -name "<filename>" -not -path "./.git/*" | head -5
  ```
  Print: `💡 Did you mean: <found-path>? Update AGENTS.md or restore the file.`

- If no match is found anywhere:
  Print: `💡 <path> no longer exists — remove or update the reference in AGENTS.md.`

For every **stale** reference, print:

```
💡 <file> was last modified <FILE_MTIME>, but AGENTS.md records last_updated: <LAST_UPDATED>.
   Re-run /harness:observe (or the AGENTS.md generator) to refresh the snapshot.
```

---

### Step 8: Exit code

| Condition                                        | Exit code |
|--------------------------------------------------|-----------|
| All references exist and all content is current  | `0`       |
| One or more references are missing               | `1`       |
| All refs exist but one or more are stale         | `2`       |
| Not a git repo (staleness check skipped)         | `0` ¹     |
| No AGENTS.md found                               | `0`       |

¹ Missing-file check still runs even outside a git repo; only staleness is skipped.

Print the final line:

```
Exit: <code>  (<reason>)
```

---

## Flags

| Flag                | Effect                                                              |
|---------------------|---------------------------------------------------------------------|
| `--path <dir>`      | Limit search to a specific directory instead of the whole repo      |
| `--fail-on-stale`   | Treat stale references as exit code `1` (same as missing)           |
| `--no-stale-check`  | Skip the staleness / git-history check entirely                     |
| `--no-remediation`  | Omit the remediation suggestions section                            |
| `--json`            | Emit a machine-readable JSON report instead of the human report     |

### JSON output format (with `--json`)

```json
{
  "gate": "doc-freshness",
  "timestamp": "<ISO-8601>",
  "files": [
    {
      "agents_md": "AGENTS.md",
      "last_updated": "2026-01-10",
      "recorded_head": "157af7b",
      "current_head": "a3c91f2",
      "references": [
        { "path": "tests/browser/agent_driver.py", "exists": true, "stale": false, "file_mtime": "2026-01-08" },
        { "path": "pyproject.toml", "exists": false, "stale": null, "file_mtime": null }
      ]
    }
  ],
  "summary": {
    "agents_md_count": 1,
    "total_refs": 5,
    "missing": 1,
    "stale": 1,
    "passed": false
  }
}
```

---

## Notes

- The gate is **read-only**: it never modifies `AGENTS.md` or any referenced file.
- To regenerate a stale `AGENTS.md`, run `/harness:observe` — it rewrites the auto-generated block and updates `last_updated` to today's date and `head` to the current commit SHA.
- To wire this into CI, add the following step to your workflow (after the checkout step):
  ```yaml
  - name: Doc Freshness Gate
    run: claude --skill doc-freshness-gate --fail-on-stale
  ```
  Or reference it via `harness evaluate --gate doc-freshness` when using the harness runner.
- Run `/ci-pipeline` to inject this gate into an existing generated workflow automatically.
