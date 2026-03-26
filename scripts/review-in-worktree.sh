#!/usr/bin/env bash
# review-in-worktree.sh — Launch an interactive Claude review session in a
# worktree and guarantee cleanup on exit (normal, SIGINT, SIGTERM, crash).
#
# This script is intentionally dumb: worktree lifecycle + launch Claude.
# All review logic lives in the pr-reviewer skill (loaded via --append-system-prompt).
#
# Usage: review-in-worktree.sh <repo_root> <worktree_path> <branch> <language> [pr_number]

set -euo pipefail

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

# Load the pr-reviewer skill as system prompt context
SKILL_CONTENT=$(cat "${CLAUDE_PLUGIN_ROOT}/skills/pr-reviewer/SKILL.md" 2>/dev/null || echo "")

PR_CONTEXT=""
if [ -n "$PR_NUMBER" ]; then
  PR_CONTEXT=" (PR #${PR_NUMBER})"
fi

# Launch interactive Claude session with the skill loaded as context.
# The skill handles review logic; we just tell it what to review.
# Worktree setup is already done — skip that section of the skill.
claude \
  --append-system-prompt "You are already in an isolated worktree for this review. Skip the 'Worktree Setup' section — it is already done. ${SKILL_CONTENT}" \
  "Review ${LANGUAGE} branch ${BRANCH}${PR_CONTEXT}. Do NOT edit any files — this is a read-only review."
