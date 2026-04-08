# Python Style Guide Reference

Consolidated from Google Python Style Guide and PEP 8, adapted for **ruff**, **basedpyright**, **uv**, **pydantic**.

This guide covers only what requires **human judgment** during review. Formatting, import ordering, deprecated syntax, bare excepts, unused imports, and similar mechanical issues are caught and auto-fixed by ruff and basedpyright — don't flag them in review.

---

## 1. Imports — What Ruff Won't Catch

Ruff handles ordering, unused imports, deprecated typing imports, and `Optional` → union rewrites.

**Reviewer must check:**
- Import modules, not individual symbols (exception: `typing`, `collections.abc`) [Google 2.2]
- Absolute imports only — no relative imports [Google 2.3]
- `TYPE_CHECKING` imports go inside `if typing.TYPE_CHECKING:` block — not at top level
- Aliases only for standard abbreviations (`np`, `pd`) — don't alias to obscure origin

```python
# Good
from __future__ import annotations

import os
from collections.abc import Sequence

import httpx
from pydantic import BaseModel

from myproject.models import User

# Bad — hiding origin
from myproject.services.user_management import UserService as US
```

---

## 2. Naming — Semantic Quality

Ruff enforces case conventions (N8xx). Reviewers catch **meaning** problems:

**Red flags:**
- Type-encoding: `user_dict` → `users`, `name_str` → `name`
- Abbreviations by deleting letters: `msg` is fine, `usr`, `cfg`, `mgr` are not
- Shadowing builtins: `list`, `type`, `id`, `input`, `format`, `hash`
- Vague names: `data`, `result`, `info`, `temp`, `stuff` — name the *what*
- Boolean names that don't read as questions: `active` → `is_active`
- Exception classes missing `Error` suffix

---

## 3. Type Annotations — Design Decisions

basedpyright catches missing annotations and type errors. Reviewers catch **design** issues:

### Accept Broad, Return Narrow
```python
# Good — caller can pass any sequence
def process(items: Sequence[str]) -> list[str]: ...

# Bad — unnecessarily restrictive
def process(items: list[str]) -> list[str]: ...
```

Use `Sequence`, `Mapping`, `Iterable` in parameters. Return concrete types.

### Self for Fluent APIs
```python
from typing import Self

class Builder:
    def set_name(self, name: str) -> Self:
        self._name = name
        return self
```

### Always Parameterize Generics
```python
cache: dict[str, list[int]] = {}   # Good
cache: dict = {}                    # Bad — implicit Any, basedpyright may miss
```

---

## 4. Docstrings — Content Quality

Ruff checks presence and format. Reviewers check **content**:

```python
def fetch_users(
    role: Role,
    *,
    active_only: bool = True,
    limit: int = 100,
) -> list[User]:
    """Fetch users matching the given role.

    Queries the user service with pagination. Results are cached
    for 60 seconds per role.

    Args:
        role: The role to filter by.
        active_only: If True, exclude deactivated accounts.
        limit: Maximum number of users to return.

    Returns:
        Users sorted by creation date, newest first.
        Empty list if no matches.

    Raises:
        ServiceUnavailableError: If the user service is down
            after all retry attempts.
    """
```

**Key judgment calls:**
- Summary line uses imperative mood ("Fetch users" not "Fetches users")
- `Args:` omits type info when annotations are present (no redundancy)
- `Returns:` describes *semantics* beyond what the type says (ordering, emptiness behavior)
- `Raises:` only lists exceptions *callers should handle* — not `TypeError` from wrong args
- `@property` described as attribute: `"""The user's display name."""`
- Comments explain *why*, never *what*

---

## 5. Function and Class Design

### Functions
- Under ~40 lines — decompose if longer [Google 3.18]
- All branches return explicitly (no implicit `None` mixed with real values)
- Use `*` for keyword-only args when 3+ optional params:
  ```python
  def connect(host: str, port: int, *, ssl: bool = True, timeout: float = 30.0): ...
  ```

### Nested Functions
- Only when closing over a local variable (not `self`/`cls`)
- Otherwise, `_private` module-level function — keeps it testable [Google 2.6]

### Class Design
- Never `@staticmethod` — module-level function instead [Google 2.17]
- `@classmethod` only for alternative constructors (`from_dict`, `from_csv`)
- `@property` for computed/derived attributes only — don't wrap trivially private attrs
- Expensive operations never behind `@property` — callers expect cheap access

---

## 6. Error Handling — Judgment Calls

Ruff catches bare excepts and missing `from` in re-raises. Reviewers catch:

```python
# Good — specific, informative, preserves context
try:
    user = await fetch_user(user_id)
except httpx.TimeoutException:
    raise ServiceUnavailableError(
        f"User service timeout for {user_id}"
    ) from None
except httpx.HTTPStatusError as exc:
    if exc.response.status_code == 404:
        return None
    raise
```

**Judgment calls:**
- Is the `try` block minimal? Large try blocks mask unrelated errors
- Does `raise ... from None` intentionally suppress the chain, or accidentally?
- Are error messages actionable? Include context (IDs, paths, states)
- Is `except Exception` with re-raise genuinely needed, or too broad?
- Never `assert` for validation — stripped with `-O` flag [Google 2.4]
- Never `return`/`break`/`continue` in `finally` — silently cancels exceptions

---

## 7. Pydantic Patterns

### Pydantic v2 API (flag v1 patterns)
```python
from pydantic import BaseModel, ConfigDict, Field, field_validator

class CreateUserRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    name: str = Field(min_length=1, max_length=255)
    email: str = Field(pattern=r"^[\w.+-]+@[\w-]+\.[\w.]+$")
    role: Role = Role.USER
    tags: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()
```

**v1 → v2 flags (not caught by linters):**
- `class Config:` → `model_config = ConfigDict(...)`
- `.dict()` → `model_dump()`
- `.parse_obj()` → `model_validate()`
- `.schema()` → `model_json_schema()`
- `@validator` → `field_validator`
- `@root_validator` → `model_validator`

### Right Tool for the Job
| Use case | Tool |
|----------|------|
| API input/output, external data | `pydantic.BaseModel` |
| Internal data containers | `dataclasses.dataclass` |
| Immutable value objects | `@dataclass(frozen=True)` or `NamedTuple` |
| Settings/config | `pydantic_settings.BaseSettings` |
| Simple enums | `enum.Enum` / `StrEnum` |

**Flag:** pydantic models used for purely internal data that never crosses a boundary.

---

## 8. Async — Concurrency Mistakes

Ruff catches blocking calls in async code (`ASYNC1xx`). Reviewers catch:

```python
# Bad — sequential when concurrent is possible
user = await fetch_user(user_id)
perms = await fetch_permissions(user_id)
prefs = await fetch_preferences(user_id)

# Good — concurrent independent operations
user, perms, prefs = await asyncio.gather(
    fetch_user(user_id),
    fetch_permissions(user_id),
    fetch_preferences(user_id),
)
```

**Judgment calls:**
- Are sequential awaits actually independent? (gather them)
- Are task results checked? Fire-and-forget loses errors silently
- Is `asyncio.run()` used only at the entry point?
- Are connections/sessions cleaned up with async context managers?

---

## 9. Security — Easy to Miss

Ruff catches some security issues (S-rules), but these require human review:

- **Path traversal:** `Path.resolve()` + prefix check before file operations with user input
- **JWT:** expiration set, `algorithms=["HS256"]` explicitly specified (default accepts `none`)
- **Session cookies:** `httponly=True`, `secure=True`, `samesite='Strict'` — all three
- **External requests:** timeouts always set (httpx, requests, aiohttp)
- **Logging:** sensitive data never logged (passwords, tokens, PII, credit cards)
- **Input validation:** every system boundary uses pydantic or explicit checks
- **Deserialization:** `pickle.loads()` / `yaml.load()` with untrusted input

---

## 10. Testing — Quality, Not Just Presence

CI catches missing tests and failures. Reviewers catch **quality**:

- **Names describe behavior:** `test_create_user_with_duplicate_email_raises_conflict`
- **Assertions are specific:** `assert result.status == "active"` not `assert result`
- **Exception testing uses match:** `pytest.raises(ValidationError, match="email")`
- **Parametrize for variants** — don't copy-paste the same test with different inputs
- **Fixtures over setup/teardown** — composition over inheritance
- **Mock external deps only** — never mock the unit under test
- **Tests cover the *why*:** if a bug fix, the test should fail without the fix

---

## 11. Performance — Patterns That Look Fine But Aren't

- **Sequential awaits** on independent operations (see Async section)
- **N+1 queries** — loading related objects in a loop instead of eager/batch load
- **String concatenation in loops** — `+=` in loop vs `"".join()`
- **List where set works** — membership testing on large collections
- **Missing timeouts** on external calls — can hang indefinitely
- **Generators ignored** — building full list when caller only needs iteration

---

## Ruff Rule Reference (for review citations)

When citing issues that overlap with ruff rules, use the ID for specificity:

| Category | Prefix | Example Rules |
|----------|--------|---------------|
| flake8-bugbear | `B` | `B006` mutable default, `B007` unused loop var |
| flake8-simplify | `SIM` | `SIM102` collapsible if, `SIM110` reimplemented any/all |
| flake8-async | `ASYNC` | `ASYNC100` blocking in async |
| Ruff-specific | `RUF` | `RUF012` mutable class default |
| bandit | `S` | `S101` assert, `S608` SQL injection, `S602` shell injection |
