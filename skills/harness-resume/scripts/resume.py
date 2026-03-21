#!/usr/bin/env python3
"""
resume.py — Display the most recent plan state for agent context handoff.

Reads .claude/plan-progress.md (primary) or .plan_progress.jsonl (fallback)
and prints the structured plan state so a new agent session can orient itself.

Usage
-----
# Full plan state summary (default):
    python skills/harness-resume/scripts/resume.py

# Search hints only (fast orientation):
    python skills/harness-resume/scripts/resume.py --hints

# Machine-readable JSON:
    python skills/harness-resume/scripts/resume.py --json

# Use a non-default Markdown path:
    python skills/harness-resume/scripts/resume.py --md-path .claude/other.md

# Prefer JSONL over Markdown:
    python skills/harness-resume/scripts/resume.py --prefer jsonl
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make harness_skills importable when running this script directly
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from harness_skills.resume import main  # noqa: E402

if __name__ == "__main__":
    main()
