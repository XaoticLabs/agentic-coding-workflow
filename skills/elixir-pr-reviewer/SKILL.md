---
name: elixir-pr-reviewer
description: Review Elixir pull requests for code quality, readability, Elixir/OTP best practices, style guide compliance, test coverage, and modern Ecto/Phoenix patterns. Use this skill when the user requests code review, PR analysis, or mentions reviewing code in Elixir projects. Focus on maintaining existing codebase patterns rather than introducing new ones.
---

# Elixir PR Reviewer

## Overview

Review Elixir pull requests comprehensively, focusing on code quality, Elixir/OTP best practices from "Elixir in Action", style guide compliance, behavior-based test coverage, and modern idiomatic Ecto/Phoenix standards. Ensure new code maintains existing patterns in the codebase rather than introducing inconsistencies.

## When to Use This Skill

Invoke this skill when:
- User asks to review code in Elixir projects
- User mentions analyzing or reviewing pull requests
- User requests code quality assessment for Elixir code
- User asks to check code against style guides or best practices

## Review Workflow

Follow this systematic workflow when reviewing Elixir PRs:

### 0. Auto-Worktree Setup (for GitHub PRs)

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

### 1. Understand the Change Context

**First, gather context about the change:**

- If reviewing a GitHub PR, use `gh` commands to fetch PR information:
  ```bash
  gh pr view <pr-number>
  gh pr diff <pr-number>
  ```

- If reviewing local changes, use git commands:
  ```bash
  git diff main...HEAD
  git log main..HEAD --oneline
  ```

- Read the PR description or ask the user about:
  - What is the purpose of this change?
  - What files are being modified?
  - Are there any special considerations?

**Understand existing codebase patterns:**

- Before reviewing, scan existing code in the same module or context to understand established patterns
- Use `Grep` or `Glob` to find similar implementations in the codebase
- Look for existing test patterns, naming conventions, and architectural decisions
- Note any domain-specific patterns (e.g., how the codebase handles errors, structures contexts, or organizes tests)

### 2. Analyze Code Changes

**Review each changed file systematically:**

1. **Module organization** - Check against the style guide's module attribute ordering
2. **Function structure** - Verify proper function head usage, pattern matching, guards
3. **Naming conventions** - Ensure snake_case, CamelCase, and boolean function suffixes are correct
4. **Process design** - For GenServers, verify all callbacks are implemented, especially `handle_info/2`
5. **Error handling** - Check for proper "let it crash" philosophy, appropriate use of try/rescue
6. **Data structures** - Verify appropriate use of Maps, Lists, Structs, Keyword lists

**Load reference materials as needed:**

- For style questions: Read `references/elixir_style_guide.md`
- For OTP patterns: Read `references/elixir_otp_best_practices.md`
- For Ecto/Phoenix code: Read `references/ecto_phoenix_patterns.md`
- For testing questions: Read `references/testing_practices.md`

### 3. Check Style Guide Compliance

**Verify adherence to the Elixir style guide:**

- **Formatting**: Line length (98 chars), whitespace, indentation
- **Module structure**: Correct ordering of @moduledoc, use, import, alias, etc.
- **Naming**: snake_case for functions/variables, CamelCase for modules, ? suffix for booleans
- **Collections**: Proper keyword list and map syntax
- **Comments**: Proper placement and formatting
- **Type specs**: Correct @spec placement and formatting

**Use the style guide reference:**
```elixir
# Load the complete style guide
Read references/elixir_style_guide.md
```

### 4. Evaluate OTP and Elixir Best Practices

**Check for common OTP patterns and anti-patterns:**

- **GenServer design**: Interface separation, callback completeness, state management
- **Supervision trees**: Appropriate strategy, layered design, restart intensity
- **Concurrency**: Proper use of call vs cast, Task management, Agent usage
- **Error handling**: Let it crash philosophy, proper error propagation
- **Module design**: Single responsibility, clear public API, appropriate function length

**Use the OTP best practices reference:**
```elixir
# Load OTP patterns and principles
Read references/elixir_otp_best_practices.md
```

**Common anti-patterns to flag:**
- Over-using processes when not needed
- Catching all errors without good reason
- Blocking GenServer calls
- Process dictionary abuse
- Large message passing between processes
- Premature abstraction
- Missing backpressure handling

### 5. Review Ecto and Phoenix Patterns

**For code involving Ecto or Phoenix, verify:**

**Ecto patterns:**
- Schema design (UUIDs, Ecto.Enum, virtual fields, redaction)
- Changeset structure (separate changesets for different operations)
- Query organization (composable queries, N+1 prevention, preloading)
- Transaction usage (Ecto.Multi for complex operations)
- Proper context boundaries

**Phoenix patterns:**
- Thin controllers (business logic in contexts)
- Proper context design (domain-driven, single responsibility)
- LiveView best practices (streams, temporary assigns, event handling)
- Authentication and authorization patterns

**Use the Ecto/Phoenix reference:**
```elixir
# Load Ecto and Phoenix patterns
Read references/ecto_phoenix_patterns.md
```

### 6. Assess Test Coverage

**Evaluate test quality and completeness:**

- **Coverage**: Are all new functions tested?
- **Behavior-based**: Tests focus on what code does, not how
- **Test organization**: Proper use of describe blocks, clear test names
- **Factory usage**: Appropriate use of ExMachina for test data
- **Async safety**: Tests marked async when safe
- **Edge cases**: Unhappy paths and boundary conditions covered
- **Integration**: Complex workflows have integration tests

**Check for testing anti-patterns:**
- Testing private functions directly
- Shared state between tests
- Brittle tests that break on refactoring
- Missing edge case tests
- Over-mocking
- Large setup blocks
- Unclear test descriptions

**Use the testing reference:**
```elixir
# Load testing best practices
Read references/testing_practices.md
```

### 7. Check Pattern Consistency

**This is critical: New code must maintain existing patterns.**

**Compare new code against existing patterns:**

1. **Find similar implementations** in the codebase:
   ```elixir
   # Search for similar modules, functions, or patterns
   Grep "pattern" path/to/relevant/code
   Glob "**/*similar_module*.ex"
   ```

2. **Check consistency:**
   - Does the new code follow the same error handling approach?
   - Are function names consistent with existing conventions?
   - Does the module structure match other modules in the same context?
   - Are similar operations implemented the same way?
   - Does testing follow established patterns?

3. **Flag inconsistencies:**
   - New pattern introduced without clear justification
   - Different error handling than rest of codebase
   - Naming that doesn't match existing conventions
   - Test organization that differs from established style

**Example patterns to check:**
- How does the codebase typically structure contexts?
- What's the established pattern for handling external API calls?
- How are errors typically returned (tuples, raises, etc.)?
- What's the test setup pattern in this area of the codebase?
- How are configurations typically accessed?

### 8. Provide Structured Feedback

**Organize findings into clear categories:**

#### ✅ Strengths
- List positive aspects of the code
- Highlight good practices observed
- Acknowledge well-tested or well-structured code

#### ⚠️ Issues Found

**Critical Issues (Must Fix):**
- Security vulnerabilities
- Bugs or logical errors
- Violations of core OTP principles
- Missing required tests
- Breaking changes to public APIs
- Anti-patterns that will cause production issues

**Style & Convention Issues:**
- Style guide violations
- Naming inconsistencies
- Formatting issues
- Missing documentation
- Type spec issues

**Pattern Consistency Issues:**
- New patterns that differ from existing code
- Inconsistent error handling
- Different testing approaches
- Architectural deviations

**Suggestions (Optional Improvements):**
- Performance optimizations
- Readability improvements
- Additional test cases
- Refactoring opportunities
- Documentation enhancements

#### 📝 Code Examples

For each issue, provide:
1. **Location**: File path and line number (e.g., `lib/my_app/accounts.ex:45`)
2. **Current code**: Show the problematic code
3. **Explanation**: Why it's an issue and what guideline/principle it violates
4. **Suggested fix**: Show the corrected code with explanation
5. **Reference**: Link to relevant section in style guide or best practices

**Example format:**
```
⚠️ **GenServer missing handle_info callback**

Location: `lib/my_app/cache.ex:23`

Current code:
```elixir
def handle_cast({:put, key, value}, state) do
  {:noreply, Map.put(state, key, value)}
end
```

Issue: GenServer doesn't implement `handle_info/2`, which means unexpected messages will crash the process.

Reference: OTP Best Practices - "Always implement handle_info/2 to prevent crashes from unexpected messages"

Suggested fix:
```elixir
def handle_cast({:put, key, value}, state) do
  {:noreply, Map.put(state, key, value)}
end

def handle_info(_msg, state) do
  {:noreply, state}
end
```

#### 🎯 Summary

Provide a high-level summary:
- Overall code quality assessment
- Major themes in the feedback
- Priority of changes needed
- Any blocking issues before merge

## Key Principles

**Maintain Existing Patterns:**
- The most important principle is consistency with the existing codebase
- Don't introduce new patterns without discussing with the team
- When in doubt, match what already exists

**Be Constructive:**
- Focus on helping improve the code, not criticizing
- Explain the "why" behind suggestions
- Provide concrete examples and alternatives
- Acknowledge good work

**Prioritize Issues:**
- Separate must-fix from nice-to-have
- Focus on behavior and correctness first
- Style issues are important but secondary to functionality

**Reference Standards:**
- Always cite specific guidelines when pointing out issues
- Use the reference materials to back up suggestions
- Point to examples in the codebase when available

## Resources

This skill includes comprehensive reference materials:

### references/elixir_style_guide.md
The community Elixir style guide covering formatting, naming, module structure, and code organization. Load this when questions arise about code style, formatting, or conventions.

### references/elixir_otp_best_practices.md
Key patterns and principles from "Elixir in Action" covering GenServer design, supervision trees, concurrency patterns, error handling, and common anti-patterns. Load this when reviewing process-based code or OTP implementations.

### references/ecto_phoenix_patterns.md
Modern patterns for Ecto and Phoenix including schema design, changesets, queries, transactions, context design, LiveView patterns, and testing. Load this when reviewing database code, Phoenix controllers, or LiveView components.

### references/testing_practices.md
Comprehensive testing guidance covering behavior-based testing, ExUnit fundamentals, context testing, controller testing, LiveView testing, mocking, and test data management. Load this when evaluating test coverage and quality.

**How to use references:**
- Load references on-demand when specific questions arise
- Don't load all references at once; be selective based on the code being reviewed
- Reference specific sections when providing feedback
- Use grep patterns to find relevant sections quickly if references are large
