"""Tests for skills.perf_hooks — PerfHooks file-based performance measurement.

Coverage targets
----------------
Measurement
  - __repr__ does not raise
  - as_dict() returns all seven fields
  - _parse_row() round-trips a written row correctly

PerfHooks.start_timer / stop_timer
  - start records epoch to JSON timer state
  - stop removes entry from JSON and returns positive elapsed ms
  - stop raises KeyError when no matching start exists
  - two independent timers can run concurrently without interference
  - stop with custom notes and timestamp works

PerfHooks.timer (context manager)
  - elapsed_ms is populated after exit
  - row is appended to perf.md on success
  - row is appended to perf.md even when the block raises

PerfHooks.sample_memory
  - returns a non-negative float
  - row is appended to perf.md with metric = memory_rss

PerfHooks.record_startup
  - returns a Measurement with metric = startup and label = startup
  - row is appended to perf.md

PerfHooks.list
  - returns empty list when file does not exist
  - filters by agent, metric, and label correctly
  - returns rows in file order

PerfHooks.stats
  - prints header and at least one data row to stdout
  - prints "(no measurements found)" when file is empty

CLI entry point (main)
  - start / stop subcommands print expected strings
  - sample-memory subcommand prints RSS line
  - record-startup subcommand prints startup line
  - list subcommand prints header row
  - stats subcommand prints stats table
  - stop with missing timer exits with code 1
"""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers that isolate file I/O
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_hooks(tmp_path: Path):
    """Return a PerfHooks instance backed by temporary files."""
    from skills.perf_hooks import PerfHooks

    return PerfHooks(
        perf_file=tmp_path / "perf.md",
        timer_state=tmp_path / "perf-timers.json",
    )


@pytest.fixture
def tmp_hooks_with_data(tmp_hooks):
    """PerfHooks pre-populated with one entry of each metric kind."""
    tmp_hooks.record_startup(agent="agent/test", duration_ms=500.0)
    tmp_hooks.sample_memory("after_init", agent="agent/test", notes="cold")
    tmp_hooks.start_timer("call_llm", agent="agent/test")
    tmp_hooks.stop_timer("call_llm", agent="agent/test", notes="hit")
    return tmp_hooks


# ===========================================================================
# Measurement dataclass
# ===========================================================================


class TestMeasurement:
    def test_as_dict_has_all_fields(self, tmp_hooks) -> None:
        m = tmp_hooks.record_startup(agent="a", duration_ms=100.0)
        d = m.as_dict()
        for key in ("timestamp", "agent", "metric", "label", "value", "unit", "notes"):
            assert key in d

    def test_as_dict_values_match(self, tmp_hooks) -> None:
        m = tmp_hooks.record_startup(agent="a/b", duration_ms=200.0, notes="cold")
        d = m.as_dict()
        assert d["agent"] == "a/b"
        assert d["value"] == pytest.approx(200.0)
        assert d["notes"] == "cold"
        assert d["metric"] == "startup"
        assert d["unit"] == "ms"

    def test_repr_does_not_raise(self, tmp_hooks) -> None:
        m = tmp_hooks.record_startup(agent="a", duration_ms=1.0)
        # __repr__ is marked pragma: no cover but must not raise when called
        assert repr(m)  # non-empty string


# ===========================================================================
# start_timer / stop_timer
# ===========================================================================


class TestTimerStartStop:
    def test_start_persists_timer_state(self, tmp_hooks) -> None:
        # Verify persistence behaviourally: a matching stop_timer must succeed
        # (it would raise KeyError if start_timer had not persisted the epoch).
        tmp_hooks.start_timer("op", agent="ag")
        elapsed = tmp_hooks.stop_timer("op", agent="ag")
        assert elapsed > 0

    def test_stop_returns_positive_elapsed(self, tmp_hooks) -> None:
        tmp_hooks.start_timer("op", agent="ag")
        elapsed = tmp_hooks.stop_timer("op", agent="ag")
        assert elapsed > 0

    def test_stop_removes_entry_so_second_stop_raises(self, tmp_hooks) -> None:
        # After a successful stop_timer the state entry is removed — a second
        # stop for the same label/agent must raise KeyError.
        tmp_hooks.start_timer("op", agent="ag")
        tmp_hooks.stop_timer("op", agent="ag")
        with pytest.raises(KeyError):
            tmp_hooks.stop_timer("op", agent="ag")

    def test_stop_appends_row_to_perf_file(self, tmp_hooks, tmp_path: Path) -> None:
        tmp_hooks.start_timer("op", agent="ag")
        tmp_hooks.stop_timer("op", agent="ag", notes="done")
        rows = tmp_hooks.list(metric="response_time")
        assert len(rows) == 1
        assert rows[0].notes == "done"

    def test_stop_without_start_raises_key_error(self, tmp_hooks) -> None:
        with pytest.raises(KeyError, match="op"):
            tmp_hooks.stop_timer("op", agent="ag")

    def test_two_concurrent_timers(self, tmp_hooks) -> None:
        tmp_hooks.start_timer("a", agent="ag")
        tmp_hooks.start_timer("b", agent="ag")
        tmp_hooks.stop_timer("a", agent="ag")
        tmp_hooks.stop_timer("b", agent="ag")
        rows = tmp_hooks.list(metric="response_time")
        labels = {r.label for r in rows}
        assert labels == {"a", "b"}

    def test_stop_with_custom_timestamp(self, tmp_hooks) -> None:
        tmp_hooks.start_timer("ts_op", agent="ag")
        ts = "2026-01-01T00:00:00Z"
        tmp_hooks.stop_timer("ts_op", agent="ag", timestamp=ts)
        rows = tmp_hooks.list(label="ts_op")
        assert rows[0].timestamp == ts


# ===========================================================================
# timer context manager
# ===========================================================================


class TestTimerContextManager:
    def test_elapsed_ms_populated_after_exit(self, tmp_hooks) -> None:
        with tmp_hooks.timer("ctx", agent="ag") as t:
            pass
        assert t.elapsed_ms >= 0

    def test_row_written_on_success(self, tmp_hooks) -> None:
        with tmp_hooks.timer("ctx_op", agent="ag", notes="ok") as _t:
            pass
        rows = tmp_hooks.list(label="ctx_op")
        assert len(rows) == 1
        assert rows[0].metric == "response_time"
        assert rows[0].notes == "ok"

    def test_row_written_even_on_exception(self, tmp_hooks) -> None:
        with pytest.raises(RuntimeError):
            with tmp_hooks.timer("ctx_err", agent="ag"):
                raise RuntimeError("boom")
        rows = tmp_hooks.list(label="ctx_err")
        assert len(rows) == 1


# ===========================================================================
# sample_memory
# ===========================================================================


class TestSampleMemory:
    def test_returns_non_negative_float(self, tmp_hooks) -> None:
        mb = tmp_hooks.sample_memory("snap", agent="ag")
        assert isinstance(mb, float)
        assert mb >= 0.0

    def test_row_has_memory_rss_metric(self, tmp_hooks) -> None:
        tmp_hooks.sample_memory("snap", agent="ag", notes="warm")
        rows = tmp_hooks.list(metric="memory_rss")
        assert len(rows) == 1
        assert rows[0].unit == "MB"
        assert rows[0].label == "snap"
        assert rows[0].notes == "warm"


# ===========================================================================
# record_startup
# ===========================================================================


class TestRecordStartup:
    def test_returns_measurement(self, tmp_hooks) -> None:
        from skills.perf_hooks import Measurement

        m = tmp_hooks.record_startup(agent="ag", duration_ms=750.5)
        assert isinstance(m, Measurement)

    def test_metric_is_startup(self, tmp_hooks) -> None:
        m = tmp_hooks.record_startup(agent="ag", duration_ms=750.5)
        assert m.metric == "startup"
        assert m.label == "startup"
        assert m.unit == "ms"
        assert m.value == pytest.approx(750.5)

    def test_row_written_to_file(self, tmp_hooks) -> None:
        tmp_hooks.record_startup(agent="ag", duration_ms=300.0)
        rows = tmp_hooks.list(metric="startup")
        assert len(rows) == 1

    def test_notes_stored(self, tmp_hooks) -> None:
        tmp_hooks.record_startup(agent="ag", duration_ms=1.0, notes="first run")
        rows = tmp_hooks.list(metric="startup")
        assert rows[0].notes == "first run"


# ===========================================================================
# list
# ===========================================================================


class TestList:
    def test_empty_when_file_missing(self, tmp_hooks) -> None:
        assert tmp_hooks.list() == []

    def test_returns_all_rows(self, tmp_hooks_with_data) -> None:
        rows = tmp_hooks_with_data.list()
        assert len(rows) == 3

    def test_filter_by_agent(self, tmp_hooks, tmp_path: Path) -> None:
        tmp_hooks.record_startup(agent="agent/a", duration_ms=100.0)
        tmp_hooks.record_startup(agent="agent/b", duration_ms=200.0)
        rows = tmp_hooks.list(agent="agent/a")
        assert all(r.agent == "agent/a" for r in rows)
        assert len(rows) == 1

    def test_filter_by_metric(self, tmp_hooks_with_data) -> None:
        rows = tmp_hooks_with_data.list(metric="startup")
        assert all(r.metric == "startup" for r in rows)
        assert len(rows) == 1

    def test_filter_by_label(self, tmp_hooks_with_data) -> None:
        rows = tmp_hooks_with_data.list(label="startup")
        assert len(rows) == 1
        assert rows[0].label == "startup"

    def test_combined_filters(self, tmp_hooks) -> None:
        tmp_hooks.record_startup(agent="a1", duration_ms=1.0)
        tmp_hooks.record_startup(agent="a2", duration_ms=2.0)
        tmp_hooks.sample_memory("snap", agent="a1")
        rows = tmp_hooks.list(agent="a1", metric="startup")
        assert len(rows) == 1
        assert rows[0].agent == "a1"
        assert rows[0].metric == "startup"

    def test_file_order_preserved(self, tmp_hooks) -> None:
        for i in range(3):
            tmp_hooks.record_startup(agent="ag", duration_ms=float(i * 100))
        rows = tmp_hooks.list(metric="startup")
        values = [r.value for r in rows]
        assert values == [0.0, 100.0, 200.0]


# ===========================================================================
# stats
# ===========================================================================


class TestStats:
    def test_stats_prints_table(self, tmp_hooks_with_data, capsys) -> None:
        tmp_hooks_with_data.stats()
        out = capsys.readouterr().out
        # Header line expected
        assert "Metric" in out
        assert "Label" in out
        # At least one data row
        assert "startup" in out

    def test_stats_no_data_prints_message(self, tmp_hooks, capsys) -> None:
        tmp_hooks.stats()
        out = capsys.readouterr().out
        assert "no measurements found" in out

    def test_stats_filter_by_metric(self, tmp_hooks_with_data, capsys) -> None:
        tmp_hooks_with_data.stats(metric="startup")
        out = capsys.readouterr().out
        assert "startup" in out
        # memory_rss should not appear
        assert "memory_rss" not in out

    def test_stats_filter_by_agent(self, tmp_hooks_with_data, capsys) -> None:
        tmp_hooks_with_data.stats(agent="agent/test")
        out = capsys.readouterr().out
        assert "startup" in out

    def test_stats_unknown_agent_no_data(self, tmp_hooks_with_data, capsys) -> None:
        tmp_hooks_with_data.stats(agent="nobody")
        out = capsys.readouterr().out
        assert "no measurements found" in out


# ===========================================================================
# CLI entry point
# ===========================================================================


class TestCLIMain:
    """Test the argparse-based main() entry point."""

    def _run(self, argv: list[str], tmp_hooks_paths: dict) -> tuple[str, str, int]:
        """Run main() with patched PERF_FILE / TIMER_STATE, return stdout, stderr, exit code."""
        import skills.perf_hooks as ph

        orig_file = ph.PERF_FILE
        orig_timers = ph.TIMER_STATE
        ph.PERF_FILE = tmp_hooks_paths["perf_file"]
        ph.TIMER_STATE = tmp_hooks_paths["timer_state"]

        buf_out = StringIO()
        buf_err = StringIO()
        real_out, real_err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = buf_out, buf_err

        exit_code = 0
        try:
            ph.main(argv)
        except SystemExit as exc:
            exit_code = int(exc.code) if exc.code is not None else 0
        finally:
            sys.stdout, sys.stderr = real_out, real_err
            ph.PERF_FILE = orig_file
            ph.TIMER_STATE = orig_timers

        return buf_out.getvalue(), buf_err.getvalue(), exit_code

    @pytest.fixture
    def paths(self, tmp_path: Path) -> dict:
        return {
            "perf_file": tmp_path / "perf.md",
            "timer_state": tmp_path / "timers.json",
        }

    def test_start_prints_timer_started(self, paths) -> None:
        out, err, code = self._run(
            ["start", "--label", "op", "--agent", "ag"], paths
        )
        assert "Timer started" in out
        assert code == 0

    def test_stop_after_start_prints_elapsed(self, paths) -> None:
        self._run(["start", "--label", "op", "--agent", "ag"], paths)
        out, _err, code = self._run(
            ["stop", "--label", "op", "--agent", "ag"], paths
        )
        assert "Elapsed" in out
        assert "op" in out
        assert code == 0

    def test_stop_without_start_exits_1(self, paths) -> None:
        _out, err, code = self._run(
            ["stop", "--label", "ghost", "--agent", "ag"], paths
        )
        assert code == 1
        assert "ERROR" in err

    def test_sample_memory_prints_rss(self, paths) -> None:
        out, _err, code = self._run(
            ["sample-memory", "--label", "snap", "--agent", "ag"], paths
        )
        assert "RSS" in out
        assert "MB" in out
        assert code == 0

    def test_record_startup_prints_startup(self, paths) -> None:
        out, _err, code = self._run(
            [
                "record-startup",
                "--agent", "ag",
                "--duration-ms", "1234.5",
            ],
            paths,
        )
        assert "Startup recorded" in out
        assert "1234.5" in out
        assert code == 0

    def test_list_prints_header_when_data_exists(self, paths) -> None:
        self._run(
            ["record-startup", "--agent", "ag", "--duration-ms", "100"],
            paths,
        )
        out, _err, code = self._run(["list"], paths)
        assert "Timestamp" in out
        assert "Agent" in out
        assert code == 0

    def test_list_no_data_prints_message(self, paths) -> None:
        out, _err, code = self._run(["list"], paths)
        assert "no measurements found" in out
        assert code == 0

    def test_stats_prints_table_when_data_exists(self, paths) -> None:
        self._run(
            ["record-startup", "--agent", "ag", "--duration-ms", "100"],
            paths,
        )
        out, _err, code = self._run(["stats"], paths)
        assert "startup" in out
        assert code == 0
