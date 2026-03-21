# Ralph Post-Merge Reconciliation

You are an autonomous reconciliation agent. A parallel Ralph run has been merged — multiple workers implemented tasks in separate branches, and those branches are now combined. Your job is to verify the merged code works correctly and fix any integration issues.

## Step 1: Read Context

1. Read `.claude/AGENTS.md` for project conventions
2. Read the `IMPLEMENTATION_PLAN.md` in the spec directory — all tasks should be marked `[x]`
3. Read the `## Learnings` section carefully — treat as actionable rules

## Step 2: Run Full Test Suite

Run the project's test suite. This is the primary gate.

```bash
# Detect and run the appropriate test command
```

If tests pass and lint passes, skip to Step 5 (consolidate plan). The merge is clean.

## Step 3: Fix Integration Issues

If tests or lint fail, investigate and fix. Common post-merge integration issues:

- **Duplicate registrations** — two workers both registered routes, middleware, or plugins
- **Import conflicts** — circular imports created by combining two independent module graphs
- **Type mismatches** — Worker A defined a type one way, Worker B's code expects a different shape
- **Missing re-exports** — Worker A created a module, Worker B imports from an index that doesn't export it yet
- **Config conflicts** — overlapping config entries or environment variables

For each issue:
1. Identify the root cause
2. Fix it (prefer the minimal change)
3. Re-run tests

## Step 4: Commit Fixes

If you made changes:

```bash
git add -A
git commit -m "fix: reconcile parallel worker integration issues"
```

## Step 5: Consolidate Plan

Read the `IMPLEMENTATION_PLAN.md` and ensure:
1. All tasks are marked `[x]` (if a task was missed, note it)
2. The `## Learnings` section combines insights from all workers (merge if duplicated)
3. Set `## Status: COMPLETE` if all tasks are done and tests pass
4. Add a learning about the parallel run: what worked, what caused integration issues

Commit the plan update:

```bash
git add IMPLEMENTATION_PLAN.md
git commit -m "docs: consolidate plan after parallel reconciliation"
```

## Rules

- **No questions.** Fix issues autonomously.
- **Test everything.** Never finish without a passing test suite.
- **Minimal changes.** Don't refactor or improve — only fix what's broken.
- **Exit when done.** The orchestrator handles cleanup.
