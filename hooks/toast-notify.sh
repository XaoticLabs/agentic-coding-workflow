#!/bin/bash
# Toast notification when Claude Code stops - extracts context from transcript

input=$(cat)
transcript_path=$(echo "$input" | jq -r '.transcript_path // empty' 2>/dev/null)

title="Claude Code"
message="Needs your attention"

if [[ -n "$transcript_path" && -f "$transcript_path" ]]; then
    # Get the last meaningful content from the transcript.
    # A Stop hook fires AFTER Claude's turn is complete, so any tool_use
    # in the last assistant message has already been resolved (there will be
    # a tool_result following it). We only show "Approve X?" if the very
    # last tool_use has NO matching tool_result — meaning it's genuinely
    # waiting for user approval.
    last_msg=$(jq -rs '
        # Collect all entries
        . as $all |

        # Find the last assistant message
        ([.[] | select(.type == "assistant")] | last) as $last_asst |

        # Collect all tool_result tool_use_ids from user messages
        # (tool_results are nested inside user message content arrays)
        ([.[] | select(.type == "user") | .message.content // [] |
          if type == "array" then .[] else empty end |
          select(.type == "tool_result") | .tool_use_id] | unique) as $resolved_ids |

        if $last_asst == null then empty
        elif ($last_asst.message.content | type) != "array" then
            $last_asst.message.content
        else
            # Extract text from the last assistant message
            ($last_asst.message.content | map(select(.type == "text") | .text) | join(" ")) as $text |
            # Extract the last tool_use if any
            ($last_asst.message.content | map(select(.type == "tool_use")) | last) as $tool |

            # Check if that tool_use has a matching tool_result
            (if $tool then
                ($resolved_ids | index($tool.id)) != null
            else
                true
            end) as $tool_resolved |

            if ($text | length) > 0 then
                $text
            elif $tool and ($tool_resolved | not) then
                "TOOL:" + $tool.name
            else
                empty
            end
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
