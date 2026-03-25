"""Tests for harness plan command."""

from __future__ import annotations

import json

from click.testing import CliRunner

from harness_skills.cli.main import cli


class TestPlanCmd:
    runner = CliRunner()

    def test_help(self) -> None:
        result = self.runner.invoke(cli, ["plan", "--help"])
        assert result.exit_code == 0

    def test_create_plan(self, tmp_path) -> None:
        out = str(tmp_path / "plans")
        result = self.runner.invoke(
            cli,
            ["plan", "Implement user auth", "--output-dir", out, "--plan-id", "PLAN-test1"],
        )
        assert result.exit_code == 0
        plan_file = tmp_path / "plans" / "PLAN-test1.yaml"
        assert plan_file.exists()
        content = plan_file.read_text()
        assert "Implement user auth" in content
        assert "PLAN-test1" in content

    def test_create_plan_auto_id(self, tmp_path) -> None:
        out = str(tmp_path / "plans")
        result = self.runner.invoke(
            cli, ["plan", "Add billing module", "--output-dir", out]
        )
        assert result.exit_code == 0
        files = list((tmp_path / "plans").glob("PLAN-*.yaml"))
        assert len(files) == 1

    def test_duplicate_plan_exits_1(self, tmp_path) -> None:
        out = str(tmp_path / "plans")
        self.runner.invoke(
            cli,
            ["plan", "First plan", "--output-dir", out, "--plan-id", "PLAN-dup"],
        )
        result = self.runner.invoke(
            cli,
            ["plan", "Second plan", "--output-dir", out, "--plan-id", "PLAN-dup"],
        )
        assert result.exit_code == 1

    def test_json_output(self, tmp_path) -> None:
        out = str(tmp_path / "plans")
        result = self.runner.invoke(
            cli,
            [
                "plan", "JSON test",
                "--output-dir", out,
                "--plan-id", "PLAN-json",
                "--output-format", "json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["command"] == "harness plan"
        assert data["status"] == "passed"
        assert data["plan_id"] == "PLAN-json"

    def test_custom_title(self, tmp_path) -> None:
        out = str(tmp_path / "plans")
        result = self.runner.invoke(
            cli,
            [
                "plan", "A very long description that should be truncated",
                "--output-dir", out,
                "--title", "Short Title",
                "--plan-id", "PLAN-title",
                "--output-format", "json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["title"] == "Short Title"
