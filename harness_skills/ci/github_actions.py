"""GitHub Actions workflow generator."""

from __future__ import annotations

import yaml

from harness_skills.ci.base import BaseCIGenerator, CIPipelineResult

_SETUP_ACTIONS: dict[str, dict] = {
    "python": {
        "name": "Set up Python",
        "uses": "actions/setup-python@v5",
        "with": {"python-version": "${{ matrix.python-version || '3.12' }}"},
    },
    "javascript": {
        "name": "Set up Node.js",
        "uses": "actions/setup-node@v4",
        "with": {"node-version": "${{ matrix.node-version || '20' }}"},
    },
    "typescript": {
        "name": "Set up Node.js",
        "uses": "actions/setup-node@v4",
        "with": {"node-version": "${{ matrix.node-version || '20' }}"},
    },
    "go": {
        "name": "Set up Go",
        "uses": "actions/setup-go@v5",
        "with": {"go-version": "${{ matrix.go-version || '1.21' }}"},
    },
}

_INSTALL_COMMANDS: dict[str, str] = {
    "python": "uv sync --frozen",
    "javascript": "npm ci",
    "typescript": "npm ci",
    "go": "go mod download",
}


class GitHubActionsGenerator(BaseCIGenerator):
    """Generates a GitHub Actions workflow for harness evaluate."""

    def platform(self) -> str:
        return "github-actions"

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

        steps = [
            {"name": "Checkout", "uses": "actions/checkout@v4"},
        ]

        # Language setup
        if lang in _SETUP_ACTIONS:
            steps.append(_SETUP_ACTIONS[lang])

        # Install dependencies
        install = _INSTALL_COMMANDS.get(lang, "echo 'No install step for this language'")
        steps.append({"name": "Install dependencies", "run": install})

        # Extra setup
        for cmd in (extra_setup or []):
            steps.append({"name": f"Setup: {cmd[:40]}", "run": cmd})

        # Harness evaluate
        evaluate_cmd = "harness evaluate --output-format json"
        if gate_ids:
            for gid in gate_ids:
                evaluate_cmd += f" --gate {gid}"
        steps.append({"name": "Run harness evaluate", "run": evaluate_cmd})

        # Upload results
        steps.append({
            "name": "Upload evaluation report",
            "uses": "actions/upload-artifact@v4",
            "if": "always()",
            "with": {
                "name": "harness-evaluation-report",
                "path": "evaluation-report.json",
                "retention-days": 30,
            },
        })

        workflow = {
            "name": "Harness Evaluate",
            "on": {"pull_request": {"branches": ["main", "master"]}},
            "jobs": {
                "evaluate": {
                    "runs-on": "ubuntu-latest",
                    "steps": steps,
                },
            },
        }

        content = yaml.dump(workflow, default_flow_style=False, sort_keys=False)

        return CIPipelineResult(
            platform="github-actions",
            file_path=".github/workflows/harness-evaluate.yml",
            content=content,
        )
