#!/bin/bash
# Dashboard: polls worktree status and displays it in a tmux pane.
# Runs in a dedicated tmux pane, refreshing every N seconds.
#
# Usage: dashboard.sh [--interval 30]

set -euo pipefail

INTERVAL=30
TARGET_BRANCH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --interval) INTERVAL="$2"; shift 2 ;;
    *) shift ;;
  esac
done

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
WORKTREE_BASE="${REPO_ROOT}/.claude/worktrees"
MESSAGE_DIR="${REPO_ROOT}/.claude/messages"

# Find base branch
if [ -z "$TARGET_BRANCH" ]; then
  for candidate in main master; do
    if git show-ref --verify --quiet "refs/heads/$candidate"; then
      TARGET_BRANCH="$candidate"
      break
    fi
  done
fi

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

clear_screen() {
  printf '\033[2J\033[H'
}

get_worktree_status() {
  local wt_path="$1"
  local branch=$(git -C "$wt_path" symbolic-ref --short HEAD 2>/dev/null || echo "detached")
  local last_commit=$(git -C "$wt_path" log --oneline -1 2>/dev/null || echo "no commits")
  local dirty_count=$(git -C "$wt_path" status --short 2>/dev/null | wc -l | tr -d ' ')
  local ahead=$(git -C "$wt_path" rev-list --count "${TARGET_BRANCH}..HEAD" 2>/dev/null || echo "?")

  # Check if tests pass (quick check — look for recent test results)
  local tests_status="unknown"
  if [ "$dirty_count" -eq 0 ]; then
    tests_status="clean"
  else
    tests_status="dirty (${dirty_count} files)"
  fi

  # Check tmux for active Claude session
  local claude_status="inactive"
  if command -v tmux &>/dev/null && [ -n "${TMUX:-}" ]; then
    local pane_info=$(tmux list-panes -a -F '#{pane_current_path} #{pane_current_command}' 2>/dev/null | grep "$wt_path" | head -1)
    if [ -n "$pane_info" ]; then
      local cmd=$(echo "$pane_info" | awk '{print $2}')
      if [[ "$cmd" == *"claude"* || "$cmd" == *"node"* ]]; then
        claude_status="running"
      else
        claude_status="shell idle"
      fi
    fi
  fi

  echo "${branch}|${last_commit}|${tests_status}|${ahead}|${claude_status}"
}

render_messages() {
  if [ ! -d "$MESSAGE_DIR" ]; then
    return
  fi

  local msg_files=$(find "$MESSAGE_DIR" -name "*.md" -newer "$MESSAGE_DIR/.last-read" 2>/dev/null || \
                    find "$MESSAGE_DIR" -name "*.md" 2>/dev/null)

  if [ -n "$msg_files" ]; then
    echo ""
    echo -e "${CYAN}━━━ Agent Messages ━━━${NC}"
    echo "$msg_files" | while read -r f; do
      [ -f "$f" ] || continue
      local from=$(head -5 "$f" | grep "^from:" | sed 's/^from: //')
      local subject=$(head -5 "$f" | grep "^subject:" | sed 's/^subject: //')
      local time=$(stat -f "%Sm" -t "%H:%M" "$f" 2>/dev/null || date -r "$f" +%H:%M 2>/dev/null || echo "??:??")
      echo -e "  ${YELLOW}[${time}]${NC} ${from:-agent}: ${subject:-<no subject>}"
    done
    touch "$MESSAGE_DIR/.last-read" 2>/dev/null || true
  fi
}

# Main loop
while true; do
  clear_screen

  echo -e "${BLUE}━━━ Parallel Work Dashboard ━━━${NC}"
  echo -e "Target: ${TARGET_BRANCH} | Refresh: ${INTERVAL}s"
  echo -e "Time: $(date +%H:%M:%S)"
  echo ""

  if [ ! -d "$WORKTREE_BASE" ] || [ -z "$(ls -A "$WORKTREE_BASE" 2>/dev/null)" ]; then
    echo -e "${YELLOW}No active worktrees in .claude/worktrees/${NC}"
  else
    printf "%-20s %-30s %-15s %-8s %-12s\n" "WORKTREE" "BRANCH" "STATUS" "AHEAD" "CLAUDE"
    printf "%-20s %-30s %-15s %-8s %-12s\n" "--------" "------" "------" "-----" "------"

    for wt_dir in "$WORKTREE_BASE"/*/; do
      [ -d "$wt_dir" ] || continue
      name=$(basename "$wt_dir")

      status_line=$(get_worktree_status "$wt_dir")
      IFS='|' read -r branch last_commit tests_status ahead claude_status <<< "$status_line"

      # Color code status
      case "$tests_status" in
        clean) status_color="${GREEN}" ;;
        dirty*) status_color="${YELLOW}" ;;
        *) status_color="${NC}" ;;
      esac

      case "$claude_status" in
        running) claude_color="${GREEN}" ;;
        "shell idle") claude_color="${YELLOW}" ;;
        *) claude_color="${RED}" ;;
      esac

      printf "%-20s %-30s ${status_color}%-15s${NC} %-8s ${claude_color}%-12s${NC}\n" \
        "$name" "${branch:0:28}" "$tests_status" "$ahead" "$claude_status"
    done
  fi

  # Show recent agent messages
  render_messages

  echo ""
  echo -e "${BLUE}Press Ctrl-C to exit${NC}"

  sleep "$INTERVAL"
done
