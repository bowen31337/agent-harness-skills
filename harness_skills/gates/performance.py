"""
harness_skills/gates/performance.py
=====================================
Performance benchmark gate — evaluates timing spans against configurable
per-rule thresholds loaded from a YAML rules file.

Default thresholds file: ``.harness/perf-thresholds.yml``

The gate supports two input modes:

  1. **File** — reads span data from a JSON file (``config.spans_file``).
  2. **Direct** — accepts a list of :class:`SpanRecord` objects at call time
     via ``gate.run(spans=[…])``.

Each rule in the YAML is evaluated independently:

* ``api_endpoint_latency``  — HTTP server-side spans ≤ 500 ms  (p99, error)
* ``span_latency``           — any OpenTelemetry span ≤ 2 000 ms (p99, error)
* ``db_query_latency``       — DB query spans ≤ 200 ms  (p99, warning)
* ``external_http_latency``  — outbound HTTP spans ≤ 1 000 ms (warning)
* ``e2e_p95_budget``         — end-to-end p95 ≤ 300 ms (warning)

Rules are skipped with ``enabled: false`` and downgraded with
``severity: warning``.  An optional baseline comparison fires when
``baseline.enabled: true`` and a baseline spans file is available.

CLI usage::

    python -m harness_skills.gates.performance \\
        --thresholds .harness/perf-thresholds.yml \\
        --spans perf-spans.json \\
        --output perf-report.json

Programmatic usage::

    from harness_skills.gates.performance import PerformanceGate, SpanRecord
    from harness_skills.models.gate_configs import PerformanceGateConfig

    spans = [
        SpanRecord("GET /api/users",      "http_endpoint", duration_ms=430),
        SpanRecord("SELECT * FROM users", "db_query",      duration_ms=55),
    ]
    gate   = PerformanceGate(PerformanceGateConfig())
    result = gate.run(spans=spans)
    if not result.passed:
        result.print_violations()
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

try:
    import yaml  # type: ignore[import]
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

from harness_skills.models.gate_configs import PerformanceGateConfig


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

SpanType = Literal[
    "http_endpoint",   # span.kind = server  (api_endpoint_latency, e2e_p95_budget)
    "span",            # any generic OpenTelemetry span  (span_latency)
    "db_query",        # spans tagged with db.system  (db_query_latency)
    "http_client",     # span.kind = client  (external_http_latency)
]

Severity = Literal["error", "warning"]


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class SpanRecord:
    """A single timing observation from a trace or benchmark run.

    Parameters
    ----------
    name:
        Human-readable span name (e.g. ``"GET /api/users"``).
    span_type:
        One of ``"http_endpoint"``, ``"span"``, ``"db_query"``,
        ``"http_client"``.  Used to match rules in the thresholds file.
    duration_ms:
        Elapsed time in milliseconds for this single observation.
    attributes:
        Optional key-value pairs from the span (e.g.
        ``{"http.route": "/api/users", "http.status_code": 200}``).
    """

    name: str
    span_type: str
    duration_ms: float
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ThresholdViolation:
    """A single rule breach detected by :class:`PerformanceGate`.

    Attributes
    ----------
    rule_id:
        The ``id`` field from the thresholds YAML rule.
    description:
        Human-readable rule description (from the YAML ``description``
        field).
    severity:
        ``"error"`` blocks the gate; ``"warning"`` annotates only.
    span_name:
        Name of the span or group that breached the rule.
    measured_ms:
        The computed percentile (or mean) duration that was evaluated,
        in milliseconds.
    threshold_ms:
        The configured upper limit in milliseconds.
    percentile:
        The percentile used for aggregation (e.g. ``"p99"``, ``"p95"``).
    suggestion:
        Optional actionable guidance taken from the YAML ``suggestion``
        field.
    """

    rule_id: str
    description: str
    severity: Severity
    span_name: str
    measured_ms: float
    threshold_ms: float
    percentile: str = "p99"
    suggestion: str = ""

    def summary(self) -> str:
        """One-line human-readable summary."""
        return (
            f"[{self.severity.upper():7s}] {self.rule_id:<30s} "
            f"span={self.span_name!r:<30s} "
            f"{self.measured_ms:.0f} ms > {self.threshold_ms:.0f} ms "
            f"({self.percentile})"
        )


@dataclass
class PerformanceGateResult:
    """Aggregate result returned by :class:`PerformanceGate`.

    Attributes
    ----------
    passed:
        ``True`` when all *error*-severity rules pass (or
        ``fail_on_error=False``).
    violations:
        All threshold breaches found (both ``error`` and ``warning``
        severity).
    rules_evaluated:
        Number of enabled rules that were checked.
    spans_evaluated:
        Total number of span records that were assessed.
    """

    passed: bool
    violations: List[ThresholdViolation] = field(default_factory=list)
    rules_evaluated: int = 0
    spans_evaluated: int = 0

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def errors(self) -> List[ThresholdViolation]:
        """Return only error-severity violations."""
        return [v for v in self.violations if v.severity == "error"]

    def warnings(self) -> List[ThresholdViolation]:
        """Return only warning-severity violations."""
        return [v for v in self.violations if v.severity == "warning"]

    # ------------------------------------------------------------------
    # Output helpers
    # ------------------------------------------------------------------

    def print_violations(self) -> None:
        """Print all violations to stdout."""
        if not self.violations:
            print("  \u2713  No threshold violations found.")
            return
        for v in self.violations:
            print(f"  {v.summary()}")
            if v.suggestion:
                print(f"      \u2192 {v.suggestion.strip()}")

    def to_report_dict(self) -> Dict[str, Any]:
        """Serialise to the ``perf-report.json`` schema consumed by
        ``.harness/perf_summary.py`` and CI pipelines."""
        return {
            "summary": {
                "passed": self.passed,
                "total_gates": self.rules_evaluated,
                "passed_gates": self.rules_evaluated - len(self.violations),
                "blocking_failures": len(self.errors()),
                "warnings": len(self.warnings()),
                "spans_evaluated": self.spans_evaluated,
            },
            "failures": [
                {
                    "rule_id": v.rule_id,
                    "severity": v.severity,
                    "span_name": v.span_name,
                    "measured_ms": v.measured_ms,
                    "threshold_ms": v.threshold_ms,
                    "percentile": v.percentile,
                    "suggestion": v.suggestion,
                    "message": v.description,
                }
                for v in self.violations
            ],
        }

    def __str__(self) -> str:
        lines = [
            f"PerformanceGate: {'PASSED' if self.passed else 'FAILED'}",
            f"  Rules evaluated  : {self.rules_evaluated}",
            f"  Spans evaluated  : {self.spans_evaluated}",
            f"  Violations       : {len(self.violations)} "
            f"({len(self.errors())} error, {len(self.warnings())} warning)",
        ]
        if self.violations:
            lines.append("")
            for v in self.violations:
                lines.append("  " + v.summary())
                if v.suggestion:
                    lines.append(f"      \u2192 {v.suggestion.strip()}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers — percentile calculation
# ---------------------------------------------------------------------------

_PERCENTILE_MAP: Dict[str, float] = {
    "p50":    0.50,
    "p75":    0.75,
    "p90":    0.90,
    "p95":    0.95,
    "p99":    0.99,
    "p100":   1.00,
    "max":    1.00,
    "min":    0.00,
    "median": 0.50,
    "mean":   -1.0,  # special case — handled below
}


def _compute_percentile(values: List[float], pct_key: str) -> float:
    """Compute *pct_key* percentile of *values* using linear interpolation.

    Recognised keys: ``p50``, ``p75``, ``p90``, ``p95``, ``p99``,
    ``p100``, ``max``, ``min``, ``median``, ``mean``.
    Unrecognised keys fall back to ``p99``.
    """
    if not values:
        return 0.0

    key = pct_key.lower()
    if key == "mean":
        return statistics.mean(values)
    if key == "min":
        return min(values)

    q = _PERCENTILE_MAP.get(key, 0.99)
    sorted_vals = sorted(values)
    idx = q * (len(sorted_vals) - 1)
    lo = int(idx)
    hi = lo + 1
    if hi >= len(sorted_vals):
        return sorted_vals[-1]
    return sorted_vals[lo] + (idx - lo) * (sorted_vals[hi] - sorted_vals[lo])


def _check_operator(measured: float, operator: str, threshold: float) -> bool:
    """Return ``True`` when the constraint is **satisfied** (rule passes).

    Operators
    ---------
    ``lte`` → measured ≤ threshold  (latency must not exceed the limit)
    ``gte`` → measured ≥ threshold
    ``lt``  → measured < threshold
    ``gt``  → measured > threshold
    ``eq``  → measured == threshold  (exact; rarely used for timing)

    Unknown operators return ``True`` (conservative pass) to avoid
    false positives from typos in the YAML.
    """
    if operator == "lte":
        return measured <= threshold
    if operator == "gte":
        return measured >= threshold
    if operator == "lt":
        return measured < threshold
    if operator == "gt":
        return measured > threshold
    if operator == "eq":
        return abs(measured - threshold) < 1e-9
    return True  # unknown operator → pass


# ---------------------------------------------------------------------------
# YAML / JSON loaders
# ---------------------------------------------------------------------------


def _load_thresholds(path: Path) -> Dict[str, Any]:
    """Load the thresholds config dict from *path* (YAML preferred, JSON fallback).

    Returns a dict with ``version``, ``defaults``, ``rules``, and
    optionally ``baseline`` keys.

    Raises
    ------
    FileNotFoundError
        When *path* does not exist on disk.
    ValueError
        When the file cannot be parsed as YAML or JSON.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"Thresholds file not found: '{path}'. "
            "Create it at .harness/perf-thresholds.yml or pass --thresholds <file>."
        )

    text = path.read_text(encoding="utf-8")

    if _YAML_AVAILABLE:
        try:
            data = yaml.safe_load(text)
            if isinstance(data, dict):
                return data
        except yaml.YAMLError:
            pass  # fall through to JSON

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Cannot parse '{path}' as YAML or JSON: {exc}"
        ) from exc


def _load_spans_file(path: Path) -> List[SpanRecord]:
    """Load span records from a JSON file.

    The file must be a JSON array where each element has at least::

        {"name": "...", "span_type": "...", "duration_ms": 123.4}

    An optional ``"attributes"`` object per element is also supported.

    Raises
    ------
    FileNotFoundError
        When *path* does not exist.
    ValueError
        When the file is not valid JSON or is not a list.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"Spans file not found: '{path}'. "
            "Run your benchmark harness to produce this file first."
        )

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Cannot parse '{path}' as JSON: {exc}") from exc

    if not isinstance(raw, list):
        raise ValueError(
            f"Spans file '{path}' must contain a JSON array of span objects, "
            f"got {type(raw).__name__}."
        )

    spans: List[SpanRecord] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        spans.append(
            SpanRecord(
                name=str(item.get("name", "unknown")),
                span_type=str(item.get("span_type", "span")),
                duration_ms=float(item.get("duration_ms", 0.0)),
                attributes=item.get("attributes") or {},
            )
        )
    return spans


# ---------------------------------------------------------------------------
# Baseline regression helper
# ---------------------------------------------------------------------------


def _check_baseline_regression(
    *,
    current_spans: List[SpanRecord],
    baseline_path: Path,
    regression_threshold_pct: float,
    severity: str,
    violations: List[ThresholdViolation],
) -> None:
    """Append regression violations comparing *current_spans* to *baseline_path*.

    The baseline file uses the same JSON schema as the spans file.  For
    each span name present in both datasets, the **mean** duration is
    compared.  When the current mean is more than *regression_threshold_pct* %
    slower than the baseline mean, a violation is appended with the
    ``"baseline_regression"`` rule ID.

    Silent no-op when the baseline file is unavailable (to avoid blocking
    CI on the very first run before a baseline exists).
    """
    try:
        baseline_spans = _load_spans_file(baseline_path)
    except (FileNotFoundError, ValueError):
        return  # baseline not yet available — skip gracefully

    # Build mean per (span_type, name) key
    def _group_means(spans: List[SpanRecord]) -> Dict[str, float]:
        groups: Dict[str, List[float]] = {}
        for s in spans:
            key = f"{s.span_type}:{s.name}"
            groups.setdefault(key, []).append(s.duration_ms)
        return {k: statistics.mean(v) for k, v in groups.items()}

    baseline_means = _group_means(baseline_spans)
    current_means = _group_means(current_spans)

    for key, current_mean in current_means.items():
        baseline_mean = baseline_means.get(key)
        if baseline_mean is None or baseline_mean <= 0:
            continue

        pct_change = ((current_mean - baseline_mean) / baseline_mean) * 100.0
        if pct_change > regression_threshold_pct:
            _, span_name = key.split(":", 1)
            allowed_ms = baseline_mean * (1 + regression_threshold_pct / 100.0)
            violations.append(
                ThresholdViolation(
                    rule_id="baseline_regression",
                    description=(
                        f"Regression vs baseline: {pct_change:.1f}% slower "
                        f"(baseline mean: {baseline_mean:.0f} ms, "
                        f"current mean: {current_mean:.0f} ms)"
                    ),
                    severity=severity,  # type: ignore[arg-type]
                    span_name=span_name,
                    measured_ms=round(current_mean, 2),
                    threshold_ms=round(allowed_ms, 2),
                    percentile="mean",
                    suggestion=(
                        "Compare the current trace with the baseline to identify "
                        "newly introduced latency.  Run with --baseline <prev-run> "
                        "to see the diff."
                    ),
                )
            )


# ---------------------------------------------------------------------------
# PerformanceGate
# ---------------------------------------------------------------------------


class PerformanceGate:
    """Evaluate timing spans against configurable per-rule latency thresholds.

    Instantiate with a :class:`~harness_skills.models.gate_configs.PerformanceGateConfig`
    (or leave ``config=None`` to accept all defaults) and call
    :meth:`run` with either a list of :class:`SpanRecord` objects or let
    the gate load them from ``config.spans_file``.

    Example::

        from pathlib import Path
        from harness_skills.gates.performance import PerformanceGate, SpanRecord
        from harness_skills.models.gate_configs import PerformanceGateConfig

        spans = [
            SpanRecord("GET /api/users",      "http_endpoint", duration_ms=430),
            SpanRecord("GET /api/users",      "http_endpoint", duration_ms=510),
            SpanRecord("SELECT * FROM users", "db_query",      duration_ms=55),
        ]

        gate   = PerformanceGate(PerformanceGateConfig(
            thresholds_file=".harness/perf-thresholds.yml",
        ))
        result = gate.run(spans=spans)
        print(result)
    """

    def __init__(self, config: Optional[PerformanceGateConfig] = None) -> None:
        self.config: PerformanceGateConfig = config or PerformanceGateConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        *,
        spans: Optional[List[SpanRecord]] = None,
        repo_root: Path = Path("."),
    ) -> PerformanceGateResult:
        """Execute the gate and return a :class:`PerformanceGateResult`.

        Parameters
        ----------
        spans:
            Span records to evaluate.  When ``None``, the gate reads from
            ``config.spans_file`` relative to *repo_root*.
        repo_root:
            Absolute (or CWD-relative) path to the repository root.
            All relative paths in ``config`` are resolved against this
            directory.
        """
        repo_root = repo_root.resolve()
        cfg = self.config

        # ── 1. Load thresholds YAML ─────────────────────────────────────
        thresholds_path = Path(cfg.thresholds_file)
        if not thresholds_path.is_absolute():
            thresholds_path = (repo_root / thresholds_path).resolve()

        try:
            thresholds = _load_thresholds(thresholds_path)
        except (FileNotFoundError, ValueError) as exc:
            violation = ThresholdViolation(
                rule_id="thresholds_file_missing",
                description=str(exc),
                severity="error",
                span_name="(none)",
                measured_ms=0.0,
                threshold_ms=0.0,
                suggestion=(
                    "Create .harness/perf-thresholds.yml or pass "
                    "--thresholds <path>."
                ),
            )
            return PerformanceGateResult(
                passed=not cfg.fail_on_error,
                violations=[violation],
                rules_evaluated=0,
                spans_evaluated=0,
            )

        # ── 2. Load spans ───────────────────────────────────────────────
        if spans is None:
            spans_path = Path(cfg.spans_file)
            if not spans_path.is_absolute():
                spans_path = (repo_root / spans_path).resolve()
            try:
                spans = _load_spans_file(spans_path)
            except (FileNotFoundError, ValueError) as exc:
                violation = ThresholdViolation(
                    rule_id="spans_file_missing",
                    description=str(exc),
                    severity="error",
                    span_name="(none)",
                    measured_ms=0.0,
                    threshold_ms=0.0,
                    suggestion=(
                        "Run your benchmark harness to produce the spans file "
                        "first, or pass spans=[…] directly."
                    ),
                )
                return PerformanceGateResult(
                    passed=not cfg.fail_on_error,
                    violations=[violation],
                    rules_evaluated=0,
                    spans_evaluated=0,
                )

        # ── 3. Extract global defaults from YAML ────────────────────────
        defaults = thresholds.get("defaults", {}) or {}
        global_percentile: str = str(defaults.get("percentile", "p99"))
        fail_on_breach: bool = bool(defaults.get("fail_on_breach", True))

        # config.fail_on_error overrides the YAML's fail_on_breach
        effective_fail: bool = cfg.fail_on_error and fail_on_breach

        # ── 4. Evaluate each rule ────────────────────────────────────────
        rules = thresholds.get("rules", []) or []
        violations: List[ThresholdViolation] = []
        rules_evaluated = 0

        for rule in rules:
            if not isinstance(rule, dict):
                continue
            if not rule.get("enabled", True):
                continue
            rules_evaluated += 1

            rule_id: str = str(rule.get("id", "unknown_rule"))
            description: str = str(rule.get("description", ""))
            severity: Severity = str(  # type: ignore[assignment]
                rule.get("severity", "error")
            )
            suggestion: str = str(rule.get("suggestion", "")).strip()

            selector: Dict[str, Any] = rule.get("selector", {}) or {}
            selector_type: str = str(selector.get("type", "span"))

            threshold_cfg: Dict[str, Any] = rule.get("threshold", {}) or {}
            threshold_value: float = float(threshold_cfg.get("value", 0))
            operator: str = str(threshold_cfg.get("operator", "lte"))
            percentile_key: str = str(
                threshold_cfg.get("percentile", global_percentile)
            )

            # Select spans matching this rule's selector type
            matching = [s for s in spans if s.span_type == selector_type]
            if not matching:
                # No spans of this type — rule skipped (no data to evaluate)
                continue

            # Group observations by span name, then evaluate each group
            groups: Dict[str, List[float]] = {}
            for s in matching:
                groups.setdefault(s.name, []).append(s.duration_ms)

            for span_name, durations in groups.items():
                measured = _compute_percentile(durations, percentile_key)
                if not _check_operator(measured, operator, threshold_value):
                    violations.append(
                        ThresholdViolation(
                            rule_id=rule_id,
                            description=description,
                            severity=severity,
                            span_name=span_name,
                            measured_ms=round(measured, 2),
                            threshold_ms=threshold_value,
                            percentile=percentile_key,
                            suggestion=suggestion,
                        )
                    )

        # ── 5. Optional baseline regression check ───────────────────────
        baseline_cfg: Dict[str, Any] = thresholds.get("baseline", {}) or {}
        if baseline_cfg.get("enabled", False) and cfg.baseline_file:
            baseline_path = Path(cfg.baseline_file)
            if not baseline_path.is_absolute():
                baseline_path = (repo_root / baseline_path).resolve()

            regression_pct = float(
                baseline_cfg.get(
                    "regression_threshold_pct",
                    cfg.regression_threshold_pct,
                )
            )
            _check_baseline_regression(
                current_spans=spans,
                baseline_path=baseline_path,
                regression_threshold_pct=regression_pct,
                severity=str(baseline_cfg.get("severity", "warning")),
                violations=violations,
            )

        # ── 6. Determine pass / fail ────────────────────────────────────
        has_errors = any(v.severity == "error" for v in violations)
        passed = not has_errors or not effective_fail

        result = PerformanceGateResult(
            passed=passed,
            violations=violations,
            rules_evaluated=rules_evaluated,
            spans_evaluated=len(spans),
        )

        # ── 7. Optionally write output file ─────────────────────────────
        if cfg.output_file:
            out_path = Path(cfg.output_file)
            if not out_path.is_absolute():
                out_path = (repo_root / out_path).resolve()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                json.dumps(result.to_report_dict(), indent=2),
                encoding="utf-8",
            )

        return result


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m harness_skills.gates.performance",
        description=(
            "Performance benchmark gate — enforce per-span latency thresholds "
            "loaded from a YAML rules file and block PRs that breach them."
        ),
    )
    p.add_argument(
        "--thresholds",
        default=".harness/perf-thresholds.yml",
        metavar="FILE",
        dest="thresholds_file",
        help=(
            "Path to the threshold rules YAML "
            "(default: .harness/perf-thresholds.yml)."
        ),
    )
    p.add_argument(
        "--spans",
        default="perf-spans.json",
        metavar="FILE",
        dest="spans_file",
        help="Path to the JSON spans file (default: perf-spans.json).",
    )
    p.add_argument(
        "--baseline",
        default="",
        metavar="FILE",
        dest="baseline_file",
        help="Path to baseline spans JSON for regression comparison (optional).",
    )
    p.add_argument(
        "--output",
        default="",
        metavar="FILE",
        dest="output_file",
        help="Write perf-report.json to this path (optional).",
    )
    p.add_argument(
        "--root",
        default=".",
        metavar="PATH",
        help="Repository root for resolving relative paths (default: .).",
    )
    p.add_argument(
        "--no-fail-on-error",
        action="store_true",
        help=(
            "Emit violations but exit 0 even when error-severity rules are "
            "breached.  Useful for advisory / warning-only runs."
        ),
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-violation output; print only the summary line.",
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:  # pragma: no cover
    """CLI entry-point; returns an exit code (0 = pass, 1 = fail)."""
    args = _build_parser().parse_args(argv)

    cfg = PerformanceGateConfig(
        thresholds_file=args.thresholds_file,
        spans_file=args.spans_file,
        baseline_file=args.baseline_file,
        output_file=args.output_file,
        fail_on_error=not args.no_fail_on_error,
    )

    result = PerformanceGate(cfg).run(repo_root=Path(args.root))

    if not args.quiet:
        print(result)
        if cfg.output_file:
            print(f"\n  Report written to: {cfg.output_file}")

    return 0 if result.passed else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
