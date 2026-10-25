#!/bin/bash
# Shared utilities for hook scripts
HOOK_LIBRARY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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

# Follow hook cwd after native EnterWorktree; never verify the old checkout.
# Usage: cd_project "$input"
cd_project() {
  local directory input="${1:-}"
  [ -n "$input" ] || input='{}'
  if ! directory=$(printf '%s\n' "$input" | python3 "${HOOK_LIBRARY_DIR}/../project_directory.py") || ! cd "$directory"; then
    echo '{"decision":"block","reason":"Cannot enter the active checkout. Verification is unavailable; completion has not been verified."}'
    exit 0
  fi
}
