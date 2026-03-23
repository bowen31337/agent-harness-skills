# Harness Symbol Index

Scan the project's Python source files and emit `harness_symbols.json` — a
flat index that maps every **class name**, **function name**, and **async
function name** to its file path and line number.

Agents use this index to look up a symbol instantly instead of running
repeated `grep` / `rg` sweeps across the whole codebase.  The index is
written once and read many times; regenerate it whenever the codebase
changes significantly.

---

## Usage

```bash
# Regenerate from project root (most common)
/harness:symbol-index

# Write the index to a non-default path
/harness:symbol-index --output path/to/harness_symbols.json

# Restrict scanning to a subdirectory
/harness:symbol-index --root src/

# Include private symbols (names starting with _)
/harness:symbol-index --include-private

# Exclude test files from the index
/harness:symbol-index --exclude "tests/**"

# Combine filters
/harness:symbol-index --include "harness_skills/**" --exclude "**/__init__.py"
```

---

## Instructions

### Step 1 — Run the generator script

The repository ships `scripts/generate_symbol_index.py`, which uses
Python's built-in `ast` module to parse every `.py` file and extract
top-level and nested symbol definitions without executing any code.

```bash
python scripts/generate_symbol_index.py \
    --root "${ROOT:-.}" \
    --output "${OUTPUT:-harness_symbols.json}" \
    ${INCLUDE_PRIVATE:+--include-private} \
    ${EXCLUDE_GLOB:+--exclude "$EXCLUDE_GLOB"}
```

Map CLI flags from the user's invocation:

| User flag            | Script flag                         |
|----------------------|-------------------------------------|
| `--output PATH`      | `--output PATH`                     |
| `--root DIR`         | `--root DIR`                        |
| `--include GLOB`     | `--include GLOB` (repeatable)       |
| `--exclude GLOB`     | `--exclude GLOB` (repeatable)       |
| `--include-private`  | `--include-private`                 |

If `uv` is available, prefer `uv run python scripts/generate_symbol_index.py`.

---

### Step 2 — Verify output

After the script exits, confirm the file was written and print a brief
summary:

```bash
python - <<'EOF'
import json, sys
data = json.load(open("harness_symbols.json"))
counts = {}
for s in data["symbols"]:
    counts[s["type"]] = counts.get(s["type"], 0) + 1
print(f"version        : {data['version']}")
print(f"generated_at   : {data['generated_at']}")
print(f"total_symbols  : {data['total_symbols']}")
for k, v in sorted(counts.items()):
    print(f"  {k:<20}: {v}")
EOF
```

Expected output (numbers will vary):

```
version        : 1.0.0
generated_at   : 2026-03-23
total_symbols  : 612
  async_function      : 87
  class               : 134
  function            : 391
```

---

### Step 3 — Emit the result summary

Print the following human-readable banner:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Harness Symbol Index — generated
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Output : harness_symbols.json
  Date   : <generated_at>
  Symbols: <total_symbols>
             classes         : <N>
             functions       : <N>
             async functions : <N>

  Tip: agents can query this index with:
    python - <<'EOF'
    import json
    idx = {s["name"]: s for s in json.load(open("harness_symbols.json"))["symbols"]}
    print(idx.get("MyClass"))   # → {"name":…, "type":…, "file":…, "line":…}
    EOF

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Output schema

`harness_symbols.json` follows this structure:

```json
{
  "version": "1.0.0",
  "generated_at": "YYYY-MM-DD",
  "description": "Symbol index mapping …",
  "project_root": ".",
  "total_symbols": 612,
  "symbols": [
    {
      "name": "ContextManifest",
      "type": "class",
      "file": "harness_context.py",
      "line": 32
    },
    {
      "name": "get_context_manifest",
      "type": "async_function",
      "file": "harness_context.py",
      "line": 99
    },
    {
      "name": "render_report",
      "type": "function",
      "file": "harness_skills/cli/fmt.py",
      "line": 14
    }
  ]
}
```

### Symbol types

| `type`           | Python construct                  |
|------------------|-----------------------------------|
| `class`          | `class Foo:`                      |
| `function`       | `def foo():`                      |
| `async_function` | `async def foo():`                |

---

## How to consume the index

### Look up a single symbol

```python
import json

symbols = json.load(open("harness_symbols.json"))["symbols"]
index = {s["name"]: s for s in symbols}

hit = index.get("GitCheckpoint")
# → {"name": "GitCheckpoint", "type": "class",
#    "file": "git_checkpoint.py", "line": 105}
```

### Find all symbols in a file

```python
file_symbols = [s for s in symbols if s["file"] == "harness_context.py"]
```

### Fuzzy search (substring match)

```python
matches = [s for s in symbols if "lock" in s["name"].lower()]
```

---

## Options

| Flag                  | Effect                                                        |
|-----------------------|---------------------------------------------------------------|
| `--root DIR`          | Scan *DIR* instead of `.` (default: project root)            |
| `--output FILE`       | Write index to *FILE* (default: `harness_symbols.json`)      |
| `--include GLOB`      | Only index files whose relative path matches GLOB            |
| `--exclude GLOB`      | Exclude files matching GLOB (on top of built-in skips)       |
| `--include-private`   | Include names starting with `_` (default: omit them)         |
| `--quiet`             | Suppress progress output                                      |

Built-in excluded directories (always skipped):
`__pycache__`, `.git`, `.tox`, `.mypy_cache`, `.ruff_cache`,
`.pytest_cache`, `node_modules`, `dist`, `build`, `.venv`, `venv`.

---

## When to regenerate

| Trigger                                     | Action                          |
|---------------------------------------------|---------------------------------|
| New class or public function added          | Re-run `/harness:symbol-index`  |
| File renamed or deleted                     | Re-run `/harness:symbol-index`  |
| Starting a new agent session                | Check `generated_at`; refresh if > 1 day old |
| CI pre-merge gate                           | Run and commit updated index    |

---

## Notes

- **Read-only** — only `harness_symbols.json` is written; no source files are modified.
- **No execution** — uses `ast.parse()`, so no Python code is executed during scanning.
- **Private symbols** — names starting with `_` are skipped by default; pass
  `--include-private` to include them (adds ~30 % more entries).
- **Non-Python files** — only `.py` files are indexed; TypeScript, Go, etc. are out of scope
  for this skill. Extend `scripts/generate_symbol_index.py` for other languages.
- **Related skills**:
  - `/harness:context` — resolve which *files* are relevant to a plan (complements this index)
  - `/check-code` — run ruff / mypy / pytest quality gate
  - `/harness:lint` — architecture & principles enforcement
