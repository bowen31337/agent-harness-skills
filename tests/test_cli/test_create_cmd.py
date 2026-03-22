"""Tests for harness_skills.cli.create (``harness create``).

Uses Click's ``CliRunner`` for isolated, subprocess-free invocations.

Coverage goals:
    - --dry-run prints YAML gates block and does NOT write a file
    - --dry-run with --stack adds stack hint to header comment
    - Default invocation creates harness.config.yaml in cwd
    - --profile standard / advanced wires through to the generator
    - --no-merge overwrites an existing file
    - Merge mode (default) patches gates into an existing file
    - --output PATH writes to the specified destination
    - --output-format json emits a valid CreateConfigResponse JSON blob
    - --output-format yaml emits YAML-serialised CreateConfigResponse
    - Unknown --profile exits with a non-zero code
    - action field is "created" for new files and "updated" for merges
    - Generator import failure triggers exit code 1
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from harness_skills.cli.create import create_cmd


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


# ===========================================================================
# --dry-run
# ===========================================================================


class TestCreateCmdDryRun:
    def test_dry_run_exits_zero(self, runner: CliRunner):
        result = runner.invoke(create_cmd, ["--dry-run"])
        assert result.exit_code == 0, result.output

    def test_dry_run_prints_gates_yaml(self, runner: CliRunner):
        result = runner.invoke(create_cmd, ["--dry-run"])
        assert "gates:" in result.output

    def test_dry_run_does_not_create_file(self, runner: CliRunner, tmp_path: Path):
        dest = tmp_path / "harness.config.yaml"
        result = runner.invoke(create_cmd, ["--dry-run", "--output", str(dest)])
        assert result.exit_code == 0, result.output
        assert not dest.exists()

    def test_dry_run_header_mentions_profile(self, runner: CliRunner):
        result = runner.invoke(create_cmd, ["--dry-run", "--profile", "standard"])
        assert "standard" in result.output

    def test_dry_run_with_stack_mentions_stack(self, runner: CliRunner):
        result = runner.invoke(create_cmd, ["--dry-run", "--stack", "python"])
        assert "python" in result.output

    def test_dry_run_dry_run_label_in_output(self, runner: CliRunner):
        result = runner.invoke(create_cmd, ["--dry-run"])
        assert "dry-run" in result.output.lower()

    def test_dry_run_advanced_profile(self, runner: CliRunner):
        result = runner.invoke(create_cmd, ["--dry-run", "--profile", "advanced"])
        assert result.exit_code == 0
        assert "performance:" in result.output


# ===========================================================================
# Create from scratch (merge=False implied when no file exists)
# ===========================================================================


class TestCreateCmdNewFile:
    def test_creates_file(self, runner: CliRunner, tmp_path: Path):
        dest = tmp_path / "harness.config.yaml"
        result = runner.invoke(create_cmd, ["--output", str(dest)])
        assert result.exit_code == 0, result.output
        assert dest.exists()

    def test_created_file_is_valid_yaml(self, runner: CliRunner, tmp_path: Path):
        dest = tmp_path / "harness.config.yaml"
        runner.invoke(create_cmd, ["--output", str(dest)])
        content = yaml.safe_load(dest.read_text())
        assert content is not None

    def test_created_file_contains_gates(self, runner: CliRunner, tmp_path: Path):
        dest = tmp_path / "harness.config.yaml"
        runner.invoke(create_cmd, ["--output", str(dest)])
        content = yaml.safe_load(dest.read_text())
        assert "gates" in content["profiles"]["starter"]

    def test_standard_profile_written(self, runner: CliRunner, tmp_path: Path):
        dest = tmp_path / "harness.config.yaml"
        runner.invoke(create_cmd, ["--output", str(dest), "--profile", "standard"])
        content = yaml.safe_load(dest.read_text())
        assert "standard" in content["profiles"]

    def test_advanced_profile_written(self, runner: CliRunner, tmp_path: Path):
        dest = tmp_path / "harness.config.yaml"
        runner.invoke(create_cmd, ["--output", str(dest), "--profile", "advanced"])
        content = yaml.safe_load(dest.read_text())
        assert "advanced" in content["profiles"]

    def test_success_message_in_output(self, runner: CliRunner, tmp_path: Path):
        dest = tmp_path / "harness.config.yaml"
        result = runner.invoke(create_cmd, ["--output", str(dest)])
        assert result.exit_code == 0
        # Either "Created" or "created" in human-readable output
        assert "created" in result.output.lower() or str(dest) in result.output


# ===========================================================================
# --no-merge
# ===========================================================================


class TestCreateCmdNoMerge:
    def test_no_merge_overwrites_existing_file(self, runner: CliRunner, tmp_path: Path):
        dest = tmp_path / "harness.config.yaml"
        dest.write_text("# old sentinel\ncustom_orphan_key: yes\n")
        result = runner.invoke(
            create_cmd, ["--output", str(dest), "--no-merge", "--profile", "starter"]
        )
        assert result.exit_code == 0, result.output
        raw = dest.read_text()
        # The old sentinel comment should not survive a --no-merge
        assert "old sentinel" not in raw

    def test_no_merge_file_is_valid_yaml(self, runner: CliRunner, tmp_path: Path):
        dest = tmp_path / "harness.config.yaml"
        dest.write_text("# old file\n")
        runner.invoke(create_cmd, ["--output", str(dest), "--no-merge"])
        content = yaml.safe_load(dest.read_text())
        assert content is not None


# ===========================================================================
# Merge mode (default when file already exists)
# ===========================================================================


class TestCreateCmdMerge:
    def _make_existing(self, tmp_path: Path) -> Path:
        dest = tmp_path / "harness.config.yaml"
        dest.write_text(
            "active_profile: starter\n"
            "custom_key: stay\n"
            "profiles:\n"
            "  starter:\n"
            "    gates:\n"
            "      regression:\n"
            "        enabled: true\n"
            "        timeout_seconds: 9\n"
        )
        return dest

    def test_merge_preserves_custom_key(self, runner: CliRunner, tmp_path: Path):
        dest = self._make_existing(tmp_path)
        runner.invoke(create_cmd, ["--output", str(dest)])
        content = yaml.safe_load(dest.read_text())
        assert content.get("custom_key") == "stay"

    def test_merge_updates_gates(self, runner: CliRunner, tmp_path: Path):
        dest = self._make_existing(tmp_path)
        runner.invoke(create_cmd, ["--output", str(dest)])
        content = yaml.safe_load(dest.read_text())
        gates = content["profiles"]["starter"]["gates"]
        assert "coverage" in gates

    def test_merge_result_is_valid_yaml(self, runner: CliRunner, tmp_path: Path):
        dest = self._make_existing(tmp_path)
        runner.invoke(create_cmd, ["--output", str(dest)])
        content = yaml.safe_load(dest.read_text())
        assert content is not None

    def test_merge_exits_zero(self, runner: CliRunner, tmp_path: Path):
        dest = self._make_existing(tmp_path)
        result = runner.invoke(create_cmd, ["--output", str(dest)])
        assert result.exit_code == 0, result.output


# ===========================================================================
# --output-format json
# ===========================================================================


class TestCreateCmdJsonOutput:
    def test_json_output_is_valid_json(self, runner: CliRunner, tmp_path: Path):
        dest = tmp_path / "harness.config.yaml"
        result = runner.invoke(
            create_cmd, ["--output", str(dest), "--output-format", "json"]
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert isinstance(data, dict)

    def test_json_output_has_status(self, runner: CliRunner, tmp_path: Path):
        dest = tmp_path / "harness.config.yaml"
        result = runner.invoke(
            create_cmd, ["--output", str(dest), "--output-format", "json"]
        )
        data = json.loads(result.output)
        assert "status" in data

    def test_json_output_status_is_passed(self, runner: CliRunner, tmp_path: Path):
        dest = tmp_path / "harness.config.yaml"
        result = runner.invoke(
            create_cmd, ["--output", str(dest), "--output-format", "json"]
        )
        data = json.loads(result.output)
        assert data["status"] == "passed"

    def test_json_output_has_action(self, runner: CliRunner, tmp_path: Path):
        dest = tmp_path / "harness.config.yaml"
        result = runner.invoke(
            create_cmd, ["--output", str(dest), "--output-format", "json"]
        )
        data = json.loads(result.output)
        assert "action" in data

    def test_json_action_is_created_for_new_file(self, runner: CliRunner, tmp_path: Path):
        dest = tmp_path / "harness.config.yaml"
        result = runner.invoke(
            create_cmd, ["--output", str(dest), "--output-format", "json"]
        )
        data = json.loads(result.output)
        assert data["action"] == "created"

    def test_json_action_is_updated_for_existing_file(
        self, runner: CliRunner, tmp_path: Path
    ):
        dest = tmp_path / "harness.config.yaml"
        dest.write_text(
            "active_profile: starter\nprofiles:\n  starter:\n    gates: {}\n"
        )
        result = runner.invoke(
            create_cmd, ["--output", str(dest), "--output-format", "json"]
        )
        data = json.loads(result.output)
        assert data["action"] == "updated"

    def test_json_output_has_profile(self, runner: CliRunner, tmp_path: Path):
        dest = tmp_path / "harness.config.yaml"
        result = runner.invoke(
            create_cmd,
            ["--output", str(dest), "--output-format", "json", "--profile", "standard"],
        )
        data = json.loads(result.output)
        assert data["profile"] == "standard"

    def test_json_output_stack_null_when_not_provided(
        self, runner: CliRunner, tmp_path: Path
    ):
        dest = tmp_path / "harness.config.yaml"
        result = runner.invoke(
            create_cmd, ["--output", str(dest), "--output-format", "json"]
        )
        data = json.loads(result.output)
        assert data["stack"] is None

    def test_json_output_stack_set_when_provided(
        self, runner: CliRunner, tmp_path: Path
    ):
        dest = tmp_path / "harness.config.yaml"
        result = runner.invoke(
            create_cmd,
            ["--output", str(dest), "--output-format", "json", "--stack", "python"],
        )
        data = json.loads(result.output)
        assert data["stack"] == "python"

    def test_json_output_path_matches_output_flag(
        self, runner: CliRunner, tmp_path: Path
    ):
        dest = tmp_path / "harness.config.yaml"
        result = runner.invoke(
            create_cmd, ["--output", str(dest), "--output-format", "json"]
        )
        data = json.loads(result.output)
        assert data["path"] == str(dest)


# ===========================================================================
# --output-format yaml
# ===========================================================================


class TestCreateCmdYamlOutput:
    def test_yaml_output_is_parseable(self, runner: CliRunner, tmp_path: Path):
        dest = tmp_path / "harness.config.yaml"
        result = runner.invoke(
            create_cmd, ["--output", str(dest), "--output-format", "yaml"]
        )
        assert result.exit_code == 0, result.output
        data = yaml.safe_load(result.output)
        assert isinstance(data, dict)

    def test_yaml_output_has_status(self, runner: CliRunner, tmp_path: Path):
        dest = tmp_path / "harness.config.yaml"
        result = runner.invoke(
            create_cmd, ["--output", str(dest), "--output-format", "yaml"]
        )
        data = yaml.safe_load(result.output)
        assert "status" in data


# ===========================================================================
# Invalid profile / argument errors
# ===========================================================================


class TestCreateCmdErrors:
    def test_invalid_profile_exits_nonzero(self, runner: CliRunner, tmp_path: Path):
        dest = tmp_path / "harness.config.yaml"
        result = runner.invoke(
            create_cmd, ["--output", str(dest), "--profile", "enterprise"]
        )
        assert result.exit_code != 0

    def test_invalid_stack_exits_nonzero(self, runner: CliRunner, tmp_path: Path):
        dest = tmp_path / "harness.config.yaml"
        result = runner.invoke(
            create_cmd, ["--output", str(dest), "--stack", "cobol"]
        )
        assert result.exit_code != 0
