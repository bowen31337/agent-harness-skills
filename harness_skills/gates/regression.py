"""
harness_skills/gates/regression.py
=====================================
Regression gate — run the full test suite and block the build when any
existing test fails.

The gate executes ``pytest`` under a configurable timeout, parses the
JUnit XML report produced with ``--junitxml`` to extract per-test failure
details, and returns a :class:`GateResult` that callers can inspect or
render.

Usage (standalone CLI)::

    python -m harness_skills.gates.regression [--root .] [--timeout 300]
    python -m harness_skills.gates.regression --test-paths tests/unit
    python -m harness_skills.gates.regression --no-fail-on-error

Usage (programmatic)::

    from pathlib import Path
    from harness_skills.gates.regression import RegressionGate
    from harness_skills.models.gate_configs import RegressionGateConfig

    cfg    = RegressionGateConfig(timeout_seconds=120, extra_args=["-x"])
    result = RegressionGate(cfg).run(repo_root=Path("."))

    if not result.passed:
        for v in result.violations:
            print(v.summary())
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from harness_skills.models.gate_configs import RegressionGateConfig


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

ViolationKind = Literal[
    "test_failed",
    "suite_error",
    "timeout",
]
Severity = Literal["error", "warning"]


@dataclass
class Violation:
    """A single regression-gate violation."""

    kind: ViolationKind
    """
    ``test_failed`` — a specific test case failed.
    ``suite_error``  — the test runner exited non-zero but no JUnit XML was
                       produced (tool not installed, syntax error, etc.).
    ``timeout``      — the test suite exceeded the configured timeout.
    """

    severity: Severity
    """``error`` blocks the gate; ``warning`` is advisory only."""

    message: str
    """Human-readable description of the violation."""

    file_path: str | None = None
    """Source file that contains the failing test (if known)."""

    line_number: int | None = None
    """Line number of the failing assertion (if known)."""

    suggestion: str | None = None
    """Actionable hint for fixing the violation."""

    def summary(self) -> str:
        """One-line string suitable for console output."""
        loc = ""
        if self.file_path:
            loc = f" [{self.file_path}"
            if self.line_number:
                loc += f":{self.line_number}"
            loc += "]"
        return (
            f"[{self.severity.upper():7s}] {self.kind:15s}{loc} — {self.message}"
        )


@dataclass
class GateResult:
    """Aggregate result returned by :class:`RegressionGate`."""

    passed: bool
    """``True`` when all tests passed (or ``fail_on_error=False``)."""

    violations: list[Violation] = field(default_factory=list)
    """All violations found."""

    total_tests: int | None = None
    """Number of test cases discovered (if parseable from the JUnit report)."""

    failed_tests: int | None = None
    """Number of test cases that failed."""

    error_tests: int | None = None
    """Number of test cases that errored."""

    skipped_tests: int | None = None
    """Number of test cases that were skipped."""

    duration_ms: int | None = None
    """Wall-clock time taken by the test suite in milliseconds."""

    stats: dict[str, object] = field(default_factory=dict)
    """Extra numeric details for downstream consumers."""

    def errors(self) -> list[Violation]:
        """Return only error-severity violations."""
        return [v for v in self.violations if v.severity == "error"]

    def warnings(self) -> list[Violation]:
        """Return only warning-severity violations."""
        return [v for v in self.violations if v.severity == "warning"]

    def __str__(self) -> str:  # pragma: no cover
        lines = [f"RegressionGate: {'PASSED' if self.passed else 'FAILED'}"]
        if self.total_tests is not None:
            lines.append(
                f"  Tests : {self.total_tests} total, "
                f"{self.failed_tests or 0} failed, "
                f"{self.error_tests or 0} errors, "
                f"{self.skipped_tests or 0} skipped"
            )
        if self.duration_ms is not None:
            lines.append(f"  Time  : {self.duration_ms}ms")
        if self.violations:
            lines.append("")
            for v in self.violations:
                lines.append("  " + v.summary())
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# JUnit XML parser
# ---------------------------------------------------------------------------

_FILE_LINE_RE = re.compile(r"([\w/\\.\-]+\.py):(\d+)")


def _parse_junit_xml(
    xml_path: Path,
    severity: Severity,
) -> tuple[list[Violation], dict[str, int | None]]:
    """Parse a JUnit XML report and return (violations, stats).

    Parameters
    ----------
    xml_path:
        Path to the ``--junitxml`` output file produced by pytest.
    severity:
        Severity to assign each violation (``"error"`` or ``"warning"``).

    Returns
    -------
    tuple[list[Violation], dict]
        ``violations`` — one :class:`Violation` per failing / erroring
        test case.
        ``stats`` — ``total``, ``failed``, ``errors``, ``skipped`` counts.
    """
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError:
        return [], {}

    root = tree.getroot()

    # pytest writes a <testsuites> root wrapping one or more <testsuite>
    # elements. Older versions write a bare <testsuite> root.
    suites = list(root.iter("testsuite"))
    if not suites:
        return [], {}

    total = sum(int(s.get("tests", 0)) for s in suites)
    failed = sum(int(s.get("failures", 0)) for s in suites)
    errors = sum(int(s.get("errors", 0)) for s in suites)
    skipped = sum(int(s.get("skipped", 0)) for s in suites)

    violations: list[Violation] = []
    for tc in root.iter("testcase"):
        classname = tc.get("classname", "")
        testname = tc.get("name", "")
        full_name = f"{classname}.{testname}" if classname else testname

        for fail_el in tc.iter("failure"):
            text = fail_el.text or ""
            m = _FILE_LINE_RE.search(text)
            fp = m.group(1) if m else None
            ln = int(m.group(2)) if m else None
            msg = fail_el.get("message", "") or (text.splitlines()[0] if text else "")
            violations.append(Violation(
                kind="test_failed",
                severity=severity,
                message=f"Test failed: {full_name}" + (f" — {msg}" if msg else ""),
                file_path=fp,
                line_number=ln,
                suggestion=(
                    f"Fix the failing assertion in "
                    + (f"{fp}" if fp else "the test file")
                    + (f" at line {ln}" if ln else "")
                    + ". Run `pytest -x` locally for the full traceback."
                ),
            ))

        for err_el in tc.iter("error"):
            text = err_el.text or ""
            m = _FILE_LINE_RE.search(text)
            fp = m.group(1) if m else None
            ln = int(m.group(2)) if m else None
            msg = err_el.get("message", "") or (text.splitlines()[0] if text else "")
            violations.append(Violation(
                kind="suite_error",
                severity=severity,
                message=f"Test error: {full_name}" + (f" — {msg}" if msg else ""),
                file_path=fp,
                line_number=ln,
                suggestion=(
                    "Fix the setup/teardown error in "
                    + (f"{fp}" if fp else "the test file")
                    + ". Run `pytest -x` locally to reproduce."
                ),
            ))

    stats = {
        "total": total,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
    }
    return violations, stats


# ---------------------------------------------------------------------------
# Gate runner
# ---------------------------------------------------------------------------


class RegressionGate:
    """Runs the regression gate against a repository.

    Invokes the pytest test suite, collects failures from the JUnit XML
    report, and returns a :class:`GateResult`.  Any test failure (or test
    runner error) causes the gate to fail when ``config.fail_on_error=True``.

    Parameters
    ----------
    config:
        Gate configuration.  When omitted, defaults are used
        (timeout=300 s, no extra args, auto-discovery).

    Example::

        from pathlib import Path
        from harness_skills.gates.regression import RegressionGate
        from harness_skills.models.gate_configs import RegressionGateConfig

        result = RegressionGate(RegressionGateConfig(timeout_seconds=60)).run(Path("."))
        print(result)
    """

    def __init__(self, config: RegressionGateConfig | None = None) -> None:
        self.config: RegressionGateConfig = config or RegressionGateConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, repo_root: Path) -> GateResult:
        """Execute the regression gate against *repo_root*.

        Parameters
        ----------
        repo_root:
            Absolute (or CWD-relative) path to the repository root.
            pytest is invoked from this directory.

        Returns
        -------
        GateResult
            Populated with per-test violations if any tests fail.
        """
        import time as _time

        repo_root = repo_root.resolve()
        cfg = self.config
        severity: Severity = "error" if cfg.fail_on_error else "warning"

        junit_xml = repo_root / ".harness-regression-junit.xml"

        # ── Build pytest command ─────────────────────────────────────────
        cmd: list[str] = [
            sys.executable, "-m", "pytest",
            "--tb=short",
            f"--junitxml={junit_xml}",
            "-q",
        ]
        if cfg.test_paths:
            cmd.extend(cfg.test_paths)
        if cfg.extra_args:
            cmd.extend(cfg.extra_args)

        # ── Run the test suite ───────────────────────────────────────────
        t0 = _time.monotonic()
        try:
            result = subprocess.run(
                cmd,
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=cfg.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            junit_xml.unlink(missing_ok=True)
            violation = Violation(
                kind="timeout",
                severity=severity,
                message=(
                    f"Test suite timed out after {cfg.timeout_seconds}s. "
                    "No result is available."
                ),
                suggestion=(
                    "Increase ``timeout_seconds`` in harness.config.yaml, "
                    "or use ``extra_args: [\"-k\", \"not slow\"]`` to skip "
                    "long-running tests during the gate."
                ),
            )
            return GateResult(
                passed=not cfg.fail_on_error,
                violations=[violation],
            )

        duration_ms = int((_time.monotonic() - t0) * 1000)

        # ── All tests passed ─────────────────────────────────────────────
        if result.returncode == 0:
            # Parse the XML for stats even on success
            stats: dict[str, object] = {}
            total = failed = errors = skipped = None
            if junit_xml.exists():
                _, raw_stats = _parse_junit_xml(junit_xml, severity)
                junit_xml.unlink(missing_ok=True)
                total = raw_stats.get("total")
                failed = raw_stats.get("failed")
                errors = raw_stats.get("errors")
                skipped = raw_stats.get("skipped")
                stats = dict(raw_stats)
            return GateResult(
                passed=True,
                violations=[],
                total_tests=total,
                failed_tests=failed,
                error_tests=errors,
                skipped_tests=skipped,
                duration_ms=duration_ms,
                stats=stats,
            )

        # ── Some tests failed ────────────────────────────────────────────
        violations: list[Violation] = []
        total = failed = errors = skipped = None
        stats_dict: dict[str, object] = {}

        if junit_xml.exists():
            violations, raw_stats = _parse_junit_xml(junit_xml, severity)
            junit_xml.unlink(missing_ok=True)
            total = raw_stats.get("total")
            failed = raw_stats.get("failed")
            errors = raw_stats.get("errors")
            skipped = raw_stats.get("skipped")
            stats_dict = {k: v for k, v in raw_stats.items() if v is not None}

        # Fallback: no JUnit XML — produce a generic failure violation
        if not violations:
            violations.append(Violation(
                kind="suite_error",
                severity=severity,
                message=(
                    "Test suite exited with a non-zero status code "
                    f"(exit {result.returncode}). "
                    "No JUnit XML report was produced."
                ),
                suggestion=(
                    "Run `pytest --tb=short` locally to identify failing tests. "
                    "Ensure pytest is installed: `uv add pytest`."
                ),
            ))

        passed = not any(v.severity == "error" for v in violations)
        return GateResult(
            passed=passed,
            violations=violations,
            total_tests=total,
            failed_tests=failed,
            error_tests=errors,
            skipped_tests=skipped,
            duration_ms=duration_ms,
            stats=stats_dict,
        )


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m harness_skills.gates.regression",
        description=(
            "Regression gate — run the full test suite and block the build "
            "if any existing test fails."
        ),
    )
    p.add_argument(
        "--root",
        default=".",
        metavar="PATH",
        help="Repository root to run pytest from (default: current directory).",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=300,
        metavar="SECONDS",
        dest="timeout_seconds",
        help="Maximum seconds to allow the test suite to run (default: 300).",
    )
    p.add_argument(
        "--test-paths",
        nargs="*",
        default=[],
        metavar="PATH",
        help=(
            "Optional pytest path arguments (e.g. tests/unit tests/integration). "
            "Omit to let pytest auto-discover."
        ),
    )
    p.add_argument(
        "--fail-on-error",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Exit non-zero when any test fails (default: true). "
            "Use --no-fail-on-error to emit warnings and still pass."
        ),
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-violation output; only print the summary line.",
    )
    p.add_argument(
        "extra",
        nargs=argparse.REMAINDER,
        help="Additional arguments forwarded verbatim to pytest.",
    )
    return p


def main(argv: list[str] | None = None) -> int:  # pragma: no cover
    """CLI entry-point; returns an exit code (0 = pass, 1 = fail)."""
    args = _build_parser().parse_args(argv)
    # Strip leading '--' separator if present (from argparse.REMAINDER)
    extra = [a for a in (args.extra or []) if a != "--"]
    cfg = RegressionGateConfig(
        timeout_seconds=args.timeout_seconds,
        test_paths=args.test_paths or [],
        extra_args=extra,
        fail_on_error=args.fail_on_error,
    )
    result = RegressionGate(cfg).run(Path(args.root))

    if not args.quiet:
        print(result)

    return 0 if result.passed else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
