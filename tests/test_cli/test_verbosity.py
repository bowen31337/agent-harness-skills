"""Tests for the --verbosity option and helpers in harness_skills.cli.verbosity.

Covers:
  - VerbosityLevel constants and ordering
  - vecho() filtering (quiet / normal / verbose / debug)
  - at_least() predicate
  - get_verbosity() context walk
  - apply_verbosity() log-level mapping
  - VERBOSITY_OPTION decorator
  - HARNESS_VERBOSITY environment variable is respected via get_verbosity
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
    """CliRunner with mix_stderr=True (default) -- stderr merged into output."""
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
# get_verbosity() -- context tree walk
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
# harness manifest validate -- basic integration (no --verbosity on group)
# ---------------------------------------------------------------------------

def _write_valid_manifest(path: Path) -> None:
    """Write a manifest that passes schema validation."""
    from datetime import datetime, timezone

    manifest = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": None,
        "git_branch": None,
        "harness_version": None,
        "project_root": None,
        "detected_stack": {
            "primary_language": "python",
            "project_structure": "single-app",
        },
        "domains": [],
        "patterns": [],
        "conventions": [],
        "artifacts": [],
        "manifest_path": None,
        "schema_path": None,
        "symbols_index_path": None,
    }
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


@pytest.fixture()
def valid_manifest(tmp_path) -> Path:
    manifest = tmp_path / "harness_manifest.json"
    _write_valid_manifest(manifest)
    return manifest


class TestManifestIntegration:
    def test_valid_manifest_exits_0(self, runner, valid_manifest):
        result = runner.invoke(
            cli, ["manifest", "validate", str(valid_manifest)]
        )
        assert result.exit_code == 0

    def test_success_message_shown(self, runner, valid_manifest):
        result = runner.invoke(
            cli, ["manifest", "validate", str(valid_manifest)]
        )
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    def test_json_flag_still_emits_json(self, runner, valid_manifest):
        """--json output is machine-parseable."""
        result = runner.invoke(
            cli,
            ["manifest", "validate", str(valid_manifest), "--json"],
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["valid"] is True

    def test_validation_errors_shown_on_failure(self, runner, tmp_path):
        """Validation errors must appear so they explain the exit code."""
        bad = tmp_path / "bad.json"
        manifest = {
            "schema_version": "1.0",
            "generated_at": "2026-01-01T00:00:00+00:00",
            "detected_stack": {
                "primary_language": "python",
                # missing project_structure
            },
            "artifacts": [],
        }
        bad.write_text(json.dumps(manifest), encoding="utf-8")

        result = runner.invoke(
            cli, ["manifest", "validate", str(bad)]
        )
        assert result.exit_code == 1
        # Error details (JSONPath) must be present
        assert "$" in result.output


# ---------------------------------------------------------------------------
# harness status -- integration (plan-file path avoids state service)
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


class TestStatusIntegration:
    def test_json_output_emitted(self, runner, plan_file):
        result = runner.invoke(
            cli,
            [
                "status",
                "--plan-file", str(plan_file),
                "--format", "json",
                "--no-state-service",
            ],
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "summary" in parsed

    def test_yaml_output_emitted(self, runner, plan_file):
        import yaml

        result = runner.invoke(
            cli,
            [
                "status",
                "--plan-file", str(plan_file),
                "--format", "yaml",
                "--no-state-service",
            ],
        )
        assert result.exit_code == 0
        parsed = yaml.safe_load(result.output)
        assert "summary" in parsed

    def test_table_output_shows_banner(self, runner, plan_file):
        result = runner.invoke(
            cli,
            [
                "status",
                "--plan-file", str(plan_file),
                "--format", "table",
                "--no-state-service",
            ],
        )
        assert result.exit_code == 0
        assert "Plan Dashboard" in result.output


# ---------------------------------------------------------------------------
# Default verbosity (normal) is the fallback
# ---------------------------------------------------------------------------


class TestDefaultVerbosity:
    def test_no_verbosity_flag_defaults_to_normal(self, runner, valid_manifest):
        result = runner.invoke(
            cli, ["manifest", "validate", str(valid_manifest)]
        )
        assert result.exit_code == 0
        # Normal mode: success message is present
        assert "valid" in result.output.lower()


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
