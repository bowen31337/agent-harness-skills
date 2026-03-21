"""
harness_telemetry.py
====================
Telemetry hooks for the claw-forge agent harness.

Attaches to a ``claude_agent_sdk`` session via ``ClaudeAgentOptions(hooks=...)``
and records three categories of usage data, persisting them atomically to
``docs/harness-telemetry.json``:

  1. **Artifact reads**   — which harness files agents actually open
                            (PostToolUse on Read / Glob / Grep)
  2. **CLI commands**     — how often each ``.claude/commands/*.md`` skill is
                            invoked (UserPromptSubmit, detecting ``/<cmd>`` patterns)
  3. **Gate failures**    — which quality gates (ruff, mypy, pytest, …) fail most
                            (PostToolUse on Bash — parses exit-code markers in output)

Quick start
-----------
    from harness_telemetry import HarnessTelemetry
    from claude_agent_sdk import query, ClaudeAgentOptions

    tel = HarnessTelemetry()          # uses ./docs/harness-telemetry.json by default

    async for msg in query(
        prompt="...",
        options=ClaudeAgentOptions(
            allowed_tools=["Read", "Glob", "Grep", "Bash"],
            hooks=tel.build_hooks(),
        ),
    ):
        ...

    tel.flush()                       # persist immediately (also called on Stop hook)

CLI
---
    python harness_telemetry.py show       # pretty-print current totals
    python harness_telemetry.py reset      # wipe all recorded data
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "1.0"

#: Harness artifact extensions/names that are worth tracking.
_HARNESS_EXTENSIONS = {
    ".md", ".yaml", ".yml", ".toml", ".txt", ".xml", ".json", ".py",
}

#: Prefix of the .claude/commands directory — used to tag skill names.
_COMMANDS_PREFIX = ".claude/commands/"

#: Known CLI skill names (without the .md extension) — populated lazily.
_KNOWN_COMMANDS: set[str] = set()

#: Slash-command pattern:  /word-with-dashes  at the start of a prompt.
_SLASH_CMD_RE = re.compile(r"^/([a-z][a-z0-9-]*)", re.IGNORECASE)

# Map of (command-substring → gate-name) checked *in order* (longest match first).
_GATE_PATTERNS: list[tuple[str, str]] = [
    ("ruff check",      "ruff"),
    ("ruff format",     "ruff-format"),
    ("ruff",            "ruff"),
    ("mypy",            "mypy"),
    ("pytest",          "pytest"),
    ("check-code",      "check-code"),
]

# Substrings in Bash output that indicate a gate *failure*.
_FAILURE_MARKERS: list[str] = [
    "Found 1 error",   # ruff: singular
    "Found ",          # ruff: Found N errors / Found N fixable errors
    " error",          # mypy: "N error(s)" / "error: ..."
    "FAILED",          # pytest
    "failed",          # pytest summary  "N failed"
    "AssertionError",
    "exit code 1",
    "exit code 2",
    "returned non-zero",
]


# ---------------------------------------------------------------------------
# HarnessTelemetry
# ---------------------------------------------------------------------------

class HarnessTelemetry:
    """Collect and persist harness usage telemetry.

    Parameters
    ----------
    output_path:
        Where to write (and read) the JSON file.
        Defaults to ``docs/harness-telemetry.json`` relative to CWD.
    cwd:
        Working directory used to resolve relative paths in file-read events.
    """

    def __init__(
        self,
        output_path: str | Path = "docs/harness-telemetry.json",
        cwd: str | Path | None = None,
    ) -> None:
        self.output_path = Path(output_path)
        self.cwd = Path(cwd) if cwd else Path.cwd()

        # ── session-level counters (reset on each build_hooks() call) ──────
        self._session_id: str = ""
        self._session_started: str = ""
        self._session_ended: str = ""
        self._session_artifacts: dict[str, int] = defaultdict(int)
        self._session_commands: dict[str, int] = defaultdict(int)
        self._session_gates: dict[str, int] = defaultdict(int)

        # ── load existing totals from disk ───────────────────────────────
        self._data = self._load()

        # ── discover known CLI commands ──────────────────────────────────
        _discover_commands(self.cwd)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_hooks(self, session_id: str | None = None) -> dict[str, list[Any]]:
        """Return a *hooks* dict ready for ``ClaudeAgentOptions(hooks=...)``.

        Call once per SDK session.  Each subsequent ``build_hooks()`` call
        resets the per-session counters and starts a new logical session in the
        JSON output.
        """
        self._start_session(session_id or _iso_now())
        return {
            "SessionStart":  [_make_sync(self._on_session_start)],
            "SessionEnd":    [_make_sync(self._on_session_end)],
            "Stop":          [_make_sync(self._on_stop)],
            "UserPromptSubmit": [_make_sync(self._on_user_prompt)],
            "PostToolUse":   [
                {"matcher": "Read",            "hooks": [_make_sync(self._on_read)]},
                {"matcher": "Glob",            "hooks": [_make_sync(self._on_glob)]},
                {"matcher": "Grep",            "hooks": [_make_sync(self._on_grep)]},
                {"matcher": "Bash",            "hooks": [_make_sync(self._on_bash_post)]},
            ],
            "PostToolUseFailure": [
                {"matcher": "Bash",            "hooks": [_make_sync(self._on_bash_failure)]},
            ],
        }

    def flush(self) -> None:
        """Write current telemetry to ``output_path`` atomically."""
        self._finalise_session()
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.output_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.output_path)

    def show(self) -> None:
        """Print a human-readable summary to stdout."""
        d = self._data
        totals = d.get("totals", {})
        print(f"\n{'━' * 56}")
        print("  Harness Telemetry — totals")
        print(f"{'━' * 56}")
        _print_section("Artifact reads (top 10)",
                        totals.get("artifact_reads", {}), limit=10)
        _print_section("CLI command invocations",
                        totals.get("cli_command_invocations", {}))
        _print_section("Gate failures",
                        totals.get("gate_failures", {}))
        sessions = d.get("sessions", [])
        print(f"\n  Sessions recorded : {len(sessions)}")
        print(f"  Output file       : {self.output_path}")
        print(f"{'━' * 56}\n")

    def reset(self) -> None:
        """Wipe all recorded telemetry and overwrite the JSON file."""
        self._data = _empty_store()
        self.flush()
        print(f"[harness-telemetry] reset — {self.output_path}")

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def _start_session(self, session_id: str) -> None:
        self._session_id = session_id
        self._session_started = _iso_now()
        self._session_ended = ""
        self._session_artifacts = defaultdict(int)
        self._session_commands = defaultdict(int)
        self._session_gates = defaultdict(int)

    def _finalise_session(self) -> None:
        """Merge session counters into global totals and append session record."""
        if not self._session_id:
            return

        if not self._session_ended:
            self._session_ended = _iso_now()

        totals = self._data["totals"]
        _merge_counts(totals["artifact_reads"],         self._session_artifacts)
        _merge_counts(totals["cli_command_invocations"],self._session_commands)
        _merge_counts(totals["gate_failures"],          self._session_gates)

        self._data["last_updated"] = _iso_now()

        session_record = {
            "session_id":             self._session_id,
            "started_at":             self._session_started,
            "ended_at":               self._session_ended,
            "artifact_reads":         dict(self._session_artifacts),
            "cli_command_invocations":dict(self._session_commands),
            "gate_failures":          dict(self._session_gates),
        }
        # Deduplicate by session_id (replace if already present).
        sessions = self._data["sessions"]
        for i, s in enumerate(sessions):
            if s["session_id"] == self._session_id:
                sessions[i] = session_record
                return
        sessions.append(session_record)

    # ------------------------------------------------------------------
    # Hook callbacks
    # ------------------------------------------------------------------

    async def _on_session_start(self, input_data: dict, *_: Any) -> dict:
        sid = (
            input_data.get("session_id")
            or input_data.get("id")
            or self._session_id
        )
        if sid:
            self._session_id = str(sid)
        self._session_started = _iso_now()
        return {}

    async def _on_session_end(self, input_data: dict, *_: Any) -> dict:
        self._session_ended = _iso_now()
        return {}

    async def _on_stop(self, *_: Any) -> dict:
        """Persist when the agent stops."""
        self.flush()
        return {}

    async def _on_user_prompt(self, input_data: dict, *_: Any) -> dict:
        """Detect /command invocations in user prompts."""
        prompt: str = (
            input_data.get("prompt")
            or input_data.get("message")
            or input_data.get("content")
            or ""
        )
        prompt = prompt.strip()
        m = _SLASH_CMD_RE.match(prompt)
        if m:
            cmd = m.group(1).lower()
            self._session_commands[cmd] += 1
        return {}

    async def _on_read(self, input_data: dict, *_: Any) -> dict:
        """Track which files are opened with the Read tool."""
        path = _extract_path(input_data, keys=("file_path", "path"))
        if path:
            rel = _relativise(path, self.cwd)
            if _is_harness_artifact(rel):
                self._session_artifacts[rel] += 1
        return {}

    async def _on_glob(self, input_data: dict, *_: Any) -> dict:
        """Track Glob pattern use — record the pattern itself as an artifact key."""
        tool_input = input_data.get("tool_input") or input_data
        pattern = tool_input.get("pattern") or tool_input.get("glob") or ""
        if pattern:
            self._session_artifacts[f"[glob] {pattern}"] += 1
        # Also track each file returned in the output, if present.
        output = input_data.get("tool_output") or input_data.get("output") or ""
        if isinstance(output, str):
            for line in output.splitlines():
                line = line.strip()
                if line and _is_harness_artifact(line):
                    rel = _relativise(line, self.cwd)
                    self._session_artifacts[rel] += 1
        return {}

    async def _on_grep(self, input_data: dict, *_: Any) -> dict:
        """Track Grep — record pattern + any matching harness files."""
        tool_input = input_data.get("tool_input") or input_data
        pattern = tool_input.get("pattern") or tool_input.get("query") or ""
        path_arg = tool_input.get("path") or tool_input.get("directory") or ""
        key = f"[grep] {pattern}"
        if path_arg:
            key += f" in {_relativise(path_arg, self.cwd)}"
        self._session_artifacts[key] += 1
        return {}

    async def _on_bash_post(self, input_data: dict, *_: Any) -> dict:
        """Detect gate failures in successful Bash tool results."""
        command = _extract_bash_command(input_data)
        output  = _extract_bash_output(input_data)
        gate    = _identify_gate(command)
        if gate and _output_indicates_failure(output):
            self._session_gates[gate] += 1
        return {}

    async def _on_bash_failure(self, input_data: dict, *_: Any) -> dict:
        """Detect gate failures when the Bash tool itself errors out."""
        command = _extract_bash_command(input_data)
        gate    = _identify_gate(command)
        if gate:
            self._session_gates[gate] += 1
        else:
            # Unknown command failure — bucket it generically.
            self._session_gates["bash-failure"] += 1
        return {}

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> dict:
        if self.output_path.exists():
            try:
                return json.loads(self.output_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return _empty_store()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_store() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "last_updated":   _iso_now(),
        "totals": {
            "artifact_reads":          {},
            "cli_command_invocations": {},
            "gate_failures":           {},
        },
        "sessions": [],
    }


def _iso_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def _merge_counts(target: dict, source: dict) -> None:
    for key, count in source.items():
        target[key] = target.get(key, 0) + count


def _relativise(path: str, base: Path) -> str:
    """Return *path* relative to *base* if possible, else normalised absolute."""
    try:
        return str(Path(path).resolve().relative_to(base.resolve()))
    except ValueError:
        return str(Path(path).name)  # fallback: basename only


def _is_harness_artifact(path: str) -> bool:
    """Return True if *path* looks like a harness artifact worth tracking."""
    p = Path(path)
    # Always track files in .claude/, docs/, skills/, or the project root.
    parts = p.parts
    if any(part in {".claude", "docs", "skills", "harness_skills"} for part in parts):
        return True
    # Track root-level config / doc files.
    if len(parts) <= 2 and p.suffix in _HARNESS_EXTENSIONS:
        return True
    # Track anything in .venv only if explicitly categorised above.
    if ".venv" in parts:
        return False
    return p.suffix in _HARNESS_EXTENSIONS


def _extract_path(input_data: dict, keys: tuple[str, ...]) -> str:
    tool_input = input_data.get("tool_input") or input_data
    for k in keys:
        v = tool_input.get(k)
        if v:
            return str(v)
    return ""


def _extract_bash_command(input_data: dict) -> str:
    tool_input = input_data.get("tool_input") or input_data
    return str(
        tool_input.get("command")
        or tool_input.get("cmd")
        or tool_input.get("bash_command")
        or ""
    )


def _extract_bash_output(input_data: dict) -> str:
    return str(
        input_data.get("tool_output")
        or input_data.get("output")
        or input_data.get("result")
        or input_data.get("content")
        or ""
    )


def _identify_gate(command: str) -> str:
    """Map a shell command string to a gate name, or '' if not a gate command."""
    cmd_lower = command.lower()
    for substr, gate in _GATE_PATTERNS:
        if substr in cmd_lower:
            return gate
    return ""


def _output_indicates_failure(output: str) -> bool:
    """Heuristic: does the Bash output suggest the gate *failed*?"""
    for marker in _FAILURE_MARKERS:
        if marker in output:
            return True
    # Also check for non-zero exit-code annotations some shells/wrappers emit.
    if re.search(r"exit(?:ed)? (?:with )?(?:code )?[1-9]\d*", output, re.IGNORECASE):
        return True
    return False


def _discover_commands(cwd: Path) -> None:
    """Populate _KNOWN_COMMANDS from .claude/commands/*.md on disk."""
    cmds_dir = cwd / ".claude" / "commands"
    if cmds_dir.is_dir():
        for p in cmds_dir.glob("*.md"):
            _KNOWN_COMMANDS.add(p.stem)


def _make_sync(coro_fn: Any) -> Any:
    """Wrap an async hook as a sync callable when the SDK expects sync hooks.

    The Agent SDK accepts *both* sync and async hooks.  This wrapper tries the
    async path first and falls back gracefully.
    """
    # The SDK will await coroutine-returning callables automatically,
    # so we simply return the coroutine function as-is.
    return coro_fn


def _print_section(title: str, counts: dict, limit: int | None = None) -> None:
    print(f"\n  {title}:")
    if not counts:
        print("    (none recorded)")
        return
    sorted_items = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    if limit:
        sorted_items = sorted_items[:limit]
    width = max(len(k) for k, _ in sorted_items)
    for key, count in sorted_items:
        bar = "█" * min(count, 30)
        print(f"    {key:<{width}}  {count:>4}  {bar}")


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def _cli() -> None:
    output_path = Path("docs/harness-telemetry.json")
    tel = HarnessTelemetry(output_path=output_path)

    if len(sys.argv) < 2 or sys.argv[1] == "show":
        tel.show()
    elif sys.argv[1] == "reset":
        confirm = input("Reset ALL telemetry? [y/N] ").strip().lower()
        if confirm == "y":
            tel.reset()
        else:
            print("Aborted.")
    else:
        print(f"Usage: {sys.argv[0]} [show|reset]")
        sys.exit(1)


if __name__ == "__main__":
    _cli()
