<<<<<<< HEAD
"""Unit tests for harness_telemetry.HarnessTelemetry.

Covers:
  - Atomic flush / load round-trip
  - Session lifecycle (start → finalise → totals merge)
  - Hook callbacks: _on_read, _on_glob, _on_grep, _on_user_prompt,
                    _on_bash_post, _on_bash_failure
  - Gate-failure detection heuristics
  - Reset wipes all data
  - Session deduplication (same session_id → latest record wins)
  - CLI entry-point smoke test
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from harness_telemetry import (
    HarnessTelemetry,
    _identify_gate,
    _is_harness_artifact,
    _output_indicates_failure,
)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_tel(tmp_path: Path) -> HarnessTelemetry:
    """Return a fresh HarnessTelemetry writing to a temp directory."""
    out = tmp_path / "docs" / "harness-telemetry.json"
    return HarnessTelemetry(output_path=out, cwd=tmp_path)


def _run(coro):  # type: ignore[return]
    """Run an async coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ── Fixture ───────────────────────────────────────────────────────────────────


@pytest.fixture()
def tel(tmp_path: Path) -> HarnessTelemetry:
    t = _make_tel(tmp_path)
    t.build_hooks(session_id="test-session-1")
    return t


# ── Tests: flush / load round-trip ────────────────────────────────────────────


class TestFlushLoad:
    """Data written by flush() must survive a reload."""

    def test_flush_creates_parent_dirs(self, tmp_path: Path) -> None:
        out = tmp_path / "deeply" / "nested" / "docs" / "tel.json"
        t = HarnessTelemetry(output_path=out, cwd=tmp_path)
        t.build_hooks(session_id="s1")
        t.flush()
        assert out.exists()

    def test_flush_writes_valid_json(self, tmp_path: Path, tel: HarnessTelemetry) -> None:
        tel.flush()
        raw = tel.output_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        assert data["schema_version"] == "1.0"
        assert "totals" in data
        assert "sessions" in data

    def test_flush_is_atomic(self, tmp_path: Path, tel: HarnessTelemetry) -> None:
        """No .tmp file should be left behind after a successful flush."""
        tel.flush()
        tmp_file = tel.output_path.with_suffix(".tmp")
        assert not tmp_file.exists()

    def test_reload_restores_totals(self, tmp_path: Path) -> None:
        out = tmp_path / "docs" / "t.json"
        t1 = HarnessTelemetry(output_path=out, cwd=tmp_path)
        t1.build_hooks(session_id="s1")
        _run(t1._on_read({"tool_input": {"file_path": str(tmp_path / "CLAUDE.md")}}))
        t1.flush()

        # Second instance loads existing file.
        t2 = HarnessTelemetry(output_path=out, cwd=tmp_path)
        assert t2._data["totals"]["artifact_reads"]  # at least one entry from t1


# ── Tests: session lifecycle ───────────────────────────────────────────────────


class TestSessionLifecycle:
    """Per-session counters must be merged into totals on flush."""

    def test_session_record_appended(self, tmp_path: Path, tel: HarnessTelemetry) -> None:
        tel.flush()
        data = json.loads(tel.output_path.read_text())
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["session_id"] == "test-session-1"

    def test_totals_accumulate_across_sessions(self, tmp_path: Path) -> None:
        out = tmp_path / "docs" / "t.json"
        for i in range(3):
            t = HarnessTelemetry(output_path=out, cwd=tmp_path)
            t.build_hooks(session_id=f"sess-{i}")
            t._session_commands["check-code"] += 1
            t.flush()

        data = json.loads(out.read_text())
        assert data["totals"]["cli_command_invocations"]["check-code"] == 3
        assert len(data["sessions"]) == 3

    def test_session_deduplication(self, tmp_path: Path) -> None:
        """Flushing the same session_id twice replaces the earlier record."""
        out = tmp_path / "docs" / "t.json"
        t = HarnessTelemetry(output_path=out, cwd=tmp_path)
        t.build_hooks(session_id="dupe-session")
        t._session_gates["ruff"] += 1
        t.flush()

        # Second flush with same session_id — simulate reload + re-flush.
        t2 = HarnessTelemetry(output_path=out, cwd=tmp_path)
        t2.build_hooks(session_id="dupe-session")
        t2._session_gates["ruff"] += 5
        t2.flush()

        data = json.loads(out.read_text())
        # Only one session record for this id.
        matching = [s for s in data["sessions"] if s["session_id"] == "dupe-session"]
        assert len(matching) == 1


# ── Tests: hook callbacks ──────────────────────────────────────────────────────


class TestReadHook:
    """_on_read must track harness file paths relative to cwd."""

    def test_tracks_claude_md(self, tmp_path: Path, tel: HarnessTelemetry) -> None:
        path = str(tmp_path / "CLAUDE.md")
        _run(tel._on_read({"tool_input": {"file_path": path}}))
        assert tel._session_artifacts.get("CLAUDE.md", 0) == 1

    def test_counts_multiple_reads(self, tmp_path: Path, tel: HarnessTelemetry) -> None:
        path = str(tmp_path / "PRINCIPLES.md")
        _run(tel._on_read({"tool_input": {"file_path": path}}))
        _run(tel._on_read({"tool_input": {"file_path": path}}))
        assert tel._session_artifacts["PRINCIPLES.md"] == 2

    def test_ignores_venv_paths(self, tmp_path: Path, tel: HarnessTelemetry) -> None:
        path = str(tmp_path / ".venv" / "lib" / "site.py")
        _run(tel._on_read({"tool_input": {"file_path": path}}))
        # Nothing in _session_artifacts should reference .venv
        for key in tel._session_artifacts:
            assert ".venv" not in key


class TestGlobHook:
    """_on_glob must record the pattern and any returned harness file paths."""

    def test_records_glob_pattern(self, tmp_path: Path, tel: HarnessTelemetry) -> None:
        _run(tel._on_glob({"tool_input": {"pattern": "**/*.md"}}))
        assert "[glob] **/*.md" in tel._session_artifacts

    def test_records_returned_harness_files(self, tmp_path: Path, tel: HarnessTelemetry) -> None:
        output = "CLAUDE.md\n.claude/commands/harness/telemetry.md\n"
        _run(tel._on_glob({"tool_input": {"pattern": "**/*.md"}, "tool_output": output}))
        keys = list(tel._session_artifacts.keys())
        assert any("telemetry.md" in k for k in keys)


class TestGrepHook:
    """_on_grep must record pattern + optional directory."""

    def test_records_grep_key(self, tmp_path: Path, tel: HarnessTelemetry) -> None:
        _run(tel._on_grep({"tool_input": {"pattern": "HarnessTelemetry", "path": "."}}))
        keys = list(tel._session_artifacts.keys())
        assert any("HarnessTelemetry" in k for k in keys)

    def test_grep_without_path(self, tmp_path: Path, tel: HarnessTelemetry) -> None:
        _run(tel._on_grep({"tool_input": {"pattern": "ruff"}}))
        assert "[grep] ruff" in tel._session_artifacts


class TestUserPromptHook:
    """_on_user_prompt must detect /command patterns."""

    @pytest.mark.parametrize(
        "prompt, expected_cmd",
        [
            ("/check-code", "check-code"),
            # The slash-command regex matches [a-z][a-z0-9-]* — stops at ':',
            # so "/harness:lint" captures "harness", not "harness:lint".
            ("/harness:lint some args", "harness"),
            ("/coordinate", "coordinate"),
        ],
    )
    def test_detects_slash_command(
        self, prompt: str, expected_cmd: str, tel: HarnessTelemetry
    ) -> None:
        _run(tel._on_user_prompt({"prompt": prompt}))
        assert tel._session_commands.get(expected_cmd, 0) == 1

    def test_ignores_non_command_prompt(self, tel: HarnessTelemetry) -> None:
        _run(tel._on_user_prompt({"prompt": "Please fix the bug in main.py"}))
        assert not tel._session_commands

    def test_counts_multiple_invocations(self, tel: HarnessTelemetry) -> None:
        for _ in range(4):
            _run(tel._on_user_prompt({"prompt": "/check-code"}))
        assert tel._session_commands["check-code"] == 4


class TestBashHooks:
    """Bash hooks must detect gate failures from output and hard errors."""

    def test_ruff_failure_detected(self, tel: HarnessTelemetry) -> None:
        _run(
            tel._on_bash_post(
                {
                    "tool_input": {"command": "ruff check ."},
                    "tool_output": "Found 3 errors.",
                }
            )
        )
        assert tel._session_gates.get("ruff", 0) == 1

    def test_ruff_clean_not_detected(self, tel: HarnessTelemetry) -> None:
        _run(
            tel._on_bash_post(
                {
                    "tool_input": {"command": "ruff check ."},
                    "tool_output": "All checks passed.",
                }
            )
        )
        assert tel._session_gates.get("ruff", 0) == 0

    def test_pytest_failure_detected(self, tel: HarnessTelemetry) -> None:
        _run(
            tel._on_bash_post(
                {
                    "tool_input": {"command": "pytest tests/ -v"},
                    "tool_output": "2 failed, 5 passed",
                }
            )
        )
        assert tel._session_gates.get("pytest", 0) == 1

    def test_mypy_failure_detected(self, tel: HarnessTelemetry) -> None:
        _run(
            tel._on_bash_post(
                {
                    "tool_input": {"command": "mypy harness_skills/"},
                    "tool_output": "harness_skills/foo.py:5: error: Missing return type",
                }
            )
        )
        assert tel._session_gates.get("mypy", 0) == 1

    def test_bash_failure_hook_uses_gate_name(self, tel: HarnessTelemetry) -> None:
        _run(tel._on_bash_failure({"tool_input": {"command": "ruff format ."}}))
        assert tel._session_gates.get("ruff-format", 0) == 1

    def test_bash_failure_hook_unknown_command(self, tel: HarnessTelemetry) -> None:
        _run(tel._on_bash_failure({"tool_input": {"command": "custom-script.sh"}}))
        assert tel._session_gates.get("bash-failure", 0) == 1


# ── Tests: reset ──────────────────────────────────────────────────────────────


class TestReset:
    """reset() must wipe all data and overwrite the file."""

    def test_reset_clears_sessions(self, tmp_path: Path) -> None:
        out = tmp_path / "docs" / "t.json"
        t = HarnessTelemetry(output_path=out, cwd=tmp_path)
        t.build_hooks(session_id="s1")
        t._session_commands["check-code"] += 2
        t.flush()

        # Reset via a *new* instance that has no pending session so that
        # _finalise_session() is a no-op and the file is truly wiped.
        t2 = HarnessTelemetry(output_path=out, cwd=tmp_path)
        t2.reset()
        data = json.loads(out.read_text())
        assert data["sessions"] == []
        assert data["totals"]["cli_command_invocations"] == {}
        assert data["totals"]["artifact_reads"] == {}
        assert data["totals"]["gate_failures"] == {}


# ── Tests: utility functions ───────────────────────────────────────────────────


class TestIdentifyGate:
    @pytest.mark.parametrize(
        "command, expected",
        [
            ("ruff check .", "ruff"),
            ("ruff format .", "ruff-format"),
            ("mypy harness_skills", "mypy"),
            ("pytest tests/ -v", "pytest"),
            ("check-code", "check-code"),
            ("git commit -m 'fix'", ""),
            ("ls -la", ""),
        ],
    )
    def test_gate_mapping(self, command: str, expected: str) -> None:
        assert _identify_gate(command) == expected


class TestOutputIndicatesFailure:
    @pytest.mark.parametrize(
        "output, expected",
        [
            ("Found 3 errors.", True),
            ("Found 1 error", True),
            ("All checks passed.", False),
            ("2 failed, 5 passed", True),
            ("FAILED tests/test_foo.py::test_bar", True),
            ("AssertionError: expected True", True),
            ("exit code 1", True),
            ("returned non-zero exit status 2", True),
            ("No issues found.", False),
            ("", False),
        ],
    )
    def test_failure_detection(self, output: str, expected: bool) -> None:
        assert _output_indicates_failure(output) == expected


class TestIsHarnessArtifact:
    @pytest.mark.parametrize(
        "path, expected",
        [
            ("CLAUDE.md", True),
            ("PRINCIPLES.md", True),
            (".claude/commands/harness/telemetry.md", True),
            ("docs/harness-changelog.md", True),
            ("harness_skills/boot.py", True),
            (".venv/lib/python3.12/site-packages/foo.py", False),
            ("src/main.py", True),
        ],
    )
    def test_artifact_classification(self, path: str, expected: bool) -> None:
        assert _is_harness_artifact(path) == expected


# ── Tests: show() smoke test ──────────────────────────────────────────────────


class TestShow:
    """show() must print without raising exceptions."""

    def test_show_empty(self, tmp_path: Path, capsys) -> None:
        t = _make_tel(tmp_path)
        t.build_hooks(session_id="s1")
        t.show()
        out = capsys.readouterr().out
        assert "Harness Telemetry" in out
        assert "none recorded" in out

    def test_show_with_data(self, tmp_path: Path, capsys) -> None:
        t = _make_tel(tmp_path)
        t.build_hooks(session_id="s1")
        t._session_artifacts["CLAUDE.md"] = 5
        t._session_commands["check-code"] = 3
        t._session_gates["ruff"] = 7
        t.flush()

        t2 = HarnessTelemetry(output_path=t.output_path, cwd=tmp_path)
        t2.show()
        out = capsys.readouterr().out
        assert "CLAUDE.md" in out
        assert "check-code" in out
        assert "ruff" in out
||||||| 0e893bd
=======
"""
tests/test_telemetry.py
=======================
Pytest test suite for harness telemetry — both the hook collector
(``harness_telemetry.HarnessTelemetry``) and the analytics reporter
(``harness_skills.telemetry_reporter``).

Run with:
    pytest tests/test_telemetry.py -v
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from harness_telemetry import (
    HarnessTelemetry,
    _identify_gate,
    _is_harness_artifact,
    _merge_counts,
    _output_indicates_failure,
)
from harness_skills.telemetry_reporter import build_report, render_report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro: Any) -> Any:
    """Run a coroutine synchronously inside tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Unit tests — pure helper functions
# ---------------------------------------------------------------------------


class TestIsHarnessArtifact:
    def test_claude_commands_dir(self) -> None:
        assert _is_harness_artifact(".claude/commands/check-code.md") is True

    def test_docs_dir(self) -> None:
        assert _is_harness_artifact("docs/harness-telemetry.json") is True

    def test_skills_dir(self) -> None:
        assert _is_harness_artifact("skills/perf_hooks.py") is True

    def test_harness_skills_package(self) -> None:
        assert _is_harness_artifact("harness_skills/telemetry.py") is True

    def test_root_level_md(self) -> None:
        assert _is_harness_artifact("CLAUDE.md") is True

    def test_root_level_yaml(self) -> None:
        assert _is_harness_artifact("harness.config.yaml") is True

    def test_venv_excluded(self) -> None:
        assert _is_harness_artifact(".venv/lib/site-packages/foo.py") is False

    def test_deep_unknown_dir(self) -> None:
        # A file deep in an unknown directory that has a non-harness extension
        # is NOT a harness artifact.
        assert _is_harness_artifact("some/random/path/binary.exe") is False

    def test_deep_py_file_qualifies_by_extension(self) -> None:
        # Any .py file outside of .venv is considered a harness artifact by extension.
        assert _is_harness_artifact("some/deep/path/module.py") is True


class TestIdentifyGate:
    def test_ruff_check(self) -> None:
        assert _identify_gate("uv run ruff check .") == "ruff"

    def test_ruff_format(self) -> None:
        assert _identify_gate("uv run ruff format .") == "ruff-format"

    def test_ruff_bare(self) -> None:
        assert _identify_gate("ruff .") == "ruff"

    def test_mypy(self) -> None:
        assert _identify_gate("mypy harness_skills/") == "mypy"

    def test_pytest(self) -> None:
        assert _identify_gate("pytest tests/ -v") == "pytest"

    def test_check_code(self) -> None:
        assert _identify_gate("/check-code --strict") == "check-code"

    def test_unknown_command(self) -> None:
        assert _identify_gate("ls -la") == ""

    def test_empty_string(self) -> None:
        assert _identify_gate("") == ""

    def test_case_insensitive(self) -> None:
        assert _identify_gate("PYTEST tests/") == "pytest"


class TestOutputIndicatesFailure:
    def test_ruff_found_errors(self) -> None:
        assert _output_indicates_failure("Found 3 errors.\nfoo.py:1:1: E501") is True

    def test_ruff_no_errors(self) -> None:
        assert _output_indicates_failure("All checks passed.") is False

    def test_mypy_error(self) -> None:
        assert _output_indicates_failure("foo.py:5: error: Argument 1 ...") is True

    def test_pytest_failed(self) -> None:
        assert _output_indicates_failure("FAILED tests/test_foo.py::test_bar") is True

    def test_pytest_summary_failed(self) -> None:
        assert _output_indicates_failure("3 failed, 10 passed") is True

    def test_assertion_error(self) -> None:
        assert _output_indicates_failure("AssertionError: expected 1, got 2") is True

    def test_exit_code_1(self) -> None:
        assert _output_indicates_failure("Process exited with exit code 1") is True

    def test_exit_code_2(self) -> None:
        assert _output_indicates_failure("Exited with exit code 2") is True

    def test_nonzero_exit_regex(self) -> None:
        assert _output_indicates_failure("Process returned non-zero exit status 127") is True

    def test_clean_output(self) -> None:
        assert _output_indicates_failure("All tests passed. 42 passed in 1.23s") is False


class TestMergeCounts:
    def test_basic_merge(self) -> None:
        target: dict[str, int] = {"a": 1, "b": 2}
        _merge_counts(target, {"b": 3, "c": 4})
        assert target == {"a": 1, "b": 5, "c": 4}

    def test_empty_source(self) -> None:
        target: dict[str, int] = {"a": 1}
        _merge_counts(target, {})
        assert target == {"a": 1}

    def test_empty_target(self) -> None:
        target: dict[str, int] = {}
        _merge_counts(target, {"x": 7})
        assert target == {"x": 7}


# ---------------------------------------------------------------------------
# HarnessTelemetry — hook integration tests
# ---------------------------------------------------------------------------


@pytest.fixture
def tel(tmp_path: Path) -> HarnessTelemetry:
    """A fresh HarnessTelemetry backed by a temporary directory."""
    return HarnessTelemetry(
        output_path=tmp_path / "telemetry.json",
        cwd=tmp_path,
    )


class TestBuildHooks:
    def test_returns_required_hook_keys(self, tel: HarnessTelemetry) -> None:
        hooks = tel.build_hooks()
        assert "SessionStart" in hooks
        assert "SessionEnd" in hooks
        assert "Stop" in hooks
        assert "UserPromptSubmit" in hooks
        assert "PostToolUse" in hooks
        assert "PostToolUseFailure" in hooks

    def test_post_tool_use_has_read_glob_grep_bash(self, tel: HarnessTelemetry) -> None:
        hooks = tel.build_hooks()
        matchers = [entry["matcher"] for entry in hooks["PostToolUse"]]
        assert "Read" in matchers
        assert "Glob" in matchers
        assert "Grep" in matchers
        assert "Bash" in matchers

    def test_multiple_calls_reset_session_counters(self, tel: HarnessTelemetry) -> None:
        tel.build_hooks()
        _run(tel._on_user_prompt({"prompt": "/check-code"}))
        tel.build_hooks()  # second call — resets counters
        assert dict(tel._session_commands) == {}


class TestArtifactTracking:
    def test_on_read_tracks_harness_file(self, tel: HarnessTelemetry, tmp_path: Path) -> None:
        tel.build_hooks()
        artifact = tmp_path / "CLAUDE.md"
        artifact.touch()
        _run(tel._on_read({"tool_input": {"file_path": str(artifact)}}))
        assert "CLAUDE.md" in tel._session_artifacts

    def test_on_read_increments_count(self, tel: HarnessTelemetry, tmp_path: Path) -> None:
        tel.build_hooks()
        artifact = tmp_path / "CLAUDE.md"
        artifact.touch()
        event = {"tool_input": {"file_path": str(artifact)}}
        _run(tel._on_read(event))
        _run(tel._on_read(event))
        assert tel._session_artifacts["CLAUDE.md"] == 2

    def test_on_glob_records_pattern(self, tel: HarnessTelemetry) -> None:
        tel.build_hooks()
        _run(tel._on_glob({"tool_input": {"pattern": "**/*.md"}}))
        assert "[glob] **/*.md" in tel._session_artifacts

    def test_on_glob_also_records_output_files(self, tel: HarnessTelemetry) -> None:
        tel.build_hooks()
        _run(
            tel._on_glob(
                {
                    "tool_input": {"pattern": "docs/*.md"},
                    "tool_output": "docs/harness-telemetry.json\ndocs/design.md",
                }
            )
        )
        # The pattern key must exist
        assert "[glob] docs/*.md" in tel._session_artifacts
        # Output files are relativised; when the path can't be made relative to
        # cwd (tmp_path), _relativise falls back to the basename only.
        assert "design.md" in tel._session_artifacts

    def test_on_grep_records_pattern_key(self, tel: HarnessTelemetry, tmp_path: Path) -> None:
        tel.build_hooks()
        # Use a named subdirectory so _relativise can produce a stable relative key.
        search_dir = tmp_path / "harness_skills"
        search_dir.mkdir()
        _run(tel._on_grep({"tool_input": {"pattern": "artifact_reads", "path": str(search_dir)}}))
        key = "[grep] artifact_reads in harness_skills"
        assert key in tel._session_artifacts


class TestCommandTracking:
    def test_slash_command_is_counted(self, tel: HarnessTelemetry) -> None:
        tel.build_hooks()
        _run(tel._on_user_prompt({"prompt": "/check-code"}))
        assert tel._session_commands["check-code"] == 1

    def test_slash_command_with_args(self, tel: HarnessTelemetry) -> None:
        tel.build_hooks()
        # The regex captures [a-z0-9-]+ — colons stop the match, so
        # "/harness:lint" records the token "harness" (everything before ":").
        _run(tel._on_user_prompt({"prompt": "/harness:lint --fix"}))
        assert tel._session_commands["harness"] == 1

    def test_non_command_prompt_ignored(self, tel: HarnessTelemetry) -> None:
        tel.build_hooks()
        _run(tel._on_user_prompt({"prompt": "What is the build command?"}))
        assert dict(tel._session_commands) == {}

    def test_empty_prompt_ignored(self, tel: HarnessTelemetry) -> None:
        tel.build_hooks()
        _run(tel._on_user_prompt({"prompt": ""}))
        assert dict(tel._session_commands) == {}

    def test_multiple_invocations_accumulate(self, tel: HarnessTelemetry) -> None:
        tel.build_hooks()
        for _ in range(3):
            _run(tel._on_user_prompt({"prompt": "/check-code"}))
        assert tel._session_commands["check-code"] == 3


class TestGateFailureTracking:
    def test_ruff_failure_detected(self, tel: HarnessTelemetry) -> None:
        tel.build_hooks()
        _run(
            tel._on_bash_post(
                {
                    "tool_input": {"command": "uv run ruff check ."},
                    "tool_output": "Found 5 errors.\nfoo.py:1:1: E501",
                }
            )
        )
        assert tel._session_gates["ruff"] == 1

    def test_ruff_clean_not_counted(self, tel: HarnessTelemetry) -> None:
        tel.build_hooks()
        _run(
            tel._on_bash_post(
                {
                    "tool_input": {"command": "uv run ruff check ."},
                    "tool_output": "All checks passed.",
                }
            )
        )
        assert "ruff" not in tel._session_gates

    def test_mypy_failure_detected(self, tel: HarnessTelemetry) -> None:
        tel.build_hooks()
        _run(
            tel._on_bash_post(
                {
                    "tool_input": {"command": "mypy harness_skills/"},
                    "tool_output": "harness_skills/foo.py:10: error: Missing return type",
                }
            )
        )
        assert tel._session_gates["mypy"] == 1

    def test_pytest_failure_detected(self, tel: HarnessTelemetry) -> None:
        tel.build_hooks()
        _run(
            tel._on_bash_post(
                {
                    "tool_input": {"command": "pytest tests/ -v"},
                    "tool_output": "FAILED tests/test_foo.py::test_bar - AssertionError",
                }
            )
        )
        assert tel._session_gates["pytest"] == 1

    def test_bash_hard_failure_counted(self, tel: HarnessTelemetry) -> None:
        tel.build_hooks()
        _run(
            tel._on_bash_failure(
                {"tool_input": {"command": "mypy harness_skills/"}}
            )
        )
        assert tel._session_gates["mypy"] == 1

    def test_unknown_bash_failure_bucketed(self, tel: HarnessTelemetry) -> None:
        tel.build_hooks()
        _run(tel._on_bash_failure({"tool_input": {"command": "some-unknown-tool"}}))
        assert tel._session_gates["bash-failure"] == 1


# ---------------------------------------------------------------------------
# HarnessTelemetry — persistence (flush / load round-trip)
# ---------------------------------------------------------------------------


class TestFlushAndLoad:
    def test_flush_creates_file(self, tel: HarnessTelemetry) -> None:
        tel.build_hooks()
        tel.flush()
        assert tel.output_path.exists()

    def test_flush_writes_valid_json(self, tel: HarnessTelemetry) -> None:
        tel.build_hooks()
        tel.flush()
        data = json.loads(tel.output_path.read_text())
        assert data["schema_version"] == "1.0"
        assert "totals" in data
        assert "sessions" in data

    def test_flush_persists_artifact_reads(self, tel: HarnessTelemetry, tmp_path: Path) -> None:
        tel.build_hooks()
        artifact = tmp_path / "CLAUDE.md"
        artifact.touch()
        _run(tel._on_read({"tool_input": {"file_path": str(artifact)}}))
        tel.flush()

        data = json.loads(tel.output_path.read_text())
        assert "CLAUDE.md" in data["totals"]["artifact_reads"]
        assert data["totals"]["artifact_reads"]["CLAUDE.md"] == 1

    def test_flush_persists_command_invocations(self, tel: HarnessTelemetry) -> None:
        tel.build_hooks()
        _run(tel._on_user_prompt({"prompt": "/check-code"}))
        tel.flush()

        data = json.loads(tel.output_path.read_text())
        assert data["totals"]["cli_command_invocations"]["check-code"] == 1

    def test_flush_persists_gate_failures(self, tel: HarnessTelemetry) -> None:
        tel.build_hooks()
        _run(
            tel._on_bash_post(
                {
                    "tool_input": {"command": "pytest tests/"},
                    "tool_output": "FAILED tests/test_foo.py::test_bar",
                }
            )
        )
        tel.flush()

        data = json.loads(tel.output_path.read_text())
        assert data["totals"]["gate_failures"]["pytest"] == 1

    def test_second_flush_accumulates_totals(self, tel: HarnessTelemetry) -> None:
        # Session 1
        tel.build_hooks("sess-1")
        _run(tel._on_user_prompt({"prompt": "/check-code"}))
        tel.flush()

        # Session 2 — same output file, different session
        tel2 = HarnessTelemetry(output_path=tel.output_path, cwd=tel.cwd)
        tel2.build_hooks("sess-2")
        _run(tel2._on_user_prompt({"prompt": "/check-code"}))
        _run(tel2._on_user_prompt({"prompt": "/coordinate"}))
        tel2.flush()

        data = json.loads(tel.output_path.read_text())
        assert data["totals"]["cli_command_invocations"]["check-code"] == 2
        assert data["totals"]["cli_command_invocations"]["coordinate"] == 1
        assert len(data["sessions"]) == 2

    def test_session_deduplication(self, tel: HarnessTelemetry) -> None:
        tel.build_hooks("dup-sess")
        _run(tel._on_user_prompt({"prompt": "/check-code"}))
        tel.flush()

        # Reload, re-use same session_id — should replace, not append.
        tel2 = HarnessTelemetry(output_path=tel.output_path, cwd=tel.cwd)
        tel2.build_hooks("dup-sess")
        tel2.flush()

        data = json.loads(tel.output_path.read_text())
        session_ids = [s["session_id"] for s in data["sessions"]]
        assert session_ids.count("dup-sess") == 1

    def test_stop_hook_calls_flush(self, tel: HarnessTelemetry) -> None:
        tel.build_hooks()
        _run(tel._on_user_prompt({"prompt": "/checkpoint"}))
        _run(tel._on_stop())  # should call flush() internally
        assert tel.output_path.exists()
        data = json.loads(tel.output_path.read_text())
        assert data["totals"]["cli_command_invocations"]["checkpoint"] == 1

    def test_atomic_write_no_partial_file(self, tel: HarnessTelemetry, tmp_path: Path) -> None:
        """flush() must not leave a .tmp file behind after success."""
        tel.build_hooks()
        tel.flush()
        tmp_file = tel.output_path.with_suffix(".tmp")
        assert not tmp_file.exists()

    def test_reset_wipes_data(self, tel: HarnessTelemetry) -> None:
        # Build and flush a first session so there is persisted data to erase.
        tel.build_hooks("pre-reset")
        _run(tel._on_user_prompt({"prompt": "/check-code"}))
        tel.flush()

        # Create a *new* instance so there is no active session carrying
        # counters.  reset() calls flush() which merges any live session —
        # starting fresh ensures no in-memory session events bleed through.
        tel_fresh = HarnessTelemetry(output_path=tel.output_path, cwd=tel.cwd)
        tel_fresh.reset()

        data = json.loads(tel.output_path.read_text())
        assert data["totals"]["cli_command_invocations"] == {}
        assert data["sessions"] == []


# ---------------------------------------------------------------------------
# TelemetryReporter — build_report()
# ---------------------------------------------------------------------------


@pytest.fixture
def telemetry_file(tmp_path: Path) -> Path:
    """Write a populated telemetry JSON and return its path."""
    payload = {
        "schema_version": "1.0",
        "last_updated": "2026-03-22T00:00:00+00:00",
        "totals": {
            "artifact_reads": {
                "CLAUDE.md": 12,
                "harness.config.yaml": 9,
                ".claude/commands/check-code.md": 7,
                "docs/harness-telemetry.json": 5,
                "docs/design.md": 3,
                "harness_skills/telemetry.py": 2,
                "README.md": 1,
            },
            "cli_command_invocations": {
                "check-code": 8,
                "harness:lint": 6,
                "coordinate": 3,
                "checkpoint": 2,
            },
            "gate_failures": {
                "ruff": 11,
                "mypy": 7,
                "pytest": 4,
                "ruff-format": 2,
            },
        },
        "sessions": [
            {
                "session_id": "s1",
                "started_at": "2026-03-22T00:00:00+00:00",
                "ended_at": "2026-03-22T00:10:00+00:00",
                "artifact_reads": {"CLAUDE.md": 6, "harness.config.yaml": 4},
                "cli_command_invocations": {"check-code": 4, "harness:lint": 3},
                "gate_failures": {"ruff": 5, "mypy": 3},
            },
            {
                "session_id": "s2",
                "started_at": "2026-03-22T01:00:00+00:00",
                "ended_at": "2026-03-22T01:15:00+00:00",
                "artifact_reads": {"CLAUDE.md": 6, "harness.config.yaml": 5},
                "cli_command_invocations": {"check-code": 4, "harness:lint": 3, "coordinate": 3},
                "gate_failures": {"ruff": 6, "mypy": 4, "pytest": 4, "ruff-format": 2},
            },
        ],
    }
    path = tmp_path / "harness-telemetry.json"
    path.write_text(json.dumps(payload, indent=2))
    return path


class TestBuildReport:
    def test_returns_telemetry_report(self, telemetry_file: Path) -> None:
        from harness_skills.models.telemetry import TelemetryReport

        report = build_report(telemetry_file)
        assert isinstance(report, TelemetryReport)

    def test_summary_totals(self, telemetry_file: Path) -> None:
        report = build_report(telemetry_file)
        assert report.summary.total_artifact_reads == 39  # sum of all artifact counts
        assert report.summary.total_command_invocations == 19
        assert report.summary.total_gate_failures == 24
        assert report.summary.sessions_analyzed == 2

    def test_artifact_sorted_descending(self, telemetry_file: Path) -> None:
        report = build_report(telemetry_file)
        counts = [m.read_count for m in report.artifacts]
        assert counts == sorted(counts, reverse=True)

    def test_top_artifact_is_warm(self, telemetry_file: Path) -> None:
        # CLAUDE.md has 12/39 = 30.8 % of reads.  Because the cumulative running
        # rate already exceeds the 20 % hot-threshold after the very first item,
        # the categoriser correctly labels it "warm".
        report = build_report(telemetry_file)
        top = report.artifacts[0]
        assert top.path == "CLAUDE.md"
        assert top.category == "warm"
        assert top.recommendation is None

    def test_artifact_is_hot_when_within_20pct_cumulative(self, tmp_path: Path) -> None:
        # Build a dataset where many small-count artifacts spread reads evenly
        # so the top items each contribute ≤ 20 % cumulatively.
        reads: dict[str, int] = {f"file{i:02d}.md": 1 for i in range(10)}
        payload = {
            "schema_version": "1.0",
            "last_updated": "2026-03-22T00:00:00+00:00",
            "totals": {
                "artifact_reads": reads,  # total = 10; each = 10%
                "cli_command_invocations": {},
                "gate_failures": {},
            },
            "sessions": [],
        }
        path = tmp_path / "small.json"
        path.write_text(json.dumps(payload))
        report = build_report(path)
        # First artifact: cumulative = 1/10 = 0.10 ≤ 0.20 → "hot"
        assert report.artifacts[0].category == "hot"
        # Second artifact: cumulative = 0.20 ≤ 0.20 → "hot"
        assert report.artifacts[1].category == "hot"
        # Third artifact: cumulative = 0.30 > 0.20 and ≤ 0.60 → "warm"
        assert report.artifacts[2].category == "warm"

    def test_cold_artifacts_have_recommendation(self, telemetry_file: Path) -> None:
        report = build_report(telemetry_file)
        cold = [m for m in report.artifacts if m.category in ("cold", "unused")]
        for m in cold:
            assert m.recommendation is not None

    def test_utilization_rates_sum_to_one(self, telemetry_file: Path) -> None:
        report = build_report(telemetry_file)
        total = sum(m.utilization_rate for m in report.artifacts)
        assert abs(total - 1.0) < 0.001

    def test_gate_sorted_descending(self, telemetry_file: Path) -> None:
        report = build_report(telemetry_file)
        counts = [m.failure_count for m in report.gates]
        assert counts == sorted(counts, reverse=True)

    def test_top_gate_is_high_signal(self, telemetry_file: Path) -> None:
        report = build_report(telemetry_file)
        top_gate = report.gates[0]
        assert top_gate.gate_id == "ruff"
        assert top_gate.effectiveness_score == 1.0
        assert top_gate.signal_strength == "high"

    def test_low_signal_gate_has_recommendation(self, telemetry_file: Path) -> None:
        report = build_report(telemetry_file)
        low_gates = [g for g in report.gates if g.signal_strength in ("low", "silent")]
        for g in low_gates:
            assert g.recommendation is not None

    def test_command_frequency_rates_sum_to_one(self, telemetry_file: Path) -> None:
        report = build_report(telemetry_file)
        total = sum(m.frequency_rate for m in report.commands)
        assert abs(total - 1.0) < 0.001

    def test_sessions_active_per_command(self, telemetry_file: Path) -> None:
        report = build_report(telemetry_file)
        check_code = next(m for m in report.commands if m.command == "check-code")
        # "check-code" appears in both sessions
        assert check_code.sessions_active == 2

    def test_min_reads_filter(self, telemetry_file: Path) -> None:
        report = build_report(telemetry_file, min_reads=5)
        for m in report.artifacts:
            assert m.read_count >= 5

    def test_top_n_cap(self, telemetry_file: Path) -> None:
        report = build_report(telemetry_file, top_n=3)
        assert len(report.artifacts) <= 3

    def test_cold_artifact_count_in_summary(self, telemetry_file: Path) -> None:
        report = build_report(telemetry_file)
        cold_count = sum(
            1 for m in report.artifacts if m.category in ("cold", "unused")
        )
        assert report.summary.cold_artifact_count == cold_count

    def test_silent_gate_count_in_summary(self, telemetry_file: Path) -> None:
        report = build_report(telemetry_file)
        silent_count = sum(1 for g in report.gates if g.signal_strength == "silent")
        assert report.summary.silent_gate_count == silent_count


class TestBuildReportEmptyFile:
    def test_empty_store(self, tmp_path: Path) -> None:
        path = tmp_path / "telemetry.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "last_updated": "2026-01-01T00:00:00+00:00",
                    "totals": {
                        "artifact_reads": {},
                        "cli_command_invocations": {},
                        "gate_failures": {},
                    },
                    "sessions": [],
                }
            )
        )
        report = build_report(path)
        assert report.artifacts == []
        assert report.commands == []
        assert report.gates == []
        assert report.summary.total_artifact_reads == 0

    def test_missing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "nonexistent.json"
        report = build_report(path)
        assert report.artifacts == []
        assert report.summary.sessions_analyzed == 0


# ---------------------------------------------------------------------------
# TelemetryReporter — render_report()
# ---------------------------------------------------------------------------


class TestRenderReport:
    def test_render_contains_section_headers(self, telemetry_file: Path) -> None:
        report = build_report(telemetry_file)
        rendered = render_report(report)
        assert "Artifact Utilization Rates" in rendered
        assert "Command Call Frequency" in rendered
        assert "Gate Effectiveness Scores" in rendered

    def test_render_shows_top_artifact(self, telemetry_file: Path) -> None:
        report = build_report(telemetry_file)
        rendered = render_report(report)
        assert "CLAUDE.md" in rendered

    def test_render_shows_top_gate(self, telemetry_file: Path) -> None:
        report = build_report(telemetry_file)
        rendered = render_report(report)
        assert "ruff" in rendered

    def test_render_empty_data_shows_placeholder(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "last_updated": "2026-01-01T00:00:00+00:00",
                    "totals": {
                        "artifact_reads": {},
                        "cli_command_invocations": {},
                        "gate_failures": {},
                    },
                    "sessions": [],
                }
            )
        )
        report = build_report(path)
        rendered = render_report(report)
        assert "(no artifact reads recorded)" in rendered
        assert "(no command invocations recorded)" in rendered
        assert "(no gate failures recorded)" in rendered

    def test_render_highlights_cold_artifacts(self, telemetry_file: Path) -> None:
        report = build_report(telemetry_file)
        rendered = render_report(report)
        # There should be cold/unused artifacts in the dataset.
        if report.summary.cold_artifact_count > 0:
            assert "Underutilized artifacts" in rendered
>>>>>>> feat/observability-a-skill-generates-telemetry-hooks-that-tr
