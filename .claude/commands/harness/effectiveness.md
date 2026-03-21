# Harness Effectiveness Dashboard

Generate a **harness effectiveness scoring report** that correlates harness artifact
usage (artifact count, coverage %) with PR quality metrics (gate pass rate, review
cycles, time-to-merge) using Pearson correlation and a weighted composite score.

The dashboard ranks every harness from **Elite** (score ≥ 80) down to **Weak** (< 40)
and surfaces cross-dataset correlation insights so engineering teams can see which
harness attributes drive better PR outcomes.

---

## Scoring formula

Each harness receives a composite **effectiveness score** (0–100) from four components:

| Component | Weight | Signal |
|---|---|---|
| `gate_pass_rate` | **40 %** | Fraction of CI gates passing on first run |
| `coverage_pct` | **25 %** | Harness artifact coverage — leading indicator |
| `review_cycles` | **20 %** | Fewer rounds = higher score (inverted) |
| `time_to_merge` | **15 %** | Faster delivery = higher score (inverted) |

Harnesses with no linked PRs receive a coverage-only score penalised to 60 % of face
value, reflecting the absence of real PR evidence.

---

## Usage

```bash
# Render the Rich terminal dashboard (synthetic data, 20 harnesses)
/harness:effectiveness

# Larger dataset
/harness:effectiveness --harnesses 50

# Non-deterministic seed
/harness:effectiveness --seed 0

# Emit raw JSON instead of the Rich UI
/harness:effectiveness --json
```

---

## Instructions

### Step 1 — Run the dashboard

Execute the dashboard CLI:

```bash
python -m harness_dashboard.dashboard \
  ${HARNESSES:+--harnesses $HARNESSES} \
  ${SEED:+--seed $SEED} \
  ${JSON_FLAG} \
  2>&1
```

Where:
- `HARNESSES` defaults to `20`
- `SEED` defaults to `42` (use `0` for non-deterministic)
- `JSON_FLAG` is `--json` when `--json` is passed, empty otherwise

**Fallback** if the module is not importable:

```bash
cd /path/to/repo && python harness_dashboard/dashboard.py \
  --harnesses 20 --seed 42
```

---

### Step 2 — Interpret the output

The dashboard renders four panels:

| Panel | Content |
|---|---|
| **Header strip** | Fleet totals: harness count, PR count, avg score, avg gate-pass %, avg review cycles, avg TTM |
| **Tier breakdown** | Bar chart of Elite / Strong / Moderate / Weak counts |
| **Harness Rankings** | One row per harness sorted by score ↓; includes artifact count, coverage, PR metrics, score bar, tier badge |
| **Correlation Analysis** | 6 Pearson r values (2 artifact attrs × 3 PR metrics) with significance flags and plain-English interpretation |

**Tier thresholds:**

| Tier | Score range | Badge |
|---|---|---|
| ★ Elite    | ≥ 80 | `bold green` |
| ◆ Strong   | 60–79 | `green` |
| ● Moderate | 40–59 | `yellow` |
| ○ Weak     | < 40  | `red` |

---

### Step 3 — Emit structured output

After the terminal dashboard, always emit a fenced JSON block for downstream agents:

```json
{
  "command": "harness effectiveness",
  "generated_at": "<ISO-8601>",
  "harness_count": 20,
  "pr_count": 112,
  "fleet_avg_score": 68.4,
  "fleet_avg_gate_pass_rate": 0.724,
  "fleet_avg_review_cycles": 1.9,
  "fleet_avg_time_to_merge_hours": 38.2,
  "tier_distribution": {
    "elite": 4,
    "strong": 8,
    "moderate": 6,
    "weak": 2
  },
  "top_harness": {
    "harness_id": "hrn-003",
    "artifact_type": "factory",
    "effectiveness_score": 91.2,
    "tier": "Elite"
  },
  "bottom_harness": {
    "harness_id": "hrn-017",
    "artifact_type": "stub",
    "effectiveness_score": 31.5,
    "tier": "Weak"
  },
  "significant_correlations": [
    {
      "artifact_attr": "coverage_pct",
      "pr_metric": "gate_pass_rate",
      "pearson_r": 0.61,
      "direction": "positive",
      "interpretation": "Higher coverage pct strongly improves gate pass rate (r=+0.610, statistically significant)."
    }
  ]
}
```

---

### Step 4 — Highlight actionable insights

After the JSON block, emit a short **Insights** section:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Insights
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Top harness  : <harness_id> (<artifact_type>, score <N>)
    → <key_insight about why it ranks high>

  Weak harnesses (<N> of <total>):
    → Review artifact count and coverage to lift gate pass rates.

  Strongest correlation: <artifact_attr> ↔ <pr_metric> (r=<value>)
    → <actionable recommendation>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Rules:
- If all harnesses are Moderate or above, note that the fleet is healthy.
- If `coverage_pct ↔ gate_pass_rate` has `r > 0.4` and is significant, recommend
  raising coverage thresholds in CI.
- If `artifact_count ↔ review_cycles` has `r < -0.3` and is significant, recommend
  expanding harness artifact breadth for high-churn repos.
- If ≥ 50 % of harnesses are Weak or Moderate, recommend an audit of the lowest-scoring
  harness type and running `/harness:lint` to find configuration gaps.

---

## Options

| Flag | Default | Effect |
|---|---|---|
| `--harnesses N` | `20` | Number of synthetic harnesses to generate |
| `--seed N` | `42` | RNG seed; `0` = non-deterministic |
| `--json` | off | Emit raw `DashboardReport` JSON instead of the Rich UI |

---

## Architecture

```
harness_dashboard/
  models.py          — HarnessRecord, PRRecord, EffectivenessMetrics,
                       CorrelationInsight, DashboardReport, EffectivenessTier
  scorer.py          — compute_scores(harnesses, prs) → DashboardReport
                       _tier(), _pearson(), _compute_correlations(),
                       _fleet_stats()
  dashboard.py       — render_dashboard(report) — Rich terminal UI
                       CLI entry: python -m harness_dashboard.dashboard
  data_generator.py  — generate_dataset(num_harnesses, seed) → Dataset
```

**Data flow:**

```
generate_dataset()
       │
       ▼
 HarnessRecord[]  +  PRRecord[]  (merged only)
       │
       ▼
 compute_scores()          ← scorer.py
   ├─ _harness_metrics()   per-harness weighted score
   ├─ _compute_correlations()  Pearson r (2 attrs × 3 metrics)
   └─ _fleet_stats()        fleet-level aggregates
       │
       ▼
 DashboardReport
       │
       ▼
 render_dashboard()        ← dashboard.py  (Rich UI)
```

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Rank harnesses by PR quality impact | **`/harness:effectiveness`** ← you are here |
| View raw artifact read / command / gate counts | `/harness:telemetry` |
| Identify underutilised artifacts & silent gates | `/harness:telemetry --analyze` |
| Verify architecture & principles compliance | `/harness:lint` |
| Full quality gate (tests, coverage, security) | `/check-code` |
| Detect whether a plan is making progress | `/harness:detect-stale` |

---

## Notes

- **Merged PRs only** — unmerged / abandoned PRs are excluded from all scoring and
  correlation calculations to avoid diluting quality signals.
- **Minimum 4 harnesses required** for Pearson correlations to be statistically
  meaningful; with fewer harnesses all `p_value` fields will be `1.0`.
- **Pure standard-library statistics** — `scorer.py` uses only `math` and `statistics`
  (no numpy/scipy dependency) so the scoring engine runs anywhere Python 3.10+ is available.
- **Synthetic data by default** — the dashboard ships a realistic correlated data
  generator (`data_generator.py`) for demos and CI smoke tests.  To score real data,
  pass actual `HarnessRecord` / `PRRecord` lists to `compute_scores()` directly.
- **Deterministic output** — with the default seed of `42` the fleet avg score and tier
  distribution are stable across runs, making the output safe to snapshot in CI.
