"""
tests/test_git_checkpoint.py — pytest test suite for GitCheckpoint.

Covers:
- CheckpointMeta data model
- Branch name normalisation (agent_id / task_id sanitisation)
- ensure_branch() creates and checks out the WIP branch
- commit_checkpoint() writes a structured commit with Plan-Ref / Agent-Id / Task-Id trailers
- commit_checkpoint() writes .checkpoint_meta.json with correct fields
- commit_checkpoint() raises RuntimeError on clean working tree
- as_hook() returns an async PostToolUse hook that commits on file-mutating tools
- _summarise_tool_input() utility function

Integration tests spin up a real git repo in a tmp_path fixture so no mocking
of subprocess is required.

Run with:
    pytest tests/test_git_checkpoint.py -v
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

import pytest

from harness_tools.git_checkpoint import (
    CheckpointMeta,
    GitCheckpoint,
    _summarise_tool_input,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_repo(path: Path) -> None:
    """Initialise a minimal git repo with an initial commit."""
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@harness.local"],
        cwd=path, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Harness Test"],
        cwd=path, check=True, capture_output=True,
    )
    # Need at least one commit so that branch operations work
    readme = path / "README.md"
    readme.write_text("# test repo\n")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "--no-verify", "-m", "chore: initial commit"],
        cwd=path, check=True, capture_output=True,
    )


def _make_cp(
    tmp_path: Path,
    *,
    agent_id: str = "agent-01",
    task_id: str = "feat/auth",
    plan_ref: str = "Step 1 — scaffold",
    branch_prefix: str = "wip",
    auto_stage_all: bool = True,
) -> GitCheckpoint:
    """Return a GitCheckpoint instance backed by a real git repo in *tmp_path*."""
    _init_repo(tmp_path)
    return GitCheckpoint(
        agent_id=agent_id,
        task_id=task_id,
        plan_ref=plan_ref,
        repo_path=tmp_path,
        branch_prefix=branch_prefix,
        auto_stage_all=auto_stage_all,
    )


def _write_file(repo: Path, name: str = "change.txt", content: str = "hello\n") -> Path:
    """Write a file into the repo so there is something to stage/commit."""
    p = repo / name
    p.write_text(content)
    return p


def _current_branch(repo: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo, check=True, capture_output=True, text=True,
    )
    return result.stdout.strip()


def _commit_message(repo: Path) -> str:
    result = subprocess.run(
        ["git", "log", "-1", "--format=%B"],
        cwd=repo, check=True, capture_output=True, text=True,
    )
    return result.stdout


# ---------------------------------------------------------------------------
# CheckpointMeta — data model
# ---------------------------------------------------------------------------


class TestCheckpointMeta:
    def test_to_dict_contains_all_fields(self) -> None:
        meta = CheckpointMeta(
            agent_id="a1",
            task_id="t1",
            plan_ref="Step 1",
            branch="wip/a1/t1",
            commit_sha="abc123",
            timestamp="2026-01-01T00:00:00+00:00",
            checkpoint_index=1,
            tool_name="Edit",
            tool_input_summary="file_path=src/foo.py",
        )
        d = meta.to_dict()
        assert d["agent_id"] == "a1"
        assert d["task_id"] == "t1"
        assert d["plan_ref"] == "Step 1"
        assert d["branch"] == "wip/a1/t1"
        assert d["commit_sha"] == "abc123"
        assert d["timestamp"] == "2026-01-01T00:00:00+00:00"
        assert d["checkpoint_index"] == 1
        assert d["tool_name"] == "Edit"
        assert d["tool_input_summary"] == "file_path=src/foo.py"

    def test_to_dict_optional_fields_default_empty(self) -> None:
        meta = CheckpointMeta(
            agent_id="a",
            task_id="t",
            plan_ref="ref",
            branch="wip/a/t",
            commit_sha="sha",
            timestamp="ts",
            checkpoint_index=0,
        )
        assert meta.tool_name == ""
        assert meta.tool_input_summary == ""

    def test_to_dict_is_json_serialisable(self) -> None:
        meta = CheckpointMeta(
            agent_id="a", task_id="t", plan_ref="r", branch="b",
            commit_sha="s", timestamp="ts", checkpoint_index=1,
        )
        json.dumps(meta.to_dict())  # must not raise


# ---------------------------------------------------------------------------
# Branch name normalisation
# ---------------------------------------------------------------------------


class TestBranchNameNormalisation:
    def test_slashes_replaced_in_task_id(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path, agent_id="agent-01", task_id="feat/auth-refactor")
        assert "/" not in cp.branch.split("agent-01/")[1]

    def test_spaces_replaced_in_agent_id(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path, agent_id="my agent", task_id="task-1")
        assert " " not in cp.branch

    def test_branch_has_prefix(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path, branch_prefix="checkpoint", agent_id="a1", task_id="t1")
        assert cp.branch.startswith("checkpoint/")

    def test_branch_contains_agent_id(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path, agent_id="agent-42", task_id="t")
        assert "agent-42" in cp.branch

    def test_branch_contains_task_id_slug(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path, agent_id="a", task_id="feat/my-task")
        # Slashes become hyphens
        assert "feat-my-task" in cp.branch

    def test_branch_is_cached(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path)
        assert cp.branch is cp.branch  # same object returned each time

    def test_special_chars_stripped(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path, agent_id="agent@42!", task_id="task#1")
        # Branch name should not contain special chars
        forbidden = set("@!# ")
        assert not forbidden.intersection(cp.branch)


# ---------------------------------------------------------------------------
# ensure_branch()
# ---------------------------------------------------------------------------


class TestEnsureBranch:
    def test_creates_new_branch(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path)
        branch = cp.ensure_branch()
        assert _current_branch(tmp_path) == branch

    def test_returns_branch_name(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path)
        result = cp.ensure_branch()
        assert result == cp.branch

    def test_idempotent_second_call(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path)
        b1 = cp.ensure_branch()
        b2 = cp.ensure_branch()
        assert b1 == b2
        assert _current_branch(tmp_path) == b1

    def test_branch_name_matches_property(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path, agent_id="a99", task_id="my-task")
        cp.ensure_branch()
        assert _current_branch(tmp_path) == cp.branch


# ---------------------------------------------------------------------------
# commit_checkpoint() — commit message structure
# ---------------------------------------------------------------------------


class TestCommitCheckpointMessage:
    def test_subject_contains_task_id(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path)
        cp.ensure_branch()
        _write_file(tmp_path)
        cp.commit_checkpoint("wrote auth module")
        msg = _commit_message(tmp_path)
        assert "feat/auth" in msg or "feat-auth" in msg

    def test_subject_contains_checkpoint_number(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path)
        cp.ensure_branch()
        _write_file(tmp_path)
        cp.commit_checkpoint("first change")
        msg = _commit_message(tmp_path)
        assert "#1" in msg

    def test_plan_ref_trailer_present(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path, plan_ref="Step 3 — harden validator")
        cp.ensure_branch()
        _write_file(tmp_path)
        cp.commit_checkpoint("harden validator")
        msg = _commit_message(tmp_path)
        assert "Plan-Ref:" in msg
        assert "Step 3 — harden validator" in msg

    def test_agent_id_trailer_present(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path, agent_id="agent-42")
        cp.ensure_branch()
        _write_file(tmp_path)
        cp.commit_checkpoint("scaffolded CLI")
        msg = _commit_message(tmp_path)
        assert "Agent-Id:" in msg
        assert "agent-42" in msg

    def test_task_id_trailer_present(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path, task_id="feat/auth-refactor")
        cp.ensure_branch()
        _write_file(tmp_path)
        cp.commit_checkpoint("auth refactor")
        msg = _commit_message(tmp_path)
        assert "Task-Id:" in msg
        assert "feat/auth-refactor" in msg

    def test_tool_name_in_body(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path)
        cp.ensure_branch()
        _write_file(tmp_path)
        cp.commit_checkpoint("ran tests", tool_name="Bash")
        msg = _commit_message(tmp_path)
        assert "Bash" in msg

    def test_tool_input_summary_in_body(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path)
        cp.ensure_branch()
        _write_file(tmp_path)
        cp.commit_checkpoint("wrote file", tool_input_summary="file_path=src/foo.py")
        msg = _commit_message(tmp_path)
        assert "src/foo.py" in msg

    def test_checkpoint_index_increments(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path)
        cp.ensure_branch()
        _write_file(tmp_path, "f1.txt")
        cp.commit_checkpoint("first")
        _write_file(tmp_path, "f2.txt")
        meta2 = cp.commit_checkpoint("second")
        assert meta2.checkpoint_index == 2

    def test_wip_prefix_in_subject(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path)
        cp.ensure_branch()
        _write_file(tmp_path)
        cp.commit_checkpoint("scaffolded")
        msg = _commit_message(tmp_path)
        first_line = msg.split("\n")[0]
        assert first_line.startswith("wip(")


# ---------------------------------------------------------------------------
# commit_checkpoint() — metadata file
# ---------------------------------------------------------------------------


class TestCommitCheckpointMeta:
    def test_meta_file_created(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path)
        cp.ensure_branch()
        _write_file(tmp_path)
        cp.commit_checkpoint("wrote code")
        assert (tmp_path / ".checkpoint_meta.json").exists()

    def test_meta_file_valid_json(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path)
        cp.ensure_branch()
        _write_file(tmp_path)
        cp.commit_checkpoint("wrote code")
        content = (tmp_path / ".checkpoint_meta.json").read_text()
        data = json.loads(content)
        assert isinstance(data, dict)

    def test_meta_agent_id_matches(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path, agent_id="agent-99")
        cp.ensure_branch()
        _write_file(tmp_path)
        cp.commit_checkpoint("test")
        data = json.loads((tmp_path / ".checkpoint_meta.json").read_text())
        assert data["agent_id"] == "agent-99"

    def test_meta_task_id_matches(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path, task_id="feat/my-feature")
        cp.ensure_branch()
        _write_file(tmp_path)
        cp.commit_checkpoint("test")
        data = json.loads((tmp_path / ".checkpoint_meta.json").read_text())
        assert data["task_id"] == "feat/my-feature"

    def test_meta_plan_ref_matches(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path, plan_ref="Step 7 — deploy")
        cp.ensure_branch()
        _write_file(tmp_path)
        cp.commit_checkpoint("test")
        data = json.loads((tmp_path / ".checkpoint_meta.json").read_text())
        assert data["plan_ref"] == "Step 7 — deploy"

    def test_meta_branch_matches(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path)
        cp.ensure_branch()
        _write_file(tmp_path)
        cp.commit_checkpoint("test")
        data = json.loads((tmp_path / ".checkpoint_meta.json").read_text())
        assert data["branch"] == cp.branch

    def test_meta_commit_sha_is_40_chars(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path)
        cp.ensure_branch()
        _write_file(tmp_path)
        cp.commit_checkpoint("test")
        data = json.loads((tmp_path / ".checkpoint_meta.json").read_text())
        assert len(data["commit_sha"]) == 40

    def test_meta_timestamp_present(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path)
        cp.ensure_branch()
        _write_file(tmp_path)
        cp.commit_checkpoint("test")
        data = json.loads((tmp_path / ".checkpoint_meta.json").read_text())
        assert data["timestamp"]
        # Should look like an ISO-8601 datetime
        assert "T" in data["timestamp"]

    def test_meta_checkpoint_index_starts_at_1(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path)
        cp.ensure_branch()
        _write_file(tmp_path)
        cp.commit_checkpoint("first")
        data = json.loads((tmp_path / ".checkpoint_meta.json").read_text())
        assert data["checkpoint_index"] == 1

    def test_meta_tool_name_stored(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path)
        cp.ensure_branch()
        _write_file(tmp_path)
        cp.commit_checkpoint("test", tool_name="Write")
        data = json.loads((tmp_path / ".checkpoint_meta.json").read_text())
        assert data["tool_name"] == "Write"

    def test_meta_tool_input_summary_truncated_at_120(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path)
        cp.ensure_branch()
        _write_file(tmp_path)
        long_summary = "x" * 200
        cp.commit_checkpoint("test", tool_input_summary=long_summary)
        data = json.loads((tmp_path / ".checkpoint_meta.json").read_text())
        assert len(data["tool_input_summary"]) <= 120

    def test_returned_meta_matches_file(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path, agent_id="a1", task_id="t1", plan_ref="ref")
        cp.ensure_branch()
        _write_file(tmp_path)
        meta = cp.commit_checkpoint("check consistency")
        file_data = json.loads((tmp_path / ".checkpoint_meta.json").read_text())
        assert meta.agent_id == file_data["agent_id"]
        assert meta.task_id == file_data["task_id"]
        assert meta.commit_sha == file_data["commit_sha"]


# ---------------------------------------------------------------------------
# commit_checkpoint() — error handling
# ---------------------------------------------------------------------------


class TestCommitCheckpointErrors:
    def test_raises_on_clean_working_tree(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path)
        cp.ensure_branch()
        # No files written — tree should be clean
        with pytest.raises(RuntimeError, match="Nothing to commit"):
            cp.commit_checkpoint("empty checkpoint")

    def test_multiple_checkpoints_in_sequence(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path)
        cp.ensure_branch()
        for i in range(3):
            _write_file(tmp_path, f"file-{i}.txt", f"content {i}\n")
            meta = cp.commit_checkpoint(f"step {i+1}")
            assert meta.checkpoint_index == i + 1


# ---------------------------------------------------------------------------
# as_hook() — PostToolUse async hook
# ---------------------------------------------------------------------------


class TestAsHook:
    def test_hook_commits_on_edit(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path)
        cp.ensure_branch()
        # Write a file so there is something to commit
        _write_file(tmp_path, "edited.txt")

        hook = cp.as_hook()
        input_data = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "edited.txt"},
        }

        async def run():
            return await hook(input_data, "tid-1", {})

        asyncio.run(run())
        # A commit should now exist on the branch
        assert cp._checkpoint_index == 1

    def test_hook_silently_skips_clean_tree(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path)
        cp.ensure_branch()
        # Do NOT write any file — tree is clean

        hook = cp.as_hook()
        input_data = {"tool_name": "Read", "tool_input": {"file_path": "README.md"}}

        async def run():
            return await hook(input_data, "tid-2", {})

        asyncio.run(run())  # Must not raise
        assert cp._checkpoint_index == 0  # No commit made

    def test_hook_returns_dict(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path)
        cp.ensure_branch()
        _write_file(tmp_path)

        hook = cp.as_hook()

        async def run():
            return await hook(
                {"tool_name": "Write", "tool_input": {"file_path": "x.txt"}},
                "tid-3", {},
            )

        result = asyncio.run(run())
        assert isinstance(result, dict)

    def test_hook_increments_checkpoint_index(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path)
        cp.ensure_branch()
        hook = cp.as_hook()

        async def run():
            for i in range(3):
                _write_file(tmp_path, f"hook-{i}.txt")
                await hook(
                    {"tool_name": "Write", "tool_input": {"file_path": f"hook-{i}.txt"}},
                    f"tid-{i}", {},
                )

        asyncio.run(run())
        assert cp._checkpoint_index == 3


# ---------------------------------------------------------------------------
# _summarise_tool_input() utility
# ---------------------------------------------------------------------------


class TestSummariseToolInput:
    def test_edit_returns_file_path(self) -> None:
        result = _summarise_tool_input("Edit", {"file_path": "src/auth.py"})
        assert "src/auth.py" in result

    def test_write_returns_file_path(self) -> None:
        result = _summarise_tool_input("Write", {"file_path": "src/cli.py"})
        assert "src/cli.py" in result

    def test_bash_returns_command(self) -> None:
        result = _summarise_tool_input("Bash", {"command": "pytest tests/ -v"})
        assert "pytest" in result

    def test_bash_truncates_at_120(self) -> None:
        long_cmd = "echo " + "x" * 200
        result = _summarise_tool_input("Bash", {"command": long_cmd})
        assert len(result) <= 120

    def test_read_returns_file_path(self) -> None:
        result = _summarise_tool_input("Read", {"file_path": "README.md"})
        assert "README.md" in result

    def test_generic_tool_returns_first_kv(self) -> None:
        result = _summarise_tool_input("Glob", {"pattern": "**/*.py"})
        assert "**/*.py" in result

    def test_empty_input_returns_empty_string(self) -> None:
        result = _summarise_tool_input("UnknownTool", {})
        assert result == ""


# ---------------------------------------------------------------------------
# Multi-agent traceability — commit trailers carry agent_id and task_id
# ---------------------------------------------------------------------------


class TestMultiAgentTraceability:
    """Verify that every checkpoint commit carries the structured trailers
    required for multi-agent traceability."""

    def test_all_three_trailers_present(self, tmp_path: Path) -> None:
        cp = _make_cp(
            tmp_path,
            agent_id="agent-77",
            task_id="sprint/feature-42",
            plan_ref="Step 2 — write unit tests",
        )
        cp.ensure_branch()
        _write_file(tmp_path)
        cp.commit_checkpoint("wrote tests")
        msg = _commit_message(tmp_path)
        assert "Plan-Ref:" in msg
        assert "Agent-Id:" in msg
        assert "Task-Id:" in msg

    def test_second_agent_commits_carry_its_own_trailers(self, tmp_path: Path) -> None:
        """Two independent GitCheckpoint instances must each stamp their own
        agent_id / task_id in the meta file."""
        # Agent A
        repo_a = tmp_path / "repo-a"
        cp_a = _make_cp(repo_a, agent_id="agent-A", task_id="task-alpha")
        cp_a.ensure_branch()
        _write_file(repo_a)
        cp_a.commit_checkpoint("agent A work")
        meta_a = json.loads((repo_a / ".checkpoint_meta.json").read_text())

        # Agent B in a separate repo
        repo_b = tmp_path / "repo-b"
        cp_b = _make_cp(repo_b, agent_id="agent-B", task_id="task-beta")
        cp_b.ensure_branch()
        _write_file(repo_b)
        cp_b.commit_checkpoint("agent B work")
        meta_b = json.loads((repo_b / ".checkpoint_meta.json").read_text())

        assert meta_a["agent_id"] == "agent-A"
        assert meta_a["task_id"] == "task-alpha"
        assert meta_b["agent_id"] == "agent-B"
        assert meta_b["task_id"] == "task-beta"

    def test_branch_name_encodes_agent_and_task(self, tmp_path: Path) -> None:
        cp = _make_cp(tmp_path, agent_id="orchestrator-1", task_id="harness-task-007")
        assert "orchestrator-1" in cp.branch
        assert "harness-task-007" in cp.branch
