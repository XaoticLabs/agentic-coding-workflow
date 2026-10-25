#!/usr/bin/env bash
# Ownership and preservation checks shared by all automatic worktree cleanup.
# Metadata lives in the linked worktree's Git directory, outside its checkout.

[[ -n "${_WORKTREE_SAFETY_LOADED:-}" ]] && return 0
_WORKTREE_SAFETY_LOADED=1
WORKTREE_OWNER_TOKEN="${WORKTREE_OWNER_TOKEN:-${CLAUDE_SESSION_ID:-workflow-$$-${RANDOM}}}"
export WORKTREE_OWNER_TOKEN

worktree_metadata_dir() {
  local repo_root worktree_path common_dir repo_common top git_dir
  repo_root=$(realpath "$1") || return 1
  worktree_path=$(realpath "$2") || return 1
  top=$(git -C "$worktree_path" rev-parse --show-toplevel) || return 1
  [ "$(realpath "$top")" = "$worktree_path" ] || return 1
  [ "$worktree_path" != "$repo_root" ] || return 1
  common_dir=$(git -C "$worktree_path" rev-parse --path-format=absolute --git-common-dir) || return 1
  repo_common=$(git -C "$repo_root" rev-parse --path-format=absolute --git-common-dir) || return 1
  [ "$(realpath "$common_dir")" = "$(realpath "$repo_common")" ] || return 1
  git_dir=$(git -C "$worktree_path" rev-parse --absolute-git-dir) || return 1
  # The primary checkout is never eligible, even when repo_root is a linked checkout.
  [ "$(realpath "$git_dir")" != "$(realpath "$common_dir")" ] || return 1
  printf '%s/agentic-worktree\n' "$git_dir"
}

# Register only newly created worktrees. Never adopt an existing checkout.
# Args: <repo-root> <worktree-path> <target-ref>
register_worktree_owner() {
  local metadata branch
  metadata=$(worktree_metadata_dir "$1" "$2") || return 1
  [ ! -e "$metadata" ] || return 1
  branch=$(git -C "$2" symbolic-ref -q HEAD || printf 'detached')
  mkdir "$metadata" || return 1
  printf '%s\n' "$WORKTREE_OWNER_TOKEN" > "$metadata/owner"
  printf '%s\n' "$(realpath "$2")" > "$metadata/path"
  printf '%s\n' "$branch" > "$metadata/branch"
  printf '%s\n' "$3" > "$metadata/target"
  git -C "$1" rev-parse --verify "${3}^{commit}" > "$metadata/base-commit" || return 1
  printf '%s\n' "$$" > "$metadata/active-pid"
}

worktree_owned() {
  local metadata
  metadata=$(worktree_metadata_dir "$1" "$2") || return 1
  [ -f "$metadata/owner" ] && [ "$(cat "$metadata/owner")" = "$WORKTREE_OWNER_TOKEN" ] &&
    [ "$(cat "$metadata/path")" = "$(realpath "$2")" ]
}

activate_worktree() {
  local metadata
  worktree_owned "$1" "$2" || return 1
  metadata=$(worktree_metadata_dir "$1" "$2") || return 1
  printf '%s\n' "$$" > "$metadata/active-pid"
}

release_worktree() {
  local metadata
  worktree_owned "$1" "$2" || return 1
  metadata=$(worktree_metadata_dir "$1" "$2") || return 1
  if [ "$(cat "$metadata/active-pid" 2>/dev/null)" = "$$" ]; then
    rm -f "$metadata/active-pid"
  fi
}

# Unknown or malformed activity metadata is treated as active.
worktree_lease_active() {
  local metadata pid
  metadata=$(worktree_metadata_dir "$1" "$2") || return 0
  [ -f "$metadata/active-pid" ] || return 1
  pid=$(cat "$metadata/active-pid") || return 0
  [[ "$pid" =~ ^[0-9]+$ ]] || return 0
  kill -0 "$pid" 2>/dev/null || [ -d "/proc/$pid" ]
}

# Returns a reason on stdout and nonzero whenever removal cannot be proved safe.
# An explicit target ref overrides the creation target (e.g. parallel integration).
worktree_cleanup_check() {
  local metadata branch target changes pane_path
  worktree_owned "$1" "$2" || { echo unowned; return 1; }
  metadata=$(worktree_metadata_dir "$1" "$2") || return 1
  [ ! -f "${metadata%/agentic-worktree}/locked" ] || { echo locked; return 1; }
  if worktree_lease_active "$1" "$2"; then echo active; return 1; fi
  if command -v tmux >/dev/null 2>&1; then
    while IFS= read -r pane_path; do
      case "$pane_path/" in "$(realpath "$2")/"*) echo active_tmux; return 1 ;; esac
    done < <(tmux list-panes -a -F '#{pane_current_path}' 2>/dev/null || true)
  fi
  # A crashed launcher can leave a live child behind after its PID lease dies.
  if [ -d /proc/self ]; then
    if ! python3 - "$(realpath "$2")" <<'PY'
import os
import sys
from pathlib import Path

worktree = sys.argv[1].rstrip("/") + "/"
for process in Path("/proc").iterdir():
    if not process.name.isdecimal():
        continue
    try:
        directory = os.readlink(process / "cwd").rstrip("/") + "/"
    except OSError:
        continue
    if directory.startswith(worktree):
        sys.exit(1)
PY
    then
      echo active_process
      return 1
    fi
  fi
  branch=$(git -C "$2" symbolic-ref -q HEAD || printf 'detached')
  [ "$branch" = "$(cat "$metadata/branch")" ] || { echo branch_changed; return 1; }
  changes=$(git -C "$2" status --porcelain --untracked-files=all) || { echo status_failed; return 1; }
  [ -z "$changes" ] || { echo dirty; return 1; }
  target="${3:-$(cat "$metadata/target")}"
  git -C "$1" merge-base --is-ancestor "$(git -C "$2" rev-parse HEAD)" "$target" || {
    echo unmerged_or_unknown_target; return 1;
  }
  echo eligible
}

# Copy ignored workflow artifacts before removal. A failed copy blocks cleanup.
preserve_worktree_artifacts() {
  local metadata archive
  worktree_owned "$1" "$2" || return 1
  metadata=$(worktree_metadata_dir "$1" "$2") || return 1
  archive="$3"
  mkdir -p "$archive" || return 1
  archive=$(realpath "$archive") || return 1
  case "$archive/" in "$(realpath "$2")/"*) return 1 ;; esac
  if [ -d "$2/.claude" ]; then
    cp -a "$2/.claude" "$archive/" || return 1
    diff -qr "$2/.claude" "$archive/.claude" >/dev/null || return 1
  fi
  printf '%s\n' "$archive" > "$metadata/archive"
}

# Args: <repo-root> <worktree-path> [<target-ref>] [--keep-branch]
remove_owned_worktree() {
  local metadata reason archive branch
  if ! reason=$(worktree_cleanup_check "$1" "$2" "${3:-}"); then
    echo "PRESERVED:$2:${reason}" >&2
    return 1
  fi
  metadata=$(worktree_metadata_dir "$1" "$2") || return 1
  archive=$(cat "$metadata/archive" 2>/dev/null) || { echo "PRESERVED:$2:artifacts_not_saved" >&2; return 1; }
  [ -d "$archive" ] || return 1
  if [ -d "$2/.claude" ]; then
    diff -qr "$2/.claude" "$archive/.claude" >/dev/null || {
      echo "PRESERVED:$2:artifacts_changed" >&2; return 1;
    }
  fi
  branch=$(git -C "$2" symbolic-ref -q --short HEAD || true)
  # No force, filesystem fallback, or forced branch deletion.
  git -C "$1" worktree remove "$2" || return 1
  if [ "${4:-}" != --keep-branch ] && [ -n "$branch" ]; then
    git -C "$1" branch -d "$branch" || echo "Branch preserved: $branch" >&2
  fi
}
