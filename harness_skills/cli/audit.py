"""harness audit — score artifact freshness against current codebase state.

Exit codes:
    0  All artifacts current or stale (acceptable).
    1  Outdated or obsolete artifacts found.
    2  Internal error.
"""

from __future__ import annotations

import json
import os
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import click

from harness_skills.cli.fmt import output_format_option, resolve_output_format
from harness_skills.models.audit import AuditResponse
from harness_skills.models.base import ArtifactFreshness, FreshnessScore, Status


def _iso_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds")


_ARTIFACT_PATTERNS = [
    "AGENTS.md",
    "docs/ARCHITECTURE.md",
    "docs/PRINCIPLES.md",
    "docs/EVALUATION.md",
    "harness.config.yaml",
    "harness_manifest.json",
    "harness_symbols.json",
]

_GENERATED_RE = re.compile(
    r"last_updated:\s*(\d{4}-\d{2}-\d{2})", re.IGNORECASE
)


def _score_freshness(
    days_old: float, stale_days: int, outdated_days: int, obsolete_days: int
) -> FreshnessScore:
    if days_old <= stale_days:
        return FreshnessScore.CURRENT
    if days_old <= outdated_days:
        return FreshnessScore.STALE
    if days_old <= obsolete_days:
        return FreshnessScore.OUTDATED
    return FreshnessScore.OBSOLETE


def _extract_date(path: Path) -> datetime | None:
    """Try to extract a last_updated date from file front-matter."""
    try:
        text = path.read_text(errors="ignore")[:2000]
        m = _GENERATED_RE.search(text)
        if m:
            return datetime.fromisoformat(m.group(1)).replace(tzinfo=timezone.utc)
    except OSError:
        pass
    return None


@click.command("audit")
@click.option(
    "--project-root",
    type=click.Path(exists=True, file_okay=False, resolve_path=True),
    default=".",
    help="Root of the project to audit.",
)
@click.option("--stale-days", type=int, default=30, help="Days before stale.")
@click.option("--outdated-days", type=int, default=90, help="Days before outdated.")
@click.option("--obsolete-days", type=int, default=180, help="Days before obsolete.")
@click.option(
    "--fail-on-outdated/--no-fail-on-outdated",
    default=True,
    help="Exit 1 on outdated or obsolete artifacts.",
)
@output_format_option()
def audit_cmd(
    project_root: str,
    stale_days: int,
    outdated_days: int,
    obsolete_days: int,
    fail_on_outdated: bool,
    output_format: str | None,
) -> None:
    """Score artifact freshness against current codebase state."""
    fmt = resolve_output_format(output_format)
    root = Path(project_root)
    now = datetime.now(tz=timezone.utc)

    try:
        artifacts: list[ArtifactFreshness] = []
        for pattern in _ARTIFACT_PATTERNS:
            path = root / pattern
            if not path.exists():
                continue
            date = _extract_date(path)
            if date is None:
                mtime = os.path.getmtime(path)
                date = datetime.fromtimestamp(mtime, tz=timezone.utc)
            days_old = (now - date).total_seconds() / 86400
            score = _score_freshness(days_old, stale_days, outdated_days, obsolete_days)
            artifacts.append(
                ArtifactFreshness(
                    artifact_path=pattern,
                    artifact_type=path.suffix.lstrip(".") or "md",
                    freshness=score,
                    last_generated=date.isoformat(),
                    staleness_score=round(days_old, 1),
                )
            )

        counts = {s: 0 for s in FreshnessScore}
        for a in artifacts:
            counts[a.freshness] += 1

        has_bad = counts[FreshnessScore.OUTDATED] + counts[FreshnessScore.OBSOLETE] > 0

        resp = AuditResponse(
            status=Status.FAILED if (has_bad and fail_on_outdated) else Status.PASSED,
            timestamp=_iso_now(),
            message=f"Audited {len(artifacts)} artifact(s).",
            artifacts=artifacts,
            total_artifacts=len(artifacts),
            current_count=counts[FreshnessScore.CURRENT],
            stale_count=counts[FreshnessScore.STALE],
            outdated_count=counts[FreshnessScore.OUTDATED],
            obsolete_count=counts[FreshnessScore.OBSOLETE],
        )

    except Exception:
        traceback.print_exc()
        resp = AuditResponse(
            status=Status.FAILED,
            timestamp=_iso_now(),
            message="Internal error during audit.",
        )
        if fmt == "json":
            click.echo(json.dumps(resp.model_dump(), indent=2))
        else:
            click.echo(f"ERROR: {resp.message}", err=True)
        sys.exit(2)

    if fmt == "json":
        click.echo(json.dumps(resp.model_dump(), indent=2))
    else:
        click.echo(f"Audited {resp.total_artifacts} artifact(s):")
        for a in resp.artifacts:
            click.echo(f"  [{a.freshness.value}] {a.artifact_path} ({a.staleness_score}d)")
        click.echo(
            f"\nCurrent: {resp.current_count}  Stale: {resp.stale_count}  "
            f"Outdated: {resp.outdated_count}  Obsolete: {resp.obsolete_count}"
        )

    exit_code = 1 if (has_bad and fail_on_outdated) else 0
    sys.exit(exit_code)
