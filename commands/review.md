---
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - Write
  - Agent
  - AskUserQuestion
  - EnterPlanMode
  - ExitPlanMode
  - WebSearch
  - WebFetch
effort: high
---

# Review — Unified Code Review Command

A single entry point for all review workflows. Routes to the appropriate skill or workflow based on input.

## Input

$ARGUMENTS — Determines the review mode:

| Input | Mode | What happens |
|-------|------|-------------|
| `--learn [branch\|path\|glob] [--focus phases] [--strict]` | Review & Learn | Code-grounded review and questions on local changes or a branch |
| `--stats` | Review Stats | Show learning progress from log |
| `--plan [path\|slug]` | Plan review | Staff engineer critique of a plan document |
| `--prep [branch]` | PR prep | Clean up commits, generate PR description |
| `--spec <spec\|slug\|ticket\|description>` | Implementation review | Review code against spec/ticket/criteria |
| `<branch> [branch2...]` | PR code review | Language-specific code review in worktree |
| _(empty)_ | Auto-detect | Check for specs first, fall back to current branch review |

Optional flags:
- `--tracker jira|linear` — select the tracker for a bare ticket key; remove it before mode detection
- `go`, `python`, `typescript` (`ts`), `javascript` (`js`), or `elixir` prefix — select language guidance while retaining mixed-change coverage
- `--suggestions` — include a separate nonblocking design/taste section; default reports prioritize actionable defects
- `--env staging|prod` — for troubleshooting context
- `--focus phase1,phase2` — (learn mode only) drill specific PERFECT phases
- `--strict` — (learn mode only) require every selected question to pass for a complete exercise

## Mode Detection

Parse `$ARGUMENTS` to determine which mode to run:

Remove `--suggestions` before interpreting targets and carry it as review
context. Apply `${CLAUDE_PLUGIN_ROOT}/references/review-policy.md` to code/spec
reviews and author/reviewer loops. Preserve learn mode's teaching format.

1. If starts with `--learn` → **Review & Learn** mode
2. If starts with `--stats` → **Review Stats** mode
3. If starts with `--plan` → **Plan Review** mode
4. If starts with `--prep` → **PR Prep** mode
5. If starts with `--spec` or argument is a Jira/Linear ticket key or ticket URL, a spec path (`.claude/specs/`), or a quoted description → **Implementation Review** mode
6. If argument looks like a branch name → **PR Code Review** mode
7. If empty → check `.claude/specs/` for recent specs; if found, offer Implementation Review; otherwise review current branch

---

## Mode: Review & Learn

The single learning workflow for reviewing changes and explaining their edge
cases, design decisions, failure modes, and impact. You review and answer first;
the AI checks your reasoning against the code, then teaches from the gaps.

### 1. Parse Arguments

- Extract an optional branch, file, directory, or glob after `--learn`.
- With no target, use staged and unstaged changes plus relevant untracked files.
  If there are none, use the current feature branch's diff against its base.
- A path or glob filters that same change set. A branch selects that branch's
  diff against its PR base or the repository's default branch. Resolve ambiguity
  if a target names both a path and a branch.
- Extract `--focus` phases if provided (comma-separated: `evidence,reliability,edge-cases`). If not provided, run all 6 scored phases.
- Extract `--strict` if provided. This changes the exercise assessment, not
  permission to commit or publish.
- Detect language (same as PR Code Review).

### 2. Gather Context

- Read the relevant task, PR description, or commit history.
- For local changes, inspect `git diff --cached`, `git diff`, and relevant
  files from `git ls-files --others --exclude-standard` in the active checkout.
- For an explicit branch, use `git diff <base>...<branch>` and read file contents
  at that branch with `git show <branch>:<path>` or an isolated review worktree.
  Do not silently review HEAD instead of the requested branch.
- Read changed code, callers, tests, and comparable implementations within the
  selected scope. Preserve local edits; no stash or checkout is needed to quiz them.
- If there is no reviewable change, ask for a branch or code scope, or report
  that there is nothing to review. Do not invent issues to create an exercise.

### 3. Silent Pre-Scan

Run the full PERFECT review internally **without displaying results**. Follow the pr-reviewer skill's PERFECT phases (Evidence through Purpose), continuing code inspection when automated checks fail or are unavailable. For each finding, record Phase, Confidence, trigger, affected execution path, consequence, repository evidence or reproduction, and uncertainty.

Read `references/perfect-framework.md` for phase and confidence definitions. Load `references/source-registry.md` only when external documentation is needed for relevant semantics; source URLs do not verify local findings.

**Important**: Only **Verified** and **Likely** findings will be used for scoring. Be conservative — better to have 5 well-grounded findings than 15 questionable ones.

Store findings internally, organized by phase.

Before presenting each question, prepare a private expected answer, code
reference, key elements, plausible incorrect answers, and how to verify claims.
Ask about reachable edge cases, credible design alternatives, failure/recovery
paths, and actual callers. Distinguish defects from defensible design choices.
Choose questions in proportion to the change; there are no question quotas.

### 4. Phase-by-Phase Walk-Through

Read `references/learn-mode-prompts.md` for phase-specific prompts and teaching templates.

For each phase (in order: Evidence, Reliability, Form, Clarity, Edge Cases, Purpose — or filtered by `--focus`):

**Step A — Present & Ask:**
- Show the relevant portion of the diff/code for this phase (see learn-mode-prompts.md for what to show per phase)
- Use `AskUserQuestion` with a phase-specific prompt or a concrete question,
  one at a time. Wait for the answer before showing the expected reasoning.

**Step B — Compare:**
- Match user findings against AI findings for this phase
- Verify factual claims against code, callers, and tests before scoring. If the
  user supplies evidence that disproves an AI finding, correct the finding and
  its denominator rather than penalizing the user.
- Assess each question as **PASS**, **PARTIAL**, or **FAIL** using the shared
  learning reference. Give an incomplete answer one follow-up before teaching
  the missing reasoning. Confidence or a promise to fix something is not proof.
- Categorize each:
  - **Caught**: User identified the same issue (even if worded differently)
  - **Missed**: AI found it, user didn't
  - **Bonus**: User found something AI missed (praise this!)

**Step C — Teach:**
- For each **Caught** finding: brief confirmation with repository evidence and a reference link only when it clarifies relevant semantics
- For each **Missed** finding: use the teaching template from learn-mode-prompts.md (What, Where, Trigger, Execution path, Why it matters, Repository evidence / reproduction, Uncertainty, How to spot it, optional Reference)
- For each **Bonus** finding: verify, acknowledge, and record
- Report real issues regardless of how well the user answers the questions.

**Step D — Phase Score:**
- Report: "You found {n} of {m} issues in {Phase}. {brief note}"

### 5. Scorecard

After all phases, present the full scorecard (template in learn-mode-prompts.md):
- Phase-by-phase breakdown with scores
- Strongest and weakest phases
- Bonus finds count
- Key takeaways (patterns from the 1-2 biggest misses)
- Question results with code references, and any gaps to revisit. In `--strict`
  mode, the exercise is complete only when every selected question is PASS;
  otherwise identify the remaining topics and offer a retry. Learning scores
  do not replace verification, code review, or publishing authorization.

### 6. Persist Learning Log

```bash
mkdir -p "$(git rev-parse --show-toplevel)/.claude/reviews"
```

Append one JSON line to `.claude/reviews/learning-log.jsonl` following the schema
in learn-mode-prompts.md. Include timestamp, branch and selected scope, language,
phase scores, question results, strict mode, missed patterns with repository
evidence and uncertainty, optional reference URLs, and bonus finds.

### 7. Next Steps

Suggest:
- "Run `/review --stats` to see your progress over time"
- "Run `/review --learn --focus {weakest_phase}` next time to drill your weakest area"
- If this was their first session: "After 3+ sessions, stats will show your improvement trajectory"

---

## Mode: Review Stats

Show learning progress from the review training log.

### 1. Read Learning Log

```bash
LOG_FILE="$(git rev-parse --show-toplevel)/.claude/reviews/learning-log.jsonl"
```

If the file doesn't exist or is empty:
> No learning sessions recorded yet. Run `/review --learn <branch>` to start training.

### 2. Parse & Aggregate

Read the JSONL file. For each line, parse the JSON object. Aggregate:

- **Total sessions** and date range
- **Overall average score** across all sessions
- **Per-phase averages**: evidence, reliability, form, clarity, edge_cases, purpose
- **Last 5 sessions**: scores for trend analysis
- **Most common misses**: group by phase, count frequency of similar patterns

Older entries without scope, questions, or strict mode remain readable. Exclude
sessions with no scored findings from issue-score averages; report question
results separately rather than treating a defect-free change as a failed quiz.

### 3. Present Stats

```markdown
## Review Training Stats

**Sessions:** {total} ({first_date} — {last_date})
**Overall Score:** {avg}% (across all sessions)

### Phase Performance
| Phase | Avg Score | Last 5 Trend | Sessions |
|-------|-----------|-------------|----------|
| Evidence | {%} | {arrow up/down/flat} {recent_%} | {n with issues} |
| Reliability | {%} | {arrow} {recent_%} | {n} |
| Form | {%} | {arrow} {recent_%} | {n} |
| Clarity | {%} | {arrow} {recent_%} | {n} |
| Edge Cases | {%} | {arrow} {recent_%} | {n} |
| Purpose | {%} | {arrow} {recent_%} | {n} |

### Strongest: {phase} ({%})
### Weakest: {phase} ({%})

### Most Common Misses
1. {pattern} ({phase}, missed {n} times)
2. {pattern} ({phase}, missed {n} times)
3. {pattern} ({phase}, missed {n} times)

### Recommendations
- Focus on **{weakest_phase}** — run `/review --learn --focus {weakest_phase}`
- {specific pattern to watch for based on most common misses}
```

If 3+ sessions, add a trend section showing whether overall score is improving, stable, or declining.

---

## Mode: PR Code Review

Route to the `pr-reviewer` skill in an isolated worktree.

### 1. Parse Branches & Language

- If the first word is a supported language prefix, use it as guidance and remove it from the branch list; normalize `ts`/`js`
- Otherwise inspect changed extensions and component manifests using the reviewer skill's detection table; use `auto` for a separate launcher when the target has not yet been inspected
- Inspect all affected languages/contracts in mixed changes, even with a prefix
- Branches separated by spaces, "and", commas

### 2. Choose Review Placement

Review a small, focused change in the current session. Use an independent reviewer when the expected benefit justifies the model calls, latency, and handoff cost. A subagent needs the review tools, permissions, turn budget, and an isolated worktree at the target branch. Parallelize independent branch reviews with clear scope and separate worktrees. Use separate primary sessions when independent visibility, user interaction, or a separate lifecycle is needed.

For separate primary sessions, use the launch script below. It handles fetching,
worktree creation, PR number lookup, read-only command readiness inspection,
tmux session creation (for multi-branch), and independent Claude review sessions.
It does not install dependencies or change lockfiles. Use the project's setup
contract when setup is authorized; otherwise report incomplete verification.

Find the launch script:
```bash
LAUNCH_SCRIPT=$(find ~/.claude/plugins -path "*/agentic-coding-workflow/scripts/launch-reviews.sh" -o -path "*/agentic-coding-marketplace/scripts/launch-reviews.sh" 2>/dev/null | head -1)
if [ -z "$LAUNCH_SCRIPT" ]; then
  LAUNCH_SCRIPT="$(git rev-parse --show-toplevel)/scripts/launch-reviews.sh"
fi
```

Run it with the detected language and branch list:
```bash
env REVIEW_MODE="$REVIEW_MODE" bash "$LAUNCH_SCRIPT" "$LANGUAGE" branch1 [branch2] [branch3]
```

The script will:
- **Single branch:** Run the review directly in the current terminal
- **Multiple branches:** Create a tmux session with one pane per branch, each running an independent Claude review session

Set `REVIEW_MODE=defects` by default or `suggestions` for `--suggestions`.
Continuing reviews must carry the previous report and round count; use the
current-session/subagent path when that history needs to be supplied. Starting
a separate reviewer does not reset the repair budget.

After launching, report the tmux session name if applicable. Your job is done — the review sessions are independent.

### 3. Current Session or Subagent Review

For current-session or subagent review, follow the `pr-reviewer` skill's worktree
setup and guarded cleanup instructions. Review the requested branch, gather PR
context, and inspect the existing environment. Follow project setup only when
authorized; missing dependencies remain explicit verification limitations.
Pass the branch, criteria, prior findings/round count when available, and output
format to a delegated reviewer; inspect its evidence before reporting. This
path also serves as the fallback if the launcher is unavailable.

---

## Mode: Implementation Review

Review code changes against a spec, Jira/Linear ticket, or ad-hoc criteria.

### 1. Locate Review Criteria

- **Spec path/slug:** Read `.claude/specs/<slug>-spec.md`, extract acceptance criteria
- **Ticket key or URL** (e.g., `AI-1234`): Follow **Ticket Context and Lifecycle** in `${CLAUDE_PLUGIN_ROOT}/references/shared-patterns.md`; fetch through the shared CLI/API resolver, extract criteria, and preserve provider/site/native identity. Do not use MCP connectors. If retrieval fails or relevant context is truncated, report the gap and inspect available source; do not claim ticket compliance without the missing criteria.
- **Quoted description:** Use directly as criteria
- **Empty:** List `.claude/specs/`, ask user to select or provide criteria

### 2. Identify Changes

```bash
git diff --cached --name-only
git diff --name-only
git ls-files --others --exclude-standard
git diff origin/main...HEAD --name-only
```

Read each changed file. Note files mentioned in spec but not changed.

### 3. Spec Compliance

For each acceptance criterion: read relevant code, mark as PASS/FAIL/PARTIAL with explanation.

### 4. Quality & Pattern Review

- Search for similar implementations and repository rules; explain the concrete compatibility or maintenance consequence of any flagged deviation
- Assess readability, maintainability, edge cases, error handling, security, performance
- Auto-detect language and load the relevant review guidance; delegate an independent language-specific review when its expected benefit justifies its cost

### 5. Run Verification

Detect project type and run the project's test and lint commands.

Record commands, outcomes, and verification scope. If checks fail or cannot run, report failures or verification limitations and continue useful inspection; unavailable infrastructure does not establish a code defect. Use the pr-reviewer skill's evidence and confidence requirements for findings.

### 6. Generate Report

```markdown
# Implementation Review: [Feature Name]

**Source:** [spec path / ticket ID / description]
**Status:** APPROVE / REQUEST CHANGES / NEEDS DISCUSSION

## Spec Compliance
| Criterion | Status | Notes |
|-----------|--------|-------|

## Issues Found
(Use pr-reviewer skill severity levels and format)

## Verification and Remaining Decisions
(actual results, checked source, limitations, open reviewer decisions)
```

**Assessment criteria:**
- **APPROVE:** All criteria pass, no blockers, patterns followed, tests pass
- **REQUEST CHANGES:** Criteria fail, blockers exist, tests fail
- **NEEDS DISCUSSION:** Spec ambiguous, trade-offs need team input, or required verification unavailable without an established blocker

### 7. PR Creation Offer

If APPROVE: check for existing PR, offer to run `/agentic-coding-workflow:ship` if none exists.

---

## Mode: Plan Review

Staff engineer critique of a plan document before implementation.

### 1. Locate the Plan

- Full path → read directly
- Slug → look for `.claude/plans/<slug>.md`
- Empty → auto-detect from `.claude/plans/`, ask if multiple

### 2. Review the Plan

Read the plan directly. Use an independent reviewer with a staff engineer persona when a separate assessment is likely to catch enough material issues to justify its cost. Review across:
- **Feasibility** — technically achievable? hidden complexities?
- **Scope** — well-defined? scope creep hiding?
- **Missing considerations** — edge cases, failure modes, performance, migration?
- **Architecture** — fits existing system? better patterns available?
- **Risks** — complete? mitigations realistic? rollback story?
- **Alternatives** — simpler approach overlooked? phased rollout better?
- **Open questions** — right questions? which are blockers?

### 3. Present Review

Output structured report with verdict: Ready for `/agentic-coding-workflow:write-spec`, needs minor revisions, or needs significant rework.

This is read-only — no files are written.

---

## Mode: PR Prep

Clean up commits into logical groups and generate PR description.

### 1. Identify Branch

```bash
BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null)
git log --oneline "${BASE}..HEAD"
```

If on main/master, stop and tell user to switch to a feature branch.

### 2. Group Changes Logically

```bash
git diff --name-only "${BASE}...HEAD" | sort
```

Suggest groups (feature code, tests, config/infra, refactoring). Use AskUserQuestion to confirm groupings.

### 3. Interactive Rebase

Create backup branch first:
```bash
git branch "backup/$(git symbolic-ref --short HEAD)-$(date +%Y%m%d-%H%M%S)"
```

Then soft reset and re-commit in logical groups.

### 4. Generate PR Description

Preserve the project's PR template and write `.claude/pr-description.md` using
the **PR evidence** facts in `${CLAUDE_PLUGIN_ROOT}/references/review-policy.md`.
Without a template, use Summary, Verification, Reviewer decisions, and Recovery
when applicable, matching `/ship`. Separate actual results from future checks.

### 6. Report

Show before/after commit count, backup branch, PR description path, and next steps.

---

## Example Usage

```
/agentic-coding-workflow:review feature/auth-refactor                    # PR code review
/agentic-coding-workflow:review go feature/timeouts                     # Go review
/agentic-coding-workflow:review typescript feature/api --suggestions    # Include optional suggestions
/agentic-coding-workflow:review elixir feature/payments feature/billing  # Multi-branch Elixir review
/agentic-coding-workflow:review --learn feature/auth-refactor            # Interactive training on a PR
/agentic-coding-workflow:review --learn                                  # Learn from local changes
/agentic-coding-workflow:review --learn lib/accounts/ --strict            # Focused code questions
/agentic-coding-workflow:review --learn --focus edge-cases,reliability   # Drill specific phases
/agentic-coding-workflow:review --stats                                  # Show learning progress
/agentic-coding-workflow:review --spec batch-analysis                    # Review against spec
/agentic-coding-workflow:review --spec AI-1234 --tracker jira            # Review against a Jira ticket
/agentic-coding-workflow:review --spec "users can reset password"        # Review against description
/agentic-coding-workflow:review --plan feature-name                      # Staff engineer plan critique
/agentic-coding-workflow:review --prep                                   # Squash WIP, generate PR desc
/agentic-coding-workflow:review                                          # Auto-detect mode
```
