# Agentic Coding Workflow

A Claude Code plugin with commands, skills, and hooks for a streamlined development workflow.

## Quick Start

**1. Install Claude Code** (if you haven't already):

Native install (recommended):
```bash
curl -fsSL https://claude.ai/install.sh | bash
```
Homebrew:
```bash
brew install --cask claude-code
```

**2. Add the marketplace and install the plugin:**
```bash
claude
# then inside Claude Code:
/plugin marketplace add XaoticLabs/agentic-coding-workflow
/plugin install agentic-coding-workflow@xaoticlabs-marketplace
```

Alternatively, use the interactive UI:
```bash
claude
# then inside Claude Code:
/plugin
# Go to "Marketplaces" tab → Add → enter: XaoticLabs/agentic-coding-workflow
# Follow instructions to install and enable
/reload-plugins
```

**3. Start using it** — open any project and try:
```bash
cd your-project
claude
```
Then type any of these:
- `/agentic-coding-workflow:prime` — loads your project context (git history, docs, structure)
- `/agentic-coding-workflow:plan` — describe what you want to build, get a plan back
- `/agentic-coding-workflow:implement` — builds from the plan
- `/agentic-coding-workflow:ralph` — autonomous mode

## Why This Exists

**This plugin adds opinionated workflows on top of Claude Code** so you don't have to figure out prompting patterns yourself. Once you're more comfortable with Claude Code (or your agentic TUI of choice) I highly recommend modifying, creating, deleting, and experimenting with your own flow. This is just how one engineer works and is an attempt to unify and codify things that might help people get a more consistent flow with less of a headache of config.

### The mental model

**Interactive mode:** The workflow (`plan → spec → implement → review`) is meant to be done in order, but any step can be started independently if you've already planned, implemented, etc.

**Autonomous mode (Ralph):** Uses Geoffrey Huntley's Ralph methodology — an autonomous coding loop where Claude picks tasks, implements, tests, commits, and updates the plan with no human in the loop. You can take your spec and let Ralph run off with it.

## Commands

### Core Workflow

| Command | What it does |
|---------|--------------|
| `/agentic-coding-workflow:prime` | Loads initial context — git logs, docs, project structure. Add `--deep` for thorough codebase analysis. |
| `/agentic-coding-workflow:plan` | Interactive planning partner. Takes a ticket ID or feature description, explores edge cases, produces a plan doc. |
| `/agentic-coding-workflow:write-spec` | Transforms a plan into an implementation spec with atomic, actionable tasks. |
| `/agentic-coding-workflow:implement` | Picks up a task from a spec and builds it out. Also supports ad-hoc descriptions with plan-first flow. |
| `/agentic-coding-workflow:test` | Detects project test framework, runs the suite (or a subset), and reports structured results. |
| `/agentic-coding-workflow:review` | Unified code review — PR review, spec compliance (`--spec`), plan critique (`--plan`), WIP squash (`--prep`), or interactive PERFECT training (`--learn`). Track progress with `--stats`. Auto-detects Elixir/Python, supports parallel multi-branch reviews. |
| `/agentic-coding-workflow:ship` | Pushes the current branch, creates a PR with a generated description, and reports the URL. |

### Autonomous & Parallel

| Command | What it does |
|---------|--------------|
| `/agentic-coding-workflow:ralph` | Autonomous coding loop. Works through every task unattended — implements, tests, commits, updates the plan, repeats. Supports `--once` (HITL mode), `--clean-room` (greenfield), `--harvest` (extract patterns), `--parallel` (multiple worktrees), `--checkpoint-every=N` (human steering pauses), `--eval-gates-merge` (block merge on REVISE verdict), and `--time-budget=N` (per-iteration time limit). Desktop notifications for key events. |
| `/agentic-coding-workflow:parallel` | Spins up N worktrees with tmux panes and Claude sessions for parallel task work. |
| `/agentic-coding-workflow:reunify` | Merges parallel worktree branches back, runs tests after each merge, resolves conflicts, and verifies against the spec. |
| `/agentic-coding-workflow:spawn` | Launches a full Claude Code session in a tmux pane with an agent role preloaded — for when you need a visible, steerable instance. |
| `/agentic-coding-workflow:dashboard` | Live tmux dashboard monitoring all active worktrees and Claude activity. |

### Debugging & Analysis

| Command | What it does |
|---------|--------------|
| `/agentic-coding-workflow:debug-bug` | Bug hunter — finds and fixes bugs with structured investigation. |
| `/agentic-coding-workflow:troubleshoot` | Infrastructure diagnostics + kubectl access. Covers local Docker, staging, and prod k8s. |
| `/agentic-coding-workflow:analyze` | Data analyst — takes query results, CSVs, or datasets and produces insights, summaries, and visualizations. |
| `/agentic-coding-workflow:query` | Translates natural language questions into SQL, runs them, and presents results. |
| `/agentic-coding-workflow:techdebt` | Scans the codebase for tech debt and surfaces actionable findings. |

### Learning & Improvement

| Command | What it does |
|---------|--------------|
| `/agentic-coding-workflow:explain` | Educational breakdown of code, changes, or systems — the "why" behind the code, not just what it does. |
| `/agentic-coding-workflow:visualize` | Generates architecture diagrams — ASCII for terminal, Mermaid for docs, HTML for rich visuals. |
| `/agentic-coding-workflow:grill-me` | Reviews your staged changes, generates tough questions about edge cases and design decisions. You have to demonstrate understanding before proceeding to PR. |
| `/agentic-coding-workflow:elegant-redo` | Scraps a failed implementation and redoes it with hindsight from what went wrong. |
| `/agentic-coding-workflow:harness-audit` | Inventories all harness components, documents their assumptions, and suggests simplification experiments as models improve. |
| `/agentic-coding-workflow:update-rules` | Updates CLAUDE.md or `.claude/rules/` after corrections or pattern discoveries. |

## Skills

| Skill | What it does |
|-------|--------------|
| `/agentic-coding-workflow:checkpoint` | Manage session checkpoints — save, list, restore, fork, rewind |
| `/agentic-coding-workflow:git-worktree` | Manages git worktrees — add, list, remove, status dashboard, and cleanup |
| `/agentic-coding-workflow:parallel` | Creates multiple worktrees with tmux panes and Claude sessions for parallel work |
| `/agentic-coding-workflow:reunify` | Reunifies parallel worktree branches back onto a parent feature branch |
| `/agentic-coding-workflow:skill-forge` | Build, fix, and optimize Claude Code skills — scaffolding, progressive disclosure, eval-driven iteration |
| `tmux-multiplexer` | Controls tmux for spinning up multi-agent workflows and parallel tasks |
| `neovim-controller` | Talks to a running Neovim instance via RPC — open files, run LSP commands, navigate symbols |
| `pr-reviewer` | The brains behind `/agentic-coding-workflow:review` — uses the PERFECT framework (Purpose, Edge Cases, Reliability, Form, Evidence, Clarity, Taste) with source-grounded findings. Knows Elixir and Python patterns, auto-detects language |
| `ralph` | Orchestrates autonomous Ralph loop iterations with separated evaluator, tiered evaluation modes, pre-flight checks (override staleness, plan-spec alignment), and desktop notifications |
| `data-analytics` | Database querying and data analysis support — MCP server config, connection setup, SQL help |

## Agents

Reusable agent role definitions in `agents/` — work as both subagent prompts (via the `Agent` tool) and full primary instances (via `claude --context`).

| Agent | Role |
|-------|------|
| `researcher` | Read-only research and exploration |
| `implementer` | Code implementation from specs and tasks |
| `test-writer` | Test creation and coverage |
| `evaluator` | Independent code evaluation (used by Ralph) |
| `explorer` | Codebase exploration and analysis |

## Hooks

| Hook | Event | What it does |
|------|-------|--------------|
| `dangerous_command_blocker.py` | PreToolUse | Catches dangerous commands (`rm -rf /`, `.env` access) and blocks them |
| `subagent_permission_router.py` | PreToolUse | Auto-approves read-only tools for all sessions, extra tools for subagents |
| `ship-gate.sh` | PreToolUse | Blocks `gh pr create` unless PR description exists and user approved it |
| `audit-logger.py` | PostToolUse | Logs all tool calls to `.claude/logs/tool-calls.jsonl` for audit and debugging |
| `lint-on-stop.sh` | Stop | Runs linting and tests when Claude stops — blocks and asks Claude to fix errors |
| `rule-capture-on-stop.sh` | Stop | After implementation, prompts about capturing learned patterns as rules |
| `ralph-on-stop.sh` | Stop | In Ralph mode, manages iteration handoff and plan updates |
| `validate-output.py` | Stop | Validates command output artifacts exist and contain required sections |
| `toast-notify.sh` | Stop | Pops up a macOS notification when Claude needs your attention |
| `stop-failure-logger.sh` | StopFailure | Logs API failures (rate limits, auth errors) and sends toast notifications |
| `cleanup-review-worktrees.sh` | SessionEnd | Removes orphaned `pr-review-*` worktrees left by crashed sessions |

## CLAUDE.md & Rules System

This plugin ships with a `CLAUDE.md` and `.claude/rules/` directory that teach Claude how to work on this plugin. Projects that install this plugin should create their own:

- **`CLAUDE.md`** (project root) — project-wide conventions, architecture, preferred patterns
- **`.claude/rules/<topic>.md`** — path-scoped rules that only load when Claude touches matching files (uses YAML `globs:` frontmatter)
- **`~/.claude/CLAUDE.md`** — personal preferences that apply across all projects

The `/agentic-coding-workflow:update-rules` command helps you build these up over time. The `rule-capture-on-stop` hook gently reminds you to capture patterns after implementation tasks.

**Scope precedence:** Managed policy > CLI args > Local settings > Project settings > User settings

## Typical Workflow

### Interactive (human-in-the-loop)

1. `/agentic-coding-workflow:prime` — Load up context for a ticket
2. `/agentic-coding-workflow:plan AI-1234` — Talk through what you're building, go over edge cases and things you might not have thought of
3. `/agentic-coding-workflow:review --plan` — Get a plan critique (optional)
4. `/agentic-coding-workflow:write-spec feature-name` — Turn the plan into an implementation spec
5. `/agentic-coding-workflow:implement 1` — Build task 1 from the spec
6. Repeat for remaining tasks. Use `/agentic-coding-workflow:parallel 3 specs/feature/` to work on multiple tasks simultaneously with auto task assignment
7. `/agentic-coding-workflow:reunify` — Merge parallel branches back (if you used parallel)
8. `/agentic-coding-workflow:test` — Run the test suite
9. `/agentic-coding-workflow:review --spec` — Make sure it matches the spec
10. `/agentic-coding-workflow:ship` — Create the PR

### Autonomous (Ralph loop)

Best when the spec is solid and you'd rather review a finished branch than babysit each task.

1. `/agentic-coding-workflow:prime` — Load context
2. `/agentic-coding-workflow:plan AI-1234` — Plan the feature
3. `/agentic-coding-workflow:review --plan` — Critique the plan (don't skip — last chance to steer before Ralph takes over)
4. `/agentic-coding-workflow:write-spec feature-name --ralph` — Generate atomic specs + implementation plan
5. `/agentic-coding-workflow:ralph feature-name --once` — Run a single watched iteration to validate spec and plan (HITL mode)
6. `/agentic-coding-workflow:ralph feature-name` — Launch the autonomous loop
7. Go do something else. Check back with `/agentic-coding-workflow:ralph feature-name --status` or read `.claude/ralph-status.md`
8. Steer mid-loop by writing instructions to `.claude/ralph-inject.md`
9. `/agentic-coding-workflow:ralph feature-name --harvest` — After completion, extract reusable patterns
10. `/agentic-coding-workflow:review --spec` → `/agentic-coding-workflow:ship` — Review and create the PR

For greenfield work, add `--clean-room` to skip codebase search. For large features, `--parallel 3` splits work across worktrees — three independent Claude instances working through dependency-ordered tasks simultaneously.

**"Where do I start?"**
Run `claude` in a project. Try `/agentic-coding-workflow:prime` then `/agentic-coding-workflow:plan` with a feature idea. Once comfortable, try `/agentic-coding-workflow:implement` on a task, and then `/agentic-coding-workflow:ralph` on a small spec.
