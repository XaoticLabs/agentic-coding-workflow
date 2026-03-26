#!/usr/bin/env bash
# cleanup-review-worktrees.sh — SessionEnd hook that removes orphaned
# review worktrees. Only targets directories matching the "pr-review-*"
# naming convention used by review commands and PR reviewer skills.

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
WORKTREE_BASE="${REPO_ROOT}/.claude/worktrees"

[ -d "$WORKTREE_BASE" ] || exit 0

found=0
for dir in "$WORKTREE_BASE"/pr-review-*; do
  [ -d "$dir" ] || continue
  found=1
  git worktree remove "$dir" --force 2>/dev/null || true
done

if [ "$found" -eq 1 ]; then
  git worktree prune 2>/dev/null || true
fi

exit 0
