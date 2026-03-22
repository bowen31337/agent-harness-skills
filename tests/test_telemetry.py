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
