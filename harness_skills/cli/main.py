"""harness CLI entry point.

Supports ``--then`` command composition so that multiple subcommands can be
chained in a single invocation without extra shell glue:

    harness create --then lint --then evaluate

Each step runs in sequence; execution stops on the first non-zero exit code.

Verbosity
---------
A global ``--verbosity`` option controls how much output every subcommand
produces:

    harness --verbosity quiet evaluate --format json   # machine-parseable only
    harness --verbosity verbose status                 # adds rationale & timing
    harness --verbosity debug create                   # enables DEBUG logging
"""

from __future__ import annotations

import sys
from typing import Any

import click

<<<<<<< HEAD
from harness_skills.cli.completion_report import completion_report_cmd
||||||| 7446a2f
=======
from harness_skills.cli.boot import boot_cmd
>>>>>>> feat/skill-invocatio-skill-registers-as-harness-boot-for-lau
from harness_skills.cli.create import create_cmd
from harness_skills.cli.evaluate import evaluate_cmd
from harness_skills.cli.lint import lint_cmd
from harness_skills.cli.manifest import manifest_cmd
from harness_skills.cli.observe import observe_cmd
from harness_skills.cli.status import status_cmd
from harness_skills.cli.verbosity import (
    VERBOSITY_OPTION,
    VerbosityLevel,
    apply_verbosity,
)
from harness_skills.telemetry_reporter import telemetry_cmd


# ---------------------------------------------------------------------------
# --then pipeline helpers
# ---------------------------------------------------------------------------


def _split_on_then(args: list[str]) -> list[list[str]]:
    """Split a flat args list at ``--then`` boundaries.

    ``["create", "--profile", "standard", "--then", "lint", "--then", "evaluate"]``
    becomes ``[["create", "--profile", "standard"], ["lint"], ["evaluate"]]``.

    A trailing ``--then`` with no following tokens is silently dropped.
    """
    segments: list[list[str]] = [[]]
    for token in args:
        if token == "--then":
            segments.append([])
        else:
            segments[-1].append(token)
    return [s for s in segments if s]


class PipelineGroup(click.Group):
    """A Click Group that understands ``--then SUBCMD`` chaining.

    When the CLI is invoked with one or more ``--then`` tokens the argument
    list is split at those boundaries and each stage is run as an independent
    Click invocation in sequence.  A non-zero exit code from any stage aborts
    the remainder of the pipeline.

    Without any ``--then`` tokens the behaviour is identical to a plain
    :class:`click.Group`.

    Examples
    --------
    ::

        # Single command (normal behaviour)
<<<<<<< HEAD
        harness evaluate --output-format json

        # Pipeline (composition) — equivalent to: harness create && harness lint
        harness create --then lint --then evaluate
        harness create --profile standard --then lint --gate architecture
    """

    def main(  # type: ignore[override]
        self,
        args: list[str] | None = None,
        prog_name: str | None = None,
        complete_var: str | None = None,
        standalone_mode: bool = True,
        **extra: Any,
    ) -> Any:
        raw: list[str] = list(args if args is not None else sys.argv[1:])
        segments = _split_on_then(raw)

        # No chaining — normal Click dispatch
        if len(segments) <= 1:
            return super().main(
                args=raw,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=standalone_mode,
                **extra,
            )

        # Pipeline mode: run each segment in sequence
        last_result: Any = 0
        for i, seg in enumerate(segments):
            result = super().main(
                args=seg,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=False,
                **extra,
            )
            last_result = result

            if isinstance(result, int) and result != 0:
                click.echo(
                    f"[harness pipeline] Stage {i + 1} ({seg[0]!r}) failed "
                    f"(exit {result}) — aborting remaining stages.",
                    err=True,
                )
                if standalone_mode:
                    sys.exit(result)
                return result

        exit_code = last_result if isinstance(last_result, int) else 0
        if standalone_mode:
            sys.exit(exit_code)
        return exit_code


# ---------------------------------------------------------------------------
# CLI group and command registration
# ---------------------------------------------------------------------------


@click.group(cls=PipelineGroup)
||||||| 9c7e5db
<<<<<<< HEAD
# ---------------------------------------------------------------------------
# --then pipeline helpers
# ---------------------------------------------------------------------------


def _split_on_then(args: list[str]) -> list[list[str]]:
    """Split a flat args list at ``--then`` boundaries.

    ``["create", "--profile", "standard", "--then", "lint", "--then", "evaluate"]``
    becomes ``[["create", "--profile", "standard"], ["lint"], ["evaluate"]]``.

    A trailing ``--then`` with no following tokens is silently dropped.
    """
    segments: list[list[str]] = [[]]
    for token in args:
        if token == "--then":
            segments.append([])
        else:
            segments[-1].append(token)
    return [s for s in segments if s]


class PipelineGroup(click.Group):
    """A Click Group that understands ``--then SUBCMD`` chaining.

    When the CLI is invoked with one or more ``--then`` tokens the argument
    list is split at those boundaries and each stage is run as an independent
    Click invocation in sequence.  A non-zero exit code from any stage aborts
    the remainder of the pipeline.

    Without any ``--then`` tokens the behaviour is identical to a plain
    :class:`click.Group`.

    Examples
    --------
    ::

        # Single command (normal behaviour)
        harness evaluate --format json
||||||| 9c7e5db
        harness evaluate --format json
=======
        harness evaluate --output-format json
>>>>>>> feat/skill-invocatio-all-cli-commands-support-a-output-forma

        # Pipeline (composition) — equivalent to: harness create && harness lint
        harness create --then lint --then evaluate
        harness create --profile standard --then lint --gate architecture
    """

    def main(  # type: ignore[override]
        self,
        args: list[str] | None = None,
        prog_name: str | None = None,
        complete_var: str | None = None,
        standalone_mode: bool = True,
        **extra: Any,
    ) -> Any:
        raw: list[str] = list(args if args is not None else sys.argv[1:])
        segments = _split_on_then(raw)

        # No chaining — normal Click dispatch
        if len(segments) <= 1:
            return super().main(
                args=raw,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=standalone_mode,
                **extra,
            )

        # Pipeline mode: run each segment in sequence
        last_result: Any = 0
        for i, seg in enumerate(segments):
            result = super().main(
                args=seg,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=False,
                **extra,
            )
            last_result = result

            if isinstance(result, int) and result != 0:
                click.echo(
                    f"[harness pipeline] Stage {i + 1} ({seg[0]!r}) failed "
                    f"(exit {result}) — aborting remaining stages.",
                    err=True,
                )
                if standalone_mode:
                    sys.exit(result)
                return result

        exit_code = last_result if isinstance(last_result, int) else 0
        if standalone_mode:
            sys.exit(exit_code)
        return exit_code


# ---------------------------------------------------------------------------
# CLI group and command registration
# ---------------------------------------------------------------------------


@click.group(cls=PipelineGroup)
<<<<<<< HEAD
||||||| 8e612d9
@click.group()
=======
# ---------------------------------------------------------------------------
# --then pipeline helpers
# ---------------------------------------------------------------------------


def _split_on_then(args: list[str]) -> list[list[str]]:
    """Split a flat args list at ``--then`` boundaries.

    ``["create", "--profile", "standard", "--then", "lint", "--then", "evaluate"]``
    becomes ``[["create", "--profile", "standard"], ["lint"], ["evaluate"]]``.

    A trailing ``--then`` with no following tokens is silently dropped.
    """
    segments: list[list[str]] = [[]]
    for token in args:
        if token == "--then":
            segments.append([])
        else:
            segments[-1].append(token)
    return [s for s in segments if s]


class PipelineGroup(click.Group):
    """A Click Group that understands ``--then SUBCMD`` chaining.

    When the CLI is invoked with one or more ``--then`` tokens the argument
    list is split at those boundaries and each stage is run as an independent
    Click invocation in sequence.  A non-zero exit code from any stage aborts
    the remainder of the pipeline.

    Without any ``--then`` tokens the behaviour is identical to a plain
    :class:`click.Group`.

    Examples
    --------
    ::

        # Single command (normal behaviour)
        harness evaluate --format json

        # Pipeline (composition) — equivalent to harness create && harness lint
        harness create --then lint --then evaluate
        harness create --profile standard --then lint --gate architecture
    """

    def main(  # type: ignore[override]
        self,
        args: list[str] | None = None,
        prog_name: str | None = None,
        complete_var: str | None = None,
        standalone_mode: bool = True,
        **extra: Any,
    ) -> Any:
        raw: list[str] = list(args if args is not None else sys.argv[1:])
        segments = _split_on_then(raw)

        # No chaining — normal Click dispatch
        if len(segments) <= 1:
            return super().main(
                args=raw,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=standalone_mode,
                **extra,
            )

        # Pipeline mode: run each segment in sequence
        last_result: Any = 0
        for i, seg in enumerate(segments):
            result = super().main(
                args=seg,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=False,
                **extra,
            )
            last_result = result

            if isinstance(result, int) and result != 0:
                click.echo(
                    f"[harness pipeline] Stage {i + 1} ({seg[0]!r}) failed "
                    f"(exit {result}) — aborting remaining stages.",
                    err=True,
                )
                if standalone_mode:
                    sys.exit(result)
                return result

        exit_code = last_result if isinstance(last_result, int) else 0
        if standalone_mode:
            sys.exit(exit_code)
        return exit_code


# ---------------------------------------------------------------------------
# CLI group and command registration
# ---------------------------------------------------------------------------


@click.group(cls=PipelineGroup)
>>>>>>> feat/codebase-analys-skill-detects-primary-language-s-and-fr
=======
# ---------------------------------------------------------------------------
# --then pipeline helpers
# ---------------------------------------------------------------------------


def _split_on_then(args: list[str]) -> list[list[str]]:
    """Split a flat args list at ``--then`` boundaries.

    ``["create", "--profile", "standard", "--then", "lint", "--then", "evaluate"]``
    becomes ``[["create", "--profile", "standard"], ["lint"], ["evaluate"]]``.

    A trailing ``--then`` with no following tokens is silently dropped.
    """
    segments: list[list[str]] = [[]]
    for token in args:
        if token == "--then":
            segments.append([])
        else:
            segments[-1].append(token)
    return [s for s in segments if s]


class PipelineGroup(click.Group):
    """A Click Group that understands ``--then SUBCMD`` chaining.

    When the CLI is invoked with one or more ``--then`` tokens the argument
    list is split at those boundaries and each stage is run as an independent
    Click invocation in sequence.  A non-zero exit code from any stage aborts
    the remainder of the pipeline.

    Without any ``--then`` tokens the behaviour is identical to a plain
    :class:`click.Group`.

    Examples
    --------
    ::

        # Single command (normal behaviour)
        harness evaluate --format json

        # Pipeline (composition) — equivalent to harness create && harness lint
        harness create --then lint --then evaluate
        harness create --profile standard --then lint --gate architecture
    """

    def main(  # type: ignore[override]
        self,
        args: list[str] | None = None,
        prog_name: str | None = None,
        complete_var: str | None = None,
        standalone_mode: bool = True,
        **extra: Any,
    ) -> Any:
        raw: list[str] = list(args if args is not None else sys.argv[1:])
        segments = _split_on_then(raw)

        # No chaining — normal Click dispatch
        if len(segments) <= 1:
            return super().main(
                args=raw,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=standalone_mode,
                **extra,
            )

        # Pipeline mode: run each segment in sequence
        last_result: Any = 0
        for i, seg in enumerate(segments):
            result = super().main(
                args=seg,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=False,
                **extra,
            )
            last_result = result

            if isinstance(result, int) and result != 0:
                click.echo(
                    f"[harness pipeline] Stage {i + 1} ({seg[0]!r}) failed "
                    f"(exit {result}) — aborting remaining stages.",
                    err=True,
                )
                if standalone_mode:
                    sys.exit(result)
                return result

        exit_code = last_result if isinstance(last_result, int) else 0
        if standalone_mode:
            sys.exit(exit_code)
        return exit_code


# ---------------------------------------------------------------------------
# CLI group and command registration
# ---------------------------------------------------------------------------


@click.group(cls=PipelineGroup)
>>>>>>> feat/skill-invocatio-cli-commands-support-verbosity-levels-q
||||||| 9c7e5db
||||||| 8e612d9
@click.group()
=======
# ---------------------------------------------------------------------------
# --then pipeline helpers
# ---------------------------------------------------------------------------


def _split_on_then(args: list[str]) -> list[list[str]]:
    """Split a flat args list at ``--then`` boundaries.

    ``["create", "--profile", "standard", "--then", "lint", "--then", "evaluate"]``
    becomes ``[["create", "--profile", "standard"], ["lint"], ["evaluate"]]``.

    A trailing ``--then`` with no following tokens is silently dropped.
    """
    segments: list[list[str]] = [[]]
    for token in args:
        if token == "--then":
            segments.append([])
        else:
            segments[-1].append(token)
    return [s for s in segments if s]


class PipelineGroup(click.Group):
    """A Click Group that understands ``--then SUBCMD`` chaining.

    When the CLI is invoked with one or more ``--then`` tokens the argument
    list is split at those boundaries and each stage is run as an independent
    Click invocation in sequence.  A non-zero exit code from any stage aborts
    the remainder of the pipeline.

    Without any ``--then`` tokens the behaviour is identical to a plain
    :class:`click.Group`.

    Examples
    --------
    ::

        # Single command (normal behaviour)
        harness evaluate --format json

        # Pipeline (composition) — equivalent to harness create && harness lint
        harness create --then lint --then evaluate
        harness create --profile standard --then lint --gate architecture
    """

    def main(  # type: ignore[override]
        self,
        args: list[str] | None = None,
        prog_name: str | None = None,
        complete_var: str | None = None,
        standalone_mode: bool = True,
        **extra: Any,
    ) -> Any:
        raw: list[str] = list(args if args is not None else sys.argv[1:])
        segments = _split_on_then(raw)

        # No chaining — normal Click dispatch
        if len(segments) <= 1:
            return super().main(
                args=raw,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=standalone_mode,
                **extra,
            )

        # Pipeline mode: run each segment in sequence
        last_result: Any = 0
        for i, seg in enumerate(segments):
            result = super().main(
                args=seg,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=False,
                **extra,
            )
            last_result = result

            if isinstance(result, int) and result != 0:
                click.echo(
                    f"[harness pipeline] Stage {i + 1} ({seg[0]!r}) failed "
                    f"(exit {result}) — aborting remaining stages.",
                    err=True,
                )
                if standalone_mode:
                    sys.exit(result)
                return result

        exit_code = last_result if isinstance(last_result, int) else 0
        if standalone_mode:
            sys.exit(exit_code)
        return exit_code


# ---------------------------------------------------------------------------
# CLI group and command registration
# ---------------------------------------------------------------------------


@click.group(cls=PipelineGroup)
>>>>>>> feat/codebase-analys-skill-detects-primary-language-s-and-fr
=======
>>>>>>> feat/skill-invocatio-all-cli-commands-support-a-output-forma
@click.version_option()
<<<<<<< HEAD
def cli() -> None:
||||||| 9c7e5db
def cli() -> None:
<<<<<<< HEAD
<<<<<<< HEAD
    """Harness Skills -- agent harness engineering toolkit.

    Subcommands can be chained with ``--then`` for single-invocation pipelines:

    \b
        harness create --then lint --then evaluate

    Each stage runs in order; a failing stage aborts the remainder.
    """
||||||| 8e612d9
    """Harness Skills — agent harness engineering toolkit."""
=======
=======
@VERBOSITY_OPTION
@click.pass_context
def cli(ctx: click.Context, verbosity: str) -> None:
>>>>>>> feat/skill-invocatio-cli-commands-support-verbosity-levels-q
||||||| 9c7e5db
<<<<<<< HEAD
    """Harness Skills -- agent harness engineering toolkit.

    Subcommands can be chained with ``--then`` for single-invocation pipelines:

    \b
        harness create --then lint --then evaluate

    Each stage runs in order; a failing stage aborts the remainder.
    """
||||||| 8e612d9
    """Harness Skills — agent harness engineering toolkit."""
=======
=======
>>>>>>> feat/skill-invocatio-all-cli-commands-support-a-output-forma
    """Harness Skills — agent harness engineering toolkit.

    Subcommands can be chained with ``--then`` for single-invocation pipelines:

    \b
        harness create --then lint --then evaluate

    Each stage runs in order; a failing stage aborts the remainder.

    \b
    Verbosity levels:
        quiet    machine-parseable results only (best for CI / pipes)
        normal   standard messages — default
        verbose  adds rationale, context, and timing
        debug    enables DEBUG logging and exposes internal state
    """
<<<<<<< HEAD
<<<<<<< HEAD
||||||| 9c7e5db
>>>>>>> feat/codebase-analys-skill-detects-primary-language-s-and-fr
=======
    # Store verbosity on ctx.obj so subcommands and pipeline stages can read it
    ctx.ensure_object(dict)
    ctx.obj["verbosity"] = verbosity

    # Configure structured logging as early as possible
    apply_verbosity(verbosity)
>>>>>>> feat/skill-invocatio-cli-commands-support-verbosity-levels-q
||||||| 9c7e5db
>>>>>>> feat/codebase-analys-skill-detects-primary-language-s-and-fr
=======
>>>>>>> feat/skill-invocatio-all-cli-commands-support-a-output-forma


<<<<<<< HEAD
cli.add_command(completion_report_cmd)
||||||| 7446a2f
=======
cli.add_command(boot_cmd)
>>>>>>> feat/skill-invocatio-skill-registers-as-harness-boot-for-lau
cli.add_command(create_cmd)
cli.add_command(evaluate_cmd)
cli.add_command(lint_cmd)
cli.add_command(manifest_cmd)
cli.add_command(observe_cmd)
cli.add_command(status_cmd)
cli.add_command(telemetry_cmd)
