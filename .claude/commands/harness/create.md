# Harness Create

Generate a complete harness from scratch — analyse the codebase, detect the stack,
write `harness.config.yaml` with profile-appropriate gate defaults, and optionally
chain into `lint` and `evaluate` in a single invocation.

Use this skill when bootstrapping a new project or when a project needs a full
harness for the first time.  For incremental updates to an existing harness use
`/harness:update` instead.

---

## Usage

```bash
# Minimal bootstrap — starter profile, auto-detect stack
/harness:create

# Specify a complexity profile
/harness:create --profile standard
/harness:create --profile advanced

# Provide a stack hint (skips auto-detection)
/harness:create --profile standard --stack python
/harness:create --profile advanced --stack node

# Preview without writing to disk
/harness:create --dry-run
/harness:create --dry-run --profile advanced --stack python

# Write config then immediately lint and evaluate (one-shot pipeline)
/harness:create --then lint
/harness:create --profile standard --then lint --then evaluate

# Override the output path
/harness:create --output config/harness.config.yaml

# Force full regeneration even if a config already exists
/harness:create --no-merge
```

---

## Instructions

### Step 1 — Auto-detect the project stack

Scan the project root for well-known indicator files.  Record both the detected
language and any frameworks / test runners found.

```bash
echo "=== Stack detection ==="

# Languages
[ -f "pyproject.toml" ] || [ -f "setup.py" ] || [ -f "requirements.txt" ] \
  && echo "lang: python"
[ -f "package.json" ] && echo "lang: node"
[ -f "go.mod" ]        && echo "lang: go"
[ -f "Cargo.toml" ]    && echo "lang: rust"

# Frameworks
[ -f "manage.py" ] && echo "framework: django"
grep -q "fastapi"  requirements.txt 2>/dev/null && echo "framework: fastapi"
grep -q "flask"    requirements.txt 2>/dev/null && echo "framework: flask"
grep -q '"next"'   package.json     2>/dev/null && echo "framework: nextjs"
grep -q '"react"'  package.json     2>/dev/null && echo "framework: react"

# Test runners
[ -f "pytest.ini" ] || [ -f "conftest.py" ] && echo "test: pytest"
grep -q '"jest"'   package.json 2>/dev/null   && echo "test: jest"
grep -q '"vitest"' package.json 2>/dev/null   && echo "test: vitest"
```

If `--stack` was provided by the user, skip auto-detection and use the supplied
value directly.

---

### Step 2 — Choose a profile

| Profile    | Gates included | Recommended for |
|---|---|---|
| `starter`  | regression, coverage (80 %), lint | New projects, MVPs |
| `standard` | + architecture enforcement, principles, docs freshness | Production services |
| `advanced` | + performance, security, types, telemetry, multi-agent coordination | Critical systems |

Default profile is `starter` when not specified.

---

### Step 3 — Generate the `gates:` block

Call `harness create` CLI with the resolved profile and stack:

```bash
PROFILE="${PROFILE:-starter}"
STACK="${STACK:-}"          # empty if not provided / not detected

CMD="harness create --profile $PROFILE --output ${OUTPUT:-harness.config.yaml}"
[ -n "$STACK" ]   && CMD="$CMD --stack $STACK"
[ "$DRY_RUN" = "true" ] && CMD="$CMD --dry-run"
[ "$NO_MERGE" = "true" ] && CMD="$CMD --no-merge"

$CMD
```

The CLI generates a complete `harness.config.yaml` with:

- A `gates:` block pre-populated with profile-appropriate defaults
- Inline comments explaining each threshold and where to tweak it
- A `plugins: []` section for custom shell-command gates
- Preserved surrounding YAML keys and comments when merging into an existing file
  (unless `--no-merge` is passed)

**Exit codes**

| Code | Meaning |
|---|---|
| `0` | Config written successfully (or printed for `--dry-run`) |
| `1` | Error (invalid profile, unwritable path, YAML parse failure) |

---

### Step 3.5 — Scaffold harness artifact stubs with version identifier and generation timestamp

After writing `harness.config.yaml`, create stub files for the canonical harness
artifacts that don't yet exist.  Each stub receives an
`<!-- harness:auto-generated … -->` front-matter block with a version identifier
and generation timestamp — enabling `harness:detect-stale` to track freshness
across the full artifact set.

```bash
RUN_DATE=$(date '+%Y-%m-%d')
HEAD_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "no-git")
SERVICE=$(basename "$(pwd)")

for ARTIFACT_FILE in AGENTS.md ARCHITECTURE.md PRINCIPLES.md EVALUATION.md; do
  if [ -f "$ARTIFACT_FILE" ]; then
    echo "EXISTS (skipping stub creation): $ARTIFACT_FILE"
    continue
  fi

  ARTIFACT_KIND=$(echo "$ARTIFACT_FILE" | sed 's/\.md$//' | tr '[:upper:]' '[:lower:]')

  cat > "$ARTIFACT_FILE" <<STUB
<!-- harness:auto-generated — do not edit this block manually -->
last_updated: ${RUN_DATE}
head: ${HEAD_HASH}
artifact: ${ARTIFACT_KIND}
<!-- /harness:auto-generated -->

<!-- TODO: fill in ${ARTIFACT_FILE} content -->
STUB

  echo "Created stub: $ARTIFACT_FILE"
done
```

**Rules:**
- This step runs in **create** only (not on subsequent `harness:update` calls which
  handle their own refresh via Step 6 / Step 6.5).
- Pre-existing files are **never overwritten** — the check `[ -f "$ARTIFACT_FILE" ]`
  guards against clobbering manually-edited content.
- The `artifact:` field records the document kind so `harness:detect-stale` can
  differentiate staleness thresholds per artifact type.

---

### Step 3.55 — Populate the Security Protocols section of `AGENTS.md`

After the `AGENTS.md` stub is created (or if the file already exists), append a
**Security Protocols** section covering secret handling, input validation patterns,
and auth conventions — unless the section is already present.

```bash
# Only add the section when it does not already exist
if ! grep -q "## Security Protocols" AGENTS.md 2>/dev/null; then

  cat >> AGENTS.md <<'SECURITY_SECTION'

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
api_key = "sk-abc123..."                  # SEC003 — hardcoded API key
db_url  = "postgres://user:pass@host/db"  # SEC006 — credentials in URL
```

The security gate (`/harness:security-check-gate --scan-secrets`) flags these
rule IDs:

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

If a secret is accidentally committed, **rotate it immediately** and scrub git
history with `git filter-repo` or BFG Repo Cleaner.

---

### Input Validation Patterns

All user-supplied data must be validated before use.  Use **Pydantic ≥ 2.0**
as the standard validation layer.

**Validate request payloads with Pydantic:**

```python
from pydantic import BaseModel, HttpUrl, field_validator

class TaskRequest(BaseModel):
    feature_id: str
    target_url: HttpUrl | None = None

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
| INV001  | `cursor.execute(f"… {request…}")` | Parameterised query |
| INV003  | `subprocess.call(user_input, shell=True)` | `subprocess.run([cmd], shell=False)` |
| INV004  | `eval(request.data)` | Never pass user input to `eval`/`exec` |
| INV005  | `open(request.args["path"])` | Resolve + allow-list check |
| INV006  | `requests.get(request.args["url"])` | Validate scheme + host allow-list |
| INV008  | `pickle.loads(request.body)` | Use JSON or Pydantic |

---

### Auth Conventions

All authenticated requests use **Bearer token** authentication:

```python
import os, requests

def authenticated_get(path: str) -> dict:
    resp = requests.get(
        f"{os.environ['BASE_URL']}{path}",
        headers={"Authorization": f"Bearer {os.environ['API_TOKEN']}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()
```

| Convention       | Rule                                                            |
|------------------|-----------------------------------------------------------------|
| Token source     | Always `os.environ["VAR"]` — never a string literal            |
| Header name      | `Authorization: Bearer <token>`                                 |
| Timeout          | `timeout=30` external; `timeout=10` localhost                   |
| TLS              | Production must use `https://`; `http://` only for localhost    |
| Credential rotation | Rotate immediately if exposed in logs, errors, or commits    |
SECURITY_SECTION

  echo "Security Protocols section added to AGENTS.md"
else
  echo "Security Protocols section already present in AGENTS.md — skipping"
fi
```

**Rules:**
- The section is appended only when absent — idempotent on repeated runs.
- The content is language-aware: if `--stack node` was resolved, swap the Python
  snippets for equivalent TypeScript/JS examples (use `process.env.VAR` in place
  of `os.environ["VAR"]`; use `zod` in place of Pydantic).
- The section is intentionally written as **agent instructions**, not user docs —
  keep examples minimal, rule tables scannable, and patterns copy-paste-ready.
- `harness:update --only agents-md` preserves this section verbatim unless
  `--force` is passed.

---

### Step 3.6 — Generate `harness_manifest.json` and `harness_manifest.schema.json`

After scaffolding the artifact stubs, write the manifest and its companion schema
so that downstream tools and agents can validate manifest fragments independently.

Call the generator directly from Python:

```python
from harness_skills.generators.manifest_generator import write_manifest_pair

manifest_path, schema_path = write_manifest_pair(
    directory=".",
    detected_stack=detected_stack,       # DetectedStack model or equivalent dict
    domains=domains_detected,            # list[str] of detected domain names
    artifacts=artifacts_generated,       # list[GeneratedArtifact] written so far
    git_sha=HEAD_HASH,                   # from Step 3.5
    git_branch=GIT_BRANCH,              # git rev-parse --abbrev-ref HEAD
    harness_version=HARNESS_VERSION,    # importlib.metadata.version("harness-skills")
)
```

When the harness CLI is not available (agent-only context), construct the pair
inline:

```python
import json, datetime, shutil, pathlib

manifest = {
    "schema_version": "1.0",
    "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "git_sha": HEAD_HASH,
    "git_branch": GIT_BRANCH,
    "detected_stack": detected_stack_dict,
    "domains": domains_detected,
    "artifacts": [a.model_dump() for a in artifacts_generated],
    "manifest_path": "harness_manifest.json",
    "schema_path": "harness_manifest.schema.json",
}

# Write schema first — fail fast before touching the manifest
schema_src = pathlib.Path(__file__).parent.parent / "harness_skills" / "schemas" / "harness_manifest.schema.json"
shutil.copy2(schema_src, "harness_manifest.schema.json")

with open("harness_manifest.json", "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2)
```

**Rules:**
- The schema file is **always overwritten** with the canonical bundled version —
  it is generated, not user-editable.
- The manifest file is **always overwritten** — it reflects the current generation
  run and is not intended for manual editing.
- The schema is written **before** the manifest; if the schema write fails the
  manifest is not written, keeping the pair in sync.
- Both paths are recorded in `CreateResponse.manifest_path` and
  `CreateResponse.schema_path` for downstream consumption.
- Record both files as `GeneratedArtifact` entries with `artifact_type: "schema"`
  so they appear in the creation summary and are tracked by `harness:detect-stale`.

---

### Step 4 — Emit a creation summary

After the config is written, display a structured summary:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Harness Create — generation complete
  Profile:  <profile>  ·  Stack: <stack | auto-detected>
  Output:   <output path>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Gates generated
  ─────────────────────────────────────────────────────
  regression        enabled   threshold: all tests pass
  coverage          enabled   threshold: 80 %
  lint              enabled   threshold: zero errors
  <standard+>
  architecture      enabled   (standard profile)
  principles        enabled   (standard profile)
  docs_freshness    enabled   (standard profile)
  <advanced+>
  performance       enabled   (advanced profile)
  security          enabled   (advanced profile)
  types             enabled   (advanced profile)
  ─────────────────────────────────────────────────────
  <N> gates  ·  plugins: 0

  Config written to:    <output path>
  Manifest written to:  harness_manifest.json
  Schema written to:    harness_manifest.schema.json

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Next steps
  • Review harness.config.yaml and adjust thresholds.
  • Run /harness:lint to validate architecture & principles.
  • Run /harness:evaluate to run all quality gates.
  • Commit the config: git add harness.config.yaml harness_manifest.json harness_manifest.schema.json
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

In `--dry-run` mode, prefix the header with `[DRY-RUN]` and do not show "Config
written to" — print the YAML gates block instead.

---

### Step 5 — Handle `--then` chaining (if requested)

If the invocation includes one or more `--then` flags, pipe the command through
the `PipelineGroup` CLI which runs each named subcommand in sequence, stopping on
the first non-zero exit code.

```bash
# Single pipeline invocation — CLI handles sequencing internally
harness create --profile standard --then lint --then evaluate
```

The pipeline is equivalent to:

```bash
harness create --profile standard && harness lint && harness evaluate
```

When operating as an agent (not running the CLI directly), invoke each step as a
separate tool call, checking the exit code of each before proceeding.

---

## Options

| Flag | Default | Effect |
|---|---|---|
| `--profile PROFILE` | `starter` | Gate complexity profile: `starter`, `standard`, or `advanced` |
| `--stack STACK` | auto-detect | Stack hint for tailored inline comments: `python`, `node`, `go` |
| `--output PATH` | `harness.config.yaml` | Destination path for the generated config file |
| `--dry-run` | off | Print the generated YAML gates block to stdout; do not write to disk |
| `--no-merge` | off | Overwrite the config from scratch (discards manual edits to surrounding keys) |
| `--then SUBCMD` | — | Chain a subsequent harness subcommand (e.g. `--then lint --then evaluate`) |

---

## Output artifacts

| Artifact | Description |
|---|---|
| `harness.config.yaml` | Generated (or updated) harness configuration with gate defaults |
| `AGENTS.md` | Stub created if absent; contains version identifier and generation timestamp |
| `ARCHITECTURE.md` | Stub created if absent; contains version identifier and generation timestamp |
| `PRINCIPLES.md` | Stub created if absent; contains version identifier and generation timestamp |
| `EVALUATION.md` | Stub created if absent; contains version identifier and generation timestamp |
| `harness_manifest.json` | Machine-readable index of the detected stack, domain boundaries, and all generated artifact paths |
| `harness_manifest.schema.json` | JSON Schema (2020-12) for `harness_manifest.json` — allows downstream tools and agents to validate manifest fragments independently |

Pre-existing stub files (`AGENTS.md`, `ARCHITECTURE.md`, `PRINCIPLES.md`, `EVALUATION.md`) are never
overwritten.  The manifest and schema files are always regenerated.  The skill does **not** auto-commit.

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| First-time harness setup on a new project | **`/harness:create`** ← you are here |
| Refresh existing harness after stack changes | `/harness:update` |
| Validate architecture & principles after editing | `/harness:lint` |
| Run all quality gates before merge | `/harness:evaluate` |
| Show current plan / gate health metrics | `/harness:status` |
| Find relevant files for a plan | `/harness:context` |

---

## Notes

- **Merge-safe by default** — if `harness.config.yaml` already exists, only the
  `gates:` block for the chosen profile is updated; surrounding YAML keys and
  comments are preserved.  Pass `--no-merge` only when a full regeneration is
  required.
- **Never auto-commits** — review the generated config before committing.
- **Idempotent** — running `/harness:create` twice with the same arguments on an
  unchanged codebase produces an identical file on the second run.
- **State service not required** — this skill operates entirely from local
  filesystem inspection; no network calls are made.
- **Pipeline chaining** — combining `--then lint --then evaluate` ensures the
  generated config is immediately validated in a single agent turn.
