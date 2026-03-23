"""
skills/golden_principles_cleanup.py — Golden Principles Cleanup Task Generator

Reads .claude/principles.yaml, scans the codebase for violations using the
harness principles gate (or a text-based fallback), and emits one cleanup
task definition per violation cluster into docs/exec-plans/cleanup-tasks.yaml.

Each generated task carries the full context an agent needs to open a focused
refactoring PR without any further analysis.

Usage (CLI)
-----------
  # Generate cleanup tasks for all principle violations
  python skills/golden_principles_cleanup.py generate

  # Only blocking violations, dry-run preview
  python skills/golden_principles_cleanup.py generate --only-blocking --dry-run

  # Custom principles file and output path
  python skills/golden_principles_cleanup.py generate \\
      --principles-file path/to/principles.yaml \\
      --output path/to/cleanup-tasks.yaml

  # List tasks from an existing cleanup-tasks.yaml
  python skills/golden_principles_cleanup.py list

Programmatic use
----------------
  from pathlib import Path
  from skills.golden_principles_cleanup import GoldenPrinciplesCleanup

  cleanup = GoldenPrinciplesCleanup()
  manifest = cleanup.generate_all(
      principles_file=Path(".claude/principles.yaml"),
      output_file=Path("docs/exec-plans/cleanup-tasks.yaml"),
      only_blocking=False,
      dry_run=False,
  )
  print(f"Generated {manifest.task_count} task(s)")
  for task in manifest.tasks:
      print(f"  {task.id}  [{task.severity}]  {task.pr_title}")
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    print(
        "[golden-principles-cleanup] PyYAML not found — install it with: pip install pyyaml",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover
    print(
        "[golden-principles-cleanup] Pydantic not found — install it with: pip install 'pydantic>=2.0'",
        file=sys.stderr,
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_PRINCIPLES_FILE = _REPO_ROOT / ".claude" / "principles.yaml"
_DEFAULT_OUTPUT_FILE = _REPO_ROOT / "docs" / "exec-plans" / "cleanup-tasks.yaml"
_SHARED_STATE_FILE = _REPO_ROOT / "docs" / "exec-plans" / "shared-state.yaml"

_SOURCE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx"}
_EXCLUDE_DIRS = {
    "node_modules", ".venv", "venv", "__pycache__", ".git",
    ".mypy_cache", ".ruff_cache", "dist", "build", ".cache",
}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CleanupTask(BaseModel):
    """A single cleanup task representing a principle violation cluster."""

    id: str
    principle_id: str
    principle_category: str
    severity: str
    title: str
    scope: list[str]
    description: str
    pr_title: str
    pr_body: str
    generated_at: str
    status: str = "pending"


class CleanupTaskManifest(BaseModel):
    """Top-level manifest written to cleanup-tasks.yaml."""

    generated_at: str
    generated_from_head: str
    task_count: int
    tasks: list[CleanupTask] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_utc() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slugify(text: str) -> str:
    """Convert a file path or arbitrary string into a URL/ID-safe slug.

    Examples:
        "src/api/views.py"  →  "src-api-views-py"
        "P001"              →  "p001"
        "src/utils/helpers.tsx" → "src-utils-helpers-tsx"
    """
    text = text.lower()
    # Replace path separators and dots with dashes
    text = re.sub(r"[/\\.]", "-", text)
    # Replace any remaining non-alphanumeric chars with dashes
    text = re.sub(r"[^a-z0-9-]", "-", text)
    # Collapse consecutive dashes
    text = re.sub(r"-{2,}", "-", text)
    # Strip leading/trailing dashes
    return text.strip("-")


def _get_git_head() -> str:
    """Return the short HEAD SHA, or 'no-git' if unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return "no-git"


def _scope_summary(scope: list[str]) -> str:
    """Summarise a list of file paths for use in PR titles."""
    if len(scope) == 1:
        return Path(scope[0]).name
    if len(scope) <= 3:
        return ", ".join(Path(p).name for p in scope)
    return f"{len(scope)} files"


def _source_files(root: Path) -> list[Path]:
    """Return all source files under root, excluding common non-source dirs."""
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in _SOURCE_EXTENSIONS:
            continue
        # Check none of the parent directory names are excluded
        if any(part in _EXCLUDE_DIRS for part in path.parts):
            continue
        files.append(path)
    return sorted(files)


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class GoldenPrinciplesCleanup:
    """Generate background cleanup tasks from principle violations."""

    def __init__(self, repo_root: Path = _REPO_ROOT) -> None:
        self.repo_root = repo_root

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_principles(self, principles_file: Path) -> list[dict[str, Any]]:
        """Load and validate principles from the YAML file.

        Args:
            principles_file: Path to the principles YAML file.

        Returns:
            List of principle dicts, each with at minimum `id`, `category`,
            `severity`, and `rule` keys.

        Raises:
            FileNotFoundError: If the principles file does not exist.
            ValueError: If the file is malformed or has no `principles` key.
        """
        if not principles_file.exists():
            raise FileNotFoundError(
                f"Principles file not found: {principles_file}\n"
                "Run /define-principles first to define your project's golden rules."
            )

        raw = yaml.safe_load(principles_file.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or "principles" not in raw:
            raise ValueError(
                f"{principles_file} is missing the top-level 'principles' key. "
                "Expected format: version: '1.0' / principles: [...]"
            )

        principles = raw["principles"]
        if not isinstance(principles, list):
            raise ValueError(
                f"'principles' in {principles_file} must be a list, got {type(principles).__name__}"
            )

        # Normalise: ensure required fields are present
        normalised: list[dict[str, Any]] = []
        for i, p in enumerate(principles):
            if not isinstance(p, dict):
                raise ValueError(f"Principle at index {i} must be a mapping, got {type(p).__name__}")
            for required in ("id", "rule"):
                if required not in p:
                    raise ValueError(
                        f"Principle at index {i} is missing required field '{required}': {p!r}"
                    )
            normalised.append({
                "id": str(p["id"]),
                "category": str(p.get("category", "general")),
                "severity": str(p.get("severity", "suggestion")),
                "applies_to": p.get("applies_to", ["review-pr", "check-code"]),
                "rule": str(p["rule"]),
            })

        return normalised

    def run_principles_gate(self) -> list[dict[str, Any]]:
        """Run the harness principles gate and return a list of GateFailure dicts.

        Returns an empty list on success (no violations).
        Returns an empty list if the gate runner is unavailable (caller should
        fall back to `fallback_scan`).

        Each dict has keys: rule_id, file_path, line_number, message, severity,
        suggestion, gate_id.
        """
        cmd = [
            "uv", "run", "python", "-m", "harness_skills.cli.main",
            "evaluate", "--format", "json", "--gate", "principles",
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=self.repo_root,
            )
            output = result.stdout.strip()
            if not output:
                return []

            data = json.loads(output)
            failures = data.get("failures", [])
            gate_failures: list[dict[str, Any]] = []
            for f in failures:
                if f.get("gate_id", "") != "principles" and f.get("gate_id"):
                    # Only include principles gate failures
                    continue
                gate_failures.append({
                    "rule_id": f.get("rule_id", ""),
                    "file_path": f.get("file_path", ""),
                    "line_number": f.get("line_number"),
                    "message": f.get("message", ""),
                    "severity": f.get("severity", "error"),
                    "suggestion": f.get("suggestion", ""),
                    "gate_id": "principles",
                })
            return gate_failures

        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
            # Gate unavailable or output not parseable — caller will fall back
            return []

    def fallback_scan(self, principles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Basic grep-based scan for principle violations.

        Used when the harness gate is unavailable. Searches Python and
        TypeScript source files for patterns that suggest violations.

        Args:
            principles: List of principle dicts from `load_principles`.

        Returns:
            List of GateFailure-style dicts.
        """
        failures: list[dict[str, Any]] = []
        source_files = _source_files(self.repo_root)

        for principle in principles:
            pid = principle["id"]
            rule = principle["rule"].lower()
            severity_raw = principle["severity"]
            # Map severity to gate-style value
            gate_severity = "error" if severity_raw == "blocking" else "warning"

            # Build a heuristic pattern list based on the rule text
            patterns = self._rule_to_patterns(rule)
            if not patterns:
                continue

            for src_file in source_files:
                try:
                    lines = src_file.read_text(encoding="utf-8", errors="replace").splitlines()
                except OSError:
                    continue

                for lineno, line in enumerate(lines, start=1):
                    line_lower = line.lower()
                    for pattern, description in patterns:
                        if re.search(pattern, line_lower):
                            rel_path = str(src_file.relative_to(self.repo_root))
                            failures.append({
                                "rule_id": pid,
                                "file_path": rel_path,
                                "line_number": lineno,
                                "message": f"{description} (fallback scan)",
                                "severity": gate_severity,
                                "suggestion": principle["rule"],
                                "gate_id": "principles",
                            })
                            break  # one violation per line per principle

        return failures

    def group_violations(
        self,
        violations: list[dict[str, Any]],
        principles: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        """Group violation dicts by principle_id.

        Args:
            violations: Flat list of GateFailure-style dicts.
            principles: List of principle dicts (used to order the result).

        Returns:
            OrderedDict mapping principle_id → list of violation dicts,
            preserving the order of principles as defined in the YAML.
        """
        principle_ids = [p["id"] for p in principles]
        grouped: dict[str, list[dict[str, Any]]] = {pid: [] for pid in principle_ids}

        for v in violations:
            rule_id = v.get("rule_id", "")
            if rule_id in grouped:
                grouped[rule_id].append(v)

        # Remove principles with no violations
        return {pid: viols for pid, viols in grouped.items() if viols}

    def generate_task(
        self,
        principle: dict[str, Any],
        violations: list[dict[str, Any]],
    ) -> CleanupTask:
        """Generate a single CleanupTask for a principle violation cluster.

        Args:
            principle: A principle dict from `load_principles`.
            violations: All violations for this principle.

        Returns:
            A fully populated `CleanupTask` instance.
        """
        pid = principle["id"]
        category = principle["category"]
        severity = principle["severity"]
        rule = principle["rule"]

        # Collect unique affected files (sorted)
        scope = sorted({v["file_path"] for v in violations if v.get("file_path")})
        first_file = scope[0] if scope else "unknown"

        task_id = f"cleanup-{_slugify(pid)}-{_slugify(first_file)}"

        # Title: short imperative
        rule_snippet = " ".join(rule.split()[:8])
        if not rule_snippet.endswith((".", "!", "?")):
            rule_snippet = rule_snippet.rstrip(",;:")
        title = f"Enforce {category} rule: {rule_snippet} ({pid})"

        # Description: structured multi-line
        file_count = len(scope)
        file_lines: list[str] = []
        for v in violations:
            fp = v.get("file_path", "")
            ln = v.get("line_number")
            msg = v.get("message", "")
            loc = f"{fp}:{ln}" if ln else fp
            file_lines.append(f"  - {loc}  — {msg}")

        suggestion_lines: list[str] = []
        unique_suggestions = list(dict.fromkeys(
            v["suggestion"] for v in violations if v.get("suggestion")
        ))
        for i, sug in enumerate(unique_suggestions[:3], start=1):
            suggestion_lines.append(f"  {i}. {sug}")

        description_parts = [
            f"Principle {pid} ({category}/{severity}) is violated in {file_count} file(s).",
            "",
            f"Rule: {rule}",
            "",
            "Affected files:",
        ] + file_lines + [
            "",
            "Refactoring steps:",
        ] + (suggestion_lines if suggestion_lines else [
            f"  1. Refactor affected files to comply with the rule: \"{rule}\"",
        ]) + [
            f"  {len(suggestion_lines or [1]) + 1}. Run `/harness:lint --gate principles` to verify zero remaining violations.",
            f"  {len(suggestion_lines or [1]) + 2}. Update or add unit/integration tests covering the refactored code.",
        ]

        description = "\n".join(description_parts)

        # PR title
        scope_sum = _scope_summary(scope)
        pr_title = f"refactor: enforce {pid} {category} across {scope_sum}"

        # PR body
        scope_bullets = "\n".join(f"- `{f}`" for f in scope)
        changes_bullets = self._generate_changes_bullets(principle, violations, scope)

        pr_body = f"""\
## What & Why

Enforces principle {pid} ({category}/{severity}):
"{rule}"

This PR was generated automatically by `/golden-principles-cleanup` after
detecting {len(violations)} violation(s) across the following file(s):
{scope_bullets}

## Changes

{changes_bullets}

## Testing

- [ ] All refactored code has unit tests
- [ ] No violations remain: `uv run python -m harness_skills.cli.main evaluate --gate principles --format json`
- [ ] `/harness:lint` passes with 0 blocking violations
- [ ] Existing test suite passes: `pytest tests/ -v`

## Checklist

- [ ] PR title follows conventional commits (`refactor:` prefix)
- [ ] No unrelated changes included
- [ ] PRINCIPLES.md is up to date (run `/define-principles` if needed)"""

        now = _now_utc()

        return CleanupTask(
            id=task_id,
            principle_id=pid,
            principle_category=category,
            severity=severity,
            title=title,
            scope=scope,
            description=description,
            pr_title=pr_title,
            pr_body=pr_body,
            generated_at=now,
            status="pending",
        )

    def generate_all(
        self,
        principles_file: Path,
        output_file: Path,
        only_blocking: bool = False,
        dry_run: bool = False,
    ) -> CleanupTaskManifest:
        """Run the full generate workflow and return the manifest.

        Args:
            principles_file: Path to .claude/principles.yaml.
            output_file: Where to write cleanup-tasks.yaml (ignored if dry_run).
            only_blocking: If True, skip suggestion-severity principles.
            dry_run: If True, print YAML to stdout instead of writing the file.

        Returns:
            The generated `CleanupTaskManifest`.
        """
        principles = self.load_principles(principles_file)

        if only_blocking:
            principles = [p for p in principles if p["severity"] == "blocking"]

        # Try the harness gate first, fall back to grep scan
        violations = self.run_principles_gate()
        used_fallback = not violations
        if not violations:
            violations = self.fallback_scan(principles)

        grouped = self.group_violations(violations, principles)

        tasks: list[CleanupTask] = []
        for principle in principles:
            pid = principle["id"]
            if pid not in grouped:
                continue
            task = self.generate_task(principle, grouped[pid])
            tasks.append(task)

        now = _now_utc()
        head = _get_git_head()

        manifest = CleanupTaskManifest(
            generated_at=now,
            generated_from_head=head,
            task_count=len(tasks),
            tasks=tasks,
        )

        yaml_content = self._manifest_to_yaml(manifest)

        if dry_run:
            print(f"[dry-run] Would write to {output_file}:")
            print()
            print(yaml_content)
        else:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(yaml_content, encoding="utf-8")
            if used_fallback:
                print(
                    f"[golden-principles-cleanup] Note: harness gate unavailable, used fallback text scan.",
                    file=sys.stderr,
                )
            print(
                f"[golden-principles-cleanup] Wrote {len(tasks)} task(s) to {output_file}"
            )

        return manifest

    def publish_to_shared_state(self, manifest: CleanupTaskManifest) -> None:
        """Publish a summary to shared-state.yaml via the shared_state skill.

        Silently skips if shared-state.yaml does not exist or the script is
        unavailable.

        Args:
            manifest: The generated manifest to summarise.
        """
        shared_state_file = self.repo_root / "docs" / "exec-plans" / "shared-state.yaml"
        if not shared_state_file.exists():
            return

        shared_state_script = self.repo_root / "skills" / "shared_state.py"
        if not shared_state_script.exists():
            return

        payload = json.dumps({
            "cleanup_tasks_generated": manifest.task_count,
            "output": "docs/exec-plans/cleanup-tasks.yaml",
            "generated_from_head": manifest.generated_from_head,
        })

        try:
            subprocess.run(
                [
                    sys.executable,
                    str(shared_state_script),
                    "publish",
                    "--agent", "golden-principles-cleanup",
                    "--type", "other",
                    "--data", payload,
                ],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=self.repo_root,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass  # Non-critical — never block task generation on publish failure

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rule_to_patterns(self, rule_lower: str) -> list[tuple[str, str]]:
        """Return (regex_pattern, description) pairs for a rule heuristic.

        Patterns are matched against lowercased source lines.
        Returns an empty list if no heuristic is known for the rule.
        """
        patterns: list[tuple[str, str]] = []

        if any(kw in rule_lower for kw in ("repository layer", "repository pattern", "db query")):
            patterns += [
                (r"\bdb\.session\b", "direct db.session usage"),
                (r"\bdb\.query\b", "direct db.query usage"),
                (r"\b\.objects\.filter\b", "direct ORM query outside repository"),
                (r"\b\.objects\.get\b", "direct ORM .get() outside repository"),
                (r"\bsession\.execute\b", "direct session.execute usage"),
            ]

        if any(kw in rule_lower for kw in ("integration test", "endpoint", "api test")):
            patterns += [
                (r"@(router|app)\.(get|post|put|patch|delete)\b", "route handler without test counterpart"),
            ]

        if any(kw in rule_lower for kw in ("dataclass", "plain dict", "typed dict")):
            patterns += [
                (r"def \w+\(.*\)\s*->\s*dict\b", "function returning plain dict"),
                (r"return\s*\{['\"]", "returning a plain dict literal"),
            ]

        if any(kw in rule_lower for kw in ("environment variable", "secret", "hardcoded")):
            patterns += [
                (r"(password|secret|api_key|token)\s*=\s*['\"][^'\"]{4,}", "potential hardcoded secret"),
            ]

        if any(kw in rule_lower for kw in ("import", "layer", "module boundary")):
            patterns += [
                (r"from\s+\.\.\.", "relative import crossing module boundary"),
            ]

        return patterns

    def _generate_changes_bullets(
        self,
        principle: dict[str, Any],
        violations: list[dict[str, Any]],
        scope: list[str],
    ) -> str:
        """Generate a bullet list of expected changes for the PR body."""
        rule = principle["rule"]
        category = principle["category"]
        bullets: list[str] = []

        # One bullet per affected file
        seen_files: set[str] = set()
        for v in violations:
            fp = v.get("file_path", "")
            if fp and fp not in seen_files:
                seen_files.add(fp)
                ln = v.get("line_number")
                loc = f"line {ln}" if ln else "multiple locations"
                bullets.append(f"- Refactor `{fp}` ({loc}) to comply with: \"{rule}\"")

        if not bullets:
            for fp in scope:
                bullets.append(f"- Refactor `{fp}` to comply with the {category} principle: \"{rule}\"")

        bullets.append("- Updated affected call-sites to use the new abstraction")
        return "\n".join(bullets)

    @staticmethod
    def _manifest_to_yaml(manifest: CleanupTaskManifest) -> str:
        """Serialise a CleanupTaskManifest to a YAML string."""
        data: dict[str, Any] = {
            "generated_at": manifest.generated_at,
            "generated_from_head": manifest.generated_from_head,
            "task_count": manifest.task_count,
            "tasks": [],
        }
        for task in manifest.tasks:
            data["tasks"].append({
                "id": task.id,
                "principle_id": task.principle_id,
                "principle_category": task.principle_category,
                "severity": task.severity,
                "title": task.title,
                "scope": task.scope,
                "description": task.description,
                "pr_title": task.pr_title,
                "pr_body": task.pr_body,
                "generated_at": task.generated_at,
                "status": task.status,
            })
        return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def _print_summary_table(self, manifest: CleanupTaskManifest, output_file: Path) -> None:
        """Print a formatted summary table of the generated tasks."""
        separator = "=" * 78
        print(separator)
        print(f"  Golden Principles Cleanup — {manifest.task_count} task(s) generated")
        print(f"  Output: {output_file}")
        print(separator)

        if manifest.task_count == 0:
            print()
            print("  No violations found — all principles pass.")
            print("  cleanup-tasks.yaml was not modified.")
            print(separator)
            return

        print()
        header = f"  {'Task ID':<42} {'Principle':<10} {'Severity':<12} {'Files':<6} PR Title"
        print(header)
        print("  " + "-" * 74)

        for task in manifest.tasks:
            pr_title_trunc = task.pr_title[:36] + "..." if len(task.pr_title) > 39 else task.pr_title
            print(
                f"  {task.id:<42} {task.principle_id:<10} {task.severity:<12} "
                f"{len(task.scope):<6} {pr_title_trunc}"
            )

        print()
        print(separator)
        print()
        print("  Next steps:")
        print("    - Each task in cleanup-tasks.yaml can be dispatched to a worker agent.")
        print("    - To apply one task: open the pr_body as a PR description and follow the Changes section.")
        print("    - Re-run after fixing: /golden-principles-cleanup")
        print("    - To validate: /harness:lint --gate principles")
        print(separator)


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="golden_principles_cleanup",
        description="Generate background cleanup tasks from principle violations",
    )
    sub = p.add_subparsers(dest="command", required=True)

    # --- generate ---
    gen = sub.add_parser("generate", help="Scan for violations and generate cleanup-tasks.yaml")
    gen.add_argument(
        "--principles-file",
        dest="principles_file",
        default=str(_DEFAULT_PRINCIPLES_FILE),
        help="Path to principles YAML file (default: .claude/principles.yaml)",
    )
    gen.add_argument(
        "--output",
        dest="output",
        default=str(_DEFAULT_OUTPUT_FILE),
        help="Output path for cleanup-tasks.yaml (default: docs/exec-plans/cleanup-tasks.yaml)",
    )
    gen.add_argument(
        "--only-blocking",
        dest="only_blocking",
        action="store_true",
        default=False,
        help="Only generate tasks for severity: blocking principles",
    )
    gen.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=False,
        help="Print tasks to stdout without writing the file",
    )
    gen.add_argument(
        "--no-publish",
        dest="no_publish",
        action="store_true",
        default=False,
        help="Skip the shared-state publish step",
    )

    # --- list ---
    lst = sub.add_parser("list", help="Print a summary table of an existing cleanup-tasks.yaml")
    lst.add_argument(
        "--output",
        dest="output",
        default=str(_DEFAULT_OUTPUT_FILE),
        help="Path to cleanup-tasks.yaml (default: docs/exec-plans/cleanup-tasks.yaml)",
    )

    return p


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    cleanup = GoldenPrinciplesCleanup()

    if args.command == "generate":
        principles_file = Path(args.principles_file)
        output_file = Path(args.output)

        try:
            manifest = cleanup.generate_all(
                principles_file=principles_file,
                output_file=output_file,
                only_blocking=args.only_blocking,
                dry_run=args.dry_run,
            )
        except FileNotFoundError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(1)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(1)

        if not args.no_publish:
            cleanup.publish_to_shared_state(manifest)

        cleanup._print_summary_table(manifest, output_file)

    elif args.command == "list":
        output_file = Path(args.output)
        if not output_file.exists():
            print(f"ERROR: {output_file} not found. Run 'generate' first.", file=sys.stderr)
            sys.exit(1)

        raw = yaml.safe_load(output_file.read_text(encoding="utf-8"))
        if not raw or "tasks" not in raw:
            print("No tasks found in cleanup-tasks.yaml.", file=sys.stderr)
            sys.exit(0)

        tasks_data = raw.get("tasks", [])
        print(f"\n  Cleanup Tasks — {output_file}")
        print(f"  Generated at: {raw.get('generated_at', 'unknown')}")
        print(f"  From HEAD:    {raw.get('generated_from_head', 'unknown')}")
        print()
        print(f"  {'Task ID':<42} {'Principle':<10} {'Severity':<12} {'Files':<6} {'Status':<10} PR Title")
        print("  " + "-" * 90)
        for t in tasks_data:
            tid = t.get("id", "")
            pid = t.get("principle_id", "")
            sev = t.get("severity", "")
            scope = t.get("scope", [])
            status = t.get("status", "")
            pr_title = t.get("pr_title", "")
            pr_title_trunc = pr_title[:32] + "..." if len(pr_title) > 35 else pr_title
            print(
                f"  {tid:<42} {pid:<10} {sev:<12} {len(scope):<6} {status:<10} {pr_title_trunc}"
            )
        print()

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
