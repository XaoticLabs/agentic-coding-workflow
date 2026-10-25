#!/usr/bin/env bash
# review-in-worktree.sh — Launch an interactive Claude review session in a
# worktree and attempt owned cleanup on exit, SIGINT, SIGTERM, or SIGHUP.
# Uncatchable termination leaves the checkout for explicit recovery.
#
# This script is intentionally dumb: worktree lifecycle + launch Claude.
# All review logic lives in the pr-reviewer skill (loaded via --append-system-prompt).
#
# Usage: review-in-worktree.sh <repo_root> <worktree_path> <branch> <language> [pr_number]

set -euo pipefail

# Derive plugin root from this script's location (scripts/ is one level below root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
source "${SCRIPT_DIR}/lib/worktree-safety.sh"

REPO_ROOT="$1"
WORKTREE_PATH="$2"
BRANCH="$3"
LANGUAGE="$4"
PR_NUMBER="${5:-}"

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM HUP
  echo ""
  echo "--- Cleaning up worktree: $(basename "$WORKTREE_PATH") ---"
  if ! cd "$REPO_ROOT"; then
    echo "Worktree preserved: ${WORKTREE_PATH}" >&2
    exit "$exit_code"
  fi
  release_worktree "$REPO_ROOT" "$WORKTREE_PATH" || true
  if preserve_worktree_artifacts "$REPO_ROOT" "$WORKTREE_PATH" "${REPO_ROOT}/.claude/worktree-archives/$(date +%s)-$(basename "$WORKTREE_PATH")" &&
    remove_owned_worktree "$REPO_ROOT" "$WORKTREE_PATH" "" --keep-branch; then
    echo "Worktree removed; workflow artifacts archived."
  else
    echo "Worktree preserved: ${WORKTREE_PATH}"
  fi
  exit "$exit_code"
}

worktree_owned "$REPO_ROOT" "$WORKTREE_PATH" || { echo "Unowned worktree preserved: $WORKTREE_PATH" >&2; exit 1; }
activate_worktree "$REPO_ROOT" "$WORKTREE_PATH"
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

cd "$WORKTREE_PATH"

# Bootstrap dependencies — worktrees don't include gitignored dirs (deps/, _build/, node_modules/, .venv/)
echo "--- Bootstrapping dependencies in worktree ---"
if [ -f "mix.exs" ]; then
  echo "Elixir project detected — running mix deps.get && mix compile..."
  mix deps.get 2>&1 && mix compile 2>&1 || echo "Warning: mix bootstrap failed — tests may not run"
elif [ -f "pyproject.toml" ] || [ -f "setup.py" ]; then
  echo "Python project detected — installing dependencies..."
  if [ -f "uv.lock" ] && command -v uv >/dev/null 2>&1; then
    uv sync 2>&1 || echo "Warning: uv sync failed — tests may not run"
  elif [ -f "poetry.lock" ] && command -v poetry >/dev/null 2>&1; then
    poetry install 2>&1 || echo "Warning: poetry install failed — tests may not run"
  elif [ -f "requirements.txt" ]; then
    python -m venv .venv 2>&1 && .venv/bin/pip install -r requirements.txt 2>&1 || echo "Warning: pip install failed — tests may not run"
  fi
elif [ -f "package.json" ]; then
  echo "Node project detected — installing dependencies..."
  npm ci 2>&1 || npm install 2>&1 || echo "Warning: npm install failed — tests may not run"
fi
echo "--- Bootstrap complete ---"

# Load the pr-reviewer skill as system prompt context
SKILL_CONTENT=$(cat "${PLUGIN_ROOT}/skills/pr-reviewer/SKILL.md" 2>/dev/null || echo "")

PR_CONTEXT=""
if [ -n "$PR_NUMBER" ]; then
  PR_CONTEXT=" (PR #${PR_NUMBER})"
fi

# Launch interactive Claude session with the skill loaded as context.
# The skill handles review logic; we just tell it what to review.
# --allowedTools grants prompt-free approval for these patterns; it does not
# restrict Bash to them. The no-edit instruction is workflow policy, not a sandbox.
# Worktree setup is already done — skip that section of the skill.
claude \
  --allowedTools "Read" "Glob" "Grep" "Bash(git diff *)" "Bash(git log *)" "Bash(git show *)" "Bash(git status *)" "Bash(mix test *)" "Bash(mix format *)" "Bash(mix credo *)" "Bash(mix dialyzer *)" "Bash(uv run pytest *)" "Bash(uv run ruff *)" "Bash(uv run basedpyright *)" "Bash(npm test *)" "Bash(gh pr view *)" \
  --disallowedTools "Edit" "Write" "NotebookEdit" \
  --append-system-prompt "You are already in an isolated worktree for this review. Skip the 'Worktree Setup' section — it is already done. ${SKILL_CONTENT}" \
  "Review ${LANGUAGE} branch ${BRANCH}${PR_CONTEXT}. Do NOT edit any files — this is a read-only review."
