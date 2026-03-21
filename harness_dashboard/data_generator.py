"""
Synthetic Data Generator
=========================
Generates realistic HarnessRecord + PRRecord pairs for demos and unit tests.

The generator bakes in realistic correlations:
  - FACTORY and MOCK artifact types (higher coverage profiles) → faster TTM,
    fewer review cycles, higher gate pass rates.
  - STUB and FIXTURE types → baseline performance.
  - Artifact count correlates loosely with gate pass rate (more artifacts
    → slightly better gates), with ±30 % noise to avoid perfect linearity.
  - ~8 % of PRs are abandoned (merged=False, time_to_merge_hours=0).

Usage
-----
    from harness_dashboard.data_generator import generate_dataset

    dataset = generate_dataset(num_harnesses=20, seed=42)
    # dataset.harnesses  — list[HarnessRecord]
    # dataset.prs        — list[PRRecord]
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .models import ArtifactType, HarnessRecord, PRRecord


# ---------------------------------------------------------------------------
# Dataset container
# ---------------------------------------------------------------------------

@dataclass
class Dataset:
    """Paired harnesses and PRs returned by generate_dataset()."""

    harnesses: list[HarnessRecord]
    prs: list[PRRecord]


# ---------------------------------------------------------------------------
# Artifact-type profiles
# ---------------------------------------------------------------------------

# (base_coverage_pct, gate_pass_bonus, artifact_count_range,
#  review_cycles_mean, ttm_hours_mean)
_PROFILES: dict[ArtifactType, tuple[float, float, tuple[int, int], float, float]] = {
    ArtifactType.FIXTURE:  (72.0, +0.04, (5,  25), 2.2, 44.0),
    ArtifactType.MOCK:     (78.0, +0.07, (8,  40), 1.8, 36.0),
    ArtifactType.STUB:     (64.0, +0.02, (3,  18), 2.6, 52.0),
    ArtifactType.FACTORY:  (84.0, +0.09, (10, 50), 1.4, 30.0),
    ArtifactType.SNAPSHOT: (70.0, +0.05, (4,  22), 2.1, 42.0),
}

_START_DATE = datetime(2025, 9, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_dataset(
    num_harnesses: int = 20,
    prs_per_harness: int = 6,
    seed: int | None = 42,
) -> Dataset:
    """
    Return a ``Dataset`` of synthetic HarnessRecord and PRRecord objects.

    Correlations are intentional but noisy (±30 %) so statistical tests
    produce meaningful — rather than trivially perfect — results.

    Parameters
    ----------
    num_harnesses:
        Number of distinct harnesses to generate.
    prs_per_harness:
        Average PRs per harness (actual count is Gaussian-jittered).
    seed:
        RNG seed for reproducibility; ``None`` = non-deterministic.
    """
    rng = random.Random(seed)
    artifact_types = list(ArtifactType)

    harnesses: list[HarnessRecord] = []
    prs:       list[PRRecord]      = []
    pr_counter = 0

    for i in range(num_harnesses):
        art_type = artifact_types[i % len(artifact_types)]
        base_cov, gate_bonus, count_range, rev_mean, ttm_mean = _PROFILES[art_type]

        # ── Harness record ──────────────────────────────────────────────────
        coverage_pct   = round(max(0.0, min(100.0, rng.gauss(base_cov, 8.0))), 1)
        artifact_count = rng.randint(*count_range)
        harness_id     = f"hrn-{i + 1:03d}"

        harnesses.append(HarnessRecord(
            harness_id=harness_id,
            artifact_type=art_type,
            artifact_count=artifact_count,
            coverage_pct=coverage_pct,
            schema_version="1.0",
            created_at=_START_DATE + timedelta(days=rng.uniform(-180, 0)),
        ))

        # ── PR records for this harness ─────────────────────────────────────
        # artifact_count feeds a small gate-pass bonus (more artifacts → slightly
        # higher quality) with multiplicative noise to keep r modest.
        artifact_bonus = (artifact_count / 50) * 0.05  # up to +0.05 for max count

        n_prs = max(0, round(rng.gauss(prs_per_harness, 2.0)))

        for _ in range(n_prs):
            pr_counter += 1

            noise       = 0.7 + rng.random() * 0.6   # ±30 % noise multiplier
            gate_pass   = round(
                max(0.0, min(1.0,
                    0.58
                    + gate_bonus * noise
                    + artifact_bonus * noise
                    + coverage_pct / 1200
                    + rng.gauss(0, 0.10)
                )),
                3,
            )
            review_cyc  = max(0, round(rng.gauss(rev_mean, 1.1)))
            merged      = rng.random() < 0.92
            ttm_hours   = (
                round(max(0.5, rng.gauss(ttm_mean, ttm_mean * 0.28)), 1)
                if merged else 0.0
            )
            # Guard: merged PRs must have ttm > 0 (enforced by PRRecord validator).
            if merged and ttm_hours <= 0.0:
                ttm_hours = 0.5

            prs.append(PRRecord(
                pr_id=f"PR-{pr_counter:04d}",
                harness_id=harness_id,
                gate_pass_rate=gate_pass,
                review_cycles=review_cyc,
                time_to_merge_hours=ttm_hours,
                merged=merged,
                merged_at=_START_DATE + timedelta(days=rng.uniform(0, 180)),
            ))

    return Dataset(harnesses=harnesses, prs=prs)
