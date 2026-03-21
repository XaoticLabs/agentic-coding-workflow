#!/bin/bash
# Toast notification when Claude Code stops - extracts context from transcript

input=$(cat)
transcript_path=$(echo "$input" | jq -r '.transcript_path // empty' 2>/dev/null)

title="Claude Code"
message="Needs your attention"

if [[ -n "$transcript_path" && -f "$transcript_path" ]]; then
    # Get the last assistant message (use -s to slurp JSONL into array)
    last_msg=$(jq -rs '
        [.[] | select(.type == "assistant")] | last |
        if .message.content then
            .message.content | if type == "array" then
                # Check for tool_use first
                (map(select(.type == "tool_use")) | first) as $tool |
                if $tool then
                    "TOOL:" + $tool.name
                else
                    # Get text content
                    (map(select(.type == "text") | .text) | join(" "))
                end
            else
                .
            end
        else
            empty
        end
    ' "$transcript_path" 2>/dev/null)

    if [[ "$last_msg" == TOOL:* ]]; then
        tool_name="${last_msg#TOOL:}"
        case "$tool_name" in
            Bash)
                message="Approve command?"
                ;;
            Write|Edit|MultiEdit)
                message="Approve file changes?"
                ;;
            Task)
                message="Approve background task?"
                ;;
            *)
                message="Approve $tool_name?"
                ;;
        esac
    elif [[ -n "$last_msg" ]]; then
        # Truncate and clean text for notification
        clean_msg=$(echo "$last_msg" | tr '\n' ' ' | sed 's/  */ /g' | cut -c1-80)
        if [[ ${#last_msg} -gt 80 ]]; then
            clean_msg="${clean_msg}..."
        fi
        # Check if it's a question
        if [[ "$clean_msg" == *"?"* ]]; then
            message="$clean_msg"
        else
            message="Done: ${clean_msg}"
        fi
    fi
fi

osascript -e "display notification \"$message\" with title \"$title\""
exit 0
