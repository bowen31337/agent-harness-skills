"""Generic shell script CI fallback generator."""

from __future__ import annotations

from harness_skills.ci.base import BaseCIGenerator, CIPipelineResult


class ShellScriptGenerator(BaseCIGenerator):
    """Generates a standalone shell script for harness evaluate."""

    def platform(self) -> str:
        return "shell"

    def generate(
        self,
        *,
        primary_language: str = "python",
        python_version: str = "3.12",
        node_version: str = "20",
        gate_ids: list[str] | None = None,
        extra_setup: list[str] | None = None,
    ) -> CIPipelineResult:
        evaluate_cmd = "harness evaluate --output-format json"
        if gate_ids:
            for gid in gate_ids:
                evaluate_cmd += f" --gate {gid}"

        lines = [
            "#!/bin/bash",
            "set -euo pipefail",
            "",
            "# Harness Evaluate — CI validation script",
            f"# Generated for: {primary_language}",
            "",
            "# Check dependencies",
            'command -v harness >/dev/null 2>&1 || { echo "harness CLI not found. Install with: uv pip install agent-harness-skills"; exit 2; }',
            "",
        ]

        for cmd in (extra_setup or []):
            lines.append(f"# Setup: {cmd}")
            lines.append(cmd)
            lines.append("")

        lines.extend([
            "# Run evaluation gates",
            f'echo "Running: {evaluate_cmd}"',
            evaluate_cmd,
            "exit_code=$?",
            "",
            'if [ "$exit_code" -eq 0 ]; then',
            '    echo "All gates passed."',
            "else",
            '    echo "Gate failures detected (exit code: $exit_code)."',
            "fi",
            "",
            "exit $exit_code",
        ])

        content = "\n".join(lines) + "\n"

        return CIPipelineResult(
            platform="shell",
            file_path="scripts/harness-evaluate.sh",
            content=content,
        )
