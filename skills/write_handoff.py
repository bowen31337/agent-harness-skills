#!/usr/bin/env python3
"""
write_handoff.py — Write a context handoff document from the command line.

Agents call this script to record a structured session summary (with search
hints) to .claude/plan-progress.md, the JSONL audit log (.plan_progress.jsonl),
and optionally the shared progress table (docs/exec-plans/progress.md).

This is the CLI counterpart to the Write-tool approach described in the
context-handoff SKILL.md.  Use it when you want to build the handoff
programmatically rather than composing the Markdown by hand.

Usage
-----
# Minimal — task + status + search hints:
python skills/write_handoff.py \\
    --task "Add JWT authentication" \\
    --status in_progress \\
    --key-files "src/auth/service.py" "src/config.py" \\
    --grep "class AuthService" "def validate_token" \\
    --symbols "AuthService" "JWT_SECRET"

# Full handoff with all fields:
python skills/write_handoff.py \\
    --task "Add JWT authentication" \\
    --status in_progress \\
    --session-id "sess_01JQKW..." \\
    --accomplished "Scaffolded AuthService" "Added JWT config to src/config.py" \\
    --in-progress "Wiring middleware into request handler (~30% done)" \\
    --next-steps "Import AuthService in gateway.py" "Wire into handle_request()" \\
    --key-files "src/auth/service.py — AuthService class" \\
               "src/api/gateway.py — wire here" \\
    --key-dirs "src/auth/" "src/api/" \\
    --grep "class AuthService" "def handle_request" "JWT_SECRET" \\
    --symbols "AuthService" "handle_request" "JWT_SECRET" \\
    --open-questions "Should tokens expire after 1h or 24h?" \\
    --artifacts "src/auth/service.py (new)" "src/config.py (modified)" \\
    --notes "Using PyJWT 2.x — import is jwt not JWT" \\
    --also-progress-log \\
    --plan-id "feature/jwt-auth" \\
    --agent-id "agent/coder-v1"
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure harness_skills is importable when called as a script
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from harness_skills.handoff import (  # noqa: E402
    HandoffDocument,
    HandoffProtocol,
    SearchHints,
    _DEFAULT_HANDOFF_PATH,
    _DEFAULT_JSONL_PATH,
    _append_jsonl,
    _append_progress_log_entry,
    _slugify,
)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="write_handoff.py",
        description=(
            "Write a context handoff document to .claude/plan-progress.md "
            "so the next agent can resume work using its own search tools."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # --- Core identity ---
    p.add_argument(
        "--task", required=True,
        help="One-line description of the overall task.",
    )
    p.add_argument(
        "--status", default="in_progress",
        choices=["in_progress", "blocked", "done"],
        help="Session status (default: in_progress).",
    )
    p.add_argument(
        "--session-id", default="unknown", dest="session_id",
        help="Agent SDK session ID, or 'unknown' (default).",
    )

    # --- Progress sections ---
    p.add_argument(
        "--accomplished", nargs="*", default=[], metavar="ITEM",
        help="Items completed in this session (repeat for multiple).",
    )
    p.add_argument(
        "--in-progress", nargs="*", default=[], metavar="ITEM",
        dest="in_progress",
        help="Partially-done work — include %% complete (repeat for multiple).",
    )
    p.add_argument(
        "--next-steps", nargs="*", default=[], metavar="STEP",
        dest="next_steps",
        help="Ordered actions for the next agent (repeat for multiple).",
    )

    # --- Search hints (the most important section) ---
    hint_group = p.add_argument_group(
        "search hints",
        "Pointers the next agent uses with its own Read/Grep/Glob tools.\n"
        "Provide paths and patterns — never paste file contents here.",
    )
    hint_group.add_argument(
        "--key-files", nargs="*", default=[], metavar="PATH",
        dest="key_files",
        help="Files the next agent should Read first (max 8, relative paths).",
    )
    hint_group.add_argument(
        "--key-dirs", nargs="*", default=[], metavar="DIR",
        dest="key_dirs",
        help="Directories to Glob for orientation.",
    )
    hint_group.add_argument(
        "--grep", nargs="*", default=[], metavar="PATTERN",
        help="Regex patterns to paste directly into the Grep tool.",
    )
    hint_group.add_argument(
        "--symbols", nargs="*", default=[], metavar="SYMBOL",
        help="Function / class / variable names to search for with Grep.",
    )

    # --- Supplementary ---
    p.add_argument(
        "--open-questions", nargs="*", default=[], metavar="QUESTION",
        dest="open_questions",
        help="Unresolved decisions or blockers the next agent must address.",
    )
    p.add_argument(
        "--artifacts", nargs="*", default=[], metavar="FILE",
        help="Files created or significantly modified in this session.",
    )
    p.add_argument(
        "--notes", default="",
        help="Free-form context that doesn't fit the structured fields.",
    )

    # --- Output paths ---
    p.add_argument(
        "--md-path", default=str(_DEFAULT_HANDOFF_PATH), dest="md_path",
        help=f"Markdown handoff output path (default: {_DEFAULT_HANDOFF_PATH}).",
    )
    p.add_argument(
        "--jsonl-path", default=str(_DEFAULT_JSONL_PATH), dest="jsonl_path",
        help=f"JSONL audit log path (default: {_DEFAULT_JSONL_PATH}).",
    )

    # --- Progress log integration ---
    p.add_argument(
        "--also-progress-log", action="store_true", dest="also_progress_log",
        help=(
            "Also append a summary row to docs/exec-plans/progress.md "
            "(requires skills/progress_log.py to be importable)."
        ),
    )
    p.add_argument(
        "--plan-id", default="", dest="plan_id",
        help=(
            "Plan ID for the progress log row. "
            "Defaults to a slug derived from --task."
        ),
    )
    p.add_argument(
        "--agent-id", default="unknown", dest="agent_id",
        help="Agent identifier for the progress log row (default: unknown).",
    )

    return p


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    doc = HandoffDocument(
        session_id=args.session_id,
        timestamp=timestamp,
        task=args.task,
        status=args.status,
        accomplished=args.accomplished or [],
        in_progress=args.in_progress or [],
        next_steps=args.next_steps or [],
        search_hints=SearchHints(
            file_paths=args.key_files or [],
            directories=args.key_dirs or [],
            grep_patterns=args.grep or [],
            symbols=args.symbols or [],
        ),
        open_questions=args.open_questions or [],
        artifacts=args.artifacts or [],
        notes=args.notes or "",
    )

    md_path = Path(args.md_path)
    jsonl_path = Path(args.jsonl_path)
    protocol = HandoffProtocol(handoff_path=md_path)

    # 1. Write Markdown handoff (overwrites any previous file — latest wins)
    protocol.write_handoff(doc)
    print(f"[write_handoff] wrote {md_path}", file=sys.stderr)

    # 2. Append JSONL entry (append-only audit trail)
    resume_prompt = protocol.resuming_system_prompt_addendum(doc)
    _append_jsonl(doc, jsonl_path=jsonl_path, resume_prompt=resume_prompt)
    print(f"[write_handoff] appended to {jsonl_path}", file=sys.stderr)

    # 3. Optional progress log row
    if args.also_progress_log:
        plan_id = args.plan_id or _slugify(args.task) or "unnamed"
        _append_progress_log_entry(doc, plan_id=plan_id, agent_id=args.agent_id)

    # Confirmation to stdout
    hints = doc.search_hints
    print(f"Handoff written: {md_path}")
    print(f"  Task     : {doc.task}")
    print(f"  Status   : {doc.status}")
    print(f"  Session  : {doc.session_id}")
    print(f"  Files    : {len(hints.file_paths)}")
    print(f"  Greps    : {len(hints.grep_patterns)}")
    print(f"  Symbols  : {len(hints.symbols)}")
    print(f"  JSONL    : {jsonl_path}")
    if doc.next_steps:
        print(f"  Next     : {doc.next_steps[0]}")


if __name__ == "__main__":
    main()
