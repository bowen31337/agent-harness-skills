"""Tests for standalone harness init script."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SHELL_SCRIPT = Path("scripts/harness-init.sh")


class TestHarnessInit:

    def test_script_exists(self) -> None:
        assert Path("scripts/harness_init.py").exists()

    def test_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/harness_init.py", "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "profile" in result.stdout.lower()

    def test_dry_run(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        result = subprocess.run(
            [
                sys.executable, "scripts/harness_init.py",
                "--project-root", str(tmp_path),
                "--dry-run",
            ],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "dry-run" in result.stdout
        assert "Python" in result.stdout
        # No file should be written
        assert not (tmp_path / "harness.config.yaml").exists()

    def test_creates_config(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text('{"name":"test"}')
        result = subprocess.run(
            [
                sys.executable, "scripts/harness_init.py",
                "--project-root", str(tmp_path),
                "--profile", "standard",
            ],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        config_file = tmp_path / "harness.config.yaml"
        assert config_file.exists()
        content = config_file.read_text()
        assert "standard" in content
        assert "JavaScript" in content

    def test_invalid_dir(self, tmp_path: Path) -> None:
        result = subprocess.run(
            [
                sys.executable, "scripts/harness_init.py",
                "--project-root", str(tmp_path / "nonexistent"),
            ],
            capture_output=True, text=True,
        )
        assert result.returncode == 1


class TestHarnessInitShell:
    """Tests for the POSIX shell harness-init.sh script."""

    def test_shell_script_exists_and_executable(self) -> None:
        assert SHELL_SCRIPT.exists(), "scripts/harness-init.sh must exist"
        assert os.access(SHELL_SCRIPT, os.X_OK), "scripts/harness-init.sh must be executable"

    def test_shell_help_exits_zero(self) -> None:
        result = subprocess.run(
            ["/bin/sh", str(SHELL_SCRIPT), "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "profile" in result.stdout.lower()

    def test_shell_detects_python_creates_config(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = subprocess.run(
            ["/bin/sh", str(SHELL_SCRIPT), "--project-root", str(tmp_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        config_file = tmp_path / "harness.config.yaml"
        assert config_file.exists(), "harness.config.yaml must be created"
        content = config_file.read_text()
        assert "Python" in content
        assert "starter" in content

    def test_shell_detects_node(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text('{"name":"test"}')
        result = subprocess.run(
            ["/bin/sh", str(SHELL_SCRIPT), "--project-root", str(tmp_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        content = (tmp_path / "harness.config.yaml").read_text()
        assert "JavaScript" in content

    def test_shell_detects_go(self, tmp_path: Path) -> None:
        (tmp_path / "go.mod").write_text("module example.com/test\n")
        result = subprocess.run(
            ["/bin/sh", str(SHELL_SCRIPT), "--project-root", str(tmp_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        content = (tmp_path / "harness.config.yaml").read_text()
        assert "Go" in content

    def test_shell_detects_rust(self, tmp_path: Path) -> None:
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"\n')
        result = subprocess.run(
            ["/bin/sh", str(SHELL_SCRIPT), "--project-root", str(tmp_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        content = (tmp_path / "harness.config.yaml").read_text()
        assert "Rust" in content

    def test_shell_no_indicators_unknown(self, tmp_path: Path) -> None:
        result = subprocess.run(
            ["/bin/sh", str(SHELL_SCRIPT), "--project-root", str(tmp_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        content = (tmp_path / "harness.config.yaml").read_text()
        assert "unknown" in content

    def test_shell_posix_compatible(self) -> None:
        """Verify no bashisms beyond set -e."""
        content = SHELL_SCRIPT.read_text()
        assert content.startswith("#!/bin/sh"), "Shebang must be #!/bin/sh"
        assert "[[" not in content, "Must not use [[ ]] (bash-only)"
        assert "BASH_SOURCE" not in content, "Must not use BASH_SOURCE"
