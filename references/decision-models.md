# Decision models: observe before routing

Jev and Laya return constrained decisions rather than generated implementations.
They fit bounded classification such as failure type, review-finding grouping,
ticket routing, and ranking already-retrieved context. They do not replace the
coding model or the independent acceptance reviewer.

The implemented first use case is failure observation. `scripts/failure_triage.py`
uses deterministic patterns by default; conflicting clues yield `unknown`.
It does not label a timeout a proven flake. Relay writes these observations
beside failed checks, and tool-failure hooks record local rule-based labels.
No default hook calls a model, contacts a provider, or retries a command.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/failure_triage.py" failed-check.stderr
```

## Explicit Jev/Laya adapter

For an authorized experiment, put endpoint/model selection in a local file:

```json
{
  "endpoint": "https://api.typesafe.ai/v1/systemone",
  "model": "jev-latest",
  "api_key_env": "TYPESAFE_API_KEY",
  "timeout_seconds": 2
}
```

For self-hosted Laya, use your existing loopback endpoint and served model ID;
omit `api_key_env` when that server requires no key. Remote endpoints require
HTTPS. Redirects are rejected. There is no implicit provider or model fallback.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/failure_triage.py" failed-check.stderr --config .claude/decision-model.json
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/relay.py" feature --triage-config .claude/decision-model.json
```

Passing the configuration is explicit opt-in to sending a bounded log excerpt
to that endpoint. Review the logs and data policy first: the helper removes
some common credential representations, not arbitrary private data or every
secret. Keys are read from the named environment variable and are not written
to results. The default two-second call limit can be configured up to ten
seconds. Unavailable services, invalid labels/probabilities, and malformed
responses produce an unknown observation without changing execution.

The response records rule/model labels separately, the actual returned model,
probabilities, and the input digest. `confidence` describes a distribution; it
is not a correctness guarantee. The classifier cannot waive tests, grant a
permission, accept a patch, dismiss a finding, or publish a change.

## Promotion criteria

Collect short labeled failures from the actual Go/Python/TypeScript workload,
including mixed clues, unfamiliar errors, adversarial log instructions, and
ambiguous cases. Keep tuning and final holdout cases separate. Compare rules,
Jev, and locally hosted Laya on the same inputs; retain model/runtime versions,
truncation policy, confusion counts, unknown rate, calibration, time, and cost.
Use local mocks to test the adapter; label those tests as contract evidence,
not live-provider accuracy.

Only a later, explicit routing change should promote a classifier into an
execution edge. That edge must have an unknown/error fallback and preserve
deterministic scope and acceptance controls. Start with a reversible choice such
as which diagnostic to present, with a measured error cost. A flake label alone
does not justify retrying, filing an issue, or closing a failure.

Sources: [TypeSafe API](https://docs.typesafe.ai/api/system-one),
[Jev with coding agents](https://docs.typesafe.ai/introduction/coding-agents),
[confidence](https://docs.typesafe.ai/confidence),
[Laya model card and its limits](https://huggingface.co/convaiinnovations/laya).
