# Review Python PR

Follow the `Instructions` below to perform a comprehensive code review of a Python pull request, focusing on code quality, readability, maintainability, modern Python 3.10+ idioms, security, and pattern consistency with the existing codebase.

## Variables

branch_name: $1 (required - the git branch to review)
pr_number: $2 (optional - the GitHub PR number for additional context)

## Instructions

1. **Setup & Context**
   - If `branch_name` is provided, run `git fetch origin` and `git checkout <branch_name>` to switch to the branch
   - If `pr_number` is provided, fetch PR details using `gh pr view <pr_number>`
   - Run `git diff origin/main...HEAD` to see all changes in the branch
   - Run `git log origin/main..HEAD --oneline` to see commit history
   - **CRITICAL**: Read the actual changed files to get exact line numbers and code context

2. **Deep Code Analysis - REQUIRED**
   - **You MUST read the actual source files** that were changed using the Read tool
   - For EVERY issue found, you MUST provide:
     - Exact file path (e.g., `src/services/auth.py`)
     - Exact line number(s) where the issue occurs
     - The actual problematic code snippet from the file
     - Detailed explanation of what's wrong and why
     - A concrete code example showing the fix
   - Do NOT provide generic feedback without specific file locations and code examples

3. **Invoke Python PR Reviewer Skill**
   - Use the `python-pr-reviewer` skill to perform a comprehensive code review
   - The skill will analyze:
     - Code quality and readability
     - Maintainability and testability
     - Modern Python 3.10+ idioms and best practices
     - Security vulnerabilities (SQL injection, command injection, etc.)
     - Pattern consistency with existing codebase
     - Test coverage and quality
     - Type hints and static analysis
     - Documentation quality

4. **Review Focus Areas**
   - **Readability**: Clear variable names, proper formatting, logical structure
   - **Maintainability**: DRY principles, proper abstractions, modularity
   - **Modern Idioms**: Use of f-strings, type hints, dataclasses, pattern matching (3.10+), etc.
   - **Goal Achievement**: Does the code accomplish its intended purpose effectively?
   - **Pattern Consistency**: Uses existing codebase patterns rather than introducing new ones
   - **No Regressions**: Changes don't break existing functionality
   - **Anti-patterns**: Avoid god objects, circular dependencies, global state, etc.

5. **Testing & Validation**
   - Run tests: `uv run pytest -v`
   - Run type checking: `uv run basedpyright` or `uv run pyright`
   - Run linting: `uv run ruff check .`
   - Check test coverage if configured

## Output Structure

Return a well-formatted markdown report with the following structure:

```markdown
# PR Review: {branch_name}

**PR Number:** {pr_number or "N/A"}
**Status:** {✅ PASS or ❌ FAIL (based on blocking issues)}

## Summary

{3-5 sentences summarizing the changes, their quality, and overall assessment}

## Test Results

- **Tests:** {✅ PASS or ❌ FAIL or ⚠️ SKIPPED}
- **Type Check:** {✅ PASS or ❌ FAIL or ⚠️ SKIPPED}
- **Linting:** {✅ PASS or ❌ FAIL or ⚠️ SKIPPED}
- **Coverage:** {percentage}%

## Strengths

- {positive aspect 1}
- {positive aspect 2}
- ...

## Issues Found

### 🔴 BLOCKER: {Issue Title}
**File:** `{file_path}:{line_number}`
**Category:** {category}

**Current Code:**
```python
{actual problematic code from the file}
```

**Problem:**
{Detailed explanation of what's wrong and why it's a problem}

**Impact:**
{Explain the consequences of not fixing this}

**Suggested Fix:**
```python
{concrete code example showing how to fix it}
```

**How to Fix:**
1. {step 1}
2. {step 2}
3. {step 3}

---

### 🟠 MAJOR: {Issue Title}
{same structure as above}

---

### 🟡 MINOR: {Issue Title}
{same structure as above}

---

### ⚪ NITPICK: {Issue Title}
{same structure as above}

---

## Recommendations

1. {overall recommendation 1}
2. {overall recommendation 2}
3. ...

## Summary

**Total Issues:** {count}
- 🔴 Blockers: {count}
- 🟠 Major: {count}
- 🟡 Minor: {count}
- ⚪ Nitpicks: {count}
```

## Severity Definitions

- **blocker**: Critical issues that prevent merging (security vulnerabilities, broken functionality, test failures)
- **major**: Important issues that should be fixed before merging (maintainability problems, missing tests)
- **minor**: Issues that should be addressed but don't block merging (minor code smell, missing docstrings)
- **nitpick**: Style or preference issues (formatting, naming conventions)

## Critical Requirements

- **MANDATORY**: Every issue MUST include exact file path and line number
- **MANDATORY**: Every issue MUST include the actual problematic code snippet
- **MANDATORY**: Every issue MUST include a concrete fix with code example
- **MANDATORY**: Read the actual files to get real code, not just diffs
- Do NOT provide vague or generic feedback
- Do NOT skip line numbers or code examples
- Focus on actionable, copy-paste ready suggestions
- Consider the broader codebase context and existing patterns
- Prioritize issues based on actual impact to users and maintainers
- Be thorough, specific, and constructive in feedback

## Example Issue Format

Good example:

```markdown
### 🔴 BLOCKER: SQL Injection Vulnerability in get_user
**File:** `src/api/handlers.py:42`
**Category:** security

**Current Code:**
```python
def get_user(user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return db.execute(query)
```

**Problem:**
SQL injection vulnerability - user_id is directly interpolated into the SQL query without sanitization or parameterization. This allows arbitrary SQL code execution.

**Impact:**
An attacker could inject malicious SQL code through the user_id parameter, potentially reading, modifying, or deleting database data. This is a critical security vulnerability that could lead to complete database compromise.

**Suggested Fix:**
```python
def get_user(user_id: int):
    query = "SELECT * FROM users WHERE id = ?"
    return db.execute(query, (user_id,))
```

**How to Fix:**
1. Add type hint `user_id: int` to enforce integer type at the function signature level
2. Use parameterized query with `?` placeholder instead of f-string interpolation
3. Pass user_id as a parameter tuple `(user_id,)` to `db.execute()`
4. This prevents SQL injection by separating SQL code from data values

---
```
