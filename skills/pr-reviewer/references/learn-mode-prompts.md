# Learn Mode — Phase Prompts & Teaching Templates

Loaded only in `--learn` mode. Provides per-phase quiz prompts, scoring rules, and teaching templates for missed findings.

## Scoring Rules

- Only **Verified** and **Likely** findings count toward scoring
- **Uncertain** findings are excluded — never penalize for missing something the AI can't prove
- A user finding "matches" an AI finding if it identifies the same general issue, even if worded differently
- **Bonus** findings (user found something AI missed) are recorded and praised but don't affect the denominator
- Taste phase is not scored

## Phase Order for Walk-Through

Present phases in this order (bottom-up, matching the PERFECT review flow):
1. Evidence
2. Reliability
3. Form
4. Clarity
5. Edge Cases
6. Purpose

Skip Taste (non-blocking, not scored). If `--focus` is specified, only present the listed phases.

---

## Phase Prompts

### Evidence

**Framing:**
> We're starting with **Evidence** — automated checks. Here are the test results, linting output, and static analysis results from this PR.
>
> Look at these results. Do you see any failures, warnings, or concerning patterns in the test/CI output?

**What to show:** Test output, linting output, CI status. Show actual tool output, not just pass/fail.

**What good looks like:** User identifies specific test failures, notices skipped tests, spots linting warnings that indicate deeper issues, notices missing test coverage for new code.

**Common misses:** Skipped tests that should be running, new warnings introduced (not just failures), test files that should exist but don't.

---

### Reliability

**Framing:**
> Now we're looking at **Reliability** — performance and security. Here are the changed files that handle data, external input, or system resources.
>
> What performance or security issues do you see?

**What to show:** Changed files that handle: user input, database queries, authentication, file I/O, network calls, serialization, secrets/credentials.

**What good looks like:** User spots SQL injection, identifies N+1 queries, notices missing input validation, flags hardcoded secrets, identifies unbounded operations.

**Common misses:**
- N+1 queries (Repo.all + Enum.map with inner query, or ORM queries in loops)
- Missing input validation at system boundaries
- Unsafe deserialization (pickle, :erlang.binary_to_term)
- Race conditions in concurrent code
- Missing timeout on external calls

---

### Form

**Framing:**
> Now **Form** — design principles and codebase conventions. Here are the structural changes: new modules, modified interfaces, import changes.
>
> Does this code follow the patterns you see elsewhere in the codebase? What deviations or design issues do you notice?

**What to show:** New modules/classes, modified function signatures, import changes, module structure changes. Also show 1-2 examples of existing similar code for comparison.

**What good looks like:** User identifies pattern deviations by comparing to existing code, spots unnecessary abstractions, notices coupling issues, flags public API changes.

**Common misses:**
- Subtle pattern deviations (doing the same thing differently than existing code)
- Over-abstraction or premature generalization
- Breaking the module's single responsibility
- Accidental public API exposure

---

### Clarity

**Framing:**
> Now **Clarity** — does this code communicate its intent? Here are the new and modified functions.
>
> Can you understand what each function does from its name, parameters, and structure? What's unclear?

**What to show:** New/modified function signatures, variable declarations in complex logic, comments (or lack thereof), documentation.

**What good looks like:** User flags cryptic variable names, identifies functions that do too much, spots misleading comments, notices missing documentation on public APIs.

**Common misses:**
- Generic variable names in complex logic (data, result, temp, x)
- Comments that parrot the code instead of explaining why
- Functions over ~20 lines that could be decomposed
- Missing @doc/@moduledoc or docstrings on public functions

---

### Edge Cases

**Framing:**
> Now **Edge Cases** — boundary conditions and failure modes. Here are the functions that process input, handle errors, or make decisions.
>
> What happens when inputs are nil, empty, zero, negative, or unexpected? What failure modes aren't handled?

**What to show:** Functions that take input parameters, error handling blocks, pattern matches, conditional logic, external service calls.

**What good looks like:** User identifies nil/None paths, spots missing empty collection handling, flags unhandled error cases, notices missing timeout/retry logic.

**Common misses:**
- Nil propagation through a chain of function calls
- Empty list/map/string not handled separately from nil
- Integer boundary values (0, -1, max)
- External service timeout/failure not handled
- Race conditions in concurrent operations
- Unicode edge cases in string processing

---

### Purpose

**Framing:**
> Finally, **Purpose** — does this code solve the stated task? Here's the PR description/ticket alongside the full diff summary.
>
> Does the code address what was stated? Is there scope creep or missing implementation?

**What to show:** PR description or ticket alongside a summary of what the diff actually changes (files, functions, behaviors).

**What good looks like:** User spots scope creep (unrelated changes), identifies missing implementation (PR says X but code doesn't do X), flags over-engineering, notices the approach doesn't match the stated goal.

**Common misses:**
- Subtle scope creep disguised as "cleanup" or "while I was here"
- Partial implementation that covers the happy path but not the full requirement
- Over-engineering that addresses hypothetical future requirements

---

## Teaching Template for Misses

When the user misses a finding, present it using this structure:

```markdown
### Missed: {Issue Title}

**What:** {One-sentence description of the issue}

**Where:** `{file_path}:{line_number}`
```{lang}
{relevant code snippet}
```

**Why it matters:** {Consequence — what would happen in production, not just "it's bad practice"}

**How to spot it:** {A pattern the user can look for next time}
> "{recognizable trigger}" → check for {what to look for}

**Source:** [{source name}]({URL})
```

Example:
```markdown
### Missed: N+1 Query in User List

**What:** Each user triggers a separate query to load their profile, creating N+1 database calls.

**Where:** `lib/app_web/controllers/user_controller.ex:45`
```elixir
users = Repo.all(User)
Enum.map(users, fn user -> Repo.preload(user, :profile) end)
```

**Why it matters:** With 1000 users, this makes 1001 queries instead of 2. Page load time scales linearly with user count.

**How to spot it:** "Repo.all followed by Enum.map with Repo calls inside" → check for N+1. Use Repo.preload or a join in the original query.

**Source:** [Ecto.Query.preload/3](https://hexdocs.pm/ecto/Ecto.Query.html#preload/3)
```

---

## Scorecard Template

Present at end of review:

```markdown
## Review Training Scorecard

**PR:** {branch_name}
**Date:** {YYYY-MM-DD}
**Overall:** {caught}/{total} ({percentage}%)

### Phase Breakdown
| Phase | Found | Total | Score | Highlight |
|-------|-------|-------|-------|-----------|
| Evidence | {n} | {n} | {%} | {one-line note or "--"} |
| Reliability | {n} | {n} | {%} | {note} |
| Form | {n} | {n} | {%} | {note} |
| Clarity | {n} | {n} | {%} | {note} |
| Edge Cases | {n} | {n} | {%} | {note} |
| Purpose | {n} | {n} | {%} | {note} |

### Strongest: {phase name}
### Weakest: {phase name}
### Bonus Finds: {count} (issues you caught that AI missed)

### Key Takeaways
1. {Pattern from biggest miss — "When you see X, check for Y"}
2. {Second pattern if applicable}
3. {What you did well — specific, not generic praise}
```

---

## Learning Log Schema

Append one line per session to `.claude/reviews/learning-log.jsonl`:

```json
{
  "timestamp": "ISO-8601",
  "branch": "branch-name",
  "pr_number": null,
  "language": "elixir|python",
  "total_found": 0,
  "total_issues": 0,
  "score_pct": 0.0,
  "phases": {
    "evidence": {"found": 0, "total": 0},
    "reliability": {"found": 0, "total": 0},
    "form": {"found": 0, "total": 0},
    "clarity": {"found": 0, "total": 0},
    "edge_cases": {"found": 0, "total": 0},
    "purpose": {"found": 0, "total": 0}
  },
  "misses": [
    {"phase": "phase-name", "description": "what was missed", "pattern": "how to spot it", "source": "URL"}
  ],
  "bonuses": [
    {"phase": "phase-name", "description": "what user found that AI missed"}
  ]
}
```
