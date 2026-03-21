"""
git_checkpoint.py
=================
Git-based checkpoint integration for the Claude Agent SDK.

Agents commit work-in-progress to a dedicated WIP branch after each
significant tool use (Write / Edit / Bash).  Every commit message carries:

  - A human-readable description of the checkpoint
  - A ``Plan-Ref:`` trailer pointing to the plan step or task description
  - ``Agent-Id:`` and ``Task-Id:`` trailers for multi-agent traceability

Checkpoint metadata is also written to ``.checkpoint_meta.json`` in the
repo root so external tooling (CI, dashboards) can parse it without
walking commit messages.

Usage
-----
Standalone (direct git commits)::

    from git_checkpoint import GitCheckpoint

    cp = GitCheckpoint(
        agent_id="agent-42",
        task_id="feat/auth-refactor",
        plan_ref="Step 3: extract token validator",
        repo_path="/path/to/repo",
    )
    cp.ensure_branch()          # creates wip/agent-42/feat-auth-refactor
    cp.commit_checkpoint("implemented token validator", files=["src/auth.py"])

Agent SDK hook (auto-checkpoint after every Edit/Write/Bash)::

    from git_checkpoint import GitCheckpoint
    from claude_agent_sdk import query, ClaudeAgentOptions, HookMatcher

    cp = GitCheckpoint(agent_id="agent-42", task_id="feat/auth-refactor",
                       plan_ref="Step 3: extract token validator")
    cp.ensure_branch()

    async for msg in query(
        prompt="Refactor the auth module",
        options=ClaudeAgentOptions(
            allowed_tools=["Read", "Edit", "Write", "Bash"],
            permission_mode="acceptEdits",
            hooks={
                "PostToolUse": [
                    HookMatcher(matcher="Edit|Write|Bash", hooks=[cp.as_hook()])
                ]
            },
        ),
    ):
        ...
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Coroutine


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class CheckpointMeta:
    """Persisted metadata written to ``.checkpoint_meta.json``."""

    agent_id: str
    task_id: str
    plan_ref: str
    branch: str
    commit_sha: str
    timestamp: str
    checkpoint_index: int
    tool_name: str = ""
    tool_input_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "plan_ref": self.plan_ref,
            "branch": self.branch,
            "commit_sha": self.commit_sha,
            "timestamp": self.timestamp,
            "checkpoint_index": self.checkpoint_index,
            "tool_name": self.tool_name,
            "tool_input_summary": self.tool_input_summary,
        }


# ---------------------------------------------------------------------------
# Core class
# ---------------------------------------------------------------------------

class GitCheckpoint:
    """Manages git-based WIP checkpoints for a single agent / task pair.

    Parameters
    ----------
    agent_id:
        Stable identifier for the agent instance (e.g. ``"agent-42"`` or a
        UUID).  Used in the branch name and commit trailers.
    task_id:
        The task or feature identifier (e.g. ``"feat/auth-refactor"`` or a
        ticket number).  Slashes are normalised to hyphens in branch names.
    plan_ref:
        Human-readable reference to the current plan step — included in
        every commit message as a ``Plan-Ref:`` trailer.
    repo_path:
        Absolute path to the git repository root.  Defaults to the current
        working directory.
    branch_prefix:
        Prefix for the WIP branch.  Defaults to ``"wip"``.
    meta_filename:
        Name of the JSON metadata file written at the repo root.
        Defaults to ``".checkpoint_meta.json"``.
    auto_stage_all:
        When ``True`` (default) the hook stages **all** modified/untracked
        files before committing.  Set to ``False`` to only stage files
        explicitly passed to :meth:`commit_checkpoint`.
    """

    def __init__(
        self,
        *,
        agent_id: str,
        task_id: str,
        plan_ref: str,
        repo_path: str | Path | None = None,
        branch_prefix: str = "wip",
        meta_filename: str = ".checkpoint_meta.json",
        auto_stage_all: bool = True,
    ) -> None:
        self.agent_id = agent_id
        self.task_id = task_id
        self.plan_ref = plan_ref
        self.repo_path = Path(repo_path or os.getcwd()).resolve()
        self.branch_prefix = branch_prefix
        self.meta_filename = meta_filename
        self.auto_stage_all = auto_stage_all

        self._checkpoint_index: int = 0
        self._branch: str | None = None

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def branch(self) -> str:
        """The WIP branch name (computed lazily)."""
        if self._branch is None:
            # Normalise task_id: replace slashes + spaces with hyphens,
            # strip characters that git dislikes in branch names.
            safe_task = re.sub(r"[^a-zA-Z0-9._-]", "-", self.task_id).strip("-")
            safe_agent = re.sub(r"[^a-zA-Z0-9._-]", "-", self.agent_id).strip("-")
            self._branch = f"{self.branch_prefix}/{safe_agent}/{safe_task}"
        return self._branch

    def ensure_branch(self) -> str:
        """Create the WIP branch if it does not exist, then check it out.

        Returns the branch name.
        """
        existing = self._git("branch", "--list", self.branch).strip()
        if not existing:
            # Create from current HEAD (or the default branch tip)
            self._git("checkout", "-b", self.branch)
        else:
            self._git("checkout", self.branch)
        return self.branch

    def commit_checkpoint(
        self,
        description: str,
        *,
        files: list[str] | None = None,
        tool_name: str = "",
        tool_input_summary: str = "",
    ) -> CheckpointMeta:
        """Stage files and create a WIP checkpoint commit.

        Parameters
        ----------
        description:
            Short description that appears in the first line of the commit
            message (e.g. ``"wrote token validator"``, ``"ran test suite"``).
        files:
            Explicit list of file paths to stage.  If *auto_stage_all* is
            ``True`` these are staged in addition to all other changes.
        tool_name:
            Name of the tool that triggered this checkpoint (for metadata).
        tool_input_summary:
            Brief summary of the tool input (first 120 chars is enough).

        Returns
        -------
        CheckpointMeta
            The metadata written to ``.checkpoint_meta.json``.

        Raises
        ------
        RuntimeError
            If there is nothing to commit (working tree is clean).
        """
        self._checkpoint_index += 1
        idx = self._checkpoint_index

        # Stage files
        if self.auto_stage_all:
            self._git("add", "-A")
        elif files:
            self._git("add", "--", *files)

        # Bail out early if there is nothing to commit
        status = self._git("status", "--porcelain")
        # After `git add`, use --cached to check staged changes
        staged = self._git("diff", "--cached", "--name-only").strip()
        if not staged:
            raise RuntimeError(
                f"[GitCheckpoint] Nothing to commit at checkpoint #{idx} "
                f"(working tree clean)."
            )

        # Build commit message
        timestamp = datetime.now(tz=timezone.utc).isoformat()
        subject = f"wip({self.task_id}): {description} [checkpoint #{idx}]"
        body = textwrap.dedent(f"""\
            Automated WIP checkpoint committed by agent harness.

            Checkpoint: #{idx}
            Timestamp:  {timestamp}
            Tool:       {tool_name or "—"}
            Tool Input: {tool_input_summary[:120] or "—"}
        """)
        trailers = "\n".join([
            f"Plan-Ref: {self.plan_ref}",
            f"Agent-Id: {self.agent_id}",
            f"Task-Id:  {self.task_id}",
        ])
        commit_message = f"{subject}\n\n{body}\n{trailers}"

        self._git("commit", "--no-verify", "-m", commit_message)
        commit_sha = self._git("rev-parse", "HEAD").strip()

        # Write metadata file
        meta = CheckpointMeta(
            agent_id=self.agent_id,
            task_id=self.task_id,
            plan_ref=self.plan_ref,
            branch=self.branch,
            commit_sha=commit_sha,
            timestamp=timestamp,
            checkpoint_index=idx,
            tool_name=tool_name,
            tool_input_summary=tool_input_summary[:120],
        )
        meta_path = self.repo_path / self.meta_filename
        meta_path.write_text(json.dumps(meta.to_dict(), indent=2) + "\n")

        # Stage and amend the meta file into the same commit so the SHA
        # is consistent with the written value.
        self._git("add", str(meta_path))
        amend_msg = commit_message  # keep identical subject/body/trailers
        self._git("commit", "--no-verify", "--amend", "-m", amend_msg)
        # Re-read the final SHA after the amend
        final_sha = self._git("rev-parse", "HEAD").strip()
        meta.commit_sha = final_sha
        meta_path.write_text(json.dumps(meta.to_dict(), indent=2) + "\n")
        # Stage the updated meta (with correct SHA) — silent if nothing changed
        try:
            self._git("add", str(meta_path))
            self._git("commit", "--no-verify", "--amend", "--no-edit")
        except subprocess.CalledProcessError:
            pass  # nothing changed — that's fine

        return meta

    def as_hook(
        self,
    ) -> Callable[[dict[str, Any], str, Any], Coroutine[Any, Any, dict[str, Any]]]:
        """Return an async ``PostToolUse`` hook compatible with the Agent SDK.

        The hook is called after every tool use whose name matches the
        ``HookMatcher`` pattern supplied in ``ClaudeAgentOptions.hooks``.

        The hook gracefully skips committing when the working tree is
        clean (e.g. a ``Read`` or ``Grep`` tool was matched but produced no
        file changes).
        """

        async def _checkpoint_hook(
            input_data: dict[str, Any],
            tool_use_id: str,
            context: Any,
        ) -> dict[str, Any]:
            tool_name: str = input_data.get("tool_name", "")
            tool_input: dict[str, Any] = input_data.get("tool_input", {})
            summary = _summarise_tool_input(tool_name, tool_input)

            try:
                meta = self.commit_checkpoint(
                    description=f"after {tool_name}",
                    tool_name=tool_name,
                    tool_input_summary=summary,
                )
                print(
                    f"[GitCheckpoint] ✓ checkpoint #{meta.checkpoint_index} "
                    f"→ {meta.commit_sha[:8]}  ({meta.branch})"
                )
            except RuntimeError:
                # Nothing to commit — silent skip
                pass
            except subprocess.CalledProcessError as exc:
                print(f"[GitCheckpoint] ⚠ git error during checkpoint: {exc}")

            return {}  # hooks must return a dict

        return _checkpoint_hook

    # ------------------------------------------------------------------
    # Private git helpers
    # ------------------------------------------------------------------

    def _git(self, *args: str) -> str:
        """Run a git command inside *repo_path* and return stdout."""
        result = subprocess.run(
            ["git", *args],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _summarise_tool_input(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Produce a short human-readable summary of a tool's input."""
    if tool_name in ("Edit", "Write"):
        path = tool_input.get("file_path") or tool_input.get("path", "")
        return f"file_path={path}"
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        return cmd[:120]
    if tool_name == "Read":
        return tool_input.get("file_path", "")
    # Generic fallback: first key=value pair
    for k, v in tool_input.items():
        return f"{k}={str(v)[:80]}"
    return ""
