"""Jinja2 template engine for harness artifact generation.

Provides a pre-configured Jinja2 environment that loads templates from
the ``harness_skills/templates/`` package directory.

Usage::

    from harness_skills.utils.template_engine import render_template

    output = render_template("agents_md/root.md.j2", project_name="myapp", domains=["auth", "billing"])
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

# Templates live alongside the harness_skills package
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

_env: Environment | None = None


def get_template_env() -> Environment:
    """Return a configured Jinja2 Environment (cached)."""
    global _env  # noqa: PLW0603
    if _env is not None:
        return _env

    _env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(
            disabled_extensions=("md.j2", "yaml.j2", "yml.j2", "sh.j2", "py.j2")
        ),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    return _env


def render_template(template_name: str, **context: Any) -> str:
    """Render a named template with the given context variables."""
    env = get_template_env()
    tmpl = env.get_template(template_name)
    return tmpl.render(**context)


def template_exists(template_name: str) -> bool:
    """Check if a template file exists."""
    return (_TEMPLATES_DIR / template_name).exists()


def list_templates() -> list[str]:
    """List all available template files."""
    if not _TEMPLATES_DIR.exists():
        return []
    return sorted(
        str(p.relative_to(_TEMPLATES_DIR))
        for p in _TEMPLATES_DIR.rglob("*.j2")
    )
