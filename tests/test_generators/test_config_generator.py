"""Tests for harness_skills.generators.config_generator.

Covers:
    - generate_gate_config()   builds valid YAML for each profile
    - generate_gate_config()   ValueError on unknown profile
    - generate_gate_config()   per-gate threshold values match PROFILE_GATE_DEFAULTS
    - generate_gate_config()   inline comments present for adjustable thresholds
    - generate_gate_config()   stack hint tailors the coverage-tool comment
    - generate_gate_config()   plugin-gate stub always appended
    - write_harness_config()   merge=False creates a new file from scratch
    - write_harness_config()   merge=True patches only the gates block
    - write_harness_config()   merge=True raises FileNotFoundError when file absent
    - write_harness_config()   merged result is valid YAML
    - write_harness_config()   surrounding keys preserved after merge
    - _render_*                individual gate renderers emit expected fields
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from harness_skills.generators.config_generator import (
    _render_architecture,
    _render_coverage,
    _render_docs_freshness,
    _render_lint,
    _render_performance,
    _render_principles,
    _render_regression,
    _render_security,
    _render_types,
    generate_gate_config,
    write_harness_config,
)
from harness_skills.models.gate_configs import (
    ArchitectureGateConfig,
    CoverageGateConfig,
    DocsFreshnessGateConfig,
    LintGateConfig,
    PerformanceGateConfig,
    PrinciplesGateConfig,
    RegressionGateConfig,
    SecurityGateConfig,
    TypesGateConfig,
    PROFILE_GATE_DEFAULTS,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALL_PROFILES = ["starter", "standard", "advanced"]
_ALL_GATE_IDS = [
    "regression", "coverage", "security", "performance",
    "architecture", "principles", "docs_freshness", "types", "lint",
]


def _parse_gates(yaml_text: str) -> dict:
    """Parse the ``gates:`` YAML block and return the mapping under ``gates``.

    ``generate_gate_config`` returns 4-space-indented text designed to be
    embedded under ``profiles.<profile>:`` in a full config file.  We dedent
    before calling ``yaml.safe_load`` so the text is a valid standalone doc.
    """
    parsed = yaml.safe_load(textwrap.dedent(yaml_text))
    assert parsed is not None, "YAML parsed to None"
    assert "gates" in parsed, f"No 'gates' key in parsed output: {list(parsed)}"
    return parsed["gates"]


# ===========================================================================
# generate_gate_config — profile validation
# ===========================================================================


class TestGenerateGateConfigValidation:
    def test_unknown_profile_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown profile"):
            generate_gate_config("enterprise")

    def test_empty_string_profile_raises_value_error(self):
        with pytest.raises(ValueError):
            generate_gate_config("")

    @pytest.mark.parametrize("profile", _ALL_PROFILES)
    def test_valid_profiles_do_not_raise(self, profile: str):
        # Should not raise
        result = generate_gate_config(profile)
        assert isinstance(result, str)


# ===========================================================================
# generate_gate_config — YAML validity
# ===========================================================================


class TestGenerateGateConfigYamlValidity:
    @pytest.mark.parametrize("profile", _ALL_PROFILES)
    def test_output_is_parseable_yaml(self, profile: str):
        result = generate_gate_config(profile)
        parsed = yaml.safe_load(textwrap.dedent(result))
        assert parsed is not None

    @pytest.mark.parametrize("profile", _ALL_PROFILES)
    def test_output_contains_gates_key(self, profile: str):
        result = generate_gate_config(profile)
        parsed = yaml.safe_load(textwrap.dedent(result))
        assert "gates" in parsed

    @pytest.mark.parametrize("profile", _ALL_PROFILES)
    def test_all_gate_ids_present(self, profile: str):
        gates = _parse_gates(generate_gate_config(profile))
        for gate_id in _ALL_GATE_IDS:
            assert gate_id in gates, (
                f"Gate '{gate_id}' missing from profile '{profile}'. "
                f"Found: {list(gates)}"
            )

    @pytest.mark.parametrize("profile", _ALL_PROFILES)
    def test_plugins_key_present(self, profile: str):
        gates = _parse_gates(generate_gate_config(profile))
        assert "plugins" in gates

    @pytest.mark.parametrize("profile", _ALL_PROFILES)
    def test_plugins_is_empty_list(self, profile: str):
        gates = _parse_gates(generate_gate_config(profile))
        assert gates["plugins"] == []


# ===========================================================================
# generate_gate_config — per-profile threshold values
# ===========================================================================


class TestGenerateGateConfigThresholds:
    # ── coverage ────────────────────────────────────────────────────────────

    def test_starter_coverage_threshold_matches_defaults(self):
        gates = _parse_gates(generate_gate_config("starter"))
        expected = PROFILE_GATE_DEFAULTS["starter"]["coverage"].threshold
        assert gates["coverage"]["threshold"] == pytest.approx(expected)

    def test_standard_coverage_threshold_matches_defaults(self):
        gates = _parse_gates(generate_gate_config("standard"))
        expected = PROFILE_GATE_DEFAULTS["standard"]["coverage"].threshold
        assert gates["coverage"]["threshold"] == pytest.approx(expected)

    def test_advanced_coverage_threshold_matches_defaults(self):
        gates = _parse_gates(generate_gate_config("advanced"))
        expected = PROFILE_GATE_DEFAULTS["advanced"]["coverage"].threshold
        assert gates["coverage"]["threshold"] == pytest.approx(expected)

    def test_advanced_coverage_threshold_higher_than_starter(self):
        starter = _parse_gates(generate_gate_config("starter"))["coverage"]["threshold"]
        advanced = _parse_gates(generate_gate_config("advanced"))["coverage"]["threshold"]
        assert advanced > starter

    # ── enabled flags ────────────────────────────────────────────────────────

    def test_starter_regression_is_enabled(self):
        gates = _parse_gates(generate_gate_config("starter"))
        assert gates["regression"]["enabled"] is True

    def test_starter_security_is_disabled(self):
        gates = _parse_gates(generate_gate_config("starter"))
        assert gates["security"]["enabled"] is False

    def test_starter_performance_is_disabled(self):
        gates = _parse_gates(generate_gate_config("starter"))
        assert gates["performance"]["enabled"] is False

    def test_standard_security_is_enabled(self):
        gates = _parse_gates(generate_gate_config("standard"))
        assert gates["security"]["enabled"] is True

    def test_advanced_performance_is_enabled(self):
        gates = _parse_gates(generate_gate_config("advanced"))
        assert gates["performance"]["enabled"] is True

    def test_advanced_types_strict_is_true(self):
        gates = _parse_gates(generate_gate_config("advanced"))
        assert gates["types"]["strict"] is True

    def test_starter_types_strict_is_false(self):
        gates = _parse_gates(generate_gate_config("starter"))
        assert gates["types"]["strict"] is False

    # ── advisory / fail_on_error ─────────────────────────────────────────────

    def test_starter_principles_is_advisory(self):
        """Starter principles gate must be non-blocking (fail_on_error=false)."""
        gates = _parse_gates(generate_gate_config("starter"))
        assert gates["principles"]["fail_on_error"] is False

    def test_starter_regression_fails_on_error(self):
        gates = _parse_gates(generate_gate_config("starter"))
        assert gates["regression"]["fail_on_error"] is True

    # ── docs freshness staleness ─────────────────────────────────────────────

    def test_starter_docs_freshness_30_days(self):
        gates = _parse_gates(generate_gate_config("starter"))
        assert gates["docs_freshness"]["max_staleness_days"] == 30

    def test_advanced_docs_freshness_stricter_than_starter(self):
        starter = _parse_gates(generate_gate_config("starter"))["docs_freshness"]["max_staleness_days"]
        advanced = _parse_gates(generate_gate_config("advanced"))["docs_freshness"]["max_staleness_days"]
        assert advanced < starter

    # ── security severity ────────────────────────────────────────────────────

    def test_standard_security_severity_threshold_is_high(self):
        gates = _parse_gates(generate_gate_config("standard"))
        assert gates["security"]["severity_threshold"] == "HIGH"

    def test_advanced_security_severity_threshold_is_medium(self):
        gates = _parse_gates(generate_gate_config("advanced"))
        assert gates["security"]["severity_threshold"] == "MEDIUM"

    # ── regression timeout ───────────────────────────────────────────────────

    def test_starter_regression_timeout_matches_defaults(self):
        gates = _parse_gates(generate_gate_config("starter"))
        expected = PROFILE_GATE_DEFAULTS["starter"]["regression"].timeout_seconds
        assert gates["regression"]["timeout_seconds"] == expected

    def test_advanced_regression_timeout_longer_than_starter(self):
        starter = _parse_gates(generate_gate_config("starter"))["regression"]["timeout_seconds"]
        advanced = _parse_gates(generate_gate_config("advanced"))["regression"]["timeout_seconds"]
        assert advanced >= starter

    # ── performance budget ───────────────────────────────────────────────────

    def test_advanced_performance_budget_ms_present(self):
        gates = _parse_gates(generate_gate_config("advanced"))
        assert "budget_ms" in gates["performance"]
        assert isinstance(gates["performance"]["budget_ms"], int)


# ===========================================================================
# generate_gate_config — stack hint
# ===========================================================================


class TestGenerateGateConfigStackHint:
    def test_python_stack_hint_appears_in_output(self):
        result = generate_gate_config("starter", detected_stack="python")
        assert "coverage.py" in result or "pytest" in result

    def test_node_stack_hint_appears_in_output(self):
        result = generate_gate_config("starter", detected_stack="node")
        assert "jest" in result

    def test_go_stack_hint_appears_in_output(self):
        result = generate_gate_config("starter", detected_stack="go")
        assert "go test" in result

    def test_none_stack_produces_auto_detect_comment(self):
        result = generate_gate_config("starter", detected_stack=None)
        assert "auto-detected" in result

    def test_unknown_stack_falls_back_to_auto_detect(self):
        """Any unrecognised stack string must silently fall back (no crash)."""
        result = generate_gate_config("starter", detected_stack="rust")
        assert "auto-detected" in result


# ===========================================================================
# generate_gate_config — inline comments
# ===========================================================================


class TestGenerateGateConfigInlineComments:
    def test_regression_timeout_has_comment(self):
        result = generate_gate_config("starter")
        assert "max wall-clock" in result

    def test_coverage_branch_coverage_has_comment(self):
        result = generate_gate_config("starter")
        assert "condition coverage" in result or "branch" in result

    def test_security_severity_has_choices_comment(self):
        result = generate_gate_config("standard")
        assert "CRITICAL" in result and "HIGH" in result

    def test_performance_budget_has_comment(self):
        result = generate_gate_config("advanced")
        assert "P95" in result or "budget_ms" in result

    def test_lint_autofix_has_comment(self):
        result = generate_gate_config("starter")
        assert "autofix" in result

    def test_plugin_gate_example_in_output(self):
        result = generate_gate_config("starter")
        # Plugin gate stub comment
        assert "gate_id" in result
        assert "gate_name" in result

    def test_output_starts_with_gates_header(self):
        # Output is 4-space-indented for embedding in a full config file.
        result = generate_gate_config("starter")
        assert textwrap.dedent(result).startswith("gates:")


# ===========================================================================
# write_harness_config — merge=False (create from scratch)
# ===========================================================================


class TestWriteHarnessConfigScratch:
    def test_creates_file_when_missing(self, tmp_path: Path):
        dest = tmp_path / "harness.config.yaml"
        write_harness_config(dest, "starter", merge=False)
        assert dest.exists()

    def test_created_file_is_valid_yaml(self, tmp_path: Path):
        dest = tmp_path / "harness.config.yaml"
        write_harness_config(dest, "starter", merge=False)
        content = yaml.safe_load(dest.read_text())
        assert content is not None

    def test_created_file_contains_active_profile(self, tmp_path: Path):
        dest = tmp_path / "harness.config.yaml"
        write_harness_config(dest, "standard", merge=False)
        content = yaml.safe_load(dest.read_text())
        assert "active_profile" in content
        assert content["active_profile"] == "standard"

    def test_created_file_contains_profiles_block(self, tmp_path: Path):
        dest = tmp_path / "harness.config.yaml"
        write_harness_config(dest, "advanced", merge=False)
        content = yaml.safe_load(dest.read_text())
        assert "profiles" in content

    def test_created_file_contains_gates(self, tmp_path: Path):
        dest = tmp_path / "harness.config.yaml"
        write_harness_config(dest, "starter", merge=False)
        content = yaml.safe_load(dest.read_text())
        assert "gates" in content["profiles"]["starter"]

    def test_no_merge_overwrites_existing_file(self, tmp_path: Path):
        dest = tmp_path / "harness.config.yaml"
        dest.write_text("# old content\nactive_profile: starter\n")
        write_harness_config(dest, "advanced", merge=False)
        content = yaml.safe_load(dest.read_text())
        # Profile key reflects the new profile
        assert content["active_profile"] == "advanced"

    @pytest.mark.parametrize("profile", _ALL_PROFILES)
    def test_all_profiles_create_valid_file(self, tmp_path: Path, profile: str):
        dest = tmp_path / f"harness-{profile}.yaml"
        write_harness_config(dest, profile, merge=False)
        content = yaml.safe_load(dest.read_text())
        assert content is not None


# ===========================================================================
# write_harness_config — merge=True
# ===========================================================================


_MINIMAL_EXISTING_CONFIG = textwrap.dedent("""\
    # harness.config.yaml — existing file
    active_profile: starter
    custom_key: preserved_value

    profiles:
      starter:
        description: >
          Original description — must be preserved.

        gates:
          regression:
            enabled: true
            timeout_seconds: 30

        documentation:
          auto_generate: false
""")


class TestWriteHarnessConfigMerge:
    def test_raises_file_not_found_when_file_missing(self, tmp_path: Path):
        dest = tmp_path / "nonexistent.yaml"
        with pytest.raises(FileNotFoundError):
            write_harness_config(dest, "starter", merge=True)

    def test_merged_file_is_valid_yaml(self, tmp_path: Path):
        dest = tmp_path / "harness.config.yaml"
        dest.write_text(_MINIMAL_EXISTING_CONFIG)
        write_harness_config(dest, "starter", merge=True)
        content = yaml.safe_load(dest.read_text())
        assert content is not None

    def test_merge_preserves_custom_top_level_key(self, tmp_path: Path):
        dest = tmp_path / "harness.config.yaml"
        dest.write_text(_MINIMAL_EXISTING_CONFIG)
        write_harness_config(dest, "starter", merge=True)
        content = yaml.safe_load(dest.read_text())
        assert content.get("custom_key") == "preserved_value"

    def test_merge_preserves_active_profile(self, tmp_path: Path):
        dest = tmp_path / "harness.config.yaml"
        dest.write_text(_MINIMAL_EXISTING_CONFIG)
        write_harness_config(dest, "starter", merge=True)
        content = yaml.safe_load(dest.read_text())
        assert content["active_profile"] == "starter"

    def test_merge_updates_gates_block(self, tmp_path: Path):
        dest = tmp_path / "harness.config.yaml"
        dest.write_text(_MINIMAL_EXISTING_CONFIG)
        write_harness_config(dest, "starter", detected_stack="python", merge=True)
        content = yaml.safe_load(dest.read_text())
        gates = content["profiles"]["starter"]["gates"]
        # Original timeout was 30; the merged defaults differ
        assert "coverage" in gates

    def test_merge_adds_all_gate_ids(self, tmp_path: Path):
        dest = tmp_path / "harness.config.yaml"
        dest.write_text(_MINIMAL_EXISTING_CONFIG)
        write_harness_config(dest, "starter", merge=True)
        content = yaml.safe_load(dest.read_text())
        gates = content["profiles"]["starter"]["gates"]
        for gate_id in _ALL_GATE_IDS:
            assert gate_id in gates, f"Gate '{gate_id}' missing after merge"

    def test_merge_into_existing_advanced_profile_block(self, tmp_path: Path):
        existing = textwrap.dedent("""\
            active_profile: advanced
            profiles:
              advanced:
                gates:
                  regression:
                    enabled: true
                    timeout_seconds: 999
        """)
        dest = tmp_path / "harness.config.yaml"
        dest.write_text(existing)
        write_harness_config(dest, "advanced", merge=True)
        content = yaml.safe_load(dest.read_text())
        gates = content["profiles"]["advanced"]["gates"]
        assert "coverage" in gates
        assert "performance" in gates

    def test_merge_preserves_documentation_section(self, tmp_path: Path):
        dest = tmp_path / "harness.config.yaml"
        dest.write_text(_MINIMAL_EXISTING_CONFIG)
        write_harness_config(dest, "starter", merge=True)
        content = yaml.safe_load(dest.read_text())
        # documentation section under starter must still exist
        assert "documentation" in content["profiles"]["starter"]
        assert content["profiles"]["starter"]["documentation"]["auto_generate"] is False


# ===========================================================================
# Individual gate renderer unit tests
# ===========================================================================


class TestRenderRegression:
    def test_enabled_field_present(self):
        cfg = RegressionGateConfig(enabled=True)
        out = _render_regression(cfg)
        assert "enabled: true" in out

    def test_disabled_field_present(self):
        cfg = RegressionGateConfig(enabled=False)
        out = _render_regression(cfg)
        assert "enabled: false" in out

    def test_timeout_seconds_in_output(self):
        cfg = RegressionGateConfig(timeout_seconds=42)
        out = _render_regression(cfg)
        assert "42" in out

    def test_extra_args_empty_list(self):
        cfg = RegressionGateConfig()
        out = _render_regression(cfg)
        assert "[]" in out

    def test_regression_label_present(self):
        out = _render_regression(RegressionGateConfig())
        assert "regression:" in out


class TestRenderCoverage:
    def test_threshold_value_present(self):
        cfg = CoverageGateConfig(threshold=77.5)
        out = _render_coverage(cfg, detected_stack=None)
        assert "77.5" in out

    def test_python_stack_hint_injected(self):
        cfg = CoverageGateConfig()
        out = _render_coverage(cfg, detected_stack="python")
        assert "coverage.py" in out or "pytest" in out

    def test_branch_coverage_true(self):
        cfg = CoverageGateConfig(branch_coverage=True)
        out = _render_coverage(cfg, detected_stack=None)
        assert "branch_coverage: true" in out

    def test_branch_coverage_false(self):
        cfg = CoverageGateConfig(branch_coverage=False)
        out = _render_coverage(cfg, detected_stack=None)
        assert "branch_coverage: false" in out

    def test_coverage_label_present(self):
        out = _render_coverage(CoverageGateConfig(), None)
        assert "coverage:" in out


class TestRenderSecurity:
    def test_enabled_false_reflected(self):
        cfg = SecurityGateConfig(enabled=False)
        out = _render_security(cfg)
        assert "enabled: false" in out

    def test_severity_threshold_present(self):
        cfg = SecurityGateConfig(severity_threshold="MEDIUM")
        out = _render_security(cfg)
        assert "MEDIUM" in out

    def test_scan_secrets_true(self):
        cfg = SecurityGateConfig(scan_secrets=True)
        out = _render_security(cfg)
        assert "scan_secrets: true" in out

    def test_security_label_present(self):
        out = _render_security(SecurityGateConfig())
        assert "security:" in out


class TestRenderPerformance:
    def test_budget_ms_in_output(self):
        cfg = PerformanceGateConfig(enabled=True, budget_ms=150)
        out = _render_performance(cfg)
        assert "150" in out

    def test_disabled_includes_note(self):
        cfg = PerformanceGateConfig(enabled=False)
        out = _render_performance(cfg)
        assert "enabled: false" in out

    def test_regression_threshold_pct_present(self):
        cfg = PerformanceGateConfig(enabled=True, regression_threshold_pct=15.0)
        out = _render_performance(cfg)
        assert "15.0" in out

    def test_performance_label_present(self):
        out = _render_performance(PerformanceGateConfig())
        assert "performance:" in out


class TestRenderArchitecture:
    def test_rules_listed(self):
        cfg = ArchitectureGateConfig(rules=["no_circular_dependencies"])
        out = _render_architecture(cfg)
        assert "no_circular_dependencies" in out

    def test_layer_order_present(self):
        cfg = ArchitectureGateConfig(layer_order=["domain", "api"])
        out = _render_architecture(cfg)
        assert "domain" in out
        assert "api" in out

    def test_report_only_false(self):
        cfg = ArchitectureGateConfig(report_only=False)
        out = _render_architecture(cfg)
        assert "report_only: false" in out

    def test_architecture_label_present(self):
        out = _render_architecture(ArchitectureGateConfig())
        assert "architecture:" in out


class TestRenderPrinciples:
    def test_advisory_note_when_not_fail_on_error(self):
        cfg = PrinciplesGateConfig(fail_on_error=False)
        out = _render_principles(cfg)
        assert "advisory" in out

    def test_no_advisory_note_when_fail_on_error(self):
        cfg = PrinciplesGateConfig(fail_on_error=True)
        out = _render_principles(cfg)
        assert "advisory" not in out

    def test_principles_file_path_present(self):
        cfg = PrinciplesGateConfig(principles_file=".claude/principles.yaml")
        out = _render_principles(cfg)
        assert ".claude/principles.yaml" in out

    def test_rules_listed(self):
        cfg = PrinciplesGateConfig(rules=["no_god_objects"])
        out = _render_principles(cfg)
        assert "no_god_objects" in out

    def test_principles_label_present(self):
        out = _render_principles(PrinciplesGateConfig())
        assert "principles:" in out


class TestRenderDocsFreshness:
    def test_max_staleness_days_present(self):
        cfg = DocsFreshnessGateConfig(max_staleness_days=14)
        out = _render_docs_freshness(cfg)
        assert "14" in out

    def test_tracked_files_listed(self):
        cfg = DocsFreshnessGateConfig(tracked_files=["AGENTS.md", "ARCHITECTURE.md"])
        out = _render_docs_freshness(cfg)
        assert "AGENTS.md" in out
        assert "ARCHITECTURE.md" in out

    def test_docs_freshness_label_present(self):
        out = _render_docs_freshness(DocsFreshnessGateConfig())
        assert "docs_freshness:" in out


class TestRenderTypes:
    def test_strict_true(self):
        cfg = TypesGateConfig(strict=True)
        out = _render_types(cfg)
        assert "strict: true" in out

    def test_strict_false(self):
        cfg = TypesGateConfig(strict=False)
        out = _render_types(cfg)
        assert "strict: false" in out

    def test_strict_false_hint_comment(self):
        cfg = TypesGateConfig(strict=False)
        out = _render_types(cfg)
        assert "set strict: true" in out

    def test_strict_true_hint_comment(self):
        cfg = TypesGateConfig(strict=True)
        out = _render_types(cfg)
        assert "mypy --strict" in out

    def test_ignore_errors_present(self):
        cfg = TypesGateConfig(ignore_errors=["misc"])
        out = _render_types(cfg)
        assert "misc" in out

    def test_types_label_present(self):
        out = _render_types(TypesGateConfig())
        assert "types:" in out


class TestRenderLint:
    def test_autofix_false(self):
        cfg = LintGateConfig(autofix=False)
        out = _render_lint(cfg)
        assert "autofix: false" in out

    def test_autofix_true(self):
        cfg = LintGateConfig(autofix=True)
        out = _render_lint(cfg)
        assert "autofix: true" in out

    def test_select_empty_list(self):
        cfg = LintGateConfig(select=[])
        out = _render_lint(cfg)
        assert "select: []" in out

    def test_ignore_codes_present(self):
        cfg = LintGateConfig(ignore=["E501", "W503"])
        out = _render_lint(cfg)
        assert "E501" in out

    def test_lint_label_present(self):
        out = _render_lint(LintGateConfig())
        assert "lint:" in out
