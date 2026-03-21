#!/bin/bash
# collect-pane-outputs.sh - Capture output from all panes in current window/session
#
# Usage: collect-pane-outputs.sh [options]
# Example: collect-pane-outputs.sh > results.txt
# Example: collect-pane-outputs.sh --session my-project --lines 500
# Example: collect-pane-outputs.sh --all-windows --format json
#
# Options:
#   --session      Target session (default: current)
#   --window       Target window (default: current)
#   --all-windows  Capture from all windows in session
#   --lines        Number of lines to capture (default: 1000)
#   --format       Output format: text (default) or json
#   --output       Write to file instead of stdout
#   --tail         Only capture last N lines (alternative to --lines)

set -e

RED='\033[0;31m'
NC='\033[0m'

error() { echo -e "${RED}Error: $1${NC}" >&2; exit 1; }

# Check tmux
command -v tmux >/dev/null 2>&1 || error "tmux is not installed"
[ -z "$TMUX" ] && [ -z "$TARGET_SESSION" ] && error "Not in tmux. Specify --session or run from within tmux"

# Default values
TARGET_SESSION=""
TARGET_WINDOW=""
ALL_WINDOWS=false
LINES=1000
FORMAT="text"
OUTPUT_FILE=""
TAIL_MODE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --session)
      TARGET_SESSION="$2"
      shift 2
      ;;
    --window)
      TARGET_WINDOW="$2"
      shift 2
      ;;
    --all-windows)
      ALL_WINDOWS=true
      shift
      ;;
    --lines)
      LINES="$2"
      shift 2
      ;;
    --tail)
      LINES="$2"
      TAIL_MODE=true
      shift 2
      ;;
    --format)
      FORMAT="$2"
      shift 2
      ;;
    --output)
      OUTPUT_FILE="$2"
      shift 2
      ;;
    *)
      error "Unknown option: $1"
      ;;
  esac
done

# Validate format
[[ "$FORMAT" =~ ^(text|json)$ ]] || error "Format must be 'text' or 'json'"

# Build target specification
TARGET=""
if [ -n "$TARGET_SESSION" ]; then
  TARGET="$TARGET_SESSION"
  [ -n "$TARGET_WINDOW" ] && TARGET="$TARGET:$TARGET_WINDOW"
elif [ -n "$TARGET_WINDOW" ]; then
  TARGET=":$TARGET_WINDOW"
fi

# Function to capture single pane
capture_pane() {
  local pane_target="$1"
  local pane_info="$2"

  if $TAIL_MODE; then
    tmux capture-pane -t "$pane_target" -p -S "-$LINES" 2>/dev/null || echo "(capture failed)"
  else
    tmux capture-pane -t "$pane_target" -p -S "-$LINES" 2>/dev/null || echo "(capture failed)"
  fi
}

# Function to output in text format
output_text() {
  local window_name="$1"
  local pane_index="$2"
  local pane_cmd="$3"
  local content="$4"

  echo "================================================================================"
  echo "Window: $window_name | Pane: $pane_index | Command: $pane_cmd"
  echo "================================================================================"
  echo "$content"
  echo ""
}

# Function to escape JSON string
json_escape() {
  printf '%s' "$1" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' 2>/dev/null || \
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\t/\\t/g' | sed ':a;N;$!ba;s/\n/\\n/g' | sed 's/^/"/;s/$/"/'
}

# Collect output
collect() {
  local first_json=true

  [ "$FORMAT" = "json" ] && echo "{"
  [ "$FORMAT" = "json" ] && echo '  "panes": ['

  # Get windows to process
  if $ALL_WINDOWS; then
    windows=$(tmux list-windows ${TARGET:+-t "$TARGET"} -F "#{window_index}:#{window_name}" 2>/dev/null)
  else
    windows=$(tmux display-message ${TARGET:+-t "$TARGET"} -p "#{window_index}:#{window_name}" 2>/dev/null)
  fi

  [ -z "$windows" ] && error "No windows found"

  while IFS=: read -r window_index window_name; do
    # Get panes in window
    local win_target="${TARGET_SESSION:-}${TARGET_SESSION:+:}$window_index"
    panes=$(tmux list-panes -t "$win_target" -F "#{pane_index}:#{pane_current_command}" 2>/dev/null)

    while IFS=: read -r pane_index pane_cmd; do
      local pane_target="$win_target.$pane_index"
      local content
      content=$(capture_pane "$pane_target" "$pane_index")

      if [ "$FORMAT" = "json" ]; then
        $first_json || echo ","
        first_json=false
        echo "    {"
        echo "      \"window\": \"$window_name\","
        echo "      \"window_index\": $window_index,"
        echo "      \"pane_index\": $pane_index,"
        echo "      \"command\": \"$pane_cmd\","
        echo "      \"content\": $(json_escape "$content")"
        echo -n "    }"
      else
        output_text "$window_name" "$pane_index" "$pane_cmd" "$content"
      fi
    done <<< "$panes"
  done <<< "$windows"

  [ "$FORMAT" = "json" ] && echo ""
  [ "$FORMAT" = "json" ] && echo "  ]"
  [ "$FORMAT" = "json" ] && echo "}"
}

# Execute
if [ -n "$OUTPUT_FILE" ]; then
  collect > "$OUTPUT_FILE"
  echo "Output written to: $OUTPUT_FILE" >&2
else
  collect
fi
