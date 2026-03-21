#!/bin/bash
# Ralph loop — drives autonomous Claude iterations
# Each iteration: pick task → implement → test → commit → update plan → exit
#
# Usage: loop.sh <spec-dir> [mode] [max-iterations] [--push]
#   spec-dir:       Path to the spec directory containing IMPLEMENTATION_PLAN.md
#   mode:           "build" (default) or "plan"
#   max-iterations: Maximum iterations before stopping (default: 50)
#   --push:         Push to remote after each commit

set -euo pipefail

SPEC_DIR="${1:?Usage: loop.sh <spec-dir> [mode] [max-iterations] [--push]}"
MODE="${2:-build}"
MAX_ITERATIONS="${3:-50}"
PUSH_FLAG=""

# Check for --push in any position
for arg in "$@"; do
  [ "$arg" = "--push" ] && PUSH_FLAG="1"
done

PLAN_FILE="${SPEC_DIR}/IMPLEMENTATION_PLAN.md"
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
LOG_DIR="${PROJECT_DIR}/.claude/ralph-logs"
STOP_SENTINEL="${PROJECT_DIR}/.claude/ralph-stop"
PROMPT_DIR="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$(realpath "$0")")")}/references"

mkdir -p "$LOG_DIR"

# ── Resolve prompt template ─────────────────────────────────────────────

case "$MODE" in
  plan)  PROMPT_TEMPLATE="${PROMPT_DIR}/PROMPT_plan.md" ;;
  build) PROMPT_TEMPLATE="${PROMPT_DIR}/PROMPT_build.md" ;;
  *)     echo "Error: mode must be 'plan' or 'build'"; exit 1 ;;
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
echo "║                                                     ║"
echo "║  Stop gracefully: touch .claude/ralph-stop          ║"
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

# ── Main loop ───────────────────────────────────────────────────────────

ITERATION=0

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

  # Build the prompt with spec directory context
  PROMPT=$(cat "$PROMPT_TEMPLATE")
  PROMPT="${PROMPT}

---
**Spec directory:** ${SPEC_DIR}
**Plan file:** ${PLAN_FILE}
**Iteration:** ${ITERATION}
"

  # Run Claude
  echo "Launching Claude (${MODE} mode)..."
  if echo "$PROMPT" | claude -p \
    --dangerously-skip-permissions \
    --model sonnet \
    > "$LOG_FILE" 2>&1; then
    echo "Iteration ${ITERATION} completed successfully."
  else
    echo "Iteration ${ITERATION} exited with error (code $?). Check ${LOG_FILE}"
  fi

  # Push if requested
  if [ -n "$PUSH_FLAG" ]; then
    git push 2>/dev/null || echo "Push failed (non-fatal)"
  fi

  echo ""
done

echo ""
echo "━━━ Ralph loop finished after ${ITERATION} iterations ━━━"
echo "Logs: ${LOG_DIR}/"

# Show final plan status
if [ -f "$PLAN_FILE" ]; then
  echo ""
  echo "Plan status:"
  grep -E "^## Status:|^\- \[[ x]\]" "$PLAN_FILE" | head -20
fi
