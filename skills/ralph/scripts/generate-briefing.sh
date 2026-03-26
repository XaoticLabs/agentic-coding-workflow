#!/usr/bin/env bash
# Generate a structured briefing for the next Ralph iteration.
# Extracts signal from the plan, journal, and recent git history.
# Keeps the context window focused — equivalent to autoresearch's
# "grep for the metric, not the full training log" pattern.
#
# Usage: generate-briefing.sh <plan-file> <journal-file> <iteration>
# Output: markdown briefing on stdout

set -euo pipefail

PLAN_FILE="${1:?Usage: generate-briefing.sh <plan-file> <journal-file> <iteration> [trace-file]}"
JOURNAL_FILE="${2:?}"
ITERATION="${3:?}"
TRACE_FILE="${4:-}"

# ── Remaining tasks (compact) ──────────────────────────────────────

echo "### Remaining Tasks"
if [ -f "$PLAN_FILE" ]; then
  REMAINING=$(grep '^\- \[ \] \*\*Task' "$PLAN_FILE" || true)
  if [ -n "$REMAINING" ]; then
    echo "$REMAINING"
  else
    echo "(none — all tasks complete)"
  fi
else
  echo "(no plan file found)"
fi
echo ""

# ── Recent outcomes (prefer trace, fall back to journal) ───────────

echo "### Recent Outcomes"
if [ -n "$TRACE_FILE" ] && [ -f "$TRACE_FILE" ]; then
  # Extract recent verdicts from trace
  RECENT_VERDICTS=$(grep '"type":"verdict"' "$TRACE_FILE" 2>/dev/null | tail -8)
  if [ -n "$RECENT_VERDICTS" ]; then
    echo '```'
    echo "$RECENT_VERDICTS" | while IFS= read -r line; do
      outcome=$(echo "$line" | sed 's/.*"outcome":"\([^"]*\)".*/\1/')
      task=$(echo "$line" | sed 's/.*"task":"\([^"]*\)".*/\1/')
      iter=$(echo "$line" | sed 's/.*"iter":\([0-9]*\).*/\1/')
      printf "%-15s iter=%-3s %s\n" "$outcome" "$iter" "$task"
    done
    echo '```'

    # Check for recent failures
    RECENT_FAILURES=$(echo "$RECENT_VERDICTS" | grep -E 'REVERT|TIMEOUT|NO_COMMIT' || true)
    if [ -n "$RECENT_FAILURES" ]; then
      echo ""
      echo "**Warning:** Recent failures detected. Review the notes above before retrying the same approach."

      # Extract gate failure details from trace
      GATE_FAILURES=$(grep '"type":"gate"' "$TRACE_FILE" 2>/dev/null | grep '"passed":false' | tail -3)
      if [ -n "$GATE_FAILURES" ]; then
        echo ""
        echo "**Recent gate failures (from trace):**"
        echo '```'
        echo "$GATE_FAILURES" | while IFS= read -r line; do
          gate=$(echo "$line" | sed 's/.*"gate":"\([^"]*\)".*/\1/')
          tail_output=$(echo "$line" | sed 's/.*"output_tail":"\([^"]*\)".*/\1/' | head -c 200)
          echo "Gate: ${gate}"
          [ -n "$tail_output" ] && [ "$tail_output" != "$line" ] && echo "  ${tail_output}"
        done
        echo '```'
      fi
    fi
  else
    echo "(no verdict events in trace yet)"
  fi
elif [ -f "$JOURNAL_FILE" ] && [ "$(wc -l < "$JOURNAL_FILE")" -gt 1 ]; then
  echo '```'
  # Skip header, show last 8 entries
  tail -n +2 "$JOURNAL_FILE" | tail -8 | while IFS=$'\t' read -r ts outcome task metric notes; do
    printf "%-7s %-25s %s\n" "$outcome" "$task" "$notes"
  done
  echo '```'

  # Call out recent failures explicitly
  RECENT_FAILURES=$(tail -n +2 "$JOURNAL_FILE" | tail -8 | grep -E 'REVERT|TIMEOUT|NO_COMMIT' || true)
  if [ -n "$RECENT_FAILURES" ]; then
    echo ""
    echo "**Warning:** Recent failures detected. Review the notes above before retrying the same approach."

    # Include actual error output from revert reason files
    LOG_DIR=$(dirname "$JOURNAL_FILE")/ralph-logs
    if [ -d "$LOG_DIR" ]; then
      REASON_FILES=$(find "$LOG_DIR" -name 'revert-*-reason.txt' -type f 2>/dev/null | sort -r | head -3)
      if [ -n "$REASON_FILES" ]; then
        echo ""
        echo "**Recent revert details (actual errors):**"
        for rf in $REASON_FILES; do
          echo '```'
          head -15 "$rf"
          echo '```'
        done
      fi
    fi
  fi
else
  echo "(no journal entries yet)"
fi
echo ""

# ── Active learnings (from plan) ───────────────────────────────────

echo "### Active Learnings"
if [ -f "$PLAN_FILE" ]; then
  # Extract learnings section (between ## Learnings and next ##)
  LEARNINGS=$(sed -n '/^## Learnings/,/^## /{ /^## Learnings/d; /^## /d; p; }' "$PLAN_FILE" | head -20)
  if [ -n "$LEARNINGS" ] && [ "$(echo "$LEARNINGS" | grep -c '[^ ]')" -gt 0 ]; then
    echo "$LEARNINGS"
  else
    echo "(none yet)"
  fi
else
  echo "(no plan file)"
fi
echo ""

# ── Files changed recently (conflict awareness) ───────────────────

echo "### Recently Modified Files"
RECENT_FILES=$(git log --oneline --name-only -5 2>/dev/null | grep -v '^[a-f0-9]' | sort -u | head -15 || true)
if [ -n "$RECENT_FILES" ]; then
  echo '```'
  echo "$RECENT_FILES"
  echo '```'
else
  echo "(no recent commits)"
fi
echo ""

# ── Trend metrics (if enough data) ─────────────────────────────────

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
TOTAL_JOURNAL_LINES=$(($(wc -l < "$JOURNAL_FILE") - 1))
if [ "$TOTAL_JOURNAL_LINES" -ge 6 ] && [ -x "${SCRIPT_DIR}/generate-metrics.sh" ]; then
  echo "### Trend Analysis"
  # Only include failure patterns and timeline — skip full task table to save tokens
  "${SCRIPT_DIR}/generate-metrics.sh" "$JOURNAL_FILE" "" "$TRACE_FILE" 2>/dev/null | awk '/^### Failure Patterns/,0' || true
  echo ""
fi

# ── Iteration stats ───────────────────────────────────────────────

echo "### Stats"
if [ -n "$TRACE_FILE" ] && [ -f "$TRACE_FILE" ]; then
  KEEPS=$(grep -c '"outcome":"KEEP"' "$TRACE_FILE" 2>/dev/null || echo 0)
  REVERTS=$(grep -c '"outcome":"REVERT' "$TRACE_FILE" 2>/dev/null || echo 0)
  TIMEOUTS=$(grep -c '"outcome":"TIMEOUT"' "$TRACE_FILE" 2>/dev/null || echo 0)
  TOTAL_VERDICTS=$((KEEPS + REVERTS + TIMEOUTS))
  echo "- Iteration: ${ITERATION}"
  echo "- Verdicts: ${TOTAL_VERDICTS} (${KEEPS} kept, ${REVERTS} reverted, ${TIMEOUTS} timed out)"
  TOOL_CALLS=$(grep -c '"type":"tool_call"' "$TRACE_FILE" 2>/dev/null || echo 0)
  echo "- Tool calls so far: ${TOOL_CALLS}"
  if [ "$TOTAL_VERDICTS" -gt 0 ]; then
    SUCCESS_RATE=$((KEEPS * 100 / TOTAL_VERDICTS))
    echo "- Success rate: ${SUCCESS_RATE}%"
  fi
elif [ -f "$JOURNAL_FILE" ]; then
  TOTAL_ENTRIES=$(($(wc -l < "$JOURNAL_FILE") - 1))  # minus header
  KEEPS=$(grep -c 'KEEP' "$JOURNAL_FILE" 2>/dev/null || true)
  KEEPS=${KEEPS:-0}
  REVERTS=$(grep -c 'REVERT' "$JOURNAL_FILE" 2>/dev/null || true)
  REVERTS=${REVERTS:-0}
  TIMEOUTS=$(grep -c 'TIMEOUT' "$JOURNAL_FILE" 2>/dev/null || true)
  TIMEOUTS=${TIMEOUTS:-0}
  echo "- Iteration: ${ITERATION}"
  echo "- Journal entries: ${TOTAL_ENTRIES} (${KEEPS} kept, ${REVERTS} reverted, ${TIMEOUTS} timed out)"
  if [ "$TOTAL_ENTRIES" -gt 0 ]; then
    SUCCESS_RATE=$((KEEPS * 100 / TOTAL_ENTRIES))
    echo "- Success rate: ${SUCCESS_RATE}%"
  fi
fi
