#!/usr/bin/env python3
"""
read_handoff.py — Display the latest context handoff for an agent session.

Reads .claude/plan-progress.md (Markdown) and/or .plan_progress.jsonl (JSONL)
and prints the structured summary, search hints, and resume prompt so a new
agent can orient itself before starting work.

Usage
-----
# Print the latest Markdown handoff (default):
    python scripts/read_handoff.py

# Print as JSON (machine-readable):
    python scripts/read_handoff.py --json

# Print only the search hints:
    python scripts/read_handoff.py --hints

# Print only the resume prompt (from JSONL log):
    python scripts/read_handoff.py --resume-prompt

# Read from a different path:
    python scripts/read_handoff.py --md-path .claude/other-progress.md
    python scripts/read_handoff.py --jsonl-path .other_progress.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# Defaults
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_MD_PATH   = ".claude/plan-progress.md"
DEFAULT_JSONL_PATH = ".plan_progress.jsonl"


# ─────────────────────────────────────────────────────────────────────────────
# Markdown reader
# ─────────────────────────────────────────────────────────────────────────────


def _read_markdown(path: Path) -> dict | None:
    """Parse the Markdown handoff file into a dict, or return None."""
    if not path.exists():
        return None

    text = path.read_text(encoding="utf-8")

    # Try to import the full parser from harness_skills if available
    try:
        # Add project root to path so harness_skills is importable
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        from harness_skills.handoff import HandoffDocument
        doc = HandoffDocument.from_markdown(text)
        return {
            "session_id": doc.session_id,
            "timestamp": doc.timestamp,
            "task": doc.task,
            "status": doc.status,
            "accomplished": doc.accomplished,
            "in_progress": doc.in_progress,
            "next_steps": doc.next_steps,
            "search_hints": {
                "file_paths": doc.search_hints.file_paths,
                "directories": doc.search_hints.directories,
                "grep_patterns": doc.search_hints.grep_patterns,
                "symbols": doc.search_hints.symbols,
            },
            "open_questions": doc.open_questions,
            "artifacts": doc.artifacts,
            "notes": doc.notes,
            "_source": "markdown",
        }
    except Exception:
        # Fallback: return raw text
        return {"_raw": text, "_source": "markdown"}


# ─────────────────────────────────────────────────────────────────────────────
# JSONL reader
# ─────────────────────────────────────────────────────────────────────────────


def _read_jsonl_latest(path: Path) -> dict | None:
    """Return the most-recent entry from the JSONL log, or None."""
    if not path.exists():
        return None
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        return None
    entry = json.loads(lines[-1])
    entry["_source"] = "jsonl"
    return entry


# ─────────────────────────────────────────────────────────────────────────────
# Formatters
# ─────────────────────────────────────────────────────────────────────────────


def _fmt_bullets(items: list[str], indent: int = 2) -> str:
    prefix = " " * indent
    return "\n".join(f"{prefix}- {item}" for item in items) if items else f"  (none)"


def _print_summary(entry: dict) -> None:
    """Pretty-print the full handoff summary to stdout."""
    if "_raw" in entry:
        print(entry["_raw"])
        return

    task    = entry.get("task", "")
    status  = entry.get("status", "?")
    ts      = entry.get("timestamp", "")
    sid     = entry.get("session_id", "?")
    summary = entry.get("summary", "")

    print("━" * 60)
    print(f"  CONTEXT HANDOFF  [{status.upper()}]")
    print("━" * 60)
    print(f"  Task      : {task}")
    print(f"  Session   : {sid}")
    print(f"  Timestamp : {ts}")
    if summary:
        print(f"\n  Summary\n  {summary}")

    _section("Accomplished", entry.get("accomplished", []))
    _section("In Progress",  entry.get("in_progress",  []))
    _section("Next Steps",   entry.get("next_steps",   []) or entry.get("pending", []))

    # Search hints
    hints = entry.get("search_hints", {})
    if hints:
        print("\n  Search Hints")
        print("  ─────────────")
        _hint_list("Key Files",        hints.get("file_paths", []) or hints.get("files", []))
        _hint_list("Key Directories",  hints.get("directories", []))
        _hint_list("Grep Patterns",    hints.get("grep_patterns", []))
        _hint_list("Key Symbols",      hints.get("symbols", []))

    _section("Open Questions", entry.get("open_questions", []))
    _section("Artifacts",      entry.get("artifacts",      []))

    notes = entry.get("notes", "")
    if notes:
        print(f"\n  Notes\n  {notes}")

    print("━" * 60)


def _section(title: str, items: list[str]) -> None:
    if not items:
        return
    print(f"\n  {title}")
    for item in items:
        print(f"    - {item}")


def _hint_list(label: str, items: list[str]) -> None:
    if not items:
        return
    print(f"\n    {label}:")
    for item in items:
        print(f"      {item}")


def _print_hints_only(entry: dict) -> None:
    """Print only the search hints block."""
    if "_raw" in entry:
        print(entry["_raw"])
        return

    hints = entry.get("search_hints", {})
    if not hints:
        print("(no search hints in handoff)")
        return

    files   = hints.get("file_paths", []) or hints.get("files", [])
    dirs    = hints.get("directories", [])
    patterns = hints.get("grep_patterns", [])
    symbols  = hints.get("symbols", [])

    if files:
        print("# Key Files (Read these first)")
        for f in files:
            print(f"  {f}")
    if dirs:
        print("\n# Key Directories (Glob to explore)")
        for d in dirs:
            print(f"  {d}")
    if patterns:
        print("\n# Grep Patterns")
        for p in patterns:
            print(f"  {p}")
    if symbols:
        print("\n# Key Symbols (Grep for these)")
        for s in symbols:
            print(f"  {s}")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="read_handoff",
        description="Display the latest context handoff for a new agent session.",
    )
    p.add_argument(
        "--md-path",
        default=DEFAULT_MD_PATH,
        help=f"Path to the Markdown handoff file (default: {DEFAULT_MD_PATH})",
    )
    p.add_argument(
        "--jsonl-path",
        default=DEFAULT_JSONL_PATH,
        help=f"Path to the JSONL progress log (default: {DEFAULT_JSONL_PATH})",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON (machine-readable)",
    )
    p.add_argument(
        "--hints",
        action="store_true",
        help="Print only the search hints block",
    )
    p.add_argument(
        "--resume-prompt",
        action="store_true",
        help="Print only the resume_prompt field (from JSONL log)",
    )
    p.add_argument(
        "--prefer",
        choices=["md", "jsonl"],
        default="md",
        help="Which source to prefer when both exist (default: md)",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    md_path   = Path(args.md_path)
    jsonl_path = Path(args.jsonl_path)

    # Determine entry to display
    entry: dict | None = None

    if args.resume_prompt:
        # resume_prompt only lives in JSONL
        entry = _read_jsonl_latest(jsonl_path)
        if not entry:
            print("(no JSONL handoff found)", file=sys.stderr)
            sys.exit(1)
        print(entry.get("resume_prompt", "(no resume_prompt in latest entry)"))
        return

    if args.prefer == "md":
        entry = _read_markdown(md_path) or _read_jsonl_latest(jsonl_path)
    else:
        entry = _read_jsonl_latest(jsonl_path) or _read_markdown(md_path)

    if not entry:
        print(
            f"No handoff found.\n"
            f"  Markdown : {md_path} — {'exists' if md_path.exists() else 'missing'}\n"
            f"  JSONL    : {jsonl_path} — {'exists' if jsonl_path.exists() else 'missing'}",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.json:
        print(json.dumps(entry, indent=2, ensure_ascii=False))
    elif args.hints:
        _print_hints_only(entry)
    else:
        _print_summary(entry)


if __name__ == "__main__":
    main()
