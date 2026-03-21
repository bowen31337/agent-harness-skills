"""
harness lint — run architectural and golden-principle checks in a single pass.

Usage (CLI):
    harness lint [--gate architecture|principles|lint] [--no-principles]
                 [--project-root PATH] [--format json|table]

Runs only the architecture, principles, and lint gates (no tests, coverage, or
security scan).  Emits a structured LintResponse that agents can parse without
re-running the gates.

Exit codes:
    0  All gates passed.
    1  Any error-severity violation.
    2  Internal error (gate runner exception).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click
from rich import box
from rich.console import Console
from rich.table import Table

from harness_skills.generators.evaluation import (
    GateConfig,
    GateId,
    EvaluationReport,
    Severity,
    run_all_gates,
)
from harness_skills.models.base import Status, Violation
from harness_skills.models.lint import LintResponse


# ---------------------------------------------------------------------------
# Gates that harness lint considers (subset of all evaluation gates)
# ---------------------------------------------------------------------------

_LINT_GATES: list[GateId] = [GateId.ARCHITECTURE, GateId.PRINCIPLES, GateId.LINT]

_GATE_CHOICES: list[str] = [g.value for g in _LINT_GATES]


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------


@click.command("lint")
@click.option(
    "--gate",
    "selected_gates",
    type=click.Choice(_GATE_CHOICES, case_sensitive=False),
    multiple=True,
    help=(
        "Run only the specified gate(s).  "
        "Choices: architecture, principles, lint.  "
        "Repeat to combine multiple gates."
    ),
)
@click.option(
    "--no-principles",
    is_flag=True,
    default=False,
    help="Skip loading .claude/principles.yaml and omit the principles gate.",
)
@click.option(
    "--project-root",
    default=".",
    show_default=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="Path to the repository root.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "table"], case_sensitive=False),
    default="table",
    show_default=True,
    help=(
        "Output format.  "
        "json: machine-parseable LintResponse.  "
        "table: rich ASCII table for interactive terminal use."
    ),
)
@click.pass_context
def lint_cmd(
    ctx: click.Context,
    selected_gates: tuple[str, ...],
    no_principles: bool,
    project_root: Path,
    output_format: str,
) -> None:
    """Run architecture, principles, and lint checks in a single pass.

    Only the architectural subset of gates run — no tests, no coverage, no
    security scan.  For a full quality sweep use ``harness evaluate``.

    \b
    Agent usage pattern (JSON):
        result=$(harness lint --format json)
        passed=$(echo "$result" | jq '.passed')
        if [ "$passed" = "false" ]; then
            echo "$result" | jq '.violations[] | select(.severity=="error")'
        fi

    \b
    Pipeline usage:
        harness create --profile standard --then lint --then evaluate
    """
    try:
        gates = _resolve_gates(selected_gates, no_principles)
        config = GateConfig()
        report = run_all_gates(project_root=project_root, config=config, gates=gates)
    except Exception as exc:  # noqa: BLE001
        click.echo(f"[harness lint] internal error: {exc}", err=True)
        ctx.exit(2)
        return

    lint_response = _build_lint_response(report)

    if output_format == "json":
        click.echo(lint_response.model_dump_json(indent=2))
    else:
        _print_table_report(lint_response, report)

    if not lint_response.passed:
        ctx.exit(1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_gates(
    selected_gates: tuple[str, ...],
    no_principles: bool,
) -> list[GateId]:
    """Return the ordered list of GateIds to execute.

    Starts from the lint-specific subset (architecture → principles → lint),
    applies --gate filters, then removes principles when --no-principles is set.
    """
    base: list[GateId] = (
        [GateId(g) for g in selected_gates] if selected_gates else list(_LINT_GATES)
    )
    if no_principles and GateId.PRINCIPLES in base:
        base = [g for g in base if g != GateId.PRINCIPLES]
    return base


def _build_lint_response(report: EvaluationReport) -> LintResponse:
    """Convert an EvaluationReport (from the gate runner) to a LintResponse."""
    violations: list[Violation] = []
    rules_applied: list[str] = []

    for failure in report.failures:
        sev_map = {
            Severity.ERROR: "error",
            Severity.WARNING: "warning",
            Severity.INFO: "info",
        }
        violations.append(
            Violation(
                rule_id=failure.rule_id or failure.gate_id.value,
                severity=sev_map.get(failure.severity, failure.severity.value),
                file_path=failure.file_path,
                line_number=failure.line_number,
                message=failure.message,
                suggestion=failure.suggestion,
            )
        )
        if failure.rule_id and failure.rule_id not in rules_applied:
            rules_applied.append(failure.rule_id)

    error_count = sum(1 for v in violations if v.severity == "error")
    warning_count = sum(1 for v in violations if v.severity == "warning")
    info_count = sum(1 for v in violations if v.severity == "info")
    critical_count = 0  # harness lint has no critical-severity gates

    # files_checked: count distinct file paths from gate results (approximate)
    files_checked = len(
        {f.file_path for f in report.failures if f.file_path}
    )

    return LintResponse(
        command="harness lint",
        status=Status.PASSED if report.passed else Status.FAILED,
        passed=report.passed,
        timestamp=datetime.now(timezone.utc).isoformat(),
        message=(
            "All architectural and principle checks passed."
            if report.passed
            else f"{error_count} blocking violation(s)"
        ),
        total_violations=len(violations),
        critical_count=critical_count,
        error_count=error_count,
        warning_count=warning_count,
        info_count=info_count,
        violations=violations,
        files_checked=files_checked,
        rules_applied=rules_applied,
    )


# ---------------------------------------------------------------------------
# Table formatter
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

_SEVERITY_ICON: dict[str, str] = {
    "error": "🔴",
    "warning": "🟡",
    "info": "🔵",
}


def _print_table_report(response: LintResponse, report: EvaluationReport) -> None:
    """Render a human-readable rich table to stdout."""
    console = Console()

    overall_style = "bold green" if response.passed else "bold red"
    overall_label = "PASS ✅" if response.passed else "FAIL ❌"
    console.print()
    console.print(
        f"[{overall_style}]Harness Lint — {overall_label}[/{overall_style}]"
        f"  |  {response.total_violations} violation(s)"
        f"  ·  {response.error_count} blocking"
        f"  ·  {response.warning_count} warnings"
        f"  ·  {response.info_count} info"
    )
    console.print()

    # Gate summary table
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

    for result in report.gate_results:
        if result.gate_id not in _LINT_GATES:
            continue
        status_val = result.status.value
        style = _STATUS_STYLE.get(status_val, "")
        duration_str = f"{result.duration_ms} ms" if result.duration_ms is not None else "—"
        failure_count_str = str(result.failure_count) if result.failure_count else "—"
        gates_table.add_row(
            result.gate_id.value,
            f"[{style}]{status_val}[/{style}]",
            duration_str,
            failure_count_str,
        )

    console.print(gates_table)

    # Violations detail (only when there are failures)
    if response.violations:
        errors = [v for v in response.violations if v.severity == "error"]
        warnings = [v for v in response.violations if v.severity == "warning"]
        infos = [v for v in response.violations if v.severity == "info"]

        if errors:
            console.print("[bold red]🔴 BLOCKING — Must fix before merge[/bold red]")
            _print_violation_group(console, errors)

        if warnings:
            console.print("[bold yellow]🟡 SUGGESTIONS — Nice to have[/bold yellow]")
            _print_violation_group(console, warnings)

        if infos:
            console.print("[bold cyan]🔵 INFO[/bold cyan]")
            _print_violation_group(console, infos)
    else:
        console.print(
            "[bold green]✅ All architectural and principle checks passed.[/bold green]"
        )

    console.print()


def _print_violation_group(console: Console, violations: list[Violation]) -> None:
    """Print a group of violations in the lint report format."""
    console.print("─" * 52)
    for v in violations:
        location = ""
        if v.file_path:
            location = v.file_path
            if v.line_number:
                location += f":{v.line_number}"
        loc_str = f" · {location}" if location else ""
        console.print(f"  [{v.rule_id}]{loc_str}")
        console.print(f'  "{v.message}"')
        if v.suggestion:
            console.print(f"  → {v.suggestion}")
        console.print()
