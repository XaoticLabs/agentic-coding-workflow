# Lifecycle observations and scheduled follow-up

Expose canonical read-only commands in the consuming project's existing
`.claude/project-commands.json`: `health`, `logs`, `deploy_status`, `flag_status`.
Keep targets and commands project-owned; do not guess providers or clusters.

```json
{
  "health": "./ops/health --target \"$WORKFLOW_TARGET\"",
  "logs": "./ops/logs --target \"$WORKFLOW_TARGET\" --since 10m",
  "deploy_status": "./ops/deploy-status --target \"$WORKFLOW_TARGET\"",
  "flag_status": "./ops/flag-status --target \"$WORKFLOW_TARGET\""
}
```

Run selected observations and retain target, timestamp, source state, commands,
raw exits, and output:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/observe-project.py" --target staging --actions health deploy_status
```

Exit zero means configured commands completed; interpret their actual output
against the expected build/rollout/flag state. Missing commands, failures,
timeouts, or changed source prevent a clean observation result. Reads do not
authorize deployments, flag changes, releases, or customer emails. Use existing
authorization and native connectors/CLI for those actions.

When requested, use native scheduling for later checks: a specific deployment
in two hours, or `/loop 5m` with an explicit read-only observation command until
the expected build is healthy. Retain target, expected condition, cadence,
expiry, notification destination, and stop/cancellation condition. Confirm that
scheduling actually activated; a written intention is not a scheduled task.

Session `/loop` requires an open session to run. Use persistent cloud schedules,
Desktop schedules, or GitHub Actions for independent execution. Prefer native
events where CI/providers can deliver them. Do not add another heartbeat engine.
Explicit-only publishing/worker skills cannot be automatically invoked by a
scheduled slash prompt; schedule observations and keep further actions within
existing authorization and limits.

Source: [native scheduling options](https://code.claude.com/docs/en/scheduled-tasks).
