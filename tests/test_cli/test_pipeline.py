"""Tests for harness CLI ``--then`` pipeline composition.

Covers:
    - _split_on_then: correct segmentation at ``--then`` boundaries
    - PipelineGroup: single-command (no chaining) passes through to Click normally
    - PipelineGroup: two-stage pipeline where both stages succeed
    - PipelineGroup: three-stage pipeline where an early stage fails and aborts the remainder
    - PipelineGroup: trailing ``--then`` is silently ignored
    - PipelineGroup: empty segments between consecutive ``--then`` tokens are dropped
"""

from __future__ import annotations

import click
from click.testing import CliRunner

from harness_skills.cli.main import PipelineGroup, _split_on_then

# ---------------------------------------------------------------------------
# Unit tests for _split_on_then
# ---------------------------------------------------------------------------


class TestSplitOnThen:
    def test_no_then_returns_single_segment(self):
        assert _split_on_then(["create", "--profile", "standard"]) == [
            ["create", "--profile", "standard"]
        ]

    def test_single_then_produces_two_segments(self):
        assert _split_on_then(["create", "--then", "lint"]) == [
            ["create"],
            ["lint"],
        ]

    def test_two_thens_produce_three_segments(self):
        assert _split_on_then(["create", "--then", "lint", "--then", "evaluate"]) == [
            ["create"],
            ["lint"],
            ["evaluate"],
        ]

    def test_flags_stay_with_their_segment(self):
        result = _split_on_then(
            ["create", "--profile", "standard", "--then", "lint", "--gate", "architecture"]
        )
        assert result == [
            ["create", "--profile", "standard"],
            ["lint", "--gate", "architecture"],
        ]

    def test_trailing_then_is_dropped(self):
        assert _split_on_then(["create", "--then"]) == [["create"]]

    def test_empty_segment_between_consecutive_thens_is_dropped(self):
        # "--then --then" produces an empty segment that should be filtered out
        result = _split_on_then(["create", "--then", "--then", "evaluate"])
        assert result == [["create"], ["evaluate"]]

    def test_empty_input_returns_empty_list(self):
        assert _split_on_then([]) == []

    def test_only_then_returns_empty_list(self):
        assert _split_on_then(["--then"]) == []

    def test_multiple_flags_across_all_segments(self):
        result = _split_on_then(
            ["create", "--profile", "advanced", "--stack", "python",
             "--then", "lint", "--no-principles",
             "--then", "evaluate", "--format", "json"]
        )
        assert result == [
            ["create", "--profile", "advanced", "--stack", "python"],
            ["lint", "--no-principles"],
            ["evaluate", "--format", "json"],
        ]


# ---------------------------------------------------------------------------
# Helpers: tiny Click commands for pipeline integration tests
# ---------------------------------------------------------------------------


def _make_pipeline_cli(*commands: tuple[str, int]) -> click.Group:
    """Build a PipelineGroup CLI with minimal stub commands.

    Each element of *commands* is ``(name, exit_code)`` — the command simply
    exits with the given code (0 = success, non-zero = failure).
    """

    @click.group(cls=PipelineGroup)
    def cli() -> None:
        """Test harness pipeline CLI."""

    for name, code in commands:
        # We need a fresh function per iteration to avoid closure capture issues.
        def _make_cmd(cmd_name: str, cmd_code: int) -> click.BaseCommand:
            @click.command(cmd_name)
            def _cmd() -> int | None:
                # Return the exit code so PipelineGroup.main() receives it as
                # an int via standalone_mode=False.  Raising SystemExit would
                # bypass the isinstance(result, int) check before the abort
                # message is written.
                return cmd_code if cmd_code != 0 else None

            return _cmd

        cli.add_command(_make_cmd(name, code))

    return cli


# ---------------------------------------------------------------------------
# Integration tests for PipelineGroup
# ---------------------------------------------------------------------------


class TestPipelineGroupSingleCommand:
    def test_single_command_no_then_exits_0(self):
        cli = _make_pipeline_cli(("alpha", 0))
        runner = CliRunner()
        result = runner.invoke(cli, ["alpha"])
        assert result.exit_code == 0

    def test_single_failing_command_exits_nonzero(self):
        """Standalone mode: a command that calls sys.exit(1) must exit non-zero.

        Note: ``_make_pipeline_cli`` stubs *return* the exit code (for pipeline
        mode with standalone_mode=False).  In standalone mode Click ignores a
        returned int and always exits 0.  This test therefore uses an inline
        command that raises ``SystemExit`` directly — the Click-idiomatic way to
        signal failure in standalone mode.
        """

        @click.group(cls=PipelineGroup)
        def cli() -> None:
            pass

        @cli.command("fail")
        def _fail() -> None:
            raise SystemExit(1)

        runner = CliRunner()
        result = runner.invoke(cli, ["fail"])
        assert result.exit_code != 0

    def test_single_command_passes_flags_correctly(self):
        """Flags must still reach the sub-command when there is no --then."""

        @click.group(cls=PipelineGroup)
        def cli() -> None:
            pass

        @cli.command("greet")
        @click.option("--name", default="world")
        def _greet(name: str) -> None:
            click.echo(f"Hello, {name}!")

        runner = CliRunner()
        result = runner.invoke(cli, ["greet", "--name", "harness"])
        assert result.exit_code == 0
        assert "Hello, harness!" in result.output


class TestPipelineGroupTwoStages:
    def test_both_stages_succeed_exits_0(self):
        cli = _make_pipeline_cli(("alpha", 0), ("beta", 0))
        runner = CliRunner()
        result = runner.invoke(cli, ["alpha", "--then", "beta"])
        assert result.exit_code == 0

    def test_first_stage_fails_aborts_pipeline(self):
        cli = _make_pipeline_cli(("alpha", 1), ("beta", 0))
        runner = CliRunner()
        result = runner.invoke(cli, ["alpha", "--then", "beta"])
        assert result.exit_code != 0

    def test_second_stage_fails_exits_nonzero(self):
        cli = _make_pipeline_cli(("alpha", 0), ("beta", 2))
        runner = CliRunner()
        result = runner.invoke(cli, ["alpha", "--then", "beta"])
        assert result.exit_code != 0

    def test_failure_message_mentions_failing_stage(self):
        """The abort message must reference the failing sub-command name."""
        cli = _make_pipeline_cli(("alpha", 1), ("beta", 0))
        runner = CliRunner()
        result = runner.invoke(cli, ["alpha", "--then", "beta"])
        assert result.exit_code != 0
        # PipelineGroup writes "Stage N ('alpha') failed …" to stderr (captured
        # in result.output when mix_stderr is the default True).
        assert "alpha" in result.output

    def test_stages_with_per_command_flags(self):
        @click.group(cls=PipelineGroup)
        def cli() -> None:
            pass

        @cli.command("build")
        @click.option("--profile", default="starter")
        def _build(profile: str) -> None:
            click.echo(f"built:{profile}")

        @cli.command("check")
        @click.option("--strict", is_flag=True, default=False)
        def _check(strict: bool) -> None:
            click.echo(f"checked:strict={strict}")

        runner = CliRunner()
        result = runner.invoke(
            cli, ["build", "--profile", "standard", "--then", "check", "--strict"]
        )
        assert result.exit_code == 0
        assert "built:standard" in result.output
        assert "checked:strict=True" in result.output


class TestPipelineGroupThreeStages:
    def test_all_three_succeed_exits_0(self):
        cli = _make_pipeline_cli(("s1", 0), ("s2", 0), ("s3", 0))
        runner = CliRunner()
        result = runner.invoke(cli, ["s1", "--then", "s2", "--then", "s3"])
        assert result.exit_code == 0

    def test_middle_stage_fails_third_is_skipped(self):
        """When stage 2 fails, stage 3 must NOT run."""
        ran: list[str] = []

        @click.group(cls=PipelineGroup)
        def cli() -> None:
            pass

        @cli.command("s1")
        def _s1() -> None:
            ran.append("s1")

        @cli.command("s2")
        def _s2() -> int:
            ran.append("s2")
            return 1

        @cli.command("s3")
        def _s3() -> None:
            ran.append("s3")

        runner = CliRunner()
        result = runner.invoke(cli, ["s1", "--then", "s2", "--then", "s3"])
        assert result.exit_code != 0
        assert "s1" in ran
        assert "s2" in ran
        assert "s3" not in ran, "Stage 3 must not run after stage 2 fails"

    def test_first_stage_fails_second_and_third_skipped(self):
        ran: list[str] = []

        @click.group(cls=PipelineGroup)
        def cli() -> None:
            pass

        @cli.command("s1")
        def _s1() -> None:
            ran.append("s1")
            raise SystemExit(1)

        @cli.command("s2")
        def _s2() -> None:  # pragma: no cover
            ran.append("s2")

        @cli.command("s3")
        def _s3() -> None:  # pragma: no cover
            ran.append("s3")

        runner = CliRunner()
        result = runner.invoke(cli, ["s1", "--then", "s2", "--then", "s3"])
        assert result.exit_code != 0
        assert ran == ["s1"]


class TestPipelineGroupEdgeCases:
    def test_trailing_then_is_ignored(self):
        """A bare trailing ``--then`` must not leak as an unknown flag."""
        cli = _make_pipeline_cli(("alpha", 0))
        runner = CliRunner()
        # Trailing --then with nothing after it; PipelineGroup strips it and
        # dispatches only ["alpha"] to Click, so exit code must be 0.
        result = runner.invoke(cli, ["alpha", "--then"])
        assert result.exit_code == 0, result.output

    def test_stages_run_in_order(self):
        """Execution order must be left-to-right."""
        order: list[str] = []

        @click.group(cls=PipelineGroup)
        def cli() -> None:
            pass

        for stage_name in ("first", "second", "third"):
            def _make(n: str) -> click.BaseCommand:
                @click.command(n)
                def _cmd() -> None:
                    order.append(n)
                return _cmd

            cli.add_command(_make(stage_name))

        runner = CliRunner()
        runner.invoke(cli, ["first", "--then", "second", "--then", "third"])
        assert order == ["first", "second", "third"]

    def test_each_stage_gets_independent_click_context(self):
        """Each pipeline stage must receive its own flags without bleed-over."""

        @click.group(cls=PipelineGroup)
        def cli() -> None:
            pass

        captured: dict[str, str] = {}

        @cli.command("cmd_a")
        @click.option("--color", default="red")
        def _cmd_a(color: str) -> None:
            captured["a"] = color

        @cli.command("cmd_b")
        @click.option("--color", default="blue")
        def _cmd_b(color: str) -> None:
            captured["b"] = color

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["cmd_a", "--color", "green", "--then", "cmd_b"],
        )
        assert result.exit_code == 0
        assert captured["a"] == "green"
        # cmd_b should use its own default, not cmd_a's value
        assert captured["b"] == "blue"
