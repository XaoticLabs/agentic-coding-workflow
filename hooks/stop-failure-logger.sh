#!/usr/bin/env bash
# StopFailure hook — logs API failures and sends toast notification
# Fires when a turn ends due to rate limit, auth error, or other API error.
# Output and exit code are ignored by Claude Code for this event type.

set -euo pipefail

# Read JSON from stdin
INPUT=$(cat)

ERROR=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('error','unknown'))" 2>/dev/null || echo "unknown")
ERROR_DETAILS=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('error_details',''))" 2>/dev/null || echo "")
SESSION_ID=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null || echo "")
CWD=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd',''))" 2>/dev/null || echo "")

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Log to ralph-logs if it exists (Ralph is running), otherwise log to .claude/
if [ -d "${CWD}/.claude/ralph-logs" ]; then
  LOG_DIR="${CWD}/.claude/ralph-logs"
else
  LOG_DIR="${CWD}/.claude"
  mkdir -p "$LOG_DIR"
fi

LOG_FILE="${LOG_DIR}/stop-failures.log"

echo "${TIMESTAMP}	${ERROR}	${ERROR_DETAILS}	session=${SESSION_ID}" >> "$LOG_FILE"

# Toast notification (macOS)
if command -v osascript >/dev/null 2>&1; then
  TITLE="Claude API Failure"
  case "$ERROR" in
    rate_limit)       MSG="Rate limit hit. Worker paused." ;;
    authentication*)  MSG="Auth failed. Check credentials." ;;
    billing_error)    MSG="Billing error. Check account." ;;
    server_error)     MSG="API server error. Transient." ;;
    max_output_tokens) MSG="Max output tokens reached." ;;
    *)                MSG="API error: ${ERROR}" ;;
  esac
  osascript -e "display notification \"${MSG}\" with title \"${TITLE}\"" 2>/dev/null || true
fi

exit 0
