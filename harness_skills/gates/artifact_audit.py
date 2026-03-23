"""
harness_skills/gates/artifact_audit.py
=======================================
Artifact audit gate — compares all generated artifacts against the current
codebase state and reports a per-artifact freshness score.

Freshness scores
----------------
``current``      Age ≤ stale_days.  Artifact is up to date; no action needed.
``stale``        stale_days < age ≤ outdated_days.  Consider refreshing soon.
``outdated``     outdated_days < age ≤ obsolete_days.  Refresh required.
``obsolete``     age > obsolete_days, or file missing.  Regenerate immediately.
``no_timestamp`` No ``generated_at`` / ``last_updated`` field found.

Artifact discovery
------------------
1. ``harness_manifest.json`` — ``artifacts[]`` array is the primary source.
2. Well-known fallback names: AGENTS.md, ARCHITECTURE.md, PRINCIPLES.md,
   EVALUATION.md, harness.config.yaml, harness_manifest.json.
3. Skill command files in ``.claude/commands/**/*.md`` (when enabled).
4. Any extra paths listed in ``ArtifactAuditGateConfig.extra_artifacts``.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

FreshnessScore = Literal["current", "stale", "outdated", "obsolete", "missing", "no_timestamp"]
Severity = Literal["error", "warning", "info"]

_GENERATED_AT_RE = re.compile(
    r"(?:<!--\s*)?(?:>\s*)?(?:generated_at|last_updated|updated_at)\s*:\s*"
    r"[\"']?(?P<date>\d{4}-\d{2}-\d{2})",
    re.IGNORECASE | re.MULTILINE,
)

_SCORE_ICON: dict[str, str] = {
    "current":      "✅",
    "stale":        "🔵",
    "outdated":     "🟡",
    "obsolete":     "🔴",
    "missing":      "❌",
    "no_timestamp": "⚪",
}

_SCORE_SEVERITY: dict[str, Severity] = {
    "current":      "info",
    "stale":        "info",
    "outdated":     "warning",
    "obsolete":     "error",
    "missing":      "error",
    "no_timestamp": "warning",
}

#: Artifact names that the harness generates and whose freshness matters.
_WELL_KNOWN_ARTIFACTS: list[str] = [
    "AGENTS.md",
    "ARCHITECTURE.md",
    "PRINCIPLES.md",
    "EVALUATION.md",
    "harness.config.yaml",
    "harness_manifest.json",
]

_SKIP_DIRS: frozenset[str] = frozenset({
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build", ".tox",
})


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class GateConfig:
    """Configuration for the artifact-audit gate.

    Attributes
    ----------
    stale_days:
        Artifacts older than this many days are scored ``stale``.
        Defaults to 14.
    outdated_days:
        Artifacts older than this many days are scored ``outdated``.
        Must be ≥ *stale_days*.  Defaults to 30.
    obsolete_days:
        Artifacts older than this many days are scored ``obsolete``.
        Must be ≥ *outdated_days*.  Defaults to 90.
    manifest_file:
        Path (relative to repo root) of the harness manifest that lists
        known artifacts.  Defaults to ``"harness_manifest.json"``.
    include_skill_commands:
        When ``True`` (default), skill command files in
        ``.claude/commands/`` are included in the audit.
    extra_artifacts:
        Additional file paths (relative to repo root) to include.
    fail_on_outdated:
        When ``True`` (default), ``outdated`` and ``obsolete`` artifacts
        are treated as blocking errors; ``stale`` remains advisory.
        Set to ``False`` to downgrade all violations to warnings.
    """

    stale_days: int = 14
    outdated_days: int = 30
    obsolete_days: int = 90
    manifest_file: str = "harness_manifest.json"
    include_skill_commands: bool = True
    extra_artifacts: list[str] = field(default_factory=list)
    fail_on_outdated: bool = True

    def __post_init__(self) -> None:
        if self.stale_days < 1:
            raise ValueError("stale_days must be >= 1")
        if self.outdated_days < self.stale_days:
            raise ValueError("outdated_days must be >= stale_days")
        if self.obsolete_days < self.outdated_days:
            raise ValueError("obsolete_days must be >= outdated_days")


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class ArtifactResult:
    """Per-artifact freshness assessment."""

    artifact_path: str           # path relative to repo root
    artifact_type: str           # type hint from manifest or inferred
    score: FreshnessScore
    severity: Severity
    age_days: int | None         # None when file is missing or has no timestamp
    last_updated: str | None     # ISO date string, or None
    message: str
    recommended_action: str


@dataclass
class AuditResult:
    """Aggregate result of the artifact-audit gate."""

    passed: bool
    artifacts: list[ArtifactResult] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)

    def errors(self) -> list[ArtifactResult]:
        return [a for a in self.artifacts if a.severity == "error"]

    def warnings(self) -> list[ArtifactResult]:
        return [a for a in self.artifacts if a.severity == "warning"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _today() -> date:
    """Return today UTC date.  Isolated for test monkeypatching."""
    return datetime.now(tz=timezone.utc).date()


def _parse_generated_at(content: str) -> date | None:
    m = _GENERATED_AT_RE.search(content)
    if not m:
        return None
    try:
        return datetime.strptime(m.group("date"), "%Y-%m-%d").date()
    except ValueError:
        return None


def _score_age(age_days: int, cfg: GateConfig) -> FreshnessScore:
    if age_days <= cfg.stale_days:
        return "current"
    if age_days <= cfg.outdated_days:
        return "stale"
    if age_days <= cfg.obsolete_days:
        return "outdated"
    return "obsolete"


def _recommended_action(score: FreshnessScore, artifact_path: str) -> str:
    if score == "current":
        return "No action needed. Artifact is up to date."
    if score == "stale":
        return (
            "Consider refreshing — run `/harness:update` to regenerate "
            "with the latest codebase state."
        )
    if score == "outdated":
        return (
            "Refresh required — artifact is overdue for regeneration. "
            "Run `/harness:update` to bring it up to date."
        )
    if score == "obsolete":
        return (
            "Regenerate immediately — artifact is severely out of date and "
            "may no longer reflect the codebase. Run `/harness:update` or "
            "`/harness:create`."
        )
    if score == "missing":
        return (
            f"Artifact not found at '{artifact_path}'. "
            "Run `/harness:create` to generate it."
        )
    # no_timestamp
    return (
        "Add a `generated_at: YYYY-MM-DD` timestamp to enable freshness "
        "tracking. Run `/harness:update` to regenerate with metadata."
    )


def _infer_type(path_str: str) -> str:
    p = Path(path_str)
    name_upper = p.name.upper()
    _known: dict[str, str] = {
        "AGENTS.MD":              "AGENTS.md",
        "ARCHITECTURE.MD":        "ARCHITECTURE.md",
        "PRINCIPLES.MD":          "PRINCIPLES.md",
        "EVALUATION.MD":          "EVALUATION.md",
        "HARNESS.CONFIG.YAML":    "harness.config.yaml",
        "HARNESS_MANIFEST.JSON":  "harness_manifest.json",
    }
    if name_upper in _known:
        return _known[name_upper]
    if p.suffix == ".md" and ".claude/commands" in path_str.replace("\\", "/"):
        return "skill_command"
    return p.suffix.lstrip(".") or "file"


# ---------------------------------------------------------------------------
# Core gate class
# ---------------------------------------------------------------------------


class ArtifactAuditGate:
    """Runs the artifact-audit gate against a repository tree.

    Parameters
    ----------
    config:
        Gate configuration.  Defaults to :class:`GateConfig` with all
        defaults.

    Examples
    --------
    ::

        gate = ArtifactAuditGate()
        result = gate.run(Path("."))
        for art in result.artifacts:
            print(f"{art.score:12s}  {art.artifact_path}")
    """

    def __init__(self, config: GateConfig | None = None) -> None:
        self.config = config or GateConfig()

    def run(self, repo_root: Path) -> AuditResult:
        """Scan *repo_root* for generated artifacts and return an :class:`AuditResult`."""
        repo_root = repo_root.resolve()
        discovered = self._discover_artifacts(repo_root)

        results: list[ArtifactResult] = []
        for path_str, artifact_type in discovered:
            result = self._assess(repo_root, path_str, artifact_type)
            results.append(result)

        # Sort: most urgent first
        _priority: dict[str, int] = {
            "missing":      0,
            "obsolete":     1,
            "outdated":     2,
            "no_timestamp": 3,
            "stale":        4,
            "current":      5,
        }
        results.sort(key=lambda r: (_priority.get(r.score, 9), r.artifact_path))

        errors = [r for r in results if r.severity == "error"]
        passed = len(errors) == 0 or not self.config.fail_on_outdated

        score_counts: dict[str, int] = {
            "current": 0, "stale": 0, "outdated": 0,
            "obsolete": 0, "missing": 0, "no_timestamp": 0,
        }
        for r in results:
            score_counts[r.score] = score_counts.get(r.score, 0) + 1

        return AuditResult(
            passed=passed,
            artifacts=results,
            stats={"total_artifacts": len(results), **score_counts},
        )

    # ------------------------------------------------------------------
    # Artifact discovery
    # ------------------------------------------------------------------

    def _discover_artifacts(self, repo_root: Path) -> list[tuple[str, str]]:
        """Return a deduplicated list of ``(rel_path, artifact_type)`` pairs."""
        found: dict[str, str] = {}  # rel_path → type (insertion order preserved)

        # 1. harness_manifest.json — authoritative source
        manifest_path = repo_root / self.config.manifest_file
        if manifest_path.is_file():
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                for entry in data.get("artifacts", []):
                    art_path = (entry.get("artifact_path") or "").strip()
                    art_type = (entry.get("artifact_type") or "").strip()
                    if art_path:
                        found.setdefault(art_path, art_type or _infer_type(art_path))
                # Always include the manifest file itself
                rel_manifest = str(manifest_path.relative_to(repo_root))
                found.setdefault(rel_manifest, "harness_manifest.json")
            except (json.JSONDecodeError, ValueError, OSError):
                pass  # Corrupt manifest — fall through to well-known fallbacks

        # 2. Well-known harness artifact names (fallback + supplemental)
        for name in _WELL_KNOWN_ARTIFACTS:
            candidate = repo_root / name
            if candidate.is_file():
                rel = str(candidate.relative_to(repo_root))
                found.setdefault(rel, _infer_type(name))

        # 3. Skill command files in .claude/commands/
        if self.config.include_skill_commands:
            cmd_dir = repo_root / ".claude" / "commands"
            if cmd_dir.is_dir():
                for md_file in sorted(cmd_dir.rglob("*.md")):
                    if any(part in _SKIP_DIRS for part in md_file.parts):
                        continue
                    try:
                        rel = str(md_file.relative_to(repo_root))
                        found.setdefault(rel, "skill_command")
                    except ValueError:
                        pass

        # 4. Extra artifacts requested by config
        for extra in self.config.extra_artifacts:
            found.setdefault(extra.strip(), _infer_type(extra))

        return list(found.items())

    # ------------------------------------------------------------------
    # Per-artifact assessment
    # ------------------------------------------------------------------

    def _assess(
        self,
        repo_root: Path,
        path_str: str,
        artifact_type: str,
    ) -> ArtifactResult:
        """Assess a single artifact and return an :class:`ArtifactResult`."""
        p = (repo_root / path_str).resolve()

        # ── Missing ──────────────────────────────────────────────────────
        if not p.exists():
            sev: Severity = "error" if self.config.fail_on_outdated else "warning"
            return ArtifactResult(
                artifact_path=path_str,
                artifact_type=artifact_type,
                score="missing",
                severity=sev,
                age_days=None,
                last_updated=None,
                message=f"Artifact not found: '{path_str}'",
                recommended_action=_recommended_action("missing", path_str),
            )

        # ── Read content ─────────────────────────────────────────────────
        content = ""
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass

        gen_date = _parse_generated_at(content)
        today = _today()

        # ── No timestamp ─────────────────────────────────────────────────
        if gen_date is None:
            return ArtifactResult(
                artifact_path=path_str,
                artifact_type=artifact_type,
                score="no_timestamp",
                severity="warning",
                age_days=None,
                last_updated=None,
                message=(
                    f"'{path_str}' has no `generated_at` or `last_updated` "
                    "timestamp — freshness cannot be determined."
                ),
                recommended_action=_recommended_action("no_timestamp", path_str),
            )

        # ── Score by age ─────────────────────────────────────────────────
        age_days = (today - gen_date).days
        score = _score_age(age_days, self.config)
        base_sev = _SCORE_SEVERITY[score]

        # Downgrade blocking errors to warnings when fail_on_outdated=False
        severity: Severity = base_sev
        if not self.config.fail_on_outdated and base_sev == "error":
            severity = "warning"

        return ArtifactResult(
            artifact_path=path_str,
            artifact_type=artifact_type,
            score=score,
            severity=severity,
            age_days=age_days,
            last_updated=gen_date.isoformat(),
            message=(
                f"'{path_str}' is {score.upper()}: "
                f"last_updated={gen_date.isoformat()}, age={age_days} day(s)"
            ),
            recommended_action=_recommended_action(score, path_str),
        )


# ---------------------------------------------------------------------------
# Rendering helpers (used by CLI and by the skill command steps)
# ---------------------------------------------------------------------------


def _result_to_dict(result: AuditResult) -> dict:
    """Serialise an :class:`AuditResult` to a plain dict for JSON output."""
    return {
        "command": "harness artifact-audit",
        "status": "passed" if result.passed else "failed",
        "stats": result.stats,
        "artifacts": [
            {
                "artifact_path": a.artifact_path,
                "artifact_type": a.artifact_type,
                "score": a.score,
                "severity": a.severity,
                "age_days": a.age_days,
                "last_updated": a.last_updated,
                "message": a.message,
                "recommended_action": a.recommended_action,
            }
            for a in result.artifacts
        ],
    }


def _print_report(result: AuditResult, cfg: GateConfig) -> None:  # pragma: no cover
    """Render a human-readable audit report to stdout."""
    bar = "━" * 60
    status_str = "✅ PASSED" if result.passed else "❌ FAILED"
    n = result.stats.get("total_artifacts", 0)

    print(f"\n{bar}")
    print(f"  Harness Artifact Audit — {status_str}")
    print(
        f"  {n} artifact(s)  ·  "
        f"stale>{cfg.stale_days}d  outdated>{cfg.outdated_days}d  "
        f"obsolete>{cfg.obsolete_days}d"
    )
    print(bar)

    if not result.artifacts:
        print("  No artifacts discovered.")
    else:
        for art in result.artifacts:
            icon = _SCORE_ICON.get(art.score, "❓")
            tag = f"[{art.score.upper():12s}]"
            if art.last_updated and art.age_days is not None:
                meta = f"last_updated={art.last_updated}  age={art.age_days}d"
            elif art.last_updated:
                meta = f"last_updated={art.last_updated}"
            else:
                meta = "no timestamp"
            print(f"  {icon}  {tag}  {art.artifact_path}")
            print(f"              {meta}")
            if art.score != "current":
                print(f"              → {art.recommended_action}")

    print(bar)
    s = result.stats
    print(
        f"  ✅ current:{s.get('current', 0)}  "
        f"🔵 stale:{s.get('stale', 0)}  "
        f"🟡 outdated:{s.get('outdated', 0)}  "
        f"🔴 obsolete:{s.get('obsolete', 0)}  "
        f"❌ missing:{s.get('missing', 0)}  "
        f"⚪ no_ts:{s.get('no_timestamp', 0)}"
    )
    print(bar)


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:  # pragma: no cover
    parser = argparse.ArgumentParser(
        prog="python -m harness_skills.gates.artifact_audit",
        description=(
            "Artifact audit gate — compare generated artifacts against the "
            "codebase and report per-artifact freshness scores."
        ),
    )
    parser.add_argument("--root", default=".", metavar="PATH",
                        help="Repository root (default: current directory)")
    parser.add_argument("--stale-days", type=int, default=14,
                        help="Days above which an artifact is scored 'stale' (default: 14)")
    parser.add_argument("--outdated-days", type=int, default=30,
                        help="Days above which an artifact is scored 'outdated' (default: 30)")
    parser.add_argument("--obsolete-days", type=int, default=90,
                        help="Days above which an artifact is scored 'obsolete' (default: 90)")
    parser.add_argument("--manifest", default="harness_manifest.json", metavar="FILE",
                        help="harness_manifest.json path relative to --root")
    parser.add_argument("--no-skill-commands", dest="skill_commands",
                        action="store_false", default=True,
                        help="Skip scanning .claude/commands/ for skill files")
    parser.add_argument(
        "--fail-on-outdated",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Treat outdated/obsolete artifacts as blocking errors (default: on)",
    )
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress human-readable output; emit only JSON on --json")
    parser.add_argument("--json", action="store_true", dest="emit_json",
                        help="Emit structured JSON to stdout after the report")
    args = parser.parse_args(argv)

    cfg = GateConfig(
        stale_days=args.stale_days,
        outdated_days=args.outdated_days,
        obsolete_days=args.obsolete_days,
        manifest_file=args.manifest,
        include_skill_commands=args.skill_commands,
        fail_on_outdated=args.fail_on_outdated,
    )
    result = ArtifactAuditGate(cfg).run(Path(args.root))

    if not args.quiet:
        _print_report(result, cfg)

    if args.emit_json:
        print(json.dumps(_result_to_dict(result), indent=2))

    return 0 if result.passed else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
