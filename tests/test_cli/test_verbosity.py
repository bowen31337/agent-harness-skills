"""Tests for the --verbosity option across all harness CLI commands.

Covers:
  - VerbosityLevel constants and ordering
  - vecho() filtering (quiet / normal / verbose / debug)
  - at_least() predicate
  - get_verbosity() context walk
  - apply_verbosity() log-level mapping
  - ``harness --verbosity quiet`` suppresses banners but keeps machine output
  - ``harness --verbosity verbose`` adds rationale context
  - ``harness --verbosity debug`` enables DEBUG logging
  - HARNESS_VERBOSITY environment variable is respected
  - ``harness manifest validate`` with all four verbosity levels
  - ``harness status`` with all four verbosity levels (plan-file path)
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from harness_skills.cli import VerbosityLevel, get_verbosity, vecho
from harness_skills.cli.main import cli
from harness_skills.cli.manifest import manifest_cmd
from harness_skills.cli.verbosity import (
    VERBOSITY_OPTION,
    _LOG_LEVEL_MAP,
    _RANK,
    apply_verbosity,
    at_least,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def runner() -> CliRunner:
    """CliRunner with mix_stderr=True (default) — stderr merged into output."""
    return CliRunner()


@pytest.fixture()
def isolated_runner() -> CliRunner:
    """CliRunner with mix_stderr=False for testing stdout/stderr separately."""
    return CliRunner(mix_stderr=False)


# ---------------------------------------------------------------------------
# VerbosityLevel constants
# ---------------------------------------------------------------------------


class TestVerbosityLevel:
    def test_quiet_value(self):
        assert VerbosityLevel.quiet == "quiet"

    def test_normal_value(self):
        assert VerbosityLevel.normal == "normal"

    def test_verbose_value(self):
        assert VerbosityLevel.verbose == "verbose"

    def test_debug_value(self):
        assert VerbosityLevel.debug == "debug"

    def test_choices_contains_all_levels(self):
        assert set(VerbosityLevel.CHOICES) == {"quiet", "normal", "verbose", "debug"}

    def test_choices_ordered_ascending(self):
        choices = list(VerbosityLevel.CHOICES)
        assert choices == ["quiet", "normal", "verbose", "debug"]


# ---------------------------------------------------------------------------
# _RANK ordering
# ---------------------------------------------------------------------------


class TestRankOrdering:
    def test_quiet_lowest(self):
        assert _RANK["quiet"] < _RANK["normal"]

    def test_normal_below_verbose(self):
        assert _RANK["normal"] < _RANK["verbose"]

    def test_verbose_below_debug(self):
        assert _RANK["verbose"] < _RANK["debug"]

    def test_all_levels_ranked(self):
        for level in VerbosityLevel.CHOICES:
            assert level in _RANK


# ---------------------------------------------------------------------------
# at_least()
# ---------------------------------------------------------------------------


class TestAtLeast:
    @pytest.mark.parametrize("level,min_level,expected", [
        ("quiet",   "quiet",   True),
        ("normal",  "quiet",   True),
        ("verbose", "quiet",   True),
        ("debug",   "quiet",   True),
        ("quiet",   "normal",  False),
        ("normal",  "normal",  True),
        ("verbose", "normal",  True),
        ("debug",   "normal",  True),
        ("quiet",   "verbose", False),
        ("normal",  "verbose", False),
        ("verbose", "verbose", True),
        ("debug",   "verbose", True),
        ("quiet",   "debug",   False),
        ("normal",  "debug",   False),
        ("verbose", "debug",   False),
        ("debug",   "debug",   True),
    ])
    def test_at_least_matrix(self, level, min_level, expected):
        assert at_least(level, min_level) is expected


# ---------------------------------------------------------------------------
# vecho()
# ---------------------------------------------------------------------------


class TestVecho:
    def test_quiet_suppresses_normal_messages(self, capsys):
        vecho("hello", verbosity=VerbosityLevel.quiet)
        captured = capsys.readouterr()
        assert "hello" not in captured.out

    def test_quiet_shows_quiet_messages(self, capsys):
        vecho("always", verbosity=VerbosityLevel.quiet, min_level=VerbosityLevel.quiet)
        captured = capsys.readouterr()
        assert "always" in captured.out

    def test_normal_shows_normal_messages(self, capsys):
        vecho("hello", verbosity=VerbosityLevel.normal)
        captured = capsys.readouterr()
        assert "hello" in captured.out

    def test_normal_suppresses_verbose_messages(self, capsys):
        vecho("detail", verbosity=VerbosityLevel.normal, min_level=VerbosityLevel.verbose)
        captured = capsys.readouterr()
        assert "detail" not in captured.out

    def test_verbose_shows_verbose_messages(self, capsys):
        vecho("detail", verbosity=VerbosityLevel.verbose, min_level=VerbosityLevel.verbose)
        captured = capsys.readouterr()
        assert "detail" in captured.out

    def test_verbose_suppresses_debug_messages(self, capsys):
        vecho("raw", verbosity=VerbosityLevel.verbose, min_level=VerbosityLevel.debug)
        captured = capsys.readouterr()
        assert "raw" not in captured.out

    def test_debug_shows_debug_messages(self, capsys):
        vecho("raw", verbosity=VerbosityLevel.debug, min_level=VerbosityLevel.debug)
        captured = capsys.readouterr()
        assert "raw" in captured.out

    def test_err_flag_routes_to_stderr(self, capsys):
        vecho("error msg", verbosity=VerbosityLevel.normal, err=True)
        captured = capsys.readouterr()
        assert "error msg" in captured.err
        assert "error msg" not in captured.out


# ---------------------------------------------------------------------------
# apply_verbosity() log-level mapping
# ---------------------------------------------------------------------------


class TestApplyVerbosity:
    def test_quiet_sets_error_level(self):
        apply_verbosity(VerbosityLevel.quiet)
        assert logging.getLogger().level == logging.ERROR

    def test_normal_sets_info_level(self):
        apply_verbosity(VerbosityLevel.normal)
        assert logging.getLogger().level == logging.INFO

    def test_verbose_sets_info_level(self):
        apply_verbosity(VerbosityLevel.verbose)
        assert logging.getLogger().level == logging.INFO

    def test_debug_sets_debug_level(self):
        apply_verbosity(VerbosityLevel.debug)
        assert logging.getLogger().level == logging.DEBUG

    def test_all_levels_covered_in_map(self):
        for level in VerbosityLevel.CHOICES:
            assert level in _LOG_LEVEL_MAP


# ---------------------------------------------------------------------------
# get_verbosity() — context tree walk
# ---------------------------------------------------------------------------


class TestGetVerbosity:
    def test_returns_normal_when_no_context(self):
        """Fallback when no context carries a verbosity param."""
        import click

        ctx = click.Context(click.Command("test"))
        assert get_verbosity(ctx) == VerbosityLevel.normal

    def test_reads_from_ctx_obj(self):
        import click

        ctx = click.Context(click.Command("test"))
        ctx.ensure_object(dict)
        ctx.obj["verbosity"] = VerbosityLevel.quiet
        assert get_verbosity(ctx) == VerbosityLevel.quiet

    def test_reads_from_ctx_params(self):
        import click

        ctx = click.Context(click.Command("test"))
        ctx.params["verbosity"] = VerbosityLevel.verbose
        assert get_verbosity(ctx) == VerbosityLevel.verbose

    def test_obj_takes_precedence_over_params(self):
        import click

        ctx = click.Context(click.Command("test"))
        ctx.ensure_object(dict)
        ctx.obj["verbosity"] = VerbosityLevel.debug
        ctx.params["verbosity"] = VerbosityLevel.quiet
        # obj takes precedence in get_verbosity()
        assert get_verbosity(ctx) == VerbosityLevel.debug

    def test_walks_parent_context(self):
        import click

        parent_cmd = click.Command("parent")
        child_cmd = click.Command("child")
        parent_ctx = click.Context(parent_cmd)
        parent_ctx.params["verbosity"] = VerbosityLevel.verbose
        child_ctx = click.Context(child_cmd, parent=parent_ctx)
        assert get_verbosity(child_ctx) == VerbosityLevel.verbose


# ---------------------------------------------------------------------------
# harness --verbosity option on the group
# ---------------------------------------------------------------------------


class TestGroupVerbosityOption:
    def test_help_lists_verbosity_option(self, runner):
        result = runner.invoke(cli, ["--help"])
        assert "--verbosity" in result.output

    def test_help_describes_quiet(self, runner):
        result = runner.invoke(cli, ["--help"])
        assert "quiet" in result.output

    def test_invalid_verbosity_rejected(self, runner):
        # Invoke a no-op subcommand so Click actually validates the group option.
        result = runner.invoke(cli, ["--verbosity", "silent", "manifest", "--help"])
        assert result.exit_code != 0

    def test_verbosity_choices_listed_in_help(self, runner):
        result = runner.invoke(cli, ["--help"])
        for level in VerbosityLevel.CHOICES:
            assert level in result.output

    def test_env_var_harness_verbosity_accepted(self, runner):
        """HARNESS_VERBOSITY env var should be accepted without error."""
        env = {"HARNESS_VERBOSITY": "quiet"}
        result = runner.invoke(cli, ["--help"], env=env)
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# harness manifest validate — verbosity integration
# ---------------------------------------------------------------------------


@pytest.fixture()
def valid_manifest(tmp_path) -> Path:
    from harness_skills.generators.manifest_generator import generate_manifest
    from harness_skills.models.create import DetectedStack

    stack = DetectedStack(primary_language="python", project_structure="single-app")
    manifest = tmp_path / "harness_manifest.json"
    manifest.write_text(json.dumps(generate_manifest(stack), indent=2), encoding="utf-8")
    return manifest


class TestManifestVerbosity:
    def test_quiet_suppresses_success_message(self, runner, valid_manifest):
        result = runner.invoke(
            cli, ["--verbosity", "quiet", "manifest", "validate", str(valid_manifest)]
        )
        assert result.exit_code == 0
        # The ✓ success message should NOT appear in quiet mode
        assert "✓" not in result.output
        assert "valid" not in result.output.lower()

    def test_normal_shows_success_message(self, runner, valid_manifest):
        result = runner.invoke(
            cli, ["--verbosity", "normal", "manifest", "validate", str(valid_manifest)]
        )
        assert result.exit_code == 0
        assert "✓" in result.output or "valid" in result.output.lower()

    def test_quiet_still_shows_validation_errors(self, runner, tmp_path):
        """Validation errors must always appear — they explain the exit code."""
        bad = tmp_path / "bad.json"
        from harness_skills.generators.manifest_generator import generate_manifest
        from harness_skills.models.create import DetectedStack

        m = generate_manifest(
            DetectedStack(primary_language="python", project_structure="single-app")
        )
        del m["detected_stack"]["project_structure"]
        bad.write_text(json.dumps(m), encoding="utf-8")

        result = runner.invoke(
            cli, ["--verbosity", "quiet", "manifest", "validate", str(bad)]
        )
        assert result.exit_code == 1
        # Error details (JSONPath) must still be present even in quiet mode
        assert "$" in result.output

    def test_quiet_json_flag_still_emits_json(self, runner, valid_manifest):
        """--json output is machine-parseable; always emitted even in quiet mode."""
        result = runner.invoke(
            cli,
            ["--verbosity", "quiet", "manifest", "validate", str(valid_manifest), "--json"],
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["valid"] is True

    def test_verbose_shows_file_path_context(self, runner, valid_manifest):
        result = runner.invoke(
            cli, ["--verbosity", "verbose", "manifest", "validate", str(valid_manifest)]
        )
        assert result.exit_code == 0
        # Verbose mode should mention the file being validated
        assert str(valid_manifest.name) in result.output or "Validating" in result.output


# ---------------------------------------------------------------------------
# harness status — verbosity integration (plan-file path avoids state service)
# ---------------------------------------------------------------------------


SIMPLE_PLAN = {
    "plan": {"id": "PLAN-1", "title": "Test Plan", "status": "running"},
    "tasks": [
        {"id": "T-1", "title": "Task One", "status": "running", "priority": "high"},
        {"id": "T-2", "title": "Task Two", "status": "done", "priority": "medium"},
    ],
}


@pytest.fixture()
def plan_file(tmp_path) -> Path:
    import yaml

    p = tmp_path / "plan.yaml"
    p.write_text(yaml.dump(SIMPLE_PLAN), encoding="utf-8")
    return p


class TestStatusVerbosity:
    def test_quiet_json_still_emits_json(self, runner, plan_file):
        result = runner.invoke(
            cli,
            [
                "--verbosity", "quiet",
                "status",
                "--plan-file", str(plan_file),
                "--format", "json",
                "--no-state-service",
            ],
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "summary" in parsed

    def test_quiet_yaml_still_emits_yaml(self, runner, plan_file):
        import yaml

        result = runner.invoke(
            cli,
            [
                "--verbosity", "quiet",
                "status",
                "--plan-file", str(plan_file),
                "--format", "yaml",
                "--no-state-service",
            ],
        )
        assert result.exit_code == 0
        parsed = yaml.safe_load(result.output)
        assert "summary" in parsed

    def test_quiet_table_suppresses_header_banner(self, runner, plan_file):
        result = runner.invoke(
            cli,
            [
                "--verbosity", "quiet",
                "status",
                "--plan-file", str(plan_file),
                "--format", "table",
                "--no-state-service",
            ],
        )
        assert result.exit_code == 0
        # The "harness status — Plan Dashboard" banner should not appear
        assert "Plan Dashboard" not in result.output

    def test_normal_table_shows_header_banner(self, runner, plan_file):
        result = runner.invoke(
            cli,
            [
                "--verbosity", "normal",
                "status",
                "--plan-file", str(plan_file),
                "--format", "table",
                "--no-state-service",
            ],
        )
        assert result.exit_code == 0
        assert "Plan Dashboard" in result.output

    def test_verbose_shows_load_timing(self, runner, plan_file):
        result = runner.invoke(
            cli,
            [
                "--verbosity", "verbose",
                "status",
                "--plan-file", str(plan_file),
                "--format", "table",
                "--no-state-service",
            ],
        )
        assert result.exit_code == 0
        # Verbose mode shows timing info
        assert "ms" in result.output or "Loaded" in result.output

    def test_quiet_suppresses_unreachable_state_service_warning(
        self, runner, plan_file
    ):
        """The 'state service unreachable' warning is noise — suppress in quiet."""
        result = runner.invoke(
            cli,
            [
                "--verbosity", "quiet",
                "status",
                "--plan-file", str(plan_file),
                "--format", "json",
                # Do NOT pass --no-state-service so the unreachable warning would fire
                # if verbosity were normal.  We suppress it in quiet mode.
            ],
        )
        # Should still succeed (plan file loaded fine)
        assert result.exit_code == 0
        # The warning should be absent
        assert "unreachable" not in result.output.lower()


# ---------------------------------------------------------------------------
# Default verbosity (normal) is unchanged from pre-existing behaviour
# ---------------------------------------------------------------------------


class TestDefaultVerbosity:
    def test_no_verbosity_flag_defaults_to_normal(self, runner, valid_manifest):
        result = runner.invoke(
            cli, ["manifest", "validate", str(valid_manifest)]
        )
        assert result.exit_code == 0
        # Normal mode: success message is present
        assert "✓" in result.output or "valid" in result.output.lower()

    def test_env_var_quiet_suppresses_output(self, runner, valid_manifest):
        env = {"HARNESS_VERBOSITY": "quiet"}
        result = runner.invoke(
            cli, ["manifest", "validate", str(valid_manifest)], env=env
        )
        assert result.exit_code == 0
        assert "✓" not in result.output


# ---------------------------------------------------------------------------
# VERBOSITY_OPTION is a proper Click option decorator
# ---------------------------------------------------------------------------


class TestVerbosityOptionDecorator:
    def test_option_has_envvar(self):
        import click

        # Build a minimal command with the option and check its envvar
        @click.command()
        @VERBOSITY_OPTION
        def _cmd(verbosity):
            pass

        opt = next(p for p in _cmd.params if p.name == "verbosity")
        assert "HARNESS_VERBOSITY" in (opt.envvar or [])

    def test_option_default_is_normal(self):
        import click

        @click.command()
        @VERBOSITY_OPTION
        def _cmd(verbosity):
            pass

        opt = next(p for p in _cmd.params if p.name == "verbosity")
        assert opt.default == VerbosityLevel.normal
