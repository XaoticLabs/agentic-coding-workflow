---
paths:
  - "**/*.py"
---

# Python Judgment and Project Policy

Use the consuming project's Python version, dependency manager, formatter, linter, type checker, test runner, and library versions. Inspect its manifests, CI, and task commands. Do not migrate tooling as part of an unrelated change. This repository's optional stack is in `profiles/python/uv-ruff-basedpyright/`; installing the plugin does not select it.

Formatting, import ordering, naming syntax, logging syntax, annotation completeness, and typing strictness belong in actual tool configuration. Run the project's configured checks; avoid repeating mechanically enforced rules in agent instructions.

- Choose parameter types from caller needs and return types from the guarantees callers need. Avoid exposing internal representation unnecessarily.
- Name domain concepts clearly; prefer established project vocabulary over new abbreviations.
- Decompose code around cohesive responsibilities and readable control flow. Choose functions, methods, and properties from the API's semantics and compatibility needs.
- Validate untrusted inputs at system boundaries using the project's existing approach. Choose strictness or coercion intentionally; consider dataclasses for internal containers.
- Confirm the receiver's type and installed library version before proposing API changes. Unrelated `.dict()` methods and `Config` classes are not evidence of Pydantic usage or a migration requirement. Preserve intentional Pydantic v1 compatibility.
- Keep exception handling focused on operations that can fail; preserve useful context and give callers actionable failures. Runtime validation must still work when Python assertions are disabled.
- Run independent async work concurrently only when ordering, resource limits, and failure handling permit it. Handle task failures and clean up connections reliably.
- Review path containment, secret exposure, authentication assumptions, request timeouts, and validation boundaries in context. Use path-aware containment checks rather than string prefixes.
- Verify behavior with relevant regression cases. Report which configured checks ran and any required checks that remain unavailable.
