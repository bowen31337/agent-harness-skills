"""
Pivot Tracker — strategic REFINE vs PIVOT decision.

Inspired by Anthropic's harness design for long-running applications:
https://www.anthropic.com/engineering/harness-design-long-running-apps

Key insight: after each evaluation cycle, the generator must make a strategic
decision — **refine** the current approach (scores trending up) or **pivot**
to an entirely different approach (scores declining).  Anthropic's experiments
showed that some generations refined incrementally while others took sharp
aesthetic turns between iterations.  The pivot decision should be data-driven,
not left to the generator's instinct.

The ``PivotTracker`` monitors evaluation score trends and decides:

- **APPROVE** — score meets the approval threshold; the work is done.
- **REFINE** — scores are stable or improving; keep iterating on this approach.
- **PIVOT** — 2+ consecutive score declines; the current approach is hitting
  a ceiling.  Scrap it and try something fundamentally different.

Usage
-----
::

    from harness_skills.pivot_tracker import PivotTracker, PivotDecision

    tracker = PivotTracker(approve_threshold=7.0)

    # After each evaluation round, record the score
    decision = tracker.record_score(5.2)  # → REFINE (first score, no trend)
    decision = tracker.record_score(5.8)  # → REFINE (improving)
    decision = tracker.record_score(5.5)  # → REFINE (one decline)
    decision = tracker.record_score(5.0)  # → PIVOT  (two consecutive declines)

    # After pivoting, the tracker resets its trend detection
    tracker.reset_trend()
    decision = tracker.record_score(6.5)  # → REFINE (fresh start)
    decision = tracker.record_score(7.5)  # → APPROVE (above threshold)

    # Get a markdown entry for PLAN.md
    print(tracker.to_plan_entry())
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum


class PivotDecision(str, Enum):
    """Decision after recording an evaluation score."""

    REFINE = "REFINE"
    """Scores are stable or improving — keep iterating on this approach."""

    PIVOT = "PIVOT"
    """2+ consecutive score declines — try a fundamentally different approach."""

    APPROVE = "APPROVE"
    """Score meets the approval threshold — the work is done."""


class PivotTracker:
    """Track evaluation score trends and decide REFINE vs PIVOT vs APPROVE.

    Parameters
    ----------
    approve_threshold:
        Minimum score to trigger an APPROVE decision.  Default: 7.0.
    decline_count_to_pivot:
        Number of consecutive score declines required to trigger PIVOT.
        Default: 2.
    """

    def __init__(
        self,
        approve_threshold: float = 7.0,
        decline_count_to_pivot: int = 2,
    ) -> None:
        self.approve_threshold = approve_threshold
        self.decline_count_to_pivot = decline_count_to_pivot
        self._scores: list[float] = []
        self._decisions: list[PivotDecision] = []
        self._consecutive_declines: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def scores(self) -> list[float]:
        """All recorded scores (read-only copy)."""
        return list(self._scores)

    @property
    def decisions(self) -> list[PivotDecision]:
        """All decisions made (read-only copy)."""
        return list(self._decisions)

    @property
    def consecutive_declines(self) -> int:
        """Current count of consecutive score declines."""
        return self._consecutive_declines

    @property
    def latest_score(self) -> float | None:
        """The most recently recorded score, or ``None``."""
        return self._scores[-1] if self._scores else None

    @property
    def latest_decision(self) -> PivotDecision | None:
        """The most recently made decision, or ``None``."""
        return self._decisions[-1] if self._decisions else None

    def record_score(self, score: float) -> PivotDecision:
        """Record a new evaluation score and return the strategic decision.

        Decision logic:

        1. If ``score >= approve_threshold`` → APPROVE.
        2. If this score is lower than the previous score, increment the
           consecutive-decline counter.  If it reaches
           ``decline_count_to_pivot`` → PIVOT.
        3. Otherwise → REFINE.

        Parameters
        ----------
        score:
            The evaluation score (0–10) from the latest round.

        Returns
        -------
        PivotDecision
            The recommended next action.
        """
        # Check for approval first
        if score >= self.approve_threshold:
            self._scores.append(score)
            self._consecutive_declines = 0
            decision = PivotDecision.APPROVE
            self._decisions.append(decision)
            return decision

        # Track decline trend
        if self._scores and score < self._scores[-1]:
            self._consecutive_declines += 1
        elif self._scores and score >= self._scores[-1]:
            self._consecutive_declines = 0
        # First score: no trend yet, consecutive_declines stays at 0

        self._scores.append(score)

        # Decide
        if self._consecutive_declines >= self.decline_count_to_pivot:
            decision = PivotDecision.PIVOT
        else:
            decision = PivotDecision.REFINE

        self._decisions.append(decision)
        return decision

    def reset_trend(self) -> None:
        """Reset the consecutive-decline counter after a pivot.

        Call this after the generator has pivoted to a new approach so that
        the tracker starts fresh for the new direction.  Score history is
        preserved (for audit purposes) but the decline counter resets.
        """
        self._consecutive_declines = 0

    def to_plan_entry(self) -> str:
        """Return a markdown string summarising the tracker state.

        Suitable for appending to PLAN.md or a progress log.

        Returns
        -------
        str
            Markdown-formatted summary of scores, decisions, and trend.
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        lines: list[str] = [
            f"### Pivot Tracker Status ({now})",
            "",
            f"- **Approve threshold:** {self.approve_threshold}",
            f"- **Consecutive declines:** {self._consecutive_declines}"
            f" / {self.decline_count_to_pivot} (pivot trigger)",
            f"- **Total iterations:** {len(self._scores)}",
        ]

        if self._scores:
            lines.append(f"- **Latest score:** {self._scores[-1]:.1f}")
            lines.append(f"- **Score trend:** {' → '.join(f'{s:.1f}' for s in self._scores)}")

        if self._decisions:
            lines.append(f"- **Latest decision:** {self._decisions[-1].value}")

        lines.append("")
        return "\n".join(lines)
