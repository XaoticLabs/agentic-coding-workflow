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
  - mcp__claude_ai_Linear__get_issue
  - mcp__claude_ai_Linear__list_issues
effort: high
---

# Review — Unified Code Review Command

A single entry point for all review workflows. Routes to the appropriate skill or workflow based on input.

## Input

$ARGUMENTS — Determines the review mode:

| Input | Mode | What happens |
|-------|------|-------------|
| `--learn [branch] [--focus phases]` | Review & Learn | Interactive PERFECT training on a PR |
| `--stats` | Review Stats | Show learning progress from log |
| `--plan [path\|slug]` | Plan review | Staff engineer critique of a plan document |
| `--prep [branch]` | PR prep | Clean up commits, generate PR description |
| `--spec <spec\|slug\|ticket\|description>` | Implementation review | Review code against spec/ticket/criteria |
| `<branch> [branch2...]` | PR code review | Language-specific code review in worktree |
| _(empty)_ | Auto-detect | Check for specs first, fall back to current branch review |

Optional flags:
- `elixir` or `python` prefix — force language detection
- `--env staging|prod` — for troubleshooting context
- `--focus phase1,phase2` — (learn mode only) drill specific PERFECT phases

## Mode Detection

Parse `$ARGUMENTS` to determine which mode to run:

1. If starts with `--learn` → **Review & Learn** mode
2. If starts with `--stats` → **Review Stats** mode
3. If starts with `--plan` → **Plan Review** mode
4. If starts with `--prep` → **PR Prep** mode
5. If starts with `--spec` or argument is a Linear ticket ID (pattern: `LETTERS-DIGITS`) or a spec path (`.claude/specs/`) or a quoted description → **Implementation Review** mode
6. If argument looks like a branch name → **PR Code Review** mode
7. If empty → check `.claude/specs/` for recent specs; if found, offer Implementation Review; otherwise review current branch

---

## Mode: Review & Learn

Interactive training mode where each PR review becomes a learning rep. You review first, AI reveals findings, you learn from gaps.

### 1. Parse Arguments

- Extract branch name (after `--learn`). If empty, use current branch.
- Extract `--focus` phases if provided (comma-separated: `evidence,reliability,edge-cases`). If not provided, run all 6 scored phases.
- Detect language (same as PR Code Review).

### 2. Gather Context

- Read PR description or commit history
- Run `git diff origin/main...HEAD` for full diff
- Read all changed files

### 3. Silent Pre-Scan

Run the full PERFECT review internally **without displaying results**. Follow the pr-reviewer skill's PERFECT phases (Evidence through Purpose). For each finding, tag with Phase, Confidence, and Source.

Read `references/perfect-framework.md` for phase definitions and `references/source-registry.md` for source URLs.

**Important**: Only **Verified** and **Likely** findings will be used for scoring. Be conservative — better to have 5 well-grounded findings than 15 questionable ones.

Store findings internally, organized by phase.

### 4. Phase-by-Phase Walk-Through

Read `references/learn-mode-prompts.md` for phase-specific prompts and teaching templates.

For each phase (in order: Evidence, Reliability, Form, Clarity, Edge Cases, Purpose — or filtered by `--focus`):

**Step A — Present & Ask:**
- Show the relevant portion of the diff/code for this phase (see learn-mode-prompts.md for what to show per phase)
- Use `AskUserQuestion` with the phase-specific framing prompt
- Wait for the user's findings

**Step B — Compare:**
- Match user findings against AI findings for this phase
- Categorize each:
  - **Caught**: User identified the same issue (even if worded differently)
  - **Missed**: AI found it, user didn't
  - **Bonus**: User found something AI missed (praise this!)

**Step C — Teach:**
- For each **Caught** finding: brief confirmation with the source link
- For each **Missed** finding: use the teaching template from learn-mode-prompts.md (What, Where, Why it matters, How to spot it, Source URL)
- For each **Bonus** finding: acknowledge and record

**Step D — Phase Score:**
- Report: "You found {n} of {m} issues in {Phase}. {brief note}"

### 5. Scorecard

After all phases, present the full scorecard (template in learn-mode-prompts.md):
- Phase-by-phase breakdown with scores
- Strongest and weakest phases
- Bonus finds count
- Key takeaways (patterns from the 1-2 biggest misses)

### 6. Persist Learning Log

```bash
mkdir -p "$(git rev-parse --show-toplevel)/.claude/reviews"
```

Append one JSON line to `.claude/reviews/learning-log.jsonl` following the schema in learn-mode-prompts.md. Include timestamp, branch, language, phase scores, missed patterns with source URLs, and bonus finds.

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

- If first word is `elixir` or `python`, use it as language and remove from branch list
- Otherwise auto-detect: `mix.exs` → elixir, `pyproject.toml`/`setup.py` → python
- Branches separated by spaces, "and", commas

### 2. Launch via Script

**IMPORTANT: Do NOT use subagents or the Agent tool for PR code reviews. You MUST run the launch script below.** The script handles everything: fetching, worktree creation, PR number lookup, dependency bootstrapping, tmux session creation (for multi-branch), and launching independent Claude review sessions.

Find the launch script:
```bash
LAUNCH_SCRIPT=$(find ~/.claude/plugins -path "*/agentic-coding-workflow/scripts/launch-reviews.sh" -o -path "*/agentic-coding-marketplace/scripts/launch-reviews.sh" 2>/dev/null | head -1)
if [ -z "$LAUNCH_SCRIPT" ]; then
  LAUNCH_SCRIPT="$(git rev-parse --show-toplevel)/scripts/launch-reviews.sh"
fi
```

Run it with the detected language and branch list:
```bash
bash "$LAUNCH_SCRIPT" "$LANGUAGE" branch1 [branch2] [branch3]
```

The script will:
- **Single branch:** Run the review directly in the current terminal
- **Multiple branches:** Create a tmux session with one pane per branch, each running an independent Claude review session

After launching, report the tmux session name if applicable. Your job is done — the review sessions are independent.

### 3. Fallback (no tmux, no script)

Only if the launch script cannot be found: review in current session by creating a worktree, cd into it, invoke the `pr-reviewer` skill directly, then cleanup worktree when done.

---

## Mode: Implementation Review

Review code changes against a spec, Linear ticket, or ad-hoc criteria.

### 1. Locate Review Criteria

- **Spec path/slug:** Read `.claude/specs/<slug>-spec.md`, extract acceptance criteria
- **Linear ticket ID** (e.g., `AI-1234`): Fetch via Linear MCP, extract criteria
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

- Search for similar implementations in codebase; flag deviations from established patterns
- Assess readability, maintainability, edge cases, error handling, security, performance
- Auto-detect language and spawn subagent for language-specific deep review

### 5. Run Verification

Detect project type and run the project's test and lint commands.

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

## Strengths / Recommendations / Test Results
```

**Assessment criteria:**
- **APPROVE:** All criteria pass, no blockers, patterns followed, tests pass
- **REQUEST CHANGES:** Criteria fail, blockers exist, tests fail
- **NEEDS DISCUSSION:** Spec ambiguous, trade-offs need team input

### 7. PR Creation Offer

If APPROVE: check for existing PR, offer to run `/agentic-coding-workflow:ship` if none exists.

---

## Mode: Plan Review

Staff engineer critique of a plan document before implementation.

### 1. Locate the Plan

- Full path → read directly
- Slug → look for `.claude/plans/<slug>.md`
- Empty → auto-detect from `.claude/plans/`, ask if multiple

### 2. Launch Review Subagent

Spawn a subagent with staff engineer persona to review across:
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

Write to `.claude/pr-description.md` with Summary, Changes, Test plan, Notes sections.

### 6. Report

Show before/after commit count, backup branch, PR description path, and next steps.

---

## Example Usage

```
/agentic-coding-workflow:review feature/auth-refactor                    # PR code review
/agentic-coding-workflow:review elixir feature/payments feature/billing  # Multi-branch Elixir review
/agentic-coding-workflow:review --learn feature/auth-refactor            # Interactive training on a PR
/agentic-coding-workflow:review --learn --focus edge-cases,reliability   # Drill specific phases
/agentic-coding-workflow:review --stats                                  # Show learning progress
/agentic-coding-workflow:review --spec batch-analysis                    # Review against spec
/agentic-coding-workflow:review --spec AI-1234                           # Review against Linear ticket
/agentic-coding-workflow:review --spec "users can reset password"        # Review against description
/agentic-coding-workflow:review --plan feature-name                      # Staff engineer plan critique
/agentic-coding-workflow:review --prep                                   # Squash WIP, generate PR desc
/agentic-coding-workflow:review                                          # Auto-detect mode
```
