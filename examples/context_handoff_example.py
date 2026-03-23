"""
Example: multi-session agent work with context handoff.

Usage
-----
# First agent session — explores the codebase
python examples/context_handoff_example.py session1

# Second agent session — resumes from the handoff
python examples/context_handoff_example.py session2

# Inspect the latest handoff
python examples/context_handoff_example.py view

# Print ONLY the resume_prompt (pipe it into the next session)
python examples/context_handoff_example.py resume
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import anyio

from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from handoff import HandoffTracker

LOG_PATH = str(_PROJECT_ROOT / ".plan_progress.jsonl")
PROJECT_DIR = str(_PROJECT_ROOT)

TASK = (
    "Audit the authentication module for security issues "
    "and add input-validation guards to all public endpoints"
)


# ─── Session 1 — initial exploration ─────────────────────────────────────────


async def run_session1() -> None:
    """
    First agent: explore the codebase, identify the auth module, find issues.
    When done, HandoffTracker writes a structured handoff to LOG_PATH.
    """
    tracker = HandoffTracker(task=TASK, log_path=LOG_PATH, cwd=PROJECT_DIR)

    print("══════════════════════════════════════════════")
    print("  Session 1 — initial exploration")
    print("══════════════════════════════════════════════\n")

    async for msg in query(
        prompt=(
            "Explore this Python project.  Find the authentication code, "
            "read it carefully, and identify any security issues or missing "
            "input-validation.  Summarise your findings."
        ),
        options=ClaudeAgentOptions(
            cwd=PROJECT_DIR,
            allowed_tools=["Read", "Glob", "Grep"],
            hooks=tracker.hooks(),       # ← plug in the tracker
        ),
    ):
        if isinstance(msg, ResultMessage):
            print(msg.result)

    print(f"\n✓  Handoff written → {LOG_PATH}")


# ─── Session 2 — resume from handoff ─────────────────────────────────────────


async def run_session2() -> None:
    """
    Second agent: load the handoff written by session 1 and continue the work.
    The ``resume_prompt`` from the handoff drives this session's starting prompt,
    so the agent knows exactly where to pick up — no content dump required.
    """
    resume_prompt = HandoffTracker.get_resume_prompt(LOG_PATH)
    if not resume_prompt:
        print("No handoff found.  Run 'python examples/context_handoff_example.py session1' first.")
        return

    hints = HandoffTracker.get_search_hints(LOG_PATH) or {}
    print("══════════════════════════════════════════════")
    print("  Session 2 — resuming from handoff")
    print("══════════════════════════════════════════════")
    print(f"  {len(hints.get('files', []))} file hints  "
          f"· {len(hints.get('grep_patterns', []))} grep patterns  "
          f"· {len(hints.get('symbols', []))} symbols\n")

    tracker = HandoffTracker(task=TASK, log_path=LOG_PATH, cwd=PROJECT_DIR)

    async for msg in query(
        prompt=resume_prompt,            # ← the handoff's resume_prompt drives session 2
        options=ClaudeAgentOptions(
            cwd=PROJECT_DIR,
            allowed_tools=["Read", "Edit", "Glob", "Grep"],
            permission_mode="acceptEdits",
            hooks=tracker.hooks(),
        ),
    ):
        if isinstance(msg, ResultMessage):
            print(msg.result)

    print(f"\n✓  Updated handoff written → {LOG_PATH}")


# ─── View helpers ─────────────────────────────────────────────────────────────


def view_latest() -> None:
    """Pretty-print the most recent handoff."""
    entry = HandoffTracker.read_latest(LOG_PATH)
    if not entry:
        print("No handoffs found.")
        return

    w = 60
    print("─" * w)
    print(f"Session   : {entry['session_id']}")
    print(f"Timestamp : {entry['timestamp']}")
    print(f"Task      : {entry['task']}")
    print("─" * w)

    print(f"\nSummary:\n  {entry['summary']}\n")

    print("Accomplished:")
    for item in entry["accomplished"]:
        print(f"  ✓  {item}")

    print("\nPending:")
    for item in entry["pending"]:
        print(f"  →  {item}")

    hints = entry["search_hints"]
    print("\nSearch Hints:")
    if hints["files"]:
        print("  Files (Read these first):")
        for f in hints["files"]:
            print(f"    {f}")
    if hints["grep_patterns"]:
        print("  Grep patterns:")
        for p in hints["grep_patterns"]:
            print(f"    {p}")
    if hints["glob_patterns"]:
        print("  Glob patterns:")
        for p in hints["glob_patterns"]:
            print(f"    {p}")
    if hints["symbols"]:
        print("  Symbols:")
        for s in hints["symbols"]:
            print(f"    {s}")

    print("\nKey Decisions:")
    for d in entry["key_decisions"]:
        print(f"  •  {d}")

    print("\nResume Prompt:")
    print("─" * w)
    print(entry["resume_prompt"])
    print("─" * w)


def print_resume_prompt() -> None:
    """Print only the resume_prompt (useful for scripting)."""
    prompt = HandoffTracker.get_resume_prompt(LOG_PATH)
    if prompt:
        print(prompt)
    else:
        print("No handoff found.", file=sys.stderr)
        sys.exit(1)


# ─── Entrypoint ───────────────────────────────────────────────────────────────


COMMANDS = {
    "session1": lambda: anyio.run(run_session1),
    "session2": lambda: anyio.run(run_session2),
    "view":     view_latest,
    "resume":   print_resume_prompt,
}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "view"
    fn = COMMANDS.get(cmd)
    if fn is None:
        print(f"Unknown command: {cmd!r}")
        print(f"Available: {', '.join(COMMANDS)}")
        sys.exit(1)
    fn()
