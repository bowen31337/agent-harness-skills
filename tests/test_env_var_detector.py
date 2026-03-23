"""
Tests for harness_skills.env_var_detector and harness_skills.models.env_vars.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from harness_skills.env_var_detector import (
    detect_env_vars,
    scan_config_file,
    scan_dotenv_file,
    scan_source_file,
)
from harness_skills.models.env_vars import (
    EnvVarDetectionResult,
    EnvVarEntry,
    EnvVarSource,
)
from harness_skills.models.base import Status


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(tmp_path: Path, filename: str, content: str) -> Path:
    p = tmp_path / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# EnvVarEntry model
# ---------------------------------------------------------------------------


class TestEnvVarEntry:
    def test_required_defaults_true(self):
        e = EnvVarEntry(
            name="DATABASE_URL",
            source=EnvVarSource.DOTENV_EXAMPLE,
            file_path=".env.example",
        )
        assert e.required is True

    def test_optional_entry(self):
        e = EnvVarEntry(
            name="DEBUG",
            source=EnvVarSource.DOTENV_EXAMPLE,
            file_path=".env.example",
            required=False,
        )
        assert e.required is False

    def test_default_value_is_none(self):
        e = EnvVarEntry(
            name="API_KEY",
            source=EnvVarSource.SOURCE_CODE,
            file_path="app.py",
        )
        assert e.default_value is None

    def test_extra_fields_forbidden(self):
        with pytest.raises(Exception):
            EnvVarEntry(
                name="FOO",
                source=EnvVarSource.SOURCE_CODE,
                file_path="x.py",
                unknown_field="bad",
            )


# ---------------------------------------------------------------------------
# scan_dotenv_file
# ---------------------------------------------------------------------------


class TestScanDotenvFile:
    def test_required_key(self, tmp_path):
        p = _write(tmp_path, ".env.example", "DATABASE_URL=postgres://localhost/db\n")
        entries = scan_dotenv_file(p, tmp_path)
        assert len(entries) == 1
        e = entries[0]
        assert e.name == "DATABASE_URL"
        assert e.required is True
        assert e.default_value == "postgres://localhost/db"
        assert e.source == EnvVarSource.DOTENV_EXAMPLE

    def test_optional_commented_key(self, tmp_path):
        p = _write(tmp_path, ".env.example", "# OPTIONAL_KEY=some_value\n")
        entries = scan_dotenv_file(p, tmp_path)
        assert len(entries) == 1
        e = entries[0]
        assert e.name == "OPTIONAL_KEY"
        assert e.required is False
        assert e.default_value == "some_value"

    def test_empty_value(self, tmp_path):
        p = _write(tmp_path, ".env.example", "EMPTY_VAR=\n")
        entries = scan_dotenv_file(p, tmp_path)
        assert len(entries) == 1
        assert entries[0].default_value is None  # empty string → None

    def test_comment_context_attached_to_next_var(self, tmp_path):
        content = """\
            # API key from https://console.example.com
            API_KEY=sk-...
        """
        p = _write(tmp_path, ".env.example", content)
        entries = scan_dotenv_file(p, tmp_path)
        assert len(entries) == 1
        assert "API key" in entries[0].comment

    def test_pure_comment_lines_ignored(self, tmp_path):
        content = """\
            # This is a section header
            # with multiple lines
        """
        p = _write(tmp_path, ".env.example", content)
        entries = scan_dotenv_file(p, tmp_path)
        assert entries == []

    def test_blank_line_resets_comment_context(self, tmp_path):
        content = """\
            # Unrelated comment

            ANOTHER_KEY=value
        """
        p = _write(tmp_path, ".env.example", content)
        entries = scan_dotenv_file(p, tmp_path)
        assert len(entries) == 1
        assert entries[0].comment is None  # comment cleared by blank line

    def test_multiple_keys_parsed(self, tmp_path):
        content = """\
            KEY_A=value_a
            KEY_B=value_b
            # KEY_C=optional
        """
        p = _write(tmp_path, ".env.example", content)
        entries = scan_dotenv_file(p, tmp_path)
        assert len(entries) == 3
        names = {e.name for e in entries}
        assert names == {"KEY_A", "KEY_B", "KEY_C"}

    def test_line_numbers_recorded(self, tmp_path):
        content = "FIRST=1\nSECOND=2\n"
        p = _write(tmp_path, ".env.example", content)
        entries = scan_dotenv_file(p, tmp_path)
        assert entries[0].line_number == 1
        assert entries[1].line_number == 2

    def test_file_path_is_relative(self, tmp_path):
        p = _write(tmp_path, ".env.example", "KEY=val\n")
        entries = scan_dotenv_file(p, tmp_path)
        assert entries[0].file_path == ".env.example"

    def test_unreadable_file_returns_empty(self, tmp_path):
        fake = tmp_path / "nonexistent.env"
        entries = scan_dotenv_file(fake, tmp_path)
        assert entries == []

    def test_real_world_env_example(self, tmp_path):
        """Parse a realistic .env.example with mixed required/optional vars."""
        content = """\
            # ── Anthropic (direct) ───────────────────────────────────
            # API key from https://console.anthropic.com
            # ANTHROPIC_API_KEY=sk-ant-...

            # ── Model aliases ─────────────────────────────────────────
            # MODEL_DEFAULT=claude-sonnet-4-6
            # MODEL_OPUS=claude-opus-4-6

            # ── OpenAI ────────────────────────────────────────────────
            # OPENAI_API_KEY=sk-...
            # OPENAI_MODEL=gpt-4o

            DATABASE_URL=postgres://localhost/mydb
            SECRET_KEY=change-me-in-production
        """
        p = _write(tmp_path, ".env.example", content)
        entries = scan_dotenv_file(p, tmp_path)

        optional = [e for e in entries if not e.required]
        required = [e for e in entries if e.required]

        assert len(optional) >= 4
        assert len(required) == 2
        names = {e.name for e in required}
        assert "DATABASE_URL" in names
        assert "SECRET_KEY" in names


# ---------------------------------------------------------------------------
# scan_config_file
# ---------------------------------------------------------------------------


class TestScanConfigFile:
    def test_dollar_brace_syntax(self, tmp_path):
        content = "database_url: ${DATABASE_URL}\n"
        p = _write(tmp_path, "config.yaml", content)
        entries = scan_config_file(p, tmp_path)
        assert len(entries) == 1
        assert entries[0].name == "DATABASE_URL"
        assert entries[0].source == EnvVarSource.CONFIG_FILE

    def test_multiple_refs_on_same_line(self, tmp_path):
        content = "dsn: ${DB_HOST}:${DB_PORT}/${DB_NAME}\n"
        p = _write(tmp_path, "config.yaml", content)
        entries = scan_config_file(p, tmp_path)
        names = {e.name for e in entries}
        assert names == {"DB_HOST", "DB_PORT", "DB_NAME"}

    def test_bare_dollar_var(self, tmp_path):
        # $VAR_NAME (no braces, length > 2 so not a false positive like $1)
        content = "token: $API_TOKEN\n"
        p = _write(tmp_path, "config.yaml", content)
        entries = scan_config_file(p, tmp_path)
        assert any(e.name == "API_TOKEN" for e in entries)

    def test_no_refs_returns_empty(self, tmp_path):
        content = "key: literal_value\nother: 42\n"
        p = _write(tmp_path, "config.yml", content)
        entries = scan_config_file(p, tmp_path)
        assert entries == []

    def test_toml_file(self, tmp_path):
        content = 'url = "${DATABASE_URL}"\n'
        p = _write(tmp_path, "config.toml", content)
        entries = scan_config_file(p, tmp_path)
        assert len(entries) == 1
        assert entries[0].name == "DATABASE_URL"

    def test_line_numbers_recorded(self, tmp_path):
        content = "a: literal\nb: ${SECRET}\nc: other\n"
        p = _write(tmp_path, "config.yaml", content)
        entries = scan_config_file(p, tmp_path)
        assert entries[0].line_number == 2

    def test_unreadable_file_returns_empty(self, tmp_path):
        fake = tmp_path / "missing.yaml"
        entries = scan_config_file(fake, tmp_path)
        assert entries == []


# ---------------------------------------------------------------------------
# scan_source_file
# ---------------------------------------------------------------------------


class TestScanSourceFilePython:
    def test_os_environ_get(self, tmp_path):
        p = _write(tmp_path, "app.py", "val = os.environ.get('DATABASE_URL')\n")
        entries = scan_source_file(p, tmp_path, "python")
        assert any(e.name == "DATABASE_URL" for e in entries)

    def test_os_environ_subscript(self, tmp_path):
        p = _write(tmp_path, "app.py", "key = os.environ['SECRET_KEY']\n")
        entries = scan_source_file(p, tmp_path, "python")
        assert any(e.name == "SECRET_KEY" for e in entries)

    def test_os_getenv(self, tmp_path):
        p = _write(tmp_path, "app.py", "debug = os.getenv('DEBUG')\n")
        entries = scan_source_file(p, tmp_path, "python")
        assert any(e.name == "DEBUG" for e in entries)

    def test_source_code_source_tag(self, tmp_path):
        p = _write(tmp_path, "app.py", "x = os.getenv('MY_VAR')\n")
        entries = scan_source_file(p, tmp_path, "python")
        assert all(e.source == EnvVarSource.SOURCE_CODE for e in entries)

    def test_no_env_reads_returns_empty(self, tmp_path):
        p = _write(tmp_path, "utils.py", "def add(a, b):\n    return a + b\n")
        entries = scan_source_file(p, tmp_path, "python")
        assert entries == []

    def test_multiple_reads_in_one_file(self, tmp_path):
        content = """\
            import os
            db = os.environ.get('DATABASE_URL')
            secret = os.environ['SECRET_KEY']
            debug = os.getenv('DEBUG')
        """
        p = _write(tmp_path, "settings.py", content)
        entries = scan_source_file(p, tmp_path, "python")
        names = {e.name for e in entries}
        assert {"DATABASE_URL", "SECRET_KEY", "DEBUG"}.issubset(names)

    def test_line_numbers_recorded(self, tmp_path):
        content = "import os\ndb = os.getenv('DATABASE_URL')\n"
        p = _write(tmp_path, "app.py", content)
        entries = scan_source_file(p, tmp_path, "python")
        assert entries[0].line_number == 2


class TestScanSourceFileJavaScript:
    def test_process_env_dot_access(self, tmp_path):
        p = _write(tmp_path, "app.js", "const key = process.env.API_KEY;\n")
        entries = scan_source_file(p, tmp_path, "javascript")
        assert any(e.name == "API_KEY" for e in entries)

    def test_process_env_bracket_access(self, tmp_path):
        p = _write(tmp_path, "app.ts", "const url = process.env['DATABASE_URL'];\n")
        entries = scan_source_file(p, tmp_path, "typescript")
        assert any(e.name == "DATABASE_URL" for e in entries)

    def test_multiple_process_env(self, tmp_path):
        content = """\
            const port = process.env.PORT;
            const secret = process.env['SECRET_KEY'];
            const debug = process.env.DEBUG;
        """
        p = _write(tmp_path, "server.ts", content)
        entries = scan_source_file(p, tmp_path, "typescript")
        names = {e.name for e in entries}
        assert {"PORT", "SECRET_KEY", "DEBUG"}.issubset(names)


class TestScanSourceFileGo:
    def test_os_getenv(self, tmp_path):
        p = _write(tmp_path, "main.go", 'db := os.Getenv("DATABASE_URL")\n')
        entries = scan_source_file(p, tmp_path, "go")
        assert any(e.name == "DATABASE_URL" for e in entries)

    def test_os_lookup_env(self, tmp_path):
        p = _write(tmp_path, "main.go", 'val, ok := os.LookupEnv("API_KEY")\n')
        entries = scan_source_file(p, tmp_path, "go")
        assert any(e.name == "API_KEY" for e in entries)


class TestScanSourceFileRuby:
    def test_env_bracket(self, tmp_path):
        p = _write(tmp_path, "app.rb", "url = ENV['DATABASE_URL']\n")
        entries = scan_source_file(p, tmp_path, "ruby")
        assert any(e.name == "DATABASE_URL" for e in entries)

    def test_env_fetch(self, tmp_path):
        p = _write(tmp_path, "app.rb", "key = ENV.fetch('SECRET_KEY')\n")
        entries = scan_source_file(p, tmp_path, "ruby")
        assert any(e.name == "SECRET_KEY" for e in entries)


class TestScanSourceFileUnknownLanguage:
    def test_unknown_language_returns_empty(self, tmp_path):
        p = _write(tmp_path, "config.xml", "<key>value</key>\n")
        entries = scan_source_file(p, tmp_path, "xml")
        assert entries == []


# ---------------------------------------------------------------------------
# detect_env_vars (integration)
# ---------------------------------------------------------------------------


class TestDetectEnvVars:
    def test_returns_result_model(self, tmp_path):
        result = detect_env_vars(tmp_path)
        assert isinstance(result, EnvVarDetectionResult)

    def test_status_passed(self, tmp_path):
        result = detect_env_vars(tmp_path)
        assert result.status == Status.PASSED

    def test_command_field(self, tmp_path):
        result = detect_env_vars(tmp_path)
        assert result.command == "detect-env-vars"

    def test_empty_dir_zero_vars(self, tmp_path):
        result = detect_env_vars(tmp_path)
        assert result.total_vars_found == 0
        assert result.unique_var_names == []

    def test_dotenv_file_discovered(self, tmp_path):
        _write(tmp_path, ".env.example", "API_KEY=test\n")
        result = detect_env_vars(tmp_path)
        assert ".env.example" in result.dotenv_files_found
        assert "API_KEY" in result.unique_var_names

    def test_env_sample_discovered(self, tmp_path):
        _write(tmp_path, ".env.sample", "DB_URL=postgres://\n")
        result = detect_env_vars(tmp_path)
        assert any("env.sample" in f for f in result.dotenv_files_found)

    def test_source_file_discovered(self, tmp_path):
        _write(tmp_path, "app.py", "import os\nx = os.getenv('MY_VAR')\n")
        result = detect_env_vars(tmp_path)
        assert result.source_files_scanned >= 1
        assert "MY_VAR" in result.unique_var_names

    def test_config_file_vars_discovered(self, tmp_path):
        _write(tmp_path, "config.yaml", "url: ${DATABASE_URL}\n")
        result = detect_env_vars(tmp_path)
        assert "DATABASE_URL" in result.unique_var_names
        assert any("config.yaml" in f for f in result.config_files_found)

    def test_unique_var_names_are_sorted_and_deduplicated(self, tmp_path):
        _write(tmp_path, ".env.example", "ZEBRA=1\nAPPLE=2\nZEBRA=3\n")
        result = detect_env_vars(tmp_path)
        assert result.unique_var_names == sorted(set(result.unique_var_names))
        assert result.unique_var_names.count("ZEBRA") == 1

    def test_total_vars_includes_duplicates(self, tmp_path):
        """total_vars_found counts every occurrence, not unique names."""
        _write(tmp_path, ".env.example", "KEY=1\nKEY=2\n")
        result = detect_env_vars(tmp_path)
        assert result.total_vars_found == 2
        assert len(result.unique_var_names) == 1

    def test_skip_dirs_respected(self, tmp_path):
        (tmp_path / "vendor").mkdir()
        _write(tmp_path / "vendor", "app.py", "x = os.getenv('VENDOR_KEY')\n")
        _write(tmp_path, "app.py", "y = os.getenv('REAL_KEY')\n")
        result = detect_env_vars(tmp_path, skip_dirs=frozenset({"vendor"}))
        assert "REAL_KEY" in result.unique_var_names
        assert "VENDOR_KEY" not in result.unique_var_names

    def test_include_config_false_skips_config_files(self, tmp_path):
        _write(tmp_path, "config.yaml", "url: ${SECRET_VAR}\n")
        result = detect_env_vars(tmp_path, include_config=False)
        assert "SECRET_VAR" not in result.unique_var_names
        assert result.config_files_found == []

    def test_include_source_false_skips_source_files(self, tmp_path):
        _write(tmp_path, "app.py", "x = os.getenv('RUNTIME_VAR')\n")
        result = detect_env_vars(tmp_path, include_source=False)
        assert "RUNTIME_VAR" not in result.unique_var_names
        assert result.source_files_scanned == 0

    def test_nested_subdirectory_scanned(self, tmp_path):
        (tmp_path / "sub" / "deep").mkdir(parents=True)
        _write(tmp_path / "sub" / "deep", "service.py",
               "import os\nval = os.environ['DEEP_VAR']\n")
        result = detect_env_vars(tmp_path)
        assert "DEEP_VAR" in result.unique_var_names

    def test_venv_directory_skipped(self, tmp_path):
        (tmp_path / ".venv" / "lib").mkdir(parents=True)
        _write(tmp_path / ".venv" / "lib", "site.py",
               "x = os.getenv('VENV_INTERNAL')\n")
        result = detect_env_vars(tmp_path)
        assert "VENV_INTERNAL" not in result.unique_var_names

    def test_node_modules_skipped(self, tmp_path):
        (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
        _write(tmp_path / "node_modules" / "pkg", "index.js",
               "const x = process.env.NPM_INTERNAL;\n")
        result = detect_env_vars(tmp_path)
        assert "NPM_INTERNAL" not in result.unique_var_names

    def test_combined_sources(self, tmp_path):
        """Variables from all three source types appear in unique_var_names."""
        _write(tmp_path, ".env.example", "DOTENV_VAR=1\n")
        _write(tmp_path, "config.yaml", "url: ${CONFIG_VAR}\n")
        _write(tmp_path, "app.py", "import os\nx = os.getenv('CODE_VAR')\n")
        result = detect_env_vars(tmp_path)
        assert "DOTENV_VAR" in result.unique_var_names
        assert "CONFIG_VAR" in result.unique_var_names
        assert "CODE_VAR" in result.unique_var_names

    def test_typescript_source_scanned(self, tmp_path):
        _write(tmp_path, "server.ts",
               "const port = process.env.PORT ?? '3000';\n")
        result = detect_env_vars(tmp_path)
        assert "PORT" in result.unique_var_names

    def test_go_source_scanned(self, tmp_path):
        _write(tmp_path, "main.go", 'db := os.Getenv("DATABASE_URL")\n')
        result = detect_env_vars(tmp_path)
        assert "DATABASE_URL" in result.unique_var_names

    def test_ruby_source_scanned(self, tmp_path):
        _write(tmp_path, "app.rb", "secret = ENV['SECRET_KEY']\n")
        result = detect_env_vars(tmp_path)
        assert "SECRET_KEY" in result.unique_var_names

    def test_timestamp_is_set(self, tmp_path):
        result = detect_env_vars(tmp_path)
        assert result.timestamp is not None
        assert "T" in result.timestamp  # ISO-8601 check

    def test_scanned_path_recorded(self, tmp_path):
        result = detect_env_vars(tmp_path)
        assert result.scanned_path == str(tmp_path)

    def test_single_file_path_supported(self, tmp_path):
        p = _write(tmp_path, ".env.example", "SINGLE_VAR=hello\n")
        result = detect_env_vars(p)
        assert "SINGLE_VAR" in result.unique_var_names


# ---------------------------------------------------------------------------
# EnvVarDetectionResult model
# ---------------------------------------------------------------------------


class TestEnvVarDetectionResult:
    def test_required_fields(self):
        r = EnvVarDetectionResult(
            status=Status.PASSED,
            scanned_path=".",
        )
        assert r.command == "detect-env-vars"
        assert r.env_vars == []
        assert r.unique_var_names == []
        assert r.total_vars_found == 0

    def test_all_entries_accessible(self, tmp_path):
        _write(tmp_path, ".env.example", "FOO=bar\nBAZ=qux\n")
        result = detect_env_vars(tmp_path)
        assert len(result.env_vars) == 2
        assert all(isinstance(e, EnvVarEntry) for e in result.env_vars)
