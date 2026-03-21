# Python PR Review Checklist

This comprehensive checklist covers all aspects of reviewing Python pull requests for code quality, readability, maintainability, and resilience.

## Severity Levels

- **CRITICAL**: Must be fixed before merge (security issues, broken functionality, data loss risks)
- **HIGH**: Should be fixed before merge (major code quality issues, missing tests, significant maintainability problems)
- **MEDIUM**: Should be addressed (code style issues, minor maintainability concerns, opportunities for improvement)
- **LOW**: Nice to have (suggestions, optimizations, style preferences)

---

## 1. Pattern Consistency

### Check Against Existing Codebase Patterns
- [ ] Does the code follow the same patterns used elsewhere in the codebase?
- [ ] Are similar problems solved in similar ways?
- [ ] If introducing a new pattern, is it necessary and justified?
- [ ] Are naming conventions consistent with the rest of the codebase?
- [ ] Is the file/directory structure consistent with existing organization?

**RED FLAGS:**
- ❌ Introducing a new ORM when one already exists
- ❌ Different error handling patterns from the rest of the codebase
- ❌ Inconsistent naming conventions (camelCase in a snake_case codebase)
- ❌ Different logging approaches from existing code
- ❌ Duplicating functionality that exists elsewhere

**Questions to Ask:**
- Why is this pattern different from `<similar_file_in_codebase>`?
- Can this use the existing `<pattern/utility>` instead?
- Is this new dependency necessary?

---

## 2. Code Quality and Readability

### Type Hints and Type Safety
- [ ] Are all public functions fully type-hinted?
- [ ] Are complex types properly defined (TypedDict, dataclass, etc.)?
- [ ] Do type hints use modern syntax (3.10+: `dict[str, int]` not `Dict[str, int]`)?
- [ ] Are union types using `|` instead of `Union`?
- [ ] Are optional types using `| None` instead of `Optional`?

**Examples:**
```python
# ❌ CRITICAL: Missing type hints on public API
def process_user(data):
    return data["name"]

# ✅ Good: Comprehensive type hints
def process_user(data: dict[str, Any]) -> str:
    return data["name"]
```

### Naming and Clarity
- [ ] Are variable names clear and descriptive?
- [ ] Are function names action-oriented (verbs)?
- [ ] Are class names nouns that describe their purpose?
- [ ] Are magic numbers replaced with named constants?
- [ ] Are abbreviations avoided unless they're domain-standard?

**Examples:**
```python
# ❌ HIGH: Poor naming
def proc(d, t=10):
    for i in range(t):
        x = d[i]

# ✅ Good: Clear naming
def process_data_batch(data: list[DataPoint], timeout_seconds: int = 10) -> None:
    for index in range(timeout_seconds):
        data_point = data[index]
```

### Function Length and Complexity
- [ ] Are functions under 50 lines (ideally under 30)?
- [ ] Does each function do one thing well?
- [ ] Are nested loops/conditionals under 3 levels deep?
- [ ] Can complex functions be broken into smaller helpers?

**RED FLAGS:**
- ❌ Function with 100+ lines
- ❌ Deeply nested loops (3+ levels)
- ❌ Functions that do multiple unrelated things
- ❌ Long if-elif chains that could use pattern matching

### Code Duplication
- [ ] Is there duplicated code that should be extracted?
- [ ] Are similar operations abstracted into reusable functions?
- [ ] Is copy-pasted code eliminated?

---

## 3. Modern Python Idioms (3.10+)

### Modern Features Usage
- [ ] Uses structural pattern matching for complex conditionals?
- [ ] Uses dataclasses instead of manual `__init__`?
- [ ] Uses f-strings for all string formatting?
- [ ] Uses `pathlib.Path` instead of `os.path`?
- [ ] Uses context managers for resource management?
- [ ] Uses list/dict comprehensions where appropriate?

**Examples:**
```python
# ❌ MEDIUM: Should use pattern matching
if event["type"] == "login" and "user_id" in event:
    process_login(event["user_id"])
elif event["type"] == "logout" and "user_id" in event:
    process_logout(event["user_id"])

# ✅ Good: Pattern matching
match event:
    case {"type": "login", "user_id": user_id}:
        process_login(user_id)
    case {"type": "logout", "user_id": user_id}:
        process_logout(user_id)
```

### Anti-Patterns to Flag
- [ ] No mutable default arguments
- [ ] No bare `except:` clauses
- [ ] No wildcard imports (`from module import *`)
- [ ] No manual resource management (missing context managers)
- [ ] No string concatenation in loops

---

## 4. Error Handling and Resilience

### Exception Handling
- [ ] Are exceptions specific (not catching broad `Exception`)?
- [ ] Are error messages informative and actionable?
- [ ] Are resources properly cleaned up in error cases?
- [ ] Are exceptions documented in docstrings?
- [ ] Are custom exceptions used for domain-specific errors?

**Examples:**
```python
# ❌ CRITICAL: Swallowing all exceptions
try:
    result = critical_operation()
except:
    pass

# ❌ HIGH: Too broad exception handling
try:
    data = json.loads(response)
except Exception:
    return None

# ✅ Good: Specific exception handling
try:
    data = json.loads(response)
except json.JSONDecodeError as e:
    logger.error(f"Failed to parse JSON response: {e}")
    raise ValidationError(f"Invalid JSON: {e}") from e
```

### Defensive Programming
- [ ] Are inputs validated?
- [ ] Are boundary conditions handled?
- [ ] Are null/None values checked before use?
- [ ] Are list/dict accesses safe (using `.get()`, checking bounds)?
- [ ] Are edge cases tested?

**RED FLAGS:**
- ❌ Direct dictionary access without checking (`data["key"]`)
- ❌ List access without bounds checking
- ❌ Assuming external data is well-formed
- ❌ No validation of user inputs

### Logging and Observability
- [ ] Are errors logged with appropriate levels?
- [ ] Do logs include context (IDs, timestamps, etc.)?
- [ ] Are sensitive data (passwords, tokens) not logged?
- [ ] Are important state changes logged?

---

## 5. Async/Await Patterns (if applicable)

### Proper Async Usage
- [ ] Are async functions properly awaited?
- [ ] Are multiple async operations gathered efficiently?
- [ ] Are async context managers used for async resources?
- [ ] Are blocking operations not mixed with async code?
- [ ] Is `asyncio.run()` used only at entry points?

**Examples:**
```python
# ❌ CRITICAL: Forgetting await
async def bad():
    result = fetch_data()  # Returns coroutine, not data!

# ✅ Good: Proper await
async def good() -> Data:
    result = await fetch_data()
    return result

# ✅ Good: Gathering multiple operations
async def fetch_all(ids: list[int]) -> list[Data]:
    tasks = [fetch_data(id) for id in ids]
    return await asyncio.gather(*tasks)
```

---

## 6. Test Coverage and Quality

### Test Existence
- [ ] Are new features covered by tests?
- [ ] Are bug fixes accompanied by regression tests?
- [ ] Are edge cases tested?
- [ ] Are error paths tested?
- [ ] Are tests added for all public APIs?

**CRITICAL REQUIREMENT:**
Every new feature or bug fix MUST include tests that prove it works.

### Test Quality
- [ ] Do tests have clear names describing what they test?
- [ ] Are tests independent (can run in any order)?
- [ ] Do tests use proper assertions (not just running code)?
- [ ] Are tests not overly complex?
- [ ] Do tests test behavior, not implementation?

**Examples:**
```python
# ❌ HIGH: Unclear test name
def test_user():
    pass

# ✅ Good: Clear test name
def test_user_creation_with_valid_email_succeeds():
    pass

# ❌ HIGH: No assertion
def test_process_data():
    process_data([1, 2, 3])  # Just runs, doesn't verify

# ✅ Good: Clear assertion
def test_process_data_doubles_values():
    result = process_data([1, 2, 3])
    assert result == [2, 4, 6]
```

### Test Coverage Metrics
- [ ] Are new files covered at >80%?
- [ ] Are modified functions tested?
- [ ] Are all code paths exercised?

**Questions to Ask:**
- What happens if this input is empty?
- What happens if this API call fails?
- What happens at boundary values (0, -1, MAX)?
- Is this race condition tested?

---

## 7. Proof of Functionality

### Evidence Required
- [ ] Are there tests that demonstrate the feature works?
- [ ] Is there manual testing evidence if automated tests are insufficient?
- [ ] Are before/after comparisons provided for bug fixes?
- [ ] Are performance improvements quantified?

**For Feature PRs:**
- [ ] Tests showing the feature works in the happy path
- [ ] Tests showing the feature handles errors gracefully
- [ ] Tests showing edge cases are handled
- [ ] Evidence of integration with existing features

**For Bug Fix PRs:**
- [ ] Regression test that would fail on old code
- [ ] Evidence that the fix resolves the issue
- [ ] Verification that the fix doesn't break other functionality

---

## 8. Security Considerations

### Common Security Issues
- [ ] Are SQL queries parameterized (no string concatenation)?
- [ ] Are user inputs sanitized?
- [ ] Are secrets not hardcoded?
- [ ] Are file paths validated (no path traversal)?
- [ ] Are authentication/authorization checks in place?
- [ ] Are dependencies from trusted sources?
- [ ] Are known vulnerable dependencies avoided?

**Examples:**
```python
# ❌ CRITICAL: SQL injection vulnerability
query = f"SELECT * FROM users WHERE id = {user_id}"

# ✅ Good: Parameterized query
query = "SELECT * FROM users WHERE id = ?"
cursor.execute(query, (user_id,))

# ❌ CRITICAL: Hardcoded secret
API_KEY = "sk_live_abc123..."

# ✅ Good: Secret from environment
import os
API_KEY = os.environ["API_KEY"]
```

---

## 9. Performance and Scalability

### Performance Patterns
- [ ] Are database queries efficient (no N+1 queries)?
- [ ] Are large datasets handled with generators/streaming?
- [ ] Are expensive operations cached when appropriate?
- [ ] Are set operations used for membership testing (not lists)?
- [ ] Are list comprehensions preferred over map/filter?

**Examples:**
```python
# ❌ HIGH: Loading entire file into memory
def process_large_file(path: str) -> list[str]:
    with open(path) as f:
        return [line.strip() for line in f]

# ✅ Good: Generator for memory efficiency
def process_large_file(path: str) -> Generator[str, None, None]:
    with open(path) as f:
        for line in f:
            yield line.strip()
```

### Scalability Concerns
- [ ] Will this code handle 10x current load?
- [ ] Are there potential memory leaks?
- [ ] Are there potential bottlenecks?
- [ ] Is caching used appropriately?

---

## 10. Documentation and Maintainability

### Code Documentation
- [ ] Are all public functions documented with docstrings?
- [ ] Do docstrings follow a consistent format (Google/NumPy style)?
- [ ] Are complex algorithms explained with comments?
- [ ] Are TODOs/FIXMEs justified and tracked?
- [ ] Is the PR description clear and complete?

**Examples:**
```python
# ✅ Good: Comprehensive docstring
def calculate_user_metrics(
    user_id: int,
    *,
    start_date: datetime | None = None,
    include_derived: bool = False
) -> UserMetrics:
    """Calculate aggregate metrics for a user.

    Args:
        user_id: The ID of the user to analyze
        start_date: Optional start date for metrics calculation.
            If None, uses all available data.
        include_derived: Whether to include derived metrics like
            ratios and percentages in the result.

    Returns:
        UserMetrics object containing calculated metrics

    Raises:
        UserNotFoundError: If the user ID doesn't exist
        ValueError: If start_date is in the future

    Example:
        >>> metrics = calculate_user_metrics(123, include_derived=True)
        >>> print(metrics.total_actions)
        42
    """
```

### PR Description Quality
- [ ] Does the PR description explain WHY the change is needed?
- [ ] Does it explain WHAT changed at a high level?
- [ ] Are breaking changes clearly called out?
- [ ] Are migration steps provided if needed?
- [ ] Are screenshots/examples included for UI changes?

---

## 11. Dependencies and Imports

### Dependency Management
- [ ] Are new dependencies necessary?
- [ ] Are dependencies pinned to specific versions?
- [ ] Are dependencies actively maintained?
- [ ] Are dependency licenses compatible?
- [ ] Are dependencies from trusted sources?

### Import Organization
- [ ] Are imports organized (stdlib, third-party, local)?
- [ ] Are imports alphabetized within sections?
- [ ] Are wildcard imports avoided?
- [ ] Are unused imports removed?

---

## 12. Git and Version Control

### Commit Quality
- [ ] Are commits atomic (one logical change per commit)?
- [ ] Are commit messages descriptive?
- [ ] Is the commit history clean (no "fix typo" commits)?
- [ ] Are merge commits avoided (rebase workflow)?

### PR Scope
- [ ] Is the PR focused (one feature/fix)?
- [ ] Is the PR a reasonable size (<500 lines ideally)?
- [ ] Are unrelated changes separated into different PRs?

---

## Common Review Comments Template

### Pattern Inconsistency
```
**SEVERITY: HIGH**
This introduces a new pattern for [X], but the codebase uses [Y] pattern in [file:line].
For consistency, please use the existing pattern or provide justification for the new approach.

Example: [link to existing pattern]
```

### Missing Tests
```
**SEVERITY: CRITICAL**
This feature/fix lacks tests. Please add tests that demonstrate:
1. The happy path works as expected
2. Error cases are handled correctly
3. Edge cases are covered

Line: [file:line]
```

### Type Safety Issue
```
**SEVERITY: HIGH**
Missing type hints for public function. This makes the code harder to understand and maintain.

File: [file:line]
Expected:
```python
def process_data(items: list[dict[str, Any]]) -> ProcessedResult:
    ...
```
```

### Security Concern
```
**SEVERITY: CRITICAL**
Potential security vulnerability: [describe issue]

File: [file:line]
This could lead to [injection/data leak/etc].
Please use [recommended secure approach].
```
