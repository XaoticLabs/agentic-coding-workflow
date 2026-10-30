# Elixir Style Guide

This is a community-maintained style guide for Elixir programming, emphasizing readability and consistency.

## Formatting Standards

### Whitespace Guidelines
- Eliminate trailing whitespace and end files with newlines
- Apply Unix-style line endings across all platforms
- Restrict lines to 98 characters (configurable via `.formatter.exs`)
- Space operators, commas, colons, and semicolons appropriately
- Avoid spaces around matched pairs like brackets or parentheses

### Indentation Practices
- Align successive `with` clauses consistently
- Use multiline syntax for `with` expressions containing `do` blocks exceeding one line or containing `else` options

### Parentheses Usage
- Include parentheses when using the pipe operator with single-arity functions
- Omit spacing between function names and opening parentheses
- Use parentheses in function calls, particularly within pipelines
- Drop square brackets from optional keyword list syntax

## Code Organization

### Expressions
- Group single-line function definitions together; separate multiline definitions with blank lines
- Use pipe operators for chaining multiple functions
- Avoid single-pipe chains; use direct function calls instead
- Start function chains with bare variables rather than function calls

### Naming Conventions
- Apply `snake_case` for atoms, functions, and variables
- Use `CamelCase` for modules (maintaining uppercase acronyms like HTTP or XML)
- Suffix boolean-returning functions with `?`
- Prefix guard-clause-compatible checks with `is_`

### Comments and Documentation
- Place comments on lines above the code they describe
- Capitalize multi-word comments and use proper punctuation
- Limit comment lines to 100 characters
- Use annotation keywords (TODO, FIXME, OPTIMIZE, HACK, REVIEW) in uppercase followed by colons

## Module Structure

Prescribed ordering for module attributes:

1. `@moduledoc`
2. `@behaviour`
3. `use` statements
4. `import` directives
5. `require` statements
6. `alias` declarations
7. Module attributes
8. `defstruct` definitions
9. Type specifications
10. Callbacks and macrocallbacks
11. Function definitions

Always include `@moduledoc` immediately after `defmodule`. Use `@moduledoc false` when intentionally skipping documentation.

## Collections and Data Structures

### Collections
- Employ keyword list syntax exclusively: `[a: "baz", b: "qux"]`
- Use atom-key shorthand for maps: `%{a: 1, b: 2}`
- Switch to arrow syntax when non-atom keys appear: `%{:a => 1, "c" => 0}`

### Structs
- List nil-defaulting fields as atoms first: `defstruct [:name, active: true]`
- Omit brackets for keyword list arguments in `defstruct`
- Format multiline struct definitions with aligned elements

## Exceptions

- Name exception modules with trailing `Error`: `BadHTTPCodeError`
- Use lowercase error messages without terminal punctuation

## Testing

Position the tested expression on the left and expected results on the right in assertions, unless performing pattern matching:
```elixir
assert actual_function(1) == true
```

## Type Specifications

- Group `@typedoc` and `@type` pairs together, separated by blank lines
- Place long union types on separate lines with pipe operators leading each alternative
- Name the primary type for a module `t`
- Position specifications immediately before function definitions, after `@doc`

## Code Formatter Integration

Elixir v1.6 introduced an automatic code formatter via `mix format`. Use this formatter for all projects, as it automatically enforces most formatting rules.
