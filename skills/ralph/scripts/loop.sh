#!/usr/bin/env bash
# Ralph loop — drives autonomous Claude iterations
# Each iteration: pick task → implement → test → commit → update plan → exit
#
# Usage: loop.sh <spec-dir> [mode] [max-iterations] [flags...]
#   spec-dir:       Path to the spec directory containing IMPLEMENTATION_PLAN.md
#   mode:           "build" (default), "plan", or "harvest"
#   max-iterations: Maximum iterations before stopping (default: 50)
#   --push:         Push to remote after each commit
#   --once:         Run a single iteration then stop (HITL mode)
#   --clean-room:   Skip codebase search (greenfield mode)
#   --pr:           Create/update a draft PR after first commit
#   --time-budget:  Max seconds per iteration (default: 600, 0 = no limit)

set -euo pipefail

SPEC_DIR="${1:?Usage: loop.sh <spec-dir> [mode] [max-iterations] [flags...]}"
MODE="${2:-build}"
MAX_ITERATIONS="${3:-50}"
PUSH_FLAG=""
ONCE_FLAG=""
CLEAN_ROOM_FLAG=""
PR_FLAG=""
TIME_BUDGET="600"  # 10 minutes default, 0 = no limit

# Check for flags in any position
for arg in "$@"; do
  case "$arg" in
    --push)       PUSH_FLAG="1" ;;
    --once)       ONCE_FLAG="1" ;;
    --clean-room) CLEAN_ROOM_FLAG="1" ;;
    --pr)         PR_FLAG="1" ;;
    --time-budget=*) TIME_BUDGET="${arg#--time-budget=}" ;;
  esac
done

PLAN_FILE="${SPEC_DIR}/IMPLEMENTATION_PLAN.md"
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
LOG_DIR="${PROJECT_DIR}/.claude/ralph-logs"
STOP_SENTINEL="${PROJECT_DIR}/.claude/ralph-stop"
STATUS_FILE="${PROJECT_DIR}/.claude/ralph-status.md"
INJECT_FILE="${PROJECT_DIR}/.claude/ralph-inject.md"
PROGRESS_FILE="${PROJECT_DIR}/.claude/ralph-progress.md"
JOURNAL_FILE="${PROJECT_DIR}/.claude/ralph-journal.tsv"
READONLY_FILE="${SPEC_DIR}/RALPH_READONLY"
OVERRIDES_FILE="${SPEC_DIR}/RALPH_OVERRIDES.md"
SCRIPT_DIR="$(dirname "$(realpath "$0")")"
PROMPT_DIR="${SCRIPT_DIR}/../references"

mkdir -p "$LOG_DIR"

# ── Initialize failure journal ────────────────────────────────────────
if [ ! -f "$JOURNAL_FILE" ]; then
  printf "timestamp\toutcome\ttask\tmetric\tnotes\n" > "$JOURNAL_FILE"
fi

# ── Resolve prompt template ─────────────────────────────────────────────

case "$MODE" in
  plan)      PROMPT_TEMPLATE="${PROMPT_DIR}/PROMPT_plan.md" ;;
  build)     PROMPT_TEMPLATE="${PROMPT_DIR}/PROMPT_build.md" ;;
  harvest)   PROMPT_TEMPLATE="${PROMPT_DIR}/PROMPT_harvest.md" ;;
  reconcile) PROMPT_TEMPLATE="${PROMPT_DIR}/PROMPT_reconcile.md" ;;
  *)         echo "Error: mode must be 'plan', 'build', 'harvest', or 'reconcile'"; exit 1 ;;
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
echo "║  Push:       ${PUSH_FLAG:-no}                       "
echo "║  Once:       ${ONCE_FLAG:-no}                       "
echo "║  Clean-room: ${CLEAN_ROOM_FLAG:-no}                 "
echo "║  PR:         ${PR_FLAG:-no}                         "
echo "║  Protected:  $( [ -f "$READONLY_FILE" ] && echo "yes ($(wc -l < "$READONLY_FILE") patterns)" || echo "no" )"
echo "║  Overrides:  $( [ -f "$OVERRIDES_FILE" ] && echo "yes ($(wc -l < "$OVERRIDES_FILE") lines)" || echo "no" )"
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
    fi
  done < <(grep '^\- \[x\]' "$PLAN_FILE" 2>/dev/null || true)
  rm -f "${PLAN_FILE}.bak"

  if [ "$INTEGRITY_FIXES" -gt 0 ]; then
    echo "  Fixed ${INTEGRITY_FIXES} orphaned task(s). Plan integrity restored."
    echo ""
  fi
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

# ── Progress dashboard writer ───────────────────────────────────────────

write_status() {
  local iteration=$1
  local task_name=$2
  local result=$3

  local total_tasks=0 done_tasks=0
  if [ -f "$PLAN_FILE" ]; then
    total_tasks=$(grep -c '^\- \[[ x]\] \*\*Task' "$PLAN_FILE" 2>/dev/null || echo "0")
    done_tasks=$(grep -c '^\- \[x\] \*\*Task' "$PLAN_FILE" 2>/dev/null || echo "0")
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

$(tail -20 "${LOG_DIR}/ralph-iterations.log" 2>/dev/null || echo "(no iteration log yet)")
EOF
}

# ── Main loop ───────────────────────────────────────────────────────────

ITERATION=0
START_TIME=$(date +%s)

# Append to iteration log (preserve history across restarts)
echo "" >> "${LOG_DIR}/ralph-iterations.log" 2>/dev/null || true
echo "# Ralph Run — $(date)" >> "${LOG_DIR}/ralph-iterations.log"

while :; do
  ITERATION=$((ITERATION + 1))
  TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
  LOG_FILE="${LOG_DIR}/iter-${ITERATION}-${TIMESTAMP}.log"

  echo "━━━ Iteration ${ITERATION}/${MAX_ITERATIONS} ━━━ $(date) ━━━"

  # Check stop sentinel
  if [ -f "$STOP_SENTINEL" ]; then
    echo "Stop sentinel found. Exiting gracefully."
    rm -f "$STOP_SENTINEL"
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
        echo "${ITERATION} | $(date +%H:%M:%S) | STRUGGLE_STOP | ${CURRENT_TASK}" >> "${LOG_DIR}/ralph-iterations.log"
        write_status "$ITERATION" "$CURRENT_TASK" "STRUGGLE_STOP"
        break
      fi
      echo "⚠ Retry ${SAME_TASK_COUNT}/${STRUGGLE_THRESHOLD} on task: ${CURRENT_TASK}"
    else
      SAME_TASK_COUNT=0
      LAST_TASK="$CURRENT_TASK"
    fi
  fi

  # ── Circuit breaker ─────────────────────────────────────────────────
  if ! check_circuit_breaker "$ITERATION"; then
    echo "${ITERATION} | $(date +%H:%M:%S) | HARD_CIRCUIT_BREAK | low commit ratio + consecutive reverts" >> "${LOG_DIR}/ralph-iterations.log"
    printf "%s\tHARD_CIRCUIT_BREAK\t-\treverts=%s\tConsecutive reverts on: %s\n" \
      "$(date +"%Y-%m-%dT%H:%M:%S")" "$CONSECUTIVE_REVERTS" "$CONSECUTIVE_REVERT_TASKS" >> "$JOURNAL_FILE"
    write_status "$ITERATION" "${CURRENT_TASK:-unknown}" "HARD_CIRCUIT_BREAK"
    break
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
    PROMPT="${PROMPT}

---
## Mid-Loop Steering (from user)

$(cat "$INJECT_FILE")
"
    rm -f "$INJECT_FILE"
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
    BRIEFING=$("${SCRIPT_DIR}/generate-briefing.sh" "$PLAN_FILE" "$JOURNAL_FILE" "$ITERATION" 2>/dev/null || true)
  fi

  if [ -n "$BRIEFING" ]; then
    PROMPT="${PROMPT}

---
## Iteration Briefing (auto-generated)

${BRIEFING}
"
  fi

  # ── Run Claude (with optional time budget) ───────────────────────
  echo "Launching Claude (${MODE} mode, budget: $( [ "$TIME_BUDGET" = "0" ] && echo "unlimited" || echo "${TIME_BUDGET}s" ))..."
  ITER_RESULT="success"
  CLAUDE_CMD="claude -p --dangerously-skip-permissions --model sonnet"

  if [ "$TIME_BUDGET" != "0" ] && command -v timeout >/dev/null 2>&1; then
    # Use timeout (coreutils) — available on Linux, brew install coreutils on macOS
    if echo "$PROMPT" | timeout "$TIME_BUDGET" $CLAUDE_CMD > "$LOG_FILE" 2>&1; then
      echo "Iteration ${ITERATION} completed successfully."
    else
      EXIT_CODE=$?
      if [ "$EXIT_CODE" -eq 124 ]; then
        ITER_RESULT="timeout"
        echo "Iteration ${ITERATION} timed out after ${TIME_BUDGET}s."
      else
        ITER_RESULT="error (code ${EXIT_CODE})"
        echo "Iteration ${ITERATION} exited with error (code ${EXIT_CODE}). Check ${LOG_FILE}"
      fi
    fi
  elif [ "$TIME_BUDGET" != "0" ] && command -v gtimeout >/dev/null 2>&1; then
    # macOS with coreutils installed via brew
    if echo "$PROMPT" | gtimeout "$TIME_BUDGET" $CLAUDE_CMD > "$LOG_FILE" 2>&1; then
      echo "Iteration ${ITERATION} completed successfully."
    else
      EXIT_CODE=$?
      if [ "$EXIT_CODE" -eq 124 ]; then
        ITER_RESULT="timeout"
        echo "Iteration ${ITERATION} timed out after ${TIME_BUDGET}s."
      else
        ITER_RESULT="error (code ${EXIT_CODE})"
        echo "Iteration ${ITERATION} exited with error (code ${EXIT_CODE}). Check ${LOG_FILE}"
      fi
    fi
  else
    # No timeout available or budget=0 — run unbounded
    if echo "$PROMPT" | $CLAUDE_CMD > "$LOG_FILE" 2>&1; then
      echo "Iteration ${ITERATION} completed successfully."
    else
      ITER_RESULT="error (code $?)"
      echo "Iteration ${ITERATION} exited with error (code $?). Check ${LOG_FILE}"
    fi
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
        fi
      fi
    fi

    # Verdict: keep or revert
    if [ "$GATE_PASSED" = true ]; then
      echo "KEEP: Iteration ${ITERATION} passed all gates."
      COMMITS_ADDED=$(git rev-list --count "$PRE_COMMIT"..HEAD)
      printf "%s\tKEEP\t%s\tcommits=%s\t%s\n" "$JOURNAL_TS" "$TASK_LABEL" "$COMMITS_ADDED" "$POST_COMMIT" >> "$JOURNAL_FILE"
      track_success
    else
      echo "REVERT: Rolling back to ${PRE_COMMIT:0:8}..."
      git reset --hard "$PRE_COMMIT"
      ITER_RESULT="reverted"
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
    ITER_RESULT="timeout"

  elif [ "$PRE_COMMIT" = "$POST_COMMIT" ]; then
    # No commit produced — log as no-op
    printf "%s\tNO_COMMIT\t%s\t-\t%s\n" "$JOURNAL_TS" "$TASK_LABEL" "$ITER_RESULT" >> "$JOURNAL_FILE"
  fi

  # Log iteration
  echo "${ITERATION} | $(date +%H:%M:%S) | ${ITER_RESULT} | ${CURRENT_TASK:-plan}" >> "${LOG_DIR}/ralph-iterations.log"

  # Update status dashboard
  write_status "$ITERATION" "${CURRENT_TASK:-plan}" "$ITER_RESULT"

  # Push if requested (only on successful iterations)
  if [ -n "$PUSH_FLAG" ] && [ "$ITER_RESULT" = "success" ]; then
    git push 2>/dev/null || echo "Push failed (non-fatal)"
  fi

  # Auto-create/update draft PR if --pr flag
  if [ -n "$PR_FLAG" ] && [ -n "$PUSH_FLAG" ]; then
    if [ "$ITERATION" -eq 1 ]; then
      # Create draft PR on first iteration
      BRANCH=$(git branch --show-current)
      if [ "$BRANCH" != "main" ] && [ "$BRANCH" != "master" ]; then
        echo "Creating draft PR..."
        gh pr create --draft --title "Ralph: $(basename "$SPEC_DIR")" \
          --body "Autonomous implementation via Ralph loop.

Spec: \`${SPEC_DIR}\`
Mode: ${MODE}

_This PR is updated automatically by the Ralph loop._" 2>/dev/null || echo "PR creation failed (may already exist)"
      fi
    fi
  fi

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

echo ""
echo "━━━ Ralph loop finished after ${ITERATION} iterations ━━━"
echo "Logs: ${LOG_DIR}/"
echo "Status: ${STATUS_FILE}"

# Show final plan status
if [ -f "$PLAN_FILE" ]; then
  echo ""
  echo "Plan status:"
  grep -E "^## Status:|^\- \[[ x]\]" "$PLAN_FILE" | head -20
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
  elif [ "$CONSECUTIVE_REVERTS" -ge 3 ] || grep -q 'CIRCUIT_BREAK\|STRUGGLE_STOP' "${LOG_DIR}/ralph-iterations.log" 2>/dev/null; then
    SHOULD_HARVEST=true
    echo ""
    echo "━━━ Auto-harvesting (loop stopped early — capturing failure patterns) ━━━"
  fi

  if [ "$SHOULD_HARVEST" = true ]; then
    "$0" "$SPEC_DIR" harvest 1 || echo "Warning: auto-harvest failed (non-fatal)"
    echo "Harvest complete. Check .claude/ralph-harvest-*.md and RALPH_OVERRIDES.md"
  fi
fi

# ── Generate completion summary ─────────────────────────────────────────

if [ "$MODE" = "build" ] && [ -z "$ONCE_FLAG" ] && [ -z "$WORKER_ID" ]; then
  if [ -x "${SCRIPT_DIR}/generate-summary.sh" ]; then
    "${SCRIPT_DIR}/generate-summary.sh" "$SPEC_DIR" "$JOURNAL_FILE" "$ITERATION" "$COMMITS_AT_START" "$START_TIME" 2>/dev/null || true
  fi
fi

# Clean up ephemeral progress file
if [ -f "$PROGRESS_FILE" ]; then
  rm -f "$PROGRESS_FILE"
  echo "(Cleaned up ephemeral progress scratchpad)"
fi
