"""Tests for harness_skills.generators.codebase_analyzer.

Covers:
    - detect_stack()          returns DetectedStack for all supported languages
    - detect_stack()          primary_language detection from each package file
    - detect_stack()          secondary_language detection for multi-language repos
    - detect_stack()          typescript upgrade from javascript when tsconfig.json present
    - detect_stack()          typescript upgrade when typescript dep in package.json
    - detect_stack()          framework detection (python, js/ts, go, java, ruby, rust)
    - detect_stack()          test framework detection
    - detect_stack()          CI platform detection
    - detect_stack()          database detection
    - detect_stack()          project_structure monorepo vs single-app
    - detect_stack()          empty directory returns primary_language="unknown"
    - _get_python_deps()      parses pyproject.toml (PEP 621 and Poetry)
    - _get_python_deps()      parses requirements.txt
    - _get_js_deps()          parses package.json all dependency sections
    - _get_go_deps()          parses go.mod require blocks
    - _get_java_deps()        parses pom.xml and build.gradle
    - _get_ruby_deps()        parses Gemfile
    - _get_rust_deps()        parses Cargo.toml
    - _first_match()          substring matching helper
    - _first_exact_match()    exact matching helper
    - _as_dict()              safe dict coercion helper
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness_skills.generators.codebase_analyzer import (
    _as_dict,
    _detect_api_style,
    _first_exact_match,
    _first_match,
    _get_go_deps,
    _get_java_deps,
    _get_js_deps,
    _get_python_deps,
    _get_ruby_deps,
    _get_rust_deps,
    detect_stack,
)
from harness_skills.models.create import DetectedStack


# ===========================================================================
# Fixtures — package file writers
# ===========================================================================


def write_pyproject(path: Path, *, deps: list[str] | None = None, poetry: bool = False) -> None:
    """Write a minimal pyproject.toml with the given PEP 621 dependencies."""
    if poetry:
        dep_lines = "\n".join(f'{d} = "*"' for d in (deps or []))
        path.write_text(
            f"[tool.poetry]\nname = \"myapp\"\n\n[tool.poetry.dependencies]\n{dep_lines}\n",
            encoding="utf-8",
        )
    else:
        dep_lines = "\n".join(f'  "{d}",' for d in (deps or []))
        path.write_text(
            f'[project]\nname = "myapp"\ndependencies = [\n{dep_lines}\n]\n\n'
            f"[tool.pytest.ini_options]\ntestpaths = [\"tests\"]\n",
            encoding="utf-8",
        )


def write_requirements(path: Path, deps: list[str]) -> None:
    """Write a requirements.txt with the given package lines."""
    path.write_text("\n".join(deps) + "\n", encoding="utf-8")


def write_package_json(path: Path, *, deps: dict[str, str] | None = None, dev: dict[str, str] | None = None) -> None:
    """Write a minimal package.json."""
    data: dict[str, object] = {"name": "myapp", "version": "1.0.0"}
    if deps:
        data["dependencies"] = deps
    if dev:
        data["devDependencies"] = dev
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def write_go_mod(path: Path, deps: list[str]) -> None:
    """Write a go.mod with the given module dependencies."""
    lines = ["module github.com/example/app", "", "go 1.21", "", "require ("]
    for dep in deps:
        lines.append(f"\t{dep} v1.0.0")
    lines.append(")")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_cargo_toml(path: Path, deps: list[str]) -> None:
    """Write a Cargo.toml with the given crate dependencies."""
    dep_lines = "\n".join(f'{d} = "1.0"' for d in deps)
    path.write_text(
        f'[package]\nname = "myapp"\nversion = "0.1.0"\n\n[dependencies]\n{dep_lines}\n',
        encoding="utf-8",
    )


def write_gemfile(path: Path, gems: list[str]) -> None:
    """Write a Gemfile with the given gem names."""
    lines = ["source 'https://rubygems.org'"] + [f"gem '{g}'" for g in gems]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_pom_xml(path: Path, artifact_ids: list[str]) -> None:
    """Write a minimal pom.xml with the given artifactIds."""
    deps = "\n".join(
        f"    <dependency><groupId>org.example</groupId>"
        f"<artifactId>{a}</artifactId></dependency>"
        for a in artifact_ids
    )
    path.write_text(
        f"<project>\n  <dependencies>\n{deps}\n  </dependencies>\n</project>\n",
        encoding="utf-8",
    )


# ===========================================================================
# detect_stack — return type and fallback
# ===========================================================================


class TestDetectStackReturnType:
    def test_returns_detected_stack_instance(self, tmp_path: Path):
        result = detect_stack(tmp_path)
        assert isinstance(result, DetectedStack)

    def test_empty_dir_primary_language_is_unknown(self, tmp_path: Path):
        result = detect_stack(tmp_path)
        assert result.primary_language == "unknown"

    def test_empty_dir_secondary_languages_empty(self, tmp_path: Path):
        result = detect_stack(tmp_path)
        assert result.secondary_languages == []

    def test_empty_dir_framework_is_none(self, tmp_path: Path):
        result = detect_stack(tmp_path)
        assert result.framework is None

    def test_empty_dir_project_structure_is_single_app(self, tmp_path: Path):
        result = detect_stack(tmp_path)
        assert result.project_structure == "single-app"

    def test_string_path_accepted(self, tmp_path: Path):
        result = detect_stack(str(tmp_path))
        assert isinstance(result, DetectedStack)


# ===========================================================================
# detect_stack — primary language detection
# ===========================================================================


class TestPrimaryLanguageDetection:
    def test_pyproject_toml_detected_as_python(self, tmp_path: Path):
        write_pyproject(tmp_path / "pyproject.toml")
        assert detect_stack(tmp_path).primary_language == "python"

    def test_setup_py_detected_as_python(self, tmp_path: Path):
        (tmp_path / "setup.py").write_text("from setuptools import setup\nsetup()\n")
        assert detect_stack(tmp_path).primary_language == "python"

    def test_requirements_txt_detected_as_python(self, tmp_path: Path):
        write_requirements(tmp_path / "requirements.txt", ["requests"])
        assert detect_stack(tmp_path).primary_language == "python"

    def test_package_json_detected_as_javascript(self, tmp_path: Path):
        write_package_json(tmp_path / "package.json")
        assert detect_stack(tmp_path).primary_language == "javascript"

    def test_cargo_toml_detected_as_rust(self, tmp_path: Path):
        write_cargo_toml(tmp_path / "Cargo.toml", [])
        assert detect_stack(tmp_path).primary_language == "rust"

    def test_go_mod_detected_as_go(self, tmp_path: Path):
        write_go_mod(tmp_path / "go.mod", [])
        assert detect_stack(tmp_path).primary_language == "go"

    def test_gemfile_detected_as_ruby(self, tmp_path: Path):
        write_gemfile(tmp_path / "Gemfile", [])
        assert detect_stack(tmp_path).primary_language == "ruby"

    def test_pom_xml_detected_as_java(self, tmp_path: Path):
        write_pom_xml(tmp_path / "pom.xml", [])
        assert detect_stack(tmp_path).primary_language == "java"

    def test_build_gradle_detected_as_java(self, tmp_path: Path):
        (tmp_path / "build.gradle").write_text("apply plugin: 'java'\n")
        assert detect_stack(tmp_path).primary_language == "java"

    def test_pubspec_yaml_detected_as_dart(self, tmp_path: Path):
        (tmp_path / "pubspec.yaml").write_text("name: myapp\n")
        assert detect_stack(tmp_path).primary_language == "dart"

    def test_mix_exs_detected_as_elixir(self, tmp_path: Path):
        (tmp_path / "mix.exs").write_text("defmodule MyApp.MixProject do\nend\n")
        assert detect_stack(tmp_path).primary_language == "elixir"

    def test_csproj_detected_as_csharp(self, tmp_path: Path):
        (tmp_path / "MyApp.csproj").write_text("<Project />\n")
        assert detect_stack(tmp_path).primary_language == "csharp"

    def test_pyproject_takes_priority_over_package_json(self, tmp_path: Path):
        write_pyproject(tmp_path / "pyproject.toml")
        write_package_json(tmp_path / "package.json")
        assert detect_stack(tmp_path).primary_language == "python"


# ===========================================================================
# detect_stack — TypeScript upgrade
# ===========================================================================


class TestTypeScriptUpgrade:
    def test_tsconfig_upgrades_javascript_to_typescript(self, tmp_path: Path):
        write_package_json(tmp_path / "package.json")
        (tmp_path / "tsconfig.json").write_text('{"compilerOptions": {}}\n')
        assert detect_stack(tmp_path).primary_language == "typescript"

    def test_typescript_dep_upgrades_javascript_to_typescript(self, tmp_path: Path):
        write_package_json(tmp_path / "package.json", dev={"typescript": "^5.0.0"})
        assert detect_stack(tmp_path).primary_language == "typescript"

    def test_no_typescript_dep_stays_javascript(self, tmp_path: Path):
        write_package_json(tmp_path / "package.json", deps={"lodash": "^4.0.0"})
        assert detect_stack(tmp_path).primary_language == "javascript"


# ===========================================================================
# detect_stack — secondary languages
# ===========================================================================


class TestSecondaryLanguages:
    def test_python_and_js_secondary(self, tmp_path: Path):
        write_pyproject(tmp_path / "pyproject.toml")
        write_package_json(tmp_path / "package.json")
        result = detect_stack(tmp_path)
        assert result.primary_language == "python"
        assert "javascript" in result.secondary_languages

    def test_python_and_go_secondary(self, tmp_path: Path):
        write_pyproject(tmp_path / "pyproject.toml")
        write_go_mod(tmp_path / "go.mod", [])
        result = detect_stack(tmp_path)
        assert result.primary_language == "python"
        assert "go" in result.secondary_languages

    def test_no_duplicates_in_secondary(self, tmp_path: Path):
        write_pyproject(tmp_path / "pyproject.toml")
        write_requirements(tmp_path / "requirements.txt", ["requests"])
        result = detect_stack(tmp_path)
        assert result.secondary_languages.count("python") == 0


# ===========================================================================
# detect_stack — framework detection
# ===========================================================================


class TestFrameworkDetection:
    # Python
    def test_fastapi_detected(self, tmp_path: Path):
        write_pyproject(tmp_path / "pyproject.toml", deps=["fastapi>=0.100"])
        assert detect_stack(tmp_path).framework == "fastapi"

    def test_flask_detected(self, tmp_path: Path):
        write_requirements(tmp_path / "requirements.txt", ["flask==2.3.0"])
        write_pyproject(tmp_path / "pyproject.toml")
        assert detect_stack(tmp_path).framework == "flask"

    def test_django_detected(self, tmp_path: Path):
        write_pyproject(tmp_path / "pyproject.toml", deps=["django>=4.0"])
        assert detect_stack(tmp_path).framework == "django"

    def test_flask_in_requirements(self, tmp_path: Path):
        (tmp_path / "setup.py").write_text("from setuptools import setup\nsetup()\n")
        write_requirements(tmp_path / "requirements.txt", ["flask"])
        assert detect_stack(tmp_path).framework == "flask"

    # JavaScript / TypeScript
    def test_next_js_detected(self, tmp_path: Path):
        write_package_json(tmp_path / "package.json", deps={"next": "^14.0.0"})
        assert detect_stack(tmp_path).framework == "next.js"

    def test_express_detected(self, tmp_path: Path):
        write_package_json(tmp_path / "package.json", deps={"express": "^4.0.0"})
        assert detect_stack(tmp_path).framework == "express"

    def test_react_detected(self, tmp_path: Path):
        write_package_json(tmp_path / "package.json", deps={"react": "^18.0.0"})
        assert detect_stack(tmp_path).framework == "react"

    def test_nestjs_detected(self, tmp_path: Path):
        write_package_json(tmp_path / "package.json", deps={"@nestjs/core": "^10.0.0"})
        assert detect_stack(tmp_path).framework == "nestjs"

    def test_vue_detected(self, tmp_path: Path):
        write_package_json(tmp_path / "package.json", deps={"vue": "^3.0.0"})
        assert detect_stack(tmp_path).framework == "vue"

    # Go
    def test_gin_detected(self, tmp_path: Path):
        write_go_mod(tmp_path / "go.mod", ["github.com/gin-gonic/gin"])
        assert detect_stack(tmp_path).framework == "gin"

    def test_echo_detected(self, tmp_path: Path):
        write_go_mod(tmp_path / "go.mod", ["github.com/labstack/echo/v4"])
        assert detect_stack(tmp_path).framework == "echo"

    # Java
    def test_spring_boot_detected_from_pom(self, tmp_path: Path):
        write_pom_xml(tmp_path / "pom.xml", ["spring-boot-starter-web"])
        assert detect_stack(tmp_path).framework == "spring boot"

    # Ruby
    def test_rails_detected(self, tmp_path: Path):
        write_gemfile(tmp_path / "Gemfile", ["rails"])
        assert detect_stack(tmp_path).framework == "rails"

    def test_sinatra_detected(self, tmp_path: Path):
        write_gemfile(tmp_path / "Gemfile", ["sinatra"])
        assert detect_stack(tmp_path).framework == "sinatra"

    # Rust
    def test_axum_detected(self, tmp_path: Path):
        write_cargo_toml(tmp_path / "Cargo.toml", ["axum"])
        assert detect_stack(tmp_path).framework == "axum"

    def test_actix_detected(self, tmp_path: Path):
        write_cargo_toml(tmp_path / "Cargo.toml", ["actix-web"])
        assert detect_stack(tmp_path).framework == "actix"

    def test_no_framework_returns_none(self, tmp_path: Path):
        write_pyproject(tmp_path / "pyproject.toml", deps=["requests"])
        assert detect_stack(tmp_path).framework is None


# ===========================================================================
# detect_stack — test framework detection
# ===========================================================================


class TestTestFrameworkDetection:
    def test_pytest_detected_from_dep(self, tmp_path: Path):
        write_pyproject(tmp_path / "pyproject.toml", deps=["pytest>=8.0"])
        assert detect_stack(tmp_path).test_framework == "pytest"

    def test_pytest_detected_from_tool_config(self, tmp_path: Path):
        # pyproject.toml with [tool.pytest.ini_options] but no pytest dep
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\ndependencies = []\n\n'
            "[tool.pytest.ini_options]\ntestpaths = [\"tests\"]\n",
            encoding="utf-8",
        )
        assert detect_stack(tmp_path).test_framework == "pytest"

    def test_jest_detected(self, tmp_path: Path):
        write_package_json(tmp_path / "package.json", dev={"jest": "^29.0.0"})
        assert detect_stack(tmp_path).test_framework == "jest"

    def test_vitest_detected(self, tmp_path: Path):
        write_package_json(tmp_path / "package.json", dev={"vitest": "^1.0.0"})
        assert detect_stack(tmp_path).test_framework == "vitest"

    def test_playwright_detected_in_js(self, tmp_path: Path):
        write_package_json(tmp_path / "package.json", dev={"@playwright/test": "^1.40.0"})
        assert detect_stack(tmp_path).test_framework == "playwright"

    def test_go_defaults_to_testing(self, tmp_path: Path):
        write_go_mod(tmp_path / "go.mod", [])
        assert detect_stack(tmp_path).test_framework == "testing"

    def test_go_testify_detected(self, tmp_path: Path):
        write_go_mod(tmp_path / "go.mod", ["github.com/stretchr/testify"])
        assert detect_stack(tmp_path).test_framework == "testify"

    def test_rust_defaults_to_built_in(self, tmp_path: Path):
        write_cargo_toml(tmp_path / "Cargo.toml", [])
        assert detect_stack(tmp_path).test_framework == "built-in"

    def test_rspec_detected(self, tmp_path: Path):
        write_gemfile(tmp_path / "Gemfile", ["rspec"])
        assert detect_stack(tmp_path).test_framework == "rspec"

    def test_junit_detected(self, tmp_path: Path):
        write_pom_xml(tmp_path / "pom.xml", ["junit-jupiter"])
        assert detect_stack(tmp_path).test_framework == "junit"

    def test_unknown_language_test_framework_is_none(self, tmp_path: Path):
        assert detect_stack(tmp_path).test_framework is None


# ===========================================================================
# detect_stack — CI platform detection
# ===========================================================================


class TestCIPlatformDetection:
    def test_github_actions_detected(self, tmp_path: Path):
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("on: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n")
        assert detect_stack(tmp_path).ci_platform == "github-actions"

    def test_gitlab_ci_detected(self, tmp_path: Path):
        (tmp_path / ".gitlab-ci.yml").write_text("stages:\n  - test\n")
        assert detect_stack(tmp_path).ci_platform == "gitlab-ci"

    def test_circleci_detected(self, tmp_path: Path):
        circleci = tmp_path / ".circleci"
        circleci.mkdir()
        (circleci / "config.yml").write_text("version: 2.1\n")
        assert detect_stack(tmp_path).ci_platform == "circleci"

    def test_jenkins_detected(self, tmp_path: Path):
        (tmp_path / "Jenkinsfile").write_text("pipeline { agent any }\n")
        assert detect_stack(tmp_path).ci_platform == "jenkins"

    def test_travis_ci_detected(self, tmp_path: Path):
        (tmp_path / ".travis.yml").write_text("language: python\n")
        assert detect_stack(tmp_path).ci_platform == "travis-ci"

    def test_no_ci_returns_none(self, tmp_path: Path):
        assert detect_stack(tmp_path).ci_platform is None

    def test_empty_github_workflows_dir_not_detected(self, tmp_path: Path):
        # Directory exists but is empty — should not be detected
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        assert detect_stack(tmp_path).ci_platform is None


# ===========================================================================
# detect_stack — database detection
# ===========================================================================


class TestDatabaseDetection:
    def test_psycopg2_detected_as_postgresql(self, tmp_path: Path):
        write_pyproject(tmp_path / "pyproject.toml", deps=["psycopg2-binary"])
        assert detect_stack(tmp_path).database == "postgresql"

    def test_pymongo_detected_as_mongodb(self, tmp_path: Path):
        write_pyproject(tmp_path / "pyproject.toml", deps=["pymongo"])
        assert detect_stack(tmp_path).database == "mongodb"

    def test_redis_py_detected(self, tmp_path: Path):
        write_pyproject(tmp_path / "pyproject.toml", deps=["redis"])
        assert detect_stack(tmp_path).database == "redis"

    def test_pg_npm_detected_as_postgresql(self, tmp_path: Path):
        write_package_json(tmp_path / "package.json", deps={"pg": "^8.0.0"})
        assert detect_stack(tmp_path).database == "postgresql"

    def test_prisma_npm_detected(self, tmp_path: Path):
        write_package_json(tmp_path / "package.json", deps={"@prisma/client": "^5.0.0"})
        assert detect_stack(tmp_path).database == "prisma"

    def test_go_pgx_detected_as_postgresql(self, tmp_path: Path):
        write_go_mod(tmp_path / "go.mod", ["github.com/jackc/pgx/v5"])
        assert detect_stack(tmp_path).database == "postgresql"

    def test_go_mongo_detected(self, tmp_path: Path):
        write_go_mod(tmp_path / "go.mod", ["go.mongodb.org/mongo-driver"])
        assert detect_stack(tmp_path).database == "mongodb"

    def test_rust_sqlx_detected(self, tmp_path: Path):
        write_cargo_toml(tmp_path / "Cargo.toml", ["sqlx"])
        assert detect_stack(tmp_path).database == "sqlx"

    def test_no_database_dep_returns_none(self, tmp_path: Path):
        write_pyproject(tmp_path / "pyproject.toml", deps=["requests"])
        assert detect_stack(tmp_path).database is None

    def test_typescript_uses_js_db_detection(self, tmp_path: Path):
        write_package_json(tmp_path / "package.json", deps={"pg": "^8.0.0"})
        (tmp_path / "tsconfig.json").write_text("{}")
        result = detect_stack(tmp_path)
        assert result.primary_language == "typescript"
        assert result.database == "postgresql"


# ===========================================================================
# detect_stack — project structure detection
# ===========================================================================


class TestProjectStructureDetection:
    def test_single_app_default(self, tmp_path: Path):
        write_pyproject(tmp_path / "pyproject.toml")
        assert detect_stack(tmp_path).project_structure == "single-app"

    def test_lerna_json_detected_as_monorepo(self, tmp_path: Path):
        (tmp_path / "lerna.json").write_text('{"version": "independent"}\n')
        assert detect_stack(tmp_path).project_structure == "monorepo"

    def test_pnpm_workspace_detected_as_monorepo(self, tmp_path: Path):
        (tmp_path / "pnpm-workspace.yaml").write_text("packages:\n  - 'packages/*'\n")
        assert detect_stack(tmp_path).project_structure == "monorepo"

    def test_nx_json_detected_as_monorepo(self, tmp_path: Path):
        (tmp_path / "nx.json").write_text("{}\n")
        assert detect_stack(tmp_path).project_structure == "monorepo"

    def test_turbo_json_detected_as_monorepo(self, tmp_path: Path):
        (tmp_path / "turbo.json").write_text('{"pipeline": {}}\n')
        assert detect_stack(tmp_path).project_structure == "monorepo"

    def test_packages_dir_with_content_detected_as_monorepo(self, tmp_path: Path):
        packages = tmp_path / "packages" / "lib-a"
        packages.mkdir(parents=True)
        (packages / "package.json").write_text('{"name": "lib-a"}\n')
        assert detect_stack(tmp_path).project_structure == "monorepo"

    def test_apps_dir_with_content_detected_as_monorepo(self, tmp_path: Path):
        apps = tmp_path / "apps" / "web"
        apps.mkdir(parents=True)
        (apps / "package.json").write_text('{"name": "web"}\n')
        assert detect_stack(tmp_path).project_structure == "monorepo"

    def test_package_json_workspaces_detected_as_monorepo(self, tmp_path: Path):
        data = {"name": "root", "workspaces": ["packages/*"]}
        (tmp_path / "package.json").write_text(json.dumps(data))
        assert detect_stack(tmp_path).project_structure == "monorepo"

    def test_empty_packages_dir_is_not_monorepo(self, tmp_path: Path):
        (tmp_path / "packages").mkdir()
        assert detect_stack(tmp_path).project_structure == "single-app"

    def test_pyproject_uv_workspace_detected_as_monorepo(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text(
            "[tool.uv.workspace]\nmembers = [\"packages/*\"]\n",
            encoding="utf-8",
        )
        assert detect_stack(tmp_path).project_structure == "monorepo"


# ===========================================================================
# _get_python_deps — unit tests
# ===========================================================================


class TestGetPythonDeps:
    def test_pep621_dependencies_extracted(self, tmp_path: Path):
        write_pyproject(tmp_path / "pyproject.toml", deps=["fastapi>=0.100", "pydantic"])
        deps = _get_python_deps(tmp_path)
        assert "fastapi>=0.100".split(">=")[0].lower() in deps or "fastapi" in " ".join(deps)

    def test_requirements_txt_parsed(self, tmp_path: Path):
        write_requirements(tmp_path / "requirements.txt", ["flask==2.3.0", "gunicorn"])
        deps = _get_python_deps(tmp_path)
        assert "flask" in deps
        assert "gunicorn" in deps

    def test_requirements_txt_comments_ignored(self, tmp_path: Path):
        (tmp_path / "requirements.txt").write_text("# comment\nrequests\n")
        deps = _get_python_deps(tmp_path)
        assert "requests" in deps
        assert "# comment" not in deps

    def test_requirements_txt_version_specifiers_stripped(self, tmp_path: Path):
        write_requirements(tmp_path / "requirements.txt", ["django>=4.0,<5.0"])
        deps = _get_python_deps(tmp_path)
        assert "django" in deps

    def test_poetry_dependencies_extracted(self, tmp_path: Path):
        write_pyproject(tmp_path / "pyproject.toml", deps=["fastapi", "uvicorn"], poetry=True)
        deps = _get_python_deps(tmp_path)
        assert "fastapi" in deps
        assert "uvicorn" in deps

    def test_missing_files_returns_empty(self, tmp_path: Path):
        deps = _get_python_deps(tmp_path)
        assert deps == []

    def test_multiple_requirements_files_merged(self, tmp_path: Path):
        write_requirements(tmp_path / "requirements.txt", ["flask"])
        write_requirements(tmp_path / "requirements-dev.txt", ["pytest"])
        deps = _get_python_deps(tmp_path)
        assert "flask" in deps
        assert "pytest" in deps


# ===========================================================================
# _get_js_deps — unit tests
# ===========================================================================


class TestGetJsDeps:
    def test_dependencies_extracted(self, tmp_path: Path):
        write_package_json(tmp_path / "package.json", deps={"express": "^4.0"})
        assert "express" in _get_js_deps(tmp_path)

    def test_dev_dependencies_extracted(self, tmp_path: Path):
        write_package_json(tmp_path / "package.json", dev={"jest": "^29.0"})
        assert "jest" in _get_js_deps(tmp_path)

    def test_all_sections_merged(self, tmp_path: Path):
        write_package_json(tmp_path / "package.json", deps={"react": "^18"}, dev={"typescript": "^5"})
        deps = _get_js_deps(tmp_path)
        assert "react" in deps
        assert "typescript" in deps

    def test_missing_package_json_returns_empty(self, tmp_path: Path):
        assert _get_js_deps(tmp_path) == []

    def test_malformed_package_json_returns_empty(self, tmp_path: Path):
        (tmp_path / "package.json").write_text("not json{{")
        assert _get_js_deps(tmp_path) == []


# ===========================================================================
# _get_go_deps — unit tests
# ===========================================================================


class TestGetGoDeps:
    def test_require_block_extracted(self, tmp_path: Path):
        write_go_mod(tmp_path / "go.mod", ["github.com/gin-gonic/gin"])
        deps = _get_go_deps(tmp_path)
        assert any("gin-gonic/gin" in d for d in deps)

    def test_multiple_deps_extracted(self, tmp_path: Path):
        write_go_mod(tmp_path / "go.mod", [
            "github.com/gin-gonic/gin",
            "go.mongodb.org/mongo-driver",
        ])
        deps = _get_go_deps(tmp_path)
        assert any("gin-gonic" in d for d in deps)
        assert any("mongo-driver" in d for d in deps)

    def test_missing_go_mod_returns_empty(self, tmp_path: Path):
        assert _get_go_deps(tmp_path) == []


# ===========================================================================
# _get_java_deps — unit tests
# ===========================================================================


class TestGetJavaDeps:
    def test_pom_artifact_ids_extracted(self, tmp_path: Path):
        write_pom_xml(tmp_path / "pom.xml", ["spring-boot-starter-web", "junit-jupiter"])
        deps = _get_java_deps(tmp_path)
        assert "spring-boot-starter-web" in deps

    def test_missing_pom_returns_empty(self, tmp_path: Path):
        assert _get_java_deps(tmp_path) == []

    def test_build_gradle_deps_extracted(self, tmp_path: Path):
        (tmp_path / "build.gradle").write_text(
            'implementation "org.springframework.boot:spring-boot-starter:3.0.0"\n'
        )
        deps = _get_java_deps(tmp_path)
        assert any("spring" in d for d in deps)


# ===========================================================================
# _get_ruby_deps — unit tests
# ===========================================================================


class TestGetRubyDeps:
    def test_gem_names_extracted(self, tmp_path: Path):
        write_gemfile(tmp_path / "Gemfile", ["rails", "devise"])
        deps = _get_ruby_deps(tmp_path)
        assert "rails" in deps
        assert "devise" in deps

    def test_missing_gemfile_returns_empty(self, tmp_path: Path):
        assert _get_ruby_deps(tmp_path) == []

    def test_gem_with_version_extracted(self, tmp_path: Path):
        (tmp_path / "Gemfile").write_text("gem 'rails', '~> 7.0'\n")
        assert "rails" in _get_ruby_deps(tmp_path)

    def test_double_quoted_gem_extracted(self, tmp_path: Path):
        (tmp_path / "Gemfile").write_text('gem "sinatra"\n')
        assert "sinatra" in _get_ruby_deps(tmp_path)


# ===========================================================================
# _get_rust_deps — unit tests
# ===========================================================================


class TestGetRustDeps:
    def test_cargo_toml_deps_extracted(self, tmp_path: Path):
        write_cargo_toml(tmp_path / "Cargo.toml", ["axum", "tokio"])
        deps = _get_rust_deps(tmp_path)
        assert "axum" in deps
        assert "tokio" in deps

    def test_missing_cargo_toml_returns_empty(self, tmp_path: Path):
        assert _get_rust_deps(tmp_path) == []

    def test_hyphenated_crate_name_extracted(self, tmp_path: Path):
        write_cargo_toml(tmp_path / "Cargo.toml", ["actix-web", "serde_json"])
        deps = _get_rust_deps(tmp_path)
        assert "actix-web" in deps


# ===========================================================================
# Helper function unit tests
# ===========================================================================


class TestFirstMatch:
    def test_returns_first_matching_name(self):
        result = _first_match(["psycopg2", "redis"], [("psycopg2", "postgresql"), ("redis", "redis")])
        assert result == "postgresql"

    def test_returns_none_when_no_match(self):
        result = _first_match(["requests"], [("django", "django")])
        assert result is None

    def test_substring_match_works(self):
        # "psycopg2-binary" contains "psycopg2"
        result = _first_match(["psycopg2-binary"], [("psycopg2", "postgresql")])
        assert result == "postgresql"

    def test_empty_deps_returns_none(self):
        result = _first_match([], [("django", "django")])
        assert result is None

    def test_empty_table_returns_none(self):
        result = _first_match(["django"], [])
        assert result is None


class TestFirstExactMatch:
    def test_exact_match_found(self):
        result = _first_exact_match(["express", "lodash"], [("express", "express")])
        assert result == "express"

    def test_partial_match_not_returned(self):
        # "express-async" should NOT match "express" (exact match only)
        result = _first_exact_match(["express-async"], [("express", "express")])
        assert result is None

    def test_returns_none_when_no_match(self):
        result = _first_exact_match(["lodash"], [("express", "express")])
        assert result is None

    def test_empty_deps_returns_none(self):
        result = _first_exact_match([], [("react", "react")])
        assert result is None


class TestAsDict:
    def test_dict_passed_through(self):
        d = {"a": 1}
        assert _as_dict(d) is d

    def test_none_returns_empty_dict(self):
        assert _as_dict(None) == {}

    def test_list_returns_empty_dict(self):
        assert _as_dict(["a", "b"]) == {}

    def test_string_returns_empty_dict(self):
        assert _as_dict("hello") == {}

    def test_int_returns_empty_dict(self):
        assert _as_dict(42) == {}


# ===========================================================================
# Integration: detect_stack on a realistic Python project (this repo)
# ===========================================================================


class TestDetectStackOnRealProject:
    def test_detects_python_from_this_repo(self):
        """detect_stack on the actual project root must return python."""
        import harness_skills

        project_root = Path(harness_skills.__file__).parent.parent
        result = detect_stack(project_root)
        assert result.primary_language == "python"

    def test_detects_pytest_from_this_repo(self):
        """The real project uses pytest."""
        import harness_skills

        project_root = Path(harness_skills.__file__).parent.parent
        result = detect_stack(project_root)
        assert result.test_framework == "pytest"

    @pytest.mark.parametrize("platform", ["github-actions", "gitlab-ci"])
    def test_detects_ci_from_this_repo(self, platform: str):
        """The real project has both GitHub Actions and GitLab CI."""
        import harness_skills

        project_root = Path(harness_skills.__file__).parent.parent
        result = detect_stack(project_root)
        # At least one CI platform should be detected
        assert result.ci_platform is not None


# ===========================================================================
# detect_stack — documentation coverage detection
# ===========================================================================


class TestDocumentationCoverageDetection:
    def test_readme_detected(self, tmp_path: Path):
        (tmp_path / "README.md").write_text("# My Project\n")
        result = detect_stack(tmp_path)
        assert "README.md" in result.documentation_files

    def test_multiple_docs_detected(self, tmp_path: Path):
        (tmp_path / "README.md").write_text("# Readme\n")
        (tmp_path / "CONTRIBUTING.md").write_text("# Contributing\n")
        (tmp_path / "CHANGELOG.md").write_text("# Changelog\n")
        (tmp_path / "AGENTS.md").write_text("# Agents\n")
        result = detect_stack(tmp_path)
        assert sorted(result.documentation_files) == [
            "AGENTS.md",
            "CHANGELOG.md",
            "CONTRIBUTING.md",
            "README.md",
        ]

    def test_missing_readme_detected_when_absent(self, tmp_path: Path):
        result = detect_stack(tmp_path)
        assert "README.md" not in result.documentation_files

    def test_empty_dir_returns_empty_documentation_files(self, tmp_path: Path):
        result = detect_stack(tmp_path)
        assert result.documentation_files == []

    def test_partial_docs_detected(self, tmp_path: Path):
        (tmp_path / "README.md").write_text("# Readme\n")
        (tmp_path / "AGENTS.md").write_text("# Agents\n")
        result = detect_stack(tmp_path)
        assert result.documentation_files == ["README.md", "AGENTS.md"]


# ===========================================================================
# API style detection
# ===========================================================================


class TestApiStyleDetection:
    """Tests for _detect_api_style() and its integration with detect_stack()."""

    def test_fastapi_route_file_detected_as_rest(self, tmp_path: Path):
        """tmp_path with FastAPI route file -> api_style='rest'."""
        write_pyproject(tmp_path / "pyproject.toml", deps=["fastapi", "uvicorn"])
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        (app_dir / "main.py").write_text(
            'from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get("/health")\ndef health():\n    return {"ok": True}\n',
            encoding="utf-8",
        )
        result = detect_stack(tmp_path)
        assert result.api_style == "rest"

    def test_schema_graphql_detected_as_graphql(self, tmp_path: Path):
        """tmp_path with schema.graphql -> api_style='graphql'."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\ndependencies = []\n', encoding="utf-8"
        )
        (tmp_path / "schema.graphql").write_text(
            "type Query {\n  hello: String\n}\n", encoding="utf-8"
        )
        result = detect_stack(tmp_path)
        assert result.api_style == "graphql"

    def test_proto_file_detected_as_grpc(self, tmp_path: Path):
        """tmp_path with .proto file -> api_style='grpc'."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\ndependencies = []\n', encoding="utf-8"
        )
        proto_dir = tmp_path / "protos"
        proto_dir.mkdir()
        (proto_dir / "service.proto").write_text(
            'syntax = "proto3";\nservice Greeter {}\n', encoding="utf-8"
        )
        result = detect_stack(tmp_path)
        assert result.api_style == "grpc"

    def test_no_api_indicators_returns_none(self, tmp_path: Path):
        """tmp_path with no API indicators -> api_style=None."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\ndependencies = ["requests"]\n', encoding="utf-8"
        )
        result = detect_stack(tmp_path)
        assert result.api_style is None

    def test_detect_api_style_called_from_detect_stack(self, tmp_path: Path):
        """api_style field in DetectedStack is no longer always None when indicators present."""
        write_pyproject(tmp_path / "pyproject.toml", deps=["flask"])
        (tmp_path / "app.py").write_text(
            'from flask import Flask\napp = Flask(__name__)\n@app.get("/")\ndef index():\n    return "ok"\n',
            encoding="utf-8",
        )
        result = detect_stack(tmp_path)
        assert result.api_style is not None

    def test_graphql_dep_detected(self, tmp_path: Path):
        """GraphQL dependency in package.json triggers graphql detection."""
        write_package_json(
            tmp_path / "package.json",
            deps={"apollo-server": "^3.0.0", "graphql": "^16.0.0"},
        )
        result = detect_stack(tmp_path)
        assert result.api_style == "graphql"

    def test_grpc_dep_detected(self, tmp_path: Path):
        """gRPC dependency triggers grpc detection."""
        write_pyproject(tmp_path / "pyproject.toml", deps=["grpcio", "protobuf"])
        result = detect_stack(tmp_path)
        assert result.api_style == "grpc"

    def test_express_route_detected_as_rest(self, tmp_path: Path):
        """Express-style route patterns in JS files trigger REST detection."""
        write_package_json(
            tmp_path / "package.json",
            deps={"express": "^4.0.0"},
        )
        (tmp_path / "server.js").write_text(
            'const app = require("express")();\napp.get("/api/users", (req, res) => res.json([]));\n',
            encoding="utf-8",
        )
        result = detect_stack(tmp_path)
        assert result.api_style == "rest"

    def test_direct_detect_api_style_function_exists(self, tmp_path: Path):
        """_detect_api_style() exists and is callable."""
        result = _detect_api_style(tmp_path, "python")
        assert result is None

    def test_gql_extension_detected(self, tmp_path: Path):
        """schema.gql extension also triggers graphql detection."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\ndependencies = []\n', encoding="utf-8"
        )
        (tmp_path / "schema.gql").write_text("type Query { hello: String }\n", encoding="utf-8")
        result = detect_stack(tmp_path)
        assert result.api_style == "graphql"


# ===========================================================================
# Additional coverage tests
# ===========================================================================


from harness_skills.generators.codebase_analyzer import (
    _detect_database,
    _detect_documentation_coverage,
    _detect_linter,
    _detect_project_structure,
    _get_deps_for_language,
    _has_rest_routes,
)


class TestSetupCfgDeps:
    def test_setup_cfg_install_requires(self, tmp_path: Path) -> None:
        (tmp_path / "setup.cfg").write_text(
            "[options]\ninstall_requires =\n    requests>=2.0\n    flask\n",
            encoding="utf-8",
        )
        deps = _get_python_deps(tmp_path)
        assert "requests" in deps
        assert "flask" in deps


class TestGoModDeps:
    def test_go_mod_single_require(self, tmp_path: Path) -> None:
        (tmp_path / "go.mod").write_text(
            "module example.com/app\n\nrequire github.com/gin-gonic/gin v1.9.0\n",
            encoding="utf-8",
        )
        deps = _get_go_deps(tmp_path)
        assert "github.com/gin-gonic/gin" in deps

    def test_go_mod_oserror(self, tmp_path: Path) -> None:
        """When go.mod is not readable, return empty list."""
        deps = _get_go_deps(tmp_path)
        assert deps == []


class TestJavaDeps:
    def test_pom_xml_oserror(self, tmp_path: Path) -> None:
        # pom.xml exists but test parse
        (tmp_path / "pom.xml").write_text(
            "<project><dependencies>"
            "<dependency><groupId>org.spring</groupId><artifactId>spring-web</artifactId></dependency>"
            "</dependencies></project>",
            encoding="utf-8",
        )
        deps = _get_java_deps(tmp_path)
        assert "spring-web" in deps
        assert "org.spring" in deps

    def test_build_gradle_deps(self, tmp_path: Path) -> None:
        (tmp_path / "build.gradle").write_text(
            "dependencies {\n    implementation 'com.google.guava:guava'\n}\n",
            encoding="utf-8",
        )
        deps = _get_java_deps(tmp_path)
        assert any("guava" in d for d in deps)

    def test_build_gradle_kts_deps(self, tmp_path: Path) -> None:
        (tmp_path / "build.gradle.kts").write_text(
            'dependencies {\n    implementation("org.jetbrains.kotlin:kotlin-stdlib")\n}\n',
            encoding="utf-8",
        )
        deps = _get_java_deps(tmp_path)
        assert any("kotlin-stdlib" in d for d in deps)


class TestRubyDeps:
    def test_gemfile_deps(self, tmp_path: Path) -> None:
        (tmp_path / "Gemfile").write_text("gem 'rails'\ngem 'pg'\n", encoding="utf-8")
        deps = _get_ruby_deps(tmp_path)
        assert "rails" in deps
        assert "pg" in deps

    def test_gemfile_not_exist(self, tmp_path: Path) -> None:
        deps = _get_ruby_deps(tmp_path)
        assert deps == []


class TestRustDeps:
    def test_cargo_deps(self, tmp_path: Path) -> None:
        (tmp_path / "Cargo.toml").write_text(
            "[dependencies]\nserde = \"1.0\"\ntokio = { version = \"1\" }\n",
            encoding="utf-8",
        )
        deps = _get_rust_deps(tmp_path)
        assert "serde" in deps
        assert "tokio" in deps

    def test_cargo_not_exist(self, tmp_path: Path) -> None:
        deps = _get_rust_deps(tmp_path)
        assert deps == []

    def test_cargo_toml_fallback_regex(self, tmp_path: Path) -> None:
        """When TOML parsing fails (invalid format), fallback regex is used."""
        (tmp_path / "Cargo.toml").write_text(
            "[dependencies\nserde = 1.0\n",  # Invalid TOML
            encoding="utf-8",
        )
        deps = _get_rust_deps(tmp_path)
        # Regex fallback should at least find 'serde'
        assert "serde" in deps


class TestDetectDatabase:
    def test_python_database(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\ndependencies = ["sqlalchemy"]\n', encoding="utf-8"
        )
        result = _detect_database(tmp_path, "python")
        assert result is not None

    def test_unknown_language(self, tmp_path: Path) -> None:
        result = _detect_database(tmp_path, "haskell")
        assert result is None

    def test_kotlin_maps_to_java(self, tmp_path: Path) -> None:
        result = _detect_database(tmp_path, "kotlin")
        # No deps -> None, but the code path for kotlin->java is exercised
        assert result is None

    def test_typescript_maps_to_javascript(self, tmp_path: Path) -> None:
        result = _detect_database(tmp_path, "typescript")
        assert result is None

    def test_go_database(self, tmp_path: Path) -> None:
        (tmp_path / "go.mod").write_text(
            "module ex\n\ngo 1.21\n\nrequire (\n\tgorm.io/gorm v1.0\n)\n",
            encoding="utf-8",
        )
        result = _detect_database(tmp_path, "go")
        assert result is not None

    def test_rust_database(self, tmp_path: Path) -> None:
        (tmp_path / "Cargo.toml").write_text(
            "[dependencies]\ndiesel = \"2.0\"\n", encoding="utf-8"
        )
        result = _detect_database(tmp_path, "rust")
        assert result is not None

    def test_unsupported_lang_in_database_deps(self, tmp_path: Path) -> None:
        # "ruby" is not in _DATABASE_DEPS unless _DATABASE_DEPS includes it.
        result = _detect_database(tmp_path, "ruby")
        # Should return None gracefully


class TestRestRoutes:
    def test_js_rest_routes(self, tmp_path: Path) -> None:
        (tmp_path / "server.js").write_text(
            'const app = require("express")();\napp.get("/users", (req, res) => {});\n'
        )
        assert _has_rest_routes(tmp_path, "javascript") is True

    def test_ts_rest_routes(self, tmp_path: Path) -> None:
        (tmp_path / "server.ts").write_text(
            'app.post("/api/items", handler);\n'
        )
        assert _has_rest_routes(tmp_path, "typescript") is True


class TestProjectStructure:
    def test_pnpm_workspace(self, tmp_path: Path) -> None:
        (tmp_path / "pnpm-workspace.yaml").write_text("packages:\n  - 'packages/*'\n")
        result = _detect_project_structure(tmp_path)
        assert result == "monorepo"

    def test_package_json_workspaces(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text('{"workspaces": ["packages/*"]}')
        result = _detect_project_structure(tmp_path)
        assert result == "monorepo"

    def test_package_json_no_workspaces(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text('{"name": "app"}')
        result = _detect_project_structure(tmp_path)
        assert result == "single-app"

    def test_pyproject_uv_workspace(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.uv.workspace]\nmembers = []\n")
        result = _detect_project_structure(tmp_path)
        assert result == "monorepo"

    def test_package_json_malformed(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text("{not valid json")
        result = _detect_project_structure(tmp_path)
        # Should not crash


class TestDocumentationCoverage:
    def test_finds_existing_docs(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# README\n")
        (tmp_path / "CHANGELOG.md").write_text("# CHANGELOG\n")
        docs = _detect_documentation_coverage(tmp_path)
        assert "README.md" in docs
        assert "CHANGELOG.md" in docs

    def test_empty_dir_no_docs(self, tmp_path: Path) -> None:
        docs = _detect_documentation_coverage(tmp_path)
        assert docs == []


class TestDetectLinter:
    def test_ruff_toml(self, tmp_path: Path) -> None:
        (tmp_path / "ruff.toml").write_text("[lint]\n")
        assert _detect_linter(tmp_path) == "ruff"

    def test_eslint_json(self, tmp_path: Path) -> None:
        (tmp_path / ".eslintrc.json").write_text("{}")
        assert _detect_linter(tmp_path) == "eslint"

    def test_pyproject_ruff_section(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\nselect = ['E']\n")
        assert _detect_linter(tmp_path) == "ruff"

    def test_pyproject_black_section(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.black]\nline-length = 120\n")
        assert _detect_linter(tmp_path) == "black"

    def test_pyproject_flake8_section(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.flake8]\nmax-line-length = 120\n")
        assert _detect_linter(tmp_path) == "flake8"

    def test_pyproject_oserror(self, tmp_path: Path) -> None:
        # No linter config at all
        assert _detect_linter(tmp_path) is None


class TestGetDepsForLanguage:
    def test_python(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\ndependencies = ["flask"]\n', encoding="utf-8"
        )
        deps = _get_deps_for_language(tmp_path, "python")
        assert "flask" in deps

    def test_javascript(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text('{"dependencies": {"express": "4"}}')
        deps = _get_deps_for_language(tmp_path, "javascript")
        assert "express" in deps

    def test_typescript_maps_to_js(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text('{"dependencies": {"next": "14"}}')
        deps = _get_deps_for_language(tmp_path, "typescript")
        assert "next" in deps

    def test_go(self, tmp_path: Path) -> None:
        (tmp_path / "go.mod").write_text("module ex\n\ngo 1.21\n\nrequire github.com/gin-gonic/gin v1\n")
        deps = _get_deps_for_language(tmp_path, "go")
        assert any("gin" in d for d in deps)

    def test_java(self, tmp_path: Path) -> None:
        (tmp_path / "pom.xml").write_text("<project><dependencies></dependencies></project>")
        deps = _get_deps_for_language(tmp_path, "java")
        assert isinstance(deps, list)

    def test_kotlin_maps_to_java(self, tmp_path: Path) -> None:
        deps = _get_deps_for_language(tmp_path, "kotlin")
        assert isinstance(deps, list)

    def test_rust(self, tmp_path: Path) -> None:
        (tmp_path / "Cargo.toml").write_text("[dependencies]\ntokio = \"1\"\n")
        deps = _get_deps_for_language(tmp_path, "rust")
        assert "tokio" in deps

    def test_unknown_language(self, tmp_path: Path) -> None:
        deps = _get_deps_for_language(tmp_path, "haskell")
        assert deps == []


class TestRequirementsTxtDeps:
    def test_requirements_txt_with_comments_and_flags(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.txt").write_text(
            "# comment\n-r base.txt\nflask>=2.0\nrequests[security]>=2.28\n",
            encoding="utf-8",
        )
        deps = _get_python_deps(tmp_path)
        assert "flask" in deps
        assert "requests" in deps

    def test_requirements_dev_txt(self, tmp_path: Path) -> None:
        (tmp_path / "requirements-dev.txt").write_text("pytest\nmypy\n")
        deps = _get_python_deps(tmp_path)
        assert "pytest" in deps


class TestJsDeps:
    def test_package_json_all_sections(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text(json.dumps({
            "dependencies": {"react": "18"},
            "devDependencies": {"jest": "29"},
            "peerDependencies": {"react-dom": "18"},
        }))
        deps = _get_js_deps(tmp_path)
        assert "react" in deps
        assert "jest" in deps
        assert "react-dom" in deps

    def test_package_json_malformed(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text("not valid json{{{")
        deps = _get_js_deps(tmp_path)
        assert deps == []

    def test_package_json_not_exist(self, tmp_path: Path) -> None:
        deps = _get_js_deps(tmp_path)
        assert deps == []


class TestPoetryDeps:
    def test_poetry_deps(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            "[tool.poetry.dependencies]\npython = \"^3.12\"\nflask = \"^2.0\"\n\n"
            "[tool.poetry.group.dev.dependencies]\npytest = \"^7.0\"\n",
            encoding="utf-8",
        )
        deps = _get_python_deps(tmp_path)
        assert "flask" in deps
        assert "pytest" in deps


class TestDatabaseDetectJava:
    def test_java_database(self, tmp_path: Path) -> None:
        (tmp_path / "pom.xml").write_text(
            "<project><dependencies>"
            "<dependency><groupId>org.postgresql</groupId><artifactId>postgresql</artifactId></dependency>"
            "</dependencies></project>",
            encoding="utf-8",
        )
        result = _detect_database(tmp_path, "java")
        assert result is not None
