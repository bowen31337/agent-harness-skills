"""Tests for harness update command."""

from __future__ import annotations

import json

from click.testing import CliRunner

from harness_skills.cli.main import cli


class TestUpdateCmd:
    runner = CliRunner()

    def test_help(self) -> None:
        result = self.runner.invoke(cli, ["update", "--help"])
        assert result.exit_code == 0

    def test_update_json_with_mock(self, tmp_path, monkeypatch) -> None:
        """Mock regenerate_all to return a known diff."""
        fake_results = [
            {
                "path": "AGENTS.md",
                "change_type": "updated",
                "sections_changed": ["Quick Reference"],
                "manual_edits_preserved": True,
            },
        ]
        monkeypatch.setattr(
            "harness_skills.cli.update._lazy_regenerate",
            lambda: lambda root, force=False: fake_results,
        )
        monkeypatch.setattr(
            "harness_skills.cli.update._lazy_detect_stack",
            lambda: lambda root: None,
        )
        (tmp_path / "docs").mkdir()
        result = self.runner.invoke(
            cli,
            [
                "update",
                "--project-root", str(tmp_path),
                "--output-format", "json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "passed"
        assert len(data["artifacts_diff"]) == 1
        assert data["artifacts_diff"][0]["change_type"] == "updated"

    def test_no_changes_exits_1(self, tmp_path, monkeypatch) -> None:
        fake_results = [
            {"path": "AGENTS.md", "change_type": "unchanged"},
        ]
        monkeypatch.setattr(
            "harness_skills.cli.update._lazy_regenerate",
            lambda: lambda root, force=False: fake_results,
        )
        monkeypatch.setattr(
            "harness_skills.cli.update._lazy_detect_stack",
            lambda: lambda root: None,
        )
        result = self.runner.invoke(
            cli,
            ["update", "--project-root", str(tmp_path)],
        )
        assert result.exit_code == 1

    def test_no_changelog_flag(self, tmp_path, monkeypatch) -> None:
        fake_results = [
            {"path": "AGENTS.md", "change_type": "updated", "sections_changed": ["build"]},
        ]
        monkeypatch.setattr(
            "harness_skills.cli.update._lazy_regenerate",
            lambda: lambda root, force=False: fake_results,
        )
        monkeypatch.setattr(
            "harness_skills.cli.update._lazy_detect_stack",
            lambda: lambda root: None,
        )
        result = self.runner.invoke(
            cli,
            [
                "update",
                "--project-root", str(tmp_path),
                "--no-changelog",
                "--output-format", "json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["changelog_path"] is None
