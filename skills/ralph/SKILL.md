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
user-invocable: false
---

# Ralph Loop Orchestrator

Manages autonomous Claude coding loops. Not user-invocable directly — invoked by the `/ralph` command.

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/loop.sh` | Outer bash loop driving iterations |
| `scripts/generate-agents-md.sh` | Auto-generates `.claude/AGENTS.md` project guide |
| `scripts/partition-tasks.sh` | Partitions tasks into dependency waves for parallel mode |

## Prompt Templates

| Template | Mode | Purpose |
|----------|------|---------|
| `references/PROMPT_build.md` | build | Per-iteration build prompt — pick task, implement, test, commit |
| `references/PROMPT_plan.md` | plan | Planning-only prompt — gap analysis, generate implementation plan |

## Workflow

### Single-Track Mode

1. Generate project guide: `scripts/generate-agents-md.sh`
2. Run loop: `scripts/loop.sh <spec-dir> build [max-iter] [--push]`
3. Each iteration gets a fresh Claude instance with the build prompt
4. Loop exits when plan is complete or stop sentinel is touched

### Planning Mode

1. Run loop: `scripts/loop.sh <spec-dir> plan 1`
2. Single iteration: reads specs, analyzes codebase, generates `IMPLEMENTATION_PLAN.md`

### Parallel Mode

1. Generate project guide: `scripts/generate-agents-md.sh`
2. Partition tasks: `scripts/partition-tasks.sh <plan-file> <N>`
3. Create N worktrees (via `/parallel` skill infrastructure)
4. Run independent `loop.sh` in each worktree with task affinity
5. Monitor with `/ralph <slug> --status`
6. Stop all with `/ralph <slug> --stop`

## Stop Mechanisms

- **Sentinel file:** `touch .claude/ralph-stop` — loop exits after current iteration
- **Plan complete:** When all tasks marked `[x]` and status is COMPLETE
- **Max iterations:** Configurable safety limit (default 50)

## Artifacts

All Ralph artifacts live under `.claude/`:
- `specs/<slug>/IMPLEMENTATION_PLAN.md` — shared state between iterations
- `AGENTS.md` — project operational guide
- `ralph-logs/` — per-iteration output logs
- `ralph-stop` — stop sentinel (touch to stop)
