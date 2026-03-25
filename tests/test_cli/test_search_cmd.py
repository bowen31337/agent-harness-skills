"""Tests for harness search command."""

from __future__ import annotations

import json

from click.testing import CliRunner

from harness_skills.cli.main import cli


class TestSearchCmd:
    runner = CliRunner()

    def test_help(self) -> None:
        result = self.runner.invoke(cli, ["search", "--help"])
        assert result.exit_code == 0

    def test_exact_match(self, tmp_path) -> None:
        sym_file = tmp_path / "symbols.json"
        sym_file.write_text(json.dumps([
            {"name": "GateRunner", "type": "class", "file": "gates/runner.py", "line": 10},
            {"name": "detect_stack", "type": "function", "file": "codebase_analyzer.py", "line": 5},
        ]))
        result = self.runner.invoke(
            cli,
            ["search", "GateRunner", "--symbols-file", str(sym_file), "--output-format", "json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total_matches"] == 1
        assert data["results"][0]["name"] == "GateRunner"
        assert data["results"][0]["score"] == 1.0

    def test_substring_match(self, tmp_path) -> None:
        sym_file = tmp_path / "symbols.json"
        sym_file.write_text(json.dumps([
            {"name": "GateRunner", "type": "class", "file": "runner.py", "line": 1},
            {"name": "GateResult", "type": "class", "file": "base.py", "line": 2},
        ]))
        result = self.runner.invoke(
            cli,
            ["search", "Gate", "--symbols-file", str(sym_file), "--output-format", "json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total_matches"] == 2

    def test_type_filter(self, tmp_path) -> None:
        sym_file = tmp_path / "symbols.json"
        sym_file.write_text(json.dumps([
            {"name": "run_gate", "type": "function", "file": "a.py", "line": 1},
            {"name": "GateRunner", "type": "class", "file": "b.py", "line": 2},
        ]))
        result = self.runner.invoke(
            cli,
            ["search", "gate", "--symbols-file", str(sym_file), "--type", "class", "--output-format", "json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total_matches"] == 1
        assert data["results"][0]["kind"] == "class"

    def test_max_results(self, tmp_path) -> None:
        sym_file = tmp_path / "symbols.json"
        symbols = [{"name": f"test_{i}", "type": "function", "file": "t.py", "line": i} for i in range(50)]
        sym_file.write_text(json.dumps(symbols))
        result = self.runner.invoke(
            cli,
            ["search", "test", "--symbols-file", str(sym_file), "--max-results", "5", "--output-format", "json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["results"]) == 5

    def test_no_match_exits_1(self, tmp_path) -> None:
        sym_file = tmp_path / "symbols.json"
        sym_file.write_text(json.dumps([
            {"name": "Foo", "type": "class", "file": "foo.py", "line": 1},
        ]))
        result = self.runner.invoke(
            cli,
            ["search", "nonexistent", "--symbols-file", str(sym_file)],
        )
        assert result.exit_code == 1

    def test_missing_symbols_file_exits_1(self) -> None:
        result = self.runner.invoke(
            cli,
            ["search", "anything", "--symbols-file", "/tmp/does_not_exist.json"],
        )
        assert result.exit_code == 1
