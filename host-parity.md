# Host support: Claude Code, Pi, and Autolith

Claude's workflow definitions are canonical. Pi and Autolith use generated
resources and native adapters, with the existing Python and shell scripts
providing verification, tickets, worktree ownership, and Relay supervision.

Edit `commands/`, `skills/`, `agents/`, or their bundled resources, then run:

```bash
make sync-hosts
```

The synchronizer parses YAML frontmatter, builds `hosts/catalog.json`, generates
both hosts' resources, preserves text and binary supporting files, and removes
obsolete generated files recorded in `hosts/generated-files.json`. It does not
change Claude's definitions. `make check` rejects generated drift; it never
regenerates files as a side effect. Do not hand-edit manifest-listed output.

Hook adapters read `hooks/hooks.json` at runtime and invoke its actual scripts.
Changing an existing hook's implementation or registration propagates through
that shared implementation. A new native lifecycle event or tool capability
still needs an explicit adapter mapping and tests.

## Installation

The API baselines are Pi `1.4.0` (`@earendil-works/pi-coding-agent`) and Autolith
`0.67.11`. Versions and Autolith release checksums are pinned in
`hosts/versions.json`. Official sources:

- [Pi](https://github.com/earendil-works/pi)
- [Autolith](https://github.com/lambda-symbolics/autolith)

Install the optional hosts explicitly:

```bash
make install-hosts
```

This installs under `~/.local`; add `~/.local/bin` to `PATH`. The installer
requires Node 22.19+, npm, curl, jq, and tar. It downloads a pinned, checksum-verified
Autolith release and installs Pi without npm lifecycle scripts. Use
`bash scripts/install-hosts.sh --prefix /absolute/prefix` for another location.
Autolith builds its packaged Lisp images on first use.

Claude marketplace installation and `make setup` do not install either host.
The generator's YAML parser is a locked development dependency; installed host
adapters and the shared Python bridge do not require it. Default Claude checks
do not require Node, Pi, or Autolith.

## Loading the workflow

From a consuming project, load this repository's Pi package:

```bash
pi install /absolute/path/to/agentic-coding-workflow
pi
```

For a single invocation, use `pi -e /absolute/path/to/agentic-coding-workflow`.
After synchronizing an already-running package, use Pi's `/reload` or restart it.
The root `package.json` declares extension and generated skill locations; host
packages are peers provided by Pi, with no bundled npm dependencies.

Autolith uses an absolute native site root:

```bash
autolith --site-config-root /absolute/path/to/agentic-coding-workflow/hosts/autolith
```

Restart Autolith after synchronization to reload generated command operations
and roles. A site is trusted configuration, not an operating-system sandbox;
native permissions and any project containment remain in force.

| Entry | Claude | Pi | Autolith |
| --- | --- | --- | --- |
| User command | `/agentic-coding-workflow:implement` | `/implement` | `/workflow-implement` |
| User skill | `/agentic-coding-workflow:relay` | `/relay` or `/skill:relay` | `/workflow-relay` |
| Model-only skill | Native skill discovery | `Workflow` loader | Native `skill.load` |
| Explicit user-only workflow | Native invocation flag | Command authorization and native discovery filtering | User operation; excluded from native model skills |
| Role | Native agent | Restricted child Pi session | Generated native child role |

The catalog contains every current command, skill, and agent. An empty skill
directory without `SKILL.md` is not a definition. A model-only skill has no user
command. A user-only workflow is not advertised to the model as automatically
loadable. These are invocation controls; they do not grant publishing authority.

## Shared rendering

`scripts/host-bridge.py render` loads an entry from the generated catalog and
resolves package/project roots, invocation names, arguments, native tool names,
and authored dynamic context such as `prime`'s context script. Dynamic context
runs before user arguments are inserted, so arguments cannot introduce new
preprocessing commands. Package-authored snippets run in the consuming project.

`render-text` adapts bundled Markdown as the native host reads it. Supporting
scripts, references, and assets stay available in generated skill directories;
rooted shared-script references continue to point to the original package,
not to the Autolith site directory.

Generated executable entrypoints forward to the canonical scripts so Python
imports and shell paths retain their original repository layout. Other resource
files are copied, including binary assets. Both forms update from the same
canonical source.

`allowed-tools` remains approval metadata, not a tool allowlist. Actual role
restrictions come from native tool selection and the adapter's call boundary.
Native authorization behavior can differ between hosts; the adapter does not
automatically approve tools to emulate another host's permission prompts.

## Hooks and completion

The shared `event` bridge translates registered scripts into three decisions:

- `allow`: this event has no outstanding policy block.
- `repair`: deny a tool call, or continue work after a failed completion gate.
- `halt`: stop with an explicit blocked result after exhaustion or unavailable policy.

Both JSON output and process exit matter. In particular, exit zero with
`decision: block` is a failure, and `continue: false` is terminal blocking rather
than acceptance. Correction turns preserve native session identity and set
`stop_hook_active`, reusing the existing three-attempt counter. A new user turn
can retry; a pass is reused only for the same revision and working inputs.

| Shared event | Pi boundary | Autolith boundary |
| --- | --- | --- |
| Session readiness | `session_start` | Native application input/session setup |
| Dangerous shell and `.env` protection | `tool_call`, including input-field translation | Native `tool-execute` interception for shell and resource reads/edits |
| Advisory quick check | Successful write/edit `tool_result` | Successful native resource edit |
| Tool failure observation | Error `tool_execution_end` | Native failed tool result |
| Required completion verification | `agent_before_settle` | Native `agent-turn-complete-p` interception |
| Desktop readiness/input notices | Verified settlement after deferred continuations drain, or blocking UI prompt | Native final idle/input boundaries |
| API failure evidence | Provider events, log only | Native wrapper observations, log only |

Autolith's completion interceptor covers ordinary primary turns without a
custom verification fact. Native mission gates remain available for explicit
missions. Site methods preserve Autolith's own context, authorization, and
telemetry methods; they are version-sensitive integration points covered by
the installed-host smoke tests.

Pi supplies an explicit persistent `/goal` workflow with bounded continuation.
Autolith retains native goals and missions. Their lifecycle controls and native
API-failure payloads are host-specific; this is behavioral adaptation rather
than an identical Claude session implementation.

Desktop delivery belongs to the owning primary session. Native Claude
`Notification` events report actual idle/input waits, rather than per-response
Stop events. Pi waits until native settlement handlers and their deferred
continuations have drained, suppresses completion alerts for aborted, blocked,
queued, or unfinished goal states, and coalesces repeated dialogs within a paused
input episode. This final observation uses the pinned Pi runtime's settlement
boundary and is covered by a real-host continuation regression. Verification retries, API failures, and Relay status changes never
produce their own desktop alerts. Native smoke checks capture or suppress all
desktop delivery.

User questions and planning use Pi's native extension UI. Autolith instruction
rendering asks in the assistant response and requires waiting for the reply or
plan approval, since it has no matching Claude question/plan tools. Headless
workers report unavailable interaction rather than fabricating approval.

## Relay, sessions, and parallel work

Select a host explicitly; Claude remains the default:

```bash
WORKFLOW_HOST=pi bash scripts/spawn-session.sh implementer --worktree example "Implement the agreed change"
WORKFLOW_HOST=autolith python3 scripts/relay.py example --once
```

Relay and its evaluator also accept `--host`. A selected missing host fails
explicitly; it never falls back to Claude. A run records its selected host and
checks compatibility on resume.

`scripts/host-runner.py` adapts sessions and bounded jobs. Pi uses native JSON
events; Autolith uses `run-job` with a bounded, data-only S-expression contract.
Both implementation and independent evaluation use the selected host.
Transport success is checked separately from structured output, tool policy,
project verification, and controller acceptance. Requested models are not
reported as observed model provenance.

Relay workers suppress ordinary completion hooks because the controller owns
verification, attempts, commits, budgets, integration, and acceptance. Evaluator
workers have read/search tools and no shell, editor, or MCP grant. Runtime
verifiers retain their canonical shell capability; their no-product-edit rule
does not claim an operating-system read-only shell.

The existing worktree ownership primitives remain authoritative. Shared shell
pipelines and rendered parallel instructions select the host runner. Pi resume
resolves an existing native session rather than silently creating another one.
Autolith uses its native saved conversation behavior. Native session controls
and terminal layouts are not byte-identical across hosts.

## Verification

```bash
make setup
make sync-hosts
make check
make check-hosts
```

`make check` runs the normal Claude-repository checks, generator drift detection,
cross-host deterministic contracts, and local product verification. Native tests
report a skip when the relevant optional host is unavailable.

`make check-hosts` requires both installed hosts. It exercises actual native
loaders, generated invocation policy, shared dangerous-command checks,
completion failure/repair/exhaustion, source-change invalidation, restricted
workers, and native result transports. Transport exercises use a local fixture
provider with isolated credentials and no paid model calls. CI runs this as a
required separate host job with pinned installations.

Evidence is retained under `.claude/proofs/hosts/`; reusable isolated Autolith
images are under `.claude/host-tools/`. These checks establish local integration
behavior, not real-provider reasoning quality or live external integrations.
Authentication, browser interaction, external tickets, and provider-specific
failures require their own authorized runtime evidence.
