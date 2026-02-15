"""Worktree dashboard rendering for worktree-mux.

Provides both one-shot status (``print_status``) and a live-updating
dashboard (``run_dashboard``).  Both share ``render_table`` so the
output format stays consistent.
"""

import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import click

from worktree_mux.git import (
    WorktreeInfo,
    get_default_branch,
    get_divergence,
    get_last_commit_time,
    get_last_commit_timestamp,
    get_modified_count,
    list_worktrees,
)
from worktree_mux.tmux import list_windows

REFRESH_INTERVAL_SECONDS = 5


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _RowData:
    """Pre-computed data for a single dashboard table row."""

    indicator: str
    branch: str
    tmux: str
    modified: str
    divergence: str
    last_commit: str
    timestamp: int
    is_current: bool


def _get_current_worktree(worktrees: list[WorktreeInfo]) -> WorktreeInfo | None:
    """Detect which worktree the user is currently in, if any."""
    try:
        cwd = Path.cwd().resolve()
    except OSError:
        return None
    for wt in worktrees:
        try:
            cwd.relative_to(wt.path.resolve())
            return wt
        except ValueError:
            continue
    return None


def _build_rows(
    worktrees: list[WorktreeInfo],
    open_windows: set[str],
    default_branch: str,
    repo_root: Path,
    current_wt: WorktreeInfo | None,
) -> list[_RowData]:
    """Build row data for all worktrees, sorted by last commit (most recent first)."""
    rows: list[_RowData] = []
    for wt in worktrees:
        is_current = current_wt is not None and wt.path == current_wt.path
        tmux_marker = "●" if wt.leaf in open_windows else "○"
        mod_count = get_modified_count(wt.path)
        mod_str = "clean" if mod_count == 0 else f"{mod_count} file{'s' if mod_count != 1 else ''}"
        div = get_divergence(repo_root, wt.branch, default_branch)
        last = get_last_commit_time(wt.path)
        timestamp = get_last_commit_timestamp(wt.path)
        indicator = "▸" if is_current else " "
        rows.append(
            _RowData(
                indicator=indicator,
                branch=wt.name,
                tmux=tmux_marker,
                modified=mod_str,
                divergence=div.display(),
                last_commit=last,
                timestamp=timestamp,
                is_current=is_current,
            )
        )
    rows.sort(key=lambda r: r.timestamp, reverse=True)
    return rows


def _style_row(row: _RowData, widths: list[int]) -> str:
    """Format a data row with colors and proper column alignment."""
    # Indicator
    if row.indicator == "▸":
        indicator = click.style("▸", fg="cyan", bold=True)
    else:
        indicator = " "

    # Branch
    padded_branch = f"{row.branch:<{widths[0]}}"
    if row.is_current:
        branch_styled = click.style(padded_branch, fg="cyan", bold=True)
    else:
        branch_styled = padded_branch

    # tmux status
    padded_tmux = f"{row.tmux:^{widths[1]}}"
    if row.tmux == "●":
        tmux_styled = click.style(padded_tmux, fg="green")
    else:
        tmux_styled = click.style(padded_tmux, dim=True)

    # Modified files
    if row.modified == "clean":
        mod_styled = click.style(f"{row.modified:<{widths[2]}}", fg="green")
    else:
        mod_styled = click.style(f"{row.modified:<{widths[2]}}", fg="yellow")

    # Divergence — colour ↑ green, ↓ red
    if row.divergence == "even":
        div_styled = click.style(f"{row.divergence:<{widths[3]}}", dim=True)
    else:
        parts = row.divergence.split()
        colored_parts: list[str] = []
        for p in parts:
            if p.startswith("↑"):
                colored_parts.append(click.style(p, fg="green"))
            elif p.startswith("↓"):
                colored_parts.append(click.style(p, fg="red"))
            else:
                colored_parts.append(p)
        div_text = " ".join(colored_parts)
        padding = widths[3] - len(row.divergence)
        div_styled = div_text + " " * max(0, padding)

    # Last commit
    last_styled = click.style(f"{row.last_commit:<{widths[4]}}", dim=True)

    return (
        f"  {indicator} {branch_styled}  {tmux_styled}  {mod_styled}  {div_styled}  {last_styled}"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_table(repo_root: Path, session_name: str, *, live: bool = False) -> None:
    """Render the worktree dashboard table to stdout.

    Args:
        repo_root: Path to the git repository root.
        session_name: tmux session name (typically repo directory name).
        live: If True, shows refresh interval in header (for live dashboard).
    """
    worktrees = list_worktrees(repo_root)
    default_branch = get_default_branch(repo_root)
    current_wt = _get_current_worktree(worktrees)

    # Header
    repo_name = repo_root.name
    open_windows = set(list_windows(session_name))
    worktree_count = len(worktrees)
    open_count = sum(1 for wt in worktrees if wt.leaf in open_windows)
    summary = f"{worktree_count} worktree{'s' if worktree_count != 1 else ''}, {open_count} open"
    if live:
        header = (
            f"worktree-mux — {repo_name} ({summary}, refreshes every {REFRESH_INTERVAL_SECONDS}s)"
        )
    else:
        header = f"worktree-mux — {repo_name} ({summary})"
    click.echo(click.style(header, bold=True))

    term_width = shutil.get_terminal_size().columns
    click.echo(click.style("─" * min(len(header) + 2, term_width), dim=True))
    click.echo()

    if not worktrees:
        click.echo("  No worktrees found under .worktrees/")
        click.echo()
        click.echo("  Create one with: git worktree add .worktrees/<name> -b <branch>")
        return

    rows = _build_rows(worktrees, open_windows, default_branch, repo_root, current_wt)

    # Column headers
    headers = ("Branch", "tmux", "Modified", f"vs {default_branch}", "Last Commit")

    # Compute column widths (max of header width and widest data value)
    col_data: list[list[str]] = [
        [r.branch for r in rows],
        [r.tmux for r in rows],
        [r.modified for r in rows],
        [r.divergence for r in rows],
        [r.last_commit for r in rows],
    ]
    widths = [max(len(headers[i]), *(len(v) for v in col_data[i])) for i in range(len(headers))]

    # Header row
    hdr_parts = [
        f"{headers[i]:^{widths[i]}}" if i == 1 else f"{headers[i]:<{widths[i]}}"
        for i in range(len(headers))
    ]
    hdr_line = "    " + "  ".join(hdr_parts)
    sep_line = "    " + "  ".join("─" * w for w in widths)

    click.echo(click.style(hdr_line, bold=True))
    click.echo(click.style(sep_line, dim=True))

    for row in rows:
        click.echo(_style_row(row, widths))

    # Legend
    click.echo()
    has_current = any(r.is_current for r in rows)
    legend = "  ● = tmux window open    ○ = no tmux window"
    if has_current:
        legend += "    ▸ = current"
    click.echo(click.style(legend, dim=True))


def print_status(repo_root: Path, session_name: str) -> None:
    """Print a one-shot dashboard table."""
    render_table(repo_root, session_name, live=False)


def run_dashboard(repo_root: Path, session_name: str) -> None:
    """Run a live-updating dashboard until Ctrl+C."""
    try:
        while True:
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()
            render_table(repo_root, session_name, live=True)
            time.sleep(REFRESH_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()
