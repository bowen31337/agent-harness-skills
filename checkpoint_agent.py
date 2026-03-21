"""
checkpoint_agent.py
===================
Full end-to-end example: Claude Agent SDK + git-based checkpoints.

Every time the agent writes or edits a file (or runs a Bash command) a
WIP commit is automatically pushed to a dedicated branch:

    wip/<agent_id>/<task_id>

Each commit message contains structured trailers for multi-agent
traceability::

    wip(feat/auth-refactor): after Edit [checkpoint #3]

    Automated WIP checkpoint committed by agent harness.

    Checkpoint: #3
    Timestamp:  2026-03-13T18:42:00+00:00
    Tool:       Edit
    Tool Input: file_path=src/auth/token_validator.py

    Plan-Ref: Step 3 — extract and harden TokenValidator class
    Agent-Id: agent-42
    Task-Id:  feat/auth-refactor

Run
---
    python checkpoint_agent.py

Environment variables
---------------------
ANTHROPIC_API_KEY   — required unless using claude-oauth in claw-forge.yaml
AGENT_ID            — optional override (default: "agent-01")
TASK_ID             — optional override (default: "harness-task-001")
"""

from __future__ import annotations

import os
import sys
import anyio

from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    HookMatcher,
    ResultMessage,
    SystemMessage,
)

from git_checkpoint import GitCheckpoint


# ---------------------------------------------------------------------------
# Configuration — override via environment variables
# ---------------------------------------------------------------------------

AGENT_ID   = os.environ.get("AGENT_ID",  "agent-01")
TASK_ID    = os.environ.get("TASK_ID",   "harness-task-001")
PLAN_REF   = "Step 1 — scaffold harness-skills CLI entry-point"
REPO_PATH  = os.path.dirname(os.path.abspath(__file__))

# The task prompt sent to the agent
TASK_PROMPT = """\
You are scaffolding the harness-skills CLI.

1. Create `src/__init__.py` with a module docstring.
2. Create `src/cli.py` with a minimal `typer` app that has a single
   `generate` command (stub — just prints "TODO: implement generate").
3. Append a usage note to CLAUDE.md under a new "## Usage" heading.

Do not install any packages.  Do not run tests.  Just write the files.
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    # ── 1. Initialise checkpoint manager ──────────────────────────────────
    cp = GitCheckpoint(
        agent_id=AGENT_ID,
        task_id=TASK_ID,
        plan_ref=PLAN_REF,
        repo_path=REPO_PATH,
        branch_prefix="wip",
        auto_stage_all=True,
    )

    print(f"[harness] agent_id  = {AGENT_ID}")
    print(f"[harness] task_id   = {TASK_ID}")
    print(f"[harness] plan_ref  = {PLAN_REF!r}")

    # Ensure the WIP branch exists before the agent starts writing
    branch = cp.ensure_branch()
    print(f"[harness] branch    = {branch}\n")

    # ── 2. Build Agent SDK options with PostToolUse checkpoint hook ────────
    options = ClaudeAgentOptions(
        cwd=REPO_PATH,
        allowed_tools=["Read", "Edit", "Write", "Bash", "Glob"],
        permission_mode="acceptEdits",
        system_prompt=(
            "You are a precise software engineer.  "
            "Write minimal, well-documented code.  "
            "Do not install packages or run commands unless explicitly asked."
        ),
        hooks={
            # Fire the checkpoint hook after every file-mutating tool call
            "PostToolUse": [
                HookMatcher(
                    matcher="Edit|Write|Bash",
                    hooks=[cp.as_hook()],
                )
            ]
        },
        max_turns=20,
    )

    # ── 3. Run the agent and stream output ────────────────────────────────
    session_id: str | None = None

    async for message in query(prompt=TASK_PROMPT, options=options):
        if isinstance(message, SystemMessage) and message.subtype == "init":
            session_id = message.session_id
            print(f"[harness] session_id = {session_id}\n")

        elif isinstance(message, ResultMessage):
            print("\n── Agent result ──────────────────────────────────────")
            print(message.result)

    # ── 4. Final summary checkpoint ────────────────────────────────────────
    print("\n[harness] Creating final summary checkpoint …")
    try:
        meta = cp.commit_checkpoint(
            description="task complete — final state",
            tool_name="harness",
            tool_input_summary=f"session_id={session_id}",
        )
        print(
            f"[harness] ✓ final checkpoint #{meta.checkpoint_index} "
            f"→ {meta.commit_sha[:8]}  ({meta.branch})"
        )
        _print_meta_summary(meta)
    except RuntimeError as exc:
        print(f"[harness] No new changes to checkpoint: {exc}")

    print("\n[harness] Done.")


def _print_meta_summary(meta) -> None:  # type: ignore[no-untyped-def]
    import json
    from git_checkpoint import CheckpointMeta
    print("\n── Checkpoint metadata ───────────────────────────────────")
    print(json.dumps(meta.to_dict(), indent=2))


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        anyio.run(main)
    except KeyboardInterrupt:
        print("\n[harness] Interrupted.")
        sys.exit(1)
