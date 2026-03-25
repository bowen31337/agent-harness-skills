"""Tests for Jinja2 template engine utility."""

from __future__ import annotations

from harness_skills.utils.template_engine import (
    get_template_env,
    list_templates,
    render_template,
    template_exists,
)


class TestTemplateEngine:

    def test_get_template_env(self) -> None:
        env = get_template_env()
        assert env is not None
        # Calling again returns same instance (cached)
        assert get_template_env() is env

    def test_template_exists(self) -> None:
        assert template_exists("agents_md/root.md.j2") is True
        assert template_exists("nonexistent/nothing.j2") is False

    def test_list_templates(self) -> None:
        templates = list_templates()
        assert len(templates) >= 10
        assert any("root.md.j2" in t for t in templates)
        assert any("github_actions" in t for t in templates)

    def test_render_root_agents_md(self) -> None:
        output = render_template(
            "agents_md/root.md.j2",
            project_name="myapp",
            timestamp="2026-03-24",
            git_head="abc123",
            domains=["auth", "billing"],
            build_command="pytest tests/ -v",
            lint_command="ruff check .",
        )
        assert "# AGENTS.md — myapp" in output
        assert "auth" in output
        assert "billing" in output
        assert "Quick Reference" in output
        assert "CUSTOM-START" in output

    def test_render_root_agents_md_security_and_git_sections(self) -> None:
        output = render_template(
            "agents_md/root.md.j2",
            project_name="myapp",
            timestamp="2026-03-24",
            git_head="abc123",
            domains=[],
            build_command="pytest tests/ -v",
            lint_command="ruff check .",
        )
        assert "## Security Protocols" in output
        assert "Secret handling" in output
        assert "Input validation" in output
        assert "Dependency auditing" in output
        assert "## Git Workflow" in output
        assert "Branch naming" in output
        assert "Commit format" in output
        assert "PR process" in output
        assert "Squash-merge" in output

    def test_render_domain_agents_md(self) -> None:
        output = render_template(
            "agents_md/domain.md.j2",
            domain_name="auth",
            key_files=["auth/login.py", "auth/session.py"],
            patterns=["JWT-based authentication"],
            constraints=[],
        )
        assert "# auth/" in output
        assert "auth/login.py" in output
        assert "JWT-based" in output

    def test_render_architecture(self) -> None:
        output = render_template(
            "architecture/architecture.md.j2",
            timestamp="2026-03-24",
            domains=[{"name": "auth", "file_count": 5}, {"name": "billing", "file_count": 8}],
            layer_order=["UI → Service → Repository → Database"],
            layers=[],
        )
        assert "ARCHITECTURE.md" in output
        assert "auth" in output

    def test_render_architecture_with_mermaid_diagram(self) -> None:
        mermaid = "graph LR\n    auth[auth] --> billing[billing]"
        output = render_template(
            "architecture/architecture.md.j2",
            timestamp="2026-03-24",
            domains=[{"name": "auth", "file_count": 5}],
            layer_order=[],
            layers=[],
            mermaid_diagram=mermaid,
        )
        assert "## Dependency Flow" in output
        assert "### Module Dependency Graph" in output
        assert "```mermaid" in output
        assert "graph LR" in output
        assert "auth[auth] --> billing[billing]" in output

    def test_render_architecture_without_mermaid_diagram(self) -> None:
        output = render_template(
            "architecture/architecture.md.j2",
            timestamp="2026-03-24",
            domains=[],
            layer_order=[],
            layers=[],
        )
        assert "```mermaid" not in output
        assert "Module Dependency Graph" not in output

    def test_render_principles(self) -> None:
        output = render_template(
            "principles/principles.md.j2",
            timestamp="2026-03-24",
            principles=[{
                "id": "P001",
                "name": "No magic numbers",
                "rule": "Extract numeric literals to named constants.",
                "rationale": "Improves readability.",
                "example": "MAX_RETRIES = 3",
            }],
        )
        assert "PRINCIPLES.md" in output
        assert "P001" in output
        assert "No magic numbers" in output

    def test_render_evaluation(self) -> None:
        output = render_template(
            "evaluation/evaluation.md.j2",
            timestamp="2026-03-24",
            gates=[{"name": "Coverage", "id": "coverage", "threshold": "90%"}],
        )
        assert "EVALUATION.md" in output
        assert "Coverage" in output

    def test_cross_links_in_root_agents_md(self) -> None:
        output = render_template(
            "agents_md/root.md.j2",
            project_name="myapp",
            timestamp="2026-03-24",
            git_head="abc123",
            domains=[],
            build_command="pytest tests/ -v",
            lint_command="ruff check .",
        )
        assert "## Related Documentation" in output
        assert "[ARCHITECTURE.md](./ARCHITECTURE.md)" in output
        assert "[PRINCIPLES.md](./PRINCIPLES.md)" in output
        assert "[EVALUATION.md](./EVALUATION.md)" in output

    def test_cross_links_in_domain_agents_md(self) -> None:
        output = render_template(
            "agents_md/domain.md.j2",
            domain_name="auth",
            key_files=["auth/login.py"],
            patterns=[],
            constraints=[],
        )
        assert "## Related Documentation" in output
        assert "[AGENTS.md](../AGENTS.md)" in output
        assert "[ARCHITECTURE.md](../ARCHITECTURE.md)" in output
        assert "[PRINCIPLES.md](../PRINCIPLES.md)" in output

    def test_cross_links_in_architecture(self) -> None:
        output = render_template(
            "architecture/architecture.md.j2",
            timestamp="2026-03-24",
            domains=[],
            layer_order=[],
            layers=[],
        )
        assert "## Related Documentation" in output
        assert "[AGENTS.md](./AGENTS.md)" in output
        assert "[PRINCIPLES.md](./PRINCIPLES.md)" in output

    def test_cross_links_in_principles(self) -> None:
        output = render_template(
            "principles/principles.md.j2",
            timestamp="2026-03-24",
            principles=[],
        )
        assert "## Related Documentation" in output
        assert "[AGENTS.md](./AGENTS.md)" in output
        assert "[ARCHITECTURE.md](./ARCHITECTURE.md)" in output
        assert "[EVALUATION.md](./EVALUATION.md)" in output

    def test_cross_links_in_evaluation(self) -> None:
        output = render_template(
            "evaluation/evaluation.md.j2",
            timestamp="2026-03-24",
            gates=[],
        )
        assert "## Related Documentation" in output
        assert "[AGENTS.md](./AGENTS.md)" in output
        assert "[ARCHITECTURE.md](./ARCHITECTURE.md)" in output
        assert "[PRINCIPLES.md](./PRINCIPLES.md)" in output

    def test_render_plan(self) -> None:
        output = render_template(
            "exec_plans/plan.yaml.j2",
            plan_id="PLAN-001",
            title="Add auth",
            objective="Implement authentication",
            timestamp="2026-03-24",
        )
        assert "PLAN-001" in output
        assert "Add auth" in output

    def test_render_completion_report(self) -> None:
        output = render_template(
            "exec_plans/completion_report.md.j2",
            plan_id="PLAN-001",
            timestamp="2026-03-24",
            summary="Done",
            completed_tasks=["Task 1", "Task 2"],
            debt_items=[],
            followup=["Review tests"],
        )
        assert "PLAN-001" in output
        assert "Task 1" in output
        assert "Review tests" in output
