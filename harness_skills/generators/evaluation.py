"""
Evaluation gate runner and gate failure report formatter.

Produces structured JSON output conforming to
harness_skills/schemas/evaluation_report.schema.json so that agents can parse
failures and iterate on specific issues without human intervention.

## Tools / callables exposed

    run_all_gates(project_root, config)  →  EvaluationReport
    run_gate(gate_id, project_root, config)  →  GateResult
    format_report(report)  →  str   (JSON, --format json)

## Architecture

    GateRunner (ABC)
        ├── RegressionGate   – pytest invocation, parses junit XML
        ├── CoverageGate     – coverage.py / jest --coverage, checks threshold
        ├── SecurityGate     – pip-audit / npm audit / bandit
        ├── PerformanceGate  – timing assertions from harness config
        ├── ArchitectureGate – import layer violations via AST
        ├── PrinciplesGate   – PRINCIPLES.md rule scanner
        ├── DocsFreshnessGate– staleness scores for generated artifacts
        ├── TypesGate        – mypy / tsc --noEmit / pyright
        └── LintGate         – ruff / eslint / golangci-lint

    GateOrchestrator.run(gates, project_root, config)
        runs gates in sequence, collects GateResults, builds EvaluationReport

## Usage — standalone

    from harness_skills.generators.evaluation import run_all_gates, GateConfig

    report = run_all_gates("/path/to/project", config=GateConfig())
    print(report.model_dump_json(indent=2))
    if not report.passed:
        for failure in report.failures:
            print(failure.suggestion)

## Usage — from another agent / skill

    from harness_skills.generators.evaluation import run_gate, GateId

    result = run_gate(GateId.COVERAGE, project_root=".", config=GateConfig(coverage_threshold=90))
    for f in result.failures:
        # severity, gate_id, file_path, line_number, suggestion are always present
        agent_act_on(f)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class Severity(str, Enum):
    """How blocking a failure is.

    error   – blocks the PR; agent must fix before opening.
    warning – advisory; agent should note but PR can proceed.
    info    – purely informational; no action required.
    """

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class GateId(str, Enum):
    """Stable identifiers for every built-in evaluation gate."""

    REGRESSION = "regression"
    COVERAGE = "coverage"
    SECURITY = "security"
    PERFORMANCE = "performance"
    ARCHITECTURE = "architecture"
    PRINCIPLES = "principles"
    DOCS_FRESHNESS = "docs_freshness"
    TYPES = "types"
    LINT = "lint"


class GateStatus(str, Enum):
    """Outcome of a single gate run."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"  # gate itself threw an exception


# ---------------------------------------------------------------------------
# Core data models
# ---------------------------------------------------------------------------


class GateFailure(BaseModel):
    """A single actionable violation produced by a gate.

    Every field agents need to locate, understand, and fix the issue is
    present without requiring further tool calls (G1 — structured over
    free-form; G4 — agent-driven context assembly).

    Required fields: severity, gate_id, message.
    Optional but strongly recommended: file_path, line_number, suggestion.
    """

    severity: Severity = Field(
        ...,
        description="How blocking: error blocks PR, warning is advisory, info is informational.",
    )
    gate_id: GateId = Field(..., description="Which gate produced this failure.")
    message: str = Field(..., description="Human- and agent-readable description of what failed.")
    file_path: Optional[str] = Field(
        None,
        description="Repo-relative path to the offending file, or None when not file-specific.",
    )
    line_number: Optional[int] = Field(
        None,
        ge=1,
        description="1-based line number in file_path, or None when not applicable.",
    )
    suggestion: Optional[str] = Field(
        None,
        description=(
            "Concrete, agent-actionable fix suggestion. "
            "Specific enough that an agent can act without human help in >90% of cases."
        ),
    )
    rule_id: Optional[str] = Field(
        None,
        description="Optional linter/checker rule ID (e.g. 'E501', 'no-unused-vars').",
    )
    context: Optional[str] = Field(
        None,
        description="Optional short code snippet or diff excerpt for additional context.",
    )


class GateResult(BaseModel):
    """Result for a single gate.

    Progressive disclosure (G2): read status first; drill into failures only
    when the gate failed.
    """

    gate_id: GateId
    status: GateStatus
    duration_ms: Optional[int] = Field(None, ge=0)
    failures: list[GateFailure] = Field(default_factory=list)
    failure_count: int = Field(0, ge=0)
    message: Optional[str] = Field(None, description="Short human-readable gate summary.")

    @model_validator(mode="after")
    def _sync_failure_count(self) -> "GateResult":
        self.failure_count = len(self.failures)
        return self


class EvaluationSummary(BaseModel):
    """Top-level counts for quick agent assessment without loading every failure."""

    total_gates: int = Field(0, ge=0)
    passed_gates: int = Field(0, ge=0)
    failed_gates: int = Field(0, ge=0)
    skipped_gates: int = Field(0, ge=0)
    error_gates: int = Field(0, ge=0)
    total_failures: int = Field(0, ge=0, description="All GateFailure objects (all severities).")
    blocking_failures: int = Field(
        0,
        ge=0,
        description="GateFailures with severity=error — must fix before opening PR.",
    )


class ReportMetadata(BaseModel):
    """Provenance for staleness detection and telemetry (G3 — tool lifecycle)."""

    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    schema_version: str = "1.0"
    harness_version: Optional[str] = None
    project_root: Optional[str] = None
    git_sha: Optional[str] = None
    git_branch: Optional[str] = None


class EvaluationReport(BaseModel):
    """Structured output from harness evaluate.

    Conforms to harness_skills/schemas/evaluation_report.schema.json.
    Agents should:
      1. Check `passed` — if True, open the PR.
      2. If False, read `summary.blocking_failures` to assess scope.
      3. Iterate over `failures` (severity=error first) and act on each.
    """

    schema_version: str = "1.0"
    passed: bool
    summary: EvaluationSummary
    gate_results: list[GateResult] = Field(default_factory=list)
    failures: list[GateFailure] = Field(
        default_factory=list,
        description="Flat list of all GateFailures across every gate — agent convenience field.",
    )
    metadata: Optional[ReportMetadata] = None

    @classmethod
    def from_gate_results(
        cls,
        gate_results: list[GateResult],
        metadata: Optional[ReportMetadata] = None,
    ) -> "EvaluationReport":
        """Build a complete EvaluationReport from a list of GateResults."""
        all_failures: list[GateFailure] = []
        passed_count = failed_count = skipped_count = error_count = 0

        for result in gate_results:
            all_failures.extend(result.failures)
            match result.status:
                case GateStatus.PASSED:
                    passed_count += 1
                case GateStatus.FAILED:
                    failed_count += 1
                case GateStatus.SKIPPED:
                    skipped_count += 1
                case GateStatus.ERROR:
                    error_count += 1

        blocking = sum(1 for f in all_failures if f.severity == Severity.ERROR)
        summary = EvaluationSummary(
            total_gates=len(gate_results),
            passed_gates=passed_count,
            failed_gates=failed_count,
            skipped_gates=skipped_count,
            error_gates=error_count,
            total_failures=len(all_failures),
            blocking_failures=blocking,
        )

        return cls(
            passed=(failed_count == 0 and error_count == 0),
            summary=summary,
            gate_results=gate_results,
            failures=all_failures,
            metadata=metadata,
        )


# ---------------------------------------------------------------------------
# Gate configuration
# ---------------------------------------------------------------------------


class GateConfig(BaseModel):
    """Per-gate configuration.  Agents and engineers can override thresholds
    or disable individual gates without touching code (G3 — tool lifecycle).
    """

    enabled_gates: list[GateId] = Field(
        default_factory=lambda: list(GateId),
        description="Gates to run.  Omitted gates are skipped.",
    )
    coverage_threshold: float = Field(
        90.0,
        ge=0.0,
        le=100.0,
        description="Minimum line-coverage percentage (%).",
    )
    max_staleness_days: int = Field(
        30,
        ge=1,
        description="Artifact freshness threshold: files older than this are flagged stale.",
    )
    performance_budget_ms: Optional[int] = Field(
        None,
        description="Optional response-time budget in milliseconds for performance gate.",
    )
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary extra config passed through to gate runners.",
    )
    gates: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Per-gate configuration keyed by gate_id. "
            "Each value is a dict of gate-specific keys (enabled, fail_on_error, "
            "threshold, etc.).  Takes precedence over the flat fields above."
        ),
    )

    # ------------------------------------------------------------------
    # Per-gate config helpers
    # ------------------------------------------------------------------

    def is_gate_enabled(self, gate_id: str) -> bool:
        """Return True if *gate_id* should run.

        Checks ``gates.<gate_id>.enabled`` first; falls back to whether the
        gate appears in ``enabled_gates``.
        """
        gate_cfg = self.gates.get(gate_id.lower(), {})
        if "enabled" in gate_cfg:
            return bool(gate_cfg["enabled"])
        return gate_id in {g.value for g in self.enabled_gates}

    def get_coverage_threshold(self) -> float:
        """Return coverage threshold, preferring per-gate override."""
        return float(self.gates.get("coverage", {}).get("threshold", self.coverage_threshold))

    def get_staleness_days(self) -> int:
        """Return docs_freshness staleness threshold, preferring per-gate override."""
        return int(
            self.gates.get("docs_freshness", {}).get("max_staleness_days", self.max_staleness_days)
        )

    def get_performance_budget_ms(self) -> Optional[int]:
        """Return performance budget in ms, preferring per-gate override."""
        return self.gates.get("performance", {}).get("budget_ms", self.performance_budget_ms)


# ---------------------------------------------------------------------------
# Gate runner base class
# ---------------------------------------------------------------------------


class GateRunner(ABC):
    """Abstract base class for all evaluation gate runners.

    Subclasses implement _run() and return a list of GateFailure objects.
    The base class handles timing, exception wrapping, and GateResult assembly.
    """

    gate_id: GateId  # must be set on each subclass

    def run(self, project_root: Path, config: GateConfig) -> GateResult:
        """Execute the gate and return a GateResult.  Never raises."""
        if not config.is_gate_enabled(self.gate_id.value):
            return GateResult(gate_id=self.gate_id, status=GateStatus.SKIPPED)

        start = time.monotonic()
        try:
            failures = self._run(project_root, config)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            status = GateStatus.PASSED if not failures else GateStatus.FAILED
            message = self._summary_message(failures, config)
            return GateResult(
                gate_id=self.gate_id,
                status=status,
                duration_ms=elapsed_ms,
                failures=failures,
                message=message,
            )
        except Exception as exc:  # noqa: BLE001
            elapsed_ms = int((time.monotonic() - start) * 1000)
            failure = GateFailure(
                severity=Severity.ERROR,
                gate_id=self.gate_id,
                message=f"Gate runner raised an exception: {exc}",
                suggestion=(
                    f"Check that the required tool for the {self.gate_id.value} gate "
                    "is installed and accessible in PATH."
                ),
            )
            return GateResult(
                gate_id=self.gate_id,
                status=GateStatus.ERROR,
                duration_ms=elapsed_ms,
                failures=[failure],
                message=str(exc),
            )

    @abstractmethod
    def _run(self, project_root: Path, config: GateConfig) -> list[GateFailure]:
        """Run checks and return GateFailure list.  Empty list means passed."""

    def _summary_message(
        self, failures: list[GateFailure], config: GateConfig  # noqa: ARG002
    ) -> str:
        n = len(failures)
        errors = sum(1 for f in failures if f.severity == Severity.ERROR)
        if n == 0:
            return f"{self.gate_id.value}: passed"
        return f"{self.gate_id.value}: {n} issue(s) ({errors} blocking)"

    # ------------------------------------------------------------------
    # Helpers shared by gate runners
    # ------------------------------------------------------------------

    @staticmethod
    def _run_cmd(
        args: list[str],
        cwd: Path,
        *,
        capture: bool = True,
    ) -> tuple[int, str, str]:
        """Run a subprocess and return (returncode, stdout, stderr)."""
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=capture,
            text=True,
        )
        return result.returncode, result.stdout or "", result.stderr or ""

    @staticmethod
    def _repo_rel(path: Path, project_root: Path) -> str:
        """Convert an absolute path to repo-relative string."""
        try:
            return str(path.relative_to(project_root))
        except ValueError:
            return str(path)


# ---------------------------------------------------------------------------
# Gate implementations
# ---------------------------------------------------------------------------


class RegressionGate(GateRunner):
    """Ensure all existing tests pass (no regressions).

    Runs pytest and parses JUnit XML for precise failure locations.
    Falls back to exit-code + stderr parsing when JUnit XML is unavailable.
    """

    gate_id = GateId.REGRESSION

    def _run(self, project_root: Path, config: GateConfig) -> list[GateFailure]:
        junit_xml = project_root / ".harness-junit.xml"
        returncode, stdout, stderr = self._run_cmd(
            [
                sys.executable, "-m", "pytest",
                "--tb=short",
                f"--junitxml={junit_xml}",
                "-q",
            ],
            cwd=project_root,
        )

        if returncode == 0:
            return []

        failures: list[GateFailure] = []

        # Parse JUnit XML for precise locations
        if junit_xml.exists():
            try:
                tree = ET.parse(junit_xml)
                for tc in tree.iter("testcase"):
                    for fail_el in tc.iter("failure"):
                        text = fail_el.text or ""
                        file_path, line_number = self._parse_location(text, project_root)
                        failures.append(
                            GateFailure(
                                severity=Severity.ERROR,
                                gate_id=GateId.REGRESSION,
                                message=f"Test failed: {tc.get('classname')}.{tc.get('name')}",
                                file_path=file_path,
                                line_number=line_number,
                                suggestion=(
                                    f"Fix the failing assertion in "
                                    f"{file_path or 'the test file'}"
                                    f"{f' at line {line_number}' if line_number else ''}. "
                                    "Run `pytest -x` locally to see the full traceback."
                                ),
                                context=text[:500] if text else None,
                            )
                        )
                junit_xml.unlink(missing_ok=True)
            except ET.ParseError:
                junit_xml.unlink(missing_ok=True)

        # Fallback: no JUnit XML
        if not failures:
            failures.append(
                GateFailure(
                    severity=Severity.ERROR,
                    gate_id=GateId.REGRESSION,
                    message="Test suite failed (pytest exited non-zero).",
                    suggestion=(
                        "Run `pytest --tb=short` to identify failing tests, "
                        "then fix each failure before re-running the gate."
                    ),
                    context=(stderr or stdout)[:500] or None,
                )
            )

        return failures

    @staticmethod
    def _parse_location(text: str, project_root: Path) -> tuple[Optional[str], Optional[int]]:
        match = re.search(r"([\w/\\.\-]+\.py):(\d+)", text)
        if not match:
            return None, None
        raw_path = match.group(1)
        line = int(match.group(2))
        candidate = project_root / raw_path
        if candidate.exists():
            return str(raw_path), line
        return raw_path, line


class CoverageGate(GateRunner):
    """Block PRs that drop coverage below the configured threshold.

    Reads coverage.py JSON report; generates one GateFailure per file that
    falls below threshold, plus an overall failure when the project total dips.
    """

    gate_id = GateId.COVERAGE

    def _run(self, project_root: Path, config: GateConfig) -> list[GateFailure]:
        threshold = config.get_coverage_threshold()
        coverage_json = project_root / ".coverage.json"

        # Run coverage via pytest-cov
        returncode, stdout, stderr = self._run_cmd(
            [
                sys.executable, "-m", "pytest",
                f"--cov={project_root}",
                "--cov-report=json:.coverage.json",
                "--cov-report=term-missing",
                "-q",
                "--tb=no",
            ],
            cwd=project_root,
        )

        if not coverage_json.exists():
            return [
                GateFailure(
                    severity=Severity.ERROR,
                    gate_id=GateId.COVERAGE,
                    message="Coverage report not generated — pytest-cov may not be installed.",
                    suggestion=(
                        "Install pytest-cov: `uv add --dev pytest-cov`, "
                        "then re-run `harness evaluate`."
                    ),
                )
            ]

        try:
            data = json.loads(coverage_json.read_text())
        except json.JSONDecodeError:
            return [
                GateFailure(
                    severity=Severity.ERROR,
                    gate_id=GateId.COVERAGE,
                    message="Coverage JSON report is malformed.",
                    suggestion="Delete .coverage.json and re-run the gate.",
                )
            ]
        finally:
            coverage_json.unlink(missing_ok=True)

        failures: list[GateFailure] = []
        totals = data.get("totals", {})
        project_pct: float = totals.get("percent_covered", 0.0)

        if project_pct < threshold:
            failures.append(
                GateFailure(
                    severity=Severity.ERROR,
                    gate_id=GateId.COVERAGE,
                    message=(
                        f"Project coverage {project_pct:.1f}% is below "
                        f"required {threshold:.1f}%."
                    ),
                    suggestion=(
                        f"Add tests to bring coverage to {threshold:.1f}%. "
                        "Focus on files with the lowest `percent_covered` in the "
                        "per-file breakdown below."
                    ),
                )
            )

        # Per-file failures (advisory warnings for files > 10 pp below threshold)
        for file_path, file_data in data.get("files", {}).items():
            file_pct: float = file_data.get("summary", {}).get("percent_covered", 100.0)
            if file_pct < threshold - 10:
                rel = self._repo_rel(Path(file_path), project_root)
                failures.append(
                    GateFailure(
                        severity=Severity.WARNING,
                        gate_id=GateId.COVERAGE,
                        message=f"{rel}: coverage {file_pct:.1f}% (threshold {threshold:.1f}%).",
                        file_path=rel,
                        suggestion=(
                            f"Add unit tests for the uncovered lines in {rel}. "
                            "Run `pytest --cov-report=term-missing` to see which lines are missing."
                        ),
                    )
                )

        return failures

    def _summary_message(self, failures: list[GateFailure], config: GateConfig) -> str:
        if not failures:
            return f"{self.gate_id.value}: passed (>= {config.coverage_threshold:.1f}%)"
        errors = [f for f in failures if f.severity == Severity.ERROR]
        if errors:
            return errors[0].message
        return super()._summary_message(failures, config)


class SecurityGate(GateRunner):
    """Check for known vulnerabilities and secret leaks.

    Runs pip-audit for Python dependency CVEs.  Extends to npm audit / bandit
    when detected (future plugins).
    """

    gate_id = GateId.SECURITY

    def _run(self, project_root: Path, config: GateConfig) -> list[GateFailure]:
        failures: list[GateFailure] = []
        failures.extend(self._run_pip_audit(project_root))
        failures.extend(self._run_bandit(project_root))
        return failures

    def _run_pip_audit(self, project_root: Path) -> list[GateFailure]:
        returncode, stdout, stderr = self._run_cmd(
            [sys.executable, "-m", "pip_audit", "--format=json", "--progress-spinner=off"],
            cwd=project_root,
        )
        if returncode == 0:
            return []
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            if returncode == 127 or "No module named pip_audit" in stderr:
                return []  # pip-audit not installed — skip silently
            return [
                GateFailure(
                    severity=Severity.WARNING,
                    gate_id=GateId.SECURITY,
                    message="pip-audit returned non-zero but output was not parseable JSON.",
                    suggestion="Run `pip-audit` manually to inspect dependency vulnerabilities.",
                    context=(stdout or stderr)[:300],
                )
            ]

        failures: list[GateFailure] = []
        for dep in data.get("dependencies", []):
            for vuln in dep.get("vulns", []):
                cve = vuln.get("id", "UNKNOWN")
                pkg = dep.get("name", "unknown")
                fixed = vuln.get("fix_versions", [])
                fix_hint = (
                    f"Upgrade {pkg} to {fixed[0]}" if fixed else f"No fix available for {pkg}"
                )
                failures.append(
                    GateFailure(
                        severity=Severity.ERROR,
                        gate_id=GateId.SECURITY,
                        message=f"{pkg}: {cve} — {vuln.get('description', '')}",
                        suggestion=fix_hint + ". Run `pip-audit --fix` to auto-upgrade.",
                        rule_id=cve,
                    )
                )
        return failures

    def _run_bandit(self, project_root: Path) -> list[GateFailure]:
        returncode, stdout, _ = self._run_cmd(
            [sys.executable, "-m", "bandit", "-r", ".", "-f", "json", "-q"],
            cwd=project_root,
        )
        if returncode not in (1, 0):
            return []  # bandit not installed or project not Python
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return []

        failures: list[GateFailure] = []
        for issue in data.get("results", []):
            sev_map = {"HIGH": Severity.ERROR, "MEDIUM": Severity.WARNING, "LOW": Severity.INFO}
            sev = sev_map.get(issue.get("issue_severity", "LOW"), Severity.INFO)
            rel = self._repo_rel(Path(issue.get("filename", "")), project_root)
            failures.append(
                GateFailure(
                    severity=sev,
                    gate_id=GateId.SECURITY,
                    message=f"[bandit] {issue.get('test_id')}: {issue.get('issue_text')}",
                    file_path=rel,
                    line_number=issue.get("line_number"),
                    suggestion=(
                        f"See https://bandit.readthedocs.io/en/latest/plugins/"
                        f"{issue.get('test_id', '').lower()}.html for remediation guidance."
                    ),
                    rule_id=issue.get("test_id"),
                    context=issue.get("code"),
                )
            )
        return failures


class PerformanceGate(GateRunner):
    """Check build / startup time against a configured budget.

    When no performance_budget_ms is configured this gate is skipped so it
    doesn't block teams that haven't set a budget yet (G3 — tool lifecycle).
    """

    gate_id = GateId.PERFORMANCE

    def _run(self, project_root: Path, config: GateConfig) -> list[GateFailure]:
        if config.performance_budget_ms is None:
            return []  # No budget configured — pass silently

        perf_script = project_root / ".harness-perf.sh"
        if not perf_script.exists():
            return [
                GateFailure(
                    severity=Severity.INFO,
                    gate_id=GateId.PERFORMANCE,
                    message="Performance gate configured but .harness-perf.sh not found.",
                    suggestion=(
                        "Create .harness-perf.sh that boots the application and exits. "
                        "harness evaluate will measure its wall-clock time."
                    ),
                )
            ]

        start = time.monotonic()
        returncode, _, stderr = self._run_cmd(["bash", str(perf_script)], cwd=project_root)
        elapsed_ms = int((time.monotonic() - start) * 1000)

        if returncode != 0:
            return [
                GateFailure(
                    severity=Severity.ERROR,
                    gate_id=GateId.PERFORMANCE,
                    message=f".harness-perf.sh exited with code {returncode}.",
                    suggestion="Ensure .harness-perf.sh boots the app cleanly.",
                    context=stderr[:300],
                )
            ]

        budget = config.performance_budget_ms
        if elapsed_ms > budget:
            return [
                GateFailure(
                    severity=Severity.ERROR,
                    gate_id=GateId.PERFORMANCE,
                    message=f"Boot time {elapsed_ms}ms exceeds budget {budget}ms.",
                    suggestion=(
                        f"Profile startup to find slowdowns. "
                        f"Need to save at least {elapsed_ms - budget}ms."
                    ),
                )
            ]
        return []


class ArchitectureGate(GateRunner):
    """Detect import layer violations using simple AST import analysis.

    Reads architecture rules from harness.config.yaml (layer_order field).
    Reports each violation with exact file path and line number so agents can
    fix the import without exploring the codebase further.
    """

    gate_id = GateId.ARCHITECTURE

    # Default layer order — lower index = lower in the stack.
    # Imports must only go from higher → lower (e.g. service → repo, never repo → service).
    DEFAULT_LAYERS: list[str] = ["types", "config", "repo", "service", "runtime", "ui", "cli"]

    def _run(self, project_root: Path, config: GateConfig) -> list[GateFailure]:
        import ast

        layer_order: list[str] = config.extra.get("layer_order", self.DEFAULT_LAYERS)
        layer_rank = {layer: i for i, layer in enumerate(layer_order)}

        failures: list[GateFailure] = []
        for py_file in sorted(project_root.rglob("*.py")):
            # Skip venv, test fixtures, generated files
            parts = set(py_file.parts)
            if any(skip in parts for skip in {".venv", "venv", "__pycache__", ".git"}):
                continue

            file_layer = self._detect_layer(py_file, layer_order, project_root)
            if file_layer is None:
                continue

            try:
                source = py_file.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(source, filename=str(py_file))
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if not isinstance(node, (ast.Import, ast.ImportFrom)):
                    continue
                imported_module = (
                    node.names[0].name
                    if isinstance(node, ast.Import)
                    else (node.module or "")
                )
                imported_layer = self._module_to_layer(imported_module, layer_order, project_root)
                if imported_layer is None:
                    continue
                if layer_rank.get(imported_layer, -1) > layer_rank.get(file_layer, -1):
                    rel = self._repo_rel(py_file, project_root)
                    failures.append(
                        GateFailure(
                            severity=Severity.ERROR,
                            gate_id=GateId.ARCHITECTURE,
                            message=(
                                f"Layer violation: {file_layer!r} imports from {imported_layer!r} "
                                f"({imported_module})."
                            ),
                            file_path=rel,
                            line_number=node.lineno,
                            suggestion=(
                                f"Move the dependency on `{imported_module}` behind an interface "
                                f"or inject it from a higher layer. "
                                f"Layer {file_layer!r} may only import from: "
                                + ", ".join(
                                    l for l in layer_order
                                    if layer_rank[l] <= layer_rank[file_layer]
                                    and l != file_layer
                                )
                                + "."
                            ),
                            rule_id="arch/layer-violation",
                        )
                    )

        return failures

    def _detect_layer(
        self, py_file: Path, layers: list[str], project_root: Path
    ) -> Optional[str]:
        parts = py_file.relative_to(project_root).parts
        for part in parts:
            for layer in layers:
                if layer in part.lower():
                    return layer
        return None

    def _module_to_layer(
        self, module: str, layers: list[str], project_root: Path
    ) -> Optional[str]:
        # Map imported module name back to a layer by checking if any layer
        # keyword appears in the module path segments.
        for segment in module.split("."):
            for layer in layers:
                if layer in segment.lower():
                    return layer
        return None


class PrinciplesGate(GateRunner):
    """Scan codebase for violations of PRINCIPLES.md golden rules.

    Currently implements: magic number detection, hard-coded string URLs,
    and direct os.environ access outside config layer.  Additional rules are
    loaded from harness.config.yaml `principle_rules` list.
    """

    gate_id = GateId.PRINCIPLES

    def _run(self, project_root: Path, config: GateConfig) -> list[GateFailure]:
        import ast

        failures: list[GateFailure] = []
        for py_file in sorted(project_root.rglob("*.py")):
            parts = set(py_file.parts)
            if any(skip in parts for skip in {".venv", "venv", "__pycache__", ".git"}):
                continue
            try:
                source = py_file.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(source, filename=str(py_file))
            except SyntaxError:
                continue

            rel = self._repo_rel(py_file, project_root)
            failures.extend(self._check_magic_numbers(tree, rel))
            failures.extend(self._check_hardcoded_urls(tree, rel))

        return failures

    def _check_magic_numbers(self, tree: Any, file_path: str) -> list[GateFailure]:
        import ast

        failures = []
        ALLOWED = {0, 1, -1, 2, 100, 1000}
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                if node.value not in ALLOWED and abs(node.value) > 1:
                    failures.append(
                        GateFailure(
                            severity=Severity.WARNING,
                            gate_id=GateId.PRINCIPLES,
                            message=f"Magic number {node.value!r} — extract to a named constant.",
                            file_path=file_path,
                            line_number=node.lineno,
                            suggestion=(
                                f"Replace {node.value!r} with a named constant, e.g. "
                                f"`SOME_THRESHOLD = {node.value!r}` in a config or constants module."
                            ),
                            rule_id="principles/no-magic-numbers",
                        )
                    )
        return failures

    def _check_hardcoded_urls(self, tree: Any, file_path: str) -> list[GateFailure]:
        import ast

        failures = []
        url_re = re.compile(r"https?://[^\s\"']+")
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if url_re.search(node.value) and len(node.value) > 10:
                    failures.append(
                        GateFailure(
                            severity=Severity.WARNING,
                            gate_id=GateId.PRINCIPLES,
                            message=f"Hard-coded URL: {node.value[:60]!r}",
                            file_path=file_path,
                            line_number=node.lineno,
                            suggestion=(
                                "Move this URL to harness.config.yaml or an environment variable. "
                                "Hard-coded URLs make environment-switching and testing harder."
                            ),
                            rule_id="principles/no-hardcoded-urls",
                        )
                    )
        return failures


class DocsFreshnessGate(GateRunner):
    """Check that generated harness artifacts haven't gone stale.

    Reads generation timestamps embedded in AGENTS.md, ARCHITECTURE.md,
    PRINCIPLES.md, and EVALUATION.md.  Files older than max_staleness_days
    are flagged for regeneration.
    """

    gate_id = GateId.DOCS_FRESHNESS

    TRACKED_FILES = [
        "AGENTS.md",
        "ARCHITECTURE.md",
        "PRINCIPLES.md",
        "EVALUATION.md",
    ]
    TIMESTAMP_RE = re.compile(r"generated_at:\s*([\d\-T:.+Z]+)")

    def _run(self, project_root: Path, config: GateConfig) -> list[GateFailure]:
        failures: list[GateFailure] = []
        now = datetime.now(timezone.utc)

        for name in self.TRACKED_FILES:
            path = project_root / name
            if not path.exists():
                failures.append(
                    GateFailure(
                        severity=Severity.WARNING,
                        gate_id=GateId.DOCS_FRESHNESS,
                        message=f"{name} not found — harness artifacts not yet generated.",
                        file_path=name,
                        suggestion=(
                            f"Run `harness create` to generate {name} and other harness artifacts."
                        ),
                        rule_id="docs/missing-artifact",
                    )
                )
                continue

            content = path.read_text(encoding="utf-8", errors="replace")
            match = self.TIMESTAMP_RE.search(content)
            if not match:
                failures.append(
                    GateFailure(
                        severity=Severity.INFO,
                        gate_id=GateId.DOCS_FRESHNESS,
                        message=f"{name} has no embedded generation timestamp.",
                        file_path=name,
                        suggestion=(
                            f"Run `harness update` to regenerate {name} with embedded timestamps."
                        ),
                        rule_id="docs/missing-timestamp",
                    )
                )
                continue

            try:
                generated_at = datetime.fromisoformat(match.group(1).replace("Z", "+00:00"))
                age_days = (now - generated_at).days
                if age_days > config.get_staleness_days():
                    failures.append(
                        GateFailure(
                            severity=Severity.WARNING,
                            gate_id=GateId.DOCS_FRESHNESS,
                            message=(
                                f"{name} is {age_days} days old "
                                f"(threshold: {config.get_staleness_days()} days)."
                            ),
                            file_path=name,
                            suggestion=f"Run `harness update` to refresh {name}.",
                            rule_id="docs/stale-artifact",
                        )
                    )
            except ValueError:
                pass

        return failures


class TypesGate(GateRunner):
    """Run mypy (Python) or tsc --noEmit (TypeScript) and map errors to GateFailures.

    Detects the project language from pyproject.toml / tsconfig.json and runs
    the appropriate type checker.  Each type error becomes a GateFailure with
    exact file_path and line_number.
    """

    gate_id = GateId.TYPES

    def _run(self, project_root: Path, config: GateConfig) -> list[GateFailure]:
        if (project_root / "pyproject.toml").exists() or (project_root / "setup.py").exists():
            return self._run_mypy(project_root)
        if (project_root / "tsconfig.json").exists():
            return self._run_tsc(project_root)
        return []  # Unknown language — skip

    def _run_mypy(self, project_root: Path) -> list[GateFailure]:
        returncode, stdout, stderr = self._run_cmd(
            [sys.executable, "-m", "mypy", ".", "--show-error-codes", "--no-error-summary"],
            cwd=project_root,
        )
        if returncode == 0:
            return []

        failures: list[GateFailure] = []
        # Mypy output format: path/to/file.py:42: error: message  [error-code]
        pattern = re.compile(r"^(.+?):(\d+): (error|warning|note): (.+?)(?:\s+\[(.+)\])?$")
        for line in (stdout + stderr).splitlines():
            m = pattern.match(line)
            if not m:
                continue
            rel_path, lineno, level, msg, code = m.groups()
            sev = Severity.ERROR if level == "error" else Severity.WARNING
            failures.append(
                GateFailure(
                    severity=sev,
                    gate_id=GateId.TYPES,
                    message=msg.strip(),
                    file_path=rel_path,
                    line_number=int(lineno),
                    suggestion=(
                        f"Fix the type error in {rel_path}:{lineno}. "
                        "Run `mypy .` locally to see the full context."
                    ),
                    rule_id=code,
                )
            )
        return failures

    def _run_tsc(self, project_root: Path) -> list[GateFailure]:
        returncode, stdout, stderr = self._run_cmd(
            ["npx", "tsc", "--noEmit", "--pretty", "false"],
            cwd=project_root,
        )
        if returncode == 0:
            return []

        failures: list[GateFailure] = []
        pattern = re.compile(r"^(.+?)\((\d+),\d+\):\s+error\s+(TS\d+):\s+(.+)$")
        for line in (stdout + stderr).splitlines():
            m = pattern.match(line)
            if not m:
                continue
            rel_path, lineno, code, msg = m.groups()
            failures.append(
                GateFailure(
                    severity=Severity.ERROR,
                    gate_id=GateId.TYPES,
                    message=msg.strip(),
                    file_path=rel_path,
                    line_number=int(lineno),
                    suggestion=(
                        f"Fix the TypeScript error {code} in {rel_path}:{lineno}. "
                        "Run `npx tsc --noEmit` locally for context."
                    ),
                    rule_id=code,
                )
            )
        return failures


class LintGate(GateRunner):
    """Run the project linter and map each violation to a GateFailure.

    Auto-detects Ruff (Python) or ESLint (JavaScript/TypeScript).
    Emits machine-parseable JSON output so every violation has a precise
    file_path, line_number, rule_id, and suggestion.
    """

    gate_id = GateId.LINT

    def _run(self, project_root: Path, config: GateConfig) -> list[GateFailure]:
        if (project_root / "pyproject.toml").exists() or (project_root / "ruff.toml").exists():
            return self._run_ruff(project_root)
        if (project_root / ".eslintrc.js").exists() or (project_root / ".eslintrc.json").exists():
            return self._run_eslint(project_root)
        # Fallback: try ruff anyway
        return self._run_ruff(project_root)

    def _run_ruff(self, project_root: Path) -> list[GateFailure]:
        returncode, stdout, stderr = self._run_cmd(
            [sys.executable, "-m", "ruff", "check", ".", "--output-format=json"],
            cwd=project_root,
        )
        if returncode == 0:
            return []

        try:
            violations = json.loads(stdout)
        except json.JSONDecodeError:
            if not stdout.strip():
                return []
            return [
                GateFailure(
                    severity=Severity.WARNING,
                    gate_id=GateId.LINT,
                    message="Ruff produced non-JSON output — run `ruff check .` manually.",
                    suggestion="Run `ruff check .` to identify lint violations.",
                    context=stdout[:300],
                )
            ]

        failures: list[GateFailure] = []
        for v in violations:
            loc = v.get("location", {})
            fix = v.get("fix")
            fix_hint = fix.get("message") if fix else None
            failures.append(
                GateFailure(
                    severity=Severity.ERROR,
                    gate_id=GateId.LINT,
                    message=v.get("message", ""),
                    file_path=self._repo_rel(Path(v.get("filename", "")), project_root),
                    line_number=loc.get("row"),
                    suggestion=(
                        fix_hint
                        or f"Run `ruff check --fix .` to auto-fix {v.get('code')} violations."
                    ),
                    rule_id=v.get("code"),
                )
            )
        return failures

    def _run_eslint(self, project_root: Path) -> list[GateFailure]:
        returncode, stdout, _ = self._run_cmd(
            ["npx", "eslint", ".", "--format=json"],
            cwd=project_root,
        )
        if returncode == 0:
            return []

        try:
            files = json.loads(stdout)
        except json.JSONDecodeError:
            return []

        failures: list[GateFailure] = []
        for file_result in files:
            rel = self._repo_rel(Path(file_result.get("filePath", "")), project_root)
            for msg in file_result.get("messages", []):
                sev = Severity.ERROR if msg.get("severity") == 2 else Severity.WARNING
                rule = msg.get("ruleId") or "unknown"
                failures.append(
                    GateFailure(
                        severity=sev,
                        gate_id=GateId.LINT,
                        message=msg.get("message", ""),
                        file_path=rel,
                        line_number=msg.get("line"),
                        suggestion=(
                            f"Fix ESLint rule {rule} in {rel}:{msg.get('line')}. "
                            "Run `npx eslint --fix .` to auto-fix where possible."
                        ),
                        rule_id=rule,
                    )
                )
        return failures


# ---------------------------------------------------------------------------
# Gate registry
# ---------------------------------------------------------------------------

_GATE_RUNNERS: dict[GateId, GateRunner] = {
    GateId.REGRESSION: RegressionGate(),
    GateId.COVERAGE: CoverageGate(),
    GateId.SECURITY: SecurityGate(),
    GateId.PERFORMANCE: PerformanceGate(),
    GateId.ARCHITECTURE: ArchitectureGate(),
    GateId.PRINCIPLES: PrinciplesGate(),
    GateId.DOCS_FRESHNESS: DocsFreshnessGate(),
    GateId.TYPES: TypesGate(),
    GateId.LINT: LintGate(),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_gate(
    gate_id: GateId,
    project_root: str | Path = ".",
    config: Optional[GateConfig] = None,
) -> GateResult:
    """Run a single gate and return its GateResult.

    Args:
        gate_id:      Which gate to run.
        project_root: Path to the repository root.
        config:       GateConfig instance (uses defaults when None).

    Returns:
        GateResult with status, duration_ms, failures, and message.
    """
    if config is None:
        config = GateConfig()
    root = Path(project_root).resolve()
    runner = _GATE_RUNNERS[gate_id]
    return runner.run(root, config)


def run_all_gates(
    project_root: str | Path = ".",
    config: Optional[GateConfig] = None,
    *,
    gates: Optional[list[GateId]] = None,
) -> EvaluationReport:
    """Run all (or a subset of) gates and return a complete EvaluationReport.

    This is the primary entry point — equivalent to `harness evaluate --format json`.

    Args:
        project_root: Path to the repository root.
        config:       GateConfig instance (uses defaults when None).
        gates:        Optional subset of GateIds to run; defaults to all.

    Returns:
        EvaluationReport conforming to evaluation_report.schema.json.
        If report.passed is False, iterate report.failures (severity=error first)
        and act on each failure's suggestion.
    """
    if config is None:
        config = GateConfig()
    root = Path(project_root).resolve()

    gate_ids = gates if gates is not None else list(GateId)
    results: list[GateResult] = []
    for gid in gate_ids:
        results.append(_GATE_RUNNERS[gid].run(root, config))

    metadata = _collect_metadata(root)
    return EvaluationReport.from_gate_results(results, metadata=metadata)


def format_report(report: EvaluationReport, *, indent: int = 2) -> str:
    """Serialise an EvaluationReport to a JSON string.

    The output is validated against evaluation_report.schema.json at runtime
    when jsonschema is available, raising ValueError on violations.
    """
    json_str = report.model_dump_json(indent=indent)

    # Runtime schema validation (optional dependency)
    try:
        import importlib.resources
        import jsonschema  # type: ignore[import]

        schema_path = (
            Path(__file__).parent.parent / "schemas" / "evaluation_report.schema.json"
        )
        if schema_path.exists():
            schema = json.loads(schema_path.read_text())
            data = json.loads(json_str)
            jsonschema.validate(instance=data, schema=schema)
    except ImportError:
        pass  # jsonschema not installed — skip validation

    return json_str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _collect_metadata(project_root: Path) -> ReportMetadata:
    git_sha = git_branch = None
    try:
        rc, sha, _ = _run_silent(["git", "rev-parse", "HEAD"], cwd=project_root)
        if rc == 0:
            git_sha = sha.strip()
        rc2, branch, _ = _run_silent(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=project_root
        )
        if rc2 == 0:
            git_branch = branch.strip()
    except FileNotFoundError:
        pass  # git not available

    from harness_skills import __version__

    return ReportMetadata(
        project_root=str(project_root),
        harness_version=__version__,
        git_sha=git_sha,
        git_branch=git_branch,
    )


def _run_silent(args: list[str], cwd: Path) -> tuple[int, str, str]:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    return result.returncode, result.stdout or "", result.stderr or ""
