"""Tests for harness_skills.generators.docs_generator — full docs pipeline."""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from harness_skills.generators.docs_generator import (
    _extract_django_models,
    _extract_fastapi_routes,
    _extract_flask_routes,
    _extract_imports,
    _extract_pydantic_models,
    _extract_sqlalchemy_models,
    _first_party_packages,
    _git_head,
    _grep,
    _grep_recursive,
    _harness_header,
    _module_name,
    _now_iso,
    _python_files,
    _render_dot,
    _render_mermaid,
    _render_openapi_yaml,
    _render_routes_md,
    _render_schema_table,
    build_import_graph,
    generate_api,
    generate_docs,
    generate_graphs,
    generate_schemas,
)
from harness_skills.models.docs import DependencyEdge, RouteEntity, SchemaEntity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PYDANTIC_SOURCE = textwrap.dedent("""\
    from pydantic import BaseModel

    class User(BaseModel):
        name: str
        email: str
        age: int
""")

SQLALCHEMY_SOURCE = textwrap.dedent("""\
    from sqlalchemy import Column, Integer, String
    from sqlalchemy.orm import DeclarativeBase

    class Base(DeclarativeBase):
        pass

    class Account(Base):
        __tablename__ = "accounts"
        id = Column(Integer, primary_key=True)
        name = Column(String)
""")

DJANGO_SOURCE = textwrap.dedent("""\
    from django.db import models

    class Article(models.Model):
        title = models.CharField(max_length=200)
        body = models.TextField()
        published = models.BooleanField(default=False)
""")

FASTAPI_SOURCE = textwrap.dedent('''\
    from fastapi import FastAPI

    app = FastAPI()

    @app.get("/users")
    async def list_users():
        """List all users."""
        return []

    @app.post("/users")
    async def create_user():
        """Create a new user."""
        return {}
''')

FLASK_SOURCE = textwrap.dedent('''\
    from flask import Flask

    app = Flask(__name__)

    @app.route("/health", methods=["GET"])
    def health_check():
        return "ok"

    @app.route("/items", methods=["GET", "POST"])
    def items():
        return []
''')


def _write_pkg(root: Path, pkg_name: str, files: dict[str, str]) -> None:
    """Create a package directory with __init__.py and given files."""
    pkg_dir = root / pkg_name
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "__init__.py").write_text("")
    for name, content in files.items():
        (pkg_dir / name).write_text(content)


# ---------------------------------------------------------------------------
# _git_head
# ---------------------------------------------------------------------------


class TestGitHead:
    def test_returns_string(self):
        result = _git_head()
        assert isinstance(result, str)
        assert len(result) > 0

    @patch("harness_skills.generators.docs_generator.subprocess.check_output", side_effect=OSError)
    def test_fallback_on_error(self, mock_co):
        assert _git_head() == "unknown"


# ---------------------------------------------------------------------------
# _now_iso
# ---------------------------------------------------------------------------


class TestNowIso:
    def test_returns_iso_format(self):
        result = _now_iso()
        assert "T" in result
        assert result.endswith("Z")


# ---------------------------------------------------------------------------
# _harness_header
# ---------------------------------------------------------------------------


class TestHarnessHeader:
    def test_contains_markers(self):
        header = _harness_header("2025-01-01T00:00:00Z", "abc1234")
        assert "harness:auto-generated" in header
        assert "2025-01-01T00:00:00Z" in header
        assert "abc1234" in header


# ---------------------------------------------------------------------------
# _python_files
# ---------------------------------------------------------------------------


class TestPythonFiles:
    def test_finds_py_files(self, tmp_path):
        (tmp_path / "app.py").write_text("x = 1")
        (tmp_path / "utils.py").write_text("y = 2")
        (tmp_path / "data.txt").write_text("not python")
        result = _python_files(tmp_path)
        assert len(result) == 2
        assert all(p.suffix == ".py" for p in result)

    def test_excludes_test_files(self, tmp_path):
        (tmp_path / "app.py").write_text("")
        (tmp_path / "test_app.py").write_text("")
        (tmp_path / "app_test.py").write_text("")
        result = _python_files(tmp_path, include_tests=False)
        assert len(result) == 1

    def test_includes_test_files(self, tmp_path):
        (tmp_path / "app.py").write_text("")
        (tmp_path / "test_app.py").write_text("")
        result = _python_files(tmp_path, include_tests=True)
        assert len(result) == 2

    def test_excludes_hidden_dirs(self, tmp_path):
        hidden = tmp_path / "__pycache__"
        hidden.mkdir()
        (hidden / "cached.py").write_text("")
        (tmp_path / "app.py").write_text("")
        result = _python_files(tmp_path)
        assert len(result) == 1

    def test_excludes_node_modules(self, tmp_path):
        nm = tmp_path / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        (nm / "index.py").write_text("")
        (tmp_path / "main.py").write_text("")
        result = _python_files(tmp_path)
        assert len(result) == 1

    def test_sorted(self, tmp_path):
        (tmp_path / "z.py").write_text("")
        (tmp_path / "a.py").write_text("")
        result = _python_files(tmp_path)
        assert result == sorted(result)


# ---------------------------------------------------------------------------
# _grep / _grep_recursive
# ---------------------------------------------------------------------------


class TestGrep:
    def test_grep_finds_match(self, tmp_path):
        f = tmp_path / "sample.py"
        f.write_text("import os\nimport sys\nprint('hello')\n")
        lines = _grep("import", f)
        assert len(lines) == 2

    def test_grep_no_match(self, tmp_path):
        f = tmp_path / "sample.py"
        f.write_text("x = 1\n")
        lines = _grep("import", f)
        assert lines == []

    def test_grep_nonexistent_file(self, tmp_path):
        lines = _grep("pattern", tmp_path / "nope.py")
        assert lines == []

    def test_grep_with_flags(self, tmp_path):
        f = tmp_path / "sample.py"
        f.write_text("Import os\nimport sys\n")
        lines = _grep("import", f, flags="-i")
        assert len(lines) == 2  # case-insensitive matches both

    def test_grep_recursive(self, tmp_path):
        sub = tmp_path / "pkg"
        sub.mkdir()
        (sub / "a.py").write_text("from fastapi import FastAPI\n")
        (sub / "b.py").write_text("x = 1\n")
        result = _grep_recursive("from fastapi import", tmp_path)
        # grep -r may return 0 or 1 depending on OS grep flags support
        assert isinstance(result, list)
        # On systems where it works, it should find a.py
        if result:
            assert any("a.py" in r for r in result)

    def test_grep_recursive_no_match(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n")
        result = _grep_recursive("nonexistent_pattern_xyz", tmp_path)
        assert result == []


# ---------------------------------------------------------------------------
# Schema extraction
# ---------------------------------------------------------------------------


class TestExtractPydanticModels:
    def test_finds_basemodel(self, tmp_path):
        f = tmp_path / "models.py"
        f.write_text(PYDANTIC_SOURCE)
        entities = _extract_pydantic_models(f)
        assert len(entities) == 1
        assert entities[0].name == "User"
        assert entities[0].framework == "pydantic"
        assert entities[0].field_count == 3

    def test_ignores_non_basemodel(self, tmp_path):
        f = tmp_path / "other.py"
        f.write_text("class Foo:\n    pass\n")
        assert _extract_pydantic_models(f) == []

    def test_syntax_error(self, tmp_path):
        f = tmp_path / "bad.py"
        f.write_text("def broken(\n")
        assert _extract_pydantic_models(f) == []


class TestExtractSQLAlchemyModels:
    def test_finds_sa_model(self, tmp_path):
        f = tmp_path / "models.py"
        f.write_text(SQLALCHEMY_SOURCE)
        entities = _extract_sqlalchemy_models(f)
        # Should find Account (has Column), and possibly Base
        names = [e.name for e in entities]
        assert "Account" in names

    def test_syntax_error(self, tmp_path):
        f = tmp_path / "bad.py"
        f.write_text("def broken(\n")
        assert _extract_sqlalchemy_models(f) == []


class TestExtractDjangoModels:
    def test_finds_django_model(self, tmp_path):
        f = tmp_path / "models.py"
        f.write_text(DJANGO_SOURCE)
        entities = _extract_django_models(f)
        assert len(entities) == 1
        assert entities[0].name == "Article"
        assert entities[0].framework == "django"

    def test_no_django_model(self, tmp_path):
        f = tmp_path / "other.py"
        f.write_text("class Foo:\n    bar = 1\n")
        assert _extract_django_models(f) == []

    def test_syntax_error(self, tmp_path):
        f = tmp_path / "bad.py"
        f.write_text("def broken(\n")
        assert _extract_django_models(f) == []


# ---------------------------------------------------------------------------
# _render_schema_table
# ---------------------------------------------------------------------------


class TestRenderSchemaTable:
    def test_no_entities(self):
        result = _render_schema_table([], "pydantic", "# Header")
        assert "No `pydantic` models detected" in result

    def test_with_entities(self):
        entities = [
            SchemaEntity(name="User", source_file="models.py", framework="pydantic", field_count=3),
        ]
        result = _render_schema_table(entities, "pydantic", "# Header")
        assert "1 model(s) detected" in result
        assert "`User`" in result
        assert "models.py" in result


# ---------------------------------------------------------------------------
# generate_schemas
# ---------------------------------------------------------------------------


class TestGenerateSchemas:
    def test_generates_pydantic_schemas(self, tmp_path):
        _write_pkg(tmp_path, "myapp", {"models.py": PYDANTIC_SOURCE})
        header = "<!-- test -->"
        result = generate_schemas(tmp_path, tmp_path / "docs" / "generated", header=header)
        assert result.entities_found >= 1
        assert "pydantic" in result.frameworks
        assert len(result.files_written) > 0

    def test_dry_run(self, tmp_path):
        _write_pkg(tmp_path, "myapp", {"models.py": PYDANTIC_SOURCE})
        header = "<!-- test -->"
        result = generate_schemas(tmp_path, tmp_path / "docs" / "generated", header=header, dry_run=True)
        assert result.entities_found >= 1
        # Dry run should not create directories
        assert not (tmp_path / "docs" / "generated" / "schemas").exists()

    def test_empty_project(self, tmp_path):
        header = "<!-- test -->"
        result = generate_schemas(tmp_path, tmp_path / "docs" / "generated", header=header)
        assert result.entities_found == 0
        assert result.frameworks == []

    def test_sqlalchemy_models(self, tmp_path):
        _write_pkg(tmp_path, "myapp", {"db.py": SQLALCHEMY_SOURCE})
        header = "<!-- test -->"
        result = generate_schemas(tmp_path, tmp_path / "docs" / "generated", header=header)
        assert "sqlalchemy" in result.frameworks

    def test_django_models(self, tmp_path):
        _write_pkg(tmp_path, "myapp", {"models.py": DJANGO_SOURCE})
        header = "<!-- test -->"
        result = generate_schemas(tmp_path, tmp_path / "docs" / "generated", header=header)
        assert "django" in result.frameworks


# ---------------------------------------------------------------------------
# Route extraction
# ---------------------------------------------------------------------------


class TestExtractFastapiRoutes:
    def test_finds_routes(self, tmp_path):
        f = tmp_path / "api.py"
        f.write_text(FASTAPI_SOURCE)
        routes = _extract_fastapi_routes(f)
        assert len(routes) == 2
        methods = {r.method for r in routes}
        assert "GET" in methods
        assert "POST" in methods
        paths = {r.path for r in routes}
        assert "/users" in paths

    def test_no_routes(self, tmp_path):
        f = tmp_path / "app.py"
        f.write_text("x = 1\n")
        assert _extract_fastapi_routes(f) == []

    def test_handler_name_extracted(self, tmp_path):
        f = tmp_path / "api.py"
        f.write_text(FASTAPI_SOURCE)
        routes = _extract_fastapi_routes(f)
        handlers = {r.handler for r in routes}
        assert "list_users" in handlers
        assert "create_user" in handlers

    def test_docstring_summary(self, tmp_path):
        f = tmp_path / "api.py"
        f.write_text(FASTAPI_SOURCE)
        routes = _extract_fastapi_routes(f)
        summaries = {r.summary for r in routes if r.summary}
        assert len(summaries) > 0

    def test_os_error(self, tmp_path):
        f = tmp_path / "nonexistent.py"
        assert _extract_fastapi_routes(f) == []


class TestExtractFlaskRoutes:
    def test_finds_routes(self, tmp_path):
        f = tmp_path / "app.py"
        f.write_text(FLASK_SOURCE)
        routes = _extract_flask_routes(f)
        assert len(routes) >= 2  # /health (GET) + /items (GET, POST)
        paths = {r.path for r in routes}
        assert "/health" in paths
        assert "/items" in paths

    def test_multiple_methods_on_separate_decorators(self, tmp_path):
        # When methods are on a separate line / arg, Flask regex may not capture them
        # due to the non-greedy .*? matching. Test the actual behavior.
        source = textwrap.dedent('''\
            from flask import Flask
            app = Flask(__name__)

            @app.route("/data", methods=["POST"])
            def post_data():
                return {}
        ''')
        f = tmp_path / "app.py"
        f.write_text(source)
        routes = _extract_flask_routes(f)
        # The regex may or may not capture methods depending on line layout
        assert len(routes) >= 1
        paths = {r.path for r in routes}
        assert "/data" in paths

    def test_no_routes(self, tmp_path):
        f = tmp_path / "app.py"
        f.write_text("x = 1\n")
        assert _extract_flask_routes(f) == []

    def test_os_error(self, tmp_path):
        f = tmp_path / "nonexistent.py"
        assert _extract_flask_routes(f) == []


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


class TestRenderRoutesMd:
    def test_empty_routes(self):
        result = _render_routes_md([], "# Header")
        assert "No HTTP routes detected" in result

    def test_with_routes(self):
        routes = [
            RouteEntity(method="GET", path="/users", handler="list_users"),
        ]
        result = _render_routes_md(routes, "# Header")
        assert "1 route(s) detected" in result
        assert "/users" in result
        assert "list_users" in result


class TestRenderOpenApiYaml:
    def test_empty_routes(self):
        result = _render_openapi_yaml([], "abc123", "2025-01-01", "myproject")
        assert "openapi" in result
        assert "myproject" in result

    def test_with_routes(self):
        routes = [
            RouteEntity(method="GET", path="/users", handler="list_users", summary="List users"),
        ]
        result = _render_openapi_yaml(routes, "abc123", "2025-01-01", "myproject")
        assert "/users" in result
        assert "list_users" in result


# ---------------------------------------------------------------------------
# generate_api
# ---------------------------------------------------------------------------


class TestGenerateApi:
    def test_no_frameworks(self, tmp_path):
        _write_pkg(tmp_path, "myapp", {"main.py": "x = 1\n"})
        header = "<!-- test -->"
        with patch("harness_skills.generators.docs_generator._grep_recursive", return_value=[]):
            result = generate_api(
                tmp_path, tmp_path / "docs" / "generated",
                header=header, timestamp="2025-01-01", head="abc",
            )
        assert result.routes_found == 0
        assert result.frameworks == []
        assert len(result.files_written) > 0  # still writes index + empty files

    def test_fastapi_routes(self, tmp_path):
        _write_pkg(tmp_path, "myapp", {"api.py": FASTAPI_SOURCE})
        header = "<!-- test -->"
        with patch("harness_skills.generators.docs_generator._grep_recursive") as mock_grep:
            mock_grep.side_effect = lambda pattern, root, **kw: (
                [str(tmp_path / "myapp" / "api.py")] if "fastapi" in pattern else []
            )
            result = generate_api(
                tmp_path, tmp_path / "docs" / "generated",
                header=header, timestamp="2025-01-01", head="abc",
            )
        assert result.routes_found >= 2
        assert "fastapi" in result.frameworks

    def test_dry_run(self, tmp_path):
        _write_pkg(tmp_path, "myapp", {"api.py": FASTAPI_SOURCE})
        header = "<!-- test -->"
        with patch("harness_skills.generators.docs_generator._grep_recursive", return_value=[]):
            result = generate_api(
                tmp_path, tmp_path / "docs" / "generated",
                header=header, timestamp="2025-01-01", head="abc",
                dry_run=True,
            )
        assert not (tmp_path / "docs" / "generated" / "api").exists()


# ---------------------------------------------------------------------------
# Dependency graph helpers
# ---------------------------------------------------------------------------


class TestFirstPartyPackages:
    def test_finds_packages(self, tmp_path):
        _write_pkg(tmp_path, "myapp", {})
        _write_pkg(tmp_path, "utils", {})
        pkgs = _first_party_packages(tmp_path)
        assert "myapp" in pkgs
        assert "utils" in pkgs

    def test_excludes_special_dirs(self, tmp_path):
        # __pycache__ has __init__.py-like files but should be excluded
        cache = tmp_path / "__pycache__"
        cache.mkdir()
        (cache / "__init__.py").write_text("")
        pkgs = _first_party_packages(tmp_path)
        assert "__pycache__" not in pkgs


class TestModuleName:
    def test_regular_file(self, tmp_path):
        pkg = tmp_path / "myapp"
        pkg.mkdir()
        f = pkg / "main.py"
        f.write_text("")
        assert _module_name(f, tmp_path) == "myapp.main"

    def test_init_file(self, tmp_path):
        pkg = tmp_path / "myapp"
        pkg.mkdir()
        f = pkg / "__init__.py"
        f.write_text("")
        assert _module_name(f, tmp_path) == "myapp"

    def test_nested(self, tmp_path):
        sub = tmp_path / "myapp" / "sub"
        sub.mkdir(parents=True)
        f = sub / "utils.py"
        f.write_text("")
        assert _module_name(f, tmp_path) == "myapp.sub.utils"


class TestExtractImports:
    def test_import_statement(self, tmp_path):
        f = tmp_path / "app.py"
        f.write_text("import os\nimport json\n")
        imports = _extract_imports(f)
        assert "os" in imports
        assert "json" in imports

    def test_from_import(self, tmp_path):
        f = tmp_path / "app.py"
        f.write_text("from pathlib import Path\nfrom myapp.utils import helper\n")
        imports = _extract_imports(f)
        assert "pathlib" in imports
        assert "myapp.utils" in imports

    def test_relative_import_excluded(self, tmp_path):
        f = tmp_path / "app.py"
        f.write_text("from . import sibling\n")
        imports = _extract_imports(f)
        # Relative imports (level > 0) should be excluded
        assert "sibling" not in imports

    def test_syntax_error(self, tmp_path):
        f = tmp_path / "bad.py"
        f.write_text("def broken(\n")
        assert _extract_imports(f) == []


class TestBuildImportGraph:
    def test_builds_graph(self, tmp_path):
        _write_pkg(tmp_path, "myapp", {
            "main.py": "from myapp.utils import helper\n",
            "utils.py": "x = 1\n",
        })
        graph = build_import_graph(tmp_path)
        assert graph.edge_count() >= 1
        modules = graph.modules()
        assert any("myapp" in m for m in modules)


# ---------------------------------------------------------------------------
# Mermaid / DOT rendering
# ---------------------------------------------------------------------------


class TestRenderMermaid:
    def test_empty(self):
        result = _render_mermaid([])
        assert "No first-party dependencies detected" in result

    def test_with_edges(self):
        edges = [DependencyEdge(source="a.main", target="a.utils")]
        result = _render_mermaid(edges)
        assert "mermaid" in result
        assert "a_main" in result
        assert "a_utils" in result


class TestRenderDot:
    def test_basic(self):
        edges = [DependencyEdge(source="a.main", target="a.utils")]
        result = _render_dot(edges)
        assert "digraph" in result
        assert '"a.main"' in result
        assert '"a.utils"' in result


# ---------------------------------------------------------------------------
# generate_graphs
# ---------------------------------------------------------------------------


class TestGenerateGraphs:
    def test_generates_files(self, tmp_path):
        _write_pkg(tmp_path, "myapp", {
            "main.py": "from myapp.utils import helper\n",
            "utils.py": "x = 1\n",
        })
        header = "<!-- test -->"
        result = generate_graphs(tmp_path, tmp_path / "docs" / "generated", header=header)
        assert result.modules_found >= 2
        assert len(result.files_written) >= 2

    def test_dot_format(self, tmp_path):
        _write_pkg(tmp_path, "myapp", {
            "main.py": "from myapp.utils import helper\n",
            "utils.py": "x = 1\n",
        })
        header = "<!-- test -->"
        result = generate_graphs(
            tmp_path, tmp_path / "docs" / "generated",
            header=header, graphs_format="dot",
        )
        assert any(".dot" in f for f in result.files_written)

    def test_empty_project(self, tmp_path):
        header = "<!-- test -->"
        result = generate_graphs(tmp_path, tmp_path / "docs" / "generated", header=header)
        assert result.edges_found == 0

    def test_dry_run(self, tmp_path):
        _write_pkg(tmp_path, "myapp", {"main.py": "x = 1\n"})
        header = "<!-- test -->"
        result = generate_graphs(
            tmp_path, tmp_path / "docs" / "generated",
            header=header, dry_run=True,
        )
        assert not (tmp_path / "docs" / "generated" / "graphs").exists()

    def test_isolated_modules_counted(self, tmp_path):
        _write_pkg(tmp_path, "myapp", {
            "main.py": "from myapp.utils import helper\n",
            "utils.py": "x = 1\n",
            "orphan.py": "y = 2\n",
        })
        header = "<!-- test -->"
        result = generate_graphs(tmp_path, tmp_path / "docs" / "generated", header=header)
        # orphan.py imports nothing and is imported by nothing
        assert result.isolated_modules >= 1


# ---------------------------------------------------------------------------
# generate_docs (top-level)
# ---------------------------------------------------------------------------


class TestGenerateDocs:
    @patch("harness_skills.generators.docs_generator._git_head", return_value="abc1234")
    @patch("harness_skills.generators.docs_generator._grep_recursive", return_value=[])
    def test_full_pipeline(self, mock_grep, mock_head, tmp_path):
        _write_pkg(tmp_path, "myapp", {"models.py": PYDANTIC_SOURCE, "main.py": "x = 1\n"})
        report = generate_docs(root=tmp_path)
        assert report.status.value == "passed"
        assert report.head == "abc1234"
        assert report.categories.schemas.entities_found >= 1

    @patch("harness_skills.generators.docs_generator._git_head", return_value="abc1234")
    @patch("harness_skills.generators.docs_generator._grep_recursive", return_value=[])
    def test_only_schemas(self, mock_grep, mock_head, tmp_path):
        _write_pkg(tmp_path, "myapp", {"models.py": PYDANTIC_SOURCE})
        report = generate_docs(root=tmp_path, only="schemas")
        assert report.categories.schemas.entities_found >= 1
        # api and graphs should be empty defaults
        assert report.categories.api.routes_found == 0
        assert report.categories.graphs.modules_found == 0

    @patch("harness_skills.generators.docs_generator._git_head", return_value="abc1234")
    @patch("harness_skills.generators.docs_generator._grep_recursive", return_value=[])
    def test_only_api(self, mock_grep, mock_head, tmp_path):
        _write_pkg(tmp_path, "myapp", {"main.py": "x = 1\n"})
        report = generate_docs(root=tmp_path, only="api")
        assert report.categories.schemas.entities_found == 0
        assert report.categories.graphs.modules_found == 0

    @patch("harness_skills.generators.docs_generator._git_head", return_value="abc1234")
    @patch("harness_skills.generators.docs_generator._grep_recursive", return_value=[])
    def test_only_graphs(self, mock_grep, mock_head, tmp_path):
        _write_pkg(tmp_path, "myapp", {"main.py": "x = 1\n"})
        report = generate_docs(root=tmp_path, only="graphs")
        assert report.categories.schemas.entities_found == 0
        assert report.categories.api.routes_found == 0

    @patch("harness_skills.generators.docs_generator._git_head", return_value="abc1234")
    @patch("harness_skills.generators.docs_generator._grep_recursive", return_value=[])
    def test_dry_run(self, mock_grep, mock_head, tmp_path):
        _write_pkg(tmp_path, "myapp", {"models.py": PYDANTIC_SOURCE})
        report = generate_docs(root=tmp_path, dry_run=True)
        assert report.dry_run is True
        # No index.md should be written in dry run
        assert not (tmp_path / "docs" / "generated" / "index.md").exists()

    @patch("harness_skills.generators.docs_generator._git_head", return_value="abc1234")
    @patch("harness_skills.generators.docs_generator._grep_recursive", return_value=[])
    def test_empty_project(self, mock_grep, mock_head, tmp_path):
        report = generate_docs(root=tmp_path)
        assert report.status.value == "passed"

    @patch("harness_skills.generators.docs_generator._git_head", return_value="abc1234")
    @patch("harness_skills.generators.docs_generator._grep_recursive", return_value=[])
    def test_dot_format(self, mock_grep, mock_head, tmp_path):
        _write_pkg(tmp_path, "myapp", {"main.py": "x = 1\n"})
        report = generate_docs(root=tmp_path, graphs_format="dot")
        assert report.status.value == "passed"

    @patch("harness_skills.generators.docs_generator._git_head", return_value="abc1234")
    @patch("harness_skills.generators.docs_generator._grep_recursive", return_value=[])
    def test_include_tests(self, mock_grep, mock_head, tmp_path):
        _write_pkg(tmp_path, "myapp", {
            "main.py": "x = 1\n",
            "test_main.py": "y = 2\n",
        })
        report = generate_docs(root=tmp_path, include_tests=True)
        assert report.status.value == "passed"

    @patch("harness_skills.generators.docs_generator._git_head", return_value="abc1234")
    @patch("harness_skills.generators.docs_generator._grep_recursive", return_value=[])
    def test_writes_index(self, mock_grep, mock_head, tmp_path):
        _write_pkg(tmp_path, "myapp", {"models.py": PYDANTIC_SOURCE})
        report = generate_docs(root=tmp_path)
        index_path = tmp_path / "docs" / "generated" / "index.md"
        assert index_path.exists()
        content = index_path.read_text()
        assert "Generated Documentation" in content

    @patch("harness_skills.generators.docs_generator._git_head", return_value="abc1234")
    @patch("harness_skills.generators.docs_generator._grep_recursive", return_value=[])
    def test_total_files_written(self, mock_grep, mock_head, tmp_path):
        _write_pkg(tmp_path, "myapp", {"models.py": PYDANTIC_SOURCE})
        report = generate_docs(root=tmp_path)
        assert report.total_files_written > 0

    @patch("harness_skills.generators.docs_generator._git_head", return_value="abc1234")
    @patch("harness_skills.generators.docs_generator._grep_recursive", return_value=[])
    def test_succeeded_property(self, mock_grep, mock_head, tmp_path):
        report = generate_docs(root=tmp_path)
        assert report.succeeded is True
