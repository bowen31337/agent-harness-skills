from __future__ import annotations
import argparse, re, sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal


@dataclass
class GateConfig:
    """Configuration for the documentation-freshness gate."""
    max_staleness_days: int = 30
    fail_on_error: bool = True
    tracked_files: list[str] = field(
        default_factory=lambda: [
            "AGENTS.md", "ARCHITECTURE.md", "PRINCIPLES.md", "EVALUATION.md",
        ]
    )

    def __post_init__(self) -> None:
        if self.max_staleness_days < 1:
            raise ValueError("max_staleness_days must be >= 1")


_SKIP_DIRS: frozenset[str] = frozenset({
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build", ".tox", ".eggs",
})
_TRACKED_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs",
    ".yaml", ".yml", ".toml", ".json", ".md", ".txt",
    ".sh", ".bash", ".env", ".cfg", ".ini", ".xml", ".html", ".css", ".sql",
})
_GENERATED_AT_RE = re.compile(
    r"(?:<!--\s*)?(?:>\s*)?generated_at\s*:\s*(?P<date>\d{4}-\d{2}-\d{2})",
    re.IGNORECASE | re.MULTILINE,
)
_MD_LINK_RE  = re.compile(r"\[[^\]]*\]\((?P<path>[^)#?\s]+)\)")
_BACKTICK_RE = re.compile(r"`(?P<path>[^`\n]+)`")
_BARE_PATH_RE = re.compile(
    r"(?<![`\[\(\w/.])(?P<path>(?:\./|[a-zA-Z0-9_.-]+/)[a-zA-Z0-9_./-]+)(?![`\]\)])"
)

ViolationKind = Literal["dead_ref", "stale_content", "missing_timestamp"]
Severity      = Literal["error", "warning"]


@dataclass
class Violation:
    agents_file:     Path
    kind:            ViolationKind
    severity:        Severity
    message:         str
    referenced_path: Path | None = None
    line_number:     int  | None = None

    def summary(self) -> str:
        loc = f":{self.line_number}" if self.line_number else ""
        return (
            f"[{self.severity.upper():7s}] {self.kind:20s} "
            f"{self.agents_file}{loc} — {self.message}"
        )


@dataclass
class GateResult:
    passed:        bool
    violations:    list[Violation] = field(default_factory=list)
    checked_files: list[Path]      = field(default_factory=list)
    stats:         dict[str, int]  = field(default_factory=dict)

    def errors(self)   -> list[Violation]:
        return [v for v in self.violations if v.severity == "error"]

    def warnings(self) -> list[Violation]:
        return [v for v in self.violations if v.severity == "warning"]


def _looks_like_file_path(raw: str) -> bool:
    if not raw or len(raw) > 260:
        return False
    if raw.lower().startswith(("http://", "https://", "mailto:", "#", "{", "/")):
        return False
    return "/" in raw or Path(raw).suffix.lower() in _TRACKED_EXTENSIONS


def _char_to_line(line_starts: list[int], pos: int) -> int:
    lo, hi = 0, len(line_starts) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if line_starts[mid] <= pos:
            lo = mid
        else:
            hi = mid - 1
    return lo + 1


def _extract_file_refs(content: str) -> list[tuple[str, int]]:
    """Return (raw_path, 1-based-line) for every file reference in content."""
    line_starts: list[int] = [0]
    for m in re.finditer(r"\n", content):
        line_starts.append(m.end())
    seen: set[tuple[str, int]] = set()
    results: list[tuple[str, int]] = []

    def add(raw: str, pos: int) -> None:
        raw = raw.strip().rstrip("/.")
        if not _looks_like_file_path(raw):
            return
        key = (raw, _char_to_line(line_starts, pos))
        if key not in seen:
            seen.add(key)
            results.append(key)

    for m in _MD_LINK_RE.finditer(content):   add(m.group("path"), m.start())
    for m in _BACKTICK_RE.finditer(content):   add(m.group("path"), m.start())
    for m in _BARE_PATH_RE.finditer(content):
        raw = m.group("path").strip().rstrip("/.")
        ln  = _char_to_line(line_starts, m.start())
        if (raw, ln) not in seen and _looks_like_file_path(raw):
            seen.add((raw, ln))
            results.append((raw, ln))
    return results


def _parse_generated_at(content: str) -> date | None:
    m = _GENERATED_AT_RE.search(content)
    if not m:
        return None
    try:
        return datetime.strptime(m.group("date"), "%Y-%m-%d").date()
    except ValueError:
        return None


def _today() -> date:
    """Return today UTC date. Isolated for test monkeypatching."""
    return datetime.now(tz=timezone.utc).date()


class DocsFreshnessGate:
    """Runs the documentation-freshness gate against a repository tree."""

    def __init__(self, config: GateConfig | None = None) -> None:
        self.config = config or GateConfig()

    def run(self, repo_root: Path) -> GateResult:
        """Scan repo_root for AGENTS.md files and return a GateResult."""
        repo_root    = repo_root.resolve()
        agents_files = self._find_agents_files(repo_root)
        violations: list[Violation] = []
        total_refs = 0

        for af in agents_files:
            content = af.read_text(encoding="utf-8", errors="replace")
            n, viols = self._check_dead_refs(af, content, repo_root)
            total_refs += n
            violations.extend(viols)
            violations.extend(self._check_freshness(af, content))

        violations.sort(key=lambda v: (str(v.agents_file), v.line_number or 0))
        errors = sum(1 for v in violations if v.severity == "error")
        return GateResult(
            passed=errors == 0 or not self.config.fail_on_error,
            violations=violations,
            checked_files=agents_files,
            stats={
                "agents_files":       len(agents_files),
                "total_refs_checked": total_refs,
                "dead_refs":          sum(1 for v in violations if v.kind == "dead_ref"),
                "stale":              sum(1 for v in violations if v.kind == "stale_content"),
                "missing_timestamps": sum(
                    1 for v in violations if v.kind == "missing_timestamp"
                ),
            },
        )

    def _find_agents_files(self, repo_root: Path) -> list[Path]:
        results = []
        for path in repo_root.rglob("AGENTS.md"):
            if not any(p in _SKIP_DIRS for p in path.parts) and path.is_file():
                results.append(path)
        return sorted(results)

    def _check_dead_refs(
        self, agents_file: Path, content: str, repo_root: Path
    ) -> tuple[int, list[Violation]]:
        violations = []
        refs       = _extract_file_refs(content)
        agents_dir = agents_file.parent
        sev: Severity = "error" if self.config.fail_on_error else "warning"
        for raw_path, lineno in refs:
            local     = (agents_dir / raw_path).resolve()
            from_root = (repo_root  / raw_path).resolve()
            if local.exists() or from_root.exists():
                continue
            violations.append(Violation(
                agents_file=agents_file, kind="dead_ref", severity=sev,
                message=f"Referenced file does not exist: '{raw_path}'",
                referenced_path=local, line_number=lineno,
            ))
        return len(refs), violations

    def _check_freshness(self, agents_file: Path, content: str) -> list[Violation]:
        violations: list[Violation] = []
        sev: Severity = "error" if self.config.fail_on_error else "warning"
        gen_date = _parse_generated_at(content)
        if gen_date is None:
            violations.append(Violation(
                agents_file=agents_file, kind="missing_timestamp", severity=sev,
                message=(
                    "No 'generated_at: YYYY-MM-DD' timestamp found. "
                    "Add one to track content age."
                ),
            ))
            return violations
        staleness = (_today() - gen_date).days
        if staleness > self.config.max_staleness_days:
            violations.append(Violation(
                agents_file=agents_file, kind="stale_content", severity=sev,
                message=(
                    f"Content is {staleness} day(s) old "
                    f"(generated_at: {gen_date.isoformat()}, "
                    f"threshold: {self.config.max_staleness_days} day(s)). "
                    "Regenerate or update the file."
                ),
            ))
        return violations


def main(argv: list[str] | None = None) -> int:  # pragma: no cover
    p = argparse.ArgumentParser(
        prog="python -m harness_skills.gates.docs_freshness",
        description="Documentation freshness gate — verify AGENTS.md files.",
    )
    p.add_argument("--root", default=".", metavar="PATH")
    p.add_argument("--max-staleness-days", type=int, default=30)
    p.add_argument("--fail-on-error", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--quiet", action="store_true")
    args   = p.parse_args(argv)
    cfg    = GateConfig(max_staleness_days=args.max_staleness_days, fail_on_error=args.fail_on_error)
    result = DocsFreshnessGate(cfg).run(Path(args.root))
    if not args.quiet:
        print(result)
    return 0 if result.passed else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
