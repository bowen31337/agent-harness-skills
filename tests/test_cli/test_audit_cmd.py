"""Tests for harness audit command."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from click.testing import CliRunner

from harness_skills.cli.main import cli


class TestAuditCmd:
    runner = CliRunner()

    def test_help(self) -> None:
        result = self.runner.invoke(cli, ["audit", "--help"])
        assert result.exit_code == 0

    def test_empty_dir_exits_0(self, tmp_path) -> None:
        result = self.runner.invoke(
            cli,
            ["audit", "--project-root", str(tmp_path), "--output-format", "json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total_artifacts"] == 0

    def test_fresh_artifact(self, tmp_path) -> None:
        now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text(f"<!-- harness:auto-generated -->\nlast_updated: {now}\n# AGENTS\n")
        result = self.runner.invoke(
            cli,
            ["audit", "--project-root", str(tmp_path), "--output-format", "json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total_artifacts"] == 1
        assert data["current_count"] == 1

    def test_stale_artifact(self, tmp_path) -> None:
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("<!-- harness:auto-generated -->\nlast_updated: 2020-01-01\n# AGENTS\n")
        result = self.runner.invoke(
            cli,
            [
                "audit",
                "--project-root", str(tmp_path),
                "--stale-days", "1",
                "--outdated-days", "2",
                "--obsolete-days", "3",
                "--output-format", "json",
            ],
        )
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["obsolete_count"] == 1

    def test_no_fail_on_outdated(self, tmp_path) -> None:
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("<!-- harness:auto-generated -->\nlast_updated: 2020-01-01\n# AGENTS\n")
        result = self.runner.invoke(
            cli,
            [
                "audit",
                "--project-root", str(tmp_path),
                "--no-fail-on-outdated",
                "--output-format", "json",
            ],
        )
        assert result.exit_code == 0

    def test_table_output(self, tmp_path) -> None:
        result = self.runner.invoke(
            cli,
            ["audit", "--project-root", str(tmp_path), "--output-format", "table"],
        )
        assert result.exit_code == 0
        assert "Audited" in result.output
