---
name: git-worktree
description: |
  Manage git worktrees for parallel branch work. Use when: working on multiple branches
  simultaneously, reviewing PRs while coding, hotfixes without stashing, parallel feature
  development, checking worktree status, monitoring parallel work, cleaning up finished
  worktrees, removing stale worktrees, tidying up after parallel work.
  Keywords: worktree, git worktree, parallel branches, multiple working directories,
  branch isolation, git add worktree, worktree status, worktree cleanup, remove worktrees,
  clean worktrees, prune worktrees, worktree activity, monitor worktrees, check progress.
allowed-tools: Bash, Read, AskUserQuestion
effort: low
user-invocable: true
---

# Git Worktree Manager

## Commands

| Command | Description |
|---------|-------------|
| `/agentic-coding-workflow:git-worktree add [branch]` | Create worktree (creates branch if needed) |
| `/agentic-coding-workflow:git-worktree list` | Show all worktrees |
| `/agentic-coding-workflow:git-worktree remove [name]` | Remove a worktree |
| `/agentic-coding-workflow:git-worktree status` | Dashboard of all worktrees with activity |
| `/agentic-coding-workflow:git-worktree cleanup` | Find and remove finished worktrees |

## Pre-flight

```bash
git rev-parse --is-inside-work-tree 2>/dev/null || echo "NOT_A_GIT_REPO"
```

If not a git repo, inform user and stop.

## /worktree add [branch]

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/git-worktree/scripts/worktree-add.sh" "<branch>"
```

Output: `CREATED:<path>` or `EXISTS:<path>`. Report path and `cd` command to switch.

## /worktree list

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/git-worktree/scripts/worktree-list.sh"
```

Formats output as a table: path, branch, commit. Highlights worktrees under `.claude/worktrees/`.

## /worktree remove [name]

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/git-worktree/scripts/worktree-remove.sh" "<name>" [--force]
```

Exit codes:
- 0 + `REMOVED:` — success
- 1 + `NOT_FOUND:` — worktree not found
- 2 + `DIRTY:` — has uncommitted changes, needs `--force`. Show changes, ask user to confirm.

## /worktree status

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/git-worktree/scripts/status.sh"
```

Output is structured blocks per worktree with fields: `index`, `dir`, `branch`, `commit`, `status`, `tmux`.

If output is `NO_WORKTREES`, report that no active worktrees exist.

Format into a readable dashboard:

```
Worktree Status Dashboard
==========================

1. feature-payments [.claude/worktrees/feature-payments]
   Branch: feature/payments | Last commit: abc1234 "Add payment handler"
   Git: clean (no uncommitted changes)
   Claude: Writing tests in test_payments.py (tmux session: work:1.2)
```

For worktrees with an active tmux pane, capture recent output:

```bash
tmux capture-pane -t "$PANE_ID" -p -S -20 2>/dev/null
```

## /worktree cleanup

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/git-worktree/scripts/cleanup.sh"
```

Output is structured blocks per worktree with fields: `dir`, `path`, `branch`, `dirty`, `merged`, `unpushed`, `action`.

If output is `NO_WORKTREES`, report that no worktrees exist and stop.

Format into a table, then use AskUserQuestion to offer:
- Remove specific worktrees by number
- Remove all merged+clean worktrees
- Remove all (with confirmation for dirty ones)

For auto-remove of merged+clean:
```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/git-worktree/scripts/cleanup.sh" --auto-remove-merged
```

**Safety:** Never force-remove without explicit user confirmation. Always show uncommitted changes before removing dirty worktrees. Warn if branch has unpushed commits.

## When to Suggest Worktrees

**Use worktrees when:**
- Reviewing PR while keeping current work
- Hotfix on main without stashing
- Comparing implementations across branches
- Running tests on one branch while developing another
- Parallel Claude sessions working on different features

**Use regular branches when:**
- Simple single-branch workflow
- Small stashable changes

## Error Handling

| Error | Action |
|-------|--------|
| Not a git repo | Navigate to git repository first |
| Branch has worktree | Show existing path |
| Path exists | Suggest different name or remove |
| Uncommitted changes | Warn, offer `--force` |
| Branch doesn't exist | Create from HEAD |
