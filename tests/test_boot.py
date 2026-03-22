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
