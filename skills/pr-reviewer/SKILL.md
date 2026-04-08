---
name: pr-reviewer
description: |
  Review pull requests for code quality, readability, maintainability, and security.
  Uses the PERFECT framework: Purpose, Edge Cases, Reliability, Form, Evidence, Clarity, Taste.
  Supports Elixir and Python. Auto-detects language from changed files.
  Use when: review code, review PR, code review, check PR, review pull request,
  review elixir, review python, PR analysis, code quality, review changes,
  review branch, check code, analyze PR, review for bugs, review for security.
  Keywords: review, PR, pull request, code review, code quality, PERFECT, Elixir, Python,
  OTP, Phoenix, Ecto, GenServer, pytest, ruff, pyright, mix test, credo, dialyzer.
allowed-tools: Bash, Read, Grep, Glob, WebSearch, WebFetch
effort: high
user-invocable: false
---

# PR Reviewer

Review pull requests using the PERFECT framework with structured output, source-grounded findings, and language-specific checks. Auto-detects language from changed files.

Read `references/perfect-framework.md` for the full PERFECT phase definitions, severity mapping, and confidence level requirements.

When verifying findings, load `references/source-registry.md` to look up authoritative source URLs by phase and language.

When invoked in learn mode (from the review command's `--learn` flag), load `references/learn-mode-prompts.md` for phase-specific quiz prompts and teaching templates.

## Language Detection

Determine the project language from changed files:

```bash
# Check changed file extensions
git diff origin/main...HEAD --name-only 2>/dev/null | grep -E '\.(ex|exs)$' && echo "ELIXIR"
git diff origin/main...HEAD --name-only 2>/dev/null | grep -E '\.py$' && echo "PYTHON"
```

Fallback: check for `mix.exs` (Elixir) or `pyproject.toml`/`setup.py` (Python) in the repo root.

If both languages are present, review both. If the caller specifies a language, use that.

## Worktree Setup

Always review in an isolated worktree to keep the user's working directory clean:

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
WORKTREE_BASE="${REPO_ROOT}/.claude/worktrees"
DIR_NAME="pr-review-$(echo "$BRANCH" | sed 's/[\/]/-/g' | sed 's/[^a-zA-Z0-9._-]//g')"
WORKTREE_PATH="${WORKTREE_BASE}/${DIR_NAME}"

mkdir -p "$WORKTREE_BASE"
git fetch origin "$BRANCH"
git worktree add "$WORKTREE_PATH" "origin/$BRANCH" --detach
cd "$WORKTREE_PATH"
```

Clean up after review:
```bash
cd "$REPO_ROOT"
git worktree remove "$WORKTREE_PATH"
git worktree prune
```

## Review Workflow — PERFECT Phases

Review bottom-up: automated gates first, human judgment last. Each phase produces findings tagged with a PERFECT phase and confidence level.

### Phase 0: Gather Context

Before starting phases, collect the raw materials:

- Read the PR description (`gh pr view <number>`) or commit history (`git log origin/main..HEAD --oneline`)
- Run `git diff origin/main...HEAD` to see all changes
- **Read the actual changed files** — diffs alone are insufficient for line-accurate feedback
- Note the stated purpose of the PR for the Purpose phase later

### Phase 1: Evidence (Fully Automated Gate)

**Stop here if this phase fails. Do not proceed to human review.**

Run all validation tools and report results:

**Elixir:**
```bash
mix test
mix format --check-formatted
mix credo        # if configured
mix dialyzer     # if configured
```

**Python:**
```bash
uv run pytest -v           # or pytest
uv run ruff check .        # or ruff
uv run basedpyright        # or pyright, if configured
```

Also check CI status if PR number is available: `gh pr checks <number>`

All Evidence findings are **Confidence: Verified** (backed by tool output). Severity: **BLOCKER**.

### Phase 2: Reliability

Scan for performance and security issues:

1. Review static analysis output from Phase 1 for security-relevant warnings
2. Check for: hardcoded secrets, SQL injection, unsafe deserialization, missing auth checks, N+1 queries, unbounded memory, race conditions
3. **Verification**: For each finding, look up the relevant source in `references/source-registry.md` (Reliability section). Cite OWASP/CWE IDs with URLs. If no matching source found, use WebSearch to verify before presenting.

Load language-specific references conditionally:
- **Elixir**: `references/elixir/elixir_otp_best_practices.md` — when reviewing concurrency, GenServers, supervision
- **Python**: `references/python/python_review_checklist.md` — security section

Tag findings: **Verified** (has source URL), **Likely** (tool flagged it), or **Uncertain** (AI judgment only).
Severity: **MAJOR**, escalate to **BLOCKER** for confirmed security vulnerabilities.

### Phase 3: Form

Check alignment with design principles and codebase conventions:

1. **Search for existing patterns first** — grep the codebase for similar implementations before flagging deviations. This is the highest-priority check.
2. Check module structure, import ordering, public API surface
3. Verify high cohesion / low coupling
4. **Verification**: Cite repo pattern matches (grep proof) or style guide URLs from `references/source-registry.md` (Form section). Ruff rule IDs, Credo check names are valid citations.

Load language-specific references conditionally:
- **Elixir**: `references/elixir/elixir_style_guide.md` — formatting, naming, module structure
- **Elixir**: `references/elixir/ecto_phoenix_patterns.md` — schemas, changesets, controllers, LiveView
- **Python**: `references/python/python_style_guide.md` — naming, imports, type annotations, pydantic, ruff rules (Google + PEP 8 adapted for ruff/basedpyright/uv)
- **Python**: `references/python/python_review_checklist.md` — code quality section

Severity: **MAJOR** for pattern deviations, **MINOR** for style.

### Phase 4: Clarity

Assess whether code communicates its intent:

1. Check variable/function naming — are they self-documenting?
2. Check function length — can you understand at a glance?
3. Check comments — do they explain "why" not "what"?
4. Check public API documentation (@doc, docstrings)
5. Flag dead code, commented-out code, TODO debris
6. **Verification**: Cite naming convention docs (PEP 8 naming, Elixir doc guide) from `references/source-registry.md` (Clarity section). For naming issues, also grep the repo for the project's own conventions.

Load conditionally:
- **Elixir**: `references/elixir/elixir_style_guide.md` — if not already loaded in Form phase
- **Python**: `references/python/python_style_guide.md` — if not already loaded in Form phase (docstrings, comments, naming sections)

Severity: **MINOR**.

### Phase 5: Edge Cases

Identify boundary conditions and failure modes:

1. Flag nil/None handling gaps, empty collection handling, boundary values
2. Check error paths — do they return meaningful errors?
3. Check external service failure handling (timeouts, retries)
4. Check concurrent access safety
5. **Verification**: Cite CWE IDs for known weakness classes, property-test references (Hypothesis/StreamData). Use `references/source-registry.md` (Edge Cases section). For uncertain findings, WebSearch to verify.

Load conditionally:
- **Elixir**: `references/elixir/testing_practices.md` — for test coverage of edge cases

Severity: **BLOCKER** for crash-causing gaps, **MAJOR** for degraded behavior.

### Phase 6: Purpose

Verify code solves the stated task:

1. Compare PR description/ticket/commit messages against the actual diff
2. Flag scope creep — changes unrelated to stated purpose
3. Flag missing implementation — stated goals not addressed
4. Assess whether the approach is appropriate (not over/under-engineered)
5. **Verification**: This is a comparison phase — cite the PR description and specific diff sections as evidence.

Severity: **BLOCKER**.

### Phase 7: Taste

Note personal preferences. These are **non-blocking observations only**.

- Alternative approaches worth considering
- Stylistic preferences beyond established conventions
- "I would have done it differently" observations

Severity: **NITPICK** only. Must never block a merge. No confidence tagging needed.

### Phase 8: Test Coverage Assessment

Cross-cutting check across all phases:

- Happy path tested?
- Error cases and edge cases covered? (ties to Phase 5)
- Tests are behavior-based (test what code does, not how)?
- Test organization follows existing patterns? (ties to Phase 3)
- Test code gets the same review rigor as production code

## Output Format

Structure all reviews using this format:

```markdown
# PR Review: {branch_name}

**PR Number:** {number or "N/A"}
**Status:** {PASS or FAIL}

## Summary
{3-5 sentences: what changed, quality assessment, overall verdict}

## Test Results
- **Tests:** {PASS / FAIL / SKIPPED}
- **Formatting/Linting:** {PASS / FAIL / SKIPPED}
- **Static Analysis:** {PASS / FAIL / SKIPPED}

## Strengths
- {positive aspects}

## Issues Found

### {SEVERITY_EMOJI} {SEVERITY}: {Issue Title}
**File:** `{file_path}:{line_number}`
**Phase:** {Evidence | Reliability | Form | Clarity | Edge Cases | Purpose | Taste}
**Confidence:** {Verified | Likely | Uncertain}

**Current Code:**
```{lang}
{actual code from the file}
```

**Problem:** {what's wrong and why}
**Source:** [{source name}]({source URL}) — {brief citation}

**Suggested Fix:**
```{lang}
{concrete fix}
```
---

## PERFECT Summary

| Phase | Issues | Top Severity | Human Action Needed |
|-------|--------|-------------|-------------------|
| Evidence | {n} | {severity} | {None / action} |
| Reliability | {n} | {severity} | {None / action} |
| Form | {n} | {severity} | {None / action} |
| Clarity | {n} | {severity} | {None / action} |
| Edge Cases | {n} | {severity} | {None / action} |
| Purpose | {n} | {severity} | {None / action} |
| Taste | {n} | NITPICK | Author discretion |

## Recommendations
1. {prioritized recommendations}

## Issue Totals
**Total Issues:** {count}
- Blockers: {count}
- Major: {count}
- Minor: {count}
- Nitpicks: {count}
- By confidence: {verified} Verified, {likely} Likely, {uncertain} Uncertain
```

## Severity Levels

| Level | Emoji | Meaning |
|-------|-------|---------|
| BLOCKER | Red circle | Must fix before merge — broken functionality, security, test failures |
| MAJOR | Orange circle | Should fix before merge — maintainability, missing tests, pattern deviations |
| MINOR | Yellow circle | Should address — code smell, missing docs, minor improvements |
| NITPICK | White circle | Optional — style, formatting, preferences |

## Critical Requirements

- Every issue MUST include exact file path and line number
- Every issue MUST include the actual code snippet (not just the diff)
- Every issue MUST include a concrete fix with code example
- Every issue MUST include a Phase and Confidence tag
- Every Verified/Likely issue MUST cite its source with a URL when available
- Read the actual files — do not rely solely on diffs
- Check callers of modified functions to verify compatibility
- Focus on actionable, copy-paste-ready suggestions
- Acknowledge good work alongside issues
- For Uncertain findings: attempt WebSearch verification before presenting. If still unverified, present transparently as Uncertain
