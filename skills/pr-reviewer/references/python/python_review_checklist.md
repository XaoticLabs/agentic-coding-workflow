# Python PR Review Checklist

Quick-scan index for Python PR reviews. See `python_style_guide.md` for rationale, examples, and edge cases.

Tooling handles: formatting, import order, unused imports, type errors, bare excepts, deprecated syntax, test failures.

| # | Area | Key Cues | Severity |
|---|------|----------|----------|
| 1 | **Pattern Consistency** | Follows codebase patterns? Grep before flagging. New pattern justified? | MAJOR |
| 2 | **Imports** | Module imports (not symbols). Absolute only. `TYPE_CHECKING` block. No obscure aliases. | MINOR |
| 3 | **Naming** | No type-encoding, no abbreviation-by-deletion, no builtin shadowing, booleans as questions | MINOR |
| 4 | **Type Design** | Abstract params (`Sequence`/`Mapping`), concrete returns. `Self`. Parameterized generics. | MAJOR |
| 5 | **Docstrings** | Imperative summary. Args sans types. Returns describes semantics. Comments = *why*. | MINOR |
| 6 | **Design** | <40 lines, <3 nesting. Explicit returns. `*` for 3+ optionals. No `@staticmethod`. | MAJOR |
| 7 | **Error Handling** | Minimal `try`. Actionable messages. Intentional `from None`? No `assert` for validation. | MAJOR |
| 8 | **Pydantic** | v2 API only. Flag `.dict()`, `class Config:`, `@validator`. `BaseSettings` for config. | MAJOR |
| 9 | **Security** | Path traversal, JWT expiry+algorithms, cookie flags, timeouts, no sensitive logging, no unsafe deser | **BLOCKER** |
| 10 | **Async** | `gather()` independent awaits. Check task results. Async context managers. `run()` at entry only. | MAJOR |
| 11 | **Testing** | Behavioral names. Specific assertions. `match=` on raises. Parametrize. Mock external only. | MAJOR |
| 12 | **Performance** | Sequential independent awaits, N+1, string `+=` loop, list membership, missing timeouts | MINOR |
| 13 | **Logging** | `%`-style (not f-strings). Appropriate level. Structured context. | MINOR |
