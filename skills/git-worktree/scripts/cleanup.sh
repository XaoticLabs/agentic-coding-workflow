#!/usr/bin/env bash
# Assesses all worktrees under .claude/worktrees/ for cleanup eligibility.
# Outputs structured data for each worktree: path, branch, dirty/clean, merged status.
# Usage: cleanup.sh [--auto-remove-merged]

set -euo pipefail

AUTO_REMOVE="${1:-}"
REPO_ROOT=$(git rev-parse --show-toplevel)
WORKTREE_BASE="${REPO_ROOT}/.claude/worktrees"
MAIN_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@' || echo "main")

if [ ! -d "$WORKTREE_BASE" ]; then
  echo "NO_WORKTREES"
  exit 0
fi

REMOVED=0
REMAINING=0

for wt_dir in "$WORKTREE_BASE"/*/; do
  [ -d "$wt_dir" ] || continue

  DIR_NAME=$(basename "$wt_dir")
  BRANCH=$(git -C "$wt_dir" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "detached")

  # Check dirty
  CHANGES=$(git -C "$wt_dir" status --porcelain 2>/dev/null || true)
  if [ -n "$CHANGES" ]; then
    DIRTY="yes"
    DIRTY_COUNT=$(echo "$CHANGES" | wc -l | tr -d ' ')
  else
    DIRTY="no"
    DIRTY_COUNT=0
  fi

  # Check merged
  if git branch --merged "$MAIN_BRANCH" 2>/dev/null | grep -q "$BRANCH"; then
    MERGED="yes"
  else
    MERGED="no"
  fi

  # Check unpushed
  UNPUSHED=$(git -C "$wt_dir" log --oneline "@{upstream}..HEAD" 2>/dev/null | wc -l | tr -d ' ' || echo "unknown")

  # Auto-remove if merged+clean and flag is set
  if [ "$AUTO_REMOVE" = "--auto-remove-merged" ] && [ "$MERGED" = "yes" ] && [ "$DIRTY" = "no" ]; then
    git worktree remove "$wt_dir" 2>/dev/null && {
      git branch -d "$BRANCH" 2>/dev/null || true
      echo "AUTO_REMOVED:${DIR_NAME}:${BRANCH}"
      REMOVED=$((REMOVED + 1))
      continue
    }
  fi

  REMAINING=$((REMAINING + 1))
  echo "---"
  echo "dir: ${DIR_NAME}"
  echo "path: ${wt_dir%/}"
  echo "branch: ${BRANCH}"
  echo "dirty: ${DIRTY} (${DIRTY_COUNT} files)"
  echo "merged: ${MERGED}"
  echo "unpushed: ${UNPUSHED}"

  # Recommend action
  if [ "$MERGED" = "yes" ] && [ "$DIRTY" = "no" ]; then
    echo "action: safe_to_remove"
  elif [ "$DIRTY" = "yes" ]; then
    echo "action: has_changes"
  else
    echo "action: unmerged"
  fi
done

git worktree prune 2>/dev/null || true

if [ "$REMOVED" -gt 0 ]; then
  echo "SUMMARY: removed=${REMOVED} remaining=${REMAINING}"
fi
