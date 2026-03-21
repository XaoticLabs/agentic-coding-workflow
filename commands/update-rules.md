---
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
  - AskUserQuestion
---

# Update Rules

Guides Claude through updating the project's CLAUDE.md or `.claude/rules/` files after a correction, pattern discovery, or learned convention. Implements the "update your rules so you don't make that mistake again" pattern.

## Input

$ARGUMENTS — Either:
- A description of what to remember (e.g., `"always use snake_case for database columns"`)
- Empty — will analyze the current conversation for corrections or patterns worth capturing

## Instructions

### Phase 1: Identify What to Capture

**If input is provided:**
- Use the provided description as the rule to capture

**If no input provided:**
- Review the recent conversation for:
  - Corrections the user made ("no, don't do X", "use Y instead")
  - Patterns that worked well and should be repeated
  - Conventions that weren't obvious from the code
  - Mistakes that should be prevented in the future
- Summarize what you found and confirm with the user via AskUserQuestion

### Phase 2: Determine Placement

Rules belong in different places depending on their scope. Evaluate the rule and choose:

**Project-wide conventions → `CLAUDE.md` (root)**
- Applies to all code in the project
- Examples: "use snake_case for all database columns", "always add integration tests", "prefer composition over inheritance"

**File-type-specific rules → `.claude/rules/<topic>.md` (path-scoped)**
- Only matters when working with certain file types or directories
- Examples: "Elixir contexts must have a public API module" (scoped to `lib/**/*.ex`), "React components use named exports" (scoped to `src/components/**/*.tsx`)
- Use YAML frontmatter `globs:` to scope the rule to matching paths

**Personal preferences → `~/.claude/CLAUDE.md` or `~/.claude/rules/`**
- User-specific, not project conventions
- Examples: "I prefer verbose commit messages", "always explain your reasoning before making changes"

Present your recommendation to the user and confirm via AskUserQuestion before writing.

### Phase 3: Check for Existing Rules

Before creating a new rule:

1. Read `CLAUDE.md` if it exists — check if the rule is already covered or conflicts
2. Scan `.claude/rules/` for existing rule files on the same topic
3. If a related rule file exists, update it rather than creating a new one
4. If the rule contradicts an existing rule, flag the conflict to the user

### Phase 4: Write the Rule

**If updating `CLAUDE.md`:**
- Find the most appropriate section for the new rule
- Add it concisely — one line if possible, a short paragraph if needed
- Don't reorganize the file — just add the rule where it fits

**If creating/updating a `.claude/rules/` file:**
- Use this format:
```markdown
---
globs:
  - "path/pattern/**/*.ext"
description: One-line description of when this rule applies
---

# Rule Topic

- Rule statement 1
- Rule statement 2
```
- File names should be descriptive: `elixir-contexts.md`, `api-conventions.md`, `testing.md`

**If updating personal rules (`~/.claude/`):**
- Check if `~/.claude/CLAUDE.md` exists first
- Append the rule, keeping personal preferences organized

### Phase 5: Confirm

After writing, show the user:
- What was added/modified
- Where it was placed
- Why that location was chosen

## Error Handling

- If `CLAUDE.md` doesn't exist and the rule is project-wide, create it with a minimal structure
- If `.claude/rules/` doesn't exist, create the directory
- If `~/.claude/` doesn't exist, tell the user how to create it manually
- If the user disagrees with placement, move the rule to their preferred location

## Example Usage

```
/update-rules "always run mix format before committing Elixir code"
```
→ Adds to `.claude/rules/elixir.md` scoped to `**/*.ex` files

```
/update-rules "don't mock the database in integration tests"
```
→ Adds to `CLAUDE.md` under testing conventions (project-wide rule)

```
/update-rules
```
→ Scans conversation for corrections and patterns, proposes rules to capture
