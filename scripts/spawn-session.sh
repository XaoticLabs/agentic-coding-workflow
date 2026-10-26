#!/usr/bin/env bash
# Launch a plugin role; native worktrees/tmux handle isolated sessions.
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: spawn-session.sh <role> [--name <name>] [--worktree <name>] [--context <file>] [--goal <condition> | [--] [prompt]]
       spawn-session.sh --resume <session> [--context <file>] [--goal <condition> | [--] [prompt]]
USAGE
}
error() { echo "Error: $*" >&2; exit 2; }

if [ "${1:-}" = --help ] || [ "${1:-}" = -h ]; then usage; exit 0; fi
[ "$#" -gt 0 ] || { usage >&2; exit 2; }
ROLE=""
if [[ "$1" != -* ]]; then ROLE="$1"; shift; fi
PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${PLUGIN_ROOT}/scripts/lib/claude-runner.sh"
WORKTREE_NAME=""
SESSION_NAME=""
RESUME=""
GOAL=""
CONTEXT_FILE=""
PROMPT=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --name|--worktree|--context|--resume|--goal)
      [ "$#" -ge 2 ] && [ -n "$2" ] && [[ "$2" != -* ]] || error "$1 requires a value."
      case "$1" in
        --name) SESSION_NAME="$2" ;;
        --worktree) WORKTREE_NAME="$2" ;;
        --context) CONTEXT_FILE="$2" ;;
        --resume) RESUME="$2" ;;
        --goal) GOAL="$2" ;;
      esac
      shift 2 ;;
    --)
      shift
      PROMPT="${PROMPT:+$PROMPT }$*"
      break ;;
    -*) error "Unknown option: $1" ;;
    *) PROMPT="${PROMPT:+$PROMPT }$1"; shift ;;
  esac
done
if [ -n "$RESUME" ]; then
  [ -z "$ROLE$SESSION_NAME$WORKTREE_NAME" ] || error '--resume restores the saved agent and checkout; do not combine it with a role, --name, or --worktree.'
else
  [[ "$ROLE" =~ ^[a-z][a-z0-9-]*$ ]] || error 'A valid role is required for a new session.'
  [ -f "$PLUGIN_ROOT/agents/$ROLE.md" ] || error "Unknown role: $ROLE. See $PLUGIN_ROOT/agents/."
fi
if [ -n "$GOAL" ]; then
  [ -z "$PROMPT" ] || error 'Use either --goal or a task prompt.'
  [[ "$GOAL" =~ [^[:space:]] ]] || error 'The goal condition must not be blank.'
  PROMPT="$GOAL"
fi
command -v claude >/dev/null 2>&1 || error 'Claude Code is not installed.'

if [ -n "$CONTEXT_FILE" ]; then
  [ -f "$CONTEXT_FILE" ] && [ -r "$CONTEXT_FILE" ] || error "Context file is not readable: $CONTEXT_FILE"
  CONTEXT_FILE=$(realpath "$CONTEXT_FILE")
  PROMPT="Read the context file at ${CONTEXT_FILE} before starting.

${PROMPT}"
fi
if [ -n "$GOAL" ]; then
  [ "${#PROMPT}" -le 4000 ] || error 'The goal condition, including context instructions, exceeds 4000 characters.'
  PROMPT="/goal $PROMPT"
fi
# Ordinary sessions must not inherit a caller's Ralph worker contract. Keep
# the override in argv so it also survives an existing tmux server's env.
workflow_model_environment_args
WORKFLOW_MODEL_ARGS=()
if [ -z "$RESUME" ]; then
  MODEL_ROLE=build
  [ "$ROLE" != evaluator ] || MODEL_ROLE=evaluator
  workflow_model_args "$MODEL_ROLE"
fi
CLAUDE_ARGS=("${WORKFLOW_ENV_ARGS[@]}" RALPH_MODE=0 claude --plugin-dir "$PLUGIN_ROOT" "${WORKFLOW_MODEL_ARGS[@]}")
if [ -n "$RESUME" ]; then
  CLAUDE_ARGS+=(--resume "$RESUME")
else
  CLAUDE_ARGS+=(--agent "agentic-coding-workflow:$ROLE")
  SESSION_NAME="${SESSION_NAME:-$WORKTREE_NAME}"
  [ -z "$SESSION_NAME" ] || CLAUDE_ARGS+=(--name "$SESSION_NAME")
  if [ -n "$WORKTREE_NAME" ]; then
    CLAUDE_ARGS+=(--worktree "$WORKTREE_NAME" --tmux)
  fi
fi
[ -z "$PROMPT" ] || CLAUDE_ARGS+=("$PROMPT")

if [ -n "$RESUME" ]; then
  # Native resume restores the saved worktree and agent; never create a new
  # session after a missing/ambiguous session or a failed resume.
  exec "${CLAUDE_ARGS[@]}"
fi
command -v tmux >/dev/null 2>&1 || error 'tmux is not installed.'
if [ -n "$WORKTREE_NAME" ]; then
  exec "${CLAUDE_ARGS[@]}"
fi

# Sharing the current checkout is a deliberate pane operation. The native
# --tmux flag requires --worktree; preserve the non-isolated mode separately.
[ -n "${TMUX:-}" ] || error 'For the current checkout, run inside tmux; otherwise pass --worktree <name>.'
printf -v COMMAND '%q ' "${CLAUDE_ARGS[@]}"
exec tmux split-window -h -c "$PWD" bash -c "$COMMAND"
