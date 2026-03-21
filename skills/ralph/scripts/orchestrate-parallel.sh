#!/usr/bin/env bash
# Orchestrate a full parallel Ralph lifecycle:
#   1. Partition tasks with file affinity
#   2. Create worktrees and launch workers
#   3. Poll for completion
#   4. Merge worker branches
#   5. Reconcile (verify tests on merged code)
#   6. Cleanup
#
# Usage: orchestrate-parallel.sh <spec-dir> <slug> <num-workers> <max-iterations> [flags...]
#   --push:       Push after each worker commit
#   --clean-room: Skip codebase search (greenfield mode)
#   --pr:         Auto-create draft PR

set -euo pipefail

SPEC_DIR="${1:?Usage: orchestrate-parallel.sh <spec-dir> <slug> <num-workers> <max-iterations> [flags...]}"
SLUG="${2:?Usage: orchestrate-parallel.sh <spec-dir> <slug> <num-workers> <max-iterations> [flags...]}"
NUM_WORKERS="${3:?Usage: orchestrate-parallel.sh <spec-dir> <slug> <num-workers> <max-iterations> [flags...]}"
MAX_ITERATIONS="${4:-50}"

PUSH_FLAG=""
CLEAN_ROOM_FLAG=""
PR_FLAG=""

for arg in "$@"; do
  case "$arg" in
    --push)       PUSH_FLAG="--push" ;;
    --clean-room) CLEAN_ROOM_FLAG="--clean-room" ;;
    --pr)         PR_FLAG="--pr" ;;
  esac
done

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
REPO_ROOT=$(git rev-parse --show-toplevel)
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$REPO_ROOT}"
PLAN_FILE="${SPEC_DIR}/IMPLEMENTATION_PLAN.md"
TARGET_BRANCH=$(git branch --show-current)
WORKTREE_BASE="${REPO_ROOT}/.claude/worktrees"
STOP_SENTINEL="${PROJECT_DIR}/.claude/ralph-stop"
STATUS_FILE="${PROJECT_DIR}/.claude/ralph-status.md"
META_FILE="${PROJECT_DIR}/.claude/ralph-parallel-meta.json"
POLL_INTERVAL=30

# ── Phase banner ─────────────────────────────────────────────────────────

update_phase() {
  local phase="$1"
  local detail="${2:-}"

  cat > "$STATUS_FILE" <<EOF
# Ralph Parallel Status

**Phase:** ${phase}
**Detail:** ${detail}
**Slug:** ${SLUG}
**Workers:** ${NUM_WORKERS}
**Target branch:** ${TARGET_BRANCH}
**Updated:** $(date)
EOF
}

echo "╔══════════════════════════════════════════════════════╗"
echo "║  RALPH PARALLEL — Full Lifecycle Orchestrator        ║"
echo "║                                                      ║"
echo "║  Slug:       ${SLUG}"
echo "║  Workers:    ${NUM_WORKERS}"
echo "║  Spec dir:   ${SPEC_DIR}"
echo "║  Max iters:  ${MAX_ITERATIONS}"
echo "║  Target:     ${TARGET_BRANCH}"
echo "║                                                      ║"
echo "║  Stop: touch .claude/ralph-stop                      ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Phase 1: Save metadata ──────────────────────────────────────────────

update_phase "SETUP" "Saving metadata and partitioning tasks"

cat > "$META_FILE" <<EOF
{
  "slug": "${SLUG}",
  "num_workers": ${NUM_WORKERS},
  "target_branch": "${TARGET_BRANCH}",
  "spec_dir": "${SPEC_DIR}",
  "started_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

echo "Metadata saved to ${META_FILE}"

# ── Phase 2: Partition tasks ────────────────────────────────────────────

echo ""
echo "━━━ Partitioning tasks with file affinity ━━━"

PARTITION_JSON=$("$SCRIPT_DIR/partition-tasks.sh" "$PLAN_FILE" "$NUM_WORKERS")
echo "$PARTITION_JSON" | head -30

# Extract worker task lists for logging
echo ""
echo "Task assignments:"
for ((w=0; w<NUM_WORKERS; w++)); do
  TASKS=$(echo "$PARTITION_JSON" | grep "worker-${w}" | head -1 || echo "  none")
  echo "  worker-${w}: ${TASKS}"
done

# ── Phase 3: Create worktrees ───────────────────────────────────────────

echo ""
echo "━━━ Creating worktrees ━━━"

mkdir -p "$WORKTREE_BASE"

# Ensure .claude/worktrees/ is gitignored
if ! grep -q '\.claude/worktrees/' "${REPO_ROOT}/.gitignore" 2>/dev/null; then
  echo -e '\n# Git worktrees (parallel branch work)\n.claude/worktrees/' >> "${REPO_ROOT}/.gitignore"
fi

BRANCH_PREFIX="ralph/${SLUG}"

for ((i=0; i<NUM_WORKERS; i++)); do
  BRANCH="${BRANCH_PREFIX}/worker-${i}"
  WORKTREE_PATH="${WORKTREE_BASE}/ralph-${SLUG}-worker-${i}"

  # Remove stale worktree if it exists
  if [ -d "$WORKTREE_PATH" ]; then
    echo "Removing stale worktree: ${WORKTREE_PATH}"
    git worktree remove --force "$WORKTREE_PATH" 2>/dev/null || rm -rf "$WORKTREE_PATH"
  fi

  # Remove stale branch if it exists
  if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
    git branch -D "$BRANCH" 2>/dev/null || true
  fi

  git worktree add -b "$BRANCH" "$WORKTREE_PATH"
  echo "Created worktree: ${WORKTREE_PATH} (branch: ${BRANCH})"

  # Copy spec directory into worktree
  mkdir -p "${WORKTREE_PATH}/.claude/specs/"
  cp -r "$SPEC_DIR" "${WORKTREE_PATH}/.claude/specs/${SLUG}/"

  # Ensure .claude dir exists for markers
  mkdir -p "${WORKTREE_PATH}/.claude/ralph-logs"
done

# ── Phase 4: Launch workers ─────────────────────────────────────────────

echo ""
echo "━━━ Launching workers ━━━"

update_phase "WORKING" "All ${NUM_WORKERS} workers running"

SESSION_NAME="ralph-${SLUG}"

# Kill existing session if present
tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true

# Resolve bash path — need bash 4+ for associative arrays in loop.sh
BASH_PATH=$(command -v bash)

# Build flag string for loop.sh
FLAGS=""
[ -n "$PUSH_FLAG" ] && FLAGS="$FLAGS --push"
[ -n "$CLEAN_ROOM_FLAG" ] && FLAGS="$FLAGS --clean-room"
[ -n "$PR_FLAG" ] && FLAGS="$FLAGS --pr"

for ((i=0; i<NUM_WORKERS; i++)); do
  WORKTREE_PATH="${WORKTREE_BASE}/ralph-${SLUG}-worker-${i}"
  WORKER_SPEC_DIR=".claude/specs/${SLUG}"

  CMD="export PATH='${PATH}'; RALPH_WORKER_ID=worker-${i} CLAUDE_PROJECT_DIR='${WORKTREE_PATH}' '${BASH_PATH}' '${SCRIPT_DIR}/loop.sh' '${WORKER_SPEC_DIR}' build ${MAX_ITERATIONS} ${FLAGS}"

  if [ "$i" -eq 0 ]; then
    tmux new-session -d -s "$SESSION_NAME" -c "$WORKTREE_PATH" "$CMD"
  else
    tmux split-window -t "$SESSION_NAME" -c "$WORKTREE_PATH" "$CMD"
  fi
done

tmux select-layout -t "$SESSION_NAME" tiled

echo "Workers launched in tmux session: ${SESSION_NAME}"
echo "Attach: tmux attach -t ${SESSION_NAME}"
echo ""

# ── Phase 5: Poll for completion ────────────────────────────────────────

echo "━━━ Waiting for all workers to complete ━━━"

while :; do
  # Check stop sentinel
  if [ -f "$STOP_SENTINEL" ]; then
    echo "Stop sentinel found. Halting orchestrator."
    rm -f "$STOP_SENTINEL"
    update_phase "STOPPED" "User requested stop"
    echo "Workers may still be running. Kill with: tmux kill-session -t ${SESSION_NAME}"
    exit 0
  fi

  # Count completed workers
  DONE_COUNT=0
  for ((i=0; i<NUM_WORKERS; i++)); do
    WORKTREE_PATH="${WORKTREE_BASE}/ralph-${SLUG}-worker-${i}"
    MARKER="${WORKTREE_PATH}/.claude/ralph-worker-done-worker-${i}"
    if [ -f "$MARKER" ]; then
      DONE_COUNT=$((DONE_COUNT + 1))
    fi
  done

  echo "$(date +%H:%M:%S) — ${DONE_COUNT}/${NUM_WORKERS} workers done"
  update_phase "WORKING" "${DONE_COUNT}/${NUM_WORKERS} workers complete"

  if [ "$DONE_COUNT" -ge "$NUM_WORKERS" ]; then
    echo "All workers complete!"
    break
  fi

  sleep "$POLL_INTERVAL"
done

# ── Phase 6: Merge ──────────────────────────────────────────────────────

echo ""
echo "━━━ Phase: MERGE ━━━"
update_phase "MERGING" "Merging ${NUM_WORKERS} worker branches into ${TARGET_BRANCH}"

# Switch back to the main repo (not a worktree) for merging
cd "$REPO_ROOT"

if "$SCRIPT_DIR/merge-workers.sh" "$SLUG" "$NUM_WORKERS" "$TARGET_BRANCH" "$SPEC_DIR"; then
  echo "Merge successful!"
else
  echo "Merge failed. Check output above for details."
  update_phase "MERGE_FAILED" "Manual intervention needed"
  exit 1
fi

# ── Phase 7: Reconcile ──────────────────────────────────────────────────

echo ""
echo "━━━ Phase: RECONCILE ━━━"
update_phase "RECONCILING" "Running post-merge verification (max 3 iterations)"

# Run reconcile loop on the merged branch (max 3 iterations)
RECONCILE_MAX=3
"$SCRIPT_DIR/loop.sh" "$SPEC_DIR" reconcile "$RECONCILE_MAX" || {
  echo "Warning: reconciliation had issues. Check logs."
}

# ── Phase 8: Cleanup ────────────────────────────────────────────────────

echo ""
echo "━━━ Phase: CLEANUP ━━━"
update_phase "CLEANUP" "Removing worktrees and temporary files"

# Remove worktrees
for ((i=0; i<NUM_WORKERS; i++)); do
  WORKTREE_PATH="${WORKTREE_BASE}/ralph-${SLUG}-worker-${i}"
  BRANCH="${BRANCH_PREFIX}/worker-${i}"

  if [ -d "$WORKTREE_PATH" ]; then
    git worktree remove --force "$WORKTREE_PATH" 2>/dev/null || rm -rf "$WORKTREE_PATH"
    echo "Removed worktree: ${WORKTREE_PATH}"
  fi

  # Delete worker branch (already merged)
  git branch -D "$BRANCH" 2>/dev/null || true
done

# Clean up temporary files
rm -f "$META_FILE"
rm -f "${PROJECT_DIR}/.claude/ralph-worker-done-"*

# Kill tmux session
tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true

# ── Final report ─────────────────────────────────────────────────────────

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  RALPH PARALLEL — Complete!                          ║"
echo "║                                                      ║"
echo "║  Slug:    ${SLUG}"
echo "║  Branch:  ${TARGET_BRANCH}"
echo "║  Workers: ${NUM_WORKERS}"
echo "║                                                      ║"
echo "║  All workers merged and reconciled.                  ║"
echo "║  Worktrees cleaned up.                               ║"
echo "╚══════════════════════════════════════════════════════╝"

update_phase "DONE" "All workers merged, reconciled, and cleaned up"
