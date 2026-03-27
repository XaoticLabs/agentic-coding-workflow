---
name: ralph
description: |
  Autonomous coding loop using Geoffrey Huntley's Ralph methodology. Repeatedly invokes
  Claude with fresh context, using git and files as memory. Each iteration picks one task,
  implements it, tests it, commits, updates the plan, and exits. Backpressure from tests
  and lint ensures quality without human oversight. Includes separated evaluator for
  independent code evaluation, sprint contracts for measurable acceptance criteria, and
  tiered evaluation modes (end-of-run or per-iteration). Keywords: ralph, autonomous loop,
  autonomous coding, auto-implement, headless, unattended, batch implement, ralph loop,
  geoffrey huntley, self-driving, auto-pilot coding, evaluator, contracts, evaluation.
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
| `references/PROMPT_contracts.md` | contracts | Sprint contract generation — measurable "done" criteria per task |
| `references/PROMPT_evaluate.md` | evaluate | Independent code evaluation — grade against spec/contracts, return verdict |
| `references/PROMPT_harvest.md` | harvest | Post-run pattern extraction — analyze diffs, extract conventions |
| `references/PROMPT_resolve.md` | resolve | Merge conflict resolution — resolve markers, test, commit |
| `references/PROMPT_reconcile.md` | reconcile | Post-merge verification — run tests, fix integration issues |

## Evaluation & Meta References

| File | Purpose |
|------|---------|
| `references/evaluation-calibration.md` | Scored examples and LLM code smell catalog for evaluator calibration |
| `references/PROMPT_CHANGELOG.md` | Tracks prompt revisions, intended vs observed behavioral effects, and steering insights |

## Worktree Isolation

All build/reconcile mode runs automatically create a git worktree at `.claude/worktrees/<slug>` on branch `<slug>`. This provides:

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

### Contract Generation Mode

1. Run loop: `scripts/loop.sh <spec-dir> contracts 1`
2. Single iteration: reads plan + specs, generates `CONTRACTS.md` with measurable criteria per task
3. Should run after plan mode — contracts define what "done" looks like for each task
4. The evaluator grades against these contracts during build iterations

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

## Evaluator

The evaluator is a separate Claude session that reviews implementation quality independently from the generator. Its value depends on where the task sits relative to what the model can do reliably solo — it's not a fixed yes/no decision.

### End-of-Run Evaluation (default)

By default, the evaluator runs **once at the end of the run**, reviewing the full body of work:
- Reviews the entire diff from run start to HEAD
- Grades against full spec and all contracts
- Produces an advisory quality report (does NOT trigger reverts)
- Human reviews the report before merging
- Disable with `RALPH_EVAL_END_OF_RUN=false`

This is the recommended mode for current models (Opus 4.6), per the Anthropic harness design findings: tasks within the model's comfort zone don't need per-iteration evaluation.

### Per-Iteration Evaluation (opt-in)

For tasks at the edge of what the model handles reliably, enable per-iteration evaluation:
- Set `RALPH_EVAL_PER_ITER=true`
- Evaluator runs after each iteration that passes mechanical gates
- REVISE verdict triggers a revert with guidance saved for next iteration
- Triggers when diff touches >= `RALPH_EVAL_DIFF_THRESHOLD` files (default: 5)

Use this when:
- The task is at the edge of model capability
- Previous runs had high revert rates on similar tasks
- The spec is complex with many interacting requirements

### UI Evaluation (opt-in)

- Set `RALPH_EVALUATE_UI=true` to enable Playwright-based UI testing
- Evaluator starts dev server, navigates pages, tests user flows
- Only useful for web projects with UI components

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
- `ralph-eval-verdict.json` — latest evaluator verdict (JSON, machine-readable)
- `ralph-eval-summary.md` — latest evaluator summary (human-readable)
- `ralph-logs/ralph-summary-<slug>.md` — completion summary with metrics and PR description (auto-generated)
- `ralph-logs/revert-*-reason.txt` — actual error output from gate failures (including evaluator REVISE reasons)
- `ralph-logs/eval-*-*.log` — evaluator iteration logs
- `ralph-logs/injections.log` — audit trail of mid-loop steering injections
- `ralph-parallel-meta.json` — parallel run metadata (slug, workers, target branch)
- `ralph-worker-done-*` — per-worker completion markers (in each worktree)
- `harness-audit-<date>.md` — harness audit reports (from /harness-audit command)
- `specs/<slug>/CONTRACTS.md` — sprint contracts (measurable done criteria per task)
