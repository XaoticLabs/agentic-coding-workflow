---
name: worktree-status
description: |
  Show status of all active worktrees in .claude/worktrees/ and what Claude is doing in each
  via tmux pane capture. Use when: checking parallel work progress, monitoring worktree
  activity, seeing what's running across worktrees. Keywords: worktree status, parallel
  status, worktree activity, what's running, monitor worktrees, check progress.
allowed-tools: Bash, Read
user-invocable: true
---

# Worktree Status

Shows all active worktrees in `.claude/worktrees/` and what Claude is doing in each (via tmux pane capture).

## Workflow

### 1. Gather Worktree Info

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
WORKTREE_BASE="${REPO_ROOT}/.claude/worktrees"

# Get all worktrees with porcelain output for parsing
git worktree list --porcelain
```

### 2. For Each Worktree, Collect Status

```bash
# Git status (clean/dirty, branch, last commit)
git -C "$WORKTREE_PATH" log --oneline -1
git -C "$WORKTREE_PATH" status --short

# Check if there's a tmux pane running in this worktree
# Look for tmux panes where the current directory matches the worktree path
tmux list-panes -a -F '#{pane_current_path} #{session_name}:#{window_index}.#{pane_index} #{pane_current_command}' 2>/dev/null | grep "$WORKTREE_PATH"
```

### 3. Capture Claude Activity (if tmux is active)

```bash
# For each pane that's in a worktree directory, capture recent output
tmux capture-pane -t "$PANE_ID" -p -S -20 2>/dev/null
```

Look for indicators of what Claude is doing:
- Tool calls in progress
- Files being edited
- Tests running
- Waiting for input

### 4. Present Status Dashboard

```
Worktree Status Dashboard
==========================

1. feature-payments [.claude/worktrees/feature-payments]
   Branch: feature/payments | Last commit: abc1234 "Add payment handler"
   Git: clean (no uncommitted changes)
   Claude: Writing tests in test_payments.py (tmux session: work:1.2)

2. fix-auth-bug [.claude/worktrees/fix-auth-bug]
   Branch: fix/auth-bug | Last commit: def5678 "Fix token validation"
   Git: 2 modified files
   Claude: No active session detected

3. refactor-api [.claude/worktrees/refactor-api]
   Branch: refactor/api-layer | Last commit: ghi9012 "Extract API client"
   Git: clean
   Claude: Running test suite (tmux session: work:1.3)
```

### 5. Optional: Quick Actions

After showing status, offer:
- **Switch to worktree**: provide `cd` path
- **Open in tmux pane**: launch new Claude session in worktree
- **Remove finished worktree**: if merged and clean
