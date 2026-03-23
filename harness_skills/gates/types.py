"""
harness_skills/gates/types.py
==============================
Static type-checking gate — **zero-error policy**.

The gate invokes the project's type checker (mypy for Python, tsc for
TypeScript) and blocks the build when **any** type errors are reported.
Warnings and notes are collected for visibility but never cause a failure.

Supported checkers
------------------
* **mypy** — Python static type checker.  Auto-selected when
  ``pyproject.toml``, ``setup.py``, or ``mypy.ini`` is present.
  ``--strict`` is passed when ``config.strict=True``.
* **tsc** — TypeScript compiler (``npx tsc --noEmit``).  Auto-selected
  when ``tsconfig.json`` is present.  Strict mode is driven by the
  project's own ``tsconfig.json``; the gate does *not* add ``--strict``.
* **pyright** — Python type checker (Pylance backend).  Explicitly
  selected via ``checker: "pyright"`` in ``harness.config.yaml``; not
  auto-detected to avoid ambiguity with mypy in mixed projects.

Zero-error policy
-----------------
The gate enforces **zero type errors**::

    if error_count > 0:
        result.passed = False   # gate fails

Warnings (mypy ``note`` lines) are reported but the gate still passes.

Usage (standalone CLI)::

    python -m harness_skills.gates.types [--root .] [--strict]
    python -m harness_skills.gates.types --checker tsc --root ./frontend

Usage (programmatic)::

    from pathlib import Path
    from harness_skills.gates.types import TypesGate
    from harness_skills.models.gate_configs import TypesGateConfig

    cfg    = TypesGateConfig(strict=True, ignore_errors=["import"])
    result = TypesGate(cfg).run(repo_root=Path("."))

    if not result.passed:
        for v in result.violations:
            print(v.summary())
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from harness_skills.models.gate_configs import TypesGateConfig


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

ViolationKind = Literal[
    "type_error",           # checker found a type error
    "checker_not_found",    # checker binary not installed / not on PATH
    "no_source_detected",   # couldn't auto-detect language / checker
    "internal_error",       # unexpected subprocess error
]

Severity = Literal["error", "warning", "note"]


@dataclass
class TypeViolation:
    """A single type-checking violation."""

    kind: ViolationKind
    """Category of the violation."""

    severity: Severity
    """``error`` blocks the gate; ``warning`` / ``note`` are advisory only."""

    message: str
    """Human-readable description."""

    file_path: Path | None = None
    """Source file where the error was found (if known)."""

    line_number: int | None = None
    """1-based line number (if known)."""

    error_code: str | None = None
    """Checker-specific error code, e.g. ``"assignment"`` (mypy) or
    ``"TS2304"`` (tsc)."""

    def summary(self) -> str:
        """One-line string suitable for console output."""
        loc = ""
        if self.file_path:
            loc = f" [{self.file_path}"
            if self.line_number:
                loc += f":{self.line_number}"
            loc += "]"
        code_str = f" [{self.error_code}]" if self.error_code else ""
        return (
            f"[{self.severity.upper():7s}] {self.kind:20s}{loc}{code_str}"
            f" — {self.message}"
        )


@dataclass
class TypesGateResult:
    """Aggregate result returned by :class:`TypesGate`."""

    passed: bool
    """``True`` when zero errors were found (or ``fail_on_error=False``)."""

    violations: list[TypeViolation] = field(default_factory=list)
    """All violations found (errors + warnings + notes)."""

    checker: str | None = None
    """The checker that was used: ``"mypy"``, ``"tsc"``, ``"pyright"``, or
    ``None`` if auto-detection failed."""

    error_count: int = 0
    """Number of *error*-severity violations."""

    warning_count: int = 0
    """Number of *warning*- or *note*-severity violations."""

    stats: dict[str, object] = field(default_factory=dict)
    """Extra details: ``error_count``, ``warning_count``, ``checker``."""

    def errors(self) -> list[TypeViolation]:
        """Return only error-severity violations."""
        return [v for v in self.violations if v.severity == "error"]

    def warnings(self) -> list[TypeViolation]:
        """Return only non-error violations (warning / note)."""
        return [v for v in self.violations if v.severity != "error"]

    def __str__(self) -> str:  # pragma: no cover
        checker_str = self.checker or "unknown"
        lines = [
            f"TypesGate [{checker_str}]: {'PASSED' if self.passed else 'FAILED'}",
            f"  Errors   : {self.error_count}",
            f"  Warnings : {self.warning_count}",
        ]
        if self.violations:
            lines.append("")
            for v in self.violations:
                lines.append("  " + v.summary())
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Checker detection
# ---------------------------------------------------------------------------

#: Sentinel meaning "no suitable checker found"
_NO_CHECKER = ""

#: mypy output line pattern:
#:   path/to/file.py:12: error: Some message  [error-code]
_MYPY_LINE_RE = re.compile(
    r"^(.+?):(\d+):\s+(error|warning|note):\s+(.+?)(?:\s+\[([^\]]+)\])?$"
)

#: tsc output line pattern (default format, not --pretty):
#:   path/to/file.ts(12,5): error TS2304: Cannot find name 'foo'.
_TSC_LINE_RE = re.compile(
    r"^(.+?)\((\d+),\d+\):\s+(error|warning)\s+(TS\d+):\s+(.+)$"
)

#: pyright output line pattern:
#:   /abs/path/file.py:12:5: error: Some message  (reportGeneralTypeIssues)
_PYRIGHT_LINE_RE = re.compile(
    r"^(.+?):(\d+):\d+:\s+(error|warning|information):\s+(.+?)(?:\s+\(([^)]+)\))?$"
)


def _detect_checker(repo_root: Path, hint: str) -> str:
    """Return the checker to use based on *hint* and project layout.

    Parameters
    ----------
    hint:
        Value of ``TypesGateConfig.checker``.  ``"auto"`` triggers
        heuristic detection.
    repo_root:
        Repository root path (used for heuristic detection only).

    Returns
    -------
    str
        One of ``"mypy"``, ``"tsc"``, ``"pyright"``, or ``_NO_CHECKER``
        when auto-detection finds nothing.
    """
    if hint != "auto":
        return hint  # user explicitly selected a checker

    # Python project indicators
    python_markers = [
        repo_root / "pyproject.toml",
        repo_root / "setup.py",
        repo_root / "setup.cfg",
        repo_root / "mypy.ini",
        repo_root / ".mypy.ini",
    ]
    if any(p.exists() for p in python_markers):
        return "mypy"

    # TypeScript project indicator
    if (repo_root / "tsconfig.json").exists():
        return "tsc"

    return _NO_CHECKER


# ---------------------------------------------------------------------------
# Output parsers
# ---------------------------------------------------------------------------


def _parse_mypy_output(
    output: str,
    ignore_codes: set[str],
    fail_on_error: bool,
) -> list[TypeViolation]:
    """Parse ``mypy`` stdout/stderr into a list of :class:`TypeViolation`.

    Only ``error`` and ``warning`` lines are parsed; ``note`` lines (which
    provide context for the preceding error) are collected but marked
    ``note`` severity and never counted as errors.

    Parameters
    ----------
    output:
        Combined stdout + stderr from the mypy subprocess.
    ignore_codes:
        Set of mypy error codes (e.g. ``{"import", "attr-defined"}``) to
        skip — matching violations are excluded from the result list.
    fail_on_error:
        Controls the severity assigned to violations.  When ``False`` all
        errors are downgraded to ``"warning"`` so the gate remains
        advisory.
    """
    violations: list[TypeViolation] = []
    for line in output.splitlines():
        m = _MYPY_LINE_RE.match(line)
        if not m:
            continue
        file_str, lineno_str, level, msg, code = m.groups()
        if code and code in ignore_codes:
            continue
        if level == "note":
            sev: Severity = "note"
        elif level == "warning":
            sev = "warning"
        else:
            sev = "error" if fail_on_error else "warning"
        violations.append(TypeViolation(
            kind="type_error",
            severity=sev,
            message=msg.strip(),
            file_path=Path(file_str),
            line_number=int(lineno_str),
            error_code=code,
        ))
    return violations


def _parse_tsc_output(
    output: str,
    ignore_codes: set[str],
    fail_on_error: bool,
) -> list[TypeViolation]:
    """Parse ``tsc --noEmit`` stdout/stderr into :class:`TypeViolation` objects.

    TypeScript diagnostic codes use the form ``TS<number>`` (e.g. ``TS2304``).
    Pass ``ignore_codes={"TS2304"}`` to suppress specific diagnostics.
    """
    violations: list[TypeViolation] = []
    for line in output.splitlines():
        m = _TSC_LINE_RE.match(line)
        if not m:
            continue
        file_str, lineno_str, level, code, msg = m.groups()
        if code in ignore_codes:
            continue
        sev = "error" if (level == "error" and fail_on_error) else "warning"
        violations.append(TypeViolation(
            kind="type_error",
            severity=sev,
            message=msg.strip(),
            file_path=Path(file_str),
            line_number=int(lineno_str),
            error_code=code,
        ))
    return violations


def _parse_pyright_output(
    output: str,
    ignore_codes: set[str],
    fail_on_error: bool,
) -> list[TypeViolation]:
    """Parse ``pyright`` stdout into :class:`TypeViolation` objects."""
    violations: list[TypeViolation] = []
    for line in output.splitlines():
        m = _PYRIGHT_LINE_RE.match(line)
        if not m:
            continue
        file_str, lineno_str, level, msg, code = m.groups()
        if code and code in ignore_codes:
            continue
        if level == "information":
            sev: Severity = "note"
        elif level == "warning":
            sev = "warning"
        else:
            sev = "error" if fail_on_error else "warning"
        violations.append(TypeViolation(
            kind="type_error",
            severity=sev,
            message=msg.strip(),
            file_path=Path(file_str),
            line_number=int(lineno_str),
            error_code=code,
        ))
    return violations


# ---------------------------------------------------------------------------
# Gate runner
# ---------------------------------------------------------------------------


class TypesGate:
    """Runs the static type-checking gate against a repository.

    Detects the appropriate checker (mypy or tsc) from the project layout,
    invokes it, parses the output, and enforces a **zero-error policy**:
    any *error*-severity violation causes the gate to fail.

    Parameters
    ----------
    config:
        Gate configuration.  When omitted, defaults are used
        (strict=False, auto-detect checker, fail on any error).

    Example::

        from pathlib import Path
        from harness_skills.gates.types import TypesGate
        from harness_skills.models.gate_configs import TypesGateConfig

        result = TypesGate(TypesGateConfig(strict=True)).run(Path("."))
        print(result)
    """

    def __init__(self, config: TypesGateConfig | None = None) -> None:
        self.config: TypesGateConfig = config or TypesGateConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, repo_root: Path) -> TypesGateResult:
        """Execute the gate against *repo_root* and return a
        :class:`TypesGateResult`.

        Parameters
        ----------
        repo_root:
            Absolute (or CWD-relative) path to the repository root.
        """
        repo_root = repo_root.resolve()
        cfg = self.config
        ignore_set = set(cfg.ignore_errors)

        checker = _detect_checker(repo_root, cfg.checker)

        if not checker:
            violation = TypeViolation(
                kind="no_source_detected",
                severity="warning",
                message=(
                    "Could not detect a supported type checker.  "
                    "Add a pyproject.toml (Python/mypy) or tsconfig.json "
                    "(TypeScript/tsc) to the project root, or set "
                    "checker: mypy|tsc|pyright in harness.config.yaml."
                ),
            )
            return TypesGateResult(
                passed=True,  # no checker → gate skipped gracefully
                violations=[violation],
                checker=None,
                stats={"skipped_reason": "no_source_detected"},
            )

        # Dispatch to the appropriate checker
        if checker == "mypy":
            return self._run_mypy(repo_root, ignore_set)
        elif checker == "tsc":
            return self._run_tsc(repo_root, ignore_set)
        elif checker == "pyright":
            return self._run_pyright(repo_root, ignore_set)
        else:
            violation = TypeViolation(
                kind="no_source_detected",
                severity="error" if cfg.fail_on_error else "warning",
                message=f"Unknown checker {checker!r}. Valid options: auto, mypy, tsc, pyright.",
            )
            return TypesGateResult(
                passed=not cfg.fail_on_error,
                violations=[violation],
                checker=checker,
            )

    # ------------------------------------------------------------------
    # Checker runners
    # ------------------------------------------------------------------

    def _run_mypy(self, repo_root: Path, ignore_set: set[str]) -> TypesGateResult:
        """Invoke mypy and return a :class:`TypesGateResult`."""
        cfg = self.config
        strict_args = ["--strict"] if cfg.strict else []
        disable_args: list[str] = []
        for code in cfg.ignore_errors:
            disable_args += ["--disable-error-code", code]

        cmd = [
            sys.executable, "-m", "mypy",
            "--show-error-codes",
            "--no-error-summary",
            *strict_args,
            *disable_args,
            *cfg.paths,
        ]
        try:
            proc = subprocess.run(
                cmd, cwd=repo_root, capture_output=True, text=True
            )
        except FileNotFoundError:
            return TypesGateResult(
                passed=not cfg.fail_on_error,
                violations=[TypeViolation(
                    kind="checker_not_found",
                    severity="error" if cfg.fail_on_error else "warning",
                    message=(
                        "mypy is not installed or not on PATH.  "
                        "Install it with: pip install mypy"
                    ),
                )],
                checker="mypy",
            )

        output = proc.stdout + proc.stderr
        violations = _parse_mypy_output(output, ignore_set, cfg.fail_on_error)
        return self._build_result("mypy", violations)

    def _run_tsc(self, repo_root: Path, ignore_set: set[str]) -> TypesGateResult:
        """Invoke the TypeScript compiler (tsc) and return a
        :class:`TypesGateResult`."""
        cfg = self.config
        # --pretty false gives machine-parseable output
        cmd = ["npx", "tsc", "--noEmit", "--pretty", "false"]
        try:
            proc = subprocess.run(
                cmd, cwd=repo_root, capture_output=True, text=True
            )
        except FileNotFoundError:
            return TypesGateResult(
                passed=not cfg.fail_on_error,
                violations=[TypeViolation(
                    kind="checker_not_found",
                    severity="error" if cfg.fail_on_error else "warning",
                    message=(
                        "npx / tsc is not installed.  "
                        "Install TypeScript with: npm install --save-dev typescript"
                    ),
                )],
                checker="tsc",
            )

        output = proc.stdout + proc.stderr
        violations = _parse_tsc_output(output, ignore_set, cfg.fail_on_error)
        return self._build_result("tsc", violations)

    def _run_pyright(self, repo_root: Path, ignore_set: set[str]) -> TypesGateResult:
        """Invoke pyright and return a :class:`TypesGateResult`."""
        cfg = self.config
        cmd = ["pyright", "--outputjson"]
        try:
            proc = subprocess.run(
                cmd, cwd=repo_root, capture_output=True, text=True
            )
        except FileNotFoundError:
            # Try via npx as a fallback
            try:
                proc = subprocess.run(
                    ["npx", "pyright", "--outputjson"],
                    cwd=repo_root, capture_output=True, text=True
                )
            except FileNotFoundError:
                return TypesGateResult(
                    passed=not cfg.fail_on_error,
                    violations=[TypeViolation(
                        kind="checker_not_found",
                        severity="error" if cfg.fail_on_error else "warning",
                        message=(
                            "pyright is not installed.  "
                            "Install it with: pip install pyright or npm install -g pyright"
                        ),
                    )],
                    checker="pyright",
                )

        # pyright --outputjson emits a JSON report; fall back to text parsing
        import json as _json
        violations: list[TypeViolation] = []
        try:
            data = _json.loads(proc.stdout)
            for diag in data.get("generalDiagnostics", []):
                level = diag.get("severity", "error")
                code = diag.get("rule")
                if code and code in ignore_set:
                    continue
                if level == "information":
                    sev: Severity = "note"
                elif level == "warning":
                    sev = "warning"
                else:
                    sev = "error" if cfg.fail_on_error else "warning"
                rng = diag.get("range", {}).get("start", {})
                fp_str = diag.get("file")
                violations.append(TypeViolation(
                    kind="type_error",
                    severity=sev,
                    message=diag.get("message", "").strip(),
                    file_path=Path(fp_str) if fp_str else None,
                    line_number=(rng.get("line", 0) + 1) if rng else None,
                    error_code=code,
                ))
        except _json.JSONDecodeError:
            # Fall back to text-mode parsing
            violations = _parse_pyright_output(
                proc.stdout + proc.stderr, ignore_set, cfg.fail_on_error
            )

        return self._build_result("pyright", violations)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_result(
        self, checker: str, violations: list[TypeViolation]
    ) -> TypesGateResult:
        """Assemble a :class:`TypesGateResult` from *violations*."""
        cfg = self.config
        error_count = sum(1 for v in violations if v.severity == "error")
        warning_count = sum(1 for v in violations if v.severity != "error")
        passed = (error_count == 0) or (not cfg.fail_on_error)
        return TypesGateResult(
            passed=passed,
            violations=violations,
            checker=checker,
            error_count=error_count,
            warning_count=warning_count,
            stats={
                "checker": checker,
                "error_count": error_count,
                "warning_count": warning_count,
            },
        )


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m harness_skills.gates.types",
        description=(
            "Type-safety gate — enforce zero type errors "
            "(mypy / tsc / pyright)."
        ),
    )
    p.add_argument(
        "--root",
        default=".",
        metavar="PATH",
        help="Repository root (default: current directory).",
    )
    p.add_argument(
        "--checker",
        choices=["auto", "mypy", "tsc", "pyright"],
        default="auto",
        help="Type checker to use (default: auto-detect from project layout).",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Enable strict mode (--strict for mypy, strict tsconfig for tsc).",
    )
    p.add_argument(
        "--ignore-error",
        action="append",
        dest="ignore_errors",
        default=[],
        metavar="CODE",
        help=(
            "Error code to suppress (repeatable).  "
            "E.g. --ignore-error import --ignore-error attr-defined"
        ),
    )
    p.add_argument(
        "--fail-on-error",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Exit non-zero when type errors are found (default: true). "
            "Use --no-fail-on-error to emit warnings and still pass."
        ),
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-violation output; only print the summary line.",
    )
    p.add_argument(
        "paths",
        nargs="*",
        default=["."],
        metavar="PATH",
        help="Paths to check (default: current directory).",
    )
    return p


def main(argv: list[str] | None = None) -> int:  # pragma: no cover
    """CLI entry-point; returns an exit code (0 = pass, 1 = fail, 2 = error)."""
    args = _build_parser().parse_args(argv)
    cfg = TypesGateConfig(
        checker=args.checker,
        strict=args.strict,
        ignore_errors=args.ignore_errors,
        fail_on_error=args.fail_on_error,
        paths=args.paths or ["."],
    )
    result = TypesGate(cfg).run(Path(args.root))

    if not args.quiet:
        print(result)

    return 0 if result.passed else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
