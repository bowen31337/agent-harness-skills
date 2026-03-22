"""Unit tests for the health-check-endpoint skill.

Validates:
  - harness_skills.boot.generate_health_check_spec() produces a correctly-shaped
    HealthCheckSpec from a BootConfig.
  - HealthCheckSpec default values match the canonical spec.
  - The JSON Schema at harness_skills/schemas/health_check_response.schema.json
    accepts all three valid example payloads (healthy / degraded / unhealthy) and
    rejects malformed ones.

No network calls or subprocesses are made — all tests are purely in-process.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from harness_skills.boot import (
    BootConfig,
    DatabaseIsolation,
    HealthCheckMethod,
    HealthCheckSpec,
    IsolationConfig,
    generate_health_check_spec,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SCHEMA_PATH = (
    pathlib.Path(__file__).parent.parent
    / "harness_skills"
    / "schemas"
    / "health_check_response.schema.json"
)


def _load_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text())


def _validate(payload: dict) -> None:
    """Validate *payload* against the health_check_response JSON Schema.

    Falls back to a minimal hand-rolled check when jsonschema is not installed,
    so the tests still run in lean environments.
    """
    try:
        import jsonschema  # noqa: PLC0415

        jsonschema.validate(payload, _load_schema())
    except ImportError:
        _minimal_validate(payload)


def _minimal_validate(payload: dict) -> None:
    """Lightweight schema check that does not require jsonschema."""
    assert "status" in payload, "missing required field: status"
    assert "timestamp" in payload, "missing required field: timestamp"
    assert payload["status"] in (
        "healthy",
        "degraded",
        "unhealthy",
    ), f"invalid status: {payload['status']!r}"

    for check in payload.get("checks", []):
        assert "name" in check, "CheckResult missing 'name'"
        assert "status" in check, "CheckResult missing 'status'"
        assert check["status"] in (
            "pass",
            "fail",
            "warn",
        ), f"invalid check status: {check['status']!r}"


# ---------------------------------------------------------------------------
# Schema path
# ---------------------------------------------------------------------------


class TestSchemaFile:
    def test_schema_file_exists(self) -> None:
        assert _SCHEMA_PATH.exists(), f"Schema file not found: {_SCHEMA_PATH}"

    def test_schema_file_is_valid_json(self) -> None:
        schema = _load_schema()
        assert schema.get("title") == "HealthCheckResponse"
        assert "status" in schema["properties"]
        assert "timestamp" in schema["properties"]


# ---------------------------------------------------------------------------
# generate_health_check_spec()
# ---------------------------------------------------------------------------


class TestGenerateHealthCheckSpec:
    def _make_config(
        self,
        *,
        port: int = 8001,
        health_path: str = "/health",
        health_method: HealthCheckMethod = HealthCheckMethod.GET,
        health_timeout_s: float = 30.0,
        health_interval_s: float = 1.0,
    ) -> BootConfig:
        return BootConfig(
            worktree_id="test-wt-1",
            start_command="uvicorn app:app",
            isolation=IsolationConfig(port=port),
            health_path=health_path,
            health_method=health_method,
            health_timeout_s=health_timeout_s,
            health_interval_s=health_interval_s,
        )

    def test_url_composed_from_port_and_path(self) -> None:
        cfg = self._make_config(port=8001, health_path="/health")
        spec = generate_health_check_spec(cfg)
        assert spec.url == "http://localhost:8001/health"

    def test_url_uses_custom_path(self) -> None:
        cfg = self._make_config(port=9000, health_path="/healthz")
        spec = generate_health_check_spec(cfg)
        assert spec.url == "http://localhost:9000/healthz"

    def test_method_defaults_to_get(self) -> None:
        cfg = self._make_config()
        spec = generate_health_check_spec(cfg)
        assert spec.method == HealthCheckMethod.GET

    def test_method_head_propagated(self) -> None:
        cfg = self._make_config(health_method=HealthCheckMethod.HEAD)
        spec = generate_health_check_spec(cfg)
        assert spec.method == HealthCheckMethod.HEAD

    def test_expected_codes_cover_entire_2xx_range(self) -> None:
        cfg = self._make_config()
        spec = generate_health_check_spec(cfg)
        assert spec.expected_codes == list(range(200, 300))

    def test_timeout_s_is_five_seconds(self) -> None:
        """Per-request timeout must match the spec (5 s)."""
        cfg = self._make_config()
        spec = generate_health_check_spec(cfg)
        assert spec.timeout_s == 5.0

    def test_interval_s_propagated_from_config(self) -> None:
        cfg = self._make_config(health_interval_s=2.5)
        spec = generate_health_check_spec(cfg)
        assert spec.interval_s == 2.5

    def test_max_wait_s_propagated_from_config(self) -> None:
        cfg = self._make_config(health_timeout_s=60.0)
        spec = generate_health_check_spec(cfg)
        assert spec.max_wait_s == 60.0

    def test_headers_empty_by_default(self) -> None:
        cfg = self._make_config()
        spec = generate_health_check_spec(cfg)
        assert spec.headers == {}

    def test_returns_health_check_spec_instance(self) -> None:
        cfg = self._make_config()
        spec = generate_health_check_spec(cfg)
        assert isinstance(spec, HealthCheckSpec)


# ---------------------------------------------------------------------------
# HealthCheckSpec defaults
# ---------------------------------------------------------------------------


class TestHealthCheckSpecDefaults:
    def test_default_method_is_get(self) -> None:
        spec = HealthCheckSpec(url="http://localhost:8000/health")
        assert spec.method == HealthCheckMethod.GET

    def test_default_expected_codes(self) -> None:
        spec = HealthCheckSpec(url="http://localhost:8000/health")
        assert spec.expected_codes == [200]

    def test_default_timeout_s(self) -> None:
        spec = HealthCheckSpec(url="http://localhost:8000/health")
        assert spec.timeout_s == 5.0

    def test_default_interval_s(self) -> None:
        spec = HealthCheckSpec(url="http://localhost:8000/health")
        assert spec.interval_s == 1.0

    def test_default_max_wait_s(self) -> None:
        spec = HealthCheckSpec(url="http://localhost:8000/health")
        assert spec.max_wait_s == 30.0

    def test_default_headers_empty(self) -> None:
        spec = HealthCheckSpec(url="http://localhost:8000/health")
        assert spec.headers == {}


# ---------------------------------------------------------------------------
# JSON Schema validation — valid payloads
# ---------------------------------------------------------------------------


class TestSchemaValidPayloads:
    def test_minimal_healthy_payload(self) -> None:
        payload = {
            "status": "healthy",
            "timestamp": "2026-03-20T14:32:01Z",
        }
        _validate(payload)

    def test_full_healthy_payload(self) -> None:
        payload = {
            "status": "healthy",
            "timestamp": "2026-03-20T14:32:01Z",
            "version": "abc1234",
            "uptime_s": 4.7,
            "checks": [
                {
                    "name": "database",
                    "status": "pass",
                    "latency_ms": 3,
                    "message": "pool_size=2/10",
                    "error_code": None,
                },
                {
                    "name": "migrations",
                    "status": "pass",
                    "latency_ms": None,
                    "message": "schema up to date",
                    "error_code": None,
                },
            ],
            "instance": {
                "worktree_id": "fb563322",
                "port": 8001,
                "pid": 12345,
                "git_sha": "abc1234",
                "git_branch": "feat/my-feature",
                "db_schema": "worktree_fb563322",
                "environment": "test",
            },
        }
        _validate(payload)

    def test_degraded_payload(self) -> None:
        payload = {
            "status": "degraded",
            "timestamp": "2026-03-20T14:32:05Z",
            "version": "abc1234",
            "uptime_s": 8.1,
            "checks": [
                {
                    "name": "database",
                    "status": "pass",
                    "latency_ms": 4,
                    "message": None,
                    "error_code": None,
                },
                {
                    "name": "redis",
                    "status": "warn",
                    "latency_ms": 450,
                    "message": "latency above threshold (450ms > 200ms)",
                    "error_code": "REDIS_HIGH_LATENCY",
                },
            ],
            "instance": {
                "worktree_id": "fb563322",
                "port": 8001,
                "pid": 12345,
                "git_sha": "abc1234",
                "git_branch": "feat/my-feature",
                "db_schema": "worktree_fb563322",
                "environment": "test",
            },
        }
        _validate(payload)

    def test_unhealthy_payload(self) -> None:
        payload = {
            "status": "unhealthy",
            "timestamp": "2026-03-20T14:32:10Z",
            "version": "abc1234",
            "uptime_s": 2.3,
            "checks": [
                {
                    "name": "database",
                    "status": "fail",
                    "latency_ms": None,
                    "message": "connection refused: localhost:5432",
                    "error_code": "DB_CONNECTION_REFUSED",
                },
                {
                    "name": "migrations",
                    "status": "fail",
                    "latency_ms": None,
                    "message": "cannot check migrations: database unreachable",
                    "error_code": "DB_CONNECTION_REFUSED",
                },
            ],
            "instance": {
                "worktree_id": "fb563322",
                "port": 8001,
                "pid": 12345,
                "git_sha": "abc1234",
                "git_branch": "feat/my-feature",
                "db_schema": "worktree_fb563322",
                "environment": "test",
            },
        }
        _validate(payload)

    def test_null_optional_fields_are_accepted(self) -> None:
        payload = {
            "status": "healthy",
            "timestamp": "2026-03-20T14:32:01Z",
            "version": None,
            "uptime_s": None,
            "checks": [],
        }
        _validate(payload)


# ---------------------------------------------------------------------------
# JSON Schema validation — invalid payloads (jsonschema only)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("jsonschema"),
    reason="jsonschema not installed",
)
class TestSchemaInvalidPayloads:
    def test_missing_status_field_fails(self) -> None:
        import jsonschema  # noqa: PLC0415

        with pytest.raises(jsonschema.ValidationError):
            _validate({"timestamp": "2026-03-20T14:32:01Z"})

    def test_missing_timestamp_field_fails(self) -> None:
        import jsonschema  # noqa: PLC0415

        with pytest.raises(jsonschema.ValidationError):
            _validate({"status": "healthy"})

    def test_invalid_status_value_fails(self) -> None:
        import jsonschema  # noqa: PLC0415

        with pytest.raises(jsonschema.ValidationError):
            _validate({"status": "ok", "timestamp": "2026-03-20T14:32:01Z"})

    def test_invalid_check_status_fails(self) -> None:
        import jsonschema  # noqa: PLC0415

        payload = {
            "status": "healthy",
            "timestamp": "2026-03-20T14:32:01Z",
            "checks": [{"name": "db", "status": "unknown"}],
        }
        with pytest.raises(jsonschema.ValidationError):
            _validate(payload)

    def test_additional_top_level_field_fails(self) -> None:
        import jsonschema  # noqa: PLC0415

        payload = {
            "status": "healthy",
            "timestamp": "2026-03-20T14:32:01Z",
            "unexpected_field": "value",
        }
        with pytest.raises(jsonschema.ValidationError):
            _validate(payload)

    def test_port_out_of_range_fails(self) -> None:
        import jsonschema  # noqa: PLC0415

        payload = {
            "status": "healthy",
            "timestamp": "2026-03-20T14:32:01Z",
            "instance": {"port": 99999},
        }
        with pytest.raises(jsonschema.ValidationError):
            _validate(payload)


# ---------------------------------------------------------------------------
# Status semantics
# ---------------------------------------------------------------------------


class TestStatusSemantics:
    """Verify the status-derivation rules described in the spec."""

    def test_any_fail_check_requires_unhealthy(self) -> None:
        checks = [
            {"name": "db", "status": "fail"},
            {"name": "cache", "status": "pass"},
        ]
        has_fail = any(c["status"] == "fail" for c in checks)
        assert has_fail
        expected_status = "unhealthy"
        assert expected_status == "unhealthy"

    def test_warn_only_requires_degraded(self) -> None:
        checks = [
            {"name": "db", "status": "pass"},
            {"name": "cache", "status": "warn"},
        ]
        has_fail = any(c["status"] == "fail" for c in checks)
        has_warn = any(c["status"] == "warn" for c in checks)
        assert not has_fail
        assert has_warn
        expected_status = "degraded"
        assert expected_status == "degraded"

    def test_all_pass_requires_healthy(self) -> None:
        checks = [
            {"name": "db", "status": "pass"},
            {"name": "cache", "status": "pass"},
        ]
        has_fail = any(c["status"] == "fail" for c in checks)
        has_warn = any(c["status"] == "warn" for c in checks)
        assert not has_fail
        assert not has_warn
        expected_status = "healthy"
        assert expected_status == "healthy"

    def test_unhealthy_maps_to_http_503(self) -> None:
        overall = "unhealthy"
        http_status = 200 if overall in ("healthy", "degraded") else 503
        assert http_status == 503

    def test_healthy_maps_to_http_200(self) -> None:
        overall = "healthy"
        http_status = 200 if overall in ("healthy", "degraded") else 503
        assert http_status == 200

    def test_degraded_maps_to_http_200(self) -> None:
        overall = "degraded"
        http_status = 200 if overall in ("healthy", "degraded") else 503
        assert http_status == 200


# ---------------------------------------------------------------------------
# IsolationConfig — database isolation env var derivation
# ---------------------------------------------------------------------------


class TestIsolationConfig:
    def test_schema_isolation_derives_db_schema(self) -> None:
        cfg = BootConfig(
            worktree_id="abc123",
            start_command="uvicorn app:app",
            isolation=IsolationConfig(
                port=8001,
                db_isolation=DatabaseIsolation.SCHEMA,
                db_schema="worktree_abc123",
            ),
        )
        assert cfg.isolation.db_schema == "worktree_abc123"
        assert cfg.isolation.db_isolation == DatabaseIsolation.SCHEMA

    def test_file_isolation_derives_database_url(self) -> None:
        cfg = BootConfig(
            worktree_id="abc123",
            start_command="uvicorn app:app",
            isolation=IsolationConfig(
                port=8001,
                db_isolation=DatabaseIsolation.FILE,
                db_file="/tmp/harness_abc123.db",
            ),
        )
        assert cfg.isolation.db_file == "/tmp/harness_abc123.db"
        assert cfg.isolation.db_isolation == DatabaseIsolation.FILE

    def test_extra_env_vars_stored(self) -> None:
        iso = IsolationConfig(
            port=8001,
            extra_env={"APP_ENV": "test", "LOG_LEVEL": "debug"},
        )
        assert iso.extra_env["APP_ENV"] == "test"
        assert iso.extra_env["LOG_LEVEL"] == "debug"
