---
name: python-pr-reviewer
description: Review Python GitHub pull requests for code quality, readability, maintainability, and security. Use when users request a review of Python code, PRs, or repositories. Focuses on modern Python 3.10+ idioms, pattern consistency, comprehensive test coverage, and proof that features actually work.
---

# Python PR Reviewer

## Overview

Conduct comprehensive, expert-level reviews of Python pull requests with a focus on code quality, readability, maintainability, resilience, and security. Reviews emphasize following existing codebase patterns, modern Python 3.10+ idioms, comprehensive test coverage, and requiring proof that features and fixes actually work.

## When to Use This Skill

Invoke this skill when:
- User requests a review of Python code in a repository or PR
- User asks to "review this code" or "check this PR" in a Python project
- User wants feedback on Python code quality or maintainability
- User asks for suggestions to improve Python code
- Reviewing GitHub pull requests for Python projects

## Review Workflow

Follow this structured workflow to conduct thorough PR reviews.

### Step 0: Auto-Worktree Setup (for GitHub PRs)

When reviewing a GitHub PR, automatically create a temporary worktree to check out the PR branch. This keeps the user's current working directory clean.

```bash
# 1. Get PR branch name
PR_BRANCH=$(gh pr view <pr-number> --json headRefName -q '.headRefName')

# 2. Create temporary worktree under .claude/worktrees/
REPO_ROOT=$(git rev-parse --show-toplevel)
WORKTREE_BASE="${REPO_ROOT}/.claude/worktrees"
DIR_NAME="review-$(echo "$PR_BRANCH" | sed 's/[\/]/-/g' | sed 's/[^a-zA-Z0-9._-]//g')"
WORKTREE_PATH="${WORKTREE_BASE}/${DIR_NAME}"

# Ensure gitignored
if ! grep -q '\.claude/worktrees/' "${REPO_ROOT}/.gitignore" 2>/dev/null; then
  echo -e '\n# Git worktrees (parallel branch work)\n.claude/worktrees/' >> "${REPO_ROOT}/.gitignore"
fi

# Fetch and create worktree
git fetch origin "$PR_BRANCH"
mkdir -p "$WORKTREE_BASE"
git worktree add "$WORKTREE_PATH" "origin/$PR_BRANCH"

# 3. Work from the worktree for the rest of the review
cd "$WORKTREE_PATH"
```

After the review is complete, tear down the worktree:
```bash
cd "$REPO_ROOT"
git worktree remove "$WORKTREE_PATH"
git worktree prune
```

For local-only reviews (no PR number), skip this step and review in the current directory.

### Step 1: Understand the Context

Before reviewing code, understand the codebase and PR context.

**1.1 Read the PR Description**
- Understand what the PR is trying to accomplish
- Note any claims about functionality or fixes
- Identify if this is a feature, bug fix, refactoring, or other type of change

**1.2 Explore the Codebase** (if unfamiliar)
- Use the Task tool with subagent_type=Explore to understand:
  - Existing code patterns and conventions
  - How similar features are implemented
  - Testing patterns used in the codebase
  - Project structure and organization

**1.3 Identify Changed Files**
- Use `git diff` or GitHub's PR interface to see what files changed
- Read the changed files to understand modifications

### Step 2: Conduct Systematic Review

Review the code against each category using the comprehensive checklist. Load reference materials as needed.

**2.1 Pattern Consistency (HIGHEST PRIORITY)**
Consistency with existing codebase patterns is critical. New patterns should only be introduced when absolutely necessary.

Check:
- Does this follow the same patterns used elsewhere in the codebase?
- Are similar problems solved in similar ways?
- If introducing a new pattern, is it justified and necessary?
- Are naming conventions consistent?
- Is error handling consistent with existing code?

Load `references/review_checklist.md` section 1 for detailed checklist.

**2.2 Test Coverage and Proof of Functionality (CRITICAL)**
Every feature and bug fix MUST include tests that prove it works.

Check:
- Are there tests for new features?
- Are there regression tests for bug fixes?
- Do tests cover edge cases and error paths?
- Are tests clear and maintainable?
- Is there evidence (tests or manual testing) that this actually works?

Load `references/review_checklist.md` section 6-7 for detailed checklist.

**2.3 Modern Python Idioms**
Code should use Python 3.10+ features and idioms.

Check:
- Type hints with modern syntax (`dict[str, int]` not `Dict[str, int]`)
- Union types with `|` instead of `Union`
- Pattern matching for complex conditionals (3.10+)
- Dataclasses instead of manual `__init__`
- F-strings for formatting
- Context managers for resources
- Proper async/await patterns

Load `references/modern_python_guide.md` for comprehensive guidance and examples.

**2.4 Code Quality and Readability**
Code should be clear, maintainable, and well-documented.

Check:
- Clear naming and structure
- Appropriate function length and complexity
- No code duplication
- Comprehensive type hints
- Good docstrings
- No anti-patterns

Load `references/review_checklist.md` sections 2-3 for detailed checklist.

**2.5 Error Handling and Resilience**
Code should handle errors gracefully and be resilient to edge cases.

Check:
- Specific exception handling
- Defensive programming (input validation, boundary conditions)
- Proper logging
- Resources cleaned up in error cases

Load `references/review_checklist.md` section 4 for detailed checklist.

**2.6 Security**
Identify potential security vulnerabilities.

Check:
- No SQL/command/code injection vulnerabilities
- Proper password hashing
- No hardcoded secrets
- Input validation and output sanitization
- Secure session management

Load `references/security_guide.md` for comprehensive security checklist.

**2.7 Performance and Scalability**
Check for performance issues and scalability concerns.

Check:
- Efficient database queries
- Generators for large datasets
- Appropriate caching
- Set operations for membership testing
- No obvious bottlenecks

Load `references/review_checklist.md` section 9 for detailed checklist.

### Step 3: Structure the Review Output

Present findings in a structured format with clear severity levels and actionable feedback.

**3.1 Severity Levels**

Use these severity levels for all findings:

- **CRITICAL**: Must be fixed before merge
  - Security vulnerabilities
  - Broken functionality
  - Data loss risks
  - Missing tests for features/fixes

- **HIGH**: Should be fixed before merge
  - Major code quality issues
  - Significant maintainability problems
  - Pattern inconsistencies
  - Missing type hints on public APIs

- **MEDIUM**: Should be addressed
  - Code style issues
  - Minor maintainability concerns
  - Opportunities for improvement
  - Non-critical security concerns

- **LOW**: Nice to have
  - Suggestions
  - Optional optimizations
  - Style preferences

**3.2 Review Output Format**

Structure the review as follows:

```markdown
# Python PR Review: [PR Title/Description]

## Summary

[1-2 sentences about what the PR does]

**Overall Assessment**: [APPROVE / REQUEST CHANGES / COMMENT]
- [X] Tests included and prove functionality
- [X] Follows existing codebase patterns
- [ ] Issue found: [brief description]

## Critical Issues (Must Fix Before Merge)

### [Category]: [Issue Description]
**Severity**: CRITICAL
**File**: `path/to/file.py:line_number`

[Detailed explanation of the issue]

**Current Code**:
```python
[Show the problematic code with line numbers]
```

**Suggested Fix**:
```python
[Show the corrected code]
```

**Why This Matters**: [Explain the impact of this issue]

---

## High Priority Issues (Should Fix Before Merge)

[Same format as Critical Issues]

---

## Medium Priority Issues (Should Address)

[Same format as Critical Issues, can be more concise]

---

## Low Priority Suggestions

[Brief list of suggestions]

---

## Positive Observations

[Call out good practices, clever solutions, or well-written code]

## Test Coverage Assessment

[Evaluate the comprehensiveness of tests]

- [ ] Happy path tested
- [ ] Error cases tested
- [ ] Edge cases tested
- [ ] Integration tests if needed

## Conclusion

[Final recommendation: approve, request changes, or needs discussion]
```

**3.3 Code Examples**

Always include:
- **File path and line numbers** for every issue (e.g., `src/models/user.py:42`)
- **Current code** showing the problem with line numbers
- **Suggested fix** with concrete code example
- **Explanation** of why it's an issue and why the fix is better

### Step 4: Provide Actionable Feedback

Ensure all feedback is specific, actionable, and educational.

**Do:**
- ✅ Point to specific lines of code
- ✅ Provide concrete code examples of fixes
- ✅ Explain why something is an issue
- ✅ Reference existing patterns in the codebase
- ✅ Suggest specific improvements
- ✅ Acknowledge good practices

**Don't:**
- ❌ Give vague feedback like "improve this function"
- ❌ Just say "add tests" without being specific about what to test
- ❌ Criticize without explaining or suggesting alternatives
- ❌ Focus only on negatives (acknowledge good work too)
- ❌ Suggest new patterns without strong justification

## Example Review Comments

### Pattern Consistency Issue

```markdown
### Pattern Inconsistency: Different Error Handling Approach
**Severity**: HIGH
**File**: `src/api/users.py:45-52`

This PR introduces a new error handling pattern that differs from the existing codebase.

**Current Code**:
```python
# src/api/users.py:45-52
def create_user(data: dict) -> dict:
    try:
        user = User(**data)
        db.session.add(user)
        db.session.commit()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

**Issue**: The codebase uses exception-based error handling (letting exceptions propagate), not try-catch with success flags. See `src/api/posts.py:23-28` for the pattern.

**Suggested Fix**:
```python
# Follow existing pattern from src/api/posts.py
def create_user(data: dict) -> User:
    """Create a new user.

    Raises:
        ValidationError: If user data is invalid
        DatabaseError: If database operation fails
    """
    user = User(**data)
    db.session.add(user)
    db.session.commit()
    return user
```

**Why This Matters**: Consistency makes the codebase easier to understand and maintain. The existing pattern is clearer because callers know to handle exceptions rather than checking return values.
```

### Missing Tests Issue

```markdown
### Missing Tests: No Proof That Feature Works
**Severity**: CRITICAL
**File**: `src/features/user_notifications.py`

This new feature has no tests demonstrating that it works correctly.

**Required Tests**:
1. Test that notifications are sent when user is created
2. Test that notification format is correct
3. Test that errors are handled gracefully (e.g., email service down)
4. Test edge case: user with no email address

**Example Test Structure**:
```python
# tests/features/test_user_notifications.py
def test_notification_sent_on_user_creation():
    """Test that a welcome notification is sent when user is created."""
    user = create_user(name="Alice", email="alice@example.com")

    # Verify notification was sent
    assert len(mock_email_service.sent_emails) == 1
    assert mock_email_service.sent_emails[0].to == "alice@example.com"
    assert "Welcome" in mock_email_service.sent_emails[0].subject

def test_notification_handles_email_service_failure():
    """Test that user creation succeeds even if notification fails."""
    with mock_email_service.failing():
        user = create_user(name="Bob", email="bob@example.com")
        assert user.id is not None  # User was created
        # Error should be logged but not raised
```

**Why This Matters**: Tests are the proof that code works. Without tests, we can't be confident this feature actually functions or that future changes won't break it.
```

### Security Issue

```markdown
### Security Vulnerability: SQL Injection
**Severity**: CRITICAL
**File**: `src/database/queries.py:67`

This code is vulnerable to SQL injection attacks.

**Current Code**:
```python
# src/database/queries.py:67
def find_user_by_email(email: str) -> User | None:
    query = f"SELECT * FROM users WHERE email = '{email}'"
    return db.execute(query).fetchone()
```

**Vulnerability**: An attacker could pass `email = "' OR '1'='1"` to bypass authentication or extract data.

**Fix**: Use parameterized queries:
```python
def find_user_by_email(email: str) -> User | None:
    query = "SELECT * FROM users WHERE email = ?"
    return db.execute(query, (email,)).fetchone()
```

**Why This Matters**: SQL injection is one of the most common and dangerous vulnerabilities. It can lead to complete database compromise.
```

## Tips for Effective Reviews

1. **Focus on what matters most**: Pattern consistency and test coverage are top priorities.

2. **Be specific**: Always reference exact file paths and line numbers.

3. **Provide context**: Explain why something is an issue, don't just state that it is.

4. **Suggest, don't demand**: Use "Consider..." or "Suggest..." for non-critical items.

5. **Be constructive**: Frame feedback in terms of improving the code, not criticizing the author.

6. **Reference documentation**: Point to the modern Python guide or security guide when relevant.

7. **Acknowledge good work**: Call out well-written code, clever solutions, or good practices.

8. **Prioritize ruthlessly**: Don't flag every tiny issue. Focus on what significantly impacts quality, maintainability, or security.

## Resources

This skill includes comprehensive reference materials:

### references/modern_python_guide.md
Comprehensive guide to modern Python 3.10+ features, idioms, and best practices. Includes code examples for:
- Type hints and type safety
- Structural pattern matching (3.10+)
- Dataclasses
- Async/await patterns
- Error handling
- And much more

Load this when reviewing code for modern Python idioms.

### references/review_checklist.md
Comprehensive checklist covering all aspects of Python code review:
- Pattern consistency
- Code quality and readability
- Modern Python idioms
- Error handling and resilience
- Test coverage
- Security
- Performance
- Documentation

Load relevant sections when conducting systematic reviews.

### references/security_guide.md
Detailed guide to Python security best practices:
- Injection vulnerabilities (SQL, command, path traversal, code)
- Authentication and authorization
- Input validation and sanitization
- Secrets management
- Cryptography
- DoS prevention
- Dependency security

Load this when reviewing code for security issues.
