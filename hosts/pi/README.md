# Pi adapter

The root `package.json` is an official Pi package manifest. It loads `index.ts`
and the user-invocable native skills under `generated/skills/`. Host-provided
packages stay peer dependencies; Claude installation requires no Node runtime.

After editing canonical commands, skills, agents, or hook registration, run
`make sync-hosts` from the repository root. Generated files are disposable;
edit `commands/`, `skills/`, `agents/`, and `hooks/hooks.json`.

Load this checkout with `pi -e /absolute/path/to/agentic-coding-workflow`, or
install the local package with `pi install /absolute/path/to/agentic-coding-workflow`.
Reload Pi after synchronizing an active installation.

Commands use `/name`; user skills also accept `/skill:name`. Model-only skills
are absent from the native user command catalog and load through the `Workflow`
tool. User-only workflows are absent from automatic skill discovery and are
rejected by the model workflow loader. These invocation controls do not grant
permission for underlying publishing or other actions.

Interactive commands register after Pi selects TUI mode. JSON, print, and RPC
inputs expand through the awaited native input event, so the original prompt
owns the model run and completion checks. Generated executable resources forward
to their canonical scripts, preserving script-relative imports and resources.

The adapter translates native tools to the existing hook protocol, including
file paths, session identity, correction turns, JSON decisions, and terminal
blocking. Hook failures block policy decisions; optional observations remain
advisory. Pi's `agent_before_settle` is the completion boundary. Verification
entries use `agentic-coding-workflow:verification` with `passed` or `blocked`;
JSON callers must inspect them instead of interpreting process exit zero as
verified completion.

`/goal <objective>` continues for up to 100 model turns. Select another finite
bound with `/goal --max-turns N <objective>`. `/goal status`, `pause`, `resume`,
and `clear` operate on native session-persisted state. The model requests
completion through `workflow_goal`; configured verification must pass before
completion is recorded. A goal verdict does not replace independent review.

`task` starts a child Pi process using the canonical role, current parent model,
role effort and turn limit, cancellation, bounded output, and optional owned
worktree isolation. Non-interactive children cannot grant user approvals.
Worker mode (`WORKFLOW_HOST_WORKER=1`) registers only protection/rendering and
turn limits; Relay owns worker verification and acceptance. Explicit role tool
policies are enforced at every call, including nested and newly registered tools.
Ordinary native role sessions persist their role and restore it on resume.

`tests/test_pi_host.py` exercises generation and the installed Pi loader without
provider calls. The native smoke uses real registered hook scripts to exercise
file protection, retry exhaustion, success reuse, source invalidation, invocation
policy and resumed role restrictions. Set `WORKFLOW_REQUIRE_PI=1` to fail rather
than skip when Pi is missing. `hosts/versions.json` records the tested host.
