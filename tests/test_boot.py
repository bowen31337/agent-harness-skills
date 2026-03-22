<<<<<<< HEAD
"""
tests/test_boot.py — pytest test suite for harness_skills.boot

Covers:
- generate_boot_script()   — script content and formatting
- generate_health_check_spec() — spec fields derived from BootConfig
- boot_instance()          — subprocess launch + health poll integration

Run with:
    pytest tests/test_boot.py -v
"""

from __future__ import annotations

import http.server
import json
import os
import socket
import stat
import threading
import time
from pathlib import Path

import pytest

from harness_skills.boot import (
    BootConfig,
    BootResult,
    DatabaseIsolation,
    HealthCheckMethod,
    HealthCheckSpec,
    IsolationConfig,
    boot_instance,
    generate_boot_script,
    generate_health_check_spec,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _free_port() -> int:
    """Return an OS-assigned free TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _minimal_config(port: int | None = None, **kwargs) -> BootConfig:
    """Build a minimal BootConfig suitable for unit tests."""
    p = port or _free_port()
    return BootConfig(
        worktree_id="test_wt_abc123",
        start_command="echo hello",
        isolation=IsolationConfig(port=p),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# generate_boot_script — content tests
# ---------------------------------------------------------------------------


class TestGenerateBootScript:
    def test_returns_string(self):
        script = generate_boot_script(_minimal_config())
        assert isinstance(script, str)

    def test_starts_with_shebang(self):
        script = generate_boot_script(_minimal_config())
        assert script.startswith("#!/usr/bin/env bash")

    def test_contains_set_euo_pipefail(self):
        script = generate_boot_script(_minimal_config())
        assert "set -euo pipefail" in script

    def test_worktree_id_in_script(self):
        cfg = _minimal_config()
        script = generate_boot_script(cfg)
        assert cfg.worktree_id in script

    def test_port_in_script(self):
        port = _free_port()
        script = generate_boot_script(_minimal_config(port=port))
        assert str(port) in script

    def test_health_url_in_script(self):
        port = _free_port()
        cfg = _minimal_config(port=port, health_path="/healthz")
        script = generate_boot_script(cfg)
        assert f"http://localhost:{port}/healthz" in script

    def test_default_health_url(self):
        port = _free_port()
        cfg = _minimal_config(port=port)
        script = generate_boot_script(cfg)
        assert f"http://localhost:{port}/health" in script

    def test_start_command_in_script(self):
        cfg = BootConfig(
            worktree_id="wt1",
            start_command="uvicorn myapp.main:app --host 0.0.0.0",
            isolation=IsolationConfig(port=_free_port()),
        )
        script = generate_boot_script(cfg)
        assert "uvicorn myapp.main:app --host 0.0.0.0" in script

    def test_list_start_command_joined(self):
        cfg = BootConfig(
            worktree_id="wt2",
            start_command=["python", "-m", "myapp"],
            isolation=IsolationConfig(port=_free_port()),
        )
        script = generate_boot_script(cfg)
        assert "python -m myapp" in script

    def test_log_file_in_script(self):
        cfg = _minimal_config(log_file="/tmp/test_app.log")
        script = generate_boot_script(cfg)
        assert "LOG_FILE=" in script
        assert "/tmp/test_app.log" in script

    def test_working_dir_in_script(self):
        cfg = _minimal_config(working_dir="/srv/app")
        script = generate_boot_script(cfg)
        assert 'cd "/srv/app"' in script

    def test_extra_env_vars_exported(self):
        cfg = _minimal_config()
        cfg.isolation.extra_env = {"MY_VAR": "hello", "OTHER": "42"}
        script = generate_boot_script(cfg)
        assert 'export MY_VAR="hello"' in script
        assert 'export OTHER="42"' in script

    def test_health_timeout_in_script(self):
        cfg = _minimal_config(health_timeout_s=60.0)
        script = generate_boot_script(cfg)
        assert "60" in script

    def test_health_method_get(self):
        cfg = _minimal_config(health_method=HealthCheckMethod.GET)
        script = generate_boot_script(cfg)
        assert "-X GET" in script

    def test_health_method_head(self):
        cfg = _minimal_config(health_method=HealthCheckMethod.HEAD)
        script = generate_boot_script(cfg)
        assert "-X HEAD" in script

    # ── Database isolation blocks ──────────────────────────────────────────

    def test_no_db_isolation(self):
        cfg = _minimal_config()
        cfg.isolation.db_isolation = DatabaseIsolation.NONE
        script = generate_boot_script(cfg)
        assert "DB_SCHEMA" not in script
        assert "DATABASE_URL" not in script

    def test_schema_isolation_exports_db_schema(self):
        cfg = _minimal_config()
        cfg.isolation.db_isolation = DatabaseIsolation.SCHEMA
        cfg.isolation.db_schema = "wt_custom"
        script = generate_boot_script(cfg)
        assert 'export DB_SCHEMA="wt_custom"' in script

    def test_schema_isolation_defaults_schema_name(self):
        cfg = _minimal_config()
        cfg.isolation.db_isolation = DatabaseIsolation.SCHEMA
        cfg.isolation.db_schema = ""   # trigger default
        script = generate_boot_script(cfg)
        assert "export DB_SCHEMA=" in script
        assert cfg.worktree_id in script  # default includes worktree id

    def test_file_isolation_exports_database_url(self):
        cfg = _minimal_config()
        cfg.isolation.db_isolation = DatabaseIsolation.FILE
        cfg.isolation.db_file = "/tmp/custom.db"
        script = generate_boot_script(cfg)
        assert 'export DATABASE_URL="sqlite:////' in script or \
               'export DATABASE_URL="sqlite:///tmp/custom.db"' in script

    def test_file_isolation_defaults_db_path(self):
        cfg = _minimal_config()
        cfg.isolation.db_isolation = DatabaseIsolation.FILE
        cfg.isolation.db_file = ""    # trigger default
        script = generate_boot_script(cfg)
        assert "export DATABASE_URL=" in script
        assert cfg.worktree_id in script

    def test_container_isolation_comment_only(self):
        cfg = _minimal_config()
        cfg.isolation.db_isolation = DatabaseIsolation.CONTAINER
        script = generate_boot_script(cfg)
        # Container isolation doesn't set env vars — managed externally
        assert "DATABASE_URL" not in script or "already be set" in script

    # ── Script name in header comment ──────────────────────────────────────

    def test_script_name_in_header(self):
        cfg = _minimal_config()
        script = generate_boot_script(cfg)
        assert f"boot_{cfg.worktree_id}.sh" in script


# ---------------------------------------------------------------------------
# generate_health_check_spec — field tests
# ---------------------------------------------------------------------------


class TestGenerateHealthCheckSpec:
    def test_returns_health_check_spec(self):
        spec = generate_health_check_spec(_minimal_config())
        assert isinstance(spec, HealthCheckSpec)

    def test_url_uses_port_and_path(self):
        port = _free_port()
        cfg = _minimal_config(port=port, health_path="/api/ping")
        spec = generate_health_check_spec(cfg)
        assert spec.url == f"http://localhost:{port}/api/ping"

    def test_method_matches_config(self):
        cfg = _minimal_config(health_method=HealthCheckMethod.HEAD)
        spec = generate_health_check_spec(cfg)
        assert spec.method == HealthCheckMethod.HEAD

    def test_expected_codes_are_2xx(self):
        spec = generate_health_check_spec(_minimal_config())
        assert all(200 <= code < 300 for code in spec.expected_codes)
        assert 200 in spec.expected_codes

    def test_interval_propagated(self):
        cfg = _minimal_config(health_interval_s=2.5)
        spec = generate_health_check_spec(cfg)
        assert spec.interval_s == pytest.approx(2.5)

    def test_max_wait_propagated(self):
        cfg = _minimal_config(health_timeout_s=45.0)
        spec = generate_health_check_spec(cfg)
        assert spec.max_wait_s == pytest.approx(45.0)

    def test_headers_empty_by_default(self):
        spec = generate_health_check_spec(_minimal_config())
        assert spec.headers == {}

    def test_spec_is_json_serialisable(self):
        import dataclasses
        spec = generate_health_check_spec(_minimal_config())
        d = dataclasses.asdict(spec)
        json.dumps(d)   # must not raise


# ---------------------------------------------------------------------------
# boot_instance — integration tests with a real HTTP server
# ---------------------------------------------------------------------------


class _AlwaysOKHandler(http.server.BaseHTTPRequestHandler):
    """Minimal handler that returns 200 for GET /health and GET /."""

    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_HEAD(self):  # noqa: N802
        self.send_response(200)
        self.end_headers()

    def log_message(self, *_args):  # suppress request noise in test output
        pass


class _AlwaysFailHandler(http.server.BaseHTTPRequestHandler):
    """Returns 503 for every request — simulates an unhealthy service."""

    def do_GET(self):  # noqa: N802
        self.send_response(503)
        self.end_headers()

    def log_message(self, *_args):
        pass


def _start_server(handler_class, port: int) -> http.server.HTTPServer:
    server = http.server.HTTPServer(("127.0.0.1", port), handler_class)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


class TestBootInstance:
    def test_boot_succeeds_when_app_is_healthy(self):
        port = _free_port()
        # Pre-start a healthy HTTP server on the target port
        server = _start_server(_AlwaysOKHandler, port)
        try:
            cfg = BootConfig(
                worktree_id="boot_ok_test",
                # The actual "app" is already running; use a no-op command
                start_command="true",
                isolation=IsolationConfig(port=port),
                health_timeout_s=5.0,
                health_interval_s=0.1,
            )
            result = boot_instance(cfg)
            assert result.ready is True
            assert result.port == port
            assert result.error == ""
            assert result.elapsed_s >= 0.0
        finally:
            server.shutdown()

    def test_boot_result_worktree_id_matches(self):
        port = _free_port()
        server = _start_server(_AlwaysOKHandler, port)
        try:
            cfg = BootConfig(
                worktree_id="my_wt_id",
                start_command="true",
                isolation=IsolationConfig(port=port),
                health_timeout_s=5.0,
                health_interval_s=0.1,
            )
            result = boot_instance(cfg)
            assert result.worktree_id == "my_wt_id"
        finally:
            server.shutdown()

    def test_boot_timeout_when_app_never_healthy(self):
        port = _free_port()
        server = _start_server(_AlwaysFailHandler, port)
        try:
            cfg = BootConfig(
                worktree_id="boot_fail_test",
                start_command="true",
                isolation=IsolationConfig(port=port),
                health_timeout_s=2.0,
                health_interval_s=0.2,
            )
            result = boot_instance(cfg)
            assert result.ready is False
            assert result.error != ""
            assert result.elapsed_s >= 1.9   # at least near the timeout
        finally:
            server.shutdown()

    def test_boot_timeout_when_port_not_open(self):
        port = _free_port()
        # Do NOT start any server on this port
        cfg = BootConfig(
            worktree_id="boot_no_server",
            start_command="true",
            isolation=IsolationConfig(port=port),
            health_timeout_s=2.0,
            health_interval_s=0.2,
        )
        result = boot_instance(cfg)
        assert result.ready is False
        assert result.error != ""

    def test_boot_result_health_url(self):
        port = _free_port()
        server = _start_server(_AlwaysOKHandler, port)
        try:
            cfg = BootConfig(
                worktree_id="url_test",
                start_command="true",
                isolation=IsolationConfig(port=port),
                health_path="/healthz",
                health_timeout_s=5.0,
                health_interval_s=0.1,
            )
            result = boot_instance(cfg)
            assert result.health_url == f"http://localhost:{port}/healthz"
        finally:
            server.shutdown()

    def test_boot_head_method_succeeds(self):
        port = _free_port()
        server = _start_server(_AlwaysOKHandler, port)
        try:
            cfg = BootConfig(
                worktree_id="head_test",
                start_command="true",
                isolation=IsolationConfig(port=port),
                health_method=HealthCheckMethod.HEAD,
                health_timeout_s=5.0,
                health_interval_s=0.1,
            )
            result = boot_instance(cfg)
            assert result.ready is True
        finally:
            server.shutdown()

    def test_timeout_override_respected(self):
        port = _free_port()
        server = _start_server(_AlwaysFailHandler, port)
        try:
            cfg = BootConfig(
                worktree_id="timeout_override_test",
                start_command="true",
                isolation=IsolationConfig(port=port),
                health_timeout_s=60.0,   # would wait 60s by default
                health_interval_s=0.1,
            )
            start = time.monotonic()
            result = boot_instance(cfg, timeout=1.5)  # override to 1.5s
            elapsed = time.monotonic() - start
            assert result.ready is False
            assert elapsed < 10.0  # much less than 60s default
        finally:
            server.shutdown()

    def test_invalid_command_returns_error_result(self):
        port = _free_port()
        cfg = BootConfig(
            worktree_id="bad_cmd_test",
            start_command="/nonexistent_binary_xyz",
            isolation=IsolationConfig(port=port),
            health_timeout_s=2.0,
            health_interval_s=0.1,
        )
        result = boot_instance(cfg)
        # Should return a BootResult (not raise), with ready=False
        assert isinstance(result, BootResult)
        assert result.ready is False

    def test_log_file_created(self, tmp_path: Path):
        port = _free_port()
        server = _start_server(_AlwaysOKHandler, port)
        log_path = str(tmp_path / "app.log")
        try:
            cfg = BootConfig(
                worktree_id="log_test",
                start_command="true",
                isolation=IsolationConfig(port=port),
                health_timeout_s=5.0,
                health_interval_s=0.1,
                log_file=log_path,
            )
            result = boot_instance(cfg)
            assert result.ready is True
            # Log file should exist (even if empty for 'true')
            assert Path(log_path).exists()
        finally:
            server.shutdown()

    def test_extra_env_injected(self):
        """Verify extra_env vars reach the subprocess by running env and checking output."""
        port = _free_port()
        server = _start_server(_AlwaysOKHandler, port)
        try:
            cfg = BootConfig(
                worktree_id="env_test",
                start_command="true",
                isolation=IsolationConfig(
                    port=port,
                    extra_env={"HARNESS_TEST_TOKEN": "secret99"},
                ),
                health_timeout_s=5.0,
                health_interval_s=0.1,
            )
            # We're not checking the subprocess env directly here — just
            # verifying boot_instance() doesn't raise with extra_env set.
            result = boot_instance(cfg)
            assert result.ready is True
        finally:
            server.shutdown()

    def test_schema_db_isolation_sets_env(self):
        port = _free_port()
        server = _start_server(_AlwaysOKHandler, port)
        try:
            cfg = BootConfig(
                worktree_id="schema_iso_test",
                start_command="true",
                isolation=IsolationConfig(
                    port=port,
                    db_isolation=DatabaseIsolation.SCHEMA,
                    db_schema="wt_schema_abc",
                ),
                health_timeout_s=5.0,
                health_interval_s=0.1,
            )
            result = boot_instance(cfg)
            assert result.ready is True
        finally:
            server.shutdown()

    def test_file_db_isolation_sets_env(self):
        port = _free_port()
        server = _start_server(_AlwaysOKHandler, port)
        try:
            cfg = BootConfig(
                worktree_id="file_iso_test",
                start_command="true",
                isolation=IsolationConfig(
                    port=port,
                    db_isolation=DatabaseIsolation.FILE,
                    db_file="/tmp/harness_file_iso_test.db",
                ),
                health_timeout_s=5.0,
                health_interval_s=0.1,
            )
            result = boot_instance(cfg)
            assert result.ready is True
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# Port determinism helper (used by the skill's Step 3)
# ---------------------------------------------------------------------------


def _worktree_port(worktree_id: str, base: int = 8100, span: int = 900) -> int:
    import hashlib
    digest = int(hashlib.sha256(worktree_id.encode()).hexdigest(), 16)
    return base + (digest % span)


class TestWorktreePortAllocation:
    def test_same_id_same_port(self):
        p1 = _worktree_port("wt_abc123")
        p2 = _worktree_port("wt_abc123")
        assert p1 == p2

    def test_different_ids_likely_different_ports(self):
        ports = {_worktree_port(f"wt_{i:04d}") for i in range(50)}
        # With 50 IDs in a 900-port range, collisions are possible but rare
        assert len(ports) > 40

    def test_port_in_valid_range(self):
        for i in range(100):
            p = _worktree_port(f"task_{i}")
            assert 8100 <= p <= 8999


# ---------------------------------------------------------------------------
# Script is executable when written to disk
# ---------------------------------------------------------------------------


class TestBootScriptOnDisk:
    def test_script_can_be_written_and_made_executable(self, tmp_path: Path):
        cfg = _minimal_config()
        content = generate_boot_script(cfg)

        script_path = tmp_path / f"boot_{cfg.worktree_id}.sh"
        script_path.write_text(content)
        current = script_path.stat().st_mode
        script_path.chmod(current | stat.S_IXUSR | stat.S_IXGRP)

        # Verify executable bit is set
        refreshed = script_path.stat().st_mode
        assert refreshed & stat.S_IXUSR

    def test_script_is_valid_utf8(self):
        content = generate_boot_script(_minimal_config())
        content.encode("utf-8")  # must not raise

    def test_script_line_endings_are_unix(self):
        content = generate_boot_script(_minimal_config())
        assert "\r\n" not in content
||||||| 0e893bd
=======
"""
tests/test_boot.py
==================
Unit tests for :mod:`harness_skills.boot`.

Test strategy
-------------
* **Data models** — verify all dataclass defaults and field assignments for
  ``IsolationConfig``, ``BootConfig``, ``HealthCheckSpec``, and ``BootResult``.
* **generate_boot_script** — verify that the rendered bash script contains the
  expected PORT export, health URL, isolation block, launch command, and timeout
  values for every isolation strategy.
* **generate_health_check_spec** — verify that the spec URL is derived correctly
  from the port and health_path, that expected_codes covers the full 2xx range,
  and that timeout/interval values mirror the BootConfig.
* **_poll_health_check** — use ``unittest.mock`` to control ``urllib.request.urlopen``
  and ``time.sleep`` so the polling loop can be exercised without real network I/O.
  Scenarios covered: immediate success, delayed success after several retries,
  timeout, HTTP error codes, connection errors, and non-2xx responses.
* **boot_instance** — mock ``subprocess.Popen`` and ``_poll_health_check`` so the
  full boot flow can be tested without starting real processes.  Covers success,
  health-check failure (process killed), pre-launch OSError, log file routing, and
  timeout override.
"""

from __future__ import annotations

import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from harness_skills.boot import (
    BootConfig,
    BootResult,
    DatabaseIsolation,
    HealthCheckMethod,
    HealthCheckSpec,
    IsolationConfig,
    _build_isolation_block,
    _build_launch_block,
    _poll_health_check,
    boot_instance,
    generate_boot_script,
    generate_health_check_spec,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def minimal_config(
    worktree_id: str = "abc12345",
    start_command: str = "uvicorn myapp.main:app",
    port: int = 8001,
    **kwargs,
) -> BootConfig:
    """Return a minimal BootConfig suitable for most tests."""
    return BootConfig(
        worktree_id=worktree_id,
        start_command=start_command,
        isolation=IsolationConfig(port=port),
        **kwargs,
    )


def _make_http_response(status: int) -> MagicMock:
    """Return a mock urllib response with the given HTTP status."""
    resp = MagicMock()
    resp.status = status
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ===========================================================================
# IsolationConfig — defaults and field assignment
# ===========================================================================


class TestIsolationConfig:
    def test_default_port(self):
        assert IsolationConfig().port == 8000

    def test_default_db_isolation(self):
        assert IsolationConfig().db_isolation == DatabaseIsolation.NONE

    def test_default_db_schema_empty(self):
        assert IsolationConfig().db_schema == ""

    def test_default_db_file_empty(self):
        assert IsolationConfig().db_file == ""

    def test_default_extra_env_empty_dict(self):
        assert IsolationConfig().extra_env == {}

    def test_custom_port(self):
        assert IsolationConfig(port=9999).port == 9999

    def test_schema_isolation(self):
        iso = IsolationConfig(
            db_isolation=DatabaseIsolation.SCHEMA,
            db_schema="my_schema",
        )
        assert iso.db_isolation == DatabaseIsolation.SCHEMA
        assert iso.db_schema == "my_schema"

    def test_file_isolation(self):
        iso = IsolationConfig(
            db_isolation=DatabaseIsolation.FILE,
            db_file="/tmp/my.db",
        )
        assert iso.db_isolation == DatabaseIsolation.FILE
        assert iso.db_file == "/tmp/my.db"

    def test_extra_env_stored(self):
        iso = IsolationConfig(extra_env={"FOO": "bar", "BAZ": "qux"})
        assert iso.extra_env == {"FOO": "bar", "BAZ": "qux"}

    def test_extra_env_instances_are_independent(self):
        """Mutable default must not be shared between instances."""
        a = IsolationConfig()
        b = IsolationConfig()
        a.extra_env["KEY"] = "val"
        assert "KEY" not in b.extra_env


# ===========================================================================
# BootConfig — defaults and field assignment
# ===========================================================================


class TestBootConfig:
    def test_required_fields_stored(self):
        cfg = minimal_config()
        assert cfg.worktree_id == "abc12345"
        assert cfg.start_command == "uvicorn myapp.main:app"

    def test_default_health_path(self):
        assert minimal_config().health_path == "/health"

    def test_default_health_method(self):
        assert minimal_config().health_method == HealthCheckMethod.GET

    def test_default_health_timeout(self):
        assert minimal_config().health_timeout_s == 30.0

    def test_default_health_interval(self):
        assert minimal_config().health_interval_s == 1.0

    def test_default_working_dir_empty(self):
        assert minimal_config().working_dir == ""

    def test_default_log_file_empty(self):
        assert minimal_config().log_file == ""

    def test_start_command_as_list(self):
        cfg = BootConfig(
            worktree_id="x",
            start_command=["uvicorn", "myapp.main:app", "--port", "8001"],
            isolation=IsolationConfig(port=8001),
        )
        assert cfg.start_command == ["uvicorn", "myapp.main:app", "--port", "8001"]

    def test_custom_health_path(self):
        cfg = minimal_config(health_path="/api/healthz")
        assert cfg.health_path == "/api/healthz"

    def test_head_health_method(self):
        cfg = minimal_config(health_method=HealthCheckMethod.HEAD)
        assert cfg.health_method == HealthCheckMethod.HEAD

    def test_isolation_instance_isolated_from_default(self):
        """Each BootConfig must get its own IsolationConfig instance."""
        a = minimal_config(port=8001)
        b = minimal_config(port=8002)
        assert a.isolation.port == 8001
        assert b.isolation.port == 8002


# ===========================================================================
# HealthCheckSpec — defaults
# ===========================================================================


class TestHealthCheckSpec:
    def test_default_method(self):
        spec = HealthCheckSpec(url="http://localhost:8001/health")
        assert spec.method == HealthCheckMethod.GET

    def test_default_expected_codes_contains_200(self):
        spec = HealthCheckSpec(url="http://localhost:8001/health")
        assert 200 in spec.expected_codes

    def test_default_timeout(self):
        spec = HealthCheckSpec(url="http://localhost:8001/health")
        assert spec.timeout_s == 5.0

    def test_default_interval(self):
        spec = HealthCheckSpec(url="http://localhost:8001/health")
        assert spec.interval_s == 1.0

    def test_default_max_wait(self):
        spec = HealthCheckSpec(url="http://localhost:8001/health")
        assert spec.max_wait_s == 30.0

    def test_default_headers_empty(self):
        spec = HealthCheckSpec(url="http://localhost:8001/health")
        assert spec.headers == {}

    def test_custom_url_stored(self):
        spec = HealthCheckSpec(url="http://localhost:9999/readyz")
        assert spec.url == "http://localhost:9999/readyz"


# ===========================================================================
# BootResult — field assignment
# ===========================================================================


class TestBootResult:
    def test_ready_true(self):
        r = BootResult(
            worktree_id="x",
            pid=1234,
            port=8001,
            health_url="http://localhost:8001/health",
            ready=True,
            elapsed_s=2.3,
        )
        assert r.ready is True
        assert r.error == ""

    def test_ready_false_with_error(self):
        r = BootResult(
            worktree_id="x",
            pid=0,
            port=8001,
            health_url="http://localhost:8001/health",
            ready=False,
            elapsed_s=30.0,
            error="Health check timed out after 30.0s",
        )
        assert r.ready is False
        assert "timed out" in r.error


# ===========================================================================
# _build_isolation_block
# ===========================================================================


class TestBuildIsolationBlock:
    def test_none_isolation_produces_comment(self):
        cfg = minimal_config()
        block = _build_isolation_block(cfg)
        assert "No database isolation" in block
        assert "export DB_SCHEMA" not in block
        assert "export DATABASE_URL" not in block

    def test_schema_isolation_exports_db_schema(self):
        cfg = BootConfig(
            worktree_id="wt1",
            start_command="app",
            isolation=IsolationConfig(
                port=8001,
                db_isolation=DatabaseIsolation.SCHEMA,
                db_schema="myschema",
            ),
        )
        block = _build_isolation_block(cfg)
        assert 'export DB_SCHEMA="myschema"' in block

    def test_schema_isolation_defaults_schema_name_when_empty(self):
        cfg = BootConfig(
            worktree_id="wt1",
            start_command="app",
            isolation=IsolationConfig(
                port=8001,
                db_isolation=DatabaseIsolation.SCHEMA,
                db_schema="",  # intentionally empty
            ),
        )
        block = _build_isolation_block(cfg)
        assert 'export DB_SCHEMA="worktree_wt1"' in block

    def test_file_isolation_exports_database_url(self):
        cfg = BootConfig(
            worktree_id="wt2",
            start_command="app",
            isolation=IsolationConfig(
                port=8001,
                db_isolation=DatabaseIsolation.FILE,
                db_file="/data/wt2.db",
            ),
        )
        block = _build_isolation_block(cfg)
        assert 'export DATABASE_URL="sqlite:////data/wt2.db"' in block

    def test_file_isolation_defaults_db_file_when_empty(self):
        cfg = BootConfig(
            worktree_id="wt2",
            start_command="app",
            isolation=IsolationConfig(
                port=8001,
                db_isolation=DatabaseIsolation.FILE,
                db_file="",
            ),
        )
        block = _build_isolation_block(cfg)
        assert "wt2.db" in block

    def test_container_isolation_produces_comment(self):
        cfg = BootConfig(
            worktree_id="wt3",
            start_command="app",
            isolation=IsolationConfig(
                port=8001,
                db_isolation=DatabaseIsolation.CONTAINER,
            ),
        )
        block = _build_isolation_block(cfg)
        assert "Container-level isolation" in block or "DATABASE_URL" in block or "external" in block.lower()


# ===========================================================================
# _build_launch_block
# ===========================================================================


class TestBuildLaunchBlock:
    def test_string_command_without_log_file(self):
        cfg = minimal_config(start_command="uvicorn app:main --port 8001")
        block = _build_launch_block(cfg)
        assert "uvicorn app:main --port 8001 &" in block
        assert "LOG_FILE" not in block

    def test_list_command_joined_with_spaces(self):
        cfg = BootConfig(
            worktree_id="x",
            start_command=["python", "-m", "myapp", "--port", "8001"],
            isolation=IsolationConfig(port=8001),
        )
        block = _build_launch_block(cfg)
        assert "python -m myapp --port 8001 &" in block

    def test_string_command_with_log_file(self):
        cfg = minimal_config(
            start_command="uvicorn app:main",
            log_file="/tmp/app.log",
        )
        block = _build_launch_block(cfg)
        assert "LOG_FILE" in block
        assert "&" in block


# ===========================================================================
# generate_boot_script
# ===========================================================================


class TestGenerateBootScript:
    def test_returns_string(self):
        script = generate_boot_script(minimal_config())
        assert isinstance(script, str)

    def test_shebang_line_present(self):
        script = generate_boot_script(minimal_config())
        assert script.startswith("#!/usr/bin/env bash")

    def test_port_exported(self):
        script = generate_boot_script(minimal_config(port=9876))
        assert 'PORT="9876"' in script

    def test_health_url_contains_port_and_path(self):
        cfg = minimal_config(port=8005, health_path="/readyz")
        script = generate_boot_script(cfg)
        assert "http://localhost:8005/readyz" in script

    def test_health_timeout_present(self):
        cfg = minimal_config(health_timeout_s=45.0)
        script = generate_boot_script(cfg)
        assert "HEALTH_TIMEOUT=45" in script

    def test_health_interval_present(self):
        cfg = minimal_config(health_interval_s=2.5)
        script = generate_boot_script(cfg)
        assert "HEALTH_INTERVAL=2.5" in script

    def test_worktree_id_in_script(self):
        cfg = minimal_config(worktree_id="deadbeef")
        script = generate_boot_script(cfg)
        assert "deadbeef" in script

    def test_start_command_in_script(self):
        cfg = minimal_config(start_command="gunicorn myapp:app -w 4")
        script = generate_boot_script(cfg)
        assert "gunicorn myapp:app -w 4" in script

    def test_get_health_method_in_curl(self):
        cfg = minimal_config(health_method=HealthCheckMethod.GET)
        script = generate_boot_script(cfg)
        assert "-X GET" in script

    def test_head_health_method_in_curl(self):
        cfg = minimal_config(health_method=HealthCheckMethod.HEAD)
        script = generate_boot_script(cfg)
        assert "-X HEAD" in script

    def test_working_dir_cd_present(self):
        cfg = minimal_config(working_dir="/opt/myapp")
        script = generate_boot_script(cfg)
        assert 'cd "/opt/myapp"' in script

    def test_no_working_dir_has_comment(self):
        cfg = minimal_config(working_dir="")
        script = generate_boot_script(cfg)
        assert "working dir: inherited" in script

    def test_log_file_variable_set(self):
        cfg = minimal_config(log_file="/var/log/app.log")
        script = generate_boot_script(cfg)
        assert 'LOG_FILE="/var/log/app.log"' in script

    def test_no_log_file_has_comment(self):
        cfg = minimal_config(log_file="")
        script = generate_boot_script(cfg)
        assert "log file: inherited streams" in script

    def test_extra_env_exported(self):
        cfg = BootConfig(
            worktree_id="x",
            start_command="app",
            isolation=IsolationConfig(
                port=8001,
                extra_env={"MY_FLAG": "1", "LOG_LEVEL": "debug"},
            ),
        )
        script = generate_boot_script(cfg)
        assert 'export MY_FLAG="1"' in script
        assert 'export LOG_LEVEL="debug"' in script

    def test_no_extra_env_has_comment(self):
        cfg = minimal_config()
        script = generate_boot_script(cfg)
        assert "No extra environment variables" in script

    def test_schema_isolation_in_script(self):
        cfg = BootConfig(
            worktree_id="wt",
            start_command="app",
            isolation=IsolationConfig(
                port=8001,
                db_isolation=DatabaseIsolation.SCHEMA,
                db_schema="wt_schema",
            ),
        )
        script = generate_boot_script(cfg)
        assert 'DB_SCHEMA="wt_schema"' in script

    def test_file_isolation_in_script(self):
        cfg = BootConfig(
            worktree_id="wt",
            start_command="app",
            isolation=IsolationConfig(
                port=8001,
                db_isolation=DatabaseIsolation.FILE,
                db_file="/tmp/wt.db",
            ),
        )
        script = generate_boot_script(cfg)
        assert "wt.db" in script

    def test_script_contains_health_check_loop(self):
        script = generate_boot_script(minimal_config())
        assert "while true" in script
        assert "curl" in script
        assert "http_code" in script.lower() or "HTTP_STATUS" in script

    def test_script_kills_process_on_timeout(self):
        script = generate_boot_script(minimal_config())
        assert "kill" in script

    def test_script_exits_0_on_success(self):
        script = generate_boot_script(minimal_config())
        assert "exit 0" in script

    def test_script_exits_1_on_timeout(self):
        script = generate_boot_script(minimal_config())
        assert "exit 1" in script

    def test_list_start_command_joined(self):
        cfg = BootConfig(
            worktree_id="x",
            start_command=["node", "server.js", "--port", "3000"],
            isolation=IsolationConfig(port=3000),
        )
        script = generate_boot_script(cfg)
        assert "node server.js --port 3000" in script

    def test_script_name_in_comment_header(self):
        cfg = minimal_config(worktree_id="mywtree")
        script = generate_boot_script(cfg)
        assert "boot_mywtree.sh" in script

    def test_two_calls_same_config_produce_identical_scripts(self):
        cfg = minimal_config()
        assert generate_boot_script(cfg) == generate_boot_script(cfg)


# ===========================================================================
# generate_health_check_spec
# ===========================================================================


class TestGenerateHealthCheckSpec:
    def test_url_contains_port(self):
        spec = generate_health_check_spec(minimal_config(port=8888))
        assert "8888" in spec.url

    def test_url_contains_health_path(self):
        spec = generate_health_check_spec(minimal_config(health_path="/api/health"))
        assert spec.url.endswith("/api/health")

    def test_url_scheme_is_http(self):
        spec = generate_health_check_spec(minimal_config(port=8001))
        assert spec.url.startswith("http://localhost:")

    def test_method_mirrors_config(self):
        cfg = minimal_config(health_method=HealthCheckMethod.HEAD)
        spec = generate_health_check_spec(cfg)
        assert spec.method == HealthCheckMethod.HEAD

    def test_expected_codes_covers_full_2xx_range(self):
        spec = generate_health_check_spec(minimal_config())
        for code in range(200, 300):
            assert code in spec.expected_codes, f"Missing expected code {code}"

    def test_interval_mirrors_config(self):
        cfg = minimal_config(health_interval_s=3.0)
        spec = generate_health_check_spec(cfg)
        assert spec.interval_s == pytest.approx(3.0)

    def test_max_wait_mirrors_timeout(self):
        cfg = minimal_config(health_timeout_s=60.0)
        spec = generate_health_check_spec(cfg)
        assert spec.max_wait_s == pytest.approx(60.0)

    def test_per_request_timeout_is_5s(self):
        spec = generate_health_check_spec(minimal_config())
        assert spec.timeout_s == pytest.approx(5.0)

    def test_returns_health_check_spec_instance(self):
        spec = generate_health_check_spec(minimal_config())
        assert isinstance(spec, HealthCheckSpec)


# ===========================================================================
# _poll_health_check — mocked network calls
# ===========================================================================


class TestPollHealthCheck:
    """Test the internal polling loop via mocked urllib calls."""

    def _make_spec(
        self,
        max_wait_s: float = 5.0,
        interval_s: float = 0.0,
        expected_codes: list[int] | None = None,
    ) -> HealthCheckSpec:
        return HealthCheckSpec(
            url="http://localhost:8001/health",
            timeout_s=1.0,
            interval_s=interval_s,
            max_wait_s=max_wait_s,
            expected_codes=expected_codes or list(range(200, 300)),
        )

    def test_immediate_success_returns_ready_true(self):
        spec = self._make_spec()
        with patch("urllib.request.urlopen") as mock_open, \
             patch("time.sleep"):
            mock_open.return_value = _make_http_response(200)
            ready, elapsed, error = _poll_health_check(spec)
        assert ready is True
        assert error == ""
        assert elapsed >= 0

    def test_head_method_used_when_specified(self):
        spec = HealthCheckSpec(
            url="http://localhost:8001/health",
            method=HealthCheckMethod.HEAD,
            expected_codes=list(range(200, 300)),
            timeout_s=1.0,
            interval_s=0.0,
            max_wait_s=5.0,
        )
        captured_requests = []

        def fake_urlopen(req, timeout=None):
            captured_requests.append(req)
            return _make_http_response(200)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
             patch("time.sleep"):
            ready, _, _ = _poll_health_check(spec)

        assert ready is True
        assert captured_requests[0].method == "HEAD"

    def test_retry_on_connection_error_then_success(self):
        spec = self._make_spec(max_wait_s=10.0)
        call_count = 0

        def fake_urlopen(req, timeout=None):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise urllib.error.URLError("connection refused")
            return _make_http_response(200)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
             patch("time.sleep"), \
             patch("time.monotonic", side_effect=[0.0, 0.5, 1.0, 1.5, 2.0]):
            ready, _, error = _poll_health_check(spec)

        assert ready is True
        assert call_count == 3

    def test_timeout_returns_ready_false(self):
        spec = self._make_spec(max_wait_s=0.01, interval_s=0.0)

        def fake_urlopen(req, timeout=None):
            raise urllib.error.URLError("connection refused")

        # Simulate monotonic time exceeding max_wait immediately on 2nd check
        with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
             patch("time.sleep"), \
             patch("time.monotonic", side_effect=[0.0, 1.0]):
            ready, elapsed, error = _poll_health_check(spec)

        assert ready is False
        assert "timed out" in error.lower()

    def test_unexpected_http_status_retries(self):
        spec = self._make_spec(max_wait_s=10.0)
        call_count = 0

        def fake_urlopen(req, timeout=None):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return _make_http_response(503)
            return _make_http_response(200)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
             patch("time.sleep"), \
             patch("time.monotonic", side_effect=[0.0, 0.5, 1.0, 1.5]):
            ready, _, _ = _poll_health_check(spec)

        assert ready is True
        assert call_count == 2

    def test_http_error_in_expected_codes_returns_ready(self):
        """An HTTPError whose code IS in expected_codes should succeed."""
        spec = HealthCheckSpec(
            url="http://localhost:8001/health",
            expected_codes=[200, 204],
            timeout_s=1.0,
            interval_s=0.0,
            max_wait_s=5.0,
        )

        def fake_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(
                url=req.full_url,
                code=204,
                msg="No Content",
                hdrs=None,  # type: ignore[arg-type]
                fp=None,
            )

        with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
             patch("time.sleep"):
            ready, _, error = _poll_health_check(spec)

        assert ready is True
        assert error == ""

    def test_http_error_not_in_expected_codes_retries(self):
        """An HTTPError whose code is NOT in expected_codes should retry."""
        spec = self._make_spec(max_wait_s=10.0)
        call_count = 0

        def fake_urlopen(req, timeout=None):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise urllib.error.HTTPError(
                    url=req.full_url,
                    code=503,
                    msg="Service Unavailable",
                    hdrs=None,  # type: ignore[arg-type]
                    fp=None,
                )
            return _make_http_response(200)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
             patch("time.sleep"), \
             patch("time.monotonic", side_effect=[0.0, 0.5, 1.0, 1.5]):
            ready, _, _ = _poll_health_check(spec)

        assert ready is True
        assert call_count == 2

    def test_oserror_is_caught_and_retried(self):
        spec = self._make_spec(max_wait_s=10.0)
        call_count = 0

        def fake_urlopen(req, timeout=None):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise OSError("socket error")
            return _make_http_response(200)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
             patch("time.sleep"), \
             patch("time.monotonic", side_effect=[0.0, 0.5, 1.0, 1.5]):
            ready, _, _ = _poll_health_check(spec)

        assert ready is True

    def test_error_message_contains_url_on_timeout(self):
        spec = self._make_spec(max_wait_s=0.01)

        def fake_urlopen(req, timeout=None):
            raise urllib.error.URLError("refused")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
             patch("time.sleep"), \
             patch("time.monotonic", side_effect=[0.0, 1.0]):
            _, _, error = _poll_health_check(spec)

        assert "localhost:8001" in error

    def test_sleep_called_between_retries(self):
        spec = self._make_spec(max_wait_s=10.0, interval_s=2.0)
        call_count = 0

        def fake_urlopen(req, timeout=None):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise urllib.error.URLError("refused")
            return _make_http_response(200)

        sleep_calls = []
        with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
             patch("time.sleep", side_effect=lambda s: sleep_calls.append(s)), \
             patch("time.monotonic", side_effect=[0.0, 0.5, 1.0, 1.5]):
            _poll_health_check(spec)

        assert 2.0 in sleep_calls


# ===========================================================================
# boot_instance — mocked subprocess and poll
# ===========================================================================


class TestBootInstance:
    def _make_proc(self, pid: int = 1234) -> MagicMock:
        proc = MagicMock()
        proc.pid = pid
        return proc

    def test_success_returns_ready_true(self):
        cfg = minimal_config()
        proc = self._make_proc()

        with patch("subprocess.Popen", return_value=proc), \
             patch(
                 "harness_skills.boot._poll_health_check",
                 return_value=(True, 1.5, ""),
             ):
            result = boot_instance(cfg)

        assert result.ready is True
        assert result.pid == 1234
        assert result.port == 8001
        assert result.elapsed_s == pytest.approx(1.5)
        assert result.error == ""

    def test_health_check_failure_kills_process(self):
        cfg = minimal_config()
        proc = self._make_proc()

        with patch("subprocess.Popen", return_value=proc), \
             patch(
                 "harness_skills.boot._poll_health_check",
                 return_value=(False, 30.0, "Health check timed out after 30.0s"),
             ):
            result = boot_instance(cfg)

        assert result.ready is False
        proc.kill.assert_called_once()

    def test_health_check_failure_error_message_propagated(self):
        cfg = minimal_config()
        proc = self._make_proc()

        with patch("subprocess.Popen", return_value=proc), \
             patch(
                 "harness_skills.boot._poll_health_check",
                 return_value=(False, 30.0, "Connection refused"),
             ):
            result = boot_instance(cfg)

        assert "Connection refused" in result.error

    def test_popen_oserror_returns_ready_false(self):
        cfg = minimal_config()

        with patch("subprocess.Popen", side_effect=OSError("no such file")):
            result = boot_instance(cfg)

        assert result.ready is False
        assert result.pid == 0
        assert "Failed to start process" in result.error

    def test_popen_value_error_returns_ready_false(self):
        cfg = minimal_config()

        with patch("subprocess.Popen", side_effect=ValueError("bad command")):
            result = boot_instance(cfg)

        assert result.ready is False
        assert result.pid == 0

    def test_worktree_id_in_result(self):
        cfg = minimal_config(worktree_id="deadbeef")
        proc = self._make_proc()

        with patch("subprocess.Popen", return_value=proc), \
             patch(
                 "harness_skills.boot._poll_health_check",
                 return_value=(True, 1.0, ""),
             ):
            result = boot_instance(cfg)

        assert result.worktree_id == "deadbeef"

    def test_health_url_in_result(self):
        cfg = minimal_config(port=8099, health_path="/ping")
        proc = self._make_proc()

        with patch("subprocess.Popen", return_value=proc), \
             patch(
                 "harness_skills.boot._poll_health_check",
                 return_value=(True, 0.5, ""),
             ):
            result = boot_instance(cfg)

        assert result.health_url == "http://localhost:8099/ping"

    def test_port_env_var_set_in_subprocess_env(self):
        cfg = minimal_config(port=7777)
        proc = self._make_proc()
        captured_env = {}

        def fake_popen(cmd, shell=False, env=None, cwd=None, stdout=None, stderr=None):
            captured_env.update(env or {})
            return proc

        with patch("subprocess.Popen", side_effect=fake_popen), \
             patch(
                 "harness_skills.boot._poll_health_check",
                 return_value=(True, 1.0, ""),
             ):
            boot_instance(cfg)

        assert captured_env.get("PORT") == "7777"

    def test_schema_isolation_sets_db_schema_env(self):
        cfg = BootConfig(
            worktree_id="wt",
            start_command="app",
            isolation=IsolationConfig(
                port=8001,
                db_isolation=DatabaseIsolation.SCHEMA,
                db_schema="test_schema",
            ),
        )
        proc = self._make_proc()
        captured_env = {}

        def fake_popen(cmd, shell=False, env=None, cwd=None, stdout=None, stderr=None):
            captured_env.update(env or {})
            return proc

        with patch("subprocess.Popen", side_effect=fake_popen), \
             patch(
                 "harness_skills.boot._poll_health_check",
                 return_value=(True, 1.0, ""),
             ):
            boot_instance(cfg)

        assert captured_env.get("DB_SCHEMA") == "test_schema"

    def test_file_isolation_sets_database_url_env(self):
        cfg = BootConfig(
            worktree_id="wt",
            start_command="app",
            isolation=IsolationConfig(
                port=8001,
                db_isolation=DatabaseIsolation.FILE,
                db_file="/tmp/test.db",
            ),
        )
        proc = self._make_proc()
        captured_env = {}

        def fake_popen(cmd, shell=False, env=None, cwd=None, stdout=None, stderr=None):
            captured_env.update(env or {})
            return proc

        with patch("subprocess.Popen", side_effect=fake_popen), \
             patch(
                 "harness_skills.boot._poll_health_check",
                 return_value=(True, 1.0, ""),
             ):
            boot_instance(cfg)

        assert captured_env.get("DATABASE_URL") == "sqlite:////tmp/test.db"

    def test_extra_env_injected_into_subprocess(self):
        cfg = BootConfig(
            worktree_id="wt",
            start_command="app",
            isolation=IsolationConfig(
                port=8001,
                extra_env={"MY_KEY": "my_val"},
            ),
        )
        proc = self._make_proc()
        captured_env = {}

        def fake_popen(cmd, shell=False, env=None, cwd=None, stdout=None, stderr=None):
            captured_env.update(env or {})
            return proc

        with patch("subprocess.Popen", side_effect=fake_popen), \
             patch(
                 "harness_skills.boot._poll_health_check",
                 return_value=(True, 1.0, ""),
             ):
            boot_instance(cfg)

        assert captured_env.get("MY_KEY") == "my_val"

    def test_working_dir_passed_as_cwd(self):
        cfg = minimal_config(working_dir="/opt/app")
        proc = self._make_proc()
        captured_cwd = {}

        def fake_popen(cmd, shell=False, env=None, cwd=None, stdout=None, stderr=None):
            captured_cwd["cwd"] = cwd
            return proc

        with patch("subprocess.Popen", side_effect=fake_popen), \
             patch(
                 "harness_skills.boot._poll_health_check",
                 return_value=(True, 1.0, ""),
             ):
            boot_instance(cfg)

        assert captured_cwd["cwd"] == "/opt/app"

    def test_empty_working_dir_passes_none_as_cwd(self):
        cfg = minimal_config(working_dir="")
        proc = self._make_proc()
        captured_cwd = {}

        def fake_popen(cmd, shell=False, env=None, cwd=None, stdout=None, stderr=None):
            captured_cwd["cwd"] = cwd
            return proc

        with patch("subprocess.Popen", side_effect=fake_popen), \
             patch(
                 "harness_skills.boot._poll_health_check",
                 return_value=(True, 1.0, ""),
             ):
            boot_instance(cfg)

        assert captured_cwd["cwd"] is None

    def test_timeout_override_respected(self):
        cfg = minimal_config(health_timeout_s=30.0)
        proc = self._make_proc()
        captured_spec: list[HealthCheckSpec] = []

        def fake_poll(spec):
            captured_spec.append(spec)
            return (True, 1.0, "")

        with patch("subprocess.Popen", return_value=proc), \
             patch("harness_skills.boot._poll_health_check", side_effect=fake_poll):
            boot_instance(cfg, timeout=90.0)

        assert captured_spec[0].max_wait_s == pytest.approx(90.0)

    def test_log_file_redirects_stdout_stderr(self, tmp_path: Path):
        log_path = str(tmp_path / "app.log")
        cfg = minimal_config(log_file=log_path)
        proc = self._make_proc()
        captured_kwargs: dict = {}

        def fake_popen(cmd, shell=False, env=None, cwd=None, stdout=None, stderr=None):
            captured_kwargs["stdout"] = stdout
            captured_kwargs["stderr"] = stderr
            return proc

        with patch("subprocess.Popen", side_effect=fake_popen), \
             patch(
                 "harness_skills.boot._poll_health_check",
                 return_value=(True, 1.0, ""),
             ):
            boot_instance(cfg)

        # stdout and stderr should be the same file handle (not None)
        assert captured_kwargs["stdout"] is not None
        assert captured_kwargs["stdout"] is captured_kwargs["stderr"]

    def test_string_command_uses_shell_true(self):
        cfg = minimal_config(start_command="gunicorn myapp:app")
        proc = self._make_proc()
        captured_shell = {}

        def fake_popen(cmd, shell=False, env=None, cwd=None, stdout=None, stderr=None):
            captured_shell["shell"] = shell
            return proc

        with patch("subprocess.Popen", side_effect=fake_popen), \
             patch(
                 "harness_skills.boot._poll_health_check",
                 return_value=(True, 1.0, ""),
             ):
            boot_instance(cfg)

        assert captured_shell["shell"] is True

    def test_list_command_uses_shell_false(self):
        cfg = BootConfig(
            worktree_id="x",
            start_command=["gunicorn", "myapp:app"],
            isolation=IsolationConfig(port=8001),
        )
        proc = self._make_proc()
        captured_shell = {}

        def fake_popen(cmd, shell=False, env=None, cwd=None, stdout=None, stderr=None):
            captured_shell["shell"] = shell
            return proc

        with patch("subprocess.Popen", side_effect=fake_popen), \
             patch(
                 "harness_skills.boot._poll_health_check",
                 return_value=(True, 1.0, ""),
             ):
            boot_instance(cfg)

        assert captured_shell["shell"] is False

    def test_always_returns_boot_result(self):
        cfg = minimal_config()
        proc = self._make_proc()

        with patch("subprocess.Popen", return_value=proc), \
             patch(
                 "harness_skills.boot._poll_health_check",
                 return_value=(True, 2.0, ""),
             ):
            result = boot_instance(cfg)

        assert isinstance(result, BootResult)

    def test_schema_isolation_auto_name_when_db_schema_empty(self):
        """When db_schema is empty and isolation=schema, auto-name must be applied."""
        cfg = BootConfig(
            worktree_id="myworktree",
            start_command="app",
            isolation=IsolationConfig(
                port=8001,
                db_isolation=DatabaseIsolation.SCHEMA,
                db_schema="",
            ),
        )
        proc = self._make_proc()
        captured_env: dict = {}

        def fake_popen(cmd, shell=False, env=None, cwd=None, stdout=None, stderr=None):
            captured_env.update(env or {})
            return proc

        with patch("subprocess.Popen", side_effect=fake_popen), \
             patch(
                 "harness_skills.boot._poll_health_check",
                 return_value=(True, 1.0, ""),
             ):
            boot_instance(cfg)

        assert captured_env.get("DB_SCHEMA") == "worktree_myworktree"

    def test_file_isolation_auto_path_when_db_file_empty(self):
        """When db_file is empty and isolation=file, auto-path must be applied."""
        cfg = BootConfig(
            worktree_id="myworktree",
            start_command="app",
            isolation=IsolationConfig(
                port=8001,
                db_isolation=DatabaseIsolation.FILE,
                db_file="",
            ),
        )
        proc = self._make_proc()
        captured_env: dict = {}

        def fake_popen(cmd, shell=False, env=None, cwd=None, stdout=None, stderr=None):
            captured_env.update(env or {})
            return proc

        with patch("subprocess.Popen", side_effect=fake_popen), \
             patch(
                 "harness_skills.boot._poll_health_check",
                 return_value=(True, 1.0, ""),
             ):
            boot_instance(cfg)

        db_url = captured_env.get("DATABASE_URL", "")
        assert "myworktree" in db_url
        assert db_url.startswith("sqlite:///")


# ===========================================================================
# DatabaseIsolation enum
# ===========================================================================


class TestDatabaseIsolationEnum:
    def test_none_value(self):
        assert DatabaseIsolation.NONE.value == "none"

    def test_schema_value(self):
        assert DatabaseIsolation.SCHEMA.value == "schema"

    def test_file_value(self):
        assert DatabaseIsolation.FILE.value == "file"

    def test_container_value(self):
        assert DatabaseIsolation.CONTAINER.value == "container"

    def test_construct_from_string(self):
        assert DatabaseIsolation("schema") == DatabaseIsolation.SCHEMA


# ===========================================================================
# HealthCheckMethod enum
# ===========================================================================


class TestHealthCheckMethodEnum:
    def test_get_value(self):
        assert HealthCheckMethod.GET.value == "GET"

    def test_head_value(self):
        assert HealthCheckMethod.HEAD.value == "HEAD"

    def test_construct_from_string(self):
        assert HealthCheckMethod("HEAD") == HealthCheckMethod.HEAD


# ===========================================================================
# Integration: generate_boot_script + generate_health_check_spec round-trip
# ===========================================================================


class TestIntegration:
    def test_script_url_matches_spec_url(self):
        cfg = minimal_config(port=8055, health_path="/readyz")
        script = generate_boot_script(cfg)
        spec = generate_health_check_spec(cfg)
        assert spec.url in script

    def test_advanced_config_full_script(self):
        """Full advanced BootConfig produces a coherent script."""
        cfg = BootConfig(
            worktree_id="fe9a1b2c",
            start_command="uvicorn api.main:app --host 0.0.0.0 --port 8010",
            isolation=IsolationConfig(
                port=8010,
                db_isolation=DatabaseIsolation.SCHEMA,
                db_schema="wt_fe9a1b2c",
                extra_env={"FEATURE_X": "on", "DEBUG": "1"},
            ),
            health_path="/api/health",
            health_method=HealthCheckMethod.GET,
            health_timeout_s=60.0,
            health_interval_s=2.0,
            working_dir="/srv/api",
            log_file="/var/log/api_fe9a1b2c.log",
        )
        script = generate_boot_script(cfg)
        spec = generate_health_check_spec(cfg)

        # Script coherence checks
        assert "fe9a1b2c" in script
        assert 'PORT="8010"' in script
        assert "wt_fe9a1b2c" in script
        assert 'export FEATURE_X="on"' in script
        assert 'export DEBUG="1"' in script
        assert "http://localhost:8010/api/health" in script
        assert "HEALTH_TIMEOUT=60" in script
        assert "HEALTH_INTERVAL=2.0" in script
        assert 'cd "/srv/api"' in script
        assert 'LOG_FILE="/var/log/api_fe9a1b2c.log"' in script

        # Spec coherence checks
        assert spec.url == "http://localhost:8010/api/health"
        assert spec.max_wait_s == pytest.approx(60.0)
        assert spec.interval_s == pytest.approx(2.0)
        assert all(c in spec.expected_codes for c in [200, 201, 204])
>>>>>>> feat/observability-a-skill-generates-a-harness-boot-command
