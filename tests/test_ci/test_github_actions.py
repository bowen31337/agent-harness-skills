"""Tests for GitHub Actions CI generator."""

from __future__ import annotations

import yaml

from harness_skills.ci.github_actions import GitHubActionsGenerator


class TestGitHubActionsGenerator:

    def test_platform(self) -> None:
        assert GitHubActionsGenerator().platform() == "github-actions"

    def test_generate_python(self) -> None:
        g = GitHubActionsGenerator()
        result = g.generate(primary_language="python")
        assert result.platform == "github-actions"
        assert result.file_path == ".github/workflows/harness-evaluate.yml"

        workflow = yaml.safe_load(result.content)
        assert workflow["name"] == "Harness Evaluate"
        assert "pull_request" in workflow["on"]

        steps = workflow["jobs"]["evaluate"]["steps"]
        step_names = [s["name"] for s in steps]
        assert "Checkout" in step_names
        assert "Set up Python" in step_names
        assert "Install dependencies" in step_names
        assert "Run harness evaluate" in step_names

    def test_generate_typescript(self) -> None:
        result = GitHubActionsGenerator().generate(primary_language="typescript")
        workflow = yaml.safe_load(result.content)
        steps = workflow["jobs"]["evaluate"]["steps"]
        step_names = [s["name"] for s in steps]
        assert "Set up Node.js" in step_names

    def test_generate_go(self) -> None:
        result = GitHubActionsGenerator().generate(primary_language="go")
        workflow = yaml.safe_load(result.content)
        steps = workflow["jobs"]["evaluate"]["steps"]
        step_names = [s["name"] for s in steps]
        assert "Set up Go" in step_names

    def test_gate_ids(self) -> None:
        result = GitHubActionsGenerator().generate(gate_ids=["coverage", "types"])
        workflow = yaml.safe_load(result.content)
        evaluate_step = [s for s in workflow["jobs"]["evaluate"]["steps"] if s["name"] == "Run harness evaluate"][0]
        assert "--gate coverage" in evaluate_step["run"]
        assert "--gate types" in evaluate_step["run"]

    def test_extra_setup(self) -> None:
        result = GitHubActionsGenerator().generate(extra_setup=["apt-get install -y libfoo"])
        workflow = yaml.safe_load(result.content)
        steps = workflow["jobs"]["evaluate"]["steps"]
        assert any("libfoo" in s.get("run", "") for s in steps)

    def test_output_is_valid_yaml(self) -> None:
        result = GitHubActionsGenerator().generate()
        parsed = yaml.safe_load(result.content)
        assert isinstance(parsed, dict)
        assert "jobs" in parsed
