"""Tests for cleanup task generation from pattern frequency data."""

from __future__ import annotations

from pathlib import Path

from harness_skills.generators.pattern_extractor import (
    PatternFrequency,
    generate_cleanup_tasks,
)


class TestGenerateCleanupTasks:

    def _make_patterns(self) -> list[PatternFrequency]:
        return [
            PatternFrequency(
                pattern_name="@dataclass",
                category="decorator",
                occurrences=15,
                example_files=["models/a.py", "models/b.py"],
                suggested_principle="Use @dataclass decorator consistently for this pattern.",
            ),
            PatternFrequency(
                pattern_name="extends BaseModel",
                category="base_class",
                occurrences=8,
                example_files=["gate.py"],
                suggested_principle="New components of this type should extend BaseModel.",
            ),
        ]

    def test_produces_valid_yaml_structure(self) -> None:
        result = generate_cleanup_tasks(self._make_patterns())
        assert isinstance(result, dict)
        assert "task_count" in result
        assert "tasks" in result
        assert isinstance(result["tasks"], list)

    def test_task_count_matches(self) -> None:
        patterns = self._make_patterns()
        result = generate_cleanup_tasks(patterns)
        assert result["task_count"] == len(patterns)

    def test_each_task_has_required_fields(self) -> None:
        result = generate_cleanup_tasks(self._make_patterns())
        required_fields = {"id", "title", "description", "file_glob", "estimated_effort"}
        for task in result["tasks"]:
            assert required_fields.issubset(task.keys()), (
                f"Missing fields: {required_fields - task.keys()}"
            )

    def test_tasks_derived_from_pattern_data(self) -> None:
        result = generate_cleanup_tasks(self._make_patterns())
        task = result["tasks"][0]
        assert "@dataclass" in task["title"]
        assert "15" in task["description"]
        assert "decorator" in task["description"]

    def test_task_ids_are_slugified(self) -> None:
        result = generate_cleanup_tasks(self._make_patterns())
        for task in result["tasks"]:
            assert task["id"].startswith("cleanup-")
            assert " " not in task["id"]
            assert "@" not in task["id"]

    def test_estimated_effort_values(self) -> None:
        patterns = [
            PatternFrequency(pattern_name="@small", category="decorator", occurrences=5),
            PatternFrequency(pattern_name="@medium", category="decorator", occurrences=20),
            PatternFrequency(pattern_name="@large", category="decorator", occurrences=40),
            PatternFrequency(pattern_name="@huge", category="decorator", occurrences=100),
        ]
        result = generate_cleanup_tasks(patterns)
        efforts = [t["estimated_effort"] for t in result["tasks"]]
        assert efforts == ["low", "medium", "high", "very-high"]

    def test_empty_patterns_produce_empty_tasks(self) -> None:
        result = generate_cleanup_tasks([])
        assert result["task_count"] == 0
        assert result["tasks"] == []

    def test_writes_yaml_to_output_path(self, tmp_path: Path) -> None:
        output = tmp_path / "docs" / "exec-plans" / "cleanup-tasks-generated.yaml"
        result = generate_cleanup_tasks(self._make_patterns(), output_path=output)
        assert output.exists()
        content = output.read_text()
        assert "task_count" in content
        assert "cleanup-" in content
        assert result["task_count"] == 2

    def test_file_glob_present(self) -> None:
        result = generate_cleanup_tasks(self._make_patterns())
        for task in result["tasks"]:
            assert task["file_glob"] == "**/*.py"
