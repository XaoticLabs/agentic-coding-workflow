#!/usr/bin/env bash
# Generate a completion summary artifact after a Ralph run.
# Produces .claude/ralph-logs/ralph-summary-<slug>.md with key metrics, commits,
# and a ready-to-use PR description.
#
# Usage: generate-summary.sh <spec-dir> <journal-file> <iterations> <commits-at-start> <start-time>

set -euo pipefail

SPEC_DIR="${1:?Usage: generate-summary.sh <spec-dir> <journal-file> <iterations> <commits-at-start> <start-time> [trace-file]}"
JOURNAL_FILE="${2:?}"
ITERATIONS="${3:?}"
COMMITS_AT_START="${4:?}"
START_TIME="${5:?}"
TRACE_FILE="${6:-}"

SLUG=$(basename "$SPEC_DIR")
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
PLAN_FILE="${SPEC_DIR}/IMPLEMENTATION_PLAN.md"
SUMMARY_FILE="${PROJECT_DIR}/.claude/ralph-logs/ralph-summary-${SLUG}.md"

# ── Metrics ────────────────────────────────────────────────────────────

COMMITS_NOW=$(git rev-list --count HEAD 2>/dev/null || echo "0")
NEW_COMMITS=$((COMMITS_NOW - COMMITS_AT_START))
ELAPSED=$(( $(date +%s) - START_TIME ))
MINUTES=$((ELAPSED / 60))

KEEPS=0
REVERTS=0
TIMEOUTS=0
NO_COMMITS=0
if [ -f "$JOURNAL_FILE" ]; then
  KEEPS=$(tail -n +2 "$JOURNAL_FILE" | grep -c 'KEEP' 2>/dev/null || true)
  REVERTS=$(tail -n +2 "$JOURNAL_FILE" | grep -c 'REVERT' 2>/dev/null || true)
  TIMEOUTS=$(tail -n +2 "$JOURNAL_FILE" | grep -c 'TIMEOUT' 2>/dev/null || true)
  NO_COMMITS=$(tail -n +2 "$JOURNAL_FILE" | grep -c 'NO_COMMIT' 2>/dev/null || true)
fi
KEEPS=${KEEPS:-0}
REVERTS=${REVERTS:-0}
TIMEOUTS=${TIMEOUTS:-0}
NO_COMMITS=${NO_COMMITS:-0}

# Success rate = kept / (kept + reverted + timed out)
# Excludes NO_COMMIT and INTEGRITY_FIX entries which aren't real attempts
SUCCESS_RATE="N/A"
REAL_ATTEMPTS=$((KEEPS + REVERTS + TIMEOUTS))
[ "$REAL_ATTEMPTS" -gt 0 ] && SUCCESS_RATE="$((KEEPS * 100 / REAL_ATTEMPTS))%"

# ── Task status ────────────────────────────────────────────────────────

TOTAL_TASKS=0
DONE_TASKS=0
SKIPPED_TASKS=""
if [ -f "$PLAN_FILE" ]; then
  TOTAL_TASKS=$(grep -c '^\- \[[ x]\] \*\*Task' "$PLAN_FILE" 2>/dev/null || echo "0")
  DONE_TASKS=$(grep -c '^\- \[x\] \*\*Task' "$PLAN_FILE" 2>/dev/null || echo "0")
  SKIPPED_TASKS=$(grep '^\- \[ \] \*\*Task' "$PLAN_FILE" 2>/dev/null || true)
fi

PLAN_STATUS="UNKNOWN"
if [ -f "$PLAN_FILE" ]; then
  PLAN_STATUS=$(grep -oP '## Status: \K.*' "$PLAN_FILE" 2>/dev/null || echo "UNKNOWN")
fi

# ── Commits list ───────────────────────────────────────────────────────

COMMIT_LIST=""
if [ "$NEW_COMMITS" -gt 0 ]; then
  COMMIT_LIST=$(git log --oneline -"$NEW_COMMITS" 2>/dev/null || true)
fi

# ── Files modified ─────────────────────────────────────────────────────

FILES_MODIFIED=""
if [ "$NEW_COMMITS" -gt 0 ]; then
  FILES_MODIFIED=$(git diff --name-only HEAD~"$NEW_COMMITS"..HEAD 2>/dev/null | sort -u || true)
  FILES_COUNT=$(echo "$FILES_MODIFIED" | grep -c '[^ ]' 2>/dev/null || echo "0")
fi

# ── Most reverted tasks ───────────────────────────────────────────────

REVERT_ANALYSIS=""
if [ -f "$JOURNAL_FILE" ]; then
  REVERT_ANALYSIS=$(tail -n +2 "$JOURNAL_FILE" | grep 'REVERT' | awk -F'\t' '{print $3}' | sort | uniq -c | sort -rn | head -5 || true)
fi

# ── Write summary ─────────────────────────────────────────────────────

cat > "$SUMMARY_FILE" <<EOF
# Ralph Run Summary — ${SLUG}

**Generated:** $(date)
**Plan status:** ${PLAN_STATUS}

## Metrics

| Metric | Value |
|--------|-------|
| Iterations | ${ITERATIONS} |
| Commits kept | ${KEEPS} |
| Reverts | ${REVERTS} |
| Timeouts | ${TIMEOUTS} |
| No-ops | ${NO_COMMITS} |
| Success rate | ${SUCCESS_RATE} |
| Tasks completed | ${DONE_TASKS} / ${TOTAL_TASKS} |
| Duration | ${MINUTES} minutes |

## Commits

\`\`\`
${COMMIT_LIST:-"(no commits)"}
\`\`\`

## Files Modified (${FILES_COUNT:-0} files)

\`\`\`
${FILES_MODIFIED:-"(none)"}
\`\`\`
EOF

# Add skipped tasks if any
if [ -n "$SKIPPED_TASKS" ]; then
  cat >> "$SUMMARY_FILE" <<EOF

## Incomplete Tasks

${SKIPPED_TASKS}
EOF
fi

# Add revert analysis if any
if [ -n "$REVERT_ANALYSIS" ]; then
  cat >> "$SUMMARY_FILE" <<EOF

## Most Reverted Tasks

\`\`\`
${REVERT_ANALYSIS}
\`\`\`
EOF
fi

# ── Tool usage (from trace) ──────────────────────────────────────────

if [ -n "$TRACE_FILE" ] && [ -f "$TRACE_FILE" ]; then
  TOOL_USAGE=$(grep '"type":"tool_call"' "$TRACE_FILE" 2>/dev/null | \
    sed 's/.*"tool":"\([^"]*\)".*/\1/' | sort | uniq -c | sort -rn || true)
  TOTAL_TOOL_CALLS=$(grep -c '"type":"tool_call"' "$TRACE_FILE" 2>/dev/null || echo 0)
  if [ -n "$TOOL_USAGE" ]; then
    cat >> "$SUMMARY_FILE" <<EOF

## Tool Usage (${TOTAL_TOOL_CALLS} total calls)

\`\`\`
${TOOL_USAGE}
\`\`\`

**Trace file:** \`${TRACE_FILE}\`
View with: \`trace-viewer.py ${TRACE_FILE} --view tools\`
EOF
  fi
fi

# ── PR template detection ─────────────────────────────────────────────

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "$PROJECT_DIR")
PR_TEMPLATE=""
for tmpl in \
  "${REPO_ROOT}/.github/pull_request_template.md" \
  "${REPO_ROOT}/.github/PULL_REQUEST_TEMPLATE.md" \
  "${REPO_ROOT}/.github/PULL_REQUEST_TEMPLATE/pull_request_template.md" \
  "${REPO_ROOT}/docs/pull_request_template.md" \
  "${REPO_ROOT}/pull_request_template.md" \
  "${REPO_ROOT}/PULL_REQUEST_TEMPLATE.md"; do
  if [ -f "$tmpl" ]; then
    PR_TEMPLATE="$tmpl"
    break
  fi
done

cat >> "$SUMMARY_FILE" <<EOF

## Next Step

Run \`/ship\` to fill the PR template and create a PR.
\`/ship\` will auto-detect your project's PR template and fill it in properly.

EOF

if [ -n "$PR_TEMPLATE" ]; then
  cat >> "$SUMMARY_FILE" <<EOF
**PR template detected:** \`${PR_TEMPLATE}\`
The \`/ship\` command will use this template and fill in each section with
context from the spec, diff, and Ralph run metrics.

EOF
fi

# Add a basic PR description as fallback context for /ship
cat >> "$SUMMARY_FILE" <<EOF
## Ralph Run Context (for PR description)

Autonomous implementation via Ralph loop (\`${SLUG}\`).

- ${DONE_TASKS}/${TOTAL_TASKS} tasks completed across ${ITERATIONS} iterations
- ${KEEPS} commits kept, ${REVERTS} reverted (${SUCCESS_RATE} success rate)
- Duration: ${MINUTES} minutes

### Commits

$(echo "$COMMIT_LIST" | head -20 | sed 's/^/- /' || echo "- (no commits)")

### Files Modified

${FILES_COUNT:-0} files changed.
EOF

echo "Summary written to ${SUMMARY_FILE}"
