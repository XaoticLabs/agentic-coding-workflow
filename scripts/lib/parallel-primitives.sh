#!/usr/bin/env bash
# Shared primitives for parallel workflow orchestration.
# Source this file from orchestrate-parallel.sh, merge-workers.sh, loop.sh, etc.
#
# Provides:
#   Worktree lifecycle:  create_worker_worktree, cleanup_worker_worktree, ensure_worktrees_gitignored
#   Tmux management:     create_tmux_session, add_tmux_pane, kill_session_safe
#   Test/lint detection: detect_test_command, detect_lint_command, run_test_gate
#   Tracing:             trace_event (portable version for orchestrator scripts)

# Guard against double-sourcing
[[ -n "${_PARALLEL_PRIMITIVES_LOADED:-}" ]] && return 0
_PARALLEL_PRIMITIVES_LOADED=1
source "$(dirname "${BASH_SOURCE[0]}")/worktree-safety.sh"
_PROJECT_COMMANDS_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/project-commands.py"

# ── Worktree lifecycle ─────────────────────────────────────────────────

# Ensure .claude/worktrees/ is in .gitignore
# Args: <repo-root>
ensure_worktrees_gitignored() {
  local repo_root="$1"
  if git -C "$repo_root" check-ignore -q .claude/worktrees/.probe; then return 0; fi
  if ! grep -q '\.claude/worktrees/' "${repo_root}/.gitignore" 2>/dev/null; then
    echo -e '\n# Git worktrees (parallel branch work)\n.claude/worktrees/' >> "${repo_root}/.gitignore"
  fi
}

# Create a worker worktree with branch, spec copy, and task assignments.
# Args: <repo-root> <worktree-path> <branch-name> [<spec-dir> <slug> <task-list> <start-point>]
# task-list: comma-separated task numbers (optional)
# start-point: branch/commit to branch from (optional, defaults to HEAD)
create_worker_worktree() {
  local repo_root="$1"
  local worktree_path="$2"
  local branch_name="$3"
  local spec_dir="${4:-}"
  local slug="${5:-}"
  local task_list="${6:-}"
  local start_point="${7:-}"

  # Existing paths and branches may belong to another run or contain unfinished work.
  if [ -e "$worktree_path" ] || [ -L "$worktree_path" ] ||
    git -C "$repo_root" show-ref --verify --quiet "refs/heads/$branch_name"; then
    echo "ERROR: Worktree path or branch already exists; preserved: $worktree_path ($branch_name)" >&2
    return 1
  fi

  if [ -n "$start_point" ]; then
    git -C "$repo_root" worktree add -b "$branch_name" "$worktree_path" "$start_point"
  else
    git -C "$repo_root" worktree add -b "$branch_name" "$worktree_path"
  fi
  register_worktree_owner "$repo_root" "$worktree_path" "${start_point:-HEAD}" || return 1

  # Copy spec directory into worktree
  if [ -n "$spec_dir" ] && [ -n "$slug" ] && [ -d "$spec_dir" ]; then
    mkdir -p "${worktree_path}/.claude/specs/"
    cp -r "$spec_dir" "${worktree_path}/.claude/specs/${slug}/"
  fi

  # Copy project guidance and command configuration, including untracked overrides.
  local context_file
  mkdir -p "${worktree_path}/.claude"
  for context_file in AGENTS.md project-commands.json; do
    if [ -f "${repo_root}/.claude/${context_file}" ]; then
      cp "${repo_root}/.claude/${context_file}" "${worktree_path}/.claude/"
    fi
  done

  # Ensure .claude dirs exist for markers and logs
  mkdir -p "${worktree_path}/.claude/ralph-logs"

  # Write task assignments if provided
  if [ -n "$task_list" ]; then
    echo "$task_list" > "${worktree_path}/.claude/ralph-assigned-tasks"
  fi
}

# Remove a worktree and optionally its branch.
# Args: <repo-root> <worktree-path> <branch-name> [--keep-branch] [<target-ref> <archive-dir>]
cleanup_worker_worktree() {
  local repo_root="$1"
  local worktree_path="$2"
  local branch_name="$3"
  local keep_branch="${4:-}"
  local reason

  if [ "$(git -C "$worktree_path" symbolic-ref -q --short HEAD)" != "$branch_name" ]; then
    echo "PRESERVED:${worktree_path}:branch_changed" >&2
    return 1
  fi
  if ! reason=$(worktree_cleanup_check "$repo_root" "$worktree_path" "${5:-}"); then
    echo "PRESERVED:${worktree_path}:${reason}" >&2
    return 1
  fi
  preserve_worktree_artifacts "$repo_root" "$worktree_path" "${6:-${repo_root}/.claude/worktree-archives/$(date +%s)-$(basename "$worktree_path")}" || return 1
  remove_owned_worktree "$repo_root" "$worktree_path" "${5:-}" "$keep_branch"
}

# ── Tmux management ───────────────────────────────────────────────────

# Create a tmux workspace with the first pane.
# If already inside tmux, creates a new window (tab) in the current session.
# Otherwise creates a new detached session.
# Args: <name> <working-dir> <command>
# Stdout: the tmux target to use for add_tmux_pane and select-layout
create_tmux_session() {
  local name="$1"
  local working_dir="$2"
  local command="$3"

  if [ -n "${TMUX:-}" ]; then
    # Already in tmux — create a window (tab) in the current session
    tmux new-window -n "$name" -c "$working_dir" "$command"
    echo "$(tmux display-message -p '#{session_name}'):${name}"
  else
    # Not in tmux — create a detached session
    tmux kill-session -t "$name" 2>/dev/null || true
    tmux new-session -d -s "$name" -c "$working_dir" "$command"
    echo "$name"
  fi
}

# Add a pane to an existing tmux workspace.
# Args: <target> <working-dir> <command>
# <target> should be the value returned by create_tmux_session
add_tmux_pane() {
  local target="$1"
  local working_dir="$2"
  local command="$3"

  tmux split-window -t "$target" -c "$working_dir" "$command"
}

# Safely kill a tmux workspace (tries window first, then session).
# Args: <name>
kill_workspace_safe() {
  local name="$1"
  # Try as a window name first (for when created inside tmux)
  tmux kill-window -t ":${name}" 2>/dev/null || \
    tmux kill-session -t "$name" 2>/dev/null || true
}

# Backward compat alias
kill_session_safe() { kill_workspace_safe "$@"; }

# ── Test/lint detection ───────────────────────────────────────────────

# Detect the test command from project-commands.json or common project files.
# Args: <project-dir>
# Outputs: test command string (or empty)
detect_test_command() {
  local project_dir="$1"
  local test_cmd=""
  local config_status

  if test_cmd=$(python3 "$_PROJECT_COMMANDS_SCRIPT" get "$project_dir" test); then
    printf '%s\n' "$test_cmd"
    return 0
  else
    config_status=$?
    [ "$config_status" -eq 1 ] || return "$config_status"
  fi

  # Fall back to file detection
  if [ -z "$test_cmd" ]; then
    if [ -f "${project_dir}/mix.exs" ]; then
      test_cmd="mix test"
    elif [ -f "${project_dir}/pytest.ini" ] || [ -f "${project_dir}/pyproject.toml" ]; then
      test_cmd="pytest"
    elif [ -f "${project_dir}/package.json" ]; then
      if grep -q '"test"' "${project_dir}/package.json" 2>/dev/null; then
        test_cmd="npm test"
      fi
    elif [ -f "${project_dir}/Makefile" ]; then
      if grep -q '^test:' "${project_dir}/Makefile" 2>/dev/null; then
        test_cmd="make test"
      fi
    elif [ -f "${project_dir}/Cargo.toml" ]; then
      test_cmd="cargo test"
    elif [ -f "${project_dir}/go.mod" ]; then
      test_cmd="go test ./..."
    fi
  fi

  printf '%s\n' "$test_cmd"
}

# Detect the lint command from project-commands.json or common project files.
# Args: <project-dir>
# Outputs: lint command string (or empty)
detect_lint_command() {
  local project_dir="$1"
  local lint_cmd=""
  local config_status

  if lint_cmd=$(python3 "$_PROJECT_COMMANDS_SCRIPT" get "$project_dir" lint); then
    printf '%s\n' "$lint_cmd"
    return 0
  else
    config_status=$?
    [ "$config_status" -eq 1 ] || return "$config_status"
  fi

  # Fall back to file detection
  if [ -z "$lint_cmd" ]; then
    if [ -f "${project_dir}/mix.exs" ]; then
      lint_cmd="mix credo"
    elif [ -f "${project_dir}/.eslintrc.js" ] || [ -f "${project_dir}/.eslintrc.json" ] || [ -f "${project_dir}/eslint.config.js" ]; then
      lint_cmd="npx eslint ."
    elif [ -f "${project_dir}/pyproject.toml" ]; then
      if grep -q 'ruff' "${project_dir}/pyproject.toml" 2>/dev/null; then
        lint_cmd="ruff check ."
      fi
    fi
  fi

  printf '%s\n' "$lint_cmd"
}

# Run test gate: execute test command, return 0 if pass, 1 if fail.
# Args: <project-dir> [<log-file>]
# Outputs: test output to log file (or /dev/null)
run_test_gate() {
  local project_dir="$1"
  local log_file="${2:-/dev/null}"

  local test_cmd
  if ! test_cmd=$(detect_test_command "$project_dir"); then
    echo "Unable to read project test configuration." | tee "$log_file" >&2
    return 1
  fi

  if [ -z "$test_cmd" ]; then
    echo "  No test command detected — skipping test gate."
    return 0
  fi

  echo "  Running tests: $test_cmd"
  if (cd "$project_dir" && eval "$test_cmd") > "$log_file" 2>&1; then
    return 0
  else
    return 1
  fi
}

# Verify the final candidate with both configured checks before evaluation.
# Args: <project-dir> <log-prefix>
run_verification_gate() {
  local project_dir="$1" log_prefix="$2" lint_cmd passed=true
  if ! run_test_gate "$project_dir" "${log_prefix}-test.log"; then passed=false; fi
  if lint_cmd=$(detect_lint_command "$project_dir"); then
    if [ -n "$lint_cmd" ] && ! (cd "$project_dir" && eval "$lint_cmd") > "${log_prefix}-lint.log" 2>&1; then
      passed=false
    fi
  else
    passed=false
  fi
  [ "$passed" = true ]
}

# ── Tracing ───────────────────────────────────────────────────────────

# Portable trace_event for use by orchestrator scripts.
# Requires TRACE_FILE to be set in the calling script.
# Usage: trace_event <type> [key=value ...]
trace_event() {
  local trace_file="${TRACE_FILE:-}"
  [ -z "$trace_file" ] && return 0

  local type="$1"
  shift
  local json="{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"type\":\"${type}\""
  for kv in "$@"; do
    local key="${kv%%=*}"
    local val="${kv#*=}"
    if [[ "$val" =~ ^[0-9]+$ ]]; then
      json="${json},\"${key}\":${val}"
    elif [[ "$val" == "true" || "$val" == "false" ]]; then
      json="${json},\"${key}\":${val}"
    else
      val=$(printf '%s' "$val" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n' ' ' | head -c 500)
      json="${json},\"${key}\":\"${val}\""
    fi
  done
  json="${json}}"
  echo "$json" >> "$trace_file"
}
