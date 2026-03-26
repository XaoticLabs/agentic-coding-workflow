---
name: pr-reviewer
description: |
  Review pull requests for code quality, readability, maintainability, and security.
  Supports Elixir and Python. Auto-detects language from changed files.
  Use when: review code, review PR, code review, check PR, review pull request,
  review elixir, review python, PR analysis, code quality, review changes,
  review branch, check code, analyze PR, review for bugs, review for security.
  Keywords: review, PR, pull request, code review, code quality, Elixir, Python,
  OTP, Phoenix, Ecto, GenServer, pytest, ruff, pyright, mix test, credo, dialyzer.
allowed-tools: Bash, Read, Grep, Glob
effort: high
user-invocable: false
---

# PR Reviewer

Review pull requests with structured output, language-specific checks, and pattern consistency analysis. Auto-detects language from changed files.

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

## Review Workflow

### 1. Gather Context

- Read the PR description (`gh pr view <number>`) or commit history (`git log origin/main..HEAD --oneline`)
- Run `git diff origin/main...HEAD` to see all changes
- **Read the actual changed files** — diffs alone are insufficient for line-accurate feedback

### 2. Pattern Consistency (highest priority)

Search for similar implementations in the codebase before flagging pattern issues. New code must follow existing conventions unless there's strong justification to deviate.

### 3. Run Validation Tools

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

### 4. Language-Specific Deep Review

Load reference materials conditionally based on what the code touches:

**Elixir references** (in `references/elixir/`):
- `elixir_style_guide.md` — when checking formatting, naming, module structure
- `elixir_otp_best_practices.md` — when reviewing GenServers, supervision trees, concurrency
- `ecto_phoenix_patterns.md` — when reviewing schemas, changesets, queries, controllers, LiveView
- `testing_practices.md` — when evaluating test coverage and quality

**Python references** (in `references/python/`):
- `python_review_checklist.md` — consolidated checklist covering code quality, modern idioms, security, and testing

Only load references relevant to the code being reviewed. Do not load all references upfront.

### 5. Assess Test Coverage

Every feature and bug fix must include tests that prove it works:
- Happy path tested?
- Error cases and edge cases covered?
- Tests are behavior-based (test what code does, not how)?
- Test organization follows existing patterns?

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
**Category:** {category}

**Current Code:**
```{lang}
{actual code from the file}
```

**Problem:** {what's wrong and why}

**Suggested Fix:**
```{lang}
{concrete fix}
```
---

## Recommendations
1. {prioritized recommendations}

## Summary
**Total Issues:** {count}
- Blockers: {count}
- Major: {count}
- Minor: {count}
- Nitpicks: {count}
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
- Read the actual files — do not rely solely on diffs
- Check callers of modified functions to verify compatibility
- Focus on actionable, copy-paste-ready suggestions
- Acknowledge good work alongside issues
