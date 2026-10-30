# Python PR Review Checklist

Quick-scan index for Python PR reviews. See `python_style_guide.md` for rationale, examples, and edge cases.

Use the project's configured checks and library versions. Mechanical rules belong in tool configuration; confirm the actual check result and project policy before treating a convention as a finding.

| # | Area | Key Cues | Severity |
|---|------|----------|----------|
| 1 | **Pattern Consistency** | Follows codebase patterns? Grep before flagging. New pattern justified? | MAJOR |
| 2 | **Imports** | Module imports (not symbols). Absolute only. `TYPE_CHECKING` block. No obscure aliases. | MINOR |
| 3 | **Naming** | No type-encoding, no abbreviation-by-deletion, no builtin shadowing, booleans as questions | MINOR |
| 4 | **Type Design** | Abstract params (`Sequence`/`Mapping`), concrete returns. `Self`. Parameterized generics. | MAJOR |
| 5 | **Docstrings** | Imperative summary. Args sans types. Returns describes semantics. Comments = *why*. | MINOR |
| 6 | **Design** | Clear responsibilities and control flow; useful decomposition without fixed size limits. API choices fit semantics and compatibility. | MAJOR |
| 7 | **Error Handling** | Minimal `try`. Actionable messages. Intentional `from None`? No `assert` for validation. | MAJOR |
| 8 | **Pydantic** | Confirm model type and supported Pydantic version before flagging an API. Respect intentional v1 compatibility; unrelated `.dict()` methods and `Config` classes are valid. | MAJOR |
| 9 | **Security** | Path traversal, JWT expiry+algorithms, cookie flags, timeouts, no sensitive logging, no unsafe deser | **BLOCKER** |
| 10 | **Async** | `gather()` independent awaits. Check task results. Async context managers. `run()` at entry only. | MAJOR |
| 11 | **Testing** | Behavioral names. Specific assertions. `match=` on raises. Parametrize. Mock external only. | MAJOR |
| 12 | **Performance** | Sequential independent awaits, N+1, string `+=` loop, list membership, missing timeouts | MINOR |
| 13 | **Logging** | `%`-style (not f-strings). Appropriate level. Structured context. | MINOR |
