#!/usr/bin/env bash
# review-in-worktree.sh — Launch an interactive Claude review session in a
# worktree and attempt owned cleanup on exit, SIGINT, SIGTERM, or SIGHUP.
# Uncatchable termination leaves the checkout for explicit recovery.
#
# This script is intentionally dumb: worktree lifecycle + launch Claude.
# All review logic lives in the pr-reviewer skill (loaded via --append-system-prompt).
#
# Usage: review-in-worktree.sh <repo_root> <worktree_path> <branch> <language> [pr_number] [defects|suggestions]

set -euo pipefail

# Derive plugin root from this script's location (scripts/ is one level below root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
source "${SCRIPT_DIR}/lib/worktree-safety.sh"
source "${SCRIPT_DIR}/lib/claude-runner.sh"

REPO_ROOT="$1"
WORKTREE_PATH="$2"
BRANCH="$3"
LANGUAGE="$4"
PR_NUMBER="${5:-}"
REVIEW_MODE="${6:-defects}"
case "$REVIEW_MODE" in defects|suggestions) ;; *) echo "Error: invalid review mode" >&2; exit 2 ;; esac

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

# Inspect configuration without installing dependencies or changing lockfiles.
# A missing environment limits verification, but does not prevent code inspection.
echo "Inspecting project check configuration (no dependency installation)..."
if ! python3 "${PLUGIN_ROOT}/scripts/project-commands.py" readiness "$PWD"; then
  echo "Verification setup is incomplete; continue inspection and report limitations."
fi

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
workflow_model_args evaluator
if [ "${WORKFLOW_HOST:-claude}" != claude ]; then
  # The host runner supplies the evaluator's restricted native role and keeps
  # the selected host throughout its child lifecycle. This launcher owns cleanup.
  python3 "${PLUGIN_ROOT}/scripts/host-runner.py" prompt \
    --host "$WORKFLOW_HOST" --role evaluator \
    "You are in an isolated worktree. Review ${LANGUAGE} branch ${BRANCH}${PR_CONTEXT}. Read ${PLUGIN_ROOT}/skills/pr-reviewer/SKILL.md and ${PLUGIN_ROOT}/references/review-policy.md. Review mode: ${REVIEW_MODE}. Do not edit files."
  exit $?
fi
claude "${WORKFLOW_MODEL_ARGS[@]}" \
  --allowedTools "Read" "Glob" "Grep" "Bash(git diff *)" "Bash(git log *)" "Bash(git show *)" "Bash(git status *)" "Bash(mix test *)" "Bash(mix format *)" "Bash(mix credo *)" "Bash(mix dialyzer *)" "Bash(uv run pytest *)" "Bash(uv run ruff *)" "Bash(uv run basedpyright *)" "Bash(npm test *)" "Bash(gh pr view *)" \
  --disallowedTools "Edit" "Write" "NotebookEdit" \
  --append-system-prompt "You are already in an isolated worktree for this review. Skip the 'Worktree Setup' section — it is already done. Plugin root: ${PLUGIN_ROOT}. Resolve reviewer-relative references under ${PLUGIN_ROOT}/skills/pr-reviewer. Read ${PLUGIN_ROOT}/references/review-policy.md. Review mode: ${REVIEW_MODE}; include optional design/taste suggestions only in suggestions mode. ${SKILL_CONTENT}" \
  "Review ${LANGUAGE} branch ${BRANCH}${PR_CONTEXT}. Do NOT edit any files — this is a read-only review."
