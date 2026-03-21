#!/usr/bin/env bash
# Ralph loop — drives autonomous Claude iterations
# Each iteration: pick task → implement → test → commit → update plan → exit
#
# Usage: loop.sh <spec-dir> [mode] [max-iterations] [flags...]
#   spec-dir:       Path to the spec directory containing IMPLEMENTATION_PLAN.md
#   mode:           "build" (default), "plan", or "harvest"
#   max-iterations: Maximum iterations before stopping (default: 50)
#   --push:         Push to remote after each commit
#   --once:         Run a single iteration then stop (HITL mode)
#   --clean-room:   Skip codebase search (greenfield mode)
#   --pr:           Create/update a draft PR after first commit

set -euo pipefail

SPEC_DIR="${1:?Usage: loop.sh <spec-dir> [mode] [max-iterations] [flags...]}"
MODE="${2:-build}"
MAX_ITERATIONS="${3:-50}"
PUSH_FLAG=""
ONCE_FLAG=""
CLEAN_ROOM_FLAG=""
PR_FLAG=""

# Check for flags in any position
for arg in "$@"; do
  case "$arg" in
    --push)       PUSH_FLAG="1" ;;
    --once)       ONCE_FLAG="1" ;;
    --clean-room) CLEAN_ROOM_FLAG="1" ;;
    --pr)         PR_FLAG="1" ;;
  esac
done

PLAN_FILE="${SPEC_DIR}/IMPLEMENTATION_PLAN.md"
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
LOG_DIR="${PROJECT_DIR}/.claude/ralph-logs"
STOP_SENTINEL="${PROJECT_DIR}/.claude/ralph-stop"
STATUS_FILE="${PROJECT_DIR}/.claude/ralph-status.md"
INJECT_FILE="${PROJECT_DIR}/.claude/ralph-inject.md"
PROGRESS_FILE="${PROJECT_DIR}/.claude/ralph-progress.md"
SCRIPT_DIR="$(dirname "$(realpath "$0")")"
PROMPT_DIR="${SCRIPT_DIR}/../references"

mkdir -p "$LOG_DIR"

# ── Resolve prompt template ─────────────────────────────────────────────

case "$MODE" in
  plan)      PROMPT_TEMPLATE="${PROMPT_DIR}/PROMPT_plan.md" ;;
  build)     PROMPT_TEMPLATE="${PROMPT_DIR}/PROMPT_build.md" ;;
  harvest)   PROMPT_TEMPLATE="${PROMPT_DIR}/PROMPT_harvest.md" ;;
  reconcile) PROMPT_TEMPLATE="${PROMPT_DIR}/PROMPT_reconcile.md" ;;
  *)         echo "Error: mode must be 'plan', 'build', 'harvest', or 'reconcile'"; exit 1 ;;
esac

if [ ! -f "$PROMPT_TEMPLATE" ]; then
  echo "Error: prompt template not found: $PROMPT_TEMPLATE"
  exit 1
fi

# ── Safety warning ──────────────────────────────────────────────────────

echo "╔══════════════════════════════════════════════════════╗"
echo "║  RALPH LOOP — Autonomous Coding Mode                ║"
echo "║                                                     ║"
echo "║  Mode:       ${MODE}                                "
echo "║  Spec dir:   ${SPEC_DIR}                            "
echo "║  Max iters:  ${MAX_ITERATIONS}                      "
echo "║  Push:       ${PUSH_FLAG:-no}                       "
echo "║  Once:       ${ONCE_FLAG:-no}                       "
echo "║  Clean-room: ${CLEAN_ROOM_FLAG:-no}                 "
echo "║  PR:         ${PR_FLAG:-no}                         "
echo "║                                                     ║"
echo "║  Stop gracefully: touch .claude/ralph-stop          ║"
echo "║  Steer mid-loop:  write .claude/ralph-inject.md     ║"
echo "║  This uses --dangerously-skip-permissions           ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Pre-flight checks ──────────────────────────────────────────────────

if [ "$MODE" = "build" ] && [ ! -f "$PLAN_FILE" ]; then
  echo "Error: No IMPLEMENTATION_PLAN.md found at ${PLAN_FILE}"
  echo "Run with mode=plan first, or create the plan via /write-spec --ralph"
  exit 1
fi

# Clean up any previous stop sentinel
rm -f "$STOP_SENTINEL"

# ── Struggle detection helpers ──────────────────────────────────────────

LAST_TASK=""
SAME_TASK_COUNT=0
STRUGGLE_THRESHOLD=3

# Extract the current top-priority incomplete task name from the plan
get_current_task() {
  if [ -f "$PLAN_FILE" ]; then
    grep -m1 '^\- \[ \] \*\*Task' "$PLAN_FILE" 2>/dev/null | sed 's/.*\*\*Task [0-9]*: \(.*\)\*\*.*/\1/' || echo ""
  fi
}

# ── Circuit breaker helpers ─────────────────────────────────────────────

COMMITS_AT_START=$(git rev-list --count HEAD 2>/dev/null || echo "0")
CIRCUIT_BREAKER_WINDOW=5     # Check every N iterations
CIRCUIT_BREAKER_MIN_RATIO=30 # Minimum commit% (commits/iterations * 100)

check_circuit_breaker() {
  local iteration=$1
  if [ "$iteration" -lt "$CIRCUIT_BREAKER_WINDOW" ]; then
    return 0  # Too early to judge
  fi

  # Only check at window boundaries
  if [ $((iteration % CIRCUIT_BREAKER_WINDOW)) -ne 0 ]; then
    return 0
  fi

  local commits_now
  commits_now=$(git rev-list --count HEAD 2>/dev/null || echo "0")
  local new_commits=$((commits_now - COMMITS_AT_START))
  local ratio=$((new_commits * 100 / iteration))

  if [ "$ratio" -lt "$CIRCUIT_BREAKER_MIN_RATIO" ]; then
    echo ""
    echo "⚡ CIRCUIT BREAKER: Only ${new_commits} commits in ${iteration} iterations (${ratio}% success rate)."
    echo "   Threshold is ${CIRCUIT_BREAKER_MIN_RATIO}%. Ralph may be spinning."
    echo "   Stopping to prevent token waste. Check logs and plan for issues."
    return 1
  fi
  return 0
}

# ── Progress dashboard writer ───────────────────────────────────────────

write_status() {
  local iteration=$1
  local task_name=$2
  local result=$3

  local total_tasks=0 done_tasks=0
  if [ -f "$PLAN_FILE" ]; then
    total_tasks=$(grep -c '^\- \[[ x]\] \*\*Task' "$PLAN_FILE" 2>/dev/null || echo "0")
    done_tasks=$(grep -c '^\- \[x\] \*\*Task' "$PLAN_FILE" 2>/dev/null || echo "0")
  fi

  local commits_now
  commits_now=$(git rev-list --count HEAD 2>/dev/null || echo "0")
  local new_commits=$((commits_now - COMMITS_AT_START))
  local elapsed=$(($(date +%s) - START_TIME))
  local minutes=$((elapsed / 60))

  cat > "$STATUS_FILE" <<EOF
# Ralph Status Dashboard

**Last updated:** $(date)
**Spec:** ${SPEC_DIR}
**Mode:** ${MODE}

## Progress

- **Iteration:** ${iteration} / ${MAX_ITERATIONS}
- **Tasks:** ${done_tasks} / ${total_tasks} complete
- **Commits:** ${new_commits} in this run
- **Elapsed:** ${minutes} minutes
- **Success rate:** $( [ "$iteration" -gt 0 ] && echo "$((new_commits * 100 / iteration))%" || echo "N/A" )
- **Last task:** ${task_name}
- **Last result:** ${result}

## Recent Iterations

$(tail -20 "${LOG_DIR}/ralph-iterations.log" 2>/dev/null || echo "(no iteration log yet)")
EOF
}

# ── Main loop ───────────────────────────────────────────────────────────

ITERATION=0
START_TIME=$(date +%s)

# Initialize iteration log
echo "# Ralph Iteration Log — $(date)" > "${LOG_DIR}/ralph-iterations.log"

while :; do
  ITERATION=$((ITERATION + 1))
  TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
  LOG_FILE="${LOG_DIR}/iter-${ITERATION}-${TIMESTAMP}.log"

  echo "━━━ Iteration ${ITERATION}/${MAX_ITERATIONS} ━━━ $(date) ━━━"

  # Check stop sentinel
  if [ -f "$STOP_SENTINEL" ]; then
    echo "Stop sentinel found. Exiting gracefully."
    rm -f "$STOP_SENTINEL"
    break
  fi

  # Check if plan is complete (build mode only)
  if [ "$MODE" = "build" ] && [ -f "$PLAN_FILE" ]; then
    if grep -q "## Status: COMPLETE" "$PLAN_FILE"; then
      echo "All tasks complete! Plan status: COMPLETE"
      break
    fi
  fi

  # Check max iterations
  if [ "$ITERATION" -gt "$MAX_ITERATIONS" ]; then
    echo "Max iterations (${MAX_ITERATIONS}) reached. Stopping."
    break
  fi

  # ── Struggle detection ──────────────────────────────────────────────
  if [ "$MODE" = "build" ]; then
    CURRENT_TASK=$(get_current_task)
    if [ -n "$CURRENT_TASK" ] && [ "$CURRENT_TASK" = "$LAST_TASK" ]; then
      SAME_TASK_COUNT=$((SAME_TASK_COUNT + 1))
      if [ "$SAME_TASK_COUNT" -ge "$STRUGGLE_THRESHOLD" ]; then
        echo ""
        echo "⚠ STRUGGLE DETECTED: Task '${CURRENT_TASK}' has been attempted ${SAME_TASK_COUNT} times."
        echo "  Ralph may be stuck. Stopping to prevent token waste."
        echo "  Review logs and consider breaking the task down or adding context."
        echo "${ITERATION} | $(date +%H:%M:%S) | STRUGGLE_STOP | ${CURRENT_TASK}" >> "${LOG_DIR}/ralph-iterations.log"
        write_status "$ITERATION" "$CURRENT_TASK" "STRUGGLE_STOP"
        break
      fi
      echo "⚠ Retry ${SAME_TASK_COUNT}/${STRUGGLE_THRESHOLD} on task: ${CURRENT_TASK}"
    else
      SAME_TASK_COUNT=0
      LAST_TASK="$CURRENT_TASK"
    fi
  fi

  # ── Circuit breaker ─────────────────────────────────────────────────
  if ! check_circuit_breaker "$ITERATION"; then
    echo "${ITERATION} | $(date +%H:%M:%S) | CIRCUIT_BREAK | low commit ratio" >> "${LOG_DIR}/ralph-iterations.log"
    write_status "$ITERATION" "${CURRENT_TASK:-unknown}" "CIRCUIT_BREAK"
    break
  fi

  # ── Build the prompt ────────────────────────────────────────────────
  PROMPT=$(cat "$PROMPT_TEMPLATE")

  # Clean-room mode: strip codebase search step
  if [ -n "$CLEAN_ROOM_FLAG" ] && [ "$MODE" = "build" ]; then
    PROMPT=$(awk '/^## Step 3: Search Before Implementing/{skip=1; next} /^## Step 4/{skip=0} !skip' <<< "$PROMPT")
    PROMPT="${PROMPT}

**Clean-room mode:** Do NOT search the existing codebase. Implement from spec only — this is greenfield work."
  fi

  # Mid-loop injection: append user steering if present
  if [ -f "$INJECT_FILE" ]; then
    echo "📋 Injecting mid-loop instructions from .claude/ralph-inject.md"
    PROMPT="${PROMPT}

---
## Mid-Loop Steering (from user)

$(cat "$INJECT_FILE")
"
    rm -f "$INJECT_FILE"
  fi

  # Targeted spec loading: extract spec file for current task
  TASK_SPEC=""
  if [ "$MODE" = "build" ] && [ -f "$PLAN_FILE" ]; then
    TASK_SPEC=$(grep -m1 '^\- \[ \] \*\*Task' "$PLAN_FILE" 2>/dev/null | grep -o 'Spec: [^ ]*' | sed 's/Spec: //' || echo "")
  fi

  PROMPT="${PROMPT}

---
**Spec directory:** ${SPEC_DIR}
**Plan file:** ${PLAN_FILE}
**Iteration:** ${ITERATION}
$( [ -n "$TASK_SPEC" ] && echo "**Current task spec file:** ${SPEC_DIR}/${TASK_SPEC}" || true )
"

  # Run Claude
  echo "Launching Claude (${MODE} mode)..."
  ITER_RESULT="success"
  if echo "$PROMPT" | claude -p \
    --dangerously-skip-permissions \
    --model sonnet \
    > "$LOG_FILE" 2>&1; then
    echo "Iteration ${ITERATION} completed successfully."
  else
    ITER_RESULT="error (code $?)"
    echo "Iteration ${ITERATION} exited with error (code $?). Check ${LOG_FILE}"
  fi

  # Log iteration
  echo "${ITERATION} | $(date +%H:%M:%S) | ${ITER_RESULT} | ${CURRENT_TASK:-plan}" >> "${LOG_DIR}/ralph-iterations.log"

  # Update status dashboard
  write_status "$ITERATION" "${CURRENT_TASK:-plan}" "$ITER_RESULT"

  # Push if requested
  if [ -n "$PUSH_FLAG" ]; then
    git push 2>/dev/null || echo "Push failed (non-fatal)"
  fi

  # Auto-create/update draft PR if --pr flag
  if [ -n "$PR_FLAG" ] && [ -n "$PUSH_FLAG" ]; then
    if [ "$ITERATION" -eq 1 ]; then
      # Create draft PR on first iteration
      BRANCH=$(git branch --show-current)
      if [ "$BRANCH" != "main" ] && [ "$BRANCH" != "master" ]; then
        echo "Creating draft PR..."
        gh pr create --draft --title "Ralph: $(basename "$SPEC_DIR")" \
          --body "Autonomous implementation via Ralph loop.

Spec: \`${SPEC_DIR}\`
Mode: ${MODE}

_This PR is updated automatically by the Ralph loop._" 2>/dev/null || echo "PR creation failed (may already exist)"
      fi
    fi
  fi

  # --once mode: exit after single iteration
  if [ -n "$ONCE_FLAG" ]; then
    echo ""
    echo "━━━ Single iteration complete (--once mode) ━━━"
    break
  fi

  echo ""
done

# ── Write worker completion marker ─────────────────────────────────────

WORKER_ID="${RALPH_WORKER_ID:-}"
if [ -n "$WORKER_ID" ]; then
  MARKER_FILE="${PROJECT_DIR}/.claude/ralph-worker-done-${WORKER_ID}"
  echo "{\"worker\": \"${WORKER_ID}\", \"status\": \"done\", \"iterations\": ${ITERATION}, \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" \
    > "$MARKER_FILE"
  echo "Worker completion marker written: ${MARKER_FILE}"
fi

echo ""
echo "━━━ Ralph loop finished after ${ITERATION} iterations ━━━"
echo "Logs: ${LOG_DIR}/"
echo "Status: ${STATUS_FILE}"

# Show final plan status
if [ -f "$PLAN_FILE" ]; then
  echo ""
  echo "Plan status:"
  grep -E "^## Status:|^\- \[[ x]\]" "$PLAN_FILE" | head -20
fi

# Clean up ephemeral progress file
if [ -f "$PROGRESS_FILE" ]; then
  rm -f "$PROGRESS_FILE"
  echo "(Cleaned up ephemeral progress scratchpad)"
fi
