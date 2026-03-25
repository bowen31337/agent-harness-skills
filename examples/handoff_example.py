"""
Demonstrates the full context handoff lifecycle:

  Session A — ending agent writes a handoff before stopping.
  Session B — resuming agent reads search hints and rebuilds its own context.

Run:
    uv add claude-agent-sdk
    python examples/handoff_example.py
"""

from __future__ import annotations

import anyio
from claude_agent_sdk import (
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    query,
)

from harness_skills.handoff import HandoffDocument, HandoffProtocol, SearchHints

# ---------------------------------------------------------------------------
# Shared setup
# ---------------------------------------------------------------------------

PROTOCOL = HandoffProtocol(handoff_path=__import__("pathlib").Path(".claude/plan-progress.md"))

TASK = "Implement JWT authentication middleware for the FastAPI app"


# ---------------------------------------------------------------------------
# Session A — the "ending" agent
# ---------------------------------------------------------------------------

async def run_ending_session() -> str | None:
    """
    The ending agent works on the task, then writes a structured handoff
    to .claude/plan-progress.md before it stops.
    """
    print("\n━━━ SESSION A — ending agent ━━━")

    base = ClaudeAgentOptions(
        allowed_tools=["Read", "Glob", "Grep", "Write"],
        permission_mode="acceptEdits",
        max_turns=30,
    )
    options = PROTOCOL.ending_agent_options(base_options=base, task=TASK)

    # The system prompt now includes the mandatory handoff instruction block.
    print(f"System prompt length: {len(options.system_prompt)} chars")
    print("Handoff instruction injected ✓\n")

    session_id: str | None = None

    async for message in query(
        prompt=(
            f"Task: {TASK}\n\n"
            "1. Explore the codebase to understand the structure.\n"
            "2. Implement what you can.\n"
            "3. Before stopping, write the mandatory handoff document as instructed."
        ),
        options=options,
    ):
        if isinstance(message, SystemMessage) and message.subtype == "init":
            session_id = message.session_id
            print(f"Session ID: {session_id}")
        elif isinstance(message, ResultMessage):
            print(f"\nSession A result (truncated):\n{message.result[:400]}…\n")

    return session_id


# ---------------------------------------------------------------------------
# Session B — the "resuming" agent
# ---------------------------------------------------------------------------

async def run_resuming_session() -> None:
    """
    The resuming agent reads the handoff, gets injected search hints, then
    uses its own tools to verify and rebuild context before continuing work.
    """
    print("\n━━━ SESSION B — resuming agent ━━━")

    base = ClaudeAgentOptions(
        allowed_tools=["Read", "Glob", "Grep", "Edit", "Write"],
        permission_mode="acceptEdits",
        max_turns=40,
    )
    options, handoff_doc = PROTOCOL.resuming_agent_options(base_options=base)

    if handoff_doc is None:
        print("No handoff found — starting fresh (no .claude/plan-progress.md).")
    else:
        print(f"Handoff loaded  : task='{handoff_doc.task}', status='{handoff_doc.status}'")
        print(f"Search hints    : {len(handoff_doc.search_hints.file_paths)} files, "
              f"{len(handoff_doc.search_hints.grep_patterns)} patterns, "
              f"{len(handoff_doc.search_hints.symbols)} symbols")
        print("Context injected into system prompt ✓\n")

    async for message in query(
        prompt=(
            "You have been handed off from a previous session. "
            "First, use your tools to verify the context from the handoff. "
            "Then continue from where the last agent left off.\n\n"
            "When you finish this session, write a fresh handoff document."
        ),
        options=options,
    ):
        if isinstance(message, ResultMessage):
            print(f"\nSession B result (truncated):\n{message.result[:400]}…\n")


# ---------------------------------------------------------------------------
# Orchestrator-side API — writing handoffs from Python
# ---------------------------------------------------------------------------

def demo_programmatic_handoff() -> None:
    """
    Show how an orchestrator can write a HandoffDocument directly (e.g. after
    receiving structured output from an agent, or for testing).
    """
    print("\n━━━ Programmatic handoff write/read round-trip ━━━")

    doc = HandoffDocument(
        session_id="demo-abc-123",
        timestamp="2026-03-13T10:30:00Z",
        task=TASK,
        status="in_progress",
        accomplished=[
            "Created `src/auth/` directory.",
            "Implemented `JWTTokenService` in `src/auth/tokens.py`.",
            "Added `pyproject.toml` dependency: `python-jose[cryptography]`.",
        ],
        in_progress=[
            "`UserAuthMiddleware` in `src/middleware/auth.py` — 70% done; error-handling missing.",
        ],
        next_steps=[
            "Finish error-handling in `UserAuthMiddleware.__call__`.",
            "Register middleware in `src/main.py` (`app.add_middleware(...)`).",
            "Write pytest tests for token generation and validation.",
            "Add `/api/auth/login` and `/api/auth/refresh` endpoints.",
        ],
        search_hints=SearchHints(
            file_paths=[
                "src/auth/tokens.py",
                "src/middleware/auth.py",
                "src/main.py",
                "tests/test_auth.py",
            ],
            grep_patterns=[
                r"class JWTTokenService",
                r"class UserAuthMiddleware",
                r"def (create|verify)_token",
                r"TODO.*auth",
                r"app\.add_middleware",
            ],
            symbols=[
                "JWTTokenService",
                "UserAuthMiddleware",
                "create_access_token",
                "verify_token",
            ],
            directories=["src/auth/", "src/middleware/", "tests/"],
        ),
        open_questions=[
            "Should access tokens be 15 min or 1 hour TTL?",
            "Do we need refresh-token rotation?",
        ],
        artifacts=[
            "src/auth/__init__.py",
            "src/auth/tokens.py",
            "src/middleware/__init__.py",
            "src/middleware/auth.py",
        ],
        notes=(
            "The app uses FastAPI 0.115. The existing `src/main.py` already has "
            "`from fastapi import FastAPI; app = FastAPI()` — we just need to add "
            "the middleware call after that line."
        ),
    )

    # Write to disk
    PROTOCOL.write_handoff(doc)
    path = PROTOCOL.handoff_path
    print(f"Written to {path} ({path.stat().st_size} bytes)")

    # Round-trip: parse it back
    doc2 = HandoffDocument.from_markdown(path.read_text())
    assert doc2.session_id == doc.session_id
    assert doc2.search_hints.file_paths == doc.search_hints.file_paths
    assert doc2.search_hints.grep_patterns == doc.search_hints.grep_patterns
    print("Round-trip parse ✓")
    print(f"Next steps ({len(doc2.next_steps)}):")
    for step in doc2.next_steps:
        print(f"  • {step}")

    # Show what the resuming agent's system-prompt addendum looks like
    addendum = PROTOCOL.resuming_system_prompt_addendum(doc2)
    print(f"\nSystem-prompt addendum preview ({len(addendum)} chars):")
    print(addendum[:600], "…")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    # 1. Demonstrate programmatic handoff (no live agent needed)
    demo_programmatic_handoff()

    # 2. Live agent sessions — comment these in to run with a real API key:
    #
    # await run_ending_session()    # Session A writes the handoff
    # await run_resuming_session()  # Session B reads it and rebuilds context


if __name__ == "__main__":
    anyio.run(main)
