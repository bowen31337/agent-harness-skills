"""Tests for harness_skills.cli.context (``harness context``).

Uses Click's ``CliRunner`` for isolated, subprocess-free invocations.

Coverage goals:
    - Pydantic model: ContextManifest / ContextManifestFile / SearchPattern
    - Keyword tokenisation: _tokenize_domain
    - Pattern generation: _generate_patterns
    - Exclusion rules: _should_exclude
    - CLI: exit code 0 on files found, exit code 1 on no files
    - CLI: --format json emits valid JSON with the expected schema shape
    - CLI: --format human also emits trailing JSON block
    - CLI: --max-files caps the file list
    - CLI: exit code 2 on internal error
    - State service helpers: _fetch_plan / _extract_keywords_from_plan / _extract_seed_files
    - Budget advisory path exercised at unit level
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from harness_skills.cli.context import (
    _build_rationale,
    _extract_keywords_from_plan,
    _extract_seed_files,
    _fetch_plan,
    _filter_and_rank,
    _generate_patterns,
    _should_exclude,
    _tokenize_domain,
    context_cmd,
)
from harness_skills.models.context import (
    ContextManifest,
    ContextManifestFile,
    ContextStats,
    SearchPattern,
    SkipEntry,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def populated_manifest() -> ContextManifest:
    """A ContextManifest with two files and three patterns."""
    return ContextManifest(
        command="harness context",
        status="passed",
        input="auth",
        keywords=["auth", "jwt"],
        files=[
            ContextManifestFile(
                path="src/auth/middleware.py",
                score=120,
                estimated_lines=84,
                sources=["state_service", "git_log"],
                rationale="listed in plan tasks; 2 matching commit(s)",
            ),
            ContextManifestFile(
                path="src/models/user.py",
                score=55,
                estimated_lines=210,
                sources=["git_log", "symbol_grep"],
                rationale="5 matching commit(s); keyword match in source",
            ),
        ],
        patterns=[
            SearchPattern(
                label="define:auth",
                pattern=r"(?:class|def|function|fn|type|interface|struct)\s+\w*auth\w*",
                flags="-i",
                rationale="Symbol definitions matching 'auth'",
            ),
        ],
        skip_list=[
            SkipEntry(path="migrations/0042_add_auth_table.py", reason="generated migration file"),
        ],
        stats=ContextStats(
            total_candidate_files=34,
            returned_files=2,
            total_estimated_lines=294,
            state_service_used=True,
        ),
    )


# ---------------------------------------------------------------------------
# ContextManifest model validation
# ---------------------------------------------------------------------------


class TestContextManifestModel:
    def test_default_command_field(self):
        m = ContextManifest(command="harness context", status="passed", input="auth")
        assert m.command == "harness context"

    def test_files_default_empty(self):
        m = ContextManifest(command="harness context", status="passed", input="auth")
        assert m.files == []

    def test_patterns_default_empty(self):
        m = ContextManifest(command="harness context", status="passed", input="auth")
        assert m.patterns == []

    def test_stats_default_values(self):
        m = ContextManifest(command="harness context", status="passed", input="auth")
        assert m.stats.total_candidate_files == 0
        assert m.stats.state_service_used is False

    def test_model_dump_json_is_valid(self, populated_manifest):
        raw = populated_manifest.model_dump_json(indent=2)
        data = json.loads(raw)
        assert data["command"] == "harness context"
        assert data["input"] == "auth"
        assert isinstance(data["files"], list)
        assert len(data["files"]) == 2

    def test_file_score_non_negative(self):
        f = ContextManifestFile(path="foo.py", score=0)
        assert f.score == 0

    def test_search_pattern_defaults(self):
        p = SearchPattern(label="define:auth", pattern=r"\w+auth\w*")
        assert p.flags == "-i"
        assert p.rationale == ""

    def test_skip_entry_reason_optional(self):
        s = SkipEntry(path="some/file.py")
        assert s.reason == ""


# ---------------------------------------------------------------------------
# _tokenize_domain
# ---------------------------------------------------------------------------


class TestTokenizeDomain:
    def test_simple_single_word(self):
        assert _tokenize_domain("auth") == ["auth"]

    def test_multi_word_space(self):
        assert _tokenize_domain("user onboarding") == ["user", "onboarding"]

    def test_hyphen_separated(self):
        assert _tokenize_domain("user-auth") == ["user", "auth"]

    def test_underscore_separated(self):
        assert _tokenize_domain("auth_flow") == ["auth", "flow"]

    def test_camel_case(self):
        assert _tokenize_domain("userOnboarding") == ["user", "onboarding"]

    def test_drops_short_tokens(self):
        # "to" and "a" should be dropped (< 3 chars)
        result = _tokenize_domain("go to a store")
        assert "to" not in result
        assert "a" not in result
        assert "store" in result

    def test_plan_id_yields_prefix_keyword(self):
        # "PLAN" → "plan", "42" < 3 chars → dropped
        result = _tokenize_domain("PLAN-42")
        assert "plan" in result
        assert "42" not in result

    def test_all_lowercase(self):
        result = _tokenize_domain("AuthService")
        assert all(kw == kw.lower() for kw in result)

    def test_empty_string(self):
        assert _tokenize_domain("") == []

    def test_repeated_delimiters(self):
        result = _tokenize_domain("user--auth__flow")
        assert "user" in result
        assert "auth" in result
        assert "flow" in result


# ---------------------------------------------------------------------------
# _should_exclude
# ---------------------------------------------------------------------------


class TestShouldExclude:
    def test_git_dir_excluded(self):
        excluded, reason = _should_exclude(".git/config", [])
        assert excluded is True

    def test_node_modules_excluded(self):
        excluded, _ = _should_exclude("node_modules/lodash/index.js", [])
        assert excluded is True

    def test_pycache_excluded(self):
        excluded, _ = _should_exclude("harness_skills/__pycache__/foo.pyc", [])
        assert excluded is True

    def test_pyc_file_excluded(self):
        excluded, _ = _should_exclude("harness_skills/cli/context.pyc", [])
        assert excluded is True

    def test_dist_dir_excluded(self):
        excluded, _ = _should_exclude("app/dist/bundle.js", [])
        assert excluded is True

    def test_lock_file_excluded(self):
        excluded, reason = _should_exclude("package-lock.json", [])
        assert excluded is True
        assert "lockfile" in reason

    def test_generated_migration_excluded(self):
        excluded, reason = _should_exclude("migrations/0042_add_auth.py", [])
        assert excluded is True

    def test_min_js_excluded(self):
        excluded, _ = _should_exclude("static/jquery.min.js", [])
        assert excluded is True

    def test_normal_source_not_excluded(self):
        excluded, _ = _should_exclude("src/auth/middleware.py", [])
        assert excluded is False

    def test_extra_glob_pattern_excluded(self):
        excluded, reason = _should_exclude("src/generated/foo.py", ["src/generated/*"])
        assert excluded is True
        assert "user-excluded" in reason

    def test_extra_regex_pattern_excluded(self):
        excluded, _ = _should_exclude("src/legacy/old_file.py", [r"legacy/"])
        assert excluded is True


# ---------------------------------------------------------------------------
# _generate_patterns
# ---------------------------------------------------------------------------


class TestGeneratePatterns:
    def test_generates_three_patterns_per_keyword(self):
        patterns = _generate_patterns(["auth"])
        labels = {p.label for p in patterns}
        assert "define:auth" in labels
        assert "import:auth" in labels
        assert "route:auth" in labels

    def test_caps_at_max_patterns(self):
        # 6 keywords × 3 patterns each = 18, but cap is 15
        patterns = _generate_patterns(["auth", "jwt", "user", "login", "token", "session"])
        assert len(patterns) <= 15

    def test_no_duplicate_labels(self):
        patterns = _generate_patterns(["auth", "auth"])
        labels = [p.label for p in patterns]
        assert len(labels) == len(set(labels))

    def test_empty_keywords_returns_empty(self):
        assert _generate_patterns([]) == []

    def test_pattern_flags_default_case_insensitive(self):
        patterns = _generate_patterns(["auth"])
        for p in patterns:
            assert p.flags == "-i"

    def test_define_pattern_contains_keyword(self):
        patterns = _generate_patterns(["auth"])
        define_p = next(p for p in patterns if p.label == "define:auth")
        assert "auth" in define_p.pattern

    def test_import_pattern_contains_keyword(self):
        patterns = _generate_patterns(["jwt"])
        import_p = next(p for p in patterns if p.label == "import:jwt")
        assert "jwt" in import_p.pattern


# ---------------------------------------------------------------------------
# _filter_and_rank
# ---------------------------------------------------------------------------


class TestFilterAndRank:
    def test_ranks_by_score_descending(self, tmp_path):
        (tmp_path / "high.py").write_text("x", encoding="utf-8")
        (tmp_path / "low.py").write_text("x", encoding="utf-8")
        import os

        original = os.getcwd()
        os.chdir(tmp_path)
        try:
            scores = {"high.py": 100, "low.py": 10}
            ranked, _ = _filter_and_rank(scores, max_files=10, extra_excludes=[], include_glob=None)
            assert ranked[0] == "high.py"
            assert ranked[1] == "low.py"
        finally:
            os.chdir(original)

    def test_caps_at_max_files(self, tmp_path):
        import os

        original = os.getcwd()
        os.chdir(tmp_path)
        try:
            for i in range(5):
                (tmp_path / f"file{i}.py").write_text("x", encoding="utf-8")
            scores = {f"file{i}.py": i * 10 for i in range(5)}
            ranked, _ = _filter_and_rank(scores, max_files=3, extra_excludes=[], include_glob=None)
            assert len(ranked) == 3
        finally:
            os.chdir(original)

    def test_excludes_lockfiles(self, tmp_path):
        import os

        original = os.getcwd()
        os.chdir(tmp_path)
        try:
            (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
            (tmp_path / "src.py").write_text("x", encoding="utf-8")
            scores = {"package-lock.json": 50, "src.py": 10}
            ranked, skip_list = _filter_and_rank(
                scores, max_files=10, extra_excludes=[], include_glob=None
            )
            assert "package-lock.json" not in ranked
            assert any(e.path == "package-lock.json" for e in skip_list)
        finally:
            os.chdir(original)

    def test_nonexistent_files_omitted(self, tmp_path):
        import os

        original = os.getcwd()
        os.chdir(tmp_path)
        try:
            scores = {"ghost.py": 50}
            ranked, _ = _filter_and_rank(scores, max_files=10, extra_excludes=[], include_glob=None)
            assert ranked == []
        finally:
            os.chdir(original)


# ---------------------------------------------------------------------------
# State service helpers
# ---------------------------------------------------------------------------


class TestFetchPlan:
    def test_returns_none_on_connection_error(self):
        data, used = _fetch_plan("PLAN-99", "http://localhost:19999")
        assert data is None
        assert used is False

    def test_returns_data_on_200(self):
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"description": "auth service"}).encode()

        with patch("harness_skills.cli.context.urlopen", return_value=mock_resp):
            data, used = _fetch_plan("PLAN-42", "http://localhost:8888")

        assert used is True
        assert data["description"] == "auth service"


class TestExtractKeywordsFromPlan:
    def test_extracts_from_description(self):
        plan = {"description": "authentication flow", "tasks": []}
        kws = _extract_keywords_from_plan(plan)
        assert "authentication" in kws
        assert "flow" in kws

    def test_extracts_from_domain(self):
        plan = {"description": "x", "domain": "auth", "tasks": []}
        kws = _extract_keywords_from_plan(plan)
        assert "auth" in kws

    def test_extracts_from_task_descriptions(self):
        plan = {
            "description": "x",
            "tasks": [{"description": "implement jwt middleware"}],
        }
        kws = _extract_keywords_from_plan(plan)
        assert "implement" in kws or "jwt" in kws

    def test_deduplicates_keywords(self):
        plan = {
            "description": "auth authentication",
            "tasks": [{"description": "auth check"}],
        }
        kws = _extract_keywords_from_plan(plan)
        assert kws.count("auth") == 1

    def test_caps_at_10_keywords(self):
        plan = {
            "description": "one two three four five six seven eight nine ten eleven twelve",
            "tasks": [],
        }
        kws = _extract_keywords_from_plan(plan)
        assert len(kws) <= 10


class TestExtractSeedFiles:
    def test_collects_files_from_tasks(self):
        plan = {
            "tasks": [
                {"files_touched": ["src/auth.py", "tests/test_auth.py"]},
                {"files_touched": ["src/models.py"]},
            ]
        }
        files = _extract_seed_files(plan)
        assert "src/auth.py" in files
        assert "tests/test_auth.py" in files
        assert "src/models.py" in files

    def test_deduplicates_files(self):
        plan = {
            "tasks": [
                {"files_touched": ["src/auth.py"]},
                {"files_touched": ["src/auth.py"]},
            ]
        }
        files = _extract_seed_files(plan)
        assert files.count("src/auth.py") == 1

    def test_empty_tasks_returns_empty(self):
        assert _extract_seed_files({"tasks": []}) == []


# ---------------------------------------------------------------------------
# _build_rationale
# ---------------------------------------------------------------------------


class TestBuildRationale:
    def test_state_service_source(self):
        r = _build_rationale("f.py", ["state_service"], 100)
        assert "listed in plan tasks" in r

    def test_git_log_source_shows_commits(self):
        r = _build_rationale("f.py", ["git_log"], 30)
        assert "matching commit" in r

    def test_grep_source(self):
        r = _build_rationale("f.py", ["symbol_grep"], 10)
        assert "keyword match" in r

    def test_path_source(self):
        r = _build_rationale("f.py", ["path_name"], 2)
        assert "keyword in path name" in r

    def test_fallback_shows_score(self):
        r = _build_rationale("f.py", [], 7)
        assert "score=7" in r


# ---------------------------------------------------------------------------
# CLI — exit codes
# ---------------------------------------------------------------------------


class TestContextCmdExitCodes:
    def test_exit_1_when_no_files_found(self, runner):
        """A domain that matches nothing should exit with code 1."""
        with patch("harness_skills.cli.context._git_log_strategy", return_value={}), patch(
            "harness_skills.cli.context._grep_strategy", return_value={}
        ), patch("harness_skills.cli.context._path_strategy", return_value=[]):
            result = runner.invoke(context_cmd, ["zzznomatch_xyzzy123"])
        assert result.exit_code == 1

    def test_exit_0_when_files_found(self, runner, tmp_path):
        """A domain with at least one matching file should exit with code 0."""
        fake_file = tmp_path / "auth_middleware.py"
        fake_file.write_text("class AuthMiddleware: pass", encoding="utf-8")

        with runner.isolated_filesystem(temp_dir=tmp_path):
            (Path(".") / "auth_middleware.py").write_text(
                "class AuthMiddleware: pass", encoding="utf-8"
            )
            with patch(
                "harness_skills.cli.context._git_log_strategy", return_value={}
            ), patch("harness_skills.cli.context._grep_strategy", return_value={}), patch(
                "harness_skills.cli.context._path_strategy",
                return_value=["auth_middleware.py"],
            ):
                result = runner.invoke(context_cmd, ["auth"])
        assert result.exit_code == 0

    def test_exit_2_on_internal_error(self, runner):
        """An unexpected exception in _build_manifest should exit with code 2."""
        with patch(
            "harness_skills.cli.context._build_manifest",
            side_effect=RuntimeError("boom"),
        ):
            result = runner.invoke(context_cmd, ["auth"])
        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# CLI — --format json output shape
# ---------------------------------------------------------------------------


class TestContextCmdJsonOutput:
    def _invoke_json(self, runner, domain="auth"):
        with patch("harness_skills.cli.context._git_log_strategy", return_value={}), patch(
            "harness_skills.cli.context._grep_strategy", return_value={}
        ), patch("harness_skills.cli.context._path_strategy", return_value=[]):
            return runner.invoke(context_cmd, [domain, "--format", "json"])

    def test_output_is_parseable_json(self, runner):
        result = self._invoke_json(runner)
        data = json.loads(result.output)
        assert isinstance(data, dict)

    def test_output_has_command_field(self, runner):
        data = json.loads(self._invoke_json(runner).output)
        assert data["command"] == "harness context"

    def test_output_has_input_field(self, runner):
        data = json.loads(self._invoke_json(runner, domain="auth").output)
        assert data["input"] == "auth"

    def test_output_has_keywords_list(self, runner):
        data = json.loads(self._invoke_json(runner, domain="auth").output)
        assert isinstance(data["keywords"], list)
        assert "auth" in data["keywords"]

    def test_output_has_files_list(self, runner):
        data = json.loads(self._invoke_json(runner).output)
        assert isinstance(data["files"], list)

    def test_output_has_patterns_list(self, runner):
        data = json.loads(self._invoke_json(runner).output)
        assert isinstance(data["patterns"], list)

    def test_output_has_stats_block(self, runner):
        data = json.loads(self._invoke_json(runner).output)
        assert "stats" in data
        assert "returned_files" in data["stats"]

    def test_output_has_skip_list(self, runner):
        data = json.loads(self._invoke_json(runner).output)
        assert "skip_list" in data


# ---------------------------------------------------------------------------
# CLI — --format human emits trailing JSON
# ---------------------------------------------------------------------------


class TestContextCmdHumanOutput:
    def test_human_output_contains_json_block(self, runner):
        with patch("harness_skills.cli.context._git_log_strategy", return_value={}), patch(
            "harness_skills.cli.context._grep_strategy", return_value={}
        ), patch("harness_skills.cli.context._path_strategy", return_value=[]):
            result = runner.invoke(context_cmd, ["auth", "--format", "human"])

        # The human output ends with a JSON block — find the outermost { (first one)
        # rfind would land inside the patterns array; find gives us the manifest root.
        output = result.output
        start = output.find("{")
        assert start != -1, "No JSON object found in human output"
        data = json.loads(output[start:])
        assert data["command"] == "harness context"

    def test_human_output_contains_harness_context_header(self, runner):
        with patch("harness_skills.cli.context._git_log_strategy", return_value={}), patch(
            "harness_skills.cli.context._grep_strategy", return_value={}
        ), patch("harness_skills.cli.context._path_strategy", return_value=[]):
            result = runner.invoke(context_cmd, ["auth"])

        assert "Harness Context" in result.output


# ---------------------------------------------------------------------------
# CLI — --max-files flag
# ---------------------------------------------------------------------------


class TestContextCmdMaxFiles:
    def test_max_files_caps_file_list(self, runner, tmp_path):
        files = [f"file{i}.py" for i in range(10)]

        with runner.isolated_filesystem(temp_dir=tmp_path):
            for f in files:
                Path(f).write_text("x", encoding="utf-8")
            with patch(
                "harness_skills.cli.context._git_log_strategy", return_value={}
            ), patch("harness_skills.cli.context._grep_strategy", return_value={}), patch(
                "harness_skills.cli.context._path_strategy",
                return_value=files,
            ):
                result = runner.invoke(
                    context_cmd, ["auth", "--max-files", "3", "--format", "json"]
                )

        data = json.loads(result.output)
        assert len(data["files"]) <= 3


# ---------------------------------------------------------------------------
# CLI — plan ID input falls back gracefully without state service
# ---------------------------------------------------------------------------


class TestContextCmdPlanId:
    def test_plan_id_falls_back_to_keywords(self, runner):
        """PLAN-42 with no state service should still produce a valid manifest."""
        with patch(
            "harness_skills.cli.context._fetch_plan", return_value=(None, False)
        ), patch("harness_skills.cli.context._git_log_strategy", return_value={}), patch(
            "harness_skills.cli.context._grep_strategy", return_value={}
        ), patch(
            "harness_skills.cli.context._path_strategy", return_value=[]
        ):
            result = runner.invoke(context_cmd, ["PLAN-42", "--format", "json"])

        data = json.loads(result.output)
        assert data["input"] == "PLAN-42"
        assert data["stats"]["state_service_used"] is False

    def test_plan_id_uses_state_service_files(self, runner, tmp_path):
        """When the state service returns file data it should seed the manifest."""
        plan_data = {
            "description": "auth middleware",
            "tasks": [{"description": "add jwt check", "files_touched": ["src/auth.py"]}],
        }

        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path("src").mkdir()
            Path("src/auth.py").write_text("# auth", encoding="utf-8")

            with patch(
                "harness_skills.cli.context._fetch_plan",
                return_value=(plan_data, True),
            ), patch(
                "harness_skills.cli.context._git_log_strategy", return_value={}
            ), patch(
                "harness_skills.cli.context._grep_strategy", return_value={}
            ), patch(
                "harness_skills.cli.context._path_strategy", return_value=[]
            ):
                result = runner.invoke(
                    context_cmd, ["PLAN-42", "--format", "json"]
                )

        data = json.loads(result.output)
        paths = [f["path"] for f in data["files"]]
        assert "src/auth.py" in paths
        assert data["stats"]["state_service_used"] is True
