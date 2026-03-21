"""
Harness Effectiveness Dashboard
================================

Rich-powered terminal dashboard that renders a DashboardReport.

Usage (standalone):
    python -m harness_dashboard.dashboard

Usage (programmatic):
    from harness_dashboard.dashboard import render_dashboard
    from harness_dashboard.scorer import compute_scores

    report = compute_scores(harnesses, prs)
    render_dashboard(report)
"""

from __future__ import annotations

from typing import Sequence

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .models import (
    CorrelationInsight,
    DashboardReport,
    EffectivenessMetrics,
    EffectivenessTier,
)


# ---------------------------------------------------------------------------
# Colour mapping
# ---------------------------------------------------------------------------

_TIER_STYLE: dict[EffectivenessTier, str] = {
    EffectivenessTier.ELITE:    "bold green",
    EffectivenessTier.STRONG:   "green",
    EffectivenessTier.MODERATE: "yellow",
    EffectivenessTier.WEAK:     "red",
}

_TIER_BADGE: dict[EffectivenessTier, str] = {
    EffectivenessTier.ELITE:    "★ ELITE",
    EffectivenessTier.STRONG:   "◆ STRONG",
    EffectivenessTier.MODERATE: "● MODERATE",
    EffectivenessTier.WEAK:     "○ WEAK",
}


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def _header_panel(report: DashboardReport) -> Panel:
    """Top-level stats strip."""
    generated = report.generated_at.strftime("%Y-%m-%d %H:%M UTC")

    stats = Table.grid(padding=(0, 3))
    stats.add_column(justify="center")
    stats.add_column(justify="center")
    stats.add_column(justify="center")
    stats.add_column(justify="center")
    stats.add_column(justify="center")
    stats.add_column(justify="center")
    stats.add_column(justify="center")

    def _kv(label: str, value: str, style: str = "bold cyan") -> Text:
        t = Text()
        t.append(f"{value}\n", style=style)
        t.append(label, style="dim")
        return t

    tier_dist = (
        f"[bold green]{report.elite_count}★[/] "
        f"[green]{report.strong_count}◆[/] "
        f"[yellow]{report.moderate_count}●[/] "
        f"[red]{report.weak_count}○[/]"
    )

    stats.add_row(
        _kv("Harnesses", str(report.harness_count)),
        _kv("PRs analysed", str(report.pr_count)),
        _kv("Fleet avg score", f"{report.fleet_avg_score:.1f}"),
        _kv("Avg gate pass", f"{report.fleet_avg_gate_pass_rate * 100:.1f}%"),
        _kv("Avg review cycles", f"{report.fleet_avg_review_cycles:.1f}"),
        _kv("Avg TTM (hrs)", f"{report.fleet_avg_time_to_merge_hours:.1f}"),
    )

    return Panel(
        stats,
        title=f"[bold]Harness Effectiveness Dashboard[/]  [dim]{generated}[/]",
        title_align="left",
        subtitle=f"[dim]Tier distribution: {tier_dist}[/]",
        subtitle_align="left",
        border_style="bright_blue",
        padding=(1, 2),
    )


def _metrics_table(metrics: Sequence[EffectivenessMetrics]) -> Table:
    """Per-harness ranked table."""
    t = Table(
        title="[bold]Harness Rankings[/]  (sorted by effectiveness score ↓)",
        box=box.SIMPLE_HEAD,
        show_lines=False,
        header_style="bold bright_blue",
        row_styles=["", "dim"],
    )

    t.add_column("#",            style="dim",         width=4,  justify="right")
    t.add_column("Harness ID",   style="bold",        min_width=14)
    t.add_column("Type",                              width=10)
    t.add_column("Artifacts",    justify="right",     width=10)
    t.add_column("Coverage",     justify="right",     width=10)
    t.add_column("PRs",          justify="right",     width=5)
    t.add_column("Gate Pass",    justify="right",     width=11)
    t.add_column("Rev Cycles",   justify="right",     width=11)
    t.add_column("TTM (hrs)",    justify="right",     width=10)
    t.add_column("Score",        justify="right",     width=8)
    t.add_column("Bar",                               width=22)
    t.add_column("Tier",         justify="center",    width=12)

    for rank, m in enumerate(metrics, start=1):
        tier_style = _TIER_STYLE[m.tier]
        badge = _TIER_BADGE[m.tier]

        bar_filled = round(m.effectiveness_score / 100 * 20)
        bar = Text()
        bar.append("█" * bar_filled, style=tier_style)
        bar.append("░" * (20 - bar_filled), style="dim")

        gate_style = (
            "green" if m.avg_gate_pass_rate >= 0.80
            else "yellow" if m.avg_gate_pass_rate >= 0.60
            else "red"
        )

        t.add_row(
            str(rank),
            m.harness_id,
            m.artifact_type.value,
            str(m.artifact_count),
            f"{m.coverage_pct:.1f}%",
            str(m.pr_count) if m.pr_count > 0 else "[dim]—[/]",
            Text(f"{m.avg_gate_pass_rate * 100:.1f}%", style=gate_style)
            if m.pr_count > 0 else Text("—", style="dim"),
            str(f"{m.avg_review_cycles:.1f}") if m.pr_count > 0 else "—",
            str(f"{m.avg_time_to_merge_hours:.1f}") if m.pr_count > 0 else "—",
            Text(f"{m.effectiveness_score:.1f}", style=f"bold {tier_style}"),
            bar,
            Text(badge, style=tier_style),
        )

    return t


def _correlation_table(correlations: Sequence[CorrelationInsight]) -> Table:
    """Pearson correlation matrix panel."""
    t = Table(
        title="[bold]Correlation Analysis[/]  (artifact attributes × PR quality metrics)",
        box=box.SIMPLE_HEAD,
        header_style="bold bright_blue",
        show_lines=False,
    )

    t.add_column("Artifact Attr",  min_width=16)
    t.add_column("PR Metric",      min_width=20)
    t.add_column("Pearson r",      justify="right", width=10)
    t.add_column("p-value",        justify="right", width=10)
    t.add_column("Sig.",           justify="center", width=6)
    t.add_column("Direction",      width=10)
    t.add_column("Interpretation", min_width=40)

    for c in correlations:
        r_style = (
            "bold green" if c.pearson_r > 0.4
            else "green" if c.pearson_r > 0.1
            else "bold red" if c.pearson_r < -0.4
            else "red" if c.pearson_r < -0.1
            else "dim"
        )
        sig_mark = Text("✓", style="bold green") if c.significant else Text("–", style="dim")
        dir_style = {
            "positive": "green",
            "negative": "red",
            "neutral": "dim",
        }[c.direction]

        t.add_row(
            c.artifact_attr.replace("_", " "),
            c.pr_metric.replace("_", " "),
            Text(f"{c.pearson_r:+.3f}", style=r_style),
            f"{c.p_value:.3f}",
            sig_mark,
            Text(c.direction, style=dir_style),
            Text(c.interpretation, style="dim"),
        )

    return t


def _tier_summary(report: DashboardReport) -> Panel:
    """Compact tier breakdown sidebar."""
    lines = Text()
    total = report.harness_count or 1

    for tier, count, style in [
        (EffectivenessTier.ELITE,    report.elite_count,    "bold green"),
        (EffectivenessTier.STRONG,   report.strong_count,   "green"),
        (EffectivenessTier.MODERATE, report.moderate_count, "yellow"),
        (EffectivenessTier.WEAK,     report.weak_count,     "red"),
    ]:
        pct = count / total * 100
        bar_w = round(pct / 100 * 15)
        lines.append(f"{_TIER_BADGE[tier]:<14}", style=style)
        lines.append(f"{'█' * bar_w}{'░' * (15 - bar_w)}", style=style)
        lines.append(f"  {count:>3} ({pct:4.1f}%)\n")

    return Panel(lines, title="[bold]Tier Breakdown[/]", border_style="bright_blue", padding=(1, 2))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_dashboard(report: DashboardReport, *, console: Console | None = None) -> None:
    """
    Render the full harness effectiveness dashboard to the terminal.

    Parameters
    ----------
    report:
        Fully populated DashboardReport from compute_scores().
    console:
        Optional Rich Console; creates a new one if None.
    """
    con = console or Console()

    con.print()
    con.print(_header_panel(report))
    con.print()
    con.print(_tier_summary(report))
    con.print()
    con.print(_metrics_table(report.metrics))
    con.print()
    con.print(_correlation_table(report.correlations))
    con.print()


# ---------------------------------------------------------------------------
# CLI entry point:  python -m harness_dashboard.dashboard
# ---------------------------------------------------------------------------

def _cli_main() -> None:
    """Demo: generate synthetic data, score it, render dashboard."""
    import click  # noqa: PLC0415

    from .data_generator import generate_dataset
    from .scorer import compute_scores

    @click.command()
    @click.option("--harnesses", default=20, show_default=True,
                  help="Number of synthetic harnesses to generate")
    @click.option("--seed", default=42, show_default=True,
                  help="Random seed for reproducibility (0 = random)")
    @click.option("--json", "as_json", is_flag=True, default=False,
                  help="Emit the DashboardReport as JSON instead of the Rich UI")
    def main(harnesses: int, seed: int, as_json: bool) -> None:
        """Harness Effectiveness Dashboard — demo with synthetic data."""
        effective_seed: int | None = seed if seed != 0 else None
        dataset = generate_dataset(num_harnesses=harnesses, seed=effective_seed)
        report = compute_scores(dataset.harnesses, dataset.prs)

        if as_json:
            import json  # noqa: PLC0415
            click.echo(report.model_dump_json(indent=2))
        else:
            render_dashboard(report)

    main()


if __name__ == "__main__":
    _cli_main()
