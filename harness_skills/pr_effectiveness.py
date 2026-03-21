"""
PR Effectiveness Models & Sample Data
======================================
Data models for PR records, harness artifacts, and the structured effectiveness
report that Claude generates.  Also includes a realistic sample-data generator
for demonstration and testing.

Data model hierarchy
--------------------
  HarnessArtifact        — one CI artifact on a PR (test run, lint, scan…)
  PRRecord               — one pull request with its artifacts + quality metrics
  ArtifactEffectivenessScore — Claude's effectiveness judgment for one artifact type
  HarnessEffectivenessReport — full dashboard report (Claude's structured output)
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Artifact taxonomy
# ---------------------------------------------------------------------------


class ArtifactType(str, Enum):
    BUILD              = "build"
    LINT               = "lint"
    UNIT_TESTS         = "unit_tests"
    TYPE_CHECK         = "type_check"
    COVERAGE_REPORT    = "coverage_report"
    INTEGRATION_TESTS  = "integration_tests"
    SECURITY_SCAN      = "security_scan"
    E2E_TESTS          = "e2e_tests"
    PERF_BENCHMARK     = "perf_benchmark"
    CONTRACT_TESTS     = "contract_tests"
    MUTATION_TESTS     = "mutation_tests"


# ---------------------------------------------------------------------------
# Core domain models
# ---------------------------------------------------------------------------


class HarnessArtifact(BaseModel):
    """A single CI/CD artifact produced on a pull request."""

    artifact_type: ArtifactType
    passed: bool
    execution_time_seconds: float
    coverage_pct: Optional[float] = None   # populated only for COVERAGE_REPORT
    issues_found: int = 0


class PRRecord(BaseModel):
    """A pull request together with its harness artifacts and quality metrics."""

    pr_id: str
    repo: str
    author: str
    created_at: datetime
    merged_at: Optional[datetime] = None
    artifacts: list[HarnessArtifact] = Field(default_factory=list)

    # ── Quality metrics ──────────────────────────────────────────────────────
    # gate_pass_rate : fraction of CI gates that passed on the *first* run (0–1)
    # review_cycles  : number of "Request Changes" rounds before approval
    # time_to_merge  : wall-clock hours from open to merge (None if abandoned)
    gate_pass_rate: float
    review_cycles: int
    time_to_merge_hours: Optional[float] = None

    merged: bool = False
    post_merge_incidents: int = 0

    # ── Derived helpers ──────────────────────────────────────────────────────

    @property
    def artifact_types_used(self) -> set[ArtifactType]:
        return {a.artifact_type for a in self.artifacts}

    @property
    def artifact_count(self) -> int:
        return len(self.artifacts)


# ---------------------------------------------------------------------------
# Structured output models (Claude writes these)
# ---------------------------------------------------------------------------


class ArtifactEffectivenessScore(BaseModel):
    """Effectiveness judgment for a single artifact type."""

    artifact_type: str
    effectiveness_score: float = Field(
        ge=0, le=100,
        description="Composite effectiveness score 0–100.",
    )
    gate_pass_impact: float = Field(
        description="Δ gate_pass_rate (positive = artifact users have higher pass rate).",
    )
    review_cycle_impact: float = Field(
        description="Δ review_cycles (negative = artifact users need fewer review rounds).",
    )
    merge_time_impact: float = Field(
        description="Δ time_to_merge_hours (negative = artifact users merge faster).",
    )
    usage_rate: float = Field(
        ge=0, le=1,
        description="Fraction of PRs in the dataset that include this artifact.",
    )
    confidence: float = Field(
        ge=0, le=1,
        description="Statistical confidence 0–1 (penalised when n_with < 20).",
    )
    priority: str = Field(
        description="Investment priority: critical | high | medium | low.",
    )
    key_insight: str = Field(
        description="One concise sentence describing the artifact's impact pattern.",
    )
    recommendation: str = Field(
        description="Specific, actionable recommendation for this artifact.",
    )


class HarnessEffectivenessReport(BaseModel):
    """Full harness effectiveness dashboard report."""

    analysis_timestamp: str
    total_prs_analyzed: int
    date_range: str

    overall_harness_health_score: float = Field(
        ge=0, le=100,
        description="Weighted composite of coverage and effectiveness.",
    )
    coverage_score: float = Field(
        ge=0, le=100,
        description="How broadly artifacts are adopted across PRs.",
    )
    effectiveness_score: float = Field(
        ge=0, le=100,
        description="How impactful the adopted artifacts actually are.",
    )

    artifact_scores: list[ArtifactEffectivenessScore] = Field(
        description="One entry per artifact type, ordered by effectiveness_score descending.",
    )
    critical_gaps: list[str] = Field(
        description="Missing or underused artifacts with high potential impact.",
    )
    top_recommendations: list[str] = Field(
        description="Top 3–5 prioritised actions, most important first.",
    )
    executive_summary: str = Field(
        description="2–3 sentence executive summary suitable for engineering leadership.",
    )
    methodology_note: str = Field(
        description="One sentence describing the statistical methodology used.",
    )


# ---------------------------------------------------------------------------
# Sample data generator
# ---------------------------------------------------------------------------

# Profiles: (base_adoption_rate, gate_pass_effect, review_cycle_effect, merge_time_effect_hours)
# Effects represent the *expected delta* observed on PRs that USE the artifact vs those that don't.
# Noise is added in the generator so correlations are real but not perfect.
_ARTIFACT_PROFILES: dict[ArtifactType, tuple[float, float, float, float]] = {
    ArtifactType.BUILD:             (0.93, +0.18, -0.10,  -2.0),
    ArtifactType.LINT:              (0.88, +0.10, -0.40,  -1.5),
    ArtifactType.UNIT_TESTS:        (0.81, +0.20, -0.50,  -4.0),
    ArtifactType.TYPE_CHECK:        (0.67, +0.08, -0.70,  -2.5),
    ArtifactType.COVERAGE_REPORT:   (0.71, +0.06, -0.30,  -1.0),
    ArtifactType.INTEGRATION_TESTS: (0.55, +0.15, -0.40,  -6.0),
    ArtifactType.SECURITY_SCAN:     (0.42, +0.22, -0.20,  -3.0),
    ArtifactType.E2E_TESTS:         (0.26, +0.25, -0.80, -10.0),
    ArtifactType.PERF_BENCHMARK:    (0.21, +0.05, -0.10,  -1.5),
    ArtifactType.CONTRACT_TESTS:    (0.17, +0.18, -0.60,  -5.0),
    ArtifactType.MUTATION_TESTS:    (0.09, +0.12, -0.30,  -2.0),
}

_REPOS    = ["api-gateway", "auth-service", "payment-service", "frontend", "data-pipeline"]
_AUTHORS  = [f"dev-{i:02d}" for i in range(1, 16)]


def generate_sample_prs(n: int = 250, seed: int = 42) -> list[PRRecord]:
    """
    Generate *n* realistic PR records with correlated harness artifact usage.

    Patterns baked in:
    - High-adoption artifacts (build, lint) have diffuse correlation because
      they run on good *and* bad PRs alike.
    - Selective artifacts (e2e, contract_tests) show stronger correlation
      because teams invest in them only on well-prepared PRs.
    - All correlations have noise so real-world variance is reflected.
    """
    rng = random.Random(seed)

    # api-gateway and auth-service teams run more artifacts than others
    _HIGH_QUALITY_REPOS = {"api-gateway", "auth-service"}

    start_date = datetime(2025, 9, 1, tzinfo=timezone.utc)
    records: list[PRRecord] = []

    for i in range(n):
        repo   = rng.choice(_REPOS)
        author = rng.choice(_AUTHORS)
        created_at = start_date + timedelta(
            days=rng.uniform(0, 180),
            hours=rng.uniform(0, 24),
        )

        # ── Base quality values (before artifact adjustments) ────────────────
        gate_pass_base    = max(0.0, min(1.0, 0.55 + rng.gauss(0, 0.12)))
        review_base       = max(0, int(rng.gauss(2.2, 1.1)))
        merge_time_base   = max(1.0, rng.gauss(48.0, 20.0))

        gate_pass_adj  = 0.0
        review_adj     = 0.0
        merge_time_adj = 0.0

        artifacts: list[HarnessArtifact] = []
        repo_factor = 1.0 if repo in _HIGH_QUALITY_REPOS else 0.85

        for art_type, (adoption, gp_eff, rc_eff, mt_eff) in _ARTIFACT_PROFILES.items():
            if rng.random() < adoption * repo_factor:
                passed    = rng.random() < 0.87
                coverage  = rng.uniform(55.0, 95.0) if art_type is ArtifactType.COVERAGE_REPORT else None
                issues    = max(0, int(rng.gauss(1.5, 1.8))) if not passed else rng.randint(0, 2)

                artifacts.append(HarnessArtifact(
                    artifact_type=art_type,
                    passed=passed,
                    execution_time_seconds=rng.uniform(15.0, 300.0),
                    coverage_pct=round(coverage, 1) if coverage else None,
                    issues_found=issues,
                ))

                # Apply effect with multiplicative noise (±30 %)
                noise = 0.7 + rng.random() * 0.6
                gate_pass_adj  += gp_eff * noise
                review_adj     += rc_eff * noise
                merge_time_adj += mt_eff * noise

        # ── Final metric values ───────────────────────────────────────────────
        gate_pass_rate     = round(max(0.0, min(1.0, gate_pass_base + gate_pass_adj)), 3)
        review_cycles      = max(0, review_base + round(review_adj))
        time_to_merge_raw  = max(0.5, merge_time_base + merge_time_adj)
        time_to_merge      = time_to_merge_raw if rng.random() < 0.92 else None
        merged             = time_to_merge is not None
        merged_at          = created_at + timedelta(hours=time_to_merge) if merged else None

        records.append(PRRecord(
            pr_id=f"PR-{i + 1:04d}",
            repo=repo,
            author=author,
            created_at=created_at,
            merged_at=merged_at,
            artifacts=artifacts,
            gate_pass_rate=gate_pass_rate,
            review_cycles=int(review_cycles),
            time_to_merge_hours=round(time_to_merge, 1) if time_to_merge else None,
            merged=merged,
            post_merge_incidents=(
                rng.randint(0, 2) if merged and rng.random() < 0.10 else 0
            ),
        ))

    return records
