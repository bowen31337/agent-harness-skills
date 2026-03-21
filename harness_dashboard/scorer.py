"""
Harness Effectiveness Scoring Engine
=====================================
Translates raw HarnessRecord + PRRecord lists into a fully computed
DashboardReport, including per-harness EffectivenessMetrics and
cross-dataset CorrelationInsights.

Scoring formula
---------------
When a harness has associated PRs, the effectiveness score (0–100) is a
weighted combination of four components:

  gate_pass_rate  (40 %) — fraction of CI gates that passed first-run
  coverage_pct    (25 %) — harness artifact coverage (leading indicator)
  review_cycles   (20 %) — inverted: fewer rounds = higher score
  time_to_merge   (15 %) — inverted: faster delivery = higher score

Harnesses without any linked PRs receive a coverage-only score penalised
to 60 % of face value, reflecting the absence of real PR evidence.

CorrelationInsights are computed via Pearson r between each artifact
attribute (artifact_count, coverage_pct) and each PR quality metric
(gate_pass_rate, review_cycles, time_to_merge_hours), using per-harness
averages as the unit of observation.

Statistics
----------
Pure standard-library implementation (no numpy/scipy required):
  - Pearson r via the definitional sum formula.
  - Two-tailed p-value via the Fisher z-transform normal approximation
    (z = arctanh(r) * sqrt(n−3), valid for n > 3).

Public API
----------
    compute_scores(harnesses, prs) -> DashboardReport
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Sequence

from .models import (
    CorrelationInsight,
    DashboardReport,
    EffectivenessMetrics,
    EffectivenessTier,
    HarnessRecord,
    PRRecord,
)

# ---------------------------------------------------------------------------
# Scoring weights  (must sum to 1.0)
# ---------------------------------------------------------------------------

_W_GATE_PASS = 0.40   # gate_pass_rate is the primary signal
_W_COVERAGE  = 0.25   # coverage is a leading indicator
_W_REVIEW    = 0.20   # review cycles → friction
_W_TTM       = 0.15   # time-to-merge → delivery speed

# Harnesses with no PR evidence receive this fraction of their coverage score.
_NO_PR_COVERAGE_WEIGHT = 0.60

# Normalisation ceilings (values at or above these map to 0 quality points).
_MAX_REVIEW_CYCLES = 6.0    # ≥ 6 rounds → 0 pts
_MAX_TTM_HOURS     = 168.0  # 1 calendar week → 0 pts

# Pearson p-value threshold for "statistically significant".
_SIG_ALPHA = 0.05


# ---------------------------------------------------------------------------
# Tier classification
# ---------------------------------------------------------------------------

def _tier(score: float) -> EffectivenessTier:
    if score >= 80:
        return EffectivenessTier.ELITE
    if score >= 60:
        return EffectivenessTier.STRONG
    if score >= 40:
        return EffectivenessTier.MODERATE
    return EffectivenessTier.WEAK


# ---------------------------------------------------------------------------
# Pure-Python Pearson r + p-value
# ---------------------------------------------------------------------------

def _pearson(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """
    Compute Pearson r and a two-tailed p-value for paired samples *xs* / *ys*.

    Returns (0.0, 1.0) when the correlation is undefined (constant vectors,
    fewer than 4 pairs, or any arithmetic failure).

    p-value method: Fisher z-transform normal approximation.
      z = arctanh(r) * sqrt(n − 3)  →  z ~ N(0, 1) under H₀: ρ = 0
      p = erfc(|z| / sqrt(2))        (two-tailed)

    Valid for n > 3; gives a conservative estimate that degrades gracefully
    for small n.
    """
    n = len(xs)
    if n < 4 or len(ys) != n:
        return 0.0, 1.0

    mx = statistics.mean(xs)
    my = statistics.mean(ys)

    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx  = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy  = math.sqrt(sum((y - my) ** 2 for y in ys))

    if sx == 0.0 or sy == 0.0:
        return 0.0, 1.0

    r = num / (sx * sy)
    # Clamp floating-point drift.
    r = max(-1.0, min(1.0, r))

    # p-value via Fisher z-transform.
    try:
        z = math.atanh(r) * math.sqrt(n - 3)
        p = math.erfc(abs(z) / math.sqrt(2))
    except (ValueError, ZeroDivisionError):
        p = 1.0

    return round(r, 6), round(max(0.0, min(1.0, p)), 6)


# ---------------------------------------------------------------------------
# Per-harness metric computation
# ---------------------------------------------------------------------------

def _pr_averages(prs: list[PRRecord]) -> tuple[float, float, float]:
    """Return (avg_gate_pass, avg_review_cycles, avg_ttm_hours) for *prs*."""
    n = len(prs)
    if n == 0:
        return 0.0, 0.0, 0.0

    avg_gate = sum(pr.gate_pass_rate for pr in prs) / n
    avg_rev  = sum(pr.review_cycles  for pr in prs) / n

    merged  = [pr for pr in prs if pr.merged]
    avg_ttm = (
        sum(pr.time_to_merge_hours for pr in merged) / len(merged)
        if merged else 0.0
    )
    return avg_gate, avg_rev, avg_ttm


def _effectiveness_score(
    coverage_pct: float,
    avg_gate: float,
    avg_rev: float,
    avg_ttm: float,
    has_prs: bool,
) -> float:
    """
    Composite effectiveness score in [0, 100].

    When *has_prs* is False only coverage contributes, penalised by
    ``_NO_PR_COVERAGE_WEIGHT`` to reflect the absence of PR evidence.
    """
    cov_component = coverage_pct  # already 0–100

    if not has_prs:
        return round(cov_component * _NO_PR_COVERAGE_WEIGHT, 2)

    gate_component   = avg_gate * 100
    review_component = max(0.0, (1.0 - avg_rev / _MAX_REVIEW_CYCLES) * 100)
    ttm_component    = max(0.0, (1.0 - avg_ttm / _MAX_TTM_HOURS)     * 100)

    raw = (
        _W_GATE_PASS * gate_component
        + _W_COVERAGE  * cov_component
        + _W_REVIEW    * review_component
        + _W_TTM       * ttm_component
    )
    return round(min(100.0, max(0.0, raw)), 2)


def _harness_metrics(
    harness: HarnessRecord,
    prs: list[PRRecord],
) -> EffectivenessMetrics:
    avg_gate, avg_rev, avg_ttm = _pr_averages(prs)
    has_prs = len(prs) > 0

    score = _effectiveness_score(
        harness.coverage_pct, avg_gate, avg_rev, avg_ttm, has_prs
    )
    tier = _tier(score)

    return EffectivenessMetrics(
        harness_id=harness.harness_id,
        artifact_type=harness.artifact_type,
        artifact_count=harness.artifact_count,
        coverage_pct=harness.coverage_pct,
        pr_count=len(prs),
        avg_gate_pass_rate=round(avg_gate, 4),
        avg_review_cycles=round(avg_rev, 4),
        avg_time_to_merge_hours=round(avg_ttm, 2),
        effectiveness_score=score,
        tier=tier,
    )


# ---------------------------------------------------------------------------
# Correlation insights
# ---------------------------------------------------------------------------

def _direction(r: float, pr_metric: str) -> str:
    """
    Quality-oriented direction label.

    For review_cycles and time_to_merge_hours a *negative* r means the
    attribute is associated with *better* outcomes — labelled "positive".
    """
    if abs(r) < 0.05:
        return "neutral"
    lower_is_better = {"review_cycles", "time_to_merge_hours"}
    if pr_metric in lower_is_better:
        return "positive" if r < 0 else "negative"
    return "positive" if r > 0 else "negative"


def _interpretation(
    attr: str,
    metric: str,
    r: float,
    sig: bool,
    direction: str,
) -> str:
    attr_lbl   = attr.replace("_", " ")
    metric_lbl = metric.replace("_", " ")
    sig_str    = "statistically significant" if sig else "not statistically significant"
    strength   = (
        "strongly" if abs(r) >= 0.4
        else "moderately" if abs(r) >= 0.2
        else "weakly"
    )
    if direction == "neutral":
        return (
            f"No meaningful relationship between {attr_lbl} and "
            f"{metric_lbl} ({sig_str})."
        )
    impact = "improves" if direction == "positive" else "harms"
    return (
        f"Higher {attr_lbl} {strength} {impact} {metric_lbl} "
        f"(r={r:+.3f}, {sig_str})."
    )


def _compute_correlations(
    metrics: list[EffectivenessMetrics],
) -> list[CorrelationInsight]:
    """
    Compute Pearson r between each artifact attribute and each PR metric.

    Unit of observation: per-harness average.  Only harnesses with ≥ 1 PR
    are included so PR-metric vectors are well-defined.
    """
    pr_rows = [m for m in metrics if m.pr_count > 0]
    if not pr_rows:
        return []

    ac_vec  = [float(m.artifact_count)         for m in pr_rows]
    cov_vec = [m.coverage_pct                   for m in pr_rows]
    gp_vec  = [m.avg_gate_pass_rate             for m in pr_rows]
    rv_vec  = [float(m.avg_review_cycles)       for m in pr_rows]
    ttm_vec = [m.avg_time_to_merge_hours        for m in pr_rows]

    attr_vecs: dict[str, list[float]] = {
        "artifact_count": ac_vec,
        "coverage_pct":   cov_vec,
    }
    metric_vecs: dict[str, list[float]] = {
        "gate_pass_rate":      gp_vec,
        "review_cycles":       rv_vec,
        "time_to_merge_hours": ttm_vec,
    }

    insights: list[CorrelationInsight] = []
    for attr_name, attr_vec in attr_vecs.items():
        for metric_name, metric_vec in metric_vecs.items():
            r, p   = _pearson(attr_vec, metric_vec)
            sig    = p < _SIG_ALPHA
            dir_   = _direction(r, metric_name)
            interp = _interpretation(attr_name, metric_name, r, sig, dir_)

            insights.append(CorrelationInsight(
                artifact_attr=attr_name,   # type: ignore[arg-type]
                pr_metric=metric_name,     # type: ignore[arg-type]
                pearson_r=round(r, 4),
                p_value=round(p, 4),
                significant=sig,
                direction=dir_,
                interpretation=interp,
            ))

    return insights


# ---------------------------------------------------------------------------
# Fleet-level aggregates
# ---------------------------------------------------------------------------

def _fleet_stats(metrics: list[EffectivenessMetrics]) -> dict:
    n = len(metrics)
    if n == 0:
        return dict(
            fleet_avg_score=0.0,
            fleet_avg_gate_pass_rate=0.0,
            fleet_avg_review_cycles=0.0,
            fleet_avg_time_to_merge_hours=0.0,
            elite_count=0,
            strong_count=0,
            moderate_count=0,
            weak_count=0,
        )

    pr_rows = [m for m in metrics if m.pr_count > 0]
    pr_n    = len(pr_rows)

    return dict(
        fleet_avg_score=round(
            sum(m.effectiveness_score for m in metrics) / n, 2
        ),
        fleet_avg_gate_pass_rate=(
            round(sum(m.avg_gate_pass_rate for m in pr_rows) / pr_n, 4)
            if pr_n else 0.0
        ),
        fleet_avg_review_cycles=(
            round(sum(m.avg_review_cycles for m in pr_rows) / pr_n, 2)
            if pr_n else 0.0
        ),
        fleet_avg_time_to_merge_hours=(
            round(sum(m.avg_time_to_merge_hours for m in pr_rows) / pr_n, 2)
            if pr_n else 0.0
        ),
        elite_count=sum(
            1 for m in metrics if m.tier == EffectivenessTier.ELITE
        ),
        strong_count=sum(
            1 for m in metrics if m.tier == EffectivenessTier.STRONG
        ),
        moderate_count=sum(
            1 for m in metrics if m.tier == EffectivenessTier.MODERATE
        ),
        weak_count=sum(
            1 for m in metrics if m.tier == EffectivenessTier.WEAK
        ),
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def compute_scores(
    harnesses: Sequence[HarnessRecord],
    prs: Sequence[PRRecord],
) -> DashboardReport:
    """
    Correlate harness artifact usage with PR quality metrics and return a
    fully populated DashboardReport.

    Parameters
    ----------
    harnesses:
        One record per harness describing its artifact footprint
        (artifact type, count, coverage percentage).
    prs:
        Pull-request records, each linked to a harness via ``harness_id``.
        Unmatched ``harness_id`` values are silently ignored.

    Returns
    -------
    DashboardReport
        Metrics sorted by ``effectiveness_score`` descending.  Includes
        per-harness ``EffectivenessMetrics``, cross-dataset
        ``CorrelationInsights``, and fleet-level aggregate statistics.
    """
    # Only merged PRs carry meaningful quality signals (gate pass rate,
    # review cycles, time-to-merge).  Unmerged / abandoned PRs are excluded
    # so they don't dilute the effectiveness scores.
    merged_prs = [pr for pr in prs if pr.merged]

    # Index merged PRs by harness_id for O(1) lookup.
    pr_index: dict[str, list[PRRecord]] = defaultdict(list)
    for pr in merged_prs:
        pr_index[pr.harness_id].append(pr)

    # Per-harness metrics.
    all_metrics: list[EffectivenessMetrics] = [
        _harness_metrics(h, pr_index[h.harness_id])
        for h in harnesses
    ]

    # Sort descending by score so the dashboard renders rank directly.
    all_metrics.sort(key=lambda m: m.effectiveness_score, reverse=True)

    correlations = _compute_correlations(all_metrics)
    fleet        = _fleet_stats(all_metrics)

    return DashboardReport(
        harness_count=len(harnesses),
        pr_count=len(merged_prs),
        metrics=all_metrics,
        correlations=correlations,
        **fleet,
    )
