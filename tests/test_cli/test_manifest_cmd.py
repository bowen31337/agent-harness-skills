"""Tests for harness_skills.cli.manifest (``harness manifest validate``).

Uses Click's ``CliRunner`` for isolated, filesystem-independent invocations.

Covers:
    - exit code 0 on valid manifest
    - exit code 1 on schema violations, with JSONPath error locations on stderr
    - exit code 2 on missing file or invalid JSON
    - ``--json`` flag: machine-readable output to stdout
    - default path (``harness_manifest.json`` in CWD)
    - explicit path argument
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from harness_skills.cli.manifest import manifest_cmd
from harness_skills.generators.manifest_generator import generate_manifest
from harness_skills.models.create import DetectedStack, GeneratedArtifact

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_STACK = DetectedStack(
    primary_language="python",
    project_structure="single-app",
)

VALID_ARTIFACT = GeneratedArtifact(
    artifact_path="harness.config.yaml",
    artifact_type="harness.config.yaml",
)


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _write_valid(path: Path) -> None:
    """Write a minimal valid ``harness_manifest.json`` to *path*."""
    path.write_text(
        json.dumps(generate_manifest(VALID_STACK), indent=2),
        encoding="utf-8",
    )


def _write_invalid_stack(path: Path) -> None:
    """Write a manifest with a missing required field to *path*."""
    m = generate_manifest(VALID_STACK)
    del m["detected_stack"]["project_structure"]
    path.write_text(json.dumps(m, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# ``harness manifest validate`` — human-readable output
# ---------------------------------------------------------------------------


class TestValidateCmdHumanReadable:
    def test_exit_0_on_valid_manifest(self, runner, tmp_path):
        manifest = tmp_path / "harness_manifest.json"
        _write_valid(manifest)
        result = runner.invoke(manifest_cmd, ["validate", str(manifest)])
        assert result.exit_code == 0, result.output

    def test_success_message_on_valid(self, runner, tmp_path):
        manifest = tmp_path / "harness_manifest.json"
        _write_valid(manifest)
        result = runner.invoke(manifest_cmd, ["validate", str(manifest)])
        assert "valid" in result.output.lower()

    def test_exit_1_on_schema_violation(self, runner, tmp_path):
        manifest = tmp_path / "harness_manifest.json"
        _write_invalid_stack(manifest)
        result = runner.invoke(manifest_cmd, ["validate", str(manifest)])
        assert result.exit_code == 1

    def test_jsonpath_location_in_stderr_on_violation(self, runner, tmp_path):
        manifest = tmp_path / "harness_manifest.json"
        _write_invalid_stack(manifest)
        result = runner.invoke(manifest_cmd, ["validate", str(manifest)], catch_exceptions=False)
        # errors go to stderr (mix_stderr=True by default in CliRunner)
        combined = result.output
        assert "$" in combined, "Expected a '$'-rooted JSONPath in output"

    def test_detected_stack_in_error_output(self, runner, tmp_path):
        manifest = tmp_path / "harness_manifest.json"
        _write_invalid_stack(manifest)
        result = runner.invoke(manifest_cmd, ["validate", str(manifest)])
        assert "detected_stack" in result.output or "project_structure" in result.output

    def test_exit_2_on_missing_file(self, runner, tmp_path):
        missing = tmp_path / "does_not_exist.json"
        result = runner.invoke(manifest_cmd, ["validate", str(missing)])
        assert result.exit_code == 2

    def test_exit_2_on_invalid_json(self, runner, tmp_path):
        bad = tmp_path / "harness_manifest.json"
        bad.write_text("{ this is not JSON }", encoding="utf-8")
        result = runner.invoke(manifest_cmd, ["validate", str(bad)])
        assert result.exit_code == 2

    def test_wrong_schema_version_produces_error(self, runner, tmp_path):
        manifest = tmp_path / "harness_manifest.json"
        m = generate_manifest(VALID_STACK)
        m["schema_version"] = "99.0"
        manifest.write_text(json.dumps(m), encoding="utf-8")
        result = runner.invoke(manifest_cmd, ["validate", str(manifest)])
        assert result.exit_code == 1

    def test_invalid_artifact_type_reports_array_index(self, runner, tmp_path):
        manifest = tmp_path / "harness_manifest.json"
        m = generate_manifest(
            VALID_STACK,
            artifacts=[
                VALID_ARTIFACT.model_dump(),
                {"artifact_path": "foo.md", "artifact_type": "NOT_VALID"},
            ],
        )
        manifest.write_text(json.dumps(m), encoding="utf-8")
        result = runner.invoke(manifest_cmd, ["validate", str(manifest)])
        assert result.exit_code == 1
        # second artifact → index 1
        assert "[1]" in result.output

    def test_multiple_violations_all_reported(self, runner, tmp_path):
        """More than one JSONPath error should all appear in the output."""
        manifest = tmp_path / "harness_manifest.json"
        m = generate_manifest(VALID_STACK)
        # Two violations: wrong schema_version AND bad project_structure
        m["schema_version"] = "9.9"
        m["detected_stack"]["project_structure"] = "flatland"
        manifest.write_text(json.dumps(m), encoding="utf-8")
        result = runner.invoke(manifest_cmd, ["validate", str(manifest)])
        assert result.exit_code == 1
        # Both fields should appear in output
        assert "schema_version" in result.output or "9.9" in result.output
        assert "project_structure" in result.output or "flatland" in result.output


# ---------------------------------------------------------------------------
# ``harness manifest validate --json``
# ---------------------------------------------------------------------------


class TestValidateCmdJsonOutput:
    def test_valid_manifest_json_flag(self, runner, tmp_path):
        manifest = tmp_path / "harness_manifest.json"
        _write_valid(manifest)
        result = runner.invoke(manifest_cmd, ["validate", str(manifest), "--json"])
        assert result.exit_code == 0
        report = json.loads(result.output)
        assert report["valid"] is True
        assert report["error_count"] == 0
        assert report["errors"] == []

    def test_invalid_manifest_json_flag_exit_1(self, runner, tmp_path):
        manifest = tmp_path / "harness_manifest.json"
        _write_invalid_stack(manifest)
        result = runner.invoke(manifest_cmd, ["validate", str(manifest), "--json"])
        assert result.exit_code == 1

    def test_invalid_manifest_json_report_structure(self, runner, tmp_path):
        manifest = tmp_path / "harness_manifest.json"
        _write_invalid_stack(manifest)
        result = runner.invoke(manifest_cmd, ["validate", str(manifest), "--json"])
        report = json.loads(result.output)
        assert report["valid"] is False
        assert report["error_count"] >= 1
        assert len(report["errors"]) == report["error_count"]

    def test_json_errors_have_jsonpath_field(self, runner, tmp_path):
        manifest = tmp_path / "harness_manifest.json"
        _write_invalid_stack(manifest)
        result = runner.invoke(manifest_cmd, ["validate", str(manifest), "--json"])
        report = json.loads(result.output)
        for entry in report["errors"]:
            assert "jsonpath" in entry
            assert entry["jsonpath"].startswith("$")

    def test_json_errors_have_message_field(self, runner, tmp_path):
        manifest = tmp_path / "harness_manifest.json"
        _write_invalid_stack(manifest)
        result = runner.invoke(manifest_cmd, ["validate", str(manifest), "--json"])
        report = json.loads(result.output)
        for entry in report["errors"]:
            assert "message" in entry
            assert isinstance(entry["message"], str)
            assert entry["message"]  # non-empty

    def test_missing_file_json_flag_exit_2(self, runner, tmp_path):
        missing = tmp_path / "nope.json"
        result = runner.invoke(manifest_cmd, ["validate", str(missing), "--json"])
        assert result.exit_code == 2
        report = json.loads(result.output)
        assert report["valid"] is False

    def test_invalid_json_file_json_flag_exit_2(self, runner, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{broken", encoding="utf-8")
        result = runner.invoke(manifest_cmd, ["validate", str(bad), "--json"])
        assert result.exit_code == 2
        report = json.loads(result.output)
        assert report["valid"] is False

    def test_json_output_includes_path(self, runner, tmp_path):
        manifest = tmp_path / "harness_manifest.json"
        _write_valid(manifest)
        result = runner.invoke(manifest_cmd, ["validate", str(manifest), "--json"])
        report = json.loads(result.output)
        assert "path" in report

    def test_valid_manifest_json_output_is_parseable(self, runner, tmp_path):
        manifest = tmp_path / "harness_manifest.json"
        _write_valid(manifest)
        result = runner.invoke(manifest_cmd, ["validate", str(manifest), "--json"])
        # Must not raise
        parsed = json.loads(result.output)
        assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# Default path behaviour (``harness_manifest.json`` in CWD)
# ---------------------------------------------------------------------------


class TestValidateCmdDefaultPath:
    def test_uses_default_path_when_no_argument(self, runner, tmp_path):
        manifest = tmp_path / "harness_manifest.json"
        _write_valid(manifest)
        # Run inside tmp_path so the default "harness_manifest.json" resolves
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            _write_valid(Path(td) / "harness_manifest.json")
            result = runner.invoke(manifest_cmd, ["validate"])
        assert result.exit_code == 0

    def test_missing_default_path_exits_2(self, runner, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # No harness_manifest.json present
            result = runner.invoke(manifest_cmd, ["validate"])
        assert result.exit_code == 2
