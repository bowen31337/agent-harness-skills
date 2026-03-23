# AGENTS.md Generator

Generate or refresh `AGENTS.md` — the agent-facing reference document for this repository.
The generated file includes an **Architecture Overview** section that maps every domain
package, its public API surface, and the direction of cross-domain dependencies, so agents
understand the codebase structure before writing any code.

---

## Usage

```bash
# Regenerate AGENTS.md from scratch (or refresh in-place)
/agents-md-generator

# Dry-run — print the generated content without writing to disk
/agents-md-generator --dry-run

# Limit the architecture section to top-level domains only
/agents-md-generator --shallow

# Specify a custom output path (default: AGENTS.md at project root)
/agents-md-generator --out docs/AGENTS.md
```

---

## Instructions

### Step 0 — Collect generation metadata

```bash
RUN_DATE=$(date '+%Y-%m-%d')
HEAD_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "no-git")
SERVICE_NAME=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")
```

---

### Step 1 — Detect language(s)

```bash
# Python packages?
find . -name "__init__.py" \
  -not -path "./.venv/*" -not -path "./node_modules/*" | head -5

# JS/TS packages?
find . \( -name "index.ts" -o -name "index.js" \) \
  | grep -v node_modules | grep -v dist | head -5
```

Set `LANG_MODE` to `python`, `js`, or `both` based on what is found.

---

### Step 2 — Discover domain packages

#### Python

A *domain package* is any directory that:
- Contains an `__init__.py`, **and**
- Lives at depth 1 or 2 beneath a recognised source root, **and**
- Is **not** a test package (`tests/`, `test_*`, `*_test`).

```bash
find . -name "__init__.py" \
  -not -path "./.venv/*" \
  -not -path "./node_modules/*" \
  -not -path "*/tests/*" \
  -not -path "*/test_*" \
  | sed 's|/__init__.py||' \
  | sort
```

#### JS / TS

A *domain package* is any directory that contains an `index.ts` or `index.js`
beneath `src/` and is not under `node_modules/`, `dist/`, or `__tests__/`.

```bash
find src \( -name "index.ts" -o -name "index.js" \) \
  | grep -v node_modules | grep -v dist | grep -v __tests__ \
  | sed 's|/index\.[tj]s||' \
  | sort
```

Collect results into **DOMAINS**.

---

### Step 3 — Analyse each domain's public surface

For each domain in DOMAINS:

#### 3a — API surface declaration

**Python** — check for `__all__`:

```bash
grep -n "__all__" <domain>/__init__.py 2>/dev/null || echo "__MISSING__"
```

- Present → **EXPLICIT** ✅
- Absent → **IMPLICIT** ⚠️
- File missing entirely → **NONE** ❌

**JS/TS** — check for named exports:

```bash
grep -n "^export " <domain>/index.ts 2>/dev/null \
  || grep -n "^export " <domain>/index.js 2>/dev/null \
  || echo "__MISSING__"
```

- Named `export` statements → **EXPLICIT** ✅
- `export *` only → **WILDCARD** 🔶
- Nothing → **IMPLICIT** ⚠️

#### 3b — Extract key exported symbols

For EXPLICIT domains, list the first 5–10 public symbols to give agents a quick
orientation:

**Python:**
```bash
python3 -c "
import ast, sys
src = open('<domain>/__init__.py').read()
tree = ast.parse(src)
for node in ast.walk(tree):
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id == '__all__':
                if isinstance(node.value, ast.List):
                    names = [e.s for e in node.value.elts if isinstance(e, ast.Constant)]
                    print(', '.join(names[:10]))
" 2>/dev/null || grep -o '"[^"]*"' <domain>/__init__.py | head -10 | tr '\n' ' '
```

**JS/TS:**
```bash
grep "^export " <domain>/index.ts 2>/dev/null \
  | sed 's/export [^{]*{\([^}]*\)}.*/\1/' \
  | head -5
```

---

### Step 4 — Map dependency flow direction

For each domain, determine which *other* domains it imports from:

**Python:**
```bash
grep -rn "^from \|^import " <domain>/ \
  --include="*.py" \
  --exclude-dir=__pycache__ \
  2>/dev/null \
  | grep -v "^<domain>/__init__" \
  | grep -oP '(?<=from )\S+|(?<=import )\S+' \
  | grep -v "^\." \
  | sort -u
```

Cross-reference each import against **DOMAINS** to identify intra-project
dependencies.  For each pair `(A → B)` record:

```
A depends on B   (A imports from B's public surface)
```

Build a directed adjacency list:

```python
deps = {
    "harness_skills/cli":        ["harness_skills/models", "harness_skills/generators"],
    "harness_skills/gates":      ["harness_skills/models", "harness_skills/plugins"],
    "harness_skills/generators": ["harness_skills/models"],
    "harness_skills/plugins":    ["harness_skills/models"],
    "harness_skills/models":     [],   # foundation — no local deps
    "harness_skills/utils":      [],
}
```

Identify **foundation layers** (no outgoing edges to other project domains) and
**orchestration layers** (highest in-degree, most things depend on them).

---

### Step 5 — Build the Architecture Overview section

Using the data collected in Steps 2–4, render the following sub-sections:

#### 5a — Domain Map table

```markdown
## Architecture Overview

### Domain Map

| # | Domain | Lang | API Surface | Key Symbols | Role |
|---|--------|------|-------------|-------------|------|
| 1 | `harness_skills/models` | Python | ✅ EXPLICIT | `Status`, `GateResult`, `Violation`, … | Foundation — no local deps |
| 2 | `harness_skills/plugins` | Python | ✅ EXPLICIT | `PluginGateConfig`, `load_plugin_gates`, … | Gate plugin system |
| 3 | `harness_skills/gates` | Python | ✅ EXPLICIT | `CoverageGate`, `GateEvaluator`, `run_gates` | Built-in gate runners |
| 4 | `harness_skills/generators` | Python | ✅ EXPLICIT | `EvaluationReport`, `run_all_gates` | Artifact generators |
| 5 | `harness_skills/cli` | Python | ✅ EXPLICIT | `cli`, `PipelineGroup` | CLI entry point |
```

Rules for the **Role** column:
- A domain with 0 outgoing project-deps → `Foundation — no local deps`
- A domain depended on by ≥ 3 others → `Core shared library`
- A domain that imports from ≥ 3 others → `Orchestration / entry-point layer`
- Otherwise → derive a 3–5 word summary from the domain name + `__all__` symbols

#### 5b — Dependency flow diagram

Render a text-art tree showing the **flow of imports** (arrows point from
dependent → dependency, i.e. "A → B" means A imports B):

```markdown
### Dependency Flow

```
<orchestration>
    │
    ├── <domain-A> ──► <foundation>
    │       │
    │       └──────── ► <shared-lib>
    │
    ├── <domain-B> ──► <foundation>
    │
    └── <domain-C> ──► <shared-lib>
                    ──► <foundation>

<standalone>   (no local deps — safe to import anywhere)
<standalone2>  (no local deps — safe to import anywhere)
```
```

For this project the rendered diagram should match the actual dependency graph
discovered in Step 4.  Use `──►` for dependency arrows and indent child nodes
with `│   ` / `├── ` / `└── ` connectors.

#### 5c — Boundary status summary

```markdown
### Module Boundary Status

> Source of truth: run `/module-boundaries` to refresh violations.

| Domain | Boundary | Violations |
|--------|----------|------------|
| `harness_skills/models` | ✅ EXPLICIT | 17 (tests only) |
| `harness_skills/plugins` | ✅ EXPLICIT | 6 (tests only) |
| `dom_snapshot_utility` | ✅ EXPLICIT | 1 |
| … | … | … |

**Rules agents must follow:**
- Always import from the domain root (`from harness_skills.models import …`), never from sub-modules.
- Never import a private symbol (leading `_`) across a domain boundary.
- See `ARCHITECTURE.md` and `.claude/principles.yaml` (`MB001`–`MB014`) for full enforcement rules.
```

---

### Step 6 — Collect existing content from AGENTS.md

If `AGENTS.md` already exists:

1. Read the full file.
2. Strip the existing `<!-- harness:auto-generated … -->` provenance block and any
   existing `## Architecture Overview` section (they will be regenerated).
3. Preserve **all other sections** verbatim (e.g., `## Browser Automation`,
   `## Environment Variables`, hand-written notes).

If the file does not exist, start with an empty body.

---

### Step 7 — Assemble and write AGENTS.md

Write (or overwrite) `AGENTS.md` using this exact structure:

```markdown
<!-- harness:auto-generated — do not edit this block manually -->
last_updated: <RUN_DATE>
head: <HEAD_HASH>
service: <SERVICE_NAME>
<!-- /harness:auto-generated -->

Agent-facing reference for this repository.

---

## Architecture Overview

<content from Step 5 — Domain Map, Dependency Flow, Boundary Status>

---

<all preserved sections from Step 6, each separated by ---  >
```

Rules:
- The provenance block is always **first** — nothing above it.
- The `## Architecture Overview` section is always **immediately after** the
  provenance block and the one-line description.
- Preserved sections follow in their original order.
- Do **not** auto-commit.  Stage with `git add AGENTS.md` after writing.
- If `--dry-run` is passed, print the assembled content to stdout and exit without
  writing any files.

---

### Step 8 — Summary

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅ AGENTS.md generated
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Domains mapped:       <N>
  Dependency edges:     <E>
  Boundary violations:  <V>  (run /module-boundaries to fix)
  Preserved sections:   <S>

  File written:  AGENTS.md  (<size> lines)

  Next steps:
    • Commit:          git add AGENTS.md && git commit -m "docs: refresh AGENTS.md"
    • Fix violations:  /module-boundaries
    • Full audit:      /check-code
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Flags

| Flag | Behaviour |
|---|---|
| `--dry-run` | Print generated content to stdout; do not write any files |
| `--shallow` | Include top-level domains only (skip sub-packages at depth > 1) |
| `--out <path>` | Write to a custom path instead of `AGENTS.md` |
| `--no-arch` | Skip the Architecture Overview section (use if `ARCHITECTURE.md` is the canonical source) |
| `--arch-only` | Only regenerate the Architecture Overview section; preserve all other content exactly |

---

## Notes

- **Idempotent** — safe to re-run at any time.  The provenance block and
  `## Architecture Overview` section are always regenerated; all other content is
  preserved.
- **Read-only analysis** — Steps 1–5 never write files.  Only Step 7 writes
  `AGENTS.md` (unless `--dry-run`).
- **Complements `/module-boundaries`** — this skill *reads* boundary data to
  populate AGENTS.md; it does not update `.claude/principles.yaml`.  Run
  `/module-boundaries` first if you want fresh violation counts.
- **Complements `/architecture`** — `ARCHITECTURE.md` is the deep technical
  reference; `AGENTS.md` is the agent-actionable quick-reference.  Both can
  coexist.  The Architecture Overview section in AGENTS.md intentionally mirrors
  the key tables from ARCHITECTURE.md in a more compact form.
- **CI-safe** — all discovery steps use read-only shell commands; no network
  calls are made.
