"""harness update — re-scan codebase and update existing harness artifacts.

Uses three-way merge to preserve manual edits while updating auto-generated
sections.  Appends changes to ``docs/harness-changelog.md``.

Exit codes:
    0  Artifacts updated successfully.
    1  No changes detected.
    2  Internal error.
"""

from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import click

from harness_skills.cli.fmt import output_format_option, resolve_output_format
from harness_skills.models.base import Status
from harness_skills.models.update import ArtifactDiff, ChangelogEntry, UpdateResponse


def _iso_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds")


def _lazy_regenerate():
    from harness_skills.generators.agents_md import regenerate_all  # noqa: PLC0415

    return regenerate_all


def _lazy_detect_stack():
    from harness_skills.generators.codebase_analyzer import detect_stack  # noqa: PLC0415

    return detect_stack


@click.command("update")
@click.option(
    "--project-root",
    type=click.Path(exists=True, file_okay=False, resolve_path=True),
    default=".",
    help="Root of the project to re-scan.",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite manual edits (except CUSTOM blocks).",
)
@click.option(
    "--no-changelog",
    is_flag=True,
    default=False,
    help="Skip appending to docs/harness-changelog.md.",
)
@output_format_option()
def update_cmd(
    project_root: str,
    force: bool,
    no_changelog: bool,
    output_format: str | None,
) -> None:
    """Re-scan codebase and update harness artifacts via three-way merge."""
    fmt = resolve_output_format(output_format)
    root = Path(project_root)
    t0 = datetime.now(tz=timezone.utc)

    try:
        detect_stack = _lazy_detect_stack()
        regenerate_all = _lazy_regenerate()

        stack = detect_stack(root)
        results = regenerate_all(root, force=force)

        diffs: list[ArtifactDiff] = []
        changelog_entries: list[ChangelogEntry] = []
        for r in results:
            if isinstance(r, dict):
                change_type = r.get("change_type", "unchanged")
                art_path = r.get("path", "")
                secs = r.get("sections_changed", [])
                preserved = r.get("manual_edits_preserved", True)
            else:
                change_type = getattr(r, "change_type", "unchanged")
                art_path = getattr(r, "path", "")
                secs = getattr(r, "sections_changed", [])
                preserved = getattr(r, "manual_edits_preserved", True)
            diff = ArtifactDiff(
                artifact_path=art_path,
                change_type=change_type,
                sections_changed=secs,
                manual_edits_preserved=preserved,
            )
            diffs.append(diff)
            if change_type != "unchanged":
                changelog_entries.append(
                    ChangelogEntry(
                        artifact_path=diff.artifact_path,
                        change_summary=f"{change_type}: {', '.join(diff.sections_changed) or 'full file'}",
                    )
                )

        changelog_path = None
        if not no_changelog and changelog_entries:
            cl_path = root / "docs" / "harness-changelog.md"
            cl_path.parent.mkdir(parents=True, exist_ok=True)
            with cl_path.open("a") as f:
                f.write(f"\n## Update {_iso_now()}\n\n")
                for entry in changelog_entries:
                    f.write(f"- **{entry.artifact_path}**: {entry.change_summary}\n")
            changelog_path = str(cl_path)

        has_changes = any(d.change_type != "unchanged" for d in diffs)
        elapsed = int((datetime.now(tz=timezone.utc) - t0).total_seconds() * 1000)

        resp = UpdateResponse(
            status=Status.PASSED if has_changes else Status.SKIPPED,
            timestamp=_iso_now(),
            duration_ms=elapsed,
            message=f"Updated {sum(1 for d in diffs if d.change_type != 'unchanged')} artifact(s)."
            if has_changes
            else "No changes detected.",
            artifacts_diff=diffs,
            changelog_path=changelog_path,
            changelog_entries=changelog_entries,
        )

    except Exception:
        traceback.print_exc()
        resp = UpdateResponse(
            status=Status.FAILED,
            timestamp=_iso_now(),
            message="Internal error during update.",
        )
        if fmt == "json":
            click.echo(json.dumps(resp.model_dump(), indent=2))
        else:
            click.echo(f"ERROR: {resp.message}", err=True)
        sys.exit(2)

    if fmt == "json":
        click.echo(json.dumps(resp.model_dump(), indent=2))
    else:
        click.echo(f"Status: {resp.status.value}")
        click.echo(f"Message: {resp.message}")
        for d in resp.artifacts_diff:
            if d.change_type != "unchanged":
                click.echo(f"  {d.change_type}: {d.artifact_path}")

    sys.exit(0 if has_changes else 1)
