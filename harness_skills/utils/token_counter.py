"""Token budget estimation for AGENTS.md and other generated artifacts.

Uses a word-based heuristic (~1.3 tokens per word) which is reasonably
accurate for English technical prose without requiring a tokenizer library.

Usage::

    from harness_skills.utils.token_counter import estimate_tokens, enforce_budget

    tokens = estimate_tokens("Hello world, this is a test.")
    text, was_truncated = enforce_budget(long_text, max_tokens=500)
"""

from __future__ import annotations

# Average tokens per word for English technical text (GPT/Claude tokenizers).
# Code-heavy text tends toward ~1.5; prose toward ~1.2. We use 1.3 as middle ground.
_TOKENS_PER_WORD = 1.3


def estimate_tokens(text: str) -> int:
    """Estimate the token count for a text string.

    Returns an integer estimate. Never returns less than 0.
    """
    if not text:
        return 0
    words = text.split()
    return max(1, int(len(words) * _TOKENS_PER_WORD))


def enforce_budget(text: str, max_tokens: int) -> tuple[str, bool]:
    """Truncate text to fit within a token budget.

    Returns ``(text, was_truncated)``. If the text fits, it's returned unchanged.
    If truncated, a ``\\n\\n[... truncated to ~{max_tokens} tokens]`` marker is appended.
    """
    current = estimate_tokens(text)
    if current <= max_tokens:
        return text, False

    words = text.split()
    target_words = int(max_tokens / _TOKENS_PER_WORD)
    truncated = " ".join(words[:target_words])
    truncated += f"\n\n[... truncated to ~{max_tokens} tokens]"
    return truncated, True
