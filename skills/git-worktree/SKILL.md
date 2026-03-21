---
name: git-worktree
description: |
  Manage git worktrees for parallel branch work. Use when: working on multiple branches
  simultaneously, reviewing PRs while coding, hotfixes without stashing, parallel feature
  development. Keywords: worktree, git worktree, parallel branches, multiple working
  directories, branch isolation, git add worktree.
allowed-tools: Bash, Read
user-invocable: true
---

# Git Worktree Manager

## Commands

| Command | Description |
|---------|-------------|
| `/worktree-add [branch]` | Create worktree (creates branch if needed) |
| `/worktree-list` | Show all worktrees |
| `/worktree-remove [name]` | Remove a worktree |
| `/worktree-switch [name]` | Get path to switch to worktree |

## Pre-flight

```bash
git rev-parse --is-inside-work-tree 2>/dev/null || echo "NOT_A_GIT_REPO"
```

If not a git repo, inform user and stop.

## Worktree Location

**Standard location:** `<project-root>/.claude/worktrees/<sanitized-branch>/`

All worktrees live under `.claude/worktrees/` within the project root. This makes discovery, cleanup, and gitignore trivial. The directory is automatically gitignored.

Sanitize branch: Replace `/` with `-`, strip special chars.

## /worktree-add [branch]

```bash
# 1. Get paths
REPO_ROOT=$(git rev-parse --show-toplevel)
WORKTREE_BASE="${REPO_ROOT}/.claude/worktrees"
BRANCH="$1"
DIR_NAME=$(echo "$BRANCH" | sed 's/[\/]/-/g' | sed 's/[^a-zA-Z0-9._-]//g')
WORKTREE_PATH="${WORKTREE_BASE}/${DIR_NAME}"

# 2. Ensure .claude/worktrees/ is gitignored
if ! grep -q '\.claude/worktrees/' "${REPO_ROOT}/.gitignore" 2>/dev/null; then
  echo -e '\n# Git worktrees (parallel branch work)\n.claude/worktrees/' >> "${REPO_ROOT}/.gitignore"
fi

# 3. Check existing
git worktree list | grep -q "$WORKTREE_PATH" && echo "Worktree exists"

# 4. Create
mkdir -p "$WORKTREE_BASE"
if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  git worktree add "$WORKTREE_PATH" "$BRANCH"
else
  git worktree add -b "$BRANCH" "$WORKTREE_PATH"
fi
```

Report: path created, `cd` command to switch.

## /worktree-list

```bash
git worktree list
```

Format output as table: path, branch, commit. Highlight worktrees under `.claude/worktrees/`.

## /worktree-remove [name]

```bash
# Find worktree by branch or directory name
git worktree list --porcelain

# Remove (warn if uncommitted changes)
git worktree remove "$WORKTREE_PATH"
# Force if needed: git worktree remove --force "$WORKTREE_PATH"

# Clean up stale refs
git worktree prune
```

## /worktree-switch [name]

Find worktree path and display:
```
Path: /code/myapp/.claude/worktrees/feature-auth
To switch: cd /code/myapp/.claude/worktrees/feature-auth
```

Note: Cannot change user's shell cwd—provide path for manual `cd`.

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

## Example

```
User: /worktree-add feature/payments

Claude: Creating worktree for 'feature/payments'...

Created:
  Path: /code/myapp/.claude/worktrees/feature-payments
  Branch: feature/payments (new from main)

Switch: cd /code/myapp/.claude/worktrees/feature-payments
```
