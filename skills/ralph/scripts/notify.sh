#!/usr/bin/env bash
# Cross-platform desktop notification for Ralph loop events.
# Sends alerts so the human doesn't have to poll for status.
#
# Usage: notify.sh <event-type> <title> <message>
#   event-type: struggle | circuit_break | eval_warning | complete | checkpoint
#   title:      Short notification title
#   message:    Notification body text
#
# Environment:
#   RALPH_NOTIFY=false    Disable notifications entirely
#   RALPH_NOTIFY_SOUND=1  Play alert sound (macOS only, default: 1)

set -euo pipefail

EVENT_TYPE="${1:-info}"
TITLE="${2:-Ralph Loop}"
MESSAGE="${3:-}"

# Allow disabling via environment
if [ "${RALPH_NOTIFY:-true}" = "false" ]; then
  exit 0
fi

SOUND="${RALPH_NOTIFY_SOUND:-1}"

# Map event types to urgency levels
case "$EVENT_TYPE" in
  struggle|circuit_break|eval_warning)
    URGENCY="critical"
    ;;
  checkpoint)
    URGENCY="normal"
    ;;
  complete)
    URGENCY="low"
    ;;
  *)
    URGENCY="normal"
    ;;
esac

# macOS: osascript
if [ "$(uname)" = "Darwin" ]; then
  SOUND_CLAUSE=""
  if [ "$SOUND" = "1" ]; then
    SOUND_CLAUSE=' sound name "Funk"'
  fi
  osascript -e "display notification \"${MESSAGE}\" with title \"${TITLE}\"${SOUND_CLAUSE}" 2>/dev/null || true
  exit 0
fi

# Linux: notify-send
if command -v notify-send >/dev/null 2>&1; then
  notify-send --urgency="$URGENCY" "$TITLE" "$MESSAGE" 2>/dev/null || true
  exit 0
fi

# Fallback: terminal bell
printf '\a' 2>/dev/null || true
