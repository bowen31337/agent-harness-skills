"""
harness_skills.resume - Load and present the most recent plan state for context handoff.

This module is the programmatic backend for the harness:resume skill. It reads
the canonical plan-progress sources, formats the state into a concise context
block, and optionally injects that block into a new Agent SDK session so the
resuming agent can orient itself immediately.

Architecture:
    .claude/plan-progress.md  (primary, Markdown, latest-wins)
    .plan_progress.jsonl       (fallback, JSONL, append-only log)
         |
         v  load_plan_state()
    PlanState
         |
         v  format_resume_context() / build_resume_prompt()
    Agent system prompt addendum  ->  resume_agent_options()

Quick start - CLI:
    python -m harness_skills.resume
    python -m harness_skills.resume --hints
    python -m harness_skills.resume --json

Quick start - Programmatic:
    from harness_skills.resume import load_plan_state, resume_agent_options
    from claude_agent_sdk import ClaudeAgentOptions

    state = load_plan_state()
    options, state = resume_agent_options(ClaudeAgentOptions(...), state=state)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_DEFAULT_MD_PATH = Path(".claude/plan-progress.md")
_DEFAULT_JSONL_PATH = Path(".plan_progress.jsonl")


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

    Fields map 1-to-1 with the handoff format written by the context-handoff
    skill. ``source`` records which backing store was used:
    ``"markdown"`` | ``"jsonl"`` | ``"none"``.
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
    source: str = "none"
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


def _load_from_markdown(path: Path) -> PlanState | None:
    """Parse .claude/plan-progress.md into a PlanState, or return None."""
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    try:
        from harness_skills.handoff import HandoffDocument
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
    except Exception:
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

    Tries the preferred source first, falls back to the other.
    Returns ``PlanState(source="none")`` when neither file exists.

    Parameters
    ----------
    md_path:
        Path to the Markdown handoff file (default: ``.claude/plan-progress.md``).
    jsonl_path:
        Path to the JSONL progress log (default: ``.plan_progress.jsonl``).
    prefer:
        Which source to try first -- ``"md"`` (default) or ``"jsonl"``.
    """
    if prefer == "jsonl":
        state = _load_from_jsonl(jsonl_path) or _load_from_markdown(md_path)
    else:
        state = _load_from_markdown(md_path) or _load_from_jsonl(jsonl_path)
    return state or PlanState(source="none")


def format_resume_context(state: PlanState) -> str:
    """Render state as a human-readable context block."""
    if not state.found():
        return (
            "(no plan state found -- "
            ".claude/plan-progress.md and .plan_progress.jsonl are both missing)"
        )
    if state._raw:
        return state._raw

    lines: list[str] = [
        "=" * 62,
        "  PLAN STATE  [" + state.status.upper() + "]",
        "=" * 62,
        "  Task      : " + state.task,
        "  Session   : " + state.session_id,
        "  Timestamp : " + state.timestamp,
        "  Source    : " + state.source,
    ]

    def section(title: str, items: list[str]) -> None:
        if not items:
            return
        lines.append("\n  " + title)
        for item in items:
            lines.append("    - " + item)

    section("Accomplished", state.accomplished)
    section("In Progress", state.in_progress)
    section("Next Steps", state.next_steps)

    hints = state.search_hints
    if not hints.is_empty():
        lines.append("\n  Search Hints")
        lines.append("  " + "-" * 30)
        if hints.file_paths:
            lines.append("\n    Key Files (read these first):")
            for f in hints.file_paths:
                lines.append("      " + f)
        if hints.directories:
            lines.append("\n    Key Directories (glob to explore):")
            for d in hints.directories:
                lines.append("      " + d)
        if hints.grep_patterns:
            lines.append("\n    Grep Patterns:")
            for p in hints.grep_patterns:
                lines.append("      " + p)
        if hints.symbols:
            lines.append("\n    Key Symbols:")
            for s in hints.symbols:
                lines.append("      " + s)

    section("Open Questions", state.open_questions)
    section("Artifacts", state.artifacts)

    if state.notes:
        lines.append("\n  Notes\n  " + state.notes)

    lines.append("=" * 62)
    return "\n".join(lines)


def format_hints_only(state: PlanState) -> str:
    """Return a compact string listing only the search hints."""
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
        parts.extend("  " + f for f in hints.file_paths)
    if hints.directories:
        parts.append("\n# Key Directories (Glob to explore)")
        parts.extend("  " + d for d in hints.directories)
    if hints.grep_patterns:
        parts.append("\n# Grep Patterns")
        parts.extend("  " + p for p in hints.grep_patterns)
    if hints.symbols:
        parts.append("\n# Key Symbols (Grep for these)")
        parts.extend("  " + s for s in hints.symbols)
    return "\n".join(parts)


_RESUME_PREAMBLE = (
    "---------------------------------------------------------\n"
    "RESUMING FROM SAVED PLAN STATE\n"
    "---------------------------------------------------------\n"
    "Task   : {task}\n"
    "Status : {status}\n"
    "Saved  : {timestamp}\n"
    "\n"
    "{context_block}\n"
    "---------------------------------------------------------\n"
    "CONTEXT REBUILD INSTRUCTIONS\n"
    "---------------------------------------------------------\n"
    "The descriptions above may be stale -- always verify with your own tools:\n"
    "\n"
    "1. Read each file listed under 'Key Files' using the Read tool.\n"
    "2. Run each 'Grep Pattern' with the Grep tool.\n"
    "3. Glob each 'Key Directory' to confirm current structure.\n"
    "4. Search for each 'Key Symbol' with Grep.\n"
    "5. Continue from 'Next Steps' unless your search reveals a reason to change course.\n"
    "6. When your session ends, overwrite .claude/plan-progress.md with a fresh handoff.\n"
    "---------------------------------------------------------\n"
)


def build_resume_prompt(state: PlanState) -> str:
    """
    Build the system-prompt addendum that orients a resuming agent.

    Returns an empty string when no plan state is available.
    """
    if not state.found():
        return ""
    context_block = format_resume_context(state)
    return _RESUME_PREAMBLE.format(
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
    Inject the most-recent plan state into base_options system prompt.

    If state is provided it is used directly; otherwise load_plan_state is
    called. Returns (augmented_options, plan_state). When no plan state exists,
    base_options is returned unchanged with PlanState(source="none").
    """
    if state is None:
        state = load_plan_state(md_path=md_path, jsonl_path=jsonl_path, prefer=prefer)
    if not state.found():
        return base_options, state
    addendum = build_resume_prompt(state)
    existing = getattr(base_options, "system_prompt", None) or ""
    base_options.system_prompt = (addendum + "\n\n" + existing).strip()
    return base_options, state


def _build_cli() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m harness_skills.resume",
        description="Display the most recent plan state for agent context handoff.",
    )
    p.add_argument("--md-path", default=str(_DEFAULT_MD_PATH),
                   help="Markdown handoff file (default: .claude/plan-progress.md)")
    p.add_argument("--jsonl-path", default=str(_DEFAULT_JSONL_PATH),
                   help="JSONL progress log (default: .plan_progress.jsonl)")
    p.add_argument("--prefer", choices=["md", "jsonl"], default="md",
                   help="Source to prefer when both exist (default: md)")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.add_argument("--hints", action="store_true", help="Print only search hints")
    return p


def main(argv: list[str] | None = None) -> None:
    args = _build_cli().parse_args(argv)
    state = load_plan_state(
        md_path=Path(args.md_path),
        jsonl_path=Path(args.jsonl_path),
        prefer=args.prefer,
    )
    if not state.found():
        md_exists = "exists" if Path(args.md_path).exists() else "missing"
        jsonl_exists = "exists" if Path(args.jsonl_path).exists() else "missing"
        print(
            "No plan state found.\n"
            "  Markdown : " + args.md_path + " -- " + md_exists + "\n"
            "  JSONL    : " + args.jsonl_path + " -- " + jsonl_exists,
            file=sys.stderr,
        )
        sys.exit(1)
    if args.json:
        print(json.dumps(state.to_dict(), indent=2, ensure_ascii=False))
    elif args.hints:
        print(format_hints_only(state))
    else:
        print(format_resume_context(state))


if __name__ == "__main__":
    main()
