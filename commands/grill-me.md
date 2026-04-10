---
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - AskUserQuestion
  - Agent
effort: high
---

# Grill Me — Edge Case & Design Decision Quiz

Reviews your staged/unstaged changes, generates tough questions about edge cases and design decisions, pre-computes expected answers, and evaluates your responses against them. Only lets you proceed to PR creation after you demonstrate real understanding.

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

### Phase 2: Deep Analysis

**Read all changed files** in full (not just the diff) to understand the broader context.

**Search for related code:**
- Find similar patterns in the codebase
- Identify callers/consumers of changed functions
- Look for tests that cover the changed code
- Check if the changes touch shared abstractions
- Look for existing error handling patterns in the same module

**Categorize the changes:**
- New functionality vs modifications to existing code
- Data model changes
- API surface changes
- Configuration changes
- Test changes

**Identify actual issues** — before generating questions, find real problems:
- Trace each code path manually. What inputs reach this code? What state can exist?
- Check: are there callers that pass nil/empty/unexpected types?
- Check: does the existing test suite cover the changed behavior? (Read the tests, don't assume)
- Check: are there race conditions given the concurrency model of the project?
- Check: if this touches a database, what happens on rollback/failure mid-transaction?
- Distinguish between real risks (things that can actually happen given the codebase) and theoretical risks (things that sound scary but can't happen here)

### Phase 3: Generate Questions with Expected Answers

Generate 5-10 questions. **For each question, write an expected answer BEFORE presenting it to the user.** The expected answer is your rubric — keep it private.

**Question format (internal, not shown to user):**
```
Question: [The question]
Code Reference: [Specific file:line or diff hunk]
Expected Answer: [What a correct answer must include — specific elements, not vibes]
Disqualifiers: [Answers that sound confident but are wrong — common false passes]
Verification: [How to check the user's claims against the actual code]
Severity: [REAL RISK — this can happen in production | DESIGN QUESTION — defensible either way | THEORETICAL — unlikely but worth knowing about]
```

**Question categories:**

**Edge Cases (at least 2):**
- Only ask about edge cases that can actually occur given the callers and data flow you observed
- Reference the specific caller or data path that could trigger the edge case
- Don't ask about nil inputs if the type system or upstream code prevents them

**Design Decisions (at least 2):**
- Ask about decisions where there IS a credible alternative — not rhetorical questions
- Name the specific alternative and its trade-off
- Your expected answer should acknowledge the trade-off, not just defend the choice

**Failure Modes (at least 1):**
- Trace what happens when the failure occurs — don't just ask "what if X fails"
- Your expected answer should include: what the user sees, whether data is consistent, and recovery path

**Impact Assessment (at least 1):**
- Identify actual callers/consumers — don't ask "who else uses this" as a quiz question when YOU should know the answer
- Your expected answer should name the specific impacted code paths

**Security (if applicable):**
- Only ask if the code actually handles user input, auth, or sensitive data
- Reference the specific untrusted input vector

**Question quality gates — reject questions that:**
- Are theoretical risks that can't happen given the actual codebase (false positives)
- Have obvious answers visible in the diff (wastes the developer's time)
- Are style preferences disguised as design questions
- Could be answered by reading the function signature alone

### Phase 4: The Quiz

Present questions one at a time using AskUserQuestion. For each question:

1. **Ask the question** — include the relevant code snippet for context
2. **Evaluate the answer against your expected answer and the actual code:**

**Evaluation protocol — apply these rules in order:**

**Step A: Verify factual claims.** If the user says "I handle that in function X" or "the framework does Y" or "that can't happen because Z":
- Read the actual code to confirm. Use Read, Grep, or Glob.
- If the claim is wrong, it's a FAIL regardless of how confident the answer sounded.
- If the claim is right, proceed to Step B.

**Step B: Check for completeness against your expected answer.**
- Does the answer address ALL the specific elements in your expected answer?
- Missing a key element = PARTIAL at best, even if what they said was correct.

**Step C: Check for disqualifiers.**
- Does the answer match any of your pre-identified "sounds right but wrong" patterns?
- Common disqualifier: restating the code's behavior without explaining WHY it's correct for the edge case.
- Common disqualifier: "the tests cover that" without being able to name which test.
- Common disqualifier: vague appeals to the framework handling it, without specifics.

**Step D: Assign the result:**
- **PASS** — factual claims verified, all key elements of expected answer addressed, no disqualifiers hit
- **PARTIAL** — factual claims correct but missing key elements. Tell them WHAT is missing (not the answer) and ask for elaboration. They get ONE follow-up attempt.
- **FAIL** — factual claim was wrong, OR hit a disqualifier, OR missing the core insight after follow-up. Explain the real answer and why it matters.

**Anti-agreeableness rules:**
- A confident, articulate answer that is factually wrong is still a FAIL. Do not let eloquence substitute for correctness.
- "I'll fix that" or "good point, I should handle that" is not a PASS — it confirms they MISSED it. Score as FAIL but note the awareness positively in the summary.
- If you're unsure whether an answer is correct, verify against the code before scoring. Default to checking, not to passing.
- Partial credit exists for a reason — use it. A perfect PASS rate should be uncommon for non-trivial changes.
- If every answer is getting PASS, your questions were probably too easy. Note this in the summary.

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
| # | Category | Severity | Topic | Result |
|---|----------|----------|-------|--------|
| 1 | Edge Case | REAL RISK | Nil input from API caller | FAIL |
| 2 | Design | DESIGN QUESTION | Module responsibility | PASS |
| ... | ... | ... | ... | ... |

### Accuracy Self-Check
- Questions asked about real risks: [N]
- Questions asked about theoretical risks: [N]
- Times I verified user claims against code: [N]
- False passes avoided by verification: [N]

### Areas of Strength
- [What the developer demonstrated good understanding of]

### Areas to Review
- [Specific gaps with file:line references]
- [Code areas to reconsider]

### Issues Found During Analysis
- [Any real bugs or issues discovered during Phase 2 that weren't quiz questions — report these regardless of quiz outcome]

### Next Steps
- [What to do based on the verdict]
```

**If READY:**
- Ask if they want to commit their changes now

**If ALMOST or NOT READY:**
- Offer to re-quiz on failed topics after the developer has reviewed
- Suggest specific files to re-read or patterns to study
- List the specific lines of code to revisit

## Error Handling

- If the diff is too large (>50 files), focus on the most impactful changes and note that not everything was covered
- If the changes are trivial (config only, typo fix), acknowledge that and ask 2-3 lighter questions instead of the full quiz
- If the user gets frustrated, remind them: "The goal is to catch issues before they're committed — better to find gaps now than during code review"

## Important Constraints

- **Be tough and honest** — your job is to find what the developer missed, not to validate what they did
- **No trick questions** — every question should have a concrete, practical answer grounded in the actual code
- **Reference the actual code** — generic questions are less valuable than specific ones
- **Verify, don't trust** — when the developer claims something, check it before scoring
- **Distinguish real from theoretical** — flag severity so the developer knows what actually matters
- **One question at a time** — don't overwhelm with a wall of questions
- **Report real issues regardless of quiz outcome** — if you found a bug during analysis, say so even if the developer aced the quiz
- **Don't manufacture problems** — if the code is genuinely solid, say so. A short quiz with high marks is better than invented concerns to fill a quota
- **Calibrate to the change** — a 3-line config change doesn't need 10 questions about concurrency

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
