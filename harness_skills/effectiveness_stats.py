"""
Harness Effectiveness — Statistics Engine
==========================================
Pure-Python statistics layer (numpy + scipy) that computes correlation metrics
between harness artifact usage and PR quality outcomes.

All statistical work happens here so that the Claude analyzer receives
pre-computed, JSON-serialisable summaries rather than raw PR objects.

Key exports
-----------
  ArtifactStats           — dataclass holding computed stats for one artifact
  compute_artifact_stats  — compute ArtifactStats for a single ArtifactType
  compute_all_stats       — compute for every ArtifactType in one shot
  compute_correlation_matrix      — pairwise artifact-usage correlation matrix
  compute_artifact_combination_effects  — top PR clusters by artifact combo
  stats_to_json_summary   — serialize all stats to a compact JSON string
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy import stats as sp_stats

from harness_skills.pr_effectiveness import ArtifactType, PRRecord


# ---------------------------------------------------------------------------
# Per-artifact statistics dataclass
# ---------------------------------------------------------------------------


@dataclass
class ArtifactStats:
    """Computed correlation statistics for a single artifact type."""

    artifact_type: str

    # ── Sample sizes ─────────────────────────────────────────────────────────
    n_total:   int
    n_with:    int
    n_without: int
    usage_rate: float          # n_with / n_total

    # ── Metric means (with vs without artifact) ───────────────────────────────
    gate_pass_with:    float
    gate_pass_without: float
    gate_pass_delta:   float   # positive = artifact users have higher pass rate

    review_with:    float
    review_without: float
    review_delta:   float      # negative = artifact users need fewer review rounds

    merge_time_with:    Optional[float]   # hours; None if too few merged PRs
    merge_time_without: Optional[float]
    merge_time_delta:   Optional[float]   # negative = artifact users merge faster

    # ── Point-biserial correlations (binary use ↔ continuous metric) ─────────
    gate_pass_correlation: float
    review_correlation:    float
    merge_time_correlation: Optional[float]

    # ── Two-tailed p-values ───────────────────────────────────────────────────
    gate_pass_pvalue:    float
    review_pvalue:       float
    merge_time_pvalue:   Optional[float]


# ---------------------------------------------------------------------------
# Core computation helpers
# ---------------------------------------------------------------------------


def _safe_pointbiserial(
    binary: np.ndarray,
    continuous: np.ndarray,
) -> tuple[float, float]:
    """Return (r, p) for point-biserial correlation; (0.0, 1.0) on failure."""
    ones = int(binary.sum())
    if ones == 0 or ones == len(binary):
        return 0.0, 1.0
    try:
        r, p = sp_stats.pointbiserialr(binary, continuous)
        return float(r), float(p)
    except Exception:
        return 0.0, 1.0


def compute_artifact_stats(prs: list[PRRecord], artifact_type: ArtifactType) -> ArtifactStats:
    """Compute correlation statistics for *artifact_type* across *prs*."""

    usage      = np.array([1 if artifact_type in pr.artifact_types_used else 0 for pr in prs])
    gate_pass  = np.array([pr.gate_pass_rate for pr in prs])
    review     = np.array([float(pr.review_cycles) for pr in prs])

    # Merge-time arrays contain only merged PRs to avoid None contamination.
    merged_prs      = [pr for pr in prs if pr.time_to_merge_hours is not None]
    merge_times_arr = np.array([pr.time_to_merge_hours for pr in merged_prs])
    usage_merged    = np.array([1 if artifact_type in pr.artifact_types_used else 0 for pr in merged_prs])

    n_total  = len(prs)
    n_with   = int(usage.sum())
    n_without = n_total - n_with

    with_mask    = usage == 1
    without_mask = usage == 0

    # ── Means ─────────────────────────────────────────────────────────────────
    gp_with    = float(gate_pass[with_mask].mean())    if n_with    > 0 else 0.0
    gp_without = float(gate_pass[without_mask].mean()) if n_without > 0 else 0.0

    rv_with    = float(review[with_mask].mean())    if n_with    > 0 else 0.0
    rv_without = float(review[without_mask].mean()) if n_without > 0 else 0.0

    mt_n_with    = int((usage_merged == 1).sum())
    mt_n_without = int((usage_merged == 0).sum())
    mt_with    = float(merge_times_arr[usage_merged == 1].mean()) if mt_n_with    > 0 else None
    mt_without = float(merge_times_arr[usage_merged == 0].mean()) if mt_n_without > 0 else None
    mt_delta   = (mt_with - mt_without) if (mt_with is not None and mt_without is not None) else None

    # ── Correlations ──────────────────────────────────────────────────────────
    gp_r, gp_p = _safe_pointbiserial(usage, gate_pass)
    rv_r, rv_p = _safe_pointbiserial(usage, review)

    mt_r: Optional[float] = None
    mt_p: Optional[float] = None
    if len(merge_times_arr) >= 10:
        mt_r, mt_p = _safe_pointbiserial(usage_merged, merge_times_arr)

    return ArtifactStats(
        artifact_type=artifact_type.value,
        n_total=n_total,
        n_with=n_with,
        n_without=n_without,
        usage_rate=round(n_with / n_total, 4),

        gate_pass_with=round(gp_with, 4),
        gate_pass_without=round(gp_without, 4),
        gate_pass_delta=round(gp_with - gp_without, 4),

        review_with=round(rv_with, 4),
        review_without=round(rv_without, 4),
        review_delta=round(rv_with - rv_without, 4),

        merge_time_with=round(mt_with, 2)    if mt_with    is not None else None,
        merge_time_without=round(mt_without, 2) if mt_without is not None else None,
        merge_time_delta=round(mt_delta, 2)  if mt_delta   is not None else None,

        gate_pass_correlation=round(gp_r, 4),
        review_correlation=round(rv_r, 4),
        merge_time_correlation=round(mt_r, 4) if mt_r is not None else None,

        gate_pass_pvalue=round(gp_p, 4),
        review_pvalue=round(rv_p, 4),
        merge_time_pvalue=round(mt_p, 4) if mt_p is not None else None,
    )


def compute_all_stats(prs: list[PRRecord]) -> dict[str, ArtifactStats]:
    """Compute ArtifactStats for every ArtifactType in one pass."""
    return {art.value: compute_artifact_stats(prs, art) for art in ArtifactType}


# ---------------------------------------------------------------------------
# Pairwise correlation matrix
# ---------------------------------------------------------------------------


def compute_correlation_matrix(prs: list[PRRecord]) -> dict[str, dict[str, float]]:
    """
    Return a symmetric matrix of Pearson correlations between artifact usage
    vectors.  Positive values = artifacts tend to co-occur; negative = mutual
    exclusion (rare with harness artifacts, but possible in selective pipelines).
    """
    artifact_types = list(ArtifactType)
    # Build binary usage matrix (n_prs × n_artifacts)
    usage_matrix = np.column_stack([
        np.array([1 if art in pr.artifact_types_used else 0 for pr in prs])
        for art in artifact_types
    ]).astype(float)

    matrix: dict[str, dict[str, float]] = {}
    for i, a1 in enumerate(artifact_types):
        row: dict[str, float] = {}
        for j, a2 in enumerate(artifact_types):
            if i == j:
                row[a2.value] = 1.0
            else:
                try:
                    r, _ = sp_stats.pearsonr(usage_matrix[:, i], usage_matrix[:, j])
                    row[a2.value] = round(float(r), 3)
                except Exception:
                    row[a2.value] = 0.0
        matrix[a1.value] = row
    return matrix


# ---------------------------------------------------------------------------
# Artifact combination effects
# ---------------------------------------------------------------------------


def compute_artifact_combination_effects(prs: list[PRRecord]) -> list[dict]:
    """
    Cluster PRs by their exact set of artifact types used.
    Return the top 15 clusters (min 5 PRs) ranked by avg gate_pass_rate.

    This reveals *synergy*: which combinations produce the best outcomes.
    """
    clusters: dict[frozenset, dict[str, list]] = {}

    for pr in prs:
        key = frozenset(a.value for a in pr.artifact_types_used)
        if key not in clusters:
            clusters[key] = {"gate_pass": [], "review": [], "merge_time": []}
        clusters[key]["gate_pass"].append(pr.gate_pass_rate)
        clusters[key]["review"].append(float(pr.review_cycles))
        if pr.time_to_merge_hours is not None:
            clusters[key]["merge_time"].append(pr.time_to_merge_hours)

    results: list[dict] = []
    for combo, metrics in clusters.items():
        n = len(metrics["gate_pass"])
        if n < 5:
            continue
        results.append({
            "artifacts":          sorted(combo),
            "n_prs":              n,
            "avg_gate_pass_rate": round(float(np.mean(metrics["gate_pass"])),  3),
            "avg_review_cycles":  round(float(np.mean(metrics["review"])),     2),
            "avg_merge_time_hrs": (
                round(float(np.mean(metrics["merge_time"])), 1)
                if metrics["merge_time"] else None
            ),
        })

    results.sort(key=lambda x: x["avg_gate_pass_rate"], reverse=True)
    return results[:15]


# ---------------------------------------------------------------------------
# Serialisation helpers used by the analyzer
# ---------------------------------------------------------------------------


def stats_to_dict(stats: ArtifactStats) -> dict:
    """Convert an ArtifactStats dataclass to a plain dict."""
    return dataclasses.asdict(stats)


def stats_to_json_summary(all_stats: dict[str, ArtifactStats]) -> str:
    """
    Produce a compact JSON summary of all artifact statistics.
    Used as context for the Claude structured-output call.
    """
    summary: dict[str, dict] = {}
    for art_type, s in all_stats.items():
        summary[art_type] = {
            "n_with":                  s.n_with,
            "usage_rate":              s.usage_rate,
            "gate_pass_delta":         s.gate_pass_delta,
            "gate_pass_correlation":   s.gate_pass_correlation,
            "gate_pass_pvalue":        s.gate_pass_pvalue,
            "gate_pass_significant":   s.gate_pass_pvalue < 0.05,
            "review_delta":            s.review_delta,
            "review_correlation":      s.review_correlation,
            "review_pvalue":           s.review_pvalue,
            "review_significant":      s.review_pvalue < 0.05,
            "merge_time_delta":        s.merge_time_delta,
            "merge_time_correlation":  s.merge_time_correlation,
            "merge_time_pvalue":       s.merge_time_pvalue,
            "merge_time_significant":  (
                s.merge_time_pvalue < 0.05
                if s.merge_time_pvalue is not None else False
            ),
            # Full detail also included for drill-down queries
            "gate_pass_with":          s.gate_pass_with,
            "gate_pass_without":       s.gate_pass_without,
            "review_with":             s.review_with,
            "review_without":          s.review_without,
            "merge_time_with":         s.merge_time_with,
            "merge_time_without":      s.merge_time_without,
        }
    return json.dumps(summary, indent=2)
