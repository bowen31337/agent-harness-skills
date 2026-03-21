#!/usr/bin/env python3
"""
harness-context: Given a plan ID or domain name, returns a minimal set of file paths
and search patterns for agent-driven context assembly — without dumping file contents.

Usage:
    python harness_context.py "auth module"
    python harness_context.py "PLAN-42" --cwd /path/to/repo
    python harness_context.py "payment processing" --json
"""

import anyio
import argparse
import json
import sys
from typing import List

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ResultMessage,
    CLINotFoundError,
    CLIConnectionError,
    query,
)
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------

class ContextManifest(BaseModel):
    """Minimal context manifest returned by the harness — paths + patterns only."""

    file_paths: List[str] = Field(
        description="Specific file paths most relevant to the plan or domain, "
                    "ordered by relevance (most important first)."
    )
    search_patterns: List[str] = Field(
        description="Regex or glob patterns an assembler agent should search for "
                    "to gather additional context (e.g. symbol names, import paths, "
                    "config keys)."
    )
    glob_patterns: List[str] = Field(
        description="Glob patterns that match files belonging to this plan/domain "
                    "(e.g. 'src/auth/**/*.py', 'tests/**/test_payment*.py')."
    )
    rationale: str = Field(
        description="One or two sentences explaining why these paths and patterns "
                    "are the right entry points for this plan/domain."
    )


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a **context harvester** agent. Your only job is to produce a minimal,
precise manifest of file paths and search patterns for a given plan or domain —
you must NOT read or dump full file contents.

## Your process

1. **Explore structure** — Use Glob with broad patterns (e.g. `**/*.py`,
   `src/**`, `tests/**`) to map the repository layout.
2. **Narrow by name** — Use Glob with domain-specific patterns to find files
   whose *names* match the plan/domain (e.g. `**/auth*.py`, `**/*payment*`).
3. **Find symbols** — Use Grep to locate key identifiers, class names, function
   names, or config keys related to the domain. Keep searches focused; avoid
   reading whole files.
4. **Rank and trim** — Select only the most essential files. Prefer entry points,
   interfaces, and config files over deep implementation details.
5. **Return JSON** — Output a single JSON object matching the schema below.
   Nothing else — no prose, no markdown fences.

## Output schema (strict)

{
  "file_paths": ["path/to/most/relevant.py", ...],   // <= 15 files
  "search_patterns": ["ClassName", "CONSTANT_NAME", "import auth", ...],
  "glob_patterns": ["src/domain/**/*.py", "tests/**/test_domain*"],
  "rationale": "These files are the primary entry points for X because ..."
}

## Rules

- **Never** call Read, Write, Edit, Bash, or any tool not in [Glob, Grep].
- Keep `file_paths` to <= 15 entries; favour breadth over depth.
- `search_patterns` should be valid Python regex strings usable with `grep -E`.
- Output ONLY the raw JSON object — no surrounding text.
"""


# ---------------------------------------------------------------------------
# Core async function
# ---------------------------------------------------------------------------

async def get_context_manifest(
    plan_or_domain: str,
    cwd: str = ".",
    max_turns: int = 20,
) -> ContextManifest:
    """
    Run the context-harvester agent and return a ContextManifest.

    The agent is restricted to Glob + Grep so it can never modify files or
    read full file contents beyond what those tools surface.
    """
    prompt = (
        f"Produce a context manifest for: **{plan_or_domain}**\n\n"
        "Explore the repository with Glob and Grep, then return a single JSON "
        "object (no markdown, no prose) matching the required schema."
    )

    result_text: str | None = None

    async for message in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            cwd=cwd,
            allowed_tools=["Glob", "Grep"],
            system_prompt=SYSTEM_PROMPT,
            max_turns=max_turns,
            output_format={
                "type": "json_schema",
                "schema": ContextManifest.model_json_schema(),
            },
        ),
    ):
        if isinstance(message, ResultMessage):
            result_text = message.result

    if not result_text:
        return ContextManifest(
            file_paths=[],
            search_patterns=[],
            glob_patterns=[],
            rationale="Agent returned no result.",
        )

    # Parse and validate through Pydantic
    try:
        data = json.loads(result_text)
        return ContextManifest(**data)
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(
            f"Agent output could not be parsed as ContextManifest: {exc}\n"
            f"Raw output:\n{result_text}"
        ) from exc


# ---------------------------------------------------------------------------
# CLI rendering helpers
# ---------------------------------------------------------------------------

def _render_human(manifest: ContextManifest, plan_or_domain: str) -> None:
    """Print a human-readable summary of the manifest."""
    bar = "─" * 60
    print(f"\n{bar}")
    print(f"  Context manifest for: {plan_or_domain}")
    print(bar)

    print(f"\n  File Paths  ({len(manifest.file_paths)} files)")
    if manifest.file_paths:
        for i, path in enumerate(manifest.file_paths, 1):
            print(f"     {i:>2}. {path}")
    else:
        print("     (none found)")

    print(f"\n  Search Patterns  ({len(manifest.search_patterns)})")
    if manifest.search_patterns:
        for pattern in manifest.search_patterns:
            print(f"     {pattern}")
    else:
        print("     (none found)")

    print(f"\n  Glob Patterns  ({len(manifest.glob_patterns)})")
    if manifest.glob_patterns:
        for pattern in manifest.glob_patterns:
            print(f"     {pattern}")
    else:
        print("     (none found)")

    print(f"\n  Rationale")
    print(f"     {manifest.rationale}")
    print(f"\n{bar}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Return a minimal context manifest (file paths + search patterns) "
            "for a plan ID or domain name — no file contents dumped."
        )
    )
    parser.add_argument(
        "plan_or_domain",
        help="Plan ID (e.g. 'PLAN-42') or domain name (e.g. 'auth module')",
    )
    parser.add_argument(
        "--cwd",
        default=".",
        metavar="DIR",
        help="Repository root to search in (default: current directory)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Emit raw JSON instead of the human-readable summary",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=20,
        metavar="N",
        help="Maximum agent turns before stopping (default: 20)",
    )
    args = parser.parse_args()

    try:
        manifest = anyio.run(
            get_context_manifest,
            args.plan_or_domain,
            args.cwd,
            args.max_turns,
        )
    except CLINotFoundError:
        print(
            "ERROR: Claude Code CLI not found.\n"
            "Install it with:  pip install claude-agent-sdk",
            file=sys.stderr,
        )
        sys.exit(1)
    except CLIConnectionError as exc:
        print(f"ERROR: Could not connect to the Claude CLI: {exc}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.as_json:
        print(json.dumps(manifest.model_dump(), indent=2))
    else:
        _render_human(manifest, args.plan_or_domain)


if __name__ == "__main__":
    main()
