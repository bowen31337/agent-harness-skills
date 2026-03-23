"""
tests/test_generators/test_config_generator.py
================================================
Tests for harness_skills.generators.config_generator.

Coverage targets:
  - generate_gate_config()  — YAML shape, per-gate enabled/fail_on_error/threshold
  - write_harness_config()  — file creation, merge into existing file, error paths
  - Per-profile defaults    — starter / standard / advanced thresholds
  - Stack hint              — coverage tool-comment tailoring
  - Plugin comment          — always present at the end of the gates block
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from harness_skills.generators.config_generator import (
    generate_gate_config,
    write_harness_config,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_gates(yaml_text: str) -> dict:
    """Parse the generated YAML fragment and return the ``gates`` dict.

    ``generate_gate_config`` produces a YAML *fragment* indented for embedding
    under ``profiles.<profile>:`` in ``harness.config.yaml``.  We strip the
    common leading whitespace (4 spaces) before feeding it to the YAML parser
    so it can be treated as a valid standalone document.
    """
    import textwrap as _textwrap
    dedented = _textwrap.dedent(yaml_text)
    doc = yaml.safe_load(dedented)
    assert doc is not None, "YAML parsed to None"
    assert "gates" in doc, f"No 'gates' key in parsed doc. Keys: {list(doc.keys())}"
    return doc["gates"]


# ---------------------------------------------------------------------------
# generate_gate_config — invalid input
# ---------------------------------------------------------------------------


class TestGenerateGateConfigInvalidInput:
    def test_unknown_profile_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown profile"):
            generate_gate_config("unknown_profile")

    def test_empty_string_profile_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            generate_gate_config("")

    def test_profile_case_sensitive(self) -> None:
        with pytest.raises(ValueError):
            generate_gate_config("Starter")  # wrong case


# ---------------------------------------------------------------------------
# generate_gate_config — YAML structure
# ---------------------------------------------------------------------------


class TestGenerateGateConfigYamlStructure:
    """The generated text must parse as valid YAML and contain a ``gates:`` key."""

    PROFILES = ["starter", "standard", "advanced"]
    EXPECTED_GATES = [
        "regression", "coverage", "security", "performance",
        "architecture", "principles", "docs_freshness", "types", "lint",
    ]

    @pytest.mark.parametrize("profile", PROFILES)
    def test_output_is_valid_yaml(self, profile: str) -> None:
        text = generate_gate_config(profile)
        doc = yaml.safe_load(text)
        assert doc is not None
        assert isinstance(doc, dict)

    @pytest.mark.parametrize("profile", PROFILES)
    def test_gates_key_present(self, profile: str) -> None:
        text = generate_gate_config(profile)
        gates = _parse_gates(text)
        assert isinstance(gates, dict)

    @pytest.mark.parametrize("profile", PROFILES)
    def test_all_nine_built_in_gates_present(self, profile: str) -> None:
        gates = _parse_gates(generate_gate_config(profile))
        for gate_id in self.EXPECTED_GATES:
            assert gate_id in gates, f"Gate '{gate_id}' missing from {profile!r} profile"

    @pytest.mark.parametrize("profile", PROFILES)
    def test_plugins_section_present(self, profile: str) -> None:
        text = generate_gate_config(profile)
        # plugins: [] is in the raw YAML comment block; it also parses as a key
        gates = _parse_gates(text)
        assert "plugins" in gates


# ---------------------------------------------------------------------------
# Per-gate enabled / fail_on_error flags
# ---------------------------------------------------------------------------


class TestPerGateEnabledAndFailOnError:
    """Every gate must expose ``enabled`` and ``fail_on_error`` so engineers
    can toggle them without knowing the full schema."""

    CONTROL_GATES = [
        "regression", "coverage", "docs_freshness", "lint",
    ]

    def test_starter_regression_enabled(self) -> None:
        gates = _parse_gates(generate_gate_config("starter"))
        assert gates["regression"]["enabled"] is True

    def test_starter_coverage_enabled(self) -> None:
        gates = _parse_gates(generate_gate_config("starter"))
        assert gates["coverage"]["enabled"] is True

    def test_starter_docs_freshness_enabled(self) -> None:
        gates = _parse_gates(generate_gate_config("starter"))
        assert gates["docs_freshness"]["enabled"] is True

    def test_starter_lint_enabled(self) -> None:
        gates = _parse_gates(generate_gate_config("starter"))
        assert gates["lint"]["enabled"] is True

    def test_starter_security_disabled(self) -> None:
        gates = _parse_gates(generate_gate_config("starter"))
        assert gates["security"]["enabled"] is False

    def test_starter_performance_disabled(self) -> None:
        gates = _parse_gates(generate_gate_config("starter"))
        assert gates["performance"]["enabled"] is False

    def test_starter_types_disabled(self) -> None:
        gates = _parse_gates(generate_gate_config("starter"))
        assert gates["types"]["enabled"] is False

    def test_starter_architecture_disabled(self) -> None:
        gates = _parse_gates(generate_gate_config("starter"))
        assert gates["architecture"]["enabled"] is False

    def test_standard_all_core_gates_enabled(self) -> None:
        gates = _parse_gates(generate_gate_config("standard"))
        for gate_id in ["regression", "coverage", "security", "architecture",
                        "principles", "docs_freshness", "types", "lint"]:
            assert gates[gate_id]["enabled"] is True, (
                f"Gate '{gate_id}' should be enabled in standard profile"
            )

    def test_advanced_all_gates_enabled(self) -> None:
        gates = _parse_gates(generate_gate_config("advanced"))
        for gate_id in ["regression", "coverage", "security", "performance",
                        "architecture", "principles", "docs_freshness", "types", "lint"]:
            assert gates[gate_id]["enabled"] is True, (
                f"Gate '{gate_id}' should be enabled in advanced profile"
            )

    @pytest.mark.parametrize("profile", ["starter", "standard", "advanced"])
    @pytest.mark.parametrize("gate_id", ["regression", "coverage", "docs_freshness", "lint"])
    def test_active_gates_have_fail_on_error_field(self, profile: str, gate_id: str) -> None:
        gates = _parse_gates(generate_gate_config(profile))
        assert "fail_on_error" in gates[gate_id], (
            f"Gate '{gate_id}' in profile '{profile}' is missing 'fail_on_error'"
        )


# ---------------------------------------------------------------------------
# Coverage threshold per profile
# ---------------------------------------------------------------------------


class TestCoverageThresholds:
    def test_starter_threshold_is_60(self) -> None:
        gates = _parse_gates(generate_gate_config("starter"))
        assert gates["coverage"]["threshold"] == 60.0

    def test_standard_threshold_is_80(self) -> None:
        gates = _parse_gates(generate_gate_config("standard"))
        assert gates["coverage"]["threshold"] == 80.0

    def test_advanced_threshold_is_90(self) -> None:
        gates = _parse_gates(generate_gate_config("advanced"))
        assert gates["coverage"]["threshold"] == 90.0

    def test_starter_branch_coverage_off(self) -> None:
        gates = _parse_gates(generate_gate_config("starter"))
        assert gates["coverage"]["branch_coverage"] is False

    def test_standard_branch_coverage_on(self) -> None:
        gates = _parse_gates(generate_gate_config("standard"))
        assert gates["coverage"]["branch_coverage"] is True

    def test_advanced_branch_coverage_on(self) -> None:
        gates = _parse_gates(generate_gate_config("advanced"))
        assert gates["coverage"]["branch_coverage"] is True


# ---------------------------------------------------------------------------
# Stack-aware coverage tool hint
# ---------------------------------------------------------------------------


class TestStackHint:
    def test_python_stack_hint_in_coverage_comment(self) -> None:
        text = generate_gate_config("starter", detected_stack="python")
        assert "pytest --cov" in text

    def test_node_stack_hint_in_coverage_comment(self) -> None:
        text = generate_gate_config("starter", detected_stack="node")
        assert "jest" in text

    def test_go_stack_hint_in_coverage_comment(self) -> None:
        text = generate_gate_config("starter", detected_stack="go")
        assert "go test" in text

    def test_no_stack_hint_uses_auto_detect_comment(self) -> None:
        text = generate_gate_config("starter", detected_stack=None)
        assert "auto-detected" in text

    def test_unknown_stack_hint_falls_back_to_auto(self) -> None:
        text = generate_gate_config("standard", detected_stack="cobol")
        assert "auto-detected" in text


# ---------------------------------------------------------------------------
# Docs freshness — staleness days per profile
# ---------------------------------------------------------------------------


class TestDocsFreshnessConfig:
    def test_starter_staleness_30_days(self) -> None:
        gates = _parse_gates(generate_gate_config("starter"))
        assert gates["docs_freshness"]["max_staleness_days"] == 30

    def test_standard_staleness_14_days(self) -> None:
        gates = _parse_gates(generate_gate_config("standard"))
        assert gates["docs_freshness"]["max_staleness_days"] == 14

    def test_advanced_staleness_7_days(self) -> None:
        gates = _parse_gates(generate_gate_config("advanced"))
        assert gates["docs_freshness"]["max_staleness_days"] == 7

    def test_tracked_files_list_non_empty(self) -> None:
        for profile in ("starter", "standard", "advanced"):
            gates = _parse_gates(generate_gate_config(profile))
            tracked = gates["docs_freshness"].get("tracked_files", [])
            assert isinstance(tracked, list)
            assert len(tracked) >= 1, f"{profile}: tracked_files must be non-empty"


# ---------------------------------------------------------------------------
# Regression gate
# ---------------------------------------------------------------------------


class TestRegressionGateConfig:
    def test_starter_timeout_120(self) -> None:
        gates = _parse_gates(generate_gate_config("starter"))
        assert gates["regression"]["timeout_seconds"] == 120

    def test_standard_timeout_300(self) -> None:
        gates = _parse_gates(generate_gate_config("standard"))
        assert gates["regression"]["timeout_seconds"] == 300

    def test_extra_args_is_list(self) -> None:
        for profile in ("starter", "standard", "advanced"):
            gates = _parse_gates(generate_gate_config(profile))
            assert isinstance(gates["regression"]["extra_args"], list)


# ---------------------------------------------------------------------------
# Security gate
# ---------------------------------------------------------------------------


class TestSecurityGateConfig:
    def test_standard_severity_threshold_high(self) -> None:
        gates = _parse_gates(generate_gate_config("standard"))
        assert gates["security"]["severity_threshold"] == "HIGH"

    def test_advanced_severity_threshold_medium(self) -> None:
        gates = _parse_gates(generate_gate_config("advanced"))
        assert gates["security"]["severity_threshold"] == "MEDIUM"

    def test_advanced_scan_secrets_true(self) -> None:
        gates = _parse_gates(generate_gate_config("advanced"))
        assert gates["security"]["scan_secrets"] is True

    def test_standard_scan_secrets_false(self) -> None:
        gates = _parse_gates(generate_gate_config("standard"))
        assert gates["security"]["scan_secrets"] is False


# ---------------------------------------------------------------------------
# Types gate
# ---------------------------------------------------------------------------


class TestTypesGateConfig:
    def test_advanced_strict_mode_on(self) -> None:
        gates = _parse_gates(generate_gate_config("advanced"))
        assert gates["types"]["strict"] is True

    def test_standard_strict_mode_off(self) -> None:
        gates = _parse_gates(generate_gate_config("standard"))
        assert gates["types"]["strict"] is False


# ---------------------------------------------------------------------------
# Plugin comment
# ---------------------------------------------------------------------------


class TestPluginSection:
    """The plugin stub and its comment block must always be present."""

    @pytest.mark.parametrize("profile", ["starter", "standard", "advanced"])
    def test_plugin_comment_in_output(self, profile: str) -> None:
        text = generate_gate_config(profile)
        assert "plugins:" in text
        assert "gate_id" in text   # part of the example block
        assert "command" in text

    @pytest.mark.parametrize("profile", ["starter", "standard", "advanced"])
    def test_plugins_parses_as_empty_list(self, profile: str) -> None:
        gates = _parse_gates(generate_gate_config(profile))
        assert gates.get("plugins") == [] or gates.get("plugins") is None


# ---------------------------------------------------------------------------
# write_harness_config — file creation
# ---------------------------------------------------------------------------


class TestWriteHarnessConfig:
    def test_creates_file_when_merge_false(self, tmp_path: Path) -> None:
        out = tmp_path / "harness.config.yaml"
        write_harness_config(out, "starter", merge=False)
        assert out.exists()

    def test_created_file_is_valid_yaml(self, tmp_path: Path) -> None:
        out = tmp_path / "harness.config.yaml"
        write_harness_config(out, "standard", merge=False)
        doc = yaml.safe_load(out.read_text())
        assert doc is not None

    def test_created_file_has_active_profile(self, tmp_path: Path) -> None:
        out = tmp_path / "harness.config.yaml"
        write_harness_config(out, "standard", merge=False)
        doc = yaml.safe_load(out.read_text())
        assert doc.get("active_profile") == "standard"

    def test_created_file_has_gates_block(self, tmp_path: Path) -> None:
        out = tmp_path / "harness.config.yaml"
        write_harness_config(out, "advanced", merge=False)
        doc = yaml.safe_load(out.read_text())
        assert "profiles" in doc
        assert "advanced" in doc["profiles"]
        assert "gates" in doc["profiles"]["advanced"]

    def test_invalid_profile_raises_on_create(self, tmp_path: Path) -> None:
        out = tmp_path / "harness.config.yaml"
        with pytest.raises(ValueError, match="Unknown profile"):
            write_harness_config(out, "bogus", merge=False)

    def test_file_not_found_raises_when_merge_true(self, tmp_path: Path) -> None:
        missing = tmp_path / "does_not_exist.yaml"
        with pytest.raises(FileNotFoundError):
            write_harness_config(missing, "starter", merge=True)

    def test_merge_updates_gates_block(self, tmp_path: Path) -> None:
        """Merging into an existing config replaces only the gates block."""
        existing = textwrap.dedent("""\
            active_profile: starter
            profiles:
              starter:
                description: "old description"
                gates:
                  regression:
                    enabled: false
        """)
        cfg = tmp_path / "harness.config.yaml"
        cfg.write_text(existing)

        write_harness_config(cfg, "starter", merge=True)

        doc = yaml.safe_load(cfg.read_text())
        # The gates block must be replaced
        gates = doc["profiles"]["starter"]["gates"]
        assert gates["regression"]["enabled"] is True   # default restored

    def test_merge_preserves_surrounding_keys(self, tmp_path: Path) -> None:
        existing = textwrap.dedent("""\
            active_profile: starter
            custom_key: keep_me
            profiles:
              starter:
                description: "should be kept"
                gates:
                  regression:
                    enabled: false
        """)
        cfg = tmp_path / "harness.config.yaml"
        cfg.write_text(existing)

        write_harness_config(cfg, "starter", merge=True)

        text = cfg.read_text()
        assert "keep_me" in text

    def test_stack_hint_forwarded_to_coverage_comment(self, tmp_path: Path) -> None:
        out = tmp_path / "harness.config.yaml"
        write_harness_config(out, "standard", detected_stack="python", merge=False)
        text = out.read_text()
        assert "pytest --cov" in text


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    """Running generate_gate_config twice with the same args must produce
    identical output."""

    @pytest.mark.parametrize("profile", ["starter", "standard", "advanced"])
    def test_same_output_on_repeated_calls(self, profile: str) -> None:
        first = generate_gate_config(profile, detected_stack="python")
        second = generate_gate_config(profile, detected_stack="python")
        assert first == second

    def test_write_twice_merge_idempotent(self, tmp_path: Path) -> None:
        out = tmp_path / "harness.config.yaml"
        write_harness_config(out, "standard", merge=False)
        first_text = out.read_text()

        write_harness_config(out, "standard", merge=True)
        second_doc = yaml.safe_load(out.read_text())
        first_doc = yaml.safe_load(first_text)

        # Gates must remain identical after a merge pass on a freshly-generated file
        assert (
            second_doc["profiles"]["standard"]["gates"]
            == first_doc["profiles"]["standard"]["gates"]
        )
