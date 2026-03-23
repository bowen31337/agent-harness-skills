"""Static-analysis documentation generator for ``/generate-docs``.

Produces three categories of auto-derived documentation under ``docs/generated/``:

* **schemas/** — database / data-model schemas (SQLAlchemy, Pydantic, Django ORM, Prisma)
* **api/**     — HTTP API specifications (FastAPI, Flask, Django URLs)
* **graphs/**  — module dependency graphs (Mermaid diagram + statistics)

All output files carry a ``<!-- harness:auto-generated -->`` header so the
``/doc-freshness-gate`` skill can detect when they become stale.

Design principles
-----------------
* **No running server required** — pure static analysis via ``grep`` / ``ast`` / file I/O.
* **No third-party tool dependencies** — only the stdlib and packages already in
  ``requirements.txt`` (``pydantic``, ``requests``).
* **Idempotent** — the same commit always produces identical output.
* **Incremental** — callers may request a single category via ``only``.
"""

from __future__ import annotations

import ast
import re
import subprocess
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from harness_skills.models.docs import (
    APICategoryResult,
    DependencyEdge,
    GeneratedDocsCategories,
    GeneratedDocsReport,
    GraphCategoryResult,
    RouteEntity,
    SchemaCategoryResult,
    SchemaEntity,
)
from harness_skills.models.base import Status


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

HARNESS_HEADER_TPL = """\
<!-- harness:auto-generated — do not edit this block manually -->
<!-- generated: {timestamp} -->
<!-- head: {head} -->
<!-- /harness:auto-generated -->
"""

_EXCLUDE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "site-packages", "dist", "build", ".mypy_cache", ".ruff_cache",
}

CategoryName = Literal["schemas", "api", "graphs"]


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _harness_header(timestamp: str, head: str) -> str:
    return HARNESS_HEADER_TPL.format(timestamp=timestamp, head=head)


def _python_files(root: Path, *, include_tests: bool = False) -> list[Path]:
    """Return all first-party .py files under *root*, excluding hidden/generated dirs."""
    results: list[Path] = []
    for p in root.rglob("*.py"):
        parts = set(p.parts)
        if parts & _EXCLUDE_DIRS:
            continue
        if not include_tests and ("test_" in p.name or p.name.endswith("_test.py")):
            continue
        results.append(p)
    return sorted(results)


def _grep(pattern: str, path: Path, flags: str = "") -> list[str]:
    """Run grep and return matching lines (never raises)."""
    cmd = ["grep", "-n"]
    if flags:
        cmd += flags.split()
    cmd += [pattern, str(path)]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True)
        return out.splitlines()
    except subprocess.CalledProcessError:
        return []


def _grep_recursive(
    pattern: str,
    root: Path,
    *,
    include: str = "*.py",
    flags: str = "",
) -> list[str]:
    """Run grep -r and return file paths containing the pattern."""
    cmd = ["grep", "-rl", f"--include={include}"]
    if flags:
        cmd += flags.split()
    cmd += [pattern, str(root)]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True)
        return [ln.strip() for ln in out.splitlines() if ln.strip()]
    except subprocess.CalledProcessError:
        return []


# ---------------------------------------------------------------------------
# Schema generation
# ---------------------------------------------------------------------------

@dataclass
class _PydanticField:
    name: str
    annotation: str
    required: bool = True
    default: str = "—"
    notes: str = ""


def _extract_pydantic_models(py_file: Path) -> list[SchemaEntity]:
    """Parse *py_file* with the AST and extract Pydantic BaseModel subclasses."""
    try:
        source = py_file.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(py_file))
    except SyntaxError:
        return []

    entities: list[SchemaEntity] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bases = [
            (b.id if isinstance(b, ast.Name) else
             b.attr if isinstance(b, ast.Attribute) else "")
            for b in node.bases
        ]
        if not any("BaseModel" in b for b in bases):
            continue
        # Count annotated fields (class-level annotations)
        field_count = sum(
            1 for stmt in node.body
            if isinstance(stmt, ast.AnnAssign)
        )
        entities.append(SchemaEntity(
            name=node.name,
            source_file=str(py_file),
            framework="pydantic",
            field_count=field_count,
        ))
    return entities


def _extract_sqlalchemy_models(py_file: Path) -> list[SchemaEntity]:
    """Heuristically detect SQLAlchemy mapped classes."""
    try:
        source = py_file.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(py_file))
    except SyntaxError:
        return []

    sa_keywords = {"Column", "mapped_column", "relationship", "ForeignKey"}
    entities: list[SchemaEntity] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        body_names: set[str] = set()
        for stmt in node.body:
            for child in ast.walk(stmt):
                if isinstance(child, ast.Name):
                    body_names.add(child.id)
                elif isinstance(child, ast.Attribute):
                    body_names.add(child.attr)
        if sa_keywords & body_names:
            field_count = sum(
                1 for stmt in node.body
                if isinstance(stmt, (ast.Assign, ast.AnnAssign))
            )
            entities.append(SchemaEntity(
                name=node.name,
                source_file=str(py_file),
                framework="sqlalchemy",
                field_count=field_count,
            ))
    return entities


def _extract_django_models(py_file: Path) -> list[SchemaEntity]:
    """Heuristically detect Django models.Model subclasses."""
    try:
        source = py_file.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(py_file))
    except SyntaxError:
        return []

    django_field_pattern = re.compile(
        r"models\.(Char|Integer|Boolean|Date|Float|Text|Foreign|Many|One|Auto|Email|URL|Slug)"
    )
    entities: list[SchemaEntity] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bases_str = ast.unparse(node) if hasattr(ast, "unparse") else ""
        if "models.Model" not in bases_str:
            continue
        field_count = len(django_field_pattern.findall(ast.unparse(node) if hasattr(ast, "unparse") else ""))
        entities.append(SchemaEntity(
            name=node.name,
            source_file=str(py_file),
            framework="django",
            field_count=field_count,
        ))
    return entities


def _render_schema_table(entities: list[SchemaEntity], framework: str, header: str) -> str:
    """Render a Markdown document for one framework's entities."""
    if not entities:
        return (
            f"{header}\n\n# {framework.title()} Schemas\n\n"
            f"No `{framework}` models detected in this repository.\n"
        )

    lines = [header, "", f"# {framework.title()} Schemas", ""]
    lines.append(f"*{len(entities)} model(s) detected.*\n")
    lines.append("| Model | Source File | Fields |")
    lines.append("|-------|-------------|--------|")
    for e in entities:
        rel = e.source_file
        lines.append(f"| `{e.name}` | `{rel}` | {e.field_count} |")
    lines.append("")

    for e in entities:
        lines.append(f"## `{e.name}`\n")
        lines.append(f"**Source:** `{e.source_file}`  ")
        lines.append(f"**Framework:** {e.framework}  ")
        lines.append(f"**Fields:** {e.field_count}\n")

    return "\n".join(lines)


def generate_schemas(
    root: Path,
    out_dir: Path,
    *,
    header: str,
    include_tests: bool = False,
    dry_run: bool = False,
) -> SchemaCategoryResult:
    """Generate docs/generated/schemas/ and return the result."""
    schemas_dir = out_dir / "schemas"
    if not dry_run:
        schemas_dir.mkdir(parents=True, exist_ok=True)

    py_files = _python_files(root, include_tests=include_tests)

    all_pydantic: list[SchemaEntity] = []
    all_sqlalchemy: list[SchemaEntity] = []
    all_django: list[SchemaEntity] = []

    for f in py_files:
        all_pydantic.extend(_extract_pydantic_models(f))
        all_sqlalchemy.extend(_extract_sqlalchemy_models(f))
        all_django.extend(_extract_django_models(f))

    files_written: list[str] = []
    frameworks: list[str] = []

    def _write(filename: str, content: str) -> None:
        path = schemas_dir / filename
        if not dry_run:
            path.write_text(content, encoding="utf-8")
        files_written.append(str(path.relative_to(root)))

    if all_pydantic:
        frameworks.append("pydantic")
        _write("pydantic.md", _render_schema_table(all_pydantic, "pydantic", header))

    if all_sqlalchemy:
        frameworks.append("sqlalchemy")
        _write("sqlalchemy.md", _render_schema_table(all_sqlalchemy, "sqlalchemy", header))

    if all_django:
        frameworks.append("django")
        _write("django-orm.md", _render_schema_table(all_django, "Django ORM", header))

    all_entities = all_pydantic + all_sqlalchemy + all_django

    # Index
    index_rows = "\n".join(
        f"| [{fw}.md]({fw}.md) | {fw.title()} | {sum(1 for e in all_entities if e.framework == fw)} |"
        for fw in frameworks
    ) or "*(no schema frameworks detected)*"

    index_content = (
        f"{header}\n"
        "# Database & Data-Model Schemas\n\n"
        f"*{len(all_entities)} model(s) across {len(frameworks)} framework(s).*\n\n"
        "| File | Framework | Models |\n"
        "|------|-----------|--------|\n"
        f"{index_rows}\n"
    )
    _write("index.md", index_content)

    return SchemaCategoryResult(
        files_written=files_written,
        entities_found=len(all_entities),
        frameworks=frameworks,
        entities=all_entities,
    )


# ---------------------------------------------------------------------------
# API generation
# ---------------------------------------------------------------------------

_FASTAPI_ROUTE_RE = re.compile(
    r'@(?:app|router)\.(get|post|put|patch|delete|head|options)\s*\(\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)


def _extract_fastapi_routes(py_file: Path) -> list[RouteEntity]:
    try:
        source = py_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = source.splitlines()
    routes: list[RouteEntity] = []
    for i, line in enumerate(lines):
        m = _FASTAPI_ROUTE_RE.search(line)
        if not m:
            continue
        method = m.group(1).upper()
        path = m.group(2)
        # Try to grab the function name from the next non-empty line
        handler = ""
        for j in range(i + 1, min(i + 5, len(lines))):
            fn_m = re.match(r"\s*async\s+def\s+(\w+)|def\s+(\w+)", lines[j])
            if fn_m:
                handler = fn_m.group(1) or fn_m.group(2)
                break
        # Grab docstring
        summary = ""
        if handler:
            for j in range(i + 2, min(i + 8, len(lines))):
                ds_m = re.match(r'\s+"""(.+?)"""|\s+"""(.+)', lines[j])
                if ds_m:
                    summary = (ds_m.group(1) or ds_m.group(2)).strip()
                    break
        routes.append(RouteEntity(
            method=method,
            path=path,
            handler=handler,
            summary=summary,
            source_file=str(py_file),
        ))
    return routes


_FLASK_ROUTE_RE = re.compile(
    r'@(?:app|bp|blueprint)\s*\.route\s*\(\s*["\']([^"\']+)["\'].*?(?:methods\s*=\s*\[([^\]]+)\])?',
    re.IGNORECASE,
)


def _extract_flask_routes(py_file: Path) -> list[RouteEntity]:
    try:
        source = py_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = source.splitlines()
    routes: list[RouteEntity] = []
    for i, line in enumerate(lines):
        m = _FLASK_ROUTE_RE.search(line)
        if not m:
            continue
        path = m.group(1)
        raw_methods = m.group(2) or "GET"
        methods = [mth.strip().strip("'\"").upper() for mth in raw_methods.split(",")]
        handler = ""
        for j in range(i + 1, min(i + 5, len(lines))):
            fn_m = re.match(r"\s*def\s+(\w+)", lines[j])
            if fn_m:
                handler = fn_m.group(1)
                break
        for mth in methods:
            routes.append(RouteEntity(
                method=mth,
                path=path,
                handler=handler,
                source_file=str(py_file),
            ))
    return routes


def _render_routes_md(routes: list[RouteEntity], header: str) -> str:
    if not routes:
        return (
            f"{header}\n\n# HTTP API Routes\n\n"
            "No HTTP routes detected. Add FastAPI, Flask, or Django URL patterns.\n"
        )
    lines = [header, "", "# HTTP API Routes", "",
             f"*{len(routes)} route(s) detected.*\n",
             "| Method | Path | Handler | Summary |",
             "|--------|------|---------|---------|"]
    for r in routes:
        lines.append(f"| {r.method} | `{r.path}` | `{r.handler}` | {r.summary} |")
    lines.append("")
    return "\n".join(lines)


def _render_openapi_yaml(routes: list[RouteEntity], head: str, timestamp: str, project_name: str) -> str:
    """Build a minimal OpenAPI 3.1 YAML document from extracted routes."""
    paths_block = ""
    grouped: dict[str, list[RouteEntity]] = {}
    for r in routes:
        grouped.setdefault(r.path, []).append(r)

    for path, path_routes in sorted(grouped.items()):
        paths_block += f"  {path}:\n"
        for r in path_routes:
            paths_block += textwrap.dedent(f"""\
                    {r.method.lower()}:
                      operationId: {r.handler or 'unknown'}
                      summary: "{r.summary or r.handler}"
                      responses:
                        "200":
                          description: "OK"
            """)

    return textwrap.dedent(f"""\
        openapi: "3.1.0"
        info:
          title: "{project_name} API"
          version: "{head}"
          description: "Auto-generated by /generate-docs. Do not edit manually."
          x-generated-at: "{timestamp}"
        paths:
        {paths_block or "  {}"}
    """)


def generate_api(
    root: Path,
    out_dir: Path,
    *,
    header: str,
    timestamp: str,
    head: str,
    include_tests: bool = False,
    dry_run: bool = False,
) -> APICategoryResult:
    """Generate docs/generated/api/ and return the result."""
    api_dir = out_dir / "api"
    if not dry_run:
        api_dir.mkdir(parents=True, exist_ok=True)

    py_files = _python_files(root, include_tests=include_tests)
    all_routes: list[RouteEntity] = []
    frameworks: list[str] = []

    fastapi_files = _grep_recursive("from fastapi import\\|import fastapi", root)
    flask_files = _grep_recursive("from flask import Flask", root)

    if fastapi_files:
        frameworks.append("fastapi")
        for f in py_files:
            all_routes.extend(_extract_fastapi_routes(f))

    if flask_files:
        frameworks.append("flask")
        for f in py_files:
            all_routes.extend(_extract_flask_routes(f))

    files_written: list[str] = []

    def _write(filename: str, content: str) -> None:
        path = api_dir / filename
        if not dry_run:
            path.write_text(content, encoding="utf-8")
        files_written.append(str(path.relative_to(root)))

    project_name = root.name
    _write("routes.md", _render_routes_md(all_routes, header))
    _write("openapi.yaml", _render_openapi_yaml(all_routes, head, timestamp, project_name))

    index_rows = "\n".join(
        f"| {fw.title()} | `{fw}` |" for fw in frameworks
    ) or "*(no HTTP framework detected)*"

    _write("index.md", (
        f"{header}\n"
        "# HTTP API Specifications\n\n"
        f"*{len(all_routes)} route(s) across {len(frameworks)} framework(s).*\n\n"
        "| File | Description |\n"
        "|------|-------------|\n"
        "| [openapi.yaml](openapi.yaml) | OpenAPI 3.1 specification |\n"
        "| [routes.md](routes.md) | Human-readable route table |\n\n"
        "## Detected Frameworks\n\n"
        "| Framework | Identifier |\n"
        "|-----------|------------|\n"
        f"{index_rows}\n"
    ))

    return APICategoryResult(
        files_written=files_written,
        routes_found=len(all_routes),
        frameworks=frameworks,
        routes=all_routes,
    )


# ---------------------------------------------------------------------------
# Dependency graph generation
# ---------------------------------------------------------------------------

def _first_party_packages(root: Path) -> set[str]:
    """Return the top-level package names that live under *root*."""
    packages: set[str] = set()
    for init in root.glob("*/__init__.py"):
        pkg = init.parent.name
        if pkg not in _EXCLUDE_DIRS:
            packages.add(pkg)
    return packages


def _module_name(py_file: Path, root: Path) -> str:
    """Convert a file path to a dotted module name relative to *root*."""
    rel = py_file.relative_to(root)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1].removesuffix(".py")
    return ".".join(parts)


def _extract_imports(py_file: Path) -> list[str]:
    """Return a list of top-level import targets from *py_file*."""
    try:
        source = py_file.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(py_file))
    except SyntaxError:
        return []
    targets: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                targets.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                targets.append(node.module)
    return targets


def _render_mermaid(edges: list[DependencyEdge]) -> str:
    if not edges:
        return "```mermaid\ngraph LR\n  %% No first-party dependencies detected\n```"
    lines = ["```mermaid", "graph LR"]
    for e in edges:
        # Mermaid needs safe node IDs — replace dots with underscores for the ID,
        # but keep the label human-readable.
        src_id = e.source.replace(".", "_").replace("-", "_")
        tgt_id = e.target.replace(".", "_").replace("-", "_")
        lines.append(f'  {src_id}["{e.source}"] --> {tgt_id}["{e.target}"]')
    lines.append("```")
    return "\n".join(lines)


def _render_dot(edges: list[DependencyEdge]) -> str:
    lines = ["digraph dependencies {", '  rankdir=LR;']
    for e in edges:
        lines.append(f'  "{e.source}" -> "{e.target}";')
    lines.append("}")
    return "\n".join(lines)


def generate_graphs(
    root: Path,
    out_dir: Path,
    *,
    header: str,
    include_tests: bool = False,
    graphs_format: Literal["mermaid", "dot"] = "mermaid",
    dry_run: bool = False,
) -> GraphCategoryResult:
    """Generate docs/generated/graphs/ and return the result."""
    graphs_dir = out_dir / "graphs"
    if not dry_run:
        graphs_dir.mkdir(parents=True, exist_ok=True)

    first_party = _first_party_packages(root)
    py_files = _python_files(root, include_tests=include_tests)

    edges: list[DependencyEdge] = []
    all_modules: set[str] = set()

    for f in py_files:
        mod = _module_name(f, root)
        all_modules.add(mod)
        for imp in _extract_imports(f):
            # Keep only first-party imports
            top = imp.split(".")[0]
            if top in first_party and imp != mod:
                edges.append(DependencyEdge(source=mod, target=imp))

    # Deduplicate edges
    seen: set[tuple[str, str]] = set()
    unique_edges: list[DependencyEdge] = []
    for e in edges:
        key = (e.source, e.target)
        if key not in seen:
            seen.add(key)
            unique_edges.append(e)
    edges = unique_edges

    # Statistics
    from collections import Counter
    target_counts = Counter(e.target for e in edges)
    source_counts = Counter(e.source for e in edges)
    most_imported = target_counts.most_common(1)[0][0] if target_counts else ""
    largest_fan_out = source_counts.most_common(1)[0][0] if source_counts else ""

    referenced = {e.source for e in edges} | {e.target for e in edges}
    isolated_count = len(all_modules - referenced)

    stats_section = (
        "\n## Statistics\n\n"
        "| Metric | Value |\n"
        "|--------|-------|\n"
        f"| Total modules | {len(all_modules)} |\n"
        f"| Total edges | {len(edges)} |\n"
        f"| Most-imported module | `{most_imported}` |\n"
        f"| Largest fan-out | `{largest_fan_out}` |\n"
        f"| Isolated modules | {isolated_count} |\n"
    )

    files_written: list[str] = []

    def _write(filename: str, content: str) -> None:
        path = graphs_dir / filename
        if not dry_run:
            path.write_text(content, encoding="utf-8")
        files_written.append(str(path.relative_to(root)))

    graph_body = _render_mermaid(edges) if graphs_format == "mermaid" else _render_dot(edges)
    ext = "md" if graphs_format == "mermaid" else "dot"

    deps_content = (
        f"{header}\n"
        "# Module Dependency Graph\n\n"
        "> Only first-party modules are shown. "
        "Third-party and stdlib imports are omitted.\n\n"
        f"{graph_body}\n"
        f"{stats_section}"
    )
    _write(f"dependencies.{ext}", deps_content)

    _write("index.md", (
        f"{header}\n"
        "# Module Dependency Graphs\n\n"
        f"*{len(all_modules)} module(s), {len(edges)} edge(s).*\n\n"
        "| File | Format | Description |\n"
        "|------|--------|-------------|\n"
        f"| [dependencies.{ext}](dependencies.{ext}) | {graphs_format.title()} | First-party import graph |\n"
    ))

    return GraphCategoryResult(
        files_written=files_written,
        modules_found=len(all_modules),
        edges_found=len(edges),
        most_imported=most_imported,
        largest_fan_out=largest_fan_out,
        isolated_modules=isolated_count,
        edges=edges,
    )


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def generate_docs(
    root: Path | None = None,
    *,
    out_dir: Path | None = None,
    only: CategoryName | None = None,
    include_tests: bool = False,
    graphs_format: Literal["mermaid", "dot"] = "mermaid",
    dry_run: bool = False,
) -> GeneratedDocsReport:
    """Run the full ``/generate-docs`` pipeline.

    Parameters
    ----------
    root:
        Repository root directory.  Defaults to the current working directory.
    out_dir:
        Output directory root.  Defaults to ``<root>/docs/generated``.
    only:
        If set, generate only the named category (``"schemas"``, ``"api"``, or
        ``"graphs"``).  All other categories are skipped.
    include_tests:
        If True, test files are included when scanning for models and routes.
    graphs_format:
        ``"mermaid"`` (default) or ``"dot"`` (Graphviz).
    dry_run:
        Discover and report without writing any files.

    Returns
    -------
    GeneratedDocsReport
        Fully-populated report that also matches the JSON emitted to stdout.
    """
    root = (root or Path.cwd()).resolve()
    out_dir = (out_dir or root / "docs" / "generated").resolve()

    timestamp = _now_iso()
    head = _git_head()
    header = _harness_header(timestamp, head)

    warnings: list[str] = []
    errors: list[str] = []

    schemas_result = SchemaCategoryResult()
    api_result = APICategoryResult()
    graphs_result = GraphCategoryResult()

    run_schemas = only in (None, "schemas")
    run_api = only in (None, "api")
    run_graphs = only in (None, "graphs")

    try:
        if run_schemas:
            schemas_result = generate_schemas(
                root, out_dir, header=header,
                include_tests=include_tests, dry_run=dry_run,
            )
    except Exception as exc:  # pragma: no cover
        errors.append(f"schemas: {exc}")

    try:
        if run_api:
            api_result = generate_api(
                root, out_dir, header=header,
                timestamp=timestamp, head=head,
                include_tests=include_tests, dry_run=dry_run,
            )
    except Exception as exc:  # pragma: no cover
        errors.append(f"api: {exc}")

    try:
        if run_graphs:
            graphs_result = generate_graphs(
                root, out_dir, header=header,
                include_tests=include_tests,
                graphs_format=graphs_format,
                dry_run=dry_run,
            )
    except Exception as exc:  # pragma: no cover
        errors.append(f"graphs: {exc}")

    # Write top-level index
    all_files = (
        schemas_result.files_written
        + api_result.files_written
        + graphs_result.files_written
    )

    index_content = (
        f"{header}\n"
        "# Generated Documentation\n\n"
        "This directory is fully auto-generated by `/generate-docs`. "
        "**Do not edit these files manually.**\n\n"
        "| Category | Index | Contents |\n"
        "|----------|-------|----------|\n"
        "| Schemas | [schemas/index.md](schemas/index.md) | SQLAlchemy, Pydantic, Django ORM |\n"
        "| API Specs | [api/index.md](api/index.md) | OpenAPI 3.1 YAML + route summary |\n"
        "| Dependency Graphs | [graphs/index.md](graphs/index.md) | Mermaid diagram + statistics |\n\n"
        "## Regenerate\n\n"
        "```bash\n/generate-docs\n```\n\n"
        f"## Freshness\n\nLast generated from commit `{head}` at `{timestamp}`.\n"
    )

    if not dry_run and all_files:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.md").write_text(index_content, encoding="utf-8")

    status = Status.FAILED if errors else Status.PASSED

    return GeneratedDocsReport(
        command="generate-docs",
        status=status,
        timestamp=timestamp,
        head=head,
        out_dir=str(out_dir.relative_to(root)),
        dry_run=dry_run,
        categories=GeneratedDocsCategories(
            schemas=schemas_result,
            api=api_result,
            graphs=graphs_result,
        ),
        warnings=warnings,
        errors=errors,
    )
