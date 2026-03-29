#!/usr/bin/env bash
# launch-reviews.sh — Create worktrees and launch review sessions via tmux.
# Handles single branch (direct run) and multiple branches (tmux panes).
#
# Usage: launch-reviews.sh <language> <branch1> [branch2] [branch3] ...

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REVIEW_SCRIPT="${SCRIPT_DIR}/review-in-worktree.sh"

LANGUAGE="$1"
shift
BRANCHES=("$@")

if [ ${#BRANCHES[@]} -eq 0 ]; then
  echo "Error: No branches specified"
  echo "Usage: launch-reviews.sh <language> <branch1> [branch2] ..."
  exit 1
fi

REPO_ROOT=$(git rev-parse --show-toplevel)
WORKTREE_BASE="${REPO_ROOT}/.claude/worktrees"
mkdir -p "$WORKTREE_BASE"

# Fetch all branches
for BRANCH in "${BRANCHES[@]}"; do
  echo "Fetching origin/${BRANCH}..."
  git fetch origin "$BRANCH" 2>&1 || echo "Warning: could not fetch ${BRANCH}"
done

# Look up PR numbers for each branch
declare -a PR_NUMBERS
for BRANCH in "${BRANCHES[@]}"; do
  PR_NUM=$(gh pr list --head "$BRANCH" --json number -q '.[0].number' 2>/dev/null || echo "")
  PR_NUMBERS+=("$PR_NUM")
done

# Create worktrees
declare -a WORKTREE_PATHS
for BRANCH in "${BRANCHES[@]}"; do
  DIR_NAME="pr-review-$(echo "$BRANCH" | sed 's/[\/]/-/g' | sed 's/[^a-zA-Z0-9._-]//g')"
  WORKTREE_PATH="${WORKTREE_BASE}/${DIR_NAME}"

  # Remove stale worktree if it exists
  if [ -d "$WORKTREE_PATH" ]; then
    git worktree remove "$WORKTREE_PATH" --force 2>/dev/null || true
  fi

  git worktree add "$WORKTREE_PATH" "origin/${BRANCH}" --detach
  WORKTREE_PATHS+=("$WORKTREE_PATH")
done

# Single branch — run directly, no tmux needed
if [ ${#BRANCHES[@]} -eq 1 ]; then
  echo "Single branch — launching review directly..."
  exec bash "$REVIEW_SCRIPT" "$REPO_ROOT" "${WORKTREE_PATHS[0]}" "${BRANCHES[0]}" "$LANGUAGE" "${PR_NUMBERS[0]}"
fi

# Multiple branches — require tmux
if ! command -v tmux >/dev/null 2>&1; then
  echo "Error: tmux is required for multi-branch reviews but was not found."
  echo "Install with: brew install tmux"
  # Clean up worktrees
  for WP in "${WORKTREE_PATHS[@]}"; do
    git worktree remove "$WP" --force 2>/dev/null || true
  done
  git worktree prune 2>/dev/null || true
  exit 1
fi

WORKSPACE_NAME="pr-review-$(date +%s)"
FIRST=true

for i in "${!BRANCHES[@]}"; do
  BRANCH="${BRANCHES[$i]}"
  WORKTREE_PATH="${WORKTREE_PATHS[$i]}"
  PR_NUM="${PR_NUMBERS[$i]}"

  CMD="bash '${REVIEW_SCRIPT}' '${REPO_ROOT}' '${WORKTREE_PATH}' '${BRANCH}' '${LANGUAGE}' '${PR_NUM}'; echo '--- Review complete. Press enter to close ---'; read"

  if [ "$FIRST" = true ]; then
    if [ -n "${TMUX:-}" ]; then
      # In tmux — create a window (tab)
      tmux new-window -n "$WORKSPACE_NAME" "$CMD"
      TMUX_TARGET="$(tmux display-message -p '#{session_name}'):${WORKSPACE_NAME}"
    else
      # Not in tmux — create a session
      tmux new-session -d -s "$WORKSPACE_NAME" -n "reviews" "$CMD"
      TMUX_TARGET="$WORKSPACE_NAME"
    fi
    FIRST=false
  else
    tmux split-window -t "$TMUX_TARGET" -h "$CMD"
    tmux select-layout -t "$TMUX_TARGET" tiled
  fi
done

echo ""
if [ -n "${TMUX:-}" ]; then
  echo "=== Reviews launched in tab: ${WORKSPACE_NAME} ==="
  echo "  Branches: ${BRANCHES[*]}"
  echo "  Switch:   Ctrl-B n/p or Ctrl-B <number>"
else
  echo "=== Reviews launched in session: ${WORKSPACE_NAME} ==="
  echo "  Branches: ${BRANCHES[*]}"
  echo "  Attach:   tmux attach -t ${WORKSPACE_NAME}"
  tmux attach-session -t "$WORKSPACE_NAME"
fi
