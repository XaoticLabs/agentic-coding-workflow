# Python PR Review Checklist

Consolidated checklist covering code quality, modern idioms, security, and testing for Python 3.10+ PRs.

## Pattern Consistency (Highest Priority)
- Does the code follow existing codebase patterns?
- Are similar problems solved the same way?
- If introducing a new pattern, is it justified?
- Consistent naming conventions, error handling, logging?

## Type Hints & Modern Syntax
- All public functions type-hinted
- `dict[str, int]` not `Dict[str, int]` (3.10+)
- `X | None` not `Optional[X]`
- `match` statements for complex conditionals
- Dataclasses for data containers
- f-strings for formatting
- `pathlib.Path` over `os.path`

## Code Quality
- Functions under 50 lines, single responsibility
- Nesting under 3 levels deep
- No code duplication
- Clear, descriptive names (no abbreviations)
- Magic numbers replaced with constants

## Error Handling
- Specific exceptions (not bare `except:` or `except Exception`)
- Informative, actionable error messages
- Resources cleaned up in error cases (context managers)
- Custom exceptions for domain-specific errors

## Security (Flag as BLOCKER)

**Injection:**
- SQL queries parameterized (`cursor.execute(query, (param,))`) — never f-strings
- No `subprocess.run(..., shell=True)` with user input
- No `eval()`/`exec()` with user input
- File paths validated against traversal (`Path.resolve()` + prefix check)

**Auth & Secrets:**
- Passwords hashed with bcrypt/argon2, never plain text or MD5/SHA1
- Secrets from environment variables, never hardcoded
- JWTs include expiration, use strong secrets, verify with `algorithms=["HS256"]`
- Session cookies: `httponly=True`, `secure=True`, `samesite='Strict'`
- Cryptographically secure randoms via `secrets` module, not `random`

**Defense:**
- Input validated (Pydantic preferred)
- HTML output sanitized (XSS prevention)
- File upload size limits enforced
- External request timeouts set
- Sensitive data never logged

## Async Patterns (if applicable)
- All async functions properly awaited
- Multiple operations gathered with `asyncio.gather()`
- No blocking calls in async code
- `asyncio.run()` only at entry points

## Testing (Flag missing tests as BLOCKER)
- New features have tests proving they work
- Bug fixes have regression tests
- Happy path + error cases + edge cases covered
- Tests are behavior-based, not implementation-based
- Clear test names describing what they test
- Proper assertions (not just running code)

## Performance
- No N+1 queries
- Large datasets use generators/streaming
- Sets for membership testing, not lists
- Expensive operations cached when appropriate

## Dependencies & Imports
- New dependencies necessary and actively maintained?
- Versions pinned
- Import order: stdlib → third-party → local
- No wildcard imports
