"""Tests for harness_skills.cli.boot (``harness boot``).

Uses Click's ``CliRunner`` for isolated, subprocess-free invocations.
All calls to harness_skills.boot are mocked.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner

from harness_skills.cli.boot import _parse_env_pairs, boot_cmd


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _mock_boot_api(ready: bool = True, pid: int = 1234, elapsed: float = 1.5, error: str = ""):
    """Return a tuple of mocks matching _get_boot_api return shape."""
    from harness_skills.boot import (
        BootConfig,
        BootResult,
        DatabaseIsolation,
        HealthCheckMethod,
        IsolationConfig,
    )

    def fake_boot_instance(config):
        return BootResult(
            worktree_id=config.worktree_id,
            pid=pid,
            port=config.isolation.port,
            health_url=f"http://localhost:{config.isolation.port}{config.health_path}",
            ready=ready,
            elapsed_s=elapsed,
            error=error,
        )

    def fake_generate_script(config):
        return f"#!/bin/bash\n# boot {config.worktree_id}\necho 'hello'"

    return (
        BootConfig,
        DatabaseIsolation,
        HealthCheckMethod,
        IsolationConfig,
        fake_boot_instance,
        fake_generate_script,
    )


# ===========================================================================
# _parse_env_pairs
# ===========================================================================


class TestParseEnvPairs:
    def test_empty_tuple(self):
        assert _parse_env_pairs(()) == {}

    def test_single_pair(self):
        assert _parse_env_pairs(("FOO=bar",)) == {"FOO": "bar"}

    def test_multiple_pairs(self):
        result = _parse_env_pairs(("A=1", "B=2"))
        assert result == {"A": "1", "B": "2"}

    def test_value_with_equals_sign(self):
        result = _parse_env_pairs(("DSN=postgres://host:5432/db?opt=val",))
        assert result == {"DSN": "postgres://host:5432/db?opt=val"}

    def test_empty_value(self):
        result = _parse_env_pairs(("KEY=",))
        assert result == {"KEY": ""}

    def test_missing_equals_raises(self):
        import click

        with pytest.raises(click.BadParameter, match="KEY_VALUE"):
            _parse_env_pairs(("KEY_VALUE",))


# ===========================================================================
# boot_cmd — launch mode (default)
# ===========================================================================


class TestBootCmdLaunch:
    @patch("harness_skills.cli.boot._get_boot_api")
    def test_launch_success_exits_zero(self, mock_api, runner: CliRunner):
        mock_api.return_value = _mock_boot_api(ready=True)
        result = runner.invoke(boot_cmd, [
            "--worktree-id", "task-123",
            "--command", "uvicorn app:main",
            "--port", "8001",
        ])
        assert result.exit_code == 0
        assert "ready" in result.output.lower()

    @patch("harness_skills.cli.boot._get_boot_api")
    def test_launch_shows_instance_details(self, mock_api, runner: CliRunner):
        mock_api.return_value = _mock_boot_api(ready=True, pid=9999)
        result = runner.invoke(boot_cmd, [
            "--worktree-id", "task-456",
            "--command", "python server.py",
        ])
        assert "9999" in result.output  # PID
        assert "8000" in result.output  # default port
        assert "/health" in result.output  # default health path

    @patch("harness_skills.cli.boot._get_boot_api")
    def test_launch_failure_exits_one(self, mock_api, runner: CliRunner):
        mock_api.return_value = _mock_boot_api(ready=False, error="timeout")
        result = runner.invoke(boot_cmd, [
            "--worktree-id", "task-789",
            "--command", "python app.py",
        ])
        assert result.exit_code == 1
        assert "failed" in result.output.lower() or "timeout" in result.output.lower()

    @patch("harness_skills.cli.boot._get_boot_api")
    def test_launch_with_db_isolation_schema(self, mock_api, runner: CliRunner):
        mock_api.return_value = _mock_boot_api(ready=True)
        result = runner.invoke(boot_cmd, [
            "--worktree-id", "task-s",
            "--command", "python app.py",
            "--db-isolation", "schema",
        ])
        assert result.exit_code == 0
        assert "schema" in result.output.lower()

    @patch("harness_skills.cli.boot._get_boot_api")
    def test_launch_with_db_isolation_file(self, mock_api, runner: CliRunner):
        mock_api.return_value = _mock_boot_api(ready=True)
        result = runner.invoke(boot_cmd, [
            "--worktree-id", "task-f",
            "--command", "python app.py",
            "--db-isolation", "file",
        ])
        assert result.exit_code == 0
        assert "file" in result.output.lower()

    @patch("harness_skills.cli.boot._get_boot_api")
    def test_launch_with_db_isolation_container(self, mock_api, runner: CliRunner):
        mock_api.return_value = _mock_boot_api(ready=True)
        result = runner.invoke(boot_cmd, [
            "--worktree-id", "task-c",
            "--command", "python app.py",
            "--db-isolation", "container",
        ])
        assert result.exit_code == 0
        assert "container" in result.output.lower()

    @patch("harness_skills.cli.boot._get_boot_api")
    def test_launch_with_log_file(self, mock_api, runner: CliRunner):
        mock_api.return_value = _mock_boot_api(ready=True)
        result = runner.invoke(boot_cmd, [
            "--worktree-id", "task-l",
            "--command", "python app.py",
            "--log-file", "/tmp/app.log",
        ])
        assert result.exit_code == 0
        assert "/tmp/app.log" in result.output

    @patch("harness_skills.cli.boot._get_boot_api")
    def test_launch_without_log_file_shows_inherited(self, mock_api, runner: CliRunner):
        mock_api.return_value = _mock_boot_api(ready=True)
        result = runner.invoke(boot_cmd, [
            "--worktree-id", "task-nl",
            "--command", "python app.py",
        ])
        assert result.exit_code == 0
        assert "inherited" in result.output.lower()

    @patch("harness_skills.cli.boot._get_boot_api")
    def test_launch_with_custom_db_schema(self, mock_api, runner: CliRunner):
        mock_api.return_value = _mock_boot_api(ready=True)
        result = runner.invoke(boot_cmd, [
            "--worktree-id", "task-ds",
            "--command", "python app.py",
            "--db-isolation", "schema",
            "--db-schema", "myschema",
        ])
        assert result.exit_code == 0
        assert "myschema" in result.output

    @patch("harness_skills.cli.boot._get_boot_api")
    def test_launch_with_custom_db_file(self, mock_api, runner: CliRunner):
        mock_api.return_value = _mock_boot_api(ready=True)
        result = runner.invoke(boot_cmd, [
            "--worktree-id", "task-df",
            "--command", "python app.py",
            "--db-isolation", "file",
            "--db-file", "/tmp/my.db",
        ])
        assert result.exit_code == 0
        assert "/tmp/my.db" in result.output


# ===========================================================================
# boot_cmd — dry-run mode
# ===========================================================================


class TestBootCmdDryRun:
    @patch("harness_skills.cli.boot._get_boot_api")
    def test_dry_run_prints_script(self, mock_api, runner: CliRunner):
        mock_api.return_value = _mock_boot_api()
        result = runner.invoke(boot_cmd, [
            "--worktree-id", "task-dry",
            "--command", "python app.py",
            "--dry-run",
        ])
        assert result.exit_code == 0
        assert "DRY-RUN" in result.output
        assert "#!/bin/bash" in result.output

    @patch("harness_skills.cli.boot._get_boot_api")
    def test_dry_run_does_not_launch(self, mock_api, runner: CliRunner):
        api = _mock_boot_api()
        # Replace boot_instance with a mock to verify it's NOT called
        boot_fn = MagicMock()
        api_list = list(api)
        api_list[4] = boot_fn
        mock_api.return_value = tuple(api_list)
        result = runner.invoke(boot_cmd, [
            "--worktree-id", "task-dry2",
            "--command", "python app.py",
            "--dry-run",
        ])
        assert result.exit_code == 0
        boot_fn.assert_not_called()


# ===========================================================================
# boot_cmd — generate-script mode
# ===========================================================================


class TestBootCmdGenerateScript:
    @patch("harness_skills.cli.boot._get_boot_api")
    def test_generate_script_creates_file(self, mock_api, runner: CliRunner, tmp_path: Path):
        mock_api.return_value = _mock_boot_api()
        out_path = str(tmp_path / "boot.sh")
        result = runner.invoke(boot_cmd, [
            "--worktree-id", "task-gen",
            "--command", "python app.py",
            "--generate-script",
            "--output", out_path,
        ])
        assert result.exit_code == 0
        assert Path(out_path).exists()
        assert "script generated" in result.output.lower() or "generate-script" in result.output.lower()

    @patch("harness_skills.cli.boot._get_boot_api")
    def test_generate_script_default_filename(self, mock_api, runner: CliRunner, tmp_path: Path):
        mock_api.return_value = _mock_boot_api()
        result = runner.invoke(boot_cmd, [
            "--worktree-id", "task-def",
            "--command", "python app.py",
            "--generate-script",
        ], catch_exceptions=False)
        # Default filename: boot_<worktree_id>.sh
        expected = Path("boot_task-def.sh")
        # Clean up if created in cwd
        if expected.exists():
            expected.unlink()

    @patch("harness_skills.cli.boot._get_boot_api")
    def test_generate_script_file_is_executable(self, mock_api, runner: CliRunner, tmp_path: Path):
        mock_api.return_value = _mock_boot_api()
        out_path = str(tmp_path / "boot_exec.sh")
        runner.invoke(boot_cmd, [
            "--worktree-id", "task-exec",
            "--command", "python app.py",
            "--generate-script",
            "--output", out_path,
        ])
        assert os.access(out_path, os.X_OK)

    @patch("harness_skills.cli.boot._get_boot_api")
    def test_generate_script_write_failure(self, mock_api, runner: CliRunner):
        mock_api.return_value = _mock_boot_api()
        result = runner.invoke(boot_cmd, [
            "--worktree-id", "task-wf",
            "--command", "python app.py",
            "--generate-script",
            "--output", "/nonexistent/dir/boot.sh",
        ])
        assert result.exit_code == 1
        assert "failed" in result.output.lower() or "error" in result.output.lower()


# ===========================================================================
# boot_cmd — env parsing errors
# ===========================================================================


class TestBootCmdEnvErrors:
    @patch("harness_skills.cli.boot._get_boot_api")
    def test_invalid_env_format_exits_one(self, mock_api, runner: CliRunner):
        mock_api.return_value = _mock_boot_api()
        result = runner.invoke(boot_cmd, [
            "--worktree-id", "task-env",
            "--command", "python app.py",
            "--env", "BADFORMAT",
        ])
        assert result.exit_code == 1

    @patch("harness_skills.cli.boot._get_boot_api")
    def test_valid_env_pairs_pass_through(self, mock_api, runner: CliRunner):
        mock_api.return_value = _mock_boot_api(ready=True)
        result = runner.invoke(boot_cmd, [
            "--worktree-id", "task-envok",
            "--command", "python app.py",
            "--env", "FOO=bar",
            "--env", "BAZ=qux",
        ])
        assert result.exit_code == 0


# ===========================================================================
# boot_cmd — dependency import error
# ===========================================================================


class TestBootCmdDependencyError:
    @patch("harness_skills.cli.boot._get_boot_api")
    def test_import_error_exits_one(self, mock_api, runner: CliRunner):
        mock_api.side_effect = ImportError("no module named harness_skills.boot")
        result = runner.invoke(boot_cmd, [
            "--worktree-id", "task-ie",
            "--command", "python app.py",
        ])
        assert result.exit_code == 1
        assert "dependency error" in result.output.lower() or "error" in result.output.lower()


# ===========================================================================
# boot_cmd — health options
# ===========================================================================


class TestGetBootApi:
    """Test _get_boot_api lazy import."""

    def test_get_boot_api_returns_expected_tuple(self):
        from harness_skills.cli.boot import _get_boot_api

        result = _get_boot_api()
        assert len(result) == 6
        # Check that the types are correct
        from harness_skills.boot import (
            BootConfig,
            DatabaseIsolation,
            HealthCheckMethod,
            IsolationConfig,
            boot_instance,
            generate_boot_script,
        )

        assert result[0] is BootConfig
        assert result[1] is DatabaseIsolation
        assert result[2] is HealthCheckMethod
        assert result[3] is IsolationConfig
        assert result[4] is boot_instance
        assert result[5] is generate_boot_script


class TestBootCmdReturnAfterExit:
    """Use a real Click context with patched exit to reach return stmts."""

    @patch("harness_skills.cli.boot._get_boot_api")
    def test_dependency_error_return_reached(self, mock_api):
        mock_api.side_effect = RuntimeError("boom")
        with click.Context(boot_cmd) as ctx:
            ctx.exit = MagicMock()
            boot_cmd.callback(
                "t", "c", 8000, "/health", "GET", 30.0, 1.0,
                "none", "", "", (), "", "", "launch", None, False,
            )
        ctx.exit.assert_called_with(1)

    @patch("harness_skills.cli.boot._get_boot_api")
    def test_env_parse_error_return_reached(self, mock_api):
        mock_api.return_value = _mock_boot_api()
        with click.Context(boot_cmd) as ctx:
            ctx.exit = MagicMock()
            boot_cmd.callback(
                "t", "c", 8000, "/health", "GET", 30.0, 1.0,
                "none", "", "", ("NOEQ",), "", "", "launch", None, False,
            )
        ctx.exit.assert_called_with(1)

    @patch("harness_skills.cli.boot._get_boot_api")
    def test_script_write_error_return_reached(self, mock_api):
        mock_api.return_value = _mock_boot_api()
        with click.Context(boot_cmd) as ctx:
            ctx.exit = MagicMock()
            boot_cmd.callback(
                "t", "c", 8000, "/health", "GET", 30.0, 1.0,
                "none", "", "", (), "", "", "script", "/no/such/dir/s.sh", False,
            )
        ctx.exit.assert_called_with(1)

    @patch("harness_skills.cli.boot._get_boot_api")
    def test_launch_failure_return_reached(self, mock_api):
        mock_api.return_value = _mock_boot_api(ready=False, error="timeout")
        with click.Context(boot_cmd) as ctx:
            ctx.exit = MagicMock()
            boot_cmd.callback(
                "t", "c", 8000, "/health", "GET", 30.0, 1.0,
                "none", "", "", (), "", "", "launch", None, False,
            )
        ctx.exit.assert_called_with(1)


class TestBootCmdHealthOptions:
    @patch("harness_skills.cli.boot._get_boot_api")
    def test_custom_health_path(self, mock_api, runner: CliRunner):
        mock_api.return_value = _mock_boot_api(ready=True)
        result = runner.invoke(boot_cmd, [
            "--worktree-id", "task-hp",
            "--command", "python app.py",
            "--health-path", "/api/healthz",
        ])
        assert result.exit_code == 0
        assert "/api/healthz" in result.output

    @patch("harness_skills.cli.boot._get_boot_api")
    def test_custom_health_method(self, mock_api, runner: CliRunner):
        mock_api.return_value = _mock_boot_api(ready=True)
        result = runner.invoke(boot_cmd, [
            "--worktree-id", "task-hm",
            "--command", "python app.py",
            "--health-method", "HEAD",
        ])
        assert result.exit_code == 0

    @patch("harness_skills.cli.boot._get_boot_api")
    def test_custom_health_timeout(self, mock_api, runner: CliRunner):
        mock_api.return_value = _mock_boot_api(ready=True)
        result = runner.invoke(boot_cmd, [
            "--worktree-id", "task-ht",
            "--command", "python app.py",
            "--health-timeout", "60",
        ])
        assert result.exit_code == 0

    def test_port_out_of_range(self, runner: CliRunner):
        result = runner.invoke(boot_cmd, [
            "--worktree-id", "task-pr",
            "--command", "python app.py",
            "--port", "99999",
        ])
        assert result.exit_code != 0
