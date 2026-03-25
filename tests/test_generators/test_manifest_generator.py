"""Tests for harness_skills.generators.manifest_generator.

Covers:
    - generate_manifest()   builds a valid dict
    - validate_manifest()   returns (jsonpath, message) pairs on violations
    - write_manifest()      validates before writing; raises ManifestValidationError
    - write_manifest_pair() atomic write of manifest + schema; pre-validates
    - ManifestValidationError  exception attributes
    - _jsonpath_from_absolute_path()  JSONPath formatting helper
"""

from __future__ import annotations

import json
from collections import deque
from datetime import datetime
from pathlib import Path

import pytest

from harness_skills.generators.manifest_generator import (
    ManifestValidationError,
    _jsonpath_from_absolute_path,
    generate_manifest,
    validate_manifest,
    write_manifest,
    write_manifest_pair,
    write_manifest_schema,
)
from harness_skills.models.create import DetectedStack, GeneratedArtifact

# ---------------------------------------------------------------------------
# Shared fixtures / constants
# ---------------------------------------------------------------------------

VALID_STACK = DetectedStack(
    primary_language="python",
    project_structure="single-app",
)

# Schema-compatible stack dict — the Pydantic model includes ``linter`` and
# ``documentation_files`` which the JSON schema does not yet declare, so we
# use a plain dict with only schema-known fields where validation is tested.
VALID_STACK_DICT: dict = {
    "primary_language": "python",
    "project_structure": "single-app",
}

VALID_ARTIFACT = GeneratedArtifact(
    artifact_path="harness.config.yaml",
    artifact_type="harness.config.yaml",
)


# ---------------------------------------------------------------------------
# generate_manifest
# ---------------------------------------------------------------------------


class TestGenerateManifest:
    def test_schema_version_set(self):
        m = generate_manifest(VALID_STACK)
        assert m["schema_version"] == "1.0"

    def test_generated_at_is_iso8601(self):
        m = generate_manifest(VALID_STACK)
        # datetime.fromisoformat raises if the string is not valid ISO-8601
        ts = datetime.fromisoformat(m["generated_at"])
        assert ts.tzinfo is not None, "generated_at must include timezone info"

    def test_stack_serialised_from_pydantic(self):
        m = generate_manifest(VALID_STACK)
        assert m["detected_stack"]["primary_language"] == "python"
        assert m["detected_stack"]["project_structure"] == "single-app"

    def test_stack_accepted_as_plain_dict(self):
        stack_dict = {
            "primary_language": "go",
            "project_structure": "monorepo",
        }
        m = generate_manifest(stack_dict)
        assert m["detected_stack"]["primary_language"] == "go"

    def test_domains_default_empty(self):
        m = generate_manifest(VALID_STACK)
        assert m["domains"] == []

    def test_domains_stored(self):
        m = generate_manifest(VALID_STACK, domains=["auth", "billing"])
        assert m["domains"] == ["auth", "billing"]

    def test_artifacts_default_empty(self):
        m = generate_manifest(VALID_STACK)
        assert m["artifacts"] == []

    def test_artifacts_serialised_from_pydantic(self):
        m = generate_manifest(VALID_STACK, artifacts=[VALID_ARTIFACT])
        assert len(m["artifacts"]) == 1
        assert m["artifacts"][0]["artifact_path"] == "harness.config.yaml"

    def test_metadata_forwarded(self):
        m = generate_manifest(
            VALID_STACK,
            git_sha="abc1234",
            git_branch="main",
            harness_version="0.1.0",
            project_root="/repo",
        )
        assert m["git_sha"] == "abc1234"
        assert m["git_branch"] == "main"
        assert m["harness_version"] == "0.1.0"
        assert m["project_root"] == "/repo"

    def test_optional_metadata_defaults_to_none(self):
        m = generate_manifest(VALID_STACK)
        for key in ("git_sha", "git_branch", "harness_version", "project_root",
                    "manifest_path", "schema_path", "symbols_index_path"):
            assert m[key] is None

    def test_valid_against_schema(self):
        m = generate_manifest(VALID_STACK_DICT, artifacts=[VALID_ARTIFACT])
        assert validate_manifest(m) == []


# ---------------------------------------------------------------------------
# validate_manifest
# ---------------------------------------------------------------------------


class TestValidateManifest:
    def test_valid_manifest_returns_empty_list(self):
        m = generate_manifest(VALID_STACK_DICT)
        assert validate_manifest(m) == []

    def test_missing_schema_version(self):
        m = generate_manifest(VALID_STACK)
        del m["schema_version"]
        errors = validate_manifest(m)
        assert errors, "Expected at least one error"
        assert any("schema_version" in msg for _, msg in errors)

    def test_wrong_schema_version_const(self):
        m = generate_manifest(VALID_STACK)
        m["schema_version"] = "2.0"
        errors = validate_manifest(m)
        assert errors, "schema_version const violation should produce an error"

    def test_missing_detected_stack(self):
        m = generate_manifest(VALID_STACK)
        del m["detected_stack"]
        errors = validate_manifest(m)
        assert errors
        assert any("detected_stack" in msg for _, msg in errors)

    def test_missing_detected_stack_required_field(self):
        m = generate_manifest(VALID_STACK)
        del m["detected_stack"]["project_structure"]
        errors = validate_manifest(m)
        assert errors
        jsonpaths = [jp for jp, _ in errors]
        # error should be anchored at $.detected_stack
        assert any("detected_stack" in jp for jp in jsonpaths)

    def test_invalid_project_structure_enum(self):
        m = generate_manifest(VALID_STACK)
        m["detected_stack"]["project_structure"] = "unknown-layout"
        errors = validate_manifest(m)
        assert errors
        jsonpaths = [jp for jp, _ in errors]
        assert any("project_structure" in jp for jp in jsonpaths)

    def test_invalid_artifact_type_enum(self):
        m = generate_manifest(
            VALID_STACK,
            artifacts=[{
                "artifact_path": "foo.md",
                "artifact_type": "NOT_A_REAL_TYPE",
            }],
        )
        errors = validate_manifest(m)
        assert errors
        jsonpaths = [jp for jp, _ in errors]
        # path should reference the nested artifact_type
        assert any("artifacts" in jp for jp in jsonpaths)

    def test_artifact_type_array_index_in_jsonpath(self):
        """Array indices must appear as [N] in JSONPath."""
        m = generate_manifest(
            VALID_STACK,
            artifacts=[
                VALID_ARTIFACT.model_dump(),
                {
                    "artifact_path": "x.md",
                    "artifact_type": "INVALID",
                },
            ],
        )
        errors = validate_manifest(m)
        jsonpaths = [jp for jp, _ in errors]
        # second artifact is at index 1
        assert any("[1]" in jp for jp in jsonpaths)

    def test_additional_property_rejected(self):
        m = generate_manifest(VALID_STACK)
        m["completely_unknown_field"] = "surprise"
        errors = validate_manifest(m)
        assert errors

    def test_additional_property_in_detected_stack_rejected(self):
        m = generate_manifest(VALID_STACK)
        m["detected_stack"]["not_a_real_field"] = "oops"
        errors = validate_manifest(m)
        assert errors

    def test_all_jsonpaths_start_with_dollar(self):
        m = generate_manifest(VALID_STACK)
        m["schema_version"] = "99"
        errors = validate_manifest(m)
        assert errors
        for jp, _ in errors:
            assert jp.startswith("$"), f"Expected '$'-rooted JSONPath, got: {jp!r}"

    def test_missing_artifacts_key(self):
        m = generate_manifest(VALID_STACK)
        del m["artifacts"]
        errors = validate_manifest(m)
        assert errors
        assert any("artifacts" in msg for _, msg in errors)

    def test_token_count_negative_rejected(self):
        m = generate_manifest(
            VALID_STACK,
            artifacts=[{
                "artifact_path": "x.md",
                "artifact_type": "other",
                "token_count": -1,  # minimum is 0
            }],
        )
        errors = validate_manifest(m)
        assert errors


# ---------------------------------------------------------------------------
# ManifestValidationError
# ---------------------------------------------------------------------------


class TestManifestValidationError:
    def test_errors_attribute(self):
        errors = [("$.foo", "missing field"), ("$.bar", "bad value")]
        exc = ManifestValidationError(errors)
        assert exc.errors == errors

    def test_str_contains_jsonpaths(self):
        errors = [("$.detected_stack", "'project_structure' is a required property")]
        exc = ManifestValidationError(errors)
        msg = str(exc)
        assert "$.detected_stack" in msg
        assert "'project_structure' is a required property" in msg

    def test_is_value_error(self):
        exc = ManifestValidationError([])
        assert isinstance(exc, ValueError)


# ---------------------------------------------------------------------------
# _jsonpath_from_absolute_path (private helper)
# ---------------------------------------------------------------------------


class TestJsonpathFromAbsolutePath:
    def test_empty_path_returns_dollar(self):
        assert _jsonpath_from_absolute_path(deque()) == "$"

    def test_single_string_segment(self):
        assert _jsonpath_from_absolute_path(deque(["detected_stack"])) == "$.detected_stack"

    def test_nested_string_segments(self):
        result = _jsonpath_from_absolute_path(deque(["detected_stack", "primary_language"]))
        assert result == "$.detected_stack.primary_language"

    def test_array_index_uses_bracket_notation(self):
        result = _jsonpath_from_absolute_path(deque(["artifacts", 0, "artifact_type"]))
        assert result == "$.artifacts[0].artifact_type"

    def test_second_array_index(self):
        result = _jsonpath_from_absolute_path(deque(["artifacts", 2, "token_count"]))
        assert result == "$.artifacts[2].token_count"

    def test_root_string_key(self):
        assert _jsonpath_from_absolute_path(deque(["schema_version"])) == "$.schema_version"


# ---------------------------------------------------------------------------
# write_manifest
# ---------------------------------------------------------------------------


class TestWriteManifest:
    def test_writes_valid_manifest(self, tmp_path):
        dest = tmp_path / "harness_manifest.json"
        write_manifest(dest, VALID_STACK_DICT)
        data = json.loads(dest.read_text())
        assert data["schema_version"] == "1.0"
        assert data["detected_stack"]["primary_language"] == "python"

    def test_written_file_passes_schema_validation(self, tmp_path):
        dest = tmp_path / "harness_manifest.json"
        write_manifest(dest, VALID_STACK_DICT, artifacts=[VALID_ARTIFACT])
        data = json.loads(dest.read_text())
        assert validate_manifest(data) == []

    def test_raises_manifest_validation_error_on_bad_stack(self, tmp_path):
        dest = tmp_path / "harness_manifest.json"
        bad_stack = {"primary_language": "python"}  # missing required project_structure
        with pytest.raises(ManifestValidationError):
            write_manifest(dest, bad_stack)

    def test_file_not_written_on_validation_failure(self, tmp_path):
        dest = tmp_path / "harness_manifest.json"
        bad_stack = {"primary_language": "python"}
        with pytest.raises(ManifestValidationError):
            write_manifest(dest, bad_stack)
        assert not dest.exists(), "File must not be written when validation fails"

    def test_validation_error_has_jsonpath_errors(self, tmp_path):
        dest = tmp_path / "harness_manifest.json"
        bad_stack = {"primary_language": "python"}
        with pytest.raises(ManifestValidationError) as exc_info:
            write_manifest(dest, bad_stack)
        jsonpaths = [jp for jp, _ in exc_info.value.errors]
        assert all(jp.startswith("$") for jp in jsonpaths)

    def test_returns_resolved_path(self, tmp_path):
        dest = tmp_path / "harness_manifest.json"
        result = write_manifest(dest, VALID_STACK_DICT)
        assert result == dest.resolve()

    def test_domains_and_artifacts_stored(self, tmp_path):
        dest = tmp_path / "harness_manifest.json"
        write_manifest(
            dest,
            VALID_STACK_DICT,
            domains=["auth", "billing"],
            artifacts=[VALID_ARTIFACT],
        )
        data = json.loads(dest.read_text())
        assert data["domains"] == ["auth", "billing"]
        assert data["artifacts"][0]["artifact_path"] == "harness.config.yaml"


# ---------------------------------------------------------------------------
# write_manifest_schema
# ---------------------------------------------------------------------------


class TestWriteManifestSchema:
    def test_writes_schema_file(self, tmp_path):
        dest = tmp_path / "harness_manifest.schema.json"
        write_manifest_schema(dest)
        assert dest.exists()

    def test_schema_is_valid_json(self, tmp_path):
        dest = tmp_path / "harness_manifest.schema.json"
        write_manifest_schema(dest)
        data = json.loads(dest.read_text())
        assert data.get("title") == "HarnessManifest"

    def test_schema_contains_required_version_const(self, tmp_path):
        dest = tmp_path / "harness_manifest.schema.json"
        write_manifest_schema(dest)
        data = json.loads(dest.read_text())
        assert data["properties"]["schema_version"]["const"] == "1.0"

    def test_returns_resolved_path(self, tmp_path):
        dest = tmp_path / "harness_manifest.schema.json"
        result = write_manifest_schema(dest)
        assert result == dest.resolve()


# ---------------------------------------------------------------------------
# write_manifest_pair
# ---------------------------------------------------------------------------


class TestWriteManifestPair:
    def test_writes_both_files(self, tmp_path):
        m_path, s_path = write_manifest_pair(tmp_path, VALID_STACK_DICT)
        assert m_path.exists()
        assert s_path.exists()

    def test_manifest_is_valid_json(self, tmp_path):
        m_path, _ = write_manifest_pair(tmp_path, VALID_STACK_DICT)
        data = json.loads(m_path.read_text())
        assert data["schema_version"] == "1.0"

    def test_manifest_passes_schema_validation(self, tmp_path):
        m_path, _ = write_manifest_pair(tmp_path, VALID_STACK_DICT)
        data = json.loads(m_path.read_text())
        assert validate_manifest(data) == []

    def test_schema_file_is_bundled_content(self, tmp_path):
        _, s_path = write_manifest_pair(tmp_path, VALID_STACK_DICT)
        schema = json.loads(s_path.read_text())
        assert schema.get("title") == "HarnessManifest"

    def test_manifest_records_own_paths(self, tmp_path):
        m_path, s_path = write_manifest_pair(tmp_path, VALID_STACK_DICT)
        data = json.loads(m_path.read_text())
        assert data["manifest_path"] == "harness_manifest.json"
        assert data["schema_path"] == "harness_manifest.schema.json"

    def test_custom_filenames(self, tmp_path):
        m_path, s_path = write_manifest_pair(
            tmp_path,
            VALID_STACK_DICT,
            manifest_filename="my_manifest.json",
            schema_filename="my_schema.json",
        )
        assert m_path.name == "my_manifest.json"
        assert s_path.name == "my_schema.json"

    def test_raises_on_invalid_manifest_before_writing(self, tmp_path):
        bad_stack = {"primary_language": "python"}  # missing project_structure
        with pytest.raises(ManifestValidationError):
            write_manifest_pair(tmp_path, bad_stack)
        # Neither file should exist when validation fails pre-write
        assert not (tmp_path / "harness_manifest.json").exists()

    def test_raises_if_directory_missing(self, tmp_path):
        missing = tmp_path / "does_not_exist"
        with pytest.raises(FileNotFoundError):
            write_manifest_pair(missing, VALID_STACK_DICT)

    def test_raises_if_path_is_file(self, tmp_path):
        a_file = tmp_path / "not_a_dir.txt"
        a_file.write_text("hello")
        with pytest.raises(NotADirectoryError):
            write_manifest_pair(a_file, VALID_STACK_DICT)

    def test_returns_tuple_of_paths(self, tmp_path):
        result = write_manifest_pair(tmp_path, VALID_STACK_DICT)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_domains_and_artifacts_in_manifest(self, tmp_path):
        m_path, _ = write_manifest_pair(
            tmp_path,
            VALID_STACK_DICT,
            domains=["payments"],
            artifacts=[VALID_ARTIFACT],
        )
        data = json.loads(m_path.read_text())
        assert "payments" in data["domains"]
        assert data["artifacts"][0]["artifact_type"] == "harness.config.yaml"


# ---------------------------------------------------------------------------
# generate_manifest — patterns and conventions
# ---------------------------------------------------------------------------


class TestGenerateManifestPatternsConventions:
    def test_patterns_default_empty(self):
        m = generate_manifest(VALID_STACK)
        assert m["patterns"] == []

    def test_patterns_stored(self):
        m = generate_manifest(VALID_STACK, patterns=["plugin-architecture", "gate-pattern"])
        assert m["patterns"] == ["plugin-architecture", "gate-pattern"]

    def test_conventions_default_empty(self):
        m = generate_manifest(VALID_STACK)
        assert m["conventions"] == []

    def test_conventions_stored(self):
        m = generate_manifest(VALID_STACK, conventions=["pep8", "type-annotations"])
        assert m["conventions"] == ["pep8", "type-annotations"]

    def test_patterns_and_conventions_valid_against_schema(self):
        m = generate_manifest(
            VALID_STACK_DICT,
            patterns=["plugin-architecture"],
            conventions=["pep8"],
        )
        assert validate_manifest(m) == []

    def test_invalid_patterns_type_rejected(self):
        """patterns must be an array of strings; non-string item should fail."""
        m = generate_manifest(VALID_STACK)
        m["patterns"] = [123]  # integer instead of string
        errors = validate_manifest(m)
        assert errors

    def test_invalid_conventions_type_rejected(self):
        m = generate_manifest(VALID_STACK)
        m["conventions"] = "not-a-list"  # string instead of array
        errors = validate_manifest(m)
        assert errors

    def test_write_manifest_pair_with_patterns_and_conventions(self, tmp_path):
        m_path, _ = write_manifest_pair(
            tmp_path,
            VALID_STACK_DICT,
            patterns=["plugin-architecture"],
            conventions=["pep8", "type-annotations"],
        )
        data = json.loads(m_path.read_text())
        assert data["patterns"] == ["plugin-architecture"]
        assert data["conventions"] == ["pep8", "type-annotations"]
        assert validate_manifest(data) == []


# ---------------------------------------------------------------------------
# Additional coverage tests
# ---------------------------------------------------------------------------


from unittest.mock import patch, MagicMock
from harness_skills.generators.manifest_generator import _to_dict


class TestToDict:
    def test_none_passthrough(self) -> None:
        assert _to_dict(None) is None

    def test_dict_passthrough(self) -> None:
        d = {"key": "value"}
        assert _to_dict(d) is d

    def test_pydantic_v2_model_dump(self) -> None:
        obj = MagicMock()
        obj.model_dump.return_value = {"a": 1}
        del obj.dict  # Remove dict attr so model_dump path is taken
        result = _to_dict(obj)
        assert result == {"a": 1}

    def test_pydantic_v1_dict(self) -> None:
        obj = MagicMock(spec=[])
        obj.dict = MagicMock(return_value={"b": 2})
        # Ensure model_dump is not present
        assert not hasattr(obj, "model_dump")
        result = _to_dict(obj)
        assert result == {"b": 2}

    def test_plain_object_passthrough(self) -> None:
        result = _to_dict(42)
        assert result == 42


class TestValidateManifestSchemaNotFound:
    def test_schema_not_found_raises(self) -> None:
        with patch("harness_skills.generators.manifest_generator._BUNDLED_SCHEMA",
                   Path("/nonexistent/schema.json")):
            with pytest.raises(FileNotFoundError):
                validate_manifest({})


class TestWriteManifestSchemaNotFound:
    def test_schema_not_found_raises(self) -> None:
        with patch("harness_skills.generators.manifest_generator._BUNDLED_SCHEMA",
                   Path("/nonexistent/schema.json")):
            with pytest.raises(FileNotFoundError):
                write_manifest_schema("/tmp/out.json")
