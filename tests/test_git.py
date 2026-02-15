"""Tests for worktree_mux.git — worktree discovery and name resolution."""

from pathlib import Path

import pytest

from worktree_mux.git import (
    AmbiguousWorktreeError,
    Divergence,
    WorktreeInfo,
    WorktreeNotFoundError,
    check_leaf_collision,
    resolve_worktree,
)


def _wt(path: str, branch: str = "main") -> WorktreeInfo:
    """Create a WorktreeInfo for testing."""
    return WorktreeInfo(path=Path(path), branch=branch, commit="abc123")


# ---------------------------------------------------------------------------
# Divergence
# ---------------------------------------------------------------------------


class TestDivergenceDisplay:
    def test_even(self) -> None:
        assert Divergence(ahead=0, behind=0).display() == "even"

    def test_ahead_only(self) -> None:
        assert Divergence(ahead=3, behind=0).display() == "↑3"

    def test_behind_only(self) -> None:
        assert Divergence(ahead=0, behind=2).display() == "↓2"

    def test_diverged(self) -> None:
        assert Divergence(ahead=3, behind=2).display() == "↑3 ↓2"


# ---------------------------------------------------------------------------
# WorktreeInfo properties
# ---------------------------------------------------------------------------


class TestWorktreeInfo:
    def test_name_extracts_relative_path(self) -> None:
        wt = _wt("/repo/.worktrees/feature/auth")
        assert wt.name == "feature/auth"

    def test_name_nested(self) -> None:
        wt = _wt("/repo/.worktrees/fix/parser-bug")
        assert wt.name == "fix/parser-bug"

    def test_name_flat(self) -> None:
        wt = _wt("/repo/.worktrees/refactor-models")
        assert wt.name == "refactor-models"

    def test_name_fallback_when_no_worktrees_dir(self) -> None:
        wt = _wt("/repo/some-other-path")
        assert wt.name == "some-other-path"

    def test_leaf(self) -> None:
        wt = _wt("/repo/.worktrees/feature/auth")
        assert wt.leaf == "auth"

    def test_leaf_flat(self) -> None:
        wt = _wt("/repo/.worktrees/refactor-models")
        assert wt.leaf == "refactor-models"


# ---------------------------------------------------------------------------
# Name resolution
# ---------------------------------------------------------------------------


class TestResolveWorktree:
    """Test name resolution: exact → leaf → substring → error.

    Resolution is designed for quick, fuzzy access. Users type the
    shortest unambiguous identifier and worktree-mux finds the match.
    """

    @pytest.fixture()
    def worktrees(self) -> list[WorktreeInfo]:
        return [
            _wt("/repo/.worktrees/feature/auth", "feature/auth"),
            _wt("/repo/.worktrees/fix/parser-bug", "fix/parser-bug"),
            _wt("/repo/.worktrees/refactor-models", "refactor-models"),
        ]

    def test_exact_path_match(self, worktrees: list[WorktreeInfo]) -> None:
        """Full relative path resolves unambiguously."""
        result = resolve_worktree("feature/auth", worktrees)
        assert result.name == "feature/auth"

    def test_leaf_match(self, worktrees: list[WorktreeInfo]) -> None:
        """Leaf name 'auth' uniquely identifies feature/auth."""
        result = resolve_worktree("auth", worktrees)
        assert result.name == "feature/auth"

    def test_substring_match(self, worktrees: list[WorktreeInfo]) -> None:
        """'parser' is a substring of only fix/parser-bug."""
        result = resolve_worktree("parser", worktrees)
        assert result.name == "fix/parser-bug"

    def test_ambiguous_substring_raises(self, worktrees: list[WorktreeInfo]) -> None:
        """'re' matches both 'feature/auth' and 'refactor-models'."""
        with pytest.raises(AmbiguousWorktreeError) as exc_info:
            resolve_worktree("re", worktrees)
        assert len(exc_info.value.matches) >= 2

    def test_no_match_raises(self, worktrees: list[WorktreeInfo]) -> None:
        with pytest.raises(WorktreeNotFoundError) as exc_info:
            resolve_worktree("nonexistent", worktrees)
        assert exc_info.value.query == "nonexistent"
        assert len(exc_info.value.available) == 3

    def test_ambiguous_leaf_raises(self) -> None:
        """Two worktrees with the same leaf must error."""
        worktrees = [
            _wt("/repo/.worktrees/feature/auth", "feature/auth"),
            _wt("/repo/.worktrees/fix/auth", "fix/auth"),
        ]
        with pytest.raises(AmbiguousWorktreeError) as exc_info:
            resolve_worktree("auth", worktrees)
        assert len(exc_info.value.matches) == 2

    def test_exact_path_overrides_ambiguous_leaf(self) -> None:
        """Exact path match bypasses leaf ambiguity."""
        worktrees = [
            _wt("/repo/.worktrees/feature/auth", "feature/auth"),
            _wt("/repo/.worktrees/fix/auth", "fix/auth"),
        ]
        result = resolve_worktree("feature/auth", worktrees)
        assert result.name == "feature/auth"


# ---------------------------------------------------------------------------
# Leaf collision detection
# ---------------------------------------------------------------------------


class TestCheckLeafCollision:
    def test_no_collision(self) -> None:
        worktrees = [
            _wt("/repo/.worktrees/feature/auth"),
            _wt("/repo/.worktrees/fix/parser"),
        ]
        result = check_leaf_collision(worktrees[0], worktrees)
        assert len(result) == 1

    def test_collision_detected(self) -> None:
        worktrees = [
            _wt("/repo/.worktrees/feature/auth"),
            _wt("/repo/.worktrees/fix/auth"),
        ]
        result = check_leaf_collision(worktrees[0], worktrees)
        assert len(result) == 2
