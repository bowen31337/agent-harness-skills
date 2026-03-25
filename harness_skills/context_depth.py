"""Context depth map for tiered AGENTS.md loading."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ContextTier(str, Enum):
    """Tier levels for context assembly."""

    L0 = "L0"  # Always loaded (root overview)
    L1 = "L1"  # Loaded on demand (domain docs)
    L2 = "L2"  # Search only (file-level)


class TieredFile(BaseModel):
    """A file assigned to a context tier."""

    file_path: str
    tier: ContextTier
    token_estimate: int = 0


class ContextDepthMap(BaseModel):
    """Maps files to context tiers based on token budgets."""

    files: list[TieredFile] = Field(default_factory=list)
    l0_budget: int = 500
    l1_budget: int = 1000

    def l0_files(self) -> list[TieredFile]:
        return [f for f in self.files if f.tier == ContextTier.L0]

    def l1_files(self) -> list[TieredFile]:
        return [f for f in self.files if f.tier == ContextTier.L1]

    def l2_files(self) -> list[TieredFile]:
        return [f for f in self.files if f.tier == ContextTier.L2]


def build_depth_map(
    file_tokens: list[tuple[str, int]],
    l0_budget: int = 500,
    l1_budget: int = 1000,
) -> ContextDepthMap:
    """Assign files to tiers based on token budgets.

    Args:
        file_tokens: List of (file_path, estimated_tokens) sorted by relevance/score.
        l0_budget: Max total tokens for L0 tier.
        l1_budget: Max total tokens for L1 tier.

    Returns:
        A ContextDepthMap with files assigned to L0, L1, or L2.
    """
    files: list[TieredFile] = []
    l0_used = 0
    l1_used = 0

    for path, tokens in file_tokens:
        if l0_used + tokens <= l0_budget:
            files.append(TieredFile(file_path=path, tier=ContextTier.L0, token_estimate=tokens))
            l0_used += tokens
        elif l1_used + tokens <= l1_budget:
            files.append(TieredFile(file_path=path, tier=ContextTier.L1, token_estimate=tokens))
            l1_used += tokens
        else:
            files.append(TieredFile(file_path=path, tier=ContextTier.L2, token_estimate=tokens))

    return ContextDepthMap(files=files, l0_budget=l0_budget, l1_budget=l1_budget)
