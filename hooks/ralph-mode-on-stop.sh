#!/bin/bash
# Stop hook: In Ralph mode, block stop if IMPLEMENTATION_PLAN.md wasn't updated
# Replaces the prompt-based hook to avoid "No assistant message found" errors

input=$(cat)

# Prevent infinite loops
stop_hook_active=$(echo "$input" | jq -r '.stop_hook_active // false' 2>/dev/null)
if [ "$stop_hook_active" = "true" ]; then
    exit 0
fi

# Only active in Ralph mode
if [ "${RALPH_MODE}" != "1" ]; then
    exit 0
fi

cd "$CLAUDE_PROJECT_DIR" || exit 0

# Find the implementation plan
plan_file=""
for candidate in IMPLEMENTATION_PLAN.md .claude/plans/IMPLEMENTATION_PLAN.md; do
    if [ -f "$candidate" ]; then
        plan_file="$candidate"
        break
    fi
done

if [ -z "$plan_file" ]; then
    # No plan file found — nothing to check
    exit 0
fi

# Check if the plan file was modified in the working tree (staged or unstaged)
plan_changed=$(git diff --name-only -- "$plan_file" 2>/dev/null; git diff --cached --name-only -- "$plan_file" 2>/dev/null)

if [ -n "$plan_changed" ]; then
    # Plan was updated — all good
    exit 0
fi

# Check if there were any code changes at all
code_changes=$(git diff --name-only 2>/dev/null; git diff --cached --name-only 2>/dev/null)
if [ -z "$code_changes" ]; then
    # No code changes — nothing to enforce
    exit 0
fi

# Code was changed but plan wasn't updated — block
echo '{"decision": "block", "reason": "Ralph mode: IMPLEMENTATION_PLAN.md was not updated. Mark the completed task as done and add any learnings before exiting."}'
exit 0
