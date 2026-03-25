"""Tests for harness_skills.error_query_agent — tools, server, CLI."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from io import StringIO
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import pytest

# ---------------------------------------------------------------------------
# Mock claude_agent_sdk before importing the module under test
# ---------------------------------------------------------------------------

_mock_sdk = ModuleType("claude_agent_sdk")
_mock_sdk.AssistantMessage = type("AssistantMessage", (), {})
_mock_sdk.ClaudeAgentOptions = MagicMock
_mock_sdk.ClaudeSDKClient = MagicMock
_mock_sdk.ResultMessage = type("ResultMessage", (), {"result": None})
_mock_sdk.SystemMessage = type("SystemMessage", (), {})
_mock_sdk.TextBlock = type("TextBlock", (), {"text": ""})
_mock_sdk.create_sdk_mcp_server = MagicMock(return_value=MagicMock())


def _mock_tool_decorator(name, desc, params):
    """Replacement for @tool that just returns the function as-is."""
    def wrapper(fn):
        return fn
    return wrapper


_mock_sdk.tool = _mock_tool_decorator

sys.modules.setdefault("claude_agent_sdk", _mock_sdk)

from harness_skills.error_aggregation import (
    ErrorAggregationView,
    ErrorGroup,
    ErrorRecord,
    aggregate_errors,
)
from harness_skills.error_query_agent import (
    _async_main,
    _build_arg_parser,
    _make_get_error_domain_list,
    _make_query_recent_errors,
    build_error_tools,
    main,
    run_error_query,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NOW = datetime(2025, 11, 1, 12, 0, 0, tzinfo=timezone.utc)


def _make_records(n: int = 5) -> list[ErrorRecord]:
    records = []
    for i in range(n):
        records.append(
            ErrorRecord(
                timestamp=NOW - timedelta(minutes=i * 5),
                domain="gate_runner",
                error_type="TimeoutError",
                message=f"Timeout after 30s on task {i}",
                severity="error",
            )
        )
    return records


def _make_view(records: list[ErrorRecord] | None = None) -> ErrorAggregationView:
    recs = records or _make_records()
    return aggregate_errors(recs, window_minutes=120, now=NOW)


# ---------------------------------------------------------------------------
# Tool factories
# ---------------------------------------------------------------------------


class TestMakeQueryRecentErrors:
    def test_returns_callable(self):
        view = _make_view()
        tool_fn = _make_query_recent_errors(view)
        assert callable(tool_fn)

    @pytest.mark.anyio
    async def test_query_returns_json(self):
        view = _make_view()
        tool_fn = _make_query_recent_errors(view)
        result = await tool_fn({"limit": 5})
        assert "content" in result
        text = result["content"][0]["text"]
        parsed = json.loads(text)
        assert "total_events" in parsed
        assert "errors" in parsed
        assert parsed["domain_filter"] is None

    @pytest.mark.anyio
    async def test_query_with_domain_filter(self):
        view = _make_view()
        tool_fn = _make_query_recent_errors(view)
        result = await tool_fn({"domain": "gate_runner", "limit": 3})
        text = result["content"][0]["text"]
        parsed = json.loads(text)
        assert parsed["domain_filter"] == "gate_runner"

    @pytest.mark.anyio
    async def test_query_limit_clamped(self):
        view = _make_view()
        tool_fn = _make_query_recent_errors(view)
        # limit > 50 should be clamped to 50
        result = await tool_fn({"limit": 100})
        text = result["content"][0]["text"]
        parsed = json.loads(text)
        assert parsed["returned_groups"] <= 50

    @pytest.mark.anyio
    async def test_query_limit_min_1(self):
        view = _make_view()
        tool_fn = _make_query_recent_errors(view)
        result = await tool_fn({"limit": -5})
        text = result["content"][0]["text"]
        parsed = json.loads(text)
        assert parsed["returned_groups"] <= 1

    @pytest.mark.anyio
    async def test_empty_domain_treated_as_none(self):
        view = _make_view()
        tool_fn = _make_query_recent_errors(view)
        result = await tool_fn({"domain": "", "limit": 5})
        text = result["content"][0]["text"]
        parsed = json.loads(text)
        assert parsed["domain_filter"] is None


class TestMakeGetErrorDomainList:
    def test_returns_callable(self):
        view = _make_view()
        tool_fn = _make_get_error_domain_list(view)
        assert callable(tool_fn)

    @pytest.mark.anyio
    async def test_domain_list_returns_json(self):
        view = _make_view()
        tool_fn = _make_get_error_domain_list(view)
        result = await tool_fn({})
        text = result["content"][0]["text"]
        parsed = json.loads(text)
        assert "domain_count" in parsed
        assert "total_events" in parsed
        assert "domains" in parsed


# ---------------------------------------------------------------------------
# build_error_tools
# ---------------------------------------------------------------------------


class TestBuildErrorTools:
    def test_with_records(self):
        records = _make_records()
        server = build_error_tools(records=records, window_minutes=120)
        assert server is not None

    def test_with_view(self):
        view = _make_view()
        server = build_error_tools(view=view)
        assert server is not None

    def test_with_no_args(self):
        server = build_error_tools()
        assert server is not None

    def test_view_takes_priority(self):
        view = _make_view()
        records = _make_records(10)
        server = build_error_tools(records=records, view=view)
        assert server is not None


# ---------------------------------------------------------------------------
# run_error_query
# ---------------------------------------------------------------------------


class TestRunErrorQuery:
    @pytest.mark.anyio
    async def test_run_error_query_with_view(self):
        view = _make_view()

        mock_client_instance = AsyncMock()

        from harness_skills.error_query_agent import ResultMessage

        mock_msg = MagicMock(spec=ResultMessage)
        mock_msg.result = "Summary of errors"

        async def mock_receive():
            yield mock_msg

        mock_client_instance.query = AsyncMock()
        mock_client_instance.receive_response = mock_receive

        mock_client_cls = MagicMock()
        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client_ctx

        with patch("harness_skills.error_query_agent.ClaudeSDKClient", mock_client_cls), \
             patch("harness_skills.error_query_agent.build_error_tools") as mock_build:
            mock_build.return_value = MagicMock()
            result = await run_error_query(
                prompt="What are the top errors?",
                view=view,
                stream_to_stdout=False,
            )
        assert result == "Summary of errors"

    @pytest.mark.anyio
    async def test_run_error_query_with_assistant_message(self):
        view = _make_view()

        from harness_skills.error_query_agent import AssistantMessage, TextBlock

        mock_text_block = MagicMock(spec=TextBlock)
        mock_text_block.text = "Here is the analysis"

        mock_assistant_msg = MagicMock(spec=AssistantMessage)
        mock_assistant_msg.content = [mock_text_block]

        mock_client_instance = AsyncMock()

        async def mock_receive():
            yield mock_assistant_msg

        mock_client_instance.query = AsyncMock()
        mock_client_instance.receive_response = mock_receive

        mock_client_cls = MagicMock()
        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client_ctx

        with patch("harness_skills.error_query_agent.ClaudeSDKClient", mock_client_cls), \
             patch("harness_skills.error_query_agent.build_error_tools") as mock_build:
            mock_build.return_value = MagicMock()
            result = await run_error_query(
                prompt="Summarise errors",
                view=view,
                stream_to_stdout=False,
            )
        assert "Here is the analysis" in result

    @pytest.mark.anyio
    async def test_run_error_query_stream_to_stdout(self, capsys):
        view = _make_view()

        from harness_skills.error_query_agent import AssistantMessage, TextBlock

        mock_text_block = MagicMock(spec=TextBlock)
        mock_text_block.text = "Streamed output"

        mock_assistant_msg = MagicMock(spec=AssistantMessage)
        mock_assistant_msg.content = [mock_text_block]

        mock_client_instance = AsyncMock()

        async def mock_receive():
            yield mock_assistant_msg

        mock_client_instance.query = AsyncMock()
        mock_client_instance.receive_response = mock_receive

        mock_client_cls = MagicMock()
        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client_ctx

        with patch("harness_skills.error_query_agent.ClaudeSDKClient", mock_client_cls), \
             patch("harness_skills.error_query_agent.build_error_tools") as mock_build:
            mock_build.return_value = MagicMock()
            result = await run_error_query(
                prompt="Show errors",
                view=view,
                stream_to_stdout=True,
            )
        captured = capsys.readouterr()
        assert "Streamed output" in captured.out

    @pytest.mark.anyio
    async def test_run_error_query_uses_records_when_no_view(self):
        records = _make_records()

        mock_client_instance = AsyncMock()

        from harness_skills.error_query_agent import ResultMessage
        mock_msg = MagicMock(spec=ResultMessage)
        mock_msg.result = "Done"

        async def mock_receive():
            yield mock_msg

        mock_client_instance.query = AsyncMock()
        mock_client_instance.receive_response = mock_receive

        mock_client_cls = MagicMock()
        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client_ctx

        with patch("harness_skills.error_query_agent.ClaudeSDKClient", mock_client_cls), \
             patch("harness_skills.error_query_agent.build_error_tools") as mock_build:
            mock_build.return_value = MagicMock()
            result = await run_error_query(
                prompt="Top errors?",
                records=records,
                stream_to_stdout=False,
            )
        assert result == "Done"


# ---------------------------------------------------------------------------
# CLI argument parser
# ---------------------------------------------------------------------------


class TestBuildArgParser:
    def test_defaults(self):
        parser = _build_arg_parser()
        args = parser.parse_args([])
        assert args.log_file is None
        assert args.window == 60
        assert args.model == "claude-opus-4-6"
        assert args.max_turns == 6
        assert args.json_summary is False

    def test_custom_args(self):
        parser = _build_arg_parser()
        args = parser.parse_args([
            "--log-file", "/tmp/errors.ndjson",
            "--window", "120",
            "--prompt", "What is wrong?",
            "--model", "claude-sonnet-4-20250514",
            "--max-turns", "3",
            "--json-summary",
        ])
        assert args.log_file == "/tmp/errors.ndjson"
        assert args.window == 120
        assert args.prompt == "What is wrong?"
        assert args.model == "claude-sonnet-4-20250514"
        assert args.max_turns == 3
        assert args.json_summary is True


# ---------------------------------------------------------------------------
# _async_main
# ---------------------------------------------------------------------------


class TestAsyncMain:
    @pytest.mark.anyio
    async def test_json_summary_mode(self, tmp_path):
        log_file = tmp_path / "errors.ndjson"
        ts = NOW.isoformat()
        lines = [
            json.dumps({"timestamp": ts, "domain": "test", "error_type": "E", "message": "msg"}),
        ]
        log_file.write_text("\n".join(lines))

        with patch("harness_skills.error_query_agent.load_errors_from_log") as mock_load:
            mock_load.return_value = [
                ErrorRecord(timestamp=NOW, domain="test", error_type="E", message="msg"),
            ]
            # Capture stdout
            captured = StringIO()
            with patch("sys.stdout", captured):
                await _async_main([
                    "--log-file", str(log_file),
                    "--window", "120",
                    "--json-summary",
                ])
            output = captured.getvalue()
            parsed = json.loads(output)
            assert "window" in parsed

    @pytest.mark.anyio
    async def test_no_log_file_json_summary(self):
        with patch("harness_skills.error_query_agent.run_error_query", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = "result"
            captured = StringIO()
            with patch("sys.stdout", captured):
                await _async_main(["--json-summary"])
            # With --json-summary, run_error_query should NOT be called
            mock_run.assert_not_called()
            output = captured.getvalue()
            parsed = json.loads(output)
            assert "window" in parsed

    @pytest.mark.anyio
    async def test_runs_agent_query(self):
        with patch("harness_skills.error_query_agent.run_error_query", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = "analysis result"
            await _async_main(["--prompt", "Show me errors"])
            mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# main (sync wrapper)
# ---------------------------------------------------------------------------


class TestMain:
    def test_main_delegates_to_anyio(self):
        with patch("harness_skills.error_query_agent.anyio.run") as mock_anyio_run:
            main(["--json-summary"])
            mock_anyio_run.assert_called_once()
            call_args = mock_anyio_run.call_args
            assert call_args[0][1] == ["--json-summary"]
