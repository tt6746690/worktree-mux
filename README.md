# worktree-mux

A tmux control panel for git worktrees.

When you run multiple AI agents or parallel feature branches, each git worktree becomes its own dev environment. worktree-mux maps **1 worktree → 1 tmux window**, so you can instantly jump between contexts to run commands, inspect logs, or debug — without losing your place.
- **What it does**: fast terminal access to every worktree
- **What it doesn't do**: create or manage worktrees — git still does that

_Think_: a dashboard for parallel coding environments.

See [PLAN.md](PLAN.md) for assumptions and design considerations.

## Install

```bash
# Install from PyPI
uv tool install worktree-mux

# Or install from source
git clone https://github.com/tt6746690/worktree-mux.git
uv tool install worktree-mux/

# (Optional) Short alias — add to ~/.zshrc
alias wm='worktree-mux'
```

## Usage


1. **Create worktrees with git**: worktree-mux just views them

```bash
git worktree add .worktrees/feature/auth -b feature/auth
git worktree add .worktrees/fix/parser-bug -b fix/parser-bug
git worktree add .worktrees/refactor-models -b refactor-models
```

2. **See all worktrees** and their tmux/git status with `worktree-mux ls` (or just `worktree-mux`)

```
Worktrees in my-repo:

  ○ feature/auth                   /path/to/feature/auth
  ○ fix/parser-bug                 /path/to/fix/parser-bug
  ○ refactor-models                /path/to/refactor-models

● = tmux window open    ○ = no tmux window
Session: my-repo (3 worktrees, 0 open)
```

3. **Jump into a worktree**: creates a tmux window and switches to it with `worktree-mux cd`

```bash
worktree-mux cd auth             # (fuzzy) leaf name match
worktree-mux cd parser           # (fuzzy) substring match
worktree-mux cd feature/auth     # exact path match
worktree-mux cd                  # go to the main window (repo root)
```

Return to your previous session: `prefix + s` and toggle

4. **Live dashboard** of worktrees — shows branch status, divergence, modified files with `worktree-mux dash`

```
my-repo — worktree dashboard (refreshes every 5s)
──────────────────────────────────────────────────────────────────────

Branch              tmux  Modified   vs main   Last Commit
──────────────────  ────  ────────   ───────   ─────────────────
feature/auth        ●     2 files    ↑3        12 minutes ago
fix/parser-bug      ○     clean      ↑1        2 hours ago
refactor-models     ○     3 files    ↑5 ↓2     35 minutes ago

● = tmux window open    ○ = no tmux window
```

5. **Cleanup**: worktree-mux automatically cleans up orphaned tmux windows (from removed worktrees) on every command. No manual close needed — just delete the worktree with `git worktree remove` and the window goes away.
