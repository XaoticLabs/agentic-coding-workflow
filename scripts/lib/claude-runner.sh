#!/usr/bin/env bash
# Model propagation and recorded pipelines used by shell workflow launchers.

[[ -n "${_CLAUDE_RUNNER_LOADED:-}" ]] && return 0
_CLAUDE_RUNNER_LOADED=1
_WORKFLOW_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Omit --model when native configuration owns selection. Arrays preserve IDs.
workflow_model_args() {
  local selected
  selected=$(python3 "${_WORKFLOW_ROOT}/scripts/workflow_models.py" "$1") || return
  WORKFLOW_MODEL_ARGS=()
  [ -z "$selected" ] || WORKFLOW_MODEL_ARGS=(--model "$selected")
}

# tmux servers do not reliably inherit the launching shell's environment.
write_workflow_model_environment() {
  local key
  for key in WORKFLOW_MODEL WORKFLOW_BUILD_MODEL WORKFLOW_EVALUATOR_MODEL WORKFLOW_MERGE_MODEL ANTHROPIC_MODEL; do
    if [[ -v "$key" ]]; then
      printf 'export %s=%q\n' "$key" "${!key}"
    else
      printf 'unset %s\n' "$key"
    fi
  done
}

# The argv form is used when a tmux boundary has no generated launcher file.
workflow_model_environment_args() {
  local key
  WORKFLOW_ENV_ARGS=(env)
  for key in WORKFLOW_MODEL WORKFLOW_BUILD_MODEL WORKFLOW_EVALUATOR_MODEL WORKFLOW_MERGE_MODEL ANTHROPIC_MODEL; do
    [[ -v "$key" ]] || WORKFLOW_ENV_ARGS+=(-u "$key")
  done
  for key in WORKFLOW_MODEL WORKFLOW_BUILD_MODEL WORKFLOW_EVALUATOR_MODEL WORKFLOW_MERGE_MODEL ANTHROPIC_MODEL; do
    [[ ! -v "$key" ]] || WORKFLOW_ENV_ARGS+=("$key=${!key}")
  done
}

candidate_state() {
  (cd "$1" && python3 "${_WORKFLOW_ROOT}/hooks/verification-state.py" snapshot)
}

# Args: <prompt> <log> <trace> <timeout-seconds> <processor> <claude-args...>
# Always records all stages. Call in a conditional; no caller shell options change.
run_claude_pipeline() {
  local prompt="$1" log="$2" trace="$3" budget="$4" processor="$5"
  shift 5
  local -a invocation=(claude "$@") statuses
  if [ "$budget" != 0 ]; then
    if command -v timeout >/dev/null 2>&1; then
      invocation=(timeout --kill-after=5 "$budget" "${invocation[@]}")
    elif command -v gtimeout >/dev/null 2>&1; then
      invocation=(gtimeout --kill-after=5 "$budget" "${invocation[@]}")
    else
      invocation=(bash -c 'echo "A timeout utility is required for a bounded Claude invocation." >&2; exit 127')
    fi
  fi
  if printf '%s\n' "$prompt" 2>"${log}.prompt-stderr.log" |
    "${invocation[@]}" 2>"${log}.claude-stderr.log" |
    "$processor" --trace-file "$trace" >"$log" 2> >(tee "${log}.processor-stderr.log" >&2); then
    statuses=("${PIPESTATUS[@]}")
  else
    statuses=("${PIPESTATUS[@]}")
  fi
  PROMPT_EXIT=${statuses[0]} CLAUDE_EXIT=${statuses[1]} PROCESSOR_EXIT=${statuses[2]}
  PIPELINE_RESULT=success
  if [ "$budget" != 0 ] && { [ "$CLAUDE_EXIT" -eq 124 ] || [ "$CLAUDE_EXIT" -eq 137 ]; }; then
    PIPELINE_RESULT=timeout
  elif [ "$CLAUDE_EXIT" -ne 0 ]; then
    PIPELINE_RESULT="error (code ${CLAUDE_EXIT})"
  elif [ "$PROCESSOR_EXIT" -ne 0 ]; then
    PIPELINE_RESULT="processor error (code ${PROCESSOR_EXIT})"
  elif [ "$PROMPT_EXIT" -ne 0 ]; then
    PIPELINE_RESULT="prompt error (code ${PROMPT_EXIT})"
  fi
  if ! python3 - "$log" "$PROMPT_EXIT" "$CLAUDE_EXIT" "$PROCESSOR_EXIT" "$PIPELINE_RESULT" <<'PY'
import json
import sys
from pathlib import Path

log, prompt, claude, processor, outcome = sys.argv[1:]
Path(log + ".status.json").write_text(json.dumps({
    "prompt_exit": int(prompt), "claude_exit": int(claude),
    "processor_exit": int(processor), "outcome": outcome,
}) + "\n")
PY
  then
    PIPELINE_RESULT="status recording error"
    return 1
  fi
  [ "$PIPELINE_RESULT" = success ]
}

# Args: <prompt> <base> <revision> <verdict> <summary> <log> <timeout>
# 0 = ACCEPT, 1 = REVISE, 3 = ERROR. The controller writes all artifacts.
evaluate_candidate() {
  local prompt="$1" status
  shift
  EVALUATION_VERDICT=ERROR
  if EVALUATION_VERDICT=$(printf '%s\n' "$prompt" | python3 "${_WORKFLOW_ROOT}/scripts/evaluate.py" \
    --base "$1" --revision "$2" --verdict "$3" --summary "$4" --log "$5" --timeout "$6"); then
    return 0
  else
    status=$?
    case "$EVALUATION_VERDICT:$status" in
      REVISE:1) return 1 ;;
      *) EVALUATION_VERDICT=ERROR; return 3 ;;
    esac
  fi
}
