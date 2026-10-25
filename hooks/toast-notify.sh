#!/usr/bin/env bash
# Stop carries the final rendered response; the transcript may lag behind it.
input=$(cat)
echo "$input" | jq -e 'type == "object"' >/dev/null 2>&1 || exit 0
[ "$(echo "$input" | jq -r '.stop_hook_active // false')" = true ] && exit 0
command -v osascript >/dev/null 2>&1 || exit 0
message=$(echo "$input" | jq -j '.last_assistant_message // "Claude finished responding"' | tr '\n' ' ' | cut -c1-160)
osascript -e 'on run argv
  display notification (item 1 of argv) with title "Claude Code"
end run' -- "$message" >/dev/null 2>&1 || true
exit 0
