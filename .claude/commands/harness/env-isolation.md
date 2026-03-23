# Harness Env Isolation

Generate environment isolation configuration artefacts for a specific agent
worktree — a `.env` file, a docker-compose service override, or a bash export
script — so that each worktree gets its own port, database schema, SQLite file,
or container without starting any process.

Use this skill when preparing an isolated environment for an agent worktree
before booting it.  For booting the instance once the env is configured, use
`/harness:boot` (or `boot_instance` from `harness_skills.boot`).

---

## Usage

```bash
# Minimal — .env file on port 8001 with no DB isolation
/harness:env-isolation --worktree-id fb563322 --port 8001

# PostgreSQL schema isolation
/harness:env-isolation --worktree-id fb563322 --port 8001 --db schema

# SQLite file isolation
/harness:env-isolation --worktree-id fb563322 --port 8001 --db file

# Container isolation (docker-compose format)
/harness:env-isolation --worktree-id fb563322 --port 8001 --db container --format docker-compose

# Shell export script
/harness:env-isolation --worktree-id fb563322 --port 8001 --format shell

# Auto-assign a port (avoids 8000, 8001)
/harness:env-isolation --worktree-id fb563322 --auto-port --taken 8000,8001

# Write to a specific file
/harness:env-isolation --worktree-id fb563322 --port 8001 --output .env.fb563322

# Dry-run — print to stdout without writing
/harness:env-isolation --worktree-id fb563322 --port 8001 --dry-run
```

---

## Instructions

### Step 1 — Parse arguments

Extract the following from the user's invocation:

| Argument | Default | Description |
|---|---|---|
| `--worktree-id ID` | — | **Required.** Worktree identifier (e.g. task-UUID prefix or branch slug). |
| `--port PORT` | — | TCP port for the instance.  Required unless `--auto-port` is set. |
| `--auto-port` | off | Auto-assign a collision-free port from `[--base-port, --base-port + 200)`. |
| `--base-port N` | `8000` | Base port for auto-assignment. |
| `--taken PORTS` | — | Comma-separated list of ports already in use (for `--auto-port`). |
| `--db STRATEGY` | `none` | Database isolation strategy: `none`, `schema`, `file`, `container`. |
| `--schema NAME` | auto | PostgreSQL schema name (auto-derived from worktree-id when omitted). |
| `--db-file PATH` | auto | SQLite file path (auto-derived when omitted). |
| `--format FMT` | `dotenv` | Output format: `dotenv`, `docker-compose`, `shell`. |
| `--output PATH` | auto | File to write.  Auto-derived from format and worktree-id when omitted. |
| `--dry-run` | off | Print to stdout; do not write to disk. |
| `--extra KEY=VAL` | — | Additional env-var pair (may be repeated). |

Validate required arguments and report clear errors for invalid combinations
(e.g. `--port` with `--auto-port`).

---

### Step 2 — Resolve port

**If `--auto-port` is set:**

```python
from harness_skills.env_isolation import assign_port

taken = [int(p) for p in taken_str.split(",") if p.strip()] if taken_str else []
port = assign_port(worktree_id=WORKTREE_ID, taken=taken, base=BASE_PORT)
print(f"[harness:env-isolation] Auto-assigned port: {port}")
```

**If `--port` is set:**

Use the supplied value directly.

---

### Step 3 — Build the `EnvIsolationSpec`

```python
from harness_skills.env_isolation import EnvIsolationSpec, DbIsolation

DB_STRATEGY_MAP = {
    "none":      DbIsolation.NONE,
    "schema":    DbIsolation.SCHEMA,
    "file":      DbIsolation.FILE,
    "container": DbIsolation.CONTAINER,
}

extra_vars = {}
for pair in extra_pairs:          # e.g. ["LOG_LEVEL=debug", "PAYMENTS=false"]
    key, _, val = pair.partition("=")
    extra_vars[key.strip()] = val.strip()

spec = EnvIsolationSpec(
    worktree_id=WORKTREE_ID,
    port=port,
    db_isolation=DB_STRATEGY_MAP.get(DB_STRATEGY, DbIsolation.NONE),
    db_schema=SCHEMA or "",       # empty → auto-derived
    db_file=DB_FILE or "",        # empty → auto-derived
    extra_vars=extra_vars,
)
```

---

### Step 4 — Generate the config

```python
from harness_skills.env_isolation import OutputFormat, generate_env_config

FORMAT_MAP = {
    "dotenv":         OutputFormat.DOTENV,
    "docker-compose": OutputFormat.DOCKER_COMPOSE,
    "shell":          OutputFormat.SHELL,
}

content = generate_env_config(spec, FORMAT_MAP[FORMAT])
```

---

### Step 5 — Write or print

**Determine the output path when `--output` is not supplied:**

| Format | Default output path |
|---|---|
| `dotenv` | `.env.<worktree_id>` |
| `docker-compose` | `docker-compose.<worktree_id>.yml` |
| `shell` | `.harness_env_<worktree_id>.sh` |

**Dry-run:**

```
══════════════════════════════════════════════════════════
  [DRY-RUN] harness:env-isolation
  Worktree: <worktree_id>   Port: <port>   DB: <strategy>
  Format:   <format>
══════════════════════════════════════════════════════════
<generated config content>
══════════════════════════════════════════════════════════
```

**Write to disk:**

```python
with open(output_path, "w") as f:
    f.write(content)
```

---

### Step 6 — Emit a summary

```
══════════════════════════════════════════════════════════
  harness:env-isolation — complete
  Worktree:  <worktree_id>
  Port:      <port>  (<auto-assigned | explicit>)
  DB:        <strategy>  (<schema-name | db-file | container-name | n/a>)
  Format:    <format>
  Output:    <output_path>
══════════════════════════════════════════════════════════
  Next steps
  • Review <output_path> and adjust values if needed.
  • Source the env before starting the app:
      dotenv:  env $(grep -v '^#' <output_path> | xargs) <start-command>
      shell:   source <output_path> && <start-command>
      compose: docker compose -f docker-compose.yml -f <output_path> up
  • Boot the instance:  /harness:boot  (or boot_instance() in Python)
══════════════════════════════════════════════════════════
```

---

## Options

| Flag | Default | Effect |
|---|---|---|
| `--worktree-id ID` | — | Worktree identifier |
| `--port PORT` | — | Explicit port |
| `--auto-port` | off | Auto-assign a collision-free port |
| `--base-port N` | `8000` | Base port for auto-assignment |
| `--taken PORTS` | `""` | Comma-separated already-used ports |
| `--db STRATEGY` | `none` | Database isolation: `none`, `schema`, `file`, `container` |
| `--schema NAME` | auto | PostgreSQL schema name |
| `--db-file PATH` | auto | SQLite file path |
| `--format FMT` | `dotenv` | Output format: `dotenv`, `docker-compose`, `shell` |
| `--output PATH` | auto | Destination file |
| `--dry-run` | off | Print to stdout; do not write |
| `--extra KEY=VAL` | — | Extra env-var (repeatable) |

---

## Output artefacts

| Format | Default path | Contents |
|---|---|---|
| `dotenv` | `.env.<worktree_id>` | `PORT`, DB vars, extra vars |
| `docker-compose` | `docker-compose.<worktree_id>.yml` | Service entry with port mapping and DB environment |
| `shell` | `.harness_env_<worktree_id>.sh` | `export` statements, sourceable in bash |

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Generate env config before booting | **`/harness:env-isolation`** ← you are here |
| Boot the instance after env is ready | `/harness:boot` (or `boot_instance()`) |
| First-time harness setup | `/harness:create` |
| Run all quality gates before merge | `/harness:evaluate` |

---

## Key Files

| Path | Purpose |
|---|---|
| `harness_skills/env_isolation.py` | All public API — `generate_env_config`, `assign_port`, `schema_name`, `container_name`, data models. |
| `skills/env-isolation/SKILL.md` | Skill definition (usage examples, reference tables). |
