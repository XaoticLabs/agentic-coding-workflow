#!/usr/bin/env bash
# Ralph loop — drives autonomous Claude iterations
# Each iteration: pick task → implement → test → commit → update plan → exit
#
# Usage: loop.sh <spec-dir> [mode] [max-iterations] [flags...]
#   spec-dir:       Path to the spec directory containing IMPLEMENTATION_PLAN.md
#   mode:           "build" (default), "plan", or "harvest"
#   max-iterations: Maximum iterations before stopping (default: 50)
#   --once:         Run a single iteration then stop (HITL mode)
#   --clean-room:   Skip codebase search (greenfield mode)
#   --time-budget:  Max seconds per iteration (default: 600, 0 = no limit)

set -euo pipefail

SPEC_DIR="${1:?Usage: loop.sh <spec-dir> [mode] [max-iterations] [flags...]}"
MODE="${2:-build}"
MAX_ITERATIONS="${3:-50}"
ONCE_FLAG=""
CLEAN_ROOM_FLAG=""
TIME_BUDGET="600"  # 10 minutes default, 0 = no limit

# Check for flags in any position
for arg in "$@"; do
  case "$arg" in
    --once)       ONCE_FLAG="1" ;;
    --clean-room) CLEAN_ROOM_FLAG="1" ;;
    --time-budget=*) TIME_BUDGET="${arg#--time-budget=}" ;;
  esac
done

PLAN_FILE="${SPEC_DIR}/IMPLEMENTATION_PLAN.md"
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
SCRIPT_DIR="$(dirname "$(realpath "$0")")"
PROMPT_DIR="${SCRIPT_DIR}/../references"

SLUG=$(basename "$SPEC_DIR")
STREAM_PROCESSOR="${SCRIPT_DIR}/stream-processor.py"

# ── Artifact paths (simplified model) ─────────────────────────────────
# All ralph artifacts live under .claude/ralph/<slug>/
# Per-run artifacts go in .claude/ralph/<slug>/runs/<timestamp>/
# Journal appends across runs at .claude/ralph/<slug>/journal.tsv
RALPH_BASE="${PROJECT_DIR}/.claude/ralph/${SLUG}"
RUN_TIMESTAMP=$(date +%Y%m%d-%H%M%S)
RUN_DIR="${RALPH_BASE}/runs/${RUN_TIMESTAMP}"
LOG_DIR="${RUN_DIR}"
STOP_SENTINEL="${PROJECT_DIR}/.claude/ralph/stop"
STATUS_FILE="${PROJECT_DIR}/.claude/ralph/status.md"
INJECT_FILE="${PROJECT_DIR}/.claude/ralph/inject.md"
PROGRESS_FILE="${PROJECT_DIR}/.claude/ralph-progress.md"
JOURNAL_FILE="${RALPH_BASE}/journal.tsv"
READONLY_FILE="${SPEC_DIR}/RALPH_READONLY"
OVERRIDES_FILE="${SPEC_DIR}/RALPH_OVERRIDES.md"

# Source shared primitives (for ensure_worktrees_gitignored, detect_test_command, etc.)
_LIB_DIR="${SCRIPT_DIR}/../../../scripts/lib"
if [ -f "${_LIB_DIR}/parallel-primitives.sh" ]; then
  source "${_LIB_DIR}/parallel-primitives.sh"
else
  PLUGIN_LIB="${CLAUDE_PLUGIN_ROOT:-${SCRIPT_DIR}/../../..}/scripts/lib/parallel-primitives.sh"
  [ -f "$PLUGIN_LIB" ] && source "$PLUGIN_LIB"
fi

# ── Evaluator configuration ──────────────────────────────────────────
# Default: single evaluator pass at END of run (reviews full body of work).
# Per-iteration evaluation is opt-in for edge-of-capability tasks.
#
# The evaluator's value depends on where the task sits relative to what the
# model can do reliably solo. For tasks within the model's comfort zone,
# per-iteration evaluation is unnecessary overhead. For tasks at the edge,
# it gives real lift. (See: Anthropic harness design article)
EVAL_VERDICT_FILE="${RUN_DIR}/eval-verdict.json"
EVAL_SUMMARY_FILE="${RUN_DIR}/eval-summary.md"
# Contracts removed — acceptance criteria now live inline in IMPLEMENTATION_PLAN.md
RALPH_EVALUATE_UI="${RALPH_EVALUATE_UI:-false}"
# Per-iteration evaluation (opt-in for hard tasks)
EVAL_PER_ITER="${RALPH_EVAL_PER_ITER:-false}"            # Run evaluator per-iteration (default: end-of-run only)
EVAL_DIFF_THRESHOLD="${RALPH_EVAL_DIFF_THRESHOLD:-5}"    # Files changed to trigger per-iter eval (when enabled)
# End-of-run evaluation (default: on)
EVAL_END_OF_RUN="${RALPH_EVAL_END_OF_RUN:-true}"         # Run evaluator once at end of run

mkdir -p "$RUN_DIR" || { echo "ERROR: Failed to create run directory: ${RUN_DIR}" >&2; exit 1; }
mkdir -p "$RALPH_BASE" || { echo "ERROR: Failed to create ralph base: ${RALPH_BASE}" >&2; exit 1; }
if [ ! -w "$RUN_DIR" ]; then
  echo "ERROR: Run directory is not writable: ${RUN_DIR}" >&2
  exit 1
fi

# ── Trace file (single structured log for the run) ───────────────────
TRACE_FILE="${RUN_DIR}/trace.jsonl"

# ── Trace event helper ────────────────────────────────────────────────
# Appends a single JSON line to the trace file.
# Usage: trace_event <type> [key=value ...]
trace_event() {
  local type="$1"
  shift
  local json="{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"type\":\"${type}\""
  for kv in "$@"; do
    local key="${kv%%=*}"
    local val="${kv#*=}"
    if [[ "$val" =~ ^[0-9]+$ ]]; then
      json="${json},\"${key}\":${val}"
    elif [[ "$val" == "true" || "$val" == "false" ]]; then
      json="${json},\"${key}\":${val}"
    else
      # Escape quotes and collapse newlines, truncate for safety
      val=$(printf '%s' "$val" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n' ' ' | head -c 500)
      json="${json},\"${key}\":\"${val}\""
    fi
  done
  json="${json}}"
  echo "$json" >> "$TRACE_FILE"
}

# ── Initialize failure journal ────────────────────────────────────────
if [ ! -f "$JOURNAL_FILE" ]; then
  printf "timestamp\toutcome\ttask\tmetric\tnotes\n" > "$JOURNAL_FILE"
fi

# ── Resolve prompt template ─────────────────────────────────────────────

case "$MODE" in
  plan)       PROMPT_TEMPLATE="${PROMPT_DIR}/PROMPT_plan.md" ;;
  build)      PROMPT_TEMPLATE="${PROMPT_DIR}/PROMPT_build.md" ;;
  harvest)    PROMPT_TEMPLATE="${PROMPT_DIR}/PROMPT_harvest.md" ;;
  reconcile)  PROMPT_TEMPLATE="${PROMPT_DIR}/PROMPT_reconcile.md" ;;
  evaluate)   PROMPT_TEMPLATE="${PROMPT_DIR}/PROMPT_evaluate.md" ;;
  *)          echo "Error: mode must be 'plan', 'build', 'harvest', 'evaluate', or 'reconcile'"; exit 1 ;;
esac

if [ ! -f "$PROMPT_TEMPLATE" ]; then
  echo "Error: prompt template not found: $PROMPT_TEMPLATE"
  exit 1
fi

# ── Safety warning ──────────────────────────────────────────────────────

echo "╔══════════════════════════════════════════════════════╗"
echo "║  RALPH LOOP — Autonomous Coding Mode                ║"
echo "║                                                     ║"
echo "║  Mode:       ${MODE}                                "
echo "║  Spec dir:   ${SPEC_DIR}                            "
echo "║  Max iters:  ${MAX_ITERATIONS}                      "
echo "║  Time budget: $( [ "$TIME_BUDGET" = "0" ] && echo "unlimited" || echo "${TIME_BUDGET}s" )"
echo "║  Once:       ${ONCE_FLAG:-no}                       "
echo "║  Clean-room: ${CLEAN_ROOM_FLAG:-no}                 "
echo "║  Worktree:  auto (build/reconcile modes)              "
echo "║  Protected:  $( [ -f "$READONLY_FILE" ] && echo "yes ($(wc -l < "$READONLY_FILE") patterns)" || echo "no" )"
echo "║  Overrides:  $( [ -f "$OVERRIDES_FILE" ] && echo "yes ($(wc -l < "$OVERRIDES_FILE") lines)" || echo "no" )"
echo "║  Criteria:   inline (in IMPLEMENTATION_PLAN.md)"
echo "║  Evaluator:  $( [ "$EVAL_PER_ITER" = "true" ] && echo "per-iteration (>=${EVAL_DIFF_THRESHOLD} files)" || echo "end-of-run" )"
echo "║  UI eval:    ${RALPH_EVALUATE_UI}"
echo "║                                                     ║"
echo "║  Stop gracefully: touch .claude/ralph-stop          ║"
echo "║  Steer mid-loop:  write .claude/ralph-inject.md     ║"
echo "║  This uses --dangerously-skip-permissions           ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Pre-flight checks ──────────────────────────────────────────────────

if [ "$MODE" = "build" ] && [ ! -f "$PLAN_FILE" ]; then
  echo "Error: No IMPLEMENTATION_PLAN.md found at ${PLAN_FILE}"
  echo "Run with mode=plan first, or create the plan via /write-spec --ralph"
  exit 1
fi

# Clean up any previous stop sentinel
rm -f "$STOP_SENTINEL"

# ── Register output validation for plan mode ──────────────────────────
# The validate-output.py stop hook checks expected-output.json to catch
# format errors at plan-creation time. The partitioner and loop.sh parse
# task index lines with regex — if the planner emits a different format,
# parallel mode silently treats all tasks as "complete" and does nothing.
if [ "$MODE" = "plan" ]; then
  cat > "${PROJECT_DIR}/.claude/expected-output.json" <<VALIDATE_EOF
{
    "source": "ralph-plan",
    "rules": [
        {
            "type": "file_exists",
            "path": "${SPEC_DIR}/IMPLEMENTATION_PLAN.md"
        },
        {
            "type": "file_contains",
            "path": "${SPEC_DIR}/IMPLEMENTATION_PLAN.md",
            "sections": ["## Task Index", "## Tasks", "## Status: IN_PROGRESS"]
        },
        {
            "type": "file_min_lines",
            "path": "${SPEC_DIR}/IMPLEMENTATION_PLAN.md",
            "min_lines": 15
        },
        {
            "type": "task_index_format",
            "path": "${SPEC_DIR}/IMPLEMENTATION_PLAN.md",
            "min_tasks": 1
        }
    ]
}
VALIDATE_EOF
  echo "Registered plan output validation (expected-output.json)"
fi

# ── Plan integrity check ─────────────────────────────────────────────
# Verify that [x] tasks with "Completed in <hash>" reference commits
# reachable from HEAD. If a previous run was interrupted after reverts,
# the plan file on disk may claim tasks are done when their commits are
# orphaned (reverted via git reset --hard). Re-mark these as incomplete.

if [ "$MODE" = "build" ] && [ -f "$PLAN_FILE" ]; then
  INTEGRITY_FIXES=0
  while IFS= read -r line; do
    # Extract commit hash from "Completed in <hash>"
    hash=$(echo "$line" | grep -o 'Completed in [a-f0-9]*' | awk '{print $3}' || true)
    if [ -z "$hash" ]; then
      continue
    fi
    # Check if commit is reachable from HEAD
    if ! git merge-base --is-ancestor "$hash" HEAD 2>/dev/null; then
      # Extract task number for logging
      task_num=$(echo "$line" | grep -o 'Task [0-9]*' | head -1)
      echo "⚠ INTEGRITY: ${task_num} references orphaned commit ${hash:0:8} — re-marking incomplete"
      # Re-mark as incomplete: replace "- [x]" with "- [ ]" and strip "Completed in <hash>"
      escaped_hash=$(echo "$hash" | sed 's/[.[\*^$()+?{}|]/\\&/g')
      sed -i.bak "s/^\(- \)\[x\]\(.*\) — Completed in ${escaped_hash}.*/\1[ ]\2/" "$PLAN_FILE"
      # Also ensure status is not COMPLETE if we just un-did a task
      sed -i.bak 's/^## Status: COMPLETE/## Status: IN_PROGRESS/' "$PLAN_FILE"
      INTEGRITY_FIXES=$((INTEGRITY_FIXES + 1))
      printf "%s\tINTEGRITY_FIX\t%s\t-\tOrphaned commit %s re-marked incomplete\n" \
        "$(date +"%Y-%m-%dT%H:%M:%S")" "${task_num:-unknown}" "$hash" >> "$JOURNAL_FILE"
      trace_event "integrity_fix" "task=${task_num:-unknown}" "orphaned_commit=$hash"
    fi
  done < <(grep '^\- \[x\]' "$PLAN_FILE" 2>/dev/null || true)
  rm -f "${PLAN_FILE}.bak"

  if [ "$INTEGRITY_FIXES" -gt 0 ]; then
    echo "  Fixed ${INTEGRITY_FIXES} orphaned task(s). Plan integrity restored."
    echo ""
  fi
fi

# ── Worktree isolation (single-track build mode) ────────────────────────
# Always run build mode in a worktree for branch isolation.
# Skip if: parallel worker (already has worktree), or plan/harvest mode (read-only).

USING_WORKTREE=false
MAIN_PROJECT_DIR="$PROJECT_DIR"
MAIN_STOP_SENTINEL="$STOP_SENTINEL"

if [ -z "${RALPH_WORKER_ID:-}" ] && [[ "$MODE" == "build" || "$MODE" == "reconcile" ]]; then
  TARGET_BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || echo "main")
  REPO_ROOT=$(git rev-parse --show-toplevel)
  WORKTREE_BRANCH="${SLUG}"
  WORKTREE_BASE="${REPO_ROOT}/.claude/worktrees"
  WORKTREE_PATH="${WORKTREE_BASE}/${SLUG}"

  # Ensure .claude/worktrees/ is gitignored
  ensure_worktrees_gitignored "$REPO_ROOT"

  # Remove stale worktree if it exists
  if [ -d "$WORKTREE_PATH" ]; then
    echo "Removing stale worktree: ${WORKTREE_PATH}"
    git worktree remove --force "$WORKTREE_PATH" 2>/dev/null || rm -rf "$WORKTREE_PATH"
  fi

  # Remove stale branch if it exists
  if git show-ref --verify --quiet "refs/heads/$WORKTREE_BRANCH"; then
    git branch -D "$WORKTREE_BRANCH" 2>/dev/null || true
  fi

  mkdir -p "$WORKTREE_BASE"
  git worktree add -b "$WORKTREE_BRANCH" "$WORKTREE_PATH"
  echo "Created worktree: ${WORKTREE_PATH} (branch: ${WORKTREE_BRANCH})"

  # Copy spec directory and supporting files into worktree
  mkdir -p "${WORKTREE_PATH}/.claude/specs/"
  cp -r "$SPEC_DIR" "${WORKTREE_PATH}/.claude/specs/${SLUG}/" || { echo "ERROR: Failed to copy spec directory to worktree" >&2; exit 1; }
  if [ ! -f "${WORKTREE_PATH}/.claude/specs/${SLUG}/IMPLEMENTATION_PLAN.md" ]; then
    echo "ERROR: Plan file missing in worktree after copy: ${WORKTREE_PATH}/.claude/specs/${SLUG}/IMPLEMENTATION_PLAN.md" >&2
    exit 1
  fi
  mkdir -p "${WORKTREE_PATH}/.claude/ralph/${SLUG}/runs/${RUN_TIMESTAMP}"
  [ -f "${PROJECT_DIR}/.claude/AGENTS.md" ] && cp "${PROJECT_DIR}/.claude/AGENTS.md" "${WORKTREE_PATH}/.claude/"

  # Switch into worktree and re-point all path variables
  if [ ! -d "$WORKTREE_PATH" ]; then
    echo "ERROR: Worktree directory does not exist: ${WORKTREE_PATH}" >&2
    exit 1
  fi
  cd "$WORKTREE_PATH" || { echo "ERROR: Failed to cd into worktree: ${WORKTREE_PATH}" >&2; exit 1; }
  PROJECT_DIR="$WORKTREE_PATH"
  SPEC_DIR=".claude/specs/${SLUG}"
  PLAN_FILE="${SPEC_DIR}/IMPLEMENTATION_PLAN.md"
  RALPH_BASE="${PROJECT_DIR}/.claude/ralph/${SLUG}"
  RUN_DIR="${RALPH_BASE}/runs/${RUN_TIMESTAMP}"
  LOG_DIR="${RUN_DIR}"
  STOP_SENTINEL="${PROJECT_DIR}/.claude/ralph/stop"
  STATUS_FILE="${PROJECT_DIR}/.claude/ralph/status.md"
  INJECT_FILE="${PROJECT_DIR}/.claude/ralph/inject.md"
  PROGRESS_FILE="${PROJECT_DIR}/.claude/ralph-progress.md"
  JOURNAL_FILE="${RALPH_BASE}/journal.tsv"
  READONLY_FILE="${SPEC_DIR}/RALPH_READONLY"
  OVERRIDES_FILE="${SPEC_DIR}/RALPH_OVERRIDES.md"
  EVAL_VERDICT_FILE="${RUN_DIR}/eval-verdict.json"
  EVAL_SUMMARY_FILE="${RUN_DIR}/eval-summary.md"

  # Re-initialize run dir and journal in worktree
  mkdir -p "$RUN_DIR"
  if [ ! -f "$JOURNAL_FILE" ]; then
    printf "timestamp\toutcome\ttask\tmetric\tnotes\n" > "$JOURNAL_FILE"
  fi
  TRACE_FILE="${RUN_DIR}/trace.jsonl"

  USING_WORKTREE=true

  echo ""
  echo "  Worktree: ${WORKTREE_PATH}"
  echo "  Branch:   ${WORKTREE_BRANCH}"
  echo "  ORC will auto-discover this worktree."
  echo ""
fi

# ── Struggle detection helpers ──────────────────────────────────────────

LAST_TASK=""
SAME_TASK_COUNT=0
STRUGGLE_THRESHOLD=3

# Extract the current top-priority incomplete task name from the plan
get_current_task() {
  if [ -f "$PLAN_FILE" ]; then
    grep -m1 '^\- \[ \] \*\*Task' "$PLAN_FILE" 2>/dev/null | sed 's/.*\*\*Task [0-9]*: \(.*\)\*\*.*/\1/' || echo ""
  fi
}

# ── Circuit breaker helpers ─────────────────────────────────────────────

COMMITS_AT_START=$(git rev-list --count HEAD 2>/dev/null || echo "0")
COMMITS_AT_START_HASH=$(git rev-parse HEAD 2>/dev/null || echo "none")
CIRCUIT_BREAKER_WINDOW=5     # Check every N iterations
CIRCUIT_BREAKER_MIN_RATIO=30 # Minimum commit% (commits/iterations * 100)
CONSECUTIVE_REVERTS=0        # Track consecutive reverts across different tasks
CONSECUTIVE_REVERT_TASKS=""  # Track which tasks were reverted consecutively
CIRCUIT_BREAKER_SOFT_WARNED=false  # Only warn once per soft break

check_circuit_breaker() {
  local iteration=$1
  if [ "$iteration" -lt "$CIRCUIT_BREAKER_WINDOW" ]; then
    return 0  # Too early to judge
  fi

  # Only check at window boundaries
  if [ $((iteration % CIRCUIT_BREAKER_WINDOW)) -ne 0 ]; then
    return 0
  fi

  local commits_now
  commits_now=$(git rev-list --count HEAD 2>/dev/null || echo "0")
  local new_commits=$((commits_now - COMMITS_AT_START))
  local ratio=$((new_commits * 100 / iteration))

  if [ "$ratio" -lt "$CIRCUIT_BREAKER_MIN_RATIO" ]; then
    # Hard break: low ratio AND 3+ consecutive reverts on different tasks (systemic failure)
    if [ "$CONSECUTIVE_REVERTS" -ge 3 ]; then
      echo ""
      echo "⚡ HARD CIRCUIT BREAK: ${ratio}% success rate AND ${CONSECUTIVE_REVERTS} consecutive reverts on different tasks."
      echo "   This indicates a systemic issue, not just a hard task."
      echo "   Recent revert tasks: ${CONSECUTIVE_REVERT_TASKS}"
      echo "   Stopping immediately. Review test infrastructure, project setup, or plan quality."
      return 1
    fi

    # Soft break: low ratio but might recover — warn in briefing but continue
    if [ "$CIRCUIT_BREAKER_SOFT_WARNED" = false ]; then
      echo ""
      echo "⚠ SOFT CIRCUIT BREAK: Only ${new_commits} commits in ${iteration} iterations (${ratio}% success rate)."
      echo "   Threshold is ${CIRCUIT_BREAKER_MIN_RATIO}%. Ralph may be struggling."
      echo "   Continuing — will hard-stop if 3+ consecutive reverts on different tasks occur."
      CIRCUIT_BREAKER_SOFT_WARNED=true
      printf "%s\tSOFT_CIRCUIT_BREAK\t-\tratio=%s%%\tLow commit ratio but continuing\n" \
        "$(date +"%Y-%m-%dT%H:%M:%S")" "$ratio" >> "$JOURNAL_FILE"
      trace_event "circuit_break" "type_detail=soft" "reason=Low commit ratio ${ratio}%"
    fi
  fi
  return 0
}

# Track consecutive reverts for hard circuit breaker
track_revert() {
  local task="$1"
  CONSECUTIVE_REVERTS=$((CONSECUTIVE_REVERTS + 1))
  CONSECUTIVE_REVERT_TASKS="${CONSECUTIVE_REVERT_TASKS:+${CONSECUTIVE_REVERT_TASKS}, }${task}"
}

track_success() {
  CONSECUTIVE_REVERTS=0
  CONSECUTIVE_REVERT_TASKS=""
}

# ── Evaluator phase (tiered: light vs full) ───────────────────────────
# Returns 0 = ACCEPT, 1 = REVISE, 2 = skipped (light eval)
run_evaluator() {
  local pre_commit="$1"
  local post_commit="$2"
  local task_label="$3"
  local iteration="$4"

  # Determine whether to run full evaluation
  local diff_file_count
  diff_file_count=$(git diff --name-only "$pre_commit" "$post_commit" | wc -l | tr -d ' ')
  # Per-iteration evaluation must be explicitly enabled.
  # Default is end-of-run only (per Anthropic harness design findings).
  local run_full=false
  if [ "$EVAL_PER_ITER" = "true" ]; then
    if [ "$diff_file_count" -ge "$EVAL_DIFF_THRESHOLD" ]; then
      run_full=true
    fi
  fi

  if [ "$run_full" = "false" ]; then
    echo "  Evaluator: LIGHT mode (${diff_file_count} files changed, threshold ${EVAL_DIFF_THRESHOLD}). Skipping LLM evaluation."
    trace_event "evaluator" "tier=light" "files_changed=${diff_file_count}"
    return 2
  fi

  echo "  Evaluator: FULL mode (${diff_file_count} files changed). Launching evaluation..."
  trace_event "evaluator" "tier=full" "files_changed=${diff_file_count}"

  # Build evaluator prompt
  local eval_prompt
  eval_prompt=$(cat "${PROMPT_DIR}/PROMPT_evaluate.md")

  # Append context metadata
  eval_prompt="${eval_prompt}

---
**Pre-commit:** ${pre_commit}
**Post-commit:** ${post_commit}
**Task:** ${task_label}
**Iteration:** ${iteration}
**Spec directory:** ${SPEC_DIR}
**UI evaluation:** ${RALPH_EVALUATE_UI}
**Verdict output:** ${EVAL_VERDICT_FILE}
**Summary output:** ${EVAL_SUMMARY_FILE}
"

  # Run evaluator as a separate Claude session
  rm -f "$EVAL_VERDICT_FILE" "$EVAL_SUMMARY_FILE"

  local eval_log="${LOG_DIR}/eval-${iteration}-$(date +%Y%m%d-%H%M%S).log"
  local eval_timeout="${RALPH_EVAL_TIMEOUT:-300}"  # 5 min default for evaluation

  local EVAL_TIMEOUT_CMD=""
  if command -v timeout >/dev/null 2>&1; then
    EVAL_TIMEOUT_CMD="timeout $eval_timeout"
  elif command -v gtimeout >/dev/null 2>&1; then
    EVAL_TIMEOUT_CMD="gtimeout $eval_timeout"
  fi

  set +e
  if [ -n "$EVAL_TIMEOUT_CMD" ]; then
    echo "$eval_prompt" | $EVAL_TIMEOUT_CMD claude -p --dangerously-skip-permissions --verbose --model sonnet --output-format stream-json 2>/dev/null \
      | "$STREAM_PROCESSOR" --trace-file "$TRACE_FILE" > "$eval_log"
  else
    echo "$eval_prompt" | claude -p --dangerously-skip-permissions --verbose --model sonnet --output-format stream-json 2>/dev/null \
      | "$STREAM_PROCESSOR" --trace-file "$TRACE_FILE" > "$eval_log"
  fi
  local eval_exit=$?
  set -e

  # Parse verdict
  if [ -f "$EVAL_VERDICT_FILE" ]; then
    local verdict
    verdict=$(python3 -c "import json; print(json.load(open('${EVAL_VERDICT_FILE}'))['verdict'])" 2>/dev/null || echo "UNKNOWN")
    local avg_score
    avg_score=$(python3 -c "import json; print(json.load(open('${EVAL_VERDICT_FILE}'))['average'])" 2>/dev/null || echo "?")

    echo "  Evaluator verdict: ${verdict} (avg score: ${avg_score})"
    trace_event "eval_verdict" "verdict=${verdict}" "avg_score=${avg_score}" "task=${task_label}" "iter=${iteration}"

    if [ "$verdict" = "ACCEPT" ]; then
      return 0
    elif [ "$verdict" = "REVISE" ]; then
      local guidance
      guidance=$(python3 -c "import json; v=json.load(open('${EVAL_VERDICT_FILE}')); print(v.get('revise_guidance','No guidance provided'))" 2>/dev/null || echo "Check eval summary")
      echo "  Evaluator says REVISE: ${guidance:0:200}"
      return 1
    else
      echo "  Evaluator returned unknown verdict: ${verdict}. Treating as ACCEPT."
      return 0
    fi
  else
    echo "  Evaluator did not produce a verdict file. Treating as ACCEPT (evaluation error, not blocking)."
    trace_event "eval_error" "reason=no_verdict_file" "exit_code=${eval_exit}"
    return 0
  fi
}

# ── Progress dashboard writer ───────────────────────────────────────────

write_status() {
  local iteration=$1
  local task_name=$2
  local result=$3

  local total_tasks=0 done_tasks=0
  if [ -f "$PLAN_FILE" ]; then
    total_tasks=$(grep -c '^\- \[[ x]\] \*\*Task' "$PLAN_FILE" 2>/dev/null || true); total_tasks=${total_tasks:-0}
    done_tasks=$(grep -c '^\- \[x\] \*\*Task' "$PLAN_FILE" 2>/dev/null || true); done_tasks=${done_tasks:-0}
  fi

  local commits_now
  commits_now=$(git rev-list --count HEAD 2>/dev/null || echo "0")
  local new_commits=$((commits_now - COMMITS_AT_START))
  local elapsed=$(($(date +%s) - START_TIME))
  local minutes=$((elapsed / 60))

  cat > "$STATUS_FILE" <<EOF
# Ralph Status Dashboard

**Last updated:** $(date)
**Spec:** ${SPEC_DIR}
**Mode:** ${MODE}

## Progress

- **Iteration:** ${iteration} / ${MAX_ITERATIONS}
- **Tasks:** ${done_tasks} / ${total_tasks} complete
- **Commits:** ${new_commits} in this run
- **Elapsed:** ${minutes} minutes
- **Success rate:** $( KEPT=$(tail -n +2 "$JOURNAL_FILE" 2>/dev/null | grep -c 'KEEP' || echo 0); REAL=$(tail -n +2 "$JOURNAL_FILE" 2>/dev/null | grep -cE 'KEEP|REVERT|TIMEOUT' || echo 0); [ "$REAL" -gt 0 ] && echo "$((KEPT * 100 / REAL))%" || echo "N/A" )
- **Last task:** ${task_name}
- **Last result:** ${result}

## Recent Iterations

$(tail -20 "$JOURNAL_FILE" 2>/dev/null || echo "(no journal entries yet)")
EOF
}

# ── Main loop ───────────────────────────────────────────────────────────

ITERATION=0
START_TIME=$(date +%s)

# Trace: run start
trace_event "run_start" "slug=${SLUG}" "mode=${MODE}" "max_iters=${MAX_ITERATIONS}"

# Run start marker in journal (if this is a fresh journal)
echo "# Ralph Run — $(date) — ${MODE} mode" >> "${RUN_DIR}/orchestrator.log" 2>/dev/null || true

while :; do
  ITERATION=$((ITERATION + 1))
  ITER_START_TIME=$(date +%s)
  TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
  INJECTION_CONSUMED=""
  LOG_FILE="${LOG_DIR}/iter-${ITERATION}-${TIMESTAMP}.log"

  echo "━━━ Iteration ${ITERATION}/${MAX_ITERATIONS} ━━━ $(date) ━━━"

  # Check stop sentinel (check main repo too when running in a worktree)
  if [ -f "$STOP_SENTINEL" ] || [ -f "$MAIN_STOP_SENTINEL" ]; then
    echo "Stop sentinel found. Exiting gracefully."
    rm -f "$STOP_SENTINEL" "$MAIN_STOP_SENTINEL" 2>/dev/null || true
    break
  fi

  # Check if plan is complete (build mode only)
  if [ "$MODE" = "build" ] && [ -f "$PLAN_FILE" ]; then
    if grep -q "## Status: COMPLETE" "$PLAN_FILE"; then
      echo "All tasks complete! Plan status: COMPLETE"
      break
    fi
  fi

  # Check max iterations
  if [ "$ITERATION" -gt "$MAX_ITERATIONS" ]; then
    echo "Max iterations (${MAX_ITERATIONS}) reached. Stopping."
    break
  fi

  # ── Struggle detection ──────────────────────────────────────────────
  if [ "$MODE" = "build" ]; then
    CURRENT_TASK=$(get_current_task)
    if [ -n "$CURRENT_TASK" ] && [ "$CURRENT_TASK" = "$LAST_TASK" ]; then
      SAME_TASK_COUNT=$((SAME_TASK_COUNT + 1))
      if [ "$SAME_TASK_COUNT" -ge "$STRUGGLE_THRESHOLD" ]; then
        echo ""
        echo "⚠ STRUGGLE DETECTED: Task '${CURRENT_TASK}' has been attempted ${SAME_TASK_COUNT} times."
        echo "  Ralph may be stuck. Stopping to prevent token waste."
        echo "  Review logs and consider breaking the task down or adding context."
        echo "${ITERATION} | $(date +%H:%M:%S) | STRUGGLE_STOP | ${CURRENT_TASK}" >> "${RUN_DIR}/orchestrator.log"
        write_status "$ITERATION" "$CURRENT_TASK" "STRUGGLE_STOP"
        break
      fi
      trace_event "struggle_warning" "task=${CURRENT_TASK}" "retry=${SAME_TASK_COUNT}" "threshold=${STRUGGLE_THRESHOLD}"
      echo "⚠ Retry ${SAME_TASK_COUNT}/${STRUGGLE_THRESHOLD} on task: ${CURRENT_TASK}"
    else
      SAME_TASK_COUNT=0
      LAST_TASK="$CURRENT_TASK"
    fi
  fi

  # ── Circuit breaker ─────────────────────────────────────────────────
  if ! check_circuit_breaker "$ITERATION"; then
    echo "${ITERATION} | $(date +%H:%M:%S) | HARD_CIRCUIT_BREAK | low commit ratio + consecutive reverts" >> "${RUN_DIR}/orchestrator.log"
    printf "%s\tHARD_CIRCUIT_BREAK\t-\treverts=%s\tConsecutive reverts on: %s\n" \
      "$(date +"%Y-%m-%dT%H:%M:%S")" "$CONSECUTIVE_REVERTS" "$CONSECUTIVE_REVERT_TASKS" >> "$JOURNAL_FILE"
    trace_event "circuit_break" "type_detail=hard" "reason=${CONSECUTIVE_REVERTS} consecutive reverts" "tasks=${CONSECUTIVE_REVERT_TASKS}"
    write_status "$ITERATION" "${CURRENT_TASK:-unknown}" "HARD_CIRCUIT_BREAK"
    break
  fi

  # ── Plan state snapshot ────────────────────────────────────────────
  if [ "$MODE" = "build" ] && [ -f "$PLAN_FILE" ]; then
    PLAN_TOTAL=$(grep -c '^\- \[[ x]\] \*\*Task' "$PLAN_FILE" 2>/dev/null || true); PLAN_TOTAL=${PLAN_TOTAL:-0}
    PLAN_DONE=$(grep -c '^\- \[x\] \*\*Task' "$PLAN_FILE" 2>/dev/null || true); PLAN_DONE=${PLAN_DONE:-0}
    PLAN_REMAINING=$((PLAN_TOTAL - PLAN_DONE))
    trace_event "plan_state" "iter=${ITERATION}" "total=${PLAN_TOTAL}" "done=${PLAN_DONE}" "remaining=${PLAN_REMAINING}" "task=${CURRENT_TASK:-unknown}"
  fi

  # ── Build the prompt ────────────────────────────────────────────────
  PROMPT=$(cat "$PROMPT_TEMPLATE")

  # Clean-room mode: strip codebase search step
  if [ -n "$CLEAN_ROOM_FLAG" ] && [ "$MODE" = "build" ]; then
    PROMPT=$(awk '/^## Step 3: Search Before Implementing/{skip=1; next} /^## Step 4/{skip=0} !skip' <<< "$PROMPT")
    PROMPT="${PROMPT}

**Clean-room mode:** Do NOT search the existing codebase. Implement from spec only — this is greenfield work."
  fi

  # Persistent overrides: project-local prompt tuning (survives across runs)
  if [ -f "$OVERRIDES_FILE" ]; then
    PROMPT="${PROMPT}

---
## Project Overrides (persistent — from previous runs or human tuning)

The following rules were learned from previous Ralph runs on this project, or set by the human. Follow them as if they were part of the base prompt. They take precedence over general instructions when they conflict.

$(cat "$OVERRIDES_FILE")
"
  fi

  # Mid-loop injection: append user steering if present (one-shot, consumed)
  if [ -f "$INJECT_FILE" ]; then
    echo "📋 Injecting mid-loop instructions from .claude/ralph-inject.md"
    # Audit trail: log injection before consuming
    INJECTION_LOG="${LOG_DIR}/injections.log"
    {
      echo "━━━ Injection at $(date) (iteration ${ITERATION}) ━━━"
      cat "$INJECT_FILE"
      echo ""
    } >> "$INJECTION_LOG"
    trace_event "injection" "iter=${ITERATION}" "content=$(head -3 "$INJECT_FILE" | tr '\n' ' ')"
    PROMPT="${PROMPT}

---
## Mid-Loop Steering (from user)

$(cat "$INJECT_FILE")
"
    rm -f "$INJECT_FILE"
    INJECTION_CONSUMED=1
  fi

  # Targeted spec loading: extract spec file for current task
  TASK_SPEC=""
  if [ "$MODE" = "build" ] && [ -f "$PLAN_FILE" ]; then
    TASK_SPEC=$(grep -m1 '^\- \[ \] \*\*Task' "$PLAN_FILE" 2>/dev/null | grep -o 'Spec: [^ ]*' | sed 's/Spec: //' || echo "")
  fi

  PROMPT="${PROMPT}

---
**Spec directory:** ${SPEC_DIR}
**Plan file:** ${PLAN_FILE}
**Iteration:** ${ITERATION}
$( [ -n "$TASK_SPEC" ] && echo "**Current task spec file:** ${SPEC_DIR}/${TASK_SPEC}" || true )
"

  # ── Snapshot pre-iteration state ──────────────────────────────────
  PRE_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "none")

  # ── Generate structured briefing for context ─────────────────────
  BRIEFING=""
  if [ "$MODE" = "build" ] && [ -x "${SCRIPT_DIR}/generate-briefing.sh" ]; then
    BRIEFING=$("${SCRIPT_DIR}/generate-briefing.sh" "$PLAN_FILE" "$JOURNAL_FILE" "$ITERATION" "$TRACE_FILE" 2>/dev/null || true)
  fi

  if [ -n "$BRIEFING" ]; then
    PROMPT="${PROMPT}

---
## Iteration Briefing (auto-generated)

${BRIEFING}
"
  fi

  # ── Run Claude (with optional time budget) ───────────────────────
  PROMPT_BYTES=${#PROMPT}
  trace_event "prompt_built" "iter=${ITERATION}" "prompt_bytes=${PROMPT_BYTES}" "has_overrides=$( [ -f "$OVERRIDES_FILE" ] && echo true || echo false )" "has_injection=$( [ -n "${INJECTION_CONSUMED:-}" ] && echo true || echo false )" "has_briefing=$( [ -n "$BRIEFING" ] && echo true || echo false )"
  echo "Launching Claude (${MODE} mode, budget: $( [ "$TIME_BUDGET" = "0" ] && echo "unlimited" || echo "${TIME_BUDGET}s" ), prompt: ${PROMPT_BYTES} bytes)..."
  ITER_RESULT="success"
  CLAUDE_CMD="claude -p --dangerously-skip-permissions --verbose --model sonnet --output-format stream-json"

  # Trace: iteration start
  trace_event "iteration_start" "iter=${ITERATION}" "task=${CURRENT_TASK:-plan}" "pre_commit=${PRE_COMMIT}"

  # Resolve timeout command
  TIMEOUT_CMD=""
  if [ "$TIME_BUDGET" != "0" ]; then
    if command -v timeout >/dev/null 2>&1; then
      TIMEOUT_CMD="timeout $TIME_BUDGET"
    elif command -v gtimeout >/dev/null 2>&1; then
      TIMEOUT_CMD="gtimeout $TIME_BUDGET"
    fi
  fi

  # Re-check stop sentinel immediately before launching Claude (prompt build can take time)
  if [ -f "$STOP_SENTINEL" ] || [ -f "$MAIN_STOP_SENTINEL" ]; then
    echo "Stop sentinel found before Claude invocation. Exiting gracefully."
    rm -f "$STOP_SENTINEL" "$MAIN_STOP_SENTINEL" 2>/dev/null || true
    break
  fi

  # Run Claude piped through the stream processor:
  #   claude stdout (stream-json) -> processor stdin
  #   processor stdout (text)     -> LOG_FILE
  #   processor stderr (display)  -> terminal (tmux pane)
  #   processor also appends tool_call events to TRACE_FILE
  set +e
  set -o pipefail
  if [ -n "$TIMEOUT_CMD" ]; then
    echo "$PROMPT" | $TIMEOUT_CMD $CLAUDE_CMD 2>/dev/null \
      | "$STREAM_PROCESSOR" --trace-file "$TRACE_FILE" > "$LOG_FILE"
  else
    echo "$PROMPT" | $CLAUDE_CMD 2>/dev/null \
      | "$STREAM_PROCESSOR" --trace-file "$TRACE_FILE" > "$LOG_FILE"
  fi
  PIPELINE_STATUS=("${PIPESTATUS[@]}")
  set +o pipefail
  CLAUDE_EXIT=${PIPELINE_STATUS[0]}
  PROCESSOR_EXIT=${PIPELINE_STATUS[1]:-0}
  if [ "$PROCESSOR_EXIT" -ne 0 ]; then
    echo "WARNING: Stream processor exited with code ${PROCESSOR_EXIT} — log output may be incomplete." >&2
  fi
  set -e

  if [ "$CLAUDE_EXIT" -eq 0 ]; then
    echo "Iteration ${ITERATION} completed successfully."
  elif [ "$CLAUDE_EXIT" -eq 124 ]; then
    ITER_RESULT="timeout"
    echo "Iteration ${ITERATION} timed out after ${TIME_BUDGET}s."
  else
    ITER_RESULT="error (code ${CLAUDE_EXIT})"
    echo "Iteration ${ITERATION} exited with error (code ${CLAUDE_EXIT}). Check ${LOG_FILE}"
  fi

  # ── Post-iteration gate: mechanical accept/reject ────────────────
  POST_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "none")
  TASK_LABEL="${CURRENT_TASK:-plan}"
  JOURNAL_TS=$(date +"%Y-%m-%dT%H:%M:%S")

  if [ "$PRE_COMMIT" != "$POST_COMMIT" ] && [ "$MODE" = "build" ]; then
    GATE_PASSED=true

    # Gate 1: Protected files check
    if [ -f "$READONLY_FILE" ] && [ "$GATE_PASSED" = true ]; then
      CHANGED_FILES=$(git diff --name-only "$PRE_COMMIT" HEAD)
      VIOLATED=""
      while IFS= read -r pattern; do
        # Skip empty lines and comments
        [[ -z "$pattern" || "$pattern" == \#* ]] && continue
        MATCH=$(echo "$CHANGED_FILES" | grep -E "$pattern" || true)
        if [ -n "$MATCH" ]; then
          VIOLATED="${VIOLATED}${MATCH}\n"
        fi
      done < "$READONLY_FILE"

      if [ -n "$VIOLATED" ]; then
        GATE_PASSED=false
        echo "REVERT: Modified protected files: $(echo -e "$VIOLATED" | head -5)"
        printf "%s\tREVERT_PROTECTED\t%s\t-\tModified protected: %s\n" "$JOURNAL_TS" "$TASK_LABEL" "$(echo -e "$VIOLATED" | tr '\n' ' ')" >> "$JOURNAL_FILE"
        trace_event "gate" "gate=protected_files" "passed=false" "violated=$(echo -e "$VIOLATED" | tr '\n' ' ' | head -c 200)"
      fi
    fi

    # Gate 2: Diff size check (prevent sprawling iterations)
    if [ "$GATE_PASSED" = true ]; then
      # Default max files, can be overridden via RALPH_MAX_DIFF_FILES in RALPH_OVERRIDES.md
      MAX_DIFF_FILES="${RALPH_MAX_DIFF_FILES:-20}"
      if [ -f "$OVERRIDES_FILE" ]; then
        OVERRIDE_MAX=$(grep 'RALPH_MAX_DIFF_FILES' "$OVERRIDES_FILE" 2>/dev/null | grep -o '[0-9]*' | head -1 || true)
        [ -n "$OVERRIDE_MAX" ] && MAX_DIFF_FILES="$OVERRIDE_MAX"
      fi
      DIFF_FILE_COUNT=$(git diff --name-only "$PRE_COMMIT" HEAD | wc -l | tr -d ' ')
      if [ "$DIFF_FILE_COUNT" -gt "$MAX_DIFF_FILES" ]; then
        GATE_PASSED=false
        echo "REVERT: Diff touches ${DIFF_FILE_COUNT} files (max ${MAX_DIFF_FILES}). Iteration scope too large."
        printf "%s\tREVERT_SCOPE\t%s\tfiles=%s\tDiff touched %s files (max %s)\n" \
          "$JOURNAL_TS" "$TASK_LABEL" "$DIFF_FILE_COUNT" "$DIFF_FILE_COUNT" "$MAX_DIFF_FILES" >> "$JOURNAL_FILE"
        trace_event "gate" "gate=diff_size" "passed=false" "files_changed=${DIFF_FILE_COUNT}" "max=${MAX_DIFF_FILES}"
      fi
    fi

    # Gate 3: External test + lint verification (tamper-proof)
    if [ "$GATE_PASSED" = true ]; then
      echo "Running external verification gate..."

      # Detect test/lint commands from AGENTS.md
      AGENTS_FILE="${PROJECT_DIR}/.claude/AGENTS.md"
      TEST_CMD=""
      LINT_CMD=""
      if [ -f "$AGENTS_FILE" ]; then
        TEST_CMD=$(grep -A1 '| Test' "$AGENTS_FILE" 2>/dev/null | tail -1 | sed 's/.*| `\(.*\)`.*/\1/' | sed 's/|//g' | xargs || true)
        LINT_CMD=$(grep -A1 '| Lint' "$AGENTS_FILE" 2>/dev/null | tail -1 | sed 's/.*| `\(.*\)`.*/\1/' | sed 's/|//g' | xargs || true)
      fi
      if [ -z "$TEST_CMD" ]; then
        echo "WARNING: No test command found in AGENTS.md — external test gate will be skipped." >&2
      fi
      if [ -z "$LINT_CMD" ]; then
        echo "WARNING: No lint command found in AGENTS.md — external lint gate will be skipped." >&2
      fi

      # Load gate ignore patterns from RALPH_OVERRIDES.md
      # Lines matching "RALPH_GATE_IGNORE: <regex>" define patterns that, when they
      # are the ONLY source of failure in gate output, should not trigger a revert.
      # This solves the mismatch where Claude's judgment says "ignore this warning"
      # but the mechanical gate reverts anyway on non-zero exit.
      GATE_IGNORE_PATTERNS=()
      if [ -f "$OVERRIDES_FILE" ]; then
        while IFS= read -r line; do
          pattern=$(echo "$line" | sed -n 's/.*RALPH_GATE_IGNORE: *//p' | xargs)
          [ -n "$pattern" ] && GATE_IGNORE_PATTERNS+=("$pattern")
        done < "$OVERRIDES_FILE"
      fi

      # gate_check: run a gate command, filtering known-ignorable failures.
      # Returns 0 if the command passes or all failures match ignore patterns.
      gate_check() {
        local cmd="$1" log_file="$2"
        if eval "$cmd" > "$log_file" 2>&1; then
          return 0
        fi
        # Command failed — check if ALL error lines match ignore patterns
        if [ "${#GATE_IGNORE_PATTERNS[@]}" -gt 0 ]; then
          local unmatched=0
          # Check the last 30 lines of output for non-ignorable errors
          while IFS= read -r err_line; do
            local matched=false
            for pat in "${GATE_IGNORE_PATTERNS[@]}"; do
              if echo "$err_line" | grep -qE "$pat"; then
                matched=true
                break
              fi
            done
            if [ "$matched" = false ] && [ -n "$err_line" ]; then
              # Skip blank lines and common noise (exit status lines, dividers)
              if echo "$err_line" | grep -qE '^(done|Halting|_+$|\s*$)'; then
                continue
              fi
              unmatched=$((unmatched + 1))
            fi
          done < <(tail -30 "$log_file")
          if [ "$unmatched" -eq 0 ]; then
            echo "  Gate: all failures matched RALPH_GATE_IGNORE patterns — treating as pass."
            return 0
          fi
        fi
        return 1
      }

      if [ -n "$TEST_CMD" ]; then
        echo "  Gate: running tests ($TEST_CMD)..."
        if ! gate_check "$TEST_CMD" "${LOG_DIR}/gate-test-${ITERATION}.log"; then
          GATE_PASSED=false
          FAIL_TAIL=$(tail -5 "${LOG_DIR}/gate-test-${ITERATION}.log" | tr '\n' ' ')
          echo "  GATE FAILED: Tests did not pass."
          # Capture revert reason with actionable error details
          REVERT_REASON_FILE="${LOG_DIR}/revert-${ITERATION}-reason.txt"
          {
            echo "REVERT_TESTS — Iteration ${ITERATION} — $(date)"
            echo "Task: ${TASK_LABEL}"
            echo "Command: ${TEST_CMD}"
            echo "---"
            tail -30 "${LOG_DIR}/gate-test-${ITERATION}.log"
          } > "$REVERT_REASON_FILE"
          printf "%s\tREVERT_TESTS\t%s\t-\t%s\n" "$JOURNAL_TS" "$TASK_LABEL" "$FAIL_TAIL" >> "$JOURNAL_FILE"
          trace_event "gate" "gate=tests" "passed=false" "output_tail=${FAIL_TAIL}"
        fi
      fi

      if [ "$GATE_PASSED" = true ] && [ -n "$LINT_CMD" ]; then
        echo "  Gate: running lint ($LINT_CMD)..."
        if ! gate_check "$LINT_CMD" "${LOG_DIR}/gate-lint-${ITERATION}.log"; then
          GATE_PASSED=false
          FAIL_TAIL=$(tail -5 "${LOG_DIR}/gate-lint-${ITERATION}.log" | tr '\n' ' ')
          echo "  GATE FAILED: Lint did not pass."
          # Capture revert reason with actionable error details
          REVERT_REASON_FILE="${LOG_DIR}/revert-${ITERATION}-reason.txt"
          {
            echo "REVERT_LINT — Iteration ${ITERATION} — $(date)"
            echo "Task: ${TASK_LABEL}"
            echo "Command: ${LINT_CMD}"
            echo "---"
            tail -30 "${LOG_DIR}/gate-lint-${ITERATION}.log"
          } > "$REVERT_REASON_FILE"
          printf "%s\tREVERT_LINT\t%s\t-\t%s\n" "$JOURNAL_TS" "$TASK_LABEL" "$FAIL_TAIL" >> "$JOURNAL_FILE"
          trace_event "gate" "gate=lint" "passed=false" "output_tail=${FAIL_TAIL}"
        fi
      fi
    fi

    # Verdict: keep or revert
    if [ "$GATE_PASSED" = true ]; then
      echo "KEEP: Iteration ${ITERATION} passed all mechanical gates."
      trace_event "gate" "gate=all" "passed=true"

      # ── Per-iteration evaluator (opt-in for edge-of-capability tasks) ──
      EVAL_RESULT=0
      if [ "$EVAL_PER_ITER" = "true" ] && [ -z "$ONCE_FLAG" ]; then
        run_evaluator "$PRE_COMMIT" "$POST_COMMIT" "$TASK_LABEL" "$ITERATION" || EVAL_RESULT=$?
      fi

      if [ "$EVAL_RESULT" -eq 1 ]; then
        # REVISE verdict — revert and feed guidance to next iteration
        echo "REVERT (evaluator): Evaluation says REVISE. Rolling back to ${PRE_COMMIT:0:8}..."
        # Save evaluation guidance for next iteration's briefing
        REVERT_REASON_FILE="${LOG_DIR}/revert-${ITERATION}-reason.txt"
        {
          echo "REVERT_EVALUATION — Iteration ${ITERATION} — $(date)"
          echo "Task: ${TASK_LABEL}"
          echo "Evaluator verdict: REVISE"
          echo "---"
          if [ -f "$EVAL_SUMMARY_FILE" ]; then
            head -40 "$EVAL_SUMMARY_FILE"
          elif [ -f "$EVAL_VERDICT_FILE" ]; then
            cat "$EVAL_VERDICT_FILE"
          fi
        } > "$REVERT_REASON_FILE"
        git reset --hard "$PRE_COMMIT"
        ITER_RESULT="reverted (evaluator)"
        printf "%s\tREVERT_EVAL\t%s\t-\tEvaluator said REVISE\n" "$JOURNAL_TS" "$TASK_LABEL" >> "$JOURNAL_FILE"
        trace_event "verdict" "outcome=REVERT_EVAL" "task=${TASK_LABEL}" "iter=${ITERATION}"
        track_revert "$TASK_LABEL"
      else
        # ACCEPT or skipped — keep the commit
        COMMITS_ADDED=$(git rev-list --count "$PRE_COMMIT"..HEAD)
        printf "%s\tKEEP\t%s\tcommits=%s\t%s\n" "$JOURNAL_TS" "$TASK_LABEL" "$COMMITS_ADDED" "$POST_COMMIT" >> "$JOURNAL_FILE"
        # Capture commit details for the trace
        COMMIT_MSG=$(git log --format="%s" -1 2>/dev/null || echo "")
        DIFF_STAT=$(git diff --shortstat "$PRE_COMMIT"..HEAD 2>/dev/null || echo "")
        FILES_CHANGED=$(git diff --name-only "$PRE_COMMIT"..HEAD 2>/dev/null | tr '\n' ',' | sed 's/,$//' || echo "")
        trace_event "verdict" "outcome=KEEP" "task=${TASK_LABEL}" "iter=${ITERATION}" "commit=${POST_COMMIT}" "commit_msg=${COMMIT_MSG}" "diff_stat=${DIFF_STAT}" "files_changed=${FILES_CHANGED}"
        track_success
      fi
    else
      echo "REVERT: Rolling back to ${PRE_COMMIT:0:8}..."
      if [ -z "$PRE_COMMIT" ] || [ "$PRE_COMMIT" = "none" ]; then
        echo "ERROR: Cannot revert — PRE_COMMIT is unset or invalid (${PRE_COMMIT}). Manual intervention required." >&2
        trace_event "verdict" "outcome=REVERT_FAILED" "reason=invalid_pre_commit" "task=${TASK_LABEL}" "iter=${ITERATION}"
      elif ! git reset --hard "$PRE_COMMIT" 2>&1; then
        echo "ERROR: git reset --hard failed — branch may be in an inconsistent state. Manual intervention required." >&2
        trace_event "verdict" "outcome=REVERT_FAILED" "reason=reset_failed" "task=${TASK_LABEL}" "iter=${ITERATION}"
        exit 1
      fi
      ITER_RESULT="reverted"
      trace_event "verdict" "outcome=REVERT" "task=${TASK_LABEL}" "iter=${ITERATION}"
      track_revert "$TASK_LABEL"
      # Re-mark task as incomplete if plan was updated during the iteration
      # (The reset already handles this since plan changes are reverted too)
    fi

  elif [ "$ITER_RESULT" = "timeout" ]; then
    # Timeout — revert any partial work
    POST_COMMIT_AFTER_TIMEOUT=$(git rev-parse HEAD 2>/dev/null || echo "none")
    if [ "$PRE_COMMIT" != "$POST_COMMIT_AFTER_TIMEOUT" ]; then
      echo "REVERT: Timed out with uncommitted state, rolling back..."
      git reset --hard "$PRE_COMMIT"
    fi
    printf "%s\tTIMEOUT\t%s\t%ss\tKilled after time budget exceeded\n" "$JOURNAL_TS" "$TASK_LABEL" "$TIME_BUDGET" >> "$JOURNAL_FILE"
    trace_event "verdict" "outcome=TIMEOUT" "task=${TASK_LABEL}" "iter=${ITERATION}" "budget=${TIME_BUDGET}"
    ITER_RESULT="timeout"

  elif [ "$PRE_COMMIT" = "$POST_COMMIT" ]; then
    # No commit produced — log as no-op
    printf "%s\tNO_COMMIT\t%s\t-\t%s\n" "$JOURNAL_TS" "$TASK_LABEL" "$ITER_RESULT" >> "$JOURNAL_FILE"
    trace_event "verdict" "outcome=NO_COMMIT" "task=${TASK_LABEL}" "iter=${ITERATION}"
  fi

  # Log iteration (legacy + trace)
  echo "${ITERATION} | $(date +%H:%M:%S) | ${ITER_RESULT} | ${CURRENT_TASK:-plan}" >> "${RUN_DIR}/orchestrator.log"
  ITER_DURATION=$(( $(date +%s) - ITER_START_TIME ))
  trace_event "iteration_end" "iter=${ITERATION}" "outcome=${ITER_RESULT}" "commit=${POST_COMMIT:-none}" "duration_s=${ITER_DURATION}"

  # Update status dashboard
  write_status "$ITERATION" "${CURRENT_TASK:-plan}" "$ITER_RESULT"

  # ── Update progress scratchpad ────────────────────────────────────
  # Mechanical append after each iteration so harvest and future iterations
  # can see session-level decisions and outcomes. Claude also writes to this
  # file from Step 7b of the build prompt (richer, but may be reverted).
  {
    echo "### Iteration ${ITERATION} — $(date +%H:%M:%S) — ${ITER_RESULT}"
    echo "- **Task:** ${CURRENT_TASK:-plan}"
    echo "- **Pre-commit:** ${PRE_COMMIT:0:8}"
    echo "- **Post-commit:** ${POST_COMMIT:0:8}"
    if [ "$ITER_RESULT" = "reverted" ] || [[ "$ITER_RESULT" == *"reverted"* ]]; then
      REVERT_FILE="${LOG_DIR}/revert-${ITERATION}-reason.txt"
      if [ -f "$REVERT_FILE" ]; then
        echo "- **Revert reason:** $(head -1 "$REVERT_FILE")"
      fi
    fi
    echo ""
  } >> "$PROGRESS_FILE"

  # --once mode: exit after single iteration
  if [ -n "$ONCE_FLAG" ]; then
    echo ""
    echo "━━━ Single iteration complete (--once mode) ━━━"
    break
  fi

  echo ""
done

# ── Write worker completion marker ─────────────────────────────────────

WORKER_ID="${RALPH_WORKER_ID:-}"
if [ -n "$WORKER_ID" ]; then
  MARKER_FILE="${PROJECT_DIR}/.claude/ralph-worker-done-${WORKER_ID}"
  echo "{\"worker\": \"${WORKER_ID}\", \"status\": \"done\", \"iterations\": ${ITERATION}, \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" \
    > "$MARKER_FILE"
  echo "Worker completion marker written: ${MARKER_FILE}"
fi

# ── Trace: run end ──────────────────────────────────────────────────────
TOTAL_DURATION_M=$(( ($(date +%s) - START_TIME) / 60 ))
KEPT_COUNT=$(grep -c '"outcome":"KEEP"' "$TRACE_FILE" 2>/dev/null || echo 0)
REVERTED_COUNT=$(grep -c '"outcome":"REVERT' "$TRACE_FILE" 2>/dev/null || echo 0)
trace_event "run_end" "total_iters=${ITERATION}" "kept=${KEPT_COUNT}" "reverted=${REVERTED_COUNT}" "duration_m=${TOTAL_DURATION_M}"

echo ""
echo "━━━ Ralph loop finished after ${ITERATION} iterations ━━━"
echo "Run:   ${RUN_DIR}/"
echo "Trace: ${TRACE_FILE}"
echo "Journal: ${JOURNAL_FILE}"
echo "View:  trace-viewer.py ${TRACE_FILE} [--view timeline|summary|tools|reverts]"

# Show final plan status
if [ -f "$PLAN_FILE" ]; then
  echo ""
  echo "Plan status:"
  grep -E "^## Status:|^\- \[[ x]\]" "$PLAN_FILE" | head -20
fi

# ── Worktree cleanup (single-track mode) ───────────────────────────────
if [ "$USING_WORKTREE" = true ]; then
  echo ""

  # Copy run artifacts back to main project before potential cleanup
  MAIN_RUN_DIR="${MAIN_PROJECT_DIR}/.claude/ralph/${SLUG}/runs/${RUN_TIMESTAMP}"
  mkdir -p "$MAIN_RUN_DIR"
  cp "$TRACE_FILE" "$MAIN_RUN_DIR/" 2>/dev/null || true
  [ -f "${RUN_DIR}/eval-verdict.json" ] && cp "${RUN_DIR}/eval-verdict.json" "$MAIN_RUN_DIR/" 2>/dev/null || true
  [ -f "${RUN_DIR}/eval-summary.md" ] && cp "${RUN_DIR}/eval-summary.md" "$MAIN_RUN_DIR/" 2>/dev/null || true
  [ -f "${RUN_DIR}/orchestrator.log" ] && cp "${RUN_DIR}/orchestrator.log" "$MAIN_RUN_DIR/" 2>/dev/null || true
  # Append worktree journal to main persistent journal
  MAIN_JOURNAL="${MAIN_PROJECT_DIR}/.claude/ralph/${SLUG}/journal.tsv"
  mkdir -p "$(dirname "$MAIN_JOURNAL")"
  if [ -f "$JOURNAL_FILE" ]; then
    if [ ! -f "$MAIN_JOURNAL" ]; then
      cp "$JOURNAL_FILE" "$MAIN_JOURNAL"
    else
      tail -n +2 "$JOURNAL_FILE" >> "$MAIN_JOURNAL"  # skip header, append data
    fi
  fi

  BRANCH_COMMITS=$(git rev-list --count "${TARGET_BRANCH}..HEAD" 2>/dev/null || echo "0")

  if [ "$BRANCH_COMMITS" -gt 0 ]; then
    echo "Branch '${WORKTREE_BRANCH}' has ${BRANCH_COMMITS} commits ahead of ${TARGET_BRANCH}."
    echo ""
    echo "  To merge:   cd ${MAIN_PROJECT_DIR} && git merge ${WORKTREE_BRANCH}"
    echo "  To review:  git log --oneline ${TARGET_BRANCH}..${WORKTREE_BRANCH}"
    echo "  To discard: git worktree remove --force ${WORKTREE_PATH} && git branch -D ${WORKTREE_BRANCH}"
    echo ""

    # Prompt for merge if running interactively (not a worker)
    if [ -t 0 ] && [ -z "${RALPH_NO_MERGE_PROMPT:-}" ]; then
      read -p "Merge '${WORKTREE_BRANCH}' into ${TARGET_BRANCH} now? [y/N] " -n 1 -r REPLY
      echo ""
      if [[ "$REPLY" =~ ^[Yy]$ ]]; then
        cd "$MAIN_PROJECT_DIR"
        if git merge "$WORKTREE_BRANCH"; then
          echo "Merged successfully. Cleaning up worktree..."
          git worktree remove --force "$WORKTREE_PATH" 2>/dev/null || rm -rf "$WORKTREE_PATH"
          git branch -D "$WORKTREE_BRANCH" 2>/dev/null || true
          git worktree prune 2>/dev/null || true
          echo "Worktree and branch cleaned up."
        else
          echo "Merge failed (conflicts?). Worktree preserved for manual resolution."
          echo "  Resolve, then: git worktree remove --force ${WORKTREE_PATH}"
        fi
      else
        echo "Worktree preserved at: ${WORKTREE_PATH}"
        echo "Branch preserved: ${WORKTREE_BRANCH}"
      fi
    else
      echo "Non-interactive mode — worktree preserved."
      echo "Merge manually or use /agentic-coding-workflow:reunify"
    fi
  else
    echo "No new commits on worktree branch. Cleaning up..."
    cd "$MAIN_PROJECT_DIR"
    git worktree remove --force "$WORKTREE_PATH" 2>/dev/null || rm -rf "$WORKTREE_PATH"
    git branch -D "$WORKTREE_BRANCH" 2>/dev/null || true
    git worktree prune 2>/dev/null || true
    echo "Worktree and branch cleaned up (no changes to keep)."
  fi
fi

# ── End-of-run evaluator pass ──────────────────────────────────────────
# Single evaluator pass reviewing the FULL body of work, not per-iteration.
# This is the default evaluation mode (per Anthropic harness design findings:
# "moved the evaluator to a single pass at the end of the run").
# The evaluator grades the entire diff from start-of-run to HEAD.

if [ "$EVAL_END_OF_RUN" = "true" ] && [ "$MODE" = "build" ] && [ -z "$ONCE_FLAG" ] && [ -z "$WORKER_ID" ]; then
  FINAL_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "none")
  if [ "$COMMITS_AT_START_HASH" != "$FINAL_COMMIT" ] && [ "$FINAL_COMMIT" != "none" ]; then
    echo ""
    echo "━━━ End-of-run evaluation (reviewing full body of work) ━━━"

    # Build end-of-run evaluator prompt with full-run context
    ENDRUN_EVAL_PROMPT=$(cat "${PROMPT_DIR}/PROMPT_evaluate.md")
    ENDRUN_EVAL_PROMPT="${ENDRUN_EVAL_PROMPT}

---
**Evaluation mode:** END-OF-RUN (reviewing all changes from this Ralph run, not a single iteration)
**Pre-commit (run start):** ${COMMITS_AT_START_HASH}
**Post-commit (run end):** ${FINAL_COMMIT}
**Total iterations:** ${ITERATION}
**Kept iterations:** ${KEPT_COUNT}
**Reverted iterations:** ${REVERTED_COUNT}
**Spec directory:** ${SPEC_DIR}
**UI evaluation:** ${RALPH_EVALUATE_UI}
**Verdict output:** ${EVAL_VERDICT_FILE}
**Summary output:** ${EVAL_SUMMARY_FILE}

**Important:** You are reviewing the ENTIRE run's output, not a single task. Grade the overall implementation against the full spec and plan acceptance criteria. Your verdict does NOT trigger a revert — it produces a quality report for the human to review before merging.
"

    rm -f "$EVAL_VERDICT_FILE" "$EVAL_SUMMARY_FILE"
    ENDRUN_EVAL_LOG="${LOG_DIR}/eval-endofrun-$(date +%Y%m%d-%H%M%S).log"
    ENDRUN_EVAL_TIMEOUT="${RALPH_EVAL_TIMEOUT:-600}"  # 10 min for end-of-run (more to review)

    ENDRUN_TIMEOUT_CMD=""
    if command -v timeout >/dev/null 2>&1; then
      ENDRUN_TIMEOUT_CMD="timeout $ENDRUN_EVAL_TIMEOUT"
    elif command -v gtimeout >/dev/null 2>&1; then
      ENDRUN_TIMEOUT_CMD="gtimeout $ENDRUN_EVAL_TIMEOUT"
    fi

    set +e
    if [ -n "$ENDRUN_TIMEOUT_CMD" ]; then
      echo "$ENDRUN_EVAL_PROMPT" | $ENDRUN_TIMEOUT_CMD claude -p --dangerously-skip-permissions --verbose --model sonnet --output-format stream-json 2>/dev/null \
        | "$STREAM_PROCESSOR" --trace-file "$TRACE_FILE" > "$ENDRUN_EVAL_LOG"
    else
      echo "$ENDRUN_EVAL_PROMPT" | claude -p --dangerously-skip-permissions --verbose --model sonnet --output-format stream-json 2>/dev/null \
        | "$STREAM_PROCESSOR" --trace-file "$TRACE_FILE" > "$ENDRUN_EVAL_LOG"
    fi
    set -e

    if [ -f "$EVAL_VERDICT_FILE" ]; then
      ENDRUN_VERDICT=$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d['verdict'])" "$EVAL_VERDICT_FILE" 2>/dev/null || echo "UNKNOWN")
      ENDRUN_AVG=$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d['average'])" "$EVAL_VERDICT_FILE" 2>/dev/null || echo "?")
      if [ "$ENDRUN_VERDICT" = "UNKNOWN" ] || [ "$ENDRUN_AVG" = "?" ]; then
        echo "WARNING: Eval verdict file exists but could not be parsed — check ${EVAL_VERDICT_FILE}" >&2
      fi
      echo "End-of-run evaluation: ${ENDRUN_VERDICT} (avg score: ${ENDRUN_AVG})"
      echo "Full report: ${EVAL_SUMMARY_FILE}"
      trace_event "endrun_eval" "verdict=${ENDRUN_VERDICT}" "avg_score=${ENDRUN_AVG}"
    else
      echo "End-of-run evaluation did not produce a verdict (non-fatal)."
      trace_event "endrun_eval" "verdict=error" "reason=no_verdict_file"
    fi
  else
    echo "(No new commits in this run — skipping end-of-run evaluation)"
  fi
fi

# ── Auto-harvest on completion ──────────────────────────────────────────
# Run harvest automatically when plan is complete or circuit breaker fired.
# Disable with AUTO_HARVEST=false environment variable.

AUTO_HARVEST="${AUTO_HARVEST:-true}"
if [ "$AUTO_HARVEST" = "true" ] && [ "$MODE" = "build" ] && [ -z "$ONCE_FLAG" ] && [ -z "$WORKER_ID" ]; then
  SHOULD_HARVEST=false
  if [ -f "$PLAN_FILE" ] && grep -q "## Status: COMPLETE" "$PLAN_FILE"; then
    SHOULD_HARVEST=true
    echo ""
    echo "━━━ Auto-harvesting (plan complete) ━━━"
  elif [ "$CONSECUTIVE_REVERTS" -ge 3 ] || grep -q 'CIRCUIT_BREAK\|STRUGGLE_STOP' "${RUN_DIR}/orchestrator.log" 2>/dev/null; then
    SHOULD_HARVEST=true
    echo ""
    echo "━━━ Auto-harvesting (loop stopped early — capturing failure patterns) ━━━"
  fi

  if [ "$SHOULD_HARVEST" = true ]; then
    "$0" "$SPEC_DIR" harvest 1 || echo "Warning: auto-harvest failed (non-fatal)"
    echo "Harvest complete. Check .claude/ralph-logs/ralph-harvest-*.md and specs/<slug>/RALPH_OVERRIDES.md"
  fi
fi

# ── Generate completion summary ─────────────────────────────────────────

if [ "$MODE" = "build" ] && [ -z "$ONCE_FLAG" ] && [ -z "$WORKER_ID" ]; then
  if [ -x "${SCRIPT_DIR}/generate-summary.sh" ]; then
    "${SCRIPT_DIR}/generate-summary.sh" "$SPEC_DIR" "$JOURNAL_FILE" "$ITERATION" "$COMMITS_AT_START" "$START_TIME" "$TRACE_FILE" 2>/dev/null || true
  fi
fi

# Clean up ephemeral progress file
if [ -f "$PROGRESS_FILE" ]; then
  rm -f "$PROGRESS_FILE"
  echo "(Cleaned up ephemeral progress scratchpad)"
fi
