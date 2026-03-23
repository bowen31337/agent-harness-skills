"""
harness_skills/gates/file_size.py
====================================
File-size gate implementation.

Scans source files in the repository and blocks the build when any file's
line count exceeds a configurable **hard limit** (``max_lines``).  A
**soft limit** (``warn_lines``) produces advisory warnings for files that are
growing towards the hard cap but have not yet crossed it.

The gate is designed to prevent monolithic files — large single files are
notoriously hard for both human reviewers and AI agents to reason about.
Enforcing a size cap encourages incremental refactoring into smaller,
well-scoped modules.

Threshold rationale (defaults)
-------------------------------
* **300 lines** (warn)  — files above this size benefit from review.
* **500 lines** (error) — above this size, splitting is almost always
  worth the effort for long-term maintainability.

Both thresholds are fully configurable via :class:`~harness_skills.models.\
gate_configs.FileSizeGateConfig`.

Usage (standalone CLI)::

    python -m harness_skills.gates.file_size [--root .] [--max-lines 500]
    python -m harness_skills.gates.file_size --max-lines 400 --warn-lines 250
    python -m harness_skills.gates.file_size --report-only          # never fail

Usage (programmatic)::

    from pathlib import Path
    from harness_skills.gates.file_size import FileSizeGate
    from harness_skills.models.gate_configs import FileSizeGateConfig

    cfg    = FileSizeGateConfig(max_lines=400, warn_lines=250)
    result = FileSizeGate(cfg).run(repo_root=Path("."))

    if not result.passed:
        for v in result.violations:
            print(v.summary())
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from harness_skills.models.gate_configs import FileSizeGateConfig


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

ViolationKind = Literal["exceeds_hard_limit", "exceeds_soft_limit"]
Severity = Literal["error", "warning"]


@dataclass
class Violation:
    """A single file-size gate violation."""

    kind: ViolationKind
    """
    ``exceeds_hard_limit`` — file line count is above ``max_lines``.
    ``exceeds_soft_limit`` — file line count is above ``warn_lines`` but
                             still within ``max_lines``.
    """

    severity: Severity
    """``error`` blocks the gate; ``warning`` is advisory only."""

    message: str
    """Human-readable description of the violation."""

    file_path: Path
    """Repository-relative path to the offending file."""

    line_count: int
    """Actual number of lines in the file."""

    limit: int
    """The threshold that was exceeded (``max_lines`` or ``warn_lines``)."""

    def summary(self) -> str:
        """One-line string suitable for console output."""
        return (
            f"[{self.severity.upper():7s}] {self.kind:20s}"
            f" {self.file_path} — {self.line_count} lines"
            f" (limit: {self.limit})"
        )


@dataclass
class GateResult:
    """Aggregate result returned by :class:`FileSizeGate`."""

    passed: bool
    """``True`` when no hard-limit violations were found (or
    ``fail_on_error=False`` / ``report_only=True``)."""

    violations: list[Violation] = field(default_factory=list)
    """All violations found, sorted by line count descending."""

    files_scanned: int = 0
    """Total number of source files examined."""

    max_lines: int = 500
    """Hard limit used for this run."""

    warn_lines: int = 300
    """Soft limit used for this run."""

    stats: dict[str, object] = field(default_factory=dict)
    """Extra metrics: ``files_scanned``, ``errors``, ``warnings``,
    ``largest_file``, ``largest_file_lines``."""

    def errors(self) -> list[Violation]:
        """Return only error-severity violations."""
        return [v for v in self.violations if v.severity == "error"]

    def warnings(self) -> list[Violation]:
        """Return only warning-severity violations."""
        return [v for v in self.violations if v.severity == "warning"]

    def __str__(self) -> str:  # pragma: no cover
        lines = [
            f"FileSizeGate: {'PASSED' if self.passed else 'FAILED'}",
            f"  Files scanned : {self.files_scanned}",
            f"  Hard limit    : {self.max_lines} lines",
            f"  Soft limit    : {self.warn_lines} lines",
            f"  Errors        : {len(self.errors())}",
            f"  Warnings      : {len(self.warnings())}",
        ]
        if self.violations:
            lines.append("")
            for v in self.violations:
                lines.append("  " + v.summary())
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _matches_any(path_str: str, patterns: list[str]) -> bool:
    """Return ``True`` if *path_str* matches at least one glob in *patterns*.

    Both the full path and the basename are tested so that patterns like
    ``"*.min.js"`` work without requiring a full-path glob.
    """
    basename = Path(path_str).name
    for pat in patterns:
        if fnmatch.fnmatch(path_str, pat):
            return True
        if fnmatch.fnmatch(basename, pat):
            return True
    return False


def _collect_files(
    repo_root: Path,
    include_patterns: list[str],
    exclude_patterns: list[str],
) -> list[Path]:
    """Enumerate source files under *repo_root* that pass the include/exclude filters.

    Parameters
    ----------
    repo_root:
        Absolute path to the repository root.
    include_patterns:
        Glob patterns for files to include (relative to *repo_root*).
    exclude_patterns:
        Glob patterns for paths to skip (matched against relative path strings).

    Returns
    -------
    list[Path]
        Absolute paths to candidate files, sorted for deterministic output.
    """
    candidates: set[Path] = set()

    for pattern in include_patterns:
        for match in repo_root.glob(pattern):
            if match.is_file():
                candidates.add(match)

    result: list[Path] = []
    for path in sorted(candidates):
        rel = path.relative_to(repo_root).as_posix()
        if not _matches_any(rel, exclude_patterns):
            result.append(path)

    return result


def _count_lines(path: Path) -> int:
    """Count the number of lines in *path*.

    Uses a binary read with newline counting to avoid encoding errors on
    files with mixed or unknown encodings.

    Parameters
    ----------
    path:
        Absolute path to the file to count.

    Returns
    -------
    int
        Number of newline characters in the file, which corresponds to the
        number of lines as reported by most text editors and ``wc -l``.
        An empty file or a single line without a trailing newline returns 1
        (matching the visual line count in most editors).
    """
    try:
        data = path.read_bytes()
    except OSError:
        return 0

    if not data:
        return 0

    count = data.count(b"\n")
    # If the last byte is not a newline the final line is still a real line
    if data[-1:] != b"\n":
        count += 1
    return count


# ---------------------------------------------------------------------------
# Gate runner
# ---------------------------------------------------------------------------


class FileSizeGate:
    """Scans source files and enforces configurable line-count thresholds.

    Parameters
    ----------
    config:
        Gate configuration.  When omitted, defaults are used
        (``max_lines=500``, ``warn_lines=300``).

    Example::

        from pathlib import Path
        from harness_skills.gates.file_size import FileSizeGate
        from harness_skills.models.gate_configs import FileSizeGateConfig

        result = FileSizeGate(FileSizeGateConfig(max_lines=400)).run(Path("."))
        print(result)
    """

    def __init__(self, config: FileSizeGateConfig | None = None) -> None:
        self.config: FileSizeGateConfig = config or FileSizeGateConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, repo_root: Path) -> GateResult:
        """Execute the gate against *repo_root* and return a :class:`GateResult`.

        Parameters
        ----------
        repo_root:
            Absolute (or CWD-relative) path to the repository root.
            All include/exclude glob patterns are applied relative to this
            directory.
        """
        repo_root = repo_root.resolve()
        cfg = self.config

        # ── 1. Collect candidate files ──────────────────────────────────
        files = _collect_files(
            repo_root,
            include_patterns=cfg.include_patterns,
            exclude_patterns=cfg.exclude_patterns,
        )

        # ── 2. Count lines and build violations ─────────────────────────
        violations: list[Violation] = []
        largest_file: str = ""
        largest_lines: int = 0

        for path in files:
            line_count = _count_lines(path)
            rel_path = path.relative_to(repo_root)

            if line_count > largest_lines:
                largest_lines = line_count
                largest_file = rel_path.as_posix()

            if line_count > cfg.max_lines:
                # Determine effective severity: report_only downgrades errors
                # to warnings; fail_on_error controls whether warnings block.
                severity: Severity = (
                    "warning" if cfg.report_only else "error"
                )
                overrun = line_count - cfg.max_lines
                violations.append(
                    Violation(
                        kind="exceeds_hard_limit",
                        severity=severity,
                        message=(
                            f"{rel_path} has {line_count} lines "
                            f"({overrun} over the {cfg.max_lines}-line hard limit). "
                            "Consider splitting into smaller, focused modules."
                        ),
                        file_path=rel_path,
                        line_count=line_count,
                        limit=cfg.max_lines,
                    )
                )
            elif cfg.warn_lines > 0 and line_count > cfg.warn_lines:
                headroom = cfg.max_lines - line_count
                violations.append(
                    Violation(
                        kind="exceeds_soft_limit",
                        severity="warning",
                        message=(
                            f"{rel_path} has {line_count} lines "
                            f"({line_count - cfg.warn_lines} over the "
                            f"{cfg.warn_lines}-line soft limit, "
                            f"{headroom} lines before the hard cap). "
                            "Plan to split before it crosses the hard limit."
                        ),
                        file_path=rel_path,
                        line_count=line_count,
                        limit=cfg.warn_lines,
                    )
                )

        # Sort violations: errors first, then by line count descending
        violations.sort(
            key=lambda v: (0 if v.severity == "error" else 1, -v.line_count)
        )

        # ── 3. Determine pass/fail ───────────────────────────────────────
        has_errors = any(v.severity == "error" for v in violations)
        # Gate fails only when there are error-severity violations AND
        # fail_on_error=True AND report_only=False
        passed = not has_errors or not cfg.fail_on_error

        return GateResult(
            passed=passed,
            violations=violations,
            files_scanned=len(files),
            max_lines=cfg.max_lines,
            warn_lines=cfg.warn_lines,
            stats={
                "files_scanned": len(files),
                "errors": sum(1 for v in violations if v.severity == "error"),
                "warnings": sum(1 for v in violations if v.severity == "warning"),
                "largest_file": largest_file,
                "largest_file_lines": largest_lines,
            },
        )


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m harness_skills.gates.file_size",
        description=(
            "File-size gate — enforce per-file line-count limits "
            "to prevent monolithic files that confuse agents and reviewers."
        ),
    )
    p.add_argument(
        "--root",
        default=".",
        metavar="PATH",
        help="Repository root (default: current directory).",
    )
    p.add_argument(
        "--max-lines",
        type=int,
        default=500,
        metavar="N",
        help=(
            "Hard limit: files with more than N lines produce an error "
            "(default: 500)."
        ),
    )
    p.add_argument(
        "--warn-lines",
        type=int,
        default=300,
        metavar="N",
        help=(
            "Soft limit: files with more than N lines produce a warning "
            "(default: 300). Set to 0 to disable."
        ),
    )
    p.add_argument(
        "--report-only",
        action="store_true",
        default=False,
        help=(
            "Downgrade all violations to warnings — the gate never exits "
            "non-zero. Useful for onboarding existing large codebases."
        ),
    )
    p.add_argument(
        "--fail-on-error",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Exit non-zero when hard-limit violations are found (default: true). "
            "Use --no-fail-on-error for advisory-only mode."
        ),
    )
    p.add_argument(
        "--include",
        dest="include_patterns",
        action="append",
        metavar="GLOB",
        default=None,
        help=(
            "Glob pattern for files to scan (repeatable). "
            "Overrides the built-in default pattern list when provided at "
            "least once."
        ),
    )
    p.add_argument(
        "--exclude",
        dest="exclude_patterns",
        action="append",
        metavar="GLOB",
        default=None,
        help=(
            "Extra glob pattern to exclude (repeatable). "
            "Appended to the built-in exclusion list."
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

    # Build config, allowing CLI --include to override defaults entirely
    base_cfg = FileSizeGateConfig()
    include = args.include_patterns if args.include_patterns else base_cfg.include_patterns
    exclude = base_cfg.exclude_patterns + (args.exclude_patterns or [])

    cfg = FileSizeGateConfig(
        max_lines=args.max_lines,
        warn_lines=args.warn_lines,
        report_only=args.report_only,
        fail_on_error=args.fail_on_error,
        include_patterns=include,
        exclude_patterns=exclude,
    )

    result = FileSizeGate(cfg).run(Path(args.root))

    if not args.quiet:
        print(result)

    return 0 if result.passed else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
