#!/usr/bin/env bash
# Removes a git worktree by branch name or directory name.
# Usage: worktree-remove.sh <name> [--force]
# Outputs status and any warnings.

set -euo pipefail

NAME="${1:?Usage: worktree-remove.sh <name> [--force]}"
FORCE="${2:-}"

REPO_ROOT=$(git rev-parse --show-toplevel)
WORKTREE_BASE="${REPO_ROOT}/.claude/worktrees"

# Find worktree path — try as directory name first, then branch name
WORKTREE_PATH="${WORKTREE_BASE}/${NAME}"
if [ ! -d "$WORKTREE_PATH" ]; then
  # Try sanitized branch name
  DIR_NAME=$(echo "$NAME" | sed 's/[\/]/-/g' | sed 's/[^a-zA-Z0-9._-]//g')
  WORKTREE_PATH="${WORKTREE_BASE}/${DIR_NAME}"
fi

if [ ! -d "$WORKTREE_PATH" ]; then
  echo "NOT_FOUND:${NAME}"
  exit 1
fi

# Check for uncommitted changes
CHANGES=$(git -C "$WORKTREE_PATH" status --porcelain 2>/dev/null || true)
if [ -n "$CHANGES" ] && [ "$FORCE" != "--force" ]; then
  echo "DIRTY:${WORKTREE_PATH}"
  echo "$CHANGES"
  exit 2
fi

# Remove worktree
if [ "$FORCE" = "--force" ]; then
  git worktree remove --force "$WORKTREE_PATH"
else
  git worktree remove "$WORKTREE_PATH"
fi

# Prune stale refs
git worktree prune

echo "REMOVED:${WORKTREE_PATH}"
