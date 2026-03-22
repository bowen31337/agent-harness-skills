"""harness context — return a minimal ContextManifest for a plan ID or domain.

Usage (CLI):
    harness context <PLAN_ID_OR_DOMAIN>
            [--max-files N] [--budget N] [--format json|human]
            [--state-url URL] [--no-git]
            [--include GLOB] [--exclude GLOB]

Returns a ranked list of file paths and search patterns covering the scope
of the given plan ID or domain — without loading any file contents into the
context window.

Exit codes:
    0  Manifest generated (one or more files found).
    1  No candidate files discovered.
    2  Internal error (unexpected exception).
"""

from __future__ import annotations

import json
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Optional
from urllib.error import URLError
from urllib.request import urlopen

import click
from rich.console import Console

from harness_skills.models.base import Status
from harness_skills.models.context import (
    ContextManifest,
    ContextManifestFile,
    ContextStats,
    SearchPattern,
    SkipEntry,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PLAN_ID_RE = re.compile(r"^[A-Za-z]+-\d+$")

_SOURCE_EXTENSIONS_RE = re.compile(
    r"\.(py|ts|tsx|js|jsx|go|rs|rb|java|kt|swift|yaml|json|toml|md)$"
)

_EXCLUDE_RULES: list[tuple[str, str]] = [
    (r"\.git/", "git metadata"),
    (r"node_modules/", "dependency directory"),
    (r"__pycache__/", "Python cache"),
    (r"\.pyc$", "compiled Python"),
    (r"/dist/", "build output"),
    (r"/build/", "build output"),
    (r"(\.lock$|-lock\.json$)", "lockfile"),
    (r"migrations/\d+_", "generated migration file"),
    (r"\.min\.(js|css)$", "minified asset"),
]

_MAX_PATTERNS = 15
_CHARS_PER_LINE = 38  # average chars per source line for token budgeting
_CHARS_PER_TOKEN = 4  # conservative estimate

# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------


@click.command("context")
@click.argument("input_arg", metavar="PLAN_ID_OR_DOMAIN")
@click.option(
    "--max-files",
    "max_files",
    default=20,
    show_default=True,
    type=int,
    help="Cap returned file list at N entries.",
)
@click.option(
    "--budget",
    "budget",
    default=None,
    type=int,
    help="Emit a token budget advisory for a context window of N tokens.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "human"], case_sensitive=False),
    default="human",
    show_default=True,
    help=(
        "Output format.  "
        "human: human-readable summary followed by JSON manifest.  "
        "json: machine-readable ContextManifest only."
    ),
)
@click.option(
    "--state-url",
    "state_url",
    default="http://localhost:8888",
    show_default=True,
    envvar="CLAW_FORGE_STATE_URL",
    help="Override the state service URL.",
)
@click.option(
    "--no-git",
    "no_git",
    is_flag=True,
    default=False,
    help="Skip git-log strategy (useful in shallow clones or CI detached HEADs).",
)
@click.option(
    "--include",
    "include_glob",
    default=None,
    metavar="GLOB",
    help='Restrict candidate files to paths matching GLOB (e.g. "src/**/*.py").',
)
@click.option(
    "--exclude",
    "exclude_glob",
    default=None,
    metavar="GLOB",
    help="Add an extra exclusion pattern on top of the built-in skip list.",
)
@click.pass_context
def context_cmd(
    ctx: click.Context,
    input_arg: str,
    max_files: int,
    budget: Optional[int],
    output_format: str,
    state_url: str,
    no_git: bool,
    include_glob: Optional[str],
    exclude_glob: Optional[str],
) -> None:
    """Return a minimal ContextManifest for PLAN_ID_OR_DOMAIN.

    Produces a ranked list of file paths and targeted search patterns that
    cover the plan's scope without loading file contents into the context
    window.  Agents iterate the ``files`` list in order, loading only as many
    files as their token budget allows.

    \b
    Resolve by plan ID (queries the state service):
        harness context PLAN-42

    \b
    Resolve by domain name (heuristic file discovery):
        harness context auth
        harness context "user onboarding"

    \b
    Machine-readable output only:
        harness context auth --format json

    \b
    With token budget advisory:
        harness context PLAN-42 --budget 40000
    """
    try:
        manifest = _build_manifest(
            input_arg=input_arg,
            max_files=max_files,
            state_url=state_url,
            no_git=no_git,
            include_glob=include_glob,
            exclude_glob=exclude_glob,
        )
    except Exception as exc:  # noqa: BLE001
        click.echo(f"[harness context] internal error: {exc}", err=True)
        ctx.exit(2)
        return

    if output_format == "json":
        click.echo(manifest.model_dump_json(indent=2))
    else:
        _print_human_report(manifest, budget)
        click.echo(manifest.model_dump_json(indent=2))

    if not manifest.files:
        ctx.exit(1)


# ---------------------------------------------------------------------------
# Step 1-6 orchestration
# ---------------------------------------------------------------------------


def _build_manifest(
    input_arg: str,
    max_files: int,
    state_url: str,
    no_git: bool,
    include_glob: Optional[str],
    exclude_glob: Optional[str],
) -> ContextManifest:
    """Orchestrate all discovery steps and return a populated ContextManifest."""

    # Step 1 — identify input type
    is_plan_id = bool(_PLAN_ID_RE.match(input_arg))

    # Step 2A / 2B — extract keywords and seed files
    state_service_used = False
    seed_files: list[str] = []
    keywords: list[str] = []

    if is_plan_id:
        plan_data, state_service_used = _fetch_plan(input_arg, state_url)
        if plan_data:
            keywords = _extract_keywords_from_plan(plan_data)
            seed_files = _extract_seed_files(plan_data)

    if not keywords:
        keywords = _tokenize_domain(input_arg)

    # Step 3 — discover candidate files (scores accumulate from all strategies)
    scores: dict[str, int] = defaultdict(int)
    sources_map: dict[str, list[str]] = defaultdict(list)

    # Seed files from state service get the highest confidence score
    for f in seed_files:
        scores[f] += 100
        if "state_service" not in sources_map[f]:
            sources_map[f].append("state_service")

    # Strategy A — git log (highest signal)
    if not no_git:
        for path, commit_count in _git_log_strategy(keywords).items():
            scores[path] += 10 * commit_count
            if "git_log" not in sources_map[path]:
                sources_map[path].append("git_log")

    # Strategy B — symbol grep (medium signal)
    for path, match_count in _grep_strategy(keywords).items():
        scores[path] += 5 * match_count
        if "symbol_grep" not in sources_map[path]:
            sources_map[path].append("symbol_grep")

    # Strategy C — path name match (low signal)
    for path in _path_strategy(keywords):
        scores[path] += 2
        if "path_name" not in sources_map[path]:
            sources_map[path].append("path_name")

    total_candidates = len(scores)

    # Step 4 — filter, exclude, and rank
    extra_excludes = [exclude_glob] if exclude_glob else []
    ranked_paths, skip_list = _filter_and_rank(
        scores=scores,
        max_files=max_files,
        extra_excludes=extra_excludes,
        include_glob=include_glob,
    )

    # Build ContextManifestFile entries
    files: list[ContextManifestFile] = []
    total_lines = 0
    for path in ranked_paths:
        lines = _count_lines(path)
        total_lines += lines
        src_list = sources_map.get(path, ["unknown"])
        files.append(
            ContextManifestFile(
                path=path,
                score=scores[path],
                estimated_lines=lines,
                sources=src_list,
                rationale=_build_rationale(path, src_list, scores[path]),
            )
        )

    # Step 5 — generate search patterns
    patterns = _generate_patterns(keywords)

    # Step 6 — assemble and return
    return ContextManifest(
        command="harness context",
        status=Status.PASSED if files else Status.WARNING,
        input=input_arg,
        keywords=keywords,
        files=files,
        patterns=patterns,
        skip_list=skip_list,
        stats=ContextStats(
            total_candidate_files=total_candidates,
            returned_files=len(files),
            total_estimated_lines=total_lines,
            state_service_used=state_service_used,
        ),
        timestamp=datetime.now(timezone.utc).isoformat(),
        message=(
            f"{len(files)} file(s) found for '{input_arg}'"
            if files
            else f"No candidate files discovered for '{input_arg}'"
        ),
    )


# ---------------------------------------------------------------------------
# Step 2A — state service helpers
# ---------------------------------------------------------------------------


def _fetch_plan(plan_id: str, state_url: str) -> tuple[dict | None, bool]:
    """Query the state service for plan metadata.

    Returns ``(plan_data, service_was_used)``.  On any error (timeout,
    non-200, malformed JSON) returns ``(None, False)`` so the caller can
    fall through to keyword-based discovery.
    """
    url = f"{state_url.rstrip('/')}/features/{plan_id}"
    try:
        with urlopen(url, timeout=3) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                return data, True
    except (URLError, OSError, ValueError):
        pass
    return None, False


def _extract_keywords_from_plan(plan_data: dict) -> list[str]:
    """Tokenise keywords from a plan JSON document (description + tasks)."""
    texts: list[str] = []
    for key in ("description", "domain"):
        if key in plan_data:
            texts.append(str(plan_data[key]))
    for task in plan_data.get("tasks", []):
        if "description" in task:
            texts.append(str(task["description"]))

    seen: set[str] = set()
    result: list[str] = []
    for text in texts:
        for kw in _tokenize_domain(text):
            if kw not in seen:
                seen.add(kw)
                result.append(kw)
    return result[:10]  # cap to keep grep invocations manageable


def _extract_seed_files(plan_data: dict) -> list[str]:
    """Collect files_touched from all tasks in a plan."""
    files: list[str] = []
    seen: set[str] = set()
    for task in plan_data.get("tasks", []):
        for f in task.get("files_touched", []):
            if f not in seen:
                seen.add(f)
                files.append(f)
    return files


# ---------------------------------------------------------------------------
# Step 2B — keyword tokenisation
# ---------------------------------------------------------------------------

_CAMEL_SPLIT_RE = re.compile(r"(?<=[a-z])(?=[A-Z])")


def _tokenize_domain(domain: str) -> list[str]:
    """Split a domain string into lowercase keywords.

    Handles spaces, hyphens, underscores, and camelCase boundaries.
    Drops tokens shorter than 3 characters.

    Examples::

        "userOnboarding"   → ["user", "onboarding"]
        "user-auth_flow"   → ["user", "auth", "flow"]
        "PLAN-42"          → ["plan"]
    """
    raw_tokens = re.split(r"[\s\-_]+", domain)
    tokens: list[str] = []
    for tok in raw_tokens:
        tokens.extend(_CAMEL_SPLIT_RE.split(tok))
    return [t.lower() for t in tokens if len(t) >= 3]


# ---------------------------------------------------------------------------
# Step 3 — file discovery strategies
# ---------------------------------------------------------------------------


def _git_log_strategy(keywords: list[str]) -> dict[str, int]:
    """Strategy A — files in commits whose message mentions a keyword.

    Returns ``{relative_path: commit_count}``.
    """
    hits: dict[str, int] = defaultdict(int)
    for kw in keywords:
        try:
            result = subprocess.run(
                ["git", "log", "--all", "--oneline", "--name-only", f"--grep={kw}", "-20"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                continue
            for line in result.stdout.splitlines():
                line = line.strip()
                # Commit summary lines start with a short SHA (hex chars)
                if not line or re.match(r"^[0-9a-f]{7,} ", line):
                    continue
                if _SOURCE_EXTENSIONS_RE.search(line):
                    hits[line] += 1
        except Exception:  # noqa: BLE001
            pass
    return dict(hits)


def _grep_strategy(keywords: list[str]) -> dict[str, int]:
    """Strategy B — source files that contain a keyword.

    Returns ``{relative_path: keyword_match_count}``.
    """
    hits: dict[str, int] = defaultdict(int)
    includes = [
        "--include=*.py",
        "--include=*.ts",
        "--include=*.tsx",
        "--include=*.js",
        "--include=*.go",
        "--include=*.rs",
    ]
    for kw in keywords:
        try:
            result = subprocess.run(
                ["grep", "-rl", "-i", kw, "."] + includes,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode not in (0, 1):  # 1 = no matches (normal)
                continue
            for line in result.stdout.splitlines():
                path = line.strip().lstrip("./")
                if path:
                    hits[path] += 1
        except Exception:  # noqa: BLE001
            pass
    return dict(hits)


def _path_strategy(keywords: list[str]) -> list[str]:
    """Strategy C — files whose name or directory path contains a keyword.

    Returns a sorted list of relative paths.
    """
    hits: set[str] = set()
    skip_dirs = {".git", "node_modules", "__pycache__", "dist", "build"}
    try:
        root = Path(".")
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            # Skip excluded directories
            if any(part in skip_dirs for part in p.parts):
                continue
            name_lower = p.name.lower()
            parts_lower = [part.lower() for part in p.parts]
            for kw in keywords:
                if kw in name_lower or any(kw in part for part in parts_lower):
                    # Normalise: strip leading "./"
                    hits.add(str(p).lstrip("./"))
                    break
    except Exception:  # noqa: BLE001
        pass
    return sorted(hits)


# ---------------------------------------------------------------------------
# Step 4 — filtering and ranking
# ---------------------------------------------------------------------------


def _should_exclude(path: str, extra_patterns: list[str]) -> tuple[bool, str]:
    """Return ``(True, reason)`` if path matches any exclusion rule."""
    for pattern, reason in _EXCLUDE_RULES:
        if re.search(pattern, path):
            return True, reason
    for ep in extra_patterns:
        if re.search(ep, path) or fnmatch(path, ep):
            return True, "user-excluded pattern"
    return False, ""


def _filter_and_rank(
    scores: dict[str, int],
    max_files: int,
    extra_excludes: list[str],
    include_glob: Optional[str],
) -> tuple[list[str], list[SkipEntry]]:
    """Apply exclusions, optional include filter, rank, and cap the file list.

    Returns ``(ranked_paths, skip_list)``.
    """
    skip_list: list[SkipEntry] = []
    passing: list[tuple[str, int]] = []

    for path, score in scores.items():
        excluded, reason = _should_exclude(path, extra_excludes)
        if excluded:
            skip_list.append(SkipEntry(path=path, reason=reason))
            continue

        if include_glob and not fnmatch(path, include_glob):
            continue

        # Verify the file exists (handles both "./path" and "path" forms)
        if not Path(path).exists() and not Path(f"./{path}").exists():
            continue

        passing.append((path, score))

    passing.sort(key=lambda item: item[1], reverse=True)
    ranked = [p for p, _ in passing[:max_files]]
    return ranked, skip_list


# ---------------------------------------------------------------------------
# Line count helper
# ---------------------------------------------------------------------------


def _count_lines(path: str) -> int:
    """Return a line count for a file; 0 on any error."""
    for candidate in (path, f"./{path}"):
        p = Path(candidate)
        if p.exists():
            try:
                return sum(1 for _ in p.open("rb"))
            except Exception:  # noqa: BLE001
                return 0
    return 0


# ---------------------------------------------------------------------------
# Step 5 — search pattern generation
# ---------------------------------------------------------------------------


def _generate_patterns(keywords: list[str]) -> list[SearchPattern]:
    """Generate up to ``_MAX_PATTERNS`` targeted grep patterns for ``keywords``."""
    patterns: list[SearchPattern] = []
    seen_labels: set[str] = set()

    for kw in keywords:
        candidates: list[SearchPattern] = [
            SearchPattern(
                label=f"define:{kw}",
                pattern=rf"(?:class|def|function|fn|type|interface|struct)\s+\w*{kw}\w*",
                flags="-i",
                rationale=f"Symbol definitions matching '{kw}'",
            ),
            SearchPattern(
                label=f"import:{kw}",
                pattern=rf"(?:import|from|require|use)\s+.*{kw}",
                flags="-i",
                rationale=f"Import statements pulling in '{kw}' components",
            ),
            SearchPattern(
                label=f"route:{kw}",
                pattern=rf"(?:@\w+\.(?:get|post|put|patch|delete)|router\.\w+)\s*\(['\"].*{kw}",
                flags="-i",
                rationale=f"HTTP endpoints related to '{kw}'",
            ),
        ]
        for pat in candidates:
            if pat.label not in seen_labels and len(patterns) < _MAX_PATTERNS:
                seen_labels.add(pat.label)
                patterns.append(pat)

    return patterns


# ---------------------------------------------------------------------------
# Rationale builder
# ---------------------------------------------------------------------------


def _build_rationale(path: str, sources: list[str], score: int) -> str:
    """Produce a short human-readable rationale string for a ranked file."""
    parts: list[str] = []
    if "state_service" in sources:
        parts.append("listed in plan tasks")
    if "git_log" in sources:
        git_contrib = score - (100 if "state_service" in sources else 0)
        n_commits = max(git_contrib // 10, 0)
        if n_commits:
            parts.append(f"{n_commits} matching commit(s)")
    if "symbol_grep" in sources:
        parts.append("keyword match in source")
    if "path_name" in sources:
        parts.append("keyword in path name")
    return "; ".join(parts) if parts else f"score={score}"


# ---------------------------------------------------------------------------
# Step 6 — human-readable renderer
# ---------------------------------------------------------------------------

_SOURCE_LABEL: dict[str, str] = {
    "state_service": "state service",
    "git_log": "git",
    "symbol_grep": "grep",
    "path_name": "path",
}


def _print_human_report(manifest: ContextManifest, budget: Optional[int]) -> None:
    """Print the human-readable summary to stdout (rich console)."""
    console = Console()
    sep = "━" * 56
    n_files = len(manifest.files)
    n_patterns = len(manifest.patterns)
    total_lines = manifest.stats.total_estimated_lines

    console.print()
    console.print(sep)
    console.print(f"  Harness Context — [bold]{manifest.input}[/bold]")
    console.print(
        f"  {n_files} file(s) · {n_patterns} pattern(s) · ~{total_lines} estimated lines"
    )
    console.print(sep)
    console.print()

    # Ranked files
    if manifest.files:
        console.print("[bold]Ranked Files[/bold]")
        console.print("─" * 56)
        console.print(f"  {'#':>3}  {'Score':>6}  {'Lines':>6}  Path")
        console.print(f"  {'─' * 3}  {'─' * 6}  {'─' * 6}  {'─' * 32}")
        for i, f in enumerate(manifest.files, start=1):
            src_str = " + ".join(_SOURCE_LABEL.get(s, s) for s in f.sources)
            console.print(
                f"  {i:>3}  {f.score:>6}  {f.estimated_lines:>6}  {f.path}"
                f"   ← {src_str}"
            )
        console.print()

    # Search patterns
    if manifest.patterns:
        console.print("[bold]Search Patterns[/bold] (apply to ranked files first)")
        console.print("─" * 56)
        for pat in manifest.patterns:
            console.print(f"  {pat.label:<22}  {pat.flags}  {pat.pattern[:48]}")
        console.print()

    # Skip list
    if manifest.skip_list:
        console.print("[bold]Skip List[/bold] (do not load)")
        console.print("─" * 56)
        for entry in manifest.skip_list[:10]:
            console.print(f"  {entry.path}   ({entry.reason})")
        if len(manifest.skip_list) > 10:
            console.print(f"  … and {len(manifest.skip_list) - 10} more")
        console.print()

    # Step 7 — optional token budget advisory
    if budget is not None:
        _print_budget_advisory(console, manifest, budget)

    console.print(sep)
    console.print(
        "  [dim]Tip: read only the top-N files; use patterns to extract[/dim]"
    )
    console.print(
        "  [dim]specific sections rather than loading full contents.[/dim]"
    )
    console.print(sep)
    console.print()


def _print_budget_advisory(
    console: Console,
    manifest: ContextManifest,
    budget: int,
) -> None:
    """Step 7 — print a token budget breakdown table."""
    chars_budget = budget * _CHARS_PER_TOKEN
    console.print(f"[bold]Token Budget Advisory[/bold]  (target: {budget:,} tokens)")
    console.print("─" * 72)
    console.print(f"  Assume ~{_CHARS_PER_TOKEN} chars/token → {chars_budget:,} chars budget")
    console.print()
    console.print(
        f"  {'File':<42}  {'Lines':>6}  {'Est. chars':>11}  {'Cumulative':>11}"
    )
    console.print("  " + "─" * 70)

    cumulative = 0
    fits_count = 0
    for f in manifest.files:
        est_chars = f.estimated_lines * _CHARS_PER_LINE
        cumulative += est_chars
        within = "✅" if cumulative <= chars_budget else "❌"
        if cumulative <= chars_budget:
            fits_count += 1
        console.print(
            f"  {f.path:<42}  {f.estimated_lines:>6}  {est_chars:>11,}  {cumulative:>11,}  {within}"
        )

    console.print("  " + "─" * 70)
    remaining = len(manifest.files) - fits_count
    if fits_count == len(manifest.files):
        console.print(
            f"  → Load all {fits_count} ranked file(s) comfortably within budget."
        )
        excess = manifest.stats.total_candidate_files - fits_count
        if excess > 0:
            console.print(
                f"    Use patterns on remaining {excess} candidates to extract snippets."
            )
    else:
        console.print(
            f"  → Load the top {fits_count} file(s) within budget;"
            f" use patterns for the remaining {remaining}."
        )
    console.print()
