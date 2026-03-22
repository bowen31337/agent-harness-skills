"""harness create — generate or initialise a harness.config.yaml for the project.

Usage (CLI):
    harness create [--profile PROFILE] [--stack STACK] [--output PATH]
                   [--output-format json|yaml|table]
    harness create --dry-run
    harness create --no-merge --profile advanced --stack python

Generates a complete ``harness.config.yaml`` pre-populated with sensible gate
defaults for the chosen complexity profile.  If the config file already exists
at the output path, the ``gates:`` block for the selected profile is merged in
without disturbing surrounding YAML keys or comments.

Agents should:
  1. Run ``harness create`` once at project bootstrap (starter profile).
  2. Re-run with ``--profile standard`` or ``--profile advanced`` as quality
     requirements grow.
  3. Chain with lint and evaluate in a single invocation:
         harness create --then lint --then evaluate

Verbosity behaviour:
    quiet    Success message suppressed; YAML (--dry-run) still emitted.
    normal   "Created/Updated <path>  (profile: …)" on success.
    verbose  Adds stack-detection result and merge decision details.
    debug    Includes raw generator config in the output.

Exit codes:
    0   Config written (or printed for --dry-run).
    1   Internal error (e.g. invalid profile, unwritable path).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import click
import yaml

from harness_skills.cli.fmt import output_format_option, resolve_output_format

from harness_skills.cli.verbosity import VerbosityLevel, get_verbosity, vecho

_PROFILE_CHOICE = click.Choice(
    ["starter", "standard", "advanced"], case_sensitive=False
)
_STACK_CHOICE = click.Choice(["python", "node", "go"], case_sensitive=False)


def _get_generator():
    """Lazy import of config_generator to avoid load-time dependency failures."""
    from harness_skills.generators.config_generator import (  # noqa: PLC0415
        generate_gate_config,
        write_harness_config,
    )
    return generate_gate_config, write_harness_config


@click.command("create")
@click.option(
    "--profile",
    type=_PROFILE_CHOICE,
    default="starter",
    show_default=True,
    help=(
        "Complexity profile to generate gates for.  "
        "starter: essential gates only.  "
        "standard: adds architecture enforcement.  "
        "advanced: all features including telemetry and multi-agent coordination."
    ),
)
@click.option(
    "--stack",
    type=_STACK_CHOICE,
    default=None,
    help=(
        "Stack hint used to tailor inline comments (e.g. coverage-tool name).  "
        "Auto-detected from project files when omitted."
    ),
)
@click.option(
    "--output",
    default="harness.config.yaml",
    show_default=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Destination path for the config file.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help=(
        "Print the generated YAML gates block to stdout without writing to disk.  "
        "Useful for reviewing defaults before committing."
    ),
)
@click.option(
    "--no-merge",
    is_flag=True,
    default=False,
    help=(
        "Overwrite the config file from scratch instead of merging into the "
        "existing one.  Warning: this discards any manual edits to surrounding "
        "YAML keys."
    ),
)
@output_format_option(
    help_extra=(
        "For --dry-run the YAML gates block is always printed; "
        "this flag controls only the result summary for normal writes."
    ),
)
@click.pass_context
def create_cmd(
    ctx: click.Context,
    profile: str,
    stack: Optional[str],
    output: Path,
    dry_run: bool,
    no_merge: bool,
    output_format: Optional[str],
) -> None:
    """Generate or update harness.config.yaml with profile-appropriate gate defaults.

    If the output file already exists, only the ``gates:`` block for the chosen
    profile is updated — all surrounding YAML keys and comments are preserved
    (unless --no-merge is passed).

    \b
    Typical usage:
        harness create                         # starter profile, auto-detect stack
        harness create --profile standard      # add architecture enforcement
        harness create --profile advanced --stack python
        harness create --dry-run               # preview without writing
        harness create --then lint             # create then immediately lint

    \b
    Agent usage pattern:
        harness create --profile standard --then lint --then evaluate
        harness create --output-format json    # structured result for scripting
    """
<<<<<<< HEAD
    fmt = resolve_output_format(output_format)

||||||| 9c7e5db
=======
    verbosity = get_verbosity(ctx)

>>>>>>> feat/skill-invocatio-cli-commands-support-verbosity-levels-q
    try:
        generate_gate_config, write_harness_config = _get_generator()
    except Exception as exc:
        # Always show dependency errors — they explain a non-zero exit code.
        vecho(
            "harness create: dependency error -- " + str(exc),
            verbosity=verbosity,
            min_level=VerbosityLevel.quiet,
            err=True,
        )
        ctx.exit(1)
        return

    if dry_run:
        # --dry-run emits YAML to stdout — machine-parseable, always shown.
        gates_yaml = generate_gate_config(profile, detected_stack=stack)
        header = "# harness create --profile " + profile
        if stack:
            header += " --stack " + stack
        header += "  (dry-run — not written to disk)\n"
        click.echo(header + gates_yaml)
        return

<<<<<<< HEAD
    existed = output.exists()

    try:
        merge = not no_merge
        if merge and not output.exists():
            merge = False

        write_harness_config(
            path=output,
            profile=profile,
            detected_stack=stack,
            merge=merge,
||||||| 9c7e5db
    try:
        merge = not no_merge
        if merge and not output.exists():
            merge = False

        write_harness_config(
            path=output,
            profile=profile,
            detected_stack=stack,
            merge=merge,
        )
    except Exception as exc:
        click.echo("harness create failed: " + str(exc), err=True)
        ctx.exit(1)
        return

    action = "Updated" if (not no_merge and output.exists()) else "Created"
    stack_hint = ("  stack: " + stack) if stack else ""
    click.echo(action + " " + str(output) + "  (profile: " + profile + stack_hint + ")")
||||||| 8e612d9
=======
"""harness create — generate or initialise a harness.config.yaml for the project.

Usage (CLI):
    harness create [--profile PROFILE] [--stack STACK] [--output PATH]
    harness create --dry-run
    harness create --no-merge --profile advanced --stack python

Generates a complete ``harness.config.yaml`` pre-populated with sensible gate
defaults for the chosen complexity profile.  If the config file already exists
at the output path, the ``gates:`` block for the selected profile is merged in
without disturbing surrounding YAML keys or comments.

Agents should:
  1. Run ``harness create`` once at project bootstrap (starter profile).
  2. Re-run with ``--profile standard`` or ``--profile advanced`` as quality
     requirements grow.
  3. Chain with lint and evaluate in a single invocation:
         harness create --then lint --then evaluate

Exit codes:
    0   Config written (or printed for --dry-run).
    1   Internal error (e.g. invalid profile, unwritable path).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import click

from harness_skills.generators.config_generator import (
    generate_gate_config,
    write_harness_config,
)

_PROFILE_CHOICE = click.Choice(
    ["starter", "standard", "advanced"], case_sensitive=False
)
_STACK_CHOICE = click.Choice(["python", "node", "go"], case_sensitive=False)


@click.command("create")
@click.option(
    "--profile",
    type=_PROFILE_CHOICE,
    default="starter",
    show_default=True,
    help=(
        "Complexity profile to generate gates for.  "
        "starter: essential gates only.  "
        "standard: adds architecture enforcement.  "
        "advanced: all features including telemetry and multi-agent coordination."
    ),
)
@click.option(
    "--stack",
    type=_STACK_CHOICE,
    default=None,
    help=(
        "Stack hint used to tailor inline comments (e.g. coverage-tool name).  "
        "Auto-detected from project files when omitted."
    ),
)
@click.option(
    "--output",
    default="harness.config.yaml",
    show_default=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Destination path for the config file.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help=(
        "Print the generated YAML gates block to stdout without writing to disk.  "
        "Useful for reviewing defaults before committing."
    ),
)
@click.option(
    "--no-merge",
    is_flag=True,
    default=False,
    help=(
        "Overwrite the config file from scratch instead of merging into the existing one.  "
        "Warning: this discards any manual edits to surrounding YAML keys."
    ),
)
@click.pass_context
def create_cmd(
    ctx: click.Context,
    profile: str,
    stack: Optional[str],
    output: Path,
    dry_run: bool,
    no_merge: bool,
) -> None:
    """Generate or update harness.config.yaml with profile-appropriate gate defaults.

    If the output file already exists, only the ``gates:`` block for the chosen
    profile is updated — all surrounding YAML keys and comments are preserved
    (unless --no-merge is passed).

    \b
    Typical usage:
        harness create                         # starter profile, auto-detect stack
        harness create --profile standard      # add architecture enforcement
        harness create --profile advanced --stack python
        harness create --dry-run               # preview without writing
        harness create --then lint             # create then immediately lint

    \b
    Agent usage pattern:
        harness create --profile standard --then lint --then evaluate
    """
    if dry_run:
        gates_yaml = generate_gate_config(profile, detected_stack=stack)
        header = "# harness create --profile " + profile
        if stack:
            header += " --stack " + stack
        header += "  (dry-run — not written to disk)\n"
        click.echo(header + gates_yaml)
        return

    try:
        merge = not no_merge
        if merge and not output.exists():
            merge = False

        write_harness_config(
            path=output,
            profile=profile,
            detected_stack=stack,
            merge=merge,
=======
    # ── Decide merge strategy ────────────────────────────────────────────────
    file_exists = output.exists()
    merge = (not no_merge) and file_exists

    vecho(
        f"  Stack : {stack or 'auto-detect'}"
        f"  |  Profile : {profile}"
        f"  |  Mode : {'merge into existing' if merge else 'create from scratch'}",
        verbosity=verbosity,
        min_level=VerbosityLevel.verbose,
    )

    try:
        write_harness_config(
            path=output,
            profile=profile,
            detected_stack=stack,
            merge=merge,
        )
    except Exception as exc:
        # Always show write errors.
        vecho(
            "harness create failed: " + str(exc),
            verbosity=verbosity,
            min_level=VerbosityLevel.quiet,
            err=True,
>>>>>>> feat/skill-invocatio-cli-commands-support-verbosity-levels-q
        )
        ctx.exit(1)
        return

<<<<<<< HEAD
    action = "updated" if (not no_merge and existed) else "created"

    if fmt == "json":
        result = {
            "status": "ok",
            "action": action,
            "path": str(output),
            "profile": profile,
            "stack": stack,
        }
        click.echo(json.dumps(result, indent=2))
    elif fmt == "yaml":
        result = {
            "status": "ok",
            "action": action,
            "path": str(output),
            "profile": profile,
            "stack": stack,
        }
        click.echo(
            yaml.dump(result, default_flow_style=False, sort_keys=False, allow_unicode=True),
            nl=False,
        )
    else:
        action_label = action.capitalize()
        stack_hint = ("  stack: " + stack) if stack else ""
        click.echo(
            action_label + " " + str(output)
            + "  (profile: " + profile + stack_hint + ")"
        )
||||||| 9c7e5db
    action = "Updated" if (not no_merge and output.exists()) else "Created"
    stack_hint = ("  stack: " + stack) if stack else ""
    click.echo(action + " " + str(output) + "  (profile: " + profile + stack_hint + ")")
>>>>>>> feat/codebase-analys-skill-detects-primary-language-s-and-fr
=======
    action = "Updated" if merge else "Created"
    stack_hint = ("  stack: " + stack) if stack else ""

    # Success message — suppressed in quiet mode (not machine-parseable).
    vecho(
        action + " " + str(output) + "  (profile: " + profile + stack_hint + ")",
        verbosity=verbosity,
    )

    # Verbose: additional detail about what changed.
    if merge:
        vecho(
            f"  Merged '{profile}' gates into existing {output} "
            "(surrounding keys preserved).",
            verbosity=verbosity,
            min_level=VerbosityLevel.verbose,
        )
    else:
        vecho(
            f"  New file created at {output}.",
            verbosity=verbosity,
            min_level=VerbosityLevel.verbose,
        )
>>>>>>> feat/skill-invocatio-cli-commands-support-verbosity-levels-q
