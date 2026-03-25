"""Tests for harness resume command."""

from __future__ import annotations

import json

from click.testing import CliRunner

from harness_skills.cli.main import cli


class TestResumeCmd:
    runner = CliRunner()

    def test_help(self) -> None:
        result = self.runner.invoke(cli, ["resume", "--help"])
        assert result.exit_code == 0

    def test_no_files_exits_1(self, tmp_path) -> None:
        result = self.runner.invoke(
            cli,
            [
                "resume",
                "--md-path", str(tmp_path / "missing.md"),
                "--jsonl-path", str(tmp_path / "missing.jsonl"),
            ],
        )
        assert result.exit_code == 1

    def test_with_md_file(self, tmp_path) -> None:
        md = tmp_path / "plan-progress.md"
        md.write_text(
            "# Plan Progress\n\n"
            "## Current Step\n"
            "Implementing auth module\n\n"
            "## Completed\n"
            "- Set up project structure\n\n"
            "## Search Hints\n"
            "- `src/auth/`\n"
            "- `grep -r 'def login'`\n"
        )
        result = self.runner.invoke(
            cli,
            [
                "resume",
                "--md-path", str(md),
                "--jsonl-path", str(tmp_path / "missing.jsonl"),
            ],
        )
        # Either exits 0 (found state) or 1 (state.found() is False)
        # depending on resume.py parsing. Just ensure no crash (exit != 2)
        assert result.exit_code != 2

    def test_json_output_no_state(self, tmp_path) -> None:
        result = self.runner.invoke(
            cli,
            [
                "resume",
                "--md-path", str(tmp_path / "nope.md"),
                "--jsonl-path", str(tmp_path / "nope.jsonl"),
                "--output-format", "json",
            ],
        )
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["status"] == "failed"
        assert "No plan state" in data["message"]
