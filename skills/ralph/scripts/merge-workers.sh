#!/usr/bin/env bash
# Merge parallel worker branches into a target branch.
#
# Features:
#   - Overlap-based merge ordering (least overlap first) via analyze-overlap.sh
#   - Test gate after each merge (configurable)
#   - Graceful degradation: skip failed workers instead of hard exit
#   - Structured JSON result for orchestrator consumption
#
# Usage:
#   merge-workers.sh --target <branch> --branches <b1> <b2> ... [options]
#
# Options:
#   --target <branch>       Target branch to merge into (required)
#   --branches <b1> <b2>    Space-separated list of branches to merge (required)
#   --spec-dir <path>       Spec directory for conflict resolution context
#   --strictness <level>    strict|normal|lenient (default: normal)
#                           strict:  any failure = abort (legacy behavior)
#                           normal:  skip failed workers, run test gates
#                           lenient: skip failed workers, no test gates
#   --project-dir <path>    Project directory for test detection (default: cwd)
#
# Output: JSON summary to stdout on success. Log messages to stderr.
# Exit codes: 0 = all merged, 1 = partial merge (some skipped), 2 = fatal error

set -euo pipefail

# ── Parse arguments ───────────────────────────────────────────────────

TARGET_BRANCH=""
BRANCHES=()
SPEC_DIR=""
STRICTNESS="normal"
PROJECT_DIR="."

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)     TARGET_BRANCH="$2"; shift 2 ;;
    --branches)   shift; while [[ $# -gt 0 && ! "$1" =~ ^-- ]]; do BRANCHES+=("$1"); shift; done ;;
    --spec-dir)   SPEC_DIR="$2"; shift 2 ;;
    --strictness) STRICTNESS="$2"; shift 2 ;;
    --project-dir) PROJECT_DIR="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$TARGET_BRANCH" ] || [ ${#BRANCHES[@]} -eq 0 ]; then
  echo "Usage: merge-workers.sh --target <branch> --branches <b1> <b2> ... [--strictness strict|normal|lenient]" >&2
  exit 2
fi

# ── Setup ─────────────────────────────────────────────────────────────

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
REPO_ROOT=$(git rev-parse --show-toplevel)

# Source shared primitives
LIB_DIR="${REPO_ROOT}/scripts/lib"
if [ -f "${LIB_DIR}/parallel-primitives.sh" ]; then
  source "${LIB_DIR}/parallel-primitives.sh"
else
  PLUGIN_LIB="${CLAUDE_PLUGIN_ROOT:-${SCRIPT_DIR}/../../..}/scripts/lib/parallel-primitives.sh"
  [ -f "$PLUGIN_LIB" ] && source "$PLUGIN_LIB"
fi

# Resolve prompt
RESOLVE_PROMPT="${LIB_DIR}/PROMPT_resolve.md"
if [ ! -f "$RESOLVE_PROMPT" ]; then
  RESOLVE_PROMPT="${SCRIPT_DIR}/../references/PROMPT_resolve.md"
fi

# Analyze overlap script (from reunify skill)
ANALYZE_OVERLAP="${SCRIPT_DIR}/../../reunify/scripts/analyze-overlap.sh"
if [ ! -f "$ANALYZE_OVERLAP" ]; then
  ANALYZE_OVERLAP="${REPO_ROOT}/skills/reunify/scripts/analyze-overlap.sh"
fi

echo "━━━ Merging ${#BRANCHES[@]} worker branches into ${TARGET_BRANCH} (strictness: ${STRICTNESS}) ━━━" >&2

# Ensure we're on the target branch.
# A stale worktree from a previous run may hold the branch — detect and remove it.
if ! git checkout "$TARGET_BRANCH" >&2 2>&1; then
  STALE_WT=$(git worktree list --porcelain 2>/dev/null \
    | awk -v branch="refs/heads/${TARGET_BRANCH}" '/^worktree /{wt=$2} /^branch /{if ($2==branch) print wt}')
  if [ -n "$STALE_WT" ]; then
    echo "WARNING: Stale worktree at ${STALE_WT} holds branch ${TARGET_BRANCH}. Removing it." >&2
    git worktree remove "$STALE_WT" --force >&2 2>&1 || true
    git checkout "$TARGET_BRANCH" >&2 2>&1 || {
      echo "Error: could not checkout target branch ${TARGET_BRANCH} even after removing stale worktree" >&2
      exit 2
    }
  else
    echo "Error: could not checkout target branch: ${TARGET_BRANCH}" >&2
    exit 2
  fi
fi

# ── Determine merge order ────────────────────────────────────────────

MERGE_ORDER=()

if [ -f "$ANALYZE_OVERLAP" ] && [ ${#BRANCHES[@]} -gt 1 ]; then
  echo "Analyzing file overlap for optimal merge order..." >&2
  OVERLAP_JSON=$("$ANALYZE_OVERLAP" "$TARGET_BRANCH" "${BRANCHES[@]}" 2>/dev/null || echo "")

  if [ -n "$OVERLAP_JSON" ]; then
    # Extract recommended order from JSON
    ORDERED=$(echo "$OVERLAP_JSON" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for branch in data.get('recommended_order', []):
    print(branch)
" 2>/dev/null || echo "")

    if [ -n "$ORDERED" ]; then
      while IFS= read -r branch; do
        MERGE_ORDER+=("$branch")
      done <<< "$ORDERED"
      echo "Merge order (overlap-optimized): ${MERGE_ORDER[*]}" >&2
    fi
  fi
fi

# Fall back to original order if overlap analysis failed
if [ ${#MERGE_ORDER[@]} -eq 0 ]; then
  MERGE_ORDER=("${BRANCHES[@]}")
  echo "Using original branch order" >&2
fi

# ── Merge loop ────────────────────────────────────────────────────────

declare -a RESULTS=()
MERGED_COUNT=0
SKIPPED_COUNT=0
CONFLICT_COUNT=0
FAILED_COUNT=0

for BRANCH in "${MERGE_ORDER[@]}"; do
  echo "" >&2
  echo "── Merging ${BRANCH} ──" >&2

  # Check if branch exists
  if ! git show-ref --verify --quiet "refs/heads/${BRANCH}"; then
    echo "Warning: branch ${BRANCH} not found, skipping" >&2
    RESULTS+=("{\"branch\":\"${BRANCH}\",\"status\":\"skipped\",\"reason\":\"branch not found\"}")
    SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
    continue
  fi

  # Check if branch has commits ahead of target
  AHEAD=$(git rev-list --count "${TARGET_BRANCH}..${BRANCH}" 2>/dev/null || echo "0")
  if [ "$AHEAD" -eq 0 ]; then
    echo "${BRANCH}: no new commits, skipping" >&2
    RESULTS+=("{\"branch\":\"${BRANCH}\",\"status\":\"skipped\",\"reason\":\"no new commits\"}")
    SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
    continue
  fi

  echo "${BRANCH}: ${AHEAD} commits to merge" >&2

  # Save pre-merge state for rollback
  PRE_MERGE_COMMIT=$(git rev-parse HEAD)

  # Attempt merge
  MERGE_CLEAN=true
  if ! git merge --no-edit "$BRANCH" >&2 2>&1; then
    MERGE_CLEAN=false
    echo "${BRANCH}: CONFLICT — launching Claude to resolve" >&2
    CONFLICT_COUNT=$((CONFLICT_COUNT + 1))

    # Build resolve prompt with context
    CONTEXT="
---
**Merging branch:** ${BRANCH}
**Into:** ${TARGET_BRANCH}
**Spec directory:** ${SPEC_DIR}
**Branches remaining:** $(( ${#MERGE_ORDER[@]} - MERGED_COUNT - SKIPPED_COUNT - FAILED_COUNT - 1 ))
"
    PROMPT=$(python3 -c "
import sys
template = open('${RESOLVE_PROMPT}').read()
context = sys.stdin.read()
print(template.replace('{{CONTEXT}}', context))
" <<< "$CONTEXT")

    # Launch Claude to resolve
    if echo "$PROMPT" | claude -p --dangerously-skip-permissions --model sonnet >&2 2>&1; then
      echo "${BRANCH}: conflicts resolved by Claude" >&2
    else
      echo "${BRANCH}: conflict resolution FAILED" >&2
      git merge --abort 2>/dev/null || true

      if [ "$STRICTNESS" = "strict" ]; then
        echo "STRICT MODE: Aborting entire merge due to conflict resolution failure." >&2
        RESULTS+=("{\"branch\":\"${BRANCH}\",\"status\":\"failed\",\"reason\":\"conflict resolution failed\"}")
        # Output partial results before exit
        _emit_json_result "$MERGED_COUNT" "$SKIPPED_COUNT" "$CONFLICT_COUNT" "1" "aborted" || true
        exit 1
      fi

      RESULTS+=("{\"branch\":\"${BRANCH}\",\"status\":\"failed\",\"reason\":\"conflict resolution failed\"}")
      FAILED_COUNT=$((FAILED_COUNT + 1))
      continue
    fi
  fi

  # Post-merge test gate (skip in lenient mode)
  if [ "$STRICTNESS" != "lenient" ]; then
    TEST_LOG="/tmp/merge-test-${BRANCH//\//-}.log"
    if ! run_test_gate "$PROJECT_DIR" "$TEST_LOG"; then
      FAIL_TAIL=$(tail -5 "$TEST_LOG" 2>/dev/null | tr '\n' ' ' || echo "unknown failure")
      echo "${BRANCH}: POST-MERGE TESTS FAILED — ${FAIL_TAIL}" >&2

      if [ "$STRICTNESS" = "strict" ]; then
        echo "STRICT MODE: Aborting due to post-merge test failure." >&2
        git reset --hard "$PRE_MERGE_COMMIT" >&2 2>&1
        RESULTS+=("{\"branch\":\"${BRANCH}\",\"status\":\"failed\",\"reason\":\"post-merge tests failed\"}")
        exit 1
      fi

      # Normal mode: rollback this merge, skip the branch
      echo "${BRANCH}: rolling back merge and skipping" >&2
      git reset --hard "$PRE_MERGE_COMMIT" >&2 2>&1
      RESULTS+=("{\"branch\":\"${BRANCH}\",\"status\":\"failed\",\"reason\":\"post-merge tests failed\",\"test_output\":\"${FAIL_TAIL}\"}")
      FAILED_COUNT=$((FAILED_COUNT + 1))
      continue
    fi
  fi

  # Success
  if [ "$MERGE_CLEAN" = true ]; then
    echo "${BRANCH}: merged cleanly" >&2
    RESULTS+=("{\"branch\":\"${BRANCH}\",\"status\":\"merged\",\"commits\":${AHEAD}}")
  else
    echo "${BRANCH}: merged with conflict resolution" >&2
    RESULTS+=("{\"branch\":\"${BRANCH}\",\"status\":\"merged_with_conflicts\",\"commits\":${AHEAD}}")
  fi
  MERGED_COUNT=$((MERGED_COUNT + 1))
done

# ── Output JSON result ────────────────────────────────────────────────

OVERALL="success"
EXIT_CODE=0
if [ "$FAILED_COUNT" -gt 0 ]; then
  OVERALL="partial"
  EXIT_CODE=1
fi
if [ "$MERGED_COUNT" -eq 0 ] && [ "$FAILED_COUNT" -gt 0 ]; then
  OVERALL="failed"
  EXIT_CODE=1
fi

# Build results array
RESULTS_JSON="["
for ((r=0; r<${#RESULTS[@]}; r++)); do
  [ "$r" -gt 0 ] && RESULTS_JSON+=","
  RESULTS_JSON+="${RESULTS[$r]}"
done
RESULTS_JSON+="]"

cat <<EOF
{
  "status": "${OVERALL}",
  "target_branch": "${TARGET_BRANCH}",
  "merged": ${MERGED_COUNT},
  "skipped": ${SKIPPED_COUNT},
  "failed": ${FAILED_COUNT},
  "conflicts_resolved": ${CONFLICT_COUNT},
  "results": ${RESULTS_JSON}
}
EOF

echo "" >&2
echo "━━━ Merge ${OVERALL}: ${MERGED_COUNT} merged, ${SKIPPED_COUNT} skipped, ${FAILED_COUNT} failed ━━━" >&2

exit $EXIT_CODE
