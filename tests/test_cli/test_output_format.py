"""Tests for the ``--output-format`` flag across all harness CLI commands.

Covers:
    - ``resolve_output_format`` auto-detection (TTY vs non-TTY)
    - ``--output-format json|yaml|table`` accepted by every command
    - Structured JSON output is parseable for evaluate, status, manifest, create, telemetry
    - YAML output is parseable for evaluate, status, manifest, create, telemetry
    - TTY default: table when stdout is a TTY, json when not (non-TTY is default in CliRunner)
    - Backward-compat: ``--json`` still works for ``harness manifest validate``
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from harness_skills.cli.fmt import resolve_output_format
from harness_skills.cli.main import cli
from harness_skills.cli.manifest import manifest_cmd
from harness_skills.generators.manifest_generator import generate_manifest
from harness_skills.models.create import DetectedStack, GeneratedArtifact


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_STACK = DetectedStack(
    primary_language="python",
    project_structure="single-app",
)


def _write_valid_manifest(path: Path) -> None:
    path.write_text(
        json.dumps(generate_manifest(VALID_STACK), indent=2),
        encoding="utf-8",
    )


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# resolve_output_format unit tests
# ---------------------------------------------------------------------------


class TestResolveOutputFormat:
    def test_explicit_json_returned_as_is(self):
        assert resolve_output_format("json") == "json"

    def test_explicit_yaml_returned_as_is(self):
        assert resolve_output_format("yaml") == "yaml"

    def test_explicit_table_returned_as_is(self):
        assert resolve_output_format("table") == "table"

    def test_explicit_values_are_lowercased(self):
        assert resolve_output_format("JSON") == "json"
        assert resolve_output_format("YAML") == "yaml"
        assert resolve_output_format("TABLE") == "table"

    def test_none_with_tty_returns_table(self):
        with patch.object(sys.stdout, "isatty", return_value=True):
            assert resolve_output_format(None) == "table"

    def test_none_without_tty_returns_json(self):
        with patch.object(sys.stdout, "isatty", return_value=False):
            assert resolve_output_format(None) == "json"


# ---------------------------------------------------------------------------
# harness manifest validate --output-format
# ---------------------------------------------------------------------------


class TestManifestOutputFormat:
    def test_json_produces_parseable_output(self, runner, tmp_path):
        manifest = tmp_path / "harness_manifest.json"
        _write_valid_manifest(manifest)
        result = runner.invoke(
            manifest_cmd, ["validate", str(manifest), "--output-format", "json"]
        )
        assert result.exit_code == 0, result.output
        report = json.loads(result.output)
        assert report["valid"] is True
        assert report["error_count"] == 0

    def test_yaml_produces_parseable_output(self, runner, tmp_path):
        manifest = tmp_path / "harness_manifest.json"
        _write_valid_manifest(manifest)
        result = runner.invoke(
            manifest_cmd, ["validate", str(manifest), "--output-format", "yaml"]
        )
        assert result.exit_code == 0, result.output
        report = yaml.safe_load(result.output)
        assert report["valid"] is True
        assert report["error_count"] == 0

    def test_table_produces_human_readable(self, runner, tmp_path):
        manifest = tmp_path / "harness_manifest.json"
        _write_valid_manifest(manifest)
        result = runner.invoke(
            manifest_cmd, ["validate", str(manifest), "--output-format", "table"]
        )
        assert result.exit_code == 0, result.output
        assert "valid" in result.output.lower()
        # Should NOT be JSON
        with pytest.raises(json.JSONDecodeError):
            json.loads(result.output)

    def test_json_flag_still_works_as_alias(self, runner, tmp_path):
        """Backward compat: --json maps to --output-format json."""
        manifest = tmp_path / "harness_manifest.json"
        _write_valid_manifest(manifest)
        result = runner.invoke(manifest_cmd, ["validate", str(manifest), "--json"])
        assert result.exit_code == 0, result.output
        report = json.loads(result.output)
        assert report["valid"] is True

    def test_non_tty_defaults_to_json(self, runner, tmp_path):
        """CliRunner stdout is not a TTY — default should be json."""
        manifest = tmp_path / "harness_manifest.json"
        _write_valid_manifest(manifest)
        # CliRunner is not a TTY by default
        result = runner.invoke(manifest_cmd, ["validate", str(manifest)])
        assert result.exit_code == 0, result.output
        # Should be parseable JSON
        report = json.loads(result.output)
        assert report["valid"] is True

    def test_yaml_invalid_manifest_exits_1(self, runner, tmp_path):
        manifest = tmp_path / "harness_manifest.json"
        m = generate_manifest(VALID_STACK)
        del m["detected_stack"]["project_structure"]
        manifest.write_text(json.dumps(m), encoding="utf-8")
        result = runner.invoke(
            manifest_cmd, ["validate", str(manifest), "--output-format", "yaml"]
        )
        assert result.exit_code == 1
        report = yaml.safe_load(result.output)
        assert report["valid"] is False
        assert report["error_count"] >= 1

    def test_json_missing_file_emits_structured_error(self, runner, tmp_path):
        missing = tmp_path / "nope.json"
        result = runner.invoke(
            manifest_cmd, ["validate", str(missing), "--output-format", "json"]
        )
        assert result.exit_code == 2
        report = json.loads(result.output)
        assert report["valid"] is False

    def test_yaml_missing_file_emits_structured_error(self, runner, tmp_path):
        missing = tmp_path / "nope.json"
        result = runner.invoke(
            manifest_cmd, ["validate", str(missing), "--output-format", "yaml"]
        )
        assert result.exit_code == 2
        report = yaml.safe_load(result.output)
        assert report["valid"] is False


# ---------------------------------------------------------------------------
# harness create --output-format
# ---------------------------------------------------------------------------

# The real config_generator may have pre-existing bugs unrelated to output
# format; we mock it out so we can test the flag plumbing in isolation.
_MOCK_GATES_YAML = "# gates:\n  coverage: {threshold: 90}\n"


def _patch_generator():
    """Patch harness_skills.cli.create._get_generator with stub functions."""
    def _fake_get_generator():
        def _generate(profile, detected_stack=None):
            return _MOCK_GATES_YAML

        def _write(path, profile, detected_stack=None, merge=False):
            Path(path).write_text("gates: {}", encoding="utf-8")

        return _generate, _write

    return patch(
        "harness_skills.cli.create._get_generator",
        side_effect=_fake_get_generator,
    )


class TestCreateOutputFormat:
    def test_json_produces_parseable_output(self, runner, tmp_path):
        with _patch_generator():
            result = runner.invoke(
                cli,
                [
                    "create",
                    "--output", str(tmp_path / "harness.config.yaml"),
                    "--output-format", "json",
                ],
            )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert data["action"] in ("created", "updated")
        assert "path" in data
        assert "profile" in data

    def test_yaml_produces_parseable_output(self, runner, tmp_path):
        with _patch_generator():
            result = runner.invoke(
                cli,
                [
                    "create",
                    "--output", str(tmp_path / "harness.config.yaml"),
                    "--output-format", "yaml",
                ],
            )
        assert result.exit_code == 0, result.output
        data = yaml.safe_load(result.output)
        assert data["status"] == "ok"
        assert data["action"] in ("created", "updated")

    def test_table_produces_human_readable(self, runner, tmp_path):
        with _patch_generator():
            result = runner.invoke(
                cli,
                [
                    "create",
                    "--output", str(tmp_path / "harness.config.yaml"),
                    "--output-format", "table",
                ],
            )
        assert result.exit_code == 0, result.output
        # Human-readable: contains "Created" or "Updated"
        assert any(
            word in result.output for word in ("Created", "Updated", "created", "updated")
        )
        # Should NOT be JSON
        with pytest.raises((json.JSONDecodeError, ValueError)):
            json.loads(result.output)

    def test_non_tty_defaults_to_json(self, runner, tmp_path):
        """CliRunner is not a TTY — create should default to json output."""
        with _patch_generator():
            result = runner.invoke(
                cli,
                ["create", "--output", str(tmp_path / "harness.config.yaml")],
            )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["status"] == "ok"

    def test_json_includes_profile_and_stack(self, runner, tmp_path):
        with _patch_generator():
            result = runner.invoke(
                cli,
                [
                    "create",
                    "--output", str(tmp_path / "harness.config.yaml"),
                    "--profile", "standard",
                    "--stack", "python",
                    "--output-format", "json",
                ],
            )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["profile"] == "standard"
        assert data["stack"] == "python"

    def test_dry_run_always_emits_yaml_gates(self, runner, tmp_path):
        """--dry-run output is the YAML gates block regardless of --output-format."""
        with _patch_generator():
            result = runner.invoke(
                cli,
                [
                    "create",
                    "--dry-run",
                    "--output-format", "json",
                ],
            )
        assert result.exit_code == 0, result.output
        # Dry-run always prints a YAML gates comment header
        assert "dry-run" in result.output


# ---------------------------------------------------------------------------
# harness evaluate --output-format
# ---------------------------------------------------------------------------


class TestEvaluateOutputFormat:
    def test_json_flag_accepted(self, runner, tmp_path):
        result = runner.invoke(
            cli,
            [
                "evaluate",
                "--project-root", str(tmp_path),
                "--output-format", "json",
            ],
        )
        # exit code 0 or 1 depending on gates; just verify JSON is parseable
        assert result.exit_code in (0, 1), result.output
        data = json.loads(result.output)
        assert "passed" in data

    def test_yaml_flag_accepted(self, runner, tmp_path):
        result = runner.invoke(
            cli,
            [
                "evaluate",
                "--project-root", str(tmp_path),
                "--output-format", "yaml",
            ],
        )
        assert result.exit_code in (0, 1), result.output
        data = yaml.safe_load(result.output)
        assert "passed" in data

    def test_table_flag_accepted(self, runner, tmp_path):
        result = runner.invoke(
            cli,
            [
                "evaluate",
                "--project-root", str(tmp_path),
                "--output-format", "table",
            ],
        )
        assert result.exit_code in (0, 1), result.output
        # Table output is not valid JSON
        with pytest.raises((json.JSONDecodeError, ValueError)):
            json.loads(result.output)

    def test_non_tty_defaults_to_json(self, runner, tmp_path):
        result = runner.invoke(
            cli, ["evaluate", "--project-root", str(tmp_path)]
        )
        assert result.exit_code in (0, 1), result.output
        data = json.loads(result.output)
        assert "passed" in data

    def test_invalid_format_rejected(self, runner, tmp_path):
        result = runner.invoke(
            cli,
            [
                "evaluate",
                "--project-root", str(tmp_path),
                "--output-format", "xml",
            ],
        )
        assert result.exit_code != 0
        assert "xml" in result.output.lower() or "invalid" in result.output.lower()


# ---------------------------------------------------------------------------
# harness telemetry --output-format
# ---------------------------------------------------------------------------


class TestTelemetryOutputFormat:
    def _run(self, runner, tmp_path, fmt: Optional[str] = None) -> "Result":  # type: ignore[name-defined]
        args = ["telemetry", "--telemetry-file", str(tmp_path / "telemetry.json")]
        if fmt:
            args += ["--output-format", fmt]
        return runner.invoke(cli, args)

    def test_json_produces_parseable_output(self, runner, tmp_path):
        result = self._run(runner, tmp_path, fmt="json")
        assert result.exit_code in (0, 1), result.output
        data = json.loads(result.output)
        assert "artifacts" in data
        assert "commands" in data
        assert "gates" in data

    def test_yaml_produces_parseable_output(self, runner, tmp_path):
        result = self._run(runner, tmp_path, fmt="yaml")
        assert result.exit_code in (0, 1), result.output
        data = yaml.safe_load(result.output)
        assert "artifacts" in data

    def test_table_produces_human_readable(self, runner, tmp_path):
        result = self._run(runner, tmp_path, fmt="table")
        assert result.exit_code in (0, 1), result.output
        assert "Harness Telemetry Report" in result.output

    def test_non_tty_defaults_to_json(self, runner, tmp_path):
        result = self._run(runner, tmp_path)
        assert result.exit_code in (0, 1), result.output
        data = json.loads(result.output)
        assert "artifacts" in data


# ---------------------------------------------------------------------------
# harness status --output-format (smoke tests — no live state service needed)
# ---------------------------------------------------------------------------


class TestStatusOutputFormat:
    def _plan_file(self, tmp_path: Path) -> Path:
        plan = {
            "plan": {"id": "p1", "title": "Test Plan", "status": "running"},
            "tasks": [
                {"id": "t1", "title": "Task one", "status": "done", "priority": "medium"},
            ],
        }
        p = tmp_path / "plan.yaml"
        import yaml as _yaml
        p.write_text(_yaml.dump(plan), encoding="utf-8")
        return p

    def test_json_produces_parseable_output(self, runner, tmp_path):
        plan = self._plan_file(tmp_path)
        result = runner.invoke(
            cli,
            [
                "status",
                "--plan-file", str(plan),
                "--no-state-service",
                "--output-format", "json",
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "summary" in data
        assert "plans" in data

    def test_yaml_produces_parseable_output(self, runner, tmp_path):
        plan = self._plan_file(tmp_path)
        result = runner.invoke(
            cli,
            [
                "status",
                "--plan-file", str(plan),
                "--no-state-service",
                "--output-format", "yaml",
            ],
        )
        assert result.exit_code == 0, result.output
        data = yaml.safe_load(result.output)
        assert "summary" in data

    def test_table_produces_human_readable(self, runner, tmp_path):
        plan = self._plan_file(tmp_path)
        result = runner.invoke(
            cli,
            [
                "status",
                "--plan-file", str(plan),
                "--no-state-service",
                "--output-format", "table",
            ],
        )
        assert result.exit_code == 0, result.output
        with pytest.raises((json.JSONDecodeError, ValueError)):
            json.loads(result.output)

    def test_non_tty_defaults_to_json(self, runner, tmp_path):
        plan = self._plan_file(tmp_path)
        result = runner.invoke(
            cli,
            ["status", "--plan-file", str(plan), "--no-state-service"],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "summary" in data
