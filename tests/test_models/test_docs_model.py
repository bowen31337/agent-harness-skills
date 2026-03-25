"""Tests for harness_skills.models.docs — 100% coverage target."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from harness_skills.models.base import Status
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


# ── SchemaEntity ─────────────────────────────────────────────────────────────


class TestSchemaEntity:
    def test_minimal(self):
        e = SchemaEntity(name="users", source_file="models.py", framework="sqlalchemy")
        assert e.name == "users"
        assert e.field_count == 0
        assert e.notes == ""

    def test_full(self):
        e = SchemaEntity(
            name="orders",
            source_file="db.py",
            framework="django",
            field_count=5,
            notes="important",
        )
        assert e.field_count == 5
        assert e.notes == "important"

    def test_field_count_ge_zero(self):
        with pytest.raises(ValidationError):
            SchemaEntity(
                name="x", source_file="f.py", framework="sa", field_count=-1
            )

    def test_roundtrip(self):
        e = SchemaEntity(name="t", source_file="a.py", framework="fw")
        assert SchemaEntity.model_validate(e.model_dump()) == e


# ── RouteEntity ──────────────────────────────────────────────────────────────


class TestRouteEntity:
    def test_minimal(self):
        r = RouteEntity(method="GET", path="/api/users", handler="list_users")
        assert r.summary == ""
        assert r.source_file == ""

    def test_full(self):
        r = RouteEntity(
            method="POST",
            path="/api/items",
            handler="create_item",
            summary="Create an item",
            source_file="views.py",
        )
        assert r.summary == "Create an item"

    def test_roundtrip(self):
        r = RouteEntity(method="DELETE", path="/x", handler="h")
        assert RouteEntity.model_validate(r.model_dump()) == r


# ── DependencyEdge ───────────────────────────────────────────────────────────


class TestDependencyEdge:
    def test_create(self):
        d = DependencyEdge(source="a.b", target="c.d")
        assert d.source == "a.b"
        assert d.target == "c.d"

    def test_roundtrip(self):
        d = DependencyEdge(source="x", target="y")
        assert DependencyEdge.model_validate(d.model_dump()) == d


# ── SchemaCategoryResult ─────────────────────────────────────────────────────


class TestSchemaCategoryResult:
    def test_defaults(self):
        s = SchemaCategoryResult()
        assert s.files_written == []
        assert s.entities_found == 0
        assert s.frameworks == []
        assert s.entities == []

    def test_entities_found_ge_zero(self):
        with pytest.raises(ValidationError):
            SchemaCategoryResult(entities_found=-1)

    def test_with_entities(self):
        entity = SchemaEntity(name="t", source_file="f.py", framework="fw")
        s = SchemaCategoryResult(
            files_written=["a.md"],
            entities_found=1,
            frameworks=["fw"],
            entities=[entity],
        )
        assert len(s.entities) == 1

    def test_roundtrip(self):
        s = SchemaCategoryResult(entities_found=3)
        assert SchemaCategoryResult.model_validate(s.model_dump()) == s


# ── APICategoryResult ────────────────────────────────────────────────────────


class TestAPICategoryResult:
    def test_defaults(self):
        a = APICategoryResult()
        assert a.routes_found == 0
        assert a.routes == []

    def test_routes_found_ge_zero(self):
        with pytest.raises(ValidationError):
            APICategoryResult(routes_found=-1)

    def test_with_routes(self):
        route = RouteEntity(method="GET", path="/", handler="root")
        a = APICategoryResult(routes=[route], routes_found=1)
        assert len(a.routes) == 1

    def test_roundtrip(self):
        a = APICategoryResult(frameworks=["flask"])
        assert APICategoryResult.model_validate(a.model_dump()) == a


# ── GraphCategoryResult ──────────────────────────────────────────────────────


class TestGraphCategoryResult:
    def test_defaults(self):
        g = GraphCategoryResult()
        assert g.modules_found == 0
        assert g.edges_found == 0
        assert g.most_imported == ""
        assert g.largest_fan_out == ""
        assert g.isolated_modules == 0
        assert g.edges == []

    def test_ge_zero_fields(self):
        for field, val in [
            ("modules_found", -1),
            ("edges_found", -1),
            ("isolated_modules", -1),
        ]:
            with pytest.raises(ValidationError):
                GraphCategoryResult(**{field: val})

    def test_with_edges(self):
        edge = DependencyEdge(source="a", target="b")
        g = GraphCategoryResult(edges=[edge], edges_found=1, modules_found=2)
        assert len(g.edges) == 1

    def test_roundtrip(self):
        g = GraphCategoryResult(most_imported="core")
        assert GraphCategoryResult.model_validate(g.model_dump()) == g


# ── GeneratedDocsCategories ──────────────────────────────────────────────────


class TestGeneratedDocsCategories:
    def test_defaults(self):
        c = GeneratedDocsCategories()
        assert isinstance(c.schemas, SchemaCategoryResult)
        assert isinstance(c.api, APICategoryResult)
        assert isinstance(c.graphs, GraphCategoryResult)

    def test_roundtrip(self):
        c = GeneratedDocsCategories()
        assert GeneratedDocsCategories.model_validate(c.model_dump()) == c


# ── GeneratedDocsReport ──────────────────────────────────────────────────────


class TestGeneratedDocsReport:
    def _make_report(self, **kwargs):
        defaults = dict(command="generate-docs", status=Status.PASSED)
        defaults.update(kwargs)
        return GeneratedDocsReport(**defaults)

    def test_defaults(self):
        r = self._make_report()
        assert r.command == "generate-docs"
        assert r.head == "unknown"
        assert r.out_dir == "docs/generated"
        assert r.dry_run is False
        assert r.warnings == []
        assert r.errors == []

    def test_total_files_written_zero(self):
        r = self._make_report()
        assert r.total_files_written == 0

    def test_total_files_written_nonzero(self):
        cats = GeneratedDocsCategories(
            schemas=SchemaCategoryResult(files_written=["a.md", "b.md"]),
            api=APICategoryResult(files_written=["c.md"]),
            graphs=GraphCategoryResult(files_written=["d.md", "e.md", "f.md"]),
        )
        r = self._make_report(categories=cats)
        assert r.total_files_written == 6

    def test_succeeded_true(self):
        r = self._make_report(status=Status.PASSED)
        assert r.succeeded is True

    def test_succeeded_false_with_errors(self):
        r = self._make_report(status=Status.PASSED, errors=["boom"])
        assert r.succeeded is False

    def test_succeeded_false_wrong_status(self):
        r = self._make_report(status=Status.FAILED)
        assert r.succeeded is False

    def test_roundtrip(self):
        r = self._make_report(head="abc123", dry_run=True)
        assert GeneratedDocsReport.model_validate(r.model_dump()) == r

    def test_roundtrip_json(self):
        r = self._make_report()
        json_str = r.model_dump_json()
        restored = GeneratedDocsReport.model_validate_json(json_str)
        assert restored == r
