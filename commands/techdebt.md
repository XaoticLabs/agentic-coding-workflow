---
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - Agent
  - Write
  - AskUserQuestion
  - EnterPlanMode
  - ExitPlanMode
effort: high
---

# Tech Debt Scanner

Scans the codebase for tech debt: TODO/FIXME comments, dead code, duplicated patterns, inconsistencies, and code smells. Produces a prioritized report with actionable recommendations.

## Input

$ARGUMENTS - Either:
- Empty (scans the entire project)
- A directory path (e.g., `lib/` or `src/components/`) — scopes the scan
- A category filter (e.g., `todos`, `dead-code`, `duplication`, `inconsistencies`) — runs only that scan
- A path + category (e.g., `lib/ todos`)

## Instructions

### Phase 1: Determine Scope

**Parse the input:**
- If empty, scan the project root (respect `.gitignore` by using git-aware tools)
- If a directory path is provided, scope all scans to that directory
- If a category is provided, only run that specific scan
- If both, combine them

**Detect the project type** by checking for:
- `mix.exs` → Elixir project
- `pyproject.toml` / `setup.py` / `requirements.txt` → Python project
- `package.json` → JavaScript/TypeScript project
- `go.mod` → Go project
- `Cargo.toml` → Rust project
- Multiple indicators → polyglot project, scan all relevant patterns

### Phase 2: Parallel Scans

Launch scans in parallel using the Agent tool where possible. Each scan category is independent.

#### 2a: TODO/FIXME/HACK Comments

Search for markers that indicate deferred work:
- `TODO`, `FIXME`, `HACK`, `XXX`, `TEMP`, `WORKAROUND`, `DEPRECATED`
- Categorize by urgency: `FIXME` > `HACK` > `TODO` > others
- Extract the surrounding context (the comment text and which function/module it's in)
- Flag TODOs that reference ticket IDs (these may be closeable)
- Flag TODOs older than 6 months (use `git blame` on the line)

#### 2b: Dead Code Detection

Look for signals of unused code:
- **Unused imports/aliases** — imports that don't appear elsewhere in the file
- **Unused functions** — functions defined but never called anywhere in the project (use Grep across the codebase)
- **Commented-out code blocks** — multi-line comments that look like code (contain `=`, `def`, `fn`, `function`, `class`, `if`, `return`)
- **Empty modules/files** — files with only boilerplate and no meaningful logic
- **Unreachable code** — code after unconditional returns/raises

Language-specific checks:
- Elixir: unused module attributes (`@`-prefixed), unused `alias`/`import`/`use`
- Python: unused imports (check with grep, not just linting), `pass`-only functions
- JS/TS: unused `export`s (exported but never imported elsewhere)

#### 2c: Duplication Detection

Look for duplicated patterns:
- **Near-identical functions** — functions in different files with very similar names and signatures
- **Copy-paste patterns** — blocks of 5+ similar lines appearing in multiple locations
- **Reimplemented utilities** — common operations (string manipulation, date formatting, error wrapping) implemented multiple times instead of using a shared helper
- **Duplicated configuration** — similar config blocks across files

Focus on structural duplication, not just textual matches.

#### 2d: Pattern Inconsistencies

Check for inconsistent patterns within the codebase:
- **Naming conventions** — mixed casing styles (`camelCase` vs `snake_case`) in the same layer
- **Error handling** — some modules using exceptions, others using result tuples, others using error codes
- **Logging** — inconsistent log levels, formats, or logger usage
- **Testing patterns** — inconsistent test structure, setup/teardown approaches
- **Import ordering** — inconsistent grouping or ordering of imports

Language-specific checks:
- Elixir: mixed `with` vs nested `case`, inconsistent `{:ok, _}`/`{:error, _}` handling
- Python: mixed `async`/sync patterns, inconsistent type annotation coverage
- JS/TS: mixed `async/await` vs `.then()`, inconsistent error boundaries

### Phase 3: Prioritize Findings

Score each finding on two axes:

**Impact** (how much does this hurt?):
- High: actively causes bugs, confuses developers, blocks features
- Medium: slows development, increases cognitive load
- Low: cosmetic, minor inconvenience

**Effort to fix** (how hard is the fix?):
- Quick fix: < 30 minutes, single file
- Small task: 1-2 hours, a few files
- Project: half-day+, cross-cutting changes

**Priority matrix:**
| | Quick Fix | Small Task | Project |
|---|---|---|---|
| **High Impact** | Fix now | Fix soon | Plan it |
| **Medium Impact** | Fix now | Backlog | Defer |
| **Low Impact** | Opportunistic | Defer | Ignore |

### Phase 4: Generate Report

**Create the output directory** if it doesn't exist:
```bash
mkdir -p .claude/reports
```

**Write the report** to `.claude/reports/agentic-coding-workflow:techdebt-<date>.md`:

```markdown
# Tech Debt Report

> Generated: [date]
> Scope: [directory or "full project"]
> Project type: [detected type]

## Summary

| Category | Count | High | Medium | Low |
|----------|-------|------|--------|-----|
| TODOs/FIXMEs | X | X | X | X |
| Dead code | X | X | X | X |
| Duplication | X | X | X | X |
| Inconsistencies | X | X | X | X |
| **Total** | **X** | **X** | **X** | **X** |

## Fix Now (High Impact + Quick Fix)

[Numbered list of findings with file:line, description, and suggested fix]

## Fix Soon (High Impact + Small Task)

[Numbered list]

## Plan It (High Impact + Project-Sized)

[Numbered list with rough scope description]

## Backlog

[Grouped by category, brief descriptions]

## Detailed Findings

### TODOs/FIXMEs
[Full list with file:line, age, text, and any referenced tickets]

### Dead Code
[Full list with file:line and evidence of non-use]

### Duplication
[Groups of duplicated code with all locations listed]

### Inconsistencies
[Patterns found with examples of each variant]
```

**Present the summary** to the user inline (don't just point to the file).

## Error Handling

- If the project type can't be detected, scan for common patterns across all languages
- If a scan category finds nothing, report it as clean — don't skip the section
- If `git blame` is unavailable (not a git repo), skip TODO age analysis
- If the codebase is very large (>10k files), suggest scoping to a subdirectory via `AskUserQuestion`

## Example Usage

```
/agentic-coding-workflow:techdebt
```
Full project scan, all categories.

```
/agentic-coding-workflow:techdebt lib/
```
Scan only the `lib/` directory.

```
/agentic-coding-workflow:techdebt todos
```
Only scan for TODO/FIXME comments across the project.

```
/agentic-coding-workflow:techdebt src/api dead-code
```
Scan `src/api` for dead code only.
