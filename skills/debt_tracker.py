"""
skills/debt_tracker.py — Technical Debt Tracker

Agents use this script to append, resolve, and summarise technical-debt
entries in docs/exec-plans/debt.md.

Usage (CLI)
-----------
  # Log a new debt item
  python skills/debt_tracker.py log \
      --severity high \
      --area "src/auth/middleware.py" \
      --description "Token not validated in service layer" \
      --remediation "Move validation into AuthService.verify()" \
      --logged-by "agent/coder-v1"

  # Resolve an existing item
  python skills/debt_tracker.py resolve \
      --id DEBT-003 \
      --resolution "Moved validation; tests green" \
      --resolved-by "agent/coder-v1"

  # Print a summary table to stdout
  python skills/debt_tracker.py summary

Programmatic use
----------------
  from skills.debt_tracker import DebtTracker
  tracker = DebtTracker()
  tracker.log(severity="medium", area="src/api/rate_limit.py",
               description="Hard-coded 100 req/min constant",
               remediation="Load from tenant config / env var",
               logged_by="agent/planner-v1")
  tracker.summary()
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
DEBT_FILE = _REPO_ROOT / "docs" / "exec-plans" / "debt.md"

# ---------------------------------------------------------------------------
# Severity helpers
# ---------------------------------------------------------------------------
SEVERITY_EMOJI = {
    "critical": "🔴 **critical**",
    "high":     "🟠 **high**",
    "medium":   "🟡 **medium**",
    "low":      "🟢 **low**",
}

SEVERITY_ORDER = ["critical", "high", "medium", "low"]


def _normalise_severity(raw: str) -> str:
    s = raw.strip().lower()
    if s not in SEVERITY_EMOJI:
        raise ValueError(
            f"Unknown severity {raw!r}. Valid values: {', '.join(SEVERITY_ORDER)}"
        )
    return s


# ---------------------------------------------------------------------------
# Markdown helpers
# ---------------------------------------------------------------------------
_OPEN_ANCHOR   = "<!-- agents append new entries here — do not remove this comment -->"
_CLOSED_ANCHOR = "<!-- move entries here when remediation is complete -->"
_SUMMARY_OPEN  = "## Debt Summary"

_OPEN_HEADER = (
    "| ID | Severity | Area / File | Description | Remediation Notes"
    " | Logged By | Logged At | Status |"
)
_OPEN_SEP = (
    "|----|----------|-------------|-------------|-------------------"
    "|-----------|-----------|----|"  # mirrored from existing file
)

_RESOLVED_HEADER = (
    "| ID | Severity | Area / File | Description"
    " | Resolution | Resolved By | Resolved At |"
)
_RESOLVED_SEP = (
    "|----|----------|-------------|-------------"
    "|------------|-------------|-------------|"
)


def _table_row_open(
    id_: str,
    severity: str,
    area: str,
    description: str,
    remediation: str,
    logged_by: str,
    logged_at: str,
    status: str = "open",
) -> str:
    return (
        f"| {id_} | {SEVERITY_EMOJI[severity]} | {area} | {description}"
        f" | {remediation} | {logged_by} | {logged_at} | {status} |"
    )


def _table_row_resolved(
    id_: str,
    severity: str,
    area: str,
    description: str,
    resolution: str,
    resolved_by: str,
    resolved_at: str,
) -> str:
    return (
        f"| {id_} | {SEVERITY_EMOJI[severity]} | {area} | {description}"
        f" | {resolution} | {resolved_by} | {resolved_at} |"
    )


# ---------------------------------------------------------------------------
# Core tracker class
# ---------------------------------------------------------------------------
class DebtTracker:
    """Read, mutate, and write docs/exec-plans/debt.md."""

    def __init__(self, debt_file: Path = DEBT_FILE) -> None:
        self.debt_file = debt_file
        self.debt_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.debt_file.exists():
            self._initialise_file()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log(
        self,
        severity: str,
        area: str,
        description: str,
        remediation: str,
        logged_by: str,
        logged_at: Optional[str] = None,
    ) -> str:
        """Append a new open-debt entry. Returns the assigned DEBT-NNN id."""
        severity = _normalise_severity(severity)
        if logged_at is None:
            logged_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        content = self.debt_file.read_text(encoding="utf-8")
        new_id = self._next_id(content)

        row = _table_row_open(
            id_=new_id,
            severity=severity,
            area=area,
            description=description,
            remediation=remediation,
            logged_by=logged_by,
            logged_at=logged_at,
        )

        # Insert *after* the anchor comment (and the header rows if present)
        content = self._insert_open_row(content, row)
        content = self._rebuild_summary(content)
        self.debt_file.write_text(content, encoding="utf-8")
        print(f"[debt-tracker] Logged {new_id} ({severity}): {description[:60]}")
        return new_id

    def resolve(
        self,
        id_: str,
        resolution: str,
        resolved_by: str,
        resolved_at: Optional[str] = None,
    ) -> None:
        """Move a debt entry from Open to Resolved."""
        id_ = id_.upper().strip()
        if resolved_at is None:
            resolved_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        content = self.debt_file.read_text(encoding="utf-8")

        # Find the open row
        pattern = re.compile(
            r"^\| " + re.escape(id_) + r" \|.*$", re.MULTILINE
        )
        match = pattern.search(content)
        if not match:
            raise ValueError(f"No open entry found with id {id_!r}")

        raw_row = match.group(0)
        cols = [c.strip() for c in raw_row.split("|")[1:-1]]
        # cols: id, severity, area, description, remediation, logged_by, logged_at, status
        if len(cols) < 5:
            raise ValueError(f"Unexpected row format for {id_!r}: {raw_row!r}")

        sev_raw = cols[1]
        area = cols[2]
        description = cols[3]

        # Derive plain severity key from emoji label
        severity_key = next(
            (k for k in SEVERITY_ORDER if k in sev_raw.lower()), "low"
        )

        resolved_row = _table_row_resolved(
            id_=id_,
            severity=severity_key,
            area=area,
            description=description,
            resolution=resolution,
            resolved_by=resolved_by,
            resolved_at=resolved_at,
        )

        # Remove open row
        content = content.replace(raw_row + "\n", "").replace(raw_row, "")
        # Insert into resolved section
        content = self._insert_resolved_row(content, resolved_row)
        content = self._rebuild_summary(content)
        self.debt_file.write_text(content, encoding="utf-8")
        print(f"[debt-tracker] Resolved {id_}: {resolution[:60]}")

    def summary(self) -> None:
        """Print a plain-text debt summary to stdout."""
        content = self.debt_file.read_text(encoding="utf-8")
        counts = self._count_entries(content)
        print("\n=== Technical Debt Summary ===")
        print(f"  Total open : {counts['total_open']}")
        for sev in SEVERITY_ORDER:
            print(f"  {sev.capitalize():8s}: {counts[sev]}")
        print(f"  Resolved   : {counts['resolved']}")
        print()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _next_id(self, content: str) -> str:
        ids = re.findall(r"DEBT-(\d+)", content)
        next_num = max((int(n) for n in ids), default=0) + 1
        return f"DEBT-{next_num:03d}"

    def _insert_open_row(self, content: str, row: str) -> str:
        """Insert row immediately after the Open-section anchor + header."""
        anchor_pos = content.find(_OPEN_ANCHOR)
        if anchor_pos == -1:
            raise RuntimeError("Could not find open-debt anchor in debt.md")

        # Find the end of the anchor line
        insert_after = content.find("\n", anchor_pos) + 1

        # Skip blank lines and header/separator rows that already exist
        tail = content[insert_after:]
        for line in tail.splitlines(keepends=True):
            stripped = line.strip()
            if stripped.startswith("| ID |") or stripped.startswith("|----"):
                insert_after += len(line)
            elif stripped == "":
                insert_after += len(line)
            else:
                break

        return content[:insert_after] + row + "\n" + content[insert_after:]

    def _insert_resolved_row(self, content: str, row: str) -> str:
        """Insert row immediately after the Resolved-section anchor + header."""
        anchor_pos = content.find(_CLOSED_ANCHOR)
        if anchor_pos == -1:
            # Fallback: append before the summary section
            summary_pos = content.find(_SUMMARY_OPEN)
            if summary_pos == -1:
                return content + "\n" + row + "\n"
            return content[:summary_pos] + row + "\n\n" + content[summary_pos:]

        insert_after = content.find("\n", anchor_pos) + 1
        tail = content[insert_after:]
        for line in tail.splitlines(keepends=True):
            stripped = line.strip()
            if stripped.startswith("| ID |") or stripped.startswith("|----"):
                insert_after += len(line)
            elif stripped == "":
                insert_after += len(line)
            else:
                break

        return content[:insert_after] + row + "\n" + content[insert_after:]

    def _count_entries(self, content: str) -> dict:
        counts: dict = {sev: 0 for sev in SEVERITY_ORDER}
        counts["total_open"] = 0
        counts["resolved"] = 0

        open_section = self._section_between(content, _OPEN_ANCHOR, _CLOSED_ANCHOR)
        resolved_section = self._section_between(content, _CLOSED_ANCHOR, _SUMMARY_OPEN)

        for line in open_section.splitlines():
            if not line.startswith("| DEBT-"):
                continue
            counts["total_open"] += 1
            for sev in SEVERITY_ORDER:
                if sev in line.lower():
                    counts[sev] += 1
                    break

        for line in resolved_section.splitlines():
            if line.startswith("| DEBT-"):
                counts["resolved"] += 1

        return counts

    def _section_between(self, content: str, start_marker: str, end_marker: str) -> str:
        s = content.find(start_marker)
        e = content.find(end_marker)
        if s == -1:
            return ""
        if e == -1:
            return content[s:]
        return content[s:e]

    def _rebuild_summary(self, content: str) -> str:
        """Rewrite the Debt Summary table with current counts."""
        counts = self._count_entries(content)

        new_summary = f"""\
## Debt Summary

_Updated automatically by `skills/debt_tracker.py` on each run._

| Metric | Count |
|--------|-------|
| Total open | {counts['total_open']} |
| Critical | {counts['critical']} |
| High | {counts['high']} |
| Medium | {counts['medium']} |
| Low | {counts['low']} |
| Resolved (all time) | {counts['resolved']} |
"""

        summary_pos = content.find(_SUMMARY_OPEN)
        if summary_pos == -1:
            return content + "\n---\n\n" + new_summary
        return content[:summary_pos] + new_summary

    def _initialise_file(self) -> None:
        self.debt_file.write_text(
            """\
# Technical Debt Tracker

> Agents append entries below using `skills/debt_tracker.py`.
> Each entry records a known shortcut, compromise, or TODO with severity and a clear path to remediation.

---

## Severity Key

| Severity | Meaning |
|----------|---------|
| 🔴 **critical** | Blocks correctness, security, or production safety. Remediate before next release. |
| 🟠 **high**     | Degrades reliability or maintainability significantly. Remediate within 1–2 sprints. |
| 🟡 **medium**   | Noticeable friction or tech-debt accumulation. Remediate within the quarter. |
| 🟢 **low**      | Minor polish or nice-to-have. Track and batch into a cleanup sprint. |

---

## Open Debt

<!-- agents append new entries here — do not remove this comment -->

| ID | Severity | Area / File | Description | Remediation Notes | Logged By | Logged At | Status |
|----|----------|-------------|-------------|-------------------|-----------|-----------|--------|

---

## Resolved Debt

<!-- move entries here when remediation is complete -->

| ID | Severity | Area / File | Description | Resolution | Resolved By | Resolved At |
|----|----------|-------------|-------------|------------|-------------|-------------|

---

## Debt Summary

_Updated automatically by `skills/debt_tracker.py` on each run._

| Metric | Count |
|--------|-------|
| Total open | 0 |
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Low | 0 |
| Resolved (all time) | 0 |
""",
            encoding="utf-8",
        )
        print(f"[debt-tracker] Initialised {self.debt_file}")


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="debt_tracker",
        description="Log and manage technical debt in docs/exec-plans/debt.md",
    )
    sub = p.add_subparsers(dest="command", required=True)

    # --- log ---
    log_p = sub.add_parser("log", help="Append a new open-debt entry")
    log_p.add_argument(
        "--severity", required=True,
        choices=SEVERITY_ORDER,
        help="Severity level: critical | high | medium | low",
    )
    log_p.add_argument("--area", required=True, help="File path or system area affected")
    log_p.add_argument("--description", required=True, help="Short description of the debt")
    log_p.add_argument("--remediation", required=True, help="How to fix it")
    log_p.add_argument("--logged-by", required=True, dest="logged_by",
                       help="Agent or human who identified this debt")
    log_p.add_argument("--logged-at", dest="logged_at", default=None,
                       help="Override timestamp (ISO-ish, default: now UTC)")
    log_p.add_argument("--debt-file", default=None,
                       help="Override path to debt.md")

    # --- resolve ---
    res_p = sub.add_parser("resolve", help="Mark an open debt item as resolved")
    res_p.add_argument("--id", required=True, dest="id_",
                       help="Debt ID to resolve, e.g. DEBT-003")
    res_p.add_argument("--resolution", required=True,
                       help="What was done to fix it")
    res_p.add_argument("--resolved-by", required=True, dest="resolved_by",
                       help="Agent or human who resolved it")
    res_p.add_argument("--resolved-at", dest="resolved_at", default=None,
                       help="Override timestamp (default: now UTC)")
    res_p.add_argument("--debt-file", default=None,
                       help="Override path to debt.md")

    # --- summary ---
    sum_p = sub.add_parser("summary", help="Print debt summary to stdout")
    sum_p.add_argument("--debt-file", default=None,
                       help="Override path to debt.md")

    return p


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    debt_file = Path(args.debt_file) if getattr(args, "debt_file", None) else DEBT_FILE
    tracker = DebtTracker(debt_file=debt_file)

    if args.command == "log":
        tracker.log(
            severity=args.severity,
            area=args.area,
            description=args.description,
            remediation=args.remediation,
            logged_by=args.logged_by,
            logged_at=args.logged_at,
        )
    elif args.command == "resolve":
        tracker.resolve(
            id_=args.id_,
            resolution=args.resolution,
            resolved_by=args.resolved_by,
            resolved_at=args.resolved_at,
        )
    elif args.command == "summary":
        tracker.summary()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
