#!/usr/bin/env bash
# Lists all git worktrees with branch and commit info.
# Highlights worktrees under .claude/worktrees/.

set -euo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel)
WORKTREE_BASE="${REPO_ROOT}/.claude/worktrees"

# Header
printf "%-50s %-30s %s\n" "PATH" "BRANCH" "COMMIT"
printf "%-50s %-30s %s\n" "----" "------" "------"

git worktree list --porcelain | while read -r line; do
  case "$line" in
    "worktree "*)
      wt_path="${line#worktree }"
      ;;
    "branch "*)
      wt_branch="${line#branch refs/heads/}"
      ;;
    "HEAD "*)
      wt_commit="${line#HEAD }"
      wt_commit="${wt_commit:0:7}"
      ;;
    "")
      # End of entry — print it
      if [[ -n "${wt_path:-}" ]]; then
        display_path="$wt_path"
        if [[ "$wt_path" == "$WORKTREE_BASE"* ]]; then
          display_path=".claude/worktrees/${wt_path#$WORKTREE_BASE/}"
        fi
        printf "%-50s %-30s %s\n" "$display_path" "${wt_branch:-detached}" "${wt_commit:-unknown}"
      fi
      unset wt_path wt_branch wt_commit
      ;;
  esac
done
