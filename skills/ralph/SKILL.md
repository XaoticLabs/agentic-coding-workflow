---
name: ralph
description: |
  Autonomous coding loop using Geoffrey Huntley's Ralph methodology. Repeatedly invokes
  Claude with fresh context, using git and files as memory. Each iteration picks one task,
  implements it, tests it, commits, updates the plan, and exits. Backpressure from tests
  and lint ensures quality without human oversight. Includes separated evaluator for
  independent code evaluation and tiered evaluation modes (end-of-run or per-iteration).
  Keywords: ralph, autonomous loop, autonomous coding, auto-implement, headless, unattended,
  batch implement, ralph loop, geoffrey huntley, self-driving, auto-pilot coding, evaluator,
  evaluation.
allowed-tools: Bash, Read, Write, Glob, Grep
effort: medium
user-invocable: false
---

# Ralph Loop Orchestrator

Manages autonomous Claude coding loops. Not user-invocable directly — invoked by the `/agentic-coding-workflow:ralph` command.

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/loop.sh` | Outer bash loop driving iterations (with steering checkpoints and eval-gates-merge) |
| `scripts/notify.sh` | Cross-platform desktop notifications for loop events |
| `scripts/check-overrides-staleness.sh` | Pre-flight check for stale override rules |
| `scripts/validate-alignment.sh` | Pre-flight check for plan-spec criteria alignment |
| `scripts/generate-agents-md.sh` | Initializes `.claude/project-commands.json` (preserving overrides) and generates `.claude/AGENTS.md` |
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
| `references/PROMPT_evaluate.md` | evaluate | Independent code evaluation — grade against spec and plan acceptance criteria, return verdict |
| `references/PROMPT_harvest.md` | harvest | Post-run pattern extraction — analyze diffs, extract conventions |
| `references/PROMPT_resolve.md` | resolve | Merge conflict resolution — resolve markers, test, commit |
| `references/PROMPT_reconcile.md` | reconcile | Post-merge verification — run tests, fix integration issues |

## Evaluation & Meta References

| File | Purpose |
|------|---------|
| `references/evaluation-calibration.md` | Scored examples and LLM code smell catalog for evaluator calibration |
| `references/PROMPT_CHANGELOG.md` | Tracks prompt revisions, intended vs observed behavioral effects, and steering insights |

## Worktree Isolation

All standalone build/reconcile runs create a worktree at `.claude/worktrees/<slug>-<run-id>` on branch `ralph-<slug>/<run-id>`. Run IDs include a timestamp, PID, and random suffix so preserved runs can coexist. This provides:

- **Branch isolation** — Ralph never commits directly to main
- **ORC integration** — ORC auto-discovers the worktree for stop/merge controls
- **Safe rollback** — if Ralph goes sideways, just delete the branch
- **Consistent model** — single-track and parallel mode both use worktrees

Plan and harvest modes run in-place (read-only/analytical, no commits). Parallel workers get their own worktrees from `orchestrate-parallel.sh`.

## Workflow

### Observed Autonomous Iteration (--once)

1. Generate project guide: `scripts/generate-agents-md.sh`
2. Run single iteration: `scripts/loop.sh <spec-dir> build 1 --once`
3. Observe the autonomous `claude -p` run and review its output and commits afterward. There is no interactive approval inside the iteration.
4. Graduate to AFK mode once prompts are tuned

All command launches use `scripts/launch.sh <spec-dir> [options...]`. It shares `scripts/options.sh` with the loop and orchestrator so foreground, tmux, and parallel paths receive the same options.

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

## Evaluator

The evaluator is a separate Claude session that reviews implementation quality independently from the generator. Its value depends on where the task sits relative to what the model can do reliably solo — it's not a fixed yes/no decision.

### End-of-Run Evaluation (default)

Full quality evaluation runs **once at the end of the run** by default, in addition to mandatory integrity review of each committed build iteration:
- Reviews the entire diff from run start to HEAD
- Grades against full spec and plan acceptance criteria
- Produces an advisory quality report (does NOT trigger reverts)
- Human reviews the report before merging
- Disable with `RALPH_EVAL_END_OF_RUN=false`

Single-track completion runs harvest and summary generation while the worktree exists,
then final test/lint verification → end-of-run evaluation → artifact preservation →
merge decision → guarded cleanup. Evaluation always reviews the worktree branch.
Reports, logs, the journal, and a copy of the worktree's `.claude/` artifacts are saved
under the main project's run directory before removal.

This is the recommended mode for current models (Opus 4.6), per the Anthropic harness design findings: tasks within the model's comfort zone don't need per-iteration evaluation.

### Verification Integrity (mandatory)

Every committed build iteration gets a separate read-only review before KEEP, including
workers, `--once`, iterations without a RED commit, and runs with quality evaluation disabled.
The controller captures original specs/plan and verification policy before the builder runs,
keeps the original test/lint commands, and supplies the final diff plus intermediate commit
patches. Nonzero check exits remain failures; `RALPH_GATE_IGNORE` cannot turn them into passes.
Rejected iterations restore ignored acceptance/configuration inputs as well as tracked code.

Follow **Test and Verification Integrity** in `commands/shared-patterns.md`. Protect criteria
and human-approved behavioral expectations, not whole files. Add cases in existing files;
justify and independently review mistaken agent tests or changes that could weaken coverage.
A human-approved expectation needs human approval to change; unattended agents leave it
pending and stop with a proposed correction. Agent-authored RED tests are not human approval,
and separate failing commits are optional unless requested. REVISE rolls back with guidance;
missing/malformed review, errors, or timeout preserve work and stop without acceptance.

These are controller and review safeguards, not an OS security boundary against an agent
with the controller's filesystem/process privileges. Keep the controller and authoritative
CI/acceptance checks outside the builder's write permissions when enforcing against a hostile agent.

### Per-Iteration Quality Evaluation (opt-in)

For tasks at the edge of what the model handles reliably, enable per-iteration evaluation:
- Set `RALPH_EVAL_PER_ITER=true`
- Expands the mandatory integrity review to a full quality review after mechanical gates
- REVISE verdict triggers a revert with guidance saved for next iteration
- Full quality scope triggers when diff touches >= `RALPH_EVAL_DIFF_THRESHOLD` files (default: 5); integrity review always runs

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
| `--once` | One autonomous iteration, foreground; review afterward |
| `--clean-room` | Skip codebase search — greenfield mode |
| `--checkpoint-every=N` | Pause for human steering every N iterations |
| `--eval-gates-merge` | Require a fresh end-of-run ACCEPT verdict before offering a merge |
| `--time-budget=N` | Max seconds per iteration (default 600) |

## Human Steering

### Steering Checkpoints (`--checkpoint-every=N`)

Pauses the loop every N iterations for human input when stdin is a terminal. Without a terminal, it logs the checkpoint and continues. At each checkpoint you can:
- **Continue** (Enter) — resume autonomous execution
- **Stop** (s) — graceful stop at the checkpoint
- **Inject** (i) — opens `inject.md` in your editor for mid-loop steering

This addresses the Knuth/Stappers insight: models need periodic human course-correction,
not just a single `--once` check at the start. Desktop notification fires at each checkpoint.

### Strategic Context

Add a `## Strategic Context` section to `IMPLEMENTATION_PLAN.md` with human-written intent,
constraints, and architectural decisions. Unlike `## Learnings` (machine-written tactical notes),
this section carries the "why" across context boundaries and is fed into every iteration's briefing.

### Eval Gates Merge (`--eval-gates-merge`)

When set, the merge prompt requires a successful end-of-run evaluator pass with an ACCEPT
verdict for the verified HEAD. REVISE, missing or malformed verdicts, evaluator errors or
timeouts, disabled evaluation, and `--once` all leave the gate closed. Per-iteration verdicts
cannot satisfy it. Changes after verification, including while the confirmation prompt is open,
block the merge. The confirmed merge fast-forwards to the verified commit SHA and checks
that the target has not advanced during confirmation. A diverged target requires integration
and fresh verification before merging. The worktree and branch
are preserved for review. A manual `git merge <branch>` bypasses this prompt gate.

### Worktree Preservation

Startup refuses existing paths or branch names instead of replacing them. Automatic cleanup
requires matching run ownership, no active lease/process or tmux pane, unchanged branch
identity, a clean checkout including untracked files, and HEAD reachable from the target.
Cleanup copies and checks `.claude/` artifacts before removing a worktree. Failed checks,
failed merges, and unknown ownership preserve both checkout and branch. Branch deletion
uses `git branch -d`; cleanup never falls back to filesystem deletion.

### Evaluation Results

All evaluation modes use `scripts/evaluate.py`: `ACCEPT`, `REVISE`, `ERROR`, or `NOT_RUN`.
The evaluator has Read, Glob, and Grep under native restricted permissions; it cannot run
shell commands, write source or verdict files, or call MCP tools. The controller supplies
diff/log evidence, validates structured CLI output against the score and evidence contract,
and writes reports bound to the candidate SHA and source fingerprint. Errors preserve work
and return failure. Per-iteration and wave reports retain separate artifact paths.

UI evaluation consumes screenshots and interaction logs captured before final verification.
Set `RALPH_EVAL_UI_EVIDENCE` to a nonempty directory inside the project when
`RALPH_EVALUATE_UI=true`. Missing or changed evidence is ERROR; evaluators do not launch
servers or browsers. Native restricted mode requires Claude Code v2.1.248 or later.

## Pre-Flight Checks

Before the loop starts, two advisory checks run automatically:

1. **Override staleness** — flags rules in `RALPH_OVERRIDES.md` older than 30 days without
   recent journal confirmation. Stale rules silently bias every iteration.
2. **Plan-spec alignment** — validates that acceptance criteria in `IMPLEMENTATION_PLAN.md`
   match the corresponding spec files. Divergence means the evaluator grades against stale criteria.

## Desktop Notifications

The loop sends desktop notifications (macOS/Linux) for critical events:
- Struggle detection (stuck on same task)
- Circuit breaker (soft and hard)
- Evaluator REVISE verdict
- Steering checkpoints
- Loop completion

Disable with `RALPH_NOTIFY=false`. Disable sound with `RALPH_NOTIFY_SOUND=0`.

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
