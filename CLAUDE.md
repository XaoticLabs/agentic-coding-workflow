# Agentic Coding Workflow — Plugin Development Guide

This is a Claude Code plugin that provides commands, skills, and hooks for a streamlined development workflow. All changes to this repo are plugin components — treat them accordingly.

## Graph engineering

Use `references/graph-engineering.md` for task dependencies, execution states,
and source-bound evidence. Keep the ordinary native-session path small. Relay
(`scripts/relay.py`) is the only specialized execution engine. Its controller owns progress,
commits, bounded processes, integration, and acceptance. Workers never edit a
plan to establish completion. Jev/Laya observations cannot authorize actions,
skip checks, or approve patches. Runtime QA uses the `verify-project` skill and
`runtime-verifier` role with project-owned procedures and actual artifacts.
Use `devex-review` for onboarding friction and `test-audit` for evidence-backed
test improvements. These optional capabilities do not add mandatory review
phases to every change.

## Architecture

```
commands/       → Existing slash commands (retained for compatibility)
skills/         → Reusable skills (SKILL.md + scripts/ + references/)
references/     → Shared plugin workflow references (not commands)
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

**Agent definitions are shared context** — the same `agents/evaluator.md` works as a subagent prompt (`Agent` tool) or a full instance context (`claude --plugin-dir /path/to/agentic-coding-workflow --agent agentic-coding-workflow:evaluator` or `/agentic-coding-workflow:spawn evaluator`).

## Workflow

Use `references/model-policy.md` for executor model selection and observed model
provenance. Preserve the user's chosen model and compare cost per accepted
outcome. `references/verification-evidence.md` defines evidence for runtime
claims. Private setup and batch comparisons are described in
`references/execution-environments.md` and `references/experiments.md`.

Use the least elaborate workflow that resolves material uncertainty and produces verifiable results. Choose by uncertainty, impact, reversibility, and scope; reassess after inspection. The shared policy is in `references/shared-patterns.md` under **Proportional Workflow**.

Keep changes focused and review maintainability in context: clear responsibilities, readable flow, appropriate validation, and ease of safe change. Code size, addition-to-deletion ratios, and helper call counts do not establish quality. Retain useful decomposition, including single-use helpers. Adopt numeric size thresholds only when our own evaluations demonstrate a benefit for a particular workload, with recorded methods, results, tradeoffs, and reassessment conditions.

| Task | Default workflow |
|------|------------------|
| Small, clear change | Inspect relevant context → implement → verify → report |
| Substantial feature | Clarify material uncertainty → maintain a concise plan → implement → verify → review |
| Ordinary unattended work | Set a native `/goal` → continue in one isolated feature session → verify → review |
| Enforced limits or coordinated recovery | Select Relay with agreed boundaries → execute in owned worktrees → verify → review |

`/agentic-coding-workflow:implement "<change>"` supports direct interactive work. `/agentic-coding-workflow:plan` writes a concise plan when context is sufficient; `--interview` selects deeper questioning. `/agentic-coding-workflow:write-spec` is available for detailed task handoffs. Teaching (`explain`, `review --learn`) and explicit contract-test approval (`implement --approve-tests`) remain selected modes. Planning, specs, new worktrees, and repeated approvals are not universal prerequisites. Verification and project-required gates apply to every path.

Keep related tasks in the current feature session. Use native compaction for
context management and native resume after interruptions, preserving acceptance
criteria, user decisions, remaining work, and verification requirements. Recheck
current source state after resume. Fresh sessions remain appropriate for
unrelated work, required isolation, demonstrated context degradation, and
independent reviewers. Follow **Native Goals and Session Continuity** in
`references/shared-patterns.md`.

Save generated artifacts in `.claude/plans/` and `.claude/specs/` when needed.
Use native `/goal` for ordinary unattended continuation; it judges surfaced
evidence and does not replace deterministic verification or required independent
review. Select `/agentic-coding-workflow:relay` for enforced iteration/time bounds,
dependent workers, preserved candidates, or durable executor records. For manual parallel
work, use `/agentic-coding-workflow:parallel` and `/agentic-coding-workflow:reunify`.
Review and ship when requested; honor project approval policy and existing
authorization using **External Actions and Approval** in `references/shared-patterns.md`.
Local files and approval grants do not authenticate human review.

Use `references/review-policy.md` for reviewable changes, PR evidence, actionable
findings, and bounded repair; `references/project-readiness.md` documents
project-owned Go/Python/TypeScript checks and configuration readiness.

Ticket connectors default to installed CLI tools and explicitly configured APIs,
not MCP. Reuse `scripts/tickets.py` and `references/ticket-trackers.md` across
prime/plan/implement/review/ship. Keep provider/site/native identity consistent,
report unavailable or unauthenticated connections, and make remote updates
explicit. `references/delivery-follow-up.md` connects independent review and
post-publish CI/feedback handling to the existing shared review budget.

Always inspect recent `git log` before committing and follow the repository's historical commit pattern. Current history uses concise, lowercase `type: description` subjects (for example, `fix: ...`), normally without a body.

## File Organization

- Plugin components go in the appropriate top-level directory, not nested arbitrarily
- Keep `hooks.json` as the single source of truth for hook registration
- New scripts must be `chmod +x` and use appropriate shebangs
- Keep skill-specific references with their skill. Shared plugin policies belong in `references/` with links from the workflows that use them.
- **Runtime artifacts go in `.claude/`** — plans, specs, prime-context, logs, and generated workflow output. Native plugin evals write ignored raw results to `evals/results/`; keep representative cases, fixtures, graders, and sanitized benchmark summaries under `evals/` in version control. Use the split and retention policy in `evals/README.md`.

## What NOT to Do

- Prefer skills for new workflows; existing command files remain supported. Consolidate duplicate command/skill names gradually into a single skill. Expose Relay directly without a Ralph compatibility entrypoint. `relay` and `reunify` have skill entrypoints.
- Use `disable-model-invocation: true` for explicit workflows with consequential side effects. `user-invocable: false` is model-only discovery, not a disabled skill. Invocation controls do not grant authorization for publishing or other underlying actions.
- Don't put project-specific context (like database schemas or deployment details) in plugin files — that belongs in the consuming project's own CLAUDE.md
- Command `allowed-tools` frontmatter grants prompt-free approval; it does not restrict the available tool set. Use CLI `--tools` / `--disallowedTools` when restriction is required.
- Respect consuming projects' configured tooling. Language-specific tool preferences belong in optional profiles and project configuration, not global hooks. Keep mechanical rules in formatter, linter, and type-checker configuration; use agent instructions for contextual judgment.
- Don't hardcode paths — use `${CLAUDE_PLUGIN_ROOT}` for plugin-relative and `${CLAUDE_PROJECT_DIR}` for project-relative paths

## Testing & Validation

- Use `skills/skill-forge/scripts/validate-skill.py` for structural diagnostics, `claude plugin validate .` for native schema checks, and native `claude plugin eval .` plus deterministic tests for behavioral evidence. Structural diagnostics are not quality scores.
- During optimization, filter native evals with `--tag tuning`. Freeze the candidate and success criteria before using `--tag holdout` for a final comparison. Holdout feedback used for another edit becomes tuning evidence and requires fresh final cases. Record results or `NOT_RUN` limitations in `evals/benchmarks/`.
- Optional failure logging and notification hooks fail open. Policy gates intentionally block unmet or unverifiable requirements; test failure and timeout behavior as well as successful checks.
- **Local plugin development**: Validate with `claude plugin validate .`, then start a development session with `claude --plugin-dir "$PWD"`. From another project, pass the absolute path to this checkout. Reload components with `/reload-plugins` after edits, or restart the development session. Keep installed plugin caches managed by Claude Code. See the [plugin reference](https://code.claude.com/docs/en/plugins-reference) and [local plugin testing guide](https://code.claude.com/docs/en/plugins/create#load-a-plugin-for-one-session).

## Learning & Output Styles

- `/agentic-coding-workflow:explain` — educational breakdown of code, changes, or systems (the "why" behind the code)
- `/agentic-coding-workflow:visualize` — ASCII, Mermaid, and HTML architecture diagrams

## Rule Maintenance

After making corrections or discovering patterns, update rules:
- Plugin-wide conventions → this file
- Component-specific rules → `.claude/rules/<topic>.md` (path-scoped via frontmatter)
- Use `/agentic-coding-workflow:update-rules` to be guided through the right placement
