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

# ── Worktree lifecycle ─────────────────────────────────────────────────

# Ensure .claude/worktrees/ is in .gitignore
# Args: <repo-root>
ensure_worktrees_gitignored() {
  local repo_root="$1"
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

  # Remove stale worktree if it exists
  if [ -d "$worktree_path" ]; then
    git -C "$repo_root" worktree remove --force "$worktree_path" 2>/dev/null || rm -rf "$worktree_path"
  fi

  # Remove stale branch if it exists
  if git -C "$repo_root" show-ref --verify --quiet "refs/heads/$branch_name"; then
    git -C "$repo_root" branch -D "$branch_name" 2>/dev/null || true
  fi

  if [ -n "$start_point" ]; then
    git -C "$repo_root" worktree add -b "$branch_name" "$worktree_path" "$start_point"
  else
    git -C "$repo_root" worktree add -b "$branch_name" "$worktree_path"
  fi

  # Copy spec directory into worktree
  if [ -n "$spec_dir" ] && [ -n "$slug" ] && [ -d "$spec_dir" ]; then
    mkdir -p "${worktree_path}/.claude/specs/"
    cp -r "$spec_dir" "${worktree_path}/.claude/specs/${slug}/"
  fi

  # Copy AGENTS.md if it exists
  local agents_file="${repo_root}/.claude/AGENTS.md"
  [ -f "$agents_file" ] && mkdir -p "${worktree_path}/.claude" && cp "$agents_file" "${worktree_path}/.claude/"

  # Ensure .claude dirs exist for markers and logs
  mkdir -p "${worktree_path}/.claude/ralph-logs"

  # Write task assignments if provided
  if [ -n "$task_list" ]; then
    echo "$task_list" > "${worktree_path}/.claude/ralph-assigned-tasks"
  fi
}

# Remove a worktree and optionally its branch.
# Args: <repo-root> <worktree-path> <branch-name> [--keep-branch]
cleanup_worker_worktree() {
  local repo_root="$1"
  local worktree_path="$2"
  local branch_name="$3"
  local keep_branch="${4:-}"

  if [ -d "$worktree_path" ]; then
    git -C "$repo_root" worktree remove --force "$worktree_path" 2>/dev/null || rm -rf "$worktree_path"
  fi

  if [ "$keep_branch" != "--keep-branch" ]; then
    git -C "$repo_root" branch -D "$branch_name" 2>/dev/null || true
  fi
}

# ── Tmux management ───────────────────────────────────────────────────

# Create a tmux session with the first pane.
# Args: <session-name> <working-dir> <command>
create_tmux_session() {
  local session_name="$1"
  local working_dir="$2"
  local command="$3"

  # Kill existing session if present
  tmux kill-session -t "$session_name" 2>/dev/null || true

  tmux new-session -d -s "$session_name" -c "$working_dir" "$command"
}

# Add a pane to an existing tmux session.
# Args: <session-name> <working-dir> <command>
add_tmux_pane() {
  local session_name="$1"
  local working_dir="$2"
  local command="$3"

  tmux split-window -t "$session_name" -c "$working_dir" "$command"
}

# Safely kill a tmux session.
# Args: <session-name>
kill_session_safe() {
  local session_name="$1"
  tmux kill-session -t "$session_name" 2>/dev/null || true
}

# ── Test/lint detection ───────────────────────────────────────────────

# Detect the test command from AGENTS.md or common project files.
# Args: <project-dir>
# Outputs: test command string (or empty)
detect_test_command() {
  local project_dir="$1"
  local agents_file="${project_dir}/.claude/AGENTS.md"
  local test_cmd=""

  # Try AGENTS.md first (Ralph convention)
  if [ -f "$agents_file" ]; then
    test_cmd=$(grep -A1 '| Test' "$agents_file" 2>/dev/null | tail -1 | sed 's/.*| `\(.*\)`.*/\1/' | sed 's/|//g' | xargs || true)
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

  echo "$test_cmd"
}

# Detect the lint command from AGENTS.md or common project files.
# Args: <project-dir>
# Outputs: lint command string (or empty)
detect_lint_command() {
  local project_dir="$1"
  local agents_file="${project_dir}/.claude/AGENTS.md"
  local lint_cmd=""

  # Try AGENTS.md first
  if [ -f "$agents_file" ]; then
    lint_cmd=$(grep -A1 '| Lint' "$agents_file" 2>/dev/null | tail -1 | sed 's/.*| `\(.*\)`.*/\1/' | sed 's/|//g' | xargs || true)
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

  echo "$lint_cmd"
}

# Run test gate: execute test command, return 0 if pass, 1 if fail.
# Args: <project-dir> [<log-file>]
# Outputs: test output to log file (or /dev/null)
run_test_gate() {
  local project_dir="$1"
  local log_file="${2:-/dev/null}"

  local test_cmd
  test_cmd=$(detect_test_command "$project_dir")

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
