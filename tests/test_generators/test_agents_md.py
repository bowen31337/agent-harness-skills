"""Tests for harness_skills.generators.agents_md.

Covers:
    - build_front_matter()          builds a valid front-matter block
    - parse_agents_md()             splits content into block + body
    - parse_front_matter_meta()     extracts key-value fields from block
    - is_placeholder_body()         detects TODO-only body content
    - has_custom_blocks()           detects CUSTOM-START/END markers
    - _three_way_merge()            three-way merge with base/current/force
    - regenerate_front_matter()     single-file regeneration (create/update/unchanged)
    - regenerate_all()              multi-file scan + regeneration
    - _service_name()               service name derivation
    - _iter_agents_md()             file discovery with exclusion rules
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness_skills.generators.agents_md import (
    BLOCK_END,
    BLOCK_START,
    CUSTOM_BLOCK_END,
    CUSTOM_BLOCK_START,
    _iter_agents_md,
    _service_name,
    _three_way_merge,
    build_front_matter,
    has_custom_blocks,
    is_placeholder_body,
    parse_agents_md,
    parse_front_matter_meta,
    regenerate_all,
    regenerate_front_matter,
)

# ---------------------------------------------------------------------------
# Shared helpers / fixtures
# ---------------------------------------------------------------------------

RUN_DATE = "2026-03-23"
HEAD_HASH = "abc1234"
SERVICE = "auth-service"


def _make_full_agents_md(
    service: str = SERVICE,
    run_date: str = RUN_DATE,
    head_hash: str = HEAD_HASH,
    body: str = "## Overview\n\nThis is the agent guide.\n",
) -> str:
    block = build_front_matter(service, run_date, head_hash)
    return block + "\n\n" + body


# ---------------------------------------------------------------------------
# build_front_matter
# ---------------------------------------------------------------------------


class TestBuildFrontMatter:
    def test_starts_with_block_start(self):
        block = build_front_matter(SERVICE, RUN_DATE, HEAD_HASH)
        assert block.startswith(BLOCK_START)

    def test_ends_with_block_end(self):
        block = build_front_matter(SERVICE, RUN_DATE, HEAD_HASH)
        assert block.endswith(BLOCK_END)

    def test_contains_last_updated(self):
        block = build_front_matter(SERVICE, RUN_DATE, HEAD_HASH)
        assert f"last_updated: {RUN_DATE}" in block

    def test_contains_head(self):
        block = build_front_matter(SERVICE, RUN_DATE, HEAD_HASH)
        assert f"head: {HEAD_HASH}" in block

    def test_contains_service(self):
        block = build_front_matter(SERVICE, RUN_DATE, HEAD_HASH)
        assert f"service: {SERVICE}" in block

    def test_no_trailing_newline(self):
        block = build_front_matter(SERVICE, RUN_DATE, HEAD_HASH)
        assert not block.endswith("\n")

    def test_roundtrip_via_parse(self):
        block = build_front_matter(SERVICE, RUN_DATE, HEAD_HASH)
        # The standard separator between block and body is "\n\n"; parsing
        # must strip exactly that separator and return only the body text.
        content = block + "\n\nsome body"
        recovered_block, body = parse_agents_md(content)
        assert recovered_block == block
        assert body == "some body"

    def test_roundtrip_with_newline_terminated_body(self):
        block = build_front_matter(SERVICE, RUN_DATE, HEAD_HASH)
        content = block + "\n\nsome body\n"
        recovered_block, body = parse_agents_md(content)
        assert recovered_block == block
        assert body == "some body\n"


# ---------------------------------------------------------------------------
# parse_agents_md
# ---------------------------------------------------------------------------


class TestParseAgentsMd:
    def test_extracts_block_from_content(self):
        block = build_front_matter(SERVICE, RUN_DATE, HEAD_HASH)
        # "\n\n" separator is stripped; only the body remains.
        content = block + "\n\nAgent body here.\n"
        recovered_block, body = parse_agents_md(content)
        assert recovered_block == block
        assert body == "Agent body here.\n"

    def test_no_block_returns_none_and_full_content(self):
        content = "No auto-generated block here.\n\nJust a regular file."
        recovered_block, body = parse_agents_md(content)
        assert recovered_block is None
        assert body == content

    def test_block_at_start_of_file(self):
        block = build_front_matter(SERVICE, RUN_DATE, HEAD_HASH)
        # Standard "\n\n" separator is consumed; body returned without it.
        content = block + "\n\nBody text."
        recovered_block, body = parse_agents_md(content)
        assert recovered_block is not None
        assert body == "Body text."

    def test_empty_body_after_block(self):
        block = build_front_matter(SERVICE, RUN_DATE, HEAD_HASH)
        content = block  # no trailing newline + no body
        _, body = parse_agents_md(content)
        assert body == ""

    def test_body_with_multiple_sections(self):
        block = build_front_matter(SERVICE, RUN_DATE, HEAD_HASH)
        body = "## Section One\n\nContent.\n\n## Section Two\n\nMore content.\n"
        # Exactly "\n\n" separator consumed; multi-section body preserved intact.
        content = block + "\n\n" + body
        _, recovered_body = parse_agents_md(content)
        assert recovered_body == body

    def test_extra_blank_line_beyond_separator_preserved(self):
        block = build_front_matter(SERVICE, RUN_DATE, HEAD_HASH)
        # Three newlines: "\n\n" separator is consumed, the third is kept.
        content = block + "\n\n\nBody with extra blank."
        _, body = parse_agents_md(content)
        assert body.startswith("\nBody with extra blank.")


# ---------------------------------------------------------------------------
# parse_front_matter_meta
# ---------------------------------------------------------------------------


class TestParseFrontMatterMeta:
    def test_extracts_last_updated(self):
        block = build_front_matter(SERVICE, RUN_DATE, HEAD_HASH)
        meta = parse_front_matter_meta(block)
        assert meta["last_updated"] == RUN_DATE

    def test_extracts_head(self):
        block = build_front_matter(SERVICE, RUN_DATE, HEAD_HASH)
        meta = parse_front_matter_meta(block)
        assert meta["head"] == HEAD_HASH

    def test_extracts_service(self):
        block = build_front_matter(SERVICE, RUN_DATE, HEAD_HASH)
        meta = parse_front_matter_meta(block)
        assert meta["service"] == SERVICE

    def test_ignores_comment_lines(self):
        block = build_front_matter(SERVICE, RUN_DATE, HEAD_HASH)
        meta = parse_front_matter_meta(block)
        # Comment lines starting with <!-- should not appear as keys
        assert not any(k.startswith("<!--") for k in meta)

    def test_empty_block_returns_empty_dict(self):
        meta = parse_front_matter_meta(f"{BLOCK_START}\n{BLOCK_END}")
        assert meta == {}

    def test_extra_fields_included(self):
        block = f"{BLOCK_START}\nlast_updated: 2026-01-01\nartifact: agents-md\n{BLOCK_END}"
        meta = parse_front_matter_meta(block)
        assert meta["artifact"] == "agents-md"


# ---------------------------------------------------------------------------
# is_placeholder_body
# ---------------------------------------------------------------------------


class TestIsPlaceholderBody:
    def test_empty_string_is_placeholder(self):
        assert is_placeholder_body("") is True

    def test_whitespace_only_is_placeholder(self):
        assert is_placeholder_body("   \n\n  ") is True

    def test_todo_comment_is_placeholder(self):
        assert is_placeholder_body("<!-- TODO: fill in content -->") is True

    def test_multi_line_todo_is_placeholder(self):
        body = "<!-- TODO:\n  add agent guide here\n-->"
        assert is_placeholder_body(body) is True

    def test_manual_content_is_not_placeholder(self):
        assert is_placeholder_body("## Overview\n\nThis is real content.") is False

    def test_todo_plus_real_content_is_not_placeholder(self):
        body = "<!-- TODO: update -->\n## Section\n\nSome content."
        assert is_placeholder_body(body) is False

    def test_single_hash_heading_is_not_placeholder(self):
        assert is_placeholder_body("# Title\n") is False


# ---------------------------------------------------------------------------
# has_custom_blocks
# ---------------------------------------------------------------------------


class TestHasCustomBlocks:
    def test_detects_custom_start_end_pair(self):
        body = f"{CUSTOM_BLOCK_START}\nManual content\n{CUSTOM_BLOCK_END}"
        assert has_custom_blocks(body) is True

    def test_no_custom_blocks(self):
        assert has_custom_blocks("## Section\n\nContent.") is False

    def test_only_start_marker_is_not_detected(self):
        # Both markers must be present
        assert has_custom_blocks(f"{CUSTOM_BLOCK_START}\nContent") is False

    def test_only_end_marker_is_not_detected(self):
        assert has_custom_blocks(f"Content\n{CUSTOM_BLOCK_END}") is False


# ---------------------------------------------------------------------------
# _three_way_merge
# ---------------------------------------------------------------------------


class TestThreeWayMerge:
    def test_no_base_no_manual_edits_preserves_placeholder(self):
        current = "<!-- TODO: fill in content -->"
        merged, manual_preserved, sections = _three_way_merge(None, current)
        assert merged == current
        assert manual_preserved is False
        assert sections == []

    def test_no_base_manual_edits_preserved(self):
        current = "## Overview\n\nUser added this manually."
        merged, manual_preserved, sections = _three_way_merge(None, current)
        assert merged == current
        assert manual_preserved is True

    def test_base_equals_current_no_edits(self):
        body = "## Overview\n\nOriginal content."
        merged, manual_preserved, sections = _three_way_merge(body, body)
        assert merged == body
        assert manual_preserved is False
        assert sections == []

    def test_base_differs_from_current_manual_edits_preserved(self):
        base = "## Overview\n\nOriginal generated content."
        current = "## Overview\n\nUser has edited this section manually."
        merged, manual_preserved, sections = _three_way_merge(base, current)
        assert merged == current
        assert manual_preserved is True
        assert sections == []

    def test_force_flag_with_manual_edits(self):
        base = "## Overview\n\nOriginal content."
        current = "## Overview\n\nManual edit by user."
        merged, manual_preserved, sections = _three_way_merge(base, current, force=True)
        # With force, manual edits are overwritten (body is "unchanged" here
        # because the force path returns current body but flags it overwritten)
        assert manual_preserved is False
        assert "body" in sections

    def test_custom_blocks_always_preserved_even_with_force(self):
        body = (
            "## Overview\n\n"
            f"{CUSTOM_BLOCK_START}\nManual custom content\n{CUSTOM_BLOCK_END}\n"
        )
        merged, manual_preserved, _ = _three_way_merge("different base", body, force=True)
        assert CUSTOM_BLOCK_START in merged
        assert "Manual custom content" in merged
        assert manual_preserved is True

    def test_placeholder_body_with_no_base_not_flagged_as_manual(self):
        placeholder = "<!-- TODO: fill in content -->"
        merged, manual_preserved, _ = _three_way_merge(None, placeholder)
        assert manual_preserved is False

    def test_no_base_empty_body_not_flagged_as_manual(self):
        merged, manual_preserved, _ = _three_way_merge(None, "")
        assert manual_preserved is False


# ---------------------------------------------------------------------------
# _service_name
# ---------------------------------------------------------------------------


class TestServiceName:
    def test_root_level_uses_root_dir_name(self, tmp_path):
        # tmp_path is something like /tmp/pytest-xxx/test_service_name0
        agents_md = tmp_path / "AGENTS.md"
        name = _service_name(agents_md, tmp_path)
        assert name == tmp_path.name.lower().replace(" ", "-")

    def test_subdirectory_uses_parent_dir_name(self, tmp_path):
        subdir = tmp_path / "auth-service"
        agents_md = subdir / "AGENTS.md"
        name = _service_name(agents_md, tmp_path)
        assert name == "auth-service"

    def test_spaces_replaced_with_hyphens(self, tmp_path):
        subdir = tmp_path / "my service"
        agents_md = subdir / "AGENTS.md"
        name = _service_name(agents_md, tmp_path)
        assert name == "my-service"

    def test_result_is_lowercase(self, tmp_path):
        subdir = tmp_path / "AuthService"
        agents_md = subdir / "AGENTS.md"
        name = _service_name(agents_md, tmp_path)
        assert name == "authservice"


# ---------------------------------------------------------------------------
# _iter_agents_md
# ---------------------------------------------------------------------------


class TestIterAgentsMd:
    def test_finds_root_agents_md(self, tmp_path):
        (tmp_path / "AGENTS.md").write_text("# Root")
        found = list(_iter_agents_md(tmp_path))
        assert tmp_path / "AGENTS.md" in found

    def test_finds_nested_agents_md(self, tmp_path):
        sub = tmp_path / "src" / "auth"
        sub.mkdir(parents=True)
        (sub / "AGENTS.md").write_text("# Auth")
        found = list(_iter_agents_md(tmp_path))
        assert sub / "AGENTS.md" in found

    def test_excludes_node_modules(self, tmp_path):
        nm = tmp_path / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        (nm / "AGENTS.md").write_text("# Should be excluded")
        found = list(_iter_agents_md(tmp_path))
        assert not any("node_modules" in str(p) for p in found)

    def test_excludes_git_dir(self, tmp_path):
        git = tmp_path / ".git" / "info"
        git.mkdir(parents=True)
        (git / "AGENTS.md").write_text("# git internal")
        found = list(_iter_agents_md(tmp_path))
        assert not any(".git" in str(p) for p in found)

    def test_excludes_venv(self, tmp_path):
        venv = tmp_path / ".venv" / "lib"
        venv.mkdir(parents=True)
        (venv / "AGENTS.md").write_text("# venv internal")
        found = list(_iter_agents_md(tmp_path))
        assert not any(".venv" in str(p) for p in found)

    def test_custom_exclude_pattern(self, tmp_path):
        custom = tmp_path / "legacy" / "old"
        custom.mkdir(parents=True)
        (custom / "AGENTS.md").write_text("# Legacy")
        found = list(_iter_agents_md(tmp_path, exclude_patterns=["legacy"]))
        assert not any("legacy" in str(p) for p in found)

    def test_no_agents_md_returns_empty(self, tmp_path):
        (tmp_path / "README.md").write_text("# Readme")
        found = list(_iter_agents_md(tmp_path))
        assert found == []

    def test_multiple_files_all_found(self, tmp_path):
        (tmp_path / "AGENTS.md").write_text("# Root")
        auth = tmp_path / "auth"
        auth.mkdir()
        (auth / "AGENTS.md").write_text("# Auth")
        billing = tmp_path / "billing"
        billing.mkdir()
        (billing / "AGENTS.md").write_text("# Billing")
        found = list(_iter_agents_md(tmp_path))
        assert len(found) == 3


# ---------------------------------------------------------------------------
# regenerate_front_matter — file creation
# ---------------------------------------------------------------------------


class TestRegenerateFrontMatterCreation:
    def test_creates_file_when_missing(self, tmp_path):
        target = tmp_path / "AGENTS.md"
        assert not target.exists()
        diff = regenerate_front_matter(target, run_date=RUN_DATE, head_hash=HEAD_HASH, root=tmp_path)
        assert target.exists()

    def test_created_file_has_front_matter_block(self, tmp_path):
        target = tmp_path / "AGENTS.md"
        regenerate_front_matter(target, run_date=RUN_DATE, head_hash=HEAD_HASH, root=tmp_path)
        content = target.read_text()
        assert BLOCK_START in content
        assert BLOCK_END in content

    def test_created_file_has_todo_body(self, tmp_path):
        target = tmp_path / "AGENTS.md"
        regenerate_front_matter(target, run_date=RUN_DATE, head_hash=HEAD_HASH, root=tmp_path)
        content = target.read_text()
        assert "TODO" in content

    def test_diff_change_type_created(self, tmp_path):
        target = tmp_path / "AGENTS.md"
        diff = regenerate_front_matter(target, run_date=RUN_DATE, head_hash=HEAD_HASH, root=tmp_path)
        assert diff.change_type == "created"

    def test_diff_sections_changed_contains_front_matter(self, tmp_path):
        target = tmp_path / "AGENTS.md"
        diff = regenerate_front_matter(target, run_date=RUN_DATE, head_hash=HEAD_HASH, root=tmp_path)
        assert "front-matter" in diff.sections_changed

    def test_diff_manual_edits_preserved_false_for_new_file(self, tmp_path):
        target = tmp_path / "AGENTS.md"
        diff = regenerate_front_matter(target, run_date=RUN_DATE, head_hash=HEAD_HASH, root=tmp_path)
        assert diff.manual_edits_preserved is False

    def test_creates_parent_directories(self, tmp_path):
        target = tmp_path / "src" / "auth" / "AGENTS.md"
        assert not target.parent.exists()
        regenerate_front_matter(target, run_date=RUN_DATE, head_hash=HEAD_HASH, root=tmp_path)
        assert target.exists()


# ---------------------------------------------------------------------------
# regenerate_front_matter — update existing file
# ---------------------------------------------------------------------------


class TestRegenerateFrontMatterUpdate:
    def _write_existing(
        self,
        path: Path,
        root: Path,
        body: str = "## Overview\n\nExisting content.\n",
        run_date: str = "2026-01-01",
        head_hash: str = "old0000",
    ) -> None:
        content = _make_full_agents_md(
            service="svc", run_date=run_date, head_hash=head_hash, body=body
        )
        path.write_text(content)

    def test_updates_last_updated_field(self, tmp_path):
        target = tmp_path / "AGENTS.md"
        self._write_existing(target, tmp_path, run_date="2026-01-01")
        regenerate_front_matter(target, run_date="2026-03-23", head_hash=HEAD_HASH, root=tmp_path)
        content = target.read_text()
        assert "last_updated: 2026-03-23" in content
        assert "last_updated: 2026-01-01" not in content

    def test_updates_head_field(self, tmp_path):
        target = tmp_path / "AGENTS.md"
        self._write_existing(target, tmp_path, head_hash="old0000")
        regenerate_front_matter(target, run_date=RUN_DATE, head_hash="newabcd", root=tmp_path)
        content = target.read_text()
        assert "head: newabcd" in content
        assert "head: old0000" not in content

    def test_preserves_body_content(self, tmp_path):
        target = tmp_path / "AGENTS.md"
        body = "## Guide\n\nImportant agent instructions here.\n"
        self._write_existing(target, tmp_path, body=body)
        regenerate_front_matter(target, run_date=RUN_DATE, head_hash=HEAD_HASH, root=tmp_path)
        content = target.read_text()
        assert "Important agent instructions here." in content

    def test_diff_change_type_updated_when_front_matter_changes(self, tmp_path):
        target = tmp_path / "AGENTS.md"
        self._write_existing(target, tmp_path, run_date="2026-01-01", head_hash="old0000")
        diff = regenerate_front_matter(
            target, run_date="2026-03-23", head_hash="newabcd", root=tmp_path
        )
        assert diff.change_type == "updated"

    def test_diff_change_type_unchanged_when_nothing_changes(self, tmp_path):
        target = tmp_path / "AGENTS.md"
        # Use the *exact* service name that regenerate_front_matter will derive
        # (root-level file → parent directory name) so the generated block is
        # bit-for-bit identical to what is already on disk.
        service = tmp_path.name.lower().replace(" ", "-")
        block = build_front_matter(service, RUN_DATE, HEAD_HASH)
        body = "## Overview\n\nExisting content.\n"
        target.write_text(block + "\n\n" + body)
        diff = regenerate_front_matter(target, run_date=RUN_DATE, head_hash=HEAD_HASH, root=tmp_path)
        assert diff.change_type == "unchanged"

    def test_diff_artifact_path_matches_file(self, tmp_path):
        target = tmp_path / "AGENTS.md"
        self._write_existing(target, tmp_path)
        diff = regenerate_front_matter(target, run_date=RUN_DATE, head_hash=HEAD_HASH, root=tmp_path)
        assert diff.artifact_path == str(target)

    def test_no_block_in_file_prepends_new_block(self, tmp_path):
        target = tmp_path / "AGENTS.md"
        target.write_text("## Manual AGENTS.md\n\nNo auto-generated block.\n")
        regenerate_front_matter(target, run_date=RUN_DATE, head_hash=HEAD_HASH, root=tmp_path)
        content = target.read_text()
        assert BLOCK_START in content

    def test_manual_edits_preserved_true_when_user_changed_body(self, tmp_path):
        # Write a file where the body differs from what git would return for
        # the stored head.  Since we are not in a git repo (tmp_path), git
        # returns None for the base → the engine sees a non-placeholder body
        # and sets manual_edits_preserved=True.
        target = tmp_path / "AGENTS.md"
        body = "## Section\n\nUser has edited this body.\n"
        self._write_existing(target, tmp_path, body=body)
        diff = regenerate_front_matter(target, run_date=RUN_DATE, head_hash=HEAD_HASH, root=tmp_path)
        assert diff.manual_edits_preserved is True

    def test_placeholder_body_not_flagged_as_manual(self, tmp_path):
        target = tmp_path / "AGENTS.md"
        placeholder_body = "<!-- TODO: fill in AGENTS.md content -->"
        block = build_front_matter("svc", "2026-01-01", "old0000")
        target.write_text(block + "\n\n" + placeholder_body + "\n")
        diff = regenerate_front_matter(target, run_date=RUN_DATE, head_hash=HEAD_HASH, root=tmp_path)
        assert diff.manual_edits_preserved is False

    def test_custom_block_body_always_preserved(self, tmp_path):
        target = tmp_path / "AGENTS.md"
        body = (
            "## Overview\n\n"
            f"{CUSTOM_BLOCK_START}\n"
            "Critical manual instructions — never overwrite.\n"
            f"{CUSTOM_BLOCK_END}\n"
        )
        self._write_existing(target, tmp_path, body=body)
        diff = regenerate_front_matter(
            target, run_date=RUN_DATE, head_hash=HEAD_HASH, root=tmp_path, force=True
        )
        content = target.read_text()
        assert "Critical manual instructions — never overwrite." in content
        assert diff.manual_edits_preserved is True


# ---------------------------------------------------------------------------
# regenerate_front_matter — force flag
# ---------------------------------------------------------------------------


class TestRegenerateFrontMatterForce:
    def test_force_overwrites_manual_body(self, tmp_path):
        target = tmp_path / "AGENTS.md"
        body = "## Section\n\nManually edited content.\n"
        block = build_front_matter("svc", "2026-01-01", "old0000")
        target.write_text(block + "\n\n" + body)
        diff = regenerate_front_matter(
            target, run_date=RUN_DATE, head_hash=HEAD_HASH, root=tmp_path, force=True
        )
        assert diff.manual_edits_preserved is False

    def test_force_does_not_remove_custom_block(self, tmp_path):
        target = tmp_path / "AGENTS.md"
        body = (
            f"{CUSTOM_BLOCK_START}\n"
            "This must survive force.\n"
            f"{CUSTOM_BLOCK_END}\n"
        )
        block = build_front_matter("svc", "2026-01-01", "old0000")
        target.write_text(block + "\n\n" + body)
        regenerate_front_matter(
            target, run_date=RUN_DATE, head_hash=HEAD_HASH, root=tmp_path, force=True
        )
        content = target.read_text()
        assert "This must survive force." in content


# ---------------------------------------------------------------------------
# regenerate_all
# ---------------------------------------------------------------------------


class TestRegenerateAll:
    def test_empty_directory_returns_empty_list(self, tmp_path):
        diffs = regenerate_all(tmp_path, run_date=RUN_DATE, head_hash=HEAD_HASH)
        assert diffs == []

    def test_single_file_returns_single_diff(self, tmp_path):
        (tmp_path / "AGENTS.md").write_text("<!-- TODO: fill in -->")
        diffs = regenerate_all(tmp_path, run_date=RUN_DATE, head_hash=HEAD_HASH)
        assert len(diffs) == 1

    def test_multiple_files_all_processed(self, tmp_path):
        (tmp_path / "AGENTS.md").write_text("<!-- TODO: root -->")
        auth = tmp_path / "auth"
        auth.mkdir()
        (auth / "AGENTS.md").write_text("<!-- TODO: auth -->")
        billing = tmp_path / "billing"
        billing.mkdir()
        (billing / "AGENTS.md").write_text("<!-- TODO: billing -->")
        diffs = regenerate_all(tmp_path, run_date=RUN_DATE, head_hash=HEAD_HASH)
        assert len(diffs) == 3

    def test_diffs_sorted_by_path(self, tmp_path):
        (tmp_path / "AGENTS.md").write_text("<!-- TODO: root -->")
        z_dir = tmp_path / "z_service"
        z_dir.mkdir()
        (z_dir / "AGENTS.md").write_text("<!-- TODO: z -->")
        a_dir = tmp_path / "a_service"
        a_dir.mkdir()
        (a_dir / "AGENTS.md").write_text("<!-- TODO: a -->")
        diffs = regenerate_all(tmp_path, run_date=RUN_DATE, head_hash=HEAD_HASH)
        paths = [d.artifact_path for d in diffs]
        assert paths == sorted(paths)

    def test_excludes_node_modules(self, tmp_path):
        nm = tmp_path / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        (nm / "AGENTS.md").write_text("<!-- TODO: nm -->")
        diffs = regenerate_all(tmp_path, run_date=RUN_DATE, head_hash=HEAD_HASH)
        assert all("node_modules" not in d.artifact_path for d in diffs)

    def test_custom_exclude_patterns_respected(self, tmp_path):
        legacy = tmp_path / "legacy"
        legacy.mkdir()
        (legacy / "AGENTS.md").write_text("<!-- TODO: legacy -->")
        (tmp_path / "AGENTS.md").write_text("<!-- TODO: root -->")
        diffs = regenerate_all(
            tmp_path,
            run_date=RUN_DATE,
            head_hash=HEAD_HASH,
            exclude_patterns=["legacy"],
        )
        assert all("legacy" not in d.artifact_path for d in diffs)
        assert len(diffs) == 1

    def test_all_files_get_updated_front_matter(self, tmp_path):
        for name in ("", "auth", "billing"):
            d = tmp_path / name if name else tmp_path
            d.mkdir(exist_ok=True)
            (d / "AGENTS.md").write_text("<!-- TODO: fill in -->")
        regenerate_all(tmp_path, run_date=RUN_DATE, head_hash=HEAD_HASH)
        for name in ("", "auth", "billing"):
            d = tmp_path / name if name else tmp_path
            content = (d / "AGENTS.md").read_text()
            assert BLOCK_START in content
            assert f"last_updated: {RUN_DATE}" in content

    def test_idempotent_second_run_returns_unchanged(self, tmp_path):
        # Seed the directory with a stale front-matter so run 1 produces an update.
        old_block = build_front_matter("old-svc", "2026-01-01", "old0000")
        (tmp_path / "AGENTS.md").write_text(old_block + "\n\n<!-- TODO: fill in -->\n")
        # First run: detects stale front-matter → updated
        diffs1 = regenerate_all(tmp_path, run_date=RUN_DATE, head_hash=HEAD_HASH)
        assert any(d.change_type in ("created", "updated") for d in diffs1)
        # Second run with the same parameters: file is already current → unchanged
        diffs2 = regenerate_all(tmp_path, run_date=RUN_DATE, head_hash=HEAD_HASH)
        assert all(d.change_type == "unchanged" for d in diffs2)

    def test_force_flag_propagated_to_each_file(self, tmp_path):
        body = "## Section\n\nUser edited content.\n"
        block = build_front_matter("root", "2026-01-01", "old0000")
        (tmp_path / "AGENTS.md").write_text(block + "\n\n" + body)
        diffs = regenerate_all(
            tmp_path, run_date=RUN_DATE, head_hash=HEAD_HASH, force=True
        )
        assert all(d.manual_edits_preserved is False for d in diffs)

    def test_returns_artifact_diff_instances(self, tmp_path):
        from harness_skills.models.update import ArtifactDiff

        (tmp_path / "AGENTS.md").write_text("<!-- TODO: fill in -->")
        diffs = regenerate_all(tmp_path, run_date=RUN_DATE, head_hash=HEAD_HASH)
        assert all(isinstance(d, ArtifactDiff) for d in diffs)
