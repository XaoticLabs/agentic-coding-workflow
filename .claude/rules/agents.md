---
globs:
  - "agents/**/*.md"
description: Rules for writing and modifying agents and subagents
---

# Agent Development Rules

## Agent Definitions
- Each agent is a single markdown file in `agents/<role-name>.md`
- One role per file — don't combine researcher + reviewer into one agent
- Every definition must include: Role, Instructions, Constraints, Output Format, and "Best Used As" sections
- The "Best Used As" section documents when to use as subagent vs primary instance

## Naming
- Use lowercase, hyphenated names: `code-reviewer.md`, `test-writer.md`
- Names should describe the role, not the task: `researcher` not `search-codebase`

## Dual-Use Design
- Agent definitions work for BOTH subagents (via `Agent` tool prompt) and primary instances (via `claude --context`)
- Write instructions that make sense in either context
- Specify constraints appropriate for autonomous operation (subagent mode) — the human-in-the-loop will add oversight in primary instance mode

## Mode Selection in Commands
- **Use subagents for:** read-only research, exploration, review, analysis, summarization
- **Use primary instances for:** implementation, testing, debugging, any task where the user wants to steer
- Commands should document which mode they use and why
- When a command switches modes mid-flow (e.g., research subagent → implementation in main session), make the handoff explicit
