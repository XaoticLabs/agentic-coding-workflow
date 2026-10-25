#!/usr/bin/env bash
# Assesses all worktrees under .claude/worktrees/ for cleanup eligibility.
# Outputs structured data for each worktree: path, branch, dirty/clean, merged status.
# Usage: cleanup.sh [--auto-remove-merged]

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../../../scripts/lib/worktree-safety.sh"

AUTO_REMOVE="${1:-}"
REPO_ROOT=$(git rev-parse --show-toplevel)
WORKTREE_BASE="${REPO_ROOT}/.claude/worktrees"
MAIN_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@' || git symbolic-ref --short HEAD)

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
  if git merge-base --is-ancestor "$(git -C "$wt_dir" rev-parse HEAD)" "$MAIN_BRANCH" 2>/dev/null; then
    MERGED="yes"
  else
    MERGED="no"
  fi

  # Check unpushed
  UNPUSHED=$(git -C "$wt_dir" log --oneline "@{upstream}..HEAD" 2>/dev/null | wc -l | tr -d ' ' || echo "unknown")

  REASON=$(worktree_cleanup_check "$REPO_ROOT" "${wt_dir%/}" "$MAIN_BRANCH" 2>/dev/null || true)
  if [ "$AUTO_REMOVE" = "--auto-remove-merged" ] && [ "$REASON" = eligible ]; then
    if preserve_worktree_artifacts "$REPO_ROOT" "${wt_dir%/}" "${REPO_ROOT}/.claude/worktree-archives/$(date +%s)-${DIR_NAME}" &&
      remove_owned_worktree "$REPO_ROOT" "${wt_dir%/}" "$MAIN_BRANCH"; then
      echo "AUTO_REMOVED:${DIR_NAME}:${BRANCH}"
      REMOVED=$((REMOVED + 1))
      continue
    fi
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
  if [ "$REASON" = eligible ]; then
    echo "action: safe_to_remove"
  elif [ "$DIRTY" = "yes" ]; then
    echo "action: has_changes"
  else
    echo "action: preserve (${REASON})"
  fi
done

if [ "$REMOVED" -gt 0 ]; then
  echo "SUMMARY: removed=${REMOVED} remaining=${REMAINING}"
fi
