#!/usr/bin/env bash
# Shows status of all active worktrees under .claude/worktrees/.
# For each: branch, last commit, dirty/clean, and active tmux pane (if any).

set -euo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel)
WORKTREE_BASE="${REPO_ROOT}/.claude/worktrees"

if [ ! -d "$WORKTREE_BASE" ]; then
  echo "NO_WORKTREES"
  exit 0
fi

# Collect tmux pane info (if available)
TMUX_PANES=""
if command -v tmux &>/dev/null; then
  TMUX_PANES=$(tmux list-panes -a -F '#{pane_current_path}|#{session_name}:#{window_index}.#{pane_index}|#{pane_current_command}' 2>/dev/null || true)
fi

INDEX=0
for wt_dir in "$WORKTREE_BASE"/*/; do
  [ -d "$wt_dir" ] || continue
  INDEX=$((INDEX + 1))

  DIR_NAME=$(basename "$wt_dir")
  BRANCH=$(git -C "$wt_dir" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "detached")
  LAST_COMMIT=$(git -C "$wt_dir" log --oneline -1 2>/dev/null || echo "no commits")
  CHANGES=$(git -C "$wt_dir" status --porcelain 2>/dev/null || true)
  DIRTY_COUNT=$(echo "$CHANGES" | grep -c '[^ ]' 2>/dev/null || echo "0")

  if [ "$DIRTY_COUNT" -gt 0 ]; then
    STATUS="dirty (${DIRTY_COUNT} files)"
  else
    STATUS="clean"
  fi

  # Check for tmux pane in this worktree
  PANE_INFO="none"
  if [ -n "$TMUX_PANES" ]; then
    MATCH=$(echo "$TMUX_PANES" | grep "${wt_dir%/}" | head -1 || true)
    if [ -n "$MATCH" ]; then
      PANE_ID=$(echo "$MATCH" | cut -d'|' -f2)
      PANE_CMD=$(echo "$MATCH" | cut -d'|' -f3)
      PANE_INFO="${PANE_ID} (${PANE_CMD})"
    fi
  fi

  echo "---"
  echo "index: ${INDEX}"
  echo "dir: ${DIR_NAME}"
  echo "branch: ${BRANCH}"
  echo "commit: ${LAST_COMMIT}"
  echo "status: ${STATUS}"
  echo "tmux: ${PANE_INFO}"
done

if [ "$INDEX" -eq 0 ]; then
  echo "NO_WORKTREES"
fi
