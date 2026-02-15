"""Git operations and worktree discovery for worktree-mux."""

import subprocess
from pathlib import Path

from pydantic import BaseModel, Field, computed_field


class GitError(Exception):
    """Raised when a git operation fails."""


class Divergence(BaseModel):
    """Commit divergence between a worktree branch and the default branch.

    Uses three-dot rev-list syntax which compares via the merge base,
    so it correctly handles diverged branches (both sides have unique commits).

    Display format:
        ↑3       — 3 commits ahead of default branch
        ↓2       — 2 commits behind default branch
        ↑3 ↓2    — diverged: 3 ahead, 2 behind
        even     — branch is at the same point as default
    """

    model_config = {"extra": "forbid"}

    ahead: int = Field(ge=0)
    behind: int = Field(ge=0)

    def display(self) -> str:
        """Compact display string."""
        if self.ahead == 0 and self.behind == 0:
            return "even"
        parts: list[str] = []
        if self.ahead > 0:
            parts.append(f"↑{self.ahead}")
        if self.behind > 0:
            parts.append(f"↓{self.behind}")
        return " ".join(parts)


class WorktreeInfo(BaseModel):
    """A git worktree located under .worktrees/."""

    model_config = {"extra": "forbid"}

    path: Path
    branch: str
    commit: str

    @computed_field  # type: ignore[prop-decorator]  # Pydantic computed field
    @property
    def name(self) -> str:
        """Relative path under .worktrees/ (e.g., 'feature/auth')."""
        parts = self.path.parts
        try:
            idx = parts.index(".worktrees")
            return "/".join(parts[idx + 1 :])
        except ValueError:
            return self.path.name

    @computed_field  # type: ignore[prop-decorator]  # Pydantic computed field
    @property
    def leaf(self) -> str:
        """Last path component (e.g., 'auth' from '.worktrees/feature/auth')."""
        return self.path.name


class AmbiguousWorktreeError(Exception):
    """Raised when a worktree query matches multiple worktrees."""

    def __init__(self, query: str, matches: list[WorktreeInfo]) -> None:
        self.query = query
        self.matches = matches
        names = ", ".join(m.name for m in matches)
        super().__init__(f"Ambiguous query '{query}' matches: {names}")


class WorktreeNotFoundError(Exception):
    """Raised when no worktree matches a query."""

    def __init__(self, query: str, available: list[WorktreeInfo]) -> None:
        self.query = query
        self.available = available
        super().__init__(f"No worktree matching '{query}'")


def get_repo_root() -> Path:
    """Get the root directory of the main git repository.

    Uses ``git rev-parse --git-common-dir`` so this works correctly
    when called from inside a worktree (always returns the main repo
    root, not the worktree root).

    Raises:
        GitError: If not inside a git repository.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GitError("Not inside a git repository.")
    git_common = Path(result.stdout.strip())
    if not git_common.is_absolute():
        git_common = Path.cwd() / git_common
    return git_common.resolve().parent


def get_default_branch(repo_root: Path) -> str:
    """Detect the default branch (main or master).

    Checks local refs for 'main' first, then 'master'.
    Falls back to 'main' if neither exists.
    """
    for branch in ("main", "master"):
        result = subprocess.run(
            ["git", "rev-parse", "--verify", f"refs/heads/{branch}"],
            capture_output=True,
            cwd=repo_root,
        )
        if result.returncode == 0:
            return branch
    return "main"


def list_worktrees(repo_root: Path) -> list[WorktreeInfo]:
    """List all worktrees under .worktrees/.

    Parses ``git worktree list --porcelain`` and returns only
    worktrees located under the repo's ``.worktrees/`` directory,
    excluding the main worktree.
    """
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    if result.returncode != 0:
        return []

    worktrees: list[WorktreeInfo] = []
    current: dict[str, str] = {}
    worktrees_dir = repo_root / ".worktrees"

    for line in result.stdout.split("\n"):
        if not line.strip():
            _maybe_add_worktree(current, repo_root, worktrees_dir, worktrees)
            current = {}
        elif line.startswith("worktree "):
            current["worktree"] = line[len("worktree ") :]
        elif line.startswith("HEAD "):
            current["HEAD"] = line[len("HEAD ") :]
        elif line.startswith("branch "):
            current["branch"] = line[len("branch ") :]

    # Handle final entry (output may not end with a blank line)
    _maybe_add_worktree(current, repo_root, worktrees_dir, worktrees)

    return worktrees


def _maybe_add_worktree(
    current: dict[str, str],
    repo_root: Path,
    worktrees_dir: Path,
    worktrees: list[WorktreeInfo],
) -> None:
    """Add a parsed worktree entry if it's under .worktrees/."""
    if "worktree" not in current:
        return
    wt_path = Path(current["worktree"])

    # Skip the main worktree
    if wt_path == repo_root:
        return

    # Only include worktrees under .worktrees/
    try:
        wt_path.relative_to(worktrees_dir)
    except ValueError:
        return

    branch = current.get("branch", "").replace("refs/heads/", "")
    commit = current.get("HEAD", "")
    worktrees.append(WorktreeInfo(path=wt_path, branch=branch, commit=commit))


def resolve_worktree(query: str, worktrees: list[WorktreeInfo]) -> WorktreeInfo:
    """Resolve a user query to a single worktree.

    Resolution order:
      1. Exact match on full relative path (e.g., 'feature/auth')
      2. Exact match on leaf name (e.g., 'auth')
      3. Substring match on relative path (e.g., 'au')
      4. Error on ambiguity or no match

    Raises:
        AmbiguousWorktreeError: If multiple worktrees match.
        WorktreeNotFoundError: If no worktree matches.
    """
    # 1. Exact path match
    for wt in worktrees:
        if wt.name == query:
            return wt

    # 2. Leaf name match
    leaf_matches = [wt for wt in worktrees if wt.leaf == query]
    if len(leaf_matches) == 1:
        return leaf_matches[0]
    if len(leaf_matches) > 1:
        raise AmbiguousWorktreeError(query, leaf_matches)

    # 3. Substring match
    sub_matches = [wt for wt in worktrees if query in wt.name]
    if len(sub_matches) == 1:
        return sub_matches[0]
    if len(sub_matches) > 1:
        raise AmbiguousWorktreeError(query, sub_matches)

    # 4. No match
    raise WorktreeNotFoundError(query, worktrees)


def check_leaf_collision(wt: WorktreeInfo, worktrees: list[WorktreeInfo]) -> list[WorktreeInfo]:
    """Check if other worktrees share the same leaf name.

    Returns all worktrees with the same leaf (including ``wt`` itself).
    A return list of length > 1 indicates a collision.
    """
    return [w for w in worktrees if w.leaf == wt.leaf]


def get_divergence(repo_root: Path, branch: str, default_branch: str) -> Divergence:
    """Get commit divergence between a branch and the default branch.

    Uses ``git rev-list --left-right --count default...branch`` which
    compares via the merge base. Left count = commits on default only
    (behind), right count = commits on branch only (ahead).
    """
    result = subprocess.run(
        ["git", "rev-list", "--left-right", "--count", f"{default_branch}...{branch}"],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    if result.returncode != 0:
        return Divergence(ahead=0, behind=0)

    parts = result.stdout.strip().split("\t")
    if len(parts) != 2:
        return Divergence(ahead=0, behind=0)

    behind, ahead = int(parts[0]), int(parts[1])
    return Divergence(ahead=ahead, behind=behind)


def get_modified_count(worktree_path: Path) -> int:
    """Count modified/untracked files in a worktree."""
    result = subprocess.run(
        ["git", "-C", str(worktree_path), "status", "--porcelain"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return 0
    return sum(1 for line in result.stdout.split("\n") if line.strip())


def get_last_commit_time(worktree_path: Path) -> str:
    """Get relative time since the last commit (e.g., '2 hours ago')."""
    result = subprocess.run(
        ["git", "-C", str(worktree_path), "log", "-1", "--format=%cr"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip()


def get_last_commit_timestamp(worktree_path: Path) -> int:
    """Get Unix timestamp of the last commit (for sorting)."""
    result = subprocess.run(
        ["git", "-C", str(worktree_path), "log", "-1", "--format=%ct"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return 0
    text = result.stdout.strip()
    return int(text) if text else 0
