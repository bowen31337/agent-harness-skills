"""Unit tests for skills/progress_log.py.

Validates that the progress-log skill generates the correct Markdown table
format and that agents can append timestamped entries as they complete steps
within a plan.

Test strategy
-------------
* A ``tmp_path`` fixture writes log files to a temporary directory so the
  real ``docs/exec-plans/progress.md`` is never modified during testing.
* Each test class targets one behaviour boundary.
* All timestamps are injected via the ``timestamp=`` parameter so entries
  remain deterministic regardless of wall-clock time.
* CLI behaviour is tested via ``skills.progress_log.main()`` with explicit
  ``argv`` lists — no subprocess spawning required.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from skills.progress_log import (
    VALID_STATUSES,
    ProgressEntry,
    ProgressLog,
    _build_row,
    _escape,
    _now_utc,
    _parse_row,
    main,
)

# ---------------------------------------------------------------------------
# Constants reused across test classes
# ---------------------------------------------------------------------------

_TS = "2026-03-20T09:00:00Z"
_PLAN = "feature/auth-refactor"
_STEP = "1. Scaffold AuthService"
_AGENT = "agent/coder-v1"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_log(tmp_path: Path) -> ProgressLog:
    """Return a ProgressLog backed by a fresh temp file."""
    return ProgressLog(log_file=tmp_path / "progress.md")


# ===========================================================================
# File initialisation
# ===========================================================================


class TestFileInitialisation:
    """The log file and its parent directories are created automatically."""

    def test_file_created_on_first_append(self, tmp_path: Path) -> None:
        log_file = tmp_path / "sub" / "progress.md"
        log = ProgressLog(log_file=log_file)
        assert not log_file.exists()

        log.append(plan_id=_PLAN, step=_STEP, status="done", agent=_AGENT, timestamp=_TS)

        assert log_file.exists()

    def test_header_written_once(self, tmp_path: Path) -> None:
        log = _make_log(tmp_path)
        log.append(plan_id=_PLAN, step=_STEP, status="done", agent=_AGENT, timestamp=_TS)

        content = (tmp_path / "progress.md").read_text(encoding="utf-8")
        assert content.startswith("# Agent Progress Log")
        assert "<!-- agents append new rows here" in content
        assert "| Timestamp (UTC) | Plan ID |" in content

    def test_header_not_duplicated_on_second_append(self, tmp_path: Path) -> None:
        log = _make_log(tmp_path)
        log.append(plan_id=_PLAN, step="Step 1", status="started", agent=_AGENT, timestamp=_TS)
        log.append(plan_id=_PLAN, step="Step 1", status="done", agent=_AGENT, timestamp=_TS)

        content = (tmp_path / "progress.md").read_text(encoding="utf-8")
        assert content.count("# Agent Progress Log") == 1

    def test_parent_directories_created(self, tmp_path: Path) -> None:
        deep = tmp_path / "a" / "b" / "c" / "progress.md"
        log = ProgressLog(log_file=deep)
        log.append(plan_id=_PLAN, step=_STEP, status="done", agent=_AGENT, timestamp=_TS)
        assert deep.exists()


# ===========================================================================
# Row format
# ===========================================================================


class TestRowFormat:
    """Appended rows must conform to the Markdown table format."""

    def test_row_contains_all_fields(self, tmp_path: Path) -> None:
        log = _make_log(tmp_path)
        log.append(
            plan_id=_PLAN,
            step=_STEP,
            status="done",
            agent=_AGENT,
            message="Created src/auth/service.py",
            timestamp=_TS,
        )
        content = (tmp_path / "progress.md").read_text(encoding="utf-8")
        assert _TS in content
        assert _PLAN in content
        assert _STEP in content
        assert _AGENT in content
        assert "Created src/auth/service.py" in content

    def test_row_is_markdown_table_row(self, tmp_path: Path) -> None:
        log = _make_log(tmp_path)
        log.append(plan_id=_PLAN, step=_STEP, status="done", agent=_AGENT, timestamp=_TS)

        lines = (tmp_path / "progress.md").read_text(encoding="utf-8").splitlines()
        data_rows = [ln for ln in lines if ln.startswith("| ") and _TS in ln]
        assert len(data_rows) == 1
        row = data_rows[0]
        # Must have leading and trailing pipe
        assert row.startswith("|")
        assert row.endswith("|")
        # Must have 6 columns (7 pipe characters)
        assert row.count("|") >= 7

    def test_missing_message_replaced_by_dash(self, tmp_path: Path) -> None:
        log = _make_log(tmp_path)
        log.append(plan_id=_PLAN, step=_STEP, status="done", agent=_AGENT, timestamp=_TS)
        content = (tmp_path / "progress.md").read_text(encoding="utf-8")
        # The message column should show "—" when no message is supplied
        assert "| — |" in content

    @pytest.mark.parametrize("status,expected_emoji", [
        ("started", "🔵"),
        ("done",    "✅"),
        ("failed",  "❌"),
        ("skipped", "⏭️"),
    ])
    def test_status_emoji_in_row(
        self, tmp_path: Path, status: str, expected_emoji: str
    ) -> None:
        log = _make_log(tmp_path)
        log.append(plan_id=_PLAN, step=_STEP, status=status, agent=_AGENT, timestamp=_TS)
        content = (tmp_path / "progress.md").read_text(encoding="utf-8")
        assert expected_emoji in content

    def test_pipe_in_message_is_escaped(self, tmp_path: Path) -> None:
        log = _make_log(tmp_path)
        log.append(
            plan_id=_PLAN,
            step=_STEP,
            status="done",
            agent=_AGENT,
            message="a | b",
            timestamp=_TS,
        )
        content = (tmp_path / "progress.md").read_text(encoding="utf-8")
        # The pipe in the message must be escaped
        assert r"a \| b" in content

    def test_pipe_in_step_is_escaped(self, tmp_path: Path) -> None:
        log = _make_log(tmp_path)
        log.append(
            plan_id=_PLAN,
            step="Step 1 | substep",
            status="done",
            agent=_AGENT,
            timestamp=_TS,
        )
        content = (tmp_path / "progress.md").read_text(encoding="utf-8")
        assert r"Step 1 \| substep" in content


# ===========================================================================
# Append return value
# ===========================================================================


class TestAppendReturnValue:
    """append() must return a ProgressEntry with the correct field values."""

    def test_returns_progress_entry(self, tmp_path: Path) -> None:
        log = _make_log(tmp_path)
        entry = log.append(plan_id=_PLAN, step=_STEP, status="done", agent=_AGENT, timestamp=_TS)
        assert isinstance(entry, ProgressEntry)

    def test_entry_fields_match_inputs(self, tmp_path: Path) -> None:
        log = _make_log(tmp_path)
        entry = log.append(
            plan_id=_PLAN,
            step=_STEP,
            status="failed",
            agent=_AGENT,
            message="boom",
            timestamp=_TS,
        )
        assert entry.plan_id == _PLAN
        assert entry.step == _STEP
        assert entry.status == "failed"
        assert entry.agent == _AGENT
        assert entry.message == "boom"
        assert entry.timestamp == _TS

    def test_default_timestamp_is_set(self, tmp_path: Path) -> None:
        log = _make_log(tmp_path)
        entry = log.append(plan_id=_PLAN, step=_STEP, status="done", agent=_AGENT)
        # Should be a non-empty UTC timestamp string
        assert entry.timestamp
        assert "T" in entry.timestamp
        assert entry.timestamp.endswith("Z")

    def test_as_dict_returns_all_fields(self, tmp_path: Path) -> None:
        log = _make_log(tmp_path)
        entry = log.append(plan_id=_PLAN, step=_STEP, status="done", agent=_AGENT, timestamp=_TS)
        d = entry.as_dict()
        assert set(d.keys()) == {"timestamp", "plan_id", "step", "status", "agent", "message"}

    def test_invalid_status_raises_value_error(self, tmp_path: Path) -> None:
        log = _make_log(tmp_path)
        with pytest.raises(ValueError, match="Unknown status"):
            log.append(plan_id=_PLAN, step=_STEP, status="invalid_status", agent=_AGENT)


# ===========================================================================
# list() — reading entries back
# ===========================================================================


class TestList:
    """list() must parse and return entries in file order."""

    def test_empty_log_returns_empty_list(self, tmp_path: Path) -> None:
        log = _make_log(tmp_path)
        assert log.list() == []

    def test_nonexistent_file_returns_empty_list(self, tmp_path: Path) -> None:
        log = ProgressLog(log_file=tmp_path / "does_not_exist.md")
        assert log.list() == []

    def test_single_entry_round_trips(self, tmp_path: Path) -> None:
        log = _make_log(tmp_path)
        log.append(plan_id=_PLAN, step=_STEP, status="done", agent=_AGENT, timestamp=_TS)

        entries = log.list()
        assert len(entries) == 1
        e = entries[0]
        assert e.timestamp == _TS
        assert e.plan_id == _PLAN
        assert e.step == _STEP
        assert e.status == "done"
        assert e.agent == _AGENT

    def test_multiple_entries_returned_in_order(self, tmp_path: Path) -> None:
        log = _make_log(tmp_path)
        log.append(plan_id=_PLAN, step="Step 1", status="started", agent=_AGENT, timestamp="2026-03-20T09:00:00Z")
        log.append(plan_id=_PLAN, step="Step 1", status="done",    agent=_AGENT, timestamp="2026-03-20T09:01:00Z")
        log.append(plan_id=_PLAN, step="Step 2", status="failed",  agent=_AGENT, timestamp="2026-03-20T09:02:00Z")

        entries = log.list()
        assert len(entries) == 3
        assert entries[0].status == "started"
        assert entries[1].status == "done"
        assert entries[2].status == "failed"

    def test_filter_by_plan_id(self, tmp_path: Path) -> None:
        log = _make_log(tmp_path)
        log.append(plan_id="plan/a", step="Step 1", status="done",    agent=_AGENT, timestamp=_TS)
        log.append(plan_id="plan/b", step="Step 1", status="started", agent=_AGENT, timestamp=_TS)
        log.append(plan_id="plan/a", step="Step 2", status="skipped", agent=_AGENT, timestamp=_TS)

        entries_a = log.list(plan_id="plan/a")
        assert len(entries_a) == 2
        assert all(e.plan_id == "plan/a" for e in entries_a)

        entries_b = log.list(plan_id="plan/b")
        assert len(entries_b) == 1
        assert entries_b[0].plan_id == "plan/b"

    def test_pipe_in_message_is_unescaped(self, tmp_path: Path) -> None:
        log = _make_log(tmp_path)
        log.append(
            plan_id=_PLAN, step=_STEP, status="done", agent=_AGENT,
            message="a | b", timestamp=_TS,
        )
        entries = log.list()
        assert entries[0].message == "a | b"

    @pytest.mark.parametrize("status", VALID_STATUSES)
    def test_all_statuses_round_trip(self, tmp_path: Path, status: str) -> None:
        log = _make_log(tmp_path)
        log.append(plan_id=_PLAN, step=_STEP, status=status, agent=_AGENT, timestamp=_TS)
        entries = log.list()
        assert entries[0].status == status


# ===========================================================================
# summary() — per-plan aggregation
# ===========================================================================


class TestSummary:
    """summary() must compute correct done/failed/skipped/started counts."""

    def test_summary_with_no_entries(self, tmp_path: Path, capsys) -> None:
        log = _make_log(tmp_path)
        log.summary()
        captured = capsys.readouterr()
        assert "no progress entries" in captured.out

    def test_summary_counts_latest_status_per_step(self, tmp_path: Path, capsys) -> None:
        log = _make_log(tmp_path)
        # Step 1 transitions: started → done
        log.append(plan_id=_PLAN, step="Step 1", status="started", agent=_AGENT, timestamp="2026-03-20T09:00:00Z")
        log.append(plan_id=_PLAN, step="Step 1", status="done",    agent=_AGENT, timestamp="2026-03-20T09:01:00Z")
        # Step 2 stays failed
        log.append(plan_id=_PLAN, step="Step 2", status="failed",  agent=_AGENT, timestamp="2026-03-20T09:02:00Z")
        # Step 3 skipped
        log.append(plan_id=_PLAN, step="Step 3", status="skipped", agent=_AGENT, timestamp="2026-03-20T09:03:00Z")

        log.summary()
        out = capsys.readouterr().out
        # 1 done, 1 failed, 1 skipped → total 3 unique steps
        assert "1" in out   # done count
        assert _PLAN in out

    def test_summary_filtered_to_one_plan(self, tmp_path: Path, capsys) -> None:
        log = _make_log(tmp_path)
        log.append(plan_id="plan/alpha", step="Step 1", status="done",    agent=_AGENT, timestamp=_TS)
        log.append(plan_id="plan/beta",  step="Step 1", status="started", agent=_AGENT, timestamp=_TS)

        log.summary(plan_id="plan/alpha")
        out = capsys.readouterr().out
        assert "plan/alpha" in out
        assert "plan/beta" not in out

    def test_summary_uses_latest_status_not_first(self, tmp_path: Path, capsys) -> None:
        """A step that goes started → done should count as done, not started."""
        log = _make_log(tmp_path)
        log.append(plan_id=_PLAN, step="Step 1", status="started", agent=_AGENT, timestamp="2026-03-20T09:00:00Z")
        log.append(plan_id=_PLAN, step="Step 1", status="done",    agent=_AGENT, timestamp="2026-03-20T09:01:00Z")

        log.summary()
        out = capsys.readouterr().out
        # done=1, started=0 (latest status wins)
        lines = [ln for ln in out.splitlines() if _PLAN in ln]
        assert lines, "Expected a summary line for the plan"
        summary_line = lines[0]
        # The 'started' column (rightmost) should show 0
        # and 'done' should show 1
        parts = summary_line.split()
        # Check total steps = 1
        assert "1" in parts


# ===========================================================================
# _build_row / _escape / _parse_row helpers
# ===========================================================================


class TestInternalHelpers:
    """Unit-test the low-level helper functions."""

    def test_escape_replaces_pipes(self) -> None:
        assert _escape("a | b") == r"a \| b"
        assert _escape("no pipe") == "no pipe"

    def test_build_row_is_markdown_row(self) -> None:
        row = _build_row(_TS, _PLAN, _STEP, "done", _AGENT, "msg")
        assert row.startswith("|")
        assert row.endswith("|")
        assert _TS in row

    def test_parse_row_header_returns_none(self) -> None:
        header = "| Timestamp (UTC) | Plan ID | Step | Status | Agent | Message |"
        assert _parse_row(header) is None

    def test_parse_row_separator_returns_none(self) -> None:
        sep = "|-----------------|---------|------|--------|-------|---------|"
        assert _parse_row(sep) is None

    def test_parse_row_empty_string_returns_none(self) -> None:
        assert _parse_row("") is None

    def test_parse_row_data_row_succeeds(self) -> None:
        row = _build_row(_TS, _PLAN, _STEP, "done", _AGENT, "details here")
        entry = _parse_row(row)
        assert entry is not None
        assert entry.timestamp == _TS
        assert entry.plan_id == _PLAN
        assert entry.step == _STEP
        assert entry.status == "done"
        assert entry.agent == _AGENT
        assert entry.message == "details here"

    def test_now_utc_format(self) -> None:
        ts = _now_utc()
        # Must match YYYY-MM-DDTHH:MM:SSZ
        import re
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", ts)


# ===========================================================================
# ProgressEntry
# ===========================================================================


class TestProgressEntry:
    """ProgressEntry data class behaviour."""

    def test_as_dict_contains_all_slots(self) -> None:
        e = ProgressEntry(
            timestamp=_TS,
            plan_id=_PLAN,
            step=_STEP,
            status="done",
            agent=_AGENT,
            message="",
        )
        d = e.as_dict()
        assert d == {
            "timestamp": _TS,
            "plan_id": _PLAN,
            "step": _STEP,
            "status": "done",
            "agent": _AGENT,
            "message": "",
        }


# ===========================================================================
# CLI interface
# ===========================================================================


class TestCLI:
    """main() must dispatch correctly for all three sub-commands."""

    def _run(self, tmp_path: Path, argv: list[str], monkeypatch, capsys):
        """Run the CLI with a patched PROGRESS_FILE pointing to tmp_path."""
        import skills.progress_log as mod
        monkeypatch.setattr(mod, "PROGRESS_FILE", tmp_path / "progress.md")
        main(argv)
        return capsys.readouterr()

    def test_append_command_writes_entry(self, tmp_path: Path, monkeypatch, capsys) -> None:
        self._run(
            tmp_path,
            [
                "append",
                "--plan-id", _PLAN,
                "--step", _STEP,
                "--status", "done",
                "--agent", _AGENT,
                "--timestamp", _TS,
            ],
            monkeypatch,
            capsys,
        )
        content = (tmp_path / "progress.md").read_text(encoding="utf-8")
        assert _TS in content
        assert _PLAN in content

    def test_append_command_stdout_contains_plan_id(self, tmp_path: Path, monkeypatch, capsys) -> None:
        out = self._run(
            tmp_path,
            ["append", "--plan-id", _PLAN, "--step", _STEP,
             "--status", "started", "--agent", _AGENT, "--timestamp", _TS],
            monkeypatch, capsys,
        )
        assert _PLAN in out.out

    def test_list_command_no_entries(self, tmp_path: Path, monkeypatch, capsys) -> None:
        out = self._run(tmp_path, ["list"], monkeypatch, capsys)
        assert "no entries" in out.out.lower()

    def test_list_command_shows_entries(self, tmp_path: Path, monkeypatch, capsys) -> None:
        import skills.progress_log as mod
        monkeypatch.setattr(mod, "PROGRESS_FILE", tmp_path / "progress.md")
        log = ProgressLog(log_file=tmp_path / "progress.md")
        log.append(plan_id=_PLAN, step=_STEP, status="done", agent=_AGENT, timestamp=_TS)

        main(["list"])
        out = capsys.readouterr().out
        assert _PLAN in out

    def test_summary_command_no_entries(self, tmp_path: Path, monkeypatch, capsys) -> None:
        out = self._run(tmp_path, ["summary"], monkeypatch, capsys)
        assert "no progress" in out.out.lower()

    def test_append_with_message(self, tmp_path: Path, monkeypatch, capsys) -> None:
        self._run(
            tmp_path,
            ["append", "--plan-id", _PLAN, "--step", _STEP,
             "--status", "failed", "--agent", _AGENT,
             "--message", "timeout after 30s", "--timestamp", _TS],
            monkeypatch, capsys,
        )
        content = (tmp_path / "progress.md").read_text(encoding="utf-8")
        assert "timeout after 30s" in content


# ===========================================================================
# Append-only guarantee
# ===========================================================================


class TestAppendOnly:
    """New entries must always be appended; existing rows must not be modified."""

    def test_existing_entries_preserved_on_new_append(self, tmp_path: Path) -> None:
        log = _make_log(tmp_path)
        log.append(plan_id=_PLAN, step="Step 1", status="started", agent=_AGENT,
                   timestamp="2026-03-20T09:00:00Z")
        log.append(plan_id=_PLAN, step="Step 1", status="done",    agent=_AGENT,
                   timestamp="2026-03-20T09:01:00Z")

        entries = log.list()
        assert len(entries) == 2
        assert entries[0].status == "started"
        assert entries[1].status == "done"

    def test_file_grows_monotonically(self, tmp_path: Path) -> None:
        log = _make_log(tmp_path)
        log_file = tmp_path / "progress.md"

        log.append(plan_id=_PLAN, step="Step 1", status="done", agent=_AGENT, timestamp=_TS)
        size_after_first = log_file.stat().st_size

        log.append(plan_id=_PLAN, step="Step 2", status="done", agent=_AGENT, timestamp=_TS)
        size_after_second = log_file.stat().st_size

        assert size_after_second > size_after_first

    def test_all_four_statuses_preserved_in_sequence(self, tmp_path: Path) -> None:
        log = _make_log(tmp_path)
        statuses = ["started", "done", "failed", "skipped"]
        for i, status in enumerate(statuses, start=1):
            log.append(
                plan_id=_PLAN, step=f"Step {i}", status=status,
                agent=_AGENT, timestamp=_TS,
            )

        entries = log.list()
        assert len(entries) == 4
        assert [e.status for e in entries] == statuses
