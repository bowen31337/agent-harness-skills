"""Unit tests for skills.golden_principles_cleanup.

All tests run entirely offline (no subprocess calls to harness or git).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from skills.golden_principles_cleanup import (
    CleanupTask,
    CleanupTaskManifest,
    GoldenPrinciplesCleanup,
    _slugify,
    main,
)

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

_PRINCIPLES_YAML = """\
version: "1.0"
principles:
  - id: "P001"
    category: "architecture"
    severity: "blocking"
    applies_to: ["review-pr", "check-code"]
    rule: "All database queries must go through the repository layer"

  - id: "P002"
    category: "testing"
    severity: "blocking"
    applies_to: ["review-pr"]
    rule: "Every public API endpoint must have an integration test"

  - id: "P003"
    category: "style"
    severity: "suggestion"
    applies_to: ["review-pr", "check-code"]
    rule: "Prefer dataclasses over plain dicts for structured data"
"""


def _write_principles(tmp_path: Path, content: str = _PRINCIPLES_YAML) -> Path:
    f = tmp_path / ".claude" / "principles.yaml"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")
    return f


def _make_violation(
    rule_id: str = "P001",
    file_path: str = "src/api/views.py",
    line_number: int | None = 42,
    message: str = "direct db.session usage",
    severity: str = "error",
    suggestion: str = "Use repository layer",
) -> dict:
    return {
        "rule_id": rule_id,
        "file_path": file_path,
        "line_number": line_number,
        "message": message,
        "severity": severity,
        "suggestion": suggestion,
        "gate_id": "principles",
    }


# ---------------------------------------------------------------------------
# TestLoadPrinciples
# ---------------------------------------------------------------------------

class TestLoadPrinciples:
    """load_principles must parse the YAML correctly and raise on errors."""

    def test_raises_on_missing_file(self, tmp_path: Path) -> None:
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)
        with pytest.raises(FileNotFoundError, match="not found"):
            cleanup.load_principles(tmp_path / "nonexistent.yaml")

    def test_returns_correct_structure(self, tmp_path: Path) -> None:
        principles_file = _write_principles(tmp_path)
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)
        principles = cleanup.load_principles(principles_file)

        assert len(principles) == 3
        p001 = principles[0]
        assert p001["id"] == "P001"
        assert p001["category"] == "architecture"
        assert p001["severity"] == "blocking"
        assert "repository layer" in p001["rule"]

    def test_raises_on_missing_principles_key(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text("version: '1.0'\n", encoding="utf-8")
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)
        with pytest.raises(ValueError, match="principles"):
            cleanup.load_principles(bad_file)

    def test_raises_on_missing_id_field(self, tmp_path: Path) -> None:
        bad_yaml = "version: '1.0'\nprinciples:\n  - rule: 'some rule'\n"
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text(bad_yaml, encoding="utf-8")
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)
        with pytest.raises(ValueError, match="id"):
            cleanup.load_principles(bad_file)

    def test_raises_on_missing_rule_field(self, tmp_path: Path) -> None:
        bad_yaml = "version: '1.0'\nprinciples:\n  - id: 'P001'\n"
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text(bad_yaml, encoding="utf-8")
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)
        with pytest.raises(ValueError, match="rule"):
            cleanup.load_principles(bad_file)

    def test_defaults_are_applied(self, tmp_path: Path) -> None:
        """Principles without optional fields should get sensible defaults."""
        minimal_yaml = "version: '1.0'\nprinciples:\n  - id: 'P001'\n    rule: 'Do the right thing'\n"
        f = tmp_path / "p.yaml"
        f.write_text(minimal_yaml, encoding="utf-8")
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)
        principles = cleanup.load_principles(f)

        assert principles[0]["category"] == "general"
        assert principles[0]["severity"] == "suggestion"

    def test_returns_empty_list_for_empty_principles(self, tmp_path: Path) -> None:
        empty_yaml = "version: '1.0'\nprinciples: []\n"
        f = tmp_path / "p.yaml"
        f.write_text(empty_yaml, encoding="utf-8")
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)
        principles = cleanup.load_principles(f)
        assert principles == []


# ---------------------------------------------------------------------------
# TestGroupViolations
# ---------------------------------------------------------------------------

class TestGroupViolations:
    """group_violations must cluster correctly by principle_id."""

    def test_groups_by_principle_id(self, tmp_path: Path) -> None:
        principles_file = _write_principles(tmp_path)
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)
        principles = cleanup.load_principles(principles_file)

        violations = [
            _make_violation("P001", "src/api/views.py"),
            _make_violation("P001", "src/api/orders.py"),
            _make_violation("P002", "src/api/users.py"),
        ]
        grouped = cleanup.group_violations(violations, principles)

        assert set(grouped.keys()) == {"P001", "P002"}
        assert len(grouped["P001"]) == 2
        assert len(grouped["P002"]) == 1

    def test_excludes_principles_with_no_violations(self, tmp_path: Path) -> None:
        principles_file = _write_principles(tmp_path)
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)
        principles = cleanup.load_principles(principles_file)

        # Only P001 has violations
        violations = [_make_violation("P001", "src/api/views.py")]
        grouped = cleanup.group_violations(violations, principles)

        assert "P001" in grouped
        assert "P002" not in grouped
        assert "P003" not in grouped

    def test_empty_violations_returns_empty_dict(self, tmp_path: Path) -> None:
        principles_file = _write_principles(tmp_path)
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)
        principles = cleanup.load_principles(principles_file)

        grouped = cleanup.group_violations([], principles)
        assert grouped == {}

    def test_unknown_rule_id_is_ignored(self, tmp_path: Path) -> None:
        principles_file = _write_principles(tmp_path)
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)
        principles = cleanup.load_principles(principles_file)

        violations = [_make_violation("P999", "src/nowhere.py")]
        grouped = cleanup.group_violations(violations, principles)

        assert "P999" not in grouped
        assert grouped == {}

    def test_preserves_principle_order(self, tmp_path: Path) -> None:
        principles_file = _write_principles(tmp_path)
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)
        principles = cleanup.load_principles(principles_file)

        violations = [
            _make_violation("P003", "src/utils/helpers.py"),
            _make_violation("P001", "src/api/views.py"),
        ]
        grouped = cleanup.group_violations(violations, principles)

        # Keys should be in the same order as principles YAML (P001 before P003)
        keys = list(grouped.keys())
        assert keys.index("P001") < keys.index("P003")


# ---------------------------------------------------------------------------
# TestGenerateTask
# ---------------------------------------------------------------------------

class TestGenerateTask:
    """generate_task must produce well-formed CleanupTask instances."""

    def _make_principle(
        self,
        pid: str = "P001",
        category: str = "architecture",
        severity: str = "blocking",
        rule: str = "All database queries must go through the repository layer",
    ) -> dict:
        return {
            "id": pid,
            "category": category,
            "severity": severity,
            "applies_to": ["review-pr", "check-code"],
            "rule": rule,
        }

    def test_returns_cleanup_task_instance(self, tmp_path: Path) -> None:
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)
        task = cleanup.generate_task(
            self._make_principle(),
            [_make_violation("P001", "src/api/views.py")],
        )
        assert isinstance(task, CleanupTask)

    def test_id_slug_format(self, tmp_path: Path) -> None:
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)
        task = cleanup.generate_task(
            self._make_principle("P001"),
            [_make_violation("P001", "src/api/views.py")],
        )
        assert task.id.startswith("cleanup-p001-")
        assert "src-api-views-py" in task.id

    def test_title_is_non_empty(self, tmp_path: Path) -> None:
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)
        task = cleanup.generate_task(
            self._make_principle(),
            [_make_violation()],
        )
        assert task.title
        assert len(task.title) > 10

    def test_description_contains_rule_and_files(self, tmp_path: Path) -> None:
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)
        task = cleanup.generate_task(
            self._make_principle(),
            [
                _make_violation("P001", "src/api/views.py", 88),
                _make_violation("P001", "src/api/orders.py", 42),
            ],
        )
        assert "P001" in task.description
        assert "repository layer" in task.description
        assert "src/api/views.py" in task.description
        assert "src/api/orders.py" in task.description
        assert "Refactoring steps" in task.description

    def test_pr_body_is_non_empty(self, tmp_path: Path) -> None:
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)
        task = cleanup.generate_task(self._make_principle(), [_make_violation()])
        assert task.pr_body
        assert "## What & Why" in task.pr_body
        assert "## Changes" in task.pr_body
        assert "## Testing" in task.pr_body
        assert "## Checklist" in task.pr_body

    def test_pr_title_contains_principle_id_and_category(self, tmp_path: Path) -> None:
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)
        task = cleanup.generate_task(self._make_principle(), [_make_violation()])
        assert "P001" in task.pr_title
        assert "architecture" in task.pr_title
        assert task.pr_title.startswith("refactor:")

    def test_scope_is_sorted_unique_files(self, tmp_path: Path) -> None:
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)
        violations = [
            _make_violation("P001", "src/b.py"),
            _make_violation("P001", "src/a.py"),
            _make_violation("P001", "src/a.py"),  # duplicate
        ]
        task = cleanup.generate_task(self._make_principle(), violations)
        assert task.scope == ["src/a.py", "src/b.py"]

    def test_status_is_pending(self, tmp_path: Path) -> None:
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)
        task = cleanup.generate_task(self._make_principle(), [_make_violation()])
        assert task.status == "pending"

    def test_severity_suggestion_principle(self, tmp_path: Path) -> None:
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)
        principle = self._make_principle(
            "P003", "style", "suggestion", "Prefer dataclasses over plain dicts"
        )
        task = cleanup.generate_task(principle, [_make_violation("P003", severity="warning")])
        assert task.severity == "suggestion"
        assert "P003" in task.pr_title

    def test_pr_title_with_one_file(self, tmp_path: Path) -> None:
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)
        task = cleanup.generate_task(
            self._make_principle(),
            [_make_violation("P001", "src/api/views.py")],
        )
        # Single file — should use the file name (not "N files")
        assert "views.py" in task.pr_title

    def test_pr_title_with_many_files(self, tmp_path: Path) -> None:
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)
        violations = [
            _make_violation("P001", f"src/module{i}.py") for i in range(5)
        ]
        task = cleanup.generate_task(self._make_principle(), violations)
        assert "5 files" in task.pr_title


# ---------------------------------------------------------------------------
# TestFallbackScan
# ---------------------------------------------------------------------------

class TestFallbackScan:
    """fallback_scan should find violations in source files."""

    def _make_repo(self, tmp_path: Path) -> tuple[Path, GoldenPrinciplesCleanup]:
        """Create a minimal fake repo with some source files."""
        src = tmp_path / "src" / "api"
        src.mkdir(parents=True)

        # This file contains a direct db.session call — violates P001
        (src / "views.py").write_text(
            "from db import session\n\ndef get_users():\n    return db.session.query(User).all()\n",
            encoding="utf-8",
        )
        # This file is clean
        (src / "clean.py").write_text(
            "from repositories.user_repo import UserRepository\n\ndef get_users():\n    return UserRepository.all()\n",
            encoding="utf-8",
        )

        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)
        return tmp_path, cleanup

    def test_finds_repository_violations(self, tmp_path: Path) -> None:
        _, cleanup = self._make_repo(tmp_path)
        principles = [
            {
                "id": "P001",
                "category": "architecture",
                "severity": "blocking",
                "applies_to": ["check-code"],
                "rule": "All database queries must go through the repository layer",
            }
        ]
        violations = cleanup.fallback_scan(principles)
        assert len(violations) > 0
        rule_ids = {v["rule_id"] for v in violations}
        assert "P001" in rule_ids

    def test_returns_gate_failure_shaped_dicts(self, tmp_path: Path) -> None:
        _, cleanup = self._make_repo(tmp_path)
        principles = [
            {
                "id": "P001",
                "category": "architecture",
                "severity": "blocking",
                "applies_to": ["check-code"],
                "rule": "All database queries must go through the repository layer",
            }
        ]
        violations = cleanup.fallback_scan(principles)
        for v in violations:
            assert "rule_id" in v
            assert "file_path" in v
            assert "message" in v
            assert "severity" in v
            assert "gate_id" in v

    def test_blocking_severity_maps_to_error(self, tmp_path: Path) -> None:
        _, cleanup = self._make_repo(tmp_path)
        principles = [
            {
                "id": "P001",
                "category": "architecture",
                "severity": "blocking",
                "applies_to": ["check-code"],
                "rule": "All database queries must go through the repository layer",
            }
        ]
        violations = cleanup.fallback_scan(principles)
        for v in violations:
            assert v["severity"] == "error"

    def test_suggestion_severity_maps_to_warning(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir(parents=True)
        (src / "helpers.py").write_text(
            "def get_data() -> dict:\n    return {'key': 'value'}\n",
            encoding="utf-8",
        )
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)
        principles = [
            {
                "id": "P003",
                "category": "style",
                "severity": "suggestion",
                "applies_to": ["check-code"],
                "rule": "Prefer dataclasses over plain dicts for structured data",
            }
        ]
        violations = cleanup.fallback_scan(principles)
        for v in violations:
            assert v["severity"] == "warning"

    def test_no_violations_when_files_are_clean(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir(parents=True)
        (src / "repo.py").write_text(
            "class UserRepository:\n    def all(self):\n        ...\n",
            encoding="utf-8",
        )
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)
        principles = [
            {
                "id": "P001",
                "category": "architecture",
                "severity": "blocking",
                "applies_to": ["check-code"],
                "rule": "All database queries must go through the repository layer",
            }
        ]
        violations = cleanup.fallback_scan(principles)
        # The clean repo file shouldn't trigger violations
        assert all(v["rule_id"] == "P001" for v in violations)
        # No db.session calls in the clean file
        p001_violations = [v for v in violations if v["rule_id"] == "P001"]
        assert len(p001_violations) == 0

    def test_excludes_venv_and_cache_dirs(self, tmp_path: Path) -> None:
        # Files in .venv or __pycache__ should be ignored
        venv_src = tmp_path / ".venv" / "lib" / "site-packages"
        venv_src.mkdir(parents=True)
        (venv_src / "some_lib.py").write_text(
            "x = db.session.query(User).all()\n", encoding="utf-8"
        )
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)
        principles = [
            {
                "id": "P001",
                "category": "architecture",
                "severity": "blocking",
                "applies_to": ["check-code"],
                "rule": "All database queries must go through the repository layer",
            }
        ]
        violations = cleanup.fallback_scan(principles)
        for v in violations:
            assert ".venv" not in v["file_path"]

    def test_unknown_rule_returns_no_violations(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir(parents=True)
        (src / "app.py").write_text("x = 1\n", encoding="utf-8")
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)
        principles = [
            {
                "id": "P099",
                "category": "misc",
                "severity": "suggestion",
                "applies_to": ["check-code"],
                "rule": "Use descriptive variable names",
            }
        ]
        violations = cleanup.fallback_scan(principles)
        # No heuristic for this rule — should return empty
        assert violations == []


# ---------------------------------------------------------------------------
# TestGenerateAll
# ---------------------------------------------------------------------------

class TestGenerateAll:
    """generate_all wires together all stages and writes the output file."""

    def test_empty_manifest_when_no_violations(self, tmp_path: Path) -> None:
        """If there are no violations (and no source files), the manifest is empty."""
        principles_file = _write_principles(tmp_path)
        output_file = tmp_path / "cleanup-tasks.yaml"
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)

        manifest = cleanup.generate_all(
            principles_file=principles_file,
            output_file=output_file,
            only_blocking=False,
            dry_run=False,
        )

        assert manifest.task_count == 0
        assert manifest.tasks == []
        assert output_file.exists()

    def test_writes_yaml_file_with_correct_structure(self, tmp_path: Path) -> None:
        """generate_all must write a parseable YAML file with the right keys."""
        # Create a source file that will trigger a P001 violation
        src = tmp_path / "src"
        src.mkdir()
        (src / "views.py").write_text(
            "result = db.session.query(User).all()\n", encoding="utf-8"
        )
        principles_file = _write_principles(tmp_path)
        output_file = tmp_path / "docs" / "exec-plans" / "cleanup-tasks.yaml"
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)

        manifest = cleanup.generate_all(
            principles_file=principles_file,
            output_file=output_file,
            only_blocking=False,
            dry_run=False,
        )

        assert output_file.exists()
        raw = yaml.safe_load(output_file.read_text(encoding="utf-8"))

        assert "generated_at" in raw
        assert "generated_from_head" in raw
        assert "task_count" in raw
        assert "tasks" in raw
        assert raw["task_count"] == manifest.task_count

    def test_dry_run_does_not_write_file(self, tmp_path: Path, capsys) -> None:
        principles_file = _write_principles(tmp_path)
        output_file = tmp_path / "cleanup-tasks.yaml"
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)

        cleanup.generate_all(
            principles_file=principles_file,
            output_file=output_file,
            only_blocking=False,
            dry_run=True,
        )

        assert not output_file.exists()
        captured = capsys.readouterr()
        assert "dry-run" in captured.out

    def test_only_blocking_skips_suggestion_principles(self, tmp_path: Path) -> None:
        # Create source files that would trigger both P001 and P003
        src = tmp_path / "src"
        src.mkdir()
        (src / "mixed.py").write_text(
            "result = db.session.query(User).all()\ndef f() -> dict:\n    return {'a': 1}\n",
            encoding="utf-8",
        )
        principles_file = _write_principles(tmp_path)
        output_file = tmp_path / "cleanup-tasks.yaml"
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)

        manifest = cleanup.generate_all(
            principles_file=principles_file,
            output_file=output_file,
            only_blocking=True,
            dry_run=False,
        )

        severities = {t.severity for t in manifest.tasks}
        assert "suggestion" not in severities

    def test_creates_output_directory_if_missing(self, tmp_path: Path) -> None:
        principles_file = _write_principles(tmp_path)
        output_file = tmp_path / "new" / "nested" / "dir" / "cleanup-tasks.yaml"
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)

        cleanup.generate_all(
            principles_file=principles_file,
            output_file=output_file,
            only_blocking=False,
            dry_run=False,
        )

        assert output_file.exists()

    def test_raises_file_not_found_for_missing_principles(self, tmp_path: Path) -> None:
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)
        with pytest.raises(FileNotFoundError):
            cleanup.generate_all(
                principles_file=tmp_path / "missing.yaml",
                output_file=tmp_path / "out.yaml",
                only_blocking=False,
                dry_run=False,
            )

    def test_manifest_generated_at_is_set(self, tmp_path: Path) -> None:
        principles_file = _write_principles(tmp_path)
        output_file = tmp_path / "cleanup-tasks.yaml"
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)

        manifest = cleanup.generate_all(
            principles_file=principles_file,
            output_file=output_file,
            only_blocking=False,
            dry_run=False,
        )

        assert manifest.generated_at
        assert "T" in manifest.generated_at  # ISO-8601 format

    def test_manifest_generated_from_head_is_set(self, tmp_path: Path) -> None:
        principles_file = _write_principles(tmp_path)
        output_file = tmp_path / "cleanup-tasks.yaml"
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)

        manifest = cleanup.generate_all(
            principles_file=principles_file,
            output_file=output_file,
            only_blocking=False,
            dry_run=False,
        )

        # Will be "no-git" in a test environment without git, but must be non-empty
        assert manifest.generated_from_head


# ---------------------------------------------------------------------------
# TestCleanupTaskManifest
# ---------------------------------------------------------------------------

class TestCleanupTaskManifest:
    """CleanupTaskManifest and CleanupTask must be Pydantic-serialisable."""

    def _make_task(self, pid: str = "P001") -> CleanupTask:
        return CleanupTask(
            id=f"cleanup-{pid.lower()}-src-api-views-py",
            principle_id=pid,
            principle_category="architecture",
            severity="blocking",
            title=f"Enforce repository layer ({pid})",
            scope=["src/api/views.py", "src/api/orders.py"],
            description="Principle P001 violated.",
            pr_title=f"refactor: enforce {pid} architecture",
            pr_body="## What & Why\n...",
            generated_at="2026-03-22T10:00:00Z",
            status="pending",
        )

    def test_manifest_is_json_serialisable(self) -> None:
        manifest = CleanupTaskManifest(
            generated_at="2026-03-22T10:00:00Z",
            generated_from_head="abc1234",
            task_count=1,
            tasks=[self._make_task()],
        )
        dumped = manifest.model_dump_json()
        parsed = json.loads(dumped)
        assert "tasks" in parsed
        assert parsed["task_count"] == 1

    def test_task_is_json_serialisable(self) -> None:
        task = self._make_task()
        dumped = task.model_dump_json()
        parsed = json.loads(dumped)
        assert parsed["principle_id"] == "P001"
        assert parsed["status"] == "pending"
        assert isinstance(parsed["scope"], list)

    def test_task_default_status_is_pending(self) -> None:
        task = CleanupTask(
            id="cleanup-p001-src",
            principle_id="P001",
            principle_category="architecture",
            severity="blocking",
            title="Some title",
            scope=["src/file.py"],
            description="Some description",
            pr_title="refactor: enforce P001",
            pr_body="## What & Why\n...",
            generated_at="2026-03-22T10:00:00Z",
        )
        assert task.status == "pending"

    def test_manifest_with_no_tasks(self) -> None:
        manifest = CleanupTaskManifest(
            generated_at="2026-03-22T10:00:00Z",
            generated_from_head="abc1234",
            task_count=0,
            tasks=[],
        )
        dumped = manifest.model_dump()
        assert dumped["task_count"] == 0
        assert dumped["tasks"] == []

    def test_manifest_task_count_consistent_with_tasks_list(self) -> None:
        tasks = [self._make_task("P001"), self._make_task("P002")]
        manifest = CleanupTaskManifest(
            generated_at="2026-03-22T10:00:00Z",
            generated_from_head="abc1234",
            task_count=len(tasks),
            tasks=tasks,
        )
        assert manifest.task_count == len(manifest.tasks)


# ---------------------------------------------------------------------------
# TestSlugify
# ---------------------------------------------------------------------------

class TestSlugify:
    """_slugify must produce clean, predictable slugs."""

    @pytest.mark.parametrize(
        "input_text, expected",
        [
            ("src/api/views.py", "src-api-views-py"),
            ("P001", "p001"),
            ("src/utils/helpers.tsx", "src-utils-helpers-tsx"),
            ("src\\windows\\path.py", "src-windows-path-py"),
            ("--leading-dash", "leading-dash"),
            ("trailing-dash--", "trailing-dash"),
            ("multiple---dashes", "multiple-dashes"),
            ("UPPER_CASE.py", "upper-case-py"),
            ("src/deeply/nested/module/file.py", "src-deeply-nested-module-file-py"),
        ],
    )
    def test_slugify(self, input_text: str, expected: str) -> None:
        assert _slugify(input_text) == expected

    def test_no_leading_or_trailing_dashes(self) -> None:
        result = _slugify("/leading/slash/file.py")
        assert not result.startswith("-")
        assert not result.endswith("-")

    def test_only_lowercase_alphanumeric_and_dashes(self) -> None:
        result = _slugify("Complex_Path/With Spaces & Special#Chars.ts")
        assert all(c.isalpha() or c.isdigit() or c == "-" for c in result)
        assert result == result.lower()


# ---------------------------------------------------------------------------
# TestListCommand (CLI integration)
# ---------------------------------------------------------------------------

class TestListCommand:
    """The `list` subcommand should print a summary table from an existing file."""

    def _write_cleanup_yaml(self, tmp_path: Path) -> Path:
        output_file = tmp_path / "cleanup-tasks.yaml"
        data = {
            "generated_at": "2026-03-22T10:00:00Z",
            "generated_from_head": "abc1234",
            "task_count": 2,
            "tasks": [
                {
                    "id": "cleanup-p001-src-api-views-py",
                    "principle_id": "P001",
                    "principle_category": "architecture",
                    "severity": "blocking",
                    "title": "Enforce repository layer (P001)",
                    "scope": ["src/api/views.py", "src/api/orders.py"],
                    "description": "Principle P001 violated.",
                    "pr_title": "refactor: enforce P001 architecture across views.py, orders.py",
                    "pr_body": "## What & Why\n...",
                    "generated_at": "2026-03-22T10:00:00Z",
                    "status": "pending",
                },
                {
                    "id": "cleanup-p003-src-utils-helpers-py",
                    "principle_id": "P003",
                    "principle_category": "style",
                    "severity": "suggestion",
                    "title": "Enforce style rule (P003)",
                    "scope": ["src/utils/helpers.py"],
                    "description": "Principle P003 violated.",
                    "pr_title": "refactor: enforce P003 style across helpers.py",
                    "pr_body": "## What & Why\n...",
                    "generated_at": "2026-03-22T10:00:00Z",
                    "status": "pending",
                },
            ],
        }
        output_file.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")
        return output_file

    def test_list_prints_task_ids(self, tmp_path: Path, capsys) -> None:
        output_file = self._write_cleanup_yaml(tmp_path)
        main(["list", "--output", str(output_file)])
        captured = capsys.readouterr()
        assert "cleanup-p001-src-api-views-py" in captured.out
        assert "cleanup-p003-src-utils-helpers-py" in captured.out

    def test_list_prints_principle_ids(self, tmp_path: Path, capsys) -> None:
        output_file = self._write_cleanup_yaml(tmp_path)
        main(["list", "--output", str(output_file)])
        captured = capsys.readouterr()
        assert "P001" in captured.out
        assert "P003" in captured.out

    def test_list_prints_severity_column(self, tmp_path: Path, capsys) -> None:
        output_file = self._write_cleanup_yaml(tmp_path)
        main(["list", "--output", str(output_file)])
        captured = capsys.readouterr()
        assert "blocking" in captured.out
        assert "suggestion" in captured.out

    def test_list_prints_status_column(self, tmp_path: Path, capsys) -> None:
        output_file = self._write_cleanup_yaml(tmp_path)
        main(["list", "--output", str(output_file)])
        captured = capsys.readouterr()
        assert "pending" in captured.out

    def test_list_exits_with_error_if_file_missing(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["list", "--output", str(tmp_path / "nonexistent.yaml")])
        assert exc_info.value.code != 0

    def test_generate_then_list_round_trip(self, tmp_path: Path, capsys) -> None:
        """generate followed by list should print the same principle IDs."""
        # Create a source file with a violation to ensure at least one task
        src = tmp_path / "src"
        src.mkdir()
        (src / "views.py").write_text(
            "result = db.session.query(User).all()\n", encoding="utf-8"
        )
        principles_file = _write_principles(tmp_path)
        output_file = tmp_path / "cleanup-tasks.yaml"
        cleanup = GoldenPrinciplesCleanup(repo_root=tmp_path)

        manifest = cleanup.generate_all(
            principles_file=principles_file,
            output_file=output_file,
            only_blocking=False,
            dry_run=False,
        )

        # Reset capsys
        capsys.readouterr()

        main(["list", "--output", str(output_file)])
        captured = capsys.readouterr()

        for task in manifest.tasks:
            assert task.principle_id in captured.out
