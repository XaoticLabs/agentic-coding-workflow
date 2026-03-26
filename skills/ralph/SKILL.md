---
name: ralph
description: |
  Autonomous coding loop using Geoffrey Huntley's Ralph methodology. Repeatedly invokes
  Claude with fresh context, using git and files as memory. Each iteration picks one task,
  implements it, tests it, commits, updates the plan, and exits. Backpressure from tests
  and lint ensures quality without human oversight. Keywords: ralph, autonomous loop,
  autonomous coding, auto-implement, headless, unattended, batch implement, ralph loop,
  geoffrey huntley, self-driving, auto-pilot coding.
allowed-tools: Bash, Read, Write, Glob, Grep
effort: medium
user-invocable: false
---

# Ralph Loop Orchestrator

Manages autonomous Claude coding loops. Not user-invocable directly — invoked by the `/agentic-coding-workflow:ralph` command.

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/loop.sh` | Outer bash loop driving iterations |
| `scripts/generate-agents-md.sh` | Auto-generates `.claude/AGENTS.md` project guide |
| `scripts/generate-briefing.sh` | Per-iteration context briefing with revert details and trends |
| `scripts/generate-summary.sh` | Completion summary with metrics and PR description |
| `scripts/generate-metrics.sh` | Trend analysis from journal: failure rates, hot files, patterns |
| `scripts/partition-tasks.sh` | Partitions tasks with file-affinity assignment for parallel mode |
| `scripts/orchestrate-parallel.sh` | Full parallel lifecycle: launch, poll, merge, reconcile, cleanup |
| `scripts/merge-workers.sh` | Sequential merge of worker branches with conflict resolution |

## Prompt Templates

| Template | Mode | Purpose |
|----------|------|---------|
| `references/PROMPT_build.md` | build | Per-iteration build prompt — pick task, implement, test, commit |
| `references/PROMPT_plan.md` | plan | Planning-only prompt — gap analysis, generate implementation plan |
| `references/PROMPT_harvest.md` | harvest | Post-run pattern extraction — analyze diffs, extract conventions |
| `references/PROMPT_resolve.md` | resolve | Merge conflict resolution — resolve markers, test, commit |
| `references/PROMPT_reconcile.md` | reconcile | Post-merge verification — run tests, fix integration issues |

## Worktree Isolation

All build/reconcile mode runs automatically create a git worktree at `.claude/worktrees/ralph-<slug>` on branch `ralph/<slug>`. This provides:

- **Branch isolation** — Ralph never commits directly to main
- **ORC integration** — ORC auto-discovers the worktree for stop/merge controls
- **Safe rollback** — if Ralph goes sideways, just delete the branch
- **Consistent model** — single-track and parallel mode both use worktrees

Plan and harvest modes run in-place (read-only/analytical, no commits). Parallel workers get their own worktrees from `orchestrate-parallel.sh`.

## Workflow

### HITL Mode (--once)

1. Generate project guide: `scripts/generate-agents-md.sh`
2. Run single iteration: `scripts/loop.sh <spec-dir> build 1 --once`
3. Watch Ralph work on one task, validate approach
4. Graduate to AFK mode once prompts are tuned

### Single-Track Mode (AFK)

1. Generate project guide: `scripts/generate-agents-md.sh`
2. Run loop: `scripts/loop.sh <spec-dir> build [max-iter] [flags...]`
3. Each iteration gets a fresh Claude instance with the build prompt
4. Loop exits when plan is complete, stop sentinel is touched, or safety triggers fire

### Planning Mode

1. Run loop: `scripts/loop.sh <spec-dir> plan 1`
2. Single iteration: reads specs, analyzes codebase, generates `IMPLEMENTATION_PLAN.md`

### Harvest Mode

1. **Auto-runs on completion** — harvest runs automatically when the plan reaches COMPLETE or a circuit breaker fires. Disable with `AUTO_HARVEST=false`.
2. Can also be run manually: `scripts/loop.sh <spec-dir> harvest 1`
3. Analyzes git history, learnings, and diffs to extract reusable patterns
4. Updates AGENTS.md with discovered conventions
5. Writes/updates RALPH_OVERRIDES.md with dated rules (stale rules >30 days are pruned on next harvest)

### Parallel Mode (fully automatic lifecycle)

1. Generate project guide: `scripts/generate-agents-md.sh`
2. Launch orchestrator: `scripts/orchestrate-parallel.sh <spec-dir> <slug> <N> <max-iter>`
3. Orchestrator handles the full lifecycle automatically:
   - **Partition**: `partition-tasks.sh` assigns tasks by file affinity (each file owned by one worker)
   - **Work**: N workers run `loop.sh` in separate worktrees/branches via tmux
   - **Poll**: Orchestrator checks for worker completion markers every 30s
   - **Merge**: `merge-workers.sh` merges branches sequentially (conflicts resolved by Claude via `PROMPT_resolve.md`)
   - **Reconcile**: `loop.sh reconcile` runs post-merge verification (max 3 iterations, uses `PROMPT_reconcile.md`)
   - **Cleanup**: Worktrees, branches, and temp files removed
4. Monitor with `/agentic-coding-workflow:ralph <slug> --status` (shows current phase: working/merging/reconciling/done)
5. Stop with `/agentic-coding-workflow:ralph <slug> --stop`

## Flags

| Flag | Purpose |
|------|---------|
| `--once` | Single iteration, foreground (HITL mode) |
| `--clean-room` | Skip codebase search — greenfield mode |

## Stop Mechanisms

- **Sentinel file:** `touch .claude/ralph-stop` — loop exits after current iteration
- **Plan complete:** When all tasks marked `[x]` and status is COMPLETE
- **Max iterations:** Configurable safety limit (default 50)
- **Struggle detection:** Auto-stops after 3 failed attempts on the same task
- **Circuit breaker (tiered):** Soft warning at <30% commit ratio; hard stop if also 3+ consecutive reverts on different tasks
- **Diff size gate:** Reverts iterations that touch more than 20 files (configurable via RALPH_MAX_DIFF_FILES)

## Mid-Loop Steering

Write instructions to `.claude/ralph-inject.md` — consumed by the next iteration and deleted. Lets you course-correct without stopping the loop.

## Artifacts

All Ralph artifacts live under `.claude/`:
- `specs/<slug>/IMPLEMENTATION_PLAN.md` — shared state between iterations
- `AGENTS.md` — project operational guide
- `ralph-logs/` — per-iteration output logs + `ralph-iterations.log` summary
- `ralph-status.md` — live progress dashboard (updated each iteration)
- `ralph-progress.md` — ephemeral session scratchpad (cleaned up on completion)
- `ralph-inject.md` — mid-loop steering file (consumed and deleted)
- `ralph-logs/ralph-harvest-<slug>.md` — pattern extraction report (from harvest mode)
- `ralph-stop` — stop sentinel (touch to stop)
- `ralph-logs/ralph-summary-<slug>.md` — completion summary with metrics and PR description (auto-generated)
- `ralph-logs/revert-*-reason.txt` — actual error output from gate failures
- `ralph-logs/injections.log` — audit trail of mid-loop steering injections
- `ralph-parallel-meta.json` — parallel run metadata (slug, workers, target branch)
- `ralph-worker-done-*` — per-worker completion markers (in each worktree)
