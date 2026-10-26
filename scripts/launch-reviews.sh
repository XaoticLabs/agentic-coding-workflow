#!/usr/bin/env bash
# launch-reviews.sh — Create worktrees and launch review sessions via tmux.
# Handles single branch (direct run) and multiple branches (tmux panes).
#
# Usage: launch-reviews.sh <language> <branch1> [branch2] [branch3] ...

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REVIEW_SCRIPT="${SCRIPT_DIR}/review-in-worktree.sh"
source "${SCRIPT_DIR}/lib/worktree-safety.sh"

LANGUAGE="$1"
REVIEW_MODE="${REVIEW_MODE:-defects}"
case "$REVIEW_MODE" in defects|suggestions) ;; *) echo "Error: invalid REVIEW_MODE" >&2; exit 2 ;; esac
shift
BRANCHES=("$@")
WORKTREE_PATHS=()
REVIEW_LAUNCHED=()

if [ ${#BRANCHES[@]} -eq 0 ]; then
  echo "Error: No branches specified"
  echo "Usage: launch-reviews.sh <language> <branch1> [branch2] ..."
  exit 1
fi

REPO_ROOT=$(git rev-parse --show-toplevel)
WORKTREE_BASE="${REPO_ROOT}/.claude/worktrees"

# Only this invocation's unlaunched worktrees belong to this exit handler.
# A successfully launched review owns its cleanup in review-in-worktree.sh.
cleanup_pending_reviews() {
  local exit_code=$? i worktree_path
  trap - EXIT INT TERM HUP
  for i in "${!WORKTREE_PATHS[@]}"; do
    [ "${REVIEW_LAUNCHED[$i]:-false}" = true ] && continue
    worktree_path="${WORKTREE_PATHS[$i]}"
    [ -d "$worktree_path" ] || continue
    release_worktree "$REPO_ROOT" "$worktree_path" || true
    if ! worktree_cleanup_check "$REPO_ROOT" "$worktree_path" >/dev/null 2>&1 ||
      ! preserve_worktree_artifacts "$REPO_ROOT" "$worktree_path" "${REPO_ROOT}/.claude/worktree-archives/$(date +%s)-$(basename "$worktree_path")" ||
      ! remove_owned_worktree "$REPO_ROOT" "$worktree_path" "" --keep-branch; then
      echo "Worktree preserved: ${worktree_path}" >&2
    fi
  done
  exit "$exit_code"
}

trap cleanup_pending_reviews EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

if [ ${#BRANCHES[@]} -gt 1 ] && ! command -v tmux >/dev/null 2>&1; then
  echo "Error: tmux is required for multi-branch reviews but was not found." >&2
  exit 1
fi

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
for BRANCH in "${BRANCHES[@]}"; do
  DIR_NAME="pr-review-$(echo "$BRANCH" | sed 's/[\/]/-/g' | sed 's/[^a-zA-Z0-9._-]//g')"
  WORKTREE_PATH="${WORKTREE_BASE}/${DIR_NAME}"

  if [ -e "$WORKTREE_PATH" ] || [ -L "$WORKTREE_PATH" ]; then
    echo "Error: review worktree already exists; preserved: ${WORKTREE_PATH}" >&2
    exit 1
  fi

  git worktree add "$WORKTREE_PATH" "origin/${BRANCH}" --detach
  WORKTREE_PATHS+=("$WORKTREE_PATH")
  register_worktree_owner "$REPO_ROOT" "$WORKTREE_PATH" "$(git -C "$WORKTREE_PATH" rev-parse HEAD)"
done

# Single branch — run directly, no tmux needed
if [ ${#BRANCHES[@]} -eq 1 ]; then
  echo "Single branch — launching review directly..."
  exec bash "$REVIEW_SCRIPT" "$REPO_ROOT" "${WORKTREE_PATHS[0]}" "${BRANCHES[0]}" "$LANGUAGE" "${PR_NUMBERS[0]}" "$REVIEW_MODE"
fi

WORKSPACE_NAME="pr-review-$(date +%s)"
FIRST=true

for i in "${!BRANCHES[@]}"; do
  BRANCH="${BRANCHES[$i]}"
  WORKTREE_PATH="${WORKTREE_PATHS[$i]}"
  PR_NUM="${PR_NUMBERS[$i]}"

  printf -v CMD '%q ' env "WORKTREE_OWNER_TOKEN=${WORKTREE_OWNER_TOKEN}" bash "$REVIEW_SCRIPT" "$REPO_ROOT" "$WORKTREE_PATH" "$BRANCH" "$LANGUAGE" "$PR_NUM" "$REVIEW_MODE"

  if [ "$FIRST" = true ]; then
    if [ -n "${TMUX:-}" ]; then
      # In tmux — create a window (tab)
      tmux new-window -n "$WORKSPACE_NAME" "$CMD"
      REVIEW_LAUNCHED[$i]=true
      TMUX_TARGET="$(tmux display-message -p '#{session_name}'):${WORKSPACE_NAME}"
    else
      # Not in tmux — create a session
      tmux new-session -d -s "$WORKSPACE_NAME" -n "reviews" "$CMD"
      REVIEW_LAUNCHED[$i]=true
      TMUX_TARGET="$WORKSPACE_NAME"
    fi
    FIRST=false
  else
    tmux split-window -t "$TMUX_TARGET" -h "$CMD"
    REVIEW_LAUNCHED[$i]=true
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
