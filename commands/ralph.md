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
- `<spec-slug> --once` — single iteration, watched (HITL mode for prompt tuning)
- `<spec-slug> --clean-room` — greenfield mode, skip codebase search
- `<spec-slug> --harvest` — extract patterns and conventions after a completed run
- `<spec-slug> --pr` — auto-create/update a draft PR (requires --push)
- `<spec-slug> --status` — show completion dashboard
- `<spec-slug> --stop` — create stop sentinel to halt the loop gracefully

## Instructions

### Phase 1: Parse Arguments

Extract from `$ARGUMENTS`:
- **spec-slug** (required): matches a directory at `.claude/specs/<slug>/`
- **--parallel N**: optional, number of parallel workers (2-6)
- **--plan**: optional, planning-only mode
- **--once**: optional, single iteration then stop (HITL mode)
- **--clean-room**: optional, skip codebase search for greenfield work
- **--harvest**: optional, extract patterns after completed run
- **--pr**: optional, auto-create draft PR (requires --push)
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
First check if `.claude/ralph-status.md` exists — if so, display it (this is the live dashboard updated each iteration with progress, timing, success rate, and recent iterations).

Also read `.claude/specs/<slug>/IMPLEMENTATION_PLAN.md` and display:
- Overall status (IN_PROGRESS / COMPLETE)
- Task completion count (e.g., "7/12 tasks complete")
- Table of all tasks with status
- Any learnings recorded
- Check for running tmux sessions: `tmux list-sessions 2>/dev/null | grep ralph`
- Check ralph-logs for recent activity

Exit after displaying.

**If `--harvest`:**
Run the loop in harvest mode (single iteration):

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/ralph/scripts/loop.sh" "$SPEC_DIR" harvest 1
```

This analyzes the completed ralph run, extracts reusable patterns, updates AGENTS.md with discovered conventions, and writes a harvest report to `.claude/ralph-harvest-<slug>.md`.

Exit after harvesting.

**If `--once`:**
Launch a single iteration in the foreground (not in tmux) for HITL prompt tuning. This lets you watch Ralph work on one task, validate the approach, then decide whether to go AFK.

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

**If `--once` mode**, run in foreground:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/ralph/scripts/loop.sh" "$SPEC_DIR" build 1 --once $CLEAN_ROOM_FLAG
```

Report what happened and suggest next steps: run another `--once`, or drop the flag to go AFK.

**Otherwise, launch in tmux:**

```bash
SESSION_NAME="ralph-${SLUG}"

# Check if session already exists
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  echo "Ralph session '$SESSION_NAME' already running!"
  echo "Attach: tmux attach -t $SESSION_NAME"
  echo "Stop: /ralph $SLUG --stop"
  exit 0
fi

# Build flag string
FLAGS=""
[ -n "$PUSH_FLAG" ] && FLAGS="$FLAGS --push"
[ -n "$CLEAN_ROOM_FLAG" ] && FLAGS="$FLAGS --clean-room"
[ -n "$PR_FLAG" ] && FLAGS="$FLAGS --pr"

# Launch in new tmux session
tmux new-session -d -s "$SESSION_NAME" \
  "bash '${CLAUDE_PLUGIN_ROOT}/skills/ralph/scripts/loop.sh' '$SPEC_DIR' build $MAX_ITERATIONS $FLAGS; echo 'Ralph loop finished. Press enter to close.'; read"
```

Report:
```
Ralph loop launched!

Session:  ralph-<slug>
Attach:   tmux attach -t ralph-<slug>
Status:   /ralph <slug> --status
Stop:     /ralph <slug> --stop
Steer:    echo 'instructions' > .claude/ralph-inject.md
Logs:     .claude/ralph-logs/
Dashboard: .claude/ralph-status.md
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
[ -n "$PUSH_FLAG" ] && FLAGS="$FLAGS --push"
[ -n "$CLEAN_ROOM_FLAG" ] && FLAGS="$FLAGS --clean-room"
[ -n "$PR_FLAG" ] && FLAGS="$FLAGS --pr"

SESSION_NAME="ralph-${SLUG}-orchestrator"

# Check if already running
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  echo "Parallel orchestrator already running!"
  echo "Attach: tmux attach -t $SESSION_NAME"
  echo "Status: /ralph $SLUG --status"
  echo "Stop: /ralph $SLUG --stop"
  exit 0
fi

# Launch orchestrator in tmux (it manages worker tmux sessions internally)
tmux new-session -d -s "$SESSION_NAME" \
  "bash '${CLAUDE_PLUGIN_ROOT}/skills/ralph/scripts/orchestrate-parallel.sh' '$SPEC_DIR' '$SLUG' $N $MAX_ITERATIONS $FLAGS; echo 'Orchestrator finished. Press enter to close.'; read"
```

5. Report:
```
Ralph parallel orchestrator launched!

Session:   ralph-<slug>-orchestrator
Workers:   N
Lifecycle: partition → work → merge → reconcile → cleanup (all automatic)

Attach:    tmux attach -t ralph-<slug>-orchestrator
Status:    /ralph <slug> --status
Stop:      /ralph <slug> --stop
Steer:     echo 'instructions' > .claude/ralph-inject.md
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
- If spec directory is empty, suggest running `/write-spec`
- If loop.sh exits with errors on multiple consecutive iterations, suggest checking logs

## Example Usage

```
/ralph auth-feature --once
```
Single watched iteration (HITL mode) — validate your spec and plan before going AFK.

```
/ralph auth-feature
```
Launches autonomous loop for `.claude/specs/auth-feature/`.

```
/ralph auth-feature --plan
```
Runs planning mode only — generates/refreshes IMPLEMENTATION_PLAN.md.

```
/ralph auth-feature --clean-room
```
Greenfield mode — implements from spec only, skips codebase search.

```
/ralph auth-feature --push --pr
```
Launches loop that pushes after each commit and creates a draft PR.

```
/ralph auth-feature --parallel 3
```
Launches 3 parallel workers with file affinity. Automatically merges and reconciles when all workers finish.

```
/ralph auth-feature --status
```
Shows completion dashboard (live progress, timing, success rate).

```
/ralph auth-feature --stop
```
Creates stop sentinel — loop exits after current iteration.

```
/ralph auth-feature --harvest
```
After completion — extracts reusable patterns and updates AGENTS.md.

### Mid-loop steering

While Ralph is running, write instructions to steer the next iteration:
```bash
echo "Use the existing UserRepository instead of raw SQL queries" > .claude/ralph-inject.md
```
The file is consumed and deleted after the next iteration reads it.
