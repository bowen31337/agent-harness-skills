"""Tests that all CLI commands are registered and accessible."""

from __future__ import annotations

from click.testing import CliRunner

from harness_skills.cli.main import cli


EXPECTED_COMMANDS = {
    "audit",
    "boot",
    "completion-report",
    "context",
    "coordinate",
    "create",
    "evaluate",
    "lint",
    "manifest",
    "observe",
    "plan",
    "resume",
    "screenshot",
    "search",
    "status",
    "telemetry",
    "update",
}


class TestCommandRegistration:
    """Verify all commands are wired into the CLI group."""

    def test_all_expected_commands_registered(self) -> None:
        registered = set(cli.commands.keys())
        missing = EXPECTED_COMMANDS - registered
        assert not missing, f"Commands not registered: {missing}"

    def test_no_unexpected_commands(self) -> None:
        registered = set(cli.commands.keys())
        extra = registered - EXPECTED_COMMANDS
        if extra:
            assert False, (
                f"New commands registered but not in EXPECTED_COMMANDS: {extra}. "
                "Update EXPECTED_COMMANDS if intentional."
            )

    def test_command_count_under_ceiling(self) -> None:
        """Spec ceiling is 20 commands (tool_inventory)."""
        assert len(cli.commands) <= 20


class TestCommandHelp:
    """Each registered command should respond to --help with exit 0."""

    runner = CliRunner()

    def test_audit_help(self) -> None:
        result = self.runner.invoke(cli, ["audit", "--help"])
        assert result.exit_code == 0

    def test_boot_help(self) -> None:
        result = self.runner.invoke(cli, ["boot", "--help"])
        assert result.exit_code == 0

    def test_completion_report_help(self) -> None:
        result = self.runner.invoke(cli, ["completion-report", "--help"])
        assert result.exit_code == 0

    def test_context_help(self) -> None:
        result = self.runner.invoke(cli, ["context", "--help"])
        assert result.exit_code == 0

    def test_coordinate_help(self) -> None:
        result = self.runner.invoke(cli, ["coordinate", "--help"])
        assert result.exit_code == 0

    def test_create_help(self) -> None:
        result = self.runner.invoke(cli, ["create", "--help"])
        assert result.exit_code == 0

    def test_evaluate_help(self) -> None:
        result = self.runner.invoke(cli, ["evaluate", "--help"])
        assert result.exit_code == 0

    def test_lint_help(self) -> None:
        result = self.runner.invoke(cli, ["lint", "--help"])
        assert result.exit_code == 0

    def test_manifest_help(self) -> None:
        result = self.runner.invoke(cli, ["manifest", "--help"])
        assert result.exit_code == 0

    def test_observe_help(self) -> None:
        result = self.runner.invoke(cli, ["observe", "--help"])
        assert result.exit_code == 0

    def test_plan_help(self) -> None:
        result = self.runner.invoke(cli, ["plan", "--help"])
        assert result.exit_code == 0

    def test_resume_help(self) -> None:
        result = self.runner.invoke(cli, ["resume", "--help"])
        assert result.exit_code == 0

    def test_screenshot_help(self) -> None:
        result = self.runner.invoke(cli, ["screenshot", "--help"])
        assert result.exit_code == 0

    def test_search_help(self) -> None:
        result = self.runner.invoke(cli, ["search", "--help"])
        assert result.exit_code == 0

    def test_status_help(self) -> None:
        result = self.runner.invoke(cli, ["status", "--help"])
        assert result.exit_code == 0

    def test_telemetry_help(self) -> None:
        result = self.runner.invoke(cli, ["telemetry", "--help"])
        assert result.exit_code == 0

    def test_update_help(self) -> None:
        result = self.runner.invoke(cli, ["update", "--help"])
        assert result.exit_code == 0
