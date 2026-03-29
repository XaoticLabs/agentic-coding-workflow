---
name: reunify
description: |
  Reunify parallel worktree branches back onto a parent feature branch. Discovers
  worker branches from .claude/worktrees/, analyzes file overlap to determine
  optimal merge order, merges sequentially with test gates after each merge,
  resolves conflicts (via Claude or manual), and verifies the combined implementation
  against the original spec/plan to confirm the full feature is implemented.
  Use when: reunify branches, merge worktrees, combine parallel work, bring
  branches together, finish parallel work, merge workers, reunify workers,
  consolidate branches, merge parallel branches, combine worktree branches,
  converge branches, rejoin parallel work, done with parallel, finish worktrees.
  Keywords: reunify, merge, worktree, parallel, branches, combine, consolidate,
  workers, reconcile, rejoin, converge, reunite.
allowed-tools:
  - Bash
  - Read
  - Grep
  - Glob
  - Agent
  - AskUserQuestion
user-invocable: true
---

# Reunify Parallel Branches

Merges parallel worktree branches back onto the parent feature branch, verifies the combined implementation, and optionally cleans up worktrees.

## Phase 1: Discover Worker Branches

Run the discovery script to find qualifying worktree branches:

```bash
"${CLAUDE_PLUGIN_ROOT}/skills/reunify/scripts/discover-branches.sh"
```

Output is TSV: `name  branch  commits_ahead  dirty_files  claude_active`

Display results as a table. For each branch, show:
- Worktree name
- Branch name
- Commits ahead of parent
- Dirty file count (warn if > 0)
- Whether Claude is still active (warn if yes -- work may be in progress)

**If no qualifying branches found:** Tell the user no worktree branches descend from the current branch. Ask if they want to specify branches manually.

**If any branch has dirty files or an active Claude session:** Warn the user. Use AskUserQuestion to confirm they want to proceed or wait.

**Confirm selection:** Use AskUserQuestion to let the user confirm which branches to reunify (default: all discovered). They may want to exclude some.

## Phase 2: Analyze File Overlap and Merge Order

Run the overlap analysis script with the selected branches:

```bash
"${CLAUDE_PLUGIN_ROOT}/skills/reunify/scripts/analyze-overlap.sh" "<parent-branch>" <branch1> <branch2> ...
```

Display:
- Files changed per branch
- Any overlapping files between branches (potential conflict zones)
- The recommended merge order and why

If there are significant overlaps (>5 shared files between any pair), warn the user that conflicts are likely.

## Phase 3: Save Rollback Point

Before starting merges, save the current HEAD so we can roll back if needed:

```bash
ROLLBACK_SHA=$(git rev-parse HEAD)
echo "$ROLLBACK_SHA" > "${CLAUDE_PROJECT_DIR}/.claude/.reunify-rollback"
```

Tell the user: "Saved rollback point at `<short-sha>`. If anything goes wrong, we can reset to this state."

## Phase 4: Sequential Merge with Test Gates

For each branch in the recommended order:

1. **Merge:** `git merge --no-edit <branch>`
2. **If clean merge:**
   - Detect and run the project's test suite:
     - `mix.exs` present -> `mix test`
     - `pyproject.toml` present -> `pytest` or `python -m pytest`
     - `package.json` with test script -> `npm test`
     - `Makefile` with test target -> `make test`
     - If no test runner detected, skip test gate and warn
   - If tests pass: report success, continue to next branch
   - If tests fail: use AskUserQuestion with options:
     - "Launch Claude to fix the test failures"
     - "I'll fix manually, then tell me to continue"
     - "Abort reunification and rollback"
3. **If merge conflicts:**
   - Show the conflicted files
   - Use AskUserQuestion with options:
     - "Auto-resolve with Claude" -- spawn a subagent with the conflict resolution prompt from `${CLAUDE_PLUGIN_ROOT}/scripts/lib/PROMPT_resolve.md` (shared resolve prompt; falls back to `${CLAUDE_PLUGIN_ROOT}/skills/reunify/references/PROMPT_resolve_conflict.md` if not found)
     - "I'll resolve manually, then tell me to continue"
     - "Skip this branch for now"
     - "Abort reunification and rollback"

**On abort:** Reset to the saved rollback point:
```bash
git reset --hard $(cat "${CLAUDE_PROJECT_DIR}/.claude/.reunify-rollback")
```

Report progress after each merge: "Merged 2/4 branches. Next: <branch-name>"

## Phase 5: Final Verification

After all branches are merged, verify the full feature is implemented.

**Find the spec/plan:**
- Check `.claude/specs/` for files matching the current branch name/slug
- Check `.claude/plans/` similarly
- If multiple candidates, ask the user to pick
- If none found, use AskUserQuestion: "No spec found. Please provide a spec path, or describe what the full feature should do."

**Run verification using the review-implementation approach:**

Spawn a subagent (Agent tool) with this task:
> Review the current state of the codebase on this branch against the spec/plan at `<path>`. For each acceptance criterion, verify whether it is implemented. Report PASS/FAIL/PARTIAL for each criterion. Also run the full test suite and report results. Output a structured compliance summary.

Display the compliance summary. If any criteria are FAIL or PARTIAL:
- List the gaps clearly
- Use AskUserQuestion: "Some acceptance criteria are not fully met. Would you like to address these now, or proceed as-is?"

## Phase 6: Cleanup (Optional)

Use AskUserQuestion: "Reunification complete. Want me to clean up the worktrees?"

If yes, for each merged worktree:
```bash
git worktree remove <worktree-path>
git branch -d <branch>
```
Then: `git worktree prune`

Remove the rollback file:
```bash
rm -f "${CLAUDE_PROJECT_DIR}/.claude/.reunify-rollback"
```

## Phase 7: Report

Generate a summary report to `.claude/reunify-report.md`:

```markdown
# Reunification Report

**Date:** <date>
**Parent Branch:** <branch>
**Branches Merged:** <count>

## Merge Results

| Order | Branch | Result | Conflicts | Tests |
|-------|--------|--------|-----------|-------|
| 1 | <name> | Clean | 0 | PASS |
| 2 | <name> | Resolved | 3 files | PASS |

## Spec Compliance

| Criterion | Status |
|-----------|--------|
| <criterion> | PASS/FAIL/PARTIAL |

## Issues Encountered
- <any conflicts, test failures, or gaps>

## Worktree Cleanup
- <cleaned up / skipped>
```

Report the path to the user.

## Error Handling

- If `git merge` fails for a non-conflict reason (e.g., branch doesn't exist), skip that branch and warn
- If test detection fails, skip test gates but warn clearly
- If the rollback file is missing when needed, use `git reflog` to find the pre-merge state
- All script failures should be caught and reported, never silently swallowed
