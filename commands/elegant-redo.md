---
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - Write
  - Edit
  - AskUserQuestion
  - EnterPlanMode
  - ExitPlanMode
effort: high
---

# Elegant Redo — Scrap and Reimplement with Hindsight

Checkpoints the current implementation state, re-enters plan mode with full knowledge of what worked and what didn't, and reimplements from scratch with accumulated insight.

"Knowing everything you know now, scrap this and implement the elegant solution."

## Input

$ARGUMENTS - Either:
- Empty — redoes all uncommitted changes
- A file path or glob (e.g., `lib/accounts/auth.ex`) — redoes only the specified scope
- A quoted instruction (e.g., `"focus on the database layer"`) — guides which aspect to redo

## Instructions

### Phase 1: Capture Current State

**Save a checkpoint of the current implementation:**

```bash
# Create checkpoint directory
mkdir -p .claude/checkpoints

# Generate timestamp-based checkpoint name
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
CHECKPOINT_DIR=".claude/checkpoints/pre-redo-${TIMESTAMP}"
mkdir -p "${CHECKPOINT_DIR}"

# Save current diff (staged + unstaged)
git diff HEAD > "${CHECKPOINT_DIR}/full.diff"

# Save list of changed files
git diff HEAD --name-only > "${CHECKPOINT_DIR}/changed-files.txt"

# Save any untracked files list
git ls-files --others --exclude-standard > "${CHECKPOINT_DIR}/untracked-files.txt"
```

**Document what exists:**
- Read all currently changed files
- Understand the current approach — what was built and how
- Note what works well (keep these patterns)
- Note what feels wrong, overcomplicated, or fragile

### Phase 2: Hindsight Analysis (Plan Mode)

**Enter Plan Mode:** Call `EnterPlanMode`

**Conduct a retrospective on the current implementation:**

Analyze the current code and answer these questions:

1. **What did we learn?**
   - What assumptions turned out to be wrong?
   - What was harder than expected? What was easier?
   - What patterns from the codebase did we discover along the way?

2. **What's wrong with the current approach?**
   - Where is there unnecessary complexity?
   - Where did we over-engineer or under-engineer?
   - What's fragile or hard to test?
   - What doesn't fit the existing codebase patterns?

3. **What would the elegant solution look like?**
   - If we started fresh with everything we know now, what would we do differently?
   - What's the simplest approach that handles all the edge cases?
   - What existing patterns/abstractions should we leverage that we missed the first time?

**Present the analysis to the user** via AskUserQuestion:

> Here's what I learned from the first attempt:
>
> **Worked well:** [list]
> **Didn't work:** [list]
> **Proposed elegant approach:** [description]
>
> Should I proceed with this approach, or do you want to adjust?

**Iterate on the plan** — take user feedback and refine the approach.

### Phase 3: Clean Slate

**Once the user approves the new approach:**

Call `ExitPlanMode`

**Revert the working changes:**

```bash
# Stash everything (including untracked) for safety
git stash push -u -m "pre-elegant-redo-${TIMESTAMP}"
```

Inform the user: "Previous implementation stashed as `pre-elegant-redo-[timestamp]`. You can recover it with `git stash pop` if needed."

### Phase 4: Elegant Reimplementation

**Implement the refined solution from scratch.**

Apply everything learned:
- Use the patterns and abstractions identified in the hindsight analysis
- Keep what worked from the first attempt (don't reinvent what was already good)
- Eliminate the complexity that was identified as unnecessary
- Follow existing codebase conventions discovered during the first pass

**Implementation guidance:**
- If `$ARGUMENTS` specified a scope, only redo that scope
- If `$ARGUMENTS` included a quoted instruction, use that to guide focus
- Write tests alongside the implementation (lessons from first attempt inform what to test)
- Keep it simple — the whole point is elegance, not feature creep

### Phase 5: Comparison Report

After reimplementation, generate a comparison:

```markdown
## Elegant Redo Complete

### What Changed
| Aspect | Before | After |
|--------|--------|-------|
| Files changed | [count] | [count] |
| Lines added | [count] | [count] |
| Lines removed | [count] | [count] |
| Complexity | [assessment] | [assessment] |

### Key Improvements
- [Improvement 1: what was simplified and why]
- [Improvement 2: what pattern was adopted]
- [Improvement 3: what was eliminated]

### What Stayed the Same
- [Good pattern preserved from first attempt]

### Recovery
Previous implementation saved as:
- Stash: `git stash list` to find `pre-elegant-redo-[timestamp]`
- Diff: `.claude/checkpoints/pre-redo-[timestamp]/full.diff`
```

## Error Handling

- If there are no changes to redo, inform the user and exit
- If git stash fails, fall back to saving the diff and warn the user to manually revert
- If the user wants to abort mid-redo, remind them of the stash location
- If the reimplementation runs into the same issues, acknowledge it — sometimes the first approach was actually right

## Important Constraints

- **Always checkpoint first** — never destroy work without a recovery path
- **The plan phase is mandatory** — don't skip straight to reimplementation
- **Keep the good parts** — this isn't about starting from absolute zero, it's about applying hindsight
- **Be honest about trade-offs** — if the redo isn't clearly better, say so
- **Don't gold-plate** — elegant means simple and clean, not over-engineered
- **Respect scope** — if the user scoped the redo, don't expand beyond it

## Example Usage

```
/agentic-coding-workflow:elegant-redo
```
Checkpoint everything, analyze the full implementation, and redo from scratch.

```
/agentic-coding-workflow:elegant-redo lib/accounts/auth.ex
```
Only redo the auth module — keep everything else as-is.

```
/agentic-coding-workflow:elegant-redo "focus on the database layer, the API layer was fine"
```
Redo with guidance on what specifically needs rethinking.
