"""
skills/shared_state.py — Shared Agent State Publisher & Query Tool

Agents use this module to **publish** intermediate results into
docs/exec-plans/shared-state.yaml and to **query** results published by
other agents.  Typical payloads include:

  - discovered_endpoints   (API surface found during exploration)
  - schema_changes         (DB/model diffs an agent has applied)
  - test_results           (pass/fail counts, coverage deltas)
  - other                  (free-form structured data)

The file is updated with an advisory file lock so concurrent agents can
write safely.

Usage (CLI)
-----------
  # Publish a result (JSON payload on stdin or --data flag)
  python skills/shared_state.py publish \\
      --agent coding-03abe8fb \\
      --type discovered_endpoints \\
      --data '{"endpoints": ["/api/v1/users", "/api/v1/orders"]}'

  # Query all results of a given type
  python skills/shared_state.py query --type schema_changes

  # Query all results published by a specific agent
  python skills/shared_state.py query --agent coding-48dd7f13

  # List every published result (summary table)
  python skills/shared_state.py list

  # Dump raw YAML of the intermediate_results section
  python skills/shared_state.py dump

Programmatic use
----------------
  from skills.shared_state import SharedState, ResultType

  ss = SharedState()
  ss.publish(
      agent_id="coding-03abe8fb",
      result_type="discovered_endpoints",
      data={"endpoints": ["/api/v1/users"]},
  )

  for result in ss.query(result_type="discovered_endpoints"):
      print(result["agent_id"], result["data"])
"""

from __future__ import annotations

import argparse
import fcntl
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

try:
    import yaml
except ImportError:  # pragma: no cover
    print(
        "[shared-state] PyYAML not found — install it with: uv add pyyaml",
        file=sys.stderr,
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SHARED_STATE_FILE = _REPO_ROOT / "docs" / "exec-plans" / "shared-state.yaml"

ResultType = Literal[
    "discovered_endpoints",
    "schema_changes",
    "test_results",
    "other",
]

_VALID_TYPES: frozenset[str] = frozenset(
    {"discovered_endpoints", "schema_changes", "test_results", "other"}
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _save_yaml(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        yaml.dump(data, fh, allow_unicode=True, sort_keys=False)


# ---------------------------------------------------------------------------
# Core class
# ---------------------------------------------------------------------------


class SharedState:
    """Read/write interface for docs/exec-plans/shared-state.yaml.

    All mutations are wrapped in an exclusive advisory file lock so that
    concurrent agents can call ``publish`` without corrupting the file.
    """

    def __init__(self, state_file: Path | None = None) -> None:
        self._file: Path = state_file or _SHARED_STATE_FILE
        if not self._file.exists():
            raise FileNotFoundError(
                f"Shared state file not found: {self._file}\n"
                "Run the 'coordinate' skill first to generate it."
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def publish(
        self,
        agent_id: str,
        result_type: str,
        data: Any,
        notes: str = "",
    ) -> None:
        """Append an intermediate result to the shared state file.

        Parameters
        ----------
        agent_id:
            The ID of the publishing agent, e.g. ``"coding-03abe8fb"``.
        result_type:
            One of ``discovered_endpoints``, ``schema_changes``,
            ``test_results``, or ``other``.
        data:
            Arbitrary JSON-serialisable payload.
        notes:
            Optional human-readable description of the result.
        """
        if result_type not in _VALID_TYPES:
            raise ValueError(
                f"Invalid result_type {result_type!r}. "
                f"Must be one of: {sorted(_VALID_TYPES)}"
            )

        entry: dict[str, Any] = {
            "agent_id": agent_id,
            "type": result_type,
            "timestamp": _now(),
            "data": data,
        }
        if notes:
            entry["notes"] = notes

        with self._file.open("r+", encoding="utf-8") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                doc: dict[str, Any] = yaml.safe_load(fh) or {}
                # Ensure the key exists and is a list (strip any None/comment stub)
                if not isinstance(doc.get("intermediate_results"), list):
                    doc["intermediate_results"] = []
                doc["intermediate_results"].append(entry)
                fh.seek(0)
                fh.truncate()
                yaml.dump(doc, fh, allow_unicode=True, sort_keys=False)
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

        print(
            f"[shared-state] Published {result_type!r} from {agent_id} "
            f"at {entry['timestamp']}"
        )

    def query(
        self,
        result_type: str | None = None,
        agent_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return published results, optionally filtered.

        Parameters
        ----------
        result_type:
            If given, return only entries whose ``type`` matches.
        agent_id:
            If given, return only entries whose ``agent_id`` matches.

        Returns
        -------
        list[dict]
            Matching result entries, in publication order (oldest first).
        """
        doc = _load_yaml(self._file)
        results: list[dict[str, Any]] = doc.get("intermediate_results") or []
        # Drop any non-dict entries (e.g. if the section is a comment placeholder)
        results = [r for r in results if isinstance(r, dict)]

        if result_type is not None:
            results = [r for r in results if r.get("type") == result_type]
        if agent_id is not None:
            results = [r for r in results if r.get("agent_id") == agent_id]
        return results

    def list_all(self) -> list[dict[str, Any]]:
        """Return every published result, unfiltered."""
        return self.query()

    def dump_raw(self) -> str:
        """Return the ``intermediate_results`` section as a YAML string."""
        results = self.list_all()
        return yaml.dump({"intermediate_results": results}, allow_unicode=True, sort_keys=False)

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    def render_table(self, results: list[dict[str, Any]]) -> str:
        """Render a compact summary table of results."""
        if not results:
            return "  (no intermediate results published yet)"

        lines = [
            f"  {'Agent':<24} {'Type':<26} {'Timestamp':<22} Notes",
            "  " + "-" * 80,
        ]
        for r in results:
            agent = r.get("agent_id", "—")
            rtype = r.get("type", "—")
            ts = r.get("timestamp", "—")
            notes = r.get("notes", "")
            lines.append(
                f"  {agent:<24} {rtype:<26} {ts:<22} {notes}"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="shared_state",
        description="Publish and query intermediate agent results in shared-state.yaml.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    # publish
    pub = sub.add_parser("publish", help="Publish an intermediate result")
    pub.add_argument("--agent", required=True, dest="agent_id",
                     help="Agent ID publishing the result (e.g. coding-03abe8fb)")
    pub.add_argument(
        "--type", required=True, dest="result_type",
        choices=sorted(_VALID_TYPES),
        help="Category of the result",
    )
    pub.add_argument(
        "--data", default=None,
        help="JSON-encoded payload string. Omit to read from stdin.",
    )
    pub.add_argument("--notes", default="", help="Optional human-readable description")

    # query
    qry = sub.add_parser("query", help="Query published results (optionally filtered)")
    qry.add_argument("--type", dest="result_type", default=None,
                     choices=sorted(_VALID_TYPES),
                     help="Filter by result type")
    qry.add_argument("--agent", dest="agent_id", default=None,
                     help="Filter by agent ID")
    qry.add_argument("--json", dest="as_json", action="store_true",
                     help="Emit JSON array instead of a table")

    # list
    lst = sub.add_parser("list", help="List all published results (summary table)")
    lst.add_argument("--json", dest="as_json", action="store_true",
                     help="Emit JSON array instead of a table")

    # dump
    sub.add_parser("dump", help="Dump the raw intermediate_results YAML")

    return p


def main(argv: list[str] | None = None) -> None:  # noqa: C901
    parser = _build_parser()
    args = parser.parse_args(argv)

    ss = SharedState()

    if args.command == "publish":
        if args.data is not None:
            raw = args.data
        else:
            if sys.stdin.isatty():
                print("[shared-state] Reading JSON payload from stdin (Ctrl-D to finish)…",
                      file=sys.stderr)
            raw = sys.stdin.read().strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"[shared-state] ERROR: --data is not valid JSON: {exc}", file=sys.stderr)
            sys.exit(1)
        ss.publish(
            agent_id=args.agent_id,
            result_type=args.result_type,
            data=payload,
            notes=args.notes,
        )

    elif args.command == "query":
        results = ss.query(
            result_type=getattr(args, "result_type", None),
            agent_id=getattr(args, "agent_id", None),
        )
        if args.as_json:
            print(json.dumps(results, indent=2, default=str))
        else:
            print(ss.render_table(results))

    elif args.command == "list":
        results = ss.list_all()
        if args.as_json:
            print(json.dumps(results, indent=2, default=str))
        else:
            count = len(results)
            print(f"\n  Intermediate Results — {count} entr{'y' if count == 1 else 'ies'}\n")
            print(ss.render_table(results))
            print()

    elif args.command == "dump":
        print(ss.dump_raw())

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
