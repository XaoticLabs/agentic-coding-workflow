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

# Check if worktree already exists (registered with git)
if git worktree list | grep -q "$WORKTREE_PATH"; then
  echo "EXISTS:${WORKTREE_PATH}"
  exit 0
fi

# Detect branch name collision from sanitization:
# If the target directory exists but is NOT a registered git worktree, a different
# branch name sanitized to the same DIR_NAME — fail explicitly rather than clobbering.
if [[ -d "$WORKTREE_PATH" ]]; then
  EXISTING_BRANCH=$(git -C "$WORKTREE_PATH" branch --show-current 2>/dev/null || echo "unknown")
  echo "ERROR: Directory '${WORKTREE_PATH}' already exists (branch: ${EXISTING_BRANCH})." >&2
  echo "ERROR: Branch '${BRANCH}' sanitizes to the same directory name as an existing worktree." >&2
  echo "ERROR: Choose a branch name that produces a unique directory name after sanitization." >&2
  exit 1
fi

mkdir -p "$WORKTREE_BASE" || { echo "ERROR: Failed to create worktree base directory: ${WORKTREE_BASE}" >&2; exit 1; }

# Create worktree — reuse branch if it exists, otherwise create new
if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  git worktree add "$WORKTREE_PATH" "$BRANCH" \
    || { echo "ERROR: Failed to add worktree for branch '${BRANCH}' at '${WORKTREE_PATH}'" >&2; exit 1; }
else
  git worktree add -b "$BRANCH" "$WORKTREE_PATH" \
    || { echo "ERROR: Failed to create and add worktree for new branch '${BRANCH}' at '${WORKTREE_PATH}'" >&2; exit 1; }
fi

echo "CREATED:${WORKTREE_PATH}"
