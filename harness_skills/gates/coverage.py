"""
harness_skills/gates/coverage.py
==================================
Code-coverage gate implementation.

The gate reads a coverage report produced by a test runner and blocks the
build when the overall **line-coverage percentage** falls below a configurable
threshold (default **90 %**).

Supported report formats
-------------------------
* **XML** — pytest-cov / coverage.py XML (``coverage.xml``), JaCoCo XML.

  * *coverage.py* root element carries a ``line-rate`` float attribute
    (0.0–1.0), which is multiplied by 100.
  * *JaCoCo* stores ``<counter type="LINE" missed="M" covered="C"/>``
    elements whose ``missed`` and ``covered`` values are summed across the
    whole report.

* **JSON** — coverage.py JSON report (``coverage.json``).
  The gate reads ``totals.percent_covered`` (a float, 0–100).

* **lcov** — LCOV tracefile (``lcov.info``, ``lcov.out``, ``coverage.lcov``).
  The gate sums all ``LF:`` (lines found) and ``LH:`` (lines hit) counters
  across every source-file section.

Usage (standalone CLI)::

    python -m harness_skills.gates.coverage [--root .] [--threshold 90]
    python -m harness_skills.gates.coverage --coverage-file lcov.info --format lcov

Usage (programmatic)::

    from pathlib import Path
    from harness_skills.gates.coverage import CoverageGate
    from harness_skills.models.gate_configs import CoverageGateConfig

    cfg    = CoverageGateConfig(threshold=85.0, coverage_file="coverage.xml")
    result = CoverageGate(cfg).run(repo_root=Path("."))

    if not result.passed:
        for v in result.violations:
            print(v.summary())
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from harness_skills.models.gate_configs import CoverageGateConfig


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

ViolationKind = Literal["below_threshold", "missing_report", "parse_error"]
Severity = Literal["error", "warning"]


@dataclass
class Violation:
    """A single coverage-gate violation."""

    kind: ViolationKind
    """
    ``below_threshold`` — measured coverage is below the configured minimum.
    ``missing_report``  — the coverage report file was not found on disk.
    ``parse_error``     — the report file could not be parsed.
    """

    severity: Severity
    """``error`` blocks the gate; ``warning`` is advisory only."""

    message: str
    """Human-readable description of the violation."""

    coverage_file: Path | None = None
    """Absolute path to the coverage report (if known)."""

    actual_coverage: float | None = None
    """Measured coverage percentage (``below_threshold`` only)."""

    required_threshold: float | None = None
    """Configured threshold that was not met."""

    def summary(self) -> str:
        """One-line string suitable for console output."""
        loc = f" [{self.coverage_file}]" if self.coverage_file else ""
        return (
            f"[{self.severity.upper():7s}] {self.kind:20s}{loc} — {self.message}"
        )


@dataclass
class GateResult:
    """Aggregate result returned by :class:`CoverageGate`."""

    passed: bool
    """``True`` when coverage meets or exceeds the threshold (or
    ``fail_on_error=False``)."""

    violations: list[Violation] = field(default_factory=list)
    """All violations found (at most one per run)."""

    coverage_file: Path | None = None
    """Resolved path to the coverage report that was read."""

    actual_coverage: float | None = None
    """Measured line-coverage percentage, or ``None`` if parsing failed."""

    threshold: float = 90.0
    """The configured minimum threshold."""

    report_format: str | None = None
    """The format that was used to parse the report (``xml``, ``json``, ``lcov``)."""

    stats: dict[str, object] = field(default_factory=dict)
    """Extra numeric details: ``actual_coverage``, ``threshold``, ``delta``."""

    def errors(self) -> list[Violation]:
        """Return only error-severity violations."""
        return [v for v in self.violations if v.severity == "error"]

    def warnings(self) -> list[Violation]:
        """Return only warning-severity violations."""
        return [v for v in self.violations if v.severity == "warning"]

    def __str__(self) -> str:  # pragma: no cover
        cov_str = (
            f"{self.actual_coverage:.2f}%"
            if self.actual_coverage is not None
            else "N/A"
        )
        lines = [
            f"CoverageGate: {'PASSED' if self.passed else 'FAILED'}",
            f"  Coverage report : {self.coverage_file or '(none)'}",
            f"  Actual coverage : {cov_str}",
            f"  Required        : {self.threshold:.2f}%",
            f"  Format          : {self.report_format or 'unknown'}",
        ]
        if self.violations:
            lines.append("")
            for v in self.violations:
                lines.append("  " + v.summary())
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

_FORMAT_BY_EXTENSION: dict[str, str] = {
    ".xml": "xml",
    ".json": "json",
    ".info": "lcov",
    ".out": "lcov",
    ".lcov": "lcov",
}


def _detect_format(path: Path) -> str:
    """Infer coverage report format from *path*'s file extension.

    Falls back to ``"xml"`` for unrecognised extensions since
    ``coverage.xml`` is the most common report name.
    """
    return _FORMAT_BY_EXTENSION.get(path.suffix.lower(), "xml")


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


class _ParseError(Exception):
    """Raised internally when a coverage file cannot be parsed."""


def _parse_xml(path: Path) -> float:
    """Parse a coverage.py or JaCoCo XML report; return percent coverage.

    *coverage.py* format::

        <coverage line-rate="0.923" ...>

    *JaCoCo* format (root ``<report>`` element)::

        <counter type="LINE" missed="10" covered="90"/>

    Raises
    ------
    _ParseError
        When the file is not valid XML or contains no recognisable
        coverage data.
    """
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        raise _ParseError(f"XML parse error: {exc}") from exc

    root = tree.getroot()

    # coverage.py: root element has a "line-rate" attribute (0.0–1.0)
    line_rate = root.get("line-rate")
    if line_rate is not None:
        try:
            return float(line_rate) * 100.0
        except ValueError as exc:
            raise _ParseError(
                f"Invalid line-rate value: {line_rate!r}"
            ) from exc

    # JaCoCo: aggregate <counter type="LINE" missed="M" covered="C"/> elements
    lines_found = 0
    lines_hit = 0
    for counter in root.iter("counter"):
        if counter.get("type", "").upper() == "LINE":
            try:
                missed = int(counter.get("missed", 0))
                covered = int(counter.get("covered", 0))
                lines_found += missed + covered
                lines_hit += covered
            except ValueError:
                pass  # skip malformed counter elements

    if lines_found > 0:
        return (lines_hit / lines_found) * 100.0

    raise _ParseError(
        "No recognisable coverage data found in XML report. "
        "Tried coverage.py (line-rate attribute) and JaCoCo "
        "(<counter type=\"LINE\"> elements) formats."
    )


def _parse_json(path: Path) -> float:
    """Parse a coverage.py JSON report; return percent coverage.

    Expected structure::

        {"totals": {"percent_covered": 91.5, ...}, ...}

    Raises
    ------
    _ParseError
        When the file is not valid JSON or the expected key is missing.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise _ParseError(f"JSON parse error: {exc}") from exc

    totals = data.get("totals", {})
    pct = totals.get("percent_covered")
    if pct is not None:
        try:
            return float(pct)
        except (TypeError, ValueError) as exc:
            raise _ParseError(
                f"Invalid percent_covered value: {pct!r}"
            ) from exc

    raise _ParseError(
        "'totals.percent_covered' key not found in JSON report. "
        "Generate the report with: coverage json"
    )


_LCOV_LF_RE = re.compile(r"^LF:(\d+)\s*$", re.MULTILINE)
_LCOV_LH_RE = re.compile(r"^LH:(\d+)\s*$", re.MULTILINE)


def _parse_lcov(path: Path) -> float:
    """Parse an LCOV tracefile; return percent line coverage.

    Aggregates all ``LF:`` (lines found) and ``LH:`` (lines hit) counters
    across every source-file section in the tracefile.

    Raises
    ------
    _ParseError
        When the file cannot be read or contains no ``LF:`` entries.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise _ParseError(f"Cannot read lcov file: {exc}") from exc

    lines_found = sum(int(m.group(1)) for m in _LCOV_LF_RE.finditer(text))
    lines_hit = sum(int(m.group(1)) for m in _LCOV_LH_RE.finditer(text))

    if lines_found == 0:
        raise _ParseError(
            "No LF: (lines-found) entries found in lcov tracefile. "
            "Generate it with: lcov --capture --directory . --output-file lcov.info"
        )

    return (lines_hit / lines_found) * 100.0


_PARSERS: dict[str, object] = {
    "xml": _parse_xml,
    "json": _parse_json,
    "lcov": _parse_lcov,
}


# ---------------------------------------------------------------------------
# Gate runner
# ---------------------------------------------------------------------------


class CoverageGate:
    """Runs the code-coverage gate against a repository.

    Reads the coverage report specified in ``config.coverage_file``, parses
    it according to ``config.report_format`` (or auto-detects the format),
    and compares the resulting percentage against ``config.threshold``.

    Parameters
    ----------
    config:
        Gate configuration.  When omitted, defaults are used
        (threshold=90 %, coverage_file=coverage.xml, format=auto).

    Example::

        from pathlib import Path
        from harness_skills.gates.coverage import CoverageGate
        from harness_skills.models.gate_configs import CoverageGateConfig

        result = CoverageGate(CoverageGateConfig(threshold=85.0)).run(Path("."))
        print(result)
    """

    def __init__(self, config: CoverageGateConfig | None = None) -> None:
        self.config: CoverageGateConfig = config or CoverageGateConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, repo_root: Path) -> GateResult:
        """Execute the gate against *repo_root* and return a :class:`GateResult`.

        Parameters
        ----------
        repo_root:
            Absolute (or CWD-relative) path to the repository root.
            Relative ``coverage_file`` paths are resolved against this
            directory.
        """
        repo_root = repo_root.resolve()
        cfg = self.config
        severity: Severity = "error" if cfg.fail_on_error else "warning"

        # ── 1. Resolve coverage file path ──────────────────────────────
        cov_path = Path(cfg.coverage_file)
        if not cov_path.is_absolute():
            cov_path = (repo_root / cov_path).resolve()

        # ── 2. Verify the file exists ───────────────────────────────────
        if not cov_path.exists():
            violation = Violation(
                kind="missing_report",
                severity=severity,
                message=(
                    f"Coverage report not found: '{cov_path}'. "
                    "Run your test suite with coverage enabled before the gate "
                    "(e.g. pytest --cov --cov-report=xml)."
                ),
                coverage_file=cov_path,
                required_threshold=cfg.threshold,
            )
            return GateResult(
                passed=not cfg.fail_on_error,
                violations=[violation],
                coverage_file=cov_path,
                threshold=cfg.threshold,
            )

        # ── 3. Detect / validate format ─────────────────────────────────
        fmt = cfg.report_format
        if fmt == "auto":
            fmt = _detect_format(cov_path)

        parser = _PARSERS.get(fmt)
        if parser is None:
            violation = Violation(
                kind="parse_error",
                severity=severity,
                message=(
                    f"Unknown coverage report format: {fmt!r}. "
                    "Supported formats: xml, json, lcov."
                ),
                coverage_file=cov_path,
                required_threshold=cfg.threshold,
            )
            return GateResult(
                passed=not cfg.fail_on_error,
                violations=[violation],
                coverage_file=cov_path,
                threshold=cfg.threshold,
                report_format=fmt,
            )

        # ── 4. Parse the report ─────────────────────────────────────────
        try:
            actual_pct = parser(cov_path)  # type: ignore[operator]
        except _ParseError as exc:
            violation = Violation(
                kind="parse_error",
                severity=severity,
                message=f"Failed to parse coverage report '{cov_path}': {exc}",
                coverage_file=cov_path,
                required_threshold=cfg.threshold,
            )
            return GateResult(
                passed=not cfg.fail_on_error,
                violations=[violation],
                coverage_file=cov_path,
                threshold=cfg.threshold,
                report_format=fmt,
            )

        # ── 5. Compare against threshold ────────────────────────────────
        violations: list[Violation] = []
        if actual_pct < cfg.threshold:
            shortfall = cfg.threshold - actual_pct
            violations.append(
                Violation(
                    kind="below_threshold",
                    severity=severity,
                    message=(
                        f"Coverage {actual_pct:.2f}% is below the required "
                        f"threshold of {cfg.threshold:.2f}% "
                        f"(shortfall: {shortfall:.2f} pp). "
                        "Add tests to cover the uncovered lines."
                    ),
                    coverage_file=cov_path,
                    actual_coverage=actual_pct,
                    required_threshold=cfg.threshold,
                )
            )

        passed = (not violations) or (not cfg.fail_on_error)
        return GateResult(
            passed=passed,
            violations=violations,
            coverage_file=cov_path,
            actual_coverage=actual_pct,
            threshold=cfg.threshold,
            report_format=fmt,
            stats={
                "actual_coverage": actual_pct,
                "threshold": cfg.threshold,
                "delta": actual_pct - cfg.threshold,
            },
        )


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m harness_skills.gates.coverage",
        description=(
            "Coverage gate — enforce a minimum line-coverage threshold "
            "and block PRs that fall below it."
        ),
    )
    p.add_argument(
        "--root",
        default=".",
        metavar="PATH",
        help="Repository root to resolve relative paths against (default: current directory).",
    )
    p.add_argument(
        "--threshold",
        type=float,
        default=90.0,
        metavar="PCT",
        help="Minimum required coverage percentage 0–100 (default: 90.0).",
    )
    p.add_argument(
        "--coverage-file",
        default="coverage.xml",
        metavar="FILE",
        help=(
            "Path to the coverage report, relative to --root "
            "(default: coverage.xml)."
        ),
    )
    p.add_argument(
        "--format",
        choices=["auto", "xml", "json", "lcov"],
        default="auto",
        dest="report_format",
        help=(
            "Coverage report format. 'auto' detects from the file extension "
            "(default: auto)."
        ),
    )
    p.add_argument(
        "--fail-on-error",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Exit non-zero when coverage is below the threshold (default: true). "
            "Use --no-fail-on-error to emit a warning and still pass."
        ),
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-violation output; only print the summary line.",
    )
    return p


def main(argv: list[str] | None = None) -> int:  # pragma: no cover
    """CLI entry-point; returns an exit code (0 = pass, 1 = fail)."""
    args = _build_parser().parse_args(argv)
    cfg = CoverageGateConfig(
        threshold=args.threshold,
        coverage_file=args.coverage_file,
        report_format=args.report_format,
        fail_on_error=args.fail_on_error,
    )
    result = CoverageGate(cfg).run(Path(args.root))

    if not args.quiet:
        print(result)

    return 0 if result.passed else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
