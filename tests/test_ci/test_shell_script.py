"""Tests for shell script CI fallback generator."""

from __future__ import annotations

from harness_skills.ci.shell_script import ShellScriptGenerator


class TestShellScriptGenerator:

    def test_platform(self) -> None:
        assert ShellScriptGenerator().platform() == "shell"

    def test_generate_default(self) -> None:
        result = ShellScriptGenerator().generate()
        assert result.platform == "shell"
        assert result.file_path == "scripts/harness-evaluate.sh"
        assert result.content.startswith("#!/bin/bash")
        assert "set -euo pipefail" in result.content
        assert "harness evaluate" in result.content

    def test_generate_with_gates(self) -> None:
        result = ShellScriptGenerator().generate(gate_ids=["coverage", "types"])
        assert "--gate coverage" in result.content
        assert "--gate types" in result.content

    def test_generate_with_extra_setup(self) -> None:
        result = ShellScriptGenerator().generate(extra_setup=["uv pip install extra"])
        assert "uv pip install extra" in result.content

    def test_language_in_comment(self) -> None:
        result = ShellScriptGenerator().generate(primary_language="go")
        assert "go" in result.content

    def test_dependency_check(self) -> None:
        result = ShellScriptGenerator().generate()
        assert "command -v harness" in result.content
