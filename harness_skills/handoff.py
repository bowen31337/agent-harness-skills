"""
Context Handoff Protocol for Claude Agent SDK sessions.

When an agent session ends, it writes a structured handoff to the plan progress
log (.claude/plan-progress.md). The handoff includes search hints — file paths,
grep patterns, and symbol names — so the *next* agent can rebuild context using
its own Read/Grep/Glob tools rather than relying on pre-assembled context dumps.

Architecture
------------
                 ┌─────────────────────────┐
  Session A  →   │  ending agent runs task  │
                 │  writes handoff via Write │
                 └──────────┬──────────────┘
                            │  .claude/plan-progress.md
                 ┌──────────▼──────────────┐
  Session B  →   │  HandoffProtocol reads   │
                 │  handoff, injects search  │
                 │  hints into system prompt │
                 │  agent rebuilds context   │
                 │  with its own tools       │
                 └─────────────────────────┘

Usage
-----
Ending session:
    options = HandoffProtocol.ending_agent_options(
        base_options=ClaudeAgentOptions(allowed_tools=["Read", "Write", "Glob", "Grep"]),
        task="Implement JWT authentication",
    )
    async for msg in query(prompt="...", options=options): ...

Resuming session:
    options = await HandoffProtocol.resuming_agent_options(
        base_options=ClaudeAgentOptions(allowed_tools=["Read", "Glob", "Grep"]),
    )
    async for msg in query(prompt="Continue from handoff", options=options): ...
"""

from __future__ import annotations

import re
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class SearchHints(BaseModel):
    """
    Pointers the next agent uses with its own tools — not pre-assembled dumps.

    The principle: tell the next agent *where* to look, not *what* is there.
    It verifies for itself, so its view of the code is always fresh.
    """

    file_paths: list[str] = Field(
        default_factory=list,
        description="Files most relevant to the task, relative to cwd.",
    )
    grep_patterns: list[str] = Field(
        default_factory=list,
        description="Regex patterns to find key code (class names, function sigs, TODOs…).",
    )
    symbols: list[str] = Field(
        default_factory=list,
        description="Function / class / variable names worth searching for.",
    )
    directories: list[str] = Field(
        default_factory=list,
        description="Directories to explore first when rebuilding context.",
    )


class HandoffDocument(BaseModel):
    """Structured summary written by an ending agent for the next agent."""

    session_id: str = Field(description="Source session ID (from SystemMessage.session_id).")
    timestamp: str = Field(description="ISO-8601 UTC timestamp.")
    task: str = Field(description="High-level description of the overall task.")
    status: str = Field(
        default="in_progress",
        description="One of: in_progress | blocked | done.",
    )

    accomplished: list[str] = Field(
        default_factory=list,
        description="Bullet points: what was completed in this session.",
    )
    in_progress: list[str] = Field(
        default_factory=list,
        description="Work partially done — include % complete and what remains.",
    )
    next_steps: list[str] = Field(
        default_factory=list,
        description="Ordered actions for the next agent to take.",
    )

    search_hints: SearchHints = Field(default_factory=SearchHints)

    open_questions: list[str] = Field(
        default_factory=list,
        description="Unresolved decisions or blockers the next agent must address.",
    )
    artifacts: list[str] = Field(
        default_factory=list,
        description="Files created or significantly modified in this session.",
    )
    notes: str = Field(
        default="",
        description="Free-form context that doesn't fit the structured fields.",
    )

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_markdown(self) -> str:
        """Render as YAML-frontmatter + human-readable Markdown."""
        frontmatter: dict[str, Any] = {
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "task": self.task,
            "status": self.status,
        }
        fm = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True).strip()

        def bullets(items: list[str], indent: int = 0) -> str:
            prefix = " " * indent
            return "\n".join(f"{prefix}- {item}" for item in items) if items else f"{prefix}*(none)*"

        hints = self.search_hints
        hint_sections: list[str] = []

        if hints.file_paths:
            hint_sections.append("### Key Files\n" + bullets(hints.file_paths))
        if hints.directories:
            hint_sections.append("### Key Directories\n" + bullets(hints.directories))
        if hints.grep_patterns:
            block = "\n".join(f"  {p}" for p in hints.grep_patterns)
            hint_sections.append(f"### Grep Patterns\n```\n{block}\n```")
        if hints.symbols:
            hint_sections.append("### Key Symbols\n" + bullets(hints.symbols))

        hints_body = "\n\n".join(hint_sections) if hint_sections else "*(no hints recorded)*"

        # Build with explicit joins rather than textwrap.dedent: multi-line YAML
        # injected via f-string breaks dedent's common-whitespace detection when
        # the YAML keys start at column-0 while the template is indented.
        parts = [
            "---",
            fm,
            "---",
            "",
            "## Accomplished",
            bullets(self.accomplished),
            "",
            "## In Progress",
            bullets(self.in_progress),
            "",
            "## Next Steps",
            bullets(self.next_steps),
            "",
            "## Search Hints",
            hints_body,
            "",
            "## Open Questions",
            bullets(self.open_questions),
            "",
            "## Artifacts",
            bullets(self.artifacts),
            "",
            "## Notes",
            self.notes or "*(none)*",
            "",
        ]
        return "\n".join(parts)

    @classmethod
    def from_markdown(cls, text: str) -> "HandoffDocument":
        """Parse a previously-written handoff Markdown file."""
        # Extract YAML frontmatter
        fm_match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
        if not fm_match:
            raise ValueError("Handoff file is missing YAML frontmatter.")
        fm = yaml.safe_load(fm_match.group(1))

        def parse_section(header: str) -> list[str]:
            pattern = rf"## {re.escape(header)}\n(.*?)(?=\n## |\Z)"
            m = re.search(pattern, text, re.DOTALL)
            if not m:
                return []
            block = m.group(1).strip()
            if block in ("*(none)*", ""):
                return []
            lines = [ln.lstrip("- ").strip() for ln in block.splitlines() if ln.strip().startswith("-")]
            return [ln for ln in lines if ln]

        def parse_notes() -> str:
            m = re.search(r"## Notes\n(.*?)(?=\n## |\Z)", text, re.DOTALL)
            if not m:
                return ""
            body = m.group(1).strip()
            return "" if body == "*(none)*" else body

        # Parse search hints
        hints_m = re.search(r"## Search Hints\n(.*?)(?=\n## |\Z)", text, re.DOTALL)
        hints_text = hints_m.group(1) if hints_m else ""

        def parse_hint_list(section: str) -> list[str]:
            m = re.search(rf"### {re.escape(section)}\n(.*?)(?=\n### |\Z)", hints_text, re.DOTALL)
            if not m:
                return []
            block = m.group(1).strip()
            if "```" in block:
                block = re.sub(r"```[^\n]*\n?", "", block).strip()
            lines = [
                ln.lstrip("- ").strip() if ln.lstrip().startswith("-") else ln.strip()
                for ln in block.splitlines()
                if ln.strip() and not ln.strip().startswith("*(")
            ]
            return [ln for ln in lines if ln]

        hints = SearchHints(
            file_paths=parse_hint_list("Key Files"),
            directories=parse_hint_list("Key Directories"),
            grep_patterns=parse_hint_list("Grep Patterns"),
            symbols=parse_hint_list("Key Symbols"),
        )

        return cls(
            session_id=fm.get("session_id", "unknown"),
            timestamp=fm.get("timestamp", ""),
            task=fm.get("task", ""),
            status=fm.get("status", "in_progress"),
            accomplished=parse_section("Accomplished"),
            in_progress=parse_section("In Progress"),
            next_steps=parse_section("Next Steps"),
            search_hints=hints,
            open_questions=parse_section("Open Questions"),
            artifacts=parse_section("Artifacts"),
            notes=parse_notes(),
        )


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

_DEFAULT_HANDOFF_PATH = Path(".claude/plan-progress.md")

#: System-prompt addendum injected into the *ending* agent.
_ENDING_AGENT_INSTRUCTIONS = """\
─────────────────────────────────────────────────────────
HANDOFF PROTOCOL — REQUIRED BEFORE YOU STOP
─────────────────────────────────────────────────────────
Before you finish, you MUST write a structured handoff document so the next
agent can pick up exactly where you left off.

Write the handoff to: {handoff_path}

The file must use this exact format (YAML frontmatter + Markdown):

---
session_id: "<your session id if known, else 'unknown'>"
timestamp: "<UTC timestamp, e.g. 2026-03-13T10:30:00Z>"
task: "<one-line description of the overall task>"
status: "<in_progress | blocked | done>"
---

## Accomplished
- <bullet: what you completed>

## In Progress
- <bullet: partially-done work — include what's left and ~% complete>

## Next Steps
- <ordered action items for the next agent>

## Search Hints
### Key Files
- <relative/path/to/file.py>  — <one-line: why it matters>

### Key Directories
- <src/module/>  — <one-line: what lives here>

### Grep Patterns
```
class MyClass
def authenticate
TODO.*payment
```

### Key Symbols
- MyClass
- authenticate_user
- PAYMENT_TIMEOUT

## Open Questions
- <unresolved decisions or blockers>

## Artifacts
- <files you created or significantly modified>

## Notes
<free-form context that doesn't fit above>
─────────────────────────────────────────────────────────
SEARCH HINTS PHILOSOPHY: Provide search hints, NOT content dumps.
The next agent will use its own Read/Grep/Glob tools to verify code for
itself — give it the *map*, not the *territory*. A good hint tells the
agent: "look in src/auth/middleware.py for class UserAuthMiddleware" — and
the agent then reads the actual current code rather than a stale copy.
─────────────────────────────────────────────────────────
"""

#: System-prompt addendum injected into the *resuming* agent.
_RESUMING_AGENT_PREAMBLE = """\
─────────────────────────────────────────────────────────
CONTEXT HANDOFF FROM PREVIOUS SESSION
─────────────────────────────────────────────────────────
Task   : {task}
Status : {status}
Written: {timestamp}

{handoff_body}
─────────────────────────────────────────────────────────
CONTEXT REBUILD INSTRUCTIONS
─────────────────────────────────────────────────────────
Use your own tools to verify the above — do NOT trust stale descriptions:

1. Key files to read first:
{file_hints}

2. Grep patterns to run:
{grep_hints}

3. Key symbols to search for:
{symbol_hints}

4. Continue from "Next Steps" unless you discover a reason to change course.
5. When your session ends, overwrite the handoff file with a fresh summary.
─────────────────────────────────────────────────────────
"""


class HandoffProtocol:
    """
    Attaches context-handoff behaviour to Agent SDK sessions.

    The protocol is intentionally *thin* — it adds only a system-prompt
    addendum (for ending agents) or reads a file and injects search hints
    (for resuming agents). All actual context-building is done by the agent
    with its own tools at runtime.
    """

    def __init__(self, handoff_path: Path = _DEFAULT_HANDOFF_PATH) -> None:
        self.handoff_path = handoff_path

    # ------------------------------------------------------------------
    # Ending-session helpers
    # ------------------------------------------------------------------

    def ending_system_prompt_addendum(self, task: str = "") -> str:
        """Return the instruction block to append to an ending agent's system prompt."""
        instructions = _ENDING_AGENT_INSTRUCTIONS.format(handoff_path=str(self.handoff_path))
        if task:
            task_line = f"\nCurrent task context: {task}\n"
            instructions = task_line + instructions
        return instructions

    def ending_agent_options(
        self,
        base_options: Any,
        task: str = "",
    ) -> Any:
        """
        Return a copy of *base_options* augmented with handoff-writing instructions.

        Requires the agent to have at least the ``Write`` built-in tool available.
        ``base_options`` must be a ``ClaudeAgentOptions`` instance.
        """
        addendum = self.ending_system_prompt_addendum(task=task)
        existing = getattr(base_options, "system_prompt", None) or ""
        base_options.system_prompt = f"{existing}\n\n{addendum}".strip()

        # Ensure Write tool is allowed
        allowed: list[str] = list(getattr(base_options, "allowed_tools", None) or [])
        if "Write" not in allowed:
            allowed.append("Write")
        base_options.allowed_tools = allowed

        return base_options

    # ------------------------------------------------------------------
    # Resuming-session helpers
    # ------------------------------------------------------------------

    def load_handoff(self) -> HandoffDocument | None:
        """Read and parse the handoff file. Returns None if no file exists."""
        if not self.handoff_path.exists():
            return None
        try:
            return HandoffDocument.from_markdown(self.handoff_path.read_text())
        except (ValueError, KeyError) as exc:
            # Corrupt/empty file — log and proceed without handoff
            import warnings

            warnings.warn(
                f"Could not parse handoff at {self.handoff_path}: {exc}",
                stacklevel=2,
            )
            return None

    def resuming_system_prompt_addendum(self, doc: HandoffDocument) -> str:
        """Build the preamble injected into the resuming agent's system prompt."""

        def _bullets(items: list[str], prefix: str = "  - ") -> str:
            return "\n".join(f"{prefix}{i}" for i in items) if items else "  *(none)*"

        hints = doc.search_hints
        handoff_body = doc.to_markdown()

        return _RESUMING_AGENT_PREAMBLE.format(
            task=doc.task,
            status=doc.status,
            timestamp=doc.timestamp,
            handoff_body=handoff_body,
            file_hints=_bullets(hints.file_paths),
            grep_hints=_bullets(hints.grep_patterns),
            symbol_hints=_bullets(hints.symbols),
        )

    def resuming_agent_options(
        self,
        base_options: Any,
    ) -> tuple[Any, HandoffDocument | None]:
        """
        Return *(augmented_options, handoff_doc)*.

        If no handoff file exists, returns *(base_options, None)* unchanged.
        When a handoff exists, its search hints are injected into the system
        prompt so the agent can immediately start verifying context.
        """
        doc = self.load_handoff()
        if doc is None:
            return base_options, None

        addendum = self.resuming_system_prompt_addendum(doc)
        existing = getattr(base_options, "system_prompt", None) or ""
        base_options.system_prompt = f"{addendum}\n\n{existing}".strip()

        return base_options, doc

    # ------------------------------------------------------------------
    # Utility: write a handoff from Python (for orchestrators / tests)
    # ------------------------------------------------------------------

    def write_handoff(self, doc: HandoffDocument) -> None:
        """Persist *doc* to disk. Creates parent directories as needed."""
        self.handoff_path.parent.mkdir(parents=True, exist_ok=True)
        self.handoff_path.write_text(doc.to_markdown())

    @staticmethod
    def blank_handoff(
        session_id: str = "unknown",
        task: str = "",
    ) -> HandoffDocument:
        """Create a minimal HandoffDocument to start from."""
        return HandoffDocument(
            session_id=session_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            task=task,
        )


# ---------------------------------------------------------------------------
# JSONL persistence  (append-only audit trail)
# ---------------------------------------------------------------------------

import json as _json

_DEFAULT_JSONL_PATH = Path(".plan_progress.jsonl")


def _append_jsonl(
    doc: HandoffDocument,
    jsonl_path: Path = _DEFAULT_JSONL_PATH,
    resume_prompt: str = "",
) -> None:
    """Append *doc* as a single JSONL line to the append-only audit log.

    Each session adds exactly one line.  The full history of all handoffs
    is preserved across sessions — nothing is ever overwritten or deleted.

    Parameters
    ----------
    doc:
        The ``HandoffDocument`` to serialise.
    jsonl_path:
        Destination file (default: ``.plan_progress.jsonl``).
    resume_prompt:
        Pre-rendered resume prompt to embed so the next session can read
        it directly without re-rendering from the Markdown file.
    """
    entry: dict[str, Any] = {
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
    }
    if resume_prompt:
        entry["resume_prompt"] = resume_prompt

    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("a", encoding="utf-8") as fh:
        fh.write(_json.dumps(entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Progress-log bridge
# ---------------------------------------------------------------------------


def _append_progress_log_entry(
    doc: HandoffDocument,
    plan_id: str,
    agent_id: str,
) -> None:
    """Append a one-line handoff summary row to ``docs/exec-plans/progress.md``.

    Silently no-ops when ``skills/progress_log.py`` is not importable (e.g.
    in environments where only ``harness_skills`` is installed).

    The row uses the *same* ``(plan_id, "context-handoff")`` key on every
    call, so the progress-log summary always reflects the *most recent*
    handoff status for that plan.
    """
    import sys as _sys

    try:
        _repo_root = str(Path(__file__).resolve().parent.parent)
        if _repo_root not in _sys.path:
            _sys.path.insert(0, _repo_root)
        from skills.progress_log import ProgressLog  # type: ignore[import]
    except ImportError:
        return

    # Map handoff status → progress-log status
    _status_map = {"done": "done", "in_progress": "started", "blocked": "failed"}
    status = _status_map.get(doc.status, "started")

    # Build a compact summary message
    parts: list[str] = []
    if doc.accomplished:
        n = len(doc.accomplished)
        parts.append(f"{n} item{'s' if n != 1 else ''} accomplished")
    if doc.next_steps:
        parts.append(f"next: {doc.next_steps[0][:60]}")
    if doc.search_hints.file_paths:
        n = len(doc.search_hints.file_paths)
        parts.append(f"{n} file hint{'s' if n != 1 else ''}")
    message = "; ".join(parts) or "context handoff written"

    ProgressLog().append(
        plan_id=plan_id,
        step="context-handoff",
        status=status,
        agent=agent_id,
        message=message,
        timestamp=doc.timestamp,
    )
    print(
        f"[handoff-tracker] progress log updated for plan '{plan_id}'",
        file=_sys.stderr,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _slugify(text: str, max_len: int = 50) -> str:
    """Convert *text* to a lowercase hyphen-separated slug (for plan IDs)."""
    import re as _re
    slug = _re.sub(r"[^a-z0-9]+", "-", text.lower().strip()).strip("-")
    return slug[:max_len]


# ---------------------------------------------------------------------------
# HandoffTracker  (hook-based integration)
# ---------------------------------------------------------------------------


class HandoffTracker:
    """Hook-based context handoff for Agent SDK sessions.

    Combines system-prompt injection (so the agent writes the Markdown
    handoff using its own ``Write`` tool) with a ``Stop`` hook that, once
    the session ends:

    1. Reads ``handoff_path`` — the Markdown file the agent wrote.
    2. Appends a JSONL entry to the append-only audit log (``jsonl_path``).
    3. Writes a summary row to ``docs/exec-plans/progress.md`` (optional).

    The *next* agent reads search hints from the handoff and then uses its
    own Read / Grep / Glob tools to verify current code — never trusting
    the handoff text as ground truth.

    Usage
    -----
    .. code-block:: python

        from harness_skills.handoff import HandoffTracker
        from claude_agent_sdk import ClaudeAgentOptions

        tracker = HandoffTracker(
            task="Add Redis-backed rate limiting",
            plan_id="feature/rate-limiting",
            agent_id="agent/coder-v1",
        )

        # Ending session — inject instructions + stop hook
        options = ClaudeAgentOptions(
            system_prompt=tracker.system_prompt_addendum(),
            hooks=tracker.hooks(),
        )
        async for msg in query(prompt="...", options=options):
            ...

        # After the session ends, read from the JSONL audit log:
        resume_prompt = HandoffTracker.get_resume_prompt()
        search_hints  = HandoffTracker.get_search_hints()

    Notes
    -----
    * The ``Stop`` hook fires for both normal completion and interruption.
    * If the agent did not write the handoff file, a warning is printed and
      the hook returns without writing anything.
    * ``tracker.hooks()`` returns ``{}`` when ``claude_agent_sdk`` is not
      installed (graceful degradation for tests / non-SDK environments).
    """

    def __init__(
        self,
        task: str = "",
        plan_id: str = "",
        agent_id: str = "unknown",
        handoff_path: Path = _DEFAULT_HANDOFF_PATH,
        jsonl_path: Path = _DEFAULT_JSONL_PATH,
        write_progress_log: bool = True,
    ) -> None:
        self.task = task
        self.plan_id = plan_id or _slugify(task) or "unnamed"
        self.agent_id = agent_id
        self.handoff_path = handoff_path
        self.jsonl_path = jsonl_path
        self.write_progress_log = write_progress_log
        self._protocol = HandoffProtocol(handoff_path=handoff_path)

    # ------------------------------------------------------------------
    # System prompt
    # ------------------------------------------------------------------

    def system_prompt_addendum(self) -> str:
        """Return the instruction block to append to the ending agent's system prompt."""
        return self._protocol.ending_system_prompt_addendum(task=self.task)

    # ------------------------------------------------------------------
    # Stop hook
    # ------------------------------------------------------------------

    def _make_stop_hook(self):
        """Build and return the async ``Stop``-event hook function."""
        tracker = self

        async def _stop_hook(input_data: dict, tool_use_id: str, context: Any) -> dict:
            import sys as _sys

            doc = tracker._protocol.load_handoff()
            if doc is None:
                print(
                    f"[handoff-tracker] WARNING: no handoff found at "
                    f"{tracker.handoff_path} — skipping JSONL sync.",
                    file=_sys.stderr,
                )
                return {}

            # Build pre-rendered resume prompt for the JSONL entry
            resume_prompt = tracker._protocol.resuming_system_prompt_addendum(doc)

            # 1. Append to JSONL audit log
            _append_jsonl(doc, jsonl_path=tracker.jsonl_path, resume_prompt=resume_prompt)
            print(
                f"[handoff-tracker] appended entry to {tracker.jsonl_path}",
                file=_sys.stderr,
            )

            # 2. Write summary row to docs/exec-plans/progress.md
            if tracker.write_progress_log:
                _append_progress_log_entry(
                    doc,
                    plan_id=tracker.plan_id,
                    agent_id=tracker.agent_id,
                )

            return {}

        return _stop_hook

    def hooks(self) -> dict:
        """Return a ``hooks`` dict for ``ClaudeAgentOptions(hooks=...)``.

        The ``Stop`` event fires when the agent session ends (normal finish
        *or* interruption).  The hook reads the Markdown handoff written by
        the agent, appends to the JSONL audit log, and updates the progress
        table.

        Returns ``{}`` when ``claude_agent_sdk`` is not installed (so the
        caller can still construct ``ClaudeAgentOptions`` without errors).
        """
        try:
            from claude_agent_sdk import HookMatcher  # type: ignore[import]
        except ImportError:
            return {}

        return {
            "Stop": [HookMatcher(matcher=".*", hooks=[self._make_stop_hook()])],
        }

    # ------------------------------------------------------------------
    # Class-level convenience readers  (from JSONL audit log)
    # ------------------------------------------------------------------

    @classmethod
    def get_resume_prompt(cls, jsonl_path: Path = _DEFAULT_JSONL_PATH) -> str:
        """Return the ``resume_prompt`` string from the latest JSONL entry.

        Returns an empty string when no JSONL file exists or the latest
        entry has no ``resume_prompt`` field.
        """
        if not jsonl_path.exists():
            return ""
        lines = [ln for ln in jsonl_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if not lines:
            return ""
        try:
            entry = _json.loads(lines[-1])
        except _json.JSONDecodeError:
            return ""
        return entry.get("resume_prompt", "")

    @classmethod
    def get_search_hints(cls, jsonl_path: Path = _DEFAULT_JSONL_PATH) -> "SearchHints | None":
        """Return a ``SearchHints`` object from the latest JSONL entry.

        Returns ``None`` when no JSONL file exists, is empty, or has no
        ``search_hints`` field.
        """
        if not jsonl_path.exists():
            return None
        lines = [ln for ln in jsonl_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if not lines:
            return None
        try:
            entry = _json.loads(lines[-1])
        except _json.JSONDecodeError:
            return None
        raw = entry.get("search_hints", {})
        if not raw:
            return None
        return SearchHints(
            file_paths=raw.get("file_paths", []),
            directories=raw.get("directories", []),
            grep_patterns=raw.get("grep_patterns", []),
            symbols=raw.get("symbols", []),
        )
