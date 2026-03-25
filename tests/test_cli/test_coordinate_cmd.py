"""Tests for harness coordinate command."""

from __future__ import annotations

import json

from click.testing import CliRunner

from harness_skills.cli.main import cli


class TestCoordinateCmd:
    runner = CliRunner()

    def test_help(self) -> None:
        result = self.runner.invoke(cli, ["coordinate", "--help"])
        assert result.exit_code == 0

    def test_demo_mode(self) -> None:
        result = self.runner.invoke(cli, ["coordinate", "--demo", "--output-format", "table"])
        assert result.exit_code == 0
        assert "Agents:" in result.output
        assert "CONFLICT" in result.output

    def test_demo_json(self) -> None:
        result = self.runner.invoke(
            cli, ["coordinate", "--demo", "--output-format", "json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["command"] == "harness coordinate"
        assert data["status"] == "passed"
        assert len(data["agents"]) == 3
        assert len(data["conflicts"]) > 0
        assert len(data["suggested_order"]) == 3

    def test_demo_no_locks(self) -> None:
        result = self.runner.invoke(
            cli, ["coordinate", "--demo", "--no-locks"]
        )
        assert result.exit_code == 0

    def test_without_state_service_exits_1(self) -> None:
        result = self.runner.invoke(
            cli,
            ["coordinate", "--state-url", "http://localhost:99999"],
        )
        assert result.exit_code == 1
