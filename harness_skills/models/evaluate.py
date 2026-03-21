"""Typed response model for ``harness evaluate`` (/harness:evaluate).

Schema conforms to evaluation_report.schema.json.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from harness_skills.models.base import GateResult, HarnessResponse, Status


class EvaluateResponse(HarnessResponse):
    """Response schema for ``harness evaluate`` (/harness:evaluate).

    Runs all evaluation gates in sequence and produces a structured
    pass/fail report.  Conforms to ``evaluation_report.schema.json``.
    """

    command: str = "harness evaluate"

    gates: list[GateResult] = Field(default_factory=list)
    total_gates: int = Field(ge=0, default=0)
    passed_gates: int = Field(ge=0, default=0)
    failed_gates: int = Field(ge=0, default=0)
    skipped_gates: int = Field(ge=0, default=0)
    coverage_pct: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Code coverage percentage if the coverage gate ran.",
    )
    report_path: str | None = Field(
        default=None,
        description="Path to the full JSON report written to disk.",
    )

    @model_validator(mode="after")
    def _sync_gate_counts(self) -> "EvaluateResponse":
        """Ensure aggregate counts match the gates list if both are provided."""
        if self.gates:
            by_status: dict[Status, int] = {s: 0 for s in Status}
            for g in self.gates:
                by_status[Status(g.status)] += 1  # type: ignore[call-overload]
            # Only override the counts if they are still at the default 0
            if self.passed_gates == 0 and self.failed_gates == 0:
                self.total_gates = len(self.gates)
                self.passed_gates = by_status[Status.PASSED]
                self.failed_gates = by_status[Status.FAILED]
                self.skipped_gates = by_status[Status.SKIPPED]
        return self
