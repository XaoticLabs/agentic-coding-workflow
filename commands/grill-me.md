---
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - AskUserQuestion
  - Agent
effort: medium
---

# Grill Me — Edge Case & Design Decision Quiz

Reviews your staged/unstaged changes, generates tough questions about edge cases and design decisions, and only lets you proceed to PR creation after you demonstrate understanding.

## Input

$ARGUMENTS - Either:
- Empty — reviews all staged + unstaged changes
- A file path or glob (e.g., `lib/accounts/**`) — reviews only matching changes
- `--strict` flag — requires answering ALL questions correctly (no partial credit)

## Instructions

### Phase 1: Gather Changes

**Identify what to review:**

```bash
# Staged changes
git diff --cached --name-only

# Unstaged changes
git diff --name-only

# If on a branch, all changes vs main
git diff origin/main...HEAD --name-only
```

If $ARGUMENTS specifies a path/glob, filter the file list to matching files only.

**If no changes found:**
- Use AskUserQuestion: "No changes detected. Want me to review a specific branch, file, or directory?"

**Read the actual diffs:**
```bash
git diff --cached
git diff
# Or full branch diff if on a feature branch
git diff origin/main...HEAD
```

### Phase 2: Analyze Changes

**Read all changed files** in full (not just the diff) to understand the broader context.

**Search for related code:**
- Find similar patterns in the codebase
- Identify callers/consumers of changed functions
- Look for tests that cover the changed code
- Check if the changes touch shared abstractions

**Categorize the changes:**
- New functionality vs modifications to existing code
- Data model changes
- API surface changes
- Configuration changes
- Test changes

### Phase 3: Generate Questions

Generate 5-10 tough questions across these categories:

**Edge Cases (at least 2):**
- What happens with empty/nil/null inputs?
- What about concurrent access?
- What if the external dependency is down?
- What about extremely large or extremely small values?
- What happens at boundaries (first item, last item, zero, max int)?

**Design Decisions (at least 2):**
- Why did you choose this approach over [alternative]?
- Why is this responsibility in [module] and not [other module]?
- What's the trade-off of this abstraction level?
- Why this data structure instead of [alternative]?

**Failure Modes (at least 1):**
- How does this fail? What does the user see?
- Is the error message actionable?
- What's the recovery path?
- Could this fail silently?

**Impact Assessment (at least 1):**
- What existing behavior could this break?
- Who else calls this function/endpoint?
- What happens to existing data when this migrates?
- Could this cause a performance regression?

**Security (if applicable):**
- Is user input validated/sanitized?
- Are there authorization checks?
- Could this leak sensitive data in logs/errors?

**Quality adjustments:**
- Questions should reference specific lines/functions from the diff
- Questions should be answerable by someone who wrote the code thoughtfully
- Avoid gotcha questions — focus on questions that reveal understanding
- Harder questions for larger/riskier changes

### Phase 4: The Quiz

Present questions one at a time using AskUserQuestion. For each question:

1. **Ask the question** — include the relevant code snippet for context
2. **Evaluate the answer:**
   - **PASS** — demonstrates understanding of the issue and a reasonable approach
   - **PARTIAL** — shows awareness but missing key details. Provide a hint and ask for elaboration.
   - **FAIL** — missed the issue entirely. Explain what they should consider and why it matters.

**Scoring:**
- Track PASS/PARTIAL/FAIL for each question
- After all questions, calculate a score

### Phase 5: Verdict

**Determine the result:**

| Score | Verdict | Action |
|-------|---------|--------|
| 80%+ PASS (no FAILs) | **READY** | Offer to proceed with committing changes |
| 60-79% or 1 FAIL | **ALMOST** | Summarize gaps, suggest reviewing specific areas, offer a re-quiz on failed topics |
| Below 60% or 2+ FAILs | **NOT READY** | Detailed breakdown of gaps, specific things to investigate before re-attempting |

If `--strict` flag was used, require 100% PASS for READY verdict.

**Present the scorecard:**

```markdown
## Grill Results

**Score:** [X]/[Y] passed ([percentage]%)
**Verdict:** [READY / ALMOST / NOT READY]

### Question Breakdown
| # | Category | Topic | Result |
|---|----------|-------|--------|
| 1 | Edge Case | Nil input handling | PASS |
| 2 | Design | Module responsibility | PARTIAL |
| ... | ... | ... | ... |

### Areas of Strength
- [What the developer demonstrated good understanding of]

### Areas to Review
- [Specific gaps to address]
- [Code areas to reconsider]

### Next Steps
- [What to do based on the verdict]
```

**If READY:**
- Ask if they want to commit their changes now

**If ALMOST or NOT READY:**
- Offer to re-quiz on failed topics after the developer has reviewed
- Suggest specific files to re-read or patterns to study

## Error Handling

- If the diff is too large (>50 files), focus on the most impactful changes and note that not everything was covered
- If the changes are trivial (config only, typo fix), acknowledge that and ask 2-3 lighter questions instead of the full quiz
- If the user gets frustrated, remind them: "The goal is to catch issues before they're committed — better to find gaps now than during code review"

## Important Constraints

- **Be tough but fair** — questions should be challenging but answerable
- **No trick questions** — every question should have a concrete, practical answer
- **Reference the actual code** — generic questions are less valuable than specific ones
- **Accept reasonable answers** — there's often more than one valid approach
- **Don't be pedantic** — focus on real risks, not style preferences
- **One question at a time** — don't overwhelm with a wall of questions

## Example Usage

```
/agentic-coding-workflow:grill-me
```
Reviews all current changes and starts the quiz.

```
/agentic-coding-workflow:grill-me lib/accounts/
```
Reviews only changes in the accounts module.

```
/agentic-coding-workflow:grill-me --strict
```
Requires perfect answers before proceeding.
