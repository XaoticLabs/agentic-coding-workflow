#!/usr/bin/env bash
# Generate a structured briefing for the next Ralph iteration.
# Extracts signal from the plan, journal, and recent git history.
# Keeps the context window focused — equivalent to autoresearch's
# "grep for the metric, not the full training log" pattern.
#
# Usage: generate-briefing.sh <plan-file> <journal-file> <iteration>
# Output: markdown briefing on stdout

set -euo pipefail

PLAN_FILE="${1:?Usage: generate-briefing.sh <plan-file> <journal-file> <iteration>}"
JOURNAL_FILE="${2:?}"
ITERATION="${3:?}"

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

# ── Recent journal entries (last 8) ────────────────────────────────

echo "### Recent Outcomes"
if [ -f "$JOURNAL_FILE" ] && [ "$(wc -l < "$JOURNAL_FILE")" -gt 1 ]; then
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

# ── Iteration stats ───────────────────────────────────────────────

echo "### Stats"
if [ -f "$JOURNAL_FILE" ]; then
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
