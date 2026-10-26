#!/usr/bin/env bash
# Usage: launch.sh <spec-dir> [--once|--plan|--harvest|--parallel N] [options...]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/options.sh"
source "${SCRIPT_DIR}/../../../scripts/lib/claude-runner.sh"
SPEC_DIR="${1:?Usage: launch.sh <spec-dir> [options...]}"
shift
ralph_parse_options "$@"
PROJECT_DIR="$(realpath "${CLAUDE_PROJECT_DIR:-.}")"
cd "$PROJECT_DIR"
[ -d "$SPEC_DIR" ] || { echo "Spec directory not found: $SPEC_DIR" >&2; exit 1; }
SPEC_DIR="$(realpath "$SPEC_DIR")"
SLUG="$(basename "$SPEC_DIR")"
export CLAUDE_PROJECT_DIR="$PROJECT_DIR"
export CLAUDE_PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "${SCRIPT_DIR}/../../.." && pwd)}"

bash "${SCRIPT_DIR}/generate-agents-md.sh"
if [ "$RALPH_ACTION" != build ]; then
  exec bash "${SCRIPT_DIR}/loop.sh" "$SPEC_DIR" "$RALPH_ACTION" 1 "${RALPH_LOOP_FLAGS[@]}"
fi
if [ ! -f "${SPEC_DIR}/IMPLEMENTATION_PLAN.md" ]; then
  bash "${SCRIPT_DIR}/loop.sh" "$SPEC_DIR" plan 1 "${RALPH_LOOP_FLAGS[@]}"
fi

if [ -n "$ONCE_FLAG" ]; then
  exec bash "${SCRIPT_DIR}/loop.sh" "$SPEC_DIR" build 1 "${RALPH_LOOP_FLAGS[@]}"
fi

SESSION_NAME="ralph-${SLUG}"
INVOCATION=(bash "${SCRIPT_DIR}/loop.sh" "$SPEC_DIR" build "$RALPH_MAX_ITERATIONS")
if [ -n "$RALPH_PARALLEL_WORKERS" ]; then
  SESSION_NAME="${SESSION_NAME}-orch"
  INVOCATION=(bash "${SCRIPT_DIR}/orchestrate-parallel.sh" "$SPEC_DIR" "$SLUG" "$RALPH_PARALLEL_WORKERS" "$RALPH_MAX_ITERATIONS")
fi
INVOCATION+=("${RALPH_LOOP_FLAGS[@]}")

if ! command -v tmux >/dev/null 2>&1; then
  [ -z "$RALPH_PARALLEL_WORKERS" ] || { echo "Parallel Ralph requires tmux" >&2; exit 1; }
  echo "tmux unavailable; running Ralph in the foreground." >&2
  exec "${INVOCATION[@]}"
fi
if tmux has-session -t "$SESSION_NAME" 2>/dev/null ||
  { [ -n "${TMUX:-}" ] && tmux list-windows -F '#{window_name}' | grep -Fxq "$SESSION_NAME"; }; then
  echo "Ralph already running: $SESSION_NAME"
  exit 0
fi
PID_FILE="${PROJECT_DIR}/.claude/ralph/${SLUG}/orchestrator.pid"
if [ -n "$RALPH_PARALLEL_WORKERS" ] && [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Parallel orchestrator already running (PID: $(cat "$PID_FILE"))"
  exit 0
fi

# tmux's server may have an older environment. Persist explicit settings and
# shell-escaped arguments in one script shared by window and session launches.
LAUNCHER="${PROJECT_DIR}/.claude/ralph/${SLUG}/launch.sh"
mkdir -p "$(dirname "$LAUNCHER")"
{
  printf '#!/usr/bin/env bash\nset -euo pipefail\n'
  printf 'export CLAUDE_PROJECT_DIR=%q\n' "$PROJECT_DIR"
  printf 'export CLAUDE_PLUGIN_ROOT=%q\n' "$CLAUDE_PLUGIN_ROOT"
  printf 'export PATH=%q\n' "$PATH"
  printf 'export RALPH_EVAL_PER_ITER=%q\n' "${RALPH_EVAL_PER_ITER:-false}"
  printf 'export RALPH_EVAL_END_OF_RUN=%q\n' "${RALPH_EVAL_END_OF_RUN:-true}"
  printf 'export RALPH_PARALLEL_EVAL=%q\n' "${RALPH_PARALLEL_EVAL:-end}"
  write_workflow_model_environment
  printf 'cd %q\n' "$PROJECT_DIR"
  printf 'exec '
  printf '%q ' "${INVOCATION[@]}"
  printf '\n'
} > "$LAUNCHER"
chmod +x "$LAUNCHER"
if [ -n "${TMUX:-}" ]; then
  tmux new-window -n "$SESSION_NAME" -c "$PROJECT_DIR" bash "$LAUNCHER"
else
  tmux new-session -d -s "$SESSION_NAME" -c "$PROJECT_DIR" bash "$LAUNCHER"
fi
echo "Ralph launched: $SESSION_NAME"
echo "Status: /agentic-coding-workflow:ralph $SLUG --status"
echo "Stop: /agentic-coding-workflow:ralph $SLUG --stop"
