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
/plugin install agentic-coding-workflow@agentic-coding-marketplace
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
- `/agentic-coding-workflow:implement "<change>"` — inspects, implements, verifies, and reports; plans when needed
- `/agentic-coding-workflow:plan` — get a concise plan for a substantial or ambiguous task
- `/goal <measurable completion condition>` — ordinary unattended continuation in the same session
- `/agentic-coding-workflow:ralph` — specialized execution with enforced limits and recovery

## Why This Exists

**This plugin adds opinionated workflows on top of Claude Code** so you don't have to figure out prompting patterns yourself. Once you're more comfortable with Claude Code (or your agentic TUI of choice) I highly recommend modifying, creating, deleting, and experimenting with your own flow. This is just how one engineer works and is an attempt to unify and codify things that might help people get a more consistent flow with less of a headache of config.

### The mental model

Use the least elaborate workflow that resolves material uncertainty and produces verifiable results.

| Task | Default workflow |
|------|------------------|
| Small, clear change | Inspect relevant context → implement → verify → report |
| Substantial feature | Clarify material uncertainty → maintain a concise plan → implement → verify → review |
| Ordinary unattended work | Set a native `/goal` → continue in one isolated feature session → verify → review |
| Enforced limits or coordinated recovery | Select Ralph with agreed boundaries → execute in owned worktrees → verify → review |

Choose by uncertainty, impact, reversibility, and scope. Inspection may reveal a need for more planning, or show that existing context is sufficient. Clarification ends when the outcome, scope, material decisions, and verification approach are clear. Every path includes verification and reports its evidence and limitations.

Make substantial changes independently understandable and testable. PRs explain
the problem and resulting behavior, important decisions, actual verification
and checked source, remaining reviewer decisions, and recovery when relevant.
Keep concurrency within the team's review capacity. The shared
[review policy](references/review-policy.md) covers evidence and review scope.

Default code reviews prioritize actionable defects with local evidence; a clean
result is valid. `/review --suggestions` adds optional design/taste feedback.
Authorized author/reviewer repair carries prior findings and the round count;
after three completed rounds, unresolved material findings need human
reassessment. An ordinary review performs one pass. Existing human review
requirements remain in force.

For interactive work, a conversational plan is often enough. Save a plan or generate a detailed spec when requested or useful for handoff. `/plan --interview` selects deeper questioning; `/write-spec` selects detailed specification; `/explain` and `/review --learn` select teaching; `/implement --approve-tests` selects explicit approval of acceptance-test expectations. `/implement --plan` selects plan mode and plan approval, and `--worktree` requests isolation. These are optional modes, with no fixed question or document-length quotas.

**Ordinary unattended work:** Use native `/goal` in a continuing feature session.
Keep related tasks and their decisions together, compact context when needed,
and resume the named session after an interruption. The normal path does not
require a spec directory, task partitioner, generated briefings, or a commit and
fresh session after every task. Deterministic verification and required
independent review still apply.

**Specialized execution (Ralph):** Select this executor for enforced iteration/time
limits, dependency waves, rollback, or durable execution records. It uses
isolated single-task workers, external checks, and mandatory independent
verification-integrity review. RED/GREEN commits are optional; test files are
not frozen. Corrections or possible coverage reductions need rationale and
review, and human-approved expectations need human approval to change. The
launch command confirms scope and limits before starting unless those settings
are already authorized.

## Commands

### Core Workflow

| Command | What it does |
|---------|--------------|
| `/agentic-coding-workflow:prime` | Loads project and optional Jira/Linear ticket context through CLI/API tools. Add `--deep` for thorough codebase analysis. |
| `/agentic-coding-workflow:plan` | Writes a concise plan from a ticket, description, or context document; asks about material uncertainty. Add `--interview` for deeper exploration. |
| `/agentic-coding-workflow:write-spec` | Transforms a plan into an implementation spec with atomic, actionable tasks. |
| `/agentic-coding-workflow:implement` | Implements a ticket, spec task, or description with proportional planning/verification. Optional `--plan`, `--worktree`, `--approve-tests`, `--start-ticket`, and independent `--review` modes. |
| `/agentic-coding-workflow:test` | Detects project test framework, runs the suite (or a subset), and reports structured results. |
| `/agentic-coding-workflow:review` | Code/PR review, spec compliance (`--spec`), plan critique (`--plan`), PR prep (`--prep`), or teaching (`--learn`, `--stats`). Supports Go, Python, TypeScript/JavaScript, Elixir, and mixed changes. Use `--suggestions` for optional design/taste feedback. |
| `/agentic-coding-workflow:ship` | Pushes the branch and creates/reuses a PR. Optional `--follow-up` handles CI/review repairs; `--link-ticket` and `--ticket-status` request ticket updates. |

### Autonomous & Parallel

| Command | What it does |
|---------|--------------|
| `/agentic-coding-workflow:ralph` | Autonomous coding loop. Works through every task unattended — implements, tests, commits, updates the plan, repeats. Supports `--once` (one observed autonomous iteration), `--clean-room` (greenfield), `--harvest` (extract patterns), `--parallel` (multiple worktrees), `--checkpoint-every=N` (human steering pauses), `--eval-gates-merge` (require a fresh end-of-run ACCEPT verdict before merge), and `--time-budget=N` (per-iteration time limit). Desktop notifications for key events. |
| `/agentic-coding-workflow:parallel` | Spins up N worktrees with tmux panes and Claude sessions for parallel task work. |
| `/agentic-coding-workflow:reunify` | Merges parallel worktree branches back, runs tests after each merge, resolves conflicts, and verifies against the spec. |
| `/agentic-coding-workflow:spawn` | Starts a named plugin agent with native worktree/tmux support; `--goal` starts native continuation, and `--resume <session>` restores existing work. |
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
| `/agentic-coding-workflow:harness-audit` | Inventories all harness components, documents their assumptions, and suggests simplification experiments as models improve. |
| `/agentic-coding-workflow:update-rules` | Updates CLAUDE.md or `.claude/rules/` after corrections or pattern discoveries. |

## Skills

| Skill | What it does |
|-------|--------------|
| `/agentic-coding-workflow:git-worktree` | Uses native interactive worktrees; retains owned-worktree creation, status, preservation, and cleanup for specialized executors |
| `/agentic-coding-workflow:parallel` | Creates multiple worktrees with tmux panes and Claude sessions for parallel work |
| `/agentic-coding-workflow:reunify` | Reunifies parallel worktree branches back onto a parent feature branch |
| `/agentic-coding-workflow:skill-forge` | Build, fix, and optimize Claude Code skills — scaffolding, progressive disclosure, eval-driven iteration |
| `tmux-multiplexer` | Controls tmux for spinning up multi-agent workflows and parallel tasks |
| `neovim-controller` | Talks to a running Neovim instance via RPC — open files, run LSP commands, navigate symbols |
| `pr-reviewer` | Inspects Go, Python, TypeScript/JavaScript, Elixir, and mixed changes using PERFECT as an inspection guide; reports actionable findings, verification limits, and human decisions concisely |
| `/agentic-coding-workflow:ralph` | Launches the specialized executor with enforced limits, verification, recovery records, and desktop notifications |
| `data-analytics` | Database querying and data analysis support — MCP server config, connection setup, SQL help |

### Invocation and gradual migration

Claude Code still supports existing command files and prefers skills for new
work. This plugin keeps its existing commands while consolidating overlapping
workflows as they are maintained. `ralph` and `reunify` now each have one skill
entrypoint; their slash names and arguments are unchanged. Shared workflow
patterns live in [references/shared-patterns.md](references/shared-patterns.md),
outside command discovery. See the [Claude Code skills documentation](https://code.claude.com/docs/en/skills).

Publishing (`ship`), session/worker launches (`spawn`, `ralph`, `parallel`,
`tmux-multiplexer`), branch/worktree changes (`reunify`, `git-worktree`), and
infrastructure operations (`troubleshoot`) use
`disable-model-invocation: true` for explicit invocation. Background reference
skills use `user-invocable: false` where appropriate: that hides the user command
while allowing the model to invoke the skill. Invocation controls do not replace
the authorization needed for the actions a workflow performs.

### Native sessions and recovery

The custom `/agentic-coding-workflow:checkpoint` skill has been retired. Use
native `/rewind` for session recovery, `/resume` to continue a saved session,
and `/branch` for a conversation branch. Existing `.claude/checkpoints/` files
are left untouched; their metadata and notes do not restore conversation state
or uncommitted file contents. Keep durable history in Git. Native recovery has
[documented coverage and retention limits](https://code.claude.com/docs/en/checkpointing).
Ralph's `--checkpoint-every` remains a separate human steering pause.

For ordinary interactive isolation, use native `EnterWorktree` in a session or
`claude --worktree <name> --tmux` for a new one. `/spawn <role> --worktree <name>`
loads the plugin's agent and delegates the same setup to Claude Code. Names
follow native worktree semantics. Shared-checkout panes and specialized Ralph,
review, and parallel executors retain their explicit lifecycle controls. Plugin
cleanup preserves native worktrees, whose lifecycle is managed by Claude Code.
See the [native worktree guide](https://code.claude.com/docs/en/worktrees).

Keep one session for related feature work. `/spawn` uses `--name` when supplied,
or the worktree name for an isolated session. Return with `/resume <name>` or
`/spawn --resume <name>`; the latter restores the saved agent and checkout
without creating another worktree. Native compaction retains a summary; keep
the criteria, decisions, constraints, remaining work, and verification commands
in focus. Recheck current state after resume, including interrupted commands.
Start fresh for unrelated work, strict isolation, or demonstrated context
degradation. Independent reviewers and explicit Ralph workers keep their own
contexts. See [session management](https://code.claude.com/docs/en/sessions).

## Agents

Reusable agent role definitions in `agents/` — work as both subagent prompts (via the `Agent` tool) and full primary instances (via `claude --plugin-dir /path/to/agentic-coding-workflow --agent agentic-coding-workflow:<role>`).

Read a few relevant files directly. Delegate investigations whose intermediate output would overwhelm the main task, parallelize independent components with clear interfaces, and use independent verification when its expected benefit justifies its cost. Implementation can run in the current session, a capable subagent, or a separate primary instance; choose by tools, permissions, turn budget, isolation, and oversight. See the [routing policy](CLAUDE.md#subagents-vs-primary-instances--when-to-use-which) and [Claude subagent reference](https://code.claude.com/docs/en/sub-agents).

| Agent | Role |
|-------|------|
| `implementer` | Code implementation from specs and tasks |
| `test-writer` | Test creation and coverage |
| `evaluator` | Independent code evaluation (used by Ralph) |

## Hooks

The default hooks require Python 3.11+, Bash, Git, and jq; their Python scripts use the standard library and do not require uv. Tool approvals use Claude Code's normal permission handling. Command/skill `allowed-tools` and CLI `--allowedTools` grant prompt-free approval; they are not a complete tool whitelist. CLI `--tools` restricts available tools and `--disallowedTools` adds explicit denies. See the [CLI reference](https://code.claude.com/docs/en/cli-reference).

| Hook | Event | What it does |
|------|-------|--------------|
| `dangerous_command_blocker.py` | PreToolUse | Catches dangerous commands (`rm -rf /`, `.env` access) and blocks them |
| `lint-on-stop.sh` | Stop | Runs project-configured lint/test commands for any stack, or legacy Elixir checks; records revision/fingerprint and distinguishes incomplete/disabled verification |
| `ralph-on-stop.sh` | Stop | During Ralph builds, enforces plan updates; review stays in the outer executor |
| `validate-output.py` | Stop | Validates registered task graphs using the scheduler's shared parser |
| `toast-notify.sh` | Stop | Pops up a macOS notification when Claude needs your attention |
| `stop-failure-logger.sh` | StopFailure | Logs API failures (rate limits, auth errors) and sends toast notifications |

Review worktree cleanup belongs to the launcher and the individual review process.
They track only worktrees created by that invocation, check ownership and activity,
archive workflow artifacts, and remove clean checkouts without force. Partial launch
failures clean up pending worktrees; launched reviews handle their own exit. Dirty,
unmerged, locked, active, or unowned worktrees are retained with their paths reported.
There is no global session-end sweep. Uncatchable termination leaves worktrees for
explicit recovery through the worktree workflow, retaining its safety checks.

Task-graph validation checks structured and legacy task indexes with the same
parser used by the scheduler. Ordinary plans and specs have no output-registration
step. Ralph planning and `write-spec --ralph` register graph checks only; legacy
artifact, heading, and line-count expectations are ignored.

Python tooling is project-specific. The global toolchain blocker and regex style hook have been removed. `/agentic-coding-workflow:setup-python-rules` adapts judgment guidance to the existing stack. The optional [uv/Ruff/basedpyright profile](profiles/python/uv-ruff-basedpyright/README.md) supplies actual tool configuration and check commands only when explicitly selected. Tool configuration owns formatting, lint, typing, and file exclusions.

`/ship` prepares the destination, branch/commit, PR title, complete body, base/head, and draft status before any required review. It chooses a title from the final change and reuses existing authorization for unchanged actions. The agent-writable approval marker and ship hook have been removed: the workflow is an instruction-level policy, not authenticated approval enforcement. Organizations requiring enforcement need a trusted external permission service or publishing executor with approval storage inaccessible to the agent, bound to the exact outgoing action and content. See [External Actions and Approval](references/shared-patterns.md#external-actions-and-approval).

## Jira and Linear without MCP connectors

Ticket-aware workflows share a CLI-first resolver. Jira uses `acli` when the
requested operation is supported. Both providers have direct API adapters;
Linear or another Jira CLI can use an explicitly configured argv/JSON adapter.
There is no implicit CLI install, login, account switching, or MCP requirement.

Set `.claude/ticket-tracker.json` in the **consuming project**, for example:

```json
{
  "default_provider": "jira",
  "providers": {
    "jira": {
      "site": "https://example.atlassian.net",
      "status_map": {"in_progress": "In Progress", "in_review": "Code Review"}
    }
  }
}
```

Use your actual statuses/site. `auto` uses the supported installed CLI first,
then configured API access for unavailable operations; a failing CLI does not
silently fall back. Jira API credentials default to `JIRA_EMAIL` and
`JIRA_API_TOKEN`; Linear defaults to `LINEAR_API_KEY`. Keep credential values
in your existing environment/secret tooling. A CLI login does not configure
API credentials. See [Ticket trackers](references/ticket-trackers.md) for
OAuth/scoped-token settings, custom CLI contracts, identity checks, and limits.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tickets.py" --project-dir "$PWD" doctor
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tickets.py" --project-dir "$PWD" doctor --check
```

The first command inspects available connections/versions; `--check` also probes
authentication with read-only operations. Neither proves write permission.
URLs select their tracker; a bare `ABC-123` uses the project default or explicit
`--tracker jira|linear`. The same key can exist in both providers.

```text
/agentic-coding-workflow:implement ABC-123 --tracker jira --worktree --start-ticket --review
/agentic-coding-workflow:ship --ticket https://example.atlassian.net/browse/ABC-123 --link-ticket --follow-up
```

Implementation retrieves the ticket, establishes scope/checks, optionally starts
it, and includes bounded independent review/repair. Review the diff/evidence
yourself before invoking ship. Shipping can follow CI/review feedback for a
default 15-minute conversational budget and reuse the same three-round review
history. It does not merge. A read-only `scripts/pr-status.py PR_URL --head SHA`
helper binds checks and unresolved review threads to the published revision.
Ticket writes are opt-in; low-level `transition`/`link-pr` commands prepare JSON
without writing until `--apply` is supplied. See [Delivery follow-up](references/delivery-follow-up.md)
for draft PRs, status timing, failures, single-writer coordination, and pilot
measurements. Live-provider and native-agent validation are separate from the
deterministic adapter tests.

## CLAUDE.md & Rules System

This plugin ships with a `CLAUDE.md` and `.claude/rules/` directory that teach Claude how to work on this plugin. Projects that install this plugin should create their own:

- **`CLAUDE.md`** (project root) — project-wide conventions, architecture, preferred patterns
- **`.claude/rules/<topic>.md`** — path-scoped rules that only load when Claude touches matching files (uses YAML `paths:` frontmatter)
- **`~/.claude/CLAUDE.md`** — personal preferences that apply across all projects

Claude Code only reads `paths` from rule frontmatter; other fields are ignored. Rules without `paths` load unconditionally. See the [rule frontmatter reference](https://code.claude.com/docs/en/memory#rule-frontmatter-reference).

The `/agentic-coding-workflow:update-rules` command helps you capture useful corrections and patterns when requested.

**Scope precedence:** Managed policy > CLI args > Local settings > Project settings > User settings

## Typical Workflow

Project commands are configured in `.claude/project-commands.json`. For an existing Black/mypy project, for example:

```json
{
  "test": "python -m pytest",
  "lint": "python -m black --check . && python -m mypy .",
  "format": "python -m black ."
}
```

Supported keys are `build`, `test`, `lint`, `format`, and `run`. Go, Python,
TypeScript/JavaScript, and mixed projects select commands from their existing
CI/task configuration. Missing lint/test actions are unconfigured; null or an
empty string explicitly disables an action. Invalid configuration blocks.
The Stop hook and Ralph verification reject missing checks. Ralph's generator
leaves unknown commands missing, preserves overrides/disables, and renders
`.claude/AGENTS.md`; it retains legacy defaults for Elixir-only projects. Move
custom commands from that Markdown guide to the JSON file. Both files are
copied into worker worktrees. See [Project readiness](references/project-readiness.md)
for setup/service documentation and mixed-project aggregate commands.

Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/project-commands.py" readiness "$PWD"`
from the consuming project with the plugin root set. This read-only JSON report
distinguishes configured, unconfigured, disabled, invalid, and legacy/unsupported
roots. It does not run checks or prove environment readiness. Separate review
launches inspect this configuration and never install dependencies or change
lockfiles; missing dependencies remain explicit verification limitations.

Formatting is explicit: `"${CLAUDE_PLUGIN_ROOT}/scripts/format-project.sh"` runs
the configured format command, with a legacy Elixir default when absent. Stop
runs configured lint/test commands for any stack, preserving quoting and pipe
failures. Missing actions produce incomplete verification; both actions disabled
produce a disabled record, never passed. Include required check-only formatting
and typing in lint, and keep scope in tool configuration. Checks must not fix
files or install dependencies. The optional uv profile uses `--frozen --no-sync`.
Configured checks run on every branch, including committed code.

Verification records in `.claude/verification/<session-hash>.json` identify `HEAD` and a SHA-256 of the working inputs before and after checks. Ignored project commands, rules, guidance, and specs participate in the fingerprint; runtime logs and markers do not. `scope: "worktree"` includes local inputs beyond the committed tree. Correction turns verify again, and an earlier success is reused only for unchanged inputs. Three failed attempts produce an explicit `blocked` result and stop with a user-visible failure; a new user turn can retry. Infrastructure failures remain `incomplete`, state-capture failures remain `unavailable`, and a crash leaves `running`, never a stale success.

Ralph records prompt, Claude, and stream-processor statuses separately in `<iteration-log>.status.json` and saves each stage's stderr. A failed stage stops the run with a nonzero exit and preserves work without marking its commits accepted. Worker and merge failures block dependent waves. Each run has unique worktree and branch names, so preserved work does not collide with a later run.

All evaluator modes use the same `ACCEPT` / `REVISE` / `ERROR` / `NOT_RUN` contract. Evaluators use native restricted permissions with Read, Glob, and Grep, no shell or write tools, no MCP tools, and explicit denies for common secret paths. The controller supplies diff/log evidence and writes the reports from validated structured CLI output. Scores use the documented 1–5 scale; missing evidence, inconsistent averages, process errors, timeouts, and changes during evaluation are ERROR. Reports include the candidate SHA and source fingerprint. Iteration, wave, and final reports retain separate paths. Restricted evaluators require Claude Code v2.1.248 or later.

Final verification precedes evaluation and cleanup. Single-run merges recheck the candidate and target after confirmation and fast-forward to the verified SHA; a diverged target requires integration and fresh verification. Parallel runs also invalidate verification after any candidate change. `--eval-gates-merge` requires a current ACCEPT; optional advisory evaluation can report REVISE, while ERROR remains a failed run. UI evaluation reads evidence captured before final verification from `RALPH_EVAL_UI_EVIDENCE`, a nonempty directory inside the project, rather than starting a server or browser with evaluator permissions.

Hook feedback follows the [Claude Code hook protocol](https://code.claude.com/docs/en/hooks). StopFailure logs API errors, including the rendered error message, to `.claude/logs/stop-failures.jsonl`; it provides observability and notifications, with no automatic retry or worker lifecycle transition.

Ralph plans use a fenced JSON `{"tasks": [...]}` index under `## Task Index`. Each task has `id`, `name`, `status` (`pending`/`done`), `priority`, `deps` (integer IDs), and `files` (path strings), with optional `spec` and `completed_in`. The shared `scripts/task-plan.py` parser validates the entire dependency graph before scheduling. Unknown IDs, duplicates, self-dependencies, and cycles are errors. Existing checkbox plans remain supported; all comma-separated dependencies are preserved. Completed dependencies are already satisfied. The planner, progress displays, stop validator, and scheduler use the same task model.

Parallel run artifacts live under `.claude/ralph/<slug>/runs/<run>/`. `trace.jsonl` contains orchestrator events. Worker inputs are preserved as `worker-traces/<wave-worker>/<worker-run>/trace.jsonl`. `unified-trace.jsonl` combines every input in timestamp order and labels events with `source` and `worker_run`. It is refreshed on exit to include final verification, evaluation, and completion events, and remains after worker cleanup. The retrospective and analysis tools consume this combined artifact. To reproduce it, run `scripts/stitch-traces.sh <run>/worker-traces <slug> <run>/trace.jsonl <run>/unified-trace.jsonl`. Invalid input fails visibly and leaves any prior combined artifact intact.

### Small, clear change

Run `/agentic-coding-workflow:implement "fix the health check response header"`. It inspects the relevant code, makes the change in the current checkout, runs appropriate checks, and reports the result. Existing work and project rules are respected. No separate plan, spec, worktree, or approval round is required by default.

### Substantial feature

Clarify decisions that affect behavior, scope, or risk, then maintain a concise plan while implementing. A typical flow is `/plan` → `/implement "<planned feature>"` → `/review`. `/implement` can also manage a conversational plan itself. Use `/test` for additional test runs and `/ship` when ready to publish.

For a detailed handoff, select the spec workflow:

1. `/agentic-coding-workflow:prime` — Load up context for a ticket
2. `/agentic-coding-workflow:plan AI-1234` — Talk through what you're building, go over edge cases and things you might not have thought of
3. `/agentic-coding-workflow:review --plan` — Get a plan critique if useful
4. `/agentic-coding-workflow:write-spec feature-name` — Turn the plan into an implementation spec
5. `/agentic-coding-workflow:implement 1` — Build task 1 from the spec
6. Repeat for remaining tasks. Use `/agentic-coding-workflow:parallel 3 specs/feature/` to work on multiple tasks simultaneously with auto task assignment
7. `/agentic-coding-workflow:reunify` — Merge parallel branches back (if you used parallel)
8. `/agentic-coding-workflow:test` — Run the test suite
9. `/agentic-coding-workflow:review --spec` — Make sure it matches the spec
10. `/agentic-coding-workflow:ship` — Create the PR

### Ordinary unattended feature work

In an already isolated feature session, enter the completion condition directly:

```text
/goal The agreed authentication criteria hold, and the project's configured tests and lint pass with final results shown.
```

To start a separate named feature session with the plugin's implementation role:

```text
/agentic-coding-workflow:spawn implementer --worktree auth-update --goal "The agreed authentication criteria hold, and configured tests and lint pass with final results shown."
```

This delegates to native `/goal` as the initial prompt, names the session
`auth-update`, and leaves permission handling unchanged. Continue related
follow-ups there. Use `/goal` for status, `/goal clear` to clear the condition,
and native `/compact` when a focused summary would help. Return later with
`claude --resume auth-update`; an active goal restores with the session, while
an achieved or cleared goal does not. Set a new goal explicitly when needed.

Write conditions that can be demonstrated by real checks. The native evaluator
judges surfaced conversation evidence and does not inspect the environment
independently. A time/turn clause is model-judged, not an enforced process limit.
Keep deterministic checks and required independent review; use Ralph when
external bounds or executor recovery are required. An impossible verdict or a
cleared goal is not verified completion. See [native goals](https://code.claude.com/docs/en/goal).

### Enforced limits and coordinated recovery (Ralph)

Use Ralph when the task needs its external limits, scheduling, rollback, or
durable executor records. Its one-task worker sessions remain an explicit
isolation boundary. Ordinary serial feature work uses the native goal path above.

1. `/agentic-coding-workflow:prime` — Load context
2. `/agentic-coding-workflow:plan AI-1234` — Plan the feature
3. `/agentic-coding-workflow:review --plan` — Critique material risks if useful
4. `/agentic-coding-workflow:write-spec feature-name --ralph` — Generate atomic specs + implementation plan
5. `/agentic-coding-workflow:ralph feature-name --once` — Observe one autonomous iteration, then review its results to validate the spec and plan
6. `/agentic-coding-workflow:ralph feature-name --max 20 --time-budget=600` — Approve scope, completion checks, limits, and stop conditions, then launch in isolation
7. Go do something else. Check back with `/agentic-coding-workflow:ralph feature-name --status` or read `.claude/ralph-status.md`
8. Steer mid-loop by writing instructions to `.claude/ralph-inject.md`
9. `/agentic-coding-workflow:ralph feature-name --harvest` — After completion, extract reusable patterns
10. `/agentic-coding-workflow:review --spec` → `/agentic-coding-workflow:ship` — Review and create the PR

For greenfield work, add `--clean-room` to skip codebase search. For large features, `--parallel 3` splits work across worktrees — three independent Claude instances working through dependency-ordered tasks simultaneously.

**"Where do I start?"**
Run `claude` in a project and use `/agentic-coding-workflow:implement "<clear change>"`.
For an ambiguous feature, start with `/agentic-coding-workflow:plan`. Keep related
tasks in that session. Use native `/goal` for ordinary unattended continuation;
select `/agentic-coding-workflow:ralph` for enforced bounds or executor recovery.

## Validation and behavioral evaluation

Local structural diagnostics identify missing skill files, frontmatter fields,
resources, and script issues. They do not assign a quality score or establish
that a skill improves outcomes:

```bash
python3 skills/skill-forge/scripts/validate-skill.py skills/skill-forge --verbose
python3 -m pytest -q
bash scripts/validate-hooks.sh
claude plugin validate .
```

Reusable native eval cases under `evals/` cover skill creation and repair,
triggering near-misses, explicit invocation policy, native isolated and goal
sessions, feature-session resume, and workflow selection. Cases, graders, and
sanitized [benchmark summaries](evals/benchmarks/) stay in version control.
With Claude Code v2.1.269 or later and model access, run tuning cases from this
trusted checkout:

```bash
claude plugin eval . --tag tuning --allow-tools Write Edit --no-publish
```

Freeze the candidate and success criteria, then run the final holdout separately:

```bash
claude plugin eval . --tag holdout --allow-tools Write Edit --no-publish
```

Choose descriptions and instructions using tuning results only. A holdout used
to guide further edits becomes tuning evidence; reserve fresh final cases
before claiming independent effectiveness. Unfiltered suite runs include holdout.

The default comparison runs cases with and without the plugin. Inspect outcome
differences, failures, cost, and duration; invocation checks diagnose triggering
rather than prove an outcome improved. Runs use model calls and their results
remain under ignored `evals/results/`. Preserve useful evidence in a tracked
summary before cleaning disposable workspaces. Native evals complement standards
validation and deterministic repository tests. See the [case and reporting policy](evals/README.md)
and [plugin eval documentation](https://code.claude.com/docs/en/plugin-evals).
