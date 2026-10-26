# Skill authoring cleanup: validation and benchmark status

Date: 2026-10-25. Candidate and case/graders revision: the change containing this
summary, prepared against parent
`f74ef8567b6a0b1c0911b30d1f6f07da72bc35e3`. No candidate has been selected using
holdout scores. Holdout status: reserved, not executed or used as feedback.

## Standards validation and repository checks

| Check | Result |
| --- | --- |
| `validate-skill.py` on each of the nine `skills/*/SKILL.md` entrypoints | PASS: zero structural errors or warnings; behavior not evaluated |
| Local YAML and entrypoint inventory | PASS: no duplicate command/skill names; explicit invocation fields parse as booleans; six tuning and two holdout cases, each with graders |
| `bash scripts/validate-hooks.sh` | PASS: hook registration and all ten hook scripts valid |
| Full repository test run | 261 passed, six failed because nested pytest commands used the incomplete system Python (162.83 seconds) |
| Targeted rerun of the six affected cases with the complete environment on `PATH` | PASS: six passed, 65 deselected (8.28 seconds); all 267 collected cases have passing evidence across these runs |
| `git diff --check` | PASS |
| `claude plugin validate .` | NOT_RUN: Claude Code CLI is not installed in this environment |

The default `python3 -m pytest -q` could not collect tests because its pytest
installation lacks `pygments`. A complete, locally cached environment was
available (Python 3.13.13, pytest 9.1.1); no dependencies were downloaded and no
test expectations or runner settings were changed. The full run command was:

```bash
/home/xaotic/.cache/uv/archive-v0/8HyW871a6fRDVXir/bin/python -B -m pytest -q
```

Its six failures were in `test_review_allows_changes_in_a_red_test_file` and
`test_integrity_rejection_blocks_passing_tests_without_a_red_commit`, whose
nested commands resolve `python3` from `PATH`. After confirming that dependency
failure, the targeted rerun passed with the complete environment inherited by
subprocesses:

```bash
env PATH="/home/xaotic/.cache/uv/archive-v0/8HyW871a6fRDVXir/bin:$PATH" \
  python3 -B -m pytest -q tests/test_ralph_pipeline.py \
  -k 'review_allows_changes_in_a_red_test_file or integrity_rejection_blocks_passing_tests_without_a_red_commit'
```

The cache path is environment-specific. Other checkouts should use their own
complete test environment with `python3 -m pytest -q`.

## Behavioral benchmark

Commands prepared for a trusted checkout with Claude Code and model access:

```bash
claude plugin eval . --tag tuning --allow-tools Write Edit --no-publish
claude plugin eval . --tag holdout --allow-tools Write Edit --no-publish
```

The holdout command is for a frozen candidate and criteria, after tuning.
Neither command ran here: Claude Code is unavailable. CLI version, execution
model, judge model, cost, and duration are unavailable. Runs per arm: zero.
No reports or transcripts were generated, and no inference about effectiveness
can be made from the standards checks above.

| Case | Split | With plugin | Without plugin | Outcome delta |
| --- | --- | --- | --- | --- |
| `skill-forge-small-skill` | Tuning | NOT_RUN | NOT_RUN | Unavailable |
| `skill-forge-near-miss` | Tuning | NOT_RUN | NOT_RUN | Unavailable |
| `native-goal-workflow` | Tuning | NOT_RUN | NOT_RUN | Unavailable |
| `spawn-native-goal` | Tuning | NOT_RUN | NOT_RUN | Unavailable |
| `spawn-native-worktree` | Tuning | NOT_RUN | NOT_RUN | Unavailable |
| `resume-feature-session` | Tuning | NOT_RUN | NOT_RUN | Unavailable |
| `skill-forge-repair-skill` | Holdout | NOT_RUN | NOT_RUN | Unavailable |
| `skill-forge-explicit-deploy` | Holdout | NOT_RUN | NOT_RUN | Unavailable |

Triggering diagnostics are also NOT_RUN. The two holdout rubrics check
observable behavior and policy preservation; they were authored with this
change and have not been calibrated by model runs. Add a new dated summary
with per-arm pass counts, models, revisions, failures, report locations, cost,
and duration when evaluations become available. Retain this record of missing
evidence rather than replacing it with an inferred score.
