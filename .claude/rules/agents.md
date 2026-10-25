---
paths:
  - "agents/**/*.md"
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
- Agent definitions work for BOTH subagents (via `Agent` tool prompt) and primary instances (via `claude --plugin-dir /path/to/plugin --agent agentic-coding-workflow:<role>`); use `--append-system-prompt-file` for a standalone role file (only the Markdown instructions, without agent frontmatter metadata)
- Write instructions that make sense in either context
- Specify scope, constraints, completion checks, and reporting appropriate to the task in either mode

## Mode Selection in Commands
- Follow the task-based delegation policy in `CLAUDE.md`: read a few relevant files directly, delegate investigations with overwhelming intermediate output, parallelize independent components with clear interfaces, and use independent verification when its expected benefit justifies its cost
- Implementation, testing, and debugging may run in the current session, a capable subagent, or a separate primary instance; check tools, permissions, turn budget, worktree isolation, and oversight needs
- Keep tightly coupled work and ongoing user interaction in the current session; use a separate primary instance when independent visibility, steering, or lifecycle is needed
- Commands should document which mode they use and why
- When a command switches modes mid-flow (e.g., research subagent → implementation in main session), make the handoff explicit
