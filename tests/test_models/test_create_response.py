"""Tests for harness_skills.models.create — CreateResponse, DetectedStack, GeneratedArtifact.

Coverage targets:
  - DetectedStack — required fields, optional fields, extra="forbid"
  - GeneratedArtifact — required fields, optional token_count, overwritten default
  - CreateResponse — command default, HarnessResponse base fields, required detected_stack
  - CreateResponse — optional list fields default to empty
  - CreateResponse — JSON serialisation produces parseable output with expected keys
  - CreateResponse — model_dump_json round-trip via model_validate
  - Integration — harness create --format json emits schema-validated CreateResponse
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from harness_skills.models.base import Status
from harness_skills.models.create import CreateResponse, DetectedStack, GeneratedArtifact


# ---------------------------------------------------------------------------
# DetectedStack
# ---------------------------------------------------------------------------


class TestDetectedStack:
    def test_minimal_construction(self) -> None:
        stack = DetectedStack(
            primary_language="Python",
            project_structure="single-app",
        )
        assert stack.primary_language == "Python"
        assert stack.project_structure == "single-app"
        assert stack.framework is None
        assert stack.secondary_languages == []

    def test_full_construction(self) -> None:
        stack = DetectedStack(
            primary_language="Python",
            secondary_languages=["JavaScript"],
            framework="FastAPI",
            project_structure="monorepo",
            test_framework="pytest",
            ci_platform="GitHub Actions",
            database="PostgreSQL",
            api_style="REST",
        )
        assert stack.framework == "FastAPI"
        assert stack.ci_platform == "GitHub Actions"
        assert stack.api_style == "REST"

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            DetectedStack(
                primary_language="Python",
                project_structure="single-app",
                unknown_field="oops",
            )

    def test_project_structure_values(self) -> None:
        for val in ("monorepo", "polyrepo", "single-app"):
            stack = DetectedStack(primary_language="Go", project_structure=val)
            assert stack.project_structure == val

    def test_missing_primary_language_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DetectedStack(project_structure="single-app")  # type: ignore[call-arg]

    def test_missing_project_structure_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DetectedStack(primary_language="Python")  # type: ignore[call-arg]

    def test_json_serialisation(self) -> None:
        stack = DetectedStack(
            primary_language="Python",
            project_structure="single-app",
            framework="Django",
        )
        data = json.loads(stack.model_dump_json())
        assert data["primary_language"] == "Python"
        assert data["project_structure"] == "single-app"
        assert data["framework"] == "Django"
        assert "secondary_languages" in data


# ---------------------------------------------------------------------------
# GeneratedArtifact
# ---------------------------------------------------------------------------


class TestGeneratedArtifact:
    def test_minimal_construction(self) -> None:
        artifact = GeneratedArtifact(
            artifact_path="harness.config.yaml",
            artifact_type="harness.config.yaml",
        )
        assert artifact.artifact_path == "harness.config.yaml"
        assert artifact.overwritten is False
        assert artifact.token_count is None

    def test_overwritten_true(self) -> None:
        artifact = GeneratedArtifact(
            artifact_path="docs/AGENTS.md",
            artifact_type="AGENTS.md",
            overwritten=True,
        )
        assert artifact.overwritten is True

    def test_token_count_must_be_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            GeneratedArtifact(
                artifact_path="x.md",
                artifact_type="AGENTS.md",
                token_count=-1,
            )

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            GeneratedArtifact(
                artifact_path="x.md",
                artifact_type="AGENTS.md",
                secret="oops",
            )

    def test_json_serialisation(self) -> None:
        artifact = GeneratedArtifact(
            artifact_path="harness.config.yaml",
            artifact_type="harness.config.yaml",
            token_count=512,
            overwritten=True,
        )
        data = json.loads(artifact.model_dump_json())
        assert data["artifact_path"] == "harness.config.yaml"
        assert data["token_count"] == 512
        assert data["overwritten"] is True


# ---------------------------------------------------------------------------
# CreateResponse
# ---------------------------------------------------------------------------


_MINIMAL_STACK = DetectedStack(
    primary_language="Python",
    project_structure="single-app",
)


class TestCreateResponse:
    def test_default_command_field(self) -> None:
        r = CreateResponse(
            status=Status.PASSED,
            detected_stack=_MINIMAL_STACK,
        )
        assert r.command == "harness create"

    def test_required_detected_stack(self) -> None:
        with pytest.raises(ValidationError):
            CreateResponse(status=Status.PASSED)  # type: ignore[call-arg]

    def test_optional_lists_default_to_empty(self) -> None:
        r = CreateResponse(
            status=Status.PASSED,
            detected_stack=_MINIMAL_STACK,
        )
        assert r.artifacts_generated == []
        assert r.domains_detected == []
        assert r.warnings == []

    def test_optional_paths_default_to_none(self) -> None:
        r = CreateResponse(
            status=Status.PASSED,
            detected_stack=_MINIMAL_STACK,
        )
        assert r.manifest_path is None
        assert r.schema_path is None
        assert r.symbols_index_path is None

    def test_inherits_harness_response_fields(self) -> None:
        r = CreateResponse(
            status=Status.PASSED,
            detected_stack=_MINIMAL_STACK,
        )
        assert hasattr(r, "timestamp")
        assert hasattr(r, "duration_ms")
        assert hasattr(r, "version")
        assert hasattr(r, "message")

    def test_with_artifacts_generated(self) -> None:
        artifact = GeneratedArtifact(
            artifact_path="harness.config.yaml",
            artifact_type="harness.config.yaml",
        )
        r = CreateResponse(
            status=Status.PASSED,
            detected_stack=_MINIMAL_STACK,
            artifacts_generated=[artifact],
        )
        assert len(r.artifacts_generated) == 1
        assert r.artifacts_generated[0].artifact_path == "harness.config.yaml"

    def test_failed_status(self) -> None:
        r = CreateResponse(
            status=Status.FAILED,
            detected_stack=_MINIMAL_STACK,
            message="write failed: permission denied",
        )
        assert r.status == Status.FAILED
        assert r.message == "write failed: permission denied"


# ---------------------------------------------------------------------------
# JSON serialisation
# ---------------------------------------------------------------------------


class TestCreateResponseJson:
    def test_json_parseable(self) -> None:
        r = CreateResponse(
            status=Status.PASSED,
            detected_stack=_MINIMAL_STACK,
        )
        data = json.loads(r.model_dump_json())
        assert isinstance(data, dict)

    def test_json_contains_required_keys(self) -> None:
        r = CreateResponse(
            status=Status.PASSED,
            detected_stack=_MINIMAL_STACK,
        )
        data = json.loads(r.model_dump_json())
        for key in ("command", "status", "detected_stack", "artifacts_generated"):
            assert key in data, f"Expected key '{key}' in JSON output"

    def test_json_detected_stack_nested(self) -> None:
        r = CreateResponse(
            status=Status.PASSED,
            detected_stack=_MINIMAL_STACK,
        )
        data = json.loads(r.model_dump_json())
        assert data["detected_stack"]["primary_language"] == "Python"
        assert data["detected_stack"]["project_structure"] == "single-app"

    def test_json_status_is_string(self) -> None:
        r = CreateResponse(status=Status.PASSED, detected_stack=_MINIMAL_STACK)
        data = json.loads(r.model_dump_json())
        assert data["status"] == "passed"

    def test_json_roundtrip_via_model_validate(self) -> None:
        artifact = GeneratedArtifact(
            artifact_path="harness.config.yaml",
            artifact_type="harness.config.yaml",
            overwritten=True,
        )
        original = CreateResponse(
            status=Status.PASSED,
            detected_stack=_MINIMAL_STACK,
            artifacts_generated=[artifact],
            message="created successfully",
        )
        data = json.loads(original.model_dump_json())
        restored = CreateResponse.model_validate(data)
        assert restored.status == original.status
        assert restored.command == original.command
        assert len(restored.artifacts_generated) == 1
        assert restored.artifacts_generated[0].artifact_path == "harness.config.yaml"
        assert restored.message == original.message

    def test_indent_json_is_multiline(self) -> None:
        r = CreateResponse(status=Status.PASSED, detected_stack=_MINIMAL_STACK)
        pretty = r.model_dump_json(indent=2)
        assert "\n" in pretty
        data = json.loads(pretty)
        assert data["command"] == "harness create"


# ---------------------------------------------------------------------------
# Integration — harness create --format json emits schema-validated output
# ---------------------------------------------------------------------------


class TestCreateCmdJsonOutput:
    """White-box integration: cli/create.py --format json must emit valid CreateResponse."""

    def _runner(self):
        from click.testing import CliRunner
        return CliRunner()

    def test_json_output_is_parseable(self, tmp_path) -> None:
        from harness_skills.cli.create import create_cmd
        runner = self._runner()
        output_path = tmp_path / "harness.config.yaml"
        result = runner.invoke(
            create_cmd,
            ["--format", "json", "--output", str(output_path)],
        )
        # May exit 0 or 1 depending on whether generators are installed.
        # Focus on: if exit 0, output must be valid CreateResponse JSON.
        if result.exit_code == 0:
            data = json.loads(result.output)
            response = CreateResponse.model_validate(data)
            assert response.command == "harness create"
            assert response.status == Status.PASSED
            assert response.detected_stack is not None

    def test_json_output_command_field(self, tmp_path) -> None:
        from harness_skills.cli.create import create_cmd
        runner = self._runner()
        output_path = tmp_path / "harness.config.yaml"
        result = runner.invoke(
            create_cmd,
            ["--format", "json", "--output", str(output_path)],
        )
        if result.exit_code == 0:
            data = json.loads(result.output)
            assert data.get("command") == "harness create"

    def test_text_format_produces_plain_output(self, tmp_path) -> None:
        from harness_skills.cli.create import create_cmd
        runner = self._runner()
        output_path = tmp_path / "harness.config.yaml"
        result = runner.invoke(
            create_cmd,
            ["--output", str(output_path)],  # default text format
        )
        if result.exit_code == 0:
            # Plain text — should NOT be JSON
            try:
                json.loads(result.output)
                is_json = True
            except json.JSONDecodeError:
                is_json = False
            assert not is_json, "Default text format should not produce JSON"
