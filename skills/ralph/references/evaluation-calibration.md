# Evaluator Calibration Reference

Use these scored examples and smell patterns to calibrate your evaluation. LLM evaluators systematically overrate LLM-generated code — this reference counteracts that bias.

## Scoring Examples

### Score 5 — Excellent

```python
# Task: Add user email validation to registration endpoint
# Contract: reject emails without @, reject disposable domains, return 422 with specific error

def validate_email(email: str) -> str | None:
    """Returns error message or None if valid."""
    if "@" not in email or email.count("@") != 1:
        return "Invalid email format"
    domain = email.split("@")[1]
    if domain in DISPOSABLE_DOMAINS:
        return "Disposable email addresses not allowed"
    return None
```

**Why 5:** Minimal code. Does exactly what the contract says. No extra validation beyond spec. Returns the specific error type the contract requires. No abstraction — it's used in one place.

### Score 4 — Good

```python
def validate_email(email: str) -> str | None:
    if "@" not in email or email.count("@") != 1:
        return "Invalid email format"
    local, domain = email.split("@")
    if not local or not domain:
        return "Invalid email format"
    if domain in DISPOSABLE_DOMAINS:
        return "Disposable email addresses not allowed"
    if "." not in domain:
        return "Invalid email domain"
    return None
```

**Why 4:** Correct and clean, but adds domain dot-check not in spec. Minor scope creep. The extra checks aren't wrong, just not asked for.

### Score 3 — Acceptable

```python
import re

EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

def validate_email(email: str) -> str | None:
    if not EMAIL_REGEX.match(email):
        return "Invalid email format"
    domain = email.split("@")[1].lower()
    if domain in DISPOSABLE_DOMAINS:
        return "Disposable email addresses not allowed"
    return None
```

**Why 3:** Works correctly, meets spec. But the regex is more complex than needed for the contract's requirements (just needs @ check). Not wrong, but adds complexity without spec justification.

### Score 2 — Needs Work

```python
from abc import ABC, abstractmethod

class EmailValidator(ABC):
    @abstractmethod
    def validate(self, email: str) -> ValidationResult: ...

class FormatValidator(EmailValidator):
    def validate(self, email: str) -> ValidationResult:
        # ... regex validation

class DomainValidator(EmailValidator):
    def validate(self, email: str) -> ValidationResult:
        # ... disposable domain check

class ValidationPipeline:
    def __init__(self, validators: list[EmailValidator]):
        self.validators = validators

    def run(self, email: str) -> ValidationResult:
        for v in self.validators:
            result = v.validate(email)
            if not result.is_valid:
                return result
        return ValidationResult(is_valid=True)
```

**Why 2:** Massive over-engineering. The spec needs one function checking two things. This creates an abstract base class, three concrete classes, and a pipeline — all for two checks. Classic LLM code smell: premature generalization.

### Score 1 — Failing

```python
def validate_email(email):
    # TODO: implement email validation
    return None
```

**Why 1:** Not implemented. Stub only.

## Common LLM Code Smells

### 1. Over-Abstraction (most common)

**Pattern:** Creating base classes, factories, registries, or strategy patterns for code used in exactly one place.

**Test:** Count how many call sites use the abstraction. If it's 1, it's premature.

**Example of the smell:**
```python
# BAD: Factory for one type
class NotificationFactory:
    @staticmethod
    def create(type: str) -> Notification:
        if type == "email":
            return EmailNotification()
        raise ValueError(f"Unknown type: {type}")

# GOOD: Just use the class directly
notification = EmailNotification()
```

### 2. Defensive Excess

**Pattern:** Error handling around code that cannot fail in context.

**Test:** Can the wrapped code actually throw/error in this specific call site? If not, the handling is noise.

**Example:**
```python
# BAD: config is always a dict at this point (validated upstream)
try:
    value = config.get("key", default)
except (TypeError, AttributeError):
    value = default

# GOOD: trust the validated input
value = config.get("key", default)
```

### 3. Template Residue

**Pattern:** Generic variable names, boilerplate doc comments that restate the function signature, unused imports, "just in case" code.

**Signals:**
- Variables named `data`, `result`, `item`, `value` when a domain term exists
- Comments like `"""Gets the user."""` on `def get_user()`
- Imports at the top that nothing in the file uses
- Parameters with defaults that are never called with different values

### 4. Feature Creep

**Pattern:** Adding configuration, feature flags, extensibility points, or options not in the spec.

**Test:** Is this capability mentioned in the contract/spec? If not, it's creep.

**Example:**
```python
# BAD: spec says "send email notification" — not configurable channels
def notify(user, message, channel="email", retry=3, backoff=True):
    ...

# GOOD: spec says "send email notification"
def send_email_notification(user, message):
    ...
```

### 5. Premature Generalization

**Pattern:** Making something work for N cases when only 1 case exists or is specified.

**Test:** How many concrete implementations exist today? If 1, it shouldn't be generic.

### 6. Complexity Laundering

**Pattern:** Breaking simple logic into many small functions that individually look clean but collectively are harder to follow than the inline version.

**Test:** Would a developer reading this code for the first time need to jump between 3+ functions to understand one operation? If yes, and the original would fit in <15 lines, it's been over-decomposed.

## Evaluation Anti-Patterns

Things you (the evaluator) should NOT do:

1. **Don't praise then dock.** Skip "This is a solid implementation, but..." — just state the scores and issues.
2. **Don't grade on potential.** Grade what's there, not what it could become.
3. **Don't penalize for missing features not in the spec/contract.** The implementer's job is to match the spec, not to anticipate future needs.
4. **Don't reward complexity.** More code is not better code. A 10-line solution that meets spec scores higher than a 100-line solution that also meets spec.
5. **Don't conflate "different from how I'd do it" with "wrong."** If it meets the contract and follows project conventions, it's acceptable even if you'd have chosen a different approach.
