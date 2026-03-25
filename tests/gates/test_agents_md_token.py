"""
tests/gates/test_agents_md_token.py
=====================================
Unit tests for :mod:`harness_skills.gates.agents_md_token`.

Test strategy
-------------
* **Fixture helpers** write temporary AGENTS.md files so that the real
  file-existence and path-resolution logic runs against the actual filesystem.
* Token estimation is validated against the mathematical formula directly,
  including boundary values (exactly at budget, one token over, zero-length).
* Every violation kind (``over_budget``, ``read_error``) is exercised.
* ``fail_on_error=False`` (advisory mode) is verified: violations become
  warnings and the gate still passes.
* Multi-file scenarios: some files within budget, some over — ensures the
  gate collects *all* violations rather than short-circuiting.
* ``glob_pattern`` customisation is tested to ensure discovery works beyond
  the default ``**/AGENTS.md`` pattern.
* ``chars_per_token`` override is verified: changing the ratio changes the
  estimated count proportionally.
* No-files-found case produces a warning and passes.
* Config defaults match documented spec (max_tokens=800, glob=**/AGENTS.md,
  chars_per_token=4.0).
* A lightweight integration run exercises the :class:`AgentsMdTokenGate`
  end-to-end via ``GateResult`` attribute checks.
"""

from __future__ import annotations

import math
import textwrap
from pathlib import Path

import pytest

from harness_skills.gates.agents_md_token import (
    AgentsMdTokenGate,
    GateResult,
    Violation,
    _estimate_tokens,
)
from harness_skills.models.gate_configs import AgentsMdTokenGateConfig


# ---------------------------------------------------------------------------
# Helpers — file writers
# ---------------------------------------------------------------------------


def write_agents_md(path: Path, content: str) -> Path:
    """Write *content* to *path*, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def agents_md_with_tokens(
    path: Path,
    target_tokens: int,
    chars_per_token: float = 4.0,
) -> Path:
    """Write an AGENTS.md whose estimated token count is *exactly* target_tokens.

    Uses ASCII 'x' characters so char-count is deterministic.
    """
    chars = math.ceil(target_tokens * chars_per_token)
    # Subtract 1 to stay at or just below ceiling to hit the exact token count.
    content = "x" * chars
    return write_agents_md(path, content)


# ---------------------------------------------------------------------------
# _estimate_tokens — unit tests
# ---------------------------------------------------------------------------


class TestEstimateTokens:
    def test_empty_string_returns_zero(self) -> None:
        assert _estimate_tokens("", 4.0) == 0

    def test_exact_multiple_of_chars_per_token(self) -> None:
        # 400 chars / 4.0 = 100 tokens exactly
        assert _estimate_tokens("x" * 400, 4.0) == 100

    def test_ceiling_applied_for_partial_token(self) -> None:
        # 401 chars / 4.0 = 100.25 → ceil = 101
        assert _estimate_tokens("x" * 401, 4.0) == 101

    def test_single_char(self) -> None:
        # 1 / 4.0 = 0.25 → ceil = 1
        assert _estimate_tokens("a", 4.0) == 1

    def test_custom_chars_per_token(self) -> None:
        # 300 chars / 3.0 = 100 tokens
        assert _estimate_tokens("x" * 300, 3.0) == 100

    def test_fractional_chars_per_token(self) -> None:
        # 10 chars / 2.5 = 4.0 → 4 tokens
        assert _estimate_tokens("x" * 10, 2.5) == 4

    def test_invalid_chars_per_token_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            _estimate_tokens("hello", 0.0)

    def test_invalid_chars_per_token_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            _estimate_tokens("hello", -1.0)

    def test_unicode_multibyte_counts_characters_not_bytes(self) -> None:
        # 4 Unicode characters → ceil(4/4.0) = 1 token
        text = "αβγδ"  # 4 chars, 8 bytes in UTF-8
        assert _estimate_tokens(text, 4.0) == 1

    def test_returns_int(self) -> None:
        result = _estimate_tokens("hello world", 4.0)
        assert isinstance(result, int)


# ---------------------------------------------------------------------------
# AgentsMdTokenGateConfig — default values
# ---------------------------------------------------------------------------


class TestAgentsMdTokenGateConfigDefaults:
    def test_max_tokens_default(self) -> None:
        cfg = AgentsMdTokenGateConfig()
        assert cfg.max_tokens == 800

    def test_glob_pattern_default(self) -> None:
        cfg = AgentsMdTokenGateConfig()
        assert cfg.glob_pattern == "**/AGENTS.md"

    def test_chars_per_token_default(self) -> None:
        cfg = AgentsMdTokenGateConfig()
        assert cfg.chars_per_token == 4.0

    def test_enabled_default(self) -> None:
        cfg = AgentsMdTokenGateConfig()
        assert cfg.enabled is True

    def test_fail_on_error_default(self) -> None:
        cfg = AgentsMdTokenGateConfig()
        assert cfg.fail_on_error is True

    def test_model_dump_includes_all_fields(self) -> None:
        cfg = AgentsMdTokenGateConfig(max_tokens=500)
        d = cfg.model_dump()
        assert d["max_tokens"] == 500
        assert "glob_pattern" in d
        assert "chars_per_token" in d
        assert "enabled" in d
        assert "fail_on_error" in d

    def test_model_validate_roundtrip(self) -> None:
        original = AgentsMdTokenGateConfig(max_tokens=1200, glob_pattern="**/*AGENTS*.md")
        restored = AgentsMdTokenGateConfig.model_validate(original.model_dump())
        assert restored.max_tokens == 1200
        assert restored.glob_pattern == "**/*AGENTS*.md"

    def test_model_validate_ignores_unknown_keys(self) -> None:
        cfg = AgentsMdTokenGateConfig.model_validate(
            {"max_tokens": 300, "unknown_future_field": "ignored"}
        )
        assert cfg.max_tokens == 300


# ---------------------------------------------------------------------------
# GateResult helpers
# ---------------------------------------------------------------------------


class TestGateResult:
    def _make_violation(self, severity: str = "error") -> Violation:
        return Violation(
            kind="over_budget",
            severity=severity,  # type: ignore[arg-type]
            message="test violation",
        )

    def test_errors_filters_by_severity(self) -> None:
        result = GateResult(
            passed=False,
            violations=[
                self._make_violation("error"),
                self._make_violation("warning"),
            ],
        )
        assert len(result.errors()) == 1
        assert len(result.warnings()) == 1

    def test_passed_true_when_no_violations(self) -> None:
        result = GateResult(passed=True)
        assert result.passed is True
        assert result.errors() == []

    def test_violation_summary_format(self) -> None:
        v = Violation(
            kind="over_budget",
            severity="error",
            message="file is too big",
            agents_md_file=Path("/repo/AGENTS.md"),
            actual_tokens=1200,
            max_tokens=800,
        )
        summary = v.summary()
        assert "ERROR" in summary
        assert "over_budget" in summary
        assert "file is too big" in summary
        assert "AGENTS.md" in summary


# ---------------------------------------------------------------------------
# No AGENTS.md files found
# ---------------------------------------------------------------------------


class TestNoFilesFound:
    def test_passes_when_no_files_match(self, tmp_path: Path) -> None:
        result = AgentsMdTokenGate().run(tmp_path)
        assert result.passed is True

    def test_emits_warning_when_no_files(self, tmp_path: Path) -> None:
        result = AgentsMdTokenGate().run(tmp_path)
        assert len(result.violations) == 1
        assert result.violations[0].severity == "warning"

    def test_files_checked_is_empty_when_no_files(self, tmp_path: Path) -> None:
        result = AgentsMdTokenGate().run(tmp_path)
        assert result.files_checked == []

    def test_stats_reflect_zero_files(self, tmp_path: Path) -> None:
        result = AgentsMdTokenGate().run(tmp_path)
        assert result.stats["files_checked"] == 0
        assert result.stats["violations"] == 0

    def test_custom_glob_no_match(self, tmp_path: Path) -> None:
        # Even if AGENTS.md exists, a non-matching glob finds nothing.
        write_agents_md(tmp_path / "AGENTS.md", "# short")
        cfg = AgentsMdTokenGateConfig(glob_pattern="**/MISSING_AGENTS.md")
        result = AgentsMdTokenGate(cfg).run(tmp_path)
        assert result.passed is True
        assert result.files_checked == []


# ---------------------------------------------------------------------------
# Single file — within budget
# ---------------------------------------------------------------------------


class TestSingleFileWithinBudget:
    def test_exactly_at_budget_passes(self, tmp_path: Path) -> None:
        # File with estimated tokens == max_tokens (exactly on the edge)
        cfg = AgentsMdTokenGateConfig(max_tokens=100)
        # 400 chars / 4.0 = 100 tokens exactly → should PASS
        agents_md_with_tokens(tmp_path / "AGENTS.md", target_tokens=100)
        result = AgentsMdTokenGate(cfg).run(tmp_path)
        assert result.passed is True
        assert result.violations == []

    def test_well_under_budget_passes(self, tmp_path: Path) -> None:
        cfg = AgentsMdTokenGateConfig(max_tokens=800)
        write_agents_md(tmp_path / "AGENTS.md", "# Small\nJust a title.\n")
        result = AgentsMdTokenGate(cfg).run(tmp_path)
        assert result.passed is True
        assert result.violations == []

    def test_files_checked_contains_the_file(self, tmp_path: Path) -> None:
        p = tmp_path / "AGENTS.md"
        write_agents_md(p, "# OK\n")
        result = AgentsMdTokenGate(AgentsMdTokenGateConfig(max_tokens=800)).run(tmp_path)
        assert p in result.files_checked

    def test_stats_show_correct_token_estimate(self, tmp_path: Path) -> None:
        content = "x" * 400  # exactly 100 tokens at 4 chars/token
        write_agents_md(tmp_path / "AGENTS.md", content)
        cfg = AgentsMdTokenGateConfig(max_tokens=200)
        result = AgentsMdTokenGate(cfg).run(tmp_path)
        file_stats = result.stats["file_stats"]
        assert isinstance(file_stats, list)
        assert len(file_stats) == 1
        assert file_stats[0]["estimated_tokens"] == 100
        assert file_stats[0]["over_budget"] is False

    def test_empty_agents_md_passes(self, tmp_path: Path) -> None:
        write_agents_md(tmp_path / "AGENTS.md", "")
        result = AgentsMdTokenGate(AgentsMdTokenGateConfig(max_tokens=10)).run(tmp_path)
        assert result.passed is True
        assert result.violations == []


# ---------------------------------------------------------------------------
# Single file — over budget
# ---------------------------------------------------------------------------


class TestSingleFileOverBudget:
    def test_one_token_over_fails(self, tmp_path: Path) -> None:
        cfg = AgentsMdTokenGateConfig(max_tokens=100, fail_on_error=True)
        # 401 chars / 4.0 = ceil(100.25) = 101 tokens → 1 over
        write_agents_md(tmp_path / "AGENTS.md", "x" * 401)
        result = AgentsMdTokenGate(cfg).run(tmp_path)
        assert result.passed is False

    def test_violation_kind_is_over_budget(self, tmp_path: Path) -> None:
        cfg = AgentsMdTokenGateConfig(max_tokens=50)
        write_agents_md(tmp_path / "AGENTS.md", "x" * 1000)  # 250 tokens
        result = AgentsMdTokenGate(cfg).run(tmp_path)
        assert len(result.violations) == 1
        assert result.violations[0].kind == "over_budget"

    def test_violation_contains_actual_tokens(self, tmp_path: Path) -> None:
        cfg = AgentsMdTokenGateConfig(max_tokens=50)
        write_agents_md(tmp_path / "AGENTS.md", "x" * 400)  # 100 tokens
        result = AgentsMdTokenGate(cfg).run(tmp_path)
        v = result.violations[0]
        assert v.actual_tokens == 100
        assert v.max_tokens == 50

    def test_violation_message_mentions_excess(self, tmp_path: Path) -> None:
        cfg = AgentsMdTokenGateConfig(max_tokens=50)
        write_agents_md(tmp_path / "AGENTS.md", "x" * 400)  # 100 tokens, excess=50
        result = AgentsMdTokenGate(cfg).run(tmp_path)
        assert "+50" in result.violations[0].message

    def test_violation_severity_is_error_when_fail_on_error_true(
        self, tmp_path: Path
    ) -> None:
        cfg = AgentsMdTokenGateConfig(max_tokens=10, fail_on_error=True)
        write_agents_md(tmp_path / "AGENTS.md", "x" * 1000)
        result = AgentsMdTokenGate(cfg).run(tmp_path)
        assert result.violations[0].severity == "error"

    def test_stats_show_over_budget_true(self, tmp_path: Path) -> None:
        cfg = AgentsMdTokenGateConfig(max_tokens=50)
        write_agents_md(tmp_path / "AGENTS.md", "x" * 400)  # 100 tokens
        result = AgentsMdTokenGate(cfg).run(tmp_path)
        assert result.stats["file_stats"][0]["over_budget"] is True


# ---------------------------------------------------------------------------
# Advisory mode (fail_on_error=False)
# ---------------------------------------------------------------------------


class TestAdvisoryMode:
    def test_gate_passes_even_when_over_budget(self, tmp_path: Path) -> None:
        cfg = AgentsMdTokenGateConfig(max_tokens=10, fail_on_error=False)
        write_agents_md(tmp_path / "AGENTS.md", "x" * 1000)
        result = AgentsMdTokenGate(cfg).run(tmp_path)
        assert result.passed is True

    def test_violations_have_warning_severity(self, tmp_path: Path) -> None:
        cfg = AgentsMdTokenGateConfig(max_tokens=10, fail_on_error=False)
        write_agents_md(tmp_path / "AGENTS.md", "x" * 1000)
        result = AgentsMdTokenGate(cfg).run(tmp_path)
        assert len(result.violations) == 1
        assert result.violations[0].severity == "warning"

    def test_errors_list_empty_in_advisory_mode(self, tmp_path: Path) -> None:
        cfg = AgentsMdTokenGateConfig(max_tokens=10, fail_on_error=False)
        write_agents_md(tmp_path / "AGENTS.md", "x" * 1000)
        result = AgentsMdTokenGate(cfg).run(tmp_path)
        assert result.errors() == []
        assert len(result.warnings()) == 1


# ---------------------------------------------------------------------------
# Multiple files
# ---------------------------------------------------------------------------


class TestMultipleFiles:
    def test_all_within_budget_passes(self, tmp_path: Path) -> None:
        cfg = AgentsMdTokenGateConfig(max_tokens=100)
        write_agents_md(tmp_path / "AGENTS.md", "x" * 100)   # 25 tokens
        write_agents_md(tmp_path / "sub" / "AGENTS.md", "x" * 200)  # 50 tokens
        result = AgentsMdTokenGate(cfg).run(tmp_path)
        assert result.passed is True
        assert result.violations == []

    def test_one_over_budget_fails(self, tmp_path: Path) -> None:
        cfg = AgentsMdTokenGateConfig(max_tokens=50)
        write_agents_md(tmp_path / "AGENTS.md", "x" * 100)   # 25 tokens — OK
        write_agents_md(tmp_path / "sub" / "AGENTS.md", "x" * 800)  # 200 tokens — FAIL
        result = AgentsMdTokenGate(cfg).run(tmp_path)
        assert result.passed is False
        assert len(result.violations) == 1

    def test_all_over_budget_produces_one_violation_per_file(
        self, tmp_path: Path
    ) -> None:
        cfg = AgentsMdTokenGateConfig(max_tokens=10)
        write_agents_md(tmp_path / "AGENTS.md", "x" * 400)
        write_agents_md(tmp_path / "sub" / "AGENTS.md", "x" * 400)
        write_agents_md(tmp_path / "sub2" / "AGENTS.md", "x" * 400)
        result = AgentsMdTokenGate(cfg).run(tmp_path)
        assert result.passed is False
        assert len(result.violations) == 3

    def test_files_checked_contains_all_discovered_paths(
        self, tmp_path: Path
    ) -> None:
        cfg = AgentsMdTokenGateConfig(max_tokens=10000)
        p1 = write_agents_md(tmp_path / "AGENTS.md", "# Root")
        p2 = write_agents_md(tmp_path / "sub" / "AGENTS.md", "# Sub")
        result = AgentsMdTokenGate(cfg).run(tmp_path)
        assert p1 in result.files_checked
        assert p2 in result.files_checked

    def test_stats_violations_count_matches(self, tmp_path: Path) -> None:
        cfg = AgentsMdTokenGateConfig(max_tokens=10)
        write_agents_md(tmp_path / "AGENTS.md", "x" * 400)
        write_agents_md(tmp_path / "sub" / "AGENTS.md", "x" * 400)
        result = AgentsMdTokenGate(cfg).run(tmp_path)
        assert result.stats["violations"] == 2
        assert result.stats["files_checked"] == 2


# ---------------------------------------------------------------------------
# Custom glob_pattern
# ---------------------------------------------------------------------------


class TestGlobPattern:
    def test_default_glob_matches_nested_agents_md(self, tmp_path: Path) -> None:
        write_agents_md(tmp_path / "deep" / "path" / "AGENTS.md", "# x")
        result = AgentsMdTokenGate(
            AgentsMdTokenGateConfig(max_tokens=1000)
        ).run(tmp_path)
        assert len(result.files_checked) == 1

    def test_custom_glob_matches_prefixed_files(self, tmp_path: Path) -> None:
        write_agents_md(tmp_path / "AGENTS.md", "# Root")
        write_agents_md(tmp_path / "FRONTEND_AGENTS.md", "# Frontend")
        write_agents_md(tmp_path / "BACKEND_AGENTS.md", "# Backend")
        cfg = AgentsMdTokenGateConfig(
            max_tokens=1000, glob_pattern="**/*AGENTS.md"
        )
        result = AgentsMdTokenGate(cfg).run(tmp_path)
        assert len(result.files_checked) == 3

    def test_glob_does_not_match_unrelated_md(self, tmp_path: Path) -> None:
        write_agents_md(tmp_path / "README.md", "# Read me")
        write_agents_md(tmp_path / "CHANGELOG.md", "# Changes")
        result = AgentsMdTokenGate(
            AgentsMdTokenGateConfig(max_tokens=10)
        ).run(tmp_path)
        # README.md and CHANGELOG.md should NOT be matched
        assert result.files_checked == []

    def test_glob_matches_files_in_subdirectories(self, tmp_path: Path) -> None:
        levels = ["a", "a/b", "a/b/c"]
        for level in levels:
            write_agents_md(tmp_path / level / "AGENTS.md", "# content")
        result = AgentsMdTokenGate(
            AgentsMdTokenGateConfig(max_tokens=1000)
        ).run(tmp_path)
        assert len(result.files_checked) == 3


# ---------------------------------------------------------------------------
# Custom chars_per_token
# ---------------------------------------------------------------------------


class TestCharsPerToken:
    def test_lower_ratio_increases_estimated_tokens(self, tmp_path: Path) -> None:
        # 400 chars at 4.0 chars/token = 100 tokens
        # 400 chars at 2.0 chars/token = 200 tokens
        content = "x" * 400
        write_agents_md(tmp_path / "AGENTS.md", content)

        cfg_default = AgentsMdTokenGateConfig(max_tokens=150, chars_per_token=4.0)
        cfg_tight = AgentsMdTokenGateConfig(max_tokens=150, chars_per_token=2.0)

        result_default = AgentsMdTokenGate(cfg_default).run(tmp_path)
        result_tight = AgentsMdTokenGate(cfg_tight).run(tmp_path)

        # At 4 chars/token: 100 tokens < 150 limit → PASS
        assert result_default.passed is True
        # At 2 chars/token: 200 tokens > 150 limit → FAIL
        assert result_tight.passed is False

    def test_higher_ratio_decreases_estimated_tokens(self, tmp_path: Path) -> None:
        # 400 chars at 8.0 chars/token = 50 tokens
        content = "x" * 400
        write_agents_md(tmp_path / "AGENTS.md", content)
        cfg = AgentsMdTokenGateConfig(max_tokens=75, chars_per_token=8.0)
        result = AgentsMdTokenGate(cfg).run(tmp_path)
        assert result.passed is True


# ---------------------------------------------------------------------------
# Integration — end-to-end GateResult checks
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_full_run_with_realistic_agents_md(self, tmp_path: Path) -> None:
        """Simulate a real AGENTS.md; check all GateResult attributes."""
        content = textwrap.dedent("""\
            # AGENTS.md

            ## Overview
            This service exposes a REST API for managing widgets.

            ## Quick start
            ```bash
            uvicorn app:app --reload
            ```

            ## Environment variables
            | Variable  | Default | Purpose              |
            |-----------|---------|----------------------|
            | PORT      | 8000    | Listening port       |
            | LOG_LEVEL | INFO    | Logging verbosity    |
        """)
        write_agents_md(tmp_path / "AGENTS.md", content)

        expected_tokens = math.ceil(len(content) / 4.0)
        cfg = AgentsMdTokenGateConfig(max_tokens=expected_tokens + 50)
        result = AgentsMdTokenGate(cfg).run(tmp_path)

        assert result.passed is True
        assert len(result.files_checked) == 1
        assert result.violations == []
        assert result.stats["files_checked"] == 1
        assert result.stats["violations"] == 0
        file_stat = result.stats["file_stats"][0]
        assert file_stat["estimated_tokens"] == expected_tokens
        assert file_stat["over_budget"] is False

    def test_full_run_blocking_verbose_agents_md(self, tmp_path: Path) -> None:
        """A verbose AGENTS.md blocks the gate and violation attributes are set."""
        # Build a file that is clearly over a tight 100-token limit
        content = "# Heading\n" + "This is a line of documentation.\n" * 30
        write_agents_md(tmp_path / "AGENTS.md", content)

        cfg = AgentsMdTokenGateConfig(max_tokens=100, fail_on_error=True)
        result = AgentsMdTokenGate(cfg).run(tmp_path)

        assert result.passed is False
        assert len(result.violations) == 1
        v = result.violations[0]
        assert v.kind == "over_budget"
        assert v.severity == "error"
        assert v.agents_md_file is not None
        assert v.actual_tokens is not None
        assert v.actual_tokens > 100
        assert v.max_tokens == 100

    def test_gate_uses_default_config_when_none_provided(
        self, tmp_path: Path
    ) -> None:
        """Running AgentsMdTokenGate() without config uses defaults."""
        gate = AgentsMdTokenGate()
        assert gate.config.max_tokens == 800
        assert gate.config.glob_pattern == "**/AGENTS.md"

    def test_repo_root_is_resolved_before_glob(self, tmp_path: Path) -> None:
        """Relative repo_root path is resolved; files are still found."""
        write_agents_md(tmp_path / "AGENTS.md", "# ok")
        # Pass a relative path; gate should resolve it
        import os
        original_cwd = Path.cwd()
        os.chdir(tmp_path.parent)
        try:
            relative_root = Path(tmp_path.name)
            result = AgentsMdTokenGate(
                AgentsMdTokenGateConfig(max_tokens=1000)
            ).run(relative_root)
            assert len(result.files_checked) == 1
        finally:
            os.chdir(original_cwd)

    def test_max_tokens_reported_in_gate_result(self, tmp_path: Path) -> None:
        cfg = AgentsMdTokenGateConfig(max_tokens=42)
        write_agents_md(tmp_path / "AGENTS.md", "x")
        result = AgentsMdTokenGate(cfg).run(tmp_path)
        assert result.max_tokens == 42

    def test_advisory_mode_end_to_end(self, tmp_path: Path) -> None:
        """Advisory mode: over-budget file gets warning violation, gate passes."""
        cfg = AgentsMdTokenGateConfig(max_tokens=1, fail_on_error=False)
        write_agents_md(tmp_path / "AGENTS.md", "x" * 1000)
        result = AgentsMdTokenGate(cfg).run(tmp_path)
        assert result.passed is True
        assert len(result.violations) == 1
        assert result.violations[0].severity == "warning"
        assert result.errors() == []


# ---------------------------------------------------------------------------
# Read error handling
# ---------------------------------------------------------------------------


class TestReadError:
    def test_unreadable_file_produces_read_error_violation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        p = write_agents_md(tmp_path / "AGENTS.md", "# content")
        # Monkey-patch Path.read_text to simulate an OSError
        original_read_text = Path.read_text

        def failing_read_text(self_path, *args, **kwargs):
            if self_path == p:
                raise OSError("Permission denied")
            return original_read_text(self_path, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", failing_read_text)

        cfg = AgentsMdTokenGateConfig(max_tokens=800, fail_on_error=True)
        result = AgentsMdTokenGate(cfg).run(tmp_path)

        assert result.passed is False
        assert len(result.violations) == 1
        v = result.violations[0]
        assert v.kind == "read_error"
        assert v.severity == "error"
        assert "Permission denied" in v.message
        assert v.agents_md_file == p

    def test_read_error_stats_contain_error_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        p = write_agents_md(tmp_path / "AGENTS.md", "# content")
        original_read_text = Path.read_text

        def failing_read_text(self_path, *args, **kwargs):
            if self_path == p:
                raise OSError("disk error")
            return original_read_text(self_path, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", failing_read_text)

        cfg = AgentsMdTokenGateConfig(max_tokens=800)
        result = AgentsMdTokenGate(cfg).run(tmp_path)

        file_stats = result.stats["file_stats"]
        assert len(file_stats) == 1
        assert file_stats[0]["chars"] is None
        assert file_stats[0]["estimated_tokens"] is None
        assert file_stats[0]["over_budget"] is None
        assert "disk error" in file_stats[0]["error"]

    def test_read_error_advisory_mode_produces_warning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        p = write_agents_md(tmp_path / "AGENTS.md", "# content")
        original_read_text = Path.read_text

        def failing_read_text(self_path, *args, **kwargs):
            if self_path == p:
                raise OSError("nope")
            return original_read_text(self_path, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", failing_read_text)

        cfg = AgentsMdTokenGateConfig(max_tokens=800, fail_on_error=False)
        result = AgentsMdTokenGate(cfg).run(tmp_path)

        assert result.passed is True
        assert result.violations[0].severity == "warning"


# ---------------------------------------------------------------------------
# _build_parser — CLI parser tests
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_parser_defaults(self) -> None:
        from harness_skills.gates.agents_md_token import _build_parser

        parser = _build_parser()
        args = parser.parse_args([])
        assert args.root == "."
        assert args.max_tokens == 800
        assert args.glob_pattern == "**/AGENTS.md"
        assert args.chars_per_token == 4.0
        assert args.fail_on_error is True
        assert args.quiet is False

    def test_parser_custom_values(self) -> None:
        from harness_skills.gates.agents_md_token import _build_parser

        parser = _build_parser()
        args = parser.parse_args([
            "--root", "/tmp/repo",
            "--max-tokens", "1500",
            "--glob", "**/*AGENTS*.md",
            "--chars-per-token", "3.5",
            "--no-fail-on-error",
            "--quiet",
        ])
        assert args.root == "/tmp/repo"
        assert args.max_tokens == 1500
        assert args.glob_pattern == "**/*AGENTS*.md"
        assert args.chars_per_token == 3.5
        assert args.fail_on_error is False
        assert args.quiet is True


# ---------------------------------------------------------------------------
# Violation summary — no file path
# ---------------------------------------------------------------------------


class TestViolationSummaryNoFile:
    def test_summary_without_file_path(self) -> None:
        v = Violation(
            kind="over_budget",
            severity="warning",
            message="no file given",
        )
        summary = v.summary()
        assert "WARNING" in summary
        assert "no file given" in summary
