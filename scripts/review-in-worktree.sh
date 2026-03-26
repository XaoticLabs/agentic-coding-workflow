#!/usr/bin/env bash
# review-in-worktree.sh — Launch an interactive Claude review session in a
# worktree and guarantee cleanup on exit (normal, SIGINT, SIGTERM, crash).
#
# This script is intentionally dumb: worktree lifecycle + launch Claude.
# All review logic lives in the pr-reviewer skill (loaded via --append-system-prompt).
#
# Usage: review-in-worktree.sh <repo_root> <worktree_path> <branch> <language> [pr_number]

set -euo pipefail

# Derive plugin root from this script's location (scripts/ is one level below root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

REPO_ROOT="$1"
WORKTREE_PATH="$2"
BRANCH="$3"
LANGUAGE="$4"
PR_NUMBER="${5:-}"

cleanup() {
  local exit_code=$?
  echo ""
  echo "--- Cleaning up worktree: $(basename "$WORKTREE_PATH") ---"
  cd "$REPO_ROOT" 2>/dev/null || true
  git worktree remove "$WORKTREE_PATH" --force 2>/dev/null || true
  git worktree prune 2>/dev/null || true
  echo "Worktree removed."
  exit $exit_code
}

trap cleanup EXIT INT TERM HUP

cd "$WORKTREE_PATH"

# Bootstrap dependencies — worktrees don't include gitignored dirs (deps/, _build/, node_modules/, .venv/)
echo "--- Bootstrapping dependencies in worktree ---"
if [ -f "mix.exs" ]; then
  echo "Elixir project detected — running mix deps.get && mix compile..."
  mix deps.get 2>&1 && mix compile 2>&1 || echo "Warning: mix bootstrap failed — tests may not run"
elif [ -f "pyproject.toml" ] || [ -f "setup.py" ]; then
  echo "Python project detected — installing dependencies..."
  if [ -f "pyproject.toml" ] && command -v uv >/dev/null 2>&1; then
    uv sync 2>&1 || echo "Warning: uv sync failed — tests may not run"
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
# Worktree setup is already done — skip that section of the skill.
claude \
  --allowedTools "Read" "Glob" "Grep" "Bash(git diff *)" "Bash(git log *)" "Bash(git show *)" "Bash(git status *)" "Bash(mix test *)" "Bash(mix format *)" "Bash(mix credo *)" "Bash(mix dialyzer *)" "Bash(uv run pytest *)" "Bash(uv run ruff *)" "Bash(uv run basedpyright *)" "Bash(npm test *)" "Bash(gh pr view *)" \
  --disallowedTools "Edit" "Write" "NotebookEdit" \
  --append-system-prompt "You are already in an isolated worktree for this review. Skip the 'Worktree Setup' section — it is already done. ${SKILL_CONTENT}" \
  "Review ${LANGUAGE} branch ${BRANCH}${PR_CONTEXT}. Do NOT edit any files — this is a read-only review."
