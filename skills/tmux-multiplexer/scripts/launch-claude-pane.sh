#!/bin/bash
# launch-claude-pane.sh - Launch Claude Code in a new tmux pane
#
# Usage: launch-claude-pane.sh <prompt> [options]
# Example: launch-claude-pane.sh "Review this code for bugs"
# Example: launch-claude-pane.sh "Explain this file" --context src/main.ts
# Example: launch-claude-pane.sh "Generate tests" --output /tmp/tests.md
#
# Arguments:
#   prompt       Required. The prompt to send to Claude
#
# Options:
#   --context    File to pass as context
#   --output     File to capture output to
#   --split      Split direction: h (horizontal) or v (vertical, default)
#   --size       Pane size as percentage (default: 50)
#   --session    Target session (default: current)
#   --no-attach  Don't select the new pane

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

error() { echo -e "${RED}Error: $1${NC}" >&2; exit 1; }
success() { echo -e "${GREEN}$1${NC}"; }

# Check dependencies
command -v tmux >/dev/null 2>&1 || error "tmux is not installed"
command -v claude >/dev/null 2>&1 || error "claude is not installed"

# Default values
PROMPT=""
CONTEXT_FILE=""
OUTPUT_FILE=""
SPLIT_DIR="v"
PANE_SIZE="50"
TARGET_SESSION=""
NO_ATTACH=false

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --context)
      CONTEXT_FILE="$2"
      shift 2
      ;;
    --output)
      OUTPUT_FILE="$2"
      shift 2
      ;;
    --split)
      SPLIT_DIR="$2"
      shift 2
      ;;
    --size)
      PANE_SIZE="$2"
      shift 2
      ;;
    --session)
      TARGET_SESSION="$2"
      shift 2
      ;;
    --no-attach)
      NO_ATTACH=true
      shift
      ;;
    -*)
      error "Unknown option: $1"
      ;;
    *)
      [ -z "$PROMPT" ] && PROMPT="$1" || PROMPT="$PROMPT $1"
      shift
      ;;
  esac
done

# Validate prompt
[ -z "$PROMPT" ] && error "Prompt required. Usage: $0 <prompt> [options]"

# Validate split direction
[[ "$SPLIT_DIR" =~ ^[hv]$ ]] || error "Split direction must be 'h' or 'v'"

# Validate pane size
if ! [[ "$PANE_SIZE" =~ ^[0-9]+$ ]] || [ "$PANE_SIZE" -lt 10 ] || [ "$PANE_SIZE" -gt 90 ]; then
  error "Pane size must be between 10 and 90"
fi

# Validate context file if provided
if [ -n "$CONTEXT_FILE" ] && [ ! -f "$CONTEXT_FILE" ]; then
  error "Context file not found: $CONTEXT_FILE"
fi

# Check if in tmux
[ -z "$TMUX" ] && [ -z "$TARGET_SESSION" ] && error "Not in tmux and no session specified. Use --session or run from within tmux"

# Build claude command
CLAUDE_CMD="claude -p"

# Escape prompt for shell
ESCAPED_PROMPT=$(printf '%q' "$PROMPT")
CLAUDE_CMD="$CLAUDE_CMD $ESCAPED_PROMPT"

# Add context if provided
if [ -n "$CONTEXT_FILE" ]; then
  CLAUDE_CMD="$CLAUDE_CMD --context $(printf '%q' "$CONTEXT_FILE")"
fi

# Add output redirection if provided
if [ -n "$OUTPUT_FILE" ]; then
  CLAUDE_CMD="$CLAUDE_CMD > $(printf '%q' "$OUTPUT_FILE") 2>&1"
fi

# Build tmux command
TMUX_CMD="tmux split-window -$SPLIT_DIR -p $PANE_SIZE"

if [ -n "$TARGET_SESSION" ]; then
  TMUX_CMD="$TMUX_CMD -t $TARGET_SESSION"
fi

# Execute
echo "Launching Claude in new pane..."
echo "Prompt: $PROMPT"
[ -n "$CONTEXT_FILE" ] && echo "Context: $CONTEXT_FILE"
[ -n "$OUTPUT_FILE" ] && echo "Output: $OUTPUT_FILE"

# Create pane and run claude
eval "$TMUX_CMD \"$CLAUDE_CMD; echo '--- Claude finished ---'; exec bash\""

if [ "$NO_ATTACH" = false ]; then
  # The split-window command already selects the new pane
  success "Claude launched in new pane"
else
  # Go back to original pane
  tmux select-pane -t "{last}"
  success "Claude launched in background pane"
fi
