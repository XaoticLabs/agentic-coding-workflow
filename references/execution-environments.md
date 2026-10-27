# Reproducible private execution

`scripts/project-environment.py` runs project commands and an optional agent
command in a private Linux Podman or Docker container. It copies current tracked
and nonignored source, preserving edits/deletions. Host Git metadata, ignored
credentials, home directories, and sockets are not mounted. Candidate source,
logs, and a patch remain under `.claude/environments/`; original source is never
updated automatically.

Prepare a project image containing Python 3.11+, Bash, Git, the required runtime,
and any agent CLI. Pull/build it explicitly and save its digest in
`.claude/project-environment.json`:

```json
{
  "version": 1,
  "engine": "podman",
  "image": "registry.example/team/dev@sha256:REPLACE_WITH_64_HEX_DIGEST",
  "network": "none",
  "cpus": 2,
  "memory": "2g",
  "pids_limit": 256,
  "timeout_seconds": 600,
  "pass_env": [],
  "services": [
    {
      "name": "app",
      "command": ["python3", "-m", "http.server", "8080"],
      "ready": ["python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080', timeout=2)"],
      "timeout_seconds": 20
    }
  ]
}
```

Keep immutable installation and existing checks in `.claude/project-commands.json`:

```json
{"install": "npm ci", "lint": "npm run lint", "test": "npm run test:integration"}
```

From the consuming project:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/project-environment.py" --dry-run --actions lint test
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/project-environment.py" --actions install lint test
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/project-environment.py" --actions install -- claude -p "Implement the agreed task and verify it"
```

`install` is explicit and must be first. It runs before service startup;
remaining actions run after readiness checks. Checks never install implicitly.
Missing/disabled selected actions fail. Images are never pulled implicitly.
Use lockfile-preserving installs and prebuilt images for offline work. Explicit
`bridge` networking enables setup/provider access; `none` is the default.
`pass_env` names forward required values without placing them in argv/reports;
commands must still avoid printing secrets.

Services share their run's network/filesystem, so concurrent runs can use the
same internal ports. Services must stay in the foreground. Startup, command,
and whole-container deadlines are distinct. Cleanup targets only the uniquely
owned container. Unfinished source/logs remain on failure. `--include relative/file`
copies a needed ignored spec/fixture explicitly. Secret paths, symlinks,
external paths, and nonregular entries are rejected; special exports such as
submodules require a project-specific export strategy.

The image must support the invoking user's numeric UID/GID and a read-only root
filesystem; `/tmp` and the private XDG cache remain writable. Resources are
bounded and capabilities dropped. Invoke this runner around the whole workflow;
installing the plugin does not automatically contain existing host hooks/Relay.
No native permission bypass is added.

This project-owned runner supplies isolation for trusted development work.
Trusted policy/credential brokering for untrusted code and production authority
remain separate planned work. Bridge networking is not an endpoint allowlist,
and writable artifacts are not trusted acceptance records.

## Exercise the runner itself

The opt-in `tests/smoke_environment.py` creates a disposable fixture and proves
installation before readiness, two simultaneous apps on the same internal port,
current source export, host-source preservation, candidate patches, readiness
failure, timeout, and owned-container cleanup. Build the checked-in
`tests/fixtures/environment/Containerfile`, inspect the resulting local image ID,
and pass that pinned ID with `--image` and a new `--output-dir`.
The existing GitHub test workflow exposes this as the manual `container_smoke`
option and retains results. Ordinary PR tests use local fixtures without containers
or paid model calls. Docker CI and local Podman are separate backend evidence;
report which actually ran.
