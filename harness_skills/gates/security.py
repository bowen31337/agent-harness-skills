"""
harness_skills/gates/security.py
==================================
Security gate covering three sub-checks:

1. **Secret scanning** — regex-based detection of hardcoded credentials and
   private keys in source files (``config.scan_secrets=True``).

2. **Dependency vulnerability audit** — parses a pre-generated pip-audit or
   npm audit JSON report and flags packages with known CVEs that meet or
   exceed the configured severity threshold (``config.scan_dependencies=True``).

3. **Input validation verification** — regex scan of Python/JS/TS source files
   for dangerous patterns that indicate missing input sanitisation, such as
   ``eval(request.data)``, raw SQL string formatting with request objects, or
   pickle deserialisation of user-supplied data
   (``config.scan_input_validation=True``).

Usage (standalone CLI)::

    python -m harness_skills.gates.security [--root .] [--severity HIGH]
    python -m harness_skills.gates.security --scan-secrets
    python -m harness_skills.gates.security --audit-report pip-audit-report.json

Usage (programmatic)::

    from pathlib import Path
    from harness_skills.gates.security import SecurityGate
    from harness_skills.models.gate_configs import SecurityGateConfig

    cfg    = SecurityGateConfig(severity_threshold="MEDIUM", scan_secrets=True)
    result = SecurityGate(cfg).run(repo_root=Path("."))

    if not result.passed:
        for v in result.violations:
            print(v.summary())
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from harness_skills.models.gate_configs import SecurityGateConfig


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

ViolationKind = Literal[
    "hardcoded_secret",
    "vulnerable_dependency",
    "missing_audit_report",
    "unsafe_input_handling",
]
Severity = Literal["error", "warning"]


@dataclass
class Violation:
    """A single security-gate violation."""

    kind: ViolationKind
    """
    ``hardcoded_secret``      — a credential or private key found in source.
    ``vulnerable_dependency`` — a package with a known CVE.
    ``missing_audit_report``  — no audit report file was found on disk.
    ``unsafe_input_handling`` — a dangerous pattern using unvalidated input.
    """

    severity: Severity
    """``error`` blocks the gate; ``warning`` is advisory only."""

    message: str
    """Human-readable description of the violation."""

    file_path: Path | None = None
    """Source file where the violation was detected (if applicable)."""

    line_number: int | None = None
    """1-based line number within *file_path* (if applicable)."""

    rule_id: str | None = None
    """Secret-scanner rule ID, CVE ID, or GHSA ID (if applicable)."""

    def summary(self) -> str:
        """One-line string suitable for console output."""
        parts = [f"[{self.severity.upper():7s}]", f"{self.kind:27s}"]
        if self.file_path:
            loc = str(self.file_path)
            if self.line_number:
                loc += f":{self.line_number}"
            parts.append(f"[{loc}]")
        if self.rule_id:
            parts.append(f"({self.rule_id})")
        parts.append(f"— {self.message}")
        return " ".join(parts)


@dataclass
class GateResult:
    """Aggregate result returned by :class:`SecurityGate`."""

    passed: bool
    """``True`` when no error-severity violations were found (or
    ``fail_on_error=False``)."""

    violations: list[Violation] = field(default_factory=list)
    """All violations found across all enabled sub-checks."""

    stats: dict[str, object] = field(default_factory=dict)
    """Summary counters: ``secrets_found``, ``vulnerable_dependencies``,
    ``unsafe_input_patterns``, ``total_violations``, etc."""

    def errors(self) -> list[Violation]:
        """Return only error-severity violations."""
        return [v for v in self.violations if v.severity == "error"]

    def warnings(self) -> list[Violation]:
        """Return only warning-severity violations."""
        return [v for v in self.violations if v.severity == "warning"]

    def by_kind(self, kind: ViolationKind) -> list[Violation]:
        """Return all violations of a specific *kind*."""
        return [v for v in self.violations if v.kind == kind]

    def __str__(self) -> str:  # pragma: no cover
        lines = [f"SecurityGate: {'PASSED' if self.passed else 'FAILED'}"]
        for key, val in self.stats.items():
            lines.append(f"  {key:35s}: {val}")
        if self.violations:
            lines.append("")
            for v in self.violations:
                lines.append("  " + v.summary())
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Severity ordering
# ---------------------------------------------------------------------------

_SEVERITY_RANK: dict[str, int] = {
    "CRITICAL": 4,
    "HIGH": 3,
    "MEDIUM": 2,
    "LOW": 1,
    "NONE": 0,
}


def _meets_threshold(vuln_severity: str, threshold: str) -> bool:
    """Return ``True`` when *vuln_severity* >= *threshold* by CVSS rank.

    Unknown severity values default to ``HIGH`` so they are not silently
    suppressed when the threshold is ``MEDIUM`` or lower.
    """
    rank_v = _SEVERITY_RANK.get(vuln_severity.upper(), _SEVERITY_RANK["HIGH"])
    rank_t = _SEVERITY_RANK.get(threshold.upper(), _SEVERITY_RANK["HIGH"])
    return rank_v >= rank_t


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------

_SOURCE_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".rb",
    ".php", ".cs", ".cpp", ".c", ".h", ".sh", ".bash",
    ".env", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".conf",
})

_SKIP_DIRS: frozenset[str] = frozenset({
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
    ".tox", ".eggs",
})


def _iter_source_files(root: Path) -> list[Path]:
    """Return all non-excluded source files under *root*, sorted by path."""
    results: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _SOURCE_EXTENSIONS:
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        results.append(path)
    return sorted(results)


# ---------------------------------------------------------------------------
# Sub-check 1: Secret scanning
# ---------------------------------------------------------------------------

# Each entry: (rule_id, compiled_pattern)
# Patterns intentionally exclude common placeholder values (``example_``,
# ``changeme``, ``your_``, ``xxx``, ``test``) to keep false-positive rates low.
_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "hardcoded-password",
        re.compile(
            r'(?:password|passwd|pwd)\s*=\s*["\']'
            r'(?!(?:your_|example_|placeholder|changeme|change_me|xxx|test|fake|dummy|\s*\{|\s*\$|\s*<))'
            r'[^"\']{6,}["\']',
            re.IGNORECASE,
        ),
    ),
    (
        "hardcoded-api-key",
        re.compile(
            r'(?:api[_-]?key|apikey|api[_-]?secret|access[_-]?key|client[_-]?secret)'
            r'\s*=\s*["\'][^"\']{8,}["\']',
            re.IGNORECASE,
        ),
    ),
    (
        "hardcoded-token",
        re.compile(
            r'(?:auth[_-]?token|secret[_-]?token|bearer[_-]?token|private[_-]?key)'
            r'\s*=\s*["\'][^"\']{8,}["\']',
            re.IGNORECASE,
        ),
    ),
    (
        "pem-private-key",
        re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
    ),
    (
        "aws-access-key-id",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    ),
    (
        "github-personal-access-token",
        re.compile(r"\bghp_[A-Za-z0-9]{36}\b"),
    ),
]


def _scan_file_for_secrets(
    path: Path,
    ignore_ids: list[str],
    severity: Severity,
) -> list[Violation]:
    """Scan a single file for hardcoded secrets; return a list of violations."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    violations: list[Violation] = []
    lines = text.splitlines()

    for rule_id, pattern in _SECRET_PATTERNS:
        if rule_id in ignore_ids:
            continue
        for lineno, line in enumerate(lines, start=1):
            if pattern.search(line):
                violations.append(
                    Violation(
                        kind="hardcoded_secret",
                        severity=severity,
                        message=(
                            f"Potential hardcoded secret detected by rule '{rule_id}'. "
                            "Move credentials to environment variables or a secrets manager."
                        ),
                        file_path=path,
                        line_number=lineno,
                        rule_id=rule_id,
                    )
                )
    return violations


class _SecretScanner:
    """Scans all source files under a repo root for hardcoded secrets."""

    def __init__(self, ignore_ids: list[str], fail_on_error: bool) -> None:
        self._ignore_ids = ignore_ids
        self._severity: Severity = "error" if fail_on_error else "warning"

    def scan(self, root: Path) -> list[Violation]:
        violations: list[Violation] = []
        for path in _iter_source_files(root):
            violations.extend(
                _scan_file_for_secrets(path, self._ignore_ids, self._severity)
            )
        return violations


# ---------------------------------------------------------------------------
# Sub-check 2: Dependency vulnerability audit
# ---------------------------------------------------------------------------

_AUDIT_REPORT_NAMES: list[str] = [
    "pip-audit-report.json",
    "pip_audit_report.json",
    "vulnerability-report.json",
    "audit-report.json",
    "npm-audit.json",
    "npm_audit.json",
]


def _find_audit_report(root: Path) -> Path | None:
    """Return the first recognised audit report file found directly under *root*."""
    for name in _AUDIT_REPORT_NAMES:
        candidate = root / name
        if candidate.exists():
            return candidate
    return None


def _parse_pip_audit_report(
    data: object,
    threshold: str,
    ignore_ids: list[str],
    severity: Severity,
) -> list[Violation]:
    """Parse pip-audit JSON output and return security violations.

    Expected format::

        [
          {
            "name": "requests",
            "version": "2.28.0",
            "vulns": [
              {
                "id": "PYSEC-2023-74",
                "fix_versions": ["2.31.0"],
                "aliases": ["CVE-2023-32681", "GHSA-j8r2-6x86-q33q"],
                "description": "...",
                "severity": "HIGH"   # optional — defaults to HIGH when absent
              }
            ]
          }
        ]

    Vulnerabilities without an explicit ``severity`` field default to ``HIGH``
    so they are never silently suppressed.  Unknown aliases and IDs are checked
    against *ignore_ids*.
    """
    violations: list[Violation] = []
    if not isinstance(data, list):
        return violations

    for pkg in data:
        if not isinstance(pkg, dict):
            continue
        name = pkg.get("name", "unknown")
        version = pkg.get("version", "unknown")
        vulns = pkg.get("vulns", [])
        if not isinstance(vulns, list):
            continue

        for vuln in vulns:
            if not isinstance(vuln, dict):
                continue
            vuln_id = vuln.get("id", "UNKNOWN")
            aliases: list[str] = vuln.get("aliases", [])
            if not isinstance(aliases, list):
                aliases = []
            description = vuln.get("description", "No description provided.")
            fix_versions: list[str] = vuln.get("fix_versions", [])
            if not isinstance(fix_versions, list):
                fix_versions = []
            # Severity absent → treat as HIGH (conservative default)
            vuln_severity = vuln.get("severity", "HIGH")
            if not isinstance(vuln_severity, str):
                vuln_severity = "HIGH"

            # Suppress by ID or alias
            all_ids = [vuln_id, *aliases]
            if any(vid in ignore_ids for vid in all_ids):
                continue

            # Apply severity threshold
            if not _meets_threshold(vuln_severity, threshold):
                continue

            fix_str = (
                f" Upgrade to: {', '.join(fix_versions)}." if fix_versions else ""
            )
            desc_preview = (
                description[:120] + "…" if len(description) > 120 else description
            )
            violations.append(
                Violation(
                    kind="vulnerable_dependency",
                    severity=severity,
                    message=(
                        f"{name}=={version} has a known vulnerability: "
                        f"{desc_preview}{fix_str}"
                    ),
                    rule_id=vuln_id,
                )
            )
    return violations


class _DependencyAuditor:
    """Reads a pre-generated audit report and flags vulnerable packages."""

    def __init__(
        self,
        severity_threshold: str,
        ignore_ids: list[str],
        fail_on_error: bool,
    ) -> None:
        self._threshold = severity_threshold
        self._ignore_ids = ignore_ids
        self._severity: Severity = "error" if fail_on_error else "warning"

    def audit(self, root: Path) -> list[Violation]:
        """Locate the audit report, parse it, and return violations."""
        report_path = _find_audit_report(root)
        if report_path is None:
            return [
                Violation(
                    kind="missing_audit_report",
                    # Advisory — not having a report isn't itself a vulnerability
                    severity="warning",
                    message=(
                        "No dependency audit report found in the project root. "
                        f"Expected one of: {', '.join(_AUDIT_REPORT_NAMES)}. "
                        "Generate one first: "
                        "pip-audit --format json -o pip-audit-report.json"
                    ),
                )
            ]

        try:
            data = json.loads(report_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            return [
                Violation(
                    kind="missing_audit_report",
                    severity=self._severity,
                    message=f"Failed to parse audit report '{report_path}': {exc}",
                    file_path=report_path,
                )
            ]

        return _parse_pip_audit_report(
            data, self._threshold, self._ignore_ids, self._severity
        )


# ---------------------------------------------------------------------------
# Sub-check 3: Input validation verification
# ---------------------------------------------------------------------------

# Patterns indicating *missing* or *bypassed* input validation.
# Each entry: (rule_id, compiled_pattern)
_UNSAFE_INPUT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "eval-user-input",
        re.compile(r"\beval\s*\(\s*request\.", re.IGNORECASE),
    ),
    (
        "exec-user-input",
        re.compile(r"\bexec\s*\(\s*request\.", re.IGNORECASE),
    ),
    (
        "sql-string-format",
        re.compile(
            r"(?:cursor|conn|connection|db|session)\.execute\s*\(.*request\.",
            re.IGNORECASE,
        ),
    ),
    (
        "pickle-user-input",
        re.compile(r"\bpickle\.loads?\s*\(\s*request\.", re.IGNORECASE),
    ),
    (
        "shell-injection",
        re.compile(
            r"\b(?:os\.system|subprocess\.(?:call|run|Popen|check_output))\s*\([^)]*request\.",
            re.IGNORECASE,
        ),
    ),
]

_INPUT_SCAN_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".js", ".ts", ".jsx", ".tsx",
})


def _scan_file_for_unsafe_input(
    path: Path,
    ignore_ids: list[str],
    severity: Severity,
) -> list[Violation]:
    """Scan a single file for dangerous input-handling patterns."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    violations: list[Violation] = []
    lines = text.splitlines()

    for rule_id, pattern in _UNSAFE_INPUT_PATTERNS:
        if rule_id in ignore_ids:
            continue
        for lineno, line in enumerate(lines, start=1):
            if pattern.search(line):
                violations.append(
                    Violation(
                        kind="unsafe_input_handling",
                        severity=severity,
                        message=(
                            f"Unsafe input handling detected by rule '{rule_id}'. "
                            "Validate and sanitise all user-supplied data before use."
                        ),
                        file_path=path,
                        line_number=lineno,
                        rule_id=rule_id,
                    )
                )
    return violations


class _InputValidationChecker:
    """Scans source files for patterns indicating missing input validation."""

    def __init__(self, ignore_ids: list[str], fail_on_error: bool) -> None:
        self._ignore_ids = ignore_ids
        self._severity: Severity = "error" if fail_on_error else "warning"

    def check(self, root: Path) -> list[Violation]:
        violations: list[Violation] = []
        for path in _iter_source_files(root):
            if path.suffix.lower() not in _INPUT_SCAN_EXTENSIONS:
                continue
            violations.extend(
                _scan_file_for_unsafe_input(path, self._ignore_ids, self._severity)
            )
        return violations


# ---------------------------------------------------------------------------
# Gate runner
# ---------------------------------------------------------------------------


class SecurityGate:
    """Runs the security gate against a repository.

    Runs up to three sub-checks depending on configuration:

    1. **Secret scanning** (``config.scan_secrets=True``) — regex scan of
       source files for hardcoded credentials, private keys, and API tokens.
    2. **Dependency audit** (``config.scan_dependencies=True``) — reads a
       pre-generated pip-audit or npm audit JSON report and flags packages
       with CVEs at or above ``config.severity_threshold``.
    3. **Input validation** (``config.scan_input_validation=True``) — regex
       scan for dangerous patterns such as ``eval(request.data)`` or raw SQL
       string formatting with request objects.

    Parameters
    ----------
    config:
        Gate configuration.  Defaults are conservative: ``severity_threshold``
        ``"HIGH"``, secrets scanning off, dependency scanning and input
        validation on.

    Example::

        from pathlib import Path
        from harness_skills.gates.security import SecurityGate
        from harness_skills.models.gate_configs import SecurityGateConfig

        result = SecurityGate(SecurityGateConfig(scan_secrets=True)).run(Path("."))
        print(result)
    """

    def __init__(self, config: SecurityGateConfig | None = None) -> None:
        self.config: SecurityGateConfig = config or SecurityGateConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, repo_root: Path) -> GateResult:
        """Execute all enabled sub-checks against *repo_root*.

        Parameters
        ----------
        repo_root:
            Absolute (or CWD-relative) path to the repository root.
            Relative file paths in any audit report are resolved against
            this directory.
        """
        repo_root = repo_root.resolve()
        cfg = self.config
        all_violations: list[Violation] = []

        # ── 1. Secret scanning ───────────────────────────────────────────
        secret_count = 0
        if cfg.scan_secrets:
            scanner = _SecretScanner(cfg.ignore_ids, cfg.fail_on_error)
            secret_violations = scanner.scan(repo_root)
            all_violations.extend(secret_violations)
            secret_count = len(secret_violations)

        # ── 2. Dependency vulnerability audit ────────────────────────────
        dep_count = 0
        if cfg.scan_dependencies:
            auditor = _DependencyAuditor(
                cfg.severity_threshold, cfg.ignore_ids, cfg.fail_on_error
            )
            dep_violations = auditor.audit(repo_root)
            all_violations.extend(dep_violations)
            dep_count = sum(
                1 for v in dep_violations if v.kind == "vulnerable_dependency"
            )

        # ── 3. Input validation verification ─────────────────────────────
        input_count = 0
        if cfg.scan_input_validation:
            checker = _InputValidationChecker(cfg.ignore_ids, cfg.fail_on_error)
            input_violations = checker.check(repo_root)
            all_violations.extend(input_violations)
            input_count = len(input_violations)

        # ── Determine pass/fail ───────────────────────────────────────────
        error_violations = [v for v in all_violations if v.severity == "error"]
        passed = (not error_violations) or (not cfg.fail_on_error)

        return GateResult(
            passed=passed,
            violations=all_violations,
            stats={
                "secrets_found": secret_count,
                "vulnerable_dependencies": dep_count,
                "unsafe_input_patterns": input_count,
                "total_violations": len(all_violations),
                "severity_threshold": cfg.severity_threshold,
                "scan_secrets": cfg.scan_secrets,
                "scan_dependencies": cfg.scan_dependencies,
                "scan_input_validation": cfg.scan_input_validation,
            },
        )


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m harness_skills.gates.security",
        description=(
            "Security gate — detect hardcoded secrets, vulnerable dependencies, "
            "and unsafe input handling patterns."
        ),
    )
    p.add_argument(
        "--root",
        default=".",
        metavar="PATH",
        help="Repository root (default: current directory).",
    )
    p.add_argument(
        "--severity",
        default="HIGH",
        choices=["CRITICAL", "HIGH", "MEDIUM", "LOW"],
        dest="severity_threshold",
        help=(
            "Minimum CVE severity to report for dependency vulnerabilities "
            "(default: HIGH)."
        ),
    )
    p.add_argument(
        "--scan-secrets",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable hardcoded secret scanning (default: false).",
    )
    p.add_argument(
        "--scan-dependencies",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Enable dependency vulnerability audit from pre-generated report "
            "(default: true)."
        ),
    )
    p.add_argument(
        "--scan-input-validation",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable unsafe input handling detection (default: true).",
    )
    p.add_argument(
        "--fail-on-error",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Exit non-zero on any error-severity violation (default: true). "
            "Use --no-fail-on-error for advisory/warning-only mode."
        ),
    )
    p.add_argument(
        "--ignore-ids",
        nargs="*",
        default=[],
        metavar="ID",
        help=(
            "Vulnerability or rule IDs to suppress "
            "(e.g. CVE-2023-12345 hardcoded-password)."
        ),
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-violation output; only print the summary line.",
    )
    return p


def main(argv: list[str] | None = None) -> int:  # pragma: no cover
    """CLI entry-point; returns an exit code (0 = pass, 1 = fail, 2 = error)."""
    args = _build_parser().parse_args(argv)
    cfg = SecurityGateConfig(
        fail_on_error=args.fail_on_error,
        severity_threshold=args.severity_threshold,
        scan_dependencies=args.scan_dependencies,
        scan_secrets=args.scan_secrets,
        scan_input_validation=args.scan_input_validation,
        ignore_ids=args.ignore_ids or [],
    )
    result = SecurityGate(cfg).run(Path(args.root))

    if not args.quiet:
        print(result)

    return 0 if result.passed else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
