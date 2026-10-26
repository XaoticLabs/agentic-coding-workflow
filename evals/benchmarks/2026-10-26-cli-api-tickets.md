# CLI/API tickets and delivery handoff: validation evidence

Date: 2026-10-26. Baseline: `10bd4b4`. Candidate: the uncommitted working
tree containing the CLI/API ticket resolver, read-only PR status helper,
workflow integration, references, deterministic tests, and two tuning cases.

Candidate fingerprint: SHA256
`08d8dfa297bca8c9282a7427b08b5d39ba0a61112a2a2ff4af87b311b3313299`.
The digest covers 20 changed/new versionable files, sorted by path, each
hashed as UTF-8 path, NUL, file bytes, NUL. It excludes this evidence record
and ignored runtime/planning artifacts. No candidate commit or live run is
claimed.

## Observed checks

| Check | Result |
| --- | --- |
| Final full repository suite | PASS: 396 tests in 160.29 seconds |
| Focused ticket and PR status suite | PASS: 74 tests |
| Ruff check of the two new scripts and two test files | PASS |
| Ruff format check of those four files | PASS |
| `bash scripts/validate-hooks.sh` | PASS: six registered scripts valid |
| Relative documentation targets | PASS: 19 targets resolve |
| `git diff --check` | PASS |
| Resolver/PR helper CLI help and local connection diagnostics | PASS: unavailable connections reported without installing tools or changing auth |
| `claude plugin validate .` | NOT_RUN: Claude Code CLI unavailable |
| Native plugin/model evaluations | NOT_RUN: Claude Code CLI/model access unavailable |
| Live Jira/Linear reads, state transitions, and PR links | NOT_RUN: provider CLI/credentials unavailable in this environment |
| Live GitHub PR feedback retrieval and follow-up | NOT_RUN: no live PR selected; CLI/API responses exercised using fixtures |

The final suite used Python 3.13.13 and the existing complete cached test
environment, inherited by subprocess tests:

```bash
env PATH="/home/xaotic/.cache/uv/archive-v0/8HyW871a6fRDVXir/bin:$PATH" \
  python3 -B -m pytest -q --tb=short
```

The cache path is environment-specific; no packages were downloaded. The system
pytest environment lacks `pygments`. New runtime scripts use only the standard
library and target Python 3.11+, but a separate Python 3.11 run was not performed.

## Coverage and limits

Tests cover ambiguous tracker selection, configured site/workspace boundaries,
ACLI-first reads, separate API credentials, scoped Jira gateway identities,
unavailable-operation fallback, refusal to fall back after CLI failure, real
subprocess invocation with spaced paths, JSON/HTTP wire behavior, GraphQL partial
errors, native state discovery, preview versus apply, same-named status IDs,
verified transitions, uncertain writes without replay, and idempotent API link
payloads. PR tests cover missing/pending/failed checks, neutral Bugbot checks with
unresolved findings, outdated threads, pagination/incomplete responses, changed
HEAD during retrieval, and handoff without merge authorization.

Provider fixtures follow documented interfaces; these tests do not certify a
particular installed ACLI/third-party Linear CLI version, production credential
scope, or live API response. The workflow flags are agent command instructions;
the three-round and conversational time budgets are not a new trusted executor.
The snapshot helper reads state and does not itself repair/push or enforce
branch protection. No tickets, remote settings, branches, or PRs were changed.

Native model runs per arm: zero. Execution/judge model, cost, task success, and
delivery speedup are unavailable. The new `ticket-cli-api-routing` and
`delivery-follow-up` cases are **tuning** cases, with prompts and graders present
but not executed. Existing holdout cases were not run or consumed. A future
live-provider smoke check and representative team pilot must report their own
outcomes separately from these deterministic checks.
