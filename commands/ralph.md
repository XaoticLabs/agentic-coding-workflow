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
- `<spec-slug> --once` — one observed autonomous iteration for prompt tuning
- `<spec-slug> --clean-room` — greenfield mode, skip codebase search
- `<spec-slug> --harvest` — extract patterns and conventions after a completed run
- `<spec-slug> --checkpoint-every=N` — pause between iterations for human steering (requires a terminal)
- `<spec-slug> --eval-gates-merge` — require a fresh end-of-run ACCEPT verdict before merge
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
- **--once**: optional, one autonomous iteration in the foreground, then stop
- **--clean-room**: optional, skip codebase search for greenfield work
- **--harvest**: optional, extract patterns after completed run
- **--status**: optional, show dashboard and exit
- **--stop**: optional, create stop sentinel and exit
- **--max N**: optional, max iterations (default 50)
- **--time-budget=N**: optional, max seconds per iteration (default 600, 0 = unlimited)
- **--checkpoint-every=N**: optional, pause between iterations every N iterations when a terminal is available
- **--eval-gates-merge**: optional, require a fresh end-of-run ACCEPT verdict before merge

Keep all option tokens after the slug in a Bash array named `RALPH_ARGS`. Pass them unchanged to `scripts/launch.sh`; its shared parser validates values and combinations. Do not construct flag strings, environment prefixes, or separate per-mode invocations. Both `--option=value` and `--option value` forms are supported for numeric options.

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

### Phase 3: Validate Spec Directory

```bash
SPEC_DIR=".claude/specs/${SLUG}"
```

Verify the spec directory exists. If not:
- Check if a monolithic spec exists at `.claude/specs/${SLUG}-spec.md`
- If monolithic exists but no directory, suggest: "Run `/agentic-coding-workflow:write-spec ${SLUG} --ralph` to generate Ralph-compatible specs"
- If nothing exists, list available specs and exit

### Phase 4: Confirm Launch

For `--plan` or `--harvest`, proceed directly to Phase 5.

Before a build, use AskUserQuestion to confirm the spec, worker count, iteration limit, timeout, checkpoints, and evaluation settings. Explain that Ralph runs Claude autonomously with `--dangerously-skip-permissions`, and stops via `/agentic-coding-workflow:ralph <slug> --stop`.

`--once` runs one autonomous `claude -p` iteration in the foreground. You can observe its progress and inspect its output logs and commits afterward. It cannot ask for test approval during the iteration. For steering between iterations, use `--checkpoint-every=N` in a terminal; without a terminal, checkpoints are logged and execution continues.

### Phase 5: Launch Through the Shared Implementation

Use the same launcher for planning, harvest, foreground, tmux, and parallel execution:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/ralph/scripts/launch.sh" "$SPEC_DIR" "${RALPH_ARGS[@]}"
```

The launcher initializes `.claude/project-commands.json`, preserving overrides, and refreshes `.claude/AGENTS.md`. If no plan exists, it runs one planning iteration before building. `--plan` and `--harvest` run one iteration and exit; `--once` builds once in the foreground. Other builds launch a tmux window or session. `--parallel N` selects the full parallel orchestrator and forwards the same timeout, checkpoint, and evaluation options to its workers and reconciliation loops. Parallel mode is exclusive with `--once`, `--plan`, and `--harvest`. `--no-eval` disables both per-iteration and final evaluation and cannot be combined with `--eval-per-iter` or `--eval-gates-merge`.

For example, these are shell invocations of that same entry point:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/ralph/scripts/launch.sh" "$SPEC_DIR" --once --time-budget=300
bash "${CLAUDE_PLUGIN_ROOT}/skills/ralph/scripts/launch.sh" "$SPEC_DIR" --checkpoint-every=5 --eval-gates-merge
bash "${CLAUDE_PLUGIN_ROOT}/skills/ralph/scripts/launch.sh" "$SPEC_DIR" --parallel 3 --time-budget=300 --eval-gates-merge
```

### Phase 6: Report

For foreground runs, summarize the outcome and point to the logs. For tmux runs, report the session/window (`ralph-<slug>` or `ralph-<slug>-orch`) and how to attach or switch to it.

Include these paths and commands:

- Status: `/agentic-coding-workflow:ralph <slug> --status`
- Stop: `/agentic-coding-workflow:ralph <slug> --stop`
- Steering: write instructions to `.claude/ralph/inject.md`
- Runs: `.claude/ralph/<slug>/runs/` (in the worktree during standalone builds)
- Dashboard: `.claude/ralph/status.md`

Standalone builds preserve their worktree until merge/cleanup decisions finish. Parallel execution handles partitioning, waves, merging, reconciliation, verification, evaluation, and guarded cleanup. Report any preserved work or failed gate from the script output.

## Error Handling

- If tmux is not available, fall back to running loop.sh in the foreground (warn user)
- If Claude CLI is not available, exit with a clear error
- If spec directory is empty, suggest running `/agentic-coding-workflow:write-spec`
- If loop.sh exits with errors on multiple consecutive iterations, suggest checking logs

## Example Usage

```
/agentic-coding-workflow:ralph auth-feature --once
```
One observed autonomous iteration — validate your spec and plan before going AFK.

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
