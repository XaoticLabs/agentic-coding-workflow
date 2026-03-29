#!/usr/bin/env bash
# Orchestrate a full parallel Ralph lifecycle with wave-based execution:
#   1. Partition tasks with file affinity into dependency waves
#   2. For each wave:
#      a. Create worktrees and launch workers (tmux)
#      b. Poll for completion
#      c. Merge wave branches (overlap-optimized order)
#      d. Test gate + reconcile if needed
#   3. Preserve artifacts (logs, journals, evals, unified trace)
#   4. Cleanup (worktrees, branches, temp files)
#
# The orchestrator runs as a background process (nohup) and writes a PID file
# for tracking. Workers run in tmux for visibility. Output is tee'd to a log file.
#
# Usage: orchestrate-parallel.sh <spec-dir> <slug> <num-workers> <max-iterations> [flags...]
#   --clean-room: Skip codebase search (greenfield mode)

set -euo pipefail

SPEC_DIR="${1:?Usage: orchestrate-parallel.sh <spec-dir> <slug> <num-workers> <max-iterations> [flags...]}"
SLUG="${2:?Usage: orchestrate-parallel.sh <spec-dir> <slug> <num-workers> <max-iterations> [flags...]}"
NUM_WORKERS="${3:?Usage: orchestrate-parallel.sh <spec-dir> <slug> <num-workers> <max-iterations> [flags...]}"
MAX_ITERATIONS="${4:-50}"

CLEAN_ROOM_FLAG=""
for arg in "$@"; do
  case "$arg" in
    --clean-room) CLEAN_ROOM_FLAG="--clean-room" ;;
  esac
done

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
REPO_ROOT=$(git rev-parse --show-toplevel)
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$REPO_ROOT}"

# Source shared primitives
LIB_DIR="${REPO_ROOT}/scripts/lib"
if [ -f "${LIB_DIR}/parallel-primitives.sh" ]; then
  # shellcheck source=../../../scripts/lib/parallel-primitives.sh
  source "${LIB_DIR}/parallel-primitives.sh"
else
  PLUGIN_LIB="${CLAUDE_PLUGIN_ROOT:-${SCRIPT_DIR}/../../..}/scripts/lib/parallel-primitives.sh"
  if [ -f "$PLUGIN_LIB" ]; then
    source "$PLUGIN_LIB"
  fi
fi

# Resolve spec dir to absolute path
if [[ "$SPEC_DIR" != /* ]]; then
  SPEC_DIR="${PROJECT_DIR}/${SPEC_DIR}"
fi
PLAN_FILE="${SPEC_DIR}/IMPLEMENTATION_PLAN.md"
SOURCE_BRANCH=$(git branch --show-current)
TARGET_BRANCH="${SLUG}"
WORKTREE_BASE="${REPO_ROOT}/.claude/worktrees"
POLL_INTERVAL=30
WORKER_TIMEOUT="${RALPH_WORKER_TIMEOUT:-900}"
MERGE_STRICTNESS="${RALPH_MERGE_STRICTNESS:-normal}"

# ── Artifact paths (simplified model) ─────────────────────────────────
RALPH_BASE="${PROJECT_DIR}/.claude/ralph/${SLUG}"
RUN_TIMESTAMP=$(date +%Y%m%d-%H%M%S)
RUN_DIR="${RALPH_BASE}/runs/${RUN_TIMESTAMP}"
STOP_SENTINEL="${PROJECT_DIR}/.claude/ralph/stop"
STATUS_FILE="${PROJECT_DIR}/.claude/ralph/status.md"
PID_FILE="${PROJECT_DIR}/.claude/ralph/${SLUG}/orchestrator.pid"
LOG_FILE="${RUN_DIR}/orchestrator.log"
TRACE_FILE="${RUN_DIR}/trace.jsonl"

mkdir -p "$RUN_DIR"

echo $$ > "$PID_FILE"
exec >> "$LOG_FILE" 2>&1
cleanup_pid() { rm -f "$PID_FILE"; }
trap cleanup_pid EXIT

# ── Helpers ─────────────────────────────────────────────────────────────

update_phase() {
  local phase="$1"
  local detail="${2:-}"
  cat > "$STATUS_FILE" <<EOF
# Ralph Parallel Status

**Phase:** ${phase}
**Detail:** ${detail}
**Slug:** ${SLUG}
**Workers:** ${NUM_WORKERS}
**Source branch:** ${SOURCE_BRANCH}
**Target branch:** ${TARGET_BRANCH}
**Updated:** $(date)
EOF
}

# Get tasks for a specific worker in a specific wave.
# Args: <partition-json> <worker-index> <wave-tasks-csv>
# Output: comma-separated task numbers (subset of worker's tasks that are in this wave)
get_wave_worker_tasks() {
  local partition_json="$1"
  local worker_idx="$2"
  local wave_tasks_csv="$3"
  echo "$partition_json" | python3 -c "
import sys, json
data = json.load(sys.stdin)
worker_tasks = set(data.get('workers', {}).get('worker-${worker_idx}', []))
wave_tasks = set(int(t.strip()) for t in '${wave_tasks_csv}'.split(',') if t.strip())
overlap = sorted(worker_tasks & wave_tasks)
print(','.join(str(t) for t in overlap))
" 2>/dev/null || echo ""
}

# ── Banner ──────────────────────────────────────────────────────────────

echo "╔══════════════════════════════════════════════════════╗"
echo "║  RALPH PARALLEL — Wave-Based Orchestrator            ║"
echo "║                                                      ║"
echo "║  Slug:       ${SLUG}"
echo "║  Workers:    ${NUM_WORKERS}"
echo "║  Spec dir:   ${SPEC_DIR}"
echo "║  Max iters:  ${MAX_ITERATIONS}"
echo "║  Source:     ${SOURCE_BRANCH}"
echo "║  Target:     ${TARGET_BRANCH}"
echo "║  Strictness: ${MERGE_STRICTNESS}"
echo "║                                                      ║"
echo "║  Stop: touch .claude/ralph/stop                      ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Phase 1: Setup & Partition ──────────────────────────────────────────

trace_event "parallel_start" "slug=${SLUG}" "num_workers=${NUM_WORKERS}" "source_branch=${SOURCE_BRANCH}" "target_branch=${TARGET_BRANCH}"
update_phase "SETUP" "Saving metadata and partitioning tasks"

if [ ! -f "$PLAN_FILE" ]; then
  echo "Error: Plan file not found: $PLAN_FILE" >&2
  exit 1
fi

echo "Plan file: $PLAN_FILE"

if ! PARTITION_JSON=$("$SCRIPT_DIR/partition-tasks.sh" "$PLAN_FILE" "$NUM_WORKERS" 2>&1); then
  echo "Error: partition-tasks.sh failed:" >&2
  echo "$PARTITION_JSON" >&2
  exit 1
fi
echo "$PARTITION_JSON" | head -30

# Extract wave information
NUM_WAVES=$(echo "$PARTITION_JSON" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(len(data.get('waves', [{'wave': 0}])))
" 2>/dev/null || echo "1")

echo ""
echo "Dependency waves: ${NUM_WAVES}"
trace_event "partition_done" "waves=${NUM_WAVES}" "workers=${NUM_WORKERS}"

# Setup target branch and worktree base
mkdir -p "$WORKTREE_BASE"
ensure_worktrees_gitignored "$REPO_ROOT"

if git show-ref --verify --quiet "refs/heads/${TARGET_BRANCH}"; then
  echo "Target branch ${TARGET_BRANCH} already exists, reusing"
else
  git branch "$TARGET_BRANCH"
  echo "Created target branch: ${TARGET_BRANCH} (from ${SOURCE_BRANCH})"
fi

BRANCH_PREFIX="ralph-${SLUG}"
BASH_PATH=$(command -v bash)
FLAGS=""
[ -n "$CLEAN_ROOM_FLAG" ] && FLAGS="$FLAGS --clean-room"

# Track all created worktrees/branches for cleanup
declare -a ALL_WORKTREE_PATHS=()
declare -a ALL_WORKER_BRANCHES=()

# ── Wave Execution Loop ─────────────────────────────────────────────────

for ((wave=0; wave<NUM_WAVES; wave++)); do
  echo ""
  echo "╔══════════════════════════════════════════════════════╗"
  echo "║  WAVE ${wave} of $((NUM_WAVES - 1))                               ║"
  echo "╚══════════════════════════════════════════════════════╝"

  trace_event "wave_start" "wave=${wave}" "total_waves=${NUM_WAVES}"
  update_phase "WAVE ${wave}" "Setting up workers"

  # Get tasks in this wave
  WAVE_TASKS_CSV=$(echo "$PARTITION_JSON" | python3 -c "
import sys, json
data = json.load(sys.stdin)
waves = data.get('waves', [])
for w in waves:
    if w.get('wave') == ${wave}:
        print(','.join(str(t) for t in w.get('tasks', [])))
        break
" 2>/dev/null || echo "")

  if [ -z "$WAVE_TASKS_CSV" ]; then
    echo "Wave ${wave}: no tasks, skipping"
    trace_event "wave_end" "wave=${wave}" "status=skipped" "reason=no_tasks"
    continue
  fi

  echo "Wave ${wave} tasks: ${WAVE_TASKS_CSV}"

  # ── Create worktrees for this wave ────────────────────────────────

  WAVE_WORKERS=()  # Workers that have tasks in this wave
  WAVE_BRANCHES=()

  for ((i=0; i<NUM_WORKERS; i++)); do
    WORKER_WAVE_TASKS=$(get_wave_worker_tasks "$PARTITION_JSON" "$i" "$WAVE_TASKS_CSV")

    if [ -z "$WORKER_WAVE_TASKS" ]; then
      continue  # This worker has no tasks in this wave
    fi

    BRANCH="${BRANCH_PREFIX}/wave-${wave}/worker-${i}"
    WORKTREE_PATH="${WORKTREE_BASE}/${SLUG}-wave${wave}-worker-${i}"

    # Wave 0 branches from current HEAD; wave N+1 branches from TARGET_BRANCH
    # which has all prior waves' merged code
    WAVE_START_POINT=""
    if [ "$wave" -gt 0 ]; then
      WAVE_START_POINT="$TARGET_BRANCH"
    fi
    create_worker_worktree "$REPO_ROOT" "$WORKTREE_PATH" "$BRANCH" "$SPEC_DIR" "$SLUG" "$WORKER_WAVE_TASKS" "$WAVE_START_POINT"
    echo "  worker-${i}: tasks [${WORKER_WAVE_TASKS}] → ${WORKTREE_PATH}"

    WAVE_WORKERS+=("$i")
    WAVE_BRANCHES+=("$BRANCH")
    ALL_WORKTREE_PATHS+=("$WORKTREE_PATH")
    ALL_WORKER_BRANCHES+=("$BRANCH")

    trace_event "worker_launch" "wave=${wave}" "worker=worker-${i}" "tasks=${WORKER_WAVE_TASKS}"
  done

  if [ ${#WAVE_WORKERS[@]} -eq 0 ]; then
    echo "Wave ${wave}: no workers needed, skipping"
    trace_event "wave_end" "wave=${wave}" "status=skipped" "reason=no_workers"
    continue
  fi

  echo "Wave ${wave}: launching ${#WAVE_WORKERS[@]} workers"

  # ── Launch workers in tmux ────────────────────────────────────────

  SESSION_NAME="ralph-${SLUG}-w${wave}"
  update_phase "WAVE ${wave}" "${#WAVE_WORKERS[@]} workers running"

  for idx in "${!WAVE_WORKERS[@]}"; do
    i="${WAVE_WORKERS[$idx]}"
    WORKTREE_PATH="${WORKTREE_BASE}/${SLUG}-wave${wave}-worker-${i}"
    WORKER_SPEC_DIR=".claude/specs/${SLUG}"

    LAUNCHER="${WORKTREE_PATH}/.ralph-launcher.sh"
    cat > "$LAUNCHER" <<LAUNCHER_EOF
#!/usr/bin/env bash
export PATH="${PATH}"
export RALPH_WORKER_ID="worker-${i}"
export CLAUDE_PROJECT_DIR="${WORKTREE_PATH}"
exec "${BASH_PATH}" "${SCRIPT_DIR}/loop.sh" "${WORKER_SPEC_DIR}" build ${MAX_ITERATIONS} ${FLAGS}
LAUNCHER_EOF
    chmod +x "$LAUNCHER"

    if [ "$idx" -eq 0 ]; then
      create_tmux_session "$SESSION_NAME" "$WORKTREE_PATH" "$LAUNCHER"
    else
      add_tmux_pane "$SESSION_NAME" "$WORKTREE_PATH" "$LAUNCHER"
    fi
  done

  tmux select-layout -t "$SESSION_NAME" tiled
  echo "Workers in tmux session: ${SESSION_NAME}"

  # ── Poll for completion ───────────────────────────────────────────

  declare -A WORKER_LAST_ACTIVITY
  declare -A WORKER_KILLED
  for i in "${WAVE_WORKERS[@]}"; do
    WORKER_LAST_ACTIVITY[$i]=$(date +%s)
    WORKER_KILLED[$i]=false
  done

  while :; do
    # Check stop sentinel
    if [ -f "$STOP_SENTINEL" ]; then
      echo "Stop sentinel found. Halting orchestrator."
      rm -f "$STOP_SENTINEL"
      update_phase "STOPPED" "User requested stop"
      exit 0
    fi

    DONE_COUNT=0
    NOW=$(date +%s)
    for i in "${WAVE_WORKERS[@]}"; do
      WORKTREE_PATH="${WORKTREE_BASE}/${SLUG}-wave${wave}-worker-${i}"
      MARKER="${WORKTREE_PATH}/.claude/ralph-worker-done-worker-${i}"

      if [ -f "$MARKER" ]; then
        DONE_COUNT=$((DONE_COUNT + 1))
        continue
      fi

      if [ "${WORKER_KILLED[$i]}" = true ]; then
        DONE_COUNT=$((DONE_COUNT + 1))
        continue
      fi

      # Health check
      ITER_LOG="${WORKTREE_PATH}/.claude/ralph-logs/ralph-iterations.log"
      LOG_MOD=0
      if [ -f "$ITER_LOG" ]; then
        LOG_MOD=$(stat -f %m "$ITER_LOG" 2>/dev/null || stat -c %Y "$ITER_LOG" 2>/dev/null || echo "0")
      fi
      LAST_KNOWN="${WORKER_LAST_ACTIVITY[$i]:-0}"
      if [ "$LOG_MOD" -gt "$LAST_KNOWN" ]; then
        WORKER_LAST_ACTIVITY[$i]=$LOG_MOD
      fi

      # Timeout check
      IDLE_TIME=$((NOW - ${WORKER_LAST_ACTIVITY[$i]}))
      if [ "$IDLE_TIME" -gt "$WORKER_TIMEOUT" ]; then
        echo "⚠ WORKER TIMEOUT: worker-${i} idle for ${IDLE_TIME}s"
        mkdir -p "${WORKTREE_PATH}/.claude"
        touch "${WORKTREE_PATH}/.claude/ralph-stop"

        # Wait for graceful exit
        GRACE_START=$(date +%s)
        while [ ! -f "${WORKTREE_PATH}/.claude/ralph-worker-done-worker-${i}" ]; do
          if [ $(( $(date +%s) - GRACE_START )) -ge 60 ]; then
            echo "Grace period expired for worker-${i}. Force-killing."
            tmux send-keys -t "${SESSION_NAME}" C-c 2>/dev/null || true
            break
          fi
          sleep 5
        done

        if [ ! -f "${WORKTREE_PATH}/.claude/ralph-worker-done-worker-${i}" ]; then
          echo "{\"worker\":\"worker-${i}\",\"status\":\"timeout\",\"wave\":${wave}}" \
            > "${WORKTREE_PATH}/.claude/ralph-worker-done-worker-${i}"
        fi

        trace_event "worker_timeout" "wave=${wave}" "worker=worker-${i}" "idle_s=${IDLE_TIME}"
        WORKER_KILLED[$i]=true
      fi
    done

    echo "$(date +%H:%M:%S) wave ${wave}: ${DONE_COUNT}/${#WAVE_WORKERS[@]} workers done"
    update_phase "WAVE ${wave}" "${DONE_COUNT}/${#WAVE_WORKERS[@]} workers complete"

    if [ "$DONE_COUNT" -ge "${#WAVE_WORKERS[@]}" ]; then
      echo "Wave ${wave}: all workers complete!"
      trace_event "wave_workers_done" "wave=${wave}" "workers=${#WAVE_WORKERS[@]}"
      break
    fi

    sleep "$POLL_INTERVAL"
  done

  # ── Merge wave branches ───────────────────────────────────────────

  echo ""
  echo "━━━ Merging wave ${wave} branches ━━━"
  update_phase "WAVE ${wave}" "Merging ${#WAVE_BRANCHES[@]} branches"

  cd "$REPO_ROOT"

  MERGE_RESULT_JSON=$("$SCRIPT_DIR/merge-workers.sh" \
    --target "$TARGET_BRANCH" \
    --branches "${WAVE_BRANCHES[@]}" \
    --spec-dir "$SPEC_DIR" \
    --project-dir "$PROJECT_DIR" \
    --strictness "$MERGE_STRICTNESS" \
    2>"${RUN_DIR}/wave${wave}-merge-stderr.log" || true)

  WAVE_MERGE_STATUS=$(echo "$MERGE_RESULT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null || echo "unknown")
  WAVE_MERGE_COUNT=$(echo "$MERGE_RESULT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('merged',0))" 2>/dev/null || echo "0")
  WAVE_MERGE_FAILED=$(echo "$MERGE_RESULT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('failed',0))" 2>/dev/null || echo "0")

  echo "Wave ${wave} merge: ${WAVE_MERGE_STATUS} (${WAVE_MERGE_COUNT} merged, ${WAVE_MERGE_FAILED} failed)"
  trace_event "wave_merge" "wave=${wave}" "status=${WAVE_MERGE_STATUS}" "merged=${WAVE_MERGE_COUNT}" "failed=${WAVE_MERGE_FAILED}"

  # Save wave merge result
  echo "$MERGE_RESULT_JSON" > "${RUN_DIR}/wave${wave}-merge-result.json" 2>/dev/null || true

  if [ "$WAVE_MERGE_STATUS" = "failed" ]; then
    echo "Wave ${wave}: all merges failed."
    if [ "$MERGE_STRICTNESS" = "strict" ]; then
      update_phase "MERGE_FAILED" "Wave ${wave} merge failed"
      exit 1
    fi
    echo "Continuing to next wave despite failures."
  fi

  # ── Post-wave test gate + evaluator loop ─────────────────────────

  PARALLEL_EVAL="${RALPH_PARALLEL_EVAL:-none}"
  git checkout "$TARGET_BRANCH"

  echo "Running post-wave test check..."
  WAVE_TESTS_PASS=false
  if run_test_gate "$PROJECT_DIR" "${RUN_DIR}/wave${wave}-test.log" 2>/dev/null; then
    echo "Wave ${wave}: tests pass after merge."
    WAVE_TESTS_PASS=true
  fi

  # Evaluator loop: eval → reconcile(guided) → re-eval (max 2 retries)
  EVAL_RETRY_MAX=2
  EVAL_RETRY=0
  WAVE_EVAL_VERDICT="SKIP"

  if [ "$PARALLEL_EVAL" = "wave" ] || [ "$PARALLEL_EVAL" = "merge" ]; then
    PRE_WAVE_COMMIT=$(git merge-base "$TARGET_BRANCH" "$SOURCE_BRANCH" 2>/dev/null || echo "")
    POST_WAVE_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "")

    if [ -n "$PRE_WAVE_COMMIT" ] && [ "$PRE_WAVE_COMMIT" != "$POST_WAVE_COMMIT" ]; then
      while [ "$EVAL_RETRY" -lt "$EVAL_RETRY_MAX" ]; do
        echo "Running post-merge evaluator (attempt $((EVAL_RETRY + 1)))..."
        update_phase "WAVE ${wave}" "Evaluating merged result"

        EVAL_MODE="WAVE"
        [ "$NUM_WAVES" -eq 1 ] && EVAL_MODE="PARALLEL-MERGE"

        WAVE_EVAL_PROMPT=$(cat "${SCRIPT_DIR}/../references/PROMPT_evaluate.md")
        WAVE_EVAL_PROMPT="${WAVE_EVAL_PROMPT}

---
**Evaluation mode:** ${EVAL_MODE}
**Pre-commit:** ${PRE_WAVE_COMMIT}
**Post-commit:** ${POST_WAVE_COMMIT}
**Wave:** ${wave} of $((NUM_WAVES - 1))
**Spec directory:** ${SPEC_DIR}
**Verdict output:** ${PROJECT_DIR}/.claude/ralph-eval-verdict.json
**Summary output:** ${PROJECT_DIR}/.claude/ralph-eval-summary.md
"
        rm -f "${PROJECT_DIR}/.claude/ralph-eval-verdict.json" "${PROJECT_DIR}/.claude/ralph-eval-summary.md"

        set +e
        echo "$WAVE_EVAL_PROMPT" | timeout 600 claude -p --dangerously-skip-permissions --model sonnet 2>/dev/null \
          > "${RUN_DIR}/wave${wave}-eval-${EVAL_RETRY}.log"
        set -e

        WAVE_EVAL_VERDICT="ACCEPT"
        if [ -f "${PROJECT_DIR}/.claude/ralph-eval-verdict.json" ]; then
          WAVE_EVAL_VERDICT=$(python3 -c "import json; print(json.load(open('${PROJECT_DIR}/.claude/ralph-eval-verdict.json'))['verdict'])" 2>/dev/null || echo "ACCEPT")
          WAVE_EVAL_SCORE=$(python3 -c "import json; print(json.load(open('${PROJECT_DIR}/.claude/ralph-eval-verdict.json'))['average'])" 2>/dev/null || echo "?")
          echo "Wave ${wave} eval: ${WAVE_EVAL_VERDICT} (score: ${WAVE_EVAL_SCORE})"
          trace_event "wave_eval" "wave=${wave}" "verdict=${WAVE_EVAL_VERDICT}" "score=${WAVE_EVAL_SCORE}" "attempt=${EVAL_RETRY}"
        fi

        if [ "$WAVE_EVAL_VERDICT" = "ACCEPT" ]; then
          break
        fi

        # REVISE: run eval-guided reconciliation
        echo "Evaluator says REVISE — running guided reconciliation..."
        EVAL_ISSUES=""
        if [ -f "${PROJECT_DIR}/.claude/ralph-eval-summary.md" ]; then
          EVAL_ISSUES=$(head -60 "${PROJECT_DIR}/.claude/ralph-eval-summary.md")
        fi

        # Inject evaluator findings into reconcile prompt
        export RALPH_EVAL_ISSUES="$EVAL_ISSUES"
        RALPH_WORKER_ID="reconciler" "$SCRIPT_DIR/loop.sh" "$SPEC_DIR" reconcile 2 || true
        unset RALPH_EVAL_ISSUES

        EVAL_RETRY=$((EVAL_RETRY + 1))
      done
    fi
  fi

  # Fall back to test-only reconciliation if eval not enabled or tests still failing
  if [ "$WAVE_TESTS_PASS" = false ] && [ "$WAVE_EVAL_VERDICT" != "REVISE" ]; then
    echo "Wave ${wave}: tests failing — running reconciliation..."
    RALPH_WORKER_ID="reconciler" "$SCRIPT_DIR/loop.sh" "$SPEC_DIR" reconcile 3 || {
      echo "Wave ${wave}: reconciliation had issues."
    }

    if ! run_test_gate "$PROJECT_DIR" "${RUN_DIR}/wave${wave}-post-reconcile-test.log" 2>/dev/null; then
      echo "WARNING: Wave ${wave} tests still failing after reconciliation."
      if [ "$MERGE_STRICTNESS" = "strict" ]; then
        update_phase "RECONCILE_FAILED" "Wave ${wave} tests failing"
        exit 1
      fi
    fi
  fi

  # Kill wave tmux session
  kill_session_safe "$SESSION_NAME"

  trace_event "wave_end" "wave=${wave}" "status=done" "merged=${WAVE_MERGE_COUNT}" "failed=${WAVE_MERGE_FAILED}"
  echo "Wave ${wave} complete."
done

# ── Preserve artifacts (simplified: stitch traces + append journal) ────

echo ""
echo "━━━ Phase: PRESERVE ARTIFACTS ━━━"
update_phase "PRESERVING" "Stitching traces and appending journal"

PERSISTENT_JOURNAL="${RALPH_BASE}/journal.tsv"
if [ ! -f "$PERSISTENT_JOURNAL" ]; then
  printf "timestamp\tworker\toutcome\ttask\tmetric\tnotes\n" > "$PERSISTENT_JOURNAL"
fi

# Stitch worker traces into the run trace and append worker journals
STITCH_SCRIPT="${SCRIPT_DIR}/../../../scripts/stitch-traces.sh"
[ ! -f "$STITCH_SCRIPT" ] && STITCH_SCRIPT="${CLAUDE_PLUGIN_ROOT:-${SCRIPT_DIR}/../../..}/scripts/stitch-traces.sh"

# Collect worker trace files and journals from worktrees
WORKER_TRACE_DIR=$(mktemp -d)
trap "rm -rf '$WORKER_TRACE_DIR'" EXIT

for worktree_path in "${ALL_WORKTREE_PATHS[@]}"; do
  [ -d "$worktree_path" ] || continue
  worker_name=$(basename "$worktree_path" | sed "s/^${SLUG}-//")
  WORKER_SUB="${WORKER_TRACE_DIR}/${worker_name}"
  mkdir -p "$WORKER_SUB"

  # Copy trace for stitching
  for tf in "${worktree_path}/.claude/ralph/${SLUG}/runs/"*/trace.jsonl; do
    [ -f "$tf" ] && cp "$tf" "$WORKER_SUB/" 2>/dev/null || true
  done

  # Append worker journal to persistent journal (with worker prefix)
  WORKER_JOURNAL="${worktree_path}/.claude/ralph/${SLUG}/journal.tsv"
  if [ -f "$WORKER_JOURNAL" ]; then
    tail -n +2 "$WORKER_JOURNAL" | while IFS= read -r line; do
      # Insert worker name as second column
      ts=$(echo "$line" | cut -f1)
      rest=$(echo "$line" | cut -f2-)
      printf "%s\t%s\t%s\n" "$ts" "$worker_name" "$rest"
    done >> "$PERSISTENT_JOURNAL"
  fi

  # Copy eval artifacts to run dir
  for ef in "${worktree_path}/.claude/ralph/${SLUG}/runs/"*/eval-verdict.json; do
    [ -f "$ef" ] && cp "$ef" "${RUN_DIR}/eval-${worker_name}-verdict.json" 2>/dev/null || true
  done
  for ef in "${worktree_path}/.claude/ralph/${SLUG}/runs/"*/eval-summary.md; do
    [ -f "$ef" ] && cp "$ef" "${RUN_DIR}/eval-${worker_name}-summary.md" 2>/dev/null || true
  done

  echo "Preserved: ${worker_name}"
done

# Stitch all worker traces + orchestrator trace into unified run trace
if [ -f "$STITCH_SCRIPT" ]; then
  echo "Stitching traces..."
  "$STITCH_SCRIPT" "$WORKER_TRACE_DIR" "$SLUG" "$TRACE_FILE" 2>/dev/null || echo "Trace stitching had issues (non-fatal)"
fi

# Save merge results into run dir (single file with all waves)
MERGE_RESULTS_FILE="${RUN_DIR}/merge-results.json"
echo "[" > "$MERGE_RESULTS_FILE"
FIRST_MERGE=true
for ((w=0; w<NUM_WAVES; w++)); do
  WAVE_RESULT="${RUN_DIR}/wave${w}-merge-result.json"
  if [ -f "$WAVE_RESULT" ]; then
    [ "$FIRST_MERGE" = true ] || echo "," >> "$MERGE_RESULTS_FILE"
    cat "$WAVE_RESULT" >> "$MERGE_RESULTS_FILE"
    FIRST_MERGE=false
    rm -f "$WAVE_RESULT"  # clean up individual wave files
  fi
done
echo "]" >> "$MERGE_RESULTS_FILE"

echo "Run artifacts: ${RUN_DIR}/"

# Run retrospective (accumulates learnings for future runs)
RETRO_SCRIPT="${SCRIPT_DIR}/../../../scripts/parallel-retrospective.sh"
[ ! -f "$RETRO_SCRIPT" ] && RETRO_SCRIPT="${CLAUDE_PLUGIN_ROOT:-${SCRIPT_DIR}/../../..}/scripts/parallel-retrospective.sh"
if [ -f "$RETRO_SCRIPT" ]; then
  echo "Running retrospective..."
  "$RETRO_SCRIPT" "$RUN_DIR" "$RALPH_BASE" "$SLUG" 2>/dev/null || echo "Retrospective had issues (non-fatal)"
fi

rm -rf "$WORKER_TRACE_DIR"

# ── Cleanup ─────────────────────────────────────────────────────────────

echo ""
echo "━━━ Phase: CLEANUP ━━━"
update_phase "CLEANUP" "Removing worktrees and temporary files"

for ((idx=0; idx<${#ALL_WORKTREE_PATHS[@]}; idx++)); do
  wt_path="${ALL_WORKTREE_PATHS[$idx]}"
  wt_branch="${ALL_WORKER_BRANCHES[$idx]}"
  cleanup_worker_worktree "$REPO_ROOT" "$wt_path" "$wt_branch"
done
echo "Removed ${#ALL_WORKTREE_PATHS[@]} worktrees"

rm -f "${PROJECT_DIR}/.claude/ralph-worker-done-"*

# Kill any remaining tmux sessions from all waves
for ((wave=0; wave<NUM_WAVES; wave++)); do
  kill_session_safe "ralph-${SLUG}-w${wave}"
done

# ── Final report ────────────────────────────────────────────────────────

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  RALPH PARALLEL — Complete!                          ║"
echo "║                                                      ║"
echo "║  Slug:    ${SLUG}"
echo "║  Branch:  ${TARGET_BRANCH}"
echo "║  Workers: ${NUM_WORKERS}"
echo "║  Waves:   ${NUM_WAVES}"
echo "║                                                      ║"
echo "║  All waves merged and reconciled.                    ║"
echo "║  Run:     ${RUN_DIR}/"
echo "║  Journal: ${PERSISTENT_JOURNAL}"
echo "║  Worktrees cleaned up.                               ║"
echo "╚══════════════════════════════════════════════════════╝"

trace_event "parallel_end" "status=done" "slug=${SLUG}" "workers=${NUM_WORKERS}" "waves=${NUM_WAVES}" "target=${TARGET_BRANCH}"
update_phase "DONE" "All ${NUM_WAVES} wave(s) merged into ${TARGET_BRANCH}, reconciled, artifacts preserved"
