# Reproducible setup and unattended execution plan

Status: planned. Baseline: `1e4368b`, reviewed 2026-10-25.

Extend the project command registry into reproducible execution recipes and add
a trusted launcher that contains the entire unattended workflow. Estimated
effort is **10–15 engineer-days, roughly 2–3 working weeks**, for one tested Linux
isolation backend with existing container or VM infrastructure. Other operating
systems, additional backends, and a production credential broker add scope.
This plan records future work; it does not implement or activate unattended runs.

Coordinate deterministic coverage and CI integration with the adjacent
[harness regression suite plan](harness-regression-suite.md). Keep recipe and
boundary tests free of paid model calls.

Progress note, 2026-10-25: project readiness now reports command configuration,
and review launchers no longer guess/install dependencies. Go/Python/Node/mixed
verification requires selected checks. Reproducible setup recipes, service
lifecycle management, and trusted containment below remain future work.

Progress note, 2026-10-26: the explicit project-owned private environment runner
now exports current source, uses pinned images and bounded resources, runs selected
installation before service readiness and verification, preserves logs/candidates,
and cleans up owned containers. A real concurrent Podman smoke test passed.
Trusted external policy/credential brokering, endpoint egress enforcement, and
acceptance records outside agent control remain future work below. The new runner
does not automatically contain existing host workflows.

## Current foundations and gaps

- [Project commands](../../scripts/project-commands.py) centralize `build`,
  `test`, `lint`, `format`, and `run` as strings or explicit disables. They lack
  installation, separate type checking, per-command directories, prerequisites,
  exit-code expectations, and timeout behavior.
- [Review setup](../../scripts/review-in-worktree.sh) now inspects configuration
  without installing dependencies. A shared reproducible setup executor is
  still needed. The optional [Python profile](../../profiles/python/uv-ruff-basedpyright/)
  already separates formatting from checks and uses `--frozen --no-sync`.
- [Ralph](../../skills/ralph/scripts/loop.sh) hardcodes
  `--dangerously-skip-permissions`. The shared [Claude runner](../../scripts/lib/claude-runner.sh)
  records pipeline statuses and supports invocation deadlines, but does not
  provide whole-workflow isolation or resource limits.
- [Stop checks](../../hooks/lib/lint-project.sh) and the controller's final
  [verification gates](../../scripts/lib/parallel-primitives.sh) execute project
  commands directly. Wrapping only the Claude invocation would leave these
  paths, dependency setup, and other helpers outside the boundary.
- [Verification state](../../hooks/verification-state.py) already fingerprints
  source and configuration. The restricted [evaluator](../../scripts/evaluate.py)
  demonstrates explicit tools, MCP exclusion, and noninteractive permissions.
  Neither agent-writable records nor instructions authenticate acceptance.
- [CI](../../.github/workflows/tests.yml) installs unpinned pytest. The root
  [ignore file](../../.gitignore) ignores `uv.lock`; revisit that rule if this
  repository explicitly adopts uv. Preserve consuming projects' existing stacks.

## Implementation

1. **Define versioned recipes — 2–3 days.** Extend the existing registry with
   `install` and `typecheck`, preserving supported string commands and explicit
   disables through migration. Define invocation arguments or an explicit shell,
   project-relative working directory, runtime and package-manager versions,
   required environment variable names, services, expected exit codes, outputs,
   wall-clock timeout, and termination grace period. Model application readiness,
   startup deadline, lifetime, and teardown separately from one-shot completion.
   Required, optional, and inapplicable actions must have distinct semantics.
   Missing or disabled required checks cannot count as successful verification.

   Resolve the package manager from declared project configuration, workspace
   layout, lockfiles, and existing CI. Reject ambiguous or conflicting inputs.
   Preserve dependency groups and manager configuration. Use immutable install
   behavior, such as `npm ci` or `uv sync --locked`, without fallback to dependency
   resolution. Keep lockfile updates deliberate and separate from installation.
   Verification must not install dependencies or apply fixes. Validate metadata
   and environment preparation before relying on uv's `--frozen --no-sync` checks.

2. **Implement the shared runner and migrate callers — 2–3 days.** Route CI,
   review setup, Stop checks, Ralph workers, and final gates through one recipe
   executor. Prefer argument arrays; retain explicit shell recipes for existing
   compound commands with pipe failure handling. Validate working-directory
   containment and environment prerequisites before execution. Supply a clean,
   allowlisted environment and reference secrets without storing their values
   in recipes or reports.

   Enforce deadlines with process groups and the selected environment's resource
   controls. Terminate, wait for the grace period, then kill remaining processes;
   supervise the whole environment so detached descendants cannot outlive a run.
   Record command, directory, duration, raw exit code or signal, stdout/stderr,
   and a distinct outcome for failure, timeout, unavailable prerequisites, and
   skipped work. A long-running application's successful readiness probe does
   not mean the application should exit zero immediately. Bind evidence to the
   candidate, recipe, lockfile, toolchain/image, and profile identifiers.

3. **Add a trusted execution profile and one Linux backend — 3–4 days.** Keep
   enforcement in a launcher and policy location the agent cannot modify. A
   project recipe declares needs; the trusted profile grants capabilities.
   Select one maintained container or VM backend and document its threat model.
   Prefer a disposable VM or microVM when repository code is untrusted. For an
   OCI backend, use a non-root user, restricted capabilities, syscall controls,
   and resource limits; prohibit privileged mode and the host Docker socket.

   Enclose dependency installation, Claude, approved hooks, local MCP processes,
   application services, and final verification. Use an independent clone with
   private Git metadata; worker worktrees may live inside it. Avoid writable
   mounts of the host checkout, home, shared configuration, and shared caches.
   Provide private temporary storage and per-run writable caches, with trusted
   tooling and policy mounted read-only.

   Default network access to denied. Declare exact provider endpoints, registry
   access during setup, and isolated service access by phase. Block unintended
   host, LAN, and cloud metadata access, and test alternate connection paths.
   Domain access is not authorization to mutate a remote service. Use narrowly
   scoped, short-lived credentials, and broker provider authentication where the
   backend supports it. Disable SSH-agent forwarding and undeclared sockets.

   Permit editing, build/test commands, and local commits. Keep publishing,
   deployments, remote writes, and production access behind a separate trusted
   executor with authorization bound to the exact action. Pin approved plugins,
   hooks, and MCP configurations. Account separately for remote MCP authority
   and gateways that execute tools on the host. Give every worker the same
   enforced profile and independent writable state.

4. **Enforce acceptance outside agent control — 1–2 days.** Replace unconditional
   permission bypass with profile-selected permissions. Default to `dontAsk`
   with explicit grants and controlled configuration sources; distinguish
   approval grants from tool restrictions. Allow bypass only when the trusted
   launcher has established the required outer isolation boundary. Fail startup
   when containment or required controls are unavailable; do not retry on the
   host or silently weaken the profile.

   Snapshot approved recipes, required checks, and policy at run start. Proposed
   edits to them require review before adoption as authority. Run final checks
   through trusted tooling against the exported candidate in a fresh isolated
   environment. Keep authoritative results outside agent-writable storage.
   Reject changed inputs, stale results, missing checks, and incomplete runs.
   Export changes and redacted evidence through a controlled path; preserve
   unfinished work before deleting the disposable environment. Resume only
   after rechecking source, policy, and environment state.

5. **Prove the boundaries and document operation — 2–3 days.** Add deterministic
   fixtures for clean setup, lockfile disagreement, manager selection, paths
   with spaces, absent prerequisites, nonzero exits, readiness failures,
   timeouts, interruptions, and detached child cleanup. Verify that all callers
   consume the same recipes and that required skipped checks block acceptance.

   Attempt forbidden access through shell commands, built-in file tools, hooks,
   and local MCP processes. Cover symlink/path escapes, secret reads, inherited
   environment variables, blocked destinations and sockets, host Git metadata,
   policy changes, and fabricated verification records. Test unavailable
   isolation and crashing or timed-out policy hooks. Exercise remote integrations
   through stubs with explicit capability limits. Add backend integration checks
   on a suitable CI runner, alongside unit tests that need no virtualization.
   Document provisioning, profile inspection, limits, failure recovery, artifact
   retention, credential revocation, and environment deletion.

## Current documentation constraints

Documentation was checked on 2026-10-25; recheck supported versions and backend
behavior when implementation starts. The current environment has no `claude`
on PATH, so native configuration validation remains implementation work.

- Claude's built-in shell sandbox does not contain file/web tools, hooks, or
  MCP servers. Default shell reads and inherited environment variables can
  expose credentials. If retained as an additional layer, enforce sandbox
  startup failure, disable unsandboxed retries, control excluded commands, and
  configure read, credential, and network restrictions through trusted settings.
  Inspect effective policy; a checked-in settings file alone does not lock
  inherited or merged grants.
- The standalone sandbox runtime can enclose the entire Claude process and its
  local children, but remains a beta research preview. Pin tested versions and
  explicitly protect writable configuration paths. It does not contain remote
  services or host processes reached through external integrations.
- `onFailure: "block"` requires Claude Code v2.1.295 or later for eligible
  command/HTTP hooks. It has no effect on Stop hooks, so a Stop hook cannot be
  the sole final acceptance gate. Newer managed sandbox protections have their
  own version requirements; validate supported settings rather than assuming
  the existing evaluator's minimum version covers the new profile.
- Docker Sandboxes provides microVM isolation and private-clone operation, but
  its MCP gateway can launch local servers on the host. Review network defaults,
  mounts, shared stores, credential handling, and forwarded sockets before
  selecting it as the backend. Stopping a sandbox does not delete its state.
- Isolation limits access and impact. Allowed network channels can still carry
  readable data, and sandboxing does not change what is sent to the model.

## Completion criteria

A fresh supported environment installs and verifies the same candidate from the
declared recipes without changing lockfiles. Local commands, CI, review sessions,
and Ralph use the same contract. Required checks produce attributable evidence
or an explicit failed/incomplete outcome, and application recipes demonstrate
readiness and reliable teardown.

Every phase executing project code stays inside the declared boundary. Negative
tests demonstrate denied host access through each available tool path and no
surviving processes after timeout. The agent cannot widen its authority, change
the authoritative required checks, or manufacture an accepted result. Reports
identify the exact candidate and configuration; external actions require their
own trusted authorization.

## References

- [Claude shell sandbox](https://code.claude.com/docs/en/sandboxing)
- [Claude isolation approaches](https://code.claude.com/docs/en/sandbox-environments)
- [Claude permissions](https://code.claude.com/docs/en/permissions)
- [Claude CLI controls](https://code.claude.com/docs/en/cli-reference)
- [Hook failure behavior](https://code.claude.com/docs/en/hooks#block-the-action-when-a-hook-fails)
- [uv locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/)
- [npm ci](https://docs.npmjs.com/cli/v11/commands/npm-ci/)
- [Docker Sandboxes architecture](https://docs.docker.com/ai/sandboxes/architecture/)
- [Docker Sandboxes security](https://docs.docker.com/ai/sandboxes/security/)
