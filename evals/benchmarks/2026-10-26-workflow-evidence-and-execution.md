# Model selection, runtime evidence, and private execution

Date: 2026-10-26. Baseline: `b5eac7063d098fba4e614b310f5e02fce2aab620`.
Candidate: the uncommitted changes accompanying this record. No commit, model
uplift, production result, or company rollout is claimed.

Candidate content fingerprint: `ea5849ead13f2dc6af5e25a303cdfec1bd6b439f1597242af868f459cf79eca6`.
The digest covers changed/new versionable paths, file modes and bytes, excluding
this record. Unchanged source is identified by the baseline commit. Ignored raw
reports are retained locally rather than included in this content digest.

## Observed checks

| Check | Result |
| --- | --- |
| Final complete repository suite | PASS: 419 tests in 166.96 seconds |
| Ruff checks and formatting for changed/new Python tooling and tests | PASS |
| Shell syntax and registered hooks | PASS: all six registered hook scripts valid |
| Nine skill entrypoint structural diagnostics | PASS; this is not behavioral evidence |
| Relative Markdown targets before adding this evidence record | PASS: 42 targets resolve |
| Native `claude plugin validate .` | PASS with warnings; CLI 2.1.310 |
| Real Podman environment smoke | PASS: concurrent setup/services, source preservation, candidate patch, readiness failure, timeout, owned cleanup |
| Executed experiment comparison | PASS: two equivalent arithmetic implementations, three trials each; JSON/logs/filterable HTML retained |
| `git diff --check` | PASS |
| Docker backend / manual GitHub container job | NOT_RUN locally; the workflow is available for explicit dispatch |
| Native model evaluations | NOT_RUN at user request after CLI reported unauthenticated |
| Production observations, remote mutations, schedules | NOT_RUN; no actual target or schedule selected |

The final suite used the existing complete cached environment (Python 3.13.13,
pytest 9.1.1), including subprocesses:

```bash
env PATH="/home/xaotic/.cache/uv/archive-v0/8HyW871a6fRDVXir/bin:$PATH" \
  python3 -B -m pytest -q --tb=short
```

That path is machine-specific. Ruff was 0.15.21. The system Python's incomplete
pytest installation was not used. New runtime tooling uses the standard library
and supports Python 3.11+; the real container exercised Python 3.11.

The smoke image was built from the checked-in Containerfile, then selected by
local immutable image ID:

```bash
python3 tests/smoke_environment.py \
  --image sha256:909342da84869edb17602907e2bd2913374ef965930be22888fde2c24c78fb9f \
  --output-dir .claude/proofs/environment-final-20261026
```

The smoke ran with the filesystem access needed by rootless Podman. Two apps
used port 8080 concurrently in separate containers. Both verified current
uncommitted source and explicit setup, and produced private candidate changes.
Readiness failure and whole-container timeout returned errors. Original source
was preserved and all four uniquely owned containers were absent afterward.
Run records include source, recipe, and copied-tooling fingerprints.

## Behavioral evaluation and limits

New tuning cases are `runtime-proof-regression` and `unavailable-runtime-proof`.
Deterministic checks confirmed that the first fixture fails on its known bug and
passes after a production-code fix without changing expectations; the second
really fails with a missing executable. Their native graders have not been
calibrated against model runs. Existing holdout cases were not run or consumed.

Runs per arm: zero. Observed execution/judge models, outcome deltas, and native
model duration are unavailable. Model spend: **$0**. The user authorized up to
$10, then explicitly deferred paid runs because native authentication was absent.
The prepared runner invocation uses both arms, one exploratory trial, concurrency
one, requested `best` selectors, and a $5 ceiling with headroom. These selectors
were not resolved; a final comparison should pin the intended model versions.

Local raw artifacts: `.claude/proofs/environment-final-20261026/`,
`.claude/proofs/workflow-validation/`, and
`evals/results/2026-10-26-workflow-recommendations-final/`. The validation log
retains warnings about existing metadata, command descriptions, and hook-path
quoting. Standards checks do not establish better agent decisions.

The environment runner is an explicit project-owned Linux container workflow.
Trusted external policy/credential brokering, restricted endpoint egress, and
tamper-proof acceptance remain outside this change. Observations exercise
configured commands; fixture checks do not establish production health. The
arithmetic comparison demonstrates the comparison tool, not a general speedup.
