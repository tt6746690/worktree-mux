"""Live-updating worktree dashboard for worktree-mux."""

import shutil
import sys
import time
from pathlib import Path

from worktree_mux.git import (
    get_default_branch,
    get_divergence,
    get_last_commit_time,
    get_modified_count,
    list_worktrees,
)
from worktree_mux.tmux import list_windows

REFRESH_INTERVAL_SECONDS = 5


def run_dashboard(repo_root: Path, session_name: str) -> None:
    """Run a live-updating dashboard until Ctrl+C.

    Clears the terminal and redraws the table on each refresh.
    On exit, clears the screen for a clean terminal.
    """
    try:
        while True:
            _render_frame(repo_root, session_name)
            time.sleep(REFRESH_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()


def _render_frame(repo_root: Path, session_name: str) -> None:
    """Render a single frame of the dashboard."""
    term_width = shutil.get_terminal_size().columns
    worktrees = list_worktrees(repo_root)
    default_branch = get_default_branch(repo_root)
    open_windows = set(list_windows(session_name))

    # Clear screen + cursor to top-left
    sys.stdout.write("\033[2J\033[H")

    repo_name = repo_root.name
    header = f" {repo_name} — worktree dashboard (refreshes every {REFRESH_INTERVAL_SECONDS}s)"
    print(header)
    print("─" * min(len(header) + 2, term_width))
    print()

    if not worktrees:
        print("  No worktrees found under .worktrees/")
        print()
        print("  Create one with: git worktree add .worktrees/<name> -b <branch>")
        sys.stdout.flush()
        return

    # Collect row data
    rows: list[tuple[str, str, str, str, str]] = []
    for wt in worktrees:
        tmux_status = "●" if wt.leaf in open_windows else "○"
        mod_count = get_modified_count(wt.path)
        mod_str = "clean" if mod_count == 0 else f"{mod_count} file{'s' if mod_count != 1 else ''}"
        div = get_divergence(repo_root, wt.branch, default_branch)
        last = get_last_commit_time(wt.path)
        rows.append((wt.name, tmux_status, mod_str, div.display(), last))

    # Column headers
    headers = ("Branch", "tmux", "Modified", f"vs {default_branch}", "Last Commit")

    # Compute column widths (ensure header width is minimum)
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]

    def fmt_row(cols: tuple[str, ...]) -> str:
        parts: list[str] = []
        for i in range(len(cols)):
            if i == 1:  # tmux column is centered
                parts.append(f"{cols[i]:^{widths[i]}}")
            else:
                parts.append(f"{cols[i]:<{widths[i]}}")
        return "  " + "  ".join(parts)

    print(fmt_row(headers))
    print(fmt_row(tuple("─" * w for w in widths)))
    for row in rows:
        print(fmt_row(row))

    print()
    print("  ● = tmux window open    ○ = no tmux window")
    sys.stdout.flush()
