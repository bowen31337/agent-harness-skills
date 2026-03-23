# Harness Artifact Audit

Compare **all generated artifacts** against the current codebase state and
report a **per-artifact freshness score** — `current`, `stale`, `outdated`,
or `obsolete` — together with a concrete recommended action for each artifact
that needs attention.

Use this skill whenever you need a definitive answer to: *"Which harness
artifacts are still accurate, and which need to be regenerated?"*

---

## Usage

```bash
# Audit all artifacts with default thresholds (stale>14d, outdated>30d, obsolete>90d)
/harness:audit

# Use a custom staleness window
/harness:audit --stale-days 7 --outdated-days 21 --obsolete-days 60

# Advisory mode — report issues without blocking (downgrade errors to warnings)
/harness:audit --no-fail-on-outdated

# Skip skill command files (.claude/commands/) from the scan
/harness:audit --no-skill-commands

# Emit structured JSON for downstream agent consumption
/harness:audit --json
```

---

## Instructions

### Step 0 — Resolve repository root

Determine the repository root (the directory containing `harness.config.yaml`
or `harness_manifest.json`).  Default to the current working directory:

```bash
ls harness.config.yaml harness_manifest.json 2>/dev/null || echo "__NOT_FOUND__"
```

If neither file exists in the CWD, walk up parent directories until one is
found, or inform the user that this command must be run from the project root.

---

### Step 1 — Run the artifact audit

```bash
uv run python -m harness_skills.gates.artifact_audit \
  --root . \
  --stale-days 14 \
  --outdated-days 30 \
  --obsolete-days 90 \
  --json \
  2>&1
```

> **Fallback** — if `uv` is not available:
>
> ```bash
> python -m harness_skills.gates.artifact_audit \
>   --root . \
>   --stale-days 14 \
>   --outdated-days 30 \
>   --obsolete-days 90 \
>   --json
> ```

Capture stdout (structured JSON + human-readable report) and stderr
(progress/warnings).

**Exit codes:**

| Code | Meaning |
|---|---|
| `0` | All artifacts are `current` or `stale` — gate passed |
| `1` | One or more `outdated` or `obsolete` artifacts found — gate failed |
| `2` | Input error (bad path, invalid threshold values, etc.) |

---

### Step 2 — Parse the JSON output

The gate emits an `AuditResult` JSON object.  Key fields:

| Field | Use |
|---|---|
| `status` | `passed` or `failed` |
| `stats.total_artifacts` | Number of artifacts scanned |
| `stats.current` | Count scored `current` |
| `stats.stale` | Count scored `stale` |
| `stats.outdated` | Count scored `outdated` |
| `stats.obsolete` | Count scored `obsolete` |
| `stats.missing` | Count of missing artifact files |
| `stats.no_timestamp` | Count with no freshness timestamp |
| `artifacts[]` | Full per-artifact details (see table below) |

Per-artifact fields:

| Field | Use |
|---|---|
| `artifact_path` | Path relative to repo root |
| `artifact_type` | Type tag (e.g. `AGENTS.md`, `skill_command`) |
| `score` | `current` \| `stale` \| `outdated` \| `obsolete` \| `missing` \| `no_timestamp` |
| `severity` | `error` (blocks) \| `warning` (advisory) \| `info` (informational) |
| `age_days` | Days since `generated_at` / `last_updated` (null if unavailable) |
| `last_updated` | ISO date string or null |
| `message` | Short human-readable summary |
| `recommended_action` | Concrete next step for this artifact |

---

### Step 3 — Render the human-readable report

Produce the following output based on the parsed response.

**Freshness score icons:**

| Score | Icon | Severity |
|---|---|---|
| `current` | ✅ | info — no action needed |
| `stale` | 🔵 | info — consider refreshing |
| `outdated` | 🟡 | warning — refresh required |
| `obsolete` | 🔴 | error — regenerate immediately |
| `missing` | ❌ | error — artifact absent |
| `no_timestamp` | ⚪ | warning — cannot determine age |

**When all artifacts are current (`status == "passed"`, zero errors):**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Harness Artifact Audit — ✅ PASSED
  <N> artifact(s)  ·  stale>14d  outdated>30d  obsolete>90d
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅  [CURRENT     ]  AGENTS.md
                      last_updated=2026-03-20  age=3d
  ✅  [CURRENT     ]  docs/ARCHITECTURE.md
                      last_updated=2026-03-18  age=5d
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅ current:5  🔵 stale:0  🟡 outdated:0  🔴 obsolete:0  ❌ missing:0  ⚪ no_ts:1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**When issues are found (`status == "failed"`):**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Harness Artifact Audit — ❌ FAILED
  12 artifact(s)  ·  stale>14d  outdated>30d  obsolete>90d
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ❌  [MISSING     ]  docs/EVALUATION.md
                      no timestamp
                      → Artifact not found — run `/harness:create`
  🔴  [OBSOLETE    ]  docs/ARCHITECTURE.md
                      last_updated=2025-09-01  age=203d
                      → Regenerate immediately — run `/harness:update` or `/harness:create`
  🟡  [OUTDATED    ]  docs/PRINCIPLES.md
                      last_updated=2026-01-10  age=72d
                      → Refresh required — run `/harness:update`
  🔵  [STALE       ]  .claude/commands/harness/lint.md
                      last_updated=2026-03-01  age=22d
                      → Consider refreshing — run `/harness:update`
  ✅  [CURRENT     ]  AGENTS.md
                      last_updated=2026-03-20  age=3d
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅ current:8  🔵 stale:1  🟡 outdated:1  🔴 obsolete:1  ❌ missing:1  ⚪ no_ts:0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### Step 4 — Emit structured data (agent-readable)

After the human-readable section, always emit the raw `AuditResult` JSON in
a fenced block so downstream agents can act without re-running the gate:

```json
{
  "command": "harness artifact-audit",
  "status": "failed",
  "stats": {
    "total_artifacts": 12,
    "current": 8,
    "stale": 1,
    "outdated": 1,
    "obsolete": 1,
    "missing": 1,
    "no_timestamp": 0
  },
  "artifacts": [
    {
      "artifact_path": "docs/EVALUATION.md",
      "artifact_type": "docs/EVALUATION.md",
      "score": "missing",
      "severity": "error",
      "age_days": null,
      "last_updated": null,
      "message": "Artifact not found: 'docs/EVALUATION.md'",
      "recommended_action": "Artifact not found at 'docs/EVALUATION.md'. Run `/harness:create` to generate it."
    },
    {
      "artifact_path": "docs/ARCHITECTURE.md",
      "artifact_type": "docs/ARCHITECTURE.md",
      "score": "obsolete",
      "severity": "error",
      "age_days": 203,
      "last_updated": "2025-09-01",
      "message": "'docs/ARCHITECTURE.md' is OBSOLETE: last_updated=2025-09-01, age=203 day(s)",
      "recommended_action": "Regenerate immediately — run `/harness:update` or `/harness:create`."
    }
  ]
}
```

Consumers should:
1. Check `status` — if `"passed"`, no blocking action is needed.
2. Filter `artifacts` where `severity == "error"` for urgent items.
3. Sort by `age_days` descending to prioritise the most out-of-date items.
4. Use `recommended_action` directly as the suggested next step.

---

### Step 5 — Recommend recovery actions

After presenting the report, suggest concrete next steps based on the findings:

| Finding | Recommended action |
|---|---|
| Any `obsolete` artifacts | Run `/harness:update` immediately to regenerate all stale docs |
| Any `missing` artifacts | Run `/harness:create` to generate the missing file(s) |
| Any `outdated` artifacts | Schedule a `/harness:update` run; treat as a P2 |
| Only `stale` artifacts | Plan a `/harness:update` before the next release |
| All `current` | No action needed — artifacts are fresh |
| Any `no_timestamp` | Add `generated_at:` metadata via `/harness:update` |

If three or more artifacts are `outdated` or worse, recommend running a full
`/harness:update` rather than updating individual files.

---

## Options

| Flag | Default | Effect |
|---|---|---|
| `--root PATH` | `.` | Repository root to scan |
| `--stale-days N` | `14` | Days above which an artifact is scored `stale` |
| `--outdated-days N` | `30` | Days above which an artifact is scored `outdated` |
| `--obsolete-days N` | `90` | Days above which an artifact is scored `obsolete` |
| `--manifest FILE` | `harness_manifest.json` | Path to the harness manifest (relative to `--root`) |
| `--no-skill-commands` | off | Skip scanning `.claude/commands/` for skill files |
| `--fail-on-outdated` / `--no-fail-on-outdated` | on | Treat `outdated`/`obsolete` as blocking errors; `--no-*` downgrades to warnings |
| `--quiet` | off | Suppress human-readable output |
| `--json` | off | Emit structured `AuditResult` JSON to stdout |

---

## Freshness score reference

| Score | Condition | Severity | Default action |
|---|---|---|---|
| `current` | age ≤ stale_days | info | None |
| `stale` | stale_days < age ≤ outdated_days | info | Advisory — refresh when convenient |
| `outdated` | outdated_days < age ≤ obsolete_days | warning → error* | Refresh required |
| `obsolete` | age > obsolete_days | error | Regenerate immediately |
| `missing` | File not found on disk | error | Run `/harness:create` |
| `no_timestamp` | No `generated_at` field | warning | Add timestamp via `/harness:update` |

\* `outdated` is `warning` when `--no-fail-on-outdated` is set.

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Audit all generated artifacts for freshness | **`/harness:audit`** ← you are here |
| Check only documentation files (AGENTS.md, etc.) | `/harness:docs-freshness` |
| Detect stale execution plan tasks | `/harness:detect-stale` |
| Refresh all stale artifacts at once | `/harness:update` |
| Regenerate missing artifacts from scratch | `/harness:create` |
| Full quality gate before merge | `/harness:evaluate` |

---

## Notes

- **Artifact discovery order**: `harness_manifest.json` → well-known names →
  `.claude/commands/**/*.md` → `extra_artifacts` config.  Each artifact is
  de-duplicated; the first seen type tag wins.
- **Timestamp detection**: The gate recognises `generated_at:`, `last_updated:`,
  and `updated_at:` fields in any format (YAML front-matter, HTML comments,
  Markdown blockquotes).  Date must be `YYYY-MM-DD`.
- **Skill command files** typically carry no timestamps — they will be scored
  `no_timestamp` (warning, never error).  Use `--no-skill-commands` to
  exclude them if this creates noise.
- **`fail_on_outdated: false`** in `harness.config.yaml` downgrades all
  `outdated`/`obsolete`/`missing` violations to *warnings* so CI stays green
  while the team catches up.
- This skill is **read-only** — it never modifies any artifact or config file.
