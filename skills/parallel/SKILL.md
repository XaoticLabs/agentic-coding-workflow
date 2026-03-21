---
name: parallel
description: |
  Create multiple worktrees with tmux panes and Claude sessions for parallel work.
  Use when: working on multiple tasks simultaneously, parallelizing spec tasks, spinning up
  multiple Claude instances, divide-and-conquer workflows. Keywords: parallel, worktrees,
  tmux, multiple claude, concurrent, simultaneous, divide and conquer, spin up.
allowed-tools: Bash, Read, Write
user-invocable: true
---

# Parallel Work Orchestrator

Creates N worktrees under `.claude/worktrees/`, opens tmux panes, and launches Claude sessions in each with different tasks.

## Usage

```
/parallel <count> <spec-or-tasks>
```

Examples:
- `/parallel 3 specs/feature-spec.md` — assigns tasks 1-3 from spec to separate worktrees
- `/parallel 2 "Write tests for auth" "Refactor the API client"` — two explicit tasks
- `/parallel 3` — creates 3 worktrees, asks for task assignments interactively

## Workflow

### 1. Pre-flight Checks

```bash
# Verify git repo
git rev-parse --is-inside-work-tree 2>/dev/null || echo "NOT_A_GIT_REPO"

# Verify tmux is available
command -v tmux >/dev/null 2>&1 || echo "TMUX_NOT_FOUND"

# Verify claude is available
command -v claude >/dev/null 2>&1 || echo "CLAUDE_NOT_FOUND"

# Check if in tmux (needed to create panes)
[ -n "$TMUX" ] || echo "NOT_IN_TMUX"
```

If not in tmux, create a new session first:
```bash
SESSION_NAME="parallel-$(date +%s)"
tmux new-session -d -s "$SESSION_NAME"
```

### 2. Parse Tasks

**From a spec file:** Read the spec and extract numbered tasks/sections. Each task gets its own worktree and Claude session.

**From inline arguments:** Each quoted argument is a separate task.

**Interactive:** Ask the user to describe tasks for each worktree.

### 3. Create Worktrees

For each task (1 to N):

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
WORKTREE_BASE="${REPO_ROOT}/.claude/worktrees"
BRANCH_PREFIX="parallel/$(date +%Y%m%d)"

# Ensure .claude/worktrees/ is gitignored
if ! grep -q '\.claude/worktrees/' "${REPO_ROOT}/.gitignore" 2>/dev/null; then
  echo -e '\n# Git worktrees (parallel branch work)\n.claude/worktrees/' >> "${REPO_ROOT}/.gitignore"
fi

mkdir -p "$WORKTREE_BASE"

# Create worktree with auto-named branch
BRANCH="${BRANCH_PREFIX}/task-${i}"
DIR_NAME="task-${i}"
WORKTREE_PATH="${WORKTREE_BASE}/${DIR_NAME}"

if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  git worktree add "$WORKTREE_PATH" "$BRANCH"
else
  git worktree add -b "$BRANCH" "$WORKTREE_PATH"
fi
```

### 4. Set Up Tmux Layout

```bash
SESSION_NAME="parallel-$(basename "$REPO_ROOT")"

# Create session with first pane pointing at worktree 1
tmux new-session -d -s "$SESSION_NAME" -c "${WORKTREE_BASE}/task-1"

# Add panes for remaining worktrees
for i in $(seq 2 $N); do
  tmux split-window -t "$SESSION_NAME" -c "${WORKTREE_BASE}/task-${i}"
done

# Apply tiled layout for even distribution
tmux select-layout -t "$SESSION_NAME" tiled
```

### 5. Launch Claude in Each Pane

For each pane, send the Claude command with the task prompt:

```bash
# Send claude command to each pane
tmux send-keys -t "${SESSION_NAME}:0.${pane_index}" \
  "claude -p '${TASK_PROMPT}'" Enter
```

If a spec file was provided, include it as context:
```bash
tmux send-keys -t "${SESSION_NAME}:0.${pane_index}" \
  "claude --context '${SPEC_FILE}' -p 'Implement task ${i} from the spec'" Enter
```

### 6. Report

```
Parallel sessions launched!

Session: parallel-myapp
Layout: 3 panes (tiled)

| Pane | Worktree                        | Branch                      | Task                    |
|------|---------------------------------|-----------------------------|-------------------------|
| 0    | .claude/worktrees/task-1        | parallel/20260320/task-1    | Implement auth module   |
| 1    | .claude/worktrees/task-2        | parallel/20260320/task-2    | Write API tests         |
| 2    | .claude/worktrees/task-3        | parallel/20260320/task-3    | Refactor database layer |

Switch to session: tmux attach -t parallel-myapp
Monitor status: /worktree-status
Clean up when done: /worktree-cleanup
```

## Limits

- Maximum 6 parallel worktrees (to avoid resource exhaustion)
- Each Claude session uses its own API context window
- Recommend 3-4 for most machines

## Cleanup

When parallel work is done:
1. `/worktree-status` — check progress
2. Merge branches as needed
3. `/worktree-cleanup` — remove worktrees and prune refs
