#!/usr/bin/env bash
# Shared option parser for the launcher, standalone loop, and parallel workers.

ralph_parse_options() {
  ONCE_FLAG="" CLEAN_ROOM_FLAG="" EVAL_GATES_MERGE=""
  TIME_BUDGET=600 CHECKPOINT_EVERY=""
  RALPH_ACTION=build RALPH_PARALLEL_WORKERS="" RALPH_MAX_ITERATIONS=50
  RALPH_LOOP_FLAGS=()
  local option value no_eval="" per_iter=""
  while [ "$#" -gt 0 ]; do
    option="${1%%=*}"
    case "$option" in
      --time-budget|--checkpoint-every|--parallel|--max)
        if [[ "$1" == *=* ]]; then
          value="${1#*=}"
        else
          [ "$#" -ge 2 ] || { echo "Missing value for $option" >&2; return 2; }
          shift
          value="$1"
        fi
        case "$option" in
          --time-budget)
            [[ "$value" =~ ^[0-9]+([.][0-9]+)?$ ]] || { echo "Invalid time budget: $value" >&2; return 2; }
            TIME_BUDGET="$value" ;;
          --checkpoint-every|--max)
            [[ "$value" =~ ^[1-9][0-9]*$ ]] || { echo "$option requires a positive integer" >&2; return 2; }
            if [ "$option" = --max ]; then RALPH_MAX_ITERATIONS="$value"; else CHECKPOINT_EVERY="$value"; fi ;;
          --parallel)
            [[ "$value" =~ ^[2-6]$ ]] || { echo "--parallel requires 2-6 workers" >&2; return 2; }
            RALPH_PARALLEL_WORKERS="$value" ;;
        esac ;;
      --once) ONCE_FLAG=1 ;;
      --clean-room) CLEAN_ROOM_FLAG=1 ;;
      --eval-gates-merge) EVAL_GATES_MERGE=1 ;;
      --eval-per-iter) per_iter=1 ;;
      --no-eval) no_eval=1 ;;
      --plan|--harvest)
        [ "$RALPH_ACTION" = build ] || { echo "Choose either --plan or --harvest" >&2; return 2; }
        RALPH_ACTION="${option#--}" ;;
      *) echo "Unknown Ralph option: $1" >&2; return 2 ;;
    esac
    shift
  done
  if [ -n "$no_eval" ] && { [ -n "$per_iter" ] || [ -n "$EVAL_GATES_MERGE" ]; }; then
    echo "--no-eval cannot be combined with --eval-per-iter or --eval-gates-merge" >&2
    return 2
  fi
  if [ -n "$RALPH_PARALLEL_WORKERS" ] && { [ -n "$ONCE_FLAG" ] || [ "$RALPH_ACTION" != build ]; }; then
    echo "--parallel cannot be combined with --once, --plan, or --harvest" >&2
    return 2
  fi
  if [ -n "$per_iter" ]; then
    export RALPH_EVAL_PER_ITER=true
    RALPH_LOOP_FLAGS+=(--eval-per-iter)
  fi
  if [ -n "$no_eval" ]; then
    export RALPH_EVAL_PER_ITER=false RALPH_EVAL_END_OF_RUN=false RALPH_PARALLEL_EVAL=off
    RALPH_LOOP_FLAGS+=(--no-eval)
  fi
  [ -z "$ONCE_FLAG" ] || RALPH_LOOP_FLAGS+=(--once)
  [ -z "$CLEAN_ROOM_FLAG" ] || RALPH_LOOP_FLAGS+=(--clean-room)
  RALPH_LOOP_FLAGS+=("--time-budget=$TIME_BUDGET")
  [ -z "$CHECKPOINT_EVERY" ] || RALPH_LOOP_FLAGS+=("--checkpoint-every=$CHECKPOINT_EVERY")
  [ -z "$EVAL_GATES_MERGE" ] || RALPH_LOOP_FLAGS+=(--eval-gates-merge)
  return 0
}
