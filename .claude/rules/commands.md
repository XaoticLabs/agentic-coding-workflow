---
globs:
  - "commands/**/*.md"
description: Rules for writing and modifying slash commands
---

# Command Development Rules

## Frontmatter
- Every command MUST have YAML frontmatter with `allowed-tools` listing exactly the tools it needs
- Only grant tools the command actually uses — don't copy-paste the full list from another command
- Include `EnterPlanMode`/`ExitPlanMode` if the command has a planning phase
- Include `AskUserQuestion` if the command needs user interaction

## Input Handling
- Use `$ARGUMENTS` as the input variable
- Support multiple input formats where it makes sense (ticket ID, file path, inline text)
- Validate input early and give clear errors if the format doesn't match

## Structure
- Use numbered phases with clear headers (Phase 1: X, Phase 2: Y)
- Each phase should have a single responsibility
- Include an "Error Handling" section for what to do when things go wrong
- Include "Example Usage" with 2-3 concrete examples at the bottom

## Output
- Commands that produce artifacts should write to `.claude/` subdirectories (plans/, specs/)
- Include a summary report at the end showing what was done
- Use markdown formatting in reports for readability
