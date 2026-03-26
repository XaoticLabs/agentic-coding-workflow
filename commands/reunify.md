---
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
  - Agent
  - AskUserQuestion
effort: medium
---

# Reunify Parallel Branches

Merges parallel worktree branches back onto the current feature branch, runs tests after each merge, resolves conflicts, and verifies the combined implementation against the spec/plan.

## Input

$ARGUMENTS - Options:
- Empty -- discovers worktree branches automatically from `.claude/worktrees/`
- Branch names (space-separated) -- merge specific branches instead of auto-discovering
- `--skip-tests` -- skip test gates between merges (faster but riskier)
- `--skip-verify` -- skip final spec compliance verification

## Instructions

Execute the `/agentic-coding-workflow:reunify` skill with the provided arguments.

## Example Usage

```
/agentic-coding-workflow:reunify
```
Auto-discovers and reunifies all worktree branches onto the current feature branch.

```
/agentic-coding-workflow:reunify feature/auth-worker-1 feature/auth-worker-2
```
Reunifies specific branches.

```
/agentic-coding-workflow:reunify --skip-tests
```
Reunifies all discovered branches, only running tests after the final merge.
