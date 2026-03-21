#!/usr/bin/env python3
"""
coordinate.py — Cross-agent task conflict dashboard for claw-forge harnesses.

Shows running agent status, detects file-level conflicts between agents, uses
Claude (via the Agent SDK) to suggest a task ordering that minimises merge
collisions, and displays the live task-lock state so operators can see which
plan tasks are currently locked and by whom.

Usage:
    python coordinate.py                          # live data from state service
    python coordinate.py --state-url http://...   # custom state service URL
    python coordinate.py --demo                   # demo data, no service needed
    python coordinate.py --json                   # JSON output for CI / piping
    python coordinate.py --locks-dir PATH         # custom lock directory
    python coordinate.py --no-locks               # skip the lock-state panel
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

import httpx
from dotenv import load_dotenv

load_dotenv()

# Task-lock integration (optional — gracefully absent if the package isn't installed)
try:
    from harness_skills.task_lock import TaskLock, TaskLockProtocol
    _LOCK_AVAILABLE = True
except ImportError:
    _LOCK_AVAILABLE = False

# ── Data model ────────────────────────────────────────────────────────────────

AgentStatus = Literal["pending", "running", "paused", "done", "blocked"]
ConflictSeverity = Literal["low", "medium", "high"]

STATUS_ICON = {
    "pending": "🟢",
    "running": "🟡",
    "paused":  "🔵",
    "done":    "✅",
    "blocked": "🔴",
}

SEVERITY_ICON = {
    "high":   "🔴 HIGH",
    "medium": "🟡 MED ",
    "low":    "🔵 LOW ",
}


@dataclass
class AgentTask:
    agent_id: str          # e.g. "agent-a"
    branch: str            # e.g. "feat/auth"
    task: str              # human description
    status: AgentStatus
    files: list[str] = field(default_factory=list)      # absolute/repo-relative paths
    file_line_ranges: dict[str, tuple[int, int]] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)  # agent_ids


@dataclass
class Conflict:
    agent_a: str
    agent_b: str
    shared_files: list[str]
    severity: ConflictSeverity
    detail: str = ""   # e.g. overlapping line ranges


@dataclass
class CoordinationReport:
    snapshot_time: str
    agents: list[AgentTask]
    conflicts: list[Conflict]
    suggested_slots: list[list[str]]   # each inner list = agents safe to run in parallel
    rationale: str
    savings_msg: str
    active_locks: list["TaskLock"] = field(default_factory=list)   # from TaskLockProtocol


# ── State service client ───────────────────────────────────────────────────────

async def fetch_from_state_service(state_url: str) -> list[AgentTask] | None:
    """Pull agent/task data from a running claw-forge state service."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{state_url}/agents")
            resp.raise_for_status()
            raw: list[dict] = resp.json()
    except Exception as exc:
        print(f"  ⚠️  State service unavailable ({exc}). Falling back to git.", file=sys.stderr)
        return None

    tasks: list[AgentTask] = []
    for entry in raw:
        tasks.append(AgentTask(
            agent_id=entry["agent_id"],
            branch=entry.get("branch", "unknown"),
            task=entry.get("task", "—"),
            status=entry.get("status", "running"),
            files=entry.get("files", []),
            file_line_ranges=entry.get("file_line_ranges", {}),
            dependencies=entry.get("dependencies", []),
        ))
    return tasks or None


# ── Git-based fallback ─────────────────────────────────────────────────────────

def _run(cmd: list[str], cwd: str | None = None) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    return result.stdout.strip()


def fetch_from_git() -> list[AgentTask]:
    """
    Enumerate feat/* branches, diff each against main/master, collect touched files.
    Uses branch name as a rough proxy for agent/task identity.
    """
    base = _run(["git", "rev-parse", "--show-toplevel"]) or "."
    main_branch = _run(["git", "rev-parse", "--verify", "main"], cwd=base)
    if not main_branch:
        main_branch = _run(["git", "rev-parse", "--verify", "master"], cwd=base)
    if not main_branch:
        main_branch = "HEAD"

    branches_raw = _run(["git", "branch", "--list", "feat/*", "--format=%(refname:short)"])
    branches = [b.strip() for b in branches_raw.splitlines() if b.strip()]

    if not branches:
        return []

    tasks: list[AgentTask] = []
    for i, branch in enumerate(branches):
        files_raw = _run(["git", "diff", "--name-only", f"main...{branch}"])
        files = [f.strip() for f in files_raw.splitlines() if f.strip()]

        # Derive a task description from the branch name
        task_name = branch.replace("feat/", "").replace("-", " ").replace("_", " ").title()

        tasks.append(AgentTask(
            agent_id=f"agent-{chr(ord('a') + i)}",
            branch=branch,
            task=task_name,
            status="running",
            files=files,
        ))

    return tasks


# ── Demo data ─────────────────────────────────────────────────────────────────

def demo_tasks() -> list[AgentTask]:
    return [
        AgentTask(
            agent_id="agent-a",
            branch="feat/auth",
            task="Add JWT middleware",
            status="running",
            files=[
                "src/middleware/auth.py",
                "src/models/user.py",
                "src/routes/login.py",
                "src/routes/logout.py",
                "tests/test_auth.py",
                "tests/test_middleware.py",
                "docs/auth.md",
            ],
            file_line_ranges={"src/middleware/auth.py": (1, 120), "src/models/user.py": (40, 80)},
            dependencies=[],
        ),
        AgentTask(
            agent_id="agent-b",
            branch="feat/api",
            task="Refactor user endpoints",
            status="running",
            files=[
                "src/middleware/auth.py",
                "src/routes/users.py",
                "src/routes/profile.py",
                "src/db/schema.py",
                "tests/test_users.py",
            ],
            file_line_ranges={"src/middleware/auth.py": (85, 200), "src/db/schema.py": (1, 60)},
            dependencies=[],
        ),
        AgentTask(
            agent_id="agent-c",
            branch="feat/db",
            task="Migrate schema v3",
            status="pending",
            files=[
                "src/db/schema.py",
                "src/db/migrations/v3.py",
                "src/db/connection.py",
            ],
            file_line_ranges={"src/db/schema.py": (55, 130)},
            dependencies=[],
        ),
        AgentTask(
            agent_id="agent-d",
            branch="feat/ui",
            task="Update login form",
            status="running",
            files=[
                "src/models/user.py",
                "src/templates/login.html",
                "src/static/login.css",
                "src/static/login.js",
            ],
            file_line_ranges={"src/models/user.py": (1, 35)},
            dependencies=[],
        ),
    ]


# ── Conflict detection ─────────────────────────────────────────────────────────

def _line_ranges_overlap(
    r1: tuple[int, int] | None, r2: tuple[int, int] | None
) -> bool:
    if r1 is None or r2 is None:
        return False
    return r1[0] <= r2[1] and r2[0] <= r1[1]


def detect_conflicts(tasks: list[AgentTask]) -> list[Conflict]:
    conflicts: list[Conflict] = []
    active = [t for t in tasks if t.status not in ("done",)]

    for i in range(len(active)):
        for j in range(i + 1, len(active)):
            a, b = active[i], active[j]
            shared = list(set(a.files) & set(b.files))
            if not shared:
                continue

            # Determine severity: any overlapping line ranges → HIGH
            severity: ConflictSeverity = "medium"
            high_files: list[str] = []
            for f in shared:
                if _line_ranges_overlap(
                    a.file_line_ranges.get(f),
                    b.file_line_ranges.get(f),
                ):
                    high_files.append(f)

            if high_files:
                severity = "high"
                detail = f"overlapping edits in: {', '.join(high_files)}"
            else:
                detail = ""

            conflicts.append(Conflict(
                agent_a=a.agent_id,
                agent_b=b.agent_id,
                shared_files=shared,
                severity=severity,
                detail=detail,
            ))

    return conflicts


# ── Claude-powered reorder analysis ───────────────────────────────────────────

async def suggest_reordering(
    tasks: list[AgentTask],
    conflicts: list[Conflict],
) -> tuple[list[list[str]], str, str]:
    """
    Ask Claude to analyse the conflict graph and return:
      - parallel execution slots (list of lists of agent_ids)
      - a prose rationale
      - a savings summary message

    Falls back to a heuristic if the Agent SDK is unavailable.
    """
    try:
        from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage
    except ImportError:
        return _heuristic_reorder(tasks, conflicts)

    # Build a compact JSON payload for Claude to reason over
    payload = {
        "agents": [
            {
                "id": t.agent_id,
                "task": t.task,
                "status": t.status,
                "file_count": len(t.files),
                "dependencies": t.dependencies,
            }
            for t in tasks
            if t.status != "done"
        ],
        "conflicts": [
            {
                "between": [c.agent_a, c.agent_b],
                "severity": c.severity,
                "shared_files": c.shared_files,
                "detail": c.detail,
            }
            for c in conflicts
        ],
    }

    prompt = f"""You are a software-delivery coordinator for a multi-agent coding harness.

Here is the current cross-agent state:

```json
{json.dumps(payload, indent=2)}
```

Your job:
1. Produce a **safe execution order** — a list of *slots* where each slot is a set of agent IDs
   that can safely run in parallel (no HIGH or MEDIUM conflicts between them).
   Agents in different slots must be serialised (earlier slot finishes before later slot starts).
2. Write a concise **rationale** (3-6 bullet points) explaining the key decisions.
3. Write a one-line **savings message** stating how many conflicts are eliminated by the ordering.

Reply with ONLY a JSON object — no markdown fences, no extra text:
{{
  "slots": [["agent-x", "agent-y"], ["agent-z"], ...],
  "rationale": "• ...\\n• ...\\n• ...",
  "savings_msg": "..."
}}"""

    full_response = ""
    try:
        async for message in query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                allowed_tools=[],          # pure reasoning, no tools needed
                model="claude-opus-4-6",
                thinking={"type": "adaptive"},
                max_turns=1,
            ),
        ):
            if isinstance(message, ResultMessage):
                full_response = message.result
    except Exception as exc:
        print(f"  ⚠️  Claude analysis failed ({exc}). Using heuristic.", file=sys.stderr)
        return _heuristic_reorder(tasks, conflicts)

    # Parse the JSON reply
    try:
        # Strip any accidental markdown fences
        cleaned = full_response.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        parsed = json.loads(cleaned)
        slots: list[list[str]] = parsed["slots"]
        rationale: str = parsed["rationale"]
        savings_msg: str = parsed["savings_msg"]
        return slots, rationale, savings_msg
    except Exception:
        return _heuristic_reorder(tasks, conflicts)


def _heuristic_reorder(
    tasks: list[AgentTask],
    conflicts: list[Conflict],
) -> tuple[list[list[str]], str, str]:
    """
    Simple greedy heuristic when Claude is unavailable.
    Topological sort: agents with HIGH conflicts are serialised;
    MEDIUM conflicts are flagged but may run together.
    """
    active_ids = [t.agent_id for t in tasks if t.status != "done"]
    if not active_ids:
        return [], "No active agents.", "No conflicts to resolve."

    # Build adjacency: HIGH conflicts → must be serialised
    must_precede: dict[str, set[str]] = {aid: set() for aid in active_ids}
    for c in conflicts:
        if c.severity == "high":
            # Arbitrary but consistent: alphabetically earlier agent runs first
            earlier, later = sorted([c.agent_a, c.agent_b])
            if earlier in must_precede and later in must_precede:
                must_precede[later].add(earlier)

    # Kahn's algorithm for topological sort into slots
    in_degree = {a: len(deps) for a, deps in must_precede.items()}
    slots: list[list[str]] = []
    remaining = set(active_ids)

    while remaining:
        ready = sorted(a for a in remaining if in_degree[a] == 0)
        if not ready:
            # Cycle — just dump the rest in one slot
            slots.append(sorted(remaining))
            break
        slots.append(ready)
        for a in ready:
            remaining.remove(a)
            for other in remaining:
                if a in must_precede[other]:
                    in_degree[other] -= 1

    high_count = sum(1 for c in conflicts if c.severity == "high")
    rationale = (
        "• Agents with HIGH line-range conflicts are serialised.\n"
        "• Agents sharing only different sections of a file run in parallel.\n"
        "• Ordering is alphabetical within each slot for determinism."
    )
    savings_msg = f"{high_count} HIGH conflict(s) eliminated by serialisation."
    return slots, rationale, savings_msg


# ── Rendering ─────────────────────────────────────────────────────────────────

WIDTH = 68
BAR = "━" * WIDTH
DIV = "─" * WIDTH


def _pad(s: str, width: int) -> str:
    visible = len(s.encode("utf-8").decode("utf-8"))  # rough, ignores CJK
    # Strip ANSI for length calc if needed
    return s + " " * max(0, width - len(s))


def _render_locks_panel(locks: "list[TaskLock]") -> None:
    """Render the Task Lock State panel inside the coordination report."""
    print()
    print(f"  Task Lock State")
    print(f"  {DIV}")
    if not locks:
        print("  🟢  No tasks are currently locked.")
        return

    w_task = max(len(lk.task_id) for lk in locks)
    w_agent = max(len(lk.agent_id) for lk in locks)

    header = (
        f"  {'TASK_ID':<{w_task}}  "
        f"{'AGENT_ID':<{w_agent}}  "
        f"EXPIRES_IN  ACQUIRED_AT"
    )
    print(header)
    print("  " + "─" * max(0, len(header) - 2))

    for lk in sorted(locks, key=lambda x: x.task_id):
        remaining = lk.seconds_remaining()
        mins, secs = divmod(int(max(remaining, 0)), 60)
        exp_str = f"{mins}m {secs:02d}s" if mins else f"{secs:02d}s"
        warn = " ⚠️ expiring soon" if 0 < remaining < 30 else ""
        print(
            f"  🔴 {lk.task_id:<{w_task}}  "
            f"{lk.agent_id:<{w_agent}}  "
            f"{exp_str:<10}  "
            f"{lk.acquired_at[:19]}"
            f"{warn}"
        )


def render_report(report: CoordinationReport, as_json: bool = False) -> None:
    if as_json:
        locks_data = []
        for lk in report.active_locks:
            locks_data.append({
                "task_id": lk.task_id,
                "agent_id": lk.agent_id,
                "acquired_at": lk.acquired_at,
                "expires_at": lk.expires_at,
                "timeout_seconds": lk.timeout_seconds,
                "seconds_remaining": round(lk.seconds_remaining(), 1),
            })
        print(json.dumps({
            "snapshot": report.snapshot_time,
            "agents": [
                {
                    "agent_id": a.agent_id,
                    "branch": a.branch,
                    "task": a.task,
                    "status": a.status,
                    "file_count": len(a.files),
                }
                for a in report.agents
            ],
            "conflicts": [
                {
                    "agents": [c.agent_a, c.agent_b],
                    "severity": c.severity,
                    "shared_files": c.shared_files,
                    "detail": c.detail,
                }
                for c in report.conflicts
            ],
            "suggested_slots": report.suggested_slots,
            "rationale": report.rationale,
            "savings_msg": report.savings_msg,
            "active_locks": locks_data,
        }, indent=2))
        return

    conflict_count = len(report.conflicts)
    agent_count = len(report.agents)

    print()
    print(f"  {BAR}")
    print(f"  Cross-Agent Coordination — claw-forge")
    print(f"  Snapshot: {report.snapshot_time}  |  Agents: {agent_count}  |  Conflicts: {conflict_count}")
    print(f"  {BAR}")

    # ── Agent roster ──
    print()
    print(f"  {'Agent':<22} {'Task':<34} {'Status':<12} {'Files':>5}")
    print(f"  {DIV}")
    for a in report.agents:
        icon = STATUS_ICON.get(a.status, "❓")
        agent_col = f"{a.agent_id} ({a.branch})"
        task_col = (a.task[:33] + "…") if len(a.task) > 34 else a.task
        status_col = f"{icon} {a.status}"
        print(f"  {agent_col:<22} {task_col:<34} {status_col:<12} {len(a.files):>5}")

    # ── Conflict matrix ──
    print()
    print(f"  Conflict Analysis")
    print(f"  {DIV}")
    if not report.conflicts:
        print("  ✅  No conflicts detected — all agents are touching distinct files.")
    else:
        for c in sorted(report.conflicts, key=lambda x: ("high", "medium", "low").index(x.severity)):
            sev_label = SEVERITY_ICON[c.severity]
            pair = f"{c.agent_a} × {c.agent_b}"
            files_str = ", ".join(c.shared_files[:3])
            if len(c.shared_files) > 3:
                files_str += f" (+{len(c.shared_files) - 3} more)"
            line = f"  {sev_label}   {pair:<18}  →  {files_str}"
            if c.detail:
                line += f"\n  {'':>28}     ↳ {c.detail}"
            print(line)

    # ── Suggested execution order ──
    print()
    print(f"  Suggested Execution Order  (minimises merge conflicts)")
    print(f"  {DIV}")
    if not report.suggested_slots:
        print("  (no active agents to schedule)")
    else:
        for i, slot in enumerate(report.suggested_slots, 1):
            parallel_label = "run in parallel" if len(slot) > 1 else "run"
            agents_str = "  ".join(slot)
            print(f"  Slot {i} — {parallel_label}:  {agents_str}")

    print()
    # Rationale (indented bullet list)
    print(f"  Rationale:")
    for line in report.rationale.strip().splitlines():
        print(f"    {line.strip()}")

    print()
    print(f"  {report.savings_msg}")

    # ── Task lock panel ──
    if report.active_locks is not None:   # None means locks panel was skipped
        _render_locks_panel(report.active_locks)

    print()
    print(f"  {BAR}")
    print()


# ── Main entry point ───────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cross-agent task conflict dashboard for claw-forge harnesses."
    )
    parser.add_argument(
        "--state-url",
        default="http://localhost:8420",
        help="claw-forge state service base URL (default: http://localhost:8420)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use built-in demo data (no state service required)",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Emit JSON instead of a formatted table",
    )
    parser.add_argument(
        "--locks-dir",
        default=".claude/task-locks",
        metavar="PATH",
        help="Directory containing task lock files (default: .claude/task-locks)",
    )
    parser.add_argument(
        "--no-locks",
        action="store_true",
        help="Skip the Task Lock State panel",
    )
    args = parser.parse_args()

    snapshot = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Gather agent task data
    if args.demo:
        tasks = demo_tasks()
        if not args.as_json:
            print("  ℹ️  Demo mode — using synthetic agent data.")
    else:
        tasks = await fetch_from_state_service(args.state_url) or fetch_from_git()
        if not tasks:
            print(
                "  ⚠️  No agent data found.\n"
                "  Start the state service (`claw-forge state`) or run with --demo.",
                file=sys.stderr,
            )
            sys.exit(1)

    # 2. Detect file-level conflicts
    conflicts = detect_conflicts(tasks)

    # 3. Ask Claude (or heuristic) for a safe execution order
    slots, rationale, savings_msg = await suggest_reordering(tasks, conflicts)

    # 4. Read active task locks (optional)
    active_locks: list = []
    if not args.no_locks and _LOCK_AVAILABLE:
        try:
            lock_proto = TaskLockProtocol(
                locks_dir=Path(args.locks_dir),
                default_timeout_seconds=300,
            )
            active_locks = lock_proto.list_locks()
        except Exception as exc:
            if not args.as_json:
                print(f"  ⚠️  Could not read lock state ({exc}).", file=sys.stderr)

    # 5. Render
    report = CoordinationReport(
        snapshot_time=snapshot,
        agents=tasks,
        conflicts=conflicts,
        suggested_slots=slots,
        rationale=rationale,
        savings_msg=savings_msg,
        active_locks=active_locks if (not args.no_locks and _LOCK_AVAILABLE) else None,
    )
    render_report(report, as_json=args.as_json)


if __name__ == "__main__":
    asyncio.run(main())
