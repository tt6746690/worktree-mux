"""tmux session and window management for worktree-mux."""

import os
import subprocess


class TmuxError(Exception):
    """Raised when a tmux operation fails or tmux is unavailable."""


def is_inside_tmux() -> bool:
    """Check if the current process is running inside a tmux session."""
    return "TMUX" in os.environ


def require_tmux() -> None:
    """Raise TmuxError if not running inside tmux.

    Commands that switch the tmux client (e.g., ``worktree-mux open``) need
    an active tmux environment to operate on.
    """
    if not is_inside_tmux():
        raise TmuxError(
            "Not inside a tmux session.\nworktree-mux manages tmux windows — run this from within tmux."
        )


def session_exists(session_name: str) -> bool:
    """Check if a tmux session with the given name exists."""
    result = subprocess.run(
        ["tmux", "has-session", "-t", session_name],
        capture_output=True,
    )
    return result.returncode == 0


def create_session(session_name: str, window_name: str, start_dir: str) -> None:
    """Create a detached tmux session with one initial window."""
    subprocess.run(
        [
            "tmux",
            "new-session",
            "-d",
            "-s",
            session_name,
            "-n",
            window_name,
            "-c",
            start_dir,
        ],
        check=True,
    )


def list_windows(session_name: str) -> list[str]:
    """List all window names in a tmux session.

    Returns an empty list if the session doesn't exist or tmux
    is not available.
    """
    if not session_exists(session_name):
        return []
    result = subprocess.run(
        ["tmux", "list-windows", "-t", session_name, "-F", "#{window_name}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [w.strip() for w in result.stdout.strip().split("\n") if w.strip()]


def window_exists(session_name: str, window_name: str) -> bool:
    """Check if a named window exists in a tmux session."""
    return window_name in list_windows(session_name)


def create_window(session_name: str, window_name: str, start_dir: str) -> None:
    """Create a new window in an existing tmux session."""
    subprocess.run(
        [
            "tmux",
            "new-window",
            "-t",
            session_name,
            "-n",
            window_name,
            "-c",
            start_dir,
        ],
        check=True,
    )


def switch_to_window(session_name: str, window_name: str) -> None:
    """Switch the current tmux client to a window in a session."""
    subprocess.run(
        ["tmux", "switch-client", "-t", f"{session_name}:{window_name}"],
        check=True,
    )


def kill_window(session_name: str, window_name: str) -> None:
    """Kill a window in a tmux session. No-op if the window doesn't exist."""
    subprocess.run(
        ["tmux", "kill-window", "-t", f"{session_name}:{window_name}"],
        capture_output=True,
    )
