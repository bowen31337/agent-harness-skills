"""
harness_skills/gates/agents_md_token.py
=========================================
AGENTS.md token-budget gate implementation.

The gate scans every file matching a configurable glob pattern (default:
``**/AGENTS.md``) under the repository root and blocks the build when any
single file's **estimated token count** exceeds the configured maximum
(default **800 tokens**).

Token estimation
-----------------
Token counts are approximated with the character-count heuristic::

    estimated_tokens = ceil(len(text) / chars_per_token)

where ``chars_per_token`` defaults to **4.0** — a well-established rough
average for English prose and code mixed content (matching OpenAI's guidance
for GPT-family models, which also applies closely to Claude).

This is intentionally an *estimate*: the gate's goal is to keep AGENTS.md
files reasonably concise so they do not pollute an agent's context window,
not to enforce an exact byte-level budget.  For tighter accuracy, swap in a
tiktoken-based counter as a post-processor.

Why this matters
-----------------
Every AGENTS.md file loaded by an agent occupies tokens in its context
window.  A repository with multiple, verbose AGENTS.md files can silently
exhaust a significant fraction of the context budget before the agent reads
a single line of task-relevant code.  The token-budget gate enforces a hard
ceiling per file, surfacing the problem early — at code-review time — rather
than at runtime when context limits are hit.

Usage (standalone CLI)::

    python -m harness_skills.gates.agents_md_token
    python -m harness_skills.gates.agents_md_token --max-tokens 1500
    python -m harness_skills.gates.agents_md_token --glob "**/AGENTS*.md"
    python -m harness_skills.gates.agents_md_token --no-fail-on-error

Usage (programmatic)::

    from pathlib import Path
    from harness_skills.gates.agents_md_token import AgentsMdTokenGate
    from harness_skills.models.gate_configs import AgentsMdTokenGateConfig

    cfg    = AgentsMdTokenGateConfig(max_tokens=1000)
    result = AgentsMdTokenGate(cfg).run(repo_root=Path("."))

    if not result.passed:
        for v in result.violations:
            print(v.summary())
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from harness_skills.models.gate_configs import AgentsMdTokenGateConfig


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

ViolationKind = Literal["over_budget", "read_error"]
Severity = Literal["error", "warning"]


@dataclass
class Violation:
    """A single AGENTS.md token-budget violation."""

    kind: ViolationKind
    """
    ``over_budget``  — estimated token count exceeds ``max_tokens``.
    ``read_error``   — the file could not be opened or read.
    """

    severity: Severity
    """``error`` blocks the gate; ``warning`` is advisory only."""

    message: str
    """Human-readable description of the violation."""

    agents_md_file: Path | None = None
    """Absolute path to the AGENTS.md file that triggered the violation."""

    actual_tokens: int | None = None
    """Estimated token count (``over_budget`` violations only)."""

    max_tokens: int | None = None
    """Configured token ceiling that was exceeded."""

    def summary(self) -> str:
        """One-line string suitable for console output."""
        loc = f" [{self.agents_md_file}]" if self.agents_md_file else ""
        return (
            f"[{self.severity.upper():7s}] {self.kind:15s}{loc} — {self.message}"
        )


@dataclass
class GateResult:
    """Aggregate result returned by :class:`AgentsMdTokenGate`."""

    passed: bool
    """``True`` when every AGENTS.md is within budget (or ``fail_on_error=False``)."""

    violations: list[Violation] = field(default_factory=list)
    """All violations found (one entry per over-budget or unreadable file)."""

    files_checked: list[Path] = field(default_factory=list)
    """Sorted list of AGENTS.md paths that were discovered and scanned."""

    max_tokens: int = 800
    """The configured maximum token budget per file."""

    stats: dict[str, object] = field(default_factory=dict)
    """
    Extra details:
    ``files_checked``  — number of files scanned.
    ``violations``     — number of violations found.
    ``file_stats``     — per-file breakdown (list of dicts).
    """

    def errors(self) -> list[Violation]:
        """Return only error-severity violations."""
        return [v for v in self.violations if v.severity == "error"]

    def warnings(self) -> list[Violation]:
        """Return only warning-severity violations."""
        return [v for v in self.violations if v.severity == "warning"]

    def __str__(self) -> str:  # pragma: no cover
        lines = [
            f"AgentsMdTokenGate: {'PASSED' if self.passed else 'FAILED'}",
            f"  Files checked : {len(self.files_checked)}",
            f"  Max tokens    : {self.max_tokens:,}",
            f"  Violations    : {len(self.violations)}",
        ]
        if self.violations:
            lines.append("")
            for v in self.violations:
                lines.append("  " + v.summary())
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------


def _estimate_tokens(text: str, chars_per_token: float) -> int:
    """Estimate the token count of *text* using a character-count heuristic.

    Parameters
    ----------
    text:
        UTF-8 string content of the AGENTS.md file.
    chars_per_token:
        Characters-per-token ratio.  Must be positive.

    Returns
    -------
    int
        Estimated token count (always ≥ 0; ceiling of the division).

    Raises
    ------
    ValueError
        When *chars_per_token* is not a positive number.
    """
    if chars_per_token <= 0:
        raise ValueError(
            f"chars_per_token must be a positive number, got {chars_per_token!r}"
        )
    if not text:
        return 0
    return math.ceil(len(text) / chars_per_token)


# ---------------------------------------------------------------------------
# Gate runner
# ---------------------------------------------------------------------------


class AgentsMdTokenGate:
    """Scans all AGENTS.md files in a repository and enforces a token ceiling.

    Discovers files by globbing ``config.glob_pattern`` under the repository
    root, reads each one, estimates the token count, and produces a
    :class:`Violation` for every file that exceeds ``config.max_tokens``.

    Parameters
    ----------
    config:
        Gate configuration.  When omitted, defaults are used
        (``max_tokens=800``, ``glob_pattern="**/AGENTS.md"``).

    Example::

        from pathlib import Path
        from harness_skills.gates.agents_md_token import AgentsMdTokenGate
        from harness_skills.models.gate_configs import AgentsMdTokenGateConfig

        result = AgentsMdTokenGate(
            AgentsMdTokenGateConfig(max_tokens=1000)
        ).run(Path("."))
        print(result)
    """

    def __init__(self, config: AgentsMdTokenGateConfig | None = None) -> None:
        self.config: AgentsMdTokenGateConfig = config or AgentsMdTokenGateConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, repo_root: Path) -> GateResult:
        """Execute the gate against *repo_root* and return a :class:`GateResult`.

        Parameters
        ----------
        repo_root:
            Absolute (or CWD-relative) path to the repository root.  All
            glob-discovered AGENTS.md paths are resolved relative to this
            directory.
        """
        repo_root = repo_root.resolve()
        cfg = self.config
        severity: Severity = "error" if cfg.fail_on_error else "warning"

        # ── 1. Discover AGENTS.md files ────────────────────────────────
        raw_matches = sorted(repo_root.glob(cfg.glob_pattern))
        # Keep only regular files; skip symlinks to avoid infinite loops.
        files: list[Path] = [
            f for f in raw_matches if f.is_file() and not f.is_symlink()
        ]

        if not files:
            # No files found is advisory (not a policy violation).
            no_files_msg = (
                f"No files matching '{cfg.glob_pattern}' found under "
                f"'{repo_root}'. Nothing to check."
            )
            return GateResult(
                passed=True,
                violations=[
                    Violation(
                        kind="over_budget",  # reuse closest kind; message clarifies
                        severity="warning",
                        message=no_files_msg,
                    )
                ],
                files_checked=[],
                max_tokens=cfg.max_tokens,
                stats={"files_checked": 0, "violations": 0, "file_stats": []},
            )

        # ── 2. Check each file against the token budget ────────────────
        violations: list[Violation] = []
        file_stats: list[dict[str, object]] = []

        for agents_md in files:
            # Attempt to read the file content.
            try:
                text = agents_md.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                violations.append(
                    Violation(
                        kind="read_error",
                        severity=severity,
                        message=f"Cannot read '{agents_md}': {exc}",
                        agents_md_file=agents_md,
                    )
                )
                file_stats.append(
                    {
                        "file": str(agents_md.relative_to(repo_root)),
                        "chars": None,
                        "estimated_tokens": None,
                        "max_tokens": cfg.max_tokens,
                        "over_budget": None,
                        "error": str(exc),
                    }
                )
                continue

            estimated_tokens = _estimate_tokens(text, cfg.chars_per_token)
            over_budget = estimated_tokens > cfg.max_tokens
            rel_path = agents_md.relative_to(repo_root)

            file_stats.append(
                {
                    "file": str(rel_path),
                    "chars": len(text),
                    "estimated_tokens": estimated_tokens,
                    "max_tokens": cfg.max_tokens,
                    "over_budget": over_budget,
                }
            )

            if over_budget:
                excess = estimated_tokens - cfg.max_tokens
                violations.append(
                    Violation(
                        kind="over_budget",
                        severity=severity,
                        message=(
                            f"'{rel_path}' uses ~{estimated_tokens:,} tokens "
                            f"({excess:+,} over the {cfg.max_tokens:,}-token limit). "
                            "Trim the file or raise max_tokens in harness.config.yaml."
                        ),
                        agents_md_file=agents_md,
                        actual_tokens=estimated_tokens,
                        max_tokens=cfg.max_tokens,
                    )
                )

        passed = (not violations) or (not cfg.fail_on_error)
        return GateResult(
            passed=passed,
            violations=violations,
            files_checked=files,
            max_tokens=cfg.max_tokens,
            stats={
                "files_checked": len(files),
                "violations": len(violations),
                "file_stats": file_stats,
            },
        )


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m harness_skills.gates.agents_md_token",
        description=(
            "AGENTS.md token-budget gate — enforce a maximum estimated token "
            "count per AGENTS.md file to prevent context pollution."
        ),
    )
    p.add_argument(
        "--root",
        default=".",
        metavar="PATH",
        help=(
            "Repository root to scan for AGENTS.md files "
            "(default: current directory)."
        ),
    )
    p.add_argument(
        "--max-tokens",
        type=int,
        default=800,
        metavar="N",
        help=(
            "Maximum allowed estimated tokens per AGENTS.md file "
            "(default: 800)."
        ),
    )
    p.add_argument(
        "--glob",
        default="**/AGENTS.md",
        metavar="PATTERN",
        dest="glob_pattern",
        help=(
            "Glob pattern for discovering AGENTS.md files relative to --root "
            "(default: **/AGENTS.md)."
        ),
    )
    p.add_argument(
        "--chars-per-token",
        type=float,
        default=4.0,
        metavar="N",
        help=(
            "Characters-per-token ratio used for estimation "
            "(default: 4.0)."
        ),
    )
    p.add_argument(
        "--fail-on-error",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Exit non-zero when any AGENTS.md exceeds the budget "
            "(default: true).  Use --no-fail-on-error for advisory mode."
        ),
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-violation output; only print the summary line.",
    )
    return p


def main(argv: list[str] | None = None) -> int:  # pragma: no cover
    """CLI entry-point; returns an exit code (0 = pass, 1 = fail, 2 = error)."""
    args = _build_parser().parse_args(argv)
    cfg = AgentsMdTokenGateConfig(
        max_tokens=args.max_tokens,
        glob_pattern=args.glob_pattern,
        chars_per_token=args.chars_per_token,
        fail_on_error=args.fail_on_error,
    )
    result = AgentsMdTokenGate(cfg).run(Path(args.root))

    if not args.quiet:
        print(result)

    return 0 if result.passed else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
