"""Tests for harness_skills.resume — plan state loading, formatting, and CLI."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from harness_skills.resume import (
    PlanState,
    SearchHints,
    _load_from_jsonl,
    _load_from_markdown,
    build_resume_prompt,
    format_hints_only,
    format_resume_context,
    load_plan_state,
    main,
    resume_agent_options,
)


# ── SearchHints ──────────────────────────────────────────────────────────────


class TestSearchHints:
    def test_is_empty_true_when_all_empty(self):
        h = SearchHints()
        assert h.is_empty() is True

    def test_is_empty_false_when_file_paths(self):
        h = SearchHints(file_paths=["a.py"])
        assert h.is_empty() is False

    def test_is_empty_false_when_directories(self):
        h = SearchHints(directories=["src/"])
        assert h.is_empty() is False

    def test_is_empty_false_when_grep_patterns(self):
        h = SearchHints(grep_patterns=["TODO"])
        assert h.is_empty() is False

    def test_is_empty_false_when_symbols(self):
        h = SearchHints(symbols=["MyClass"])
        assert h.is_empty() is False


# ── PlanState ────────────────────────────────────────────────────────────────


class TestPlanState:
    def test_found_false_when_source_none(self):
        s = PlanState()
        assert s.found() is False

    def test_found_true_when_source_markdown(self):
        s = PlanState(source="markdown")
        assert s.found() is True

    def test_found_true_when_source_jsonl(self):
        s = PlanState(source="jsonl")
        assert s.found() is True

    def test_to_dict_has_expected_keys(self):
        s = PlanState(task="t1", status="in_progress", source="markdown")
        d = s.to_dict()
        assert d["task"] == "t1"
        assert d["status"] == "in_progress"
        assert d["source"] == "markdown"
        assert "search_hints" in d
        assert set(d["search_hints"].keys()) == {
            "file_paths", "directories", "grep_patterns", "symbols"
        }

    def test_to_dict_includes_all_fields(self):
        s = PlanState(
            task="t1", status="done", session_id="s1", timestamp="2026-01-01",
            accomplished=["a"], in_progress=["b"], next_steps=["c"],
            search_hints=SearchHints(file_paths=["x.py"]),
            open_questions=["q1"], artifacts=["art1"], notes="note",
            source="jsonl",
        )
        d = s.to_dict()
        assert d["accomplished"] == ["a"]
        assert d["in_progress"] == ["b"]
        assert d["next_steps"] == ["c"]
        assert d["open_questions"] == ["q1"]
        assert d["artifacts"] == ["art1"]
        assert d["notes"] == "note"
        assert d["search_hints"]["file_paths"] == ["x.py"]


# ── _load_from_markdown ─────────────────────────────────────────────────────


class TestLoadFromMarkdown:
    def test_returns_none_when_file_missing(self, tmp_path):
        result = _load_from_markdown(tmp_path / "nope.md")
        assert result is None

    def test_loads_valid_markdown(self, tmp_path):
        md = tmp_path / "plan.md"
        md.write_text("# Plan\nSome raw markdown content\n")
        result = _load_from_markdown(md)
        assert result is not None
        assert result.source == "markdown"

    def test_exception_path_returns_raw_state(self, tmp_path):
        """When HandoffDocument.from_markdown raises, return raw PlanState."""
        md = tmp_path / "plan.md"
        md.write_text("not parseable as handoff")
        with patch(
            "harness_skills.handoff.HandoffDocument.from_markdown",
            side_effect=ValueError("parse error"),
        ):
            result = _load_from_markdown(md)
        assert result is not None
        assert result.source == "markdown"
        assert result._raw == "not parseable as handoff"


# ── _load_from_jsonl ────────────────────────────────────────────────────────


class TestLoadFromJsonl:
    def test_returns_none_when_file_missing(self, tmp_path):
        result = _load_from_jsonl(tmp_path / "nope.jsonl")
        assert result is None

    def test_returns_none_for_empty_file(self, tmp_path):
        f = tmp_path / "empty.jsonl"
        f.write_text("")
        assert _load_from_jsonl(f) is None

    def test_returns_none_for_blank_lines(self, tmp_path):
        f = tmp_path / "blanks.jsonl"
        f.write_text("\n\n\n")
        assert _load_from_jsonl(f) is None

    def test_returns_none_for_invalid_json(self, tmp_path):
        f = tmp_path / "bad.jsonl"
        f.write_text("{not json}\n")
        assert _load_from_jsonl(f) is None

    def test_loads_last_entry(self, tmp_path):
        f = tmp_path / "good.jsonl"
        lines = [
            json.dumps({"task": "first", "status": "in_progress"}),
            json.dumps({"task": "last", "status": "done", "timestamp": "2026-01-01"}),
        ]
        f.write_text("\n".join(lines))
        result = _load_from_jsonl(f)
        assert result is not None
        assert result.task == "last"
        assert result.status == "done"
        assert result.source == "jsonl"

    def test_loads_search_hints_with_files_fallback(self, tmp_path):
        f = tmp_path / "hints.jsonl"
        entry = {
            "task": "t1",
            "search_hints": {
                "files": ["a.py"],  # "files" key instead of "file_paths"
                "directories": ["src/"],
                "grep_patterns": ["TODO"],
                "symbols": ["MyClass"],
            },
        }
        f.write_text(json.dumps(entry))
        result = _load_from_jsonl(f)
        assert result is not None
        assert result.search_hints.file_paths == ["a.py"]
        assert result.search_hints.directories == ["src/"]

    def test_uses_pending_as_next_steps_fallback(self, tmp_path):
        f = tmp_path / "pending.jsonl"
        entry = {"task": "t1", "pending": ["step1", "step2"]}
        f.write_text(json.dumps(entry))
        result = _load_from_jsonl(f)
        assert result is not None
        assert result.next_steps == ["step1", "step2"]


# ── load_plan_state ─────────────────────────────────────────────────────────


class TestLoadPlanState:
    def test_returns_none_source_when_no_files(self, tmp_path):
        state = load_plan_state(
            md_path=tmp_path / "nope.md",
            jsonl_path=tmp_path / "nope.jsonl",
        )
        assert state.source == "none"
        assert state.found() is False

    def test_prefers_md_by_default(self, tmp_path):
        md = tmp_path / "plan.md"
        md.write_text("raw md content")
        jsonl = tmp_path / "plan.jsonl"
        jsonl.write_text(json.dumps({"task": "from jsonl"}))
        state = load_plan_state(md_path=md, jsonl_path=jsonl, prefer="md")
        assert state.source == "markdown"

    def test_prefers_jsonl_when_requested(self, tmp_path):
        md = tmp_path / "plan.md"
        md.write_text("raw md content")
        jsonl = tmp_path / "plan.jsonl"
        jsonl.write_text(json.dumps({"task": "from jsonl"}))
        state = load_plan_state(md_path=md, jsonl_path=jsonl, prefer="jsonl")
        assert state.source == "jsonl"

    def test_falls_back_to_other_source(self, tmp_path):
        jsonl = tmp_path / "plan.jsonl"
        jsonl.write_text(json.dumps({"task": "from jsonl"}))
        state = load_plan_state(
            md_path=tmp_path / "nope.md",
            jsonl_path=jsonl,
            prefer="md",
        )
        assert state.source == "jsonl"

    def test_jsonl_prefer_falls_back_to_md(self, tmp_path):
        md = tmp_path / "plan.md"
        md.write_text("raw md content")
        state = load_plan_state(
            md_path=md,
            jsonl_path=tmp_path / "nope.jsonl",
            prefer="jsonl",
        )
        assert state.source == "markdown"


# ── format_resume_context ────────────────────────────────────────────────────


class TestFormatResumeContext:
    def test_no_state_found(self):
        s = PlanState()
        text = format_resume_context(s)
        assert "no plan state found" in text

    def test_raw_passthrough(self):
        s = PlanState(source="markdown", _raw="RAW CONTENT HERE")
        assert format_resume_context(s) == "RAW CONTENT HERE"

    def test_structured_state_has_task_and_status(self):
        s = PlanState(
            task="Build auth", status="in_progress",
            session_id="s-1", timestamp="2026-01-01",
            source="jsonl",
        )
        text = format_resume_context(s)
        assert "Build auth" in text
        assert "IN_PROGRESS" in text
        assert "s-1" in text

    def test_sections_rendered(self):
        s = PlanState(
            task="t", source="jsonl",
            accomplished=["did A"],
            in_progress=["doing B"],
            next_steps=["do C"],
            open_questions=["why?"],
            artifacts=["art.md"],
        )
        text = format_resume_context(s)
        assert "Accomplished" in text
        assert "did A" in text
        assert "In Progress" in text
        assert "Next Steps" in text
        assert "Open Questions" in text
        assert "Artifacts" in text

    def test_search_hints_rendered(self):
        s = PlanState(
            task="t", source="jsonl",
            search_hints=SearchHints(
                file_paths=["a.py"],
                directories=["src/"],
                grep_patterns=["TODO"],
                symbols=["MyClass"],
            ),
        )
        text = format_resume_context(s)
        assert "Search Hints" in text
        assert "a.py" in text
        assert "src/" in text
        assert "TODO" in text
        assert "MyClass" in text

    def test_notes_rendered(self):
        s = PlanState(task="t", source="jsonl", notes="Important note")
        text = format_resume_context(s)
        assert "Notes" in text
        assert "Important note" in text


# ── format_hints_only ────────────────────────────────────────────────────────


class TestFormatHintsOnly:
    def test_no_state_found(self):
        s = PlanState()
        assert "no plan state found" in format_hints_only(s)

    def test_raw_passthrough(self):
        s = PlanState(source="markdown", _raw="RAW")
        assert format_hints_only(s) == "RAW"

    def test_empty_hints(self):
        s = PlanState(source="jsonl")
        assert "no search hints" in format_hints_only(s)

    def test_all_hint_categories(self):
        s = PlanState(
            source="jsonl",
            search_hints=SearchHints(
                file_paths=["f.py"],
                directories=["d/"],
                grep_patterns=["pat"],
                symbols=["sym"],
            ),
        )
        text = format_hints_only(s)
        assert "Key Files" in text
        assert "f.py" in text
        assert "Key Directories" in text
        assert "d/" in text
        assert "Grep Patterns" in text
        assert "pat" in text
        assert "Key Symbols" in text
        assert "sym" in text


# ── build_resume_prompt ──────────────────────────────────────────────────────


class TestBuildResumePrompt:
    def test_empty_when_no_state(self):
        assert build_resume_prompt(PlanState()) == ""

    def test_contains_preamble_when_state_found(self):
        s = PlanState(task="Build auth", source="jsonl", timestamp="2026-01-01")
        prompt = build_resume_prompt(s)
        assert "RESUMING FROM SAVED PLAN STATE" in prompt
        assert "Build auth" in prompt
        assert "2026-01-01" in prompt
        assert "CONTEXT REBUILD INSTRUCTIONS" in prompt

    def test_uses_unknown_defaults(self):
        s = PlanState(source="jsonl")  # no task or timestamp
        prompt = build_resume_prompt(s)
        assert "(unknown task)" in prompt
        assert "(unknown)" in prompt


# ── resume_agent_options ─────────────────────────────────────────────────────


class TestResumeAgentOptions:
    def test_no_state_returns_unchanged(self, tmp_path):
        opts = SimpleNamespace(system_prompt="original")
        result_opts, state = resume_agent_options(
            opts,
            md_path=tmp_path / "nope.md",
            jsonl_path=tmp_path / "nope.jsonl",
        )
        assert result_opts.system_prompt == "original"
        assert state.found() is False

    def test_state_injected_into_system_prompt(self, tmp_path):
        jsonl = tmp_path / "plan.jsonl"
        jsonl.write_text(json.dumps({"task": "auth", "status": "in_progress"}))
        opts = SimpleNamespace(system_prompt="base prompt")
        result_opts, state = resume_agent_options(
            opts,
            jsonl_path=jsonl,
            md_path=tmp_path / "nope.md",
        )
        assert "RESUMING FROM SAVED PLAN STATE" in result_opts.system_prompt
        assert "base prompt" in result_opts.system_prompt
        assert state.found() is True

    def test_uses_provided_state(self):
        s = PlanState(task="t", source="jsonl")
        opts = SimpleNamespace(system_prompt="")
        result_opts, state = resume_agent_options(opts, state=s)
        assert "RESUMING" in result_opts.system_prompt
        assert state is s

    def test_no_existing_system_prompt(self, tmp_path):
        jsonl = tmp_path / "plan.jsonl"
        jsonl.write_text(json.dumps({"task": "t"}))
        opts = SimpleNamespace()  # no system_prompt attribute
        result_opts, state = resume_agent_options(
            opts,
            jsonl_path=jsonl,
            md_path=tmp_path / "nope.md",
        )
        assert "RESUMING" in result_opts.system_prompt


# ── CLI main() ───────────────────────────────────────────────────────────────


class TestCLI:
    def test_no_state_exits_1(self, tmp_path):
        with pytest.raises(SystemExit) as exc_info:
            main([
                "--md-path", str(tmp_path / "nope.md"),
                "--jsonl-path", str(tmp_path / "nope.jsonl"),
            ])
        assert exc_info.value.code == 1

    def test_json_output(self, tmp_path, capsys):
        jsonl = tmp_path / "plan.jsonl"
        jsonl.write_text(json.dumps({"task": "t1", "status": "in_progress"}))
        main([
            "--md-path", str(tmp_path / "nope.md"),
            "--jsonl-path", str(jsonl),
            "--json",
        ])
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["task"] == "t1"

    def test_hints_output(self, tmp_path, capsys):
        jsonl = tmp_path / "plan.jsonl"
        entry = {
            "task": "t1",
            "search_hints": {"file_paths": ["a.py"]},
        }
        jsonl.write_text(json.dumps(entry))
        main([
            "--md-path", str(tmp_path / "nope.md"),
            "--jsonl-path", str(jsonl),
            "--hints",
        ])
        out = capsys.readouterr().out
        assert "a.py" in out

    def test_default_context_output(self, tmp_path, capsys):
        jsonl = tmp_path / "plan.jsonl"
        jsonl.write_text(json.dumps({"task": "t1"}))
        main([
            "--md-path", str(tmp_path / "nope.md"),
            "--jsonl-path", str(jsonl),
        ])
        out = capsys.readouterr().out
        assert "PLAN STATE" in out

    def test_prefer_jsonl_flag(self, tmp_path, capsys):
        jsonl = tmp_path / "plan.jsonl"
        jsonl.write_text(json.dumps({"task": "from-jsonl"}))
        main([
            "--md-path", str(tmp_path / "nope.md"),
            "--jsonl-path", str(jsonl),
            "--prefer", "jsonl",
            "--json",
        ])
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["source"] == "jsonl"
