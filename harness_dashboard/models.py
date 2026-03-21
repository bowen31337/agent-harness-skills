"""
Data models for the harness effectiveness scoring system.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ArtifactType(str, Enum):
    FIXTURE = "fixture"
    MOCK = "mock"
    STUB = "stub"
    FACTORY = "factory"
    SNAPSHOT = "snapshot"


class EffectivenessTier(str, Enum):
    ELITE = "Elite"        # score >= 80
    STRONG = "Strong"      # score >= 60
    MODERATE = "Moderate"  # score >= 40
    WEAK = "Weak"          # score < 40


class HarnessRecord(BaseModel):
    """A single harness and its artifact footprint."""

    harness_id: str = Field(..., description="Unique identifier for the harness")
    artifact_type: ArtifactType = Field(..., description="Primary artifact type")
    artifact_count: int = Field(..., ge=0, description="Number of artifacts produced")
    coverage_pct: float = Field(..., ge=0.0, le=100.0, description="Test coverage %")
    schema_version: str = Field(default="1.0", description="Harness schema version")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PRRecord(BaseModel):
    """A pull request linked to a harness."""

    pr_id: str = Field(..., description="Unique PR identifier")
    harness_id: str = Field(..., description="FK to HarnessRecord.harness_id")
    gate_pass_rate: float = Field(..., ge=0.0, le=1.0)
    review_cycles: int = Field(..., ge=0)
    time_to_merge_hours: float = Field(..., ge=0.0)
    merged: bool = Field(default=True)
    merged_at: datetime = Field(default_factory=datetime.utcnow)

    @model_validator(mode="after")
    def _check_merged_has_time(self) -> "PRRecord":
        if self.merged and self.time_to_merge_hours <= 0:
            raise ValueError("merged=True requires time_to_merge_hours > 0")
        return self


class EffectivenessMetrics(BaseModel):
    """Per-harness computed effectiveness after scoring."""

    harness_id: str
    artifact_type: ArtifactType
    artifact_count: int
    coverage_pct: float

    pr_count: int = Field(0)
    avg_gate_pass_rate: float = Field(0.0, ge=0.0, le=1.0)
    avg_review_cycles: float = Field(0.0, ge=0.0)
    avg_time_to_merge_hours: float = Field(0.0, ge=0.0)

    effectiveness_score: float = Field(0.0, ge=0.0, le=100.0)
    tier: EffectivenessTier = EffectivenessTier.WEAK

    def score_bar(self, width: int = 20) -> str:
        filled = round(self.effectiveness_score / 100 * width)
        return f"[{'█' * filled}{'░' * (width - filled)}]"


class CorrelationInsight(BaseModel):
    """Pearson correlation between one artifact attribute and one PR metric."""

    artifact_attr: Literal["artifact_count", "coverage_pct"]
    pr_metric: Literal["gate_pass_rate", "review_cycles", "time_to_merge_hours"]
    pearson_r: float = Field(..., ge=-1.0, le=1.0)
    p_value: float = Field(..., ge=0.0, le=1.0)
    significant: bool
    direction: Literal["positive", "negative", "neutral"]
    interpretation: str


class DashboardReport(BaseModel):
    """Top-level report returned by compute_scores()."""

    generated_at: datetime = Field(default_factory=datetime.utcnow)
    harness_count: int
    pr_count: int
    metrics: list[EffectivenessMetrics] = Field(default_factory=list)
    correlations: list[CorrelationInsight] = Field(default_factory=list)

    fleet_avg_score: float = 0.0
    fleet_avg_gate_pass_rate: float = 0.0
    fleet_avg_review_cycles: float = 0.0
    fleet_avg_time_to_merge_hours: float = 0.0
    elite_count: int = 0
    strong_count: int = 0
    moderate_count: int = 0
    weak_count: int = 0
