"""GitLab CI configuration generator."""

from __future__ import annotations

import yaml

from harness_skills.ci.base import BaseCIGenerator, CIPipelineResult

_IMAGES: dict[str, str] = {
    "python": "python:3.12-slim",
    "javascript": "node:20-slim",
    "typescript": "node:20-slim",
    "go": "golang:1.21",
    "rust": "rust:latest",
    "java": "openjdk:21-slim",
}

_INSTALL_COMMANDS: dict[str, str] = {
    "python": "uv sync --frozen",
    "javascript": "npm ci",
    "typescript": "npm ci",
    "go": "go mod download",
}


class GitLabCIGenerator(BaseCIGenerator):
    """Generates a GitLab CI job for harness evaluate."""

    def platform(self) -> str:
        return "gitlab-ci"

    def generate(
        self,
        *,
        primary_language: str = "python",
        python_version: str = "3.12",
        node_version: str = "20",
        gate_ids: list[str] | None = None,
        extra_setup: list[str] | None = None,
    ) -> CIPipelineResult:
        lang = primary_language.lower()
        image = _IMAGES.get(lang, "python:3.12-slim")
        install = _INSTALL_COMMANDS.get(lang, "echo 'ready'")

        evaluate_cmd = "harness evaluate --output-format json"
        if gate_ids:
            for gid in gate_ids:
                evaluate_cmd += f" --gate {gid}"

        scripts = [install]
        for cmd in (extra_setup or []):
            scripts.append(cmd)
        scripts.append(evaluate_cmd)

        config = {
            "stages": ["evaluate"],
            "harness-evaluate": {
                "stage": "evaluate",
                "image": image,
                "script": scripts,
                "artifacts": {
                    "paths": ["evaluation-report.json"],
                    "when": "always",
                    "expire_in": "30 days",
                },
                "rules": [{"if": "$CI_MERGE_REQUEST_IID"}],
            },
        }

        content = yaml.dump(config, default_flow_style=False, sort_keys=False)

        return CIPipelineResult(
            platform="gitlab-ci",
            file_path=".gitlab-ci.harness.yml",
            content=content,
        )
