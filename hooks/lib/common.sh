#!/bin/bash
# Shared utilities for hook scripts

# Read hook input from stdin (call once, store result)
# Usage: HOOK_INPUT=$(read_hook_input)
read_hook_input() {
  cat
}

# Check if stop_hook_active flag is set (prevents infinite loops)
# Usage: check_stop_hook_active "$input" && exit 0
check_stop_hook_active() {
  local input="$1"
  local active
  active=$(echo "$input" | jq -r '.stop_hook_active // false' 2>/dev/null)
  [ "$active" = "true" ]
}

# Check if Ralph mode is active
# Usage: check_ralph_mode || exit 0
check_ralph_mode() {
  [ "${RALPH_MODE}" = "1" ]
}

# Change to project directory or exit gracefully
# Usage: cd_project
cd_project() {
  cd "$CLAUDE_PROJECT_DIR" || exit 0
}
