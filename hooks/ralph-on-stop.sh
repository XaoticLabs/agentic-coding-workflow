#!/bin/bash
# Stop hook: Ralph plan-update enforcement
# Only active when RALPH_MODE=1.
# Blocks if code changed but IMPLEMENTATION_PLAN.md wasn't updated.
# Verification and independent review belong to the outer executor.

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
source "${SCRIPT_DIR}/lib/common.sh"

input=$(read_hook_input)
check_stop_hook_active "$input" && exit 0
check_ralph_mode || exit 0
cd_project "$input"

# ── Plan update enforcement ─────────────────────────────────────────

plan_file=""
for candidate in "${RALPH_PLAN_FILE:-}" IMPLEMENTATION_PLAN.md .claude/plans/IMPLEMENTATION_PLAN.md; do
  if [ -f "$candidate" ]; then
    plan_file="$candidate"
    break
  fi
done

if [ -n "$plan_file" ]; then
  # Ralph supplies the exact iteration base; an arbitrary HEAD~2 misses short
  # histories and can review commits belonging to previous iterations.
  base="${RALPH_PRE_COMMIT:-HEAD}"
  plan_changed=$(git diff --name-only "$base" -- "$plan_file" 2>/dev/null)
  if [ -n "${RALPH_PLAN_BLOB:-}" ] && [ "$(git hash-object -- "$plan_file")" != "$RALPH_PLAN_BLOB" ]; then
    plan_changed="$plan_file"
  fi
  code_changes=$(git diff --name-only "$base" 2>/dev/null)

  if [ -z "$plan_changed" ] && [ -n "$code_changes" ]; then
    echo '{"decision": "block", "reason": "Ralph mode: IMPLEMENTATION_PLAN.md was not updated. Mark the completed task as done and add any learnings before exiting."}'
    exit 0
  fi
fi

exit 0
