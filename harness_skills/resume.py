"""
harness_skills.resume — Load and present the most recent plan state for context handoff.

This module is the programmatic backend for the ``harness:resume`` skill.  It
reads the canonical plan-progress sources, formats the state into a concise
context block, and optionally injects that block into a new Agent SDK session
so the resuming agent can orient itself immediately.

Architecture
------------
    ┌──────────────────────────────────┐
    │  .claude/plan-progress.md        │  ← primary (Markdown, latest-wins)
    │  .plan_progress.jsonl            │  ← fallback (JSONL, append-only log)
    └────────────┬─────────────────────┘
                 │  load_plan_state()
    ┌────────────▼─────────────────────┐
    │  PlanState                        │  ← structured representation
    └────────────┬─────────────────────┘
                 │  format_resume_context() / build_resume_prompt()
    ┌────────────▼─────────────────────┐
    │  Agent system prompt addendum     │  → injected via resume_agent_options()
    └──────────────────────────────────┘

Quick start
-----------
CLI:
    python -m harness_skills.resume
    python -m harness_skills.resume --hints
    python -m harness_skills.resume --json
    python -m harness_skills.resume --output-format json
    python -m harness_skills.resume --verbosity verbose

Programmatic:
    from harness_skills.resume import load_plan_state, resume_agent_options
    from claude_agent_sdk import ClaudeAgentOptions

    state   = load_plan_state()
    options = resume_agent_options(ClaudeAgentOptions(...), state=state)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_MD_PATH    = Path(".claude/plan-progress.md")
_DEFAULT_JSONL_PATH = Path(".plan_progress.jsonl")

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class SearchHints:
    """File/symbol pointers the resuming agent uses with its own tools."""

    file_paths: list[str] = field(default_factory=list)
    directories: list[str] = field(default_factory=list)
    grep_patterns: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not any([self.file_paths, self.directories, self.grep_patterns, self.symbols])


@dataclass
class PlanState:
    """
    Structured snapshot of the plan's most-recent saved state.

    Fields map 1-to-1 with the handoff format written by the
    ``context-handoff`` skill.  ``source`` records which backing store was
    used (``"markdown"`` | ``"jsonl"`` | ``"none"``).
    """

    task: str = ""
    status: str = "in_progress"
    session_id: str = "unknown"
    timestamp: str = ""
    accomplished: list[str] = field(default_factory=list)
    in_progress: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    search_hints: SearchHints = field(default_factory=SearchHints)
    open_questions: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    notes: str = ""
    source: str = "none"  # "markdown" | "jsonl" | "none"

    # raw markdown or JSONL line for pass-through when parsing fails
    _raw: str = field(default="", repr=False)

    def found(self) -> bool:
        """Return True when actual plan state was loaded from disk."""
        return self.source != "none"

    def to_dict(self) -> dict:
        return {
            "task": self.task,
            "status": self.status,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "accomplished": self.accomplished,
            "in_progress": self.in_progress,
            "next_steps": self.next_steps,
            "search_hints": {
                "file_paths": self.search_hints.file_paths,
                "directories": self.search_hints.directories,
                "grep_patterns": self.search_hints.grep_patterns,
                "symbols": self.search_hints.symbols,
            },
            "open_questions": self.open_questions,
            "artifacts": self.artifacts,
            "notes": self.notes,
            "source": self.source,
        }


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _load_from_markdown(path: Path) -> PlanState | None:
    """Parse ``.claude/plan-progress.md`` into a PlanState, or return None."""
    if not path.exists():
        return None

    text = path.read_text(encoding="utf-8")

    # Attempt full parse via handoff module (preferred)
    try:
        from harness_skills.handoff import HandoffDocument  # noqa: PLC0415

        doc = HandoffDocument.from_markdown(text)
        return PlanState(
            task=doc.task,
            status=doc.status,
            session_id=doc.session_id,
            timestamp=doc.timestamp,
            accomplished=doc.accomplished,
            in_progress=doc.in_progress,
            next_steps=doc.next_steps,
            search_hints=SearchHints(
                file_paths=doc.search_hints.file_paths,
                directories=doc.search_hints.directories,
                grep_patterns=doc.search_hints.grep_patterns,
                symbols=doc.search_hints.symbols,
            ),
            open_questions=doc.open_questions,
            artifacts=doc.artifacts,
            notes=doc.notes,
            source="markdown",
        )
    except Exception:  # noqa: BLE001
        # Fallback: return raw text without structured parse
        return PlanState(source="markdown", _raw=text)


def _load_from_jsonl(path: Path) -> PlanState | None:
    """Return a PlanState from the most-recent JSONL entry, or None."""
    if not path.exists():
        return None
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        return None

    try:
        entry = json.loads(lines[-1])
    except json.JSONDecodeError:
        return None

    hints_raw = entry.get("search_hints", {})
    hints = SearchHints(
        file_paths=hints_raw.get("file_paths", hints_raw.get("files", [])),
        directories=hints_raw.get("directories", []),
        grep_patterns=hints_raw.get("grep_patterns", []),
        symbols=hints_raw.get("symbols", []),
    )
    return PlanState(
        task=entry.get("task", ""),
        status=entry.get("status", "in_progress"),
        session_id=entry.get("session_id", "unknown"),
        timestamp=entry.get("timestamp", ""),
        accomplished=entry.get("accomplished", []),
        in_progress=entry.get("in_progress", []),
        next_steps=entry.get("next_steps", entry.get("pending", [])),
        search_hints=hints,
        open_questions=entry.get("open_questions", []),
        artifacts=entry.get("artifacts", []),
        notes=entry.get("notes", ""),
        source="jsonl",
    )


def load_plan_state(
    md_path: Path = _DEFAULT_MD_PATH,
    jsonl_path: Path = _DEFAULT_JSONL_PATH,
    prefer: str = "md",
) -> PlanState:
    """
    Load the most recent plan state from disk.

    Preference order is controlled by *prefer* (``"md"`` or ``"jsonl"``).
    Falls back to the other source if the preferred one is missing.
    Returns an empty ``PlanState(source="none")`` when neither file exists.

    Parameters
    ----------
    md_path:
        Path to the Markdown handoff file (default: ``.claude/plan-progress.md``).
    jsonl_path:
        Path to the JSONL progress log (default: ``.plan_progress.jsonl``).
    prefer:
        Which source to try first — ``"md"`` (default) or ``"jsonl"``.
    """
    if prefer == "jsonl":
        state = _load_from_jsonl(jsonl_path) or _load_from_markdown(md_path)
    else:
        state = _load_from_markdown(md_path) or _load_from_jsonl(jsonl_path)

    return state or PlanState(source="none")


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


def _bullets(items: list[str], indent: int = 2) -> str:
    prefix = " " * indent
    return "\n".join(f"{prefix}- {item}" for item in items) if items else f"{' ' * indent}(none)"


def format_resume_context(state: PlanState) -> str:
    """
    Render *state* as a human-readable context block suitable for printing or
    injecting into an agent system prompt.

    Returns a minimal ``(no plan state found)`` message when ``state.source``
    is ``"none"``.
    """
    if not state.found():
        return "(no plan state found — .claude/plan-progress.md and .plan_progress.jsonl are both missing)"

    if state._raw:
        return state._raw

    lines: list[str] = [
        "━" * 62,
        f"  PLAN STATE  [{state.status.upper()}]",
        "━" * 62,
        f"  Task      : {state.task}",
        f"  Session   : {state.session_id}",
        f"  Timestamp : {state.timestamp}",
        f"  Source    : {state.source}",
    ]

    def section(title: str, items: list[str]) -> None:
        if not items:
            return
        lines.append(f"\n  {title}")
        for item in items:
            lines.append(f"    - {item}")

    section("Accomplished", state.accomplished)
    section("In Progress", state.in_progress)
    section("Next Steps", state.next_steps)

    hints = state.search_hints
    if not hints.is_empty():
        lines.append("\n  Search Hints")
        lines.append("  " + "─" * 30)
        if hints.file_paths:
            lines.append("\n    Key Files (read these first):")
            for f in hints.file_paths:
                lines.append(f"      {f}")
        if hints.directories:
            lines.append("\n    Key Directories (glob to explore):")
            for d in hints.directories:
                lines.append(f"      {d}")
        if hints.grep_patterns:
            lines.append("\n    Grep Patterns:")
            for p in hints.grep_patterns:
                lines.append(f"      {p}")
        if hints.symbols:
            lines.append("\n    Key Symbols:")
            for s in hints.symbols:
                lines.append(f"      {s}")

    section("Open Questions", state.open_questions)
    section("Artifacts", state.artifacts)

    if state.notes:
        lines.append(f"\n  Notes\n  {state.notes}")

    lines.append("━" * 62)
    return "\n".join(lines)


def format_hints_only(state: PlanState) -> str:
    """
    Return a compact string listing only the search hints from *state*.

    Useful for quick orientation without the full context block.
    """
    if not state.found():
        return "(no plan state found)"

    if state._raw:
        return state._raw

    hints = state.search_hints
    if hints.is_empty():
        return "(no search hints recorded in plan state)"

    parts: list[str] = []
    if hints.file_paths:
        parts.append("# Key Files (Read these first)")
        parts.extend(f"  {f}" for f in hints.file_paths)
    if hints.directories:
        parts.append("\n# Key Directories (Glob to explore)")
        parts.extend(f"  {d}" for d in hints.directories)
    if hints.grep_patterns:
        parts.append("\n# Grep Patterns")
        parts.extend(f"  {p}" for p in hints.grep_patterns)
    if hints.symbols:
        parts.append("\n# Key Symbols (Grep for these)")
        parts.extend(f"  {s}" for s in hints.symbols)

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Agent SDK integration
# ---------------------------------------------------------------------------

_RESUME_PREAMBLE_TEMPLATE = """\
─────────────────────────────────────────────────────────
RESUMING FROM SAVED PLAN STATE
─────────────────────────────────────────────────────────
Task   : {task}
Status : {status}
Saved  : {timestamp}

{context_block}
─────────────────────────────────────────────────────────
CONTEXT REBUILD INSTRUCTIONS
─────────────────────────────────────────────────────────
The descriptions above may be stale — always verify with your own tools:

1. Read each file listed under "Key Files" using the Read tool.
2. Run each "Grep Pattern" with the Grep tool.
3. Glob each "Key Directory" to confirm current structure.
4. Search for each "Key Symbol" with Grep.
5. Continue from "Next Steps" unless your search reveals a reason to change course.
6. When your session ends, overwrite .claude/plan-progress.md with a fresh handoff.
─────────────────────────────────────────────────────────
"""


def build_resume_prompt(state: PlanState) -> str:
    """
    Build the system-prompt addendum that orients a resuming agent.

    Returns an empty string when no plan state is available (so callers can
    safely concatenate without adding noise).
    """
    if not state.found():
        return ""

    context_block = format_resume_context(state)
    return _RESUME_PREAMBLE_TEMPLATE.format(
        task=state.task or "(unknown task)",
        status=state.status,
        timestamp=state.timestamp or "(unknown)",
        context_block=context_block,
    )


def resume_agent_options(
    base_options: Any,
    *,
    state: PlanState | None = None,
    md_path: Path = _DEFAULT_MD_PATH,
    jsonl_path: Path = _DEFAULT_JSONL_PATH,
    prefer: str = "md",
) -> tuple[Any, PlanState]:
    """
    Inject the most-recent plan state into *base_options* system prompt.

    If *state* is provided it is used directly; otherwise ``load_plan_state``
    is called with *md_path*, *jsonl_path*, and *prefer*.

    Returns ``(augmented_options, plan_state)``.  When no plan state exists,
    ``base_options`` is returned unchanged alongside a ``PlanState(source="none")``.

    Parameters
    ----------
    base_options:
        A ``ClaudeAgentOptions`` instance (or any object with a ``system_prompt``
        string attribute).
    state:
        Pre-loaded ``PlanState``.  When None, the state is loaded from disk.
    md_path:
        Override for the Markdown source path.
    jsonl_path:
        Override for the JSONL source path.
    prefer:
        Source preference when loading from disk (``"md"`` or ``"jsonl"``).
    """
    if state is None:
        state = load_plan_state(md_path=md_path, jsonl_path=jsonl_path, prefer=prefer)

    if not state.found():
        return base_options, state

    addendum = build_resume_prompt(state)
    existing = getattr(base_options, "system_prompt", None) or ""
    base_options.system_prompt = f"{addendum}\n\n{existing}".strip()

    return base_options, state


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_cli() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m harness_skills.resume",
        description="Display the most recent plan state for agent context handoff.",
    )
    p.add_argument(
        "--md-path",
        default=str(_DEFAULT_MD_PATH),
        help=f"Markdown handoff file (default: {_DEFAULT_MD_PATH})",
    )
    p.add_argument(
        "--jsonl-path",
        default=str(_DEFAULT_JSONL_PATH),
        help=f"JSONL progress log (default: {_DEFAULT_JSONL_PATH})",
    )
    p.add_argument(
        "--prefer",
        choices=["md", "jsonl"],
        default="md",
        help="Source to prefer when both exist (default: md)",
    )
    p.add_argument(
        "--output-format",
        dest="output_format",
        choices=["json", "yaml", "table"],
        default=None,
        metavar="FORMAT",
        help=(
            "Output format: json, yaml, or table.  "
            "Defaults to 'table' when stdout is a TTY, 'json' otherwise."
        ),
    )
    # --json kept for backward compatibility; equivalent to --output-format json
    p.add_argument("--json", action="store_true", help="Output as JSON (shorthand for --output-format json)")
    p.add_argument("--hints", action="store_true", help="Print only the search hints block")
    p.add_argument(
        "--verbosity",
        choices=["quiet", "normal", "verbose", "debug"],
        default="normal",
        help="Control output detail level (default: normal)",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    from harness_skills.cli.fmt import resolve_output_format
    from harness_skills.cli.verbosity import VerbosityLevel, vecho

    args = _build_cli().parse_args(argv)
    verbosity: str = args.verbosity

    state = load_plan_state(
        md_path=Path(args.md_path),
        jsonl_path=Path(args.jsonl_path),
        prefer=args.prefer,
    )

    if not state.found():
        vecho(
            f"No plan state found.\n"
            f"  Markdown : {args.md_path} — "
            f"{'exists' if Path(args.md_path).exists() else 'missing'}\n"
            f"  JSONL    : {args.jsonl_path} — "
            f"{'exists' if Path(args.jsonl_path).exists() else 'missing'}",
            verbosity=verbosity,
            min_level=VerbosityLevel.quiet,
            err=True,
        )
        sys.exit(1)

    # Resolve effective output format: --json flag takes precedence over --output-format
    effective_format = resolve_output_format("json" if args.json else args.output_format)

    if args.hints:
        print(format_hints_only(state))
    elif effective_format == "json":
        print(json.dumps(state.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(format_resume_context(state))


if __name__ == "__main__":
    main()
