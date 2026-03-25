# Ralph Loop Agent Instructions

## Project
agent-harness-skills — Python 3.12, Click CLI, Pydantic v2, pytest

## How to Run Tests
```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/ -o "addopts=" -q --ignore=tests/browser --ignore=tests/gates/test_agents_md_token.py
```

## Key Directories
- `harness_skills/` — main package
- `harness_skills/templates/` — Jinja2 templates (.j2 files)
- `harness_skills/gates/principles.py` — principles scanners
- `harness_skills/generators/` — code generators
- `harness_skills/models/` — Pydantic models
- `tests/` — pytest test suite

## Workflow
1. Read `prd.json` — find next story with `passes: false`
2. Read `progress.txt` — understand what's been done
3. Implement the story
4. Run tests
5. If pass: update `prd.json` (set `passes: true`), update `progress.txt`
6. If fail: fix and retry
