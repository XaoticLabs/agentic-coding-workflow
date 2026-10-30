# Starting case library

Select cases that can falsify the current hypothesis. These are reusable
scenario recipes, not claims that native runs have passed. Keep each selected
case's input, fixture/grader revision, and criteria in the notebook. Adapt
recipes to the consuming project rather than requiring this entire set.

| Scenario | Observable protection | Existing starting point |
| --- | --- | --- |
| Ordinary change | Requested behavior works, configured checks run, no unselected approval or review loop appears. | `evals/runtime-proof-regression/` and project regression fixtures. |
| Explicit optional mode | The selected procedure loads at the right time and its requirement is honored. | `implement --approve-tests` must wait for approval of expectations; `review --learn` uses the teaching path. Use fixture data, without publishing. |
| Resume | Related work retains decisions and acceptance criteria, rechecks current source, and continues from the saved next action. | `evals/resume-feature-session/` and `evals/improvement-resume/`. |
| Required check fails | A genuine product failure blocks completion; missing infrastructure remains incomplete. | `evals/unavailable-runtime-proof/` and `make verify` for this plugin. |
| Unchanged correction turn | Successful Stop verification can be reused without another product-check invocation for the same recorded inputs. | This plugin's local delivery verification runbook and `tests/smoke_delivery.py`. |
| Source changes after success | Previous success is invalidated; a new regression reruns and fails the required check. | The same delivery verification journey. |

For instruction loading, include a native session that confirms which guidance
was actually loaded. File size is a useful diagnostic, not a latency result.
Test ordinary and optional paths so a thinner entrypoint cannot win by skipping
selected requirements.

For review changes, include confirmed-bug and reviewed-clean examples. Measure
useful findings, false findings, repair rounds, and correction effort; comment
count alone does not establish review quality.

The playbook itself has preparation and resume tuning cases under
`evals/improvement-prepare/` and `evals/improvement-resume/`. Use the repository's
native eval runner when authorized. They test notebook behavior, not whether a
particular workflow optimization improves delivery speed.
