# Evaluator Calibration Reference

Use these illustrative scored examples and investigation prompts to calibrate contextual review. They are not empirical evaluations of a model or workload and do not justify numeric size thresholds. Judge clarity, cohesion, coupling, validation, and ease of change against the actual requirements and codebase.

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

**Why 5:** The named helper separates validation from endpoint execution and makes the contract easy to find and test, even if the endpoint is its only caller. It preserves the required checks and error messages with readable flow. This is a deliberately narrow exercise contract; real registration boundaries may require further validation.

### Score 4 — Good

```python
def validate_email(email: str) -> str | None:
    if "@" not in email or email.count("@") != 1:
        return "Invalid email format"
    if email.split("@")[1] in DISPOSABLE_DOMAINS:
        return "Disposable email addresses not allowed"
    domain = email.split("@")[1]
    # Include the validated domain in existing registration diagnostics.
    logger.debug("Validated registration domain %s", domain)
    return None
```

**Why 4:** In a codebase that requires these diagnostics, behavior and boundaries fit. Domain extraction is duplicated, so a named local would make the relationship clearer. This is a minor local issue, not a reason to demand inlining or fewer lines.

### Score 3 — Acceptable

```python
def validate_email(email: str) -> str | None:
    return (
        "Invalid email format"
        if email.count("@") != 1
        else "Disposable email addresses not allowed"
        if email.split("@")[1] in DISPOSABLE_DOMAINS
        else None
    )
```

**Why 3:** Meets the exercise contract, but nested conditional expressions make validation order harder to scan and extend. Explicit checks and a named domain would improve maintainability even if that adds lines. This is acceptable behavior with a local clarity improvement available.

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

**Why 2:** In a standalone endpoint with no shared validation architecture or extension requirement, this machinery spreads one policy across inheritance and pipeline dispatch. A maintainer must trace the dispatch to understand which checks execute. Replace it with a cohesive validation boundary while retaining the checks. In a project with an established shared validator pipeline, the same structure could be appropriate; class count alone does not establish a defect.

### Score 1 — Failing

```python
def validate_email(email):
    # TODO: implement email validation
    return None
```

**Why 1:** Not implemented. Stub only.

## Common LLM Code Smells

### 1. Over-Abstraction (most common)

**Pattern:** Base classes, factories, registries, or strategies that add indirection without a current responsibility or useful boundary.

**Review:** Identify what responsibility the abstraction owns and how a maintainer follows the operation. A single-use helper can clarify intent, isolate effects, or make a boundary testable. Flag the concrete navigation, coupling, or change cost when the abstraction provides no such benefit.

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

**Review:** Does the capability support the contract, a necessary boundary, or an established project requirement? Flag speculative options that add behavior or maintenance obligations outside that scope; do not classify required validation as creep.

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

**Review:** Does the generalization serve a current requirement or established architecture? Identify the extra configuration, dispatch, or coupling it imposes. The number of implementations is context, not a verdict.

### 6. Complexity Laundering

**Pattern:** Breaking simple logic into many small functions that individually look clean but collectively are harder to follow than the inline version.

**Review:** Can a developer understand the operation from names, boundaries, and data flow? Identify helpers that hide essential context or shuttle mutable state without clarifying a responsibility. Compare with a concrete alternative; retain decomposition that makes the operation easier to understand or change.

## Context Changes the Review

| Context | Appropriate review |
|---------|--------------------|
| A new feature adds files and has no obsolete code to delete | Check that the components serve acceptance criteria and have clear contracts; the addition-to-deletion ratio says nothing about quality. |
| A single-use parser separates untrusted input checks from execution | Credit the boundary and verify its failure behavior; inlining may obscure the contract. |
| A migration repeats explicit validation to enforce a new invariant | Check the transition and retained guarantees before suggesting shared validation or removing checks. |
| A helper forwards calls through generic options with no domain role | Explain how it obscures the actual API and which simpler structure would preserve behavior. |

## Evaluation Anti-Patterns

Things you (the evaluator) should NOT do:

1. **Don't praise then dock.** Skip "This is a solid implementation, but..." — just state the scores and issues.
2. **Don't grade on potential.** Grade what's there, not what it could become.
3. **Don't penalize for missing features not in the spec/contract.** The implementer's job is to match the spec, not to anticipate future needs.
4. **Don't reward size in either direction.** Compare clarity, responsibilities, coupling, and ease of safe change. More code, fewer lines, or more deletions do not establish quality.
5. **Don't conflate "different from how I'd do it" with "wrong."** If it meets the contract and follows project conventions, it's acceptable even if you'd have chosen a different approach.
6. **Don't invent calibrated thresholds.** Before adopting a workload-specific size threshold, record our own evaluation method, workload, observed review outcomes, tradeoffs, and reassessment conditions. These examples provide no such evidence.
