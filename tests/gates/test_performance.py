"""
tests/gates/test_performance.py
================================
Unit and integration tests for :mod:`harness_skills.gates.performance`.

Test strategy
-------------
* **Threshold evaluation** — rules with ``lte`` / ``gte`` / ``lt`` / ``gt`` /
  ``eq`` operators are each tested at the boundary (exact, just-over, just-under).
* **Percentile calculation** — ``p95``, ``p99``, ``mean``, ``min``, ``max`` are
  spot-checked against hand-calculated values.
* **Multi-rule YAML** — a fixture YAML containing rules for
  ``api_endpoint_latency`` and ``span_latency`` is evaluated end-to-end.
* **Rule selector filtering** — spans of the wrong ``span_type`` are ignored by a
  rule.
* **Disabled rules** — rules with ``enabled: false`` are not evaluated.
* **Missing thresholds file** — gate returns an error violation.
* **Missing spans file** — gate returns an error violation.
* **Malformed spans file** — gate returns an error violation.
* **fail_on_error=False** — violations are recorded but gate passes.
* **Baseline regression** — regression above/below the threshold.
* **Output file** — ``config.output_file`` causes a JSON report to be written.
* **to_report_dict()** — verifies the schema matches what ``perf_summary.py``
  expects (``summary.total_gates``, ``failures[*].rule_id``, etc.).
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from harness_skills.gates.performance import (
    PerformanceGate,
    PerformanceGateResult,
    SpanRecord,
    ThresholdViolation,
    _check_operator,
    _compute_percentile,
    _load_spans_file,
    _load_thresholds,
)
from harness_skills.models.gate_configs import PerformanceGateConfig


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _write_thresholds(path: Path, rules: list[dict]) -> Path:
    """Write a minimal thresholds YAML to *path*."""
    import yaml  # optional dep — skip tests if not installed

    data = {
        "version": 1,
        "defaults": {"fail_on_breach": True, "percentile": "p99"},
        "rules": rules,
    }
    path.write_text(yaml.dump(data), encoding="utf-8")
    return path


def _write_spans(path: Path, spans: list[dict]) -> Path:
    """Write span records as a JSON array to *path*."""
    path.write_text(json.dumps(spans), encoding="utf-8")
    return path


def _make_span(
    name: str = "GET /api/test",
    span_type: str = "http_endpoint",
    duration_ms: float = 100.0,
) -> SpanRecord:
    return SpanRecord(name=name, span_type=span_type, duration_ms=duration_ms)


# ---------------------------------------------------------------------------
# _compute_percentile
# ---------------------------------------------------------------------------


class TestComputePercentile:
    def test_empty_returns_zero(self) -> None:
        assert _compute_percentile([], "p99") == 0.0

    def test_single_value_all_percentiles(self) -> None:
        for key in ("p50", "p75", "p90", "p95", "p99", "p100", "max", "min", "median"):
            assert _compute_percentile([42.0], key) == 42.0

    def test_mean(self) -> None:
        assert _compute_percentile([10.0, 20.0, 30.0], "mean") == pytest.approx(20.0)

    def test_min(self) -> None:
        assert _compute_percentile([30.0, 10.0, 20.0], "min") == 10.0

    def test_p99_two_values(self) -> None:
        # With 2 values, p99 should be very close to the max
        result = _compute_percentile([100.0, 200.0], "p99")
        assert result > 195.0

    def test_p95_five_values(self) -> None:
        values = [100.0, 200.0, 300.0, 400.0, 500.0]
        # p95 of 5 values: idx = 0.95 * 4 = 3.8  → 400 + 0.8*(500-400) = 480
        assert _compute_percentile(values, "p95") == pytest.approx(480.0)

    def test_unknown_key_falls_back_to_p99(self) -> None:
        values = [100.0, 200.0, 300.0]
        result_unknown = _compute_percentile(values, "p999_undefined")
        result_p99 = _compute_percentile(values, "p99")
        assert result_unknown == pytest.approx(result_p99)


# ---------------------------------------------------------------------------
# _check_operator
# ---------------------------------------------------------------------------


class TestCheckOperator:
    def test_lte_pass(self) -> None:
        assert _check_operator(500.0, "lte", 500.0) is True
        assert _check_operator(499.9, "lte", 500.0) is True

    def test_lte_fail(self) -> None:
        assert _check_operator(500.1, "lte", 500.0) is False

    def test_gte_pass(self) -> None:
        assert _check_operator(500.0, "gte", 500.0) is True
        assert _check_operator(500.1, "gte", 500.0) is True

    def test_gte_fail(self) -> None:
        assert _check_operator(499.9, "gte", 500.0) is False

    def test_lt_pass(self) -> None:
        assert _check_operator(499.9, "lt", 500.0) is True

    def test_lt_fail_at_boundary(self) -> None:
        assert _check_operator(500.0, "lt", 500.0) is False

    def test_gt_pass(self) -> None:
        assert _check_operator(500.1, "gt", 500.0) is True

    def test_gt_fail_at_boundary(self) -> None:
        assert _check_operator(500.0, "gt", 500.0) is False

    def test_eq_pass(self) -> None:
        assert _check_operator(500.0, "eq", 500.0) is True

    def test_eq_fail(self) -> None:
        assert _check_operator(500.1, "eq", 500.0) is False

    def test_unknown_operator_is_conservative_pass(self) -> None:
        assert _check_operator(9999.0, "bogus_op", 1.0) is True


# ---------------------------------------------------------------------------
# _load_spans_file
# ---------------------------------------------------------------------------


class TestLoadSpansFile:
    def test_loads_valid_file(self, tmp_path: Path) -> None:
        p = _write_spans(tmp_path / "spans.json", [
            {"name": "GET /api/test", "span_type": "http_endpoint", "duration_ms": 100},
        ])
        spans = _load_spans_file(p)
        assert len(spans) == 1
        assert spans[0].name == "GET /api/test"
        assert spans[0].span_type == "http_endpoint"
        assert spans[0].duration_ms == pytest.approx(100.0)

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            _load_spans_file(tmp_path / "nonexistent.json")

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{not: json}", encoding="utf-8")
        with pytest.raises(ValueError, match="Cannot parse"):
            _load_spans_file(bad)

    def test_non_list_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "obj.json"
        p.write_text('{"key": "value"}', encoding="utf-8")
        with pytest.raises(ValueError, match="JSON array"):
            _load_spans_file(p)

    def test_skips_non_dict_items(self, tmp_path: Path) -> None:
        p = tmp_path / "mixed.json"
        p.write_text(
            json.dumps([
                {"name": "ok", "span_type": "span", "duration_ms": 10},
                "not a dict",
                42,
            ]),
            encoding="utf-8",
        )
        spans = _load_spans_file(p)
        assert len(spans) == 1

    def test_optional_attributes_loaded(self, tmp_path: Path) -> None:
        p = _write_spans(tmp_path / "spans.json", [
            {
                "name": "query",
                "span_type": "db_query",
                "duration_ms": 55,
                "attributes": {"db.system": "postgresql"},
            }
        ])
        spans = _load_spans_file(p)
        assert spans[0].attributes == {"db.system": "postgresql"}


# ---------------------------------------------------------------------------
# _load_thresholds
# ---------------------------------------------------------------------------


class TestLoadThresholds:
    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            _load_thresholds(tmp_path / "missing.yml")

    def test_loads_json_fallback(self, tmp_path: Path) -> None:
        p = tmp_path / "thresholds.json"
        p.write_text(
            json.dumps({"version": 1, "defaults": {}, "rules": []}),
            encoding="utf-8",
        )
        data = _load_thresholds(p)
        assert data["version"] == 1

    def test_invalid_file_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.yml"
        p.write_text("---\n[invalid yaml: :", encoding="utf-8")
        # If PyYAML is available, it may raise; if not, JSON parse fails too
        # Either way a ValueError (or FileNotFoundError) is expected
        try:
            import yaml  # noqa: F401
            with pytest.raises((ValueError, Exception)):
                _load_thresholds(p)
        except ImportError:
            with pytest.raises(ValueError):
                _load_thresholds(p)


# ---------------------------------------------------------------------------
# PerformanceGate — core rule evaluation
# ---------------------------------------------------------------------------

pytest.importorskip("yaml", reason="PyYAML required for YAML-based gate tests")


class TestPerformanceGateRuleEvaluation:
    """Test single-rule evaluation end-to-end via the gate."""

    def _gate_with_rule(
        self,
        tmp_path: Path,
        rule: dict,
        spans: list[SpanRecord],
        fail_on_error: bool = True,
    ) -> PerformanceGateResult:
        thresholds_path = _write_thresholds(tmp_path / "thresholds.yml", [rule])
        cfg = PerformanceGateConfig(
            thresholds_file=str(thresholds_path),
            fail_on_error=fail_on_error,
        )
        return PerformanceGate(cfg).run(spans=spans, repo_root=tmp_path)

    def test_api_endpoint_latency_passes_under_threshold(
        self, tmp_path: Path
    ) -> None:
        rule = {
            "id": "api_endpoint_latency",
            "description": "No API endpoint > 500 ms",
            "enabled": True,
            "selector": {"type": "http_endpoint"},
            "threshold": {"metric": "duration_ms", "operator": "lte", "value": 500},
            "severity": "error",
        }
        spans = [_make_span(duration_ms=400.0), _make_span(duration_ms=450.0)]
        result = self._gate_with_rule(tmp_path, rule, spans)
        assert result.passed
        assert result.violations == []

    def test_api_endpoint_latency_fails_over_threshold(
        self, tmp_path: Path
    ) -> None:
        rule = {
            "id": "api_endpoint_latency",
            "description": "No API endpoint > 500 ms",
            "enabled": True,
            "selector": {"type": "http_endpoint"},
            "threshold": {"metric": "duration_ms", "operator": "lte", "value": 500},
            "severity": "error",
        }
        # A single observation well above 500 ms
        spans = [_make_span(duration_ms=800.0)]
        result = self._gate_with_rule(tmp_path, rule, spans)
        assert not result.passed
        assert len(result.violations) == 1
        v = result.violations[0]
        assert v.rule_id == "api_endpoint_latency"
        assert v.severity == "error"
        assert v.threshold_ms == 500.0

    def test_span_latency_rule_uses_2000ms(self, tmp_path: Path) -> None:
        rule = {
            "id": "span_latency",
            "description": "No span > 2000 ms",
            "enabled": True,
            "selector": {"type": "span"},
            "threshold": {"metric": "duration_ms", "operator": "lte", "value": 2000},
            "severity": "error",
        }
        good = SpanRecord("process_task", "span", 1999.0)
        bad  = SpanRecord("process_task", "span", 2001.0)
        assert self._gate_with_rule(tmp_path, rule, [good]).passed
        assert not self._gate_with_rule(tmp_path, rule, [bad]).passed

    def test_wrong_span_type_is_skipped(self, tmp_path: Path) -> None:
        """Spans of a different type than the rule's selector must not be evaluated."""
        rule = {
            "id": "db_query_latency",
            "description": "DB queries <= 200 ms",
            "enabled": True,
            "selector": {"type": "db_query"},
            "threshold": {"metric": "duration_ms", "operator": "lte", "value": 200},
            "severity": "warning",
        }
        # HTTP endpoint spans — should be ignored by the db_query rule
        spans = [_make_span(span_type="http_endpoint", duration_ms=9999.0)]
        result = self._gate_with_rule(tmp_path, rule, spans)
        assert result.passed
        assert result.violations == []

    def test_disabled_rule_is_skipped(self, tmp_path: Path) -> None:
        rule = {
            "id": "disabled_rule",
            "description": "Should never fire",
            "enabled": False,
            "selector": {"type": "http_endpoint"},
            "threshold": {"metric": "duration_ms", "operator": "lte", "value": 1},
            "severity": "error",
        }
        spans = [_make_span(duration_ms=9999.0)]
        result = self._gate_with_rule(tmp_path, rule, spans)
        assert result.passed
        assert result.rules_evaluated == 0

    def test_fail_on_error_false_passes_despite_violations(
        self, tmp_path: Path
    ) -> None:
        rule = {
            "id": "api_endpoint_latency",
            "description": "No API endpoint > 500 ms",
            "enabled": True,
            "selector": {"type": "http_endpoint"},
            "threshold": {"metric": "duration_ms", "operator": "lte", "value": 500},
            "severity": "error",
        }
        spans = [_make_span(duration_ms=9999.0)]
        result = self._gate_with_rule(tmp_path, rule, spans, fail_on_error=False)
        assert result.passed          # gate passes even though rule was breached
        assert len(result.violations) == 1

    def test_warning_severity_violation_still_passes(self, tmp_path: Path) -> None:
        rule = {
            "id": "e2e_p95_budget",
            "description": "p95 <= 300 ms",
            "enabled": True,
            "selector": {"type": "http_endpoint"},
            "threshold": {
                "metric": "duration_ms",
                "operator": "lte",
                "value": 300,
                "percentile": "p95",
            },
            "severity": "warning",
        }
        spans = [_make_span(duration_ms=9999.0)]
        result = self._gate_with_rule(tmp_path, rule, spans)
        # warning-severity violations do not block the gate
        assert result.passed
        assert len(result.violations) == 1
        assert result.violations[0].severity == "warning"

    def test_percentile_override_per_rule(self, tmp_path: Path) -> None:
        """Rule-level percentile overrides the global default."""
        rule = {
            "id": "e2e_p95_budget",
            "description": "p95 <= 300 ms",
            "enabled": True,
            "selector": {"type": "http_endpoint"},
            "threshold": {
                "metric": "duration_ms",
                "operator": "lte",
                "value": 300,
                "percentile": "p95",   # ← rule-level override
            },
            "severity": "error",
        }
        # 99 fast requests + 1 slow → p95 lands on the fast cluster, p99 would be slow
        # p95 of 100 values: idx = 0.95*99 = 94.05 → interpolates between
        # sorted[94]=100 and sorted[95]=100 → 100 ms < 300 ms threshold ✓
        fast = [_make_span(duration_ms=100.0)] * 99
        slow = [_make_span(duration_ms=9000.0)]
        result = self._gate_with_rule(tmp_path, rule, fast + slow)
        assert result.passed

    def test_multiple_spans_same_name_grouped_correctly(
        self, tmp_path: Path
    ) -> None:
        """Multiple observations for the same span name are aggregated."""
        rule = {
            "id": "api_endpoint_latency",
            "description": "No API endpoint > 500 ms",
            "enabled": True,
            "selector": {"type": "http_endpoint"},
            "threshold": {"metric": "duration_ms", "operator": "lte", "value": 500},
            "severity": "error",
        }
        # 10 observations: 9 fast, 1 very slow → p99 should exceed threshold
        durations = [100.0] * 9 + [9000.0]
        spans = [_make_span(duration_ms=d) for d in durations]
        result = self._gate_with_rule(tmp_path, rule, spans)
        assert not result.passed
        assert result.violations[0].measured_ms > 500.0

    def test_multiple_span_names_evaluated_independently(
        self, tmp_path: Path
    ) -> None:
        """Two different span names each get their own violation when both breach."""
        rule = {
            "id": "api_endpoint_latency",
            "description": "No API endpoint > 500 ms",
            "enabled": True,
            "selector": {"type": "http_endpoint"},
            "threshold": {"metric": "duration_ms", "operator": "lte", "value": 500},
            "severity": "error",
        }
        spans = [
            SpanRecord("GET /slow-a", "http_endpoint", 800.0),
            SpanRecord("GET /slow-b", "http_endpoint", 900.0),
        ]
        result = self._gate_with_rule(tmp_path, rule, spans)
        assert len(result.violations) == 2
        span_names = {v.span_name for v in result.violations}
        assert "GET /slow-a" in span_names
        assert "GET /slow-b" in span_names

    def test_no_spans_returns_passed_no_violations(self, tmp_path: Path) -> None:
        rule = {
            "id": "api_endpoint_latency",
            "description": "No API endpoint > 500 ms",
            "enabled": True,
            "selector": {"type": "http_endpoint"},
            "threshold": {"metric": "duration_ms", "operator": "lte", "value": 500},
            "severity": "error",
        }
        result = self._gate_with_rule(tmp_path, rule, [])
        assert result.passed
        assert result.violations == []


# ---------------------------------------------------------------------------
# Multi-rule YAML integration
# ---------------------------------------------------------------------------


class TestMultiRuleYAML:
    """End-to-end test with the full perf-thresholds.yml-style YAML."""

    YAML_CONTENT = textwrap.dedent("""\
        version: 1
        defaults:
          fail_on_breach: true
          percentile: p99
        rules:
          - id: api_endpoint_latency
            description: "No HTTP API endpoint may exceed 500 ms at p99"
            enabled: true
            selector:
              type: http_endpoint
            threshold:
              metric: duration_ms
              operator: lte
              value: 500
            severity: error

          - id: span_latency
            description: "No individual trace span may exceed 2000 ms at p99"
            enabled: true
            selector:
              type: span
            threshold:
              metric: duration_ms
              operator: lte
              value: 2000
            severity: error

          - id: db_query_latency
            description: "No individual DB query span may exceed 200 ms at p99"
            enabled: true
            selector:
              type: db_query
            threshold:
              metric: duration_ms
              operator: lte
              value: 200
            severity: warning

          - id: external_http_latency
            description: "Outbound HTTP calls must complete within 1000 ms"
            enabled: true
            selector:
              type: http_client
            threshold:
              metric: duration_ms
              operator: lte
              value: 1000
            severity: warning

          - id: e2e_p95_budget
            description: "p95 end-to-end must stay under 300 ms"
            enabled: true
            selector:
              type: http_endpoint
            threshold:
              metric: duration_ms
              percentile: p95
              operator: lte
              value: 300
            severity: warning
        baseline:
          enabled: false
    """)

    def _setup_gate(self, tmp_path: Path) -> PerformanceGate:
        thresholds = tmp_path / "thresholds.yml"
        thresholds.write_text(self.YAML_CONTENT, encoding="utf-8")
        cfg = PerformanceGateConfig(thresholds_file=str(thresholds))
        return PerformanceGate(cfg)

    def test_all_rules_pass_with_good_spans(self, tmp_path: Path) -> None:
        gate = self._setup_gate(tmp_path)
        spans = [
            SpanRecord("GET /api/users",  "http_endpoint", 300.0),
            SpanRecord("process_task",    "span",          500.0),
            SpanRecord("SELECT users",    "db_query",       80.0),
            SpanRecord("stripe.charge",   "http_client",   200.0),
        ]
        result = gate.run(spans=spans)
        assert result.passed
        assert result.violations == []
        assert result.rules_evaluated == 5

    def test_api_endpoint_violation_blocks_gate(self, tmp_path: Path) -> None:
        gate = self._setup_gate(tmp_path)
        spans = [SpanRecord("GET /api/slow", "http_endpoint", 600.0)]
        result = gate.run(spans=spans)
        assert not result.passed
        assert any(v.rule_id == "api_endpoint_latency" for v in result.violations)

    def test_span_violation_blocks_gate(self, tmp_path: Path) -> None:
        gate = self._setup_gate(tmp_path)
        spans = [SpanRecord("process_task", "span", 2500.0)]
        result = gate.run(spans=spans)
        assert not result.passed
        assert any(v.rule_id == "span_latency" for v in result.violations)

    def test_db_warning_does_not_block(self, tmp_path: Path) -> None:
        gate = self._setup_gate(tmp_path)
        spans = [SpanRecord("SELECT users", "db_query", 500.0)]
        result = gate.run(spans=spans)
        assert result.passed  # db rule is warning severity
        assert any(v.rule_id == "db_query_latency" for v in result.violations)

    def test_external_http_warning_does_not_block(self, tmp_path: Path) -> None:
        gate = self._setup_gate(tmp_path)
        spans = [SpanRecord("stripe.charge", "http_client", 5000.0)]
        result = gate.run(spans=spans)
        assert result.passed
        assert any(v.rule_id == "external_http_latency" for v in result.violations)

    def test_spans_evaluated_count(self, tmp_path: Path) -> None:
        gate = self._setup_gate(tmp_path)
        spans = [_make_span() for _ in range(7)]
        result = gate.run(spans=spans)
        assert result.spans_evaluated == 7


# ---------------------------------------------------------------------------
# Missing / malformed inputs
# ---------------------------------------------------------------------------


class TestInputErrors:
    def test_missing_thresholds_file(self, tmp_path: Path) -> None:
        cfg = PerformanceGateConfig(
            thresholds_file=str(tmp_path / "missing.yml"),
            spans_file=str(tmp_path / "spans.json"),
        )
        result = PerformanceGate(cfg).run(repo_root=tmp_path)
        assert not result.passed
        assert result.violations[0].rule_id == "thresholds_file_missing"

    def test_missing_spans_file(self, tmp_path: Path) -> None:
        import yaml

        thresholds = tmp_path / "thresholds.yml"
        thresholds.write_text(
            yaml.dump({"version": 1, "defaults": {}, "rules": []}),
            encoding="utf-8",
        )
        cfg = PerformanceGateConfig(
            thresholds_file=str(thresholds),
            spans_file=str(tmp_path / "missing-spans.json"),
        )
        result = PerformanceGate(cfg).run(repo_root=tmp_path)
        assert not result.passed
        assert result.violations[0].rule_id == "spans_file_missing"

    def test_malformed_spans_file(self, tmp_path: Path) -> None:
        import yaml

        thresholds = tmp_path / "thresholds.yml"
        thresholds.write_text(
            yaml.dump({"version": 1, "defaults": {}, "rules": []}),
            encoding="utf-8",
        )
        bad_spans = tmp_path / "spans.json"
        bad_spans.write_text("{not a list}", encoding="utf-8")

        cfg = PerformanceGateConfig(
            thresholds_file=str(thresholds),
            spans_file=str(bad_spans),
        )
        result = PerformanceGate(cfg).run(repo_root=tmp_path)
        assert not result.passed
        assert result.violations[0].rule_id == "spans_file_missing"

    def test_missing_thresholds_with_fail_on_error_false(
        self, tmp_path: Path
    ) -> None:
        cfg = PerformanceGateConfig(
            thresholds_file=str(tmp_path / "missing.yml"),
            fail_on_error=False,
        )
        result = PerformanceGate(cfg).run(spans=[], repo_root=tmp_path)
        assert result.passed  # fail_on_error=False → gate passes despite violation


# ---------------------------------------------------------------------------
# Spans loaded from file
# ---------------------------------------------------------------------------


class TestSpansFromFile:
    def test_gate_reads_spans_from_file(self, tmp_path: Path) -> None:
        import yaml

        thresholds = tmp_path / "thresholds.yml"
        rule = {
            "id": "api_endpoint_latency",
            "description": "No API endpoint > 500 ms",
            "enabled": True,
            "selector": {"type": "http_endpoint"},
            "threshold": {"metric": "duration_ms", "operator": "lte", "value": 500},
            "severity": "error",
        }
        thresholds.write_text(
            yaml.dump({"version": 1, "defaults": {}, "rules": [rule]}),
            encoding="utf-8",
        )

        spans_file = _write_spans(tmp_path / "perf-spans.json", [
            {"name": "GET /api/test", "span_type": "http_endpoint", "duration_ms": 300},
        ])

        cfg = PerformanceGateConfig(
            thresholds_file=str(thresholds),
            spans_file=str(spans_file),
        )
        result = PerformanceGate(cfg).run(repo_root=tmp_path)
        assert result.passed
        assert result.spans_evaluated == 1


# ---------------------------------------------------------------------------
# Output file
# ---------------------------------------------------------------------------


class TestOutputFile:
    def test_output_file_written(self, tmp_path: Path) -> None:
        import yaml

        thresholds = tmp_path / "thresholds.yml"
        thresholds.write_text(
            yaml.dump({
                "version": 1,
                "defaults": {},
                "rules": [{
                    "id": "api_endpoint_latency",
                    "description": "No API endpoint > 500 ms",
                    "enabled": True,
                    "selector": {"type": "http_endpoint"},
                    "threshold": {"metric": "duration_ms", "operator": "lte", "value": 500},
                    "severity": "error",
                }],
            }),
            encoding="utf-8",
        )

        output_path = tmp_path / "reports" / "perf-report.json"
        cfg = PerformanceGateConfig(
            thresholds_file=str(thresholds),
            output_file=str(output_path),
        )
        spans = [SpanRecord("GET /api/slow", "http_endpoint", 800.0)]
        PerformanceGate(cfg).run(spans=spans, repo_root=tmp_path)

        assert output_path.exists()
        report = json.loads(output_path.read_text())
        assert "summary" in report
        assert "failures" in report
        assert report["summary"]["blocking_failures"] == 1

    def test_to_report_dict_schema(self, tmp_path: Path) -> None:
        """to_report_dict() must match the schema expected by perf_summary.py."""
        violations = [
            ThresholdViolation(
                rule_id="api_endpoint_latency",
                description="No API endpoint > 500 ms",
                severity="error",
                span_name="GET /api/slow",
                measured_ms=600.0,
                threshold_ms=500.0,
                percentile="p99",
                suggestion="Profile the endpoint.",
            )
        ]
        result = PerformanceGateResult(
            passed=False,
            violations=violations,
            rules_evaluated=3,
            spans_evaluated=10,
        )
        d = result.to_report_dict()

        # Summary section
        s = d["summary"]
        assert s["passed"] is False
        assert s["total_gates"] == 3
        assert s["passed_gates"] == 2   # 3 rules - 1 failure
        assert s["blocking_failures"] == 1
        assert s["warnings"] == 0
        assert s["spans_evaluated"] == 10

        # Failure entries
        assert len(d["failures"]) == 1
        f = d["failures"][0]
        assert f["rule_id"] == "api_endpoint_latency"
        assert f["severity"] == "error"
        assert f["span_name"] == "GET /api/slow"
        assert f["measured_ms"] == pytest.approx(600.0)
        assert f["threshold_ms"] == pytest.approx(500.0)
        assert f["suggestion"] == "Profile the endpoint."


# ---------------------------------------------------------------------------
# Baseline regression
# ---------------------------------------------------------------------------


class TestBaselineRegression:
    def test_regression_above_threshold_adds_violation(
        self, tmp_path: Path
    ) -> None:
        import yaml

        thresholds = tmp_path / "thresholds.yml"
        thresholds.write_text(
            yaml.dump({
                "version": 1,
                "defaults": {},
                "rules": [],
                "baseline": {
                    "enabled": True,
                    "regression_threshold_pct": 10,
                    "severity": "warning",
                },
            }),
            encoding="utf-8",
        )

        baseline = _write_spans(tmp_path / "baseline.json", [
            {"name": "GET /api/test", "span_type": "http_endpoint", "duration_ms": 100},
        ])

        cfg = PerformanceGateConfig(
            thresholds_file=str(thresholds),
            baseline_file=str(baseline),
        )
        # 30 % slower than baseline → regression
        spans = [SpanRecord("GET /api/test", "http_endpoint", 130.0)]
        result = PerformanceGate(cfg).run(spans=spans, repo_root=tmp_path)

        assert any(v.rule_id == "baseline_regression" for v in result.violations)

    def test_regression_below_threshold_no_violation(
        self, tmp_path: Path
    ) -> None:
        import yaml

        thresholds = tmp_path / "thresholds.yml"
        thresholds.write_text(
            yaml.dump({
                "version": 1,
                "defaults": {},
                "rules": [],
                "baseline": {
                    "enabled": True,
                    "regression_threshold_pct": 20,
                    "severity": "warning",
                },
            }),
            encoding="utf-8",
        )

        baseline = _write_spans(tmp_path / "baseline.json", [
            {"name": "GET /api/test", "span_type": "http_endpoint", "duration_ms": 100},
        ])

        cfg = PerformanceGateConfig(
            thresholds_file=str(thresholds),
            baseline_file=str(baseline),
        )
        # Only 10 % slower → within the 20 % budget
        spans = [SpanRecord("GET /api/test", "http_endpoint", 110.0)]
        result = PerformanceGate(cfg).run(spans=spans, repo_root=tmp_path)

        assert not any(v.rule_id == "baseline_regression" for v in result.violations)

    def test_missing_baseline_skipped_gracefully(self, tmp_path: Path) -> None:
        import yaml

        thresholds = tmp_path / "thresholds.yml"
        thresholds.write_text(
            yaml.dump({
                "version": 1,
                "defaults": {},
                "rules": [],
                "baseline": {
                    "enabled": True,
                    "regression_threshold_pct": 10,
                    "severity": "warning",
                },
            }),
            encoding="utf-8",
        )

        cfg = PerformanceGateConfig(
            thresholds_file=str(thresholds),
            baseline_file=str(tmp_path / "no-such-baseline.json"),
        )
        spans = [SpanRecord("GET /api/test", "http_endpoint", 200.0)]
        result = PerformanceGate(cfg).run(spans=spans, repo_root=tmp_path)

        # Gate should still pass — missing baseline is skipped, not a failure
        assert result.passed
        assert not any(v.rule_id == "baseline_regression" for v in result.violations)


# ---------------------------------------------------------------------------
# Real .harness/perf-thresholds.yml integration test
# ---------------------------------------------------------------------------


class TestRealThresholdsFile:
    """Load the actual .harness/perf-thresholds.yml from the repo root and
    verify the gate evaluates correctly against known-good / known-bad spans."""

    REPO_ROOT = Path(__file__).parent.parent.parent  # project root

    @pytest.fixture(autouse=True)
    def _require_yaml(self) -> None:
        pytest.importorskip("yaml")

    def _thresholds_path(self) -> Path:
        return self.REPO_ROOT / ".harness" / "perf-thresholds.yml"

    def test_file_exists(self) -> None:
        assert self._thresholds_path().exists(), (
            ".harness/perf-thresholds.yml not found — "
            "run from the repository root."
        )

    def test_passes_with_good_spans(self) -> None:
        cfg = PerformanceGateConfig(
            thresholds_file=str(self._thresholds_path()),
        )
        gate = PerformanceGate(cfg)
        spans = [
            SpanRecord("GET /api/users",      "http_endpoint", 200.0),
            SpanRecord("process_background",  "span",          100.0),
            SpanRecord("SELECT users",        "db_query",       50.0),
            SpanRecord("stripe.charge",       "http_client",   300.0),
        ]
        result = gate.run(spans=spans)
        assert result.passed
        assert result.errors() == []

    def test_api_endpoint_violation_with_real_thresholds(self) -> None:
        cfg = PerformanceGateConfig(
            thresholds_file=str(self._thresholds_path()),
        )
        gate = PerformanceGate(cfg)
        spans = [SpanRecord("GET /api/slow", "http_endpoint", 600.0)]
        result = gate.run(spans=spans)
        assert not result.passed
        rule_ids = {v.rule_id for v in result.violations}
        assert "api_endpoint_latency" in rule_ids

    def test_span_latency_violation_with_real_thresholds(self) -> None:
        cfg = PerformanceGateConfig(
            thresholds_file=str(self._thresholds_path()),
        )
        gate = PerformanceGate(cfg)
        spans = [SpanRecord("slow_task", "span", 3000.0)]
        result = gate.run(spans=spans)
        assert not result.passed
        rule_ids = {v.rule_id for v in result.violations}
        assert "span_latency" in rule_ids
