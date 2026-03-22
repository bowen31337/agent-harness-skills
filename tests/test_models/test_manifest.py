"""Tests for harness_skills.models.manifest — ManifestValidationError and ManifestValidateResponse.

Coverage targets:
  - ManifestValidationError — required fields, min_length on message, extra="forbid"
  - ManifestValidationError — jsonpath must be a non-empty string
  - ManifestValidationError — JSON serialisation round-trip
  - ManifestValidateResponse — valid=True case (zero errors)
  - ManifestValidateResponse — valid=False case (with error list)
  - ManifestValidateResponse — error_count ge=0 constraint
  - ManifestValidateResponse — default command field value
  - ManifestValidateResponse — inherits HarnessResponse base fields
  - ManifestValidateResponse — model_dump_json() produces parseable JSON
  - ManifestValidateResponse — JSON output contains all expected top-level keys
  - Integration — cli/manifest.py --json output is schema-consistent
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from harness_skills.models.base import Status
from harness_skills.models.manifest import ManifestValidationError, ManifestValidateResponse


# ---------------------------------------------------------------------------
# ManifestValidationError
# ---------------------------------------------------------------------------


class TestManifestValidationError:
    def test_valid_construction(self) -> None:
        err = ManifestValidationError(
            jsonpath="$.detected_stack",
            message="'project_structure' is a required property",
        )
        assert err.jsonpath == "$.detected_stack"
        assert err.message == "'project_structure' is a required property"

    def test_root_jsonpath_accepted(self) -> None:
        err = ManifestValidationError(jsonpath="$", message="fatal error")
        assert err.jsonpath == "$"

    def test_array_index_jsonpath_accepted(self) -> None:
        err = ManifestValidationError(
            jsonpath="$.artifacts[1].artifact_type",
            message="'BAD' is not valid",
        )
        assert err.jsonpath == "$.artifacts[1].artifact_type"

    def test_empty_message_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ManifestValidationError(jsonpath="$.foo", message="")

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            ManifestValidationError(
                jsonpath="$.foo",
                message="some error",
                unknown_key="oops",
            )

    def test_json_round_trip(self) -> None:
        err = ManifestValidationError(
            jsonpath="$.schema_version",
            message="'9.9' is not one of ['1.0']",
        )
        data = json.loads(err.model_dump_json())
        assert data["jsonpath"] == "$.schema_version"
        assert data["message"] == "'9.9' is not one of ['1.0']"

    def test_json_contains_expected_keys(self) -> None:
        err = ManifestValidationError(jsonpath="$.foo", message="bar")
        data = json.loads(err.model_dump_json())
        assert "jsonpath" in data
        assert "message" in data


# ---------------------------------------------------------------------------
# ManifestValidateResponse — construction
# ---------------------------------------------------------------------------


class TestManifestValidateResponseConstruction:
    def _make_valid(self, **overrides) -> ManifestValidateResponse:
        defaults = dict(
            status=Status.PASSED,
            valid=True,
            path="harness_manifest.json",
            error_count=0,
            errors=[],
        )
        defaults.update(overrides)
        return ManifestValidateResponse(**defaults)

    def test_default_command_field(self) -> None:
        r = self._make_valid()
        assert r.command == "harness manifest validate"

    def test_inherits_harness_response_fields(self) -> None:
        r = self._make_valid()
        # HarnessResponse base fields must be accessible
        assert hasattr(r, "timestamp")
        assert hasattr(r, "duration_ms")
        assert hasattr(r, "version")
        assert hasattr(r, "message")

    def test_valid_true_no_errors(self) -> None:
        r = self._make_valid()
        assert r.valid is True
        assert r.error_count == 0
        assert r.errors == []

    def test_valid_false_with_errors(self) -> None:
        errors = [
            ManifestValidationError(
                jsonpath="$.detected_stack",
                message="'project_structure' is required",
            )
        ]
        r = ManifestValidateResponse(
            status=Status.FAILED,
            valid=False,
            path="harness_manifest.json",
            error_count=1,
            errors=errors,
        )
        assert r.valid is False
        assert r.error_count == 1
        assert len(r.errors) == 1
        assert r.errors[0].jsonpath == "$.detected_stack"

    def test_negative_error_count_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ManifestValidateResponse(
                status=Status.FAILED,
                valid=False,
                error_count=-1,
                errors=[],
            )

    def test_path_optional(self) -> None:
        r = ManifestValidateResponse(
            status=Status.FAILED,
            valid=False,
            error_count=1,
            errors=[ManifestValidationError(jsonpath="$", message="fatal")],
        )
        assert r.path is None

    def test_multiple_errors(self) -> None:
        errors = [
            ManifestValidationError(jsonpath="$.schema_version", message="bad version"),
            ManifestValidationError(
                jsonpath="$.detected_stack.project_structure",
                message="invalid value",
            ),
        ]
        r = ManifestValidateResponse(
            status=Status.FAILED,
            valid=False,
            error_count=2,
            errors=errors,
        )
        assert len(r.errors) == 2
        assert r.error_count == 2


# ---------------------------------------------------------------------------
# ManifestValidateResponse — JSON serialisation
# ---------------------------------------------------------------------------


class TestManifestValidateResponseJson:
    def test_valid_response_json_parseable(self) -> None:
        r = ManifestValidateResponse(
            status=Status.PASSED,
            valid=True,
            path="harness_manifest.json",
            error_count=0,
            errors=[],
        )
        data = json.loads(r.model_dump_json())
        assert isinstance(data, dict)

    def test_json_contains_required_keys(self) -> None:
        r = ManifestValidateResponse(
            status=Status.PASSED,
            valid=True,
            path="harness_manifest.json",
            error_count=0,
            errors=[],
        )
        data = json.loads(r.model_dump_json())
        for key in ("command", "status", "valid", "path", "error_count", "errors"):
            assert key in data, f"Expected key '{key}' in JSON output"

    def test_json_valid_true_structure(self) -> None:
        r = ManifestValidateResponse(
            status=Status.PASSED,
            valid=True,
            path="some/path.json",
            error_count=0,
            errors=[],
        )
        data = json.loads(r.model_dump_json())
        assert data["valid"] is True
        assert data["error_count"] == 0
        assert data["errors"] == []
        assert data["path"] == "some/path.json"
        assert data["command"] == "harness manifest validate"
        assert data["status"] == "passed"

    def test_json_valid_false_structure(self) -> None:
        errors = [
            ManifestValidationError(
                jsonpath="$.artifacts[0].artifact_type",
                message="'bad' is not valid",
            )
        ]
        r = ManifestValidateResponse(
            status=Status.FAILED,
            valid=False,
            path="harness_manifest.json",
            error_count=1,
            errors=errors,
        )
        data = json.loads(r.model_dump_json())
        assert data["valid"] is False
        assert data["status"] == "failed"
        assert data["error_count"] == 1
        assert len(data["errors"]) == 1
        assert data["errors"][0]["jsonpath"] == "$.artifacts[0].artifact_type"
        assert data["errors"][0]["message"] == "'bad' is not valid"

    def test_json_errors_have_jsonpath_and_message(self) -> None:
        errors = [
            ManifestValidationError(jsonpath="$.schema_version", message="bad"),
            ManifestValidationError(jsonpath="$.detected_stack", message="missing"),
        ]
        r = ManifestValidateResponse(
            status=Status.FAILED,
            valid=False,
            error_count=2,
            errors=errors,
        )
        data = json.loads(r.model_dump_json())
        for entry in data["errors"]:
            assert "jsonpath" in entry
            assert "message" in entry
            assert entry["jsonpath"].startswith("$")
            assert entry["message"]  # non-empty

    def test_indent_json_serialisation(self) -> None:
        """model_dump_json(indent=2) must produce multi-line but still parseable output."""
        r = ManifestValidateResponse(
            status=Status.PASSED,
            valid=True,
            error_count=0,
            errors=[],
        )
        pretty = r.model_dump_json(indent=2)
        assert "\n" in pretty
        data = json.loads(pretty)
        assert data["valid"] is True

    def test_roundtrip_via_model_validate(self) -> None:
        """JSON serialised then re-validated must produce an equivalent model."""
        original = ManifestValidateResponse(
            status=Status.FAILED,
            valid=False,
            path="test.json",
            error_count=1,
            errors=[ManifestValidationError(jsonpath="$.foo", message="bar")],
        )
        data = json.loads(original.model_dump_json())
        restored = ManifestValidateResponse.model_validate(data)
        assert restored.valid == original.valid
        assert restored.error_count == original.error_count
        assert restored.errors[0].jsonpath == original.errors[0].jsonpath


# ---------------------------------------------------------------------------
# Integration — _emit_error() and validate_cmd() produce schema-consistent output
# ---------------------------------------------------------------------------


class TestManifestCliJsonSchemaConsistency:
    """White-box integration tests: cli/manifest.py JSON output == ManifestValidateResponse."""

    def _get_commands(self):
        from harness_skills.cli.manifest import manifest_cmd, _emit_error
        return manifest_cmd, _emit_error

    def test_emit_error_produces_valid_schema(self, capsys) -> None:
        """_emit_error(output_json=True) must emit ManifestValidateResponse-compatible JSON."""
        _, _emit_error = self._get_commands()
        from pathlib import Path
        _emit_error(
            output_json=True,
            error="file not found: test.json",
            path=Path("test.json"),
        )
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        # Must be re-parseable as ManifestValidateResponse
        response = ManifestValidateResponse.model_validate(data)
        assert response.valid is False
        assert response.error_count == 1
        assert response.errors[0].jsonpath == "$"
        assert response.status == Status.FAILED

    def test_emit_error_no_path_sets_null(self, capsys) -> None:
        _, _emit_error = self._get_commands()
        _emit_error(output_json=True, error="something failed", path=None)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["path"] is None
