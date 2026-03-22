"""
skills/exec_plan.py — Execution Plan Manager

Agents use this script to create, update, and query execution plans stored in
docs/exec-plans/<plan-id>.yaml.  Each plan tracks a dependency graph of tasks
with multi-agent coordination metadata (assigned_agent, lock_status, depends_on).

Usage (CLI)
-----------
  # Create a new plan from the template
  python skills/exec_plan.py init --title "Implement rate-limiting" --plan-id PLAN-001

  # Claim (lock) a task for an agent
  python skills/exec_plan.py claim --plan PLAN-001 --task TASK-002 --agent coding-03abe8fb

  # Mark a task done and release its lock
  python skills/exec_plan.py done --plan PLAN-001 --task TASK-002 --agent coding-03abe8fb

  # List tasks whose dependencies are all satisfied (ready to start)
  python skills/exec_plan.py ready --plan PLAN-001

  # Show the full plan status table
  python skills/exec_plan.py status --plan PLAN-001

  # Show a text dependency graph
  python skills/exec_plan.py graph --plan PLAN-001

  # Print context assembly hints for a plan or task
  python skills/exec_plan.py context --plan PLAN-001
  python skills/exec_plan.py context --plan PLAN-001 --task TASK-002

Programmatic use
----------------
  from skills.exec_plan import ExecPlan
  plan = ExecPlan.load("PLAN-001")
  plan.claim("TASK-003", agent="coding-03abe8fb")
  plan.mark_done("TASK-003", agent="coding-03abe8fb")
  for task in plan.ready_tasks():
      print(task["id"], task["title"])
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    print(
        "[exec-plan] PyYAML not found — install it with: pip install pyyaml",
        file=sys.stderr,
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_EXEC_PLANS_DIR = _REPO_ROOT / "docs" / "exec-plans"
_TEMPLATE = _EXEC_PLANS_DIR / "plan-template.yaml"

# ---------------------------------------------------------------------------
# Status / lock constants
# ---------------------------------------------------------------------------
TASK_STATUSES = {"pending", "running", "done", "blocked", "skipped"}
LOCK_STATUSES = {"unlocked", "locked", "done"}
PLAN_STATUSES = {"pending", "running", "done", "blocked", "cancelled"}
PRIORITIES = ["critical", "high", "medium", "low"]

_STATUS_ICON = {
    "pending":  "⬜",
    "running":  "🔵",
    "done":     "✅",
    "blocked":  "🔴",
    "skipped":  "⏭️",
}

_LOCK_ICON = {
    "unlocked": "🔓",
    "locked":   "🔒",
    "done":     "✅",
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Core class
# ---------------------------------------------------------------------------
class ExecPlan:
    """Load, mutate, and persist a single execution plan YAML file."""

    def __init__(self, plan_id: str, data: dict[str, Any], file_path: Path) -> None:
        self.plan_id = plan_id
        self._data = data
        self._file = file_path

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def init(cls, title: str, plan_id: str | None = None) -> "ExecPlan":
        """Create a new plan file from the template and return an ExecPlan."""
        _EXEC_PLANS_DIR.mkdir(parents=True, exist_ok=True)

        # Auto-generate an incremental plan ID if not provided
        if plan_id is None:
            plan_id = _next_plan_id()

        dest = _EXEC_PLANS_DIR / f"{plan_id}.yaml"
        if dest.exists():
            raise FileExistsError(
                f"Plan file already exists: {dest}. Use a different --plan-id."
            )

        if not _TEMPLATE.exists():
            raise FileNotFoundError(
                f"Template not found at {_TEMPLATE}. "
                "Ensure docs/exec-plans/plan-template.yaml exists."
            )

        shutil.copy(_TEMPLATE, dest)

        # Patch the freshly copied file with real values
        instance = cls._load_file(dest)
        instance._data["plan"]["id"] = plan_id
        instance._data["plan"]["title"] = title
        instance._data["plan"]["created_at"] = _now()
        instance._data["plan"]["updated_at"] = _now()
        instance._data["plan"]["status"] = "pending"

        # Reset tasks to a minimal single-task stub
        instance._data["tasks"] = [
            {
                "id": "TASK-001",
                "title": "<first task>",
                "description": "",
                "assigned_agent": "",
                "lock_status": "unlocked",
                "depends_on": [],
                "status": "pending",
                "priority": "medium",
                "started_at": None,
                "completed_at": None,
                "notes": "",
                "context": {
                    "grep_patterns": [],
                    "glob_patterns": [],
                    "symbol_refs": [],
                },
            }
        ]
        instance._data["coordination"] = {
            "strategy": "parallel-with-serialised-hotspots",
            "hotspot_files": [],
            "merge_order": [],
            "post_merge_checklist": [],
        }
        instance._data["context_assembly"] = {
            "grep_patterns": [],
            "glob_patterns": [],
            "symbol_refs": [],
            "key_files": [],
            "rationale": "",
        }
        instance._save()
        print(f"[exec-plan] Initialised {plan_id} → {dest}")
        return instance

    @classmethod
    def load(cls, plan_id: str) -> "ExecPlan":
        """Load an existing plan by ID."""
        path = _EXEC_PLANS_DIR / f"{plan_id}.yaml"
        if not path.exists():
            raise FileNotFoundError(
                f"No plan file found for {plan_id!r}. "
                f"Expected: {path}"
            )
        return cls._load_file(path)

    @classmethod
    def _load_file(cls, path: Path) -> "ExecPlan":
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        plan_id = data.get("plan", {}).get("id", path.stem)
        return cls(plan_id=plan_id, data=data, file_path=path)

    # ------------------------------------------------------------------
    # Task mutations
    # ------------------------------------------------------------------

    def claim(self, task_id: str, agent: str) -> None:
        """Lock a task for an agent (sets lock_status=locked, status=running)."""
        task = self._get_task(task_id)
        if task["lock_status"] == "done":
            raise ValueError(f"{task_id} is already done — cannot claim.")
        if task["lock_status"] == "locked":
            holder = task.get("assigned_agent", "unknown")
            if holder != agent:
                raise ValueError(
                    f"{task_id} is already locked by {holder!r}. "
                    "Release it before claiming."
                )

        # Check dependencies
        blocked_by = self._blocked_by(task)
        if blocked_by:
            raise ValueError(
                f"{task_id} depends on tasks that are not yet done: "
                + ", ".join(blocked_by)
            )

        task["assigned_agent"] = agent
        task["lock_status"] = "locked"
        task["status"] = "running"
        task["started_at"] = _now()
        self._touch()
        self._save()
        print(f"[exec-plan] {task_id} claimed by {agent}")

    def mark_done(self, task_id: str, agent: str, notes: str = "") -> None:
        """Mark a task complete and release the lock."""
        task = self._get_task(task_id)
        if task.get("assigned_agent") not in (agent, ""):
            raise ValueError(
                f"{task_id} is assigned to {task['assigned_agent']!r}, "
                f"not {agent!r}."
            )
        task["lock_status"] = "done"
        task["status"] = "done"
        task["completed_at"] = _now()
        if notes:
            task["notes"] = notes
        # keep assigned_agent so history is preserved
        self._touch()
        self._maybe_close_plan()
        self._save()
        print(f"[exec-plan] {task_id} marked done by {agent}")

    def release(self, task_id: str, agent: str) -> None:
        """Release a lock without marking the task done (e.g. agent crash)."""
        task = self._get_task(task_id)
        if task.get("assigned_agent") not in (agent, ""):
            raise ValueError(
                f"{task_id} is assigned to {task['assigned_agent']!r}, "
                f"not {agent!r}."
            )
        task["assigned_agent"] = ""
        task["lock_status"] = "unlocked"
        task["status"] = "pending"
        task["started_at"] = None
        self._touch()
        self._save()
        print(f"[exec-plan] {task_id} lock released by {agent}")

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def ready_tasks(self) -> list[dict]:
        """Return tasks that have no unresolved dependencies and are unlocked."""
        return [
            t for t in self._tasks()
            if t["lock_status"] == "unlocked"
            and t["status"] not in ("done", "skipped", "blocked")
            and not self._blocked_by(t)
        ]

    def status_table(self) -> str:
        """Return a formatted status table as a string."""
        lines = [
            f"# Plan: {self._data['plan']['id']} — {self._data['plan']['title']}",
            f"# Status: {self._data['plan']['status']}  |  "
            f"Updated: {self._data['plan'].get('updated_at', '?')}",
            "",
            f"{'ID':<12} {'Status':<10} {'Lock':<10} {'Agent':<24} {'Priority':<10} Title",
            "-" * 90,
        ]
        for t in self._tasks():
            lines.append(
                f"{t['id']:<12} "
                f"{_STATUS_ICON.get(t['status'], t['status']):<10} "
                f"{_LOCK_ICON.get(t['lock_status'], t['lock_status']):<10} "
                f"{(t.get('assigned_agent') or '—'):<24} "
                f"{t.get('priority', 'medium'):<10} "
                f"{t['title']}"
            )
        ready = self.ready_tasks()
        if ready:
            lines.append("")
            lines.append(f"Ready to start ({len(ready)}): " + ", ".join(t["id"] for t in ready))
        return "\n".join(lines)

    def print_context(self, task_id: str | None = None) -> None:
        """Print context assembly hints for the plan or a specific task."""
        if task_id:
            task = self._get_task(task_id)
            ctx = task.get("context") or {}
            header = f"# Context assembly — {task_id}: {task['title']}"
        else:
            ctx = self._data.get("context_assembly") or {}
            header = f"# Context assembly — {self.plan_id}: {self._data['plan']['title']}"

        lines = [header, ""]

        grep = ctx.get("grep_patterns") or []
        if grep:
            lines.append("## Grep patterns")
            for p in grep:
                lines.append(f"  {p}")
            lines.append("")

        globs = ctx.get("glob_patterns") or []
        if globs:
            lines.append("## Glob patterns")
            for g in globs:
                lines.append(f"  {g}")
            lines.append("")

        symbols = ctx.get("symbol_refs") or []
        if symbols:
            lines.append("## Symbol references")
            for s in symbols:
                lines.append(f"  {s}")
            lines.append("")

        if not task_id:
            key_files = ctx.get("key_files") or []
            if key_files:
                lines.append("## Key files")
                for kf in key_files:
                    if isinstance(kf, dict):
                        lines.append(f"  {kf.get('path', '?')} — {kf.get('reason', '')}")
                    else:
                        lines.append(f"  {kf}")
                lines.append("")

            rationale = ctx.get("rationale") or ""
            if rationale:
                lines.append("## Rationale")
                lines.append(f"  {rationale}")
                lines.append("")

        if not (grep or globs or symbols):
            lines.append("(no context assembly hints defined yet)")

        print("\n".join(lines))

    def dependency_graph(self) -> str:
        """Return a text representation of the dependency graph."""
        tasks = {t["id"]: t for t in self._tasks()}
        lines = ["Dependency graph (→ means 'required by'):", ""]

        # Find roots (tasks with no dependencies)
        roots = [t for t in self._tasks() if not t.get("depends_on")]
        visited: set[str] = set()

        def _render(task_id: str, indent: int = 0) -> None:
            if task_id in visited:
                lines.append("  " * indent + f"↩ {task_id} (already shown)")
                return
            visited.add(task_id)
            t = tasks.get(task_id, {})
            icon = _STATUS_ICON.get(t.get("status", "pending"), "?")
            lines.append("  " * indent + f"{icon} {task_id}: {t.get('title', '?')}")
            # find tasks that depend on this one
            children = [
                c for c in self._tasks()
                if task_id in (c.get("depends_on") or [])
            ]
            for child in children:
                _render(child["id"], indent + 1)

        for root in roots:
            _render(root["id"])

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _tasks(self) -> list[dict]:
        return self._data.get("tasks") or []

    def _get_task(self, task_id: str) -> dict:
        for t in self._tasks():
            if t["id"] == task_id:
                return t
        raise KeyError(f"Task {task_id!r} not found in plan {self.plan_id!r}")

    def _blocked_by(self, task: dict) -> list[str]:
        """Return list of dependency IDs that are not yet done."""
        dep_ids: list[str] = task.get("depends_on") or []
        tasks_by_id = {t["id"]: t for t in self._tasks()}
        return [
            dep for dep in dep_ids
            if tasks_by_id.get(dep, {}).get("status") != "done"
        ]

    def _maybe_close_plan(self) -> None:
        all_done = all(
            t["status"] in ("done", "skipped") for t in self._tasks()
        )
        if all_done:
            self._data["plan"]["status"] = "done"

    def _touch(self) -> None:
        self._data["plan"]["updated_at"] = _now()

    def _save(self) -> None:
        with self._file.open("w", encoding="utf-8") as fh:
            yaml.dump(self._data, fh, allow_unicode=True, sort_keys=False)


# ---------------------------------------------------------------------------
# ID generator
# ---------------------------------------------------------------------------
def _next_plan_id() -> str:
    existing = sorted(_EXEC_PLANS_DIR.glob("PLAN-*.yaml"))
    nums = []
    for p in existing:
        try:
            nums.append(int(p.stem.split("-")[1]))
        except (IndexError, ValueError):
            pass
    next_num = max(nums, default=0) + 1
    return f"PLAN-{next_num:03d}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="exec_plan",
        description="Create and manage execution plans in docs/exec-plans/. Commands: init, claim, done, release, ready, status, graph, context.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    # init
    init_p = sub.add_parser("init", help="Create a new plan from the template")
    init_p.add_argument("--title", required=True, help="Human-readable plan title")
    init_p.add_argument("--plan-id", dest="plan_id", default=None,
                        help="Explicit plan ID (e.g. PLAN-007). Auto-assigned if omitted.")

    # claim
    claim_p = sub.add_parser("claim", help="Lock a task for an agent")
    claim_p.add_argument("--plan", required=True, help="Plan ID (e.g. PLAN-001)")
    claim_p.add_argument("--task", required=True, help="Task ID (e.g. TASK-002)")
    claim_p.add_argument("--agent", required=True, help="Agent ID claiming the task")

    # done
    done_p = sub.add_parser("done", help="Mark a task done and release its lock")
    done_p.add_argument("--plan", required=True)
    done_p.add_argument("--task", required=True)
    done_p.add_argument("--agent", required=True)
    done_p.add_argument("--notes", default="", help="Optional completion notes")

    # release
    rel_p = sub.add_parser("release", help="Release a task lock without marking done")
    rel_p.add_argument("--plan", required=True)
    rel_p.add_argument("--task", required=True)
    rel_p.add_argument("--agent", required=True)

    # ready
    ready_p = sub.add_parser("ready", help="List tasks ready to start")
    ready_p.add_argument("--plan", required=True)

    # status
    stat_p = sub.add_parser("status", help="Print full plan status table")
    stat_p.add_argument("--plan", required=True)

    # graph
    graph_p = sub.add_parser("graph", help="Print the dependency graph")
    graph_p.add_argument("--plan", required=True)

    # context
    ctx_p = sub.add_parser("context", help="Print context assembly hints for a plan or task")
    ctx_p.add_argument("--plan", required=True)
    ctx_p.add_argument("--task", default=None, help="Task ID (e.g. TASK-001); omit for plan-level context")

    return p


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        ExecPlan.init(title=args.title, plan_id=args.plan_id)

    elif args.command == "claim":
        plan = ExecPlan.load(args.plan)
        plan.claim(args.task, agent=args.agent)

    elif args.command == "done":
        plan = ExecPlan.load(args.plan)
        plan.mark_done(args.task, agent=args.agent, notes=args.notes)

    elif args.command == "release":
        plan = ExecPlan.load(args.plan)
        plan.release(args.task, agent=args.agent)

    elif args.command == "ready":
        plan = ExecPlan.load(args.plan)
        ready = plan.ready_tasks()
        if not ready:
            print("[exec-plan] No tasks are currently ready to start.")
        else:
            print(f"[exec-plan] {len(ready)} task(s) ready:")
            for t in ready:
                print(f"  {t['id']}: {t['title']}")

    elif args.command == "status":
        plan = ExecPlan.load(args.plan)
        print(plan.status_table())

    elif args.command == "graph":
        plan = ExecPlan.load(args.plan)
        print(plan.dependency_graph())

    elif args.command == "context":
        plan = ExecPlan.load(args.plan)
        plan.print_context(task_id=args.task)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
