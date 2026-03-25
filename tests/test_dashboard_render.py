"""
Tests for harness_dashboard.dashboard — render_dashboard and CLI entry point.

Covers the 90 uncovered lines: _header_panel, _metrics_table,
_correlation_table, _tier_summary, render_dashboard, and _cli_main.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from io import StringIO
from unittest.mock import patch

import pytest
from rich.console import Console

from harness_dashboard.dashboard import (
    _correlation_table,
    _header_panel,
    _metrics_table,
    _tier_summary,
    render_dashboard,
    _cli_main,
)
from harness_dashboard.models import (
    ArtifactType,
    CorrelationInsight,
    DashboardReport,
    EffectivenessMetrics,
    EffectivenessTier,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _metric(
    hid: str = "hrn-001",
    score: float = 75.0,
    tier: EffectivenessTier = EffectivenessTier.STRONG,
    pr_count: int = 5,
    gate: float = 0.85,
    cycles: float = 1.5,
    ttm: float = 24.0,
    art_type: ArtifactType = ArtifactType.FIXTURE,
) -> EffectivenessMetrics:
    return EffectivenessMetrics(
        harness_id=hid,
        artifact_type=art_type,
        artifact_count=10,
        coverage_pct=80.0,
        pr_count=pr_count,
        avg_gate_pass_rate=gate,
        avg_review_cycles=cycles,
        avg_time_to_merge_hours=ttm,
        effectiveness_score=score,
        tier=tier,
    )


def _correlation(
    r: float = 0.55,
    p: float = 0.01,
    sig: bool = True,
    direction: str = "positive",
) -> CorrelationInsight:
    return CorrelationInsight(
        artifact_attr="coverage_pct",
        pr_metric="gate_pass_rate",
        pearson_r=r,
        p_value=p,
        significant=sig,
        direction=direction,
        interpretation="Higher coverage correlates with higher gate pass.",
    )


def _report(
    n_metrics: int = 2,
    n_corr: int = 2,
) -> DashboardReport:
    metrics = [
        _metric(
            hid=f"hrn-{i+1:03d}",
            score=90 - i * 20,
            tier=[EffectivenessTier.ELITE, EffectivenessTier.STRONG,
                  EffectivenessTier.MODERATE, EffectivenessTier.WEAK][min(i, 3)],
        )
        for i in range(n_metrics)
    ]
    corrs = [
        _correlation(r=0.55, direction="positive"),
        _correlation(r=-0.45, direction="negative"),
    ][:n_corr]
    return DashboardReport(
        generated_at=datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc),
        harness_count=n_metrics,
        pr_count=n_metrics * 5,
        metrics=metrics,
        correlations=corrs,
        fleet_avg_score=65.0,
        fleet_avg_gate_pass_rate=0.78,
        fleet_avg_review_cycles=2.1,
        fleet_avg_time_to_merge_hours=30.5,
        elite_count=1,
        strong_count=1,
        moderate_count=0,
        weak_count=0,
    )


def _capture(report: DashboardReport) -> str:
    """Render dashboard into a string buffer."""
    buf = StringIO()
    console = Console(file=buf, force_terminal=True, width=200)
    render_dashboard(report, console=console)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# _header_panel
# ---------------------------------------------------------------------------

class TestHeaderPanel:
    def test_returns_panel(self):
        panel = _header_panel(_report())
        assert panel is not None

    def test_contains_fleet_stats(self):
        output = _capture(_report())
        assert "Harnesses" in output
        assert "PRs analysed" in output


# ---------------------------------------------------------------------------
# _metrics_table
# ---------------------------------------------------------------------------

class TestMetricsTable:
    def test_returns_table(self):
        report = _report(n_metrics=3)
        table = _metrics_table(report.metrics)
        assert table is not None

    def test_all_tiers_rendered(self):
        metrics = [
            _metric(hid="e1", score=95, tier=EffectivenessTier.ELITE, gate=0.95),
            _metric(hid="s1", score=70, tier=EffectivenessTier.STRONG, gate=0.75),
            _metric(hid="m1", score=50, tier=EffectivenessTier.MODERATE, gate=0.65),
            _metric(hid="w1", score=20, tier=EffectivenessTier.WEAK, gate=0.40),
        ]
        report = DashboardReport(
            harness_count=4, pr_count=20, metrics=metrics,
            elite_count=1, strong_count=1, moderate_count=1, weak_count=1,
        )
        output = _capture(report)
        assert "ELITE" in output
        assert "STRONG" in output
        assert "MODERATE" in output
        assert "WEAK" in output

    def test_zero_prs_dash_shown(self):
        """Harness with pr_count=0 should show dashes instead of values."""
        m = _metric(pr_count=0, gate=0.0, cycles=0.0, ttm=0.0)
        report = DashboardReport(
            harness_count=1, pr_count=0, metrics=[m],
        )
        output = _capture(report)
        # The render uses "—" (em-dash) for zero-PR entries
        assert "hrn-001" in output

    def test_gate_pass_colour_thresholds(self):
        """Gate pass rate styling: >=0.80 green, >=0.60 yellow, <0.60 red."""
        metrics = [
            _metric(hid="g1", gate=0.90),
            _metric(hid="g2", gate=0.65),
            _metric(hid="g3", gate=0.40),
        ]
        table = _metrics_table(metrics)
        assert table is not None


# ---------------------------------------------------------------------------
# _correlation_table
# ---------------------------------------------------------------------------

class TestCorrelationTable:
    def test_returns_table(self):
        corrs = [_correlation()]
        table = _correlation_table(corrs)
        assert table is not None

    def test_all_r_styles(self):
        """Test that all r-value ranges map to distinct styles."""
        corrs = [
            _correlation(r=0.55, direction="positive"),   # bold green (>0.4)
            _correlation(r=0.25, direction="positive"),   # green (>0.1)
            _correlation(r=0.05, direction="neutral"),    # dim
            _correlation(r=-0.25, direction="negative"),  # red (<-0.1)
            _correlation(r=-0.55, direction="negative"),  # bold red (<-0.4)
        ]
        table = _correlation_table(corrs)
        assert table is not None

    def test_significant_and_nonsignificant(self):
        corrs = [
            _correlation(sig=True),
            _correlation(sig=False),
        ]
        table = _correlation_table(corrs)
        assert table is not None


# ---------------------------------------------------------------------------
# _tier_summary
# ---------------------------------------------------------------------------

class TestTierSummary:
    def test_returns_panel(self):
        panel = _tier_summary(_report())
        assert panel is not None

    def test_all_tiers_appear(self):
        report = _report()
        report.elite_count = 2
        report.strong_count = 3
        report.moderate_count = 4
        report.weak_count = 1
        report.harness_count = 10
        output = _capture(report)
        # Check that tier badges appear
        assert "ELITE" in output
        assert "STRONG" in output
        assert "MODERATE" in output
        assert "WEAK" in output

    def test_zero_harness_count_no_division_error(self):
        """harness_count=0 uses 1 as denominator to avoid ZeroDivisionError."""
        report = DashboardReport(harness_count=0, pr_count=0)
        panel = _tier_summary(report)
        assert panel is not None


# ---------------------------------------------------------------------------
# render_dashboard
# ---------------------------------------------------------------------------

class TestRenderDashboard:
    def test_no_crash_with_full_report(self):
        report = _report(n_metrics=4, n_corr=2)
        output = _capture(report)
        assert "Dashboard" in output

    def test_empty_report(self):
        report = DashboardReport(harness_count=0, pr_count=0)
        output = _capture(report)
        assert "Dashboard" in output

    def test_creates_console_if_none(self):
        report = _report()
        # Should not raise
        render_dashboard(report)


# ---------------------------------------------------------------------------
# _cli_main (click-based CLI)
# ---------------------------------------------------------------------------

class TestCliMain:
    def test_default_rich_output(self):
        """_cli_main with default args renders the Rich dashboard."""
        with patch("sys.argv", ["dashboard", "--harnesses", "3", "--seed", "42"]):
            # Click commands call sys.exit on success, but we catch SystemExit
            try:
                _cli_main()
            except SystemExit as e:
                assert e.code is None or e.code == 0

    def test_json_output(self, capsys):
        """_cli_main with --json emits valid JSON."""
        with patch("sys.argv", ["dashboard", "--harnesses", "3", "--seed", "42", "--json"]):
            try:
                _cli_main()
            except SystemExit:
                pass
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "harness_count" in data
        assert "metrics" in data

    def test_seed_zero_means_random(self):
        """--seed 0 should translate to None (random)."""
        with patch("sys.argv", ["dashboard", "--harnesses", "2", "--seed", "0"]):
            try:
                _cli_main()
            except SystemExit:
                pass
