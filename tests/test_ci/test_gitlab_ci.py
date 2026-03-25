"""Tests for GitLab CI generator."""

from __future__ import annotations

import yaml

from harness_skills.ci.gitlab_ci import GitLabCIGenerator


class TestGitLabCIGenerator:

    def test_platform(self) -> None:
        assert GitLabCIGenerator().platform() == "gitlab-ci"

    def test_generate_python(self) -> None:
        result = GitLabCIGenerator().generate(primary_language="python")
        assert result.platform == "gitlab-ci"
        assert result.file_path == ".gitlab-ci.harness.yml"

        config = yaml.safe_load(result.content)
        assert "stages" in config
        assert "evaluate" in config["stages"]
        assert "harness-evaluate" in config
        job = config["harness-evaluate"]
        assert job["image"] == "python:3.12-slim"
        assert any("harness evaluate" in s for s in job["script"])

    def test_generate_go(self) -> None:
        result = GitLabCIGenerator().generate(primary_language="go")
        config = yaml.safe_load(result.content)
        assert config["harness-evaluate"]["image"] == "golang:1.21"

    def test_gate_ids(self) -> None:
        result = GitLabCIGenerator().generate(gate_ids=["regression", "lint"])
        config = yaml.safe_load(result.content)
        script = config["harness-evaluate"]["script"]
        evaluate = [s for s in script if "harness evaluate" in s][0]
        assert "--gate regression" in evaluate
        assert "--gate lint" in evaluate

    def test_output_is_valid_yaml(self) -> None:
        result = GitLabCIGenerator().generate()
        parsed = yaml.safe_load(result.content)
        assert isinstance(parsed, dict)
