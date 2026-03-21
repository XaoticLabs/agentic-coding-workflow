#!/usr/bin/env bash
# Merge parallel Ralph worker branches back to the target branch
#
# Usage: merge-workers.sh <slug> <num-workers> <target-branch> <spec-dir>
#
# Sequentially merges ralph/<slug>/worker-{0..N-1} into target branch.
# On conflict: launches Claude with PROMPT_resolve.md to resolve.

set -euo pipefail

SLUG="${1:?Usage: merge-workers.sh <slug> <num-workers> <target-branch> <spec-dir>}"
NUM_WORKERS="${2:?Usage: merge-workers.sh <slug> <num-workers> <target-branch> <spec-dir>}"
TARGET_BRANCH="${3:?Usage: merge-workers.sh <slug> <num-workers> <target-branch> <spec-dir>}"
SPEC_DIR="${4:?Usage: merge-workers.sh <slug> <num-workers> <target-branch> <spec-dir>}"

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
RESOLVE_PROMPT="${SCRIPT_DIR}/../references/PROMPT_resolve.md"

echo "━━━ Merging ${NUM_WORKERS} worker branches into ${TARGET_BRANCH} ━━━"

# Ensure we're on the target branch
git checkout "$TARGET_BRANCH" 2>/dev/null || {
  echo "Error: could not checkout target branch: ${TARGET_BRANCH}" >&2
  exit 1
}

MERGE_LOG=""
CONFLICT_COUNT=0

for ((i=0; i<NUM_WORKERS; i++)); do
  BRANCH="ralph/${SLUG}/worker-${i}"
  echo ""
  echo "── Merging worker-${i} (${BRANCH}) ──"

  # Check if branch exists
  if ! git show-ref --verify --quiet "refs/heads/${BRANCH}"; then
    echo "Warning: branch ${BRANCH} not found, skipping"
    MERGE_LOG="${MERGE_LOG}\nworker-${i}: SKIPPED (branch not found)"
    continue
  fi

  # Check if branch has commits ahead of target
  AHEAD=$(git rev-list --count "${TARGET_BRANCH}..${BRANCH}" 2>/dev/null || echo "0")
  if [ "$AHEAD" -eq 0 ]; then
    echo "worker-${i}: no new commits, skipping"
    MERGE_LOG="${MERGE_LOG}\nworker-${i}: SKIPPED (no new commits)"
    continue
  fi

  echo "worker-${i}: ${AHEAD} commits to merge"

  # Attempt merge
  if git merge --no-edit "$BRANCH"; then
    echo "worker-${i}: merged cleanly"
    MERGE_LOG="${MERGE_LOG}\nworker-${i}: MERGED (${AHEAD} commits)"
  else
    echo "worker-${i}: CONFLICT — launching Claude to resolve"
    CONFLICT_COUNT=$((CONFLICT_COUNT + 1))

    # Build resolve prompt with context
    PROMPT="$(cat "$RESOLVE_PROMPT")

---
**Merging branch:** ${BRANCH}
**Into:** ${TARGET_BRANCH}
**Spec directory:** ${SPEC_DIR}
**Worker:** ${i} of ${NUM_WORKERS}
"

    # Launch Claude to resolve
    if echo "$PROMPT" | claude -p --dangerously-skip-permissions --model sonnet 2>&1; then
      echo "worker-${i}: conflicts resolved by Claude"
      MERGE_LOG="${MERGE_LOG}\nworker-${i}: MERGED with conflict resolution (${AHEAD} commits)"
    else
      echo "Error: Claude failed to resolve conflicts for worker-${i}" >&2
      echo "Aborting merge. Manual resolution needed."
      git merge --abort 2>/dev/null || true
      MERGE_LOG="${MERGE_LOG}\nworker-${i}: FAILED (conflict resolution failed)"
      echo ""
      echo "━━━ Merge FAILED ━━━"
      echo -e "$MERGE_LOG"
      exit 1
    fi
  fi
done

echo ""
echo "━━━ Merge complete ━━━"
echo -e "$MERGE_LOG"
echo ""
echo "Conflicts resolved: ${CONFLICT_COUNT}"
echo "Branch: ${TARGET_BRANCH}"
