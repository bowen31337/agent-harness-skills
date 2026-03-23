"""
harness_skills/generators/codebase_analyzer.py
===============================================
Detect primary language(s) and framework(s) from package files.

Scans the given root directory for well-known package manager files
(package.json, pyproject.toml, Cargo.toml, go.mod, Gemfile, pom.xml,
build.gradle, composer.json, *.csproj, pubspec.yaml, mix.exs, etc.) and
returns a populated :class:`~harness_skills.models.create.DetectedStack`.

Public API
----------
    detect_stack(root_dir)   ->  DetectedStack

Usage::

    from harness_skills.generators.codebase_analyzer import detect_stack

    stack = detect_stack(".")
    print(stack.primary_language)   # "python"
    print(stack.framework)           # "fastapi"
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from harness_skills.models.create import DetectedStack

# ---------------------------------------------------------------------------
# Language detection: package files checked in priority order
# First match becomes the primary language; subsequent new languages are secondary.
# ---------------------------------------------------------------------------

#: ``(filename_or_glob, language)`` pairs inspected at the project root.
_PACKAGE_FILE_PRIORITY: list[tuple[str, str]] = [
    ("pyproject.toml", "python"),
    ("setup.py", "python"),
    ("setup.cfg", "python"),
    ("requirements.txt", "python"),
    ("Pipfile", "python"),
    ("package.json", "javascript"),
    ("Cargo.toml", "rust"),
    ("go.mod", "go"),
    ("Gemfile", "ruby"),
    ("pom.xml", "java"),
    ("build.gradle", "java"),
    ("build.gradle.kts", "kotlin"),
    ("composer.json", "php"),
    ("pubspec.yaml", "dart"),
    ("mix.exs", "elixir"),
    ("*.csproj", "csharp"),
    ("*.fsproj", "fsharp"),
    ("stack.yaml", "haskell"),
    ("*.cabal", "haskell"),
]

# ---------------------------------------------------------------------------
# Framework detection: per language, ordered ``(dep_substring, framework_name)``
# ---------------------------------------------------------------------------

_PYTHON_FRAMEWORKS: list[tuple[str, str]] = [
    ("fastapi", "fastapi"),
    ("flask", "flask"),
    ("django", "django"),
    ("starlette", "starlette"),
    ("tornado", "tornado"),
    ("aiohttp", "aiohttp"),
    ("sanic", "sanic"),
    ("litestar", "litestar"),
    ("pyramid", "pyramid"),
    ("bottle", "bottle"),
]

_JS_FRAMEWORKS: list[tuple[str, str]] = [
    ("@angular/core", "angular"),
    ("@nestjs/core", "nestjs"),
    ("next", "next.js"),
    ("nuxt", "nuxt"),
    ("remix", "remix"),
    ("astro", "astro"),
    ("svelte", "svelte"),
    ("solid-js", "solid"),
    ("express", "express"),
    ("fastify", "fastify"),
    ("koa", "koa"),
    ("hapi", "hapi"),
    ("react", "react"),
    ("vue", "vue"),
]

_RUST_FRAMEWORKS: list[tuple[str, str]] = [
    ("actix-web", "actix"),
    ("axum", "axum"),
    ("rocket", "rocket"),
    ("warp", "warp"),
    ("poem", "poem"),
    ("salvo", "salvo"),
]

_GO_FRAMEWORKS: list[tuple[str, str]] = [
    ("github.com/gin-gonic/gin", "gin"),
    ("github.com/labstack/echo", "echo"),
    ("github.com/gofiber/fiber", "fiber"),
    ("github.com/go-chi/chi", "chi"),
    ("github.com/gorilla/mux", "gorilla/mux"),
    ("github.com/beego/beego", "beego"),
    ("revel.github.com", "revel"),
]

_JAVA_FRAMEWORKS: list[tuple[str, str]] = [
    ("spring-boot", "spring boot"),
    ("spring-webmvc", "spring mvc"),
    ("quarkus", "quarkus"),
    ("micronaut", "micronaut"),
    ("vertx", "vert.x"),
    ("grails", "grails"),
    ("helidon", "helidon"),
]

_RUBY_FRAMEWORKS: list[tuple[str, str]] = [
    ("rails", "rails"),
    ("sinatra", "sinatra"),
    ("hanami", "hanami"),
    ("roda", "roda"),
    ("grape", "grape"),
]

# ---------------------------------------------------------------------------
# Test framework detection
# ---------------------------------------------------------------------------

_PYTHON_TEST_FRAMEWORKS: list[tuple[str, str]] = [
    ("pytest", "pytest"),
    ("nose2", "nose2"),
    ("nose", "nose"),
]

_JS_TEST_FRAMEWORKS: list[tuple[str, str]] = [
    ("@playwright/test", "playwright"),
    ("vitest", "vitest"),
    ("jest", "jest"),
    ("cypress", "cypress"),
    ("mocha", "mocha"),
    ("jasmine", "jasmine"),
]

_GO_TEST_FRAMEWORKS: list[tuple[str, str]] = [
    ("github.com/stretchr/testify", "testify"),
    ("github.com/onsi/ginkgo", "ginkgo"),
]

_JAVA_TEST_FRAMEWORKS: list[tuple[str, str]] = [
    ("junit", "junit"),
    ("testng", "testng"),
]

_RUBY_TEST_FRAMEWORKS: list[tuple[str, str]] = [
    ("rspec", "rspec"),
    ("minitest", "minitest"),
    ("cucumber", "cucumber"),
]

_RUST_TEST_FRAMEWORKS: list[tuple[str, str]] = [
    ("proptest", "proptest"),
    ("quickcheck", "quickcheck"),
]

# ---------------------------------------------------------------------------
# CI platform detection: ``(path_under_root, platform_name)``
# Paths that are directories are matched with ``is_dir()``; files with ``exists()``.
# ---------------------------------------------------------------------------

_CI_PLATFORM_INDICATORS: list[tuple[str, str]] = [
    (".github/workflows", "github-actions"),
    (".gitlab-ci.yml", "gitlab-ci"),
    (".circleci/config.yml", "circleci"),
    ("Jenkinsfile", "jenkins"),
    (".travis.yml", "travis-ci"),
    ("azure-pipelines.yml", "azure-pipelines"),
    (".buildkite/pipeline.yml", "buildkite"),
    ("bitbucket-pipelines.yml", "bitbucket-pipelines"),
    ("cloudbuild.yaml", "cloud-build"),
    ("cloudbuild.yml", "cloud-build"),
    (".drone.yml", "drone"),
    ("appveyor.yml", "appveyor"),
]

# ---------------------------------------------------------------------------
# Database dependency detection: per language
# ---------------------------------------------------------------------------

_DATABASE_DEPS: dict[str, list[tuple[str, str]]] = {
    "python": [
        ("psycopg2", "postgresql"),
        ("psycopg", "postgresql"),
        ("asyncpg", "postgresql"),
        ("pymongo", "mongodb"),
        ("motor", "mongodb"),
        ("redis", "redis"),
        ("aioredis", "redis"),
        ("pymysql", "mysql"),
        ("aiomysql", "mysql"),
        ("aiosqlite", "sqlite"),
        ("elasticsearch", "elasticsearch"),
        ("cassandra-driver", "cassandra"),
        ("pymssql", "mssql"),
        ("sqlalchemy", "sqlalchemy"),
    ],
    "javascript": [
        ("@prisma/client", "prisma"),
        ("prisma", "prisma"),
        ("pg", "postgresql"),
        ("postgres", "postgresql"),
        ("mysql2", "mysql"),
        ("mysql", "mysql"),
        ("mongodb", "mongodb"),
        ("mongoose", "mongodb"),
        ("ioredis", "redis"),
        ("redis", "redis"),
        ("better-sqlite3", "sqlite"),
        ("sqlite3", "sqlite"),
        ("typeorm", "typeorm"),
        ("sequelize", "sequelize"),
        ("knex", "knex"),
        ("elasticsearch", "elasticsearch"),
    ],
    "go": [
        ("github.com/jackc/pgx", "postgresql"),
        ("github.com/lib/pq", "postgresql"),
        ("gorm.io/driver/postgres", "postgresql"),
        ("go.mongodb.org/mongo-driver", "mongodb"),
        ("github.com/redis/go-redis", "redis"),
        ("github.com/go-redis/redis", "redis"),
        ("gorm.io/driver/mysql", "mysql"),
        ("github.com/go-sql-driver/mysql", "mysql"),
        ("github.com/mattn/go-sqlite3", "sqlite"),
        ("gorm.io/gorm", "gorm"),
    ],
    "java": [
        ("postgresql", "postgresql"),
        ("mysql-connector", "mysql"),
        ("mongodb", "mongodb"),
        ("spring-data-redis", "redis"),
        ("h2", "h2"),
        ("sqlite-jdbc", "sqlite"),
        ("mariadb-java-client", "mariadb"),
    ],
    "rust": [
        ("tokio-postgres", "postgresql"),
        ("sqlx", "sqlx"),
        ("diesel", "diesel"),
        ("rusqlite", "sqlite"),
        ("mongodb", "mongodb"),
        ("redis", "redis"),
    ],
}

# ---------------------------------------------------------------------------
# Monorepo indicators
# ---------------------------------------------------------------------------

_MONOREPO_FILES = [
    "lerna.json",
    "pnpm-workspace.yaml",
    "nx.json",
    "turbo.json",
    "rush.json",
    "workspace.json",
]

_MONOREPO_DIRS = [
    "packages",
    "apps",
    "services",
]

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_stack(root_dir: str | Path = ".") -> DetectedStack:
    """Detect the technology stack from package manager files.

    Scans *root_dir* (non-recursively at the top level) for well-known package
    manager and configuration files, and returns a :class:`DetectedStack`
    describing the primary language, frameworks, test tooling, CI platform, and
    database dependencies found.

    Parameters
    ----------
    root_dir:
        Root directory to scan. Defaults to the current working directory.

    Returns
    -------
    DetectedStack
        Populated stack descriptor. ``primary_language`` is always set (falls
        back to ``"unknown"`` if no recognisable package files are found).
    """
    root = Path(root_dir).resolve()

    primary_language, secondary_languages = _detect_languages(root)
    framework = _detect_framework(root, primary_language)
    test_framework = _detect_test_framework(root, primary_language)
    ci_platform = _detect_ci_platform(root)
    database = _detect_database(root, primary_language)
    project_structure = _detect_project_structure(root)

    return DetectedStack(
        primary_language=primary_language,
        secondary_languages=secondary_languages,
        framework=framework,
        project_structure=project_structure,
        test_framework=test_framework,
        ci_platform=ci_platform,
        database=database,
        api_style=None,
    )


# ---------------------------------------------------------------------------
# Language detection helpers
# ---------------------------------------------------------------------------


def _detect_languages(root: Path) -> tuple[str, list[str]]:
    """Return ``(primary_language, secondary_languages)`` by scanning package files."""
    found: list[str] = []

    for pattern, lang in _PACKAGE_FILE_PRIORITY:
        if "*" in pattern:
            if list(root.glob(pattern)):
                if lang not in found:
                    found.append(lang)
        elif (root / pattern).exists():
            if lang not in found:
                found.append(lang)

    # Upgrade javascript → typescript when tsconfig.json or typescript dep is present
    if "javascript" in found and _is_typescript_project(root):
        idx = found.index("javascript")
        found[idx] = "typescript"

    if not found:
        return "unknown", []

    primary = found[0]
    secondary = [lang for lang in found[1:] if lang != primary]
    return primary, secondary


def _is_typescript_project(root: Path) -> bool:
    """Return ``True`` when the JS project also uses TypeScript."""
    if (root / "tsconfig.json").exists():
        return True
    return _has_js_dep(root, "typescript")


# ---------------------------------------------------------------------------
# Dependency extraction helpers (one per package manager)
# ---------------------------------------------------------------------------


def _get_python_deps(root: Path) -> list[str]:
    """Return normalised Python dependency names from pyproject.toml / requirements*.txt."""
    deps: list[str] = []

    # pyproject.toml — PEP 621 and Poetry layouts
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            # PEP 621
            deps.extend(data.get("project", {}).get("dependencies", []))
            for group_deps in (
                data.get("project", {}).get("optional-dependencies", {}).values()
            ):
                deps.extend(group_deps)
            # Poetry
            poetry = data.get("tool", {}).get("poetry", {})
            deps.extend(poetry.get("dependencies", {}).keys())
            for group in poetry.get("group", {}).values():
                deps.extend(group.get("dependencies", {}).keys())
        except Exception:  # noqa: BLE001
            pass

    # setup.cfg
    setup_cfg = root / "setup.cfg"
    if setup_cfg.exists():
        try:
            import configparser

            cfg = configparser.ConfigParser()
            cfg.read_string(setup_cfg.read_text(encoding="utf-8"))
            raw = cfg.get("options", "install_requires", fallback="")
            for line in raw.splitlines():
                dep = re.split(r"[>=<!;\[#\s]", line.strip())[0].strip()
                if dep:
                    deps.append(dep)
        except Exception:  # noqa: BLE001
            pass

    # requirements*.txt
    for req_file in root.glob("requirements*.txt"):
        try:
            for line in req_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith(("#", "-")):
                    continue
                dep = re.split(r"[>=<!;\[#\s]", line)[0].strip()
                if dep:
                    deps.append(dep)
        except OSError:
            pass

    return [d.lower() for d in deps]


def _get_js_deps(root: Path) -> list[str]:
    """Return dependency names from ``package.json``."""
    pkg_json = root / "package.json"
    if not pkg_json.exists():
        return []
    try:
        data: dict[str, object] = json.loads(pkg_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    all_deps: dict[str, object] = {
        **_as_dict(data.get("dependencies")),
        **_as_dict(data.get("devDependencies")),
        **_as_dict(data.get("peerDependencies")),
    }
    return list(all_deps.keys())


def _has_js_dep(root: Path, name: str) -> bool:
    """Return ``True`` when *name* appears in any ``package.json`` dependency section."""
    return name in _get_js_deps(root)


def _get_go_deps(root: Path) -> list[str]:
    """Return module paths from ``go.mod``."""
    go_mod = root / "go.mod"
    if not go_mod.exists():
        return []
    deps: list[str] = []
    try:
        in_require = False
        for line in go_mod.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped == "require (":
                in_require = True
                continue
            if in_require and stripped == ")":
                in_require = False
                continue
            if in_require or stripped.startswith("require "):
                parts = stripped.split()
                if parts:
                    candidate = parts[0] if parts[0] != "require" else (parts[1] if len(parts) > 1 else "")
                    if candidate and not candidate.startswith("//"):
                        deps.append(candidate)
    except OSError:
        pass
    return deps


def _get_java_deps(root: Path) -> list[str]:
    """Return artifact and group IDs from ``pom.xml`` or ``build.gradle``."""
    deps: list[str] = []

    pom = root / "pom.xml"
    if pom.exists():
        try:
            text = pom.read_text(encoding="utf-8")
            deps.extend(re.findall(r"<artifactId>\s*([^<]+)\s*</artifactId>", text))
            deps.extend(re.findall(r"<groupId>\s*([^<]+)\s*</groupId>", text))
        except OSError:
            pass

    for gradle_name in ("build.gradle", "build.gradle.kts"):
        gradle = root / gradle_name
        if gradle.exists():
            try:
                text = gradle.read_text(encoding="utf-8")
                for m in re.finditer(
                    r"""['"]([\w.\-]+:[\w.\-]+)""", text
                ):
                    for part in m.group(1).split(":"):
                        deps.append(part)
            except OSError:
                pass

    return [d.lower() for d in deps]


def _get_ruby_deps(root: Path) -> list[str]:
    """Return gem names from ``Gemfile``."""
    gemfile = root / "Gemfile"
    if not gemfile.exists():
        return []
    deps: list[str] = []
    try:
        for line in gemfile.read_text(encoding="utf-8").splitlines():
            m = re.match(r"""\s*gem\s+['"]([^'"]+)['"]""", line)
            if m:
                deps.append(m.group(1).lower())
    except OSError:
        pass
    return deps


def _get_rust_deps(root: Path) -> list[str]:
    """Return crate names from ``Cargo.toml``."""
    cargo = root / "Cargo.toml"
    if not cargo.exists():
        return []
    deps: list[str] = []
    try:
        data = tomllib.loads(cargo.read_text(encoding="utf-8"))
        for section in ("dependencies", "dev-dependencies", "build-dependencies"):
            deps.extend(data.get(section, {}).keys())
    except Exception:  # noqa: BLE001
        # Fallback: simple regex for ``name = ...`` lines
        try:
            text = cargo.read_text(encoding="utf-8")
            for m in re.finditer(r"^([a-zA-Z][a-zA-Z0-9_-]*)\s*=", text, re.MULTILINE):
                deps.append(m.group(1))
        except OSError:
            pass
    return [d.lower() for d in deps]


# ---------------------------------------------------------------------------
# Framework detection
# ---------------------------------------------------------------------------


def _detect_framework(root: Path, primary_language: str) -> str | None:
    """Return the primary web/application framework name, or ``None``."""
    if primary_language == "python":
        return _first_match(_get_python_deps(root), _PYTHON_FRAMEWORKS)
    if primary_language in ("javascript", "typescript"):
        return _first_exact_match(_get_js_deps(root), _JS_FRAMEWORKS)
    if primary_language == "go":
        return _first_match(_get_go_deps(root), _GO_FRAMEWORKS)
    if primary_language in ("java", "kotlin"):
        return _first_match(_get_java_deps(root), _JAVA_FRAMEWORKS)
    if primary_language == "ruby":
        return _first_exact_match(_get_ruby_deps(root), _RUBY_FRAMEWORKS)
    if primary_language == "rust":
        return _first_exact_match(_get_rust_deps(root), _RUST_FRAMEWORKS)
    return None


# ---------------------------------------------------------------------------
# Test framework detection
# ---------------------------------------------------------------------------


def _detect_test_framework(root: Path, primary_language: str) -> str | None:
    """Return the primary test framework name, or ``None``."""
    if primary_language == "python":
        result = _first_match(_get_python_deps(root), _PYTHON_TEST_FRAMEWORKS)
        if result:
            return result
        # Detect pytest via its config section even without a dep entry
        pyproject = root / "pyproject.toml"
        if pyproject.exists():
            try:
                if "[tool.pytest" in pyproject.read_text(encoding="utf-8"):
                    return "pytest"
            except OSError:
                pass
        return None

    if primary_language in ("javascript", "typescript"):
        return _first_match(_get_js_deps(root), _JS_TEST_FRAMEWORKS)

    if primary_language == "go":
        result = _first_match(_get_go_deps(root), _GO_TEST_FRAMEWORKS)
        # Go always has a built-in test runner
        return result or "testing"

    if primary_language in ("java", "kotlin"):
        return _first_match(_get_java_deps(root), _JAVA_TEST_FRAMEWORKS)

    if primary_language == "ruby":
        return _first_exact_match(_get_ruby_deps(root), _RUBY_TEST_FRAMEWORKS)

    if primary_language == "rust":
        result = _first_exact_match(_get_rust_deps(root), _RUST_TEST_FRAMEWORKS)
        # Rust always has a built-in test harness
        return result or "built-in"

    return None


# ---------------------------------------------------------------------------
# CI platform detection
# ---------------------------------------------------------------------------


def _detect_ci_platform(root: Path) -> str | None:
    """Return the CI platform name by scanning CI configuration files."""
    for path_str, platform in _CI_PLATFORM_INDICATORS:
        candidate = root / path_str
        if candidate.is_dir() and any(candidate.iterdir()):
            return platform
        if candidate.is_file():
            return platform
    return None


# ---------------------------------------------------------------------------
# Database detection
# ---------------------------------------------------------------------------


def _detect_database(root: Path, primary_language: str) -> str | None:
    """Return the primary database/ORM name, or ``None``."""
    lang_key = primary_language
    if lang_key == "typescript":
        lang_key = "javascript"
    if lang_key == "kotlin":
        lang_key = "java"

    if lang_key not in _DATABASE_DEPS:
        return None

    if lang_key == "python":
        deps = _get_python_deps(root)
    elif lang_key == "javascript":
        deps = _get_js_deps(root)
    elif lang_key == "go":
        deps = _get_go_deps(root)
    elif lang_key == "java":
        deps = _get_java_deps(root)
    elif lang_key == "rust":
        deps = _get_rust_deps(root)
    else:
        return None

    return _first_match(deps, _DATABASE_DEPS[lang_key])


# ---------------------------------------------------------------------------
# Project structure detection
# ---------------------------------------------------------------------------


def _detect_project_structure(root: Path) -> str:
    """Return ``"monorepo"`` or ``"single-app"``."""
    for fname in _MONOREPO_FILES:
        if (root / fname).exists():
            return "monorepo"

    for dname in _MONOREPO_DIRS:
        candidate = root / dname
        if candidate.is_dir() and any(candidate.iterdir()):
            return "monorepo"

    # package.json workspaces field
    pkg_json = root / "package.json"
    if pkg_json.exists():
        try:
            data: dict[str, object] = json.loads(pkg_json.read_text(encoding="utf-8"))
            if "workspaces" in data:
                return "monorepo"
        except (json.JSONDecodeError, OSError):
            pass

    # pyproject.toml workspace indicators (uv or PEP 723 workspace)
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        try:
            text = pyproject.read_text(encoding="utf-8")
            if "tool.uv.workspace" in text or "[workspace]" in text:
                return "monorepo"
        except OSError:
            pass

    return "single-app"


# ---------------------------------------------------------------------------
# Shared matching utilities
# ---------------------------------------------------------------------------


def _first_match(deps: list[str], table: list[tuple[str, str]]) -> str | None:
    """Return the first framework name whose pattern is a substring of any dep."""
    for pattern, name in table:
        if any(pattern in dep for dep in deps):
            return name
    return None


def _first_exact_match(deps: list[str], table: list[tuple[str, str]]) -> str | None:
    """Return the first framework name that exactly matches a dep entry."""
    dep_set = set(deps)
    for dep_name, name in table:
        if dep_name in dep_set:
            return name
    return None


def _as_dict(value: object) -> dict[str, object]:
    """Safely coerce a value to ``dict``; return empty dict for non-dict values."""
    return value if isinstance(value, dict) else {}
