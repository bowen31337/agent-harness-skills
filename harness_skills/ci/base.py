"""Abstract base class for CI pipeline generators."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CIPipelineResult:
    """Output from a CI pipeline generator."""

    platform: str  # "github-actions" | "gitlab-ci" | "shell"
    file_path: str  # relative output path
    content: str  # generated file content
    artifact_type: str = "ci_pipeline"


class BaseCIGenerator(ABC):
    """Abstract CI pipeline generator."""

    @abstractmethod
    def platform(self) -> str:
        """Return the CI platform name."""

    @abstractmethod
    def generate(
        self,
        *,
        primary_language: str = "python",
        python_version: str = "3.12",
        node_version: str = "20",
        gate_ids: list[str] | None = None,
        extra_setup: list[str] | None = None,
    ) -> CIPipelineResult:
        """Generate a CI pipeline configuration."""
