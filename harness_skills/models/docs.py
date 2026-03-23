"""Typed response model for ``/generate-docs``.

Schema: harness_skills.models.docs.GeneratedDocsReport

Consumers can deserialise the JSON emitted to stdout by the skill and iterate
``categories`` to discover which files were written and how many entities were
found in each category.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from harness_skills.models.base import HarnessResponse, Status


class SchemaEntity(BaseModel):
    """A single extracted table, model, or schema definition."""

    name: str
    source_file: str
    framework: str
    field_count: int = Field(ge=0, default=0)
    notes: str = ""


class RouteEntity(BaseModel):
    """A single extracted HTTP route."""

    method: str  # GET, POST, PUT, PATCH, DELETE …
    path: str
    handler: str
    summary: str = ""
    source_file: str = ""


class DependencyEdge(BaseModel):
    """A directed import edge between two first-party modules."""

    source: str  # dotted module path, e.g. "harness_skills.cli.main"
    target: str  # dotted module path, e.g. "harness_skills.models.base"


class SchemaCategoryResult(BaseModel):
    """Result for the ``schemas`` generation category."""

    files_written: list[str] = Field(default_factory=list)
    entities_found: int = Field(ge=0, default=0)
    frameworks: list[str] = Field(default_factory=list)
    entities: list[SchemaEntity] = Field(default_factory=list)


class APICategoryResult(BaseModel):
    """Result for the ``api`` generation category."""

    files_written: list[str] = Field(default_factory=list)
    routes_found: int = Field(ge=0, default=0)
    frameworks: list[str] = Field(default_factory=list)
    routes: list[RouteEntity] = Field(default_factory=list)


class GraphCategoryResult(BaseModel):
    """Result for the ``graphs`` generation category."""

    files_written: list[str] = Field(default_factory=list)
    modules_found: int = Field(ge=0, default=0)
    edges_found: int = Field(ge=0, default=0)
    most_imported: str = ""
    largest_fan_out: str = ""
    isolated_modules: int = Field(ge=0, default=0)
    edges: list[DependencyEdge] = Field(default_factory=list)


class GeneratedDocsCategories(BaseModel):
    """Aggregated results across all three generation categories."""

    schemas: SchemaCategoryResult = Field(default_factory=SchemaCategoryResult)
    api: APICategoryResult = Field(default_factory=APICategoryResult)
    graphs: GraphCategoryResult = Field(default_factory=GraphCategoryResult)


class GeneratedDocsReport(HarnessResponse):
    """Response schema for ``/generate-docs``.

    Emitted as JSON to stdout after every run.  Consumers can pipe this to
    ``jq`` or deserialise it with Pydantic to inspect what was generated.

    Example::

        report = GeneratedDocsReport.model_validate_json(stdout_output)
        for path in report.categories.schemas.files_written:
            print(f"Schema file: {path}")
    """

    command: str = "generate-docs"
    head: str = Field(default="unknown", description="Short git SHA at generation time.")
    out_dir: str = Field(default="docs/generated", description="Root output directory.")
    dry_run: bool = Field(default=False, description="True when --dry-run was passed.")
    categories: GeneratedDocsCategories = Field(default_factory=GeneratedDocsCategories)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def total_files_written(self) -> int:
        return (
            len(self.categories.schemas.files_written)
            + len(self.categories.api.files_written)
            + len(self.categories.graphs.files_written)
        )

    @property
    def succeeded(self) -> bool:
        return self.status == Status.PASSED and not self.errors
