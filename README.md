# Agentic Coding Workflow

A Claude Code plugin with commands, skills, and hooks for a streamlined development workflow.

## Quick Start (2 minutes)

**1. Install Claude Code** (if you haven't already):
Native Install (recommended)
```bash
curl -fsSL https://claude.ai/install.sh | bash
```
Homebrew
```bash
brew install --cask claude-code
```

**2. Install this plugin** — from any project directory, run:
```bash
claude
# then inside Claude Code:
/plugin
# select "Add plugin" → paste this repo URL
```

**3. Start using it** — open your project and try:
```bash
cd your-project
claude
```
Then type any of these:
- `/prime` — loads your project context (git history, docs, structure)
- `/plan` — describe what you want to build, get a plan back
- `/implement` — builds from the plan
- `/ralph` — autonomous mode

## Why This Exists

**This plugin adds opinionated workflows on top of Claude Code** so you don't have to figure out prompting patterns yourself. Though, once you are more comfortable with Claude Code (or your agentic TUI of choice) I highly recommend modifying, creating, deleting, and experimenting with your own flow. This is just how one engineer works and is an attempt to unify and codify things that might help people get a more consistent flow with less of a headache of config.

### The mental model

**Interactive mode:** The workflow (`plan → spec → implement → review`) is meant to be done in order, but any step can be started independently if you've already planned, implemented, etc,.

**Autonomous mode (Ralph):** Experimental version of the workflow using the (in)famous Ralph Wiggums method. There's a script and more that explains it but basically you can take your spec and let Ralph run off with it.


## Commands

| Command | What it does |
|---------|--------------|
| `/prime` | Loads initial context. Looks at things like git logs and documents. Add `--deep` for a more thorough codebase analysis. |
| `/plan` | Interactive planning partner. Takes a ticket ID or feature description, goes over it with you, and produces a plan doc. |
| `/review-plan` | Spins up an agent to critique your plan if you really want to make sure it is tightened up. |
| `/write-spec` | Takes a plan doc and turns it into a proper implementation spec with atomic, actionable tasks. |
| `/implement` | Picks up a task from a spec and builds it out. Also supports ad-hoc descriptions with plan-first flow. |
| `/review-implementation` | Checks your code against the spec to make sure the agent actually built what you told it to. |
| `/debug-bug` | Bug hunter. |
| `/review-elixir` | Code review for Elixir PRs |
| `/review-python` | Code review for Python PRs |
| `/ralph` | Autonomous coding loop. Takes a spec, works through every task unattended — implements, tests, commits, updates the plan, repeats. Supports parallel mode with multiple worktrees. |
| `/update-rules` | Updates CLAUDE.md or `.claude/rules/` after corrections or pattern discoveries. |

## Skills

| Skill | What it does |
|-------|--------------|
| `/checkpoint` | Saves your current session state so you can come back to it later |
| `/checkpoints` | Lists all your saved checkpoints |
| `/rewind` | Goes back to an earlier checkpoint |
| `/restore` | Loads a specific checkpoint by name |
| `/fork-session` | Creates a safe "save point" before you try something risky |
| `/git-worktree` | Manages git worktrees so you can work on multiple branches at once |
| `tmux-multiplexer` | Controls tmux for spinning up multi-agent workflows and parallel tasks |
| `neovim-controller` | Talks to a running neovim instance via RPC - open files, run LSP commands, etc. |
| `elixir-pr-reviewer` | The brains behind `/review-elixir` - knows Elixir style guides and patterns |
| `python-pr-reviewer` | The brains behind `/review-python` - knows modern Python |
| `ralph` | Orchestrates autonomous Ralph loop iterations. Manages all the administrative stuff |

## Hooks

| Hook | What it does |
|------|--------------|
| `dangerous_command_blocker.py` | Catches dangerous commands like `rm -rf /` and blocks access to `.env` files |
| `lint-on-stop.sh` | Runs linting and tests when Claude tries to stop - if there are errors, it blocks and asks Claude to fix them |
| `rules-prompt.md` | After implementation tasks, gently prompts about capturing learned patterns as rules |
| `toast-notify.sh` | Pops up a macOS notification when Claude needs your attention |
| `ralph-plan-update` | In Ralph mode, verifies the implementation plan was updated before allowing Claude to exit |

## CLAUDE.md & Rules System

This plugin ships with a `CLAUDE.md` and `.claude/rules/` directory that teach Claude how to work on this plugin. Projects that install this plugin should create their own:

- **`CLAUDE.md`** (project root) — project-wide conventions, architecture, preferred patterns
- **`.claude/rules/<topic>.md`** — path-scoped rules that only load when Claude touches matching files (uses YAML `globs:` frontmatter)
- **`~/.claude/CLAUDE.md`** — personal preferences that apply across all projects

The `/update-rules` command helps you build these up over time. The `rules-prompt` stop hook gently reminds you to capture patterns after implementation tasks.

**Scope precedence:** Managed policy > CLI args > Local settings > Project settings > User settings

## Typical Workflow

### Interactive (human-in-the-loop)

1. `/prime` — Load up context for a ticket
2. `/plan AI-1234` — Talk through what you're building, go over edge cases and things you might not have thought of.
3. `/review-plan` — Get a plan critique (optional)
4. `/write-spec feature-name` — Turn the plan into an implementation spec
5. `/implement 1` — Build task 1 from the spec
6. `/review-implementation` — Make sure it matches the spec
7. Repeat 5-6 for remaining tasks. You can also do multiple tasks at a time with either a single agent using implement or multiple agents.

### Autonomous (Ralph loop)

Best when the spec is solid and you'd rather review a finished branch than babysit each task. Also useful for experimenting with how hands off you can comfortably get and still deliver excellent code quality.

1. `/prime` — Load context
2. `/plan AI-1234` — Plan the feature
3. `/review-plan` — Critique the plan (don't skip this — it's your last chance to steer directly without stopping Ralph)
4. `/write-spec feature-name --ralph` — Generate atomic specs + implementation plan
5. `/ralph feature-name` — Launch the autonomous loop
6. Go do something else. Check back with `/ralph feature-name --status`
7. Review the git log and merged result

For large features, `/ralph feature-name --parallel 3` splits work across worktrees — three independent Claude instances working through dependency-ordered tasks simultaneously.

**"Where do I start?"**
Run `claude` in a project. Try a few of the commands, read over the plugins a bit. Once you feel comfortable, try a few `/implement` tasks, and then try `/ralph` on a small spec.
