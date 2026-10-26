---
disable-model-invocation: true
allowed-tools:
  - Read
  - Glob
  - Bash
effort: low
---

# Spawn a Claude Session

Launch a visible, steerable session with a plugin agent role. Use the current
feature session for related tasks. Native compaction and resume manage its
context; spawning a new session is an explicit lifecycle choice.

## Phase 1: Parse the request

Parse `$ARGUMENTS` as either:

- `<role> [--name <name>] [--worktree <name>] [--context <file>] [--goal <condition> | prompt]`
- `--resume <session-name-or-id> [--context <file>] [--goal <condition> | prompt]`

Roles correspond to `agents/<role>.md` in this plugin. `--context` is a helper
option; the context file is read through the initial prompt, not a CLI flag.

Honor requests to prepare or explain a launch without executing it. Keep prompt
and path values as data when constructing shell arguments.

## Phase 2: Launch

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/spawn-session.sh" evaluator --worktree review-auth "Review authentication"
```

The helper loads the plugin and selects its namespaced `--agent`. With
`--worktree <name>`, it delegates creation and tmux setup to native
`claude --worktree <name> --tmux`. The value is a native worktree name, not a
promise to check out an existing branch of that name. No existing tmux session
is required. Native Claude Code owns this worktree's lifecycle and exit prompts.
See the [CLI reference](https://code.claude.com/docs/en/cli-reference).

These are ordinary sessions, so the helper disables inherited `RALPH_MODE`
build gates on both creation and resume. Ralph starts its workers through its
own executor.

Name a new session with `--name`; otherwise an isolated session uses its
worktree name. Related follow-ups stay there. `--resume <name-or-id>` delegates
directly to native resume, which restores the saved agent and checkout. It does
not create another worktree, reset the role, require tmux, or fall back to a
fresh session when resolution fails. Use native `/resume` inside a running
session. Avoid two workers writing to the same resumed transcript.

For an explicitly requested new goal session:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/spawn-session.sh" implementer --worktree auth-update --goal "The agreed auth criteria hold, and configured tests and lint pass with final results shown."
```

`--goal` is a helper option, not a Claude CLI flag. The helper passes a positional
`/goal <condition>` prompt to native Claude Code. Context instructions remain
inside the goal condition so `/goal` stays at the beginning. It does not add another execution loop,
generate a task plan, force commits, or change permissions. A plain prompt and
`--goal` are mutually exclusive. Follow **Native Goals and Session Continuity**
in `${CLAUDE_PLUGIN_ROOT}/references/shared-patterns.md`; native completion still needs real checks and
required independent review.

An active native goal restores on resume. Pass `--goal` while resuming only
when the user explicitly wants to replace the condition or start another one.
Native resume can reject slash-command prompts to a running background session;
report that result and use its native attach/resume flow instead of retrying
in a new session. See [session restoration](https://code.claude.com/docs/en/sessions).

For new sessions without `--worktree`, the helper opens an interactive pane in
the current checkout and requires an existing tmux session. This retains the explicit shared-checkout
mode. The helper never uses print mode or manually creates a worktree.

For context files, the helper resolves the path before the session changes
directories. For ignored environment files, use the project's `.worktreeinclude`
configuration. Do not automatically copy secrets or install dependencies.

## Phase 3: Report

Report the role or resumed session, goal/task, context file, session name, and
whether the session shares the current checkout or uses native worktree isolation.
For resume, let native restoration determine the checkout. Report launch
failures as failures; starting a session is not evidence that its task completed. Native worktrees
are not adopted by the plugin's automatic cleanup scripts.

## Error Handling

- Missing role or unknown option: show the helper's usage and available agent files.
- Missing Claude Code or tmux: report the missing dependency.
- No tmux session in shared-checkout mode: use an existing session or select a native worktree if isolation suits the request.
- Native trust, worktree, or launch failure: preserve the error and existing work; do not silently substitute manual creation.
- Missing target or native resume failure: report the result; do not create a replacement session. Let native session selection resolve ambiguous names.
- Goal plus task prompt, or resume plus role/name/worktree: reject the conflicting options.

## Example Usage

```text
/agentic-coding-workflow:spawn evaluator
/agentic-coding-workflow:spawn evaluator --context pr-diff.patch
/agentic-coding-workflow:spawn implementer --worktree accounts --goal "The agreed accounts changes are implemented and verified."
/agentic-coding-workflow:spawn --resume accounts
```
