---
name: worktree-cleanup
description: |
  Clean up git worktrees in .claude/worktrees/. Lists all worktrees, shows branch/status,
  and removes finished ones. Use when: cleaning up after parallel work, removing stale
  worktrees, tidying up worktree directory. Keywords: worktree cleanup, remove worktrees,
  clean worktrees, prune worktrees, tidy worktrees.
allowed-tools: Bash, Read
user-invocable: true
---

# Worktree Cleanup

Lists all worktrees in `.claude/worktrees/`, shows their branch and status, and removes finished ones.

## Workflow

### 1. Discover Worktrees

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
WORKTREE_BASE="${REPO_ROOT}/.claude/worktrees"

# List all worktrees with details
git worktree list --porcelain
```

### 2. Assess Each Worktree

For each worktree under `.claude/worktrees/`, check:

```bash
# Check for uncommitted changes in a worktree
git -C "$WORKTREE_PATH" status --porcelain

# Check if branch has been merged to main
git branch --merged main | grep -q "$BRANCH_NAME"

# Check for unpushed commits
git -C "$WORKTREE_PATH" log --oneline @{upstream}..HEAD 2>/dev/null
```

### 3. Present Status Table

Display a table for the user:

```
Worktrees in .claude/worktrees/:

| # | Branch           | Status     | Changes | Merged? | Action      |
|---|------------------|------------|---------|---------|-------------|
| 1 | feature-payments | clean      | none    | yes     | safe to remove |
| 2 | fix-auth-bug     | dirty      | 3 files | no      | has changes |
| 3 | refactor-api     | clean      | none    | no      | unmerged    |
```

Status categories:
- **clean** — no uncommitted changes
- **dirty** — has uncommitted changes
- **stale** — branch no longer exists on remote

### 4. Remove Worktrees

Ask user which worktrees to remove. Options:
- Remove specific worktrees by number
- Remove all merged+clean worktrees
- Remove all (with confirmation for dirty ones)

```bash
# Safe removal (fails if dirty)
git worktree remove "$WORKTREE_PATH"

# Force removal (for dirty worktrees, after user confirms)
git worktree remove --force "$WORKTREE_PATH"

# Prune stale worktree refs
git worktree prune

# Clean up empty directories
rmdir "${WORKTREE_BASE}" 2>/dev/null || true
```

### 5. Post-cleanup

```bash
# Show remaining worktrees
git worktree list

# Report what was removed
echo "Removed N worktrees. M remaining."
```

## Safety

- Never force-remove without explicit user confirmation
- Always show uncommitted changes before removing dirty worktrees
- Warn if branch has unpushed commits
- After removal, run `git worktree prune` to clean refs
