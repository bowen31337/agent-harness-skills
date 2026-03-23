"""
Context Handoff Protocol for Claude Agent SDK sessions.

When an agent session ends, ``HandoffTracker`` automatically synthesises a
structured summary and appends it to a JSONL progress log.  The entry
contains *search hints* — file paths, grep patterns, glob patterns, and
symbol names — that let the **next** agent rebuild its own context using its
built-in tools (Read / Grep / Glob) rather than relying on a pre-assembled
content dump.

Quick-start
-----------
::

    tracker = HandoffTracker(
        task="Add rate-limiting to the API gateway",
        log_path=".plan_progress.jsonl",
    )

    async for msg in query(
        prompt="Explore the gateway code and identify where to add rate-limits",
        options=ClaudeAgentOptions(
            cwd="/project",
            allowed_tools=["Read", "Glob", "Grep"],
            hooks=tracker.hooks(),          # ← plug in the tracker
        ),
    ):
        if isinstance(msg, ResultMessage):
            print(msg.result)

    # Next session picks up where this one left off:
    resume = HandoffTracker.get_resume_prompt()
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anthropic
from pydantic import BaseModel

from claude_agent_sdk import HookMatcher


# ─────────────────────────────────────────────────────────────────────────────
# Structured-output schema (Pydantic)
# ─────────────────────────────────────────────────────────────────────────────


class _SearchHints(BaseModel):
    """Actionable pointers that let the next agent rebuild context with search tools."""

    files: list[str]
    """Exact file paths the next agent should ``Read`` first."""

    grep_patterns: list[str]
    """Regex patterns ready to pass to the ``Grep`` tool."""

    glob_patterns: list[str]
    """Glob patterns ready to pass to the ``Glob`` tool (discovery)."""

    symbols: list[str]
    """Class / function / variable names central to this work."""


class _HandoffSchema(BaseModel):
    summary: str
    """2–3 sentences: what happened and what state the work is in."""

    accomplished: list[str]
    """Concrete items completed during this session."""

    pending: list[str]
    """Specific items still left to do."""

    search_hints: _SearchHints
    """How the next agent re-orients itself without a content dump."""

    key_decisions: list[str]
    """Important discoveries or architectural choices made."""

    resume_prompt: str
    """
    A self-contained prompt for the next agent.  Includes what was done,
    what to do next, and which files to look at — but *no* file content.
    """


# ─────────────────────────────────────────────────────────────────────────────
# HandoffTracker
# ─────────────────────────────────────────────────────────────────────────────


class HandoffTracker:
    """
    Hooks into a Claude Agent SDK session to record tool-use events and write
    a structured handoff when the session ends.

    Parameters
    ----------
    task:
        Human-readable description of the overall task being worked on.
        Used to orient the handoff generator.
    log_path:
        Path to the JSONL progress log.  Each session appends one JSON line.
        Defaults to ``.plan_progress.jsonl`` in the working directory.
    cwd:
        Working directory of the agent session (for context only — not used
        for file I/O by this class).
    """

    DEFAULT_LOG = ".plan_progress.jsonl"

    def __init__(
        self,
        task: str,
        log_path: str = DEFAULT_LOG,
        cwd: str = ".",
    ) -> None:
        self.task = task
        self.log_path = Path(log_path)
        self.cwd = cwd
        self._events: list[dict[str, Any]] = []

    # ── Private helpers ───────────────────────────────────────────────────────

    def _record(self, kind: str, **data: Any) -> None:
        self._events.append(
            {
                "kind": kind,
                "ts": datetime.now(timezone.utc).isoformat(),
                **data,
            }
        )

    # ── Hook callbacks ────────────────────────────────────────────────────────

    async def _on_post_tool_use(
        self, input_data: dict, tool_use_id: str, context: Any
    ) -> dict:
        """
        Fires after every tool call.  Extracts the most useful signal from each
        tool type and appends a compact event to ``self._events``.
        """
        tool_name: str = input_data.get("tool_name", "")
        tool_input: dict = input_data.get("tool_input", {})

        ev: dict[str, Any] = {"tool": tool_name}

        match tool_name:
            case "Read" | "Write" | "Edit":
                ev["file"] = tool_input.get("file_path", "")
            case "Glob":
                ev["pattern"] = tool_input.get("pattern", "")
                if p := tool_input.get("path"):
                    ev["path"] = p
            case "Grep":
                ev["pattern"] = tool_input.get("pattern", "")
                if p := tool_input.get("path"):
                    ev["path"] = p
            case "Bash":
                ev["cmd"] = (tool_input.get("command") or "")[:300]
            case "Agent":
                ev["subagent"] = tool_input.get("subagent_type", "")
                ev["desc"] = (tool_input.get("description") or "")[:200]
            case _:
                ev["input_keys"] = list(tool_input.keys())[:6]

        self._record("tool_use", **ev)
        return {}

    async def _on_session_end(
        self, input_data: dict, tool_use_id: str, context: Any
    ) -> dict:
        """
        Fires when the agent session terminates.  Calls the Claude API to
        synthesise a structured handoff and appends it to the log.
        """
        session_id: str = input_data.get("session_id", "unknown")
        await self._generate_and_write(session_id)
        return {}

    # ── Handoff generation ────────────────────────────────────────────────────

    async def _generate_and_write(self, session_id: str) -> None:
        """
        Calls ``claude-opus-4-6`` (adaptive thinking, streaming) to produce a
        structured :class:`_HandoffSchema` from the recorded events, then
        appends the result to the JSONL log.
        """
        client = anthropic.AsyncAnthropic()

        # Compact event log — cap at 6 000 chars to stay well within limits
        event_log = json.dumps(self._events, separators=(",", ":"))[:6_000]

        prompt = f"""\
You are writing a context handoff for the NEXT agent that will continue this work.
That agent starts with NO memory — give it exactly what it needs to rebuild context
using its own search tools (Read, Grep, Glob), without pre-loading file content.

TASK BEING WORKED ON
{self.task}

TOOL INVOCATIONS THIS SESSION  (compact log)
{event_log}

Produce a structured handoff.  Rules:

summary
  2–3 sentences: what happened, where things stand right now.

accomplished
  Concrete, specific items completed.

pending
  Specific items still to do.  Be precise about what comes next.

search_hints — how the next agent re-orients itself:
  files          Exact file paths it should Read first.  Max 8.
                 Only include files actually touched or essential for orientation.
  grep_patterns  Actionable regex patterns for the Grep tool.
                 E.g. "class AuthHandler", "TODO:.*rate.limit", "def validate_token".
  glob_patterns  Discovery patterns for the Glob tool.
                 E.g. "src/auth/**/*.py", "tests/test_api*".
  symbols        Class / function / variable names the next agent will need to search for.

key_decisions
  Important findings, architectural choices, or gotchas discovered.

resume_prompt
  A self-contained prompt for the next agent.  Include: what was done,
  what to do next, which files to look at first.  No file contents — pointers only."""

        # Explicit JSON schema — must include additionalProperties: false on every object
        # (required by Claude's structured-output API; Pydantic doesn't add this by default)
        json_schema = {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "accomplished": {"type": "array", "items": {"type": "string"}},
                "pending": {"type": "array", "items": {"type": "string"}},
                "search_hints": {
                    "type": "object",
                    "properties": {
                        "files": {"type": "array", "items": {"type": "string"}},
                        "grep_patterns": {"type": "array", "items": {"type": "string"}},
                        "glob_patterns": {"type": "array", "items": {"type": "string"}},
                        "symbols": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["files", "grep_patterns", "glob_patterns", "symbols"],
                    "additionalProperties": False,
                },
                "key_decisions": {"type": "array", "items": {"type": "string"}},
                "resume_prompt": {"type": "string"},
            },
            "required": [
                "summary", "accomplished", "pending",
                "search_hints", "key_decisions", "resume_prompt",
            ],
            "additionalProperties": False,
        }

        # Use streaming (long input) + get_final_message helper
        async with client.messages.stream(
            model="claude-opus-4-6",
            max_tokens=4096,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": json_schema}},
        ) as stream:
            final = await stream.get_final_message()

        # Extract the text block (thinking blocks come first with adaptive thinking)
        text = next(
            block.text
            for block in final.content
            if getattr(block, "type", "") == "text"
        )

        data = _HandoffSchema.model_validate_json(text)

        entry: dict[str, Any] = {
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task": self.task,
            "status": "completed",
            "summary": data.summary,
            "accomplished": data.accomplished,
            "pending": data.pending,
            "search_hints": {
                "files": data.search_hints.files,
                "grep_patterns": data.search_hints.grep_patterns,
                "glob_patterns": data.search_hints.glob_patterns,
                "symbols": data.search_hints.symbols,
            },
            "key_decisions": data.key_decisions,
            "resume_prompt": data.resume_prompt,
        }

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")

    # ── Public API ────────────────────────────────────────────────────────────

    def hooks(self) -> dict:
        """
        Returns a hooks dict ready to pass to ``ClaudeAgentOptions(hooks=...)``.

        Wires up:
        - ``PostToolUse`` (all tools) → records events
        - ``SessionEnd`` → generates and writes the handoff
        """
        return {
            "PostToolUse": [
                HookMatcher(matcher=".*", hooks=[self._on_post_tool_use])
            ],
            "SessionEnd": [
                HookMatcher(matcher=".*", hooks=[self._on_session_end])
            ],
        }

    # ── Log helpers (class-level) ─────────────────────────────────────────────

    @classmethod
    def read_latest(cls, log_path: str = DEFAULT_LOG) -> dict | None:
        """
        Returns the most-recent handoff entry from the JSONL log, or ``None``
        if the log is absent or empty.
        """
        path = Path(log_path)
        if not path.exists():
            return None
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        return json.loads(lines[-1]) if lines else None

    @classmethod
    def read_all(cls, log_path: str = DEFAULT_LOG) -> list[dict]:
        """Returns all handoff entries in chronological order."""
        path = Path(log_path)
        if not path.exists():
            return []
        return [
            json.loads(ln)
            for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]

    @classmethod
    def get_resume_prompt(cls, log_path: str = DEFAULT_LOG) -> str | None:
        """
        Returns the ``resume_prompt`` from the latest handoff — pass this as
        the ``prompt`` argument to the next agent session.
        """
        entry = cls.read_latest(log_path)
        return entry.get("resume_prompt") if entry else None

    @classmethod
    def get_search_hints(cls, log_path: str = DEFAULT_LOG) -> dict | None:
        """Returns the ``search_hints`` dict from the latest handoff."""
        entry = cls.read_latest(log_path)
        return entry.get("search_hints") if entry else None
