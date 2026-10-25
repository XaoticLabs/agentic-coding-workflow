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

Choose delegation from the work's independence, context needs, required capabilities, and oversight. Account for the extra model calls, latency, and handoffs:

- Read a few relevant files and perform targeted searches directly in the current session.
- Delegate an independent investigation when its intermediate search results, logs, or file contents would overwhelm the main task. Ask for a concise summary with relevant paths and evidence.
- Parallelize independent components with clear interfaces, file ownership, and completion checks.
- Use an independent verifier when its expected reduction in consequential errors justifies its cost.

Keep tightly coupled investigation, implementation, and testing together when they share substantial context.

**Subagents** (built-in `Agent` tool) can investigate, implement, and run tests when their configured tools and permissions support the task. Check tool access, the `maxTurns` budget, and `isolation: worktree` when concurrent edits need separate checkouts. Read-only roles remain read-only. See the [Claude subagent reference](https://code.claude.com/docs/en/sub-agents).

**Primary instances** (full Claude sessions via tmux / `/agentic-coding-workflow:spawn`) suit work that needs an independently visible, steerable session, user interaction unavailable to the selected subagent, or a separate session lifecycle. Implementation does not inherently require a separate primary session; choose placement from capability and oversight requirements.

Give delegated work a clear scope, inputs, output format, and verification criteria. Review its result and integrate it before treating the task as complete.

**Agent definitions are shared context** — the same `agents/researcher.md` works as a subagent prompt (`Agent` tool) or a full instance context (`claude --plugin-dir /path/to/agentic-coding-workflow --agent agentic-coding-workflow:researcher` or `/agentic-coding-workflow:spawn researcher`).

## Workflow

Use the least elaborate workflow that resolves material uncertainty and produces verifiable results. Choose by uncertainty, impact, reversibility, and scope; reassess after inspection. The shared policy is in `commands/shared-patterns.md` under **Proportional Workflow**.

| Task | Default workflow |
|------|------------------|
| Small, clear change | Inspect relevant context → implement → verify → report |
| Substantial feature | Clarify material uncertainty → maintain a concise plan → implement → verify → review |
| Long unattended task | Approve scope and limits → execute in isolation → preserve progress → verify outcomes → present evidence |

`/agentic-coding-workflow:implement "<change>"` supports direct interactive work. `/agentic-coding-workflow:plan` writes a concise plan when context is sufficient; `--interview` selects deeper questioning. `/agentic-coding-workflow:write-spec` is available for detailed task handoffs. Teaching (`explain`, `review --learn`) and explicit contract-test approval (`implement --approve-tests`) remain selected modes. Planning, specs, new worktrees, and repeated approvals are not universal prerequisites. Verification and project-required gates apply to every path.

Save generated artifacts in `.claude/plans/` and `.claude/specs/` when needed. Use `/agentic-coding-workflow:ralph` for unattended execution with agreed limits and isolated worktrees; it handles task partitioning, progress records, verification, and reunification. For manual parallel work, use `/agentic-coding-workflow:parallel` and `/agentic-coding-workflow:reunify`. Review and ship when requested; existing publishing gates still apply.

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
- Optional audit and notification hooks fail open. Policy gates intentionally block unmet or unverifiable requirements; test failure and timeout behavior as well as successful checks.
- **Local plugin development**: Validate with `claude plugin validate .`, then start a development session with `claude --plugin-dir "$PWD"`. From another project, pass the absolute path to this checkout. Reload components with `/reload-plugins` after edits, or restart the development session. Keep installed plugin caches managed by Claude Code. See the [plugin reference](https://code.claude.com/docs/en/plugins-reference) and [local plugin testing guide](https://code.claude.com/docs/en/plugins/create#load-a-plugin-for-one-session).

## Learning & Output Styles

- `/agentic-coding-workflow:explain` — educational breakdown of code, changes, or systems (the "why" behind the code)
- `/agentic-coding-workflow:visualize` — ASCII, Mermaid, and HTML architecture diagrams

## Rule Maintenance

After making corrections or discovering patterns, update rules:
- Plugin-wide conventions → this file
- Component-specific rules → `.claude/rules/<topic>.md` (path-scoped via frontmatter)
- Use `/agentic-coding-workflow:update-rules` to be guided through the right placement
