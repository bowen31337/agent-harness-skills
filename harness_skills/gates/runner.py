"""
harness_skills/gates/runner.py
================================
Gate orchestration layer — reads per-gate configuration from
``harness.config.yaml`` and drives built-in gate execution.

Each gate in ``GATE_CONFIG_CLASSES`` can be individually:

* **Enabled or disabled** — ``gates.<gate_id>.enabled: true/false``
* **Downgraded to advisory** — ``gates.<gate_id>.fail_on_error: false``
* **Threshold-adjusted** — e.g. ``gates.coverage.threshold: 85``

This module is the bridge between the YAML config written by engineers and
the runtime behaviour of ``harness evaluate``.

## Design

    HarnessConfigLoader
        Reads harness.config.yaml, selects the active profile, and returns
        a typed dict of per-gate config objects via ``gate_configs()``.

    GateEvaluator
        Orchestrates gate execution.  For each built-in gate it:
          1. Resolves the per-gate config (defaults + YAML overrides).
          2. Skips the gate if ``enabled: false``.
          3. Executes the gate's check function.
          4. Respects ``fail_on_error`` when assembling the final report.

    run_gates(project_root, config_path)  →  EvaluationSummary
        Convenience entry-point used by ``harness evaluate``.

## Usage

    from harness_skills.gates.runner import run_gates, HarnessConfigLoader

    # Load config from default path
    loader = HarnessConfigLoader("harness.config.yaml")
    gate_cfgs = loader.gate_configs()

    # Check what the coverage gate threshold is
    from harness_skills.models.gate_configs import CoverageGateConfig
    cov = gate_cfgs.get("coverage")
    if isinstance(cov, CoverageGateConfig):
        print(f"Coverage threshold: {cov.threshold}%")

    # Full evaluation
    summary = run_gates(project_root=".", config_path="harness.config.yaml")
    print(f"Passed: {summary.passed}")
    for failure in summary.failures:
        print(f"  [{failure.severity}] {failure.gate_id}: {failure.message}")
"""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import]
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

from harness_skills.models.gate_configs import (
    ArchitectureGateConfig,
    BaseGateConfig,
    CoverageGateConfig,
    DocsFreshnessGateConfig,
    LintGateConfig,
    PerformanceGateConfig,
    PrinciplesGateConfig,
    RegressionGateConfig,
    SecurityGateConfig,
    TypesGateConfig,
    GATE_CONFIG_CLASSES,
    PROFILE_GATE_DEFAULTS,
    ARCHITECTURE_STYLE_PRESETS,
)
from harness_skills.models.base import GateResult as BaseGateResult, Status
from harness_skills.plugins.loader import load_plugin_gates
from harness_skills.plugins.runner import run_plugin_gates


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class GateFailure:
    """A single actionable violation produced by a gate run."""

    gate_id: str
    severity: str          # "error" | "warning" | "info"
    message: str
    file_path: str | None = None
    line_number: int | None = None
    suggestion: str | None = None
    rule_id: str | None = None


@dataclass
class GateOutcome:
    """Outcome of running a single gate."""

    gate_id: str
    status: str            # "passed" | "failed" | "skipped" | "error"
    duration_ms: int = 0
    failures: list[GateFailure] = field(default_factory=list)
    message: str = ""

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    @property
    def skipped(self) -> bool:
        return self.status == "skipped"


@dataclass
class EvaluationSummary:
    """Aggregated result of running all configured gates."""

    passed: bool
    total_gates: int = 0
    passed_gates: int = 0
    failed_gates: int = 0
    skipped_gates: int = 0
    total_failures: int = 0
    blocking_failures: int = 0
    outcomes: list[GateOutcome] = field(default_factory=list)
    failures: list[GateFailure] = field(default_factory=list)

    def __str__(self) -> str:
        status = "PASSED" if self.passed else "FAILED"
        return (
            f"[{status}] {self.passed_gates}/{self.total_gates} gates passed "
            f"({self.skipped_gates} skipped, {self.blocking_failures} blocking failures)"
        )


# ---------------------------------------------------------------------------
# Plugin gate conversion helpers
# ---------------------------------------------------------------------------


def _plugin_result_to_outcome(result: BaseGateResult) -> GateOutcome:
    """Convert a plugin :class:`~harness_skills.models.base.GateResult` to a
    :class:`GateOutcome` understood by :class:`GateEvaluator`.

    ``Status.WARNING`` (produced when ``fail_on_error: false`` and the command
    exits non-zero) is treated as *passed* so it remains advisory — consistent
    with how built-in gates handle ``fail_on_error: false``.
    """
    failures = [
        GateFailure(
            gate_id=result.gate_id,
            severity=v.severity,
            message=v.message,
            file_path=v.file_path,
            line_number=v.line_number,
            suggestion=v.suggestion,
            rule_id=v.rule_id,
        )
        for v in result.violations
    ]
    # Map base.Status → outcome status string
    status_map = {
        Status.PASSED: "passed",
        Status.FAILED: "failed",
        Status.WARNING: "passed",   # advisory: fail_on_error=false
        Status.SKIPPED: "skipped",
        Status.RUNNING: "skipped",
    }
    status_str = status_map.get(result.status, "error")
    return GateOutcome(
        gate_id=result.gate_id,
        status=status_str,
        duration_ms=result.duration_ms or 0,
        failures=failures,
        message=result.message or f"plugin/{result.gate_id}: {status_str}",
    )


# ---------------------------------------------------------------------------
# HarnessConfigLoader
# ---------------------------------------------------------------------------


class HarnessConfigLoader:
    """Load and validate per-gate configuration from ``harness.config.yaml``.

    Parameters
    ----------
    config_path:
        Path to ``harness.config.yaml``.  Defaults to ``harness.config.yaml``
        in the current working directory.

    Examples
    --------
    ::

        loader = HarnessConfigLoader("harness.config.yaml")
        print(f"Active profile: {loader.active_profile}")

        gate_cfgs = loader.gate_configs()
        cov = gate_cfgs["coverage"]
        print(f"Coverage threshold: {cov.threshold}%")
        print(f"Coverage enabled:   {cov.enabled}")
    """

    def __init__(self, config_path: str | Path = "harness.config.yaml") -> None:
        self._path = Path(config_path)
        self._raw: dict[str, Any] = {}
        self._loaded = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def active_profile(self) -> str:
        """Name of the active profile (e.g. ``"starter"``).

        Reads ``active_profile`` from the YAML file.  Falls back to
        ``"starter"`` if the key is absent or the file cannot be read.
        """
        self._ensure_loaded()
        return str(self._raw.get("active_profile", "starter"))

    def gate_configs(
        self,
        profile: str | None = None,
    ) -> dict[str, BaseGateConfig]:
        """Return a dict of gate_id → typed per-gate config for *profile*.

        Resolution order for each gate:

        1. The ``gates.<gate_id>`` block in ``harness.config.yaml`` for the
           requested profile (partial overrides are supported — only the keys
           present in YAML override the profile default).
        2. The profile-level default from :data:`PROFILE_GATE_DEFAULTS`.
        3. The class-level default from :class:`BaseGateConfig`.

        Parameters
        ----------
        profile:
            Profile to load.  Defaults to :attr:`active_profile`.

        Returns
        -------
        dict[str, BaseGateConfig]
            One typed config object per built-in gate.  Keys are lowercase
            gate IDs matching :data:`GATE_CONFIG_CLASSES`.

        Raises
        ------
        ValueError
            If *profile* is not found in the YAML profiles section.
        """
        self._ensure_loaded()
        prof = profile or self.active_profile
        profile_data = self._profile_data(prof)
        raw_gates: dict[str, Any] = profile_data.get("gates", {}) or {}

        result: dict[str, BaseGateConfig] = {}
        # Start from profile defaults, then apply YAML overrides per gate.
        profile_defaults = PROFILE_GATE_DEFAULTS.get(prof, PROFILE_GATE_DEFAULTS["starter"])

        for gate_id, cfg_cls in GATE_CONFIG_CLASSES.items():
            # Base: profile default (or class default if profile unknown)
            default_cfg = profile_defaults.get(gate_id, cfg_cls())
            default_dict = default_cfg.model_dump()

            # Overlay: YAML overrides for this gate (partial dict is fine)
            yaml_override: dict[str, Any] = {}
            raw_gate = raw_gates.get(gate_id)
            if isinstance(raw_gate, dict):
                yaml_override = raw_gate

            merged = {**default_dict, **yaml_override}
            result[gate_id] = cfg_cls.model_validate(merged)

        return result

    def plugin_gates(self, profile: str | None = None) -> list[dict[str, Any]]:
        """Return raw plugin gate definitions for *profile*.

        Plugin gates are validated and executed by
        :mod:`harness_skills.plugins.gate_plugin`.  This method returns the
        raw YAML dicts — validation is left to the plugin loader.
        """
        self._ensure_loaded()
        prof = profile or self.active_profile
        profile_data = self._profile_data(prof)
        raw_gates: dict[str, Any] = profile_data.get("gates", {}) or {}
        plugins = raw_gates.get("plugins") or []
        return list(plugins) if isinstance(plugins, list) else []

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        if not _YAML_AVAILABLE:
            raise ImportError(
                "PyYAML is required to load harness.config.yaml. "
                "Install it with: pip install pyyaml"
            )
        if not self._path.exists():
            # Return empty config — caller gets all defaults
            self._raw = {}
            self._loaded = True
            return
        try:
            self._raw = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            raise ValueError(
                f"Failed to parse {self._path}: {exc}"
            ) from exc
        self._loaded = True

    def _profile_data(self, profile: str) -> dict[str, Any]:
        profiles: dict[str, Any] = self._raw.get("profiles", {}) or {}
        if profile not in profiles:
            # Graceful fallback — return empty profile so defaults apply
            return {}
        return profiles[profile] or {}


# ---------------------------------------------------------------------------
# Built-in gate check functions
# ---------------------------------------------------------------------------
# Each function signature:  check_<gate>(project_root, cfg) -> list[GateFailure]
# Return empty list = gate passed.


def _run_cmd(
    args: list[str], cwd: Path
) -> tuple[int, str, str]:
    """Run a subprocess; return (returncode, stdout, stderr)."""
    result = subprocess.run(
        args, cwd=cwd, capture_output=True, text=True
    )
    return result.returncode, result.stdout or "", result.stderr or ""


def _repo_rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def check_regression(
    project_root: Path, cfg: RegressionGateConfig
) -> list[GateFailure]:
    """Run test suite and collect failures."""
    import xml.etree.ElementTree as ET
    import re as _re

    junit_xml = project_root / ".harness-junit.xml"
    cmd = [
        sys.executable, "-m", "pytest",
        "--tb=short",
        f"--junitxml={junit_xml}",
        "-q",
        *cfg.extra_args,
    ]
    try:
        result = subprocess.run(
            cmd, cwd=project_root, capture_output=True, text=True,
            timeout=cfg.timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return [GateFailure(
            gate_id="regression", severity="error",
            message=f"Test suite timed out after {cfg.timeout_seconds}s.",
            suggestion="Increase timeout_seconds or optimise the test suite.",
        )]

    if result.returncode == 0:
        return []

    failures: list[GateFailure] = []
    if junit_xml.exists():
        try:
            tree = ET.parse(junit_xml)
            for tc in tree.iter("testcase"):
                for fail_el in tc.iter("failure"):
                    text = fail_el.text or ""
                    m = _re.search(r"([\w/\\.\-]+\.py):(\d+)", text)
                    fp = m.group(1) if m else None
                    ln = int(m.group(2)) if m else None
                    failures.append(GateFailure(
                        gate_id="regression", severity="error",
                        message=f"Test failed: {tc.get('classname')}.{tc.get('name')}",
                        file_path=fp, line_number=ln,
                        suggestion=(
                            f"Fix the failing assertion in {fp or 'the test file'}"
                            + (f" at line {ln}" if ln else "")
                            + ". Run `pytest -x` locally for the full traceback."
                        ),
                    ))
            junit_xml.unlink(missing_ok=True)
        except ET.ParseError:
            junit_xml.unlink(missing_ok=True)

    if not failures:
        failures.append(GateFailure(
            gate_id="regression", severity="error",
            message="Test suite failed (pytest exited non-zero).",
            suggestion="Run `pytest --tb=short` to identify failing tests.",
        ))
    return failures


def check_coverage(
    project_root: Path, cfg: CoverageGateConfig
) -> list[GateFailure]:
    """Measure code coverage and fail if below threshold."""
    import json as _json

    coverage_json = project_root / ".coverage.json"
    exclude = cfg.exclude_patterns
    omit_args: list[str] = []
    for p in exclude:
        omit_args += [f"--omit={p}"]

    branch_args = ["--branch"] if cfg.branch_coverage else []
    _run_cmd(
        [
            sys.executable, "-m", "pytest",
            f"--cov={project_root}",
            "--cov-report=json:.coverage.json",
            "--cov-report=term-missing",
            "-q", "--tb=no",
            *branch_args, *omit_args,
        ],
        cwd=project_root,
    )

    if not coverage_json.exists():
        return [GateFailure(
            gate_id="coverage", severity="error",
            message="Coverage report not generated — pytest-cov may not be installed.",
            suggestion="Install pytest-cov: `pip install pytest-cov`, then re-run.",
        )]

    try:
        data = _json.loads(coverage_json.read_text())
    except _json.JSONDecodeError:
        return [GateFailure(
            gate_id="coverage", severity="error",
            message="Coverage JSON report is malformed.",
            suggestion="Delete .coverage.json and re-run.",
        )]
    finally:
        coverage_json.unlink(missing_ok=True)

    threshold = cfg.threshold
    failures: list[GateFailure] = []
    totals = data.get("totals", {})
    pct: float = totals.get("percent_covered", 0.0)

    if pct < threshold:
        failures.append(GateFailure(
            gate_id="coverage", severity="error",
            message=f"Project coverage {pct:.1f}% is below required {threshold}%.",
            suggestion=(
                f"Add tests to raise coverage to {threshold}%. "
                "Focus on files with the lowest per-file coverage."
            ),
        ))

    # Per-file advisory warnings for files > 10 pp below threshold
    for file_path, file_data in data.get("files", {}).items():
        file_pct: float = file_data.get("summary", {}).get("percent_covered", 100.0)
        if file_pct < threshold - 10:
            rel = _repo_rel(Path(file_path), project_root)
            failures.append(GateFailure(
                gate_id="coverage", severity="warning",
                message=f"{rel}: coverage {file_pct:.1f}% (threshold {threshold}%).",
                file_path=rel,
                suggestion=(
                    f"Add unit tests for uncovered lines in {rel}. "
                    "Run `pytest --cov-report=term-missing` to see missing lines."
                ),
            ))

    return failures


def check_security(
    project_root: Path, cfg: SecurityGateConfig
) -> list[GateFailure]:
    """Run security scanners and filter by severity threshold."""
    import json as _json

    _SEV_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    threshold_rank = _SEV_RANK.get(cfg.severity_threshold.upper(), 3)
    failures: list[GateFailure] = []

    if cfg.scan_dependencies:
        rc, stdout, stderr = _run_cmd(
            [sys.executable, "-m", "pip_audit", "--format=json", "--progress-spinner=off"],
            cwd=project_root,
        )
        if rc != 0:
            try:
                data = _json.loads(stdout)
                for dep in data.get("dependencies", []):
                    for vuln in dep.get("vulns", []):
                        cve_id = vuln.get("id", "UNKNOWN")
                        if cve_id in cfg.ignore_ids:
                            continue
                        pkg = dep.get("name", "unknown")
                        fixed = vuln.get("fix_versions", [])
                        fix_hint = (
                            f"Upgrade {pkg} to {fixed[0]}" if fixed else f"No fix for {pkg}"
                        )
                        failures.append(GateFailure(
                            gate_id="security", severity="error",
                            message=f"{pkg}: {cve_id} — {vuln.get('description', '')}",
                            suggestion=fix_hint + ". Run `pip-audit --fix` to auto-upgrade.",
                            rule_id=cve_id,
                        ))
            except (_json.JSONDecodeError, KeyError):
                pass  # pip-audit not installed — skip

        # Bandit static analysis
        rc2, stdout2, _ = _run_cmd(
            [sys.executable, "-m", "bandit", "-r", ".", "-f", "json", "-q"],
            cwd=project_root,
        )
        if rc2 in (0, 1):
            try:
                bdata = _json.loads(stdout2)
                sev_map = {"HIGH": "error", "MEDIUM": "warning", "LOW": "info"}
                rank_map = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
                for issue in bdata.get("results", []):
                    issue_sev = issue.get("issue_severity", "LOW").upper()
                    if rank_map.get(issue_sev, 1) < threshold_rank:
                        continue
                    rule_id = issue.get("test_id", "")
                    if rule_id in cfg.ignore_ids:
                        continue
                    rel = _repo_rel(Path(issue.get("filename", "")), project_root)
                    failures.append(GateFailure(
                        gate_id="security",
                        severity=sev_map.get(issue_sev, "info"),
                        message=f"[bandit] {rule_id}: {issue.get('issue_text')}",
                        file_path=rel,
                        line_number=issue.get("line_number"),
                        suggestion=(
                            f"See https://bandit.readthedocs.io/en/latest/plugins/"
                            f"{rule_id.lower()}.html for remediation."
                        ),
                        rule_id=rule_id,
                    ))
            except (_json.JSONDecodeError, KeyError):
                pass  # bandit not installed

    return failures


def check_performance(
    project_root: Path, cfg: PerformanceGateConfig
) -> list[GateFailure]:
    """Time the performance benchmark script against budget_ms."""
    perf_script = project_root / ".harness-perf.sh"
    if not perf_script.exists():
        return [GateFailure(
            gate_id="performance", severity="info",
            message="Performance gate enabled but .harness-perf.sh not found.",
            suggestion=(
                "Create .harness-perf.sh that runs your benchmark and exits. "
                "harness evaluate will time its wall-clock execution."
            ),
        )]

    start = time.monotonic()
    rc, _, stderr = _run_cmd(["bash", str(perf_script)], cwd=project_root)
    elapsed_ms = int((time.monotonic() - start) * 1000)

    if rc != 0:
        return [GateFailure(
            gate_id="performance", severity="error",
            message=f".harness-perf.sh exited with code {rc}.",
            suggestion="Ensure .harness-perf.sh boots the app cleanly.",
        )]

    if elapsed_ms > cfg.budget_ms:
        return [GateFailure(
            gate_id="performance", severity="error",
            message=f"Elapsed {elapsed_ms}ms exceeds budget {cfg.budget_ms}ms.",
            suggestion=(
                f"Profile startup to find bottlenecks. "
                f"Need to save ≥{elapsed_ms - cfg.budget_ms}ms."
            ),
        )]
    return []


def _resolve_layer_definitions(
    cfg: ArchitectureGateConfig,
) -> list[dict[str, Any]]:
    """Return the final ordered layer definitions to use for enforcement.

    Resolution priority (highest to lowest):

    1. ``cfg.layer_definitions`` — explicit per-layer dicts with ``name``,
       ``rank``, and ``aliases``.  Allows engineers to define any layer stack
       for custom architectural styles.
    2. ``cfg.arch_style``        — named preset from
       :data:`~harness_skills.models.gate_configs.ARCHITECTURE_STYLE_PRESETS`
       (e.g. ``"hexagonal"``, ``"ddd"``).  An unrecognised style name falls
       through to the next option.
    3. ``cfg.layer_order``       — plain ordered name list; backward-compatible
       default with no alias support.

    Returns
    -------
    list[dict]
        Dicts with keys ``name`` (str), ``rank`` (int), and ``aliases``
        (list[str]), sorted ascending by ``rank``.
    """
    # 1. Explicit layer_definitions override everything
    if cfg.layer_definitions:
        result: list[dict[str, Any]] = []
        for i, ld in enumerate(cfg.layer_definitions):
            if not isinstance(ld, dict):
                continue
            result.append({
                "name": str(ld.get("name", f"layer_{i}")),
                "rank": int(ld.get("rank", i)),
                "aliases": [str(a) for a in ld.get("aliases", [])],
            })
        return sorted(result, key=lambda x: x["rank"])

    # 2. Named architecture style preset
    if cfg.arch_style and cfg.arch_style in ARCHITECTURE_STYLE_PRESETS:
        return list(ARCHITECTURE_STYLE_PRESETS[cfg.arch_style])

    # 3. Backward-compatible plain layer_order list
    return [
        {"name": layer, "rank": i, "aliases": []}
        for i, layer in enumerate(cfg.layer_order)
    ]


def check_architecture(
    project_root: Path, cfg: ArchitectureGateConfig
) -> list[GateFailure]:
    """Detect import layer violations via AST analysis.

    Supports three ways to configure the layer stack (highest priority first):

    1. ``cfg.layer_definitions`` — fully custom layers with name aliases.
    2. ``cfg.arch_style``        — a named preset such as ``"hexagonal"`` or
       ``"ddd"`` (see :data:`~harness_skills.models.gate_configs.\
ARCHITECTURE_STYLE_PRESETS`).
    3. ``cfg.layer_order``       — plain ordered list (backward-compatible).
    """
    import ast as _ast

    layer_defs = _resolve_layer_definitions(cfg)

    # Build term → canonical layer name mapping (canonical name + all aliases)
    term_to_layer: dict[str, str] = {}
    layer_rank: dict[str, int] = {}
    for ld in layer_defs:
        canonical = ld["name"]
        layer_rank[canonical] = ld["rank"]
        term_to_layer[canonical] = canonical
        for alias in ld.get("aliases", []):
            term_to_layer[alias] = canonical

    sev = "warning" if cfg.report_only else "error"
    failures: list[GateFailure] = []

    def _detect_layer(py_file: Path) -> str | None:
        """Return the canonical layer name for *py_file*, or ``None``."""
        parts = py_file.relative_to(project_root).parts
        for part in parts:
            part_lower = part.lower()
            for term, canonical in term_to_layer.items():
                if term in part_lower:
                    return canonical
        return None

    def _module_to_layer(module: str) -> str | None:
        """Return the canonical layer name for *module*, or ``None``."""
        for segment in module.split("."):
            segment_lower = segment.lower()
            for term, canonical in term_to_layer.items():
                if term in segment_lower:
                    return canonical
        return None

    for py_file in sorted(project_root.rglob("*.py")):
        if any(p in py_file.parts for p in {".venv", "venv", "__pycache__", ".git"}):
            continue
        file_layer = _detect_layer(py_file)
        if file_layer is None:
            continue
        try:
            source = py_file.read_text(encoding="utf-8", errors="replace")
            tree = _ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue

        for node in _ast.walk(tree):
            if not isinstance(node, (_ast.Import, _ast.ImportFrom)):
                continue
            imported_module = (
                node.names[0].name
                if isinstance(node, _ast.Import)
                else (node.module or "")
            )
            imported_layer = _module_to_layer(imported_module)
            if imported_layer is None:
                continue
            if layer_rank.get(imported_layer, -1) > layer_rank.get(file_layer, -1):
                rel = _repo_rel(py_file, project_root)
                allowed = ", ".join(
                    ld["name"] for ld in layer_defs
                    if ld["rank"] <= layer_rank[file_layer] and ld["name"] != file_layer
                )
                failures.append(GateFailure(
                    gate_id="architecture", severity=sev,
                    message=(
                        f"Layer violation: {file_layer!r} imports from "
                        f"{imported_layer!r} ({imported_module})."
                    ),
                    file_path=rel, line_number=node.lineno,
                    suggestion=(
                        f"Move `{imported_module}` behind an interface or inject "
                        f"it from a higher layer. {file_layer!r} may only import from: "
                        + (allowed or "(none — this is the innermost layer)") + "."
                    ),
                    rule_id="arch/layer-violation",
                ))
    return failures


def check_principles(
    project_root: Path, cfg: PrinciplesGateConfig
) -> list[GateFailure]:
    """Scan for golden-principles violations and return blocking failures.

    Delegates to :class:`~harness_skills.gates.principles.PrinciplesGate`
    which loads ``.claude/principles.yaml``, maps each principle's
    ``severity`` field to a :class:`GateFailure` severity level, and runs
    built-in AST scanners for automatically detectable violations.

    Severity mapping
    ----------------
    * YAML ``severity: "blocking"`` → ``GateFailure.severity = "error"``
      (fails the gate when ``cfg.fail_on_critical=True``)
    * YAML ``severity: "warning"`` → ``GateFailure.severity = "warning"``
    * YAML ``severity: "suggestion"`` → ``GateFailure.severity = "info"``

    When ``cfg.fail_on_critical=False`` all ``"error"``-level violations are
    downgraded to ``"warning"`` so the gate runs in advisory mode.
    """
    from harness_skills.gates.principles import PrinciplesGate
    from harness_skills.gates.principles import GateConfig as _PrinciplesGateConfig

    gate_cfg = _PrinciplesGateConfig(
        fail_on_critical=getattr(cfg, "fail_on_critical", True),
        fail_on_error=cfg.fail_on_error,
        principles_file=cfg.principles_file,
        rules=list(cfg.rules),
    )
    gate = PrinciplesGate(gate_cfg)
    result = gate.run(project_root)

    failures: list[GateFailure] = []
    for v in result.violations:
        failures.append(GateFailure(
            gate_id="principles",
            severity=v.severity,
            message=v.message,
            file_path=v.file_path,
            line_number=v.line_number,
            suggestion=v.suggestion,
            rule_id=v.rule_id,
        ))
    return failures


def check_docs_freshness(
    project_root: Path, cfg: DocsFreshnessGateConfig
) -> list[GateFailure]:
    """Flag generated harness artifacts that are older than max_staleness_days."""
    import re as _re
    from datetime import datetime, timezone

    ts_re = _re.compile(r"generated_at:\s*([\d\-T:.+Z]+)")
    now = datetime.now(timezone.utc)
    failures: list[GateFailure] = []

    for name in cfg.tracked_files:
        path = project_root / name
        if not path.exists():
            failures.append(GateFailure(
                gate_id="docs_freshness", severity="warning",
                message=f"{name} not found — harness artifacts not yet generated.",
                file_path=name,
                suggestion=f"Run `harness create` to generate {name}.",
                rule_id="docs/missing-artifact",
            ))
            continue

        content = path.read_text(encoding="utf-8", errors="replace")
        m = ts_re.search(content)
        if not m:
            failures.append(GateFailure(
                gate_id="docs_freshness", severity="info",
                message=f"{name} has no embedded generation timestamp.",
                file_path=name,
                suggestion=f"Run `harness update` to regenerate {name} with timestamps.",
                rule_id="docs/missing-timestamp",
            ))
            continue

        try:
            generated_at = datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
            age_days = (now - generated_at).days
            if age_days > cfg.max_staleness_days:
                failures.append(GateFailure(
                    gate_id="docs_freshness", severity="warning",
                    message=(
                        f"{name} is {age_days} days old "
                        f"(threshold: {cfg.max_staleness_days} days)."
                    ),
                    file_path=name,
                    suggestion=f"Run `harness update` to refresh {name}.",
                    rule_id="docs/stale-artifact",
                ))
        except ValueError:
            pass

    return failures


def check_types(
    project_root: Path, cfg: TypesGateConfig
) -> list[GateFailure]:
    """Run mypy or tsc and collect type errors."""
    import re as _re

    failures: list[GateFailure] = []

    if (project_root / "pyproject.toml").exists() or (project_root / "setup.py").exists():
        strict_args = ["--strict"] if cfg.strict else []
        ignore_args: list[str] = []
        for code in cfg.ignore_errors:
            ignore_args += ["--disable-error-code", code]

        rc, stdout, stderr = _run_cmd(
            [sys.executable, "-m", "mypy", ".", "--show-error-codes",
             "--no-error-summary", *strict_args, *ignore_args],
            cwd=project_root,
        )
        if rc != 0:
            pattern = _re.compile(r"^(.+?):(\d+): (error|warning|note): (.+?)(?:\s+\[(.+)\])?$")
            for line in (stdout + stderr).splitlines():
                m = pattern.match(line)
                if not m:
                    continue
                rel_path, lineno, level, msg, code = m.groups()
                if code and code in cfg.ignore_errors:
                    continue
                sev = "error" if level == "error" else "warning"
                failures.append(GateFailure(
                    gate_id="types", severity=sev,
                    message=msg.strip(),
                    file_path=rel_path, line_number=int(lineno),
                    suggestion=(
                        f"Fix the type error in {rel_path}:{lineno}. "
                        "Run `mypy .` locally for full context."
                    ),
                    rule_id=code,
                ))

    elif (project_root / "tsconfig.json").exists():
        rc, stdout, stderr = _run_cmd(
            ["npx", "tsc", "--noEmit", "--pretty", "false"],
            cwd=project_root,
        )
        if rc != 0:
            pattern = _re.compile(r"^(.+?)\((\d+),\d+\):\s+error\s+(TS\d+):\s+(.+)$")
            for line in (stdout + stderr).splitlines():
                m = pattern.match(line)
                if not m:
                    continue
                rel_path, lineno, code, msg = m.groups()
                failures.append(GateFailure(
                    gate_id="types", severity="error",
                    message=msg.strip(),
                    file_path=rel_path, line_number=int(lineno),
                    suggestion=(
                        f"Fix TypeScript error {code} in {rel_path}:{lineno}. "
                        "Run `npx tsc --noEmit` locally for context."
                    ),
                    rule_id=code,
                ))

    return failures


def check_lint(
    project_root: Path, cfg: LintGateConfig
) -> list[GateFailure]:
    """Run ruff or eslint and collect violations."""
    import json as _json

    failures: list[GateFailure] = []

    if (project_root / "pyproject.toml").exists() or (project_root / "ruff.toml").exists():
        select_args: list[str] = []
        for code in cfg.select:
            select_args += ["--select", code]
        ignore_args: list[str] = []
        for code in cfg.ignore:
            ignore_args += ["--ignore", code]
        fix_args = ["--fix"] if cfg.autofix else []

        rc, stdout, _ = _run_cmd(
            [sys.executable, "-m", "ruff", "check", ".",
             "--output-format=json", *select_args, *ignore_args, *fix_args],
            cwd=project_root,
        )
        if rc != 0:
            try:
                violations = _json.loads(stdout)
                for v in violations:
                    loc = v.get("location", {})
                    fix = v.get("fix")
                    fix_hint = fix.get("message") if fix else None
                    failures.append(GateFailure(
                        gate_id="lint", severity="error",
                        message=v.get("message", ""),
                        file_path=_repo_rel(Path(v.get("filename", "")), project_root),
                        line_number=loc.get("row"),
                        suggestion=(
                            fix_hint
                            or f"Run `ruff check --fix .` to auto-fix {v.get('code')} violations."
                        ),
                        rule_id=v.get("code"),
                    ))
            except _json.JSONDecodeError:
                pass

    elif (project_root / ".eslintrc.js").exists() or (project_root / ".eslintrc.json").exists():
        fix_args = ["--fix"] if cfg.autofix else []
        rc, stdout, _ = _run_cmd(
            ["npx", "eslint", ".", "--format=json", *fix_args],
            cwd=project_root,
        )
        if rc != 0:
            try:
                files = _json.loads(stdout)
                for file_result in files:
                    rel = _repo_rel(Path(file_result.get("filePath", "")), project_root)
                    for msg in file_result.get("messages", []):
                        sev = "error" if msg.get("severity") == 2 else "warning"
                        rule = msg.get("ruleId") or "unknown"
                        failures.append(GateFailure(
                            gate_id="lint", severity=sev,
                            message=msg.get("message", ""),
                            file_path=rel, line_number=msg.get("line"),
                            suggestion=(
                                f"Fix ESLint rule {rule} in {rel}:{msg.get('line')}. "
                                "Run `npx eslint --fix .` to auto-fix where possible."
                            ),
                            rule_id=rule,
                        ))
            except _json.JSONDecodeError:
                pass

    return failures


# ---------------------------------------------------------------------------
# Check function registry
# ---------------------------------------------------------------------------

#: Maps gate_id → check function.  Each function matches the signature
#: ``check_fn(project_root: Path, cfg: BaseGateConfig) -> list[GateFailure]``.
_GATE_CHECKS: dict[str, Any] = {
    "regression":     check_regression,
    "coverage":       check_coverage,
    "security":       check_security,
    "performance":    check_performance,
    "architecture":   check_architecture,
    "principles":     check_principles,
    "docs_freshness": check_docs_freshness,
    "types":          check_types,
    "lint":           check_lint,
}


# ---------------------------------------------------------------------------
# GateEvaluator
# ---------------------------------------------------------------------------


class GateEvaluator:
    """Orchestrate gate execution using per-gate config from harness.config.yaml.

    Parameters
    ----------
    project_root:
        Repository root.  Defaults to CWD.
    config_path:
        Path to ``harness.config.yaml``.  Resolved relative to *project_root*
        when not absolute.

    Examples
    --------
    ::

        evaluator = GateEvaluator(project_root=".", config_path="harness.config.yaml")
        summary = evaluator.run()

        if not summary.passed:
            for f in summary.failures:
                print(f"[{f.severity}] {f.gate_id}: {f.message}")
    """

    def __init__(
        self,
        project_root: str | Path = ".",
        config_path: str | Path = "harness.config.yaml",
    ) -> None:
        self.project_root = Path(project_root).resolve()
        cfg_path = Path(config_path)
        if not cfg_path.is_absolute():
            cfg_path = self.project_root / cfg_path
        self._loader = HarnessConfigLoader(cfg_path)

    def run(
        self,
        gate_ids: list[str] | None = None,
        profile: str | None = None,
    ) -> EvaluationSummary:
        """Run all (or a subset of) gates and return an :class:`EvaluationSummary`.

        Parameters
        ----------
        gate_ids:
            Optional list of gate IDs to run.  Defaults to all gates in
            :data:`GATE_CONFIG_CLASSES` order.
        profile:
            Override the active profile declared in ``harness.config.yaml``.

        Returns
        -------
        EvaluationSummary
            Aggregated results.  Inspect ``summary.passed``, ``summary.failures``,
            and ``summary.outcomes`` for full detail.
        """
        gate_cfgs = self._loader.gate_configs(profile)
        # None → run all built-in gates; [] → run no built-in gates (plugins still run)
        ids_to_run = gate_ids if gate_ids is not None else list(GATE_CONFIG_CLASSES.keys())

        outcomes: list[GateOutcome] = []
        all_failures: list[GateFailure] = []

        for gate_id in ids_to_run:
            cfg = gate_cfgs.get(gate_id)
            if cfg is None:
                continue  # Unknown gate — skip

            # Respect enabled flag
            if not cfg.enabled:
                outcomes.append(GateOutcome(
                    gate_id=gate_id,
                    status="skipped",
                    message=f"{gate_id}: disabled in {self._loader.active_profile} profile",
                ))
                continue

            check_fn = _GATE_CHECKS.get(gate_id)
            if check_fn is None:
                continue

            started = time.monotonic()
            try:
                raw_failures = check_fn(self.project_root, cfg)
            except Exception as exc:
                duration_ms = int((time.monotonic() - started) * 1000)
                outcomes.append(GateOutcome(
                    gate_id=gate_id, status="error",
                    duration_ms=duration_ms,
                    message=f"{gate_id} gate raised an exception: {exc}",
                    failures=[GateFailure(
                        gate_id=gate_id, severity="error",
                        message=f"Gate runner raised an exception: {exc}",
                        suggestion=(
                            f"Ensure the tool required by the {gate_id} gate is "
                            "installed and accessible in PATH."
                        ),
                    )],
                ))
                continue

            duration_ms = int((time.monotonic() - started) * 1000)

            # Downgrade errors to warnings when fail_on_error=false
            effective_failures: list[GateFailure] = []
            if not cfg.fail_on_error:
                for f in raw_failures:
                    if f.severity == "error":
                        f = GateFailure(
                            gate_id=f.gate_id, severity="warning",
                            message=f.message, file_path=f.file_path,
                            line_number=f.line_number, suggestion=f.suggestion,
                            rule_id=f.rule_id,
                        )
                    effective_failures.append(f)
            else:
                effective_failures = raw_failures

            blocking = any(f.severity == "error" for f in effective_failures)
            status = "failed" if blocking else ("passed" if not effective_failures else "passed")
            n = len(effective_failures)
            errors = sum(1 for f in effective_failures if f.severity == "error")
            msg = (
                f"{gate_id}: passed"
                if n == 0
                else f"{gate_id}: {n} issue(s) ({errors} blocking)"
            )

            outcomes.append(GateOutcome(
                gate_id=gate_id, status=status,
                duration_ms=duration_ms,
                failures=effective_failures,
                message=msg,
            ))
            all_failures.extend(effective_failures)

        # ── Plugin gates ────────────────────────────────────────────────────
        # Load and run custom plugin gates defined under
        # ``profiles.<active>.gates.plugins`` in harness.config.yaml.
        # Each plugin gate is a shell command; exit 0 = pass, non-zero = fail
        # (or warning when fail_on_error: false).
        raw_plugin_defs = self._loader.plugin_gates(profile)
        if raw_plugin_defs:
            plugin_cfgs = load_plugin_gates({
                "gates": {"plugins": raw_plugin_defs}
            })
            plugin_base_results = run_plugin_gates(plugin_cfgs)
            for base_result in plugin_base_results:
                outcome = _plugin_result_to_outcome(base_result)
                outcomes.append(outcome)
                all_failures.extend(outcome.failures)

        # Aggregate summary
        passed = all(o.status in ("passed", "skipped") for o in outcomes)
        blocking_count = sum(1 for f in all_failures if f.severity == "error")
        return EvaluationSummary(
            passed=passed,
            total_gates=len(outcomes),
            passed_gates=sum(1 for o in outcomes if o.status == "passed"),
            failed_gates=sum(1 for o in outcomes if o.status == "failed"),
            skipped_gates=sum(1 for o in outcomes if o.status == "skipped"),
            total_failures=len(all_failures),
            blocking_failures=blocking_count,
            outcomes=outcomes,
            failures=all_failures,
        )


# ---------------------------------------------------------------------------
# Public convenience function
# ---------------------------------------------------------------------------


def run_gates(
    project_root: str | Path = ".",
    config_path: str | Path = "harness.config.yaml",
    gate_ids: list[str] | None = None,
    profile: str | None = None,
) -> EvaluationSummary:
    """Run all configured gates and return an :class:`EvaluationSummary`.

    This is the primary entry-point for ``harness evaluate``.

    Parameters
    ----------
    project_root:
        Repository root directory.
    config_path:
        Path to ``harness.config.yaml`` (absolute or relative to *project_root*).
    gate_ids:
        Optional subset of gate IDs to run.  Defaults to all.
    profile:
        Profile override; defaults to the ``active_profile`` in the YAML file.

    Returns
    -------
    EvaluationSummary
        Inspect ``summary.passed``, ``summary.failures``, and ``summary.outcomes``.

    Examples
    --------
    ::

        summary = run_gates(".", "harness.config.yaml")
        print(summary)  # "[PASSED] 7/9 gates passed (2 skipped, 0 blocking failures)"

        if not summary.passed:
            for failure in summary.failures:
                if failure.severity == "error":
                    print(f"  {failure.gate_id}: {failure.message}")
                    if failure.suggestion:
                        print(f"    → {failure.suggestion}")
    """
    evaluator = GateEvaluator(project_root=project_root, config_path=config_path)
    return evaluator.run(gate_ids=gate_ids, profile=profile)
