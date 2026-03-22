"""harness_skills/telemetry_reporter.py
=======================================
Reads ``docs/harness-telemetry.json`` (produced by ``HarnessTelemetry`` hooks)
and derives three categories of metrics:

  1. **Artifact utilization rates**  — which harness files are accessed and how
     often, expressed as a fraction of all artifact reads.
  2. **Command call frequency**       — how often each ``/slash-command`` is
     invoked, expressed as a fraction of all command invocations.
  3. **Gate effectiveness scores**    — which quality gates have the strongest
     failure signal, normalised to 0.0–1.0.

Teams use these metrics to identify underutilised artifacts (cold/unused) for
redesign or removal, and redundant gates (silent) for configuration review.

CLI
---
    python -m harness_skills.telemetry_reporter --help
    python -m harness_skills.telemetry_reporter                     # table report
    python -m harness_skills.telemetry_reporter --format json       # raw JSON
    python -m harness_skills.telemetry_reporter --min-reads 5       # filter noise
    python -m harness_skills.telemetry_reporter --top-n 15          # cap rows
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import click
import yaml

from harness_skills.cli.fmt import output_format_option, resolve_output_format
from harness_skills.cli.verbosity import VerbosityLevel, get_verbosity, vecho
from harness_skills.models.base import HarnessResponse, Status
from harness_skills.models.telemetry import (
    ArtifactMetric,
    CommandMetric,
    GateMetric,
    TelemetryReport,
    TelemetrySummary,
)

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

_DEFAULT_TELEMETRY_PATH = "docs/harness-telemetry.json"

# ---------------------------------------------------------------------------
# Categorisation thresholds
# (percentile-based on the *sorted* read counts)
# ---------------------------------------------------------------------------

# Artifact utilization bands (by cumulative read-count percentile)
_HOT_PERCENTILE  = 0.20   # top 20 % of reads → "hot"
_WARM_PERCENTILE = 0.60   # top 20–60 % → "warm", rest → "cold"

# Gate effectiveness bands
_HIGH_EFFECTIVENESS  = 0.60
_MEDIUM_EFFECTIVENESS = 0.30


# ---------------------------------------------------------------------------
# Core analyser
# ---------------------------------------------------------------------------


def _iso_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def _load_telemetry(path: Path) -> dict[str, Any]:
    """Load the telemetry JSON file, or return an empty store on failure."""
    if not path.exists():
        return {
            "schema_version": "1.0",
            "last_updated": _iso_now(),
            "totals": {
                "artifact_reads": {},
                "cli_command_invocations": {},
                "gate_failures": {},
            },
            "sessions": [],
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        click.echo(f"[harness-telemetry] warning: could not read {path}: {exc}", err=True)
        return {
            "schema_version": None,
            "last_updated": None,
            "totals": {"artifact_reads": {}, "cli_command_invocations": {}, "gate_failures": {}},
            "sessions": [],
        }


def _categorise_artifact(
    read_count: int,
    utilization_rate: float,
    cumulative_hot_threshold: float,
    cumulative_warm_threshold: float,
    running_total_rate: float,
) -> tuple[str, Optional[str]]:
    """Return (category, recommendation) for an artifact."""
    if read_count == 0:
        return "unused", "Candidate for removal — never accessed"
    # 'running_total_rate' is the cumulative fraction *after* adding this file.
    if running_total_rate <= cumulative_hot_threshold:
        return "hot", None
    if running_total_rate <= cumulative_warm_threshold:
        return "warm", None
    return "cold", "Consider refactoring or consolidating — low utilization"


def _gate_signal(score: float) -> tuple[str, Optional[str]]:
    if score >= _HIGH_EFFECTIVENESS:
        return "high", None
    if score >= _MEDIUM_EFFECTIVENESS:
        return "medium", None
    if score > 0.0:
        return "low", "Review gate configuration — low signal relative to other gates"
    return "silent", "Gate may be redundant — consider removal or reconfiguration"


def build_report(
    telemetry_path: Path,
    min_reads: int = 0,
    top_n: Optional[int] = None,
) -> TelemetryReport:
    """Parse telemetry data and return a structured ``TelemetryReport``."""

    t0 = time.monotonic()
    data = _load_telemetry(telemetry_path)
    totals = data.get("totals", {})
    sessions = data.get("sessions", [])

    # ── Raw counts ────────────────────────────────────────────────────────────
    raw_artifacts: dict[str, int] = totals.get("artifact_reads", {})
    raw_commands: dict[str, int] = totals.get("cli_command_invocations", {})
    raw_gates: dict[str, int] = totals.get("gate_failures", {})

    total_artifact_reads = sum(raw_artifacts.values())
    total_command_invocations = sum(raw_commands.values())
    total_gate_failures = sum(raw_gates.values())

    # ── Artifact metrics ──────────────────────────────────────────────────────
    # Sort descending by read count.
    sorted_artifacts = sorted(raw_artifacts.items(), key=lambda kv: kv[1], reverse=True)

    # Filter out noise (below min_reads) *after* computing utilization rates so
    # rates are relative to the *full* dataset, not the filtered view.
    artifact_metrics: list[ArtifactMetric] = []
    running_rate = 0.0
    for path_key, count in sorted_artifacts:
        rate = count / total_artifact_reads if total_artifact_reads > 0 else 0.0
        running_rate += rate
        cat, rec = _categorise_artifact(
            read_count=count,
            utilization_rate=rate,
            cumulative_hot_threshold=_HOT_PERCENTILE,
            cumulative_warm_threshold=_WARM_PERCENTILE,
            running_total_rate=running_rate,
        )
        if count < min_reads and min_reads > 0:
            continue
        artifact_metrics.append(
            ArtifactMetric(
                path=path_key,
                read_count=count,
                utilization_rate=round(rate, 6),
                category=cat,
                recommendation=rec,
            )
        )

    if top_n is not None:
        artifact_metrics = artifact_metrics[:top_n]

    # ── Command metrics ───────────────────────────────────────────────────────
    sorted_commands = sorted(raw_commands.items(), key=lambda kv: kv[1], reverse=True)

    # Build per-command session activity count.
    sessions_by_command: dict[str, int] = {}
    for session in sessions:
        session_cmds: dict[str, int] = session.get("cli_command_invocations", {})
        for cmd in session_cmds:
            sessions_by_command[cmd] = sessions_by_command.get(cmd, 0) + 1

    command_metrics: list[CommandMetric] = []
    for cmd, count in sorted_commands:
        freq = count / total_command_invocations if total_command_invocations > 0 else 0.0
        command_metrics.append(
            CommandMetric(
                command=cmd,
                invocation_count=count,
                frequency_rate=round(freq, 6),
                sessions_active=sessions_by_command.get(cmd, 0),
            )
        )

    # ── Gate effectiveness metrics ────────────────────────────────────────────
    sorted_gates = sorted(raw_gates.items(), key=lambda kv: kv[1], reverse=True)
    max_gate_failures = sorted_gates[0][1] if sorted_gates else 0

    gate_metrics: list[GateMetric] = []
    for gate, count in sorted_gates:
        score = count / max_gate_failures if max_gate_failures > 0 else 0.0
        strength, rec = _gate_signal(score)
        gate_metrics.append(
            GateMetric(
                gate_id=gate,
                failure_count=count,
                effectiveness_score=round(score, 6),
                signal_strength=strength,
                recommendation=rec,
            )
        )

    # ── Summary ───────────────────────────────────────────────────────────────
    cold_artifact_count = sum(
        1 for m in artifact_metrics if m.category in ("cold", "unused")
    )
    silent_gate_count = sum(1 for m in gate_metrics if m.signal_strength == "silent")

    summary = TelemetrySummary(
        sessions_analyzed=len(sessions),
        total_artifact_reads=total_artifact_reads,
        total_command_invocations=total_command_invocations,
        total_gate_failures=total_gate_failures,
        unique_artifacts=len(raw_artifacts),
        unique_commands=len(raw_commands),
        unique_gates=len(raw_gates),
        cold_artifact_count=cold_artifact_count,
        silent_gate_count=silent_gate_count,
        telemetry_path=str(telemetry_path.resolve()),
        schema_version=data.get("schema_version"),
        last_updated=data.get("last_updated"),
    )

    duration_ms = int((time.monotonic() - t0) * 1000)

    return TelemetryReport(
        command="harness telemetry",
        status=Status.PASSED,
        timestamp=_iso_now(),
        duration_ms=duration_ms,
        message=(
            f"{len(artifact_metrics)} artifact(s) · "
            f"{len(command_metrics)} command(s) · "
            f"{len(gate_metrics)} gate(s) · "
            f"{cold_artifact_count} cold/unused artifact(s) · "
            f"{silent_gate_count} silent gate(s)"
        ),
        summary=summary,
        artifacts=artifact_metrics,
        commands=command_metrics,
        gates=gate_metrics,
    )


# ---------------------------------------------------------------------------
# Human-readable rendering
# ---------------------------------------------------------------------------

_SEV_ICON = {
    "hot":    "🔥",
    "warm":   "🟡",
    "cold":   "🔵",
    "unused": "⚪",
    "high":   "✅",
    "medium": "🟡",
    "low":    "🟠",
    "silent": "⚫",
}


def _bar(value: float, width: int = 20) -> str:
    filled = round(value * width)
    return "█" * filled + "░" * (width - filled)


def render_report(report: TelemetryReport, *, color: bool = True) -> str:
    lines: list[str] = []
    s = report.summary
    sep = "━" * 60

    lines.append(sep)
    lines.append("  Harness Telemetry Report")
    lines.append(f"  Generated : {report.timestamp}")
    if s.last_updated:
        lines.append(f"  Data from : {s.last_updated}  ({s.sessions_analyzed} session(s))")
    lines.append(f"  Source    : {s.telemetry_path}")
    lines.append(sep)

    # ── Artifact Utilization ─────────────────────────────────────────────────
    lines.append("")
    lines.append("  Artifact Utilization Rates")
    lines.append("  " + "─" * 58)
    if not report.artifacts:
        lines.append("    (no artifact reads recorded)")
    else:
        col_w = max(len(m.path) for m in report.artifacts)
        col_w = min(col_w, 50)
        lines.append(
            f"    {'Artifact':<{col_w}}  {'Reads':>6}  {'Rate':>6}  {'Bar':<20}  Cat"
        )
        lines.append("    " + "─" * (col_w + 42))
        for m in report.artifacts:
            icon = _SEV_ICON.get(m.category, " ")
            path_str = m.path if len(m.path) <= col_w else "…" + m.path[-(col_w - 1):]
            lines.append(
                f"    {path_str:<{col_w}}  {m.read_count:>6}  {m.utilization_rate:>5.1%}"
                f"  {_bar(m.utilization_rate):<20}  {icon} {m.category}"
            )

    cold = [m for m in report.artifacts if m.category in ("cold", "unused")]
    if cold:
        lines.append("")
        lines.append(f"  ⚠ Underutilized artifacts ({len(cold)}) — candidates for redesign or removal:")
        for m in cold:
            lines.append(f"    • {m.path}  [{m.category}]  {m.recommendation or ''}")

    # ── Command Frequency ────────────────────────────────────────────────────
    lines.append("")
    lines.append("  Command Call Frequency")
    lines.append("  " + "─" * 58)
    if not report.commands:
        lines.append("    (no command invocations recorded)")
    else:
        col_w = max(len(m.command) for m in report.commands)
        col_w = min(col_w, 40)
        lines.append(
            f"    {'Command':<{col_w}}  {'Calls':>6}  {'Freq':>6}  {'Sessions':>8}  Bar"
        )
        lines.append("    " + "─" * (col_w + 38))
        for m in report.commands:
            cmd_str = m.command if len(m.command) <= col_w else "…" + m.command[-(col_w - 1):]
            lines.append(
                f"    {cmd_str:<{col_w}}  {m.invocation_count:>6}  {m.frequency_rate:>5.1%}"
                f"  {m.sessions_active:>8}  {_bar(m.frequency_rate, width=16)}"
            )

    # ── Gate Effectiveness ───────────────────────────────────────────────────
    lines.append("")
    lines.append("  Gate Effectiveness Scores")
    lines.append("  " + "─" * 58)
    if not report.gates:
        lines.append("    (no gate failures recorded)")
    else:
        col_w = max(len(m.gate_id) for m in report.gates)
        col_w = min(col_w, 30)
        lines.append(
            f"    {'Gate':<{col_w}}  {'Failures':>8}  {'Score':>6}  {'Signal':<8}  Bar"
        )
        lines.append("    " + "─" * (col_w + 40))
        for m in report.gates:
            icon = _SEV_ICON.get(m.signal_strength, " ")
            gate_str = m.gate_id if len(m.gate_id) <= col_w else "…" + m.gate_id[-(col_w - 1):]
            lines.append(
                f"    {gate_str:<{col_w}}  {m.failure_count:>8}  {m.effectiveness_score:>5.1%}"
                f"  {icon} {m.signal_strength:<6}  {_bar(m.effectiveness_score)}"
            )

    silent = [m for m in report.gates if m.signal_strength == "silent"]
    if silent:
        lines.append("")
        lines.append(f"  ⚫ Silent gates ({len(silent)}) — consider removal or reconfiguration:")
        for m in silent:
            lines.append(f"    • {m.gate_id}  {m.recommendation or ''}")

    # ── Footer ───────────────────────────────────────────────────────────────
    lines.append("")
    lines.append(sep)
    lines.append(
        f"  {s.total_artifact_reads} artifact reads  ·  "
        f"{s.total_command_invocations} command calls  ·  "
        f"{s.total_gate_failures} gate failures  ·  "
        f"{report.duration_ms} ms"
    )
    lines.append(sep)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command("telemetry")
@click.option(
    "--telemetry-file",
    default=_DEFAULT_TELEMETRY_PATH,
    show_default=True,
    help="Path to the harness-telemetry.json file to analyse.",
)
@output_format_option()
@click.option(
    "--min-reads",
    default=0,
    show_default=True,
    help="Exclude artifacts with fewer than N total reads (reduces noise).",
)
@click.option(
    "--top-n",
    default=None,
    type=int,
    help="Cap the artifact list at N entries (sorted by reads descending).",
)
@click.pass_context
def telemetry_cmd(
    ctx: click.Context,
    telemetry_file: str,
    output_format: Optional[str],
    min_reads: int,
    top_n: Optional[int],
) -> None:
    """Report artifact utilization rates, command frequency, and gate effectiveness."""

    fmt = resolve_output_format(output_format)
    verbosity = get_verbosity(ctx)
    path = Path(telemetry_file)

    vecho(
        f"  Analysing telemetry file: {path}",
        verbosity=verbosity,
        min_level=VerbosityLevel.verbose,
    )

    report = build_report(path, min_reads=min_reads, top_n=top_n)

    if fmt == "json":
        click.echo(report.model_dump_json(indent=2))
        return

    if fmt == "yaml":
        data = json.loads(report.model_dump_json())
        click.echo(
            yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True),
            nl=False,
        )
        return

    # Table output
    click.echo(render_report(report))
    click.echo("")
    click.echo("```json")
    click.echo(report.model_dump_json(indent=2))
    click.echo("```")

    # Verbose: explain the exit code before exiting.
    if report.summary.cold_artifact_count > 0 or report.summary.silent_gate_count > 0:
        vecho(
            f"  {report.summary.cold_artifact_count} cold/unused artifact(s) · "
            f"{report.summary.silent_gate_count} silent gate(s) — exit 1",
            verbosity=verbosity,
            min_level=VerbosityLevel.verbose,
            err=True,
        )
        sys.exit(1)


# Allow running as a module: python -m harness_skills.telemetry_reporter
if __name__ == "__main__":
    telemetry_cmd()
