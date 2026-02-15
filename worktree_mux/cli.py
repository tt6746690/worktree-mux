"""worktree-mux CLI — tmux-based viewer for git worktrees.

worktree-mux gives you quick terminal access to your git worktrees through
dedicated tmux windows, organized in a per-repo tmux session.

Intended workflow:
  1. Create worktrees with git (or let agents do it)
  2. ``worktree-mux open <name>`` to jump into any worktree
  3. Use tmux ``prefix + L`` to toggle back to your main session
  4. ``worktree-mux dash`` for a live overview of all worktrees

worktree-mux is a VIEWER — it does not create, remove, or modify worktrees.
It creates tmux windows that point to existing worktrees, and cleans
up orphaned windows automatically.
"""

import sys
from pathlib import Path

import click

from worktree_mux import __version__
from worktree_mux.git import (
    AmbiguousWorktreeError,
    GitError,
    WorktreeInfo,
    WorktreeNotFoundError,
    check_leaf_collision,
    get_repo_root,
    list_worktrees,
    resolve_worktree,
)
from worktree_mux.tmux import (
    TmuxError,
    create_session,
    create_window,
    kill_window,
    list_windows,
    require_tmux,
    session_exists,
    switch_to_window,
    window_exists,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_context() -> tuple[Path, str, list[WorktreeInfo]]:
    """Get repo root, tmux session name, and worktree list."""
    try:
        repo_root = get_repo_root()
    except GitError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    session_name = repo_root.name
    worktrees = list_worktrees(repo_root)
    return repo_root, session_name, worktrees


def _sync_orphaned_windows(session_name: str, worktrees: list[WorktreeInfo]) -> None:
    """Close tmux windows whose worktrees no longer exist."""
    if not session_exists(session_name):
        return

    open_windows = list_windows(session_name)
    worktree_leaves = {wt.leaf for wt in worktrees}
    reserved = {"dash"}

    for window_name in open_windows:
        if window_name in reserved:
            continue
        if window_name not in worktree_leaves:
            click.echo(f"  Cleaned up orphaned window: {window_name}", err=True)
            kill_window(session_name, window_name)


def _handle_resolve_error(e: AmbiguousWorktreeError | WorktreeNotFoundError) -> None:
    """Print a user-friendly error for worktree resolution failures."""
    if isinstance(e, AmbiguousWorktreeError):
        click.echo(f"Ambiguous name '{e.query}' matches multiple worktrees:", err=True)
        for m in e.matches:
            click.echo(f"  {m.name}", err=True)
        click.echo("Be more specific (e.g., use the full path).", err=True)
    else:
        click.echo(f"No worktree matching '{e.query}'.", err=True)
        if e.available:
            click.echo("Available worktrees:", err=True)
            for a in e.available:
                click.echo(f"  {a.name}", err=True)
    sys.exit(1)


def _worktree_name_completion(
    ctx: click.Context,
    param: click.Parameter,
    incomplete: str,
) -> list[str]:
    """Provide tab completion for worktree names."""
    try:
        repo_root = get_repo_root()
    except GitError:
        return []
    worktrees = list_worktrees(repo_root)
    return [wt.leaf for wt in worktrees if incomplete in wt.leaf]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

HELP_TEXT = """\
A tmux-based viewer for git worktrees.

worktree-mux gives you quick terminal access to your git worktrees through
dedicated tmux windows, organized in a per-repo tmux session.

\b
Intended workflow:
  1. Create worktrees with git (or let agents do it)
  2. `worktree-mux open <name>` to jump into any worktree
  3. Use tmux `prefix + L` to toggle back to your main session
  4. `worktree-mux dash` for a live overview of all worktrees

\b
worktree-mux is a VIEWER — it does not create, remove, or modify worktrees.
It creates tmux windows pointing to existing worktrees, and cleans up
orphaned windows automatically when worktrees are removed.

\b
Install shell completions (add to ~/.zshrc):
  eval "$(_WORKTREE_MUX_COMPLETE=zsh_source worktree-mux)"

\b
Tip: Create a short alias (add to ~/.zshrc):
  alias wm='worktree-mux'
"""


@click.group(help=HELP_TEXT, invoke_without_command=True)
@click.version_option(version=__version__, prog_name="worktree-mux")
@click.pass_context
def main(ctx: click.Context) -> None:
    """worktree-mux — a tmux-based viewer for git worktrees."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@main.command("list")
def list_cmd() -> None:
    """List worktrees and their tmux/git status.

    \b
    Shows all worktrees under .worktrees/ and whether each has
    an open tmux window. Works both inside and outside tmux.

    \b
    Legend:
      ● = tmux window open
      ○ = no tmux window
    """
    repo_root, session_name, worktrees = _get_context()
    _sync_orphaned_windows(session_name, worktrees)

    open_windows = set(list_windows(session_name))

    if not worktrees:
        click.echo("No worktrees found under .worktrees/")
        click.echo("Create one with: git worktree add .worktrees/<name> -b <branch>")
        return

    click.echo(f"Worktrees in {repo_root.name}:\n")
    for wt in worktrees:
        marker = "●" if wt.leaf in open_windows else "○"
        click.echo(f"  {marker} {wt.name:<30} {wt.path}")

    open_count = sum(1 for wt in worktrees if wt.leaf in open_windows)
    click.echo()
    click.echo("● = tmux window open    ○ = no tmux window")
    click.echo(f"Session: {session_name} ({len(worktrees)} worktrees, {open_count} open)")


@main.command("open")
@click.argument("name", shell_complete=_worktree_name_completion)
def open_cmd(name: str) -> None:
    """Open a tmux window for a worktree and switch to it.

    \b
    NAME is resolved using fuzzy matching:
      1. Exact path match (e.g., 'feature/auth')
      2. Leaf name match (e.g., 'auth')
      3. Substring match (e.g., 'au')

    \b
    If the repo's tmux session doesn't exist, it is created.
    If a window already exists, worktree-mux switches to it (idempotent).

    \b
    To return to your previous session: tmux `prefix + L`
    """
    try:
        require_tmux()
    except TmuxError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    repo_root, session_name, worktrees = _get_context()
    _sync_orphaned_windows(session_name, worktrees)

    if not worktrees:
        click.echo("No worktrees found under .worktrees/", err=True)
        sys.exit(1)

    try:
        wt = resolve_worktree(name, worktrees)
    except (AmbiguousWorktreeError, WorktreeNotFoundError) as e:
        _handle_resolve_error(e)
        return  # unreachable, but keeps mypy happy

    # Check for leaf name collision — worktree-mux uses leaf names for tmux windows,
    # so two worktrees with the same leaf would conflict.
    collisions = check_leaf_collision(wt, worktrees)
    if len(collisions) > 1:
        click.echo(f"Error: Multiple worktrees share the leaf name '{wt.leaf}':", err=True)
        for c in collisions:
            click.echo(f"  {c.name}", err=True)
        click.echo("Rename one worktree directory to make leaf names unique.", err=True)
        sys.exit(1)

    window_name = wt.leaf

    if not session_exists(session_name):
        create_session(session_name, window_name, str(wt.path))
    elif not window_exists(session_name, window_name):
        create_window(session_name, window_name, str(wt.path))

    click.echo(f"→ {wt.name} (session: {session_name})")
    switch_to_window(session_name, window_name)


@main.command("close")
@click.argument("name", shell_complete=_worktree_name_completion)
def close_cmd(name: str) -> None:
    """Close the tmux window for a worktree.

    \b
    Tip: You usually don't need this. worktree-mux automatically cleans
    up orphaned windows (whose worktrees were removed) whenever
    any worktree-mux command runs.

    \b
    Use `close` to manually dismiss a worktree window you're done
    with. You can also close windows directly in tmux:
      - Type `exit` in the shell
      - Use `prefix + &`
    """
    repo_root, session_name, worktrees = _get_context()
    _sync_orphaned_windows(session_name, worktrees)

    try:
        wt = resolve_worktree(name, worktrees)
    except (AmbiguousWorktreeError, WorktreeNotFoundError) as e:
        _handle_resolve_error(e)
        return  # unreachable

    window_name = wt.leaf

    if not window_exists(session_name, window_name):
        click.echo(f"No tmux window open for {wt.name}.")
        return

    kill_window(session_name, window_name)
    click.echo(f"Closed window for {wt.name}.")


@main.command("dash")
def dash_cmd() -> None:
    """Show a live-updating dashboard of all worktrees.

    \b
    Displays a table with:
      Branch name         — git branch the worktree is on
      tmux status         — ● open, ○ closed
      Modified files      — count of uncommitted changes
      Divergence          — commits ↑ahead / ↓behind vs default branch
      Last commit         — relative time since last commit

    \b
    Refreshes every 5 seconds. Press Ctrl+C to exit.

    \b
    Tip: Run this in a dedicated tmux pane to keep it visible:
      worktree-mux open <worktree>    # get into the repo session
      prefix + "                      # split pane horizontally
      worktree-mux dash               # dashboard in the new pane
    """
    repo_root, session_name, worktrees = _get_context()
    _sync_orphaned_windows(session_name, worktrees)

    from worktree_mux.dashboard import run_dashboard

    run_dashboard(repo_root, session_name)
