#!/usr/bin/env bash
# Discover worktree branches that descend from the current feature branch.
#
# Usage: discover-branches.sh [parent-branch]
#   parent-branch: defaults to current branch in the main repo
#
# Output: one branch name per line for each qualifying worktree

set -euo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
WORKTREE_BASE="${REPO_ROOT}/.claude/worktrees"
PARENT_BRANCH="${1:-$(git symbolic-ref --short HEAD 2>/dev/null || echo "")}"

if [ -z "$PARENT_BRANCH" ]; then
  echo "Error: could not determine parent branch" >&2
  exit 1
fi

if [ ! -d "$WORKTREE_BASE" ]; then
  echo "No worktree directory found at ${WORKTREE_BASE}" >&2
  exit 0
fi

for wt_dir in "$WORKTREE_BASE"/*/; do
  [ -d "$wt_dir" ] || continue

  branch=$(git -C "$wt_dir" symbolic-ref --short HEAD 2>/dev/null || continue)
  [ "$branch" = "$PARENT_BRANCH" ] && continue

  # Check if parent branch is an ancestor of this worker branch
  if git merge-base --is-ancestor "$PARENT_BRANCH" "$branch" 2>/dev/null; then
    name=$(basename "$wt_dir")
    ahead=$(git rev-list --count "${PARENT_BRANCH}..${branch}" 2>/dev/null || echo "0")
    dirty=$(git -C "$wt_dir" status --short 2>/dev/null | wc -l | tr -d ' ')

    # Check for active Claude session
    claude_active="no"
    if command -v tmux &>/dev/null && [ -n "${TMUX:-}" ]; then
      pane_info=$(tmux list-panes -a -F '#{pane_current_path} #{pane_current_command}' 2>/dev/null | grep "$wt_dir" | head -1 || true)
      if echo "$pane_info" | grep -q "claude\|node"; then
        claude_active="yes"
      fi
    fi

    printf '%s\t%s\t%s\t%s\t%s\n' "$name" "$branch" "$ahead" "$dirty" "$claude_active"
  fi
done
