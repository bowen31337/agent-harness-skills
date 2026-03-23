"""
tests/test_env_isolation.py
===========================
pytest test suite for harness_skills.env_isolation.

Run with:
    pytest tests/test_env_isolation.py -v
"""

from __future__ import annotations

import pytest

from harness_skills.env_isolation import (
    DbIsolation,
    EnvIsolationSpec,
    OutputFormat,
    assign_port,
    container_name,
    generate_docker_compose_override,
    generate_dotenv,
    generate_env_config,
    generate_shell_exports,
    schema_name,
)


# ---------------------------------------------------------------------------
# schema_name
# ---------------------------------------------------------------------------


class TestSchemaName:
    def test_simple_id(self) -> None:
        assert schema_name("fb563322") == "worktree_fb563322"

    def test_hyphens_replaced(self) -> None:
        result = schema_name("feature-my-branch")
        assert "-" not in result
        assert result.startswith("worktree_")

    def test_slashes_replaced(self) -> None:
        result = schema_name("feature/my-branch")
        assert "/" not in result
        assert result.startswith("worktree_")

    def test_uppercase_lowercased(self) -> None:
        result = schema_name("FB563322")
        assert result == result.lower()

    def test_truncated_to_63_chars(self) -> None:
        long_id = "a" * 100
        result = schema_name(long_id)
        assert len(result) <= 63

    def test_does_not_end_with_underscore(self) -> None:
        # IDs ending in non-alphanumeric chars should not leave trailing _
        result = schema_name("abc---")
        assert not result.endswith("_")

    def test_uuid_style_id(self) -> None:
        result = schema_name("550e8400-e29b-41d4-a716-446655440000")
        assert result.startswith("worktree_")
        assert len(result) <= 63


# ---------------------------------------------------------------------------
# container_name
# ---------------------------------------------------------------------------


class TestContainerName:
    def test_simple_id(self) -> None:
        assert container_name("fb563322") == "harness_fb563322"

    def test_with_suffix(self) -> None:
        assert container_name("fb563322", "db") == "harness_fb563322_db"

    def test_hyphens_replaced(self) -> None:
        result = container_name("my-worktree")
        assert "-" not in result

    def test_truncated_to_63_chars(self) -> None:
        long_id = "z" * 200
        result = container_name(long_id)
        assert len(result) <= 63

    def test_suffix_included(self) -> None:
        result = container_name("abc", "redis")
        assert "redis" in result


# ---------------------------------------------------------------------------
# assign_port
# ---------------------------------------------------------------------------


class TestAssignPort:
    def test_returns_base_when_no_conflicts(self) -> None:
        port = assign_port("wt1", taken=[], base=9000)
        assert 9000 <= port < 9200

    def test_skips_taken_ports(self) -> None:
        all_taken = list(range(9000, 9199))
        port = assign_port("wt1", taken=all_taken, base=9000)
        assert port == 9199
        assert port not in all_taken

    def test_raises_when_range_exhausted(self) -> None:
        all_taken = list(range(9000, 9200))
        with pytest.raises(RuntimeError, match="No free port"):
            assign_port("wt1", taken=all_taken, base=9000, max_search=200)

    def test_deterministic_for_same_worktree_id(self) -> None:
        p1 = assign_port("fb563322", taken=[], base=8000)
        p2 = assign_port("fb563322", taken=[], base=8000)
        assert p1 == p2

    def test_different_worktree_ids_may_differ(self) -> None:
        # Not strictly guaranteed but extremely likely given hash spread.
        ports = {assign_port(f"wt-{i}", taken=[], base=8000) for i in range(20)}
        assert len(ports) > 1

    def test_none_taken_treated_as_empty(self) -> None:
        port = assign_port("wt_none", taken=None, base=8000)
        assert 8000 <= port < 8200


# ---------------------------------------------------------------------------
# EnvIsolationSpec defaults
# ---------------------------------------------------------------------------


class TestEnvIsolationSpecDefaults:
    def test_default_port(self) -> None:
        spec = EnvIsolationSpec(worktree_id="wt1")
        assert spec.port == 8000

    def test_default_db_isolation(self) -> None:
        spec = EnvIsolationSpec(worktree_id="wt1")
        assert spec.db_isolation == DbIsolation.NONE

    def test_extra_vars_default_empty(self) -> None:
        spec = EnvIsolationSpec(worktree_id="wt1")
        assert spec.extra_vars == {}


# ---------------------------------------------------------------------------
# generate_dotenv
# ---------------------------------------------------------------------------


class TestGenerateDotenv:
    def test_port_present(self) -> None:
        spec = EnvIsolationSpec(worktree_id="wt1", port=8001)
        content = generate_dotenv(spec)
        assert "PORT=8001" in content

    def test_worktree_id_in_header(self) -> None:
        spec = EnvIsolationSpec(worktree_id="fb563322", port=8001)
        content = generate_dotenv(spec)
        assert "fb563322" in content

    def test_no_db_vars_when_none_isolation(self) -> None:
        spec = EnvIsolationSpec(worktree_id="wt1", port=8001)
        content = generate_dotenv(spec)
        assert "DB_SCHEMA" not in content
        assert "DATABASE_URL" not in content
        assert "DB_CONTAINER" not in content

    def test_schema_var_for_schema_isolation(self) -> None:
        spec = EnvIsolationSpec(
            worktree_id="wt1",
            port=8001,
            db_isolation=DbIsolation.SCHEMA,
        )
        content = generate_dotenv(spec)
        assert "DB_SCHEMA=worktree_wt1" in content

    def test_explicit_schema_name_used(self) -> None:
        spec = EnvIsolationSpec(
            worktree_id="wt1",
            port=8001,
            db_isolation=DbIsolation.SCHEMA,
            db_schema="my_custom_schema",
        )
        content = generate_dotenv(spec)
        assert "DB_SCHEMA=my_custom_schema" in content

    def test_database_url_for_file_isolation(self) -> None:
        spec = EnvIsolationSpec(
            worktree_id="wt1",
            port=8001,
            db_isolation=DbIsolation.FILE,
        )
        content = generate_dotenv(spec)
        assert "DATABASE_URL=sqlite:////" in content or "DATABASE_URL=sqlite:///" in content
        assert "wt1" in content

    def test_explicit_db_file_used(self) -> None:
        spec = EnvIsolationSpec(
            worktree_id="wt1",
            port=8001,
            db_isolation=DbIsolation.FILE,
            db_file="/custom/path.db",
        )
        content = generate_dotenv(spec)
        assert "DATABASE_URL=sqlite:////custom/path.db" in content

    def test_container_var_for_container_isolation(self) -> None:
        spec = EnvIsolationSpec(
            worktree_id="wt1",
            port=8001,
            db_isolation=DbIsolation.CONTAINER,
        )
        content = generate_dotenv(spec)
        assert "DB_CONTAINER=" in content

    def test_extra_vars_included(self) -> None:
        spec = EnvIsolationSpec(
            worktree_id="wt1",
            port=8001,
            extra_vars={"LOG_LEVEL": "debug", "FEATURE_X": "true"},
        )
        content = generate_dotenv(spec)
        assert "LOG_LEVEL=debug" in content
        assert "FEATURE_X=true" in content

    def test_ends_with_newline(self) -> None:
        spec = EnvIsolationSpec(worktree_id="wt1", port=8001)
        content = generate_dotenv(spec)
        assert content.endswith("\n")


# ---------------------------------------------------------------------------
# generate_docker_compose_override
# ---------------------------------------------------------------------------


class TestGenerateDockerComposeOverride:
    def test_version_field_present(self) -> None:
        spec = EnvIsolationSpec(worktree_id="wt1", port=8001)
        content = generate_docker_compose_override(spec)
        assert "version:" in content

    def test_services_block_present(self) -> None:
        spec = EnvIsolationSpec(worktree_id="wt1", port=8001)
        content = generate_docker_compose_override(spec)
        assert "services:" in content

    def test_port_mapping(self) -> None:
        spec = EnvIsolationSpec(worktree_id="wt1", port=8001)
        content = generate_docker_compose_override(spec)
        assert "8001:8001" in content

    def test_port_in_environment(self) -> None:
        spec = EnvIsolationSpec(worktree_id="wt1", port=8001)
        content = generate_docker_compose_override(spec)
        assert "PORT" in content
        assert "8001" in content

    def test_schema_in_environment(self) -> None:
        spec = EnvIsolationSpec(
            worktree_id="wt1",
            port=8001,
            db_isolation=DbIsolation.SCHEMA,
        )
        content = generate_docker_compose_override(spec)
        assert "DB_SCHEMA" in content
        assert "worktree_wt1" in content

    def test_database_url_for_file_isolation(self) -> None:
        spec = EnvIsolationSpec(
            worktree_id="wt1",
            port=8001,
            db_isolation=DbIsolation.FILE,
        )
        content = generate_docker_compose_override(spec)
        assert "DATABASE_URL" in content

    def test_companion_postgres_service_for_container_isolation(self) -> None:
        spec = EnvIsolationSpec(
            worktree_id="wt1",
            port=8001,
            db_isolation=DbIsolation.CONTAINER,
        )
        content = generate_docker_compose_override(spec)
        assert "postgres" in content.lower()
        assert "_db" in content

    def test_extra_vars_in_environment_block(self) -> None:
        spec = EnvIsolationSpec(
            worktree_id="wt1",
            port=8001,
            extra_vars={"MY_VAR": "hello"},
        )
        content = generate_docker_compose_override(spec)
        assert "MY_VAR" in content
        assert "hello" in content

    def test_worktree_id_in_header_comment(self) -> None:
        spec = EnvIsolationSpec(worktree_id="fb563322", port=8001)
        content = generate_docker_compose_override(spec)
        assert "fb563322" in content


# ---------------------------------------------------------------------------
# generate_shell_exports
# ---------------------------------------------------------------------------


class TestGenerateShellExports:
    def test_shebang_present(self) -> None:
        spec = EnvIsolationSpec(worktree_id="wt1", port=8001)
        content = generate_shell_exports(spec)
        assert content.startswith("#!/usr/bin/env bash")

    def test_port_exported(self) -> None:
        spec = EnvIsolationSpec(worktree_id="wt1", port=8001)
        content = generate_shell_exports(spec)
        assert 'export PORT="8001"' in content

    def test_schema_exported_for_schema_isolation(self) -> None:
        spec = EnvIsolationSpec(
            worktree_id="wt1",
            port=8001,
            db_isolation=DbIsolation.SCHEMA,
        )
        content = generate_shell_exports(spec)
        assert 'export DB_SCHEMA="worktree_wt1"' in content

    def test_database_url_exported_for_file_isolation(self) -> None:
        spec = EnvIsolationSpec(
            worktree_id="wt1",
            port=8001,
            db_isolation=DbIsolation.FILE,
            db_file="/tmp/test.db",
        )
        content = generate_shell_exports(spec)
        assert 'export DATABASE_URL="sqlite:////tmp/test.db"' in content

    def test_container_exported_for_container_isolation(self) -> None:
        spec = EnvIsolationSpec(
            worktree_id="wt1",
            port=8001,
            db_isolation=DbIsolation.CONTAINER,
        )
        content = generate_shell_exports(spec)
        assert "export DB_CONTAINER=" in content

    def test_extra_vars_exported(self) -> None:
        spec = EnvIsolationSpec(
            worktree_id="wt1",
            port=8001,
            extra_vars={"FOO": "bar"},
        )
        content = generate_shell_exports(spec)
        assert 'export FOO="bar"' in content

    def test_no_db_exports_for_none_isolation(self) -> None:
        spec = EnvIsolationSpec(worktree_id="wt1", port=8001)
        content = generate_shell_exports(spec)
        assert "DB_SCHEMA" not in content
        assert "DATABASE_URL" not in content
        assert "DB_CONTAINER" not in content

    def test_ends_with_newline(self) -> None:
        spec = EnvIsolationSpec(worktree_id="wt1", port=8001)
        content = generate_shell_exports(spec)
        assert content.endswith("\n")


# ---------------------------------------------------------------------------
# generate_env_config (dispatch)
# ---------------------------------------------------------------------------


class TestGenerateEnvConfig:
    def test_dotenv_format_dispatches_correctly(self) -> None:
        spec = EnvIsolationSpec(worktree_id="wt1", port=8001)
        direct = generate_dotenv(spec)
        via_dispatch = generate_env_config(spec, OutputFormat.DOTENV)
        assert direct == via_dispatch

    def test_docker_compose_format_dispatches_correctly(self) -> None:
        spec = EnvIsolationSpec(worktree_id="wt1", port=8001)
        direct = generate_docker_compose_override(spec)
        via_dispatch = generate_env_config(spec, OutputFormat.DOCKER_COMPOSE)
        assert direct == via_dispatch

    def test_shell_format_dispatches_correctly(self) -> None:
        spec = EnvIsolationSpec(worktree_id="wt1", port=8001)
        direct = generate_shell_exports(spec)
        via_dispatch = generate_env_config(spec, OutputFormat.SHELL)
        assert direct == via_dispatch

    def test_unknown_format_raises_value_error(self) -> None:
        spec = EnvIsolationSpec(worktree_id="wt1", port=8001)
        with pytest.raises((ValueError, AttributeError)):
            generate_env_config(spec, "unknown_format")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Round-trip: all formats for all isolation strategies
# ---------------------------------------------------------------------------


class TestAllCombinations:
    """Smoke-test every (format, db_isolation) combination to confirm no crash."""

    @pytest.mark.parametrize("fmt", list(OutputFormat))
    @pytest.mark.parametrize(
        "db_iso",
        [DbIsolation.NONE, DbIsolation.SCHEMA, DbIsolation.FILE, DbIsolation.CONTAINER],
    )
    def test_no_exception(self, fmt: OutputFormat, db_iso: DbIsolation) -> None:
        spec = EnvIsolationSpec(
            worktree_id="smoke-test-123",
            port=9000,
            db_isolation=db_iso,
        )
        result = generate_env_config(spec, fmt)
        assert isinstance(result, str)
        assert len(result) > 0
