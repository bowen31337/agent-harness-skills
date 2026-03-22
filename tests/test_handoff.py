"""Unit tests for harness_skills.handoff.

Covers:
  - SearchHints / HandoffDocument construction and field defaults
  - HandoffDocument.to_markdown() and from_markdown() round-trip
  - HandoffProtocol.ending_system_prompt_addendum() content checks
  - HandoffProtocol.write_handoff() / load_handoff() file I/O
  - HandoffProtocol.resuming_system_prompt_addendum() content checks
  - HandoffProtocol.resuming_agent_options() — no handoff path
  - _append_jsonl() persistence and HandoffTracker.get_resume_prompt() / get_search_hints()
  - HandoffTracker.get_resume_prompt() / get_search_hints() with empty / corrupt JSONL
  - _slugify() helper
  - HandoffDocument.from_markdown() error handling (missing frontmatter)

All tests run entirely offline — no network, no LLM calls.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from harness_skills.handoff import (
    HandoffDocument,
    HandoffProtocol,
    HandoffTracker,
    SearchHints,
    _append_jsonl,
    _slugify,
)

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _minimal_doc() -> HandoffDocument:
    """Return the smallest valid HandoffDocument."""
    return HandoffDocument(
        session_id="sess_test_001",
        timestamp="2026-03-22T10:00:00Z",
        task="Add rate limiting to API gateway",
        status="in_progress",
    )


def _full_doc() -> HandoffDocument:
    """Return a HandoffDocument with every field populated."""
    return HandoffDocument(
        session_id="sess_test_002",
        timestamp="2026-03-22T11:30:00Z",
        task="Implement JWT authentication",
        status="in_progress",
        accomplished=[
            "Scaffolded AuthService in src/auth/service.py",
            "Added JWT config constants to src/config.py",
        ],
        in_progress=[
            "Wiring middleware into gateway.py (~30% done — call auth.verify() in handle_request)",
        ],
        next_steps=[
            "Import AuthService in src/api/gateway.py",
            "Call rate_limiter.check() before routing in handle_request()",
            "Add integration test for 429 response",
        ],
        search_hints=SearchHints(
            file_paths=[
                "src/auth/service.py — AuthService class",
                "src/api/gateway.py — wire middleware here",
                "src/config.py — JWT_SECRET defined here",
            ],
            directories=["src/auth/", "src/api/", "tests/"],
            grep_patterns=[
                "class AuthService",
                "def handle_request",
                "JWT_SECRET",
            ],
            symbols=["AuthService", "handle_request", "JWT_SECRET"],
        ),
        open_questions=["Should tokens expire after 1h or 24h?"],
        artifacts=[
            "src/auth/service.py (new)",
            "src/config.py (modified)",
        ],
        notes="Using PyJWT 2.x — import is `jwt`, not `JWT`.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# SearchHints
# ─────────────────────────────────────────────────────────────────────────────


class TestSearchHints:
    def test_defaults_are_empty_lists(self) -> None:
        hints = SearchHints()
        assert hints.file_paths == []
        assert hints.grep_patterns == []
        assert hints.symbols == []
        assert hints.directories == []

    def test_fields_store_values(self) -> None:
        hints = SearchHints(
            file_paths=["src/auth.py"],
            grep_patterns=["class Auth"],
            symbols=["AuthService"],
            directories=["src/"],
        )
        assert hints.file_paths == ["src/auth.py"]
        assert hints.grep_patterns == ["class Auth"]
        assert hints.symbols == ["AuthService"]
        assert hints.directories == ["src/"]


# ─────────────────────────────────────────────────────────────────────────────
# HandoffDocument — construction
# ─────────────────────────────────────────────────────────────────────────────


class TestHandoffDocumentConstruction:
    def test_minimal_document(self) -> None:
        doc = _minimal_doc()
        assert doc.session_id == "sess_test_001"
        assert doc.task == "Add rate limiting to API gateway"
        assert doc.status == "in_progress"
        assert doc.accomplished == []
        assert doc.next_steps == []
        assert doc.notes == ""

    def test_default_status_is_in_progress(self) -> None:
        doc = HandoffDocument(
            session_id="x",
            timestamp="2026-01-01T00:00:00Z",
            task="test",
        )
        assert doc.status == "in_progress"

    def test_full_document_fields(self) -> None:
        doc = _full_doc()
        assert len(doc.accomplished) == 2
        assert len(doc.next_steps) == 3
        assert len(doc.search_hints.file_paths) == 3
        assert len(doc.search_hints.grep_patterns) == 3
        assert len(doc.search_hints.symbols) == 3
        assert len(doc.search_hints.directories) == 3
        assert doc.open_questions == ["Should tokens expire after 1h or 24h?"]


# ─────────────────────────────────────────────────────────────────────────────
# HandoffDocument.to_markdown()
# ─────────────────────────────────────────────────────────────────────────────


class TestToMarkdown:
    def test_frontmatter_fields_present(self) -> None:
        md = _minimal_doc().to_markdown()
        assert "session_id: sess_test_001" in md
        assert "timestamp: '2026-03-22T10:00:00Z'" in md or "timestamp: 2026-03-22T10:00:00Z" in md
        assert "task: Add rate limiting to API gateway" in md
        assert "status: in_progress" in md

    def test_frontmatter_delimiters(self) -> None:
        md = _minimal_doc().to_markdown()
        lines = md.splitlines()
        assert lines[0] == "---"
        # Find the closing ---
        close_idx = next(i for i, l in enumerate(lines[1:], 1) if l == "---")
        assert close_idx > 0

    def test_section_headers_present(self) -> None:
        md = _full_doc().to_markdown()
        for header in [
            "## Accomplished",
            "## In Progress",
            "## Next Steps",
            "## Search Hints",
            "## Open Questions",
            "## Artifacts",
            "## Notes",
        ]:
            assert header in md, f"Missing section: {header}"

    def test_search_hint_subsections(self) -> None:
        md = _full_doc().to_markdown()
        assert "### Key Files" in md
        assert "### Key Directories" in md
        assert "### Grep Patterns" in md
        assert "### Key Symbols" in md

    def test_accomplished_bullets_rendered(self) -> None:
        md = _full_doc().to_markdown()
        assert "- Scaffolded AuthService in src/auth/service.py" in md

    def test_next_steps_bullets_rendered(self) -> None:
        md = _full_doc().to_markdown()
        assert "- Import AuthService in src/api/gateway.py" in md

    def test_grep_patterns_in_code_block(self) -> None:
        md = _full_doc().to_markdown()
        assert "```" in md
        assert "class AuthService" in md

    def test_notes_rendered(self) -> None:
        md = _full_doc().to_markdown()
        assert "PyJWT 2.x" in md

    def test_empty_sections_show_none_placeholder(self) -> None:
        md = _minimal_doc().to_markdown()
        assert "*(none)*" in md

    def test_no_search_hints_placeholder(self) -> None:
        doc = HandoffDocument(
            session_id="x",
            timestamp="2026-01-01T00:00:00Z",
            task="test",
        )
        md = doc.to_markdown()
        assert "*(no hints recorded)*" in md


# ─────────────────────────────────────────────────────────────────────────────
# HandoffDocument.from_markdown() — round-trip
# ─────────────────────────────────────────────────────────────────────────────


class TestFromMarkdownRoundTrip:
    def _roundtrip(self, original: HandoffDocument) -> HandoffDocument:
        return HandoffDocument.from_markdown(original.to_markdown())

    def test_minimal_roundtrip(self) -> None:
        doc = _minimal_doc()
        restored = self._roundtrip(doc)
        assert restored.session_id == doc.session_id
        assert restored.task == doc.task
        assert restored.status == doc.status

    def test_full_roundtrip_frontmatter(self) -> None:
        doc = _full_doc()
        restored = self._roundtrip(doc)
        assert restored.session_id == doc.session_id
        assert restored.timestamp == doc.timestamp
        assert restored.task == doc.task
        assert restored.status == doc.status

    def test_full_roundtrip_accomplished(self) -> None:
        doc = _full_doc()
        restored = self._roundtrip(doc)
        assert restored.accomplished == doc.accomplished

    def test_full_roundtrip_in_progress(self) -> None:
        doc = _full_doc()
        restored = self._roundtrip(doc)
        assert restored.in_progress == doc.in_progress

    def test_full_roundtrip_next_steps(self) -> None:
        doc = _full_doc()
        restored = self._roundtrip(doc)
        assert restored.next_steps == doc.next_steps

    def test_full_roundtrip_search_hints_files(self) -> None:
        doc = _full_doc()
        restored = self._roundtrip(doc)
        assert restored.search_hints.file_paths == doc.search_hints.file_paths

    def test_full_roundtrip_search_hints_directories(self) -> None:
        doc = _full_doc()
        restored = self._roundtrip(doc)
        assert restored.search_hints.directories == doc.search_hints.directories

    def test_full_roundtrip_search_hints_grep_patterns(self) -> None:
        doc = _full_doc()
        restored = self._roundtrip(doc)
        assert restored.search_hints.grep_patterns == doc.search_hints.grep_patterns

    def test_full_roundtrip_search_hints_symbols(self) -> None:
        doc = _full_doc()
        restored = self._roundtrip(doc)
        assert restored.search_hints.symbols == doc.search_hints.symbols

    def test_full_roundtrip_open_questions(self) -> None:
        doc = _full_doc()
        restored = self._roundtrip(doc)
        assert restored.open_questions == doc.open_questions

    def test_full_roundtrip_artifacts(self) -> None:
        doc = _full_doc()
        restored = self._roundtrip(doc)
        assert restored.artifacts == doc.artifacts

    def test_full_roundtrip_notes(self) -> None:
        doc = _full_doc()
        restored = self._roundtrip(doc)
        assert restored.notes == doc.notes

    def test_missing_frontmatter_raises(self) -> None:
        bad_md = "## Accomplished\n- did stuff\n"
        with pytest.raises(ValueError, match="frontmatter"):
            HandoffDocument.from_markdown(bad_md)

    def test_none_placeholder_gives_empty_list(self) -> None:
        doc = _minimal_doc()
        restored = self._roundtrip(doc)
        assert restored.accomplished == []
        assert restored.next_steps == []

    def test_status_blocked_preserved(self) -> None:
        doc = HandoffDocument(
            session_id="x",
            timestamp="2026-01-01T00:00:00Z",
            task="test",
            status="blocked",
        )
        restored = self._roundtrip(doc)
        assert restored.status == "blocked"

    def test_status_done_preserved(self) -> None:
        doc = HandoffDocument(
            session_id="x",
            timestamp="2026-01-01T00:00:00Z",
            task="test",
            status="done",
        )
        restored = self._roundtrip(doc)
        assert restored.status == "done"


# ─────────────────────────────────────────────────────────────────────────────
# HandoffProtocol — system prompt content
# ─────────────────────────────────────────────────────────────────────────────


class TestHandoffProtocolSystemPrompt:
    def test_ending_prompt_contains_handoff_path(self, tmp_path: Path) -> None:
        hp = HandoffProtocol(handoff_path=tmp_path / "progress.md")
        prompt = hp.ending_system_prompt_addendum()
        assert str(tmp_path / "progress.md") in prompt

    def test_ending_prompt_contains_task(self, tmp_path: Path) -> None:
        hp = HandoffProtocol(handoff_path=tmp_path / "progress.md")
        prompt = hp.ending_system_prompt_addendum(task="Build auth module")
        assert "Build auth module" in prompt

    def test_ending_prompt_mentions_search_hints(self, tmp_path: Path) -> None:
        hp = HandoffProtocol(handoff_path=tmp_path / "progress.md")
        prompt = hp.ending_system_prompt_addendum()
        assert "Search Hints" in prompt or "search hints" in prompt.lower()

    def test_ending_prompt_mentions_key_files(self, tmp_path: Path) -> None:
        hp = HandoffProtocol(handoff_path=tmp_path / "progress.md")
        prompt = hp.ending_system_prompt_addendum()
        assert "Key Files" in prompt

    def test_ending_prompt_mentions_grep_patterns(self, tmp_path: Path) -> None:
        hp = HandoffProtocol(handoff_path=tmp_path / "progress.md")
        prompt = hp.ending_system_prompt_addendum()
        assert "Grep Patterns" in prompt

    def test_resuming_prompt_contains_task(self, tmp_path: Path) -> None:
        hp = HandoffProtocol(handoff_path=tmp_path / "progress.md")
        doc = _full_doc()
        prompt = hp.resuming_system_prompt_addendum(doc)
        assert doc.task in prompt

    def test_resuming_prompt_contains_status(self, tmp_path: Path) -> None:
        hp = HandoffProtocol(handoff_path=tmp_path / "progress.md")
        doc = _full_doc()
        prompt = hp.resuming_system_prompt_addendum(doc)
        assert doc.status in prompt

    def test_resuming_prompt_lists_file_hints(self, tmp_path: Path) -> None:
        hp = HandoffProtocol(handoff_path=tmp_path / "progress.md")
        doc = _full_doc()
        prompt = hp.resuming_system_prompt_addendum(doc)
        assert "src/auth/service.py" in prompt

    def test_resuming_prompt_lists_grep_hints(self, tmp_path: Path) -> None:
        hp = HandoffProtocol(handoff_path=tmp_path / "progress.md")
        doc = _full_doc()
        prompt = hp.resuming_system_prompt_addendum(doc)
        assert "class AuthService" in prompt

    def test_resuming_prompt_lists_symbol_hints(self, tmp_path: Path) -> None:
        hp = HandoffProtocol(handoff_path=tmp_path / "progress.md")
        doc = _full_doc()
        prompt = hp.resuming_system_prompt_addendum(doc)
        assert "AuthService" in prompt


# ─────────────────────────────────────────────────────────────────────────────
# HandoffProtocol — file I/O
# ─────────────────────────────────────────────────────────────────────────────


class TestHandoffProtocolFileIO:
    def test_write_then_load_roundtrip(self, tmp_path: Path) -> None:
        path = tmp_path / ".claude" / "plan-progress.md"
        hp = HandoffProtocol(handoff_path=path)
        doc = _full_doc()
        hp.write_handoff(doc)
        loaded = hp.load_handoff()
        assert loaded is not None
        assert loaded.task == doc.task
        assert loaded.status == doc.status

    def test_write_creates_parent_dirs(self, tmp_path: Path) -> None:
        deep_path = tmp_path / "a" / "b" / "c" / "progress.md"
        hp = HandoffProtocol(handoff_path=deep_path)
        hp.write_handoff(_minimal_doc())
        assert deep_path.exists()

    def test_load_returns_none_when_missing(self, tmp_path: Path) -> None:
        hp = HandoffProtocol(handoff_path=tmp_path / "missing.md")
        assert hp.load_handoff() is None

    def test_load_returns_none_on_corrupt_file(self, tmp_path: Path) -> None:
        path = tmp_path / "corrupt.md"
        path.write_text("not a handoff file at all")
        hp = HandoffProtocol(handoff_path=path)
        import warnings
        with warnings.catch_warnings(record=True):
            result = hp.load_handoff()
        assert result is None

    def test_write_overwrites_previous(self, tmp_path: Path) -> None:
        path = tmp_path / "progress.md"
        hp = HandoffProtocol(handoff_path=path)
        doc1 = _minimal_doc()
        doc2 = HandoffDocument(
            session_id="sess_second",
            timestamp="2026-03-22T12:00:00Z",
            task="Second task",
        )
        hp.write_handoff(doc1)
        hp.write_handoff(doc2)
        loaded = hp.load_handoff()
        assert loaded is not None
        assert loaded.task == "Second task"

    def test_resuming_agent_options_no_handoff(self, tmp_path: Path) -> None:
        """When no handoff exists, options are returned unchanged."""
        hp = HandoffProtocol(handoff_path=tmp_path / "missing.md")

        class FakeOptions:
            system_prompt = "original"
            allowed_tools = ["Read"]

        opts, doc = hp.resuming_agent_options(FakeOptions())
        assert doc is None
        assert opts.system_prompt == "original"

    def test_resuming_agent_options_injects_handoff(self, tmp_path: Path) -> None:
        """When a handoff exists, its context is prepended to the system prompt."""
        path = tmp_path / "progress.md"
        hp = HandoffProtocol(handoff_path=path)
        hp.write_handoff(_full_doc())

        class FakeOptions:
            system_prompt = "original"
            allowed_tools = ["Read"]

        opts, doc = hp.resuming_agent_options(FakeOptions())
        assert doc is not None
        assert "original" in opts.system_prompt
        # The resuming preamble should appear before the original prompt
        assert opts.system_prompt.index("original") > 0

    def test_ending_agent_options_ensures_write_tool(self, tmp_path: Path) -> None:
        """ending_agent_options() guarantees Write is in allowed_tools."""
        hp = HandoffProtocol(handoff_path=tmp_path / "p.md")

        class FakeOptions:
            system_prompt = ""
            allowed_tools = ["Read"]

        opts = hp.ending_agent_options(FakeOptions(), task="test")
        assert "Write" in opts.allowed_tools

    def test_ending_agent_options_does_not_duplicate_write(self, tmp_path: Path) -> None:
        hp = HandoffProtocol(handoff_path=tmp_path / "p.md")

        class FakeOptions:
            system_prompt = ""
            allowed_tools = ["Read", "Write"]

        opts = hp.ending_agent_options(FakeOptions())
        assert opts.allowed_tools.count("Write") == 1

    def test_blank_handoff_factory(self) -> None:
        doc = HandoffProtocol.blank_handoff(session_id="abc", task="My task")
        assert doc.session_id == "abc"
        assert doc.task == "My task"
        assert doc.status == "in_progress"
        assert doc.accomplished == []


# ─────────────────────────────────────────────────────────────────────────────
# _append_jsonl and HandoffTracker class-level readers
# ─────────────────────────────────────────────────────────────────────────────


class TestAppendJsonl:
    def test_appends_one_line_per_call(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        doc = _full_doc()
        _append_jsonl(doc, jsonl_path=path)
        _append_jsonl(doc, jsonl_path=path)
        lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
        assert len(lines) == 2

    def test_entry_contains_required_fields(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        doc = _full_doc()
        _append_jsonl(doc, jsonl_path=path)
        entry = json.loads(path.read_text().strip())
        assert entry["session_id"] == doc.session_id
        assert entry["task"] == doc.task
        assert entry["status"] == doc.status
        assert "search_hints" in entry

    def test_search_hints_serialised(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        doc = _full_doc()
        _append_jsonl(doc, jsonl_path=path)
        entry = json.loads(path.read_text().strip())
        hints = entry["search_hints"]
        assert hints["file_paths"] == doc.search_hints.file_paths
        assert hints["grep_patterns"] == doc.search_hints.grep_patterns
        assert hints["symbols"] == doc.search_hints.symbols
        assert hints["directories"] == doc.search_hints.directories

    def test_resume_prompt_field_stored(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        doc = _full_doc()
        _append_jsonl(doc, jsonl_path=path, resume_prompt="RESUME ME")
        entry = json.loads(path.read_text().strip())
        assert entry["resume_prompt"] == "RESUME ME"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "deep" / "nested" / "audit.jsonl"
        _append_jsonl(_minimal_doc(), jsonl_path=path)
        assert path.exists()

    def test_entries_are_valid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        for doc in [_minimal_doc(), _full_doc()]:
            _append_jsonl(doc, jsonl_path=path)
        for line in path.read_text().splitlines():
            parsed = json.loads(line)  # must not raise
            assert "task" in parsed


class TestHandoffTrackerReaders:
    def test_get_resume_prompt_returns_empty_when_no_file(self, tmp_path: Path) -> None:
        result = HandoffTracker.get_resume_prompt(jsonl_path=tmp_path / "missing.jsonl")
        assert result == ""

    def test_get_resume_prompt_returns_empty_when_file_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.jsonl"
        path.write_text("")
        assert HandoffTracker.get_resume_prompt(jsonl_path=path) == ""

    def test_get_resume_prompt_returns_latest(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        _append_jsonl(_minimal_doc(), jsonl_path=path, resume_prompt="FIRST")
        _append_jsonl(_minimal_doc(), jsonl_path=path, resume_prompt="SECOND")
        assert HandoffTracker.get_resume_prompt(jsonl_path=path) == "SECOND"

    def test_get_resume_prompt_no_field_returns_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        _append_jsonl(_minimal_doc(), jsonl_path=path)  # no resume_prompt arg
        assert HandoffTracker.get_resume_prompt(jsonl_path=path) == ""

    def test_get_resume_prompt_corrupt_jsonl_returns_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        path.write_text("not json at all\n")
        assert HandoffTracker.get_resume_prompt(jsonl_path=path) == ""

    def test_get_search_hints_returns_none_when_no_file(self, tmp_path: Path) -> None:
        result = HandoffTracker.get_search_hints(jsonl_path=tmp_path / "missing.jsonl")
        assert result is None

    def test_get_search_hints_returns_hints_from_latest(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        _append_jsonl(_minimal_doc(), jsonl_path=path)  # empty hints
        _append_jsonl(_full_doc(), jsonl_path=path)     # full hints
        hints = HandoffTracker.get_search_hints(jsonl_path=path)
        assert hints is not None
        assert hints.file_paths == _full_doc().search_hints.file_paths

    def test_get_search_hints_returns_none_when_no_hints_field(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        # Write a JSONL line with no search_hints key
        path.write_text(json.dumps({"task": "t", "session_id": "x"}) + "\n")
        assert HandoffTracker.get_search_hints(jsonl_path=path) is None

    def test_get_search_hints_corrupt_jsonl_returns_none(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        path.write_text("{broken json\n")
        assert HandoffTracker.get_search_hints(jsonl_path=path) is None


# ─────────────────────────────────────────────────────────────────────────────
# _slugify helper
# ─────────────────────────────────────────────────────────────────────────────


class TestSlugify:
    def test_simple_phrase(self) -> None:
        assert _slugify("Add JWT authentication") == "add-jwt-authentication"

    def test_special_chars_replaced(self) -> None:
        slug = _slugify("Fix: auth/token bug (v2)")
        assert "/" not in slug
        assert "(" not in slug
        assert ")" not in slug

    def test_max_length_respected(self) -> None:
        long = "a" * 200
        assert len(_slugify(long, max_len=50)) <= 50

    def test_empty_string(self) -> None:
        assert _slugify("") == ""

    def test_leading_trailing_hyphens_stripped(self) -> None:
        slug = _slugify("  --hello world--  ")
        assert not slug.startswith("-")
        assert not slug.endswith("-")

    def test_lowercase_output(self) -> None:
        assert _slugify("CamelCase") == _slugify("CamelCase").lower()


# ─────────────────────────────────────────────────────────────────────────────
# Handoff integrity — search hint constraints
# ─────────────────────────────────────────────────────────────────────────────


class TestSearchHintQuality:
    """Validate the 'give a map, not the territory' principle in practice."""

    def test_to_markdown_does_not_embed_file_contents(self) -> None:
        """Markdown output should contain paths but not resemble file contents."""
        doc = _full_doc()
        md = doc.to_markdown()
        # Paths appear; actual Python/code syntax should not be pasted verbatim
        assert "src/auth/service.py" in md
        # No multi-line code excerpts (heuristic: no indented def bodies)
        assert "    return" not in md

    def test_key_files_are_paths_not_contents(self) -> None:
        """Key file entries look like paths (contain '/' or '.') not code."""
        doc = _full_doc()
        for fp in doc.search_hints.file_paths:
            # Every key file hint should look like a path or path-with-note
            assert "/" in fp or "." in fp, f"Expected path-like hint, got: {fp!r}"

    def test_grep_patterns_are_short_strings(self) -> None:
        """Grep patterns should be concise — not multi-line dumps."""
        doc = _full_doc()
        for pattern in doc.search_hints.grep_patterns:
            assert "\n" not in pattern, f"Pattern contains newline: {pattern!r}"
            assert len(pattern) < 200, f"Pattern suspiciously long: {pattern!r}"
