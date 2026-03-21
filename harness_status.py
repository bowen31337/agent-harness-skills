"""
harness status
==============
Plan status dashboard for the claw-forge agent harness.

Scans plan files written by the HandoffProtocol and renders a dashboard
showing active, completed, and blocked plans.

Usage
-----
    # Human-readable table (default)
    python harness_status.py

    # Machine-parseable formats
    python harness_status.py --format json
    python harness_status.py --format yaml

    # Filter by status
    python harness_status.py --filter active
    python harness_status.py --filter blocked,completed

    # Custom plans directory
    python harness_status.py --dir .claude/plans

Exit codes
----------
    0  — all plans healthy (active or completed, none blocked)
    1  — one or more plans are blocked
    2  — no plan files found
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml  # PyYAML

# ---------------------------------------------------------------------------
# Re-use domain objects from the existing harness_skills package.
# ---------------------------------------------------------------------------
try:
    from harness_skills.handoff import HandoffDocument  # type: ignore[import]
except ImportError:  # running as a standalone script without a package install
    import importlib.util, os

    _spec = importlib.util.spec_from_file_location(
        "handoff",
        Path(__file__).parent / "harness_skills" / "handoff.py",
    )
    _mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
    _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
    HandoffDocument = _mod.HandoffDocument  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Status mapping
# ---------------------------------------------------------------------------

#: Canonical status values exposed by this command (machine-stable strings).
STATUS_ACTIVE    = "active"
STATUS_COMPLETED = "completed"
STATUS_BLOCKED   = "blocked"
STATUS_UNKNOWN   = "unknown"

#: Map raw handoff `status` field → canonical status.
_RAW_TO_CANONICAL: dict[str, str] = {
    "in_progress": STATUS_ACTIVE,
    "done":        STATUS_COMPLETED,
    "blocked":     STATUS_BLOCKED,
}

_ALL_STATUSES = (STATUS_ACTIVE, STATUS_COMPLETED, STATUS_BLOCKED, STATUS_UNKNOWN)


def _canonical_status(raw: str) -> str:
    return _RAW_TO_CANONICAL.get(raw.lower().strip(), STATUS_UNKNOWN)


# ---------------------------------------------------------------------------
# Plan record  (flattened, serialisation-friendly)
# ---------------------------------------------------------------------------


def _plan_record(doc: HandoffDocument, source_file: Path) -> dict[str, Any]:
    """Convert a HandoffDocument into a flat, machine-parseable dict."""
    status = _canonical_status(doc.status)
    hints  = doc.search_hints

    return {
        # Identity
        "session_id":          doc.session_id,
        "task":                doc.task,
        # Status fields
        "status":              status,         # canonical: active|completed|blocked|unknown
        "raw_status":          doc.status,     # as written in the handoff file
        # Temporal
        "timestamp":           doc.timestamp,  # ISO-8601 string as recorded
        # Progress counters
        "accomplished_count":  len(doc.accomplished),
        "in_progress_count":   len(doc.in_progress),
        "next_steps_count":    len(doc.next_steps),
        "open_questions_count": len(doc.open_questions),
        "artifacts_count":     len(doc.artifacts),
        # Blocking detail (non-empty only when blocked)
        "blockers":            doc.open_questions if status == STATUS_BLOCKED else [],
        # Next actions
        "next_steps":          doc.next_steps,
        "accomplished":        doc.accomplished,
        # Search hints (useful for downstream tooling)
        "hints": {
            "file_paths":     hints.file_paths,
            "grep_patterns":  hints.grep_patterns,
            "symbols":        hints.symbols,
            "directories":    hints.directories,
        },
        # Provenance
        "source_file": str(source_file),
        "notes":       doc.notes,
    }


# ---------------------------------------------------------------------------
# Scanner — discovers plan files
# ---------------------------------------------------------------------------

#: Paths checked for a single-file handoff (legacy / default).
_SINGLE_FILE_PATHS = [
    Path(".claude/plan-progress.md"),
]

#: Glob patterns used when scanning a plans directory.
_PLAN_GLOB = "*.md"


def _load_plan_file(path: Path) -> dict[str, Any] | None:
    """Parse one Markdown handoff file; returns None on failure."""
    try:
        text = path.read_text(encoding="utf-8")
        doc  = HandoffDocument.from_markdown(text)
        return _plan_record(doc, path)
    except Exception as exc:  # noqa: BLE001
        # Emit a soft warning but don't crash the whole dashboard.
        print(f"[warn] Could not parse {path}: {exc}", file=sys.stderr)
        return None


def scan_plans(plans_dir: Path | None = None) -> list[dict[str, Any]]:
    """
    Discover and load all plan files.

    Search order
    ~~~~~~~~~~~~
    1. If *plans_dir* is given and exists, glob ``*.md`` inside it.
    2. Also check each path in ``_SINGLE_FILE_PATHS`` (adds the default
       ``.claude/plan-progress.md`` when it has not already been picked up).
    """
    seen: set[Path] = set()
    records: list[dict[str, Any]] = []

    def _add(p: Path) -> None:
        resolved = p.resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        rec = _load_plan_file(p)
        if rec is not None:
            records.append(rec)

    # 1. Plans directory
    if plans_dir is not None and plans_dir.is_dir():
        for f in sorted(plans_dir.glob(_PLAN_GLOB)):
            _add(f)

    # 2. Single-file fallbacks
    for p in _SINGLE_FILE_PATHS:
        if p.exists():
            _add(p)

    return records


# ---------------------------------------------------------------------------
# Summary builder
# ---------------------------------------------------------------------------


def build_dashboard(
    records: list[dict[str, Any]],
    generated_at: str,
) -> dict[str, Any]:
    """Assemble the top-level dashboard payload."""
    counts: dict[str, int] = {s: 0 for s in _ALL_STATUSES}
    for r in records:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    return {
        "generated_at": generated_at,
        "summary": {
            "total":     len(records),
            "active":    counts[STATUS_ACTIVE],
            "completed": counts[STATUS_COMPLETED],
            "blocked":   counts[STATUS_BLOCKED],
            "unknown":   counts[STATUS_UNKNOWN],
        },
        "plans": records,
    }


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

_STATUS_ICON = {
    STATUS_ACTIVE:    "▶",
    STATUS_COMPLETED: "✔",
    STATUS_BLOCKED:   "✖",
    STATUS_UNKNOWN:   "?",
}

_STATUS_COLOUR = {
    STATUS_ACTIVE:    "\033[34m",   # blue
    STATUS_COMPLETED: "\033[32m",   # green
    STATUS_BLOCKED:   "\033[31m",   # red
    STATUS_UNKNOWN:   "\033[33m",   # yellow
}
_RESET = "\033[0m"


def _coloured(text: str, colour: str, no_colour: bool) -> str:
    return text if no_colour else f"{colour}{text}{_RESET}"


def format_json(dashboard: dict[str, Any]) -> str:
    return json.dumps(dashboard, indent=2, ensure_ascii=False)


def format_yaml(dashboard: dict[str, Any]) -> str:
    return yaml.dump(dashboard, default_flow_style=False, allow_unicode=True, sort_keys=False)


def format_table(dashboard: dict[str, Any], no_colour: bool = False) -> str:
    lines: list[str] = []
    s = dashboard["summary"]
    ts = dashboard["generated_at"]

    # ── Header ──────────────────────────────────────────────────────────
    lines.append(f"\n  harness status  ·  {ts}")
    lines.append(
        f"  total {s['total']}  │  "
        + _coloured(f"▶ active {s['active']}", _STATUS_COLOUR[STATUS_ACTIVE], no_colour)
        + "  "
        + _coloured(f"✔ completed {s['completed']}", _STATUS_COLOUR[STATUS_COMPLETED], no_colour)
        + "  "
        + _coloured(f"✖ blocked {s['blocked']}", _STATUS_COLOUR[STATUS_BLOCKED], no_colour)
    )
    lines.append("")

    if not dashboard["plans"]:
        lines.append("  (no plan files found)")
        lines.append("")
        return "\n".join(lines)

    # ── Per-status sections ──────────────────────────────────────────────
    for canonical, heading in (
        (STATUS_ACTIVE,    "ACTIVE"),
        (STATUS_BLOCKED,   "BLOCKED"),
        (STATUS_COMPLETED, "COMPLETED"),
        (STATUS_UNKNOWN,   "UNKNOWN"),
    ):
        group = [p for p in dashboard["plans"] if p["status"] == canonical]
        if not group:
            continue

        icon   = _STATUS_ICON[canonical]
        colour = _STATUS_COLOUR[canonical]
        lines.append(
            _coloured(f"  {icon} {heading} ({len(group)})", colour, no_colour)
        )
        lines.append(_coloured("  " + "─" * 60, colour, no_colour))

        for p in group:
            # Task + session id
            lines.append(f"  {p['task']}")
            lines.append(
                f"    session  : {p['session_id']}  │  recorded: {p['timestamp']}"
            )

            # Progress counters
            lines.append(
                f"    progress : {p['accomplished_count']} done  "
                f"│  {p['in_progress_count']} in-progress  "
                f"│  {p['next_steps_count']} next"
            )

            # Blockers (only when blocked)
            if p["status"] == STATUS_BLOCKED and p["blockers"]:
                lines.append("    blockers :")
                for q in p["blockers"]:
                    lines.append(f"      • {q}")

            # Next steps (up to 3)
            if p["next_steps"]:
                lines.append("    next     :")
                for step in p["next_steps"][:3]:
                    lines.append(f"      → {step}")
                remaining = len(p["next_steps"]) - 3
                if remaining > 0:
                    lines.append(f"      … +{remaining} more")

            # Artifacts
            if p["artifacts_count"]:
                lines.append(f"    artifacts: {p['artifacts_count']} file(s) modified")

            # Source file
            lines.append(f"    source   : {p['source_file']}")
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_FORMATS = ("table", "json", "yaml")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="harness status",
        description="Show active, completed, and blocked plan status.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--format", "-f",
        choices=_FORMATS,
        default="table",
        metavar="FORMAT",
        help="Output format: table (default), json, yaml.",
    )
    parser.add_argument(
        "--dir", "-d",
        type=Path,
        default=None,
        metavar="DIR",
        help="Directory to scan for plan *.md files (default: .claude/plans).",
    )
    parser.add_argument(
        "--filter",
        default=None,
        metavar="STATUS[,STATUS…]",
        help=(
            "Comma-separated list of statuses to include: "
            "active, completed, blocked, unknown.  Default: all."
        ),
    )
    parser.add_argument(
        "--no-colour", "--no-color",
        action="store_true",
        default=False,
        help="Disable ANSI colour codes in table output.",
    )
    return parser.parse_args(argv)


def _resolve_filter(raw: str | None) -> set[str] | None:
    """Parse --filter value into a set of canonical status strings, or None (= all)."""
    if not raw:
        return None
    requested = {s.strip().lower() for s in raw.split(",")}
    invalid   = requested - set(_ALL_STATUSES)
    if invalid:
        print(
            f"[error] Unknown status(es) in --filter: {', '.join(sorted(invalid))}. "
            f"Valid values: {', '.join(_ALL_STATUSES)}",
            file=sys.stderr,
        )
        sys.exit(1)
    return requested


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    # Determine plans directory
    plans_dir: Path | None = args.dir
    if plans_dir is None:
        candidate = Path(".claude/plans")
        plans_dir = candidate if candidate.is_dir() else None

    # Scan
    records = scan_plans(plans_dir)

    # Apply status filter
    status_filter = _resolve_filter(args.filter)
    if status_filter:
        records = [r for r in records if r["status"] in status_filter]

    # Build dashboard
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    dashboard    = build_dashboard(records, generated_at)

    # Render
    fmt = args.format
    if fmt == "json":
        print(format_json(dashboard))
    elif fmt == "yaml":
        print(format_yaml(dashboard))
    else:
        print(format_table(dashboard, no_colour=args.no_colour))

    # Exit code
    if not records:
        return 2
    if any(r["status"] == STATUS_BLOCKED for r in records):
        return 1
    return 0


# ---------------------------------------------------------------------------
# Demo / smoke-test  (python harness_status.py --demo)
# ---------------------------------------------------------------------------


def _make_demo_files(tmp_dir: Path) -> None:
    """Write three synthetic HandoffDocument markdown files into *tmp_dir*."""
    import textwrap
    from datetime import timedelta

    now = datetime.now(timezone.utc)

    docs = [
        # Active plan
        textwrap.dedent(f"""\
            ---
            session_id: "demo-session-001"
            timestamp: "{(now - timedelta(hours=1)).isoformat()}"
            task: "Implement JWT authentication middleware"
            status: in_progress
            ---

            ## Accomplished
            - Added `UserAuthMiddleware` skeleton
            - Wired middleware into FastAPI app factory

            ## In Progress
            - JWT token validation — ~60% complete

            ## Next Steps
            - Complete token expiry check
            - Add refresh-token endpoint
            - Write integration tests

            ## Search Hints
            ### Key Files
            - src/auth/middleware.py — main middleware class
            - tests/test_auth.py — integration tests

            ### Key Symbols
            - UserAuthMiddleware
            - validate_token

            ## Open Questions

            ## Artifacts
            - src/auth/middleware.py

            ## Notes
        """),
        # Blocked plan
        textwrap.dedent(f"""\
            ---
            session_id: "demo-session-002"
            timestamp: "{(now - timedelta(minutes=30)).isoformat()}"
            task: "Database schema migration to Postgres 16"
            status: blocked
            ---

            ## Accomplished
            - Generated Alembic migration script
            - Tested on staging DB

            ## In Progress
            - Production cut-over

            ## Next Steps
            - Obtain DBA sign-off
            - Schedule maintenance window

            ## Search Hints
            ### Key Files
            - migrations/0042_pg16_upgrade.py

            ## Open Questions
            - DBA approval still pending — blocked on infra team
            - Maintenance window not yet scheduled

            ## Artifacts
            - migrations/0042_pg16_upgrade.py

            ## Notes
            Blocked waiting for infra team response.
        """),
        # Completed plan
        textwrap.dedent(f"""\
            ---
            session_id: "demo-session-003"
            timestamp: "{(now - timedelta(days=1)).isoformat()}"
            task: "Nightly backup verification"
            status: done
            ---

            ## Accomplished
            - All 12 shards verified
            - SHA-256 checksums matched
            - Alert suppression removed

            ## In Progress

            ## Next Steps

            ## Search Hints

            ## Open Questions

            ## Artifacts
            - reports/backup-verify-2026-03-12.txt

            ## Notes
            Completed without issues.
        """),
    ]

    for i, content in enumerate(docs):
        (tmp_dir / f"plan-{i+1:03d}.md").write_text(content, encoding="utf-8")


if __name__ == "__main__":
    import tempfile

    # ── Detect --demo flag manually (before argparse) ────────────────────
    if "--demo" in sys.argv:
        sys.argv.remove("--demo")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _make_demo_files(tmp_path)
            # Inject --dir so the scanner picks up our demo files
            sys.argv += ["--dir", str(tmp_path)]
            sys.exit(main())
    else:
        sys.exit(main())
