#!/bin/bash
# setup-workspace.sh - Create a tmux workspace with multiple panes
#
# Usage: setup-workspace.sh <session-name> [pane-count] [layout]
# Example: setup-workspace.sh my-project 4 tiled
#
# Arguments:
#   session-name  Required. Name for the tmux session
#   pane-count    Optional. Number of panes (default: 2, max: 8)
#   layout        Optional. Layout type (default: tiled)
#                 Options: even-horizontal, even-vertical, main-horizontal,
#                          main-vertical, tiled

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

error() { echo -e "${RED}Error: $1${NC}" >&2; exit 1; }
warn() { echo -e "${YELLOW}Warning: $1${NC}" >&2; }
success() { echo -e "${GREEN}$1${NC}"; }

# Check tmux availability
command -v tmux >/dev/null 2>&1 || error "tmux is not installed"

# Parse arguments
SESSION_NAME="${1:-}"
PANE_COUNT="${2:-2}"
LAYOUT="${3:-tiled}"

# Validate session name
[ -z "$SESSION_NAME" ] && error "Session name required. Usage: $0 <session-name> [pane-count] [layout]"

# Validate pane count
if ! [[ "$PANE_COUNT" =~ ^[0-9]+$ ]] || [ "$PANE_COUNT" -lt 1 ] || [ "$PANE_COUNT" -gt 8 ]; then
  error "Pane count must be between 1 and 8"
fi

# Validate layout
valid_layouts=("even-horizontal" "even-vertical" "main-horizontal" "main-vertical" "tiled")
layout_valid=false
for l in "${valid_layouts[@]}"; do
  [ "$l" = "$LAYOUT" ] && layout_valid=true
done
$layout_valid || error "Invalid layout. Options: ${valid_layouts[*]}"

# Check if session already exists
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  warn "Session '$SESSION_NAME' already exists"
  read -p "Kill existing session and create new? [y/N] " -n 1 -r
  echo
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    tmux kill-session -t "$SESSION_NAME"
  else
    echo "Attaching to existing session..."
    exec tmux attach-session -t "$SESSION_NAME"
  fi
fi

# Create session
echo "Creating session '$SESSION_NAME' with $PANE_COUNT panes..."
tmux new-session -d -s "$SESSION_NAME"

# Create additional panes
for ((i = 1; i < PANE_COUNT; i++)); do
  if [ $((i % 2)) -eq 1 ]; then
    tmux split-window -h -t "$SESSION_NAME"
  else
    tmux split-window -v -t "$SESSION_NAME"
  fi
done

# Apply layout
tmux select-layout -t "$SESSION_NAME" "$LAYOUT"

# Select first pane
tmux select-pane -t "$SESSION_NAME:0.0"

success "Workspace '$SESSION_NAME' created with $PANE_COUNT panes ($LAYOUT layout)"

# Attach or print info based on context
if [ -n "$TMUX" ]; then
  echo "Already in tmux. Switch with: tmux switch-client -t $SESSION_NAME"
else
  echo "Attaching to session..."
  exec tmux attach-session -t "$SESSION_NAME"
fi
