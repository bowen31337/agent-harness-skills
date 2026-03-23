#!/usr/bin/env python3
"""
scripts/import_principles.py
Import principles from a YAML config file into .claude/principles.yaml.

This script provides a non-interactive alternative to /define-principles,
allowing engineers to define golden rules in a portable YAML file and merge
them into the project principles store.  Both workflows produce an identical
.claude/principles.yaml — the interactive prompt is just a guided editor.

Usage:
  # Import from a file (merges with existing principles)
  python scripts/import_principles.py --from-file my-principles.yaml

  # Preview what would be imported without writing anything
  python scripts/import_principles.py --from-file my-principles.yaml --dry-run

  # Override the target principles file location
  python scripts/import_principles.py --from-file new.yaml --target custom/principles.yaml

  # Fail if any incoming principle has an ID that already exists
  python scripts/import_principles.py --from-file new.yaml --strict-ids

Exit codes:
  0  — success (principles written, or dry-run, or nothing to import)
  1  — validation error in the source file, or --strict-ids collision
  2  — internal error (bad config, file not found, etc.)
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
import re
import sys
from typing import Literal

try:
    import yaml
except ImportError:
    print(
        "ERROR: PyYAML is required. Install it with: pip install pyyaml",
        file=sys.stderr,
    )
    sys.exit(2)

# ── Constants ─────────────────────────────────────────────────────────────────

PRINCIPLES_FILE = Path(".claude/principles.yaml")
VALID_SEVERITIES: frozenset[str] = frozenset({"blocking", "suggestion"})
VALID_APPLIES_TO: frozenset[str] = frozenset({"review-pr", "check-code"})
# Acceptable ID patterns: P001, MB014, FEAT001, SEC01, …
ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*\d{2,}$")

# ── Types ─────────────────────────────────────────────────────────────────────

Severity = Literal["blocking", "suggestion"]


@dataclass
class PrincipleEntry:
    id: str
    category: str
    severity: Severity
    applies_to: list[str]
    rule: str


@dataclass
class ImportResult:
    added: list[PrincipleEntry] = field(default_factory=list)
    skipped: list[tuple[PrincipleEntry, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def success(self) -> bool:
        return not self.has_errors


# ── Loader ────────────────────────────────────────────────────────────────────


def load_yaml_file(path: Path) -> dict:
    """Load and parse a YAML file, returning the raw dict."""
    if not path.exists():
        print(f"ERROR: File not found: {path}", file=sys.stderr)
        sys.exit(2)
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data or {}


def load_existing_principles(target: Path) -> list[PrincipleEntry]:
    """Load existing principles from the target file (returns [] if missing)."""
    if not target.exists():
        return []
    data = load_yaml_file(target)
    entries: list[PrincipleEntry] = []
    for item in data.get("principles", []):
        entries.append(
            PrincipleEntry(
                id=item["id"],
                category=item["category"],
                severity=item["severity"],  # type: ignore[arg-type]
                applies_to=item.get("applies_to", ["review-pr", "check-code"]),
                rule=item["rule"].strip(),
            )
        )
    return entries


# ── Validation ────────────────────────────────────────────────────────────────


def validate_principle_entry(
    raw: dict, index: int
) -> tuple[PrincipleEntry | None, list[str]]:
    """
    Validate a raw principle dict from the source YAML.

    Returns (PrincipleEntry, []) on success, or (None, [error_strings]) on failure.
    """
    errors: list[str] = []
    label = f"principles[{index}]"

    # Check required fields first — all subsequent checks need them
    for field_name in ("category", "severity", "rule"):
        if field_name not in raw:
            errors.append(f"{label}: missing required field '{field_name}'")

    if errors:
        return None, errors

    severity: str = raw["severity"]
    if severity not in VALID_SEVERITIES:
        errors.append(
            f"{label}: invalid severity '{severity}'. "
            f"Must be one of: {', '.join(sorted(VALID_SEVERITIES))}"
        )

    applies_to = raw.get("applies_to", list(VALID_APPLIES_TO))
    if isinstance(applies_to, str):
        applies_to = [applies_to]
    invalid_applies = set(applies_to) - VALID_APPLIES_TO
    if invalid_applies:
        errors.append(
            f"{label}: invalid applies_to values: {sorted(invalid_applies)}. "
            f"Must be a subset of: {sorted(VALID_APPLIES_TO)}"
        )

    rule: str = raw.get("rule", "").strip()
    if not rule:
        errors.append(f"{label}: 'rule' must be a non-empty string")

    category: str = raw.get("category", "").strip()
    if not category:
        errors.append(f"{label}: 'category' must be a non-empty string")

    # 'id' is optional; validate format when supplied
    raw_id: str = raw.get("id", "").strip()
    if raw_id and not ID_PATTERN.match(raw_id):
        errors.append(
            f"{label}: id '{raw_id}' does not match expected pattern "
            "(e.g. P001, MB014). Omit the id field to have it auto-assigned."
        )

    if errors:
        return None, errors

    return (
        PrincipleEntry(
            id=raw_id,  # may be empty → assigned during merge
            category=category,
            severity=severity,  # type: ignore[arg-type]
            applies_to=list(applies_to),
            rule=rule,
        ),
        [],
    )


# ── ID assignment ─────────────────────────────────────────────────────────────


def _p_series_numbers(principles: list[PrincipleEntry]) -> set[int]:
    """Return numeric suffixes of all existing P-series IDs (P001 → 1)."""
    nums: set[int] = set()
    for p in principles:
        m = re.match(r"^P(\d+)$", p.id)
        if m:
            nums.add(int(m.group(1)))
    return nums


def assign_next_id(existing: list[PrincipleEntry]) -> str:
    """Return the next unused P-series ID (never reuses deleted IDs)."""
    used = _p_series_numbers(existing)
    n = 1
    while n in used:
        n += 1
    return f"P{n:03d}"


# ── Merge ─────────────────────────────────────────────────────────────────────


def merge_principles(
    existing: list[PrincipleEntry],
    incoming: list[PrincipleEntry],
    *,
    strict_ids: bool = False,
) -> ImportResult:
    """
    Merge *incoming* principles into the *existing* list.

    ID assignment rules:
    - Incoming entry with no id → auto-assigns the next P-series id.
    - Incoming entry whose id already exists in *existing*:
        - strict_ids=False (default): skip with a warning.
        - strict_ids=True: record as an error and abort the whole import.
    - IDs are stable: existing principles are never renumbered.
    """
    result = ImportResult()
    existing_ids: set[str] = {p.id for p in existing}
    # working_list tracks IDs seen so far (for correct sequential assignment
    # when multiple auto-assign entries arrive in the same batch).
    working_list = list(existing)

    for entry in incoming:
        if not entry.id:
            entry.id = assign_next_id(working_list)

        if entry.id in existing_ids:
            msg = f"Principle '{entry.id}' already exists — skipped."
            if strict_ids:
                result.errors.append(f"ERROR: {msg}")
            else:
                result.skipped.append((entry, msg))
            continue

        existing_ids.add(entry.id)
        working_list.append(entry)
        result.added.append(entry)

    return result


# ── Writer ────────────────────────────────────────────────────────────────────


def _entry_to_dict(p: PrincipleEntry) -> dict:
    return {
        "id": p.id,
        "category": p.category,
        "severity": p.severity,
        "applies_to": list(p.applies_to),
        "rule": p.rule,
    }


def write_principles(principles: list[PrincipleEntry], target: Path) -> None:
    """Write the full principles list to *target*, preserving the standard header."""
    target.parent.mkdir(parents=True, exist_ok=True)

    header = (
        "# .claude/principles.yaml\n"
        "# Project-specific golden rules enforced by check-code and review-pr.\n"
        "# Edit this file directly or run /define-principles to use the interactive prompt.\n"
        "#\n"
    )

    payload: dict = {
        "version": "1.0",
        "principles": [_entry_to_dict(p) for p in principles],
    }
    yaml_body = yaml.dump(
        payload,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        indent=2,
    )
    target.write_text(header + "\n" + yaml_body, encoding="utf-8")


# ── Reporter ──────────────────────────────────────────────────────────────────

_SEP = "━" * 64


def _sev_icon(severity: str) -> str:
    return "🔴" if severity == "blocking" else "🟡"


def report(result: ImportResult, *, dry_run: bool) -> None:
    mode = " (DRY RUN — nothing written)" if dry_run else ""
    print(_SEP)
    print(f"  Principle Import Summary{mode}")
    print(_SEP)

    if result.added:
        print(f"\n  ✅ Added ({len(result.added)}):")
        for p in result.added:
            icon = _sev_icon(p.severity)
            rule_preview = p.rule[:68] + "…" if len(p.rule) > 68 else p.rule
            print(f"     {p.id}  [{p.category}]  {icon} {p.severity}  — {rule_preview}")

    if result.skipped:
        print(f"\n  ⚠️  Skipped ({len(result.skipped)}):")
        for p, reason in result.skipped:
            print(f"     {p.id}  — {reason}")

    if result.errors:
        print(f"\n  ❌ Errors ({len(result.errors)}):")
        for err in result.errors:
            print(f"     {err}")

    if not result.added and not result.skipped and not result.errors:
        print("\n  (nothing to import — source file may be empty)")

    print()
    print(_SEP)


# ── CLI ───────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import principles from a YAML config file into .claude/principles.yaml",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--from-file",
        required=True,
        metavar="PATH",
        help="Source YAML file containing principles to import",
    )
    parser.add_argument(
        "--target",
        default=str(PRINCIPLES_FILE),
        metavar="PATH",
        help=f"Target principles file to merge into (default: {PRINCIPLES_FILE})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be imported without writing to disk",
    )
    parser.add_argument(
        "--strict-ids",
        action="store_true",
        help="Exit 1 if any incoming principle has a conflicting ID (default: skip silently)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = Path(args.from_file)
    target = Path(args.target)

    # 1. Load source YAML
    source_data = load_yaml_file(source)
    raw_principles: list[dict] = source_data.get("principles", [])
    if not raw_principles:
        print(f"No principles found in '{source}'.")
        return 0

    # 2. Validate each entry
    all_errors: list[str] = []
    valid_entries: list[PrincipleEntry] = []
    for i, raw in enumerate(raw_principles):
        entry, errors = validate_principle_entry(raw, i)
        if errors:
            all_errors.extend(errors)
        elif entry is not None:
            valid_entries.append(entry)

    if all_errors:
        print("Validation errors in source file:", file=sys.stderr)
        for err in all_errors:
            print(f"  {err}", file=sys.stderr)
        return 1

    # 3. Load existing principles (empty list if target doesn't exist yet)
    existing = load_existing_principles(target)

    # 4. Merge
    result = merge_principles(existing, valid_entries, strict_ids=args.strict_ids)

    # 5. Report
    report(result, dry_run=args.dry_run)

    if result.has_errors:
        return 1

    # 6. Write (unless --dry-run or nothing was added)
    if not args.dry_run and result.added:
        merged = existing + result.added
        write_principles(merged, target)
        print(f"  Wrote {len(merged)} principle(s) → {target}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
