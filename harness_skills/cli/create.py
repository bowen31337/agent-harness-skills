"""harness create — generate or initialise a harness.config.yaml for the project.

Usage (CLI):
    harness create [--profile PROFILE] [--stack STACK] [--output PATH]
    harness create --dry-run
    harness create --no-merge --profile advanced --stack python
    harness create --format json          # machine-readable CreateResponse

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

JSON output
-----------
When ``--format json`` is given the command emits a schema-validated
:class:`~harness_skills.models.create.CreateResponse` object before exit::

    {
      "command": "harness create",
      "status": "passed",
      "detected_stack": {"primary_language": "Python", ...},
      "artifacts_generated": [{"artifact_path": "harness.config.yaml", ...}],
      ...
    }

Exit codes:
    0   Config written (or printed for --dry-run).
    1   Internal error (e.g. invalid profile, unwritable path).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click

from harness_skills.models.base import Status
from harness_skills.models.create import CreateResponse, DetectedStack, GeneratedArtifact

_PROFILE_CHOICE = click.Choice(
    ["starter", "standard", "advanced"], case_sensitive=False
)
_STACK_CHOICE = click.Choice(["python", "node", "go"], case_sensitive=False)

# Map CLI stack hint → canonical primary_language for DetectedStack.
_STACK_TO_LANGUAGE: dict[str, str] = {
    "python": "Python",
    "node": "JavaScript/TypeScript",
    "go": "Go",
}


def _get_generator():
    """Lazy import of config_generator to avoid load-time dependency failures."""
    from harness_skills.generators.config_generator import (  # noqa: PLC0415
        generate_gate_config,
        write_harness_config,
    )
    return generate_gate_config, write_harness_config


def _iso_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds")


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
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"], case_sensitive=False),
    default="text",
    show_default=True,
    help=(
        "Output format.  "
        "text: human-readable success message (default).  "
        "json: machine-readable CreateResponse, schema-validated before emission."
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
    output_format: str,
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
        harness create --profile standard --format json
        harness create --profile standard --then lint --then evaluate
    """
    try:
        generate_gate_config, write_harness_config = _get_generator()
    except Exception as exc:
        click.echo("harness create: dependency error -- " + str(exc), err=True)
        ctx.exit(1)
        return

    if dry_run:
        gates_yaml = generate_gate_config(profile, detected_stack=stack)
        header = "# harness create --profile " + profile
        if stack:
            header += " --stack " + stack
        header += "  (dry-run — not written to disk)\n"
        click.echo(header + gates_yaml)
        return

    # Capture whether the file existed before writing so we can set
    # GeneratedArtifact.overwritten accurately.
    existed_before = output.exists()

    try:
        merge = not no_merge
        if merge and not existed_before:
            merge = False

        write_harness_config(
            path=output,
            profile=profile,
            detected_stack=stack,
            merge=merge,
        )
    except Exception as exc:
        if output_format == "json":
            response = CreateResponse(
                status=Status.FAILED,
                timestamp=_iso_now(),
                message=str(exc),
                detected_stack=DetectedStack(
                    primary_language=_STACK_TO_LANGUAGE.get(stack or "", "unknown"),
                    project_structure="single-app",
                ),
            )
            click.echo(response.model_dump_json(indent=2))
        else:
            click.echo("harness create failed: " + str(exc), err=True)
        ctx.exit(1)
        return

    # ── CI pipeline generation ────────────────────────────────────────────────
    ci_artifacts: list[GeneratedArtifact] = []
    try:
        from harness_skills.ci.github_actions import GitHubActionsGenerator  # noqa: PLC0415
        from harness_skills.ci.gitlab_ci import GitLabCIGenerator  # noqa: PLC0415
        from harness_skills.ci.shell_script import ShellScriptGenerator  # noqa: PLC0415

        lang = _STACK_TO_LANGUAGE.get(stack or "", "python").lower()
        for gen_cls in (GitHubActionsGenerator, GitLabCIGenerator, ShellScriptGenerator):
            gen = gen_cls()
            result = gen.generate(primary_language=lang)
            ci_path = output.parent / result.file_path
            ci_path.parent.mkdir(parents=True, exist_ok=True)
            ci_path.write_text(result.content)
            ci_artifacts.append(GeneratedArtifact(
                artifact_path=str(ci_path),
                artifact_type=result.artifact_type,
                overwritten=False,
            ))
    except Exception:
        pass  # CI generation is best-effort

    # ── docs/generated/ directory scaffolding ────────────────────────────────
    docs_generated_artifact: GeneratedArtifact | None = None
    try:
        project_root = output.parent
        docs_subdirs = ["schemas", "api", "graphs"]
        for subdir in docs_subdirs:
            d = project_root / "docs" / "generated" / subdir
            d.mkdir(parents=True, exist_ok=True)
            gitkeep = d / ".gitkeep"
            if not gitkeep.exists():
                gitkeep.write_text("")
        docs_generated_artifact = GeneratedArtifact(
            artifact_path=str(project_root / "docs" / "generated"),
            artifact_type="other",
            overwritten=False,
        )
    except Exception:
        pass  # docs/generated creation is best-effort

    # ── Emit output ──────────────────────────────────────────────────────────
    if output_format == "json":
        detected = DetectedStack(
            primary_language=_STACK_TO_LANGUAGE.get(stack or "", "unknown"),
            project_structure="single-app",
            ci_platform=None,
        )
        artifact = GeneratedArtifact(
            artifact_path=str(output),
            artifact_type="harness.config.yaml",
            overwritten=existed_before,
        )
        all_artifacts = [artifact] + ci_artifacts
        if docs_generated_artifact is not None:
            all_artifacts.append(docs_generated_artifact)
        action = "updated" if existed_before else "created"
        response = CreateResponse(
            status=Status.PASSED,
            timestamp=_iso_now(),
            message=f"harness.config.yaml {action} (profile: {profile}), {len(ci_artifacts)} CI pipeline(s)",
            detected_stack=detected,
            artifacts_generated=all_artifacts,
        )
        click.echo(response.model_dump_json(indent=2))
    else:
        action = "Updated" if existed_before else "Created"
        stack_hint = ("  stack: " + stack) if stack else ""
        click.echo(action + " " + str(output) + "  (profile: " + profile + stack_hint + ")")
