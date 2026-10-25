#!/usr/bin/env bash
# cleanup-review-worktrees.sh — SessionEnd hook that removes orphaned
# review worktrees. Only targets directories matching the "pr-review-*"
# naming convention. Session ownership, inactivity, merge ancestry, cleanliness,
# and saved artifacts are also required; a matching name alone proves nothing.

SESSION_ID=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("session_id", ""))' 2>/dev/null) || exit 0
if [ -z "${WORKTREE_OWNER_TOKEN:-${CLAUDE_SESSION_ID:-$SESSION_ID}}" ]; then exit 0; fi
export WORKTREE_OWNER_TOKEN="${WORKTREE_OWNER_TOKEN:-${CLAUDE_SESSION_ID:-$SESSION_ID}}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../scripts/lib/worktree-safety.sh" || exit 0

REPO_ROOT=$(git -C "${CLAUDE_PROJECT_DIR:-.}" rev-parse --show-toplevel 2>/dev/null) || exit 0
WORKTREE_BASE="${REPO_ROOT}/.claude/worktrees"

[ -d "$WORKTREE_BASE" ] || exit 0

for dir in "$WORKTREE_BASE"/pr-review-*; do
  [ -d "$dir" ] || continue
  worktree_cleanup_check "$REPO_ROOT" "$dir" >/dev/null 2>&1 || continue
  preserve_worktree_artifacts "$REPO_ROOT" "$dir" "${REPO_ROOT}/.claude/worktree-archives/$(date +%s)-$(basename "$dir")" &&
    remove_owned_worktree "$REPO_ROOT" "$dir" "" --keep-branch || true
done

exit 0
