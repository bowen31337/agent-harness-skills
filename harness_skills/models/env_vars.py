"""Typed response models for environment-variable pattern detection."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from harness_skills.models.base import HarnessResponse


class EnvVarSource(str, Enum):
    """The kind of file or construct where the variable was found."""

    DOTENV_EXAMPLE = "dotenv_example"
    """A ``.env.example``, ``.env.sample``, or similar template file."""

    CONFIG_FILE = "config_file"
    """A YAML, TOML, JSON, or INI configuration file that references the var."""

    SOURCE_CODE = "source_code"
    """A source file that reads the variable at runtime (os.environ, process.env, …)."""


class EnvVarEntry(BaseModel):
    """A single environment variable discovered during scanning."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="The variable name, e.g. DATABASE_URL.")
    source: EnvVarSource
    file_path: str = Field(description="Repo-relative path of the file where it was found.")
    line_number: Optional[int] = Field(
        default=None,
        description="1-based line number within file_path (None when unavailable).",
    )
    default_value: Optional[str] = Field(
        default=None,
        description=(
            "The example/default value as written in a .env file or config. "
            "None when the source is source_code or the entry has no value."
        ),
    )
    comment: Optional[str] = Field(
        default=None,
        description="Inline or preceding comment associated with the variable definition.",
    )
    required: bool = Field(
        default=True,
        description=(
            "False when the entry is commented-out in a .env.example "
            "(i.e. the variable is optional or not yet configured)."
        ),
    )


class EnvVarDetectionResult(HarnessResponse):
    """Response schema for the environment-variable pattern detection skill.

    Emitted after scanning ``.env.example`` / config / source files for
    environment-variable declarations and references.

    Example::

        {
          "command": "detect-env-vars",
          "status": "passed",
          "scanned_path": ".",
          "total_vars_found": 14,
          "unique_var_names": ["ANTHROPIC_API_KEY", "DATABASE_URL", ...],
          "env_vars": [...],
          "dotenv_files_found": [".env.example"],
          "config_files_found": [],
          "source_files_scanned": 42
        }
    """

    command: str = "detect-env-vars"

    scanned_path: str = Field(
        description="Root path that was scanned (repo-relative or absolute)."
    )
    env_vars: list[EnvVarEntry] = Field(
        default_factory=list,
        description="All variable entries discovered, one per occurrence.",
    )
    unique_var_names: list[str] = Field(
        default_factory=list,
        description=(
            "De-duplicated, alphabetically sorted list of all variable names found "
            "across every source type."
        ),
    )
    dotenv_files_found: list[str] = Field(
        default_factory=list,
        description="Repo-relative paths of .env.example / .env.sample files scanned.",
    )
    config_files_found: list[str] = Field(
        default_factory=list,
        description="Repo-relative paths of YAML/TOML/JSON config files that contained env-var references.",
    )
    source_files_scanned: int = Field(
        default=0,
        description="Number of source files (py, js, ts, go, rb, sh) that were inspected.",
    )
    total_vars_found: int = Field(
        default=0,
        description="Total number of EnvVarEntry items (not de-duplicated).",
    )
