"""Tests for the output format flags across harness CLI commands.

Covers:
    - ``resolve_output_format`` auto-detection (TTY vs non-TTY)
    - ``--format json|yaml|table`` accepted by evaluate, status, create
    - ``--json`` still works for ``harness manifest validate``
    - Structured JSON output is parseable for evaluate, status, create
    - YAML output is parseable for evaluate, status
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
from harness_skills.models.create import DetectedStack, GeneratedArtifact


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Use only fields that exist in the schema's DetectedStack definition
# (no linter, documentation_files — those are model-only fields not in schema)
VALID_STACK = DetectedStack(
    primary_language="python",
    project_structure="single-app",
)


def _write_valid_manifest(path: Path) -> None:
    """Write a manifest that passes schema validation.

    We manually build the dict to avoid the DetectedStack model serializing
    extra fields (linter, documentation_files) that the JSON Schema does not
    allow.
    """
    from datetime import datetime, timezone

    manifest = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": None,
        "git_branch": None,
        "harness_version": None,
        "project_root": None,
        "detected_stack": {
            "primary_language": "python",
            "project_structure": "single-app",
        },
        "domains": [],
        "patterns": [],
        "conventions": [],
        "artifacts": [],
        "manifest_path": None,
        "schema_path": None,
        "symbols_index_path": None,
    }
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


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
# harness manifest validate -- uses --json flag (not --output-format)
# ---------------------------------------------------------------------------


class TestManifestOutputFormat:
    def test_json_flag_produces_parseable_output(self, runner, tmp_path):
        manifest = tmp_path / "harness_manifest.json"
        _write_valid_manifest(manifest)
        result = runner.invoke(
            manifest_cmd, ["validate", str(manifest), "--json"]
        )
        assert result.exit_code == 0, result.output
        report = json.loads(result.output)
        assert report["valid"] is True
        assert report["error_count"] == 0

    def test_json_flag_still_works(self, runner, tmp_path):
        """--json maps to output_json=True on manifest validate."""
        manifest = tmp_path / "harness_manifest.json"
        _write_valid_manifest(manifest)
        result = runner.invoke(manifest_cmd, ["validate", str(manifest), "--json"])
        assert result.exit_code == 0, result.output
        report = json.loads(result.output)
        assert report["valid"] is True

    def test_default_produces_human_readable(self, runner, tmp_path):
        """Without --json, manifest validate produces human-readable text."""
        manifest = tmp_path / "harness_manifest.json"
        _write_valid_manifest(manifest)
        result = runner.invoke(manifest_cmd, ["validate", str(manifest)])
        assert result.exit_code == 0, result.output
        assert "valid" in result.output.lower()

    def test_json_invalid_manifest_exits_1(self, runner, tmp_path):
        manifest = tmp_path / "harness_manifest.json"
        m = {
            "schema_version": "1.0",
            "generated_at": "2026-01-01T00:00:00+00:00",
            "detected_stack": {"primary_language": "python"},
            "artifacts": [],
        }
        manifest.write_text(json.dumps(m), encoding="utf-8")
        result = runner.invoke(
            manifest_cmd, ["validate", str(manifest), "--json"]
        )
        assert result.exit_code == 1
        report = json.loads(result.output)
        assert report["valid"] is False
        assert report["error_count"] >= 1

    def test_json_missing_file_emits_structured_error(self, runner, tmp_path):
        missing = tmp_path / "nope.json"
        result = runner.invoke(
            manifest_cmd, ["validate", str(missing), "--json"]
        )
        assert result.exit_code == 2
        report = json.loads(result.output)
        assert report["valid"] is False

    def test_human_missing_file_exits_2(self, runner, tmp_path):
        missing = tmp_path / "nope.json"
        result = runner.invoke(
            manifest_cmd, ["validate", str(missing)]
        )
        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# harness create --format
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
                    "--format", "json",
                ],
            )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["status"] == "passed"
        assert "artifacts_generated" in data

    def test_text_produces_human_readable(self, runner, tmp_path):
        with _patch_generator():
            result = runner.invoke(
                cli,
                [
                    "create",
                    "--output", str(tmp_path / "harness.config.yaml"),
                    "--format", "text",
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

    def test_default_is_text(self, runner, tmp_path):
        """Default output format for create is text."""
        with _patch_generator():
            result = runner.invoke(
                cli,
                ["create", "--output", str(tmp_path / "harness.config.yaml")],
            )
        assert result.exit_code == 0, result.output
        # Default is text mode, should have human message
        assert any(
            word in result.output for word in ("Created", "Updated", "created", "updated")
        )

    def test_json_includes_detected_stack(self, runner, tmp_path):
        with _patch_generator():
            result = runner.invoke(
                cli,
                [
                    "create",
                    "--output", str(tmp_path / "harness.config.yaml"),
                    "--profile", "standard",
                    "--stack", "python",
                    "--format", "json",
                ],
            )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "detected_stack" in data

    def test_dry_run_always_emits_yaml_gates(self, runner, tmp_path):
        """--dry-run output is the YAML gates block regardless of --format."""
        with _patch_generator():
            result = runner.invoke(
                cli,
                [
                    "create",
                    "--dry-run",
                    "--format", "json",
                ],
            )
        assert result.exit_code == 0, result.output
        # Dry-run always prints a YAML gates comment header
        assert "dry-run" in result.output


# ---------------------------------------------------------------------------
# harness evaluate --format
# ---------------------------------------------------------------------------


class TestEvaluateOutputFormat:
    def test_json_flag_accepted(self, runner, tmp_path):
        result = runner.invoke(
            cli,
            [
                "evaluate",
                "--project-root", str(tmp_path),
                "--format", "json",
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
                "--format", "yaml",
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
                "--format", "table",
            ],
        )
        assert result.exit_code in (0, 1), result.output
        # Table output is not valid JSON
        with pytest.raises((json.JSONDecodeError, ValueError)):
            json.loads(result.output)

    def test_invalid_format_rejected(self, runner, tmp_path):
        result = runner.invoke(
            cli,
            [
                "evaluate",
                "--project-root", str(tmp_path),
                "--format", "xml",
            ],
        )
        assert result.exit_code != 0
        assert "xml" in result.output.lower() or "invalid" in result.output.lower()


# ---------------------------------------------------------------------------
# harness telemetry --format
# ---------------------------------------------------------------------------


class TestTelemetryOutputFormat:
    def _run(self, runner, tmp_path, fmt: Optional[str] = None) -> "Result":  # type: ignore[name-defined]
        args = ["telemetry", "--telemetry-file", str(tmp_path / "telemetry.json")]
        if fmt:
            args += ["--format", fmt]
        return runner.invoke(cli, args)

    def test_json_produces_parseable_output(self, runner, tmp_path):
        result = self._run(runner, tmp_path, fmt="json")
        assert result.exit_code in (0, 1), result.output
        data = json.loads(result.output)
        assert "artifacts" in data
        assert "commands" in data
        assert "gates" in data

    def test_table_produces_human_readable(self, runner, tmp_path):
        result = self._run(runner, tmp_path, fmt="table")
        assert result.exit_code in (0, 1), result.output
        assert "Harness Telemetry Report" in result.output

    def test_default_is_table(self, runner, tmp_path):
        """Default format for telemetry is table."""
        result = self._run(runner, tmp_path)
        assert result.exit_code in (0, 1), result.output
        # Default is table format
        assert "Harness Telemetry Report" in result.output


# ---------------------------------------------------------------------------
# harness status --format (smoke tests -- no live state service needed)
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
                "--format", "json",
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
                "--format", "yaml",
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
                "--format", "table",
            ],
        )
        assert result.exit_code == 0, result.output
        with pytest.raises((json.JSONDecodeError, ValueError)):
            json.loads(result.output)

    def test_default_is_table(self, runner, tmp_path):
        """Default format for status is table."""
        plan = self._plan_file(tmp_path)
        result = runner.invoke(
            cli,
            ["status", "--plan-file", str(plan), "--no-state-service"],
        )
        assert result.exit_code == 0, result.output
        # Default is table — not parseable as JSON
        with pytest.raises((json.JSONDecodeError, ValueError)):
            json.loads(result.output)
