#!/usr/bin/env bash
# Generate trend analysis metrics from the Ralph failure journal.
# Produces structured insights: failure rates by task, hot files, revert clustering.
#
# Usage: generate-metrics.sh <journal-file> [plan-file]
# Output: markdown metrics on stdout (can be piped into briefing or summary)

set -euo pipefail

JOURNAL_FILE="${1:?Usage: generate-metrics.sh <journal-file> [plan-file]}"
PLAN_FILE="${2:-}"
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
LOG_DIR="${PROJECT_DIR}/.claude/ralph-logs"

if [ ! -f "$JOURNAL_FILE" ] || [ "$(wc -l < "$JOURNAL_FILE")" -le 1 ]; then
  echo "(no journal data for metrics)"
  exit 0
fi

# ── Task failure rates ───────────────────────────────────────────────

echo "### Task Failure Rates"
echo ""

# Count outcomes per task
TASK_STATS=$(tail -n +2 "$JOURNAL_FILE" | awk -F'\t' '
  $3 != "" && $3 != "-" {
    tasks[$3]++
    if ($2 ~ /REVERT/) reverts[$3]++
    if ($2 == "KEEP") keeps[$3]++
    if ($2 == "TIMEOUT") timeouts[$3]++
  }
  END {
    for (t in tasks) {
      r = (t in reverts) ? reverts[t] : 0
      k = (t in keeps) ? keeps[t] : 0
      to = (t in timeouts) ? timeouts[t] : 0
      total = tasks[t]
      if (total > 0) {
        rate = int(r * 100 / total)
        printf "| %-35s | %3d | %3d | %3d | %3d | %3d%% |\n", t, total, k, r, to, rate
      }
    }
  }
' | sort -t'|' -k6 -rn)

if [ -n "$TASK_STATS" ]; then
  echo "| Task | Attempts | Kept | Reverted | Timeouts | Fail% |"
  echo "|------|----------|------|----------|----------|-------|"
  echo "$TASK_STATS"
else
  echo "(no per-task data)"
fi
echo ""

# ── Files most associated with reverts ───────────────────────────────

echo "### Hot Files (associated with reverts)"
echo ""

# Look at revert reason files for file lists
HOT_FILES=""
if [ -d "$LOG_DIR" ]; then
  for reason_file in "$LOG_DIR"/revert-*-reason.txt; do
    [ -f "$reason_file" ] || continue
    # Extract file paths from error output (common patterns in test/lint output)
    grep -oE '[a-zA-Z0-9_/.-]+\.(ex|exs|ts|tsx|js|jsx|py|go|rs|rb)' "$reason_file" 2>/dev/null || true
  done | sort | uniq -c | sort -rn | head -10 > /tmp/ralph-hot-files-$$ 2>/dev/null || true
  HOT_FILES=$(cat /tmp/ralph-hot-files-$$ 2>/dev/null || true)
  rm -f /tmp/ralph-hot-files-$$
fi

if [ -n "$HOT_FILES" ]; then
  echo '```'
  echo "$HOT_FILES"
  echo '```'
  echo ""
  echo "These files appear most often in revert error output. They may need extra attention or better test coverage."
else
  echo "(no revert data to analyze)"
fi
echo ""

# ── Failure clustering (consecutive reverts) ──────────────────────────

echo "### Failure Patterns"
echo ""

# Detect streaks of reverts
STREAK_INFO=$(tail -n +2 "$JOURNAL_FILE" | awk -F'\t' '
  BEGIN { streak=0; max_streak=0; streak_task="" }
  $2 ~ /REVERT/ {
    streak++
    if (streak > max_streak) {
      max_streak = streak
      streak_task = $3
    }
  }
  $2 == "KEEP" { streak=0 }
  END {
    if (max_streak > 0) printf "Longest revert streak: %d (task: %s)\n", max_streak, streak_task
  }
')

# Detect revert-then-success patterns (what changed?)
RETRY_SUCCESS=$(tail -n +2 "$JOURNAL_FILE" | awk -F'\t' '
  $2 ~ /REVERT/ { reverted[$3]++ }
  $2 == "KEEP" && ($3 in reverted) {
    printf "- **%s**: reverted %d time(s) before succeeding\n", $3, reverted[$3]
    delete reverted[$3]
  }
')

if [ -n "$STREAK_INFO" ]; then
  echo "$STREAK_INFO"
fi

if [ -n "$RETRY_SUCCESS" ]; then
  echo ""
  echo "**Retry successes** (tasks that failed then eventually passed):"
  echo "$RETRY_SUCCESS"
fi

# Detect tasks that never succeeded
NEVER_SUCCEEDED=$(tail -n +2 "$JOURNAL_FILE" | awk -F'\t' '
  $2 ~ /REVERT/ { reverted[$3]++ }
  $2 == "KEEP" { delete reverted[$3] }
  END {
    for (t in reverted) {
      if (reverted[t] >= 2) printf "- **%s**: reverted %d times, never succeeded\n", t, reverted[t]
    }
  }
')

if [ -n "$NEVER_SUCCEEDED" ]; then
  echo ""
  echo "**Never succeeded** (reverted 2+ times without a keep):"
  echo "$NEVER_SUCCEEDED"
fi

echo ""

# ── Outcome distribution over time ───────────────────────────────────

echo "### Outcome Timeline"
echo ""
echo "First half vs second half success rate:"

TOTAL_ENTRIES=$(($(wc -l < "$JOURNAL_FILE") - 1))
if [ "$TOTAL_ENTRIES" -ge 4 ]; then
  HALF=$((TOTAL_ENTRIES / 2))

  FIRST_KEEPS=$(tail -n +2 "$JOURNAL_FILE" | head -"$HALF" | grep -c 'KEEP' 2>/dev/null || echo "0")
  SECOND_KEEPS=$(tail -n +2 "$JOURNAL_FILE" | tail -"$HALF" | grep -c 'KEEP' 2>/dev/null || echo "0")

  FIRST_RATE=$((FIRST_KEEPS * 100 / HALF))
  SECOND_RATE=$((SECOND_KEEPS * 100 / HALF))

  echo "- First half (entries 1-${HALF}): ${FIRST_RATE}% success"
  echo "- Second half (entries $((HALF+1))-${TOTAL_ENTRIES}): ${SECOND_RATE}% success"

  if [ "$SECOND_RATE" -gt "$FIRST_RATE" ]; then
    echo "- Trend: **improving** (learnings are helping)"
  elif [ "$SECOND_RATE" -lt "$FIRST_RATE" ]; then
    echo "- Trend: **degrading** (tasks may be getting harder, or codebase complexity is growing)"
  else
    echo "- Trend: **stable**"
  fi
else
  echo "(not enough entries for trend analysis)"
fi
