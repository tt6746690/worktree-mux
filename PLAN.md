# worktree-mux — Git Worktree tmux Session Manager

## Goal

A Python CLI tool that provides a tmux-based "viewer" for git worktrees. It gives you quick access to terminals for each worktree in a dedicated tmux session, with easy switching between your regular `base` session and the per-repo worktree session.

- **What worktree-mux is:** A reactive view of existing worktrees with easy terminal access.
- **What worktree-mux is NOT:** A lifecycle manager — it doesn't create, remove, or modify worktrees/branches. Those are handled by you or by Copilot agents via the existing worktree skill.

---

## Core Commands

```
worktree-mux                   # show dashboard table (one-shot)
worktree-mux ls                # hidden alias for bare command
worktree-mux cd <name>         # create tmux window for a worktree in the repo session, switch to it
worktree-mux cd                # switch to the 'main' window (repo root)
worktree-mux dash              # live-updating dashboard of all worktrees
```

Running `worktree-mux` with no subcommand prints a one-shot dashboard table
(branch, tmux status, modified files, divergence, last commit) sorted by
most recent commit, with color and a current-worktree indicator.

All commands are run from anywhere inside a git repo.

---

## Resolved Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Name | worktree-mux | Evocative ("view from above the trees"), unique in CLI space |
| Language | Python 3.14 | Typed, testable, distributed via `uv tool install` |
| CLI framework | click | Shell completions, good help text, minimal overhead |
| Distribution | `uv tool install worktree-mux` | Global CLI install via uv |
| Scope | Single-repo | Run from inside a repo; `git worktree list` is source of truth |
| Worktree source | `.worktrees/` dir + `git worktree list` | Reactive — discovers whatever exists |
| State tracking | Stateless | `git worktree list` + `tmux list-windows` at runtime |
| tmux strategy | Dedicated session per repo | Named after repo dir name |
| Session naming | Repo directory name | e.g., `prediction_market_arbitrage` |
| tmux window naming | Leaf name only | e.g., `auth` not `feature/auth`; error on collision |
| Leaf collision | Error with guidance | Tell user to rename worktree dirs for unique leaves |
| Session toggle | tmux native `prefix + L` | Use tmux built-in, no custom switch command |
| Auto-switch on open | Yes | `worktree-mux cd` creates window + switches in one step |
| Auto-cleanup | Every command | Orphaned tmux windows closed before each command runs |
| Main window | Always first | Session always has a 'main' window cd'd to repo root |
| Default subcommand | dashboard table | Running bare `worktree-mux` prints one-shot dashboard |
| `cd` no argument | Switches to main | `worktree-mux cd` goes to repo root window |
| Dashboard divergence | `↑N ↓M` vs default branch | Uses `git rev-list --left-right --count` via merge-base |
| Parent branch detection | Git merge-base | Three-dot rev-list syntax handles diverged branches |
| VS Code | None (deferred) | Agents manage their own windows |
| Lifecycle | None | worktree-mux doesn't create/remove worktrees — it just views them |
| Name matching | Exact → leaf → substring → error | Fuzzy resolution for quick access |

---

## Detailed Command Specs

### `worktree-mux` (bare) / `worktree-mux ls`

Prints a one-shot dashboard table with branch name, tmux window status,
modified file count, divergence from default branch, and last commit time.
Rows are sorted by most recent commit. The current worktree (based on `$PWD`)
is highlighted with a `▸` indicator. Output is colorized when stdout is a tty.

`worktree-mux ls` is a hidden alias that behaves identically.

```
$ worktree-mux
worktree-mux — prediction_market_arbitrage
────────────────────────────────────────────────────────────────

    Branch              tmux  Modified   vs main   Last Commit
    ──────────────────  ────  ────────   ───────   ─────────────────
  ▸ feature/auth        ●     2 files    ↑3        12 minutes ago
    fix/parser-bug      ○     clean      ↑1        2 hours ago
    refactor-models     ○     3 files    ↑5 ↓2     35 minutes ago

  ● = tmux window open    ○ = no tmux window    ▸ = current
  Session: prediction_market_arbitrage (3 worktrees, 1 open)
```

Source of truth: `git worktree list --porcelain` — filters out the main worktree, shows only `.worktrees/*` entries.

### `worktree-mux cd [<name>]`

If `<name>` is given:
1. Resolve `<name>` to a worktree path (exact match first, then fuzzy)
2. Check for leaf name collisions (error if ambiguous)
3. If the repo tmux session doesn't exist, create it with a 'main' window at repo root
4. If a window for this worktree already exists, switch to it (idempotent)
5. Otherwise, create a new window named after the worktree leaf, `cd`'d to its path
6. Auto-switch the tmux client to the repo session + that window

If `<name>` is omitted, switch to the 'main' window (repo root).

```
$ worktree-mux cd auth
# resolves "auth" → .worktrees/feature/auth
# creates/switches to window "auth" in session "prediction_market_arbitrage"
→ feature/auth (session: prediction_market_arbitrage)

$ worktree-mux cd
# switches to the 'main' window at repo root
→ main (session: prediction_market_arbitrage)
```

### Removed: `close`

The `close` command has been removed. Orphaned tmux windows are cleaned
up automatically on every command. Users can also close windows directly
in tmux with `exit` or `prefix + &`.

### `worktree-mux dash`

Runs a live-updating single-pane summary in the current terminal:

```
 prediction_market_arbitrage — worktree dashboard (refreshes every 5s)
 ──────────────────────────────────────────────────────────────────────

 Branch              tmux  Modified   vs main   Last Commit
 ──────────────────  ────  ────────   ───────   ─────────────────
 feature/auth        ●     2 files    ↑3        12 minutes ago
 fix/parser-bug      ○     clean      ↑1        2 hours ago
 refactor-models     ○     3 files    ↑5 ↓2     35 minutes ago

 ● = tmux window open    ○ = no tmux window
```

Implementation: `while True` + `time.sleep(5)` loop with ANSI clear.

Per-worktree info gathered:
- Branch name (from `git worktree list`)
- tmux window status (from `tmux list-windows`)
- Modified file count (`git -C <wt> status --porcelain | wc -l`)
- Commits ahead/behind default branch (`git rev-list --left-right --count main...<branch>`)
- Last commit relative time (`git -C <wt> log -1 --format='%cr'`)

---

## Name Resolution

Given `worktree-mux cd <query>`:

1. **Exact path match:** relative path matches a worktree name (e.g., `feature/auth`)
2. **Leaf match:** last path component equals `<query>` (e.g., `auth` matches `.worktrees/feature/auth`)
3. **Substring match:** `<query>` appears anywhere in the relative path
4. **Multiple matches:** error with candidates, ask user to be more specific
5. **No match:** error with list of available worktrees

```
$ worktree-mux cd feature/auth       # exact → .worktrees/feature/auth ✓

$ worktree-mux cd auth               # leaf → .worktrees/feature/auth ✓

$ worktree-mux cd parser             # substring → .worktrees/fix/parser-bug ✓

$ worktree-mux cd re
# multiple matches:
#   feature/auth (contains "re")
#   refactor-models (contains "re")
# error: ambiguous, be more specific
```

---

## tmux Window Naming

Uses the worktree's leaf name (last path component) as the window name.

| Worktree path | tmux window name |
|---------------|-----------------|
| `.worktrees/feature/auth` | `auth` |
| `.worktrees/refactor-models` | `refactor-models` |
| `.worktrees/fix/parser-bug` | `parser-bug` |

If two worktrees share the same leaf name, `worktree-mux cd` errors and asks
the user to rename one worktree directory.

---

## Auto-Cleanup

Before every command, worktree-mux checks all windows in the repo tmux session
against current worktrees. Windows that don't correspond to any worktree
leaf are considered orphaned and closed automatically.

This keeps tmux in sync with git — when `git worktree remove` deletes
a worktree, the next worktree-mux command cleans up its window.

---

## Project Structure

```
wt/
├── PLAN.md
├── README.md
├── pyproject.toml
├── Makefile
├── .gitignore
├── worktree_mux/
│   ├── __init__.py
│   ├── cli.py           # click CLI entry point + orchestration
│   ├── git.py            # git operations + name resolution
│   ├── tmux.py           # tmux session/window management
│   └── dashboard.py      # live dashboard rendering
└── tests/
    ├── __init__.py
    └── test_git.py        # tests for resolution, divergence display
```

---

## Installation

```bash
# Global install
uv tool install worktree-mux

# Development
make install

# Shell completions (add to ~/.zshrc)
eval "$(_WORKTREE_MUX_COMPLETE=zsh_source worktree-mux)"
```

---

## Implementation Status

### Phase 1: Core ✅
- [x] Project setup (pyproject.toml, Makefile, ruff, mypy, pytest)
- [x] Repo root + session name detection
- [x] `worktree-mux ls` — parse `git worktree list --porcelain`, cross-ref with `tmux list-windows`
- [x] `worktree-mux cd <name>` — name resolution + create/switch tmux window
- [x] `worktree-mux cd` (no arg) — switch to main window at repo root
- [x] Main window created first on session init
- [x] Name resolution: exact → leaf → substring → error
- [x] Leaf collision detection and error
- [x] Auto-cleanup of orphaned tmux windows
- [x] Shell completions for worktree names

### Phase 2: Dashboard ✅
- [x] `worktree-mux dash` — live-updating dashboard with divergence display
- [x] Divergence from default branch via `git rev-list --left-right --count`

### Phase 3: Polish ✅
- [x] `--help` docs with opinionated workflow guidance
- [x] `--version` flag
- [x] README with installation + usage instructions
- [x] Tests (19 passing)
- [x] mypy strict mode passing
- [x] ruff format + lint clean
