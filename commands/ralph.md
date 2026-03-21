---
allowed-tools:
  - Read
  - Glob
  - Grep
  - Write
  - Bash
  - AskUserQuestion
---

# Ralph — Autonomous Coding Loop

Launches Geoffrey Huntley's Ralph loop: autonomous Claude iterations that pick tasks, implement, test, commit, and update the plan — no human in the loop.

## Input

$ARGUMENTS - One of:
- `<spec-slug>` — start autonomous build loop for the named spec
- `<spec-slug> --parallel N` — run N parallel worktrees
- `<spec-slug> --plan` — planning mode only (gap analysis, generate plan)
- `<spec-slug> --status` — show completion dashboard
- `<spec-slug> --stop` — create stop sentinel to halt the loop gracefully

## Instructions

### Phase 1: Parse Arguments

Extract from `$ARGUMENTS`:
- **spec-slug** (required): matches a directory at `.claude/specs/<slug>/`
- **--parallel N**: optional, number of parallel workers (2-6)
- **--plan**: optional, planning-only mode
- **--status**: optional, show dashboard and exit
- **--stop**: optional, create stop sentinel and exit
- **--push**: optional, push after each commit
- **--max N**: optional, max iterations (default 50)

### Phase 2: Handle Quick Actions

**If `--stop`:**
```bash
touch .claude/ralph-stop
```
Report that the loop will stop after the current iteration and exit.

**If `--status`:**
Read `.claude/specs/<slug>/IMPLEMENTATION_PLAN.md` and display:
- Overall status (IN_PROGRESS / COMPLETE)
- Task completion count (e.g., "7/12 tasks complete")
- Table of all tasks with status
- Any learnings recorded
- Check for running tmux sessions: `tmux list-sessions 2>/dev/null | grep ralph`
- Check ralph-logs for recent activity

Exit after displaying.

### Phase 3: Validate Spec Directory

```bash
SPEC_DIR=".claude/specs/${SLUG}"
```

Verify the spec directory exists. If not:
- Check if a monolithic spec exists at `.claude/specs/${SLUG}-spec.md`
- If monolithic exists but no directory, suggest: "Run `/write-spec ${SLUG} --ralph` to generate Ralph-compatible specs"
- If nothing exists, list available specs and exit

### Phase 4: Generate Project Guide

Run the agents generator to ensure `.claude/AGENTS.md` is current:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/ralph/scripts/generate-agents-md.sh"
```

If it detects "Unknown" project type, warn the user and suggest manually editing `.claude/AGENTS.md`.

### Phase 5: Planning Mode

**If `--plan` or no `IMPLEMENTATION_PLAN.md` exists:**

Run the loop in planning mode (single iteration):

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/ralph/scripts/loop.sh" "$SPEC_DIR" plan 1
```

If `--plan` was explicitly requested, exit after planning.
If plan was auto-generated because it didn't exist, continue to Phase 6.

### Phase 6: Launch Loop

**Confirm with user before launching:**

Use AskUserQuestion:
> Ready to launch Ralph loop.
>
> - Spec: `<slug>`
> - Tasks: N incomplete (M total)
> - Mode: build
> - Max iterations: N
>
> This will run Claude autonomously with `--dangerously-skip-permissions`.
> Each iteration picks one task, implements it, tests it, and commits.
>
> Stop anytime with: `/ralph <slug> --stop`
>
> Proceed? (yes/no)

**If confirmed, launch in tmux:**

```bash
SESSION_NAME="ralph-${SLUG}"

# Check if session already exists
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  echo "Ralph session '$SESSION_NAME' already running!"
  echo "Attach: tmux attach -t $SESSION_NAME"
  echo "Stop: /ralph $SLUG --stop"
  exit 0
fi

# Launch in new tmux session
tmux new-session -d -s "$SESSION_NAME" \
  "bash '${CLAUDE_PLUGIN_ROOT}/skills/ralph/scripts/loop.sh' '$SPEC_DIR' build $MAX_ITERATIONS $PUSH_FLAG; echo 'Ralph loop finished. Press enter to close.'; read"
```

Report:
```
Ralph loop launched!

Session:  ralph-<slug>
Attach:   tmux attach -t ralph-<slug>
Status:   /ralph <slug> --status
Stop:     /ralph <slug> --stop
Logs:     .claude/ralph-logs/
```

### Phase 7: Parallel Mode

**If `--parallel N`:**

1. Verify IMPLEMENTATION_PLAN.md exists (run planning mode if not)

2. Partition tasks:
```bash
PARTITION=$(bash "${CLAUDE_PLUGIN_ROOT}/skills/ralph/scripts/partition-tasks.sh" "$SPEC_DIR/IMPLEMENTATION_PLAN.md" $N)
```

3. For each worker (0 to N-1), create a worktree and launch a loop:

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
WORKTREE_BASE="${REPO_ROOT}/.claude/worktrees"
BRANCH_PREFIX="ralph/${SLUG}"

mkdir -p "$WORKTREE_BASE"

for i in $(seq 0 $((N-1))); do
  BRANCH="${BRANCH_PREFIX}/worker-${i}"
  WORKTREE_PATH="${WORKTREE_BASE}/ralph-${SLUG}-worker-${i}"

  if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
    git worktree add "$WORKTREE_PATH" "$BRANCH"
  else
    git worktree add -b "$BRANCH" "$WORKTREE_PATH"
  fi

  # Copy spec directory to worktree
  cp -r "$SPEC_DIR" "${WORKTREE_PATH}/.claude/specs/${SLUG}/"

  # Launch loop in tmux pane
  SESSION_NAME="ralph-${SLUG}"
  if [ "$i" -eq 0 ]; then
    tmux new-session -d -s "$SESSION_NAME" -c "$WORKTREE_PATH" \
      "CLAUDE_PROJECT_DIR='$WORKTREE_PATH' bash '${CLAUDE_PLUGIN_ROOT}/skills/ralph/scripts/loop.sh' '.claude/specs/${SLUG}' build $MAX_ITERATIONS"
  else
    tmux split-window -t "$SESSION_NAME" -c "$WORKTREE_PATH" \
      "CLAUDE_PROJECT_DIR='$WORKTREE_PATH' bash '${CLAUDE_PLUGIN_ROOT}/skills/ralph/scripts/loop.sh' '.claude/specs/${SLUG}' build $MAX_ITERATIONS"
  fi
done

tmux select-layout -t "$SESSION_NAME" tiled
```

4. Report the parallel launch with worker assignments and worktree paths.

## Error Handling

- If tmux is not available, fall back to running loop.sh in the foreground (warn user)
- If Claude CLI is not available, exit with a clear error
- If spec directory is empty, suggest running `/write-spec`
- If loop.sh exits with errors on multiple consecutive iterations, suggest checking logs

## Example Usage

```
/ralph auth-feature
```
Launches autonomous loop for `.claude/specs/auth-feature/`.

```
/ralph auth-feature --plan
```
Runs planning mode only — generates/refreshes IMPLEMENTATION_PLAN.md.

```
/ralph auth-feature --parallel 3
```
Launches 3 parallel workers in separate worktrees.

```
/ralph auth-feature --status
```
Shows completion dashboard.

```
/ralph auth-feature --stop
```
Creates stop sentinel — loop exits after current iteration.
