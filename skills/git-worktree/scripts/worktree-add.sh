#!/usr/bin/env bash
# Creates a git worktree under .claude/worktrees/ for the given branch.
# Usage: worktree-add.sh <branch-name>
# Outputs the worktree path on success.

set -euo pipefail

BRANCH="${1:?Usage: worktree-add.sh <branch-name>}"

REPO_ROOT=$(git rev-parse --show-toplevel)
WORKTREE_BASE="${REPO_ROOT}/.claude/worktrees"
DIR_NAME=$(echo "$BRANCH" | sed 's/[\/]/-/g' | sed 's/[^a-zA-Z0-9._-]//g')
WORKTREE_PATH="${WORKTREE_BASE}/${DIR_NAME}"

# Ensure .claude/worktrees/ is gitignored
if ! grep -q '\.claude/worktrees/' "${REPO_ROOT}/.gitignore" 2>/dev/null; then
  echo -e '\n# Git worktrees (parallel branch work)\n.claude/worktrees/' >> "${REPO_ROOT}/.gitignore"
fi

# Check if worktree already exists
if git worktree list | grep -q "$WORKTREE_PATH"; then
  echo "EXISTS:${WORKTREE_PATH}"
  exit 0
fi

mkdir -p "$WORKTREE_BASE"

# Create worktree — reuse branch if it exists, otherwise create new
if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  git worktree add "$WORKTREE_PATH" "$BRANCH"
else
  git worktree add -b "$BRANCH" "$WORKTREE_PATH"
fi

echo "CREATED:${WORKTREE_PATH}"
