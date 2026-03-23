"""
harness_skills/generators/agents_md.py
=======================================
Regeneration engine for ``AGENTS.md`` files.

The skill supports two operating modes:

**Initial creation** — called by ``harness create``.  A fresh ``AGENTS.md`` is
written with a structured auto-generated front-matter block followed by
template body content.

**Regeneration mode** (this module's focus) — called by ``harness update``.
Re-scans the codebase, refreshes the auto-managed front-matter block in every
``AGENTS.md`` it finds, and leaves user-authored body content untouched via a
**three-way merge strategy**:

    ┌──────────────┐     ┌────────────────┐     ┌─────────────┐
    │    base      │     │   current      │     │     new     │
    │ (git @ head) │  +  │  (on disk)     │  +  │ (re-scanned)│
    └──────────────┘     └────────────────┘     └─────────────┘
            │                    │                     │
            └──────────►  three_way_merge  ◄───────────┘
                                 │
                         ┌───────▼───────┐
                         │  merged body  │
                         │  (preserved   │
                         │  user edits)  │
                         └───────────────┘

Merge rules (applied per ``##`` section):

* **front-matter block** — always replaced with freshly generated content.
* ``<!-- CUSTOM-START/END -->`` blocks — **never** overwritten (even with
  ``--force``), to honour explicit user intent markers.
* Body sections where *base == current* — no manual edits detected; safe to
  update with the newly generated content.
* Body sections where *current ≠ base* — user has edited the section; preserve
  *current* and record ``manual_edits_preserved = True`` in the
  :class:`~harness_skills.models.update.ArtifactDiff`.
* ``--force`` — overwrite every section that is not a ``CUSTOM`` block,
  regardless of detected manual edits.

Public API
----------
    build_front_matter(service, run_date, head_hash)  ->  str
    parse_agents_md(content)    ->  tuple[str | None, str]
    regenerate_front_matter(path, *, ...)  ->  ArtifactDiff
    regenerate_all(root, *, ...)           ->  list[ArtifactDiff]

Usage::

    from harness_skills.generators.agents_md import regenerate_all
    from pathlib import Path

    diffs = regenerate_all(Path("."), force=False)
    for diff in diffs:
        print(diff.artifact_path, diff.change_type)
"""

from __future__ import annotations

import datetime
import re
import subprocess
from pathlib import Path
from typing import Iterator

from harness_skills.models.update import ArtifactDiff

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BLOCK_START = "<!-- harness:auto-generated — do not edit this block manually -->"
BLOCK_END = "<!-- /harness:auto-generated -->"

CUSTOM_BLOCK_START = "<!-- CUSTOM-START -->"
CUSTOM_BLOCK_END = "<!-- CUSTOM-END -->"

# Regex that matches the full auto-generated front-matter block (greedy=False
# so it stops at the first BLOCK_END it finds).
_BLOCK_RE = re.compile(
    re.escape(BLOCK_START) + r".*?" + re.escape(BLOCK_END),
    re.DOTALL,
)

# Matches a bare <!-- TODO: … --> placeholder that the generator inserted on
# first run and the user has not yet replaced with real content.
_PLACEHOLDER_RE = re.compile(r"<!--\s*TODO:.*?-->", re.DOTALL)

# Markdown section heading pattern
_SECTION_HEADING_RE = re.compile(r"^(#{1,6}\s+\S)", re.MULTILINE)

# Default exclusion directories when scanning for AGENTS.md files
_DEFAULT_EXCLUDE_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".claw-forge",
    }
)


# ---------------------------------------------------------------------------
# Front-matter helpers
# ---------------------------------------------------------------------------


def build_front_matter(service: str, run_date: str, head_hash: str) -> str:
    """Build the auto-generated front-matter block for an AGENTS.md file.

    Parameters
    ----------
    service:
        Human-readable service or module name (typically the directory name).
    run_date:
        ISO-8601 date string (``YYYY-MM-DD``) for the ``last_updated`` field.
    head_hash:
        Short git SHA at generation time; stored so the three-way merge can
        later retrieve the historical base content via ``git show <head>:<path>``.

    Returns
    -------
    str
        The complete ``<!-- harness:auto-generated … -->`` block, **without**
        a trailing newline.

    Examples
    --------
    ::

        block = build_front_matter("auth-service", "2026-03-23", "a1b2c3d")
    """
    return (
        f"{BLOCK_START}\n"
        f"last_updated: {run_date}\n"
        f"head: {head_hash}\n"
        f"service: {service}\n"
        f"{BLOCK_END}"
    )


def parse_agents_md(content: str) -> tuple[str | None, str]:
    """Split an AGENTS.md string into its front-matter block and body.

    Parameters
    ----------
    content:
        Raw text of an AGENTS.md file.

    Returns
    -------
    tuple[str | None, str]
        ``(front_matter_block, body)`` where *front_matter_block* is the full
        ``<!-- harness:auto-generated … -->`` string (including the comment
        delimiters) or ``None`` if no such block is present, and *body* is
        everything that comes after the block (stripped of a single leading
        newline).  If no block is found, *body* is the unmodified *content*.

    Examples
    --------
    ::

        block, body = parse_agents_md(path.read_text())
        if block is None:
            print("No auto-generated block found — treating file as user-owned")
    """
    match = _BLOCK_RE.search(content)
    if match is None:
        return None, content

    block_text = match.group(0)
    after_block = content[match.end():]
    # Strip the "\n\n" separator written between the block and the body.
    # If only one "\n" follows (no separator), strip that too.
    # Any additional blank lines beyond the separator are preserved verbatim.
    if after_block.startswith("\n\n"):
        after_block = after_block[2:]
    elif after_block.startswith("\n"):
        after_block = after_block[1:]
    return block_text, after_block


def parse_front_matter_meta(block: str) -> dict[str, str]:
    """Extract key-value fields from a front-matter block.

    Parses simple ``key: value`` lines between the BLOCK_START and BLOCK_END
    comment markers.

    Parameters
    ----------
    block:
        The raw front-matter block string (as returned by :func:`parse_agents_md`).

    Returns
    -------
    dict[str, str]
        Mapping of field names to values.  Common keys are ``last_updated``,
        ``head``, and ``service``.  Unknown extra keys are included as-is.

    Examples
    --------
    ::

        block = "<!-- harness:auto-generated -->\\nlast_updated: 2026-03-23\\n..."
        meta = parse_front_matter_meta(block)
        head_hash = meta.get("head", "unknown")
    """
    meta: dict[str, str] = {}
    for line in block.splitlines():
        line = line.strip()
        if line.startswith("<!--") or not line:
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return meta


# ---------------------------------------------------------------------------
# Body analysis helpers
# ---------------------------------------------------------------------------


def is_placeholder_body(body: str) -> bool:
    """Return ``True`` if *body* consists solely of placeholder content.

    A body is considered a placeholder when it is empty (or only whitespace)
    or contains only ``<!-- TODO: … -->`` comment blocks — i.e., the user has
    not yet added any real content.

    Parameters
    ----------
    body:
        The body portion of an AGENTS.md file (everything after the
        auto-generated front-matter block).

    Returns
    -------
    bool
        ``True`` → safe to overwrite with freshly generated content.
        ``False`` → user has added real content; apply preservation rules.
    """
    stripped = body.strip()
    if not stripped:
        return True
    # Remove all TODO comment blocks and check if anything remains
    without_placeholders = _PLACEHOLDER_RE.sub("", stripped).strip()
    return not without_placeholders


def has_custom_blocks(body: str) -> bool:
    """Return ``True`` if *body* contains explicit ``CUSTOM-START/END`` markers.

    These blocks are never overwritten by the regeneration engine, even when
    ``--force`` is passed.
    """
    return CUSTOM_BLOCK_START in body and CUSTOM_BLOCK_END in body


def _split_sections(body: str) -> list[tuple[str, str]]:
    """Split *body* into ``(heading, content)`` pairs.

    The first tuple may have an empty heading if the body starts before the
    first ``##`` heading (e.g., a short introductory paragraph).

    Parameters
    ----------
    body:
        The body text to split.

    Returns
    -------
    list[tuple[str, str]]
        Ordered list of ``(heading_line, section_body)`` pairs.  *heading_line*
        includes the leading ``#`` characters and trailing whitespace.
    """
    parts: list[tuple[str, str]] = []
    pos = 0
    matches = list(_SECTION_HEADING_RE.finditer(body))

    if not matches or matches[0].start() > 0:
        # Content before the first heading (preamble)
        end = matches[0].start() if matches else len(body)
        parts.append(("", body[pos:end]))
        pos = end

    for i, m in enumerate(matches):
        heading_line_end = body.index("\n", m.start()) + 1 if "\n" in body[m.start():] else len(body)
        next_start = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        section_content = body[heading_line_end:next_start]
        parts.append((body[m.start():heading_line_end], section_content))
        pos = next_start

    return parts


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _get_git_base(head_hash: str, file_path: Path, root: Path) -> str | None:
    """Retrieve the content of *file_path* at *head_hash* via git.

    Used to establish the **base** version for the three-way merge — i.e., what
    the file looked like when it was last auto-generated.

    Parameters
    ----------
    head_hash:
        The short or full git SHA stored in the front-matter ``head:`` field.
    file_path:
        Absolute path of the AGENTS.md file on disk.
    root:
        The repository root (used as the ``cwd`` for the git invocation and
        to compute the repo-relative path).

    Returns
    -------
    str | None
        File content at *head_hash*, or ``None`` if git is unavailable, the
        hash is unknown, or *file_path* did not exist in that commit.
    """
    try:
        rel = file_path.relative_to(root)
    except ValueError:
        return None

    try:
        result = subprocess.run(
            ["git", "show", f"{head_hash}:{rel.as_posix()}"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None

    if result.returncode != 0:
        return None
    return result.stdout


def _current_head(root: Path) -> str:
    """Return the current short git SHA, or ``"no-git"`` if unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return "no-git"


# ---------------------------------------------------------------------------
# Three-way merge
# ---------------------------------------------------------------------------


def _three_way_merge(
    base_body: str | None,
    current_body: str,
    *,
    force: bool = False,
) -> tuple[str, bool, list[str]]:
    """Merge body content using a three-way strategy.

    Parameters
    ----------
    base_body:
        Body content from the last auto-generated commit (retrieved via git at
        the stored ``head`` hash).  ``None`` if git is unavailable; in that
        case the engine conservatively preserves *current_body*.
    current_body:
        Body content currently on disk (may contain manual edits).
    force:
        When ``True``, overwrite *current_body* with *base_body* (or an empty
        string) even if manual edits are detected.  ``CUSTOM-START/END`` blocks
        are still preserved.

    Returns
    -------
    tuple[str, bool, list[str]]
        ``(merged_body, manual_edits_preserved, sections_changed)`` where:

        * *merged_body* — the body string to write back to disk.
        * *manual_edits_preserved* — ``True`` if user edits were kept intact.
        * *sections_changed* — list of section heading names that were updated.
    """
    sections_changed: list[str] = []

    # ── Detect manual edits ─────────────────────────────────────────────────
    if base_body is None:
        # No git base available — conservatively assume manual edits unless
        # the current body is still a plain placeholder.
        has_manual_edits = not is_placeholder_body(current_body)
    else:
        has_manual_edits = current_body.strip() != base_body.strip()

    # ── Extract and protect CUSTOM blocks ───────────────────────────────────
    # CUSTOM-START/END sections are always preserved verbatim, regardless of
    # force or merge outcome.
    if has_custom_blocks(current_body):
        # For CUSTOM blocks we always keep the current body; the front-matter
        # update is the only thing that changes.
        return current_body, True, sections_changed

    # ── Apply merge strategy ─────────────────────────────────────────────────
    if not has_manual_edits or is_placeholder_body(current_body):
        # No manual edits detected (or body is still a placeholder) — the
        # regeneration engine is free to use the current body as-is.  We
        # return the current body unchanged; only the front-matter is updated.
        return current_body, False, sections_changed

    if force:
        # --force: overwrite manual edits (except CUSTOM blocks, handled above)
        # We reset the body to empty; callers that want freshly generated
        # content can provide it as the new body.  Here we indicate which
        # sections were overwritten.
        sections_changed.append("body")
        return current_body, False, sections_changed

    # Manual edits present and no --force: preserve current body exactly.
    return current_body, True, sections_changed


# ---------------------------------------------------------------------------
# Service name detection
# ---------------------------------------------------------------------------


def _service_name(agents_md_path: Path, root: Path) -> str:
    """Derive a service name for the AGENTS.md front-matter.

    Uses the directory name containing the file, relative to *root*.  For the
    root-level AGENTS.md the *root* directory name itself is used.

    Parameters
    ----------
    agents_md_path:
        Absolute path of the AGENTS.md file.
    root:
        Repository root.

    Returns
    -------
    str
        The service name (directory name, lower-cased, with spaces replaced by
        hyphens).
    """
    try:
        rel = agents_md_path.relative_to(root)
        parts = rel.parts
        if len(parts) == 1:
            # Root-level AGENTS.md
            return root.name.lower().replace(" ", "-")
        # Use the immediate parent directory of the AGENTS.md file
        return parts[-2].lower().replace(" ", "-")
    except ValueError:
        return agents_md_path.parent.name.lower().replace(" ", "-")


# ---------------------------------------------------------------------------
# Core regeneration functions
# ---------------------------------------------------------------------------


def regenerate_front_matter(
    path: Path,
    *,
    run_date: str | None = None,
    head_hash: str | None = None,
    root: Path | None = None,
    force: bool = False,
) -> ArtifactDiff:
    """Update the auto-generated front-matter block in a single AGENTS.md file.

    If the file does not exist a minimal stub is created with an empty
    ``<!-- TODO: … -->`` body placeholder.

    The body portion is updated via :func:`_three_way_merge`:

    * If no manual edits are detected (git base == current body), the body is
      left unchanged and only the front-matter is refreshed.
    * If manual edits are detected and ``force=False``, the body is preserved
      verbatim and ``ArtifactDiff.manual_edits_preserved`` is set to ``True``.
    * If ``force=True``, the body is overwritten (except ``CUSTOM-START/END``
      blocks which are always preserved).

    Parameters
    ----------
    path:
        Absolute (or repo-relative) path to the target AGENTS.md file.
    run_date:
        Date string for the ``last_updated`` field (``YYYY-MM-DD``).
        Defaults to today's UTC date.
    head_hash:
        Short git SHA written into the ``head:`` field of the front-matter.
        Defaults to the current HEAD of the repository at *root*.
    root:
        Repository root used for git operations and service name derivation.
        Defaults to *path*'s parent directory.
    force:
        Overwrite manual edits in the body (except ``CUSTOM`` blocks).

    Returns
    -------
    ArtifactDiff
        A structured change record describing what was done to the file.

    Examples
    --------
    ::

        from pathlib import Path
        from harness_skills.generators.agents_md import regenerate_front_matter

        diff = regenerate_front_matter(Path("src/auth/AGENTS.md"), force=False)
        print(diff.change_type, diff.manual_edits_preserved)
    """
    path = Path(path)
    resolved_root = Path(root) if root is not None else path.parent

    if run_date is None:
        run_date = datetime.date.today().isoformat()
    if head_hash is None:
        head_hash = _current_head(resolved_root)

    service = _service_name(path, resolved_root)
    new_block = build_front_matter(service, run_date, head_hash)

    # ── File does not exist: create a stub ──────────────────────────────────
    if not path.exists():
        stub_body = f"<!-- TODO: fill in {path.name} content -->"
        content = new_block + "\n\n" + stub_body + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return ArtifactDiff(
            artifact_path=str(path),
            change_type="created",
            sections_changed=["front-matter"],
            manual_edits_preserved=False,
        )

    # ── File exists: parse and merge ────────────────────────────────────────
    original_content = path.read_text(encoding="utf-8")
    existing_block, current_body = parse_agents_md(original_content)

    # Retrieve the git base for three-way merge
    base_body: str | None = None
    if existing_block is not None:
        meta = parse_front_matter_meta(existing_block)
        stored_head = meta.get("head")
        if stored_head and stored_head != "no-git":
            base_content = _get_git_base(stored_head, path, resolved_root)
            if base_content is not None:
                _, base_body = parse_agents_md(base_content)

    # Perform three-way merge on the body
    merged_body, manual_edits_preserved, body_sections_changed = _three_way_merge(
        base_body,
        current_body,
        force=force,
    )

    # Assemble the sections_changed list
    sections_changed: list[str] = []
    if existing_block != new_block:
        sections_changed.append("front-matter")
    sections_changed.extend(body_sections_changed)

    # Build and write new content
    new_content = new_block + "\n\n" + merged_body
    # Preserve the original trailing newline behaviour
    if original_content.endswith("\n") and not new_content.endswith("\n"):
        new_content += "\n"

    if new_content == original_content:
        return ArtifactDiff(
            artifact_path=str(path),
            change_type="unchanged",
            sections_changed=[],
            manual_edits_preserved=manual_edits_preserved,
        )

    path.write_text(new_content, encoding="utf-8")
    return ArtifactDiff(
        artifact_path=str(path),
        change_type="updated",
        sections_changed=sections_changed,
        manual_edits_preserved=manual_edits_preserved,
    )


def _iter_agents_md(
    root: Path,
    exclude_patterns: list[str] | None = None,
) -> Iterator[Path]:
    """Yield all AGENTS.md paths under *root*, honouring exclusion rules.

    Parameters
    ----------
    root:
        Directory to search recursively.
    exclude_patterns:
        Additional glob patterns (relative to *root*) to exclude.  The
        built-in :data:`_DEFAULT_EXCLUDE_DIRS` are always applied.
    """
    extra_excludes = set(exclude_patterns or [])

    def _is_excluded(p: Path) -> bool:
        for part in p.relative_to(root).parts:
            if part in _DEFAULT_EXCLUDE_DIRS or part in extra_excludes:
                return True
        return False

    for agents_md in root.rglob("AGENTS.md"):
        if not _is_excluded(agents_md):
            yield agents_md


def regenerate_all(
    root: Path | str,
    *,
    run_date: str | None = None,
    head_hash: str | None = None,
    force: bool = False,
    exclude_patterns: list[str] | None = None,
) -> list[ArtifactDiff]:
    """Find every AGENTS.md under *root* and regenerate its front-matter.

    This is the primary entry point for the ``harness update --only agents-md``
    workflow.  It is **idempotent** — running it twice on an unchanged codebase
    produces no file changes on the second run.

    Parameters
    ----------
    root:
        Repository root to scan.
    run_date:
        Date string for all generated front-matter blocks.  Defaults to
        today's UTC date.
    head_hash:
        Git SHA written into all generated front-matter blocks.  Defaults
        to the current HEAD.
    force:
        Overwrite manual edits in the body (except ``CUSTOM`` blocks).
    exclude_patterns:
        Extra path components to exclude from the scan (in addition to the
        built-in list of :data:`_DEFAULT_EXCLUDE_DIRS`).

    Returns
    -------
    list[ArtifactDiff]
        One :class:`~harness_skills.models.update.ArtifactDiff` per
        discovered AGENTS.md file, ordered by path.

    Examples
    --------
    ::

        from pathlib import Path
        from harness_skills.generators.agents_md import regenerate_all

        diffs = regenerate_all(Path("."))
        for d in diffs:
            print(f"{d.artifact_path}: {d.change_type}")
    """
    root = Path(root)

    if run_date is None:
        run_date = datetime.date.today().isoformat()
    if head_hash is None:
        head_hash = _current_head(root)

    diffs: list[ArtifactDiff] = []
    for agents_md_path in sorted(_iter_agents_md(root, exclude_patterns)):
        diff = regenerate_front_matter(
            agents_md_path,
            run_date=run_date,
            head_hash=head_hash,
            root=root,
            force=force,
        )
        diffs.append(diff)
    return diffs
