"""Tests for CI architecture check script."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

# Ensure the project root is on PYTHONPATH for subprocess calls
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)


def _run_script(*args: str) -> subprocess.CompletedProcess:
    """Run ci_arch_check.py with the project root on PYTHONPATH."""
    env = os.environ.copy()
    env["PYTHONPATH"] = _PROJECT_ROOT + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, os.path.join(_PROJECT_ROOT, "scripts", "ci_arch_check.py"), *args],
        capture_output=True, text=True, env=env,
    )


class TestCIArchCheck:

    def test_script_exists(self) -> None:
        script = Path("scripts/ci_arch_check.py")
        assert script.exists()

    def test_script_help(self) -> None:
        result = _run_script("--help")
        assert result.returncode == 0
        assert "architecture" in result.stdout.lower()

    def test_missing_config(self, tmp_path: Path) -> None:
        result = _run_script("--config", str(tmp_path / "nonexistent.yaml"))
        assert result.returncode == 2

    def test_clean_project(self, tmp_path: Path) -> None:
        config = {
            "active_profile": "test",
            "profiles": {
                "test": {
                    "gates": {
                        "architecture": {
                            "arch_style": "layered",
                        },
                    },
                },
            },
        }
        cfg_file = tmp_path / "harness.config.yaml"
        with cfg_file.open("w") as f:
            yaml.dump(config, f)

        # Create a simple Python file with no violations
        (tmp_path / "app.py").write_text("import os\n")

        result = _run_script(
            "--config", str(cfg_file),
            "--project-root", str(tmp_path),
        )
        assert result.returncode == 0
        assert "No architecture violations" in result.stdout
