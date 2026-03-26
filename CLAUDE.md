# Agentic Coding Workflow — Plugin Development Guide

This is a Claude Code plugin that provides commands, skills, and hooks for a streamlined development workflow. All changes to this repo are plugin components — treat them accordingly.

## Architecture

```
commands/       → Slash commands (YAML frontmatter + markdown instructions)
skills/         → Reusable skills (SKILL.md + scripts/ + references/)
hooks/          → Pre/Post execution hooks (hooks.json + scripts)
agents/         → Reusable agent role definitions
scripts/        → Standalone utility scripts
.claude-plugin/ → Plugin manifest (plugin.json, marketplace.json)
```

Component-specific conventions are in `.claude/rules/` — see `commands.md`, `skills.md`, `hooks.md`, `agents.md` for detailed rules on each component type.

## Subagents vs Primary Instances — When to Use Which

There are two ways to throw more compute at a problem. Pick the right one:

**Subagents** (built-in `Agent` tool) — fire-and-forget workers inside your session:
- Read-only research and exploration (search, summarize, answer questions)
- Bounded tasks with self-verifying output (find X, count Y, what does Z do?)
- Keeping the main context window clean from noisy intermediate work
- Quick turnaround, no setup overhead

**Primary instances** (full Claude sessions via tmux / `/agentic-coding-workflow:spawn`) — independent sessions with their own context:
- Implementation work where you want visibility and course-correction
- Tasks needing the full permission model and human-in-the-loop approval
- Long-running work where mid-flight steering is likely
- Parallel feature work across worktrees (each instance owns a branch)

**Quick routing guide:**

| Task | Mode | Why |
|------|------|-----|
| Search codebase for all uses of X | Subagent | Read-only, bounded |
| Explore how a system works | Subagent | Research — result is a summary |
| Write tests for a module | Primary instance | Implementation — needs review as it writes |
| Implement feature A while working on B | Primary instance | Parallel work, needs own worktree |
| Fix failing CI tests | Primary instance | Debugging + implementation, needs judgment |
| Summarize recent commits | Subagent | Read-only, bounded |
| Refactor a major system | Primary instance | High-stakes, needs oversight |

**Agent definitions are shared context** — the same `agents/researcher.md` works as a subagent prompt (`Agent` tool) or a full instance context (`claude --context agents/researcher.md` or `/agentic-coding-workflow:spawn researcher`).

## Workflow

The plugin's core workflow is: `/agentic-coding-workflow:prime` → `/agentic-coding-workflow:plan` → `/agentic-coding-workflow:review --plan` → `/agentic-coding-workflow:write-spec` → `/agentic-coding-workflow:implement` → `/agentic-coding-workflow:test` → `/agentic-coding-workflow:review --spec` → `/agentic-coding-workflow:ship`. All intermediate artifacts go in `.claude/plans/` and `.claude/specs/`. Implement creates its own worktree automatically. For autonomous execution, use `/agentic-coding-workflow:ralph` which handles parallel workers, task partitioning, and reunification. For manual parallel work, use `/agentic-coding-workflow:parallel` to spin up N implement sessions, then `/agentic-coding-workflow:reunify` to merge back.

## File Organization

- Plugin components go in the appropriate top-level directory, not nested arbitrarily
- Keep `hooks.json` as the single source of truth for hook registration
- New scripts must be `chmod +x` and use appropriate shebangs
- Reference materials are scoped to their skill — don't create global reference dumps
- **Runtime artifacts go in `.claude/`** — plans, specs, checkpoints, prime-context, logs, and any other generated output. Never write runtime artifacts to top-level directories

## What NOT to Do

- Don't duplicate logic between a command and a skill — commands invoke skills, not the other way around
- Don't put project-specific context (like database schemas or deployment details) in plugin files — that belongs in the consuming project's own CLAUDE.md
- Don't create commands without YAML frontmatter — they won't get proper tool permissions
- Don't hardcode paths — use `${CLAUDE_PLUGIN_ROOT}` for plugin-relative and `${CLAUDE_PROJECT_DIR}` for project-relative paths

## Testing & Validation

- Use `skills/skill-forge/scripts/validate-skill.py` to validate skill structure
- Hook scripts should fail gracefully (exit 0 on errors) to avoid blocking all operations
- **Plugin cache vs working directory**: Edits to plugin files in the working directory don't take effect until the plugin cache is updated. The cache lives at `~/.claude/plugins/cache/`. To test changes immediately, copy modified files to the cache location

## Learning & Output Styles

- `/agentic-coding-workflow:explain` — educational breakdown of code, changes, or systems (the "why" behind the code)
- `/agentic-coding-workflow:visualize` — ASCII, Mermaid, and HTML architecture diagrams

## Rule Maintenance

After making corrections or discovering patterns, update rules:
- Plugin-wide conventions → this file
- Component-specific rules → `.claude/rules/<topic>.md` (path-scoped via frontmatter)
- Use `/agentic-coding-workflow:update-rules` to be guided through the right placement
