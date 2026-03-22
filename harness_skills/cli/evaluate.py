"""
harness evaluate — run all evaluation gates and emit a structured report.

Usage (CLI):
    harness evaluate [--format json|yaml|table] [--gate GATE_ID ...] [--project-root PATH]

Usage (agent tool call):
    harness evaluate --format json
    harness evaluate --format yaml
    harness evaluate --format json --gate regression --gate types

The --format json output conforms to evaluation_report.schema.json.
The --format yaml output is the same data serialised as YAML (human-friendly, still machine-parseable).
The --format table output renders a rich ASCII table for interactive terminal use.

Agents should:
  1. Check the top-level `passed` field.
  2. If False, read `summary.blocking_failures` for scope.
  3. Iterate `failures` (severity=error first) and act on each `suggestion`.

Exit codes:
    0  All gates passed.
    1  One or more gates failed (check `failures` for details).
    2  Internal error (gate runner exception).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import click
import yaml
from rich import box
from rich.console import Console
from rich.table import Table

<<<<<<< HEAD
from harness_skills.cli.fmt import output_format_option, resolve_output_format
||||||| 9c7e5db
=======
from harness_skills.cli.verbosity import VerbosityLevel, at_least, get_verbosity, vecho
>>>>>>> feat/skill-invocatio-cli-commands-support-verbosity-levels-q
from harness_skills.generators.evaluation import (
    GateConfig,
    GateId,
    EvaluationReport,
    Severity,
    format_report,
    run_all_gates,
    run_gate,
)


@click.command("evaluate")
@output_format_option(
    help_extra=(
        "json output conforms to evaluation_report.schema.json.  "
        "table renders a rich ASCII table for interactive terminal use."
    ),
)
@click.option(
    "--gate",
    "selected_gates",
    type=click.Choice([g.value for g in GateId], case_sensitive=False),
    multiple=True,
    help="Run only the specified gate(s).  Repeat to run multiple gates.",
)
@click.option(
    "--project-root",
    default=".",
    show_default=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="Path to the repository root.",
)
@click.option(
    "--coverage-threshold",
    default=90.0,
    show_default=True,
    type=float,
    help="Minimum line-coverage % required by the coverage gate.",
)
@click.option(
    "--max-staleness-days",
    default=30,
    show_default=True,
    type=int,
    help="Maximum age (days) for generated harness artifacts before the docs_freshness gate warns.",
)
@click.pass_context
def evaluate_cmd(
    ctx: click.Context,
    output_format: Optional[str],
    selected_gates: tuple[str, ...],
    project_root: Path,
    coverage_threshold: float,
    max_staleness_days: int,
) -> None:
    """Run all evaluation gates in sequence and emit a structured pass/fail report.

    Gates run sequentially in declaration order.  The report conforms to
    evaluation_report.schema.json and contains actionable GateFailure objects
    that agents can parse and act on without human intervention.

    When all gates pass, exits 0.  On any failure, exits 1.

    \b
    Agent usage pattern (JSON):
        result=$(harness evaluate --format json)
        passed=$(echo "$result" | jq '.passed')
        if [ "$passed" = "false" ]; then
            echo "$result" | jq '.failures[] | select(.severity=="error")'
        fi

    \b
    Agent usage pattern (YAML):
        harness evaluate --format yaml | python3 -c "
        import sys, yaml
        r = yaml.safe_load(sys.stdin)
        print('passed:', r['passed'])
        "
    """
<<<<<<< HEAD
    fmt = resolve_output_format(output_format)
||||||| 9c7e5db
=======
    verbosity = get_verbosity(ctx)
>>>>>>> feat/skill-invocatio-cli-commands-support-verbosity-levels-q
    config = GateConfig(
        coverage_threshold=coverage_threshold,
        max_staleness_days=max_staleness_days,
    )

    gates: Optional[list[GateId]] = (
        [GateId(g) for g in selected_gates] if selected_gates else None
    )

    # Verbose: announce which gates will run before executing them.
    if gates:
        vecho(
            f"  Running {len(gates)} gate(s): {', '.join(g.value for g in gates)}",
            verbosity=verbosity,
            min_level=VerbosityLevel.verbose,
        )
    else:
        vecho(
            "  Running all evaluation gates…",
            verbosity=verbosity,
            min_level=VerbosityLevel.verbose,
        )

    report = run_all_gates(project_root=project_root, config=config, gates=gates)

<<<<<<< HEAD
    if fmt == "json":
||||||| 9c7e5db
    if output_format == "json":
=======
    if output_format == "json":
        # Machine-parseable — always emitted regardless of verbosity.
>>>>>>> feat/skill-invocatio-cli-commands-support-verbosity-levels-q
        click.echo(format_report(report))
<<<<<<< HEAD
    elif fmt == "yaml":
||||||| 9c7e5db
    elif output_format == "yaml":
=======
    elif output_format == "yaml":
        # Machine-parseable — always emitted regardless of verbosity.
>>>>>>> feat/skill-invocatio-cli-commands-support-verbosity-levels-q
        click.echo(_format_yaml_report(report))
    else:
        _print_table_report(report, verbosity=verbosity)

    # Verbose: summary line with timing details.
    if output_format in ("json", "yaml"):
        vecho(
            f"  Gates run: {report.summary.total_gates}  "
            f"Passed: {report.summary.passed_gates}  "
            f"Failed: {report.summary.blocking_failures} blocking",
            verbosity=verbosity,
            min_level=VerbosityLevel.verbose,
            err=True,
        )

    # Exit code: 0 = all passed, 1 = failures
    if not report.passed:
        ctx.exit(1)


# ---------------------------------------------------------------------------
# YAML formatter
# ---------------------------------------------------------------------------


def _format_yaml_report(report: EvaluationReport) -> str:
    """Serialise an EvaluationReport to a YAML string.

    Produces the same data as --format json but in YAML, which is easier for
    humans to skim and can still be parsed by scripts (``yaml.safe_load``).
    The output is NOT validated against evaluation_report.schema.json because
    JSON Schema validators don't speak YAML directly, but the data structure is
    identical to the JSON output.
    """
    data = json.loads(report.model_dump_json())
    return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)


# ---------------------------------------------------------------------------
# Table formatter (rich)
# ---------------------------------------------------------------------------

_STATUS_STYLE: dict[str, str] = {
    "passed": "bold green",
    "failed": "bold red",
    "skipped": "dim",
    "error": "bold yellow",
}

_SEVERITY_STYLE: dict[str, str] = {
    "error": "bold red",
    "warning": "yellow",
    "info": "cyan",
}


def _print_table_report(
    report: EvaluationReport,
    *,
    verbosity: str = VerbosityLevel.normal,
) -> None:
    """Render a human-readable rich table to stdout.

    Layout:
      1. Header line — overall pass/fail + summary counts (hidden in quiet mode).
      2. Gates table — one row per gate with status, duration, failure count, message.
      3. Failures detail table — one row per GateFailure (only when failures exist).
      4. Timing footer — shown in verbose/debug mode.

    Parameters
    ----------
    report:
        The evaluation report to render.
    verbosity:
        Active verbosity level (from :func:`~harness_skills.cli.verbosity.get_verbosity`).
        In *quiet* mode the surrounding header and blank lines are omitted so
        that only the table rows remain.
    """
    console = Console()
    s = report.summary

    # ── 1. Header (suppressed in quiet mode) ───────────────────────────────
    overall_style = "bold green" if report.passed else "bold red"
    overall_label = "PASSED" if report.passed else "FAILED"
    if at_least(verbosity, VerbosityLevel.normal):
        console.print()
        console.print(
            f"[{overall_style}]{'✓' if report.passed else '✗'} Evaluation {overall_label}[/{overall_style}]"
            f"  —  {s.passed_gates}/{s.total_gates} gates passed"
            f"  |  {s.blocking_failures} blocking failure(s)"
            f"  |  {s.total_failures} total failure(s)"
        )
        console.print()

    # ── 2. Gates summary table ──────────────────────────────────────────────
    gates_table = Table(
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold",
        expand=False,
    )
    gates_table.add_column("Gate", style="bold", min_width=16)
    gates_table.add_column("Status", min_width=8)
    gates_table.add_column("Duration", justify="right", min_width=9)
    gates_table.add_column("Failures", justify="right", min_width=8)
    gates_table.add_column("Message")

    for result in report.gate_results:
        status_val = result.status.value
        style = _STATUS_STYLE.get(status_val, "")
        duration_str = f"{result.duration_ms} ms" if result.duration_ms is not None else "—"
        failure_count_str = str(result.failure_count) if result.failure_count else "—"
        message_str = result.message or ""
        gates_table.add_row(
            result.gate_id.value,
            f"[{style}]{status_val}[/{style}]",
            duration_str,
            failure_count_str,
            message_str,
        )

    console.print(gates_table)

    # ── 3. Failures detail table (only when there are failures) ────────────
    if report.failures:
        if at_least(verbosity, VerbosityLevel.normal):
            console.print()
            console.print("[bold]Failure Details[/bold]")
            console.print()

        failures_table = Table(
            box=box.SIMPLE,
            show_header=True,
            header_style="bold",
            expand=True,
        )
        failures_table.add_column("Sev", min_width=7)
        failures_table.add_column("Gate", min_width=14)
        failures_table.add_column("Location", min_width=20)
        failures_table.add_column("Message")
        failures_table.add_column("Suggestion")

        for failure in report.failures:
            sev_val = failure.severity.value
            sev_style = _SEVERITY_STYLE.get(sev_val, "")

            location = ""
            if failure.file_path:
                location = failure.file_path
                if failure.line_number:
                    location += f":{failure.line_number}"

            failures_table.add_row(
                f"[{sev_style}]{sev_val}[/{sev_style}]",
                failure.gate_id.value,
                location,
                failure.message,
                failure.suggestion or "",
            )

        console.print(failures_table)

    # ── 4. Footer / timing (verbose and debug only) ─────────────────────────
    if at_least(verbosity, VerbosityLevel.verbose) and report.gate_results:
        total_ms = sum(
            r.duration_ms for r in report.gate_results if r.duration_ms is not None
        )
        console.print(f"[dim]  Total gate time: {total_ms} ms[/dim]")

    if at_least(verbosity, VerbosityLevel.normal):
        console.print()
