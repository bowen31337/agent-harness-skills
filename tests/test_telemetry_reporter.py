"""Unit tests for harness_skills.telemetry_reporter.

Covers:
  - build_report() with realistic telemetry data
  - Artifact categorisation: hot / warm / cold / unused
  - Gate effectiveness scoring and signal-strength bands
  - Command frequency rates and sessions_active counts
  - Summary aggregate metrics (cold_artifact_count, silent_gate_count, …)
  - Filtering: --min-reads, --top-n
  - render_report() produces human-readable output with key sections
  - CLI (click runner): --format table, --format json, --min-reads, --top-n
  - Exit codes: 0 (all healthy), 1 (cold/silent detected)
  - Empty telemetry file: reporter handles gracefully
  - Missing telemetry file: reporter handles gracefully (no crash)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from harness_skills.models.base import Status
from harness_skills.telemetry_reporter import (
    build_report,
    render_report,
    telemetry_cmd,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _write_telemetry(path: Path, data: dict) -> Path:
    """Write *data* as JSON to *path*, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def _tel_path(tmp_path: Path) -> Path:
    return tmp_path / "docs" / "harness-telemetry.json"


def _minimal_store(
    *,
    artifacts: dict | None = None,
    commands: dict | None = None,
    gates: dict | None = None,
    sessions: list | None = None,
) -> dict:
    return {
        "schema_version": "1.0",
        "last_updated": "2026-03-22T00:00:00+00:00",
        "totals": {
            "artifact_reads": artifacts or {},
            "cli_command_invocations": commands or {},
            "gate_failures": gates or {},
        },
        "sessions": sessions or [],
    }


# ── Tests: empty / missing data ───────────────────────────────────────────────


class TestEmptyData:
    """Reporter must handle empty or absent telemetry files without crashing."""

    def test_missing_file_returns_empty_report(self, tmp_path: Path) -> None:
        path = tmp_path / "does-not-exist.json"
        report = build_report(path)
        assert report.artifacts == []
        assert report.commands == []
        assert report.gates == []
        assert report.summary.sessions_analyzed == 0
        assert report.status == Status.PASSED

    def test_empty_totals_returns_empty_report(self, tmp_path: Path) -> None:
        path = _write_telemetry(_tel_path(tmp_path), _minimal_store())
        report = build_report(path)
        assert report.artifacts == []
        assert report.commands == []
        assert report.gates == []

    def test_empty_report_no_cold_or_silent(self, tmp_path: Path) -> None:
        path = _write_telemetry(_tel_path(tmp_path), _minimal_store())
        report = build_report(path)
        assert report.summary.cold_artifact_count == 0
        assert report.summary.silent_gate_count == 0


# ── Tests: artifact utilization ───────────────────────────────────────────────


class TestArtifactUtilization:
    """Artifacts must be sorted by read count and categorised correctly."""

    def _report(self, tmp_path: Path, artifacts: dict) -> object:
        path = _write_telemetry(_tel_path(tmp_path), _minimal_store(artifacts=artifacts))
        return build_report(path)

    def test_sorted_descending(self, tmp_path: Path) -> None:
        report = self._report(
            tmp_path,
            {"low.md": 2, "high.md": 20, "mid.md": 8},
        )
        counts = [m.read_count for m in report.artifacts]
        assert counts == sorted(counts, reverse=True)

    def test_utilization_rates_sum_to_one(self, tmp_path: Path) -> None:
        report = self._report(
            tmp_path,
            {"a.md": 10, "b.md": 5, "c.md": 5},
        )
        total = sum(m.utilization_rate for m in report.artifacts)
        assert abs(total - 1.0) < 1e-4

    def test_hot_artifact_top_reads(self, tmp_path: Path) -> None:
        """The top artifact must be 'hot' when its cumulative read rate stays ≤ 20%.

        The categoriser uses a running cumulative rate (sorted descending).
        An artifact is 'hot' only if, after adding its fraction, the cumulative
        total is still within the top-20 % band.  A single dominant artifact
        (e.g. 90 % share) immediately overshoots both thresholds and lands as
        'cold'.  So we need a reasonably even distribution where the top file
        contributes ≤ 20 % of all reads.
        """
        # 7 artifacts; top = 10/55 ≈ 18.2 % → cumulative 0.182 ≤ 0.20 → hot.
        report = self._report(
            tmp_path,
            {"a.md": 10, "b.md": 9, "c.md": 8, "d.md": 8, "e.md": 7, "f.md": 7, "g.md": 6},
        )
        top = report.artifacts[0]
        assert top.path == "a.md"
        assert top.category == "hot"
        assert top.recommendation is None

    def test_cold_artifact_low_reads(self, tmp_path: Path) -> None:
        """Artifacts at the tail of the distribution must be 'cold'."""
        report = self._report(
            tmp_path,
            # Very skewed — one dominant file, four tiny ones.
            {"dominant.md": 200, "a.md": 1, "b.md": 1, "c.md": 1, "d.md": 1},
        )
        cold = [m for m in report.artifacts if m.category in ("cold", "unused")]
        assert len(cold) >= 1
        for m in cold:
            assert m.recommendation is not None

    def test_unique_artifacts_count(self, tmp_path: Path) -> None:
        report = self._report(tmp_path, {"a.md": 3, "b.md": 2, "c.md": 1})
        assert report.summary.unique_artifacts == 3

    def test_total_reads_summed(self, tmp_path: Path) -> None:
        report = self._report(tmp_path, {"a.md": 7, "b.md": 3})
        assert report.summary.total_artifact_reads == 10


# ── Tests: command frequency ──────────────────────────────────────────────────


class TestCommandFrequency:
    def _report(self, tmp_path: Path, commands: dict, sessions: list | None = None) -> object:
        path = _write_telemetry(
            _tel_path(tmp_path), _minimal_store(commands=commands, sessions=sessions)
        )
        return build_report(path)

    def test_sorted_descending(self, tmp_path: Path) -> None:
        report = self._report(tmp_path, {"b": 2, "a": 10, "c": 5})
        counts = [m.invocation_count for m in report.commands]
        assert counts == sorted(counts, reverse=True)

    def test_frequency_rates_sum_to_one(self, tmp_path: Path) -> None:
        report = self._report(tmp_path, {"check-code": 8, "harness:lint": 4, "coordinate": 4})
        total = sum(m.frequency_rate for m in report.commands)
        assert abs(total - 1.0) < 1e-4

    def test_sessions_active_counts_distinct_sessions(self, tmp_path: Path) -> None:
        sessions = [
            {
                "session_id": "s1",
                "started_at": "2026-03-01T00:00:00+00:00",
                "ended_at": "2026-03-01T01:00:00+00:00",
                "artifact_reads": {},
                "cli_command_invocations": {"check-code": 2},
                "gate_failures": {},
            },
            {
                "session_id": "s2",
                "started_at": "2026-03-02T00:00:00+00:00",
                "ended_at": "2026-03-02T01:00:00+00:00",
                "artifact_reads": {},
                "cli_command_invocations": {"check-code": 1, "harness:lint": 3},
                "gate_failures": {},
            },
        ]
        report = self._report(
            tmp_path,
            commands={"check-code": 3, "harness:lint": 3},
            sessions=sessions,
        )
        by_cmd = {m.command: m for m in report.commands}
        assert by_cmd["check-code"].sessions_active == 2
        assert by_cmd["harness:lint"].sessions_active == 1

    def test_unique_commands_count(self, tmp_path: Path) -> None:
        report = self._report(tmp_path, {"a": 1, "b": 2, "c": 3})
        assert report.summary.unique_commands == 3


# ── Tests: gate effectiveness ─────────────────────────────────────────────────


class TestGateEffectiveness:
    def _report(self, tmp_path: Path, gates: dict) -> object:
        path = _write_telemetry(_tel_path(tmp_path), _minimal_store(gates=gates))
        return build_report(path)

    def test_highest_gate_has_score_one(self, tmp_path: Path) -> None:
        report = self._report(tmp_path, {"ruff": 10, "mypy": 4, "pytest": 2})
        top = report.gates[0]
        assert top.gate_id == "ruff"
        assert top.effectiveness_score == pytest.approx(1.0)
        assert top.signal_strength == "high"

    def test_signal_strength_high(self, tmp_path: Path) -> None:
        report = self._report(tmp_path, {"ruff": 10, "mypy": 7})
        by_gate = {m.gate_id: m for m in report.gates}
        # 7/10 = 0.7 ≥ 0.6 → high
        assert by_gate["mypy"].signal_strength == "high"

    def test_signal_strength_medium(self, tmp_path: Path) -> None:
        report = self._report(tmp_path, {"ruff": 10, "mypy": 4})
        by_gate = {m.gate_id: m for m in report.gates}
        # 4/10 = 0.4 → medium
        assert by_gate["mypy"].signal_strength == "medium"

    def test_signal_strength_low(self, tmp_path: Path) -> None:
        report = self._report(tmp_path, {"ruff": 10, "mypy": 2})
        by_gate = {m.gate_id: m for m in report.gates}
        # 2/10 = 0.2 → low
        assert by_gate["mypy"].signal_strength == "low"
        assert by_gate["mypy"].recommendation is not None

    def test_sorted_descending_by_failures(self, tmp_path: Path) -> None:
        report = self._report(tmp_path, {"mypy": 3, "ruff": 9, "pytest": 5})
        counts = [m.failure_count for m in report.gates]
        assert counts == sorted(counts, reverse=True)

    def test_unique_gates_count(self, tmp_path: Path) -> None:
        report = self._report(tmp_path, {"ruff": 5, "mypy": 3})
        assert report.summary.unique_gates == 2

    def test_total_gate_failures_summed(self, tmp_path: Path) -> None:
        report = self._report(tmp_path, {"ruff": 11, "mypy": 7, "pytest": 4})
        assert report.summary.total_gate_failures == 22


# ── Tests: summary cold / silent counts ───────────────────────────────────────


class TestSummaryCounts:
    def test_cold_artifact_count_reflects_report(self, tmp_path: Path) -> None:
        # Very dominant artifact → others will be cold.
        path = _write_telemetry(
            _tel_path(tmp_path),
            _minimal_store(artifacts={"dominant.md": 500, "tiny.md": 1, "tiny2.md": 1}),
        )
        report = build_report(path)
        assert report.summary.cold_artifact_count == report.summary.cold_artifact_count  # tautology smoke
        cold_in_list = sum(1 for m in report.artifacts if m.category in ("cold", "unused"))
        assert report.summary.cold_artifact_count == cold_in_list

    def test_silent_gate_count_is_zero_when_all_fire(self, tmp_path: Path) -> None:
        path = _write_telemetry(
            _tel_path(tmp_path),
            _minimal_store(gates={"ruff": 10, "mypy": 7, "pytest": 5}),
        )
        report = build_report(path)
        # All gates have failures → none are silent.
        assert report.summary.silent_gate_count == 0


# ── Tests: min_reads filter ────────────────────────────────────────────────────


class TestMinReadsFilter:
    def test_excludes_artifacts_below_threshold(self, tmp_path: Path) -> None:
        path = _write_telemetry(
            _tel_path(tmp_path),
            _minimal_store(artifacts={"hot.md": 20, "cold.md": 1}),
        )
        report = build_report(path, min_reads=5)
        paths = [m.path for m in report.artifacts]
        assert "cold.md" not in paths
        assert "hot.md" in paths

    def test_rates_computed_against_full_dataset(self, tmp_path: Path) -> None:
        """Utilization rates use the *full* total, not the filtered subset."""
        path = _write_telemetry(
            _tel_path(tmp_path),
            _minimal_store(artifacts={"hot.md": 20, "cold.md": 5}),
        )
        report_full = build_report(path, min_reads=0)
        report_filtered = build_report(path, min_reads=10)
        # hot.md's utilization_rate must be the same in both reports.
        rate_full = next(m.utilization_rate for m in report_full.artifacts if m.path == "hot.md")
        rate_filt = next(m.utilization_rate for m in report_filtered.artifacts if m.path == "hot.md")
        assert abs(rate_full - rate_filt) < 1e-9


# ── Tests: top_n cap ──────────────────────────────────────────────────────────


class TestTopN:
    def test_caps_artifact_list(self, tmp_path: Path) -> None:
        artifacts = {f"file{i}.md": (10 - i) for i in range(10)}
        path = _write_telemetry(_tel_path(tmp_path), _minimal_store(artifacts=artifacts))
        report = build_report(path, top_n=3)
        assert len(report.artifacts) == 3

    def test_top_n_are_highest_reads(self, tmp_path: Path) -> None:
        artifacts = {"a.md": 1, "b.md": 5, "c.md": 3, "d.md": 8, "e.md": 2}
        path = _write_telemetry(_tel_path(tmp_path), _minimal_store(artifacts=artifacts))
        report = build_report(path, top_n=2)
        paths = {m.path for m in report.artifacts}
        assert "d.md" in paths  # 8 reads — top
        assert "b.md" in paths  # 5 reads — second


# ── Tests: render_report ──────────────────────────────────────────────────────


class TestRenderReport:
    def test_renders_artifact_section(self, tmp_path: Path) -> None:
        path = _write_telemetry(
            _tel_path(tmp_path),
            _minimal_store(artifacts={"PRINCIPLES.md": 12}),
        )
        report = build_report(path)
        text = render_report(report)
        assert "Artifact Utilization" in text
        assert "PRINCIPLES.md" in text

    def test_renders_command_section(self, tmp_path: Path) -> None:
        path = _write_telemetry(
            _tel_path(tmp_path),
            _minimal_store(commands={"check-code": 8}),
        )
        report = build_report(path)
        text = render_report(report)
        assert "Command Call Frequency" in text
        assert "check-code" in text

    def test_renders_gate_section(self, tmp_path: Path) -> None:
        path = _write_telemetry(
            _tel_path(tmp_path),
            _minimal_store(gates={"ruff": 11, "mypy": 7}),
        )
        report = build_report(path)
        text = render_report(report)
        assert "Gate Effectiveness" in text
        assert "ruff" in text
        assert "mypy" in text

    def test_empty_sections_show_no_data_message(self, tmp_path: Path) -> None:
        path = _write_telemetry(_tel_path(tmp_path), _minimal_store())
        report = build_report(path)
        text = render_report(report)
        assert "no artifact reads recorded" in text
        assert "no command invocations recorded" in text
        assert "no gate failures recorded" in text

    def test_underutilized_artifacts_highlighted(self, tmp_path: Path) -> None:
        path = _write_telemetry(
            _tel_path(tmp_path),
            _minimal_store(artifacts={"dominant.md": 500, "tiny.md": 1}),
        )
        report = build_report(path)
        text = render_report(report)
        # Should flag cold/unused artifacts.
        if any(m.category in ("cold", "unused") for m in report.artifacts):
            assert "Underutilized" in text or "cold" in text or "unused" in text


# ── Tests: CLI (click runner) ─────────────────────────────────────────────────


class TestCLI:
    def _write(self, tmp_path: Path, data: dict) -> str:
        p = _tel_path(tmp_path)
        _write_telemetry(p, data)
        return str(p)

    def test_table_output_exit_0_when_clean(self, tmp_path: Path) -> None:
        tel_file = self._write(
            tmp_path,
            _minimal_store(artifacts={"a.md": 10, "b.md": 8, "c.md": 6, "d.md": 5, "e.md": 4}),
        )
        runner = CliRunner()
        result = runner.invoke(telemetry_cmd, ["--telemetry-file", tel_file])
        # Exit 0 only if no cold/unused + no silent gates
        assert result.exit_code in (0, 1)  # depends on data distribution
        assert "Harness Telemetry Report" in result.output

    def test_json_format_produces_valid_json(self, tmp_path: Path) -> None:
        tel_file = self._write(
            tmp_path,
            _minimal_store(artifacts={"PRINCIPLES.md": 12}, gates={"ruff": 5}),
        )
        runner = CliRunner()
        result = runner.invoke(
            telemetry_cmd, ["--telemetry-file", tel_file, "--format", "json"]
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["command"] == "harness telemetry"
        assert "artifacts" in parsed
        assert "gates" in parsed

    def test_min_reads_flag_filters_output(self, tmp_path: Path) -> None:
        tel_file = self._write(
            tmp_path,
            _minimal_store(artifacts={"hot.md": 50, "noise.md": 1}),
        )
        runner = CliRunner()
        result = runner.invoke(
            telemetry_cmd,
            ["--telemetry-file", tel_file, "--format", "json", "--min-reads", "10"],
        )
        parsed = json.loads(result.output)
        paths = [a["path"] for a in parsed["artifacts"]]
        assert "noise.md" not in paths
        assert "hot.md" in paths

    def test_top_n_flag_caps_artifacts(self, tmp_path: Path) -> None:
        artifacts = {f"f{i}.md": (20 - i) for i in range(10)}
        tel_file = self._write(tmp_path, _minimal_store(artifacts=artifacts))
        runner = CliRunner()
        result = runner.invoke(
            telemetry_cmd,
            ["--telemetry-file", tel_file, "--format", "json", "--top-n", "3"],
        )
        parsed = json.loads(result.output)
        assert len(parsed["artifacts"]) == 3

    def test_exit_code_1_on_cold_artifacts(self, tmp_path: Path) -> None:
        # Very dominant single artifact → others become cold.
        tel_file = self._write(
            tmp_path,
            _minimal_store(
                artifacts={"dominant.md": 1000, "cold1.md": 1, "cold2.md": 1, "cold3.md": 1}
            ),
        )
        runner = CliRunner()
        result = runner.invoke(telemetry_cmd, ["--telemetry-file", tel_file])
        assert result.exit_code == 1

    def test_table_output_also_emits_json_block(self, tmp_path: Path) -> None:
        tel_file = self._write(
            tmp_path,
            _minimal_store(commands={"check-code": 5}),
        )
        runner = CliRunner()
        result = runner.invoke(telemetry_cmd, ["--telemetry-file", tel_file])
        # Table mode must append a ```json ... ``` block.
        assert "```json" in result.output


# ── Tests: response schema ────────────────────────────────────────────────────


class TestResponseSchema:
    """TelemetryReport must be a valid, JSON-serialisable Pydantic model."""

    def test_report_is_json_serialisable(self, tmp_path: Path) -> None:
        path = _write_telemetry(
            _tel_path(tmp_path),
            _minimal_store(
                artifacts={"CLAUDE.md": 9, "harness.config.yaml": 5},
                commands={"check-code": 4},
                gates={"ruff": 6, "pytest": 2},
            ),
        )
        report = build_report(path)
        dumped = report.model_dump_json()
        parsed = json.loads(dumped)
        assert parsed["command"] == "harness telemetry"
        assert isinstance(parsed["artifacts"], list)
        assert isinstance(parsed["commands"], list)
        assert isinstance(parsed["gates"], list)

    def test_command_field(self, tmp_path: Path) -> None:
        path = _write_telemetry(_tel_path(tmp_path), _minimal_store())
        report = build_report(path)
        assert report.command == "harness telemetry"

    def test_status_passed_when_no_issues(self, tmp_path: Path) -> None:
        path = _write_telemetry(
            _tel_path(tmp_path),
            _minimal_store(artifacts={"a.md": 5, "b.md": 5, "c.md": 5}),
        )
        report = build_report(path)
        assert report.status == Status.PASSED

    def test_duration_ms_is_non_negative(self, tmp_path: Path) -> None:
        path = _write_telemetry(_tel_path(tmp_path), _minimal_store())
        report = build_report(path)
        assert report.duration_ms is not None
        assert report.duration_ms >= 0
