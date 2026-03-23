"""Unit tests for scripts/import_principles.py — config-file principle importer."""

from __future__ import annotations

from pathlib import Path
import sys
import textwrap

import pytest
import yaml

# Allow importing directly from scripts/ without a package install
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from import_principles import (  # noqa: E402
    ImportResult,
    PrincipleEntry,
    assign_next_id,
    load_existing_principles,
    load_yaml_file,
    merge_principles,
    validate_principle_entry,
    write_principles,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _write_yaml(tmp_path: Path, filename: str, content: str) -> Path:
    """Write *content* (dedented) into *tmp_path/filename* and return the path."""
    p = tmp_path / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def _entry(
    pid: str = "P001",
    category: str = "architecture",
    severity: str = "blocking",
    applies_to: list[str] | None = None,
    rule: str = "All DB queries must go through the repository layer",
) -> PrincipleEntry:
    return PrincipleEntry(
        id=pid,
        category=category,
        severity=severity,  # type: ignore[arg-type]
        applies_to=applies_to or ["review-pr", "check-code"],
        rule=rule,
    )


# ── load_yaml_file ────────────────────────────────────────────────────────────


class TestLoadYamlFile:
    def test_returns_dict_for_valid_file(self, tmp_path: Path) -> None:
        p = _write_yaml(tmp_path, "test.yaml", 'version: "1.0"\n')
        data = load_yaml_file(p)
        assert data == {"version": "1.0"}

    def test_returns_empty_dict_for_blank_file(self, tmp_path: Path) -> None:
        p = _write_yaml(tmp_path, "blank.yaml", "")
        assert load_yaml_file(p) == {}

    def test_exits_when_file_missing(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit) as exc_info:
            load_yaml_file(tmp_path / "missing.yaml")
        assert exc_info.value.code == 2


# ── validate_principle_entry ──────────────────────────────────────────────────


class TestValidatePrincipleEntry:
    def test_valid_full_entry_passes(self) -> None:
        raw = {
            "id": "P001",
            "category": "testing",
            "severity": "blocking",
            "applies_to": ["check-code"],
            "rule": "All functions must have a docstring",
        }
        entry, errors = validate_principle_entry(raw, 0)
        assert entry is not None
        assert errors == []
        assert entry.id == "P001"

    def test_valid_entry_without_id(self) -> None:
        raw = {"category": "style", "severity": "suggestion", "rule": "Use snake_case"}
        entry, errors = validate_principle_entry(raw, 0)
        assert entry is not None
        assert entry.id == ""  # to be auto-assigned on merge

    def test_missing_category_is_error(self) -> None:
        raw = {"severity": "blocking", "rule": "Some rule"}
        entry, errors = validate_principle_entry(raw, 0)
        assert entry is None
        assert any("category" in e for e in errors)

    def test_missing_severity_is_error(self) -> None:
        raw = {"category": "testing", "rule": "Some rule"}
        entry, errors = validate_principle_entry(raw, 0)
        assert entry is None
        assert any("severity" in e for e in errors)

    def test_missing_rule_is_error(self) -> None:
        raw = {"category": "testing", "severity": "blocking"}
        entry, errors = validate_principle_entry(raw, 0)
        assert entry is None
        assert any("rule" in e for e in errors)

    def test_invalid_severity_is_error(self) -> None:
        raw = {"category": "testing", "severity": "critical", "rule": "Some rule"}
        entry, errors = validate_principle_entry(raw, 0)
        assert entry is None
        assert any("severity" in e for e in errors)

    def test_invalid_applies_to_value_is_error(self) -> None:
        raw = {
            "category": "testing",
            "severity": "blocking",
            "applies_to": ["invalid-skill"],
            "rule": "Some rule",
        }
        entry, errors = validate_principle_entry(raw, 0)
        assert entry is None
        assert any("applies_to" in e for e in errors)

    def test_empty_rule_is_error(self) -> None:
        raw = {"category": "testing", "severity": "blocking", "rule": "   "}
        entry, errors = validate_principle_entry(raw, 0)
        assert entry is None
        assert any("rule" in e for e in errors)

    def test_invalid_id_format_is_error(self) -> None:
        raw = {
            "id": "bad-id",
            "category": "testing",
            "severity": "blocking",
            "rule": "Some rule",
        }
        entry, errors = validate_principle_entry(raw, 0)
        assert entry is None
        assert any("id" in e for e in errors)

    def test_valid_non_p_series_id_passes(self) -> None:
        raw = {
            "id": "MB014",
            "category": "architecture",
            "severity": "blocking",
            "rule": "Module boundaries must be explicit",
        }
        entry, errors = validate_principle_entry(raw, 0)
        assert entry is not None
        assert entry.id == "MB014"

    def test_string_applies_to_is_coerced_to_list(self) -> None:
        raw = {
            "category": "style",
            "severity": "suggestion",
            "applies_to": "check-code",
            "rule": "Use consistent formatting",
        }
        entry, errors = validate_principle_entry(raw, 0)
        assert entry is not None
        assert entry.applies_to == ["check-code"]

    def test_default_applies_to_includes_both_skills(self) -> None:
        raw = {"category": "style", "severity": "suggestion", "rule": "Rule text"}
        entry, errors = validate_principle_entry(raw, 0)
        assert entry is not None
        assert set(entry.applies_to) == {"check-code", "review-pr"}

    def test_both_skills_in_applies_to_passes(self) -> None:
        raw = {
            "category": "testing",
            "severity": "blocking",
            "applies_to": ["check-code", "review-pr"],
            "rule": "All tests must have assertions",
        }
        entry, errors = validate_principle_entry(raw, 0)
        assert entry is not None
        assert set(entry.applies_to) == {"check-code", "review-pr"}

    def test_error_label_includes_index(self) -> None:
        raw = {"category": "test", "severity": "blocking"}  # missing rule
        _, errors = validate_principle_entry(raw, 5)
        assert any("principles[5]" in e for e in errors)

    def test_suggestion_severity_passes(self) -> None:
        raw = {"category": "style", "severity": "suggestion", "rule": "Keep it clean"}
        entry, errors = validate_principle_entry(raw, 0)
        assert entry is not None
        assert entry.severity == "suggestion"


# ── assign_next_id ────────────────────────────────────────────────────────────


class TestAssignNextId:
    def test_first_id_with_empty_list(self) -> None:
        assert assign_next_id([]) == "P001"

    def test_sequential_after_existing(self) -> None:
        existing = [_entry("P001"), _entry("P002"), _entry("P003")]
        assert assign_next_id(existing) == "P004"

    def test_fills_lowest_gap(self) -> None:
        """If P002 was deleted, P001 and P003 exist → next is P002."""
        existing = [_entry("P001"), _entry("P003")]
        assert assign_next_id(existing) == "P002"

    def test_ignores_non_p_series_ids(self) -> None:
        existing = [_entry("MB001"), _entry("MB002"), _entry("SEC01")]
        assert assign_next_id(existing) == "P001"

    def test_zero_padded_three_digits(self) -> None:
        existing = [_entry(f"P{n:03d}") for n in range(1, 10)]
        assert assign_next_id(existing) == "P010"

    def test_two_digit_padding_beyond_999(self) -> None:
        # 999 existing → next is P1000 (no truncation)
        existing = [_entry(f"P{n:03d}") for n in range(1, 10)]
        existing.append(_entry("P010"))
        result = assign_next_id(existing)
        assert result.startswith("P")
        assert int(result[1:]) == 11


# ── merge_principles ──────────────────────────────────────────────────────────


class TestMergePrinciples:
    def test_adds_brand_new_principle(self) -> None:
        existing = [_entry("P001")]
        incoming = [_entry("P002", rule="New rule")]
        result = merge_principles(existing, incoming)
        assert len(result.added) == 1
        assert result.added[0].id == "P002"

    def test_skips_duplicate_id_by_default(self) -> None:
        existing = [_entry("P001")]
        incoming = [_entry("P001", rule="Duplicate")]
        result = merge_principles(existing, incoming)
        assert len(result.added) == 0
        assert len(result.skipped) == 1

    def test_strict_ids_records_error_on_collision(self) -> None:
        existing = [_entry("P001")]
        incoming = [_entry("P001", rule="Duplicate")]
        result = merge_principles(existing, incoming, strict_ids=True)
        assert result.has_errors
        assert not result.success

    def test_strict_ids_no_error_without_collision(self) -> None:
        existing = [_entry("P001")]
        incoming = [_entry("P002", rule="New")]
        result = merge_principles(existing, incoming, strict_ids=True)
        assert not result.has_errors

    def test_auto_assigns_id_when_empty_string(self) -> None:
        existing = [_entry("P001")]
        incoming = [_entry("", rule="Auto-assigned")]
        result = merge_principles(existing, incoming)
        assert len(result.added) == 1
        assert result.added[0].id == "P002"

    def test_auto_assigned_batch_ids_are_unique(self) -> None:
        existing = [_entry("P001"), _entry("P002")]
        incoming = [
            _entry("", rule="Auto A"),
            _entry("", rule="Auto B"),
        ]
        result = merge_principles(existing, incoming)
        ids = [p.id for p in result.added]
        assert len(ids) == 2
        assert len(set(ids)) == 2  # all unique
        assert ids == ["P003", "P004"]

    def test_auto_assigned_id_does_not_collide_with_explicit_incoming(self) -> None:
        """Auto-assigned entry must skip IDs already claimed by earlier incoming entries."""
        existing = [_entry("P001")]
        incoming = [
            _entry("P002", rule="Explicit"),  # claims P002
            _entry("", rule="Auto should get P003"),
        ]
        result = merge_principles(existing, incoming)
        ids = {p.id for p in result.added}
        assert "P002" in ids
        assert "P003" in ids
        assert "P001" not in ids  # already existed

    def test_empty_incoming_returns_empty_result(self) -> None:
        existing = [_entry("P001")]
        result = merge_principles(existing, [])
        assert result.added == []
        assert result.skipped == []
        assert result.errors == []

    def test_empty_existing_and_incoming(self) -> None:
        result = merge_principles([], [])
        assert result.success
        assert result.added == []

    def test_mixed_explicit_and_auto_ids(self) -> None:
        existing = [_entry("P001")]
        incoming = [
            _entry("", rule="Gets auto"),
            _entry("P010", rule="Explicit stays P010"),
        ]
        result = merge_principles(existing, incoming)
        ids = {p.id for p in result.added}
        assert "P002" in ids  # auto-assigned
        assert "P010" in ids  # explicit

    def test_skipped_tuple_contains_reason_string(self) -> None:
        existing = [_entry("P001")]
        incoming = [_entry("P001", rule="Dup")]
        result = merge_principles(existing, incoming)
        _entry_skipped, reason = result.skipped[0]
        assert isinstance(reason, str)
        assert len(reason) > 0


# ── load_existing_principles ──────────────────────────────────────────────────


class TestLoadExistingPrinciples:
    def test_loads_single_principle(self, tmp_path: Path) -> None:
        p = _write_yaml(
            tmp_path,
            "principles.yaml",
            """
            version: "1.0"
            principles:
              - id: "P001"
                category: "arch"
                severity: "blocking"
                applies_to: ["check-code"]
                rule: "Use repository layer"
            """,
        )
        entries = load_existing_principles(p)
        assert len(entries) == 1
        assert entries[0].id == "P001"
        assert entries[0].category == "arch"

    def test_returns_empty_list_when_file_missing(self, tmp_path: Path) -> None:
        entries = load_existing_principles(tmp_path / "nonexistent.yaml")
        assert entries == []

    def test_returns_empty_list_when_no_principles_key(self, tmp_path: Path) -> None:
        p = _write_yaml(tmp_path, "principles.yaml", 'version: "1.0"\n')
        assert load_existing_principles(p) == []

    def test_loads_multiple_principles_in_order(self, tmp_path: Path) -> None:
        p = _write_yaml(
            tmp_path,
            "principles.yaml",
            """
            version: "1.0"
            principles:
              - id: "P001"
                category: "arch"
                severity: "blocking"
                applies_to: ["check-code"]
                rule: "Rule one"
              - id: "P002"
                category: "style"
                severity: "suggestion"
                applies_to: ["review-pr"]
                rule: "Rule two"
            """,
        )
        entries = load_existing_principles(p)
        assert entries[0].id == "P001"
        assert entries[1].id == "P002"


# ── write_principles ──────────────────────────────────────────────────────────


class TestWritePrinciples:
    def test_writes_valid_yaml(self, tmp_path: Path) -> None:
        target = tmp_path / ".claude" / "principles.yaml"
        write_principles([_entry("P001"), _entry("P002", category="testing")], target)
        assert target.exists()
        data = yaml.safe_load(target.read_text())
        assert data["version"] == "1.0"
        assert len(data["principles"]) == 2

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        target = tmp_path / "deep" / "nested" / "dir" / "principles.yaml"
        write_principles([_entry("P001")], target)
        assert target.exists()

    def test_round_trip_preserves_all_fields(self, tmp_path: Path) -> None:
        target = tmp_path / "principles.yaml"
        original = [
            _entry("P001", rule="Unicode: αβγ → ε"),
            _entry(
                "P002",
                category="security",
                severity="suggestion",
                applies_to=["review-pr"],
                rule="Never hardcode credentials",
            ),
        ]
        write_principles(original, target)
        reloaded = load_existing_principles(target)
        assert len(reloaded) == 2
        assert reloaded[0].id == "P001"
        assert reloaded[0].rule == "Unicode: αβγ → ε"
        assert reloaded[1].applies_to == ["review-pr"]
        assert reloaded[1].severity == "suggestion"

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        target = _write_yaml(
            tmp_path,
            "principles.yaml",
            """
            version: "1.0"
            principles:
              - id: "P001"
                category: "old"
                severity: "blocking"
                applies_to: ["check-code"]
                rule: "Old rule"
            """,
        )
        write_principles([_entry("P002", category="new")], target)
        data = yaml.safe_load(target.read_text())
        assert len(data["principles"]) == 1
        assert data["principles"][0]["id"] == "P002"

    def test_header_comment_present_in_output(self, tmp_path: Path) -> None:
        target = tmp_path / "principles.yaml"
        write_principles([_entry("P001")], target)
        raw = target.read_text()
        assert ".claude/principles.yaml" in raw
        assert "check-code" in raw

    def test_empty_list_writes_empty_principles_block(self, tmp_path: Path) -> None:
        target = tmp_path / "principles.yaml"
        write_principles([], target)
        data = yaml.safe_load(target.read_text())
        assert data["principles"] == []
