# Compare

Read the saved plan and linked baseline evidence first. Finish missing baseline
trials before authorized candidate edits. Preserve separate workflow revisions
using project-appropriate isolated checkouts; keep product task fixtures and
graders equivalent. Never replace the user's working checkout to run a trial.

## Choose the existing runner

| Question | Execution and evidence |
| --- | --- |
| Does the change preserve deterministic behavior? | Project-required checks and the existing verification runbook; this plugin uses `make check`. |
| How long do fixed commands take? | `scripts/run-experiments.py` with [the existing matrix format](../../../references/experiments.md). |
| Does the agent still select and complete the workflow correctly? | `scripts/run-evals.py` with [the existing eval conventions](../../../evals/README.md). |
| What happens in a real session, including hooks and review? | The saved task and verification recipe, actual session transcript, and final hook/check evidence. |

These are separate claims. A process exiting zero supports only its actual
assertions. Native plugin evals compare plugin/no-plugin arms; to compare old
and new instructions, run the same versioned cases in both plugin revisions
and compare their **plugin-enabled** results. Keep no-plugin results as controls.
Make the same cases available to both revisions and record the case digest.
Do not assume each revision's default suite is identical.

Run the helpers from the appropriate workflow checkout. Inspect the planned
invocations and reuse the authorized model selectors and budget, allowing
headroom for in-flight calls. If CLI/auth/model access is missing, retain the
native runner's `--dry-run` record with `--not-run-reason`; do not launch a
substitute provider or claim agent behavior was evaluated.

`run-experiments.py` measures whole command processes and groups repeats in
matrix order; it does not measure model phases, interleave arms, or reset
fixtures. Plan order explicitly and reset disposable task fixtures between
trials. Coding trials intentionally mutate their task workspace: keep it
separate from the frozen workflow source, and document this boundary rather
than dismissing a reported source change.

## Preserve each attempt

Append an `evidence` entry for each run or retained runner report. Record arm
(`baseline`, `candidate`, or `shared`), case IDs/split, checked source, command,
outcome, artifact paths, and observed metrics. Include failures, timeouts,
interruptions, and human corrections. Use null for unmeasured metrics.

Measure total time through final required verification, not just the first
response. Record first useful action, model/tool/check/review time, tokens,
cost, and intervention only where actually observable. Distinguish review work
from queue waiting. For suspected duplicate checks, retain command, source,
configuration, and relevant environment; matching command names alone do not
establish duplicate evidence. CI or post-integration checks may add protection.

After implementation, run relevant and project-required checks on the final
candidate. Record the source and verification results separately from model
outcomes. Update `candidate.source`, `stage`, and `next_action`. Failed checks
remain failed until a later, linked attempt proves the correction.

Tune only with tuning cases. Before a final holdout, freeze candidate, cases,
graders, and decision criteria. If holdout feedback informs an edit, mark it
consumed as tuning and reserve fresh final cases. A candidate change invalidates
earlier final-source evidence; retain it as history and repeat affected checks.
