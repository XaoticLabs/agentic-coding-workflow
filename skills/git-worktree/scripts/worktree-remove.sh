#!/usr/bin/env bash
# Removes a git worktree by branch name or directory name.
# Usage: worktree-remove.sh <name>
# Outputs status and any warnings.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../../../scripts/lib/worktree-safety.sh"

NAME="${1:?Usage: worktree-remove.sh <name>}"

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

# Removal flags never bypass ownership or preservation checks.
if ! REASON=$(worktree_cleanup_check "$REPO_ROOT" "$WORKTREE_PATH"); then
  echo "PRESERVED:${WORKTREE_PATH}:${REASON}"
  exit 2
fi

preserve_worktree_artifacts "$REPO_ROOT" "$WORKTREE_PATH" "${REPO_ROOT}/.claude/worktree-archives/$(date +%s)-$(basename "$WORKTREE_PATH")"
remove_owned_worktree "$REPO_ROOT" "$WORKTREE_PATH" "" --keep-branch

echo "REMOVED:${WORKTREE_PATH}"
