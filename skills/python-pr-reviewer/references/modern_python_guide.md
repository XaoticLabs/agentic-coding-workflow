# Modern Python 3.10+ Guide

This guide covers modern Python idioms, patterns, and best practices for Python 3.10 and above.

## Type Hints and Type Safety

### Always Use Type Hints
Modern Python code should use comprehensive type hints for function signatures, class attributes, and variables where clarity is needed.

```python
# ❌ Avoid: Missing type hints
def process_user(data):
    return data["name"]

# ✅ Prefer: Clear type hints
def process_user(data: dict[str, Any]) -> str:
    return data["name"]

# ✅ Even better: Use TypedDict or dataclass
from typing import TypedDict

class UserData(TypedDict):
    name: str
    email: str
    age: int

def process_user(data: UserData) -> str:
    return data["name"]
```

### Modern Type Syntax (3.10+)
Use the new union syntax with `|` instead of `Union` and built-in generics instead of importing from `typing`.

```python
# ❌ Avoid: Old-style Union
from typing import Union, Optional, List, Dict

def find_user(user_id: int) -> Optional[Dict[str, str]]:
    pass

# ✅ Prefer: Modern syntax
def find_user(user_id: int) -> dict[str, str] | None:
    pass

# ✅ Multiple types
def process(value: int | str | float) -> list[str]:
    pass
```

### Use `TypeAlias` for Complex Types
```python
from typing import TypeAlias

# ✅ Clear and reusable
UserId: TypeAlias = int
UserDict: TypeAlias = dict[str, str | int]
ResultType: TypeAlias = tuple[bool, str | None]

def get_user(user_id: UserId) -> UserDict | None:
    pass
```

## Structural Pattern Matching (3.10+)

### Use `match` for Complex Conditionals
Pattern matching is more readable and maintainable than long if-elif chains.

```python
# ❌ Avoid: Long if-elif chains
def handle_response(status, data):
    if status == 200:
        return {"success": True, "data": data}
    elif status == 404:
        return {"success": False, "error": "Not found"}
    elif status >= 500:
        return {"success": False, "error": "Server error"}
    else:
        return {"success": False, "error": "Unknown"}

# ✅ Prefer: Pattern matching
def handle_response(status: int, data: Any) -> dict[str, Any]:
    match status:
        case 200:
            return {"success": True, "data": data}
        case 404:
            return {"success": False, "error": "Not found"}
        case status if status >= 500:
            return {"success": False, "error": "Server error"}
        case _:
            return {"success": False, "error": "Unknown"}
```

### Pattern Matching with Data Structures
```python
# ✅ Pattern match on structure
def process_event(event: dict[str, Any]) -> str:
    match event:
        case {"type": "user_login", "user_id": user_id}:
            return f"User {user_id} logged in"
        case {"type": "user_logout", "user_id": user_id}:
            return f"User {user_id} logged out"
        case {"type": "error", "message": msg}:
            return f"Error: {msg}"
        case _:
            return "Unknown event"
```

## Dataclasses and Modern Class Patterns

### Use `dataclass` for Data Containers
Dataclasses reduce boilerplate and are more maintainable than traditional classes.

```python
# ❌ Avoid: Manual __init__ and __repr__
class User:
    def __init__(self, name: str, email: str, age: int):
        self.name = name
        self.email = email
        self.age = age

    def __repr__(self):
        return f"User(name={self.name}, email={self.email}, age={self.age})"

# ✅ Prefer: Dataclass
from dataclasses import dataclass

@dataclass
class User:
    name: str
    email: str
    age: int
```

### Dataclass Features
```python
from dataclasses import dataclass, field

# ✅ Frozen dataclass (immutable)
@dataclass(frozen=True)
class Point:
    x: float
    y: float

# ✅ Default values and factories
@dataclass
class Config:
    name: str
    debug: bool = False
    options: dict[str, Any] = field(default_factory=dict)

# ✅ Post-init processing
@dataclass
class Rectangle:
    width: float
    height: float
    area: float = field(init=False)

    def __post_init__(self):
        self.area = self.width * self.height
```

## Context Managers and Resource Management

### Always Use Context Managers
Proper resource management is critical for maintainable code.

```python
# ❌ Avoid: Manual resource management
def read_file(path):
    f = open(path)
    data = f.read()
    f.close()
    return data

# ✅ Prefer: Context manager
def read_file(path: str) -> str:
    with open(path) as f:
        return f.read()

# ✅ Multiple context managers
def copy_file(src: str, dst: str) -> None:
    with open(src) as f_in, open(dst, 'w') as f_out:
        f_out.write(f_in.read())
```

### Create Custom Context Managers
```python
from contextlib import contextmanager
from typing import Generator

# ✅ Custom context manager for timing
@contextmanager
def timer(name: str) -> Generator[None, None, None]:
    import time
    start = time.time()
    try:
        yield
    finally:
        duration = time.time() - start
        print(f"{name} took {duration:.2f}s")

# Usage
with timer("database_query"):
    # ... perform query ...
    pass
```

## Async/Await Best Practices

### Proper Async Patterns
```python
import asyncio
from typing import Coroutine

# ✅ Async function with proper type hints
async def fetch_user(user_id: int) -> dict[str, Any]:
    # Simulate async operation
    await asyncio.sleep(0.1)
    return {"id": user_id, "name": "John"}

# ✅ Gathering multiple async operations
async def fetch_multiple_users(user_ids: list[int]) -> list[dict[str, Any]]:
    tasks = [fetch_user(user_id) for user_id in user_ids]
    return await asyncio.gather(*tasks)

# ✅ Async context manager
class AsyncDatabaseConnection:
    async def __aenter__(self):
        # Open connection
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Close connection
        pass
```

### Avoid Common Async Pitfalls
```python
# ❌ Avoid: Forgetting await
async def bad_example():
    result = fetch_user(1)  # Returns coroutine, not result!
    return result

# ✅ Prefer: Always await
async def good_example() -> dict[str, Any]:
    result = await fetch_user(1)
    return result

# ❌ Avoid: Running async in sync context without event loop
def sync_function():
    result = fetch_user(1)  # Error!

# ✅ Prefer: Use asyncio.run for entry point
def sync_function() -> dict[str, Any]:
    return asyncio.run(fetch_user(1))
```

## Error Handling and Exceptions

### Specific Exception Handling
```python
# ❌ Avoid: Bare except
try:
    result = risky_operation()
except:
    pass

# ❌ Avoid: Catching too broad
try:
    result = parse_json(data)
except Exception:
    return None

# ✅ Prefer: Specific exceptions
from json import JSONDecodeError

try:
    result = parse_json(data)
except JSONDecodeError as e:
    logger.error(f"Failed to parse JSON: {e}")
    return None
except KeyError as e:
    logger.error(f"Missing required key: {e}")
    return None
```

### Custom Exceptions
```python
# ✅ Create domain-specific exceptions
class UserNotFoundError(Exception):
    """Raised when a user cannot be found."""
    def __init__(self, user_id: int):
        self.user_id = user_id
        super().__init__(f"User {user_id} not found")

class ValidationError(Exception):
    """Raised when data validation fails."""
    def __init__(self, field: str, message: str):
        self.field = field
        super().__init__(f"{field}: {message}")
```

### Exception Groups (3.11+)
```python
# ✅ Handle multiple exceptions together
try:
    results = await asyncio.gather(*tasks, return_exceptions=True)
except* ValueError as eg:
    for exc in eg.exceptions:
        logger.error(f"Validation error: {exc}")
except* ConnectionError as eg:
    for exc in eg.exceptions:
        logger.error(f"Connection error: {exc}")
```

## Iterators and Generators

### Use Generators for Large Datasets
```python
# ❌ Avoid: Loading everything into memory
def read_large_file(path: str) -> list[str]:
    with open(path) as f:
        return [line.strip() for line in f]

# ✅ Prefer: Generator for memory efficiency
def read_large_file(path: str) -> Generator[str, None, None]:
    with open(path) as f:
        for line in f:
            yield line.strip()

# ✅ Generator expression for one-off iteration
lines = (line.strip() for line in open(path))
```

### Iterator Tools
```python
from itertools import islice, chain, groupby

# ✅ Efficient iteration
def process_in_batches(items: list[Any], batch_size: int) -> Generator[list[Any], None, None]:
    iterator = iter(items)
    while batch := list(islice(iterator, batch_size)):
        yield batch

# ✅ Chaining iterators
combined = chain(items1, items2, items3)

# ✅ Grouping
from operator import itemgetter
data = [{"type": "A", "val": 1}, {"type": "A", "val": 2}, {"type": "B", "val": 3}]
grouped = groupby(sorted(data, key=itemgetter("type")), key=itemgetter("type"))
```

## Modern Dictionary and Collection Patterns

### Dictionary Merge Operators (3.9+)
```python
# ❌ Avoid: Manual merging
def merge_configs(default, user):
    result = default.copy()
    result.update(user)
    return result

# ✅ Prefer: Merge operator
def merge_configs(default: dict, user: dict) -> dict:
    return default | user

# ✅ In-place merge
config |= user_overrides
```

### Dictionary Comprehensions
```python
# ✅ Clean dictionary transformations
users = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
user_map = {user["id"]: user["name"] for user in users}

# ✅ Filtering in comprehension
active_users = {uid: name for uid, name in user_map.items() if uid > 0}
```

### Use `get()` with Defaults
```python
# ❌ Avoid: Manual key checking
if "key" in data:
    value = data["key"]
else:
    value = default_value

# ✅ Prefer: get() with default
value = data.get("key", default_value)

# ✅ Use setdefault for mutable defaults
from collections import defaultdict

# For accumulating values
data_by_category: defaultdict[str, list[str]] = defaultdict(list)
data_by_category[category].append(item)
```

## Function Best Practices

### Use Keyword-Only Arguments
```python
# ❌ Avoid: All positional arguments
def create_user(name, email, age, active, role):
    pass

# ✅ Prefer: Keyword-only for clarity
def create_user(
    name: str,
    email: str,
    *,
    age: int | None = None,
    active: bool = True,
    role: str = "user"
) -> User:
    pass

# Forces clear call: create_user("John", "john@example.com", age=30, role="admin")
```

### Avoid Mutable Default Arguments
```python
# ❌ Avoid: Mutable default
def add_item(item: str, items: list[str] = []) -> list[str]:
    items.append(item)
    return items

# ✅ Prefer: None with initialization
def add_item(item: str, items: list[str] | None = None) -> list[str]:
    if items is None:
        items = []
    items.append(item)
    return items
```

### Use `functools` for Function Utilities
```python
from functools import lru_cache, cached_property, wraps

# ✅ Cache expensive computations
@lru_cache(maxsize=128)
def expensive_computation(n: int) -> int:
    return sum(i * i for i in range(n))

# ✅ Cached property for classes
class DataProcessor:
    @cached_property
    def processed_data(self) -> list[int]:
        # Expensive computation done once
        return [x * 2 for x in self.raw_data]

# ✅ Preserve function metadata in decorators
def my_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        # ... decorator logic ...
        return func(*args, **kwargs)
    return wrapper
```

## Path Handling with `pathlib`

```python
from pathlib import Path

# ❌ Avoid: String manipulation
import os
path = os.path.join(base_dir, "data", "file.txt")
if os.path.exists(path):
    with open(path) as f:
        data = f.read()

# ✅ Prefer: pathlib
from pathlib import Path

path = Path(base_dir) / "data" / "file.txt"
if path.exists():
    data = path.read_text()

# ✅ Common pathlib operations
path.mkdir(parents=True, exist_ok=True)  # Create directory
files = path.glob("*.txt")  # Find files
path.stem  # Filename without extension
path.suffix  # File extension
path.parent  # Parent directory
```

## String Formatting

### Use f-strings
```python
# ❌ Avoid: Old-style formatting
name = "Alice"
message = "Hello, %s" % name
message = "Hello, {}".format(name)

# ✅ Prefer: f-strings
message = f"Hello, {name}"

# ✅ f-strings with expressions
price = 42.5
message = f"Price: ${price:.2f}"

# ✅ f-strings with debugging (3.8+)
x = 10
print(f"{x=}")  # Prints: x=10
```

## Code Organization and Imports

### Import Organization
```python
# ✅ Proper import order:
# 1. Standard library
import os
import sys
from pathlib import Path
from typing import Any

# 2. Third-party
import numpy as np
import requests
from fastapi import FastAPI

# 3. Local imports
from .models import User
from .utils import helper_function
```

### Avoid Wildcard Imports
```python
# ❌ Avoid: Wildcard imports
from module import *

# ✅ Prefer: Explicit imports
from module import SpecificClass, specific_function

# ✅ Or alias for long names
from very_long_module_name import VeryLongClassName as VLC
```

## Testing and Documentation

### Write Comprehensive Docstrings
```python
# ✅ Clear docstring with type information
def calculate_statistics(
    values: list[float],
    *,
    include_median: bool = False
) -> dict[str, float]:
    """Calculate basic statistics for a list of values.

    Args:
        values: List of numeric values to analyze
        include_median: Whether to include median in results

    Returns:
        Dictionary containing mean, std, and optionally median

    Raises:
        ValueError: If values list is empty

    Example:
        >>> calculate_statistics([1, 2, 3, 4, 5])
        {'mean': 3.0, 'std': 1.41}
    """
    if not values:
        raise ValueError("Cannot calculate statistics for empty list")

    # Implementation...
```

### Type-Safe Tests
```python
import pytest
from typing import Any

# ✅ Type hints in tests
def test_user_creation() -> None:
    user: User = create_user(name="Alice", email="alice@example.com")
    assert user.name == "Alice"
    assert user.email == "alice@example.com"

# ✅ Parametrized tests with types
@pytest.mark.parametrize("input_val,expected", [
    (1, 2),
    (2, 4),
    (3, 6),
])
def test_double(input_val: int, expected: int) -> None:
    assert double(input_val) == expected
```

## Performance and Optimization

### List Comprehensions vs map/filter
```python
# ✅ List comprehensions are usually clearer
numbers = [1, 2, 3, 4, 5]

# Prefer list comprehension
doubled = [x * 2 for x in numbers]
evens = [x for x in numbers if x % 2 == 0]

# Use map/filter only when function already exists
from math import sqrt
square_roots = list(map(sqrt, numbers))
```

### Use `set` for Membership Testing
```python
# ❌ Avoid: List for membership testing
allowed_users = ["alice", "bob", "charlie"]
if username in allowed_users:  # O(n) lookup
    pass

# ✅ Prefer: Set for O(1) lookup
allowed_users = {"alice", "bob", "charlie"}
if username in allowed_users:  # O(1) lookup
    pass
```

### Avoid Premature Optimization
```python
# ✅ Write clear code first
def process_data(items: list[Item]) -> list[Result]:
    """Process items and return results.

    Start with clear, readable implementation.
    Optimize only after profiling shows this is a bottleneck.
    """
    results = []
    for item in items:
        result = transform(item)
        if is_valid(result):
            results.append(result)
    return results
```
