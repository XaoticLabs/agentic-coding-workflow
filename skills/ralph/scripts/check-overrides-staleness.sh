#!/usr/bin/env bash
# Check RALPH_OVERRIDES.md for stale rules (older than threshold).
# Rules are expected to have a date marker: "— YYYY-MM-DD" or "[YYYY-MM-DD]"
# Rules without dates are flagged as undated.
#
# Usage: check-overrides-staleness.sh <overrides-file> [journal-file] [max-age-days]
# Output: warnings on stdout, exits 0 always (advisory, never blocks)
#
# Environment:
#   RALPH_OVERRIDE_MAX_AGE_DAYS=30  Override the default max age

set -euo pipefail

OVERRIDES_FILE="${1:?Usage: check-overrides-staleness.sh <overrides-file> [journal-file] [max-age-days]}"
JOURNAL_FILE="${2:-}"
MAX_AGE_DAYS="${3:-${RALPH_OVERRIDE_MAX_AGE_DAYS:-30}}"

if [ ! -f "$OVERRIDES_FILE" ]; then
  exit 0
fi

TODAY_EPOCH=$(date +%s)
STALE_COUNT=0
UNDATED_COUNT=0
STALE_RULES=""
UNDATED_RULES=""

while IFS= read -r line; do
  # Skip empty lines, comments, and section headers
  [[ -z "$line" || "$line" == \#* || "$line" == "---"* ]] && continue

  # Extract date from rule line (formats: "— 2025-12-15", "[2025-12-15]", "2025-12-15:")
  RULE_DATE=$(echo "$line" | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}' | head -1 || true)

  if [ -z "$RULE_DATE" ]; then
    UNDATED_COUNT=$((UNDATED_COUNT + 1))
    UNDATED_RULES="${UNDATED_RULES}\n  - ${line:0:80}"
    continue
  fi

  # Calculate age in days
  if date -j -f "%Y-%m-%d" "$RULE_DATE" "+%s" >/dev/null 2>&1; then
    # macOS date
    RULE_EPOCH=$(date -j -f "%Y-%m-%d" "$RULE_DATE" "+%s" 2>/dev/null || echo "0")
  elif date -d "$RULE_DATE" "+%s" >/dev/null 2>&1; then
    # GNU date
    RULE_EPOCH=$(date -d "$RULE_DATE" "+%s" 2>/dev/null || echo "0")
  else
    RULE_EPOCH=0
  fi

  if [ "$RULE_EPOCH" -gt 0 ]; then
    AGE_DAYS=$(( (TODAY_EPOCH - RULE_EPOCH) / 86400 ))
    if [ "$AGE_DAYS" -gt "$MAX_AGE_DAYS" ]; then
      # Check if journal has recent activity confirming this rule
      CONFIRMED=false
      if [ -n "$JOURNAL_FILE" ] && [ -f "$JOURNAL_FILE" ]; then
        # Extract a keyword from the rule to search journal
        KEYWORD=$(echo "$line" | grep -oE '[A-Za-z_]+' | head -3 | tail -1 || true)
        if [ -n "$KEYWORD" ]; then
          RECENT_MENTION=$(tail -20 "$JOURNAL_FILE" | grep -i "$KEYWORD" 2>/dev/null || true)
          [ -n "$RECENT_MENTION" ] && CONFIRMED=true
        fi
      fi

      if [ "$CONFIRMED" = false ]; then
        STALE_COUNT=$((STALE_COUNT + 1))
        STALE_RULES="${STALE_RULES}\n  - [${AGE_DAYS}d old] ${line:0:80}"
      fi
    fi
  fi
done < "$OVERRIDES_FILE"

# Report findings
if [ "$STALE_COUNT" -gt 0 ] || [ "$UNDATED_COUNT" -gt 0 ]; then
  echo "⚠ OVERRIDE STALENESS CHECK:"
  if [ "$STALE_COUNT" -gt 0 ]; then
    echo "  ${STALE_COUNT} rule(s) older than ${MAX_AGE_DAYS} days with no recent journal confirmation:"
    echo -e "$STALE_RULES"
  fi
  if [ "$UNDATED_COUNT" -gt 0 ]; then
    echo "  ${UNDATED_COUNT} rule(s) have no date marker (cannot determine age):"
    echo -e "$UNDATED_RULES"
  fi
  echo ""
  echo "  Review these rules before running. Stale rules silently bias every iteration."
  echo "  To dismiss: re-date confirmed rules or remove obsolete ones from RALPH_OVERRIDES.md"
fi
