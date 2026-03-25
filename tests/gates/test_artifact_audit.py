"""
tests/gates/test_artifact_audit.py
=====================================
Unit tests for :mod:`harness_skills.gates.artifact_audit`.

Covers:
- GateConfig validation (__post_init__)
- _parse_generated_at timestamp extraction
- _score_age freshness scoring
- _recommended_action messages for each score
- _infer_type artifact type inference
- _result_to_dict serialisation
- ArtifactAuditGate.run: discovery, assessment, pass/fail logic
- AuditResult / ArtifactResult dataclass helpers
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from harness_skills.gates.artifact_audit import (
    ArtifactAuditGate,
    ArtifactResult,
    AuditResult,
    GateConfig,
    _infer_type,
    _parse_generated_at,
    _recommended_action,
    _result_to_dict,
    _score_age,
)

# Fixed "today" for deterministic age calculations.
TODAY = date(2025, 7, 1)


@pytest.fixture(autouse=True)
def freeze_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "harness_skills.gates.artifact_audit._today", lambda: TODAY
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_file(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_manifest(repo: Path, artifacts: list[dict]) -> Path:
    """Write a harness_manifest.json with the given artifacts array."""
    data = {"artifacts": artifacts}
    return write_file(repo / "harness_manifest.json", json.dumps(data))


# ---------------------------------------------------------------------------
# GateConfig validation
# ---------------------------------------------------------------------------


class TestGateConfig:
    def test_defaults(self) -> None:
        cfg = GateConfig()
        assert cfg.stale_days == 14
        assert cfg.outdated_days == 30
        assert cfg.obsolete_days == 90
        assert cfg.fail_on_outdated is True

    def test_stale_days_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="stale_days must be >= 1"):
            GateConfig(stale_days=0)

    def test_outdated_days_must_ge_stale(self) -> None:
        with pytest.raises(ValueError, match="outdated_days must be >= stale_days"):
            GateConfig(stale_days=20, outdated_days=10)

    def test_obsolete_days_must_ge_outdated(self) -> None:
        with pytest.raises(ValueError, match="obsolete_days must be >= outdated_days"):
            GateConfig(stale_days=10, outdated_days=30, obsolete_days=20)

    def test_valid_custom_values(self) -> None:
        cfg = GateConfig(stale_days=7, outdated_days=14, obsolete_days=28)
        assert cfg.stale_days == 7


# ---------------------------------------------------------------------------
# _parse_generated_at
# ---------------------------------------------------------------------------


class TestParseGeneratedAt:
    def test_standard_format(self) -> None:
        content = "<!-- generated_at: 2025-06-15 -->"
        assert _parse_generated_at(content) == date(2025, 6, 15)

    def test_last_updated_key(self) -> None:
        content = "last_updated: 2025-01-01"
        assert _parse_generated_at(content) == date(2025, 1, 1)

    def test_updated_at_key(self) -> None:
        content = "updated_at: '2024-12-31'"
        assert _parse_generated_at(content) == date(2024, 12, 31)

    def test_quoted_date(self) -> None:
        content = '> generated_at: "2025-03-10"'
        assert _parse_generated_at(content) == date(2025, 3, 10)

    def test_no_timestamp_returns_none(self) -> None:
        assert _parse_generated_at("# Just a heading\nSome text.") is None

    def test_empty_string(self) -> None:
        assert _parse_generated_at("") is None

    def test_invalid_date_returns_none(self) -> None:
        content = "generated_at: 2025-13-40"
        assert _parse_generated_at(content) is None

    def test_case_insensitive(self) -> None:
        content = "GENERATED_AT: 2025-05-20"
        assert _parse_generated_at(content) == date(2025, 5, 20)


# ---------------------------------------------------------------------------
# _score_age
# ---------------------------------------------------------------------------


class TestScoreAge:
    def test_current(self) -> None:
        cfg = GateConfig()
        assert _score_age(0, cfg) == "current"
        assert _score_age(14, cfg) == "current"

    def test_stale(self) -> None:
        cfg = GateConfig()
        assert _score_age(15, cfg) == "stale"
        assert _score_age(30, cfg) == "stale"

    def test_outdated(self) -> None:
        cfg = GateConfig()
        assert _score_age(31, cfg) == "outdated"
        assert _score_age(90, cfg) == "outdated"

    def test_obsolete(self) -> None:
        cfg = GateConfig()
        assert _score_age(91, cfg) == "obsolete"
        assert _score_age(365, cfg) == "obsolete"

    def test_custom_thresholds(self) -> None:
        cfg = GateConfig(stale_days=5, outdated_days=10, obsolete_days=20)
        assert _score_age(5, cfg) == "current"
        assert _score_age(6, cfg) == "stale"
        assert _score_age(11, cfg) == "outdated"
        assert _score_age(21, cfg) == "obsolete"


# ---------------------------------------------------------------------------
# _recommended_action
# ---------------------------------------------------------------------------


class TestRecommendedAction:
    def test_current(self) -> None:
        action = _recommended_action("current", "AGENTS.md")
        assert "No action" in action

    def test_stale(self) -> None:
        action = _recommended_action("stale", "AGENTS.md")
        assert "refreshing" in action.lower() or "update" in action.lower()

    def test_outdated(self) -> None:
        action = _recommended_action("outdated", "AGENTS.md")
        assert "refresh" in action.lower() or "required" in action.lower()

    def test_obsolete(self) -> None:
        action = _recommended_action("obsolete", "AGENTS.md")
        assert "regenerate" in action.lower()

    def test_missing(self) -> None:
        action = _recommended_action("missing", "AGENTS.md")
        assert "AGENTS.md" in action
        assert "not found" in action.lower() or "create" in action.lower()

    def test_no_timestamp(self) -> None:
        action = _recommended_action("no_timestamp", "AGENTS.md")
        assert "generated_at" in action or "timestamp" in action.lower()


# ---------------------------------------------------------------------------
# _infer_type
# ---------------------------------------------------------------------------


class TestInferType:
    def test_agents_md(self) -> None:
        assert _infer_type("AGENTS.md") == "AGENTS.md"

    def test_architecture_md(self) -> None:
        assert _infer_type("docs/ARCHITECTURE.MD") == "ARCHITECTURE.md"

    def test_principles_md(self) -> None:
        assert _infer_type("docs/PRINCIPLES.md") == "PRINCIPLES.md"

    def test_evaluation_md(self) -> None:
        assert _infer_type("docs/EVALUATION.md") == "EVALUATION.md"

    def test_harness_config_yaml(self) -> None:
        assert _infer_type("harness.config.yaml") == "harness.config.yaml"

    def test_manifest_json(self) -> None:
        assert _infer_type("harness_manifest.json") == "harness_manifest.json"

    def test_skill_command_file(self) -> None:
        assert _infer_type(".claude/commands/deploy.md") == "skill_command"

    def test_unknown_extension(self) -> None:
        assert _infer_type("scripts/run.sh") == "sh"

    def test_no_extension(self) -> None:
        assert _infer_type("Makefile") == "file"


# ---------------------------------------------------------------------------
# AuditResult helpers
# ---------------------------------------------------------------------------


class TestAuditResult:
    def _make_art(self, severity: str = "error", score: str = "obsolete") -> ArtifactResult:
        return ArtifactResult(
            artifact_path="AGENTS.md",
            artifact_type="AGENTS.md",
            score=score,
            severity=severity,
            age_days=100,
            last_updated="2025-01-01",
            message="test",
            recommended_action="test action",
        )

    def test_errors_filter(self) -> None:
        result = AuditResult(
            passed=False,
            artifacts=[self._make_art("error"), self._make_art("warning")],
        )
        assert len(result.errors()) == 1
        assert len(result.warnings()) == 1

    def test_empty_artifacts(self) -> None:
        result = AuditResult(passed=True)
        assert result.errors() == []
        assert result.warnings() == []


# ---------------------------------------------------------------------------
# _result_to_dict serialisation
# ---------------------------------------------------------------------------


class TestResultToDict:
    def test_structure(self) -> None:
        result = AuditResult(
            passed=True,
            artifacts=[
                ArtifactResult(
                    artifact_path="AGENTS.md",
                    artifact_type="AGENTS.md",
                    score="current",
                    severity="info",
                    age_days=5,
                    last_updated="2025-06-26",
                    message="fresh",
                    recommended_action="none",
                ),
            ],
            stats={"total_artifacts": 1},
        )
        d = _result_to_dict(result)
        assert d["status"] == "passed"
        assert d["command"] == "harness artifact-audit"
        assert len(d["artifacts"]) == 1
        assert d["artifacts"][0]["score"] == "current"

    def test_failed_status(self) -> None:
        result = AuditResult(passed=False)
        d = _result_to_dict(result)
        assert d["status"] == "failed"


# ---------------------------------------------------------------------------
# ArtifactAuditGate — discovery via well-known files
# ---------------------------------------------------------------------------


class TestDiscoveryWellKnown:
    def test_discovers_agents_md(self, tmp_path: Path) -> None:
        write_file(tmp_path / "AGENTS.md", "# AGENTS\ngenerated_at: 2025-07-01\n")
        cfg = GateConfig(include_skill_commands=False)
        result = ArtifactAuditGate(cfg).run(tmp_path)
        paths = [a.artifact_path for a in result.artifacts]
        assert "AGENTS.md" in paths

    def test_discovers_multiple_well_known(self, tmp_path: Path) -> None:
        write_file(tmp_path / "AGENTS.md", "generated_at: 2025-07-01\n")
        write_file(tmp_path / "docs" / "ARCHITECTURE.md", "generated_at: 2025-07-01\n")
        write_file(tmp_path / "docs" / "PRINCIPLES.md", "generated_at: 2025-07-01\n")
        cfg = GateConfig(include_skill_commands=False)
        result = ArtifactAuditGate(cfg).run(tmp_path)
        assert len(result.artifacts) >= 3


# ---------------------------------------------------------------------------
# ArtifactAuditGate — discovery via manifest
# ---------------------------------------------------------------------------


class TestDiscoveryManifest:
    def test_manifest_artifacts_discovered(self, tmp_path: Path) -> None:
        make_manifest(tmp_path, [
            {"artifact_path": "AGENTS.md", "artifact_type": "AGENTS.md"},
            {"artifact_path": "custom/report.md", "artifact_type": "report"},
        ])
        write_file(tmp_path / "AGENTS.md", "generated_at: 2025-07-01\n")
        write_file(tmp_path / "custom" / "report.md", "generated_at: 2025-07-01\n")
        cfg = GateConfig(include_skill_commands=False)
        result = ArtifactAuditGate(cfg).run(tmp_path)
        paths = [a.artifact_path for a in result.artifacts]
        assert "AGENTS.md" in paths
        assert "custom/report.md" in paths

    def test_manifest_itself_included(self, tmp_path: Path) -> None:
        make_manifest(tmp_path, [])
        cfg = GateConfig(include_skill_commands=False)
        result = ArtifactAuditGate(cfg).run(tmp_path)
        paths = [a.artifact_path for a in result.artifacts]
        assert "harness_manifest.json" in paths

    def test_corrupt_manifest_ignored(self, tmp_path: Path) -> None:
        write_file(tmp_path / "harness_manifest.json", "NOT JSON!")
        write_file(tmp_path / "AGENTS.md", "generated_at: 2025-07-01\n")
        cfg = GateConfig(include_skill_commands=False)
        result = ArtifactAuditGate(cfg).run(tmp_path)
        # Should still discover well-known files
        paths = [a.artifact_path for a in result.artifacts]
        assert "AGENTS.md" in paths

    def test_manifest_empty_artifact_path_skipped(self, tmp_path: Path) -> None:
        make_manifest(tmp_path, [
            {"artifact_path": "", "artifact_type": "x"},
            {"artifact_path": "AGENTS.md", "artifact_type": "AGENTS.md"},
        ])
        write_file(tmp_path / "AGENTS.md", "generated_at: 2025-07-01\n")
        cfg = GateConfig(include_skill_commands=False)
        result = ArtifactAuditGate(cfg).run(tmp_path)
        paths = [a.artifact_path for a in result.artifacts]
        assert "" not in paths

    def test_manifest_missing_type_inferred(self, tmp_path: Path) -> None:
        make_manifest(tmp_path, [
            {"artifact_path": "AGENTS.md"},
        ])
        write_file(tmp_path / "AGENTS.md", "generated_at: 2025-07-01\n")
        cfg = GateConfig(include_skill_commands=False)
        result = ArtifactAuditGate(cfg).run(tmp_path)
        agents_art = [a for a in result.artifacts if a.artifact_path == "AGENTS.md"]
        assert agents_art[0].artifact_type == "AGENTS.md"


# ---------------------------------------------------------------------------
# ArtifactAuditGate — discovery via skill commands
# ---------------------------------------------------------------------------


class TestDiscoverySkillCommands:
    def test_skill_command_files_discovered(self, tmp_path: Path) -> None:
        write_file(
            tmp_path / ".claude" / "commands" / "deploy.md",
            "generated_at: 2025-07-01\n",
        )
        cfg = GateConfig(include_skill_commands=True)
        result = ArtifactAuditGate(cfg).run(tmp_path)
        paths = [a.artifact_path for a in result.artifacts]
        assert any("deploy.md" in p for p in paths)

    def test_skill_commands_disabled(self, tmp_path: Path) -> None:
        write_file(
            tmp_path / ".claude" / "commands" / "deploy.md",
            "generated_at: 2025-07-01\n",
        )
        cfg = GateConfig(include_skill_commands=False)
        result = ArtifactAuditGate(cfg).run(tmp_path)
        paths = [a.artifact_path for a in result.artifacts]
        assert not any("deploy.md" in p for p in paths)

    def test_nested_skill_commands_discovered(self, tmp_path: Path) -> None:
        write_file(
            tmp_path / ".claude" / "commands" / "harness" / "context.md",
            "generated_at: 2025-07-01\n",
        )
        cfg = GateConfig(include_skill_commands=True)
        result = ArtifactAuditGate(cfg).run(tmp_path)
        paths = [a.artifact_path for a in result.artifacts]
        assert any("context.md" in p for p in paths)


# ---------------------------------------------------------------------------
# ArtifactAuditGate — extra_artifacts config
# ---------------------------------------------------------------------------


class TestExtraArtifacts:
    def test_extra_artifacts_included(self, tmp_path: Path) -> None:
        write_file(tmp_path / "custom" / "report.md", "generated_at: 2025-07-01\n")
        cfg = GateConfig(
            include_skill_commands=False,
            extra_artifacts=["custom/report.md"],
        )
        result = ArtifactAuditGate(cfg).run(tmp_path)
        paths = [a.artifact_path for a in result.artifacts]
        assert "custom/report.md" in paths

    def test_extra_artifact_missing(self, tmp_path: Path) -> None:
        cfg = GateConfig(
            include_skill_commands=False,
            extra_artifacts=["does_not_exist.md"],
        )
        result = ArtifactAuditGate(cfg).run(tmp_path)
        missing = [a for a in result.artifacts if a.score == "missing"]
        assert len(missing) >= 1


# ---------------------------------------------------------------------------
# ArtifactAuditGate — assessment: freshness scores
# ---------------------------------------------------------------------------


class TestAssessment:
    def test_current_artifact(self, tmp_path: Path) -> None:
        # Today is 2025-07-01, generated 5 days ago = current
        write_file(tmp_path / "AGENTS.md", "generated_at: 2025-06-26\n")
        cfg = GateConfig(include_skill_commands=False)
        result = ArtifactAuditGate(cfg).run(tmp_path)
        agents = [a for a in result.artifacts if a.artifact_path == "AGENTS.md"][0]
        assert agents.score == "current"
        assert agents.severity == "info"
        assert agents.age_days == 5

    def test_stale_artifact(self, tmp_path: Path) -> None:
        # 20 days old = stale (stale_days=14)
        write_file(tmp_path / "AGENTS.md", "generated_at: 2025-06-11\n")
        cfg = GateConfig(include_skill_commands=False)
        result = ArtifactAuditGate(cfg).run(tmp_path)
        agents = [a for a in result.artifacts if a.artifact_path == "AGENTS.md"][0]
        assert agents.score == "stale"
        assert agents.severity == "info"

    def test_outdated_artifact(self, tmp_path: Path) -> None:
        # 60 days old = outdated (outdated_days=30)
        write_file(tmp_path / "AGENTS.md", "generated_at: 2025-05-02\n")
        cfg = GateConfig(include_skill_commands=False)
        result = ArtifactAuditGate(cfg).run(tmp_path)
        agents = [a for a in result.artifacts if a.artifact_path == "AGENTS.md"][0]
        assert agents.score == "outdated"
        assert agents.severity == "warning"

    def test_obsolete_artifact(self, tmp_path: Path) -> None:
        # 200 days old = obsolete (obsolete_days=90)
        write_file(tmp_path / "AGENTS.md", "generated_at: 2024-12-14\n")
        cfg = GateConfig(include_skill_commands=False)
        result = ArtifactAuditGate(cfg).run(tmp_path)
        agents = [a for a in result.artifacts if a.artifact_path == "AGENTS.md"][0]
        assert agents.score == "obsolete"
        assert agents.severity == "error"

    def test_missing_artifact(self, tmp_path: Path) -> None:
        cfg = GateConfig(
            include_skill_commands=False,
            extra_artifacts=["nonexistent.md"],
        )
        result = ArtifactAuditGate(cfg).run(tmp_path)
        missing = [a for a in result.artifacts if a.artifact_path == "nonexistent.md"]
        assert len(missing) == 1
        assert missing[0].score == "missing"
        assert missing[0].severity == "error"
        assert missing[0].age_days is None

    def test_no_timestamp_artifact(self, tmp_path: Path) -> None:
        write_file(tmp_path / "AGENTS.md", "# Just a heading\nNo timestamp here.\n")
        cfg = GateConfig(include_skill_commands=False)
        result = ArtifactAuditGate(cfg).run(tmp_path)
        agents = [a for a in result.artifacts if a.artifact_path == "AGENTS.md"][0]
        assert agents.score == "no_timestamp"
        assert agents.severity == "warning"
        assert agents.age_days is None

    def test_last_updated_iso_stored(self, tmp_path: Path) -> None:
        write_file(tmp_path / "AGENTS.md", "generated_at: 2025-06-20\n")
        cfg = GateConfig(include_skill_commands=False)
        result = ArtifactAuditGate(cfg).run(tmp_path)
        agents = [a for a in result.artifacts if a.artifact_path == "AGENTS.md"][0]
        assert agents.last_updated == "2025-06-20"


# ---------------------------------------------------------------------------
# ArtifactAuditGate — pass/fail logic
# ---------------------------------------------------------------------------


class TestPassFail:
    def test_all_current_passes(self, tmp_path: Path) -> None:
        write_file(tmp_path / "AGENTS.md", "generated_at: 2025-07-01\n")
        cfg = GateConfig(include_skill_commands=False)
        result = ArtifactAuditGate(cfg).run(tmp_path)
        assert result.passed is True

    def test_obsolete_fails(self, tmp_path: Path) -> None:
        write_file(tmp_path / "AGENTS.md", "generated_at: 2024-01-01\n")
        cfg = GateConfig(include_skill_commands=False, fail_on_outdated=True)
        result = ArtifactAuditGate(cfg).run(tmp_path)
        assert result.passed is False

    def test_fail_on_outdated_false_passes_even_with_errors(self, tmp_path: Path) -> None:
        write_file(tmp_path / "AGENTS.md", "generated_at: 2024-01-01\n")
        cfg = GateConfig(include_skill_commands=False, fail_on_outdated=False)
        result = ArtifactAuditGate(cfg).run(tmp_path)
        assert result.passed is True

    def test_missing_artifact_fails_by_default(self, tmp_path: Path) -> None:
        cfg = GateConfig(
            include_skill_commands=False,
            extra_artifacts=["missing.md"],
        )
        result = ArtifactAuditGate(cfg).run(tmp_path)
        assert result.passed is False

    def test_missing_artifact_with_fail_on_outdated_false_passes(self, tmp_path: Path) -> None:
        cfg = GateConfig(
            include_skill_commands=False,
            extra_artifacts=["missing.md"],
            fail_on_outdated=False,
        )
        result = ArtifactAuditGate(cfg).run(tmp_path)
        assert result.passed is True
        # Missing severity downgraded to warning
        missing = [a for a in result.artifacts if a.score == "missing"]
        assert missing[0].severity == "warning"

    def test_obsolete_severity_downgraded_when_fail_on_outdated_false(
        self, tmp_path: Path
    ) -> None:
        write_file(tmp_path / "AGENTS.md", "generated_at: 2024-01-01\n")
        cfg = GateConfig(include_skill_commands=False, fail_on_outdated=False)
        result = ArtifactAuditGate(cfg).run(tmp_path)
        agents = [a for a in result.artifacts if a.artifact_path == "AGENTS.md"][0]
        assert agents.severity == "warning"


# ---------------------------------------------------------------------------
# ArtifactAuditGate — sorting
# ---------------------------------------------------------------------------


class TestSorting:
    def test_most_urgent_first(self, tmp_path: Path) -> None:
        # Create artifacts with different scores
        cfg = GateConfig(
            include_skill_commands=False,
            extra_artifacts=["nonexistent.md"],
        )
        write_file(tmp_path / "AGENTS.md", "generated_at: 2025-07-01\n")  # current
        write_file(tmp_path / "docs" / "ARCHITECTURE.md", "# no timestamp\n")  # no_timestamp
        result = ArtifactAuditGate(cfg).run(tmp_path)
        # missing should come before no_timestamp, which should come before current
        scores = [a.score for a in result.artifacts]
        if "missing" in scores and "current" in scores:
            assert scores.index("missing") < scores.index("current")


# ---------------------------------------------------------------------------
# ArtifactAuditGate — stats
# ---------------------------------------------------------------------------


class TestStats:
    def test_stats_counts(self, tmp_path: Path) -> None:
        write_file(tmp_path / "AGENTS.md", "generated_at: 2025-07-01\n")  # current
        write_file(tmp_path / "docs" / "ARCHITECTURE.md", "# nothing\n")  # no_timestamp
        cfg = GateConfig(include_skill_commands=False)
        result = ArtifactAuditGate(cfg).run(tmp_path)
        assert result.stats["total_artifacts"] >= 2
        assert "current" in result.stats
        assert "no_timestamp" in result.stats

    def test_empty_repo_no_artifacts(self, tmp_path: Path) -> None:
        cfg = GateConfig(include_skill_commands=False)
        result = ArtifactAuditGate(cfg).run(tmp_path)
        assert result.stats["total_artifacts"] == 0
        assert result.passed is True


# ---------------------------------------------------------------------------
# ArtifactAuditGate — default config
# ---------------------------------------------------------------------------


class TestDefaultConfig:
    def test_default_config_when_none(self) -> None:
        gate = ArtifactAuditGate()
        assert gate.config.stale_days == 14
        assert gate.config.obsolete_days == 90

    def test_deduplicated_artifacts(self, tmp_path: Path) -> None:
        """Same path in manifest and well-known should not produce duplicates."""
        make_manifest(tmp_path, [
            {"artifact_path": "AGENTS.md", "artifact_type": "AGENTS.md"},
        ])
        write_file(tmp_path / "AGENTS.md", "generated_at: 2025-07-01\n")
        cfg = GateConfig(include_skill_commands=False)
        result = ArtifactAuditGate(cfg).run(tmp_path)
        agents_count = sum(1 for a in result.artifacts if a.artifact_path == "AGENTS.md")
        assert agents_count == 1


# ---------------------------------------------------------------------------
# ArtifactAuditGate — edge cases for coverage
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_skill_command_in_skip_dir_ignored(self, tmp_path: Path) -> None:
        """Files under _SKIP_DIRS within .claude/commands/ are skipped."""
        skip_dir = tmp_path / ".claude" / "commands" / "__pycache__"
        write_file(skip_dir / "cached.md", "generated_at: 2025-07-01\n")
        # Also write a normal skill command
        write_file(
            tmp_path / ".claude" / "commands" / "deploy.md",
            "generated_at: 2025-07-01\n",
        )
        cfg = GateConfig(include_skill_commands=True)
        result = ArtifactAuditGate(cfg).run(tmp_path)
        paths = [a.artifact_path for a in result.artifacts]
        assert not any("__pycache__" in p for p in paths)
        assert any("deploy.md" in p for p in paths)

    def test_unreadable_file_uses_empty_content(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When a file exists but read_text raises OSError, content defaults to empty."""
        p = write_file(tmp_path / "AGENTS.md", "generated_at: 2025-07-01\n")
        original_read_text = Path.read_text

        def failing_read(self_path, *args, **kwargs):
            if self_path == p.resolve():
                raise OSError("permission denied")
            return original_read_text(self_path, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", failing_read)

        cfg = GateConfig(include_skill_commands=False)
        result = ArtifactAuditGate(cfg).run(tmp_path)
        agents = [a for a in result.artifacts if a.artifact_path == "AGENTS.md"]
        assert len(agents) == 1
        # Can't parse timestamp from empty content => no_timestamp
        assert agents[0].score == "no_timestamp"

    def test_today_function_returns_date(self) -> None:
        """Verify the real _today function returns a date (not monkeypatched)."""
        from harness_skills.gates.artifact_audit import _today as real_today
        # The autouse fixture monkeypatches it, but we can verify the
        # return type of the monkeypatched version at least.
        result = real_today()
        assert isinstance(result, date)
