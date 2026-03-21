#!/bin/bash
# cleanup-session.sh - Gracefully terminate a tmux session
#
# Usage: cleanup-session.sh <session-name> [options]
# Example: cleanup-session.sh my-project
# Example: cleanup-session.sh my-project --force
# Example: cleanup-session.sh my-project --save-output /tmp/session-output.txt
#
# Arguments:
#   session-name  Required. Name of session to clean up
#
# Options:
#   --force       Kill immediately without confirmation
#   --save-output Save all pane outputs before killing
#   --graceful    Send SIGTERM to processes before killing (default)
#   --immediate   Skip graceful shutdown, kill immediately

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

error() { echo -e "${RED}Error: $1${NC}" >&2; exit 1; }
warn() { echo -e "${YELLOW}Warning: $1${NC}" >&2; }
success() { echo -e "${GREEN}$1${NC}"; }

# Check tmux
command -v tmux >/dev/null 2>&1 || error "tmux is not installed"

# Default values
SESSION_NAME=""
FORCE=false
SAVE_OUTPUT=""
GRACEFUL=true

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --force)
      FORCE=true
      shift
      ;;
    --save-output)
      SAVE_OUTPUT="$2"
      shift 2
      ;;
    --graceful)
      GRACEFUL=true
      shift
      ;;
    --immediate)
      GRACEFUL=false
      shift
      ;;
    -*)
      error "Unknown option: $1"
      ;;
    *)
      SESSION_NAME="$1"
      shift
      ;;
  esac
done

# Validate session name
[ -z "$SESSION_NAME" ] && error "Session name required. Usage: $0 <session-name> [options]"

# Check if session exists
if ! tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  warn "Session '$SESSION_NAME' does not exist"
  exit 0
fi

# Get session info
session_info=$(tmux list-windows -t "$SESSION_NAME" -F "#{window_index}:#{window_name}:#{window_panes}" 2>/dev/null)
window_count=$(echo "$session_info" | wc -l)
pane_count=$(tmux list-panes -t "$SESSION_NAME" -a 2>/dev/null | wc -l)

echo "Session: $SESSION_NAME"
echo "Windows: $window_count"
echo "Panes: $pane_count"
echo ""

# List what's running
echo "Running processes:"
tmux list-panes -t "$SESSION_NAME" -a -F "  #{window_name}/#{pane_index}: #{pane_current_command}" 2>/dev/null
echo ""

# Confirm unless force
if [ "$FORCE" = false ]; then
  read -p "Kill session '$SESSION_NAME'? [y/N] " -n 1 -r
  echo
  [[ ! $REPLY =~ ^[Yy]$ ]] && exit 0
fi

# Save output if requested
if [ -n "$SAVE_OUTPUT" ]; then
  echo "Saving pane outputs to $SAVE_OUTPUT..."

  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if [ -f "$SCRIPT_DIR/collect-pane-outputs.sh" ]; then
    "$SCRIPT_DIR/collect-pane-outputs.sh" --session "$SESSION_NAME" --all-windows > "$SAVE_OUTPUT"
  else
    # Fallback inline capture
    {
      echo "Session: $SESSION_NAME"
      echo "Captured: $(date)"
      echo ""

      for window in $(tmux list-windows -t "$SESSION_NAME" -F "#{window_index}" 2>/dev/null); do
        for pane in $(tmux list-panes -t "$SESSION_NAME:$window" -F "#{pane_index}" 2>/dev/null); do
          echo "=== Window $window, Pane $pane ==="
          tmux capture-pane -t "$SESSION_NAME:$window.$pane" -p -S -1000 2>/dev/null || echo "(capture failed)"
          echo ""
        done
      done
    } > "$SAVE_OUTPUT"
  fi

  success "Output saved to $SAVE_OUTPUT"
fi

# Graceful shutdown: send SIGTERM to processes first
if [ "$GRACEFUL" = true ]; then
  echo "Sending SIGTERM to processes..."

  for window in $(tmux list-windows -t "$SESSION_NAME" -F "#{window_index}" 2>/dev/null); do
    for pane in $(tmux list-panes -t "$SESSION_NAME:$window" -F "#{pane_index}" 2>/dev/null); do
      # Send Ctrl-C to interrupt running commands
      tmux send-keys -t "$SESSION_NAME:$window.$pane" C-c 2>/dev/null || true
    done
  done

  # Brief wait for graceful shutdown
  sleep 1
fi

# Kill the session
echo "Killing session..."
tmux kill-session -t "$SESSION_NAME"

success "Session '$SESSION_NAME' terminated"

# If we were attached to this session, we're now detached
if [ -n "$TMUX" ]; then
  current_session=$(tmux display-message -p "#{session_name}" 2>/dev/null || echo "")
  if [ "$current_session" = "$SESSION_NAME" ]; then
    warn "You were attached to the killed session"
  fi
fi
