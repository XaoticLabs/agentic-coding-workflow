#!/bin/bash
# Stop hook: Suggest /agentic-coding-workflow:update-rules if the session had user corrections
# Replaces the prompt-based hook to avoid "No assistant message found" errors

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
source "${SCRIPT_DIR}/lib/common.sh"

input=$(read_hook_input)
check_stop_hook_active "$input" && exit 0

# Get transcript path
transcript_path=$(echo "$input" | jq -r '.transcript_path // empty' 2>/dev/null)
if [ -z "$transcript_path" ] || [ ! -f "$transcript_path" ]; then
    exit 0
fi

# Check for meaningful conversation (need at least a few exchanges)
message_count=$(jq -s '[.[] | select(.type == "human" or .type == "assistant")] | length' "$transcript_path" 2>/dev/null)
if [ -z "$message_count" ] || [ "$message_count" -lt 4 ]; then
    exit 0
fi

# Look for correction signals in user messages
# Common patterns: "no", "don't", "stop", "wrong", "instead", "actually", "not that"
correction_count=$(jq -rs '
    [.[] | select(.type == "human") |
        .message.content |
        if type == "array" then
            map(select(.type == "text") | .text) | join(" ")
        elif type == "string" then
            .
        else
            ""
        end |
        select(test("\\b(no[,.]? |don.t |stop |wrong|instead |actually |not that|shouldn.t|please don)"; "i"))
    ] | length
' "$transcript_path" 2>/dev/null)

if [ -n "$correction_count" ] && [ "$correction_count" -gt 0 ]; then
    echo "Note: This session had ~${correction_count} user correction(s). Consider running /agentic-coding-workflow:update-rules to capture any patterns worth remembering."
fi

exit 0
