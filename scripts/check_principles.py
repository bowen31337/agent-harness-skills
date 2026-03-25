#!/usr/bin/env python3
"""
scripts/check_principles.py
Golden Principles Violation Scanner

Loads .claude/principles.yaml, scans the staged diff (or a target path) for
violations, and exits non-zero when any `blocking` severity violation is found.

Exit codes:
  0  — all gates passed (no blocking violations)
  1  — one or more blocking violations detected
  2  — internal error (bad config, missing files, etc.)

Usage:
  # Scan staged git diff (default — used in CI pre-merge)
  python scripts/check_principles.py

  # Scan a specific file or directory
  python scripts/check_principles.py --path src/

  # Emit JSON report instead of human-readable output
  python scripts/check_principles.py --format json

  # Write JSON report to a file (and still print to stdout)
  python scripts/check_principles.py --format json --output report.json

  # Show suggestions as well as blocking violations
  python scripts/check_principles.py --show-suggestions

  # Override principles file location
  python scripts/check_principles.py --principles path/to/principles.yaml
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Literal

try:
    import yaml
except ImportError:
    print(
        "ERROR: PyYAML is required. Install it with: uv add pyyaml",
        file=sys.stderr,
    )
    sys.exit(2)

# ── Types ─────────────────────────────────────────────────────────────────────

Severity = Literal["blocking", "suggestion"]

@dataclass
class Principle:
    id: str
    category: str
    severity: Severity
    applies_to: list[str]
    rule: str


@dataclass
class Violation:
    principle: Principle
    message: str
    file_path: str | None = None
    line_number: int | None = None
    snippet: str | None = None
    suggestion: str | None = None


@dataclass
class ScanResult:
    principles_loaded: int = 0
    files_scanned: int = 0
    violations: list[Violation] = field(default_factory=list)

    @property
    def blocking_violations(self) -> list[Violation]:
        return [v for v in self.violations if v.principle.severity == "blocking"]

    @property
    def suggestion_violations(self) -> list[Violation]:
        return [v for v in self.violations if v.principle.severity == "suggestion"]

    @property
    def passed(self) -> bool:
        return len(self.blocking_violations) == 0


# ── Principle loader ───────────────────────────────────────────────────────────

def load_principles(principles_path: Path) -> list[Principle]:
    if not principles_path.exists():
        print(
            f"ERROR: Principles file not found: {principles_path}\n"
            "       Run /define-principles to create it.",
            file=sys.stderr,
        )
        sys.exit(2)

    with principles_path.open() as fh:
        data = yaml.safe_load(fh)

    if not data or "principles" not in data:
        return []

    principles = []
    for entry in data["principles"]:
        principles.append(
            Principle(
                id=entry["id"],
                category=entry["category"],
                severity=entry["severity"],
                applies_to=entry.get("applies_to", ["review-pr", "check-code"]),
                rule=entry["rule"].strip(),
            )
        )
    return principles


# ── Diff / file source ─────────────────────────────────────────────────────────

def get_staged_diff_lines() -> dict[str, list[tuple[int, str]]]:
    """Return {filename: [(line_number, line_text), ...]} for staged additions."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--unified=0"],
            capture_output=True,
            text=True,
            check=False,
        )
        diff_text = result.stdout
    except FileNotFoundError:
        # git not available
        return {}

    files: dict[str, list[tuple[int, str]]] = {}
    current_file: str | None = None
    current_line = 0

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("+++ b/"):
            current_file = raw_line[6:]
            files.setdefault(current_file, [])
        elif raw_line.startswith("@@ "):
            # @@ -old_start,old_count +new_start,new_count @@
            m = re.search(r"\+(\d+)", raw_line)
            current_line = int(m.group(1)) if m else 0
        elif raw_line.startswith("+") and not raw_line.startswith("+++"):
            if current_file is not None:
                files[current_file].append((current_line, raw_line[1:]))
            current_line += 1
        elif not raw_line.startswith("-"):
            current_line += 1

    return files


def get_path_lines(path: Path) -> dict[str, list[tuple[int, str]]]:
    """Return {filename: [(line_number, line_text), ...]} for all text files under path."""
    files: dict[str, list[tuple[int, str]]] = {}
    targets = [path] if path.is_file() else path.rglob("*")
    for p in targets:
        if not p.is_file():
            continue
        try:
            text = p.read_text(errors="replace")
        except OSError:
            continue
        files[str(p)] = [(i + 1, line) for i, line in enumerate(text.splitlines())]
    return files


# ── Per-principle checks ───────────────────────────────────────────────────────

# Each checker receives (principle, files_dict) and yields Violation objects.
# Add new checkers here and register them in CHECKERS below.

def _check_plan_field_in_pr(
    principle: Principle,
    files: dict[str, list[tuple[int, str]]],
) -> list[Violation]:
    """P001 / P003 — PR description must contain `Plan: <ref>`."""
    violations: list[Violation] = []
    pr_body_files = [f for f in files if "PR_BODY" in f or f.endswith(".pr_body")]
    for fname in pr_body_files:
        lines = files[fname]
        text = "\n".join(line for _, line in lines)
        if not re.search(r"^\s*Plan\s*:\s*\S+", text, re.MULTILINE | re.IGNORECASE):
            violations.append(
                Violation(
                    principle=principle,
                    message=f"PR body in '{fname}' is missing a `Plan: <ref>` field.",
                    file_path=fname,
                    suggestion='Add a line like `Plan: plans/feat-your-feature.md` near the top of the PR body.',
                )
            )
    return violations


def _check_plans_directory(
    principle: Principle,
    files: dict[str, list[tuple[int, str]]],
) -> list[Violation]:
    """P002 — plans/ directory must exist and contain at least one plan file."""
    plans_dir = Path("plans")
    if not plans_dir.is_dir() or not any(plans_dir.iterdir()):
        return [
            Violation(
                principle=principle,
                message="No plan files found in the `plans/` directory.",
                suggestion=(
                    "Create the `plans/` directory and commit your execution plan "
                    "before opening a PR (e.g. `plans/feat-my-feature.md`)."
                ),
            )
        ]
    return []


def _check_no_draft_plan(
    principle: Principle,
    files: dict[str, list[tuple[int, str]]],
) -> list[Violation]:
    """P005 — Referenced plan must not have `status: draft`."""
    violations: list[Violation] = []
    plans_dir = Path("plans")
    if not plans_dir.is_dir():
        return violations
    for plan_file in plans_dir.rglob("*.md"):
        try:
            text = plan_file.read_text()
        except OSError:
            continue
        if re.search(r"^status\s*:\s*draft", text, re.MULTILINE | re.IGNORECASE):
            violations.append(
                Violation(
                    principle=principle,
                    message=f"Plan `{plan_file}` has `status: draft` — only approved plans may back a merge.",
                    file_path=str(plan_file),
                    suggestion="Update the plan's status to `approved` before merging.",
                )
            )
    return violations


def _check_ci_principles_gate(
    principle: Principle,
    files: dict[str, list[tuple[int, str]]],
) -> list[Violation]:
    """P006 — CI must include a principles compliance gate step."""
    ci_files = [
        ".gitlab-ci.yml",
        ".github/workflows/principles-gate.yml",
    ]
    found = any(Path(f).exists() for f in ci_files)
    if not found:
        return [
            Violation(
                principle=principle,
                message=(
                    "No principles compliance gate found in CI configuration. "
                    "Expected `.gitlab-ci.yml` or `.github/workflows/principles-gate.yml`."
                ),
                suggestion=(
                    "Add a CI job that runs `python scripts/check_principles.py` "
                    "and fails on blocking violations."
                ),
            )
        ]
    # Also verify the gate actually calls this script or harness evaluate
    for ci_file in ci_files:
        p = Path(ci_file)
        if not p.exists():
            continue
        content = p.read_text()
        if "check_principles" in content or "principles" in content.lower():
            return []  # gate found and wired up
    return [
        Violation(
            principle=principle,
            message="CI file exists but does not appear to invoke the principles scanner.",
            suggestion=(
                "Ensure your CI job calls `python scripts/check_principles.py` "
                "or `harness evaluate --gate principles`."
            ),
        )
    ]


def _generic_keyword_check(
    principle: Principle,
    files: dict[str, list[tuple[int, str]]],
) -> list[Violation]:
    """Fallback heuristic: flag TODO/FIXME annotations referencing the principle id."""
    violations: list[Violation] = []
    pat = re.compile(
        rf"(TODO|FIXME|HACK)\s*[:\(].*\b{re.escape(principle.id)}\b",
        re.IGNORECASE,
    )
    for fname, lines in files.items():
        for lineno, text in lines:
            if pat.search(text):
                violations.append(
                    Violation(
                        principle=principle,
                        message=f"Unresolved annotation referencing {principle.id}.",
                        file_path=fname,
                        line_number=lineno,
                        snippet=text.strip(),
                    )
                )
    return violations


# Map principle IDs → dedicated checkers (falls back to generic keyword check)
CHECKERS: dict[str, list] = {
    "P001": [_check_plan_field_in_pr],
    "P002": [_check_plans_directory],
    "P003": [_check_plan_field_in_pr],
    "P005": [_check_no_draft_plan],
    "P006": [_check_ci_principles_gate],
}


# ── Scanner ────────────────────────────────────────────────────────────────────

def scan(
    principles: list[Principle],
    files: dict[str, list[tuple[int, str]]],
    skill: str = "check-code",
) -> ScanResult:
    result = ScanResult(
        principles_loaded=len(principles),
        files_scanned=len(files),
    )
    for principle in principles:
        if skill not in principle.applies_to:
            continue
        checkers = CHECKERS.get(principle.id, [_generic_keyword_check])
        for checker in checkers:
            result.violations.extend(checker(principle, files))
    return result


# ── Reporters ─────────────────────────────────────────────────────────────────

_SEP = "━" * 72


def _severity_icon(severity: Severity) -> str:
    return "🔴" if severity == "blocking" else "🟡"


def report_human(result: ScanResult, show_suggestions: bool) -> None:
    print(_SEP)
    print("  Golden Principles Compliance Gate")
    print(_SEP)
    print(f"  Principles loaded : {result.principles_loaded}")
    print(f"  Files scanned     : {result.files_scanned}")
    total_v = len(result.violations)
    blocking_v = len(result.blocking_violations)
    print(f"  Total violations  : {total_v}  ({blocking_v} blocking)")
    print()

    if result.blocking_violations:
        print("  🔴 BLOCKING VIOLATIONS — must be resolved before merge")
        print()
        for v in result.blocking_violations:
            loc = f"  [{v.principle.id}] {v.principle.category.upper()}"
            if v.file_path:
                loc += f"  →  {v.file_path}"
                if v.line_number:
                    loc += f":{v.line_number}"
            print(loc)
            print(f"  {_severity_icon(v.principle.severity)} {v.message}")
            if v.snippet:
                print(f"     snippet: {v.snippet!r}")
            if v.suggestion:
                print(f"     💡 {v.suggestion}")
            print()

    if show_suggestions and result.suggestion_violations:
        print("  🟡 SUGGESTIONS")
        print()
        for v in result.suggestion_violations:
            loc = f"  [{v.principle.id}] {v.principle.category.upper()}"
            if v.file_path:
                loc += f"  →  {v.file_path}"
                if v.line_number:
                    loc += f":{v.line_number}"
            print(loc)
            print(f"  {_severity_icon(v.principle.severity)} {v.message}")
            if v.suggestion:
                print(f"     💡 {v.suggestion}")
            print()

    if result.passed:
        print("  ✅ All blocking principle gates passed.")
    else:
        print("  ❌ Compliance gate FAILED — resolve blocking violations above.")
    print(_SEP)


def report_json(result: ScanResult) -> dict:
    def _v_dict(v: Violation) -> dict:
        d: dict = {
            "principle_id": v.principle.id,
            "category": v.principle.category,
            "severity": v.principle.severity,
            "message": v.message,
        }
        if v.file_path:
            d["file_path"] = v.file_path
        if v.line_number:
            d["line_number"] = v.line_number
        if v.snippet:
            d["snippet"] = v.snippet
        if v.suggestion:
            d["suggestion"] = v.suggestion
        return d

    return {
        "passed": result.passed,
        "summary": {
            "principles_loaded": result.principles_loaded,
            "files_scanned": result.files_scanned,
            "total_violations": len(result.violations),
            "blocking_failures": len(result.blocking_violations),
            "suggestions": len(result.suggestion_violations),
        },
        "failures": [_v_dict(v) for v in result.blocking_violations],
        "suggestions": [_v_dict(v) for v in result.suggestion_violations],
    }


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Golden Principles Violation Scanner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--principles",
        default=".claude/principles.yaml",
        help="Path to principles YAML file (default: .claude/principles.yaml)",
    )
    parser.add_argument(
        "--path",
        default=None,
        help="Scan a file or directory instead of the staged git diff",
    )
    parser.add_argument(
        "--format",
        choices=["human", "json"],
        default="human",
        help="Output format (default: human)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Write JSON report to this file (only with --format json)",
    )
    parser.add_argument(
        "--show-suggestions",
        action="store_true",
        help="Also display suggestion-severity violations (not just blocking)",
    )
    parser.add_argument(
        "--skill",
        default="check-code",
        choices=["check-code", "review-pr"],
        help="Which skill context to use when filtering applies_to (default: check-code)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # 1. Load principles
    principles_path = Path(args.principles)
    try:
        principles = load_principles(principles_path)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"ERROR loading principles: {exc}", file=sys.stderr)
        return 2

    # 2. Collect files to scan
    if args.path:
        target = Path(args.path)
        if not target.exists():
            print(f"ERROR: --path '{target}' does not exist.", file=sys.stderr)
            return 2
        files = get_path_lines(target)
    else:
        files = get_staged_diff_lines()

    # 3. Scan
    result = scan(principles, files, skill=args.skill)

    # 4. Report
    if args.format == "json":
        payload = report_json(result)
        json_str = json.dumps(payload, indent=2)
        print(json_str)
        if args.output:
            Path(args.output).write_text(json_str)
    else:
        report_human(result, show_suggestions=args.show_suggestions)

    # 5. Exit code
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
