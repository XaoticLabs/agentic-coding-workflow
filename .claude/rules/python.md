---
paths:
  - "**/*.py"
---

# Python Conventions

## Toolchain

- **Package manager**: `uv` — use `uv run` to execute tools, `uv add` for dependencies
- **Linter + formatter**: `ruff` — formatting and linting (replaces black, isort, flake8, pylint)
- **Type checker**: `basedpyright` — strict mode by default
- **Test runner**: `pytest` via `uv run pytest`
- **Validation**: `pydantic` at system boundaries

## Human-Judgment Rules (not caught by tooling)

### Type Design
- Prefer `collections.abc` abstract types (`Sequence`, `Mapping`, `Iterable`) in function signatures — accept broad, return narrow
- Use `Self` for methods returning their own type
- Annotate class variables with `ClassVar[T]`
- Always parameterize generics (`dict[str, int]` not bare `dict`)

### Naming (beyond what ruff N8xx catches)
- No type-encoding in names: `user_dict` → `users`
- No abbreviations by deleting letters: `msg` ok, `usr` not
- Don't shadow builtins: `list`, `type`, `id`, `input`, `format`
- Descriptive names — can you understand purpose without reading the body?

### Pydantic
- Pydantic v2 API only: `model_dump()`, `model_validate()`, `ConfigDict(...)`, `field_validator`
- Pydantic for system boundaries — dataclasses for internal data
- `BaseSettings` for config, not manual env var parsing
- `ConfigDict(strict=True)` where type coercion is undesirable

### Design
- Keep responsibilities and control flow clear; choose decomposition from cohesion and readability rather than fixed length or nesting limits
- Never `@staticmethod` — use module-level function
- `@classmethod` only for alternative constructors
- `@property` only for computed attributes — not wrapping trivial private attrs
- Keyword-only args (`*`) for functions with 3+ optional params
- Single return type per function — all branches return explicitly
- Comprehensions: single for/if only — use loops for complex cases

### Error Handling
- Minimize code in `try` blocks — only the line(s) that can raise
- `raise X from Y` for chaining — don't swallow context
- Never `assert` for validation (stripped with `-O`)
- No `return`/`break`/`continue` inside `finally`
- Custom exceptions: inherit `Exception`, name ends in `Error`

### Async
- Concurrent independent operations use `asyncio.gather()` — not sequential awaits
- Task results checked — no fire-and-forget without error handling
- Async context managers for connection/session cleanup

### Security (easy to miss)
- File paths validated against traversal (`Path.resolve()` + prefix check)
- JWTs: expiration set, `algorithms=` explicitly specified
- Session cookies: `httponly=True`, `secure=True`, `samesite='Strict'`
- External request timeouts always set
- Sensitive data never logged (passwords, tokens, PII)
- Input validated at every system boundary (pydantic preferred)

### Logging
- Always `%`-style: `logger.info("User %s", name)` — not f-strings (lazy evaluation)
