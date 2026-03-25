"""Tests for token counter utility."""

from __future__ import annotations

from harness_skills.utils.token_counter import enforce_budget, estimate_tokens


class TestEstimateTokens:

    def test_empty_string(self) -> None:
        assert estimate_tokens("") == 0

    def test_single_word(self) -> None:
        result = estimate_tokens("hello")
        assert result >= 1

    def test_longer_text(self) -> None:
        text = "The quick brown fox jumps over the lazy dog"
        result = estimate_tokens(text)
        # 9 words * ~1.3 ≈ 11-12
        assert 9 <= result <= 15

    def test_code_block(self) -> None:
        code = "def hello():\n    return 'world'\n"
        result = estimate_tokens(code)
        assert result > 0


class TestEnforceBudget:

    def test_within_budget(self) -> None:
        text = "Short text"
        result, truncated = enforce_budget(text, max_tokens=100)
        assert result == text
        assert truncated is False

    def test_over_budget(self) -> None:
        text = " ".join(["word"] * 200)  # ~260 tokens
        result, truncated = enforce_budget(text, max_tokens=50)
        assert truncated is True
        assert "truncated" in result
        assert len(result) < len(text)

    def test_exact_budget(self) -> None:
        # 10 words * 1.3 = 13 tokens
        text = " ".join(["hello"] * 10)
        result, truncated = enforce_budget(text, max_tokens=13)
        assert result == text
        assert truncated is False

    def test_zero_budget(self) -> None:
        text = "hello world"
        result, truncated = enforce_budget(text, max_tokens=0)
        assert truncated is True
