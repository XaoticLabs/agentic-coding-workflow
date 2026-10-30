# Learn Mode — Phase Prompts & Teaching Templates

Loaded only in `--learn` mode. Provides code questions, per-phase review prompts,
scoring rules, and teaching templates for local changes and branch reviews.

## Code Questions and Answer Verification

Before asking a question, privately record:

- The code reference and reachable input, caller, or failure path
- The expected answer and key elements that demonstrate understanding
- Credible alternatives and their trade-offs for design questions
- Plausible incorrect answers and the code or test that distinguishes them

Ask one question at a time and show enough code for context. Cover relevant
edge cases, design decisions, failure/recovery paths, downstream effects, and
security boundaries. Skip theoretical risks prevented by actual guards and
questions answered by the function signature alone. Do not fill a quota.

Read the code to check claims such as "the caller prevents that" or "the tests
cover it." Verify external semantics when needed. Accept evidence-backed
alternatives to the expected answer and correct your own rubric when warranted.

| Result | Meaning |
|--------|---------|
| PASS | Factual claims verified and the key reasoning is complete |
| PARTIAL | Correct claims with an important missing element; explain what is missing and allow one follow-up |
| FAIL | A disproved claim, incorrect core reasoning, or a material gap remaining after the follow-up |

When evidence is unavailable, record the question as unscored with the limitation
rather than guessing PASS or FAIL. Articulate confidence and "I'll fix that"
do not establish a correct answer. Do not aim for a particular failure rate.
Always disclose real defects found, regardless of quiz performance.

`--strict` marks the exercise complete only if all selected questions pass.
Unscored or unresolved questions leave it incomplete. The assessment is for
learning; committing and publishing still follow their own authorization policy.

## Scoring Rules

- Only **Verified** and **Likely** findings count toward scoring
- **Uncertain** findings are excluded — never penalize for missing something the AI can't prove
- A user finding "matches" an AI finding if it identifies the same general issue, even if worded differently
- **Bonus** findings (user found something AI missed) are recorded and praised but don't affect the denominator
- Taste phase is not scored
- Use the framework's local-evidence confidence definitions. External URLs and pattern matches alone do not verify findings. Record unavailable checks as verification limitations, continue the walk-through, and do not score missing infrastructure as a code defect.
- Count each finding once. With no scored findings, show the issue score as N/A;
  keep code-comprehension question results separate from issue-detection scores.

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

Distinguish observed failures from checks that could not run. State what remains unverified and continue with independent code inspection.

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

**What good looks like:** User explains the concrete compatibility or maintenance impact of a deviation using repository rules and affected usages, identifies costly abstractions or coupling, or flags unintended public API changes.

**Common misses:**
- Pattern deviations that violate an applicable repository rule or impose a concrete maintenance cost
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
- Tangled responsibilities or control flow that useful named helpers could clarify
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

````markdown
### Missed: {Issue Title}

**What:** {One-sentence description of the issue}
**Confidence:** {Verified | Likely}

**Where:** `{file_path}:{line_number}`
```{lang}
{relevant code snippet}
```

**Why it matters:** {Consequence — what would happen in production, not just "it's bad practice"}

**Trigger:** {input, state, or event that exposes the issue}
**Execution path:** {entry point/caller → guards → affected operation, or affected maintenance task}
**Repository evidence / reproduction:** {file:line references and causal reasoning, or input/command with expected vs actual results}
**Uncertainty:** {unresolved assumptions or verification limits, or "None"}

**How to spot it:** {A pattern the user can look for next time}
> "{recognizable trigger}" → check for {what to look for}

**Reference (optional):** [{documentation name}]({URL}) — {relevant semantics or adopted rule; omit when unnecessary}
````

Example:
````markdown
### Missed: N+1 Query in User List

**What:** Each user triggers a separate query to load their profile, creating N+1 database calls.
**Confidence:** Likely

**Where:** `lib/app_web/controllers/user_controller.ex:45`
```elixir
users = Repo.all(User)
Enum.map(users, fn user -> Repo.preload(user, :profile) end)
```

**Why it matters:** If the profiles are initially unloaded, 1000 users would cause 1001 queries instead of 2. The extra database round trips increase with user count.

**Trigger:** A user-list request returns N users whose profiles are not preloaded.
**Execution path:** The user-list handler fetches users, then iterates through them and preloads each profile individually.
**Repository evidence / reproduction:** The handler snippet at `lib/app_web/controllers/user_controller.ex:45` shows one initial query and one per-user preload inside the loop.
**Uncertainty:** Query counts assume no earlier profile preload; confirm the handler's preceding code and the model's profile association.

**How to spot it:** "Repo.all followed by Enum.map with Repo calls inside" → check for N+1. Use Repo.preload or a join in the original query.

**Reference:** [Ecto.Query.preload/3](https://hexdocs.pm/ecto/Ecto.Query.html#preload/3) — preload semantics; the repository call path establishes the repeated queries.
````

---

## Scorecard Template

Present at end of review:

```markdown
## Review Training Scorecard

**Scope:** {local changes, path/glob, or branch_name}
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

### Code Questions
| Phase | Topic / Code Reference | Result | Gap to Revisit |
|-------|------------------------|--------|----------------|
| {phase} | {topic and file:line} | {PASS / PARTIAL / FAIL / UNSCORED} | {gap or --} |

**Strict mode:** {on/off}; **Exercise:** {complete / incomplete, when strict}

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
  "scope": "local changes, path/glob, or branch-name",
  "strict": false,
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
    {"phase": "phase-name", "description": "what was missed", "pattern": "how to spot it", "evidence": "repository locations or reproduction", "uncertainty": "unresolved assumptions or None", "source": null}
  ],
  "bonuses": [
    {"phase": "phase-name", "description": "what user found that AI missed"}
  ],
  "questions": [
    {"phase": "phase-name", "topic": "question topic", "code_reference": "file:line", "result": "PASS|PARTIAL|FAIL|UNSCORED", "notes": "evidence or remaining gap"}
  ]
}
```

Set `source` to a relevant external reference URL when used, otherwise `null`.
Keep repository evidence in `evidence`; a URL alone is not proof of a local
defect. Set `score_pct` to `null` when `total_issues` is zero. Existing entries
with a URL in `source`, or without scope, strict, and questions, remain readable.
