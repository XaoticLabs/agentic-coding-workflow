---
allowed-tools:
  - Read
  - Glob
  - Grep
  - Write
  - Bash
  - AskUserQuestion
effort: medium
---

# Ralph — Autonomous Coding Loop

Launches Geoffrey Huntley's Ralph loop: autonomous Claude iterations that pick tasks, implement, test, commit, and update the plan — no human in the loop.

## Input

$ARGUMENTS - One of:
- `<spec-slug>` — start autonomous build loop for the named spec
- `<spec-slug> --parallel N` — run N parallel worktrees
- `<spec-slug> --plan` — planning mode only (gap analysis, generate plan)
- `<spec-slug> --once` — single iteration, watched (HITL mode for prompt tuning)
- `<spec-slug> --clean-room` — greenfield mode, skip codebase search
- `<spec-slug> --harvest` — extract patterns and conventions after a completed run
- `<spec-slug> --time-budget=N` — max seconds per iteration (default: 600, 0 = no limit)
- `<spec-slug> --eval-per-iter` — enable per-iteration LLM evaluation (default: end-of-run only)
- `<spec-slug> --no-eval` — disable all LLM evaluation (mechanical gates only)
- `<spec-slug> --status` — show completion dashboard
- `<spec-slug> --stop` — create stop sentinel to halt the loop gracefully

## Instructions

### Phase 1: Parse Arguments

Extract from `$ARGUMENTS`:
- **spec-slug** (required): matches a directory at `.claude/specs/<slug>/`
- **--parallel N**: optional, number of parallel workers (2-6)
- **--plan**: optional, planning-only mode
- **--eval-per-iter**: optional, enable per-iteration LLM evaluation (for edge-of-capability tasks)
- **--no-eval**: optional, disable all LLM evaluation
- **--once**: optional, single iteration then stop (HITL mode)
- **--clean-room**: optional, skip codebase search for greenfield work
- **--harvest**: optional, extract patterns after completed run
- **--status**: optional, show dashboard and exit
- **--stop**: optional, create stop sentinel and exit
- **--max N**: optional, max iterations (default 50)
- **--time-budget=N**: optional, max seconds per iteration (default 600, 0 = unlimited)

### Phase 2: Handle Quick Actions

**If `--stop`:**
```bash
touch .claude/ralph/stop
```
Report that the loop will stop after the current iteration and exit.

**If `--status`:**
First check if `.claude/ralph/status.md` exists — if so, display it (this is the live dashboard updated each iteration with progress, timing, success rate, and recent iterations).

Check orchestrator process status:
- If `.claude/ralph/<slug>/orchestrator.pid` exists, read the PID and check if it's alive: `kill -0 <pid> 2>/dev/null`
- Report: "Orchestrator: RUNNING (PID: <pid>)" or "Orchestrator: NOT RUNNING"
- Check for worker tmux window/session: `tmux has-session -t ralph-<slug> 2>/dev/null || tmux list-windows -F '#{window_name}' | grep -q ralph-<slug>` and report active/inactive
- Check `.claude/ralph/<slug>/runs/` for recent run directories

Also read `.claude/specs/<slug>/IMPLEMENTATION_PLAN.md` and display:
- Overall status (IN_PROGRESS / COMPLETE)
- Task completion count (e.g., "7/12 tasks complete")
- Table of all tasks with status
- Any learnings recorded
- Show persistent journal tail: `tail -10 .claude/ralph/<slug>/journal.tsv`

**If the plan status is COMPLETE**, suggest next steps:
- `/agentic-coding-workflow:review --spec` to review the changes
- `/agentic-coding-workflow:ship` to fill the PR template and create a PR

Exit after displaying.

**If `--harvest`:**
Run the loop in harvest mode (single iteration):

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/ralph/scripts/loop.sh" "$SPEC_DIR" harvest 1
```

This analyzes the completed ralph run, extracts reusable patterns, updates AGENTS.md with discovered conventions, and writes a harvest report to `.claude/ralph-logs/ralph-harvest-<slug>.md`.

Exit after harvesting.

**If `--once`:**
Launch a single iteration in the foreground (not in tmux) for HITL prompt tuning. This lets you watch Ralph work on one task, validate the approach, then decide whether to go AFK.

### Phase 3: Validate Spec Directory

```bash
SPEC_DIR=".claude/specs/${SLUG}"
```

Verify the spec directory exists. If not:
- Check if a monolithic spec exists at `.claude/specs/${SLUG}-spec.md`
- If monolithic exists but no directory, suggest: "Run `/agentic-coding-workflow:write-spec ${SLUG} --ralph` to generate Ralph-compatible specs"
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
If plan was auto-generated because it didn't exist, continue to Phase 5b.

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
> Stop anytime with: `/agentic-coding-workflow:ralph <slug> --stop`
>
> Proceed? (yes/no)

**If `--once` mode**, run in foreground:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/ralph/scripts/loop.sh" "$SPEC_DIR" build 1 --once $CLEAN_ROOM_FLAG
```

Report what happened and suggest next steps: run another `--once`, or drop the flag to go AFK.

**Otherwise, launch in tmux:**

```bash
SESSION_NAME="ralph-${SLUG}"

# Check if already running (as window or session)
ALREADY_RUNNING=false
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  ALREADY_RUNNING=true
elif [ -n "${TMUX:-}" ] && tmux list-windows -F '#{window_name}' 2>/dev/null | grep -q "^${SESSION_NAME}$"; then
  ALREADY_RUNNING=true
fi

if [ "$ALREADY_RUNNING" = true ]; then
  echo "Ralph '$SESSION_NAME' already running!"
  echo "Switch: Ctrl-B n/p (tab) or tmux attach -t $SESSION_NAME (session)"
  echo "Stop: /agentic-coding-workflow:ralph $SLUG --stop"
  exit 0
fi

# Build flag string
FLAGS=""
[ -n "$CLEAN_ROOM_FLAG" ] && FLAGS="$FLAGS --clean-room"
EVAL_ENV=""
[ -n "$EVAL_PER_ITER_FLAG" ] && EVAL_ENV="RALPH_EVAL_PER_ITER=true"
[ -n "$NO_EVAL_FLAG" ] && EVAL_ENV="RALPH_EVAL_END_OF_RUN=false"

# Launch in tmux — window (tab) if already in tmux, new session if not
LOOP_CMD="$EVAL_ENV bash '${CLAUDE_PLUGIN_ROOT}/skills/ralph/scripts/loop.sh' '$SPEC_DIR' build $MAX_ITERATIONS $FLAGS; echo 'Ralph loop finished. Press enter to close.'; read"

if [ -n "$TMUX" ]; then
  tmux new-window -n "$SESSION_NAME" "$LOOP_CMD"
else
  tmux new-session -d -s "$SESSION_NAME" "$LOOP_CMD"
fi
```

Report:
```
Ralph loop launched!

Tab/Session: ralph-<slug>
Worktree:    .claude/worktrees/ralph-<slug>
Branch:      <slug>
Switch:      Ctrl-B n/p (if tab) or tmux attach -t ralph-<slug> (if session)
Status:      /agentic-coding-workflow:ralph <slug> --status
Stop:        /agentic-coding-workflow:ralph <slug> --stop
Steer:       echo 'instructions' > .claude/ralph/inject.md
Run dir:     .claude/ralph/<slug>/runs/ (inside worktree)
Journal:     .claude/ralph/<slug>/journal.tsv
Dashboard:   .claude/ralph/status.md

Changes land on the <slug> branch. Merge via ORC or `git merge <slug>`.
```

### Phase 7: Parallel Mode

**If `--parallel N`:**

1. Verify IMPLEMENTATION_PLAN.md exists (run planning mode if not)

2. Verify N is between 2 and 6

3. Check tmux is available: `command -v tmux >/dev/null 2>&1`

4. Launch the full parallel lifecycle via the orchestrator script. This handles everything automatically: partitioning tasks with file affinity, creating worktrees, launching workers, polling for completion, merging branches, running reconciliation, and cleaning up.

```bash
# Build flag string
FLAGS=""
[ -n "$CLEAN_ROOM_FLAG" ] && FLAGS="$FLAGS --clean-room"

PID_FILE=".claude/ralph/${SLUG}/orchestrator.pid"

# Check if already running via PID file
if [ -f "$PID_FILE" ]; then
  EXISTING_PID=$(cat "$PID_FILE")
  if kill -0 "$EXISTING_PID" 2>/dev/null; then
    echo "Parallel orchestrator already running! (PID: $EXISTING_PID)"
    echo "Status: /agentic-coding-workflow:ralph $SLUG --status"
    echo "Stop:   /agentic-coding-workflow:ralph $SLUG --stop"
    exit 0
  else
    echo "Stale PID file found (process $EXISTING_PID not running). Cleaning up."
    rm -f "$PID_FILE"
  fi
fi

# Launch orchestrator as a detached background process (survives terminal/tmux death)
# Workers still run in tmux for visibility; the orchestrator polls and merges independently
mkdir -p ".claude/ralph/${SLUG}"
nohup bash "${CLAUDE_PLUGIN_ROOT}/skills/ralph/scripts/orchestrate-parallel.sh" \
  "$SPEC_DIR" "$SLUG" $N $MAX_ITERATIONS $FLAGS &
```

5. Report:
```
Ralph parallel orchestrator launched!

PID:       $(cat .claude/ralph/<slug>/orchestrator.pid)
Runs:      .claude/ralph/<slug>/runs/
Journal:   .claude/ralph/<slug>/journal.tsv
Branch:    <slug>
Lifecycle: partition → wave → merge → reconcile → preserve → cleanup (all automatic)

Status:    /agentic-coding-workflow:ralph <slug> --status
Stop:      /agentic-coding-workflow:ralph <slug> --stop
Steer:     echo 'instructions' > .claude/ralph/inject.md
```

The orchestrator runs the full lifecycle automatically:
- **Partition**: Tasks assigned to workers by file affinity (each file owned by one worker)
- **Work**: N workers run in parallel, each in its own worktree and branch
- **Merge**: Worker branches merged sequentially into the target branch (conflicts resolved by Claude)
- **Reconcile**: Post-merge verification loop (max 3 iterations) ensures tests pass on combined code
- **Cleanup**: Worktrees, branches, and temporary files removed

## Error Handling

- If tmux is not available, fall back to running loop.sh in the foreground (warn user)
- If Claude CLI is not available, exit with a clear error
- If spec directory is empty, suggest running `/agentic-coding-workflow:write-spec`
- If loop.sh exits with errors on multiple consecutive iterations, suggest checking logs

## Example Usage

```
/agentic-coding-workflow:ralph auth-feature --once
```
Single watched iteration (HITL mode) — validate your spec and plan before going AFK.

```
/agentic-coding-workflow:ralph auth-feature
```
Launches autonomous loop for `.claude/specs/auth-feature/`.

```
/agentic-coding-workflow:ralph auth-feature --plan
```
Runs planning mode only — generates/refreshes IMPLEMENTATION_PLAN.md.

```
/agentic-coding-workflow:ralph auth-feature --clean-room
```
Greenfield mode — implements from spec only, skips codebase search.

```
/agentic-coding-workflow:ralph auth-feature --parallel 3
```
Launches 3 parallel workers with file affinity. Automatically merges and reconciles when all workers finish.

```
/agentic-coding-workflow:ralph auth-feature --status
```
Shows completion dashboard (live progress, timing, success rate).

```
/agentic-coding-workflow:ralph auth-feature --stop
```
Creates stop sentinel — loop exits after current iteration.

```
/agentic-coding-workflow:ralph auth-feature --eval-per-iter
```
Per-iteration LLM evaluation for edge-of-capability tasks (default: end-of-run only).

```
/agentic-coding-workflow:ralph auth-feature --harvest
```
After completion — extracts reusable patterns and updates AGENTS.md.

### Mid-loop steering

While Ralph is running, write instructions to steer the next iteration:
```bash
echo "Use the existing UserRepository instead of raw SQL queries" > .claude/ralph-inject.md
```
The file is consumed and deleted after the next iteration reads it.
